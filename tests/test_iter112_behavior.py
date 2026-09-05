"""Iteration 112 behaviors: a content rule whose LOCATIONS the caller will discard stops
reading files at its first hit, and every location-publishing direction is untouched.

`run_check` reads `applies_when` only through `RuleHit.__bool__`, and the `not` combinator
returns `RuleHit(not hit.matched, [], ...)`, so a `content_matches` node in either position
computes a location list nobody can ever read. This iteration teaches `evaluate` when it is
in that position -- one keyword-only `boolean_only` flag -- and under it the file loop leaves
at its first hit, exactly as iteration 94's guarded `break` did for `content_absent`.

The whole risk of the bite is PROPAGATION: the flag must reach the two sites that provably
discard locations and NO others, because this module has already produced a fail-open by
crediting a signal from the wrong place (CHK-009 credited a mitigation found in a TEST file).
So every skip below is paired with a control asserting the publishing direction still reads
its whole domain and still names every match.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/`, the engineer's
or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every expectation comes from
`pm.md`'s Expected Behaviors; every shape claim was MEASURED by calling the public interface
(`checks.evaluate`, `checks.run_check`, `checks._read`, `checks.RuleHit`, `checks.Verdict`)
over fixtures this file writes under pytest's `tmp_path`.

Structural notes, so this file cannot lie later:

* **THE FLAG'S PROPAGATION TABLE IS STATED AS TESTS, not as prose.** The acceptance criteria
  ask that exactly two sites pass `boolean_only=True` -- the `not` branch's inner rule and
  `run_check`'s `applies_when` -- that `any_of` / `all_of` pass the caller's value through,
  and that `present_when` / `mitigated_when` pass nothing. Read as a table:

      site                     | flag       | asserted by
      -------------------------|------------|--------------------------------------------
      not -> inner rule        | True       | b1, b2, b3, b7, b8
      run_check applies_when   | True       | b5
      any_of / all_of -> subs  | pass-thru  | b7 (True under `not`, False at top level)
      run_check present_when   | nothing    | b6a
      run_check mitigated_when | nothing    | b6b
      top-level evaluate call  | False      | b4

* **The read count is proven DISCRIMINATING by paired controls, not by hope.** One probe
  (`_reads`) is applied to fixtures that differ ONLY in WHERE the marker sits, and it must
  report a DIFFERENT count each time: 1 read for a first-file hit, 2 for a second-file hit,
  3 for no hit at all and 3 for every publishing direction. A probe that reported "1" because
  it cannot see reads would fail b3/b4/b6; a loop that never stops early would fail b1/b2.
  Neither side can pass by accident.
* **Every "not matched" fixture asserts its own PREMISE.** The same tree is first driven with
  a bare `content_matches` rule, so a `matched is False` on the `not`-wrapped rule is
  attributable to a real hit rather than to a typo in the marker.
* **`truncated_files` is paired with an UNCUT control over the same fixture** (b8), with
  `MAX_SCAN_FILES` as the only variable that moves, so `truncated_files == 3` cannot pass
  because the field happens to be non-zero for some other reason.
* **No wall-clock and no global speedup is asserted anywhere** (acceptance criterion): the
  win is concentrated in the live nodes that actually hit, so a clock assertion would be
  flaky. Read COUNTS are the deterministic observable that stands in for the saving.
* **No literal count from the live register or the live repo is written down**, so a research
  pass that grows the register cannot red this file -- the iteration-09 landmine.
* **No absolute machine path, employer or personal identifier, or real name appears here.**
  The repo root is derived from `__file__`; every fixture lives under pytest's `tmp_path`.
* **Nothing under `gaps/`, `src/` or `PRODUCT.md` is edited to make an assertion true.**
"""

from __future__ import annotations

import inspect
import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import Verdict, evaluate, run_check

