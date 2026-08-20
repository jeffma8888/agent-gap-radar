"""Iteration 18 behaviors: the corroboration point needs two SOURCES, not two labels.

The feature under test: `confidence()` grants its single corroboration point only when
two citations differ in `source_class` AND in source, where source identity is the
citation's `locator` with a `#fragment` stripped, a trailing `/` stripped and the
remainder case-folded. One document cited twice under two different class labels no
longer lifts a record.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, the engineer's notes,
the reviewer's notes, or any diff. Every assertion either calls the public library API
the spec names (`scoring.confidence`, `scoring.promotion_options`, `registry.load_all`,
`models.Gap`) or drives `agent_gap_radar.cli.main` and observes only the exit code,
stdout and stderr.

THE ORACLES, AND WHY THEY ARE WRITTEN HERE
* `LADDER` -- class -> weight, OBSERVED by parsing `radar taxonomy` output rather than
  imported from the module under test, so a change to the ladder cannot silently agree
  with itself (the convention iterations 05, 07 and 08 established).
* `_spec_confidence` -- this iteration's rule, re-derived from the spec's own words as a
  pairwise `any()` over citations. Compared against the real `confidence()` over a swept
  matrix of synthetic records.
* `_pre_change_confidence` -- the rule as it stood BEFORE this iteration (a set of class
  LABELS, weight-0 excluded). Behavior 8 claims no live confidence moves, and that claim
  is only testable against a statement of the old rule; this is that statement, written
  from the spec's quotation of the old comprehension.
* `_pre_change_promotion_options` -- the pre-change prescription, simulated with a
  class-only probe (the old rule read no locator, so under it the probe's source did not
  exist). Behavior 7 says the prescription is unchanged, so the oracle for it must be the
  OLD rule, not the new one.

WHY EVERY REGISTER-FACING ASSERTION USES AN ORACLE INSTEAD OF A LITERAL
`gaps/` is grown by an unattended research pass. A test that pinned a confidence value, a
class, or a citation count for a live `GAP-NNN` id would go red against a CORRECT register
days from now -- the iteration-09 landmine the spec's acceptance criteria name. So the live
register appears here only through comparisons between two independently written oracles,
plus a non-empty-domain guard, because a green result over zero rows is the failure that
looks like health.

WHAT THIS FILE DOES NOT PROVE, STATED RATHER THAN IMPLIED
Behavior 8 asserts byte-identity of six surfaces "to their pre-change output". This module
does not execute a pre-change tree, so it cannot compare against those bytes directly. It
proves the two things that byte-identity reduces to for a scoring change: every live
record's confidence is IDENTICAL under the old rule and the new one, and each of the six
surfaces is byte-stable across repeated invocation, exits 0, writes nothing to stderr and
ends in exactly one newline. A rendering change unrelated to scoring would pass here; that
is outside this iteration's claim. No network is touched.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import pathlib
import re
import types

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import confidence, promotion_options

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: One spelling of a document, and the three spellings behavior 3 says are the SAME source.
DOC = "https://example.invalid/p"
SAME_SOURCE_SPELLINGS = (DOC, DOC + "/", "https://EXAMPLE.invalid/P#s2")
OTHER_DOC = "https://example.invalid/q"


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Drive the CLI in-process; observe only exit code, stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


_LADDER_LINE = re.compile(r"^- `([a-z-]+)` \(weight (\d+)\)$")


def _observed_ladder() -> dict[str, int]:
    """class -> weight, parsed out of `radar taxonomy` rather than imported."""
    code, out, err = _run(["taxonomy"])
    assert code == 0, (code, err)
    section = out.split("## Evidence source classes", 1)
    assert len(section) == 2, "the taxonomy verb published no evidence-ladder heading"
    weights: dict[str, int] = {}
    for line in section[1].splitlines():
        match = _LADDER_LINE.match(line.strip())
        if match:
            weights[match.group(1)] = int(match.group(2))
    assert weights, "the taxonomy verb published no evidence ladder"
    return weights


LADDER = _observed_ladder()
#: Ladder order as published (strongest first) -- the order a tie group is reported in.
LADDER_ORDER = tuple(LADDER)
REAL_CLASSES = tuple(c for c in LADDER_ORDER if LADDER[c] > 0)
ZERO_CLASSES = tuple(c for c in LADDER_ORDER if LADDER[c] == 0)


def _gap(cites, gid: str = "GAP-900", sev: int = 3, freq: int = 3, tract: int = 3) -> Gap:
    """A schema-valid synthetic record whose citations are (source_class, locator) pairs."""
    return Gap.model_validate({
        "id": gid, "title": f"t{gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t", "locator": loc,
                      "date": "2026-01-02", "quote": "q"} for c, loc in cites],
    })


def _key(locator: str) -> str:
    """Source identity per behavior 3: drop `#fragment`, drop a trailing `/`, case-fold."""
    return locator.split("#", 1)[0].rstrip("/").casefold()


def _weight(cite) -> int:
    return LADDER.get(cite.source_class, 0)


def _spec_confidence(gap) -> int:
    """This iteration's rule, re-derived from the spec (behaviors 1-6)."""
    real = [c for c in gap.evidence if _weight(c) > 0]
    if not real:
        return 0
    strongest = max(_weight(c) for c in real)
    corroborated = any(
        a.source_class != b.source_class and _key(a.locator) != _key(b.locator)
        for a, b in itertools.combinations(real, 2))
    return min(5, strongest + 1) if corroborated else strongest


