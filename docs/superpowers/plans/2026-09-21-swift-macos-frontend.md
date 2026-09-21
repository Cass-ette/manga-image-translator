# Swift macOS Frontend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build native macOS app with SwiftUI that replaces web UI and achieves feature parity with Windows version.

**Architecture:** MVVM pattern with Services layer. SwiftUI views bind to ViewModels via @Published properties. Services manage Python subprocess communication, config parsing, and file operations. Direct stdout parsing for real-time progress (no HTTP layer).

**Tech Stack:** Swift 5.9+, SwiftUI, Foundation (Process/Pipe), python-build-standalone (embedded runtime)

---

## Project Structure

```
MangaTranslatorMac/
├── MangaTranslatorMac.xcodeproj
├── MangaTranslatorMac/
│   ├── App/
│   │   ├── MangaTranslatorMacApp.swift          # App entry point
│   │   └── Assets.xcassets                      # Icons, colors
│   ├── Models/
│   │   ├── TranslationTask.swift                # Task data model
│   │   ├── ConfigValue.swift                    # Type-safe config values
│   │   ├── ConfigOption.swift                   # UI config schema
│   │   ├── Theme.swift                          # Theme data model
│   │   └── ProgressUpdate.swift                 # Progress event model
│   ├── ViewModels/
│   │   ├── QueueViewModel.swift                 # Queue + history state
│   │   ├── ConfigViewModel.swift                # Config state
│   │   ├── VisualCompareViewModel.swift         # Compare view state
│   │   └── LogViewModel.swift                   # Log state
│   ├── Views/
│   │   ├── MainWindow.swift                     # Root window
│   │   ├── QueueView.swift                      # Left panel (queue/history)
│   │   ├── ConfigView.swift                     # Config tabs container
│   │   ├── ConfigOptionRow.swift                # Dynamic config widget
│   │   ├── TasksView.swift                      # Special tasks tab
│   │   ├── VisualCompareView.swift              # Side-by-side comparison
│   │   └── LogView.swift                        # Live log tab
│   ├── Services/
│   │   ├── PipelineService.swift                # Python process manager
│   │   ├── ProgressParser.swift                 # Stdout parser
│   │   ├── ConfigService.swift                  # JSON config loader
│   │   ├── ThemeService.swift                   # Theme manager
│   │   └── ProfileService.swift                 # Profile save/load
│   └── Resources/
│       ├── python/                              # Embedded Python runtime
│       ├── MangaStudio_Data/                    # Copied from Windows version
│       │   ├── ui_map.json
│       │   ├── tasks.json
│       │   └── themes/*.json
│       └── Info.plist
├── MangaTranslatorMacTests/
│   ├── ProgressParserTests.swift
│   ├── ConfigServiceTests.swift
│   └── PipelineServiceTests.swift
└── README.md
```

---

## Chunk 1: Phase 1 MVP - Core Translation Pipeline

**Goal**: Single image translation works end-to-end with real-time progress display.

### Task 1: Project Setup

**Files:**
- Create: `MangaTranslatorMac/MangaTranslatorMacApp.swift`
- Create: `MangaTranslatorMac/Info.plist`

- [ ] **Step 1: Create new macOS App project in Xcode**

```bash
# Create project
cd ~/Projects/manga-image-translator
mkdir -p MangaTranslatorMac
cd MangaTranslatorMac
# Open Xcode: File > New > Project > macOS > App
# Name: MangaTranslatorMac
# Interface: SwiftUI
# Language: Swift
# Minimum: macOS 13.0
```

- [ ] **Step 2: Configure Info.plist**

Edit `Info.plist`:
```xml
<key>CFBundleName</key>
<string>Manga Translator</string>
<key>CFBundleIdentifier</key>
<string>com.mangat ranslator.macos</string>
<key>LSMinimumSystemVersion</key>
<string>13.0</string>
<key>NSHumanReadableCopyright</key>
<string>© 2026</string>
```

- [ ] **Step 3: Verify build**

Run: `Cmd+B` in Xcode
Expected: Build succeeds, app launches with default SwiftUI window

- [ ] **Step 4: Initial commit**

```bash
git add MangaTranslatorMac/
git commit -m "chore: initialize macOS SwiftUI project"
```

### Task 2: Data Models

**Files:**
- Create: `MangaTranslatorMac/Models/TranslationTask.swift`
- Create: `MangaTranslatorMac/Models/ProgressUpdate.swift`

- [ ] **Step 1: Create TranslationTask model**

File: `Models/TranslationTask.swift`
```swift
import Foundation

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
    
    var displayName: String {
        switch self {
        case .queued: return "Queued"
        case .uploading: return "Uploading"
        case .detection: return "Detecting texts"
        case .ocr: return "Running OCR"
        case .maskGeneration: return "Generating mask"
        case .inpainting: return "Inpainting"
        case .translating: return "Translating"
        case .rendering: return "Rendering"
        case .finished: return "Finished"
        case .error: return "Error"
        case .cancelled: return "Cancelled"
        }
    }
}

struct TranslationTask: Identifiable, Codable {
    let id: UUID
    let sourceURL: URL
    var outputURL: URL?
    var taskType: TaskType
    var stage: ProcessingStage
    var progress: Double
    var error: String?
    var thumbnail: Data?
    var isPrivate: Bool
    var addedAt: Date
    var finishedAt: Date?
    var retryCount: Int
    
    init(sourceURL: URL, taskType: TaskType = .translation) {
        self.id = UUID()
        self.sourceURL = sourceURL
        self.taskType = taskType
        self.stage = .queued
        self.progress = 0
        self.isPrivate = false
        self.addedAt = Date()
        self.retryCount = 0
    }
}
```