#: Repo root, derived from this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The marker carries the iteration number so no other fixture in the suite can collide.
MARK = "GAPMARK112"
GLOBS = ["**/*.py"]
CLEAN = "a clean line\n"

#: A domain of files that DO NOT EXIST in any fixture: a rule over it decides while reading
#: no file at all, which is what makes a read count attributable to the rule under test.
NO_SUCH = ["**/*.rs"]


# --- helpers -----------------------------------------------------------------------------

def _materialise(tmp_path: pathlib.Path, tree: dict[str, str], name: str = "target") -> pathlib.Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _three(tmp_path: pathlib.Path, marked: tuple[str, ...] = (), name: str = "target") -> pathlib.Path:
    """`f01.py`, `f02.py`, `f03.py`; every name in `marked` carries MARK on line 2.

    The names sort in creation order, so "the FIRST file of the domain" and "the SECOND file
    of the domain" are observable facts about the fixture rather than assumptions.
    """
    tree = {f"f{i:02d}.py": CLEAN for i in (1, 2, 3)}
    for rel in marked:
        assert rel in tree, "fixture bug: the marked name is not in the domain"
        tree[rel] = CLEAN + MARK + " here\n"
    return _materialise(tmp_path, tree, name)


def _rule(pattern: str = MARK, globs=GLOBS, **extra) -> dict:
    """The spec's "the rule": a `content_matches` node over the fixture's whole domain."""
    return {"kind": "content_matches", "globs": list(globs), "pattern": pattern, **extra}


def _absent(pattern: str = MARK, globs=GLOBS) -> dict:
    return {"kind": "content_absent", "globs": list(globs), "pattern": pattern}


def _not(rule: dict) -> dict:
    return {"kind": "not", "rule": rule}


def _reads(monkeypatch, call):
    """Return `(result, [basenames read])` -- the module-level `_read` seam, counted.

    The seam is patched on the MODULE, so every recursive combinator call is caught too: a
    recursive call resolves the global at call time. This is the same probe
    `tests/test_iter94_behavior.py::_reads_during` committed for bite 1.
    """
    seen: list[str] = []
    real = checks._read

    def recording(path: pathlib.Path):
        seen.append(pathlib.Path(path).name)
        return real(path)

    monkeypatch.setattr(checks, "_read", recording)
    try:
        result = call()
    finally:
        monkeypatch.setattr(checks, "_read", real)
    return result, seen


def _premise_marker_is_findable(target: pathlib.Path, where: tuple[str, ...]) -> None:
    """Drive the SAME tree with a bare `content_matches`, so a later "not matched" is
    attributable to a real hit rather than to a typo in the marker."""
    probe = evaluate(_rule(), target)
    assert probe.matched is True, (
        f"premise failed: {MARK} is not findable in {target.name} at all, so a "
        "'the boolean-only rule did not match' result would prove nothing")
    assert probe.locations == [f"{w}:2" for w in where], \
        f"premise failed: expected matches at {list(where)}, got {probe.locations}"


def _premise_marker_is_absent(target: pathlib.Path) -> None:
    probe = evaluate(_rule(), target)
    assert probe.matched is False, \
        f"premise failed: this fixture must carry {MARK} nowhere, got {probe.locations}"


# --- acceptance criterion: the signature ---------------------------------------------------

