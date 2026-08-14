"""Schema for a gap record. Validation is the product's first quality gate."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .taxonomy import GAP_TYPES, LAYERS, SOURCE_CLASSES, STATUSES

GAP_ID_RE = re.compile(r"^GAP-\d{3}$")


class Evidence(BaseModel):
    """One citation supporting a gap. Every field here is checkable by a reader."""

    model_config = ConfigDict(extra="forbid")

    source_class: str
    title: str
    locator: str = Field(description="URL, DOI, or a stable local artifact path.")
    date: str = Field(description="ISO date (YYYY-MM-DD) the source was published.")
    quote: str = Field(description="Verbatim excerpt. Never a paraphrase.")
    note: str = ""

    @field_validator("source_class")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in SOURCE_CLASSES:
            raise ValueError(f"unknown source_class {v!r}; allowed: {SOURCE_CLASSES}")
        return v

    @field_validator("date")
    @classmethod
    def _iso_date(cls, v: str) -> str:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(f"date must be YYYY-MM-DD, got {v!r}")
        return v

    @field_validator("quote")
    @classmethod
    def _nonempty_quote(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("quote must not be empty: a citation without an excerpt "
                             "cannot be checked by a reader")
        return v


class Gap(BaseModel):
    """A single, ranked, evidence-backed gap in agent infrastructure."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    layer: str
    gap_type: str
    status: str = "open"

    problem: str = Field(description="One sentence, in the voice of the person hurt by it.")
    symptom: str = Field(description="What an operator actually observes.")
    why_now: str = Field(description="Why this is a gap in 2026 and not a solved problem.")
    existing: list[str] = Field(default_factory=list,
                                description="Partial solutions and why each falls short.")

    severity: int = Field(ge=1, le=5, description="Damage when it bites.")
    frequency: int = Field(ge=1, le=5, description="How often it bites a real team.")
    tractability: int = Field(ge=1, le=5, description="Can a small team move it?")

    evidence: list[Evidence] = Field(min_length=1)
    build_hypothesis: str = Field(
        default="",
        description="If we built one thing against this gap, what would it be?")
    tags: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not GAP_ID_RE.match(v):
            raise ValueError(f"id must look like GAP-001, got {v!r}")
        return v

    @field_validator("layer")
    @classmethod
    def _known_layer(cls, v: str) -> str:
        if v not in LAYERS:
            raise ValueError(f"unknown layer {v!r}; allowed: {tuple(LAYERS)}")
        return v

    @field_validator("gap_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in GAP_TYPES:
            raise ValueError(f"unknown gap_type {v!r}; allowed: {tuple(GAP_TYPES)}")
        return v

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in STATUSES:
            raise ValueError(f"unknown status {v!r}; allowed: {STATUSES}")
        return v