- [ ] **Step 2: Create ProgressUpdate model**

File: `Models/ProgressUpdate.swift`
```swift
import Foundation

struct ProgressUpdate {
    let stage: ProcessingStage
    let percentage: Double
    let message: String
    
    init(stage: ProcessingStage, percentage: Double, message: String) {
        self.stage = stage
        self.percentage = percentage
        self.message = message
    }
}
```

- [ ] **Step 3: Write tests for models**

File: `MangaTranslatorMacTests/ModelTests.swift`
```swift
import XCTest
@testable import MangaTranslatorMac

final class ModelTests: XCTestCase {
    func testTranslationTaskInitialization() {
        let url = URL(fileURLWithPath: "/test/image.png")
        let task = TranslationTask(sourceURL: url)
        
        XCTAssertEqual(task.sourceURL, url)
        XCTAssertEqual(task.stage, .queued)
        XCTAssertEqual(task.progress, 0)
        XCTAssertEqual(task.taskType, .translation)
        XCTAssertFalse(task.isPrivate)
    }
    
    func testProcessingStageDisplayNames() {
        XCTAssertEqual(ProcessingStage.queued.displayName, "Queued")
        XCTAssertEqual(ProcessingStage.translating.displayName, "Translating")
        XCTAssertEqual(ProcessingStage.finished.displayName, "Finished")
    }
}
```

- [ ] **Step 4: Run tests**

Run: `Cmd+U` in Xcode
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add MangaTranslatorMac/Models/
git add MangaTranslatorMacTests/ModelTests.swift
git commit -m "feat: add TranslationTask and ProgressUpdate models"
```

### Task 3: ProgressParser Service

**Files:**
- Create: `MangaTranslatorMac/Services/ProgressParser.swift`
- Create: `MangaTranslatorMacTests/ProgressParserTests.swift`

- [ ] **Step 1: Write failing test**

File: `MangaTranslatorMacTests/ProgressParserTests.swift`
```swift
import XCTest
@testable import MangaTranslatorMac

final class ProgressParserTests: XCTestCase {
    var parser: ProgressParser!
    
    override func setUp() {
        parser = ProgressParser()
    }
    
    func testParseDetectionStage() {
        let update = parser.parse("detection")
        
        XCTAssertNotNil(update)
        XCTAssertEqual(update?.stage, .detection)
        XCTAssertEqual(update?.percentage, 10)
    }
    
    func testParseOCRStage() {
        let update = parser.parse("Running OCR")
        
        XCTAssertNotNil(update)
        XCTAssertEqual(update?.stage, .ocr)
        XCTAssertEqual(update?.percentage, 30)
    }
    
    func testParseTranslatingStage() {
        let update = parser.parse("translating")
        
        XCTAssertNotNil(update)
        XCTAssertEqual(update?.stage, .translating)
        XCTAssertEqual(update?.percentage, 70)
    }
    
    func testParseErrorLine() {
        let update = parser.parse("ERROR: API key invalid")
        
        XCTAssertNotNil(update)
        XCTAssertEqual(update?.stage, .error)
        XCTAssertTrue(update!.message.contains("API key invalid"))
    }
    
    func testParseUnknownLine() {
        let update = parser.parse("some random log line")
        
        XCTAssertNil(update)
    }
}
```

- [ ] **Step 2: Run test to verify failure**

Run: `Cmd+U`
Expected: FAIL with "Use of unresolved identifier 'ProgressParser'"

- [ ] **Step 3: Implement ProgressParser**

File: `Services/ProgressParser.swift`
```swift
import Foundation

struct ProgressParser {
    func parse(_ line: String) -> ProgressUpdate? {
        let lowercased = line.lowercased()
        
        // Error detection
        if lowercased.contains("error:") || lowercased.contains("traceback") {
            return ProgressUpdate(
                stage: .error,
                percentage: 0,
                message: line
            )
        }
        
        // Stage detection
        if lowercased.contains("detection") {
            return ProgressUpdate(stage: .detection, percentage: 10, message: "Detecting text regions")
        }
        
        if lowercased.contains("ocr") {
            return ProgressUpdate(stage: .ocr, percentage: 30, message: "Running OCR")
        }
        
        if lowercased.contains("mask") {
            return ProgressUpdate(stage: .maskGeneration, percentage: 50, message: "Generating text mask")
        }
        
        if lowercased.contains("inpainting") {
            return ProgressUpdate(stage: .inpainting, percentage: 60, message: "Running inpainting")
        }
        
        if lowercased.contains("translat") {
            return ProgressUpdate(stage: .translating, percentage: 70, message: "Translating text")
        }
        
        if lowercased.contains("render") {
            return ProgressUpdate(stage: .rendering, percentage: 90, message: "Rendering translated text")
        }
        
        return nil
    }
}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `Cmd+U`
Expected: All ProgressParserTests pass

- [ ] **Step 5: Commit**

```bash
git add MangaTranslatorMac/Services/ProgressParser.swift
git add MangaTranslatorMacTests/ProgressParserTests.swift
git commit -m "feat: add ProgressParser service"
```

### Task 4: PipelineService (Basic Structure)

