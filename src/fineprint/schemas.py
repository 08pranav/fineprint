"""Shared data contracts. Every module talks in these types, so each part can be built and tested alone."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["high", "medium", "low"]
Level = Literal["simple", "standard", "expert"]
Language = Literal["en", "hi", "mr", "hinglish"]
Method = Literal["rules", "llm", "hybrid"]


class Clause(BaseModel):
    """One clause of the document, with its exact position so quotes can be verified."""

    id: str  # "C1", "C2", ... shown to the user as clause numbers
    number: int
    label: str | None = None  # the document's own numbering, e.g. "8", "iv", "a"
    text: str
    start: int  # character offset in the masked document text
    end: int
    page: int | None = None
    heading: str | None = None


class Money(BaseModel):
    """A rupee amount found in text, normalised to a float."""

    raw: str
    value: float
    start: int
    end: int


class Percent(BaseModel):
    raw: str
    value: float  # 2.5 means 2.5 %
    period: Literal["month", "year", "unspecified"] = "unspecified"
    start: int
    end: int


class Duration(BaseModel):
    raw: str
    months: float
    start: int
    end: int


class ClauseFields(BaseModel):
    """Numbers pulled out of one clause by the deterministic extractor."""

    amounts: list[Money] = Field(default_factory=list)
    percents: list[Percent] = Field(default_factory=list)
    durations: list[Duration] = Field(default_factory=list)
    plus_gst: bool = False


class LoanContext(BaseModel):
    """Document-level numbers that the rupee calculator needs. Pre-filled, then editable by the user."""

    doc_type: str = "loan"
    principal: float | None = None  # loan amount or credit limit, in rupees
    annual_rate: float | None = None  # % per year
    tenure_months: int | None = None
    emi: float | None = None  # stated EMI if the document gives one
    sources: dict[str, str] = Field(default_factory=dict)  # field -> clause id it came from


class RupeeImpact(BaseModel):
    headline: str  # "₹1,180 for every missed EMI"
    amount: float | None = None
    basis: str  # how it was computed, in words
    assumptions: list[str] = Field(default_factory=list)


class KBNote(BaseModel):
    id: str
    title: str
    body: str
    source_name: str
    source_url: str


class RiskFlag(BaseModel):
    id: str  # "F1" ...
    clause_id: str
    category: str
    category_label: str
    severity: Severity
    quote: str  # exact text from the clause; verified against the source
    reason: str  # short machine reason (rule cue or model reason)
    found_by: list[Method]
    confidence: Literal["high", "medium", "low"]
    fields: ClauseFields = Field(default_factory=ClauseFields)
    cue_pos: int = 0  # where in the clause the risk wording sits; picks the nearest number
    impact: RupeeImpact | None = None
    explanation: str = ""
    explanation_source: Literal["model", "template"] = "template"
    kb: KBNote | None = None


class AnalyzeRequest(BaseModel):
    text: str
    doc_type: str | None = None
    level: Level = "standard"
    language: Language = "en"
    method: Method | None = None  # None = best available
    context: LoanContext | None = None  # user-edited numbers


class Summary(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    clauses: int = 0
    flagged_clauses: int = 0


class AnalyzeResponse(BaseModel):
    doc_type: str
    method: Method
    model_used: bool
    clauses: list[Clause]
    flags: list[RiskFlag]
    context: LoanContext
    summary: Summary
    pii_masked: dict[str, int]
    warnings: list[str] = Field(default_factory=list)
    readability: float | None = None  # Flesch reading ease of the explanations (English only)


class AskRequest(BaseModel):
    question: str
    text: str
    language: Language | None = None  # None = reply in the language the question was asked in


class AskResponse(BaseModel):
    answer: str
    detected_language: Language
    cited_clauses: list[str]
    abstained: bool = False
    advice_guardrail: bool = False
    model_used: bool = False
    warnings: list[str] = Field(default_factory=list)
