"""Find the reference note that explains why a flagged clause matters."""
from __future__ import annotations

import json
from functools import lru_cache

from ..config import get_settings
from ..schemas import KBNote
from .bm25 import BM25, tokenize


@lru_cache(maxsize=1)
def _load() -> tuple[list[dict], BM25]:
    entries = json.loads(get_settings().kb_path.read_text(encoding="utf-8"))
    index = BM25([tokenize(e["title"] + " " + e["body"]) for e in entries])
    return entries, index


def _note(e: dict) -> KBNote:
    return KBNote(id=e["id"], title=e["title"], body=e["body"], source_name=e["source_name"], source_url=e["source_url"])


def for_flag(category: str, clause_text: str) -> KBNote | None:
    """Among notes tagged with this category, pick the one whose text best matches the clause."""
    entries, index = _load()
    candidates = [i for i, e in enumerate(entries) if category in e["categories"]]
    if not candidates:
        return None
    scores = index.scores(tokenize(clause_text))
    best = max(candidates, key=lambda i: (scores[i], -i))
    return _note(entries[best])


def search(query: str, k: int = 2) -> list[KBNote]:
    entries, index = _load()
    return [_note(entries[i]) for i, _ in index.top(tokenize(query), k=k, min_score=1.0)]
