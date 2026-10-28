"""Rule-based risk classifier: the transparent baseline, and the safety net when no model is configured."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..extract.money import find_money, find_percents
from ..schemas import Clause
from .taxonomy import CATEGORIES, RULE_THRESHOLD, Category

SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-Z(\"'])")


@dataclass
class RuleHit:
    clause_id: str
    category: str
    score: int
    quote: str
    cue: str
    cue_pos: int  # position of the strongest cue inside the clause text


def _sentences(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in SENTENCE_SPLIT.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if b > a]


def quote_around(text: str, pos: int, max_len: int = 320) -> str:
    """The sentence that contains `pos`, trimmed to max_len on a word boundary."""
    spans = _sentences(text) or [(0, len(text))]
    a, b = next(((a, b) for a, b in spans if a <= pos < b), spans[-1])
    sentence = text[a:b]
    if len(sentence.strip()) <= max_len:
        return sentence.strip()
    rel = pos - a
    start = max(0, min(rel - max_len // 3, len(sentence) - max_len))
    cut = sentence[start: start + max_len]
    if start > 0:
        cut = cut[cut.find(" ") + 1:]
    if start + max_len < len(sentence):
        cut = cut[: cut.rfind(" ")]
    return cut.strip()


def _has_nonzero_number(text: str) -> bool:
    return any(m.value > 0 for m in find_money(text)) or any(p.value > 0 for p in find_percents(text))


ABBREV_DOT = re.compile(r"(?<=\d)\.(?=\d)|(?<=\b[Rr]s)\.|(?<=\b[Nn]o)\.|(?<=\bp)\.(?=\s?[am]\b)|(?<=\bp\.[am])\.|(?<=\b[ie])\.(?=[eg]\.)|(?<=\b[ie]\.[eg])\.")


def cue_text(text: str) -> str:
    """Same length as `text`, but dots in 3.75, Rs., No., p.a. and i.e. become commas so cue
    patterns that stop at a sentence end ([^.]) are not cut short by a decimal point."""
    return ABBREV_DOT.sub(",", text)


def score_category(cat: Category, text: str) -> tuple[int, bool, int, str]:
    """Return (total score, has strong cue, position of best cue, cue text)."""
    text = cue_text(text)
    total, strong, best_pos, best_w, cue = 0, False, -1, 0, ""
    for pattern, weight in cat.cue_patterns:
        m = pattern.search(text)
        if not m:
            continue
        total += weight
        if weight >= 2:
            strong = True
        if weight > best_w:
            best_w, best_pos, cue = weight, m.start(), m.group(0)
    return total, strong, best_pos, cue


def classify_clause(clause: Clause) -> list[RuleHit]:
    hits: list[RuleHit] = []
    text = clause.text
    for cat in CATEGORIES:
        total, strong, pos, cue = score_category(cat, text)
        if not (strong and total >= RULE_THRESHOLD) and total < 3:
            continue
        if any(p.search(text) for p in cat.benign_patterns):
            # "Foreclosure charges: Nil" is good news. Only keep the flag if a real charge is also stated.
            benign_free = text
            for p in cat.benign_patterns:
                benign_free = p.sub(" ", benign_free)
            if not _has_nonzero_number(benign_free) or score_category(cat, benign_free)[0] < RULE_THRESHOLD:
                continue
        hits.append(RuleHit(clause.id, cat.id, total, quote_around(text, max(pos, 0)), cue, max(pos, 0)))
    return hits


def classify(clauses: list[Clause]) -> list[RuleHit]:
    out: list[RuleHit] = []
    for c in clauses:
        out.extend(classify_clause(c))
    return out
