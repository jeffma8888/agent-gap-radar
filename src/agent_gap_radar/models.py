"""Schema for a gap record. Validation is the product's first quality gate."""

from __future__ import annotations

import re

import pathlib
from datetime import date

from pydantic import (BaseModel, ConfigDict, Field, field_validator,
                      model_validator)

from .taxonomy import GAP_TYPES, LAYERS, SOURCE_CLASSES, STATUSES

RULE_KINDS = frozenset({
    "any_of", "all_of", "not", "file_exists", "file_absent",
    "content_matches", "content_absent",
})

GAP_ID_RE = re.compile(r"^GAP-\d{3}$")

# The ONE definition of a resolvable locator in this product. Lifted verbatim from
# `tools/promote.py`'s ingest gate, which iteration 121 named AUTHORITATIVE for the
# record-level promise, and which now calls this instead of holding its own copy --
# two doors with two spellings of one rule is how the register grew two standards in
# the first place. `re.match` + a trailing `$` (not `fullmatch`) is deliberate: it is
# byte-for-byte the predicate the ingest gate has always applied, so sharing it moves
# nothing that promote already accepted or rejected.
RESOLVABLE_LOCATOR_RE = re.compile(r"https?://\S+$")


def is_resolvable_locator(locator: str) -> bool:
    """True when `locator` has the SHAPE a reader can dereference.

    SHAPE only, never a dereference: the offline bar forbids network access, so this
    cannot and does not tell a live URL from a 404. It answers the narrower question
    the register actually needs -- "could a reader even try?" -- which is what makes a
    DERIVED confidence auditable.
    """
    return bool(RESOLVABLE_LOCATOR_RE.match(locator))


def first_unencodable(text: str) -> str | None:
    """The first codepoint of `text` that UTF-8 cannot encode, or `None`.

    THE ONE definition of "text this register may not hold", and it is an ENCODE
    rather than a codepoint-range test on purpose: the property being defended is
    exactly "these bytes can leave the process", so the predicate IS the operation
    that fails. A Python `str` may hold a UTF-16 surrogate -- `json.loads` builds one
    from the legal JSON escape for a lone surrogate, so the file on disk is valid
    UTF-8, valid JSON and schema-clean -- but `sys.stdout` cannot write one. Measured
    at HEAD before this landed: one such codepoint in `title` made `radar list`,
    `report`, `show` and `scan` exit 1 with ZERO document bytes and a bare
    `UnicodeEncodeError` traceback, while `radar validate` certified the same
    register at exit 0. The door that certifies the register could not see the
    defect it was certifying.

    SURROGATE-SCOPED BY CONSTRUCTION, never ascii-scoped: UTF-8 encodes every other
    codepoint, so an em dash, `x` U+00D7 and an astral emoji all pass here. That is
    load-bearing, not incidental -- 6 of the 120 committed records hold non-ASCII
    text, and a register that refused a real quotation's own punctuation would be a
    worse register. Control characters (NUL, an RTL override) encode fine and so stay
    accepted; whether they SHOULD is a separate product decision, deliberately not
    taken here.

    Returns the offending CHARACTER rather than a bool so the refusal can name it.
    `repr` of a surrogate is its backslash-u escape, which is what keeps the error
    path from raising the very error it reports: a message that interpolates this
    value stays pure ASCII even on the stderr stream that just rejected the bytes.
    """
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        return text[exc.start]
    return None


def _unencodable_site(value: object, where: str = "") -> tuple[str, str] | None:
    """`(path within the field, codepoint)` for the first unencodable text in `value`.

    A record's strings are not all AT a field: `tags` and `existing` are `list[str]`,
    `Check.fixtures.bad` is a `dict[str, str]`, and a rule's `pattern` and `globs` sit
    inside a plain nested `dict`. One walk over the container kinds a field can hold
    therefore covers EVERY string a record carries, which is what lets the rule be
    spelled once instead of once per field.

    Deliberately does NOT descend into a nested `BaseModel`. pydantic validates a
    sub-model BEFORE the parent field it fills, so text inside a citation is already
    refused at its own field and reported under the precise `evidence.0.quote`
    locator; descending would report the same character a second time under a blunter
    path. Dict KEYS are walked as well as values, because a key is published too --
    `Fixtures.bad`'s keys are the filenames `prd --with-fixtures` writes.
    """
    if isinstance(value, str):
        found = first_unencodable(value)
        return None if found is None else (where, found)
    if isinstance(value, dict):
        for key, item in value.items():
            for part, suffix in ((key, " (key)"), (item, "")):
                site = _unencodable_site(part, f"{where}[{key!r}]{suffix}")
                if site is not None:
                    return site
        return None
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            site = _unencodable_site(item, f"{where}[{index}]")
            if site is not None:
                return site
        return None
    return None