def _pre_change_confidence(gap) -> int:
    """The rule BEFORE this iteration: two class LABELS were enough, whatever the source."""
    real = [c for c in gap.evidence if _weight(c) > 0]
    if not real:
        return 0
    strongest = max(_weight(c) for c in real)
    labels = {c.source_class for c in real}
    return min(5, strongest + 1) if len(labels) >= 2 else strongest


def _pre_change_promotion_options(gap, floor: int) -> tuple[str, ...]:
    """The pre-change prescription: cheapest ladder rung(s) whose addition reaches `floor`.

    Simulated with a CLASS-ONLY probe, because the pre-change rule read no locator at
    all -- so under it a simulated citation had no source to collide with. Behavior 7
    claims the prescription did not move, and only the old rule can adjudicate that.
    """
    real = [c for c in gap.evidence if _weight(c) > 0]
    strongest = max((_weight(c) for c in real), default=0)
    labels = {c.source_class for c in real}
    reaching = []
    for candidate in REAL_CLASSES:
        after_labels = labels | {candidate}
        after_strongest = max(strongest, LADDER[candidate])
        after = (min(5, after_strongest + 1) if len(after_labels) >= 2
                 else after_strongest)
        if after >= floor:
            reaching.append(candidate)
    if not reaching:
        return ()
    cheapest = min(LADDER[c] for c in reaching)
    return tuple(c for c in reaching if LADDER[c] == cheapest)


# --------------------------------------------------------------------------- live register

REGISTER = load_all(GAPS_DIR)


def test_the_live_register_is_a_non_empty_domain():
    """Armed instrument: every live-register assertion below is vacuous without this."""
    assert len(REGISTER) > 0, "load_all returned no records; every register test is vacuous"


# ------------------------------------------------------------------ behaviors 1 and 2 (pair)

def test_two_classes_at_two_sources_earn_the_point_and_at_one_source_do_not():
    """Behaviors 1 + 2 asserted as a PAIR, so the change is proven two-sided.

    Both records carry the same two class labels and the same strongest weight; the ONLY
    difference is whether the second citation is a second document. A one-sided test would
    pass a scorer that had simply stopped granting the point at all.
    """
    two_sources = _gap((("peer-reviewed", DOC), ("secondary-summary", OTHER_DOC)))
    one_source = _gap((("peer-reviewed", DOC), ("secondary-summary", DOC)))
    strongest = LADDER["peer-reviewed"]

    assert confidence(two_sources) == min(5, strongest + 1)
    assert confidence(one_source) == strongest
    assert confidence(two_sources) > confidence(one_source)


# --------------------------------------------------------------------------- behavior 3

@pytest.mark.parametrize("spelling", SAME_SOURCE_SPELLINGS)
def test_every_spelling_of_one_document_is_one_source(spelling):
    """Fragment, trailing slash and case are not source identity (behavior 3)."""
    split_labels = _gap((("peer-reviewed", DOC), ("secondary-summary", spelling)))
    assert confidence(split_labels) == LADDER["peer-reviewed"], spelling


def test_no_two_spellings_of_one_document_corroborate_each_other():
    """Any PAIR drawn from the three spellings is still one source, not just DOC + x."""
    for first, second in itertools.combinations(SAME_SOURCE_SPELLINGS, 2):
        pair = _gap((("peer-reviewed", first), ("secondary-summary", second)))
        assert confidence(pair) == LADDER["peer-reviewed"], (first, second)


def test_one_host_is_not_one_source():
    """Merging too much would WITHHOLD an honest point; two paths stay two sources."""
    two_paths = _gap((("peer-reviewed", "https://example.invalid/repo/x"),
                      ("secondary-summary", "https://example.invalid/repo/y")))
    assert confidence(two_paths) == min(5, LADDER["peer-reviewed"] + 1)