def test_ac_evaluate_gains_exactly_one_new_keyword_only_parameter():
    """`boolean_only: bool = False`, KEYWORD-ONLY so it can never be confused with the
    positionally-passed `exclude_tests` in a recursive call."""
    params = inspect.signature(checks.evaluate).parameters
    assert "boolean_only" in params, \
        f"`evaluate` has no `boolean_only` parameter; it takes {list(params)}"
    flag = params["boolean_only"]
    assert flag.kind is inspect.Parameter.KEYWORD_ONLY, (
        "a positional flag can be passed by accident where `exclude_tests` is expected, "
        f"which is the fail-open this criterion exists to stop; got {flag.kind}")
    assert flag.default is False, f"the flag must default OFF, got {flag.default!r}"
    keyword_only = [n for n, p in params.items()
                    if p.kind is inspect.Parameter.KEYWORD_ONLY]
    assert keyword_only == ["boolean_only"], \
        f"exactly one new keyword-only parameter was specced, got {keyword_only}"
    assert params["exclude_tests"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, \
        "`exclude_tests` keeps its positional call convention"
    assert list(params)[:3] == ["rule", "target", "exclude_tests"], \
        f"the pre-existing parameters and their order are untouched, got {list(params)}"


# --- behavior 1: a boolean-only first-file hit reads exactly one file ----------------------

def test_b1_a_boolean_only_first_file_hit_reads_exactly_one_file(tmp_path, monkeypatch):
    target = _three(tmp_path, ("f01.py",))
    _premise_marker_is_findable(target, ("f01.py",))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert seen == ["f01.py"], (
        "under `not` the location list is discarded, so once the first file has matched "
        f"every later read is work whose result is thrown away -- reads were {seen}")
    assert hit.matched is False, "`not` inverts a rule that DID match"
    assert hit.locations == [], "`not` publishes no locations"
    assert hit.truncated_files == 0, "a three-file domain under the cap is not truncated"


def test_b1_the_returned_hit_is_a_rulehit_with_the_documented_shape(tmp_path, monkeypatch):
    """The early exit must return the same TYPE with the same three fields, not a shortcut."""
    hit, _ = _reads(monkeypatch,
                    lambda: evaluate(_not(_rule()), _three(tmp_path, ("f01.py",))))
    assert isinstance(hit, checks.RuleHit)
    assert (hit.matched, hit.locations, hit.truncated_files) == (False, [], 0)


# --- behavior 2: it stops EXACTLY at the deciding file ------------------------------------

def test_b2_it_stops_exactly_at_the_deciding_file(tmp_path, monkeypatch):
    target = _three(tmp_path, ("f02.py",))
    _premise_marker_is_findable(target, ("f02.py",))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert seen == ["f01.py", "f02.py"], (
        "the loop must read up to and including the deciding file and no further, in "
        f"domain order -- reads were {seen}")
    assert "f03.py" not in seen, f"the tail after the decision must go unread, got {seen}"
    assert hit.matched is False


# --- behavior 3: with no hit there is nothing to decide, so nothing is skipped ------------

def test_b3_no_hit_anywhere_reads_every_file(tmp_path, monkeypatch):
    target = _three(tmp_path)
    _premise_marker_is_absent(target)
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "an UNDECIDED search must read its whole domain: leaving early here would answer "
        f"'no match' over an unsearched tail -- reads were {seen}")
    assert hit.matched is True, "nothing matched, so `not` holds"
    assert hit.locations == []
    assert hit.truncated_files == 0


# --- behavior 4: the location-publishing direction is byte-for-byte untouched --------------

def test_b4_default_arguments_read_the_whole_domain_and_publish_every_match(tmp_path, monkeypatch):
    target = _three(tmp_path, ("f01.py", "f02.py", "f03.py"))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_rule(), target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "a top-level `content_matches` publishes its locations, so the flag defaults OFF "
        f"and the whole domain is read -- reads were {seen}")
    assert len(seen) == 3, f"no file may be read twice, got {seen}"
    assert hit.matched is True
    assert hit.locations == ["f01.py:2", "f02.py:2", "f03.py:2"], (
        "every match must still be named: a location list shortened by the early exit is "
        f"the regression this control exists to catch -- got {hit.locations}")
    assert hit.truncated_files == 0


