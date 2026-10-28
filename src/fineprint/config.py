"""All settings come from environment variables (or a .env file) so nothing is hard-coded."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Language model: any OpenAI-compatible endpoint (OpenAI, Groq, Gemini, OpenRouter, Ollama...).
    # Leave LLM_API_KEY empty to run in rules-only mode.
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "").strip())
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", "").strip())
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "").strip())
    llm_temperature: float = field(default_factory=lambda: _float("LLM_TEMPERATURE", 0.0))
    llm_timeout_s: float = field(default_factory=lambda: _float("LLM_TIMEOUT_S", 45.0))
    llm_batch_size: int = field(default_factory=lambda: _int("LLM_BATCH_SIZE", 25))

    # Input limits (also enforced in the UI, so users are told before they upload).
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 5))
    max_chars: int = field(default_factory=lambda: _int("MAX_CHARS", 60000))
    min_chars: int = field(default_factory=lambda: _int("MIN_CHARS", 120))

    web_dir: Path = PROJECT_ROOT / "web"
    samples_dir: Path = PROJECT_ROOT / "data" / "samples"
    kb_path: Path = PACKAGE_DIR / "kb" / "reference.json"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)


def get_settings() -> Settings:
    """Read settings fresh, so tests can change environment variables."""
    return Settings()
