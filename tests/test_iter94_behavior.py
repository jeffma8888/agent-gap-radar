"""Iteration 94 behaviors: a DECIDED `content_absent` search stops reading files, and a
hit's line number is counted over a bounded range.

`content_absent` returns `RuleHit(not found, [])` and throws its locations away, so once
one file in the domain has matched the answer is settled -- every later read is work whose
result is discarded. This iteration stops the loop at that point, GUARDED ON THE RULE KIND
so `content_matches` still reads and ranks its whole domain, and reports the same domain
incompleteness (`truncated_files`) an unbroken loop reported.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/`, the engineer's
or the reviewer's notes, `IMPLEMENTATION.patch`, `checks_head.py`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors; every shape claim was MEASURED by
calling the public interface (`checks.evaluate`, `checks.iter_files`, `checks._read`,
`checks._scope_note`, `checks.RuleHit`, `registry.load_all`) over fixtures this file writes
under pytest's `tmp_path`, or over the committed register.

Structural notes, so this file cannot lie later:

* **The read count is proven DISCRIMINATING by a paired control, not by hope.** One probe
  (`_reads_during`) is applied to fixtures that differ ONLY in WHERE the marker sits, and it
  must report a DIFFERENT count each time: 1 read for a first-file hit (behavior 1), 2 for a
  middle-file hit, 3 for a last-file hit (behavior 3) and 3 for no hit at all (behavior 2).
  A probe that reported "1" because it cannot see reads would fail behaviors 2 and 3; a loop
  that never stops early would fail behavior 1. Neither side can pass by accident.
* **Every "not matched" fixture asserts its own PREMISE.** The same tree is first driven with
  a `content_matches` rule, so `matched is False` on the `content_absent` rule is attributable
  to a real hit rather than to a typo in the marker.
* **Behavior 4's ranking fixture makes ALPHABETICAL and RANKED order DISAGREE.** The test file
  is `atest/test_x.py` and the code files are `zcode/*.py`, so plain path order would put the
  test file FIRST; the file asserts that premise before asserting the ranking, or "code before
  test" would be indistinguishable from "sorted".
* **Behavior 5 is paired with an UNCUT control over the same fixture**, with `MAX_SCAN_FILES`
  as the only variable that moves, so `truncated_files == 3` cannot pass because the field
  happens to be non-zero for some other reason.
* **No literal count from the live register or the live repo is written down.** The live-data
  assertions are stated as invariants (equality against an independently computed reference,
  non-vacuity as a strict lower bound), never as today's numbers, which would red as the
  register grows -- the iteration-09 landmine.
* **No absolute machine path, employer or personal identifier, or real name appears here.**
  The repo root is derived from `__file__`; every fixture lives under pytest's `tmp_path`.
* **Nothing under `gaps/`, `src/` or `PRODUCT.md` is edited to make an assertion true.**
"""

from __future__ import annotations

import pathlib
import re

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import evaluate
from agent_gap_radar.registry import load_all

#: Repo root, derived from this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_GAPS = REPO_ROOT / "gaps"

#: Markers carry the iteration number so no other fixture in the suite can collide.
MARK = "GAPMARK94"
GLOBS = ["**/*.py"]

#: A three-file domain is the spec's "at least 3 files": enough for a first-file hit, a
#: middle-file hit and a last-file hit to be three DIFFERENT read counts.
CLEAN = "a clean line\n"


# --- helpers -----------------------------------------------------------------------------

def _materialise(tmp_path: pathlib.Path, tree: dict[str, str], name: str = "target") -> pathlib.Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _three(tmp_path: pathlib.Path, marked: str | None, name: str = "target") -> pathlib.Path:
    """`f01.py`, `f02.py`, `f03.py`; `marked` (if given) is the one file carrying MARK.

    The names sort in creation order, so "the FIRST file of the domain" and "the LAST file
    of the domain" are observable facts about the fixture rather than assumptions.
    """
    tree = {f"f{i:02d}.py": CLEAN for i in (1, 2, 3)}
    if marked is not None:
        assert marked in tree, "fixture bug: the marked name is not in the domain"
        tree[marked] = CLEAN + MARK + " here\n"
    return _materialise(tmp_path, tree, name)


def _absent(pattern: str = MARK, globs=GLOBS, **extra) -> dict:
    return {"kind": "content_absent", "globs": list(globs), "pattern": pattern, **extra}


def _matches(pattern: str = MARK, globs=GLOBS, **extra) -> dict:
    return {"kind": "content_matches", "globs": list(globs), "pattern": pattern, **extra}