def test_b4_the_code_before_test_ranking_is_unchanged(tmp_path, monkeypatch):
    """The spec's "ranked code-before-test", on a fixture where ALPHABETICAL and RANKED order
    DISAGREE -- the test file sorts FIRST, so an assertion about the observed order is an
    assertion about RANKING and not about sorting."""
    tree = {"atest/test_x.py": CLEAN + MARK + "\n",
            "zcode/b.py": CLEAN + MARK + "\n",
            "zcode/c.py": CLEAN + MARK + "\n"}
    target = _materialise(tmp_path, tree, name="ranked")
    assert sorted(tree) == ["atest/test_x.py", "zcode/b.py", "zcode/c.py"], \
        "premise: plain path order would put the TEST file first"
    hit, seen = _reads(monkeypatch, lambda: evaluate(_rule(), target))
    assert sorted(seen) == ["b.py", "c.py", "test_x.py"], f"whole domain read, got {seen}"
    assert hit.locations == ["zcode/b.py:2", "zcode/c.py:2", "atest/test_x.py:2"], (
        "code locators must still rank ahead of test locators, and every match must still "
        f"be named -- got {hit.locations}")


# --- behavior 5: `applies_when` is a boolean-only site ------------------------------------

def _check(**extra) -> dict:
    check = {"id": "CHK-1120"}
    check.update(extra)
    return check


def test_b5_applies_when_is_a_boolean_only_site(tmp_path, monkeypatch):
    """`run_check` reads `applies_when` only through `RuleHit.__bool__`, so a hit in its
    first file settles it. The verdict and reason must not move, and the ORACLE for "what
    HEAD returns" is a reference check whose `applies_when` reads no file at all and is
    equally true -- the same code path with the variable under test removed."""
    target = _three(tmp_path, ("f01.py",))
    _premise_marker_is_findable(target, ("f01.py",))
    present = {"kind": "file_absent", "globs": NO_SUCH}

    subject, seen = _reads(monkeypatch, lambda: run_check(
        _check(applies_when=_rule(), present_when=present), target))
    assert seen == ["f01.py"], (
        "the applies_when boolean was settled by the first file and its locations are "
        f"unreachable, so the rest of the domain is wasted work -- reads were {seen}")

    reference, ref_seen = _reads(monkeypatch, lambda: run_check(
        _check(applies_when={"kind": "file_exists", "globs": GLOBS}, present_when=present),
        target))
    assert ref_seen == [], "premise: the reference precondition decides without reading a file"
    assert bool(evaluate({"kind": "file_exists", "globs": GLOBS}, target)) is True, \
        "premise: the reference precondition is TRUE, like the subject's"
    assert (subject.verdict, subject.reason, subject.locations, subject.question) == \
           (reference.verdict, reference.reason, reference.locations, reference.question), (
        "a precondition evaluated boolean-only must produce the SAME CheckOutcome as an "
        f"equally-true precondition that reads nothing; got {subject} vs {reference}")
    assert subject.verdict is Verdict.PRESENT, \
        f"premise: this check verdicts rather than degrading, got {subject.verdict}"