**Files:**
- Create: `MangaTranslatorMac/Services/PipelineService.swift`
- Create: `MangaTranslatorMacTests/PipelineServiceTests.swift`

- [ ] **Step 1: Write basic test**

File: `MangaTranslatorMacTests/PipelineServiceTests.swift`
```swift
import XCTest
@testable import MangaTranslatorMac

final class PipelineServiceTests: XCTestCase {
    func testBuildCommand() {
        let service = PipelineService(pythonPath: "/usr/bin/python3")
        let task = TranslationTask(sourceURL: URL(fileURLWithPath: "/test/input.png"))
        let config: [String: String] = [:]
        
        let command = service.buildCommand(task: task, config: config)
        
        XCTAssertTrue(command.contains("-m"))
        XCTAssertTrue(command.contains("manga_translator"))
        XCTAssertTrue(command.contains("local"))
        XCTAssertTrue(command.contains("-i"))
        XCTAssertTrue(command.contains("/test/input.png"))
    }
}
```

- [ ] **Step 2: Run test to verify failure**

Run: `Cmd+U`
Expected: FAIL with "Use of unresolved identifier 'PipelineService'"

- [ ] **Step 3: Implement PipelineService skeleton**

File: `Services/PipelineService.swift`
```swift
import Foundation

@MainActor
class PipelineService: ObservableObject {
    private var process: Process?
    private var outputPipe: Pipe?
    private var continuation: AsyncStream<ProgressUpdate>.Continuation?
    private let pythonPath: String
    private let parser = ProgressParser()
    
    init(pythonPath: String) {
        self.pythonPath = pythonPath
    }
    
    func run(task: TranslationTask, config: [String: String]) -> AsyncStream<ProgressUpdate> {
        return AsyncStream { continuation in
            self.continuation = continuation
            
            let command = self.buildCommand(task: task, config: config)
            
            let process = Process()
            let outputPipe = Pipe()
            
            process.executableURL = URL(fileURLWithPath: self.pythonPath)
            process.arguments = command
            process.standardOutput = outputPipe
            process.standardError = outputPipe
            
            self.process = process
            self.outputPipe = outputPipe
            
            // Read output asynchronously
            outputPipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                guard !data.isEmpty else { return }
                
                if let line = String(data: data, encoding: .utf8) {
                    line.enumerateLines { line, _ in
                        if let update = self.parser.parse(line) {
                            continuation.yield(update)
                        }
                    }
                }
            }
            
            // Termination handler
            process.terminationHandler = { process in
                Task { @MainActor in
                    if process.terminationStatus == 0 {
                        continuation.yield(ProgressUpdate(
                            stage: .finished,
                            percentage: 100,
                            message: "Translation complete"
                        ))
                    } else {
                        continuation.yield(ProgressUpdate(
                            stage: .error,
                            percentage: 0,
                            message: "Process failed with exit code \(process.terminationStatus)"
                        ))
                    }
                    
                    continuation.finish()
                    self.cleanup()
                }
            }
            
            // Cancellation handler
            continuation.onTermination = { @Sendable _ in
                Task { @MainActor in
                    self.cancel()
                }
            }
            
            // Start process
            do {
                try process.run()
            } catch {
                continuation.yield(ProgressUpdate(
                    stage: .error,
                    percentage: 0,
                    message: "Failed to start process: \(error.localizedDescription)"
                ))
                continuation.finish()
            }
        }
    }
    
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
    
    func buildCommand(task: TranslationTask, config: [String: String]) -> [String] {
        var command = ["-m", "manga_translator", "local"]
        
        // Input/output paths
        command.append(contentsOf: ["-i", task.sourceURL.path])
        
        let outputPath = task.outputURL?.path ??
            task.sourceURL.deletingLastPathComponent()
                .appendingPathComponent(task.sourceURL.deletingPathExtension().lastPathComponent + "_translated")
                .appendingPathExtension(task.sourceURL.pathExtension).path
        
        command.append(contentsOf: ["-o", outputPath])
        
        // TODO: Add config options
        
        return command
    }
}
```

- [ ] **Step 4: Run test to verify pass**

Run: `Cmd+U`
Expected: PipelineServiceTests.testBuildCommand passes

- [ ] **Step 5: Commit**

```bash
git add MangaTranslatorMac/Services/PipelineService.swift
git add MangaTranslatorMacTests/PipelineServiceTests.swift
git commit -m "feat: add PipelineService skeleton with command building"
```

### Task 5: QueueViewModel (MVP Version)

**Files:**
- Create: `MangaTranslatorMac/ViewModels/QueueViewModel.swift`

- [ ] **Step 1: Create QueueViewModel**

File: `ViewModels/QueueViewModel.swift`
```swift
import Foundation
import SwiftUI

@MainActor
class QueueViewModel: ObservableObject {
    @Published var queue: [TranslationTask] = []
    @Published var history: [TranslationTask] = []
    @Published var isProcessing = false
    @Published var privacyMode = false
    
    private let pipelineService: PipelineService
    private var currentTask: Task<Void, Never>?
    
    init(pipelineService: PipelineService) {
        self.pipelineService = pipelineService
    }
    
    func addTask(url: URL) {
        let task = TranslationTask(sourceURL: url)
        queue.append(task)
        
        if !isProcessing {
            processNext()
        }
    }
    
    func processNext() {
        guard !isProcessing,
              let index = queue.firstIndex(where: { $0.stage == .queued }) else {
            return
        }
        
        isProcessing = true
        var task = queue[index]
        
        currentTask = Task {
            for await update in pipelineService.run(task: task, config: [:]) {
                task.stage = update.stage
                task.progress = update.percentage / 100.0
                
                if update.stage == .error {
                    task.error = update.message
                }
                
                queue[index] = task
                
                if update.stage == .finished || update.stage == .error {
                    task.finishedAt = Date()
                    history.insert(task, at: 0)
                    queue.remove(at: index)
                    isProcessing = false
                    processNext()
                    break
                }
            }
        }
    }
    
    func cancel() {
        currentTask?.cancel()
        pipelineService.cancel()
        isProcessing = false
    }
    
    func removeTask(id: UUID) {
        queue.removeAll { $0.id == id }
    }
    
    func clearQueue() {
        queue.removeAll()
    }
    
    func clearHistory() {
        history.removeAll()
    }
}
```