# --------------------------------------------------------------------------- behavior 4

def test_same_class_at_two_sources_still_earns_nothing():
    """The point is for a different KIND of evidence, not merely a second URL."""
    assert confidence(_gap((("peer-reviewed", DOC),
                            ("peer-reviewed", OTHER_DOC)))) == LADDER["peer-reviewed"]


# --------------------------------------------------------------------------- behavior 5

@pytest.mark.parametrize("zero_class", ZERO_CLASSES)
def test_a_weightless_class_supplies_neither_half_of_a_pair(zero_class):
    """Adding weight-0 citations at fresh sources moves nothing (behavior 5)."""
    alone = confidence(_gap((("peer-reviewed", DOC),)))
    padded = _gap((("peer-reviewed", DOC),)
                  + tuple((zero_class, f"https://example.invalid/z{n}") for n in range(4)))
    assert confidence(padded) == alone == LADDER["peer-reviewed"]


def test_two_weightless_classes_at_two_sources_do_not_corroborate_each_other():
    """Both halves weightless: still 0, so a pair of weight-0 rungs cannot lift a record."""
    if len(ZERO_CLASSES) >= 2:
        pair = tuple((c, f"https://example.invalid/z{n}")
                     for n, c in enumerate(ZERO_CLASSES[:2]))
        assert confidence(_gap(pair)) == 0
    doubled = _gap(((ZERO_CLASSES[0], DOC), (ZERO_CLASSES[0], OTHER_DOC)))
    assert confidence(doubled) == 0


# --------------------------------------------------------------------------- behavior 6

def test_no_evidence_scores_zero():
    """Behavior 6's empty edge, reached with a stand-in because the SCHEMA forbids it.

    MEASURED this run: `Gap.model_validate` with `evidence: []` raises
    `ValidationError: List should have at least 1 item after validation, not 0`, so no
    validated record can exercise this branch. It is still worth pinning -- `confidence()`
    is called on stand-ins (`promotion_options` appends one) and must be total.
    """
    assert confidence(types.SimpleNamespace(evidence=[])) == 0


def test_a_register_of_only_weightless_citations_scores_zero():
    assert confidence(_gap(tuple((ZERO_CLASSES[0], f"https://example.invalid/z{n}")
                                for n in range(9)))) == 0


def test_a_corroborating_pair_survives_a_shared_source_elsewhere_in_the_record():
    """The rule is PAIRWISE, so one duplicated source must not poison the whole record.

    Three citations: `peer-reviewed` and `secondary-summary` at ONE document, plus a
    second `secondary-summary` at a different document. One pair shares a source and earns
    nothing; another pair differs in both class and source and is honest corroboration, so
    the point is due. This discriminates against the two over-merging shapes a reader of
    behavior 2 could plausibly build -- refusing the point whenever ANY pair shares a
    source, and comparing only CONSECUTIVE citations -- both of which would WITHHOLD an
    honest point, the failure the spec's Out of Scope section names by name.
    """
    hidden = _gap((("peer-reviewed", DOC),
                   ("secondary-summary", DOC),
                   ("secondary-summary", OTHER_DOC)))
    assert confidence(hidden) == min(5, LADDER["peer-reviewed"] + 1)


def test_the_verdict_does_not_depend_on_citation_order():
    """Every ordering of the record above scores the same; a consecutive-pair scan does not."""
    cites = (("peer-reviewed", DOC),
             ("secondary-summary", DOC),
             ("secondary-summary", OTHER_DOC))
    scored = {confidence(_gap(order)) for order in itertools.permutations(cites)}
    assert scored == {min(5, LADDER["peer-reviewed"] + 1)}, scored


def test_three_sources_add_at_most_one_point():
    """Three distinct classes at three distinct sources: strongest + 1, never + 2."""
    three = _gap((("practitioner-report", "https://example.invalid/a"),
                  ("survey-aggregate", "https://example.invalid/b"),
                  ("secondary-summary", "https://example.invalid/c")))
    assert confidence(three) == LADDER["practitioner-report"] + 1
    assert confidence(three) < LADDER["practitioner-report"] + 2


def test_the_result_is_capped_at_five():
    strongest_class = max(LADDER, key=lambda c: LADDER[c])
    capped = _gap(((strongest_class, "https://example.invalid/a"),
                   ("peer-reviewed", "https://example.invalid/b"),
                   ("secondary-summary", "https://example.invalid/c")))
    assert LADDER[strongest_class] == 5
    assert confidence(capped) == 5


