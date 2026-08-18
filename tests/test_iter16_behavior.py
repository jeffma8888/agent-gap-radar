"""Iteration 16 behaviors: the consumer contract stops promising a verb nobody is building.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing in this module reads `src/`,
the engineer's notes, the reviewer's notes, or any diff. The oracles are

* two COMMITTED documents -- `docs/CONSUMER_CONTRACT.md` and `PRODUCT.md`,
* the public parser surface obtained by CALLING `build_parser()`, never a hand-copied
  list of verbs, and
* the CLI's own observable output (exit code, stdout bytes) via `main`.

WHY THE COLLECTOR HERE IS A SECOND IMPLEMENTATION, ON PURPOSE
The deliverable ships its own heading collector. Re-using it to check the document would
make one bug green in two places, so this module re-derives the collection from the spec's
words -- verb = the token after `radar` inside backticks on a level-2 heading -- and then
asserts the two independent readings AGREE on the committed file
(`test_independent_collector_agrees_with_the_delivered_brake`). Agreement between two
implementations is evidence; agreement with itself is not.

THE ONE SPEC AMBIGUITY, TESTED THE REASONABLE WAY AND REPORTED
Behavior 4 names the closed set `{SHIPPED, TO BUILD, NOT PLANNED}` but does not say whether
the surrounding parentheses are part of the token. This module matches the BARE tokens
(parentheses optional), which is the weaker requirement and therefore the safer oracle: any
heading the delivered brake accepts, this module also sees. Both readings return the same
answer on the committed file, and a test pins that equivalence rather than assuming it.

WHAT THIS FILE DOES NOT PROVE, STATED RATHER THAN IMPLIED
The rule is LEXICAL over level-2 (`## `) ATX headings and finds a verb only where the
heading spells it inside backticks as `radar <verb>`. A section that DESCRIBES a verb
without naming it that way escapes the rule entirely, as does a promise made in body prose,
in a table cell, or under a deeper (`###`) heading. Behavior 10's diff-scope half -- "the
diff touches docs/, PRODUCT.md and tests/ only, with a zero-line src/ diff" -- is NOT
asserted here: reading a diff is outside this role's isolation contract, so what is pinned
instead is the OBSERVABLE consequence a zero-line `src/` diff must have (the verb surface,
the exit codes and the one-newline renderer tail), and the file-scope claim is left to the
final gate.

No network is touched, and nothing under the repo's own `gaps/` register is read to make an
assertion true -- that register is grown by an unattended research pass, so a keyed
expectation over it would go red against a CORRECT register.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass

import pytest

from agent_gap_radar.cli import build_parser, main

REPO = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO / "docs" / "CONSUMER_CONTRACT.md"
ROADMAP_PATH = REPO / "PRODUCT.md"

#: The delivered brake module, read as TEXT only (behavior 9 is a claim about its
#: docstring). `tests/` is explicitly readable under this role's isolation contract.
BRAKE_PATH = REPO / "tests" / "test_contract_verb_headings.py"

#: The closed status vocabulary the spec names, longest-first so `NOT PLANNED` can never be
#: split into two shorter matches by the alternation.
STATUS_TOKENS = ("NOT PLANNED", "TO BUILD", "SHIPPED")
_STATUS_RE = re.compile("|".join(re.escape(token) for token in STATUS_TOKENS))
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_RADAR_VERB_RE = re.compile(r"radar\s+([A-Za-z][\w-]*)")
_SEPARATOR_ROW_RE = re.compile(r"^\|[\s:|-]+\|$")


@dataclass(frozen=True)
class Heading:
    """One (level-2 heading, verb) pair with every status token that heading carries."""

    line_no: int
    text: str
    verb: str
    statuses: tuple[str, ...]


def _contract() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _roadmap() -> str:
    return ROADMAP_PATH.read_text(encoding="utf-8")


def collect(text: str, level: int = 2) -> tuple[Heading, ...]:
    """Every heading at `level` naming a `radar <verb>` inside backticks."""
    prefix = "#" * level + " "
    deeper = "#" * (level + 1)
    found: list[Heading] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.startswith(prefix) or line.startswith(deeper):
            continue
        statuses = tuple(match.group(0) for match in _STATUS_RE.finditer(line))
        for span in _CODE_SPAN_RE.findall(line):
            match = _RADAR_VERB_RE.match(span.strip())
            if match is not None:
                found.append(Heading(line_no, line, match.group(1), statuses))
    return tuple(found)


def parser_choices() -> frozenset[str]:
    """The subcommands `build_parser()` actually exposes. FAILS CLOSED.

    An empty verb set would make every `NOT PLANNED` heading pass for the wrong reason, so
    a parser with no subparsers action raises instead of returning nothing.
    """
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return frozenset(action.choices)
    raise AssertionError("build_parser() exposes no subparsers action")


def roadmap_named_verbs(text: str) -> frozenset[str]:
    """Verbs named as `radar <verb>` by a ROW of the roadmap table. FAILS CLOSED."""
    rows = [
        line
        for line in text.splitlines()
        if line.lstrip().startswith("|") and not _SEPARATOR_ROW_RE.match(line.strip())
    ]
    if not rows:
        raise AssertionError("no roadmap table rows found; nothing could be planned")
    verbs: set[str] = set()
    for row in rows:
        for span in _CODE_SPAN_RE.findall(row):
            match = _RADAR_VERB_RE.match(span.strip())
            if match is not None:
                verbs.add(match.group(1))
    return frozenset(verbs)


def violations(
    headings: tuple[Heading, ...], *, parser: frozenset[str], roadmap: frozenset[str]
) -> tuple[str, ...]:
    """Behaviors 4-7 as one evaluator: every disagreement, as a readable line."""
    out: list[str] = []
    for heading in headings:
        if len(heading.statuses) != 1:
            out.append(
                f"line {heading.line_no}: `radar {heading.verb}` carries "
                f"{len(heading.statuses)} status tokens {heading.statuses}; "
                "behavior 4 requires exactly one"
            )
            continue
        status = heading.statuses[0]
        if status == "SHIPPED" and heading.verb not in parser:
            out.append(
                f"line {heading.line_no}: `radar {heading.verb}` is SHIPPED but is not a "
                f"subcommand of build_parser() ({sorted(parser)})"
            )
        if status == "NOT PLANNED" and heading.verb in parser:
            out.append(
                f"line {heading.line_no}: `radar {heading.verb}` is NOT PLANNED but the "
                "CLI ships it"
            )
        if status == "TO BUILD":
            if heading.verb in parser:
                out.append(
                    f"line {heading.line_no}: `radar {heading.verb}` is TO BUILD but the "
                    "CLI already ships it"
                )
            if heading.verb not in roadmap:
                out.append(
                    f"line {heading.line_no}: `radar {heading.verb}` is TO BUILD but no "
                    "PRODUCT.md roadmap row names it"
                )
    return tuple(out)


def _real_violations(text: str) -> tuple[str, ...]:
    return violations(
        collect(text), parser=parser_choices(), roadmap=roadmap_named_verbs(_roadmap())
    )


# --------------------------------------------------------------------------------------
# The oracle is not vacuous
# --------------------------------------------------------------------------------------


def test_the_status_matcher_and_the_verb_matcher_both_really_fire() -> None:
    """An anti-vacuity gate: a green suite below must not mean 'the regexes see nothing'.

    Each matcher is shown firing on a planted positive and staying silent on a negative,
    because a status matcher that matched nothing would report every heading as
    'no status' and a verb matcher that matched nothing would report zero headings --
    both of which are shapes this suite has been bitten by before.
    """
    assert _STATUS_RE.findall("x (SHIPPED) y") == ["SHIPPED"]
    assert _STATUS_RE.findall("x (NOT PLANNED) y") == ["NOT PLANNED"]
    assert _STATUS_RE.findall("x (TO BUILD) y") == ["TO BUILD"]
    assert _STATUS_RE.findall("nothing here") == []
    assert collect("## `radar demo` - x (SHIPPED)\n")[0].verb == "demo"
    assert collect("## a heading naming no verb\n") == ()
    # A deeper heading is out of the collector's declared domain.
    assert collect("### `radar demo` - x (SHIPPED)\n") == ()


def test_the_committed_documents_are_both_readable_and_non_vacuous() -> None:
    """The two committed oracles really produce expectation sets."""
    assert len(_contract().splitlines()) > 50
    assert len(parser_choices()) >= 8
    assert roadmap_named_verbs(_roadmap()), "roadmap names no radar verb at all"


# --------------------------------------------------------------------------------------
# Behaviors 1-6: the committed document
# --------------------------------------------------------------------------------------


def test_behavior1_no_heading_is_still_marked_to_build() -> None:
    """Behavior 1: no `##` heading in the contract carries the status `(TO BUILD)`."""
    offenders = [
        heading.text for heading in collect(_contract()) if "TO BUILD" in heading.statuses
    ]
    assert offenders == [], offenders
    # Stronger than the heading collector, and cheap: the token is gone from EVERY
    # level-2 heading line, verb-naming or not.
    assert [
        line
        for line in _contract().splitlines()
        if line.startswith("## ") and "TO BUILD" in line
    ] == []


def test_behavior3_collector_finds_exactly_scan_and_ingest() -> None:
    """Behavior 3: exactly two verb-naming `##` headings, naming `scan` and `ingest`."""
    headings = collect(_contract())
    assert len(headings) == 2, [heading.text for heading in headings]
    assert sorted(heading.verb for heading in headings) == ["ingest", "scan"]


def test_behavior4_every_verb_heading_carries_exactly_one_status() -> None:
    """Behavior 4: exactly one status token from the closed set, per collected heading."""
    for heading in collect(_contract()):
        assert len(heading.statuses) == 1, (heading.verb, heading.statuses)
        assert heading.statuses[0] in STATUS_TOKENS


def test_behavior5_the_shipped_heading_names_a_verb_the_parser_exposes() -> None:
    """Behavior 5: a `SHIPPED` heading names one of `build_parser()`'s subcommands."""
    shipped = [
        heading.verb for heading in collect(_contract()) if heading.statuses == ("SHIPPED",)
    ]
    assert shipped == ["scan"]
    assert set(shipped) <= parser_choices()


