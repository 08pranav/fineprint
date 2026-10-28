"""Quote verification: a flag is only kept if its quote really appears in the clause.

This is FinePrint's main defence against hallucination. A model that invents a clause, or
paraphrases one, cannot pass this check, and its flag is dropped with a warning.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalise(text: str) -> str:
    text = text.translate(_MAP).lower()
    text = re.sub(r"\brs\.?\s*", "₹", text)
    text = re.sub(r"[^\w₹%.,/\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip(" .,;")


def verify_quote(quote: str, clause_text: str, min_ratio: float = 0.9) -> str | None:
    """Return the matching span of the clause (original wording) if the quote is genuine, else None."""
    q = normalise(quote)
    if len(q) < 8:
        return None
    norm_clause = normalise(clause_text)
    if q in norm_clause:
        return _original_span(quote, clause_text) or quote.strip()
    # Tolerate small differences (a dropped comma, a changed quote mark) with a word-window fuzzy match.
    q_words = q.split()
    c_words = norm_clause.split()
    n = len(q_words)
    if n == 0 or len(c_words) < max(3, n - 2):
        return None
    best, best_i = 0.0, -1
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(1, len(c_words) - size + 1)):
            window = " ".join(c_words[i: i + size])
            ratio = SequenceMatcher(None, q, window).ratio()
            if ratio > best:
                best, best_i = ratio, i
    if best >= min_ratio and best_i >= 0:
        window = " ".join(c_words[max(0, best_i - 1): best_i + n + 2])
        if not set(_numbers(q)) <= set(_numbers(window)):
            return None  # wording is close but a number was changed: that is not the same clause
        return _original_span(" ".join(c_words[best_i: best_i + n]), clause_text) or quote.strip()
    return None


def _numbers(text: str) -> list[str]:
    return [n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


def _original_span(quote: str, clause_text: str) -> str | None:
    """Map a normalised match back to the clause's own characters, for display."""
    words = [re.escape(w) for w in normalise(quote).split() if w]
    if not words:
        return None
    pattern = r"\W*".join(words).replace("₹", r"(?:₹|rs\.?\s*)")
    m = re.search(pattern, clause_text, re.IGNORECASE)
    return clause_text[m.start(): m.end()] if m else None