- [ ] **Step 2: Verify compilation**

Run: `Cmd+B`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add MangaTranslatorMac/ViewModels/QueueViewModel.swift
git commit -m "feat: add QueueViewModel with basic queue processing"
```

### Task 6: Basic UI - Queue View

**Files:**
- Create: `MangaTranslatorMac/Views/QueueView.swift`
- Modify: `MangaTranslatorMac/MangaTranslatorMacApp.swift`

- [ ] **Step 1: Create QueueView**

File: `Views/QueueView.swift`
```swift
import SwiftUI

struct QueueView: View {
    @ObservedObject var viewModel: QueueViewModel
    
    var body: some View {
        VStack(spacing: 0) {
            // Queue section
            VStack(alignment: .leading, spacing: 8) {
                Text("Queue (\(viewModel.queue.count))")
                    .font(.headline)
                    .padding(.horizontal)
                
                if viewModel.queue.isEmpty {
                    Text("No tasks in queue")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding()
                } else {
                    List(viewModel.queue) { task in
                        TaskRow(task: task, isPrivate: viewModel.privacyMode || task.isPrivate)
                    }
                }
            }
            .frame(maxHeight: .infinity)
            
            Divider()
            
            // History section
            VStack(alignment: .leading, spacing: 8) {
                Text("History (\(viewModel.history.count))")
                    .font(.headline)
                    .padding(.horizontal)
                
                if viewModel.history.isEmpty {
                    Text("No completed tasks")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding()
                } else {
                    List(viewModel.history) { task in
                        TaskRow(task: task, isPrivate: viewModel.privacyMode || task.isPrivate)
                    }
                }
            }
            .frame(maxHeight: .infinity)
            
            // Control buttons
            HStack {
                Button("Add Job") {
                    // TODO: File picker
                }
                
                Button("Clear Queue") {
                    viewModel.clearQueue()
                }
                
                Button("Clear History") {
                    viewModel.clearHistory()
                }
            }
            .padding()
        }
        .frame(minWidth: 250)
    }
}

struct TaskRow: View {
    let task: TranslationTask
    let isPrivate: Bool
    
    var body: some View {
        HStack {
            // Thumbnail or placeholder
            if isPrivate {
                Image(systemName: "eye.slash")
                    .frame(width: 50, height: 50)
                    .background(Color.gray.opacity(0.2))
                    .cornerRadius(4)
            } else {
                RoundedRectangle(cornerRadius: 4)
                    .fill(Color.gray.opacity(0.2))
                    .frame(width: 50, height: 50)
                    .overlay(
                        Image(systemName: "photo")
                            .foregroundColor(.secondary)
                    )
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(task.sourceURL.lastPathComponent)
                    .font(.caption)
                    .lineLimit(1)
                
                Text(task.stage.displayName)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                
                if task.stage != .queued && task.stage != .finished && task.stage != .error {
                    ProgressView(value: task.progress)
                        .progressViewStyle(.linear)
                }
                
                if let error = task.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundColor(.red)
                        .lineLimit(1)
                }
            }
            
            Spacer()
            
            // Status badge
            statusBadge
        }
        .padding(.vertical, 4)
    }
    
    @ViewBuilder
    private var statusBadge: some View {
        switch task.stage {
        case .finished:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        case .error:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        case .queued:
            Image(systemName: "clock")
                .foregroundColor(.secondary)
        default:
            ProgressView()
                .scaleEffect(0.7)
        }
    }
}
```

- [ ] **Step 2: Create MainWindow with QueueView**

File: `Views/MainWindow.swift`
```swift
import SwiftUI

struct MainWindow: View {
    @StateObject private var queueViewModel: QueueViewModel
    
    init() {
        let pythonPath = "/usr/bin/python3" // TODO: Bundle embedded Python
        let pipeline = PipelineService(pythonPath: pythonPath)
        _queueViewModel = StateObject(wrappedValue: QueueViewModel(pipelineService: pipeline))
    }
    
    var body: some View {
        HSplitView {
            // Left panel
            QueueView(viewModel: queueViewModel)
                .frame(minWidth: 250, maxWidth: 350)
            
            // Right panel (placeholder)
            VStack {
                Text("Configuration tabs will go here")
                    .font(.title)
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minWidth: 960, minHeight: 540)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(action: {
                    if queueViewModel.isProcessing {
                        queueViewModel.cancel()
                    } else {
                        queueViewModel.processNext()
                    }
                }) {
                    Image(systemName: queueViewModel.isProcessing ? "stop.fill" : "play.fill")
                }
            }
            
            ToolbarItem {
                Toggle(isOn: $queueViewModel.privacyMode) {
                    Image(systemName: "eye.slash")
                }
                .help("Privacy Mode")
            }
        }
    }
}
```

- [ ] **Step 3: Update App entry point**

Modify: `MangaTranslatorMacApp.swift`
```swift
import SwiftUI