def test_b5_control_a_precondition_that_does_not_hold_still_reads_its_whole_domain(
        tmp_path, monkeypatch):
    """The two-sided control for behavior 5: an UNDECIDED precondition is not shortened, and
    it still reaches NOT_APPLICABLE."""
    target = _three(tmp_path)
    _premise_marker_is_absent(target)
    out, seen = _reads(monkeypatch, lambda: run_check(
        _check(applies_when=_rule(), present_when={"kind": "file_absent", "globs": NO_SUCH}),
        target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "a precondition that has not yet matched must search its whole domain, or a check "
        f"would be skipped over an unread tail -- reads were {seen}")
    assert out.verdict is Verdict.NOT_APPLICABLE, \
        f"the precondition does not hold, got {out.verdict}"


# --- behavior 6: the two location-publishing sites are NOT boolean-only -------------------

def test_b6a_present_when_reads_its_whole_domain_and_publishes_every_location(
        tmp_path, monkeypatch):
    target = _three(tmp_path, ("f01.py", "f02.py", "f03.py"))
    out, seen = _reads(monkeypatch, lambda: run_check(_check(present_when=_rule()), target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "`present_when` locations are what the finding POINTS AT, so the flag must not "
        f"reach it -- reads were {seen}")
    assert out.verdict is Verdict.PRESENT
    assert out.locations == ["f01.py:2", "f02.py:2", "f03.py:2"], (
        "a PRESENT finding that named only its first hit would silently narrow every "
        f"scan report -- got {out.locations}")


def test_b6b_mitigated_when_reads_its_whole_domain_and_publishes_every_location(
        tmp_path, monkeypatch):
    target = _three(tmp_path, ("f01.py", "f02.py", "f03.py"))
    cannot_match = {"kind": "file_exists", "globs": NO_SUCH}
    assert bool(evaluate(cannot_match, target)) is False, \
        "premise: the present_when signature cannot match this fixture"
    out, seen = _reads(monkeypatch, lambda: run_check(
        _check(present_when=cannot_match, mitigated_when=_rule()), target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "ABSENT is the one verdict that CLAIMS SAFETY, and its locations are the evidence "
        f"for that claim, so the flag must not reach `mitigated_when` -- reads were {seen}")
    assert out.verdict is Verdict.ABSENT
    assert out.locations == ["f01.py:2", "f02.py:2", "f03.py:2"], (
        f"the mitigation evidence must be named in full, got {out.locations}")


# --- behavior 7: the flag propagates through the composite combinators and only there -----

@pytest.mark.parametrize("kind", ["any_of", "all_of"])
def test_b7_a_composite_under_not_passes_the_flag_through(tmp_path, monkeypatch, kind):
    target = _three(tmp_path, ("f01.py",))
    _premise_marker_is_findable(target, ("f01.py",))
    hit, seen = _reads(monkeypatch,
                       lambda: evaluate(_not({"kind": kind, "rules": [_rule()]}), target))
    assert seen == ["f01.py"], (
        f"`{kind}` must hand the caller's flag down to its sub-rules, or wrapping a rule "
        f"in a one-element combinator would silently undo the saving -- reads were {seen}")
    assert hit.matched is False, f"premise: the inner {kind} DID match, so `not` inverts it"
    assert hit.locations == []


@pytest.mark.parametrize("kind", ["any_of", "all_of"])
def test_b7_control_the_same_composite_at_top_level_publishes_everything(
        tmp_path, monkeypatch, kind):
    """The pass-through is only correct if the DEFAULT still reads the whole domain: the same
    combinator shape, at top level, with default arguments."""
    target = _three(tmp_path, ("f01.py", "f02.py", "f03.py"))
    hit, seen = _reads(monkeypatch,
                       lambda: evaluate({"kind": kind, "rules": [_rule()]}, target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        f"at top level `{kind}` publishes its sub-rule's locations, so the flag is OFF and "
        f"the whole domain is read -- reads were {seen}")
    assert hit.matched is True
    assert hit.locations == ["f01.py:2", "f02.py:2", "f03.py:2"], \
        f"got {hit.locations}"
    assert hit.truncated_files == 0


def test_b7_any_of_does_not_gain_an_early_return_on_first_match(tmp_path, monkeypatch):
    """OUT OF SCOPE, asserted so it stays out: `any_of` takes `max` over the
    `truncated_files` of the sub-rules it actually evaluated, so skipping a later sub-rule
    could launder a cut domain into an answer that claims safety. Under the flag the FIRST
    sub-rule matches and the SECOND is over a domain the cap cut; its truncation must still
    be reported."""
    target = _three(tmp_path, ("f01.py",))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    second = _rule(pattern="NEVERMARK112")
    hit, seen = _reads(monkeypatch, lambda: evaluate(
        _not({"kind": "any_of", "rules": [_rule(), second]}), target))
    assert hit.matched is False, "premise: the first sub-rule matched, so `any_of` is true"
    assert hit.truncated_files == 3, (
        "`any_of` must still evaluate the sub-rule whose domain was cut and report the "
        f"total that domain held; got {hit.truncated_files}")
    assert seen[0] == "f01.py", f"the deciding sub-rule still exits at its hit, got {seen}"


# --- behavior 8: the early exit moves neither completeness nor the other kinds -------------

def test_b8_an_early_exit_over_a_cut_domain_still_reports_the_total_it_held(
        tmp_path, monkeypatch):
    target = _three(tmp_path, ("f01.py",))
    _premise_marker_is_findable(target, ("f01.py",))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert seen == ["f01.py"], f"the cut domain is still exited at the hit, reads were {seen}"
    assert hit.truncated_files == 3, (
        "`truncated` stays derived from the domain size BEFORE the loop, so a cut domain is "
        f"never laundered into a clean-looking answer; got {hit.truncated_files}")
    assert hit.matched is False


def test_b8_control_the_same_fixture_uncut_reports_no_truncation(tmp_path, monkeypatch):
    """`MAX_SCAN_FILES` is the ONLY variable that moves between this and the test above."""
    target = _three(tmp_path, ("f01.py",))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert (hit.matched, hit.locations, hit.truncated_files) == (False, [], 0)
    assert seen == ["f01.py"]


@pytest.mark.parametrize("marked", [(), ("f01.py",), ("f01.py", "f02.py", "f03.py")])
def test_b8_the_other_rule_kinds_are_indifferent_to_the_flag(tmp_path, monkeypatch, marked):
    """`content_absent`, `file_exists` and `file_absent` must return a `RuleHit` equal in all
    three fields with the flag on and off -- `content_absent` because iteration 94 already
    stops it at its first hit unconditionally, the two file kinds because they read nothing.

    Driven over three fixtures (no hit, one hit, all hit) so the equality is not vacuous.
    """
    target = _three(tmp_path, marked, name=f"t{len(marked)}")
    kinds = [_absent(),
             {"kind": "file_exists", "globs": GLOBS},
             {"kind": "file_absent", "globs": GLOBS},
             {"kind": "file_exists", "globs": NO_SUCH},
             {"kind": "file_absent", "globs": NO_SUCH}]
    for rule in kinds:
        off = evaluate(rule, target)
        on = evaluate(rule, target, boolean_only=True)
        assert (on.matched, on.locations, on.truncated_files) == \
               (off.matched, off.locations, off.truncated_files), (
            f"{rule['kind']} over globs {rule['globs']} moved under the flag: "
            f"{on} vs {off}")
    # Anti-vacuity: at least one of these kinds actually decided something on this fixture.
    assert evaluate(_absent(), target).matched is (marked == ()), \
        "premise: content_absent tracks whether this fixture carries the marker"


def test_b8_content_absent_still_reads_only_up_to_its_deciding_file(tmp_path, monkeypatch):
    """Iteration 94's bite, re-asserted from this file so widening the guard cannot lose it:
    `content_absent` stops at its first hit with the flag OFF."""
    target = _three(tmp_path, ("f02.py",))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_absent(), target))
    assert seen == ["f01.py", "f02.py"], f"reads were {seen}"
    assert hit.matched is False and hit.locations == []


# --- propagation, composed: the flag is safe wherever a `not` sits -------------------------

def test_b7_a_not_inside_present_when_is_still_boolean_only(tmp_path, monkeypatch):
    """The propagation table has to compose, not just hold at depth one.

    `present_when` passes NO flag (b6a), but the rule it passes is a `not`, and a `not`
    publishes no locations of its own -- so the inner content rule is boolean-only again and
    may stop at its first hit. This is the case that would break if the flag were keyed on
    the CALL SITE instead of on "will my locations be discarded": it is a publishing site
    holding a non-publishing rule.
    """
    target = _three(tmp_path, ("f01.py",))
    _premise_marker_is_findable(target, ("f01.py",))
    out, seen = _reads(monkeypatch,
                       lambda: run_check(_check(present_when=_not(_rule())), target))
    assert seen == ["f01.py"], (
        "`not` discards its inner rule's locations wherever it sits, so the inner content "
        f"rule is decided by the first file -- reads were {seen}")
    assert out.locations == [], "a `not` present_when has no locations to publish"
    assert out.verdict is not Verdict.PRESENT, \
        f"premise: the inner rule matched, so the negated signature is NOT found; got {out}"


def test_b7_a_doubly_negated_rule_is_still_boolean_only(tmp_path, monkeypatch):
    """`not(not(rule))` re-asserts the original boolean and still discards locations, so the
    flag must survive both hops rather than being toggled by them."""
    target = _three(tmp_path, ("f01.py",))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_not(_rule())), target))
    assert seen == ["f01.py"], f"reads were {seen}"
    assert hit.matched is True, "double negation restores the inner boolean"
    assert hit.locations == [], "the locations are still discarded"


