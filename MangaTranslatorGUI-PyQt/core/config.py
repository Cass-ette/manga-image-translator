"""Configuration management"""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

@dataclass
class AppConfig:
    """Application configuration"""
    # Translation settings
    target_language: str = "ENG"
    translator: str = "google"  # Default to free translator

    # Mode
    mode: Literal["translate", "colorize"] = "translate"

    # Device
    device: str = "cpu"

    # Advanced settings
    detector: str = "default"
    ocr: str = "default"
    inpainter: str = "default"

    # Colorization
    colorization_size: int = 576

    # Output
    output_dir: str = "~/Desktop/MangaTranslator_Output"

    # API Keys (for paid translators)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""

    @staticmethod
    def get_config_path() -> Path:
        """Get config file path"""
        config_dir = Path.home() / ".manga-translator-gui"
        config_dir.mkdir(exist_ok=True)
        return config_dir / "config.json"

    def save(self):
        """Save config to file"""
        config_path = self.get_config_path()
        with open(config_path, 'w') as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> 'AppConfig':
        """Load config from file"""
        config_path = cls.get_config_path()
        if not config_path.exists():
            return cls()

        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return cls(**data)
        except Exception:
            return cls()

# Available options
LANGUAGES = [
    "ENG", "JPN", "CHS", "CHT", "KOR", "VIN", "CSY", "ARA",
    "THA", "RUS", "FRA", "DEU", "NLD", "SPA", "ITA", "TUR",
    "POL", "POR", "BRA", "IND"
]

# Free translators (no API key required)
FREE_TRANSLATORS = [
    "google", "youdao", "baidu", "papago", "original", "none"
]

# Paid translators (require API key)
PAID_TRANSLATORS = [
    "chatgpt", "gpt3.5", "gpt4", "gpt4o",  # OpenAI
    "claude",  # Anthropic
    "gemini",  # Google
    "deepseek",  # DeepSeek
    "deepl",  # DeepL
]

# All translators
TRANSLATORS = FREE_TRANSLATORS + PAID_TRANSLATORS + [
    "sugoi", "caiyun", "qwen2", "groq", "sakura",
    "m2m100", "m2m100_hf", "mbart50", "nllb"
]

DEVICES = ["cpu", "mps", "cuda"]

# API key requirements mapping
API_KEY_MAPPING = {
    "chatgpt": "openai_api_key",
    "gpt3.5": "openai_api_key",
    "gpt4": "openai_api_key",
    "gpt4o": "openai_api_key",
    "claude": "anthropic_api_key",
    "gemini": "gemini_api_key",
    "deepseek": "deepseek_api_key",
}
