"""Flesch Reading Ease for English text: higher = easier (60-70 is plain English, below 30 is very hard).

Used to check that the "Simple" level really is simpler than "Expert" (see eval/run_eval.py).
"""
from __future__ import annotations

import re

WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


def syllables(word: str) -> int:
    w = word.lower()
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def flesch(text: str) -> float | None:
    words = WORD.findall(text)
    if len(words) < 5:
        return None
    sentences = max(1, len(re.findall(r"[.!?]+(?:\s|$)", text)))
    syl = sum(syllables(w) for w in words)
    score = 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syl / len(words))
    return round(score, 1)