class RecordModel(BaseModel):
    """The base of every model a gap record is built from, holding the record-WIDE rules.

    Two of them. `extra="forbid"` was already the rule, spelled once per class in four
    places; the unencodable-text refusal below was spelled nowhere. Both belong here
    for the same reason iteration 121 moved the locator predicate to one site: two
    doors with two spellings of one rule is how this register grew two standards in
    the first place, and a fifth model added later cannot forget a rule it inherits.
    """

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _refuse_unencodable_text(cls, v: object) -> object:
        """Refuse any field holding text that could never be written to stdout.

        AT THE SCHEMA, so every door inherits it from one line: `radar validate`,
        `registry.load_all` (which is what the other seven verbs read through),
        `tools/promote.py`'s ingest gate and the evidence gates all arrive through
        `Gap.model_validate`. The quality bar's error sentence is atomic -- "Errors to
        stderr prefixed 'Error: ' with exit 2; stdout carries only the document" -- and
        text that only fails at WRITE time breaks both halves on the same bytes: exit 1
        (a code `docs/CONSUMER_CONTRACT.md` reserves for a broken pipe) and a traceback
        nobody prefixed. Refusing at the door converts that into this product's single
        standard failure. `VISION.md`'s protected rule is that a record is never
        silently dropped, and a renderer that dies mid-document drops all 120.

        No message shape of its own, on purpose: `registry._schema_problem` already
        names the file and the dotted field path, so this contributes the clause and
        nothing else -- the same reason that formatter quotes pydantic verbatim.

        `mode="after"` rather than `"before"`: the value has been coerced to its
        declared type, so the walk sees a real `str`/`list`/`dict` rather than whatever
        the JSON handed over, and a sub-model has already refused its own text under
        its own locator.
        """
        site = _unencodable_site(v)
        if site is None:
            return v
        where, codepoint = site
        at = f" at {where}" if where else ""
        raise ValueError(
            f"must not hold text that UTF-8 cannot encode{at}: {codepoint!r} is a "
            "UTF-16 surrogate, so a renderer writing this record to stdout would die "
            "with no document instead of publishing it")