@main
struct MangaTranslatorMacApp: App {
    var body: some Scene {
        WindowGroup {
            MainWindow()
        }
        .commands {
            CommandGroup(after: .newItem) {
                Button("Add Job...") {
                    // TODO: Open file picker
                }
                .keyboardShortcut("o")
            }
        }
    }
}
```

- [ ] **Step 4: Build and test UI**

Run: `Cmd+R`
Expected: App launches with queue panel on left, placeholder on right, toolbar buttons visible

- [ ] **Step 5: Commit**

```bash
git add MangaTranslatorMac/Views/
git add MangaTranslatorMac/MangaTranslatorMacApp.swift
git commit -m "feat: add basic UI with queue view and main window"
```

### Task 7: File Picker Integration

**Files:**
- Modify: `MangaTranslatorMac/Views/QueueView.swift`
- Modify: `MangaTranslatorMac/Views/MainWindow.swift`

- [ ] **Step 1: Add file picker to QueueView**

Modify `Views/QueueView.swift`, replace "Add Job" button:
```swift
Button("Add Job") {
    let panel = NSOpenPanel()
    panel.canChooseFiles = true
    panel.canChooseDirectories = false
    panel.allowsMultipleSelection = false
    panel.allowedContentTypes = [.png, .jpeg, .webp]
    
    if panel.runModal() == .OK, let url = panel.url {
        viewModel.addTask(url: url)
    }
}
```

- [ ] **Step 2: Test file selection**

Run: `Cmd+R`
1. Click "Add Job"
2. Select an image file
3. Verify task appears in queue

Expected: Task added to queue with file name visible

- [ ] **Step 3: Commit**

```bash
git add MangaTranslatorMac/Views/QueueView.swift
git commit -m "feat: add file picker for adding tasks to queue"
```

### Task 8: Copy Python Backend Resources

**Files:**
- Create: `MangaTranslatorMac/Resources/`
- Modify: Project settings (Build Phases)

- [ ] **Step 1: Copy MangaStudio_Data config files**

```bash
cd ~/Projects/manga-image-translator/MangaTranslatorMac
mkdir -p Resources/MangaStudio_Data
cp -r ../MangaStudio_Data/ui_map.json Resources/MangaStudio_Data/
cp -r ../MangaStudio_Data/tasks.json Resources/MangaStudio_Data/
cp -r ../MangaStudio_Data/themes Resources/MangaStudio_Data/
```

- [ ] **Step 2: Add resources to Xcode**

1. In Xcode, right-click project → Add Files to "MangaTranslatorMac"
2. Select `Resources/MangaStudio_Data` folder
3. Check "Create folder references"
4. Verify files appear in Project Navigator

- [ ] **Step 3: Update Python path in MainWindow**

Modify `Views/MainWindow.swift`:
```swift
init() {
    // Use system Python for now (Phase 2 will bundle embedded Python)
    let pythonPath = "/usr/bin/python3"
    let pipeline = PipelineService(pythonPath: pythonPath)
    _queueViewModel = StateObject(wrappedValue: QueueViewModel(pipelineService: pipeline))
}
```

- [ ] **Step 4: Commit**

```bash
git add MangaTranslatorMac/Resources/
git commit -m "chore: add MangaStudio_Data config files to resources"
```

### Task 9: End-to-End Integration Test

**Files:**
- Test with actual Python backend

- [ ] **Step 1: Verify manga_translator is installed**

```bash
cd ~/Projects/manga-image-translator
python3 -m manga_translator --version
```

Expected: Version number displayed (e.g., "2.1.0")

- [ ] **Step 2: Test single image translation**

Run: `Cmd+R` in Xcode
1. Click "Add Job"
2. Select a test manga image
3. Click Play button in toolbar
4. Observe progress updates in queue

Expected:
- Task status changes: Queued → Uploading → Detection → OCR → Translating → Rendering → Finished
- Progress bar animates from 0% to 100%
- Task moves to History after completion

- [ ] **Step 3: Verify output file created**

Check: Output file exists at `<input>_translated.<ext>`

- [ ] **Step 4: Document MVP completion**

Create README section:
```markdown
## Phase 1 MVP - Complete ✅

Working features:
- Add single image to queue
- Start/stop translation
- Real-time progress tracking
- Error handling
- History view
- Privacy mode toggle

