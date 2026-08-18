"""Iteration 16 brake: a `##` heading that names a `radar <verb>` must declare a status,
and that status must agree with `build_parser()` and with the `PRODUCT.md` roadmap.

WHY THIS EXISTS
`docs/CONSUMER_CONTRACT.md` is the document this product points machine consumers at.
Until iteration 16 it carried a section headed ``## `radar ingest` - the reverse direction
(TO BUILD)`` describing a ninth verb that existed nowhere else: not among
`build_parser()`'s subcommands, not on the `PRODUCT.md` roadmap, not in `src/`, `tests/`
or `tools/`. A consumer could plan against a verb that was never going to arrive.
Iteration 10 made the contract's stable-surface TABLE derivable from `build_parser()` and
left the HEADINGS unchecked; this closes the same class one level up. The verb was decided
NOT PLANNED rather than built, and this module is what stops the promise coming back.

WHY A CLOSED STATUS VOCABULARY
The drift was possible because a heading could say anything. `{SHIPPED, TO BUILD, NOT
PLANNED}` is closed, so the rule is decidable in both directions: a status is either
mapped to a machine-checkable claim or it is not a status. A heading with NO recognised
status fails, and so does a heading carrying TWO of them -- silently taking the first
would let an edit that half-changes a status read as a clean pass.

WHY EACH STATUS MEANS SOMETHING DIFFERENT
`SHIPPED` claims the verb is in the CLI, so it is checked against `build_parser()`'s
subcommand choices -- the same source of truth iteration 10 used, never a hand-copied
list. `NOT PLANNED` claims the opposite and is checked the opposite way, because a section
telling a consumer not to expect a verb that in fact ships is drift in the other
direction. `TO BUILD` is the only status that is allowed to name a verb the CLI lacks, and
it must be paid for by a roadmap row: a promise with an owner is a plan, a promise without
one is what this iteration deleted.

WHY THE READERS FAIL CLOSED
`parser_verbs()` raises when it finds no subparsers action and `roadmap_verbs()` raises
when it finds no table rows, because an empty expectation set would make every `NOT
PLANNED` heading pass for the wrong reason -- the green that means nothing. Same reason
`verb_headings()` raises on a document with no level-2 headings at all.

WHAT THIS DOES NOT COVER, STATED RATHER THAN IMPLIED
The collector is LEXICAL over level-2 (`## `) ATX headings, and it finds a verb only where
the heading spells it inside backticks as `radar <verb>`. A section that DESCRIBES a verb
without naming it that way escapes the rule completely, and so does a promise made in body
prose, in a table cell, or in a deeper (`###`) heading. It also cannot see the MIRROR
promise in the consumer's own tree (`agent-foundry/docs/INTEGRATION_AGENT_GAP_RADAR.md`),
which is a different repository and outside every test this suite can run. So this is a
brake on the shape the drift actually took, not a general prose-drift detector.
`test_no_deeper_heading_names_a_verb_today` measures the one piece of that gap which is
cheap to measure, so the deeper-heading hole is currently vacuous in fact rather than
merely tolerated.

Offline and read-only: every test reads two committed files plus `build_parser()`, and the
two-sided proofs build their documents in memory. Nothing here reads `gaps/`, so a
research pass writing records cannot redden it.
"""

from __future__ import annotations

import argparse
import pathlib
import re

import pytest

from agent_gap_radar.cli import build_parser

#: The tracked document whose headings this brake governs. Resolved from THIS file rather
#: than from the process cwd, so `pytest -n auto` reads the repo's own document no matter
#: which directory a worker starts in.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT_PATH = _REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
ROADMAP_PATH = _REPO_ROOT / "PRODUCT.md"

#: The closed status vocabulary. Order is longest-distinct-first only for readability;
#: none of these is a prefix of another, so alternation order cannot change a match.
STATUS_TOKENS: tuple[str, ...] = ("SHIPPED", "TO BUILD", "NOT PLANNED")

#: A status token must be parenthesised, so prose merely discussing the words "to build"
#: cannot satisfy or break the rule.
_STATUS_RE = re.compile(r"\((" + "|".join(re.escape(t) for t in STATUS_TOKENS) + r")\)")

#: Inline code spans, the only place a verb counts as NAMED.
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")

#: `radar <verb>` inside a code span. Flags and arguments after the verb are ignored, so
#: ``radar list --layer L`` names the verb `list`.
_RADAR_VERB_RE = re.compile(r"^radar\s+([A-Za-z][\w-]*)")

#: A GFM alignment row: pipes, dashes, colons and whitespace only.
_SEPARATOR_ROW_RE = re.compile(r"^\|[\s:|-]+\|$")


