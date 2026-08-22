"""Iteration 65 behaviors: `radar show` publishes the DISTINCT-SOURCE denominator.

`pm.md` measured that the live register holds more citations than source documents on
several records -- `radar show` for such a record renders N `### N.` evidence blocks whose
title, source class, date AND locator are byte-identical, and said nowhere that they are one
document, so a reader counts N pieces of evidence where the scorer counts fewer. Since the
pairwise corroboration rule landed, `confidence()` has known better and had no surface to say
so. This iteration derives the count through the same `scoring._source_key` the scorer keys on
and prints it once under `## Evidence`, feeding no score and entering no ordering.

BLACK-BOX, AND THE ISOLATION CONTRACT IS HONORED. Every expectation here comes from `pm.md`
(Feature / Why / Expected Behaviors) and is measured by RUNNING the product -- `cli.main`,
`render.gap_brief`, `scoring.distinct_sources`, `registry.load_all` -- or by reading the live
register, which is published data. Nothing here was read from `src/`, from the engineer's or
the reviewer's notes, from `IMPLEMENTATION.patch`, or from any diff.

STRUCTURAL CHOICES, so this file cannot lie later:

* **Every expected line is DERIVED, never pinned.** The count line for each of the live
  records is computed in this run from `len(gap.evidence)` and `scoring.distinct_sources(gap)`
  with the two plurals formed INDEPENDENTLY by this file's own arithmetic. No gap id carries a
  literal citation count, so an unattended research pass that adds a citation cannot red a
  correct repo. Behavior 6's three plural combinations are asserted as WITNESSED by the live
  register (and separately proved on fixtures), never as belonging to named ids.
* **The independence of the two plurals is proved on a FIXTURE, not only on live data.** A
  record whose 3 citations are 3 spellings of one URL is the shape that a single shared
  `if n == 1` flag renders wrongly; the fixture makes that case permanent even if the live
  register loses its witness.
* **Behavior 1 is proved by SEAM, not by re-derivation.** `distinct_sources` is required to
  CALL `_source_key`; monkeypatching that name to a collapsing stub and then to an
  everything-is-unique stub moves the answer in both directions, which re-implemented
  normalisation could not do.
* **Every absence claim has a two-sided control in the same test.** The line extractor is run
  against a known-present and a known-absent document; the cross-verb absence check runs its
  own detector against `radar show` output first, so a broken matcher cannot read as silence.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; fixture locators use `example.invalid`, which cannot resolve.
"""

from __future__ import annotations

import io
import contextlib
import pathlib
import re

import pytest

from agent_gap_radar import cli, render, scoring
from agent_gap_radar.models import Gap
from agent_gap_radar.registry import load_all

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

REGISTER = load_all(GAPS_DIR)
BY_ID = {gap.id: gap for gap in REGISTER}
LIVE_IDS = sorted(BY_ID)

EVIDENCE_HEADING = "## Evidence"
FIRST_BLOCK = "### 1."

#: Behavior 7: the invariant tail. A denominator, never a verdict.
TRAILING_SENTENCE = "Independence is counted by document, not by citation."

#: Behavior 4's shape. Anchored whole-line so trailing punctuation or an appended warning
#: cannot slip past, and the two counts are captured so they can be checked against the API.
COUNT_LINE_RE = re.compile(
    r"^(?P<n>\d+) citations? across (?P<m>\d+) distinct source documents?\. "
    + re.escape(TRAILING_SENTENCE)
    + r"$"
)

#: Behavior 9's verbs, with the argument shape each one really takes.
OTHER_VERBS: tuple[tuple[str, ...], ...] = (
    ("report", "."),
    ("list", "."),
    ("list", ".", "--json"),
    ("validate", "."),
    ("taxonomy",),
    ("prd", ".", "--gap", "GAP-003"),
    ("scan", ".", "--gaps", "gaps"),
)

#: Behavior 8: sections that must survive the insertion untouched.
REQUIRED_HEADINGS = (
    "## Problem",
    "## Symptom",
    "## Why this is still open",
    "## Existing partial solutions",
    "## Build hypothesis",
    "## Detection",
    "## Evidence",
)


# ---------------------------------------------------------------------------
# plumbing -- run the product, parse only what it publishes
# ---------------------------------------------------------------------------

def _run(argv: list[str]) -> tuple[int, str, str]:
    """Run the CLI in-process. Returns (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def _show(gap_id: str) -> str:
    code, out, err = _run(["show", gap_id, str(REPO_ROOT)])
    assert code == 0, (gap_id, code, err)
    assert err == "", err
    return out


def _expected_count_line(gap: Gap) -> str:
    """The spec's line, derived. The two plurals are formed from their OWN number."""
    n = len(gap.evidence)
    m = scoring.distinct_sources(gap)
    return (
        f"{n} citation{'' if n == 1 else 's'} across "
        f"{m} distinct source document{'' if m == 1 else 's'}. {TRAILING_SENTENCE}"
    )