class Evidence(RecordModel):
    """One citation supporting a gap. Every field here is checkable by a reader."""

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
        """Refuse anything that is not a REAL zero-padded ISO calendar date.

        The shape check alone is not enough, because the stored value is arithmetic
        input: `2026-02-30` is a plausible research-pass typo that matches the pattern,
        and any consumer that parses it -- `scoring._evidence_age_days` is the first --
        raises on it. This product puts every other quality rule at the ingest door, so
        the parse belongs here too: `radar validate` then names the offending record for
        the curator who can fix it, instead of `radar report` dying with a raw traceback
        on the primary human surface. It is also what makes the LEXICAL max in
        `scoring._newest_citation_date` correct by validation instead of by convention.
        """
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError(f"date must be YYYY-MM-DD, got {v!r}")
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"date must be a real calendar date, got {v!r}") from exc
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

        Non-blank and NOTHING stronger AT THE FIELD LEVEL, deliberately. The
        SHAPE rule the quality bar names lives one level up, on the RECORD:
        `Gap._one_citation_is_resolvable`. Iteration 121 settled row 57 by
        naming `tools/promote.py`'s `https?://\\S+$` authoritative for the
        record-level promise and leaving this field's rule alone, which is
        exactly what keeps the other two doors TRUE and is not a retraction of
        either: this field's advertised "URL, DOI, or a stable local artifact
        path" still holds, and `tools/check_locators.py` still SKIPs a non-URL
        locator and still exits 0. A DOI or a stable local path remains a legal
        locator; it simply may not be a record's ONLY citation.
        """
        if not v.strip():
            raise ValueError("locator must not be empty: a citation without a locator "
                             "cannot be resolved or checked by a reader")
        return v


class Fixtures(RecordModel):
    """Two-sided proof that a check actually discriminates.

    A detector is only trustworthy if it has been shown to FIRE on a known-bad
    sample and NOT fire on a known-good one. Shipping one without both is how a
    monitor ends up reporting health forever. The test suite runs every check in
    the register against both fixtures, so a fail-open check cannot be merged.
    """

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


class Check(RecordModel):
    """How to detect this gap in a concrete target repository.

    Rules are declarative data evaluated offline. `mitigated_when` is what makes
    an ABSENT verdict possible at all: without positive evidence of a fix, the
    honest answer is MANUAL, never "looks fine".
    """

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

    @field_validator("rationale")
    @classmethod
    def _rationale_is_one_line(cls, v: str) -> str:
        r"""Refuse a rationale that cannot be published as ONE markdown bullet.

        A REPRODUCTION, not a precaution. `render._detection_section` renders this
        field verbatim as the last bullet of `## Detection`, and iteration 29 pinned
        that block as a single CONTIGUOUS run sitting immediately before
        `## Evidence`. A rationale carrying a line break splits the bullet, so the
        block a reader sees -- and that pin -- break on whoever's iteration next
        promotes such a record; measured before this landed, a rationale of
        `line one` + newline + `line two` validated at rc 0 through the real loader.
        Untrimmed is the same defect one step smaller: a trailing newline is a line
        break, and leading space silently reindents the bullet.

        `splitlines()` rather than `"\n" in v`, because the property being defended
        is "renders as one line" and Python's line-break set is wider than `\n`
        (`\r`, `\x0b`, `\x0c`, `\u2028`, `\u2029`): the narrow test would admit a
        value that still breaks the bullet. The two predicates are complementary and
        neither is redundant -- `"a\nb"` is multi-line but trimmed, `"a\n"` is
        single-line by `splitlines` and untrimmed -- so both legs are needed to cover
        the field.

        EMPTY stays legal on purpose. Requiring a rationale is a different product
        decision (this field is optional at the door and 1 of the 120 live records
        carries no check at all); the renderer DISPLAYS that absence as
        `none recorded` rather than hiding it, which is what the register's
        below-floor-records-are-shown rule asks for.

        The message is one line, because `registry.load_all` folds the first
        validation message into a single `Error: ` line on stderr.
        """
        if len(v.splitlines()) > 1:
            raise ValueError(
                "rationale must be a single line: it is published verbatim as one "
                f"bullet of `## Detection`, got {v!r}")
        if v != v.strip():
            raise ValueError(
                "rationale must carry no leading or trailing whitespace: it is "
                f"published verbatim as one bullet of `## Detection`, got {v!r}")
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


class Gap(RecordModel):
    """A single, ranked, evidence-backed gap in agent infrastructure."""

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

    @model_validator(mode="after")
    def _one_citation_is_resolvable(self) -> "Gap":
        """At least ONE citation must carry a locator a reader can dereference.

        The quality bar makes "at least one citation with a resolvable locator and a
        verbatim quote" a RECORD-level promise, and until iteration 121 only one of the
        two doors records arrive through kept it: `tools/promote.py` held a research
        pass to `https?://\\S+$`, while a hand-committed record in `gaps/` was held only
        to "not blank". So `radar validate` -- the first verb a CI gate runs -- could
        certify a register whose evidence nobody can resolve, and a confidence DERIVED
        from an evidence ladder is only worth as much as the ladder being checkable.

        Deliberately WEAKER than the ingest gate, which demands EVERY citation be a
        URL: promote governs what a research pass may ADD, the schema governs what the
        register may HOLD -- including records that predate the gate. One degraded
        locator among several therefore does not reject the record.

        Measured before installing (120 records, 402 citations, offline): 402 of 402
        already match, so this changes zero register records and zero rendered bytes.
        It is a brake on future data, not a repair of present data.
        """
        if not any(is_resolvable_locator(e.locator) for e in self.evidence):
            raise ValueError(
                f"{self.id}: no citation has a resolvable locator; at least one "
                "must start http:// or https:// so a reader can check the claim"
            )
        return self
