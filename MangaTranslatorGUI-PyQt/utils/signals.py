"""Qt signals for cross-thread communication"""
from PyQt6.QtCore import QObject, pyqtSignal

class WorkerSignals(QObject):
    """Signals for worker threads"""
    # Progress updates
    progress = pyqtSignal(str, str, float)  # (task_id, message, percentage)

    # Task status
    started = pyqtSignal(str)  # task_id
    finished = pyqtSignal(str)  # task_id
    error = pyqtSignal(str, str)  # (task_id, error_message)

    # Log messages
    log = pyqtSignal(str)  # message