def test_out_of_scope_exclude_tests_still_filters_under_the_flag(tmp_path, monkeypatch):
    """`exclude_tests` and its propagation are OUT OF SCOPE, asserted so they stay out.

    The marker lives ONLY in a test path. With `exclude_tests` the rule must not match, so
    the `not` wrapper must hold -- boolean-only or not. The two directions are asserted over
    the same fixture so the filter, not the fixture, is what moves the answer.
    """
    tree = {"atest/test_x.py": CLEAN + MARK + "\n", "zcode/b.py": CLEAN, "zcode/c.py": CLEAN}
    target = _materialise(tmp_path, tree, name="testonly")
    assert evaluate(_rule(), target).locations == ["atest/test_x.py:2"], \
        "premise: the marker is findable, and only in a test path"
    included = evaluate(_not(_rule()), target)
    excluded = evaluate(_not(_rule()), target, True)
    assert included.matched is False, "unfiltered, the inner rule matches in the test file"
    assert excluded.matched is True, (
        "with `exclude_tests` the only hit is filtered away, so the inner rule does not "
        "match and `not` holds -- an early exit must not credit an excluded file")
    assert evaluate(_rule(), target, True).matched is False, \
        "and the same filter holds in the publishing direction"


# --- extension (tester-retry round): the invariant the flag must never move ----------------

