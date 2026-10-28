"""Entry point for hosts that look for `app` in a root app.py (Vercel). Docker and local runs use fineprint.api directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fineprint.api import app  # noqa: E402,F401
