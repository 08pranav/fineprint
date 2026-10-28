"""Deterministic extraction of rupee amounts, percentages and durations from Indian financial text.

Handles: ₹1,50,000 · Rs. 1.5 lakh · INR 2,00,000 · 1.5L · 2 crore · Rs.500/- · ₹50k ·
2% p.m. · 24% per annum · 2 per cent · 36 months · 3 years · 30 days.
The language model never does this; it is plain, tested Python.
"""
from __future__ import annotations

import re

from ..schemas import ClauseFields, Duration, Money, Percent

_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SCALE = r"lakhs?|lacs?|crores?|cr\.?|k|thousand|l(?![a-z])"
_CUR = r"₹|rs\.?|inr|rupees"

CURRENCY_FIRST = re.compile(
    rf"(?i)(?:{_CUR})\s*(?P<num>{_NUM})\s*(?P<scale>{_SCALE})?(?:\s*/-)?(?![\d%])"
)
SCALE_ONLY = re.compile(rf"(?i)\b(?P<num>{_NUM})\s*(?P<scale>lakhs?|lacs?|crores?)\b")
NUM_THEN_RUPEES = re.compile(rf"(?i)\b(?P<num>{_NUM})\s*(?:/-\s*)?(?:rupees|rs\.?|inr)\b(?!\s*\d)")

PERCENT = re.compile(
    rf"(?i)(?P<num>\d+(?:\.\d+)?)\s*(?:%|per\s*cent\b|percent\b|pct\b)"
)
MONTHLY = re.compile(r"(?i)^\W{0,3}(?:p\.?\s*m\.?|per\s+month|a\s+month|monthly|every\s+month|per\s+mensem)")
YEARLY = re.compile(r"(?i)^\W{0,3}(?:p\.?\s*a\.?|per\s+annum|per\s+year|a\s+year|annually|yearly|every\s+year|annualised|annualized)")

WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "eighteen": 18,
    "twenty": 20, "twenty-four": 24, "thirty": 30, "thirty-six": 36, "forty-eight": 48, "sixty": 60,
}
DURATION = re.compile(
    r"(?i)\b(?P<num>\d+(?:\.\d+)?|" + "|".join(sorted(WORD_NUM, key=len, reverse=True)) + r")"
    r"(?:\s*\(\d+\))?\s*(?:-\s*)?(?P<unit>months?|mths?|years?|yrs?|days?|weeks?)\b"
)
GST = re.compile(r"(?i)(?:\+|plus|and|exclusive\s+of|excluding|along\s+with)\s*(?:applicable\s+)?(?:gst|taxes|tax)\b|\bgst\s+(?:extra|as\s+applicable|applicable)")


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def _scale(scale: str | None) -> float:
    if not scale:
        return 1.0
    s = scale.lower().rstrip(".")
    if s.startswith(("lakh", "lac")) or s == "l":
        return 100000.0
    if s.startswith("cr"):
        return 10000000.0
    if s in ("k", "thousand"):
        return 1000.0
    return 1.0


def find_money(text: str) -> list[Money]:
    found: list[Money] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    for pattern in (CURRENCY_FIRST, SCALE_ONLY, NUM_THEN_RUPEES):
        for m in pattern.finditer(text):
            if not free(m.start(), m.end()):
                continue
            try:
                value = _to_float(m.group("num")) * _scale(m.groupdict().get("scale"))
            except ValueError:
                continue
            found.append(Money(raw=m.group(0).strip(), value=round(value, 2), start=m.start(), end=m.end()))
            taken.append((m.start(), m.end()))
    return sorted(found, key=lambda x: x.start)


def find_percents(text: str) -> list[Percent]:
    out: list[Percent] = []
    for m in PERCENT.finditer(text):
        tail = text[m.end(): m.end() + 30]
        period = "month" if MONTHLY.search(tail) else "year" if YEARLY.search(tail) else "unspecified"
        out.append(Percent(raw=m.group(0), value=float(m.group("num")), period=period, start=m.start(), end=m.end()))
    return out


def find_durations(text: str) -> list[Duration]:
    out: list[Duration] = []
    for m in DURATION.finditer(text):
        raw_num = m.group("num").lower()
        n = WORD_NUM.get(raw_num)
        if n is None:
            try:
                n = float(raw_num)
            except ValueError:
                continue
        unit = m.group("unit").lower()
        if unit.startswith(("month", "mth")):
            months = n
        elif unit.startswith(("year", "yr")):
            months = n * 12
        elif unit.startswith("week"):
            months = n * 7 / 30.4
        else:
            months = n / 30.4
        out.append(Duration(raw=m.group(0), months=round(months, 2), start=m.start(), end=m.end()))
    return out


def extract_fields(text: str) -> ClauseFields:
    return ClauseFields(
        amounts=find_money(text),
        percents=find_percents(text),
        durations=find_durations(text),
        plus_gst=bool(GST.search(text)),
    )


def inr(value: float | None, decimals: int = 0) -> str:
    """Format in the Indian grouping system: 1234567 -> ₹12,34,567."""
    if value is None:
        return "—"
    negative = value < 0
    value = abs(value)
    rounded = round(value, decimals)
    whole = int(rounded)
    frac = f"{rounded - whole:.{decimals}f}"[1:] if decimals else ""
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if negative else "") + "₹" + s + frac
