"""Orchestration: one function per user action. The web API and the evaluation script both call these."""
from __future__ import annotations

from .config import get_settings
from .explain.explainer import explain, numbers_ok, template
from .explain.readability import flesch
from .calc.impact import all_numbers
from .extract.context import DOC_LABELS, extract_context
from .ingest.pii import mask_pii
from .ingest.segmenter import segment
from .llm.client import LLM
from .risk.pipeline import detect, recompute_impacts
from .schemas import AnalyzeRequest, AnalyzeResponse, Clause, LoanContext, RiskFlag, Summary


class InputError(ValueError):
    """A problem with the user's input, with a message that tells them how to fix it."""


def check_length(text: str) -> str:
    s = get_settings()
    text = (text or "").strip()
    if len(text) < s.min_chars:
        raise InputError(f"The text is too short to analyse ({len(text)} characters). Paste the full terms, at least {s.min_chars} characters.")
    if len(text) > s.max_chars:
        raise InputError(f"The text is too long ({len(text):,} characters). The limit is {s.max_chars:,}. Paste the fees and charges section first.")
    return text


def prepare(text: str) -> dict:
    """Mask personal data, split into clauses and pre-fill the numbers. Fast, and needs no model."""
    text = check_length(text)
    masked, pii = mask_pii(text)
    clauses = segment(masked)
    if not clauses:
        raise InputError("No clauses could be found in this text. Check that it is the document's text, not a scanned image.")
    ctx = extract_context(clauses, masked)
    return {
        "text": masked,
        "clause_count": len(clauses),
        "doc_type": ctx.doc_type,
        "doc_label": DOC_LABELS.get(ctx.doc_type, "Document"),
        "context": ctx,
        "pii_masked": pii,
    }


def choose_method(requested: str | None, llm: LLM | None) -> tuple[str, list[str]]:
    if requested in (None, "", "auto"):
        return ("hybrid" if llm else "rules"), []
    if requested in ("llm", "hybrid") and llm is None:
        return "rules", ["No language model is set up, so the rules-only check was used."]
    return requested, []  # type: ignore[return-value]


def summarise(flags: list[RiskFlag], clauses: list[Clause]) -> Summary:
    s = Summary(clauses=len(clauses), flagged_clauses=len({f.clause_id for f in flags}))
    for f in flags:
        setattr(s, f.severity, getattr(s, f.severity) + 1)
    return s


def analyze(req: AnalyzeRequest, llm: LLM | None) -> AnalyzeResponse:
    text = check_length(req.text)
    masked, pii = mask_pii(text)
    clauses = segment(masked)
    if not clauses:
        raise InputError("No clauses could be found in this text.")
    method, warnings = choose_method(req.method, llm)
    extracted = extract_context(clauses, masked)
    ctx = req.context or extracted
    if req.doc_type:
        ctx.doc_type = req.doc_type
    if not ctx.sources and extracted.sources and req.context is not None:
        ctx.sources = {k: v for k, v in extracted.sources.items() if getattr(ctx, k) == getattr(extracted, k)}

    flags, w = detect(clauses, ctx, method=method, llm=llm if method != "rules" else None, batch_size=get_settings().llm_batch_size)
    warnings += w
    warnings += explain(flags, ctx, level=req.level, language=req.language, llm=llm if method != "rules" else None)

    readability = flesch(" ".join(f.explanation for f in flags)) if req.language == "en" and flags else None
    return AnalyzeResponse(
        doc_type=ctx.doc_type,
        method=method,  # type: ignore[arg-type]
        model_used=method != "rules",
        clauses=clauses,
        flags=flags,
        context=ctx,
        summary=summarise(flags, clauses),
        pii_masked=pii,
        warnings=warnings,
        readability=readability,
    )


def recalculate(text: str, flags: list[RiskFlag], ctx: LoanContext, level: str) -> tuple[list[RiskFlag], list[str]]:
    """User changed their numbers: redo the rupee maths only. Explanations with old numbers fall back to templates."""
    masked, _ = mask_pii(check_length(text))
    clauses = segment(masked)
    flags = recompute_impacts(flags, clauses, ctx)
    updated = 0
    for f in flags:
        if f.explanation_source == "model" and not numbers_ok(f.explanation, all_numbers(f.impact, f.fields, ctx)):
            f.explanation, f.explanation_source = template(f, level), "template"
            updated += 1
    notes = [f"{updated} explanation(s) were reset to standard text because their numbers changed."] if updated else []
    return flags, notes


def re_explain(flags: list[RiskFlag], ctx: LoanContext, level: str, language: str, llm: LLM | None) -> tuple[list[RiskFlag], list[str], float | None]:
    warnings = explain(flags, ctx, level=level, language=language, llm=llm)
    readability = flesch(" ".join(f.explanation for f in flags)) if language == "en" and flags else None
    return flags, warnings, readability