@pytest.mark.parametrize("marked", [(), ("f01.py",), ("f02.py",), ("f01.py", "f02.py", "f03.py")])
def test_b8_the_boolean_and_the_truncation_never_move_under_the_flag(
        tmp_path, monkeypatch, marked):
    """THE safety property of the whole bite, asserted on the ONE kind whose loop changed.

    The parametrized `test_b8_the_other_rule_kinds_are_indifferent_to_the_flag` above pins
    field-equality for `content_absent`, `file_exists` and `file_absent` -- the kinds that do
    NOT change. It cannot make the same claim for `content_matches`, because under the flag
    that kind is ALLOWED to shorten its `locations`. What it is never allowed to move is the
    answer: `matched` and `truncated_files` must be identical with the flag on and off, over a
    fixture set that spans no hit, a first-file hit, a mid-domain hit and an all-files hit.
    Without this, an early exit that mis-decided the boolean would be caught only indirectly
    (via `not`) and only on the fixtures behaviors 1-3 happen to use.
    """
    target = _three(tmp_path, marked, name=f"inv{len(marked)}{''.join(marked)[1:3]}")
    off = evaluate(_rule(), target)
    on = evaluate(_rule(), target, boolean_only=True)
    assert on.matched is off.matched, (
        "the flag is a permission to stop READING, never a permission to change the ANSWER; "
        f"marked={list(marked)} gave matched {on.matched} on vs {off.matched} off")
    assert on.truncated_files == off.truncated_files, (
        "`truncated` stays derived from the domain size BEFORE the loop, so it cannot depend "
        f"on how early the loop left; got {on.truncated_files} on vs {off.truncated_files} off")
    assert off.matched is (marked != ()), \
        "premise: this fixture set really does span both answers, so the equality is not vacuous"