def _count_lines(document: str) -> list[str]:
    """Every line of `document` matching behavior 4's shape."""
    return [line for line in document.splitlines() if COUNT_LINE_RE.match(line)]


def _sole_count_line(document: str) -> str:
    found = _count_lines(document)
    assert len(found) == 1, found
    return found[0]


def _fixture_gap(locators: tuple[str, ...], gid: str = "GAP-901") -> Gap:
    """A validated record with one citation per locator, all the same source class."""
    return Gap.model_validate({
        "id": gid, "title": f"t{gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s",
        "why_now": "w", "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": "peer-reviewed", "title": "t",
                      "locator": locator, "date": "2026-01-02", "quote": "q"}
                     for locator in locators],
    })


# ---------------------------------------------------------------------------
# control: the detectors used below are two-sided before anything trusts them
# ---------------------------------------------------------------------------

def test_the_count_line_detector_is_two_sided():
    """A known-present document yields one hit; known-absent and near-miss yield none."""
    good = f"## Evidence\n\n2 citations across 2 distinct source documents. {TRAILING_SENTENCE}\n"
    assert len(_count_lines(good)) == 1
    assert _count_lines("## Evidence\n\n### 1. anything\n") == []
    near_miss = f"2 citations across 2 distinct source documents. {TRAILING_SENTENCE} Fewer than cited.\n"
    assert _count_lines(near_miss) == [], "an appended clause must not read as the bare line"
    assert _count_lines("2 citations across 2 distinct source documents.") == [], \
        "the trailing sentence is part of the line"


def test_the_live_register_is_not_vacuous():
    """Anti-vacuity for everything below: 16-ish records, and BOTH sides are witnessed."""
    assert len(REGISTER) >= 10, len(REGISTER)
    mismatched = [g.id for g in REGISTER if scoring.distinct_sources(g) < len(g.evidence)]
    matched = [g.id for g in REGISTER if scoring.distinct_sources(g) == len(g.evidence)]
    assert mismatched, "no live record has fewer sources than citations -- known-bad side is empty"
    assert matched, "no live record has sources == citations -- known-good side is empty"


# ---------------------------------------------------------------------------
# Behavior 1 -- distinct_sources is the set size of _source_key, and CALLS it
# ---------------------------------------------------------------------------

def test_behavior_1_distinct_sources_is_the_source_key_set_size():
    for gap in REGISTER:
        expected = len({scoring._source_key(e) for e in gap.evidence})
        assert scoring.distinct_sources(gap) == expected, gap.id
        assert scoring.distinct_sources(gap) <= len(gap.evidence), gap.id


def test_behavior_1_distinct_sources_calls_source_key(monkeypatch):
    """The seam: swapping `_source_key` must move the answer in BOTH directions.

    Re-implemented normalisation would ignore both stubs and keep returning the real
    count, so this is what distinguishes calling the helper from copying its logic.
    """
    multi = next(g for g in REGISTER if len(g.evidence) > 1)
    real = scoring.distinct_sources(multi)

    monkeypatch.setattr(scoring, "_source_key", lambda evidence: "one-document")
    assert scoring.distinct_sources(multi) == 1, "a collapsing key must collapse the count"

    counter = iter(range(10_000))
    monkeypatch.setattr(scoring, "_source_key", lambda evidence: f"u{next(counter)}")
    assert scoring.distinct_sources(multi) == len(multi.evidence), \
        "an all-unique key must give one source per citation"

    monkeypatch.undo()
    assert scoring.distinct_sources(multi) == real


# ---------------------------------------------------------------------------
# Behavior 2 -- total on empty evidence
# ---------------------------------------------------------------------------

def test_behavior_2_empty_evidence_returns_zero_and_raises_nothing():
    """`model_construct` bypasses validation, which is the only way to reach this state.

    Noted as PM feedback in the tester report: `models.Gap` requires at least one citation,
    so no loaded record can be empty -- the branch is unreachable through `registry.load_all`
    and is unit-tested here the way `test_scoring.py` unit-tests its other unreachable keys.
    """
    empty = Gap.model_construct(id="GAP-902", evidence=[])
    assert scoring.distinct_sources(empty) == 0


# ---------------------------------------------------------------------------
# Behavior 3 -- normalisation is inherited, not re-implemented
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spellings", [
    ("https://example.invalid/p", "https://example.invalid/p#s2"),
    ("https://example.invalid/p", "https://example.invalid/p/"),
    ("https://example.invalid/p", "https://EXAMPLE.invalid/P"),
    ("https://example.invalid/p", "https://example.invalid/p/", "https://EXAMPLE.invalid/P#s2"),
])
def test_behavior_3_one_document_spelled_several_ways_counts_once(spellings):
    gap = _fixture_gap(spellings)
    assert len(gap.evidence) == len(spellings)
    assert scoring.distinct_sources(gap) == 1, spellings


