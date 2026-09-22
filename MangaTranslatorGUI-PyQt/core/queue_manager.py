"""Queue manager for processing tasks"""
import asyncio
import json
from pathlib import Path
from typing import List, Callable
from .translator import TranslationTask, run_colorization, run_translation


class QueueManager:
    """Manages translation/colorization queue"""

    def __init__(self, config):
        self.config = config
        self.queue: List[TranslationTask] = []
        self.current_task: TranslationTask = None
        self.is_processing = False
        self.progress_callback: Callable = None
        self.queue_state_file = Path.home() / ".manga-translator-gui" / "queue_state.json"

    def add_files(self, file_paths: List[str]):
        """Add files to queue"""
        output_dir = Path(self.config.output_dir).expanduser()

        for file_path in file_paths:
            input_path = Path(file_path)
            if not input_path.exists():
                continue

            # Generate output path
            output_path = output_dir / input_path.name

            # Skip if already completed
            if output_path.exists():
                continue

            task = TranslationTask(str(input_path), str(output_path), self.config)
            self.queue.append(task)

        self.save_queue_state()

    def remove_task(self, index: int):
        """Remove task from queue"""
        if 0 <= index < len(self.queue):
            del self.queue[index]
            self.save_queue_state()

    def clear_queue(self):
        """Clear all queued tasks"""
        self.queue = [t for t in self.queue if t.status == "processing"]
        self.save_queue_state()

    async def process_queue(self):
        """Process all tasks in queue"""
        self.is_processing = True

        while self.queue and self.is_processing:
            # Get next queued task
            task = next((t for t in self.queue if t.status == "queued"), None)
            if not task:
                break

            self.current_task = task

            try:
                # Update task config with current config (allows mid-queue config changes)
                task.config = self.config

                if self.config.mode == "colorize":
                    await run_colorization(task, self._on_progress)
                else:
                    await run_translation(task, self._on_progress)

            except Exception as e:
                task.status = "failed"
                task.error = str(e)

            # Save state after each task completes
            self.save_queue_state()
            self.current_task = None

        self.is_processing = False

    def stop_processing(self):
        """Stop processing queue"""
        self.is_processing = False

    def _on_progress(self, task: TranslationTask, message: str):
        """Internal progress callback"""
        if self.progress_callback:
            self.progress_callback(task, message)

    def set_progress_callback(self, callback: Callable):
        """Set progress callback"""
        self.progress_callback = callback

    def save_queue_state(self):
        """Save queue state to file"""
        state = {
            "tasks": [
                {
                    "input_path": task.input_path,
                    "output_path": task.output_path,
                    "status": task.status,
                }
                for task in self.queue
            ]
        }
        self.queue_state_file.parent.mkdir(exist_ok=True)
        with open(self.queue_state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def load_queue_state(self):
        """Load queue state from file"""
        if not self.queue_state_file.exists():
            return

        try:
            with open(self.queue_state_file, 'r') as f:
                state = json.load(f)

            for task_data in state.get("tasks", []):
                # Skip completed tasks
                if task_data["status"] == "completed":
                    continue

                # Skip if output already exists (completed in previous run)
                output_path = Path(task_data["output_path"])
                if output_path.exists():
                    continue

                # Recreate task
                task = TranslationTask(
                    task_data["input_path"],
                    task_data["output_path"],
                    self.config
                )
                task.status = "queued"  # Reset to queued
                self.queue.append(task)

        except Exception:
            pass  # Ignore errors loading state