class VerbHeadingError(Exception):
    """A document or roadmap could not be READ at all.

    Deliberately distinct from a violation. A violation is a status and a codebase that
    were both understood and disagree; this is an input whose shape defeats the parse, and
    raising keeps it from being indistinguishable from an input with nothing wrong.
    """


class VerbHeading:
    """One (level-2 heading, verb) pair, with every status token the heading carries."""

    __slots__ = ("line_no", "text", "verb", "statuses")

    def __init__(self, line_no: int, text: str, verb: str, statuses: tuple[str, ...]):
        self.line_no = line_no
        self.text = text
        self.verb = verb
        self.statuses = statuses

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"VerbHeading(line_no={self.line_no}, verb={self.verb!r}, statuses={self.statuses})"


def contract_text() -> str:
    """The committed consumer contract, as published bytes."""
    return CONTRACT_PATH.read_text(encoding="utf-8")


def roadmap_text() -> str:
    """The committed roadmap, as published bytes."""
    return ROADMAP_PATH.read_text(encoding="utf-8")


def _heading_lines(text: str, level: int = 2) -> list[tuple[int, str]]:
    """Every ATX heading line at exactly `level`, one-based line numbers."""
    prefix = "#" * level + " "
    deeper = "#" * (level + 1)
    return [
        (n, line)
        for n, line in enumerate(text.splitlines(), start=1)
        if line.startswith(prefix) and not line.startswith(deeper)
    ]


def verb_headings(text: str, level: int = 2) -> tuple[VerbHeading, ...]:
    """Collect every heading at `level` that names a `radar <verb>` inside backticks.

    A heading naming two verbs yields two records: the status rules apply per verb, and
    collapsing them would let one satisfied claim cover an unsatisfied one.
    """
    headings = _heading_lines(text, level)
    if level == 2 and not headings:
        raise VerbHeadingError(
            "no level-2 headings found: the document's shape defeats the collector, "
            "which is not the same as a document with nothing to flag"
        )
    found: list[VerbHeading] = []
    for line_no, line in headings:
        statuses = tuple(m.group(1) for m in _STATUS_RE.finditer(line))
        for span in _CODE_SPAN_RE.findall(line):
            match = _RADAR_VERB_RE.match(span.strip())
            if match is not None:
                found.append(VerbHeading(line_no, line, match.group(1), statuses))
    return tuple(found)


def parser_verbs() -> frozenset[str]:
    """The subcommand names `build_parser()` actually exposes. FAILS CLOSED.

    argparse publishes no API for enumerating subcommands, so `_actions` and
    `_SubParsersAction` are the only way to ask; the access is read-only.
    """
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return frozenset(action.choices)
    raise VerbHeadingError(
        "build_parser() exposes no subparsers action: an empty verb set would make "
        "every NOT PLANNED heading pass for the wrong reason"
    )


def roadmap_verbs(text: str) -> frozenset[str]:
    """Verbs named as `radar <verb>` by a row of the roadmap table. FAILS CLOSED.

    Restricted to table rows on purpose: the prose around the table argues about verbs,
    and a plan is a ROW -- something with a number a later iteration can cite.
    """
    rows = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith("|") and not _SEPARATOR_ROW_RE.match(line.strip())
    ]
    if not rows:
        raise VerbHeadingError("no roadmap table rows found: nothing could be planned")
    verbs: set[str] = set()
    for row in rows:
        for span in _CODE_SPAN_RE.findall(row):
            match = _RADAR_VERB_RE.match(span.strip())
            if match is not None:
                verbs.add(match.group(1))
    return frozenset(verbs)


def status_violations(
    headings: tuple[VerbHeading, ...],
    *,
    parser: frozenset[str],
    roadmap: frozenset[str],
) -> tuple[str, ...]:
    """Every disagreement between a heading's status and the code, as readable lines."""
    out: list[str] = []
    for h in headings:
        if len(h.statuses) != 1:
            out.append(
                f"line {h.line_no}: heading names `radar {h.verb}` and carries "
                f"{len(h.statuses)} status tokens {h.statuses}; expected exactly one of "
                f"{STATUS_TOKENS}"
            )
            continue
        status = h.statuses[0]
        if status == "SHIPPED" and h.verb not in parser:
            out.append(
                f"line {h.line_no}: `radar {h.verb}` is marked SHIPPED but is not a "
                f"subcommand of build_parser() ({sorted(parser)})"
            )
        if status == "NOT PLANNED" and h.verb in parser:
            out.append(
                f"line {h.line_no}: `radar {h.verb}` is marked NOT PLANNED but the CLI "
                "ships it, so the document tells a consumer not to expect what exists"
            )
        if status == "TO BUILD":
            if h.verb in parser:
                out.append(
                    f"line {h.line_no}: `radar {h.verb}` is marked TO BUILD but the CLI "
                    "already ships it"
                )
            if h.verb not in roadmap:
                out.append(
                    f"line {h.line_no}: `radar {h.verb}` is marked TO BUILD but no "
                    "PRODUCT.md roadmap row names it, so the promise has no owner"
                )
    return tuple(out)