Known limitations:
- No configuration UI (uses defaults)
- No batch processing
- No Visual Compare
- Uses system Python (not embedded)
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: mark Phase 1 MVP as complete"
```

---

## Chunk 2: Phase 2 - Configuration System

**Goal**: Dynamic UI generation from ui_map.json with all 5 config tabs functional.

### Task 10: ConfigValue and ConfigOption Models

**Files:**
- Create: `MangaTranslatorMac/Models/ConfigValue.swift`
- Create: `MangaTranslatorMac/Models/ConfigOption.swift`

- [ ] **Step 1: Create ConfigValue enum**

File: `Models/ConfigValue.swift`
```swift
import Foundation

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
    
    var intValue: Int? {
        if case .int(let val) = self { return val }
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
    
    var stringArrayValue: [String]? {
        if case .stringArray(let val) = self { return val }
        return nil
    }
    
    // Codable implementation
    enum CodingKeys: String, CodingKey {
        case type, value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode([String].self) {
            self = .stringArray(value)
        } else {
            throw DecodingError.dataCorrupted(
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Unknown type")
            )
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch self {
        case .string(let val):
            try container.encode(val)
        case .int(let val):
            try container.encode(val)
        case .double(let val):
            try container.encode(val)
        case .bool(let val):
            try container.encode(val)
        case .stringArray(let val):
            try container.encode(val)
        }
    }
}
```

- [ ] **Step 2: Create ConfigOption model**

File: `Models/ConfigOption.swift`
```swift
import Foundation

enum WidgetType: String, Codable {
    case segmentedButton = "segmented_button"
    case optionMenu = "optionmenu"
    case optionMenuLanguages = "optionmenu_languages"
    case optionMenuSeparators = "optionmenu_separators"
    case slider
    case checkbox
    case entry
    case entryWithButton = "entry_with_button"
    case translatorChainBuilder = "translator_chain_builder"
    case languageCheckboxGrid = "language_checkbox_grid"
}

struct ConfigOption: Identifiable, Codable {
    let id: String
    let widget: WidgetType
    let group: String
    let label: String
    let defaultValue: ConfigValue
    let tooltip: String?
    let section: String?
    let order: Int
    let values: [String]?  // For dropdown/segmented options
    let placeholder: String?  // For text entry
    let buttonText: String?  // For entry_with_button
    
    enum CodingKeys: String, CodingKey {
        case widget, group, label
        case defaultValue = "default"
        case tooltip, section, order
        case values, placeholder
        case buttonText = "button_text"
    }
}

struct UIMap: Codable {
    let tabOrder: [String]
    let options: [String: ConfigOption]
    
    enum CodingKeys: String, CodingKey {
        case tabOrder = "__tab_order__"
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        tabOrder = try container.decode([String].self, forKey: .tabOrder)
        
        // Decode dynamic keys
        let dynamicContainer = try decoder.container(keyedBy: DynamicCodingKeys.self)
        var options: [String: ConfigOption] = [:]
        
        for key in dynamicContainer.allKeys {
            if key.stringValue != "__tab_order__" {
                var option = try dynamicContainer.decode(ConfigOption.self, forKey: key)
                options[key.stringValue] = option
            }
        }
        
        self.options = options
    }
    
    struct DynamicCodingKeys: CodingKey {
        var stringValue: String
        init?(stringValue: String) {
            self.stringValue = stringValue
        }
        var intValue: Int?
        init?(intValue: Int) {
            return nil
        }
    }
}
```

- [ ] **Step 3: Write tests**

File: `MangaTranslatorMacTests/ConfigValueTests.swift`
```swift
import XCTest
@testable import MangaTranslatorMac

final class ConfigValueTests: XCTestCase {
    func testStringValue() {
        let config = ConfigValue.string("test")
        XCTAssertEqual(config.stringValue, "test")
        XCTAssertNil(config.intValue)
    }
    
    func testDoubleValue() {
        let config = ConfigValue.double(3.14)
        XCTAssertEqual(config.doubleValue, 3.14)
        
        let intConfig = ConfigValue.int(42)
        XCTAssertEqual(intConfig.doubleValue, 42.0)
    }
    
    func testBoolValue() {
        let config = ConfigValue.bool(true)
        XCTAssertEqual(config.boolValue, true)
    }
    
    func testCodable() throws {
        let original = ConfigValue.string("test")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(ConfigValue.self, from: data)
        
        XCTAssertEqual(original, decoded)
    }
}
```

- [ ] **Step 4: Run tests**

Run: `Cmd+U`
Expected: All ConfigValueTests pass

- [ ] **Step 5: Commit**

```bash
git add MangaTranslatorMac/Models/ConfigValue.swift
git add MangaTranslatorMac/Models/ConfigOption.swift
git add MangaTranslatorMacTests/ConfigValueTests.swift
git commit -m "feat: add ConfigValue and ConfigOption models for dynamic UI"
```

### Task 11: ConfigService - Load ui_map.json

**Files:**
- Create: `MangaTranslatorMac/Services/ConfigService.swift`

**Steps:**
- [ ] Write test for loading ui_map.json
- [ ] Implement ConfigService.loadUIMap() to parse JSON
- [ ] Verify all 666 lines of config parse correctly
- [ ] Test grouping by tab (5 tabs expected)
- [ ] Test standard vs advanced section separation
- [ ] Commit

### Task 12: ConfigViewModel

**Files:**
- Create: `MangaTranslatorMac/ViewModels/ConfigViewModel.swift`

**Steps:**
- [ ] Create ConfigViewModel with @Published config dictionary
- [ ] Add methods to get/set config values by key
- [ ] Add tab grouping logic
- [ ] Test config value updates
- [ ] Commit

### Task 13: ConfigOptionRow - Dynamic Widget Rendering

**Files:**
- Create: `MangaTranslatorMac/Views/ConfigOptionRow.swift`

**Steps:**
- [ ] Implement switch statement for all WidgetType cases
- [ ] Render segmented button (Picker with segmented style)
- [ ] Render slider with value display
- [ ] Render checkbox (Toggle)
- [ ] Render option menu (Picker)
- [ ] Render text entry (TextField)
- [ ] Test each widget type with sample data
- [ ] Commit

### Task 14: ConfigView - 5 Tabs

**Files:**
- Create: `MangaTranslatorMac/Views/ConfigView.swift`
- Modify: `MangaTranslatorMac/Views/MainWindow.swift`

**Steps:**
- [ ] Create TabView with 5 tabs (General, Detector, Image, Render, Extra)
- [ ] For each tab, render ConfigOptionRows grouped by section
- [ ] Add separator between standard and advanced settings
- [ ] Integrate ConfigView into MainWindow right panel
- [ ] Test all tabs render correctly
- [ ] Commit

### Task 15: ProfileService - Save/Load

**Files:**
- Create: `MangaTranslatorMac/Services/ProfileService.swift`

**Steps:**
- [ ] Implement save profile to JSON file
- [ ] Implement load profile from JSON file
- [ ] Implement list all profiles
- [ ] Implement delete profile
- [ ] Add toolbar menu for profile management
- [ ] Test save/load round-trip
- [ ] Commit

### Task 16: Wire Config to PipelineService

**Files:**
- Modify: `MangaTranslatorMac/Services/PipelineService.swift`
- Modify: `MangaTranslatorMac/ViewModels/QueueViewModel.swift`

**Steps:**
- [ ] Update buildCommand() to accept config dictionary
- [ ] Map config keys to CLI arguments (--target-lang, --translator, etc.)
- [ ] Pass config from ConfigViewModel to QueueViewModel
- [ ] Test translation with custom config
- [ ] Verify CLI arguments match expected format
- [ ] Commit

---

## Chunk 2: Phase 3-4 - Full Feature Set

**Goal**: Complete all queue operations, special tasks, Visual Compare, themes, and logging.

### Task 17: Enhanced Queue Operations

**Files:**
- Modify: `MangaTranslatorMac/Views/QueueView.swift`
- Modify: `MangaTranslatorMac/ViewModels/QueueViewModel.swift`

**Steps:**
- [ ] Add drag-drop file acceptance (onDrop modifier)
- [ ] Add drag-drop folder support (scan for images recursively)
- [ ] Add drag-drop ZIP support (extract to temp, scan images)
- [ ] Add queue reordering (onMove modifier)
- [ ] Add multi-select delete
- [ ] Add right-click context menu (Remove, Open in Finder, Mark Private)
- [ ] Test batch adding 50+ images
- [ ] Commit

### Task 18: Thumbnail Generation

**Files:**
- Modify: `MangaTranslatorMac/ViewModels/QueueViewModel.swift`
- Modify: `MangaTranslatorMac/Views/QueueView.swift`

**Steps:**
- [ ] Add async thumbnail generation on background queue
- [ ] Downsample images to 60×60 pt
- [ ] Store as Data in TranslationTask
- [ ] Display in TaskRow
- [ ] Test with large images (>20MB)
- [ ] Commit

### Task 19: Privacy Mode - Space Key

**Files:**
- Modify: `MangaTranslatorMac/ViewModels/QueueViewModel.swift`
- Modify: `MangaTranslatorMac/Views/QueueView.swift`

**Steps:**
- [ ] Add NSEvent monitor for Space keyDown/keyUp
- [ ] Add @Published temporaryReveal property
- [ ] Update TaskRow to show/hide based on privacy + temporaryReveal
- [ ] Test Space hold reveals, Space release hides
- [ ] Add Cmd+Shift+P shortcut for global toggle
- [ ] Commit

### Task 20: Special Tasks (RAW/Upscale/Colorize)

**Files:**
- Create: `MangaTranslatorMac/Views/TasksView.swift`
- Create: `MangaTranslatorMac/Models/TaskDefinition.swift`
- Create: `MangaTranslatorMac/Services/TaskDefinitionService.swift`

**Steps:**
- [ ] Load tasks.json with task definitions
- [ ] Create TasksView with segmented picker
- [ ] Apply backend_config overrides when task type selected
- [ ] Filter visible config options based on settings_keys
- [ ] Update PipelineService to handle task type
- [ ] Test RAW Output mode (translator=none, renderer=none)
- [ ] Test Upscaling mode
- [ ] Test Colorization mode
- [ ] Commit

### Task 21: Visual Compare

**Files:**
- Create: `MangaTranslatorMac/Views/VisualCompareView.swift`
- Create: `MangaTranslatorMac/ViewModels/VisualCompareViewModel.swift`
- Create: `MangaTranslatorMac/Views/ImageViewer.swift` (NSViewRepresentable wrapper)

**Steps:**
- [ ] Create side-by-side image viewers using NSImageView
- [ ] Add "Load Test Image" button with file picker
- [ ] Add "Run Test" button to translate single image
- [ ] Implement synchronized zoom (NSMagnificationGestureRecognizer)
- [ ] Implement synchronized pan (NSScrollView binding)
- [ ] Add "Reset View" button
- [ ] Test with sample manga page
- [ ] Commit

### Task 22: Theme System

**Files:**
- Create: `MangaTranslatorMac/Services/ThemeService.swift`
- Create: `MangaTranslatorMac/Models/Theme.swift`

**Steps:**
- [ ] Load themes from Resources/MangaStudio_Data/themes/*.json
- [ ] Parse color mappings
- [ ] Create Theme model
- [ ] Apply theme colors via SwiftUI environment
- [ ] Add theme picker to toolbar
- [ ] Test switching between 7+ themes
- [ ] Commit

### Task 23: Live Log

**Files:**
- Create: `MangaTranslatorMac/Views/LogView.swift`
- Create: `MangaTranslatorMac/ViewModels/LogViewModel.swift`

**Steps:**
- [ ] Create LogViewModel with @Published messages array
- [ ] Parse log level from stdout lines (INFO, WARNING, ERROR, DEBUG)
- [ ] Assign colors based on log level
- [ ] Render in ScrollView with monospace font
- [ ] Add auto-scroll to bottom
- [ ] Add "Clear Log" and "Copy Log" buttons
- [ ] Feed PipelineService stdout to LogViewModel
- [ ] Commit

---

## Chunk 3: Phase 5 - Polish & Release

**Goal**: Testing, error handling polish, packaging for distribution.

### Task 24: Error Recovery Enhancements

**Files:**
- Modify: `MangaTranslatorMac/Services/PipelineService.swift`
- Modify: `MangaTranslatorMac/ViewModels/QueueViewModel.swift`

**Steps:**
- [ ] Implement 429 retry with exponential backoff
- [ ] Implement GPU OOM → CPU fallback
- [ ] Implement process crash recovery (continue queue)
- [ ] Add retry button to error tasks in history
- [ ] Test API rate limiting scenario
- [ ] Test GPU memory exhaustion
- [ ] Commit

### Task 25: Bundle Embedded Python

**Files:**
- Download: python-build-standalone binary
- Modify: Xcode project (Copy Files build phase)
- Modify: `MangaTranslatorMac/Views/MainWindow.swift`

**Steps:**
- [ ] Download python-build-standalone for macOS arm64
- [ ] Extract to Resources/python/
- [ ] Add to Xcode project as bundle resource
- [ ] Update pythonPath in MainWindow to use Bundle.main.resourcePath
- [ ] Install manga_translator dependencies in embedded Python
- [ ] Test translation with embedded Python (no system Python needed)
- [ ] Commit

### Task 26: Comprehensive Testing

**Files:**
- Various test files

**Steps:**
- [ ] Run all unit tests (`Cmd+U`)
- [ ] Manual test checklist (see spec document)
- [ ] Test on clean macOS installation (no Python installed)
- [ ] Test with 100+ image batch
- [ ] Test all configuration options
- [ ] Test all three special task modes
- [ ] Test Visual Compare with multiple images
- [ ] Test privacy mode in various scenarios
- [ ] Document test results
- [ ] Commit

### Task 27: Code Signing & Notarization

**Files:**
- Xcode project settings

**Steps:**
- [ ] Configure Developer ID certificate in Xcode
- [ ] Enable Hardened Runtime
- [ ] Add entitlements (com.apple.security.files.user-selected.read-write)
- [ ] Build archive
- [ ] Export for distribution
- [ ] Notarize with Apple (xcrun notarytool)
- [ ] Staple notarization ticket
- [ ] Verify app launches on macOS 13.0+
- [ ] Document signing process in README
- [ ] Commit

### Task 28: DMG Packaging

**Files:**
- Create: `scripts/create-dmg.sh`

**Steps:**
- [ ] Install create-dmg tool (brew install create-dmg)
- [ ] Create DMG with custom background and app icon
- [ ] Add Applications folder symlink
- [ ] Test DMG installation flow
- [ ] Verify codesigning preserved in DMG
- [ ] Commit

### Task 29: Documentation

**Files:**
- Create: `MangaTranslatorMac/README.md`
- Create: `MangaTranslatorMac/CHANGELOG.md`

**Steps:**
- [ ] Write README with installation instructions
- [ ] Add screenshots of main UI
- [ ] Document system requirements (macOS 13.0+)
- [ ] Write user guide for configuration
- [ ] Write CHANGELOG with feature list
- [ ] Add troubleshooting section
- [ ] Commit

### Task 30: Release

**Files:**
- GitHub release

**Steps:**
- [ ] Tag version (git tag v1.0.0)
- [ ] Push tags to GitHub
- [ ] Create GitHub release
- [ ] Upload DMG to release
- [ ] Write release notes
- [ ] Announce in upstream repository

---

## Implementation Notes

### Testing Strategy

**Unit Tests**: All services and parsers have dedicated test files
**Integration Tests**: PipelineService end-to-end with real Python backend
**UI Tests**: Manual testing checklist from spec document
**Performance Tests**: Large queue (1000+ items), memory profiling

### Commit Frequency

Commit after each task completion (every 2-5 steps). Use conventional commit format:
- `feat:` for new features
- `fix:` for bug fixes
- `chore:` for tooling/config
- `docs:` for documentation
- `test:` for test additions

### Development Order

Follow phases sequentially (1 → 2 → 3 → 4 → 5). Each phase builds on the previous and has clear acceptance criteria.

### Dependencies

- Swift 5.9+
- macOS 13.0+ (SwiftUI features)
- Xcode 15.0+
- python-build-standalone (bundled in Phase 5)
- manga_translator Python package (from parent repo)

### Configuration Files

Reuse existing from Windows version:
- `MangaStudio_Data/ui_map.json` (666 lines)
- `MangaStudio_Data/tasks.json`
- `MangaStudio_Data/themes/*.json` (7+ themes)

No modifications needed - dynamic parsing handles all options.

---

## Plan Complete

**Total Tasks**: 30
**Estimated Duration**: 5 weeks (with full-time focus)
**Deliverable**: Native macOS app with feature parity to Windows version

**Next Steps**:
1. Review this plan
2. Execute using @superpowers:subagent-driven-development (if available)
3. Or execute using @superpowers:executing-plans in current session

**Ready to begin implementation?**