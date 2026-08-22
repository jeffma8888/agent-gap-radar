"""Iteration 63 behaviors: a truncated file domain may no longer claim safety.

`MAX_SCAN_FILES` slices the file list a content rule reads. That slice was SILENT, so a
`present_when` signature living in the unread tail went unseen, `mitigated_when` matched, and
`run_check` returned `ABSENT` -- "mitigation positively identified" -- a safety claim resting
on a search that never covered the target. `ABSENT` is the only one of the five verdicts that
ASSERTS safety, so it is the only one a cut domain can lie with. This iteration makes the cut
visible (`RuleHit.truncated_files`), propagates it through every combinator, and converts
exactly that one verdict into `UNKNOWN`.

Black-box, and the ISOLATION CONTRACT IS HONORED: every expectation below comes from `pm.md`'s
Expected Behaviors, and every claim is measured by CALLING a public interface --
`checks.RuleHit`, `checks.evaluate`, `checks.run_check`, `checks.iter_files`, `registry.load_all`
and `scan`/`scan_json` -- over fixtures this file writes under pytest's `tmp_path`, or over the
committed register. Nothing here reads the engineer's or the reviewer's notes, a diff or a patch.
ONE DISCLOSURE, also carried in the tester report: while surveying test conventions a grep was
run with `src/` in its path list, so roughly twenty fragmentary lines of `checks.py` scrolled
past. No assertion in this file was taken from them. In particular the reason-format assertion
below pins NO WORDING -- it requires only what the spec requires, that both numbers appear.

Structural notes, so this file cannot lie later:

* **Every truncation assertion is paired with an uncut control over the SAME fixture**, with the
  cap as the only variable that moves. Without the pair, a test that passed because nothing was
  ever found is indistinguishable from one that passed because truncation was reported.
* **Every fixture asserts its own premise.** A tail-marker fixture asserts the marker IS findable
  at a cap that admits it, so "not matched" is attributable to the cut rather than to a typo in
  the marker.
* **No fixture exceeds the real cap.** `MAX_SCAN_FILES` is monkeypatched down to single digits
  over trees of five to seven tiny files; a 4000-file tree would tax every future suite run and
  prove nothing extra.
* **The live-register claim is measured as a DOMAIN SIZE, never pinned to a literal.** Behavior 9
  says the cap is dormant on live data; this file measures every live rule domain against
  `checks.MAX_SCAN_FILES` instead of writing down today's 61, which would red as the repo grows.
* **No absolute machine path and no personal identifier appears here.** The repo root is derived
  from `__file__`; every fixture lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import Verdict, evaluate, run_check
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import scan, scan_json

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_GAPS = REPO_ROOT / "gaps"

#: Markers carry the iteration number so no other fixture in the suite can collide with them.
MARK = "GAPMARK63"
MITIG = "MITIGMARK63"
BOTH = "HITMARK63"


def _materialise(tmp_path: pathlib.Path, tree: dict[str, str], name: str = "target") -> pathlib.Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _py_tree(n: int, marks: dict[str, str] | None = None) -> dict[str, str]:
    """`n` files `f01.py`..`fNN.py`; `marks` overrides the body of named files.

    The names sort in creation order, so "the first MAX_SCAN_FILES in the existing order" is
    observable: a marker in `f01.py` is inside any cap of one or more, and one in `f07.py` is
    outside every cap below seven.
    """
    marks = marks or {}
    return {f"f{i:02d}.py": marks.get(f"f{i:02d}.py", "a clean line\n")
            for i in range(1, n + 1)}


def _mixed(tmp_path: pathlib.Path, py_marks=None, md_marks=None) -> pathlib.Path:
    """Five `.py` files and three `.md` files: two domains of DIFFERENT size.

    Two unequal domains are what make behavior 4's `max` distinguishable from "the first
    sub-rule" or "the last sub-rule".
    """
    tree = _py_tree(5, py_marks)
    for i in range(1, 4):
        name = f"m{i:02d}.md"
        tree[name] = (md_marks or {}).get(name, "clean prose\n")
    return _materialise(tmp_path, tree)


def _matches(pattern: str, globs=("**/*.py",)) -> dict:
    return {"kind": "content_matches", "globs": list(globs), "pattern": pattern}


def _check(with_mitigation: bool = True, question: str | None = None, **extra) -> dict:
    check = {"id": "CHK-963", "present_when": _matches(MARK)}
    if with_mitigation:
        check["mitigated_when"] = _matches(MITIG)
    if question:
        check["manual_question"] = question
    check.update(extra)
    return check


# --- behavior 1: RuleHit gains a third field, defaulting to 0 ----------------------------

def test_b1_rulehit_gains_a_third_field_defaulting_to_zero():
    hit = checks.RuleHit(True, ["f01.py:1"])
    assert hit.matched is True
    assert hit.locations == ["f01.py:1"], "a two-argument RuleHit keeps its present meaning"
    assert hit.truncated_files == 0, "an unspecified truncation must read as 'not truncated'"
    assert inspect.signature(checks.RuleHit).parameters["truncated_files"].default == 0
    assert checks.RuleHit(False, [], 7).truncated_files == 7


# --- behavior 2: content_matches / content_absent report the total the domain held --------

def test_b2_a_cut_domain_reports_the_total_it_held(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(5, {"f05.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    hit = evaluate(_matches(MARK), target)
    assert not hit.matched, "premise: the only marker lives in the unread tail"
    assert hit.truncated_files == 5, "the TOTAL the domain held, not the number read"


def test_b2_the_uncut_control_over_the_same_fixture_finds_it_and_reports_zero(tmp_path, monkeypatch):
    """The pair for the test above: same tree, cap EQUAL to the domain, so nothing is cut."""
    target = _materialise(tmp_path, _py_tree(5, {"f05.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 5)
    hit = evaluate(_matches(MARK), target)
    assert hit.matched and hit.locations == ["f05.py:1"], "premise: the marker IS findable"
    assert hit.truncated_files == 0, "a domain EQUAL to the cap is not truncated"


def test_b2_truncation_is_reported_even_when_the_rule_matched(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(5, {"f01.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    hit = evaluate(_matches(MARK), target)
    assert hit.matched and hit.locations == ["f01.py:1"]
    assert hit.truncated_files == 5, "the report is about the DOMAIN, not about the outcome"


def test_b2_the_files_read_stay_the_first_n_in_the_existing_order(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(
        5, {"f01.py": MARK + "\n", "f02.py": MARK + "\n", "f05.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    hit = evaluate(_matches(MARK), target)
    assert hit.locations == ["f01.py:1", "f02.py:1"], \
        "no currently-read file may become unread, and none beyond the cap may become read"
    assert hit.truncated_files == 5


@pytest.mark.parametrize("cap,expected", [(2, 5), (5, 0), (9, 0)])
def test_b2_content_absent_reports_truncation_the_same_way(tmp_path, monkeypatch, cap, expected):
    """`.matched` is deliberately not asserted here: behavior 2 governs `truncated_files`
    for this kind, and `content_absent`'s match semantics are settled by earlier iterations."""
    target = _materialise(tmp_path, _py_tree(5))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", cap)
    hit = evaluate({"kind": "content_absent", "globs": ["**/*.py"],
                    "pattern": "NOWHERE_" + MARK}, target)
    assert hit.truncated_files == expected


