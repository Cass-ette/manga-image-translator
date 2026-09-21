# Swift macOS Frontend for Manga Image Translator - Design Document

**Date**: 2026-09-21  
**Author**: User & Claude Collaboration  
**Status**: Draft

## Executive Summary

This document specifies the design for a native macOS application using SwiftUI that provides a graphical frontend for the manga-image-translator Python backend. The application achieves feature parity with the existing Windows version (MangaStudio) while adding macOS-specific enhancements.

**Core Goal**: Replace the web-based UI with a native macOS experience that offers real-time progress tracking, batch processing, and comprehensive configuration management.

**Why**: The current web UI suffers from poor progress visibility ("pseudo-queue"), requires manual server management, and lacks native OS integration. The Windows version demonstrates that a local GUI with direct process communication provides superior UX.

## Design Principles

1. **Feature Parity First**: Implement 100% of Windows version functionality before adding extras
2. **Direct Process Communication**: No FastAPI server, no HTTP, no WebSockets - pure stdout parsing like Windows
3. **Dynamic Configuration**: Reuse existing JSON files (ui_map.json, tasks.json, themes/*.json) for UI generation
4. **Fast Iteration**: MVP first, polish later - get a working translation pipeline before perfecting UI details
5. **YAGNI**: Don't over-engineer macOS integrations (Spotlight, file tags) - focus on core workflow

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SwiftUI Views Layer                     │
│  MainWindow, QueueView, ConfigView, TasksView,             │
│  VisualCompareView, LogView                                │
└─────────────────────────────────────────────────────────────┘
                          ↕ @Published
┌─────────────────────────────────────────────────────────────┐
│                    ViewModels Layer                         │
│  QueueViewModel, ConfigViewModel, VisualCompareViewModel,  │
│  LogViewModel                                               │
└─────────────────────────────────────────────────────────────┘
                          ↕ Service calls
┌─────────────────────────────────────────────────────────────┐
│                     Services Layer                          │
│  PipelineService, ConfigService, ThemeService,             │
│  ProfileService, ProgressParser                            │
└─────────────────────────────────────────────────────────────┘
                          ↕ Process.standardOutput
┌─────────────────────────────────────────────────────────────┐
│                  Embedded Python Backend                    │
│  python -m manga_translator local -i <input> -o <output>   │
└─────────────────────────────────────────────────────────────┘
```

**Communication Flow**: Swift launches Python as subprocess → reads stdout line-by-line → parses progress keywords → updates UI via @Published properties.

**Why Not REST API**: The web UI architecture (FastAPI server + HTTP polling) adds unnecessary latency and complexity. Direct process communication provides immediate progress updates with zero network overhead.

## Core Components

### 1. PipelineService

**Responsibility**: Manage Python backend process lifecycle and stdout parsing.

```swift
class PipelineService: ObservableObject {
    private var process: Process?
    private var outputPipe: Pipe?
    private var continuation: AsyncStream<ProgressUpdate>.Continuation?
    private let pythonPath: String
    
    /// Starts translation and returns AsyncStream of progress updates
    func run(task: TranslationTask, config: Config) -> AsyncStream<ProgressUpdate> {
        return AsyncStream { continuation in
            self.continuation = continuation
            
            // Build command from config
            let command = buildCommand(task: task, config: config)
            
            // Setup process
            let process = Process()
            let outputPipe = Pipe()
            
            process.executableURL = URL(fileURLWithPath: pythonPath)
            process.arguments = command
            process.standardOutput = outputPipe
            process.standardError = outputPipe
            
            self.process = process
            self.outputPipe = outputPipe
            
            // Read output asynchronously
            outputPipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                if data.isEmpty { return }
                
                if let line = String(data: data, encoding: .utf8) {
                    if let update = self.parseOutput(line) {
                        continuation.yield(update)
                    }
                }
            }
            
            // Termination handler
            process.terminationHandler = { process in
                if process.terminationStatus == 0 {
                    continuation.yield(ProgressUpdate(stage: .finished, percentage: 100, message: "Complete"))
                } else {
                    continuation.yield(ProgressUpdate(stage: .error, percentage: 0, message: "Exit code \(process.terminationStatus)"))
                }
                
                continuation.finish()
                self.cleanup()
            }
            
            // Start process
            try? process.run()
            
            // Cancellation handler
            continuation.onTermination = { @Sendable _ in
                self.cancel()
            }
        }
    }
    
    /// Terminates current translation and cleans up resources
    func cancel() {
        process?.terminate()
        continuation?.finish()
        cleanup()
    }
    
    private func cleanup() {
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        process = nil
        outputPipe = nil
        continuation = nil
    }
    
    /// Builds command from config (translates Swift config to CLI args)
    private func buildCommand(task: TranslationTask, config: Config) -> [String]
    
    /// Parses stdout line-by-line for progress keywords
    private func parseOutput(_ line: String) -> ProgressUpdate?
}
```

**Key Implementation Details**:
- Use `Process` with `Pipe` for stdout capture
- Parse keywords: "detection", "ocr", "translating", "rendering" → map to progress stages
- Error detection: lines containing "ERROR:" or "Traceback" → emit error update
- Single process at a time (serial execution prevents GPU OOM)

### 2. ConfigService

**Responsibility**: Load configuration schema from JSON and manage user settings.

```swift
class ConfigService {
    /// Loads ui_map.json (666 lines of config definitions)
    func loadUIMap() -> UIMap
    
    /// Loads tasks.json (RAW/Upscale/Colorize definitions)
    func loadTaskDefinitions() -> [String: TaskDefinition]
    
    /// Groups config options by tab
    func getTabGroups() -> [ConfigTab]
    
    /// Factory defaults
    func getFactoryDefaults() -> Config
}

struct ConfigOption {
    let key: String
    let widget: WidgetType
    let group: String
    let label: String
    let defaultValue: ConfigValue  // Type-safe enum instead of Any
    let tooltip: String
    let section: String?  // "advanced" or nil
    let order: Int
}

enum ConfigValue: Codable, Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case stringArray([String])
    
    var stringValue: String? {
        if case .string(let val) = self { return val }
        return nil
    }
    
    var doubleValue: Double? {
        if case .double(let val) = self { return val }
        if case .int(let val) = self { return Double(val) }
        return nil
    }
    
    var boolValue: Bool? {
        if case .bool(let val) = self { return val }
        return nil
    }
}

enum WidgetType {
    case segmentedButton(values: [String])
    case slider(range: ClosedRange<Double>)
    case checkbox
    case optionMenu(values: [String])
    case entry(placeholder: String)
    case entryWithButton(placeholder: String, buttonAction: String)
    case translatorChainBuilder
    case languageCheckboxGrid
}
```

**Type-Safe Config Dictionary**:
```swift
// Config is a dictionary with type-safe value access
typealias Config = [String: ConfigValue]

extension Config {
    subscript(key: String, default defaultValue: ConfigValue) -> ConfigValue {
        get { self[key] ?? defaultValue }
        set { self[key] = newValue }
    }
}
```

**Why Dynamic Generation**: The backend has 50+ configuration options that may change between versions. Hardcoding would require Swift recompilation for every backend update. Dynamic parsing from JSON keeps UI synchronized with backend capabilities.

### 3. QueueViewModel

**Responsibility**: Manage task queue, history, and processing state.

```swift
class QueueViewModel: ObservableObject {
    @Published var queue: [TranslationTask] = []
    @Published var history: [TranslationTask] = []
    @Published var isProcessing = false
    @Published var privacyMode = false
    
    func addTask(url: URL)
    func addTasks(urls: [URL])  // Batch add
    func removeSelected(ids: Set<UUID>)
    func clearQueue()
    func clearHistory()
    func reorderTasks(from: IndexSet, to: Int)
    func processNext()
    func skipCurrent()
    func toggleTaskPrivacy(taskId: UUID)
}

struct TranslationTask: Identifiable, Codable {
    let id = UUID()
    let sourceURL: URL
    var outputURL: URL?
    var taskType: TaskType = .translation
    var stage: ProcessingStage = .queued
    var progress: Double = 0
    var currentStageText: String = "Queued"
    var error: String?
    var thumbnail: Data?  // Stored as Data for Codable conformance
    var isPrivate: Bool = false
    var addedAt: Date = Date()
    var finishedAt: Date?
    var retryCount: Int = 0  // For exponential backoff retry
}

enum TaskType: String, Codable {
    case translation
    case rawOutput
    case upscaling
    case colorization
}

enum ProcessingStage: String, Codable {
    case queued, uploading, detection, ocr
    case maskGeneration, inpainting, translating
    case rendering, finished, error, cancelled
}
```

**Processing Logic**:
1. User adds tasks → appended to `queue` array
2. If idle → automatically call `processNext()`
3. Take first `.queued` task → update to `.uploading`
4. Call `PipelineService.run()` → receive AsyncStream
5. For each progress update → update task's `stage` and `progress`
6. On completion → move to `history`, call `processNext()` for next task

### 4. ThemeService

**Responsibility**: Load and apply visual themes from JSON files.

```swift
class ThemeService: ObservableObject {
    @Published var currentTheme: Theme
    @Published var availableThemes: [Theme] = []
    
    func loadThemes() -> [Theme]
    func applyTheme(_ theme: Theme)
}

struct Theme: Codable {
    let name: String
    let colors: [String: String]  // CSS color names → hex values
}
```

**Implementation**: Load from `MangaStudio_Data/themes/*.json`, apply via SwiftUI environment values.

### 5. ProfileService

**Responsibility**: Save/load configuration presets.

```swift
class ProfileService {
    func saveProfile(name: String, config: Config)
    func loadProfile(name: String) -> Config?
    func listProfiles() -> [String]
    func deleteProfile(name: String)
    
    private let profilesDirectory: URL  // ~/Library/Application Support/MangaTranslator/Profiles/
}
```

**File Format**: JSON encoding of `Config` struct. Each profile is a standalone `.json` file.

### 6. ProgressParser

**Responsibility**: Extract structured progress information from Python stdout.

```swift
struct ProgressParser {
    func parse(_ line: String) -> ProgressUpdate?
}

struct ProgressUpdate {
    let stage: ProcessingStage
    let percentage: Double
    let message: String
}
```

**Parsing Rules** (based on Windows version implementation):
- "detection" → stage = .detection, progress = 10%
- "ocr" | "Running OCR" → stage = .ocr, progress = 30%
- "mask" → stage = .maskGeneration, progress = 50%
- "inpainting" → stage = .inpainting, progress = 60%
- "translating" → stage = .translating, progress = 70%
- "rendering" → stage = .rendering, progress = 90%
- "ERROR:" | "Traceback" → stage = .error, extract error message
- Exit code 0 + no errors → stage = .finished, progress = 100%

## UI Structure

### Main Window Layout

```
┌────────────────────────────────────────────────────────────┐
│  Toolbar: [▶️ Start] [⏹️ Stop] [🔒 Privacy] [Theme ▾] [Profile ▾] │
├──────────┬─────────────────────────────────────────────────┤
│  Left    │              Right Panel (TabView)              │
│  Panel   ├─────────────────────────────────────────────────┤
│  (300pt) │ Tab 1: ⚙️ Configuration                         │
│          │  ├─ General & Translator                        │
│ Queue    │  ├─ Detector & OCR                             │
│ (3 items)│  ├─ Image & Inpainter                          │
│ ┌──────┐ │  ├─ Render & Output                            │
│ │ [▶]  │ │  └─ Extra Settings                             │
│ │ [▶]  │ │                                                 │
│ │ [⏸]  │ │ Tab 2: 🛠️ Tasks (RAW/Upscale/Colorize)         │
│ └──────┘ │                                                 │
│          │ Tab 3: 👁️ Visual Compare                        │
│ History  │  [Original Image] | [Translated Image]         │
│ (5 items)│  (sync zoom/pan)                               │
│ ┌──────┐ │                                                 │
│ │ ✓    │ │ Tab 4: 📊 Live Log                             │
│ │ ✓    │ │  [Colored log output with auto-scroll]         │
│ └──────┘ │                                                 │
│          │                                                 │
│ [➕ Add] │                                                 │
│ [🗑️ Del] │                                                 │
└──────────┴─────────────────────────────────────────────────┘
```

**Minimum Window Size**: 960×540 (same as Windows version)

### Queue View

**Queue Section** (upper left panel):
- List of tasks with thumbnails (60×60 pt)
- Status badge (Queued/Processing/Finished/Error)
- Progress bar (only for processing tasks)
- File name truncated with ellipsis
- Drag-drop reordering support
- Right-click context menu:
  - Mark as Private
  - Remove from Queue
  - Open in Finder
  - Show in Visual Compare

**Thumbnail Generation**:
- Generated asynchronously on background queue when task is added
- Downsampled to 60×60 pt to minimize memory usage
- Lazy loading: only generate thumbnail when task becomes visible in list
- Caching: thumbnails stored as `Data` in `TranslationTask` for persistence

**Output Directory Default**:
- Same directory as input file with `_translated` suffix
- Example: `/path/to/manga.png` → `/path/to/manga_translated.png`
- User can customize output directory in settings (saved to UserDefaults)
- Batch operations: preserve folder structure in output directory

**History Section** (lower left panel):
- Completed tasks (finished or error)
- Smaller thumbnails (40×40 pt)
- Timestamp of completion
- Right-click context menu:
  - Open Result
  - Delete Result
  - Re-translate

**Privacy Mode Behavior**:
- Global toggle: blurs ALL thumbnails
- Per-task toggle: blurs only marked tasks
- Blur implementation: `.blur(radius: 20)` modifier or SF Symbol placeholder (`eye.slash`)

### Configuration Tabs (Dynamic Generation)

**Implementation Strategy**: Parse `ui_map.json` at runtime to generate UI.

```swift
ForEach(configService.tabs) { tab in
    ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            // Standard settings
            ForEach(tab.standardSettings) { option in
                ConfigOptionRow(option: option)
            }
            
            // Advanced settings separator
            if !tab.advancedSettings.isEmpty {
                Divider()
                Text("ADVANCED SETTINGS").font(.headline)
                ForEach(tab.advancedSettings) { option in
                    ConfigOptionRow(option: option)
                }
            }
        }
        .padding()
    }
    .tabItem { Label(tab.name, systemImage: tab.icon) }
}
```

**ConfigOptionRow** renders different widgets based on `option.widget`:

```swift
struct ConfigOptionRow: View {
    @Binding var value: Any
    let option: ConfigOption
    
    var body: some View {
        HStack {
            Text(option.label)
            Spacer()
            
            switch option.widget {
            case .segmentedButton(let values):
                Picker("", selection: $value) {
                    ForEach(values, id: \.self) { Text($0) }
                }
                .pickerStyle(.segmented)
                
            case .slider(let range):
                Slider(value: $value, in: range)
                Text("\(value, specifier: "%.1f")")
                
            case .checkbox:
                Toggle("", isOn: $value)
                
            case .optionMenu(let values):
                Picker("", selection: $value) {
                    ForEach(values, id: \.self) { Text($0) }
                }
                
            case .entry(let placeholder):
                TextField(placeholder, text: $value)
                
            case .entryWithButton(let placeholder, _):
                TextField(placeholder, text: $value)
                Button("...") { openFilePicker() }
                
            // ... other widget types
            }
        }
        .help(option.tooltip)  // Native macOS tooltip
    }
}
```

### Tasks Tab

**Purpose**: Switch between task modes (Translation, RAW Output, Upscaling, Colorization).

**UI**: 
- Segmented picker for task mode selection
- Description text explaining current mode
- Only show relevant configuration options (from `tasks.json` → `settings_keys`)
- Apply backend config overrides when switching modes

**Example**: When "RAW Output" is selected:
1. Load `tasks.json` → `raw_output.backend_config`
2. Override: `translator = "none"`, `renderer = "none"`
3. UI shows only: detector, detection_size, inpainter, inpainting_size, mask_dilation_offset
4. All other settings hidden

### Visual Compare Tab

**Layout**: Side-by-side image views with synchronized interaction.

```swift
HStack(spacing: 0) {
    VStack {
        Text("Original")
        ImageViewer(image: $originalImage, zoom: $zoom, offset: $offset)
    }
    
    Divider()
    
    VStack {
        Text("Translated")
        ImageViewer(image: $translatedImage, zoom: $zoom, offset: $offset)
    }
}
```

**Features**:
- Load test image button
- Run translation on single image
- Pinch-to-zoom (trackpad gesture)
- Drag-to-pan
- Synchronized zoom/offset between both views
- "Reset View" button to fit images to viewport

**Implementation**: Use `NSImageView` wrapped in `NSViewRepresentable` for native macOS image rendering performance.

### Live Log Tab

**Purpose**: Real-time stdout display from Python backend.

**Features**:
- Color-coded log levels (INFO=blue, WARNING=yellow, ERROR=red, DEBUG=gray)
- Auto-scroll to bottom (with user override when manually scrolling up)
- Monospace font for structured output
- Copy log button
- Clear log button

**Implementation**:
```swift
ScrollViewReader { proxy in
    ScrollView {
        VStack(alignment: .leading) {
            ForEach(logViewModel.messages) { msg in
                Text(msg.text)
                    .font(.system(.body, design: .monospaced))
                    .foregroundColor(msg.level.color)
                    .id(msg.id)
            }
        }
    }
    .onChange(of: logViewModel.messages.count) {
        if logViewModel.autoScroll {
            proxy.scrollTo(logViewModel.messages.last?.id)
        }
    }
}
```

## Data Flow

### Task Submission Flow

```
User drags file/folder/ZIP into Queue
    ↓
QueueViewModel.addTasks(urls)
    ↓
Scan for image files (.png, .jpg, .jpeg, .webp, .bmp)
    ↓
For each image: create TranslationTask with thumbnail
    ↓
Append to queue array (@Published → UI updates)
    ↓
If not currently processing → call processNext()
```

### Real-Time Progress Flow

```
QueueViewModel.processNext()
    ↓
Take first .queued task, update stage to .uploading
    ↓
PipelineService.run(task, config) → returns AsyncStream<ProgressUpdate>
    ↓
for await update in stream:
    ↓
    Update task.stage and task.progress
    ↓
    @Published triggers SwiftUI re-render
    ↓
    Progress bar animates to new value
    ↓
On stream completion:
    ↓
    Move task to history
    ↓
    Call processNext() for next queued task
```

### Configuration Save/Load Flow

```
User modifies settings in Configuration tabs
    ↓
@Binding updates ConfigViewModel.currentConfig
    ↓
User clicks "Save Profile" button
    ↓
ProfileService.saveProfile(name, config)
    ↓
Encode Config to JSON
    ↓
Write to ~/Library/Application Support/MangaTranslator/Profiles/<name>.json
```

### Special Task Mode Flow

```
User selects "RAW Output" in Tasks tab
    ↓
ConfigService.loadTaskDefinitions()["raw_output"]
    ↓
Apply backend_config overrides:
  - translator: "none"
  - renderer: "none"
    ↓
Filter displayed settings to only settings_keys
    ↓
When task runs, buildCommand() respects overrides
```

## Error Handling

### Python Backend Errors

```swift
// Exit code check
if process.terminationStatus != 0 {
    task.stage = .error
    task.error = "Process failed with exit code \(process.terminationStatus)"
}

// Stdout error detection
if line.contains("ERROR:") || line.contains("Traceback") {
    let errorMsg = extractErrorMessage(from: line)
    task.stage = .error
    task.error = errorMsg
}

// API rate limiting (429) with exponential backoff retry
if line.contains("429") || line.contains("Too Many Requests") {
    task.retryCount += 1
    if task.retryCount <= 10 {
        let delay = min(2.0 * pow(2.0, Double(task.retryCount)), 30.0)
        task.stage = .pending
        task.error = "Server busy, retrying in \(Int(delay))s... (attempt \(task.retryCount)/10)"
        
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) {
            self.processTask(task)  // Retry with same task
        }
    } else {
        task.stage = .error
        task.error = "Failed after 10 retries: Server too busy"
    }
}

// GPU OOM with automatic CPU fallback
if line.contains("CUDA out of memory") {
    if config.processingDevice == "NVIDIA GPU" {
        // Automatic fallback to CPU
        config.processingDevice = "CPU"
        task.stage = .queued
        task.error = nil
        showNotification("GPU memory insufficient. Switched to CPU mode.")
        processTask(task)  // Retry with CPU
    } else {
        task.stage = .error
        task.error = "Out of memory even with CPU mode"
    }
}

// Process crash/termination
if process.terminationReason == .uncaughtSignal {
    task.stage = .error
    task.error = "Translation process crashed unexpectedly"
    currentProcess = nil
    processNext()  // Continue with next task instead of blocking queue
}
```

**Batch Processing Failure Strategy**:
- Individual task failure does NOT stop the queue
- Failed task moves to history with error status
- Queue continues with next task automatically
- User can right-click failed task → "Retry" to re-add to queue

### File System Errors

```swift
// Input file unreadable
guard FileManager.default.isReadableFile(atPath: url.path) else {
    showError("Cannot read file: \(url.lastPathComponent)")
    return
}

// Output directory not writable
guard let outputDir = outputURL?.deletingLastPathComponent(),
      FileManager.default.isWritableFile(atPath: outputDir.path) else {
    showError("Cannot write to output directory. Check permissions.")
    return
}
```

### User Input Validation

```swift
// Empty queue
if queue.isEmpty {
    showAlert("Queue is empty. Add images to translate.")
    return
}

// Unsupported file type
let validExts = ["png", "jpg", "jpeg", "webp", "bmp"]
guard validExts.contains(url.pathExtension.lowercased()) else {
    showError("Unsupported file type: \(url.pathExtension)")
    return
}

// Duplicate detection
if queue.contains(where: { $0.sourceURL == url }) {
    // Silently skip or ask user
}
```

### Configuration Errors

```swift
// Missing required API key
if config.translator == "deepl" && config.deeplApiKey.isEmpty {
    showAlert("DeepL API key required")
    disableStartButton()
}

// ui_map.json parse failure
guard let uiMap = try? JSONDecoder().decode(UIMap.self, from: data) else {
    fatalError("Failed to load ui_map.json")
}
```

### Concurrency & Resource Management

```swift
// Prevent multiple simultaneous processes
private var currentProcess: Process?

func processNext() {
    guard currentProcess == nil else { return }
    // ... start translation
}

// Cleanup on cancellation
func cancel() {
    currentProcess?.terminate()
    currentProcess = nil
}

// Ensure cleanup on deinit
deinit {
    currentProcess?.terminate()
}
```

## Privacy Mode Feature

**Purpose**: Hide sensitive/NSFW image content while preserving progress visibility.

### Global Privacy Mode

**UI**: Toggle button in toolbar (`🔒 Privacy Mode`)

**Behavior**: When enabled, ALL task thumbnails are blurred/hidden.

**Implementation**:
```swift
if viewModel.privacyMode || task.isPrivate {
    Image(systemName: "eye.slash")
        .frame(width: 60, height: 60)
        .background(.ultraThinMaterial)
} else {
    AsyncImage(url: task.sourceURL)
        .frame(width: 60, height: 60)
}
```

### Per-Task Privacy Marking

**UI**: Right-click menu item "Mark as Private"

**Behavior**: Only marked tasks are hidden, others remain visible.

**Persistence**: Save to `UserDefaults` or encode in task JSON.

### Keyboard Shortcut

- `Cmd+Shift+P`: Toggle global privacy mode
- `Space` (hold): Temporarily reveal image while key is pressed

**Space Key Implementation** (using AppKit event monitoring):

```swift
class QueueViewModel: ObservableObject {
    @Published var privacyMode = false
    @Published var temporaryReveal = false
    private var eventMonitor: Any?
    
    init() {
        setupKeyboardMonitoring()
    }
    
    private func setupKeyboardMonitoring() {
        // Monitor local events (within app)
        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .keyUp]) { event in
            if event.keyCode == 49 {  // Space bar key code
                if event.type == .keyDown && !event.isARepeat {
                    self.temporaryReveal = true
                } else if event.type == .keyUp {
                    self.temporaryReveal = false
                }
            }
            return event
        }
    }
    
    deinit {
        if let monitor = eventMonitor {
            NSEvent.removeMonitor(monitor)
        }
    }
}

// In SwiftUI view:
if (viewModel.privacyMode || task.isPrivate) && !viewModel.temporaryReveal {
    // Show blur
} else {
    // Show actual image
}
```

### Visual Compare Integration

When privacy mode is active:
- Blur/hide images in Visual Compare view
- Or disable the tab entirely
- Progress text remains visible: "Translating... 70%"

**Why This Feature**: User specifically requested ability to translate NSFW content without large previews visible to others in the room. Privacy mode allows monitoring translation progress without exposing image content.

## Testing Strategy

### Unit Tests

- `ProgressParser`: Verify correct stage/percentage mapping for all keywords
- `ConfigService`: Verify ui_map.json parsing loads all 50+ options
- `ProfileService`: Save/load round-trip preserves all settings
- `QueueViewModel`: Add/remove/reorder operations update state correctly

### Integration Tests

- End-to-end translation: Add task → process → verify output file exists
- Python backend availability: Check embedded Python can be launched
- Config → CLI args: Verify buildCommand() produces correct arguments

### UI Tests

- Queue operations: Add task, remove task, clear queue
- Privacy mode: Toggle global, mark task private, verify blur applied
- Drag-drop: Drop file onto queue, verify task appears

### Performance Tests

- Large queue (1000+ items): Measure UI responsiveness
- Memory leaks: Verify Process cleanup after multiple translations
- Thumbnail generation: Test with large images (>20MB)

### Manual Testing Checklist

Core Functionality:
- [ ] Drag-drop single file
- [ ] Drag-drop folder with 10+ images
- [ ] Queue reordering
- [ ] Start/stop translation
- [ ] Real-time progress updates
- [ ] Error display (try invalid API key)

Configuration:
- [ ] All 5 config tabs render
- [ ] Modify settings, save profile, reload profile
- [ ] Switch themes

Special Tasks:
- [ ] RAW Output mode
- [ ] Upscaling mode  
- [ ] Colorization mode

Visual Compare:
- [ ] Load image, run translation, view side-by-side
- [ ] Synchronized zoom
- [ ] Synchronized pan

Privacy Mode:
- [ ] Global toggle hides all thumbnails
- [ ] Per-task marking works
- [ ] Progress bars still update when hidden

## Development Roadmap

### Phase 1: MVP (Week 1-2)
**Goal**: Single image translation works end-to-end

- [ ] Project setup (SwiftUI macOS app)
- [ ] Bundle embedded Python runtime
- [ ] PipelineService: launch process, parse stdout
- [ ] Basic queue UI
- [ ] Basic config UI (hardcoded, not dynamic)
- [ ] Single image translation pipeline works

**Acceptance**: Can add one image, click Start, see progress bar update, translation completes.

### Phase 2: Configuration System (Week 3)
**Goal**: Full configuration UI dynamically generated

- [ ] ConfigService parses ui_map.json
- [ ] Dynamic ConfigOptionRow for all widget types
- [ ] All 5 config tabs render
- [ ] ProfileService save/load
- [ ] Settings persistence

**Acceptance**: All configuration options visible and functional, can save/load profiles.

### Phase 3: Queue & Tasks (Week 4 - First Half)
**Goal**: Batch processing and queue enhancements

- [ ] Drag-drop file/folder/ZIP
- [ ] Queue reordering
- [ ] Multi-select delete
- [ ] History view
- [ ] Batch processing (serial execution)
- [ ] Privacy mode (global + per-task)

**Acceptance**: Can batch translate 50+ images, all queue operations work, privacy mode hides content.

### Phase 4: Special Features (Week 4 - Second Half)
**Goal**: Special task modes and visual comparison

- [ ] TasksTab with RAW/Upscale/Colorize modes
- [ ] Visual Compare implementation
- [ ] Theme system (load from JSON)
- [ ] Live Log tab with color coding

**Acceptance**: Three special task modes work, Visual Compare shows side-by-side with sync zoom/pan, can switch themes.

### Phase 5: Polish & Release (Week 5)
**Goal**: Production-ready application

- [ ] Error handling polish
- [ ] Unit + integration tests
- [ ] Code signing & notarization
- [ ] DMG packaging
- [ ] README with installation instructions

**Acceptance**: App runs on fresh Mac without developer tools, passes all tests, ready for GitHub release.

## Technical Decisions

### Why SwiftUI over AppKit?

**Choice**: SwiftUI

**Rationale**:
- Declarative UI matches reactive data flow (Process stdout → ViewModel @Published → UI)
- Built-in data binding reduces boilerplate
- Modern, Apple-recommended approach for new macOS apps
- Easier to maintain long-term as Apple invests in SwiftUI

**Trade-off**: Some advanced UI features require AppKit (NSImageView, file pickers). Acceptable via NSViewRepresentable wrappers.

### Why Embedded Python over System Python?

**Choice**: Bundle python-build-standalone

**Rationale**:
- User's system Python may lack required packages
- Version consistency across all user machines
- No dependency on user installing Python + pip
- Simplified distribution (single .app bundle)

**Trade-off**: Larger app size (~200MB with Python + dependencies). Acceptable for desktop application.

### Why JSON Config Files over Swift Code?

**Choice**: Parse ui_map.json at runtime

**Rationale**:
- Backend config options change between versions
- Hardcoding in Swift requires recompilation for every update
- Dynamic parsing keeps UI synchronized with backend capabilities
- Reuses existing Windows version infrastructure

**Trade-off**: Runtime parsing overhead (negligible, <100ms), type safety weaker than Swift structs. Acceptable for flexibility gained.

### Why Serial Queue Processing?

**Choice**: Process one task at a time

**Rationale**:
- GPU models (inpainting, OCR) consume significant VRAM
- Parallel execution risks OOM crashes
- Windows version uses same approach successfully
- Simpler state management (single "current task")

**Trade-off**: Slower total throughput for large batches. Acceptable as translation is IO/compute-bound, not queue-bound.

## Design Decisions (Resolved)

### 1. Python Distribution

**Decision**: Use python-build-standalone with static linking.

**Rationale**: 
- Single .app bundle, no external dependencies
- Consistent behavior across all user machines
- Simpler than conda-pack (no environment activation needed)
- Size (~200MB) is acceptable for desktop app

**Implementation**: Bundle in `Contents/Resources/python/` within .app bundle.

### 2. Update Mechanism

**Decision**: Bundle Python with each app update (no separate Python updates).

**Rationale**:
- Simpler distribution (one artifact)
- Backend Python dependencies stay synchronized with app version
- Users already expect app updates to include all components
- Avoids complexity of in-app Python updater

**Future**: If bundle size becomes problematic, consider downloading Python on first launch (Phase 2 enhancement).

### 3. Output Format

**Decision**: Preserve input format by default.

**Rationale**:
- User expectation: translate `image.jpg` → `image_translated.jpg`
- Avoid unnecessary re-encoding quality loss
- Windows version uses PNG due to backend limitation, not user preference

**Implementation**: Add `--format` CLI arg matching input extension. Fallback to PNG if output format not supported.

### 4. Queue Persistence

**Decision**: Do NOT persist queue across app restarts (match Windows behavior).

**Rationale**:
- Queue contains file URLs that may become stale (files moved/deleted)
- Translation state (progress, errors) cannot be meaningfully persisted
- Simple "Add Job" flow makes re-adding tasks trivial
- Avoids complexity of queue state validation on restart

**User Workaround**: If user needs persistence, they can save input folder path and re-add after restart.

### 5. Batch Size Limit

**Decision**: No hard limit. Warn if queue exceeds 500 items.

**Rationale**:
- Users with large manga volumes (1000+ pages) have legitimate use case
- Memory impact is minimal (thumbnails lazy-loaded, tasks processed serially)
- 500-item warning gives user chance to cancel if accidental

**Implementation**: Show non-blocking alert: "Large queue (N items). This may take several hours. Continue?"

## Success Metrics

- [ ] Feature parity: All Windows MangaStudio features implemented
- [ ] Performance: Single image translation takes <30s (on typical manga page)
- [ ] Stability: 100 image batch completes without crashes
- [ ] Usability: User can translate first image within 2 minutes of app launch (no manual configuration)
- [ ] Privacy: Privacy mode successfully hides thumbnails while progress remains visible

## References

- [Windows Version Source Code](../MangaStudio_Data/)
- [Backend Python Code](../manga_translator/)
- [Configuration Schema](../MangaStudio_Data/ui_map.json)
- [Special Tasks Definition](../MangaStudio_Data/tasks.json)
- [Theme Files](../MangaStudio_Data/themes/)

---

**Next Steps**: 
1. Review this spec with user
2. Run spec-document-reviewer agent
3. Create implementation plan with writing-plans skill
4. Begin Phase 1 development