def test_behavior6_the_not_planned_heading_names_a_verb_the_parser_lacks() -> None:
    """Behavior 6: a `NOT PLANNED` heading names a verb that is NOT a subcommand."""
    not_planned = [
        heading.verb
        for heading in collect(_contract())
        if heading.statuses == ("NOT PLANNED",)
    ]
    assert not_planned == ["ingest"]
    assert set(not_planned).isdisjoint(parser_choices())


def test_behavior8_committed_document_is_the_known_good() -> None:
    """Behavior 8, good side: the real committed file produces ZERO violations."""
    assert _real_violations(_contract()) == ()


# --------------------------------------------------------------------------------------
# Behavior 2: the demoted section keeps its argument
# --------------------------------------------------------------------------------------


def _section_body(text: str, needle: str) -> str:
    """The body of the level-2 section whose heading contains `needle`."""
    lines = text.splitlines()
    starts = [n for n, line in enumerate(lines) if line.startswith("## ")]
    heads = [n for n in starts if needle in lines[n]]
    assert len(heads) == 1, f"expected one section naming {needle!r}, got {heads}"
    head = heads[0]
    after = [n for n in starts if n > head]
    end = after[0] if after else len(lines)
    return "\n".join(lines[head + 1 : end])


def test_behavior2_ingest_section_is_not_planned_and_keeps_its_argument() -> None:
    """Behavior 2: the heading says `(NOT PLANNED)`; the body keeps the ladder argument
    and names the shipped mechanism.

    The document is hard-wrapped, so every claim is asserted against the
    WHITESPACE-NORMALISED body -- a guessed line break inside a sentence is a
    fail-closed assertion, not a finding.
    """
    text = _contract()
    heading = next(
        heading for heading in collect(text) if heading.verb == "ingest"
    )
    assert heading.statuses == ("NOT PLANNED",), heading.text

    body = " ".join(_section_body(text, "radar ingest").split())
    assert "without a citation would make every score in the register unbelievable" in body
    assert "tools/promote.py" in body
    # The section must point at the mechanism, not merely mention a filename.
    assert "research/CANDIDATE_CONTRACT.md" in body