def _reads_during(monkeypatch, rule: dict, target: pathlib.Path):
    """Return `(hit, [basenames read])` -- the module-level `_read` seam, counted.

    The seam is patched on the MODULE, so every recursive combinator call is caught too:
    a recursive call resolves the global at call time.
    """
    seen: list[str] = []
    real = checks._read

    def recording(path: pathlib.Path):
        seen.append(pathlib.Path(path).name)
        return real(path)

    monkeypatch.setattr(checks, "_read", recording)
    hit = evaluate(rule, target)
    monkeypatch.setattr(checks, "_read", real)
    return hit, seen


def _premise_marker_is_findable(target: pathlib.Path, where: str) -> None:
    """Drive the SAME tree with `content_matches`, so a later "not matched" is attributable."""
    probe = evaluate(_matches(), target)
    assert probe.matched is True, \
        f"premise failed: {MARK} is not findable in {target.name} at all, so a " \
        "'content_absent did not match' result would prove nothing"
    assert probe.locations == [f"{where}:2"], \
        f"premise failed: expected the only match at {where}:2, got {probe.locations}"


# --- behavior 1: a decided content_absent search reads only the deciding file -------------

def test_b1_a_first_file_hit_reads_exactly_one_file(tmp_path, monkeypatch):
    target = _three(tmp_path, "f01.py")
    _premise_marker_is_findable(target, "f01.py")
    hit, seen = _reads_during(monkeypatch, _absent(), target)
    assert hit.matched is False, "the pattern IS present, so the absence claim is false"
    assert hit.locations == [], "a content_absent miss reports no locations"
    assert hit.truncated_files == 0, "a three-file domain under the cap is not truncated"
    assert seen == ["f01.py"], (
        "the answer was settled by the first file, so every later read is work whose "
        f"result is discarded -- reads were {seen}")


def test_b1_the_returned_hit_is_a_rulehit_with_the_documented_shape(tmp_path, monkeypatch):
    """The early exit must return the same TYPE with the same three fields, not a shortcut."""
    hit, _ = _reads_during(monkeypatch, _absent(), _three(tmp_path, "f01.py"))
    assert isinstance(hit, checks.RuleHit)
    assert (hit.matched, hit.locations, hit.truncated_files) == (False, [], 0)


# --- behavior 2: an UNDECIDED search is never shortened ----------------------------------

def test_b2_no_hit_anywhere_reads_every_file_and_reports_the_scope_note(tmp_path, monkeypatch):
    target = _three(tmp_path, None)
    assert evaluate(_matches(), target).matched is False, \
        "premise: this fixture carries the marker nowhere"
    hit, seen = _reads_during(monkeypatch, _absent(), target)
    assert hit.matched is True, "nothing matched, so the absence claim holds"
    assert hit.locations == [checks._scope_note(GLOBS, MARK)], \
        "an absent-and-true hit still names the scope it searched, exactly as before"
    assert hit.truncated_files == 0
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "an UNDECIDED search must read the whole domain: stopping early here would be a "
        f"fail-open absence claim over an unsearched tail -- reads were {seen}")


# --- behavior 3: the loop never stops BEFORE the deciding hit ----------------------------

def test_b3_a_last_file_hit_reads_every_file(tmp_path, monkeypatch):
    target = _three(tmp_path, "f03.py")
    _premise_marker_is_findable(target, "f03.py")
    hit, seen = _reads_during(monkeypatch, _absent(), target)
    assert hit.matched is False
    assert hit.locations == []
    assert seen == ["f01.py", "f02.py", "f03.py"], (
        "the deciding hit is in the LAST file, so the loop cannot stop before it -- "
        f"reads were {seen}")


def test_b3_a_middle_file_hit_stops_exactly_at_the_deciding_file(tmp_path, monkeypatch):
    """A direct instantiation of behaviors 1 and 3 together: the exit is AT the hit.

    Three read counts over three fixtures that differ only in WHERE the marker sits (1, 2
    and 3 reads) is what makes the probe discriminating in both directions.
    """
    target = _three(tmp_path, "f02.py")
    _premise_marker_is_findable(target, "f02.py")
    hit, seen = _reads_during(monkeypatch, _absent(), target)
    assert hit.matched is False
    assert seen == ["f01.py", "f02.py"], (
        "the loop must read up to and including the deciding file and no further -- "
        f"reads were {seen}")


# --- behavior 4: content_matches reads and ranks its WHOLE domain ------------------------