# ------------------------------------------------------- behaviors 1-6, swept against a spec oracle

def test_the_scorer_agrees_with_the_spec_rule_over_a_swept_matrix():
    """Every ordered class pair x every same/different source spelling.

    A handful of examples can agree with a scorer that keys on something close to the
    rule; this sweeps the whole 2-citation space the rule is defined over.
    """
    checked = 0
    for first, second in itertools.product(LADDER_ORDER, repeat=2):
        for locator in SAME_SOURCE_SPELLINGS + (OTHER_DOC,):
            record = _gap(((first, DOC), (second, locator)))
            assert confidence(record) == _spec_confidence(record), (first, second, locator)
            checked += 1
    assert checked == len(LADDER_ORDER) ** 2 * 4, checked


# --------------------------------------------------------------------------- behavior 7

def test_promotion_options_is_unchanged_for_every_live_record():
    """Behavior 7, via the PRE-CHANGE oracle -- the claim is that nothing moved."""
    for gap in REGISTER:
        assert promotion_options(gap) == _pre_change_promotion_options(gap, 2), gap.id


@pytest.mark.parametrize("floor", tuple(range(6)))
def test_promotion_options_is_unchanged_at_every_floor(floor):
    for gap in REGISTER:
        assert promotion_options(gap, floor) == _pre_change_promotion_options(gap, floor), (
            gap.id, floor)


def test_the_simulated_citation_counts_as_a_distinct_source():
    """The probe must not collide with a real citation whose SOURCE KEY is empty.

    AMENDED IN ITERATION 24, which retired this test's original premise rather than its
    property. When this file was written, a sole citation with `locator=""` was
    schema-valid; iteration 24 gave `Evidence.locator` the non-empty validator its twin
    `quote` already had, so that record can no longer be loaded at all and the first
    assertion below now pins the refusal instead of building on it.

    The property is untouched and still reachable, because a collision needs an empty
    SOURCE KEY and not an empty string: `_key("#s1")` is `""` under behavior 3's own
    fragment rule, and `"#s1"` is schema-valid. If the probe were keyed on an empty
    locator too, the two would read as ONE source, corroboration would be refused, and
    the prescription would jump a whole rung -- from the cheapest class to a weight-5
    one -- for a record that in truth needs only a second kind of evidence. That is a
    wrong answer published in the below-floor `Needs` column.
    """
    with pytest.raises(ValueError):  # pydantic's ValidationError IS a ValueError
        _gap((("peer-reviewed", ""),))
    assert _key("#s1") == "", "control: the empty-source-key case must still be reachable"
    empty_key = _gap((("peer-reviewed", "#s1"),))
    assert promotion_options(empty_key, 5) == _pre_change_promotion_options(empty_key, 5)
    assert promotion_options(empty_key, 5) == ("secondary-summary",)


def test_promotion_options_never_raises_on_a_live_record():
    for gap in REGISTER:
        for floor in range(6):
            assert isinstance(promotion_options(gap, floor), tuple), (gap.id, floor)


# --------------------------------------------------------------------------- behavior 8

def test_no_live_confidence_moved():
    """The old rule and the new rule score every live record identically."""
    for gap in REGISTER:
        assert confidence(gap) == _pre_change_confidence(gap), gap.id


def test_no_live_record_cites_two_classes_at_one_source():
    """The structural precondition behind the test above, asserted directly.

    States the property in the register's own terms rather than as a coincidence between
    two oracles: no live record has a citation PAIR that differs in class while resolving
    to one source. This is what makes the change a zero-byte change today.
    """
    for gap in REGISTER:
        real = [c for c in gap.evidence if _weight(c) > 0]
        for a, b in itertools.combinations(real, 2):
            assert not (a.source_class != b.source_class
                        and _key(a.locator) == _key(b.locator)), (gap.id, a.locator)


#: Two live ids and the top-ranked one, DERIVED rather than pinned. The spec names
#: GAP-016, GAP-015 and GAP-003; spelling those literals would red this file the day the
#: unattended research pass renumbers or retires one, which is the landmine acceptance
#: criterion 4 forbids. What behavior 8 actually claims is a property of the SURFACES.
FIRST_ID = REGISTER[0].id
LAST_ID = REGISTER[-1].id