# --------------------------------------------------------------------------------------
# Behaviors 7-8: the rules proven two-sided on synthetic documents
# --------------------------------------------------------------------------------------

#: Synthetic expectation sets, so the TO BUILD clause is provable at all: `planned` is on
#: the synthetic roadmap and absent from the synthetic parser, which is the one combination
#: the real repo cannot supply (nothing is legitimately TO BUILD today).
_SYN_PARSER = frozenset({"scan"})
_SYN_ROADMAP = frozenset({"scan", "planned"})


def _synthetic_violations(heading_line: str) -> tuple[str, ...]:
    document = f"# doc\n\nintro\n\n{heading_line}\n\nbody\n"
    return violations(collect(document), parser=_SYN_PARSER, roadmap=_SYN_ROADMAP)


@pytest.mark.parametrize(
    ("heading_line", "label"),
    [
        ("## `radar ingest` - x (SHIPPED)", "SHIPPED but not a parser verb"),
        ("## `radar scan` - x (NOT PLANNED)", "NOT PLANNED but the CLI ships it"),
        ("## `radar ingest` - x (TO BUILD)", "TO BUILD with no roadmap row"),
        ("## `radar scan` - x (TO BUILD)", "TO BUILD but already shipped"),
        ("## `radar ingest` - the reverse direction", "no recognised status"),
        ("## `radar ingest` - x (TO BUILD) (NOT PLANNED)", "two status tokens"),
    ],
)
def test_behavior8_known_bad_headings_are_all_caught(
    heading_line: str, label: str
) -> None:
    """Behavior 8, bad side: every way a status can disagree produces a violation."""
    found = _synthetic_violations(heading_line)
    assert found, f"no violation for known-bad case: {label}"


