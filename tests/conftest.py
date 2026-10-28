import os
import sys
from pathlib import Path

# Tests never call a real model: force rules-only mode before the app is imported.
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"


def sample(name: str) -> str:
    return (SAMPLES / name).read_text(encoding="utf-8")


class FakeLLM:
    """Returns canned replies in order, and records the prompts it was sent."""

    name = "fake-model"

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system, user, *, json_mode=False, max_tokens=1500):
        self.calls.append((system, user))
        return self.replies.pop(0) if self.replies else "{}"
