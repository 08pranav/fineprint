"""Split a document into clauses, keeping exact character offsets.

A clause starts at a numbered or bulleted line, or after a blank line. Short title-like lines
become headings for the clauses under them. Very long blocks are split at sentence ends.
"""
from __future__ import annotations

import re

from ..schemas import Clause
from .loader import PAGE_BREAK

LIST_MARKER = re.compile(
    r"^\s*(?:\d{1,2}(?:\.\d{1,2}){0,3}[.)]?\s+(?=\S)|\(?[a-z]\)\s+|\(?[ivxlc]{1,5}\)\s+|[-•*●▪]\s+)",
    re.IGNORECASE,
)
SENTENCE_END = re.compile(
    r"(?<!\bRs)(?<!\bNo)(?<!\bp\.a)(?<!\bp\.m)(?<!\bviz)(?<!\be\.g)(?<!\bi\.e)(?<!\bSr)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bLtd)"
    r"[.;](?=\s+[A-Z(\"'])"
)
MAX_CLAUSE = 520
LABEL = re.compile(r"^(?:\(?(\d{1,2}(?:\.\d{1,2}){0,3})[.)]?\s|\(?([a-z]|[ivxlc]{1,5})[.)]\s)", re.IGNORECASE)


KEY_VALUE = re.compile(r"^[A-Z][\w /&()'.,-]{1,48}:\s*\S")


def _is_heading(line: str) -> bool:
    s = line.strip().rstrip(":")
    if not s or len(s) > 70 or s.endswith((".", ";", ",")) or ":" in s:
        return False
    if LIST_MARKER.match(line) and len(s.split()) > 6:
        return False
    words = re.findall(r"[A-Za-z]+", s)
    if not words or len(words) > 9:
        return False
    if re.search(r"\d+\s*%|₹|Rs\.?\s*\d", s):
        return False
    upper = sum(1 for w in words if w.isupper())
    title = sum(1 for w in words if w[0].isupper())
    return upper == len(words) or title >= max(1, int(0.7 * len(words)))


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(PAGE_BREAK, " ")).strip()


def _split_long(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split [start, end) at sentence ends into pieces of at most ~MAX_CLAUSE characters."""
    segment = text[start:end]
    if len(segment) <= MAX_CLAUSE:
        return [(start, end)]
    cuts = [m.end() for m in SENTENCE_END.finditer(segment)]
    pieces: list[tuple[int, int]] = []
    piece_start = 0
    last_cut = None
    for cut in cuts + [len(segment)]:
        if cut - piece_start > MAX_CLAUSE and last_cut is not None and last_cut > piece_start:
            pieces.append((piece_start, last_cut))
            piece_start = last_cut
        last_cut = cut
    pieces.append((piece_start, len(segment)))
    out = []
    for a, b in pieces:
        while a < b and segment[a].isspace():
            a += 1
        if b > a:
            out.append((start + a, start + b))
    return out


def segment(text: str) -> list[Clause]:
    lines: list[tuple[int, int]] = []
    pos = 0
    for raw in text.split("\n"):
        lines.append((pos, pos + len(raw)))
        pos += len(raw) + 1

    blocks: list[tuple[int, int, str | None]] = []
    heading: str | None = None
    cur_start: int | None = None
    cur_end = 0

    def close() -> None:
        nonlocal cur_start
        if cur_start is not None and cur_end > cur_start:
            blocks.append((cur_start, cur_end, heading))
        cur_start = None

    for a, b in lines:
        line = text[a:b]
        stripped = line.strip().strip(PAGE_BREAK)
        if not stripped:
            close()
            continue
        if _is_heading(stripped) and not re.match(r"^\s*\d", stripped[:1] or ""):
            close()
            heading = _collapse(stripped).rstrip(":")
            continue
        if LIST_MARKER.match(stripped) or KEY_VALUE.match(stripped) or cur_start is None:
            close()
            lead = len(line) - len(line.lstrip())
            cur_start = a + lead
        cur_end = b

    close()

    clauses: list[Clause] = []
    for start, end, head in blocks:
        for s, e in _split_long(text, start, end):
            body = _collapse(text[s:e])
            if len(body) < 3 or not re.search(r"[A-Za-zऀ-ॿ]", body):
                continue
            n = len(clauses) + 1
            page = text.count(PAGE_BREAK, 0, s) + 1
            label = None
            if s == start:
                m = LABEL.match(body)
                label = (m.group(1) or m.group(2)) if m else None
            clauses.append(Clause(id=f"C{n}", number=n, label=label, text=body, start=s, end=e, page=page, heading=head))
    return clauses
