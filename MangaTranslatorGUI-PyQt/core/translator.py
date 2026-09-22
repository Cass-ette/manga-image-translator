"""Translator and colorizer wrapper"""
import asyncio
import sys
from pathlib import Path
from PIL import Image

# Add manga-image-translator to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from manga_translator.colorization import dispatch as colorize_dispatch, prepare as colorize_prepare
from manga_translator.config import Colorizer


class TranslationTask:
    """Single translation/colorization task"""

    def __init__(self, input_path: str, output_path: str, config):
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.config = config
        self.status = "queued"  # queued, processing, completed, failed
        self.progress = 0.0
        self.error = None


async def run_colorization(task: TranslationTask, progress_callback=None):
    """Run colorization on a single image"""
    try:
        task.status = "processing"
        task.progress = 0.1

        if progress_callback:
            progress_callback(task, "Loading image...")

        # Load image
        img = Image.open(task.input_path)

        if progress_callback:
            progress_callback(task, "Preparing model...")
        task.progress = 0.3

        # Prepare model
        await colorize_prepare(Colorizer.mc2)

        if progress_callback:
            progress_callback(task, "Colorizing...")
        task.progress = 0.5

        # Colorize
        result = await colorize_dispatch(
            Colorizer.mc2,
            device=task.config.device,
            image=img,
            colorization_size=task.config.colorization_size
        )

        if progress_callback:
            progress_callback(task, "Saving result...")
        task.progress = 0.9

        # Save
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(task.output_path)

        task.status = "completed"
        task.progress = 1.0

        if progress_callback:
            progress_callback(task, "Completed")

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        if progress_callback:
            progress_callback(task, f"Error: {e}")
        raise


async def run_translation(task: TranslationTask, progress_callback=None):
    """Run translation on a single image"""
    import subprocess
    import os
    import json
    import tempfile

    try:
        task.status = "processing"
        task.progress = 0.1

        if progress_callback:
            progress_callback(task, "Starting translation...")

        project_root = Path(__file__).parent.parent.parent
        venv_python = str(project_root / "venv" / "bin" / "python")
        result_file = project_root / "result" / "final.png"

        # Create config file
        config = {
            "translator": {
                "translator": task.config.translator,
                "target_lang": task.config.target_language,
            }
        }

        if task.config.detector and task.config.detector != "default":
            config["detector"] = {"detector": task.config.detector}
        if task.config.ocr and task.config.ocr != "default":
            config["ocr"] = {"ocr": task.config.ocr}
        if task.config.inpainter and task.config.inpainter != "default":
            config["inpainter"] = {"inpainter": task.config.inpainter}

        # Write config to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_file = f.name

        # Build command
        args = [
            venv_python, "-m", "manga_translator",
            "-v",
            "local",
            "-i", str(task.input_path),
            "--config-file", config_file,
        ]

        # Device
        if task.config.device in ["mps", "cuda"]:
            args.append("--use-gpu")

        # Set API keys as environment variables
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project_root)

        if task.config.openai_api_key:
            env["OPENAI_API_KEY"] = task.config.openai_api_key
        if task.config.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = task.config.anthropic_api_key
        if task.config.deepseek_api_key:
            env["DEEPSEEK_API_KEY"] = task.config.deepseek_api_key
        if task.config.gemini_api_key:
            env["GOOGLE_API_KEY"] = task.config.gemini_api_key

        if progress_callback:
            progress_callback(task, "Running manga_translator...")

        # Run process
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(project_root)
        )

        try:
            # Read output line by line
            stdout_lines = []
            stderr_lines = []

            while True:
                # Read stdout
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    stdout_lines.append(line)

                    if not line:
                        continue

                    # Parse progress from output
                    if "detection" in line.lower():
                        task.progress = 0.2
                        if progress_callback:
                            progress_callback(task, "Detecting text...")
                    elif "ocr" in line.lower():
                        task.progress = 0.4
                        if progress_callback:
                            progress_callback(task, "Running OCR...")
                    elif "translat" in line.lower():
                        task.progress = 0.6
                        if progress_callback:
                            progress_callback(task, "Translating...")
                    elif "inpaint" in line.lower():
                        task.progress = 0.7
                        if progress_callback:
                            progress_callback(task, "Inpainting...")
                    elif "render" in line.lower():
                        task.progress = 0.9
                        if progress_callback:
                            progress_callback(task, "Rendering...")

                # Check if process finished
                if process.poll() is not None:
                    # Read remaining output
                    remaining = process.stdout.read()
                    if remaining:
                        stdout_lines.extend(remaining.strip().split('\n'))

                    # Read all stderr
                    stderr = process.stderr.read()
                    if stderr:
                        stderr_lines = stderr.strip().split('\n')
                    break

            # Wait for completion
            process.wait()

            if process.returncode == 0:
                # Copy result from default location to target path
                import shutil
                if result_file.exists():
                    task.output_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(result_file, task.output_path)

                task.status = "completed"
                task.progress = 1.0
                if progress_callback:
                    progress_callback(task, "Translation completed")
            else:
                # Get error details
                error_msg = '\n'.join(stderr_lines[-5:]) if stderr_lines else f"Exit code {process.returncode}"
                task.status = "failed"
                task.error = error_msg
                if progress_callback:
                    progress_callback(task, f"Error: {error_msg}")
                raise Exception(error_msg)
        finally:
            # Clean up temp config file
            try:
                os.unlink(config_file)
            except:
                pass

    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        if progress_callback:
            progress_callback(task, f"Error: {e}")
        raise