def test_b4_content_matches_reads_every_file_and_names_every_match(tmp_path, monkeypatch):
    tree = {"atest/test_x.py": CLEAN + MARK + "\n",
            "zcode/b.py": CLEAN + MARK + "\n",
            "zcode/c.py": CLEAN + MARK + "\n"}
    target = _materialise(tmp_path, tree)
    hit, seen = _reads_during(monkeypatch, _matches(), target)
    assert hit.matched is True
    assert sorted(seen) == ["b.py", "c.py", "test_x.py"], \
        f"a content_matches rule must read its whole domain, got {seen}"
    assert len(seen) == 3, f"no file may be read twice, got {seen}"
    assert sorted(hit.locations) == ["atest/test_x.py:2", "zcode/b.py:2", "zcode/c.py:2"], (
        "the early exit is guarded on the rule kind, so a content_matches location list is "
        f"never truncated -- got {hit.locations}")
    assert hit.truncated_files == 0


def test_b4_the_code_before_test_ranking_is_unchanged(tmp_path, monkeypatch):
    tree = {"atest/test_x.py": CLEAN + MARK + "\n",
            "zcode/b.py": CLEAN + MARK + "\n",
            "zcode/c.py": CLEAN + MARK + "\n"}
    target = _materialise(tmp_path, tree)
    # PREMISE: plain path order would put the TEST file FIRST, so an assertion about the
    # observed order is an assertion about RANKING and not about sorting.
    assert sorted(tree) == ["atest/test_x.py", "zcode/b.py", "zcode/c.py"]
    assert [pathlib.Path(p).name for p in checks.iter_files(target, GLOBS)] == \
        ["test_x.py", "b.py", "c.py"], "premise: the domain is walked in plain path order"
    hit = evaluate(_matches(), target)
    assert hit.locations == ["zcode/b.py:2", "zcode/c.py:2", "atest/test_x.py:2"], (
        "code locators must still rank ahead of test locators, and every match must still "
        f"be named -- got {hit.locations}")


# --- behavior 5: an early exit still reports the domain incompleteness -------------------

def test_b5_an_early_exit_over_a_cut_domain_still_reports_the_total_it_held(tmp_path, monkeypatch):
    target = _three(tmp_path, "f01.py")
    _premise_marker_is_findable(target, "f01.py")
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    hit, seen = _reads_during(monkeypatch, _absent(), target)
    assert hit.matched is False
    assert hit.locations == []
    assert hit.truncated_files == 3, (
        "the early exit must report the same domain incompleteness the unbroken loop "
        "reported -- the TOTAL the domain held, computed before the loop -- so a cut "
        f"domain is never laundered into a clean-looking answer; got {hit.truncated_files}")
    assert seen == ["f01.py"], f"the cut domain is still exited at the hit, reads were {seen}"


def test_b5_control_the_same_fixture_uncut_reports_no_truncation(tmp_path, monkeypatch):
    """`MAX_SCAN_FILES` is the ONLY variable that moves between this and the test above."""
    target = _three(tmp_path, "f01.py")
    hit, seen = _reads_during(monkeypatch, _absent(), target)
    assert (hit.matched, hit.locations, hit.truncated_files) == (False, [], 0)
    assert seen == ["f01.py"]


def test_b5_the_early_exits_truncation_survives_a_combinator(tmp_path, monkeypatch):
    """Beyond the spec's three values: the report must not be lost on the way out.

    `truncated_files` exists so a cut domain cannot claim safety; a value that a `not`
    wrapper dropped would restore exactly the fail-open it was built to close.
    """
    target = _three(tmp_path, "f01.py")
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    inner = evaluate(_absent(), target)
    outer = evaluate({"kind": "not", "rule": _absent()}, target)
    assert inner.truncated_files == 3, "premise: the inner rule saw a cut domain"
    assert outer.truncated_files == inner.truncated_files == 3


# --- behavior 6: the line number of the first match in a file ----------------------------

@pytest.mark.parametrize(
    "label,body,expected",
    [
        ("first line", MARK + " here\nsecond\nthird\n", 1),
        ("interior line", "first\nsecond\n" + MARK + " here\nfourth\n", 3),
        ("final line, no trailing newline", "first\nsecond\n" + MARK + " here", 3),
    ],
)
def test_b6_a_hit_names_the_one_based_line_of_the_first_match(tmp_path, label, body, expected):
    target = _materialise(tmp_path, {"only.py": body}, name=re.sub(r"\W+", "_", label))
    hit = evaluate(_matches(), target)
    assert hit.matched is True, f"premise failed for {label!r}: the marker was not found"
    assert hit.locations == [f"only.py:{expected}"], \
        f"{label}: expected only.py:{expected}, got {hit.locations}"


def test_b6_only_the_first_match_in_a_file_is_named(tmp_path):
    body = MARK + " one\nfiller\n" + MARK + " two\n"
    hit = evaluate(_matches(), _materialise(tmp_path, {"twice.py": body}))
    assert hit.locations == ["twice.py:1"], \
        f"a file contributes ONE locator, its first match; got {hit.locations}"