def test_b1_a_last_file_hit_reads_the_WHOLE_domain(tmp_path, monkeypatch):
    """The boundary that proves the exit is at the HIT and not at a fixed file count.

    Behaviors 1 and 2 pin 1 read for a first-file hit and 2 for a second-file hit. A loop that
    stopped after a fixed number of files would satisfy both and still be wrong here: the
    deciding file is the LAST one, so the whole domain must be read.
    """
    target = _three(tmp_path, ("f03.py",))
    _premise_marker_is_findable(target, ("f03.py",))
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "the exit is at the deciding file, and here that is the last one -- reads were "
        f"{seen}")
    assert hit.matched is False, "the last file matched, so `not` inverts it"
    assert hit.locations == []


def test_b2_the_applies_when_site_also_stops_exactly_at_its_deciding_file(
        tmp_path, monkeypatch):
    """Behavior 5 pins the `applies_when` site on a FIRST-file hit, where "reads exactly one
    file" is also what a broken loop that stops after one file would report. Moving the marker
    to the second file separates the two: this site must read exactly two."""
    target = _three(tmp_path, ("f02.py",))
    _premise_marker_is_findable(target, ("f02.py",))
    out, seen = _reads(monkeypatch, lambda: run_check(
        _check(applies_when=_rule(), present_when={"kind": "file_absent", "globs": NO_SUCH}),
        target))
    assert seen == ["f01.py", "f02.py"], (
        "the precondition is settled by the second file and no later read can change it -- "
        f"reads were {seen}")
    assert out.verdict is Verdict.PRESENT, \
        f"premise: the precondition held, so the check ran; got {out.verdict}"


def test_b7_a_composite_inside_applies_when_is_still_boolean_only(tmp_path, monkeypatch):
    """The propagation table composed at the SECOND True site: `run_check`'s `applies_when`
    passes True, and an `any_of` in that position passes it through to its sub-rule."""
    target = _three(tmp_path, ("f01.py",))
    _premise_marker_is_findable(target, ("f01.py",))
    out, seen = _reads(monkeypatch, lambda: run_check(
        _check(applies_when={"kind": "any_of", "rules": [_rule()]},
               present_when={"kind": "file_absent", "globs": NO_SUCH}),
        target))
    assert seen == ["f01.py"], (
        "wrapping a precondition in a one-element combinator must not undo the saving -- "
        f"reads were {seen}")
    assert out.verdict is Verdict.PRESENT, f"premise: the precondition held; got {out.verdict}"


def test_b8_a_hit_beyond_the_cap_is_not_credited_and_truncation_is_still_reported(
        tmp_path, monkeypatch):
    """The cap and the early exit compose without laundering either one.

    The marker sits in `f03.py` and the cap cuts the domain to two files, so the rule reads
    its whole (cut) domain, does NOT find the marker, and must report the total the domain
    held. An implementation that credited an unread file, or that dropped `truncated_files`
    because it left the loop, would fail here -- and this is the direction that matters,
    because `not`-of-no-match is the shape that ends up claiming safety.
    """
    target = _three(tmp_path, ("f03.py",))
    _premise_marker_is_findable(target, ("f03.py",))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    hit, seen = _reads(monkeypatch, lambda: evaluate(_not(_rule()), target))
    assert seen == ["f01.py", "f02.py"], (
        f"only the files the cap admits may be read, and all of them must be -- got {seen}")
    assert hit.matched is True, (
        "the marker lies outside the cut domain, so the inner rule did not match and `not` "
        "holds -- an unread file must never be credited as a hit")
    assert hit.truncated_files == 3, (
        "the answer is over an incomplete domain and must say so; got "
        f"{hit.truncated_files}")
