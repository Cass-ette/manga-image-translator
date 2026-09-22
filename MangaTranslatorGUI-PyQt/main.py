#!/usr/bin/env python3
"""Manga Translator GUI - PyQt6 version"""
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.main_window import MainWindow


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Manga Translator")
    app.setOrganizationName("MangaTranslator")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
