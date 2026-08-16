"""Schema for a gap record. Validation is the product's first quality gate."""

from __future__ import annotations

import re

import pathlib

from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

from .taxonomy import GAP_TYPES, LAYERS, SOURCE_CLASSES, STATUSES

RULE_KINDS = frozenset({
    "any_of", "all_of", "not", "file_exists", "file_absent",
    "content_matches", "content_absent",
})

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


class Fixtures(BaseModel):
    """Two-sided proof that a check actually discriminates.

    A detector is only trustworthy if it has been shown to FIRE on a known-bad
    sample and NOT fire on a known-good one. Shipping one without both is how a
    monitor ends up reporting health forever. The test suite runs every check in
    the register against both fixtures, so a fail-open check cannot be merged.
    """

    model_config = ConfigDict(extra="forbid")

    bad: dict[str, str] = Field(
        description="relative path -> file content; MUST yield PRESENT")
    good: dict[str, str] = Field(
        description="relative path -> file content; MUST NOT yield PRESENT")

    @field_validator("bad", "good")
    @classmethod
    def _nonempty_tree(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("fixture file tree must not be empty")
        for path in v:
            if path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts:
                raise ValueError(f"fixture path must be relative and contained: {path!r}")
        return v


class Check(BaseModel):
    """How to detect this gap in a concrete target repository.

    Rules are declarative data evaluated offline. `mitigated_when` is what makes
    an ABSENT verdict possible at all: without positive evidence of a fix, the
    honest answer is MANUAL, never "looks fine".
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    applies_when: dict | None = None
    present_when: dict | None = None
    mitigated_when: dict | None = None
    manual_question: str = ""
    rationale: str = Field(
        default="", description="why this signature indicates the gap")
    fixtures: Fixtures | None = None

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not re.fullmatch(r"CHK-\d{3}", v):
            raise ValueError(f"check id must look like CHK-001, got {v!r}")
        return v

    @field_validator("applies_when", "present_when", "mitigated_when")
    @classmethod
    def _rule_shape(cls, v: dict | None) -> dict | None:
        if v is not None:
            _validate_rule(v)
        return v

    @model_validator(mode="after")
    def _automated_checks_need_fixtures(self) -> "Check":
        automated = self.present_when is not None or self.mitigated_when is not None
        if automated and self.fixtures is None:
            raise ValueError(
                f"{self.id}: an automated check MUST ship two-sided fixtures "
                "(bad must fire, good must not). Unproven detectors fail open.")
        if not automated and not self.manual_question.strip():
            raise ValueError(
                f"{self.id}: a manual check MUST state the question to ask, "
                "otherwise it silently passes.")
        return self


def _validate_rule(rule: dict, depth: int = 0) -> None:
    """Reject malformed rules at load time rather than at scan time."""
    if depth > 8:
        raise ValueError("rule nesting too deep (max 8)")
    kind = rule.get("kind")
    if kind not in RULE_KINDS:
        raise ValueError(f"unknown rule kind {kind!r}; allowed: {sorted(RULE_KINDS)}")
    if kind in ("any_of", "all_of"):
        subs = rule.get("rules")
        if not isinstance(subs, list) or not subs:
            raise ValueError(f"{kind} requires a non-empty 'rules' list")
        for sub in subs:
            _validate_rule(sub, depth + 1)
        return
    if kind == "not":
        inner = rule.get("rule")
        if not isinstance(inner, dict):
            raise ValueError("not requires a 'rule' object")
        _validate_rule(inner, depth + 1)
        return
    globs = rule.get("globs")
    if not isinstance(globs, list) or not globs:
        raise ValueError(f"{kind} requires a non-empty 'globs' list")
    if kind in ("content_matches", "content_absent"):
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"{kind} requires a 'pattern' string")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc


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
    check: Check | None = None

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
