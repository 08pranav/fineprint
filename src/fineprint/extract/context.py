"""Find the document-level numbers (amount, rate, tenure, EMI) and guess the document type.

These pre-fill the editable "Your numbers" form in the UI. The user can always correct them.
"""
from __future__ import annotations

import re

from ..schemas import Clause, LoanContext
from .money import find_durations, find_money, find_percents

PRINCIPAL_LABEL = re.compile(
    r"(?i)\b(loan amount|amount of (?:the )?loan|sanctioned amount|sanction amount|loan sanctioned|"
    r"amount financed|principal amount|principal|credit limit|total credit limit|card limit|purchase price|"
    r"product price|order value|cart value|invoice value|sum insured|cover amount|loan of)\b"
)
RATE_LABEL = re.compile(
    r"(?i)\b(rate of interest|interest rate|\bROI\b|annual percentage rate|\bAPR\b|interest @|interest at|finance charges?)"
)
TENURE_LABEL = re.compile(
    r"(?i)\b(tenure|loan term|term of (?:the )?loan|repayment period|repayable (?:over|in)|policy term|"
    r"number of (?:emis|instalments|installments)|no\. of (?:emis|instalments)|emi plan of)\b"
)
EMI_LABEL = re.compile(r"(?i)\b(emi amount|monthly instal+ment|instal+ment amount|emi of|emi\b)")

DOC_TYPES: dict[str, list[str]] = {
    "credit_card": [r"credit card", r"cardholder|card member", r"minimum amount due|minimum due", r"billing (cycle|statement)", r"credit limit"],
    "bnpl": [r"no[- ]cost emi|zero[- ]cost emi|0\s*% emi", r"pay later|buy now", r"merchant", r"order|purchase"],
    "insurance": [r"\bpolicy(holder)?\b", r"\binsured\b", r"\bpremium\b", r"\bclaim", r"waiting period|exclusion"],
    "subscription": [r"subscription|membership", r"auto[- ]?renew|renews automatically", r"cancel"],
    "loan": [r"\bloan\b", r"\bborrower\b", r"\bemi\b", r"sanction", r"foreclos|prepay"],
}
DOC_LABELS = {
    "loan": "Loan agreement",
    "credit_card": "Credit card terms",
    "bnpl": "EMI / pay-later offer",
    "insurance": "Insurance policy",
    "subscription": "Subscription terms",
}


def detect_doc_type(text: str) -> str:
    lower = text.lower()
    scores = {kind: sum(len(re.findall(p, lower)) for p in pats) for kind, pats in DOC_TYPES.items()}
    # Loan words appear in most documents; give the specific types a small edge.
    scores["loan"] = scores["loan"] * 0.8
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "loan"


def _after_label(clause: Clause, label: re.Pattern[str]):
    m = label.search(clause.text)
    return (m.end(), m) if m else (None, None)


def extract_context(clauses: list[Clause], full_text: str) -> LoanContext:
    ctx = LoanContext(doc_type=detect_doc_type(full_text))
    for c in clauses:
        text = c.text
        if ctx.principal is None:
            pos, _ = _after_label(c, PRINCIPAL_LABEL)
            if pos is not None:
                amounts = [a for a in find_money(text) if a.start >= pos - 2 and a.start - pos < 60 and a.value >= 500]
                if amounts:
                    ctx.principal = amounts[0].value
                    ctx.sources["principal"] = c.id
        if ctx.annual_rate is None:
            pos, _ = _after_label(c, RATE_LABEL)
            if pos is not None and not re.search(r"(?i)penal|late|overdue|default", text[: pos + 10]):
                pcts = [p for p in find_percents(text) if p.start >= pos - 2 and p.start - pos < 60]
                if pcts:
                    p = pcts[0]
                    ctx.annual_rate = round(p.value * 12, 2) if p.period == "month" else p.value
                    ctx.sources["annual_rate"] = c.id
        if ctx.tenure_months is None:
            pos, _ = _after_label(c, TENURE_LABEL)
            if pos is not None:
                durs = [d for d in find_durations(text) if d.start >= pos - 2 and d.start - pos < 60]
                if durs:
                    ctx.tenure_months = int(round(durs[0].months))
                    ctx.sources["tenure_months"] = c.id
                else:
                    m = re.search(r"\b(\d{1,3})\b", text[pos: pos + 30])
                    if m and 1 < int(m.group(1)) <= 360:
                        ctx.tenure_months = int(m.group(1))
                        ctx.sources["tenure_months"] = c.id
        if ctx.emi is None:
            pos, _ = _after_label(c, EMI_LABEL)
            if pos is not None:
                amounts = [a for a in find_money(text) if a.start >= pos - 2 and a.start - pos < 40]
                if amounts:
                    ctx.emi = amounts[0].value
                    ctx.sources["emi"] = c.id
    return ctx