def test_behavior_3_genuinely_different_documents_still_count_separately():
    """The known-good side: normalisation must not merge two real documents."""
    gap = _fixture_gap(("https://example.invalid/a", "https://example.invalid/b"))
    assert scoring.distinct_sources(gap) == 2
    same_host = _fixture_gap(("https://example.invalid/repo/x", "https://example.invalid/repo/y"))
    assert scoring.distinct_sources(same_host) == 2, "one host is not one source"


# ---------------------------------------------------------------------------
# Behavior 4 -- exactly one derived line inside ## Evidence
# ---------------------------------------------------------------------------

def test_behavior_4_gap_brief_emits_exactly_one_derived_count_line():
    for gap in REGISTER:
        document = render.gap_brief(gap)
        line = _sole_count_line(document)
        assert line == _expected_count_line(gap), gap.id
        match = COUNT_LINE_RE.match(line)
        assert int(match.group("n")) == len(gap.evidence), gap.id
        assert int(match.group("m")) == scoring.distinct_sources(gap), gap.id


def test_behavior_4_the_line_reaches_the_cli_unchanged():
    for gap_id in LIVE_IDS:
        assert _sole_count_line(_show(gap_id)) == _expected_count_line(BY_ID[gap_id]), gap_id


# ---------------------------------------------------------------------------
# Behavior 5 -- position: after the heading and its blank, before ### 1.
# ---------------------------------------------------------------------------

def test_behavior_5_the_line_sits_directly_under_the_evidence_heading():
    for gap_id in LIVE_IDS:
        lines = _show(gap_id).splitlines()
        assert EVIDENCE_HEADING in lines, gap_id
        head = lines.index(EVIDENCE_HEADING)
        assert lines[head + 1] == "", (gap_id, "no blank line after the heading")
        assert lines[head + 2] == _expected_count_line(BY_ID[gap_id]), gap_id
        assert lines[head + 3] == "", (gap_id, "exactly one blank line must follow")
        assert lines[head + 4].startswith(FIRST_BLOCK), (gap_id, lines[head + 4])


# ---------------------------------------------------------------------------
# Behavior 6 -- the two plurals move independently
# ---------------------------------------------------------------------------

def test_behavior_6_all_three_plural_combinations_are_witnessed_live():
    """The live register supplies singular/singular, plural/singular and plural/plural."""
    seen = set()
    for gap in REGISTER:
        n, m = len(gap.evidence), scoring.distinct_sources(gap)
        seen.add((n == 1, m == 1))
        assert _sole_count_line(_show(gap.id)) == _expected_count_line(gap), gap.id
    assert (True, True) in seen, "no record with 1 citation and 1 source"
    assert (False, True) in seen, "no record with several citations of ONE document"
    assert (False, False) in seen, "no record with several citations of several documents"


def test_a_shared_plural_flag_would_be_DETECTED_here():
    """Control for the test above: the wrong rendering must differ from the derived one.

    A single `if n == 1` wrapping the whole sentence pluralises both nouns off `n`. On the
    3-citations/1-document shape that produces `1 distinct source documents`, which matches
    the shape regex, so it is the EQUALITY assertion that carries the load -- proved here by
    measuring that the two strings really differ rather than assuming it.
    """
    gap = _fixture_gap((
        "https://example.invalid/p",
        "https://example.invalid/p/",
        "https://EXAMPLE.invalid/P#s2",
    ))
    derived = _expected_count_line(gap)
    shared_flag = f"3 citations across 1 distinct source documents. {TRAILING_SENTENCE}"
    assert COUNT_LINE_RE.match(shared_flag), "the regex alone cannot see this bug"
    assert derived != shared_flag, "the equality assertion would not discriminate"
    assert _sole_count_line(render.gap_brief(gap)) != shared_flag


def test_the_derived_expectation_is_not_constant():
    """Anti-vacuity for every `== _expected_count_line(gap)` above: it varies by record."""
    derived = {_expected_count_line(gap) for gap in REGISTER}
    assert len(derived) >= 3, derived


def test_behavior_6_a_shared_plural_flag_is_impossible():
    """The fixture a single `if n == 1` renders wrongly: 3 citations, 1 document."""
    gap = _fixture_gap((
        "https://example.invalid/p",
        "https://example.invalid/p/",
        "https://EXAMPLE.invalid/P#s2",
    ))
    document = render.gap_brief(gap)
    assert _sole_count_line(document) == (
        f"3 citations across 1 distinct source document. {TRAILING_SENTENCE}"
    )
    single = _fixture_gap(("https://example.invalid/only",))
    assert _sole_count_line(render.gap_brief(single)) == (
        f"1 citation across 1 distinct source document. {TRAILING_SENTENCE}"
    )
    plural_both = _fixture_gap(("https://example.invalid/a", "https://example.invalid/b"))
    assert _sole_count_line(render.gap_brief(plural_both)) == (
        f"2 citations across 2 distinct source documents. {TRAILING_SENTENCE}"
    )