SURFACES = (
    ["report"],
    #: `report --floor N` is the ONLY surface that prints the below-floor `Needs` column,
    #: i.e. the only place `promotion_options` output reaches a reader -- and that helper is
    #: what this change couples to, because the probe citation it appends now needs a
    #: locator. A surface list chosen for prominence rather than for the COUPLED helper
    #: would pass while the coupling was broken, so both floors that populate the column
    #: are exercised here.
    ["report", "--floor", "4"],
    ["report", "--floor", "5"],
    ["list"],
    ["list", "--json"],
    ["show", FIRST_ID],
    ["show", LAST_ID],
    ["prd"],
    ["prd", "--gap", FIRST_ID],
)


@pytest.mark.parametrize("argv", SURFACES, ids=lambda a: " ".join(a))
def test_each_named_surface_is_byte_stable_clean_and_ends_in_one_newline(argv):
    first_code, first_out, first_err = _run(list(argv))
    second_code, second_out, second_err = _run(list(argv))
    assert first_code == 0 == second_code, (first_code, first_err)
    assert first_err == "" == second_err
    assert first_out == second_out, argv
    assert first_out.endswith("\n") and not first_out.endswith("\n\n")


def test_the_json_surface_publishes_the_scored_confidence():
    """Ties the rendered surface to the invariance claim above, without a live literal."""
    code, out, _ = _run(["list", "--json"])
    assert code == 0
    document = json.loads(out)
    rows = document["records"]
    assert len(rows) == len(REGISTER) > 0
    by_id = {gap.id: gap for gap in REGISTER}
    for row in rows:
        gap = by_id[row["gap_id"]]
        assert row["confidence"] == confidence(gap) == _pre_change_confidence(gap), row["gap_id"]


# --------------------------------------------------------------------------- behavior 9

def test_confidence_is_pure_across_repeated_calls():
    record = _gap((("peer-reviewed", DOC), ("secondary-summary", OTHER_DOC)))
    assert len({confidence(record) for _ in range(50)}) == 1


def test_confidence_is_total_for_a_citation_carrying_no_locator():
    """Behavior 9: a stand-in with only a `source_class` must not raise.

    `promotion_options` appends exactly such a stand-in internally, so a scorer that
    reached for `.locator` unguardedly would break the below-floor `Needs` column rather
    than any score. The spec fixes only totality, not the value, so the value is asserted
    to be in range rather than pinned.
    """
    class _ClassOnlyStandIn:
        def __init__(self, source_class: str) -> None:
            self.source_class = source_class

    duck = types.SimpleNamespace(evidence=[_ClassOnlyStandIn("peer-reviewed"),
                                           _ClassOnlyStandIn("secondary-summary")])
    scored = confidence(duck)
    assert isinstance(scored, int)
    assert 0 <= scored <= 5
    assert confidence(duck) == scored


def test_confidence_is_total_over_every_live_record():
    for gap in REGISTER:
        scored = confidence(gap)
        assert isinstance(scored, int) and 0 <= scored <= 5, gap.id


#: `| ID | Priority | Confidence | Title | Strongest source | Needs |` -- the Needs cell
#: reads `weight >= N: class[, class]`, which is `promotion_options` rendered.
_NEEDS_CELL = re.compile(r"^weight >= (\d+): (.+)$")


@pytest.mark.parametrize("floor", (4, 5))
def test_the_needs_column_a_reader_sees_is_promotion_options_rendered(floor):
    """Behavior 7 on the SURFACE, with no live literal: the cell must equal the helper.

    `report --floor N` is the only place the prescription reaches a reader. Rather than
    pinning a class name for a live id (the iteration-09 landmine), every below-floor row
    is parsed and its cell compared against `promotion_options(gap, floor)` and the
    observed ladder. The row count is asserted non-zero first, because a green result over
    zero below-floor rows is the vacuous pass that reads as health.
    """
    code, out, err = _run(["report", "--floor", str(floor)])
    assert code == 0 and err == ""
    section = out.split("## Below confidence floor", 1)
    assert len(section) == 2, "report published no below-floor section"
    by_id = {gap.id: gap for gap in REGISTER}

    checked = 0
    for line in section[1].splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6 or cells[0] not in by_id:
            continue
        gap = by_id[cells[0]]
        expected = promotion_options(gap, floor)
        match = _NEEDS_CELL.match(cells[5])
        if not expected:
            assert not match, (gap.id, cells[5])
            checked += 1
            continue
        assert match, (gap.id, cells[5])
        named = tuple(part.strip() for part in match.group(2).split(","))
        assert named == expected, (gap.id, named, expected)
        assert int(match.group(1)) == LADDER[expected[0]], (gap.id, match.group(1))
        checked += 1
    assert checked > 0, f"no below-floor row parsed at floor {floor}; the check is vacuous"