@pytest.mark.parametrize("lines_before", [0, 1, 499])
def test_b6_the_line_number_is_correct_at_a_deep_offset(tmp_path, lines_before):
    """Beyond the spec's three named cases: a bounded count and a prefix-slice count must
    agree at ANY offset, so the same rule is asserted near the start and far into a file."""
    body = "".join(f"line {i}\n" for i in range(1, lines_before + 1)) + MARK + " here\n"
    target = _materialise(tmp_path, {"deep.py": body}, name=f"deep{lines_before}")
    hit = evaluate(_matches(), target)
    assert hit.locations == [f"deep.py:{lines_before + 1}"], \
        f"{lines_before} lines before the match, got {hit.locations}"


def test_b6_a_match_that_spans_lines_names_its_start_line(tmp_path):
    """AMBIGUITY, reported to PM: behavior 6 says "the 1-based line of the first match" and
    does not say whether a MULTI-LINE match is reported at its start or its end. The start
    is the only reading a reader can act on, and it is what the shipped tree does; this test
    pins it because counting to `m.end()` instead of `m.start()` is the one plausible
    off-by-one the changed expression could introduce."""
    target = _materialise(tmp_path, {"span.py": "one\nalpha\nmid\nbeta\nfive\n"})
    hit = evaluate(_matches(pattern=r"alpha[\s\S]*?beta"), target)
    assert hit.locations == ["span.py:2"], \
        f"a span from line 2 to line 4 is reported at line 2, got {hit.locations}"


def test_b6_crlf_line_endings_are_counted_the_same_way(tmp_path):
    target = _materialise(tmp_path, {"crlf.py": "one\r\ntwo\r\n" + MARK + " here\r\n"})
    hit = evaluate(_matches(), target)
    assert hit.locations == ["crlf.py:3"], f"got {hit.locations}"


# --- live register: the change moves no verdict on real data ------------------------------

def _content_rules(rule, out: list[dict]) -> list[dict]:
    """Every leaf content rule reachable from `rule`, combinators included."""
    if not isinstance(rule, dict):
        return out
    if rule.get("kind") in ("content_absent", "content_matches"):
        out.append(rule)
    for sub in rule.get("rules", []) or []:
        _content_rules(sub, out)
    if "rule" in rule:
        _content_rules(rule["rule"], out)
    return out


def _live_content_rules() -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    for gap in load_all(REPO_GAPS):
        if gap.check is None:
            continue
        check = gap.check.model_dump(exclude_none=True)
        for key in ("applies_when", "present_when", "mitigated_when"):
            for leaf in _content_rules(check.get(key), []):
                found.append((f"{check.get('id')}/{key}", leaf))
    return found


def test_live_every_content_absent_verdict_matches_an_independent_full_read():
    """A register-wide differential whose reference is computed HERE, not read from `src/`.

    For a `content_absent` rule the answer is "no file in the domain matches", so an
    independent full read of the same domain is a sound oracle for `matched`. The early exit
    is an optimisation only if the two agree on every real pattern in the register.

    `exclude_tests` rules are skipped, because this oracle does not model that filter and a
    wrong oracle would red a correct tree.
    """
    rules = [(name, r) for name, r in _live_content_rules()
             if r["kind"] == "content_absent" and not r.get("exclude_tests")]
    assert rules, "anti-vacuity: the live register carries no plain content_absent rule"
    checked = 0
    reached = 0
    with checks.read_cache_scope():
        for name, rule in rules:
            domain = checks.iter_files(REPO_ROOT, list(rule["globs"]))
            if not domain:
                continue
            try:
                regex = re.compile(rule["pattern"], re.MULTILINE)
            except re.error:
                continue
            reference_any = False
            for path in domain[:checks.MAX_SCAN_FILES]:
                text = checks._read(path)
                if text is not None and regex.search(text) is not None:
                    reference_any = True
                    break
            hit = evaluate(rule, REPO_ROOT)
            assert hit.matched is (not reference_any), (
                f"{name}: the early exit disagrees with an independent full read of the "
                f"same domain (matched={hit.matched}, reference found a match="
                f"{reference_any})")
            assert hit.locations == ([] if reference_any
                                     else [checks._scope_note(list(rule["globs"]),
                                                              rule["pattern"])]), \
                f"{name}: locations {hit.locations} do not match the documented shape"
            checked += 1
            reached += 1 if reference_any else 0
    assert checked, "anti-vacuity: no live content_absent rule saw a single file in this repo"
    assert reached, (
        "anti-vacuity: every live content_absent rule was undecided over this repo, so the "
        "early-exit branch was never taken and 'the verdicts agree' proves nothing")