# ---------------------------------------------------------------------------
# Behavior 7 -- the tail is invariant; the line is a denominator, not a verdict
# ---------------------------------------------------------------------------

def test_behavior_7_the_trailing_sentence_is_byte_identical_on_every_record():
    tails = set()
    for gap_id in LIVE_IDS:
        line = _sole_count_line(_show(gap_id))
        head, _, tail = line.partition(". ")
        tails.add(tail)
    assert tails == {TRAILING_SENTENCE}, tails


def test_behavior_7_a_source_shortfall_renders_no_warning():
    """A mismatched record's line is EXACTLY the derived line -- nothing appended."""
    mismatched = [g for g in REGISTER if scoring.distinct_sources(g) < len(g.evidence)]
    assert mismatched, "known-bad side empty"
    for gap in mismatched:
        line = _sole_count_line(_show(gap.id))
        assert line == _expected_count_line(gap), gap.id
        lowered = line.lower()
        for verdict_word in ("warn", "only", "fewer", "but ", "!", "*", "note:", "beware",
                            "weak", "duplicate", "same document", "caution"):
            assert verdict_word not in lowered, (gap.id, verdict_word, line)


# ---------------------------------------------------------------------------
# Behavior 8 -- `radar show` is otherwise unchanged
# ---------------------------------------------------------------------------

def test_behavior_8_excising_the_two_inserted_lines_leaves_the_document_intact():
    """Structural neutrality: with the count line and its blank removed, the page is a
    complete brief whose Evidence section runs straight from the heading into `### 1.`.

    Byte-neutrality against the PRE-CHANGE bytes is not measurable inside the isolation
    contract (it needs the previous build); the tester report says so and names who owns it.
    """
    for gap_id in LIVE_IDS:
        document = _show(gap_id)
        assert document.endswith("\n") and not document.endswith("\n\n"), gap_id
        assert document.count(TRAILING_SENTENCE) == 1, gap_id

        lines = document.splitlines(keepends=True)
        line_index = next(i for i, line in enumerate(lines)
                          if COUNT_LINE_RE.match(line.rstrip("\n")))
        assert lines[line_index + 1] == "\n", gap_id
        excised = "".join(lines[:line_index] + lines[line_index + 2:])

        assert TRAILING_SENTENCE not in excised, gap_id
        stripped = excised.splitlines()
        head = stripped.index(EVIDENCE_HEADING)
        assert stripped[head + 1] == "", gap_id
        assert stripped[head + 2].startswith(FIRST_BLOCK), (gap_id, stripped[head + 2])

        positions = [excised.index(heading) for heading in REQUIRED_HEADINGS]
        assert positions == sorted(positions), (gap_id, "headings reordered or missing")
        assert excised.count("| Field | Value |") == 1, gap_id
        blocks = len([line for line in stripped if re.match(r"^### \d+\. ", line)])
        assert blocks == len(BY_ID[gap_id].evidence), (gap_id, blocks)
        assert excised.endswith("\n") and not excised.endswith("\n\n"), gap_id


# ---------------------------------------------------------------------------
# Behavior 9 -- every other verb moves zero bytes
# ---------------------------------------------------------------------------

def test_behavior_9_no_other_verb_prints_the_new_line():
    control = _show(LIVE_IDS[0])
    assert TRAILING_SENTENCE in control and _count_lines(control), \
        "the detector must fire on show before its silence elsewhere means anything"
    for argv in OTHER_VERBS:
        code, out, err = _run(list(argv))
        assert code == 0, (argv, code, err)
        assert err == "", (argv, err)
        assert out, (argv, "empty stdout -- nothing was measured")
        assert out.endswith("\n") and not out.endswith("\n\n"), argv
        assert TRAILING_SENTENCE not in out, argv
        assert _count_lines(out) == [], argv
        assert "distinct source document" not in out, argv


# ---------------------------------------------------------------------------
# Behavior 10 -- the exit contract survives
# ---------------------------------------------------------------------------

def test_behavior_10_show_keeps_its_exit_contract():
    code, out, err = _run(["show", LIVE_IDS[0], str(REPO_ROOT)])
    assert (code, err) == (0, "")
    assert out.startswith("# ") and out.endswith("\n") and not out.endswith("\n\n")

    code, out, err = _run(["show", "GAP-000", str(REPO_ROOT)])
    assert code == 2, (code, out, err)
    assert out == "", out
    assert err.startswith("Error: "), err
    assert err.endswith("\n"), err
