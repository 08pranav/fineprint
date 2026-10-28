"""Combine rule hits and model hits into verified, de-duplicated risk flags.

Methods:
  rules  - regex cues only (baseline; always available)
  llm    - language model only, quotes verified
  hybrid - both, as a union. Agreement = high confidence. Model-only = medium (its quote is verified).
           Rules-only = high when the cue evidence is strong, otherwise medium.
           Why a union: in a consumer-protection tool a missed trap costs more than an extra flag,
           and every flag already quotes the document, so the reader can judge it in seconds.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..calc.impact import compute
from ..extract.money import extract_fields
from ..kb.retriever import for_flag
from ..llm.client import LLM
from ..schemas import Clause, LoanContext, RiskFlag
from . import llm_classifier, rules
from .taxonomy import BY_ID, SEVERITY_ORDER
from .verify import verify_quote

STRONG_RULE_SCORE = 4


@dataclass
class Candidate:
    clause_id: str
    category: str
    quote: str
    reason: str
    cue_pos: int = 0
    rule_score: int = 0
    by_rules: bool = False
    by_llm: bool = False
    methods: list[str] = field(default_factory=list)


def _severity(category: str, impact_amount: float | None, ctx: LoanContext) -> str:
    sev = BY_ID[category].severity
    if category == "processing_fee" and impact_amount and ctx.principal and impact_amount >= 0.03 * ctx.principal:
        return "high"
    if category == "recurring_fee" and impact_amount and impact_amount >= 1000:
        return "medium"
    return sev


def detect(
    clauses: list[Clause],
    ctx: LoanContext,
    *,
    method: str,
    llm: LLM | None = None,
    batch_size: int = 25,
) -> tuple[list[RiskFlag], list[str]]:
    warnings: list[str] = []
    by_id = {c.id: c for c in clauses}
    cands: dict[tuple[str, str], Candidate] = {}

    if method in ("rules", "hybrid"):
        for hit in rules.classify(clauses):
            cands[(hit.clause_id, hit.category)] = Candidate(
                hit.clause_id, hit.category, hit.quote, f"Matched the wording \"{hit.cue}\"",
                cue_pos=hit.cue_pos, rule_score=hit.score, by_rules=True,
            )

    if method in ("llm", "hybrid") and llm is not None:
        hits, _reviewed, w = llm_classifier.classify(clauses, llm, batch_size=batch_size)
        warnings.extend(w)
        dropped = 0
        for h in hits:
            clause = by_id[h.clause_id]
            verified = verify_quote(h.quote, clause.text)
            if verified is None:
                dropped += 1
                continue
            key = (h.clause_id, h.category)
            pos = max(0, clause.text.lower().find(verified.lower()[:20]))
            if key in cands:
                cands[key].by_llm = True
                cands[key].reason = h.reason or cands[key].reason
            else:
                cands[key] = Candidate(h.clause_id, h.category, verified, h.reason or "Flagged by the language model", cue_pos=pos, by_llm=True)
        if dropped:
            warnings.append(f"{dropped} model suggestion(s) were removed because their quote was not found in the document.")

    flags: list[RiskFlag] = []
    for cand in cands.values():
        if cand.by_rules and cand.by_llm:
            confidence = "high"
        elif cand.by_llm:
            confidence = "medium"
        else:
            confidence = "high" if cand.rule_score >= STRONG_RULE_SCORE else "medium"
        clause = by_id[cand.clause_id]
        fields = extract_fields(clause.text)
        impact = compute(cand.category, fields, ctx, cand.cue_pos, clause.text)
        found_by = [m for m, on in (("rules", cand.by_rules), ("llm", cand.by_llm)) if on]
        flags.append(
            RiskFlag(
                id="",
                clause_id=cand.clause_id,
                category=cand.category,
                category_label=BY_ID[cand.category].label,
                severity=_severity(cand.category, impact.amount, ctx),  # type: ignore[arg-type]
                quote=cand.quote,
                reason=cand.reason,
                found_by=found_by,  # type: ignore[arg-type]
                confidence=confidence,  # type: ignore[arg-type]
                fields=fields,
                cue_pos=cand.cue_pos,
                impact=impact,
                kb=for_flag(cand.category, clause.text),
            )
        )

    order = {c.id: c.number for c in clauses}
    flags.sort(key=lambda f: (SEVERITY_ORDER[f.severity], order.get(f.clause_id, 0)))
    for i, f in enumerate(flags, start=1):
        f.id = f"F{i}"
    return flags, warnings


def recompute_impacts(flags: list[RiskFlag], clauses: list[Clause], ctx: LoanContext) -> list[RiskFlag]:
    """Re-run only the deterministic calculator after the user edits their numbers."""
    by_id = {c.id: c for c in clauses}
    for f in flags:
        clause = by_id.get(f.clause_id)
        if not clause:
            continue
        f.impact = compute(f.category, f.fields, ctx, f.cue_pos, clause.text)
        f.severity = _severity(f.category, f.impact.amount, ctx)  # type: ignore[assignment]
    return flags