@pytest.mark.parametrize(
    ("heading_line", "label"),
    [
        ("## `radar scan` - x (SHIPPED)", "SHIPPED and in the parser"),
        ("## `radar ingest` - x (NOT PLANNED)", "NOT PLANNED and absent from the parser"),
        ("## `radar planned` - x (TO BUILD)", "TO BUILD, absent from parser, on roadmap"),
        ("## a heading that names no verb (SHIPPED)", "no verb, so out of domain"),
    ],
)
def test_behavior7_and_8_known_good_headings_all_pass(
    heading_line: str, label: str
) -> None:
    """Behavior 7: `TO BUILD` is LEGAL when a roadmap row owns the promise.

    The third case is the whole reason behavior 7 needs a synthetic document: the clause
    must be a RULE, not a ban, and the real file has no legitimate TO BUILD heading to
    prove that with.
    """
    assert _synthetic_violations(heading_line) == (), label


def test_the_to_build_clause_reads_both_of_its_two_conditions() -> None:
    """Behavior 7 is a conjunction, so each conjunct is falsified on its own.

    Without this, a rule that only ever checked the parser would pass every test above.
    """
    on_roadmap_only = violations(
        collect("## `radar planned` - x (TO BUILD)\n"),
        parser=frozenset({"planned"}),
        roadmap=_SYN_ROADMAP,
    )
    assert on_roadmap_only, "TO BUILD naming a verb the parser ships must fail"
    in_parser_only = violations(
        collect("## `radar orphan` - x (TO BUILD)\n"),
        parser=_SYN_PARSER,
        roadmap=frozenset({"scan"}),
    )
    assert in_parser_only, "TO BUILD with no roadmap row must fail"


# --------------------------------------------------------------------------------------
# Behavior 9, and agreement between the two independent readings
# --------------------------------------------------------------------------------------


def test_behavior9_the_delivered_brake_states_its_lexical_limitation() -> None:
    """Behavior 9: the limitation is written in the module docstring, not left implied."""
    assert BRAKE_PATH.exists(), f"no brake module at {BRAKE_PATH.name}"
    source = BRAKE_PATH.read_text(encoding="utf-8")
    docstring = ast_docstring(source)
    assert docstring is not None, "brake module has no docstring"
    normalised = " ".join(docstring.split())
    assert "LEXICAL" in normalised or "lexical" in normalised
    for clause in ("radar <verb>", "escapes the rule"):
        assert clause in normalised, clause


def ast_docstring(source: str) -> str | None:
    """The module docstring, parsed rather than regexed."""
    import ast

    return ast.get_docstring(ast.parse(source))


def test_independent_collector_agrees_with_the_delivered_brake() -> None:
    """Two independent readings of the same file must return the same (verb, status) set.

    This is the only assertion in the module that touches the deliverable's own code, and
    it is deliberately an AGREEMENT check: a disagreement means one of the two collectors
    is wrong, which no self-consistent module could ever tell us.
    """
    brake = pytest.importorskip("test_contract_verb_headings", reason="brake module absent")
    theirs = {(h.verb, h.statuses) for h in brake.verb_headings(_contract())}
    mine = {(h.verb, h.statuses) for h in collect(_contract())}
    assert mine == theirs
    assert brake.parser_verbs() == parser_choices()
    assert brake.roadmap_verbs(_roadmap()) == roadmap_named_verbs(_roadmap())


# --------------------------------------------------------------------------------------
# Behavior 10: the observable consequence of a zero-line `src/` diff
# --------------------------------------------------------------------------------------


def test_behavior10_the_verb_surface_is_the_eight_shipped_verbs_and_no_ingest() -> None:
    """Behavior 10: the CLI's verb surface is unchanged, and `ingest` is not on it."""
    assert parser_choices() == frozenset(
        {"validate", "list", "report", "show", "prd", "scan", "diff", "taxonomy"}
    )
    assert "ingest" not in parser_choices()


def test_behavior10_help_and_bare_invocation_still_exit_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Behavior 10: exit codes are unchanged for the two invocations with no inputs."""
    assert main([]) == 0
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def _register(root: pathlib.Path) -> pathlib.Path:
    """A minimal schema-valid register, built in `tmp_path` -- never the repo's own."""
    record = {
        "id": "GAP-901",
        "title": "title of GAP-901",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [
            {
                "source_class": "first-party-field",
                "title": "t",
                "locator": "https://example.invalid/x",
                "date": "2026-01-02",
                "quote": "the verbatim line",
            }
        ],
    }
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    (gaps / "GAP-901.json").write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    return gaps


@pytest.mark.parametrize("verb", ["list", "report", "taxonomy"])
def test_behavior10_every_renderer_still_ends_in_exactly_one_newline(
    verb: str, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 10: the byte-stability tail of the published renderers is unchanged."""
    argv = [verb] if verb == "taxonomy" else [verb, str(_register(tmp_path).parent)]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert out, f"{verb} produced no document"
    assert out.endswith("\n")
    assert not out.endswith("\n\n")