# --------------------------------------------------------------------------------------
# The committed document
# --------------------------------------------------------------------------------------


def test_no_heading_is_still_to_build() -> None:
    """Behavior 1: the contract promises no verb it is not building."""
    to_build = [h for h in verb_headings(contract_text()) if "TO BUILD" in h.statuses]
    assert to_build == [], f"a (TO BUILD) heading survived: {to_build}"


def test_committed_contract_has_no_status_violations() -> None:
    """Behaviors 4-7 over the real file: every verb heading agrees with the code."""
    violations = status_violations(
        verb_headings(contract_text()),
        parser=parser_verbs(),
        roadmap=roadmap_verbs(roadmap_text()),
    )
    assert violations == (), "\n".join(violations)


def test_collector_finds_exactly_the_two_documented_verbs() -> None:
    """Behavior 3, as a deliberate CENSUS.

    The two verb names are literal here on purpose: adding a third verb heading must be a
    conscious edit to this test, which is the whole point of a brake. The rest of the
    assertion is derived -- one verb ships and one does not, so both sides of the status
    rule are exercised by the committed file rather than only by synthetic documents.
    """
    headings = verb_headings(contract_text())
    assert len(headings) == 2, [h.verb for h in headings]
    assert {h.verb for h in headings} == {"scan", "ingest"}
    ships = parser_verbs()
    assert len([h for h in headings if h.verb in ships]) == 1
    assert len([h for h in headings if h.verb not in ships]) == 1
    assert len({h.statuses for h in headings}) == 2, "both statuses should be represented"


def test_ingest_section_keeps_its_argument_and_names_the_shipped_mechanism() -> None:
    """Behavior 2: the decision kept the reasoning instead of deleting it."""
    text = contract_text()
    ingest = [h for h in verb_headings(text) if h.verb == "ingest"]
    assert len(ingest) == 1
    assert ingest[0].statuses == ("NOT PLANNED",)

    lines = text.splitlines()
    start = ingest[0].line_no  # one-based heading line; body starts after it
    following = [n for n, line in _heading_lines(text) if n > start]
    end = following[0] - 1 if following else len(lines)
    body = re.sub(r"\s+", " ", "\n".join(lines[start:end]))

    assert (
        "A record appended without a citation would make every score in the register "
        "unbelievable" in body
    ), "the ladder argument did not survive the demotion"
    assert "tools/promote.py" in body, "the shipped mechanism is not named in the section"


def test_no_deeper_heading_names_a_verb_today() -> None:
    """The stated deeper-heading hole is vacuous in fact, measured rather than assumed."""
    text = contract_text()
    for level in (3, 4, 5, 6):
        assert verb_headings(text, level=level) == (), f"level-{level} heading names a verb"


# --------------------------------------------------------------------------------------
# Two-sided proofs: mutations derived from the shipped document
# --------------------------------------------------------------------------------------


def _mutated(text: str, heading: str, replacement: str) -> str:
    """Swap one heading line, asserting the mutation actually changed the text.

    A known-bad that silently no-ops reads exactly like a check that passed.
    """
    assert text.count(heading) == 1, f"heading not uniquely locatable: {heading!r}"
    out = text.replace(heading, replacement)
    assert out != text, "mutation changed nothing"
    return out


def _real_violations(text: str) -> tuple[str, ...]:
    return status_violations(
        verb_headings(text), parser=parser_verbs(), roadmap=roadmap_verbs(roadmap_text())
    )


def test_every_shipped_heading_fails_if_its_status_is_downgraded() -> None:
    """Derived known-bads: a verb the CLI ships may claim neither TO BUILD nor NOT PLANNED."""
    text = contract_text()
    ships = parser_verbs()
    subjects = [h for h in verb_headings(text) if h.verb in ships]
    assert subjects, "anti-vacuity: no shipped verb heading to mutate"
    for h in subjects:
        for wrong in ("TO BUILD", "NOT PLANNED"):
            bad = _mutated(text, h.text, h.text.replace(f"({h.statuses[0]})", f"({wrong})"))
            assert _real_violations(bad), f"{wrong} on shipped `radar {h.verb}` passed"