# --- behavior 3: the uncapped branch may not claim truncation ----------------------------

@pytest.mark.parametrize("kind", ["file_exists", "file_absent"])
def test_b3_glob_only_kinds_never_claim_truncation(tmp_path, monkeypatch, kind):
    target = _materialise(tmp_path, _py_tree(5))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 1)
    hit = evaluate({"kind": kind, "globs": ["**/*.py"]}, target)
    assert hit.matched is (kind == "file_exists"), "premise: the branch still sees the files"
    assert hit.truncated_files == 0, \
        "this branch is uncapped, so claiming truncation here would be a fabrication"


# --- behavior 4: truncation propagates through every combinator --------------------------

@pytest.mark.parametrize("order", ["py_first", "md_first"])
def test_b4_any_of_returns_the_maximum_over_the_rules_it_evaluated(tmp_path, monkeypatch, order):
    target = _mixed(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    py, md = _matches(MARK), _matches(MARK, ("**/*.md",))
    rules = [py, md] if order == "py_first" else [md, py]
    hit = evaluate({"kind": "any_of", "rules": rules}, target)
    assert not hit.matched, "premise: neither sub-rule matches, so both must be evaluated"
    assert hit.truncated_files == 5, \
        "5 py files against 3 md files: the MAXIMUM, in either order -- not the first or last"


@pytest.mark.parametrize("order", ["py_first", "md_first"])
def test_b4_all_of_returns_the_maximum_over_the_rules_it_evaluated(tmp_path, monkeypatch, order):
    target = _mixed(tmp_path, {"f01.py": BOTH + "\n"}, {"m01.md": BOTH + "\n"})
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    py, md = _matches(BOTH), _matches(BOTH, ("**/*.md",))
    rules = [py, md] if order == "py_first" else [md, py]
    hit = evaluate({"kind": "all_of", "rules": rules}, target)
    assert hit.matched, "premise: both sub-rules match, so both must be evaluated"
    assert hit.truncated_files == 5


def test_b4_not_passes_its_inner_truncation_through_unchanged(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(5, {"f05.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    inner = evaluate(_matches(MARK), target)
    outer = evaluate({"kind": "not", "rule": _matches(MARK)}, target)
    assert not inner.matched and inner.truncated_files == 5, "premise: the inner rule was cut"
    assert outer.matched, "premise: `not` inverts an unmatched inner rule"
    assert outer.truncated_files == inner.truncated_files == 5, \
        "`not` inverts the MATCH; it may not launder the incompleteness"


def test_b4_combinators_report_zero_when_no_sub_rule_was_cut(tmp_path, monkeypatch):
    target = _mixed(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 9)
    py, md = _matches(MARK), _matches(MARK, ("**/*.md",))
    for rule in ({"kind": "any_of", "rules": [py, md]},
                 {"kind": "all_of", "rules": [py, md]},
                 {"kind": "not", "rule": py}):
        assert evaluate(rule, target).truncated_files == 0, rule["kind"]


# --- behaviors 5 and 6: the one verdict that claims safety, and its control ---------------

def test_b5_absent_becomes_unknown_when_the_present_domain_was_cut(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(7, {"f01.py": MITIG + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 3)
    out = run_check(_check(), target)
    assert out.verdict is Verdict.UNKNOWN
    assert out.verdict is not Verdict.ABSENT, \
        "a mitigation cannot be 'positively identified' over a domain never searched"
    assert out.locations == [], "an UNKNOWN verdict has nothing to point at"
    numbers = set(re.findall(r"\d+", out.reason))
    assert {"3", "7"} <= numbers, (
        "the reason must name BOTH the cap applied and the total the domain held; "
        f"got {out.reason!r}")


def test_b6_absent_survives_when_the_present_domain_was_not_cut(tmp_path, monkeypatch):
    """The control that proves behavior 5 is a truncation test and not a blanket downgrade.

    Identical fixture to behavior 5's; the CAP is the only thing that moves.
    """
    target = _materialise(tmp_path, _py_tree(7, {"f01.py": MITIG + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 7)
    out = run_check(_check(), target)
    assert out.verdict is Verdict.ABSENT, \
        "ABSENT is still correct when the whole domain was searched and a mitigation was found"


def test_the_fail_open_is_closed_end_to_end_with_the_marker_only_in_the_unread_tail(
        tmp_path, monkeypatch):
    """The regression fixture the acceptance criteria ask for.

    `present_when` matches ONLY in the truncated tail and `mitigated_when` matches inside the
    cap -- the exact shape that used to report `ABSENT`. Cut, it must be `UNKNOWN`; whole, the
    tail marker is proved findable, so the cut is demonstrably what hid it.
    """
    tree = _py_tree(7, {"f01.py": MITIG + "\n", "f07.py": MARK + "\n"})
    target = _materialise(tmp_path, tree)

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 3)
    cut = run_check(_check(), target)
    assert cut.verdict is Verdict.UNKNOWN
    assert cut.verdict is not Verdict.ABSENT, "this is the fail-open this iteration closes"

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 7)
    probe = evaluate(_matches(MARK), target)
    assert probe.matched and probe.locations == ["f07.py:1"], \
        "premise: the tail marker IS findable once the domain is whole"
    whole = run_check(_check(), target)
    assert whole.verdict is Verdict.MANUAL, \
        "whole, BOTH signatures are visible, which escalates rather than passing"
    assert whole.verdict is not Verdict.ABSENT


# --- behavior 7: truncation never downgrades a positive or pre-empts NOT_APPLICABLE -------

def test_b7_a_positive_finding_over_a_cut_domain_is_still_present(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(5, {"f01.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    out = run_check(_check(with_mitigation=False), target)
    assert out.verdict is Verdict.PRESENT, \
        "a signature that WAS found is found no matter what went unread"
    assert out.locations == ["f01.py:1"]


def test_b7_both_signatures_over_a_cut_domain_still_escalate_to_manual(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(5, {"f01.py": MARK + "\n" + MITIG + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    out = run_check(_check(), target)
    assert out.verdict is Verdict.MANUAL
    assert out.reason == "ambiguous: both signatures present"


def test_b7_not_applicable_short_circuits_before_truncation_is_considered(tmp_path, monkeypatch):
    target = _materialise(tmp_path, _py_tree(5, {"f05.py": MARK + "\n"}))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 1)
    out = run_check(_check(applies_when={"kind": "file_exists", "globs": ["**/*.rs"]}), target)
    assert out.verdict is Verdict.NOT_APPLICABLE, \
        "a precondition that does not hold is decided before any domain is searched"


# --- behavior 8: MANUAL is pinned unchanged ----------------------------------------------

@pytest.mark.parametrize("cap,label", [(3, "cut"), (7, "whole")])
def test_b8_manual_stays_manual_with_its_question_cut_or_whole(tmp_path, monkeypatch, cap, label):
    """Deliberately unchanged: MANUAL already tells the reader that absence is not safety,
    so it is not the fail-open, and widening the fix here would cost the reader the question."""
    target = _materialise(tmp_path, _py_tree(7))
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", cap)
    question = "Does this project bound its own scan domain?"
    out = run_check(_check(question=question), target)
    assert out.verdict is Verdict.MANUAL, f"{label}: MANUAL is pinned by this test"
    assert out.question == question, f"{label}: the manual_question survives"


# --- behavior 9: the cap is dormant on live data, so no committed verdict may move --------

def _rule_globs(rule, out: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Every `globs` list a rule tree contains, recursing into `any_of`/`all_of`/`not`."""
    if not isinstance(rule, dict):
        return out
    if "globs" in rule:
        out.append(tuple(rule["globs"]))
    for sub in rule.get("rules", []) or []:
        _rule_globs(sub, out)
    if "rule" in rule:
        _rule_globs(rule["rule"], out)
    return out


def _live_checked_gaps():
    return [g for g in load_all(REPO_GAPS) if g.check is not None]


def test_b9_every_live_rule_domain_is_under_the_cap():
    gaps = _live_checked_gaps()
    assert gaps, "anti-vacuity: the live register must carry at least one automated check"
    domains: list[int] = []
    for gap in gaps:
        check = gap.check.model_dump(exclude_none=True)
        for key in ("applies_when", "present_when", "mitigated_when"):
            for globs in _rule_globs(check.get(key), []):
                domains.append(len(checks.iter_files(REPO_ROOT, list(globs))))
    assert domains, "anti-vacuity: no live rule declared a glob, so nothing was measured"
    assert max(domains) > 0, "anti-vacuity: no live rule saw a single file in this repo"
    assert max(domains) < checks.MAX_SCAN_FILES, (
        f"the largest live rule domain is {max(domains)} against a cap of "
        f"{checks.MAX_SCAN_FILES}: the cap is NOT dormant, so this change moves a "
        "committed verdict and behavior 9's premise is false")


def test_b9_no_live_present_when_evaluation_reports_truncation():
    """The direct form of "byte-identical": if nothing live is cut, no live verdict can move."""
    for gap in _live_checked_gaps():
        check = gap.check.model_dump(exclude_none=True)
        rule = check.get("present_when")
        if rule is None:
            continue
        assert evaluate(rule, REPO_ROOT).truncated_files == 0, \
            f"{check.get('id')} would now report truncation over this repo"


def test_b9_the_live_scan_stays_deterministic():
    gaps = load_all(REPO_GAPS)
    first = scan_json(scan(gaps, REPO_ROOT))
    assert scan_json(scan(gaps, REPO_ROOT)) == first, "the scan document must be reproducible"
    payload = json.loads(first)
    assert payload["findings"], "anti-vacuity: the live scan produced no findings at all"
