"""Mask personal identifiers before the text is stored, shown or sent to a language model.

Order matters: longer and more specific patterns run first so a card number is not mistaken
for an Aadhaar number, and money amounts with Indian commas (1,50,000) are never touched.
"""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "name",
        re.compile(
            r"((?i:applicant|borrower|co-borrower|customer|student|insured person|insured member|proposer|cardholder|card member|nominee|guarantor)"
            r"(?i:[ \t]+name)?[ \t]*[:\-][ \t]*)(?!(?:Rs|Rupees|Nil|None|Not|The|As|Per)\b)([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){0,3})"
        ),
    ),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("card", re.compile(r"(?<![\d,])(?:\d{4}[ -]){3}\d{4}(?!\d)|(?<![\d,])\d{16}(?!\d)")),
    ("aadhaar", re.compile(r"(?<![\d,])[2-9]\d{3}[ -]\d{4}[ -]\d{4}(?!\d)|(?<![\d,])[2-9]\d{11}(?!\d)")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    (
        "account",
        re.compile(
            r"(?i)((?:loan\s+)?(?:a/c|account|acct|application|customer\s+id|loan\s+id|policy)\s*"
            r"(?:no\.?|number|#|id)?\s*[:\-]?\s*)([A-Z]{0,4}\d[\dX]{5,19})"
        ),
    ),
    ("phone", re.compile(r"(?<![\d,])(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
]

TOKENS = {
    "name": "[NAME]",
    "email": "[EMAIL]",
    "card": "[CARD NUMBER]",
    "aadhaar": "[AADHAAR]",
    "pan": "[PAN]",
    "account": "[ACCOUNT NUMBER]",
    "phone": "[PHONE]",
}


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """Return the masked text and a count of what was masked, by kind."""
    counts: dict[str, int] = {}
    for kind, pattern in PATTERNS:
        if kind in ("account", "name"):
            def repl(m: re.Match[str], token: str = TOKENS[kind]) -> str:
                return m.group(1) + token
        else:
            def repl(m: re.Match[str], token: str = TOKENS[kind]) -> str:
                return token
        text, n = pattern.subn(repl, text)
        if n:
            counts[kind] = counts.get(kind, 0) + n
    return text, counts
