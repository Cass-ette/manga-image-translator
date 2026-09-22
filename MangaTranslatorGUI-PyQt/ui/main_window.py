"""Main application window"""
import sys
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QListWidget, QTabWidget, QLabel,
    QComboBox, QRadioButton, QButtonGroup, QFileDialog,
    QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.config import AppConfig, LANGUAGES, TRANSLATORS, DEVICES
from core.queue_manager import QueueManager
from core.translator import TranslationTask


class WorkerThread(QThread):
    """Worker thread for async processing"""
    finished = pyqtSignal()
    progress = pyqtSignal(object, str)  # (task, message)

    def __init__(self, queue_manager):
        super().__init__()
        self.queue_manager = queue_manager
        self.loop = None

    def run(self):
        """Run async processing in thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.queue_manager.set_progress_callback(self._on_progress)

        try:
            self.loop.run_until_complete(self.queue_manager.process_queue())
        finally:
            self.loop.close()
            self.finished.emit()

    def _on_progress(self, task, message):
        """Progress callback"""
        self.progress.emit(task, message)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.config = AppConfig.load()
        self.queue_manager = QueueManager(self.config)
        self.worker_thread = None

        self.init_ui()
        self.load_saved_config()

        # Load saved queue state (resume interrupted tasks)
        self.queue_manager.load_queue_state()
        self.update_queue_list()
        if self.queue_manager.queue:
            self.add_log(f"Resumed {len(self.queue_manager.queue)} pending task(s)")

        self.setAcceptDrops(True)

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Manga Translator")
        self.setGeometry(100, 100, 960, 600)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout (horizontal split)
        main_layout = QHBoxLayout(central_widget)

        # Left panel: Queue
        left_panel = self.create_queue_panel()
        main_layout.addWidget(left_panel, stretch=1)

        # Right panel: Config + Log tabs
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, stretch=2)

    def create_queue_panel(self):
        """Create queue panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Title
        title = QLabel("Queue")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Queue list
        self.queue_list = QListWidget()
        self.queue_list.setAlternatingRowColors(True)
        layout.addWidget(self.queue_list)

        # Buttons
        btn_layout = QHBoxLayout()

        self.add_btn = QPushButton("+ Add Files")
        self.add_btn.clicked.connect(self.add_files)
        btn_layout.addWidget(self.add_btn)

        self.add_folder_btn = QPushButton("+ Add Folder")
        self.add_folder_btn.clicked.connect(self.add_folder)
        btn_layout.addWidget(self.add_folder_btn)

        self.remove_btn = QPushButton("× Remove")
        self.remove_btn.clicked.connect(self.remove_selected)
        btn_layout.addWidget(self.remove_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.clicked.connect(self.clear_queue)
        btn_layout.addWidget(self.clear_btn)

        layout.addLayout(btn_layout)

        return panel

    def create_right_panel(self):
        """Create right panel with tabs"""
        tabs = QTabWidget()

        # Config tab
        config_tab = self.create_config_tab()
        tabs.addTab(config_tab, "Configuration")

        # Log tab
        log_tab = self.create_log_tab()
        tabs.addTab(log_tab, "Log")

        return tabs

    def create_config_tab(self):
        """Create configuration tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Target Language
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Target Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES)
        self.lang_combo.setCurrentText(self.config.target_language)
        self.lang_combo.currentTextChanged.connect(self.on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()
        layout.addLayout(lang_layout)

        # Translator
        trans_layout = QHBoxLayout()
        trans_layout.addWidget(QLabel("Translator:"))
        self.trans_combo = QComboBox()
        self.trans_combo.addItems(TRANSLATORS)
        self.trans_combo.setCurrentText(self.config.translator)
        self.trans_combo.currentTextChanged.connect(self.on_translator_changed)
        trans_layout.addWidget(self.trans_combo)
        trans_layout.addStretch()
        layout.addLayout(trans_layout)

        # API Key (shown for paid translators)
        self.api_key_layout = QHBoxLayout()
        self.api_key_label = QLabel("API Key:")
        self.api_key_layout.addWidget(self.api_key_label)

        from PyQt6.QtWidgets import QLineEdit
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter API key...")
        self.api_key_input.textChanged.connect(self.on_api_key_changed)
        self.api_key_layout.addWidget(self.api_key_input)
        self.api_key_layout.addStretch()

        self.api_key_widget = QWidget()
        self.api_key_widget.setLayout(self.api_key_layout)
        self.api_key_widget.setVisible(False)  # Hidden by default
        layout.addWidget(self.api_key_widget)

        # Mode
        layout.addWidget(QLabel("Mode:"))
        self.mode_group = QButtonGroup()

        self.translate_radio = QRadioButton("Translate")
        self.translate_radio.setChecked(True)
        self.translate_radio.toggled.connect(self.on_mode_changed)
        self.mode_group.addButton(self.translate_radio)
        layout.addWidget(self.translate_radio)

        self.colorize_radio = QRadioButton("Colorize")
        self.colorize_radio.toggled.connect(self.on_mode_changed)
        self.mode_group.addButton(self.colorize_radio)
        layout.addWidget(self.colorize_radio)

        # Device
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("Device:"))
        self.device_combo = QComboBox()
        self.device_combo.addItems(DEVICES)
        self.device_combo.setCurrentText(self.config.device)
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        device_layout.addWidget(self.device_combo)
        device_layout.addStretch()
        layout.addLayout(device_layout)

        # Output directory
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Dir:"))
        self.output_label = QLabel(self.config.output_dir)
        self.output_label.setStyleSheet("color: #666; font-size: 11px;")
        output_layout.addWidget(self.output_label, stretch=1)

        self.output_btn = QPushButton("Browse...")
        self.output_btn.clicked.connect(self.choose_output_dir)
        output_layout.addWidget(self.output_btn)
        layout.addLayout(output_layout)

        layout.addStretch()

        # Control buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Queue")
        self.start_btn.clicked.connect(self.start_processing)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        return widget

    def create_log_tab(self):
        """Create log tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        from PyQt6.QtWidgets import QTextEdit
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self.log_text)

        return widget

    def add_files(self):
        """Add files to queue"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )

        if files:
            self.queue_manager.add_files(files)
            self.update_queue_list()
            self.add_log(f"Added {len(files)} file(s) to queue")

    def add_folder(self):
        """Add all images from folder to queue"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with Images",
            ""
        )

        if folder:
            from pathlib import Path
            folder_path = Path(folder)

            # Find all images recursively
            image_files = []
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
                image_files.extend(folder_path.glob(ext))
                image_files.extend(folder_path.glob(ext.upper()))

            # Convert to strings
            file_paths = [str(f) for f in image_files]

            if file_paths:
                self.queue_manager.add_files(file_paths)
                self.update_queue_list()
                self.add_log(f"Added {len(file_paths)} file(s) from folder: {folder}")
            else:
                QMessageBox.warning(self, "No Images", "No image files found in the selected folder.")

    def load_saved_config(self):
        """Load saved config values into UI"""
        self.lang_combo.setCurrentText(self.config.target_language)
        self.trans_combo.setCurrentText(self.config.translator)
        self.device_combo.setCurrentText(self.config.device)
        self.output_label.setText(self.config.output_dir)

        if self.config.mode == "colorize":
            self.colorize_radio.setChecked(True)
        else:
            self.translate_radio.setChecked(True)

        # Trigger translator changed to show API key field if needed
        self.on_translator_changed(self.config.translator)

    def choose_output_dir(self):
        """Choose output directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self.config.output_dir
        )

        if dir_path:
            self.config.output_dir = dir_path
            self.output_label.setText(dir_path)
            self.config.save()
            self.add_log(f"Output directory: {dir_path}")

    def on_language_changed(self, language: str):
        """Handle language change"""
        self.config.target_language = language
        self.config.save()

    def on_translator_changed(self, translator: str):
        """Handle translator change"""
        self.config.translator = translator
        self.config.save()

        # Show/hide API key input for paid translators
        from core.config import API_KEY_MAPPING
        if translator in API_KEY_MAPPING:
            self.api_key_widget.setVisible(True)
            self.api_key_label.setText(f"{translator.upper()} API Key:")

            # Load existing key if any
            key_attr = API_KEY_MAPPING[translator]
            existing_key = getattr(self.config, key_attr, "")
            self.api_key_input.setText(existing_key)
        else:
            self.api_key_widget.setVisible(False)

    def on_mode_changed(self):
        """Handle mode change"""
        if self.translate_radio.isChecked():
            self.config.mode = "translate"
        else:
            self.config.mode = "colorize"
        self.config.save()

    def on_device_changed(self, device: str):
        """Handle device change"""
        self.config.device = device
        self.config.save()

    def on_api_key_changed(self, key: str):
        """Handle API key change"""
        from core.config import API_KEY_MAPPING
        translator = self.config.translator

        if translator in API_KEY_MAPPING:
            key_attr = API_KEY_MAPPING[translator]
            setattr(self.config, key_attr, key)
            self.config.save()

    def remove_selected(self):
        """Remove selected task from queue"""
        current_row = self.queue_list.currentRow()
        if current_row >= 0:
            self.queue_manager.remove_task(current_row)
            self.update_queue_list()

    def clear_queue(self):
        """Clear all queued tasks"""
        if not self.queue_manager.queue:
            return

        reply = QMessageBox.question(
            self,
            "Clear Queue",
            "Remove all tasks from queue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.queue_manager.clear_queue()
            self.update_queue_list()
            self.add_log("Queue cleared")

    def update_queue_list(self):
        """Update queue list display"""
        self.queue_list.clear()

        for task in self.queue_manager.queue:
            status_icon = {
                "queued": "⏸",
                "processing": "●",
                "completed": "✓",
                "failed": "✗"
            }.get(task.status, "?")

            item_text = f"{status_icon} {task.input_path.name}"
            if task.status == "processing":
                item_text += f" ({task.progress:.0%})"

            self.queue_list.addItem(item_text)

    def start_processing(self):
        """Start processing queue"""
        if not self.queue_manager.queue:
            QMessageBox.warning(self, "Empty Queue", "Please add files to the queue first.")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.add_log("Starting queue processing...")

        # Start worker thread
        self.worker_thread = WorkerThread(self.queue_manager)
        self.worker_thread.finished.connect(self.on_processing_finished)
        self.worker_thread.progress.connect(self.on_progress)
        self.worker_thread.start()

    def stop_processing(self):
        """Stop processing queue"""
        self.queue_manager.stop_processing()
        self.add_log("Stopping queue...")

    def on_processing_finished(self):
        """Called when processing finishes"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_log("Queue processing finished")
        self.update_queue_list()

    def on_progress(self, task, message):
        """Update progress"""
        self.update_queue_list()
        self.add_log(f"[{task.input_path.name}] {message}")

    def add_log(self, message):
        """Add log message"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop"""
        from pathlib import Path

        all_files = []

        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())

            if path.is_file():
                # Single file
                if path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                    all_files.append(str(path))

            elif path.is_dir():
                # Directory - find all images
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.webp']:
                    all_files.extend([str(f) for f in path.glob(ext)])
                    all_files.extend([str(f) for f in path.glob(ext.upper())])

        if all_files:
            self.queue_manager.add_files(all_files)
            self.update_queue_list()
            self.add_log(f"Dropped {len(all_files)} file(s)")
