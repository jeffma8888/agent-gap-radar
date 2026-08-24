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

    @field_validator("locator")
    @classmethod
    def _nonempty_locator(cls, v: str) -> str:
        """Reject a blank locator, the other half of a checkable citation.

        The quality bar names a resolvable locator AND a verbatim quote in one
        sentence; only the quote half was enforced, so a citation nobody could
        resolve still passed `radar validate`. Blank is load-bearing past
        readability too: `scoring._source_key` keys corroboration on this
        string, so two blank locators normalise to ONE source and silently
        withhold a corroboration point from the DERIVED confidence the whole
        ranking rests on.

        Non-blank and NOTHING stronger, deliberately -- see PRODUCT.md row 57.
        The three doors a locator passes through disagree on its SHAPE (the
        ingest gate demands `https?://`, the out-of-band resolver skips a
        non-URL and still exits 0, and this field's own docstring promises a
        DOI or a stable local path), so a shape rule here would make two of
        them wrong: that is a new product promise, not a hardening bite.
        """
        if not v.strip():
            raise ValueError("locator must not be empty: a citation without a locator "
                             "cannot be resolved or checked by a reader")
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

    @property
    def is_automated(self) -> bool:
        """True when a static signature exists, so `scan` can decide this check alone.

        One predicate, two consumers that must never disagree: the validator below
        demands two-sided fixtures of an automated check, and `prd` tells a build
        loop whether the register holds a reproduction sample to transcribe. A
        second copy of this expression could let the emitted document promise a
        sample the schema never required, or deny one it did.
        """
        return self.present_when is not None or self.mitigated_when is not None

    @model_validator(mode="after")
    def _automated_checks_need_fixtures(self) -> "Check":
        automated = self.is_automated
        if automated and self.fixtures is None:
            raise ValueError(
                f"{self.id}: an automated check MUST ship two-sided fixtures "
                "(bad must fire, good must not). Unproven detectors fail open.")
        if not automated and not self.manual_question.strip():
            raise ValueError(
                f"{self.id}: a manual check MUST state the question to ask, "
                "otherwise it silently passes.")
        return self


#: The three things a register can hold towards detecting one gap, strongest first.
#: Closed on purpose: every surface that reports detectability answers with one of
#: these, so a consumer switching on the value cannot be handed a fourth word.
DETECTABILITY_KINDS: tuple[str, ...] = ("automated", "manual", "none")


def detectability(check: Check | None) -> str:
    """Which of `DETECTABILITY_KINDS` the register holds for one record.

    Keyed on `Check.is_automated` rather than on the presence of `fixtures`: a
    manual check MAY carry fixtures, and it is the absence of a RULE that makes a
    gap undetectable by `scan`.

    Lives beside that predicate because it now has TWO consumers that must never
    disagree -- `prd` tells a build loop what it may transcribe, `render.gap_brief`
    tells a reader whether `radar scan` can ever verdict this record -- and a
    two-line mapping is exactly the kind of derivation that gets re-typed into a
    second surface and then drifts. PRODUCT.md row 53 already names
    `Check.is_automated` as the single copy of the automated/manual predicate; this
    is the same commitment one level up, covering the `none` limb that no property
    on `Check` can express, because a record with no check has nothing to read.
    """
    if check is None:
        return "none"
    return "automated" if check.is_automated else "manual"


def _validate_glob(kind: str, glob: object) -> None:
    """Refuse a `globs` element the matcher cannot even parse.

    THE LINE THIS RULE DRAWS, and it is deliberately narrow: the schema keeps
    `checks._match_globs`'s contract SATISFIABLE, and does NOT police glob
    QUALITY. A glob that is a string is the matcher's problem -- iteration 26
    decided that a blank, absolute or otherwise hostile pattern MATCHES NOTHING
    at scan time rather than aborting, because a register is data consumers
    write and share, and `test_iter26_behavior.py` holds that promise at CLI
    level. A glob that is NOT a string is a different class: it is unparseable,
    so there is no verdict to answer with.

    `_glob_regex` calls `pattern.split("/")` before it builds any regex, so at
    HEAD `globs=[123]` was CERTIFIED by `radar validate` (rc=0, 27 bytes of
    stdout, empty stderr) and then made `radar scan` exit 1 with an
    `AttributeError` traceback and ZERO document bytes -- the one outcome
    `_match_globs`'s own docstring names as forbidden by the CLI contract. The
    regex fallback cannot catch it: the crash precedes the `re.compile`, and
    `AttributeError` is not a `ValueError`, so no upstream handler sees it. That
    makes the schema the only door, which is why this limb belongs here while
    the shape limbs (blank, absolute, `..`) do not -- see PRODUCT.md row 61,
    which names the five committed tests that hold those shapes schema-valid.

    Raises `ValueError` so pydantic wraps it and the CLI renders `Error: ` on
    stderr with exit 2 and no stdout, the same path a bad `pattern` takes.
    """
    if not isinstance(glob, str):
        raise ValueError(
            f"{kind} requires each 'globs' element to be a string, got {glob!r}")


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
    # ONE loop for all four leaf kinds, so they cannot disagree about what a
    # glob element may be. Reached only after the `any_of`/`all_of`/`not` limbs
    # have returned, and those recurse back through here, so a bad element
    # nested inside a combinator is refused with the same message.
    for glob in globs:
        _validate_glob(kind, glob)
    if kind in ("content_matches", "content_absent"):
        pattern = rule.get("pattern")
        # `.strip()` rather than truthiness: `"   "` and `"\t"` are truthy,
        # compile fine, and are searched with `re.MULTILINE` over whole file
        # text, so they hit on incidental indentation -- 75 of this repo's own
        # 76 tracked `.py` files contain three consecutive spaces. That is a
        # signature of nothing, and the truthiness test certified it. Message
        # unchanged, so `""` keeps the refusal it already had.
        if not isinstance(pattern, str) or not pattern.strip():
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