def test_every_unshipped_heading_fails_if_it_claims_to_ship() -> None:
    """Derived known-bad: a verb absent from the CLI may not claim SHIPPED."""
    text = contract_text()
    ships = parser_verbs()
    subjects = [h for h in verb_headings(text) if h.verb not in ships]
    assert subjects, "anti-vacuity: no unshipped verb heading to mutate"
    for h in subjects:
        bad = _mutated(text, h.text, h.text.replace(f"({h.statuses[0]})", "(SHIPPED)"))
        assert _real_violations(bad), f"SHIPPED on absent `radar {h.verb}` passed"


def test_a_heading_with_no_status_and_a_heading_with_two_both_fail() -> None:
    """Behavior 4 over the real document, in both directions."""
    text = contract_text()
    for h in verb_headings(text):
        stripped = _mutated(text, h.text, h.text.replace(f" ({h.statuses[0]})", ""))
        assert _real_violations(stripped), f"`radar {h.verb}` with no status passed"
        doubled = _mutated(
            text, h.text, h.text.replace(f"({h.statuses[0]})", f"({h.statuses[0]}) (SHIPPED)")
        )
        assert _real_violations(doubled), f"`radar {h.verb}` with two statuses passed"


# --------------------------------------------------------------------------------------
# Two-sided proofs: synthetic documents, so every rule is exercised including TO BUILD
# --------------------------------------------------------------------------------------

#: Sets small enough to reason about, so a synthetic case proves the RULE and not the repo.
_PARSER = frozenset({"scan"})
_ROADMAP = frozenset({"scan", "planned"})


def _doc(heading: str) -> str:
    return "\n".join(["# Doc", "", "## Preamble", "", "prose", "", heading, "", "prose", ""])


def _synthetic_violations(heading: str) -> tuple[str, ...]:
    return status_violations(verb_headings(_doc(heading)), parser=_PARSER, roadmap=_ROADMAP)


@pytest.mark.parametrize(
    "heading",
    [
        "## `radar absent` - (SHIPPED)",  # claims to ship, is not in the parser
        "## `radar scan` - (NOT PLANNED)",  # denies a verb the parser ships
        "## `radar scan` - (TO BUILD)",  # already shipped, so nothing to build
        "## `radar unplanned` - (TO BUILD)",  # no roadmap row owns it
        "## `radar absent` - (PLANNED)",  # not a recognised status
        "## `radar absent` - (SHIPPED) (NOT PLANNED)",  # two statuses
        "## `radar absent` - the reverse direction",  # no status at all
    ],
)
def test_synthetic_known_bads_are_all_caught(heading: str) -> None:
    """Behavior 8: each rule says NO to a document that breaks exactly that rule."""
    assert _synthetic_violations(heading), f"known-bad passed: {heading}"


@pytest.mark.parametrize(
    "heading",
    [
        "## `radar scan` - (SHIPPED)",  # ships and says so
        "## `radar absent` - (NOT PLANNED)",  # absent and says so
        "## `radar planned` - (TO BUILD)",  # absent, and a roadmap row owns it
        "## The invariant a consumer must not launder",  # names no verb: not collected
        "## What a consumer must never do (SHIPPED)",  # a status but no verb: not collected
    ],
)
def test_synthetic_known_goods_all_pass(heading: str) -> None:
    """The other side: the rule is not simply "everything fails".

    `radar planned` is the positive control for behavior 7 -- TO BUILD is legal exactly
    when a roadmap row owns the verb, so a passing case is what proves the clause is a
    rule rather than a ban.
    """
    assert _synthetic_violations(heading) == ()


# --------------------------------------------------------------------------------------
# The readers themselves: anti-vacuity and fail-closed
# --------------------------------------------------------------------------------------


def test_parser_and_roadmap_readers_are_not_vacuous() -> None:
    """Two empty sets agreeing with each other is the green that means nothing."""
    verbs = parser_verbs()
    assert len(verbs) >= 2, verbs
    planned = roadmap_verbs(roadmap_text())
    assert planned, "the roadmap table names no verb at all"


def test_collector_raises_on_a_document_with_no_level_two_headings() -> None:
    with pytest.raises(VerbHeadingError):
        verb_headings("# Doc\n\nprose only\n")


def test_roadmap_reader_raises_on_a_document_with_no_table() -> None:
    with pytest.raises(VerbHeadingError):
        roadmap_verbs("# Roadmap\n\nno table here\n")


def test_no_test_in_this_module_stands_down() -> None:
    """A stood-down test is invisible in a suite total, so none is allowed here."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    # Assembled from fragments so this check cannot match its own literals -- a
    # self-matching guard fails on a healthy file, which is a fail-CLOSED detector.
    banned = ("pytest." + "skip(", "pytest." + "xfail(", "mark." + "skip", "mark." + "xfail")
    for token in banned:
        assert token not in source, f"a test stands down via {token}"
    assert "mark.parametrize" in source, "anti-vacuity: the guard must read real markers"
