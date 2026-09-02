"""Iteration 99 behaviors: the required-literal prefilter gains its ONE call site.

Iteration 93 shipped `checks.required_literals` with a published one-directional
soundness guarantee and deliberately NO caller. This iteration wires it into
`evaluate`'s shared content branch, so a file whose folded text holds no member of a
pattern's proved literal set never reaches the regex.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the
implementation as logic, nor `engineer.md`, nor `reviewer.md`, nor `fix_review.md`,
nor `IMPLEMENTATION.patch`, nor any diff. Every expectation comes from `pm.md`'s
Expected Behaviors. Every shape claim was measured by CALLING the public functions
(`checks.evaluate`, `checks.required_literals`, `checks.read_cache_scope`,
`checks.tracked_files`) and by running the CLI verbs through `main`.

THREE DISCLOSURES, also carried in the tester report, because each touches something
that is not the public API:

* **Behavior 5 substitutes and observes the private fold seam** (`checks._folded`,
  `checks._FOLD_CACHE_STACK`). Both names come from `pm.md`'s own Expected Behavior 5
  and its Implementation sketch, not from reading the source: the behavior is stated as
  object IDENTITY and stack EMPTINESS, and no public surface exposes either. The repo
  has the same precedent committed for the read memo in `tests/test_read_cache_unit.py`,
  which spies on `checks._decode`. Nothing here asserts HOW the memo works: the spy
  counts calls and compares `id()`.
* **Behavior 4 reads this repo's own tracked files as a CORPUS**, not as logic -- a
  soundness sweep needs real text to search, and the text is a haystack.
* **Behavior 4 reads `gaps/*.json` as DATA** to enumerate live content patterns. No
  record id is named, no count over the register is pinned as equality, and nothing
  under `gaps/` is edited to make an assertion true. The register is grown by an
  outside research pass, so every claim over it is a strict LOWER bound.

Structural notes, so this file cannot lie later:

* **Every substitution goes through `monkeypatch.setattr(checks, "required_literals", ...)`**,
  which is the seam `pm.md` names: `evaluate` must resolve the extractor as a bare
  module global at CALL time. An implementation that captured it at import time, or
  aliased it, would leave these tests red -- deliberately.
* **Every skip assertion is paired with its CONTROL in the same behavior.** A test that
  only ever sees a skip cannot tell a working prefilter from a broken regex path, so
  behaviors 1, 2, 5 and 6 each assert the substituted AND the unsubstituted verdict.
* **No timing is asserted anywhere.** `pm.md` requires the wall-clock prize to be
  REPORTED, never asserted; a wall-clock assertion in the suite is flake.
* **Non-vacuity is asserted, not hoped for.** Behavior 3 pins a floor on the domain size
  and on the findings actually rendered; behavior 4 pins a floor on the number of pairs
  the literal test REJECTED and on the number of patterns it could not prove; behavior 5
  pins the two-`str.lower()`-calls-are-two-objects control that makes an identity claim
  mean something; behavior 6 pins that the domain really exceeded the cap.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every synthetic target is built under pytest's `tmp_path`.
* **The case-only fixture is the one shape that separates FOLDED from RAW.** Measured by
  calling the public extractor: `required_literals` normalises every literal it returns to
  lower case, and `evaluate`'s regex is case-sensitive unless the pattern itself says
  otherwise. Every other fixture in this module holds its literal in BOTH forms, so none of
  them can tell a literal test applied to the folded text from one applied to the raw text
  -- and that rival inverts a real verdict. The final section pins it.
* **This module adds no autouse offline tripwire.** Five behavior modules each carry a
  hand-copied one; `pm.md` records that consolidating them needs a product decision about
  shared test helpers, so a sixth copy is deliberately not added here. Nothing in this
  module opens a socket: the only subprocess is the `git ls-files` behind
  `checks.tracked_files`.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"

#: The bounded REAL target behavior 3 scans. `src/` is tracked, is inside this repo,
#: and was measured to hold well over the spec's 8-file floor.
BOUNDED_TARGET = REPO_ROOT / "src"

#: Behavior 4's corpus: two bounded tracked subtrees of this repo.
CORPUS_SUBTREES = ("src", "tools")

#: A literal that cannot occur in any fixture body here, so a stub returning it forces
#: the prefilter's skip branch. Spelled once.
IMPOSSIBLE_LITERAL = "qzx-absent"

#: The fixture pattern. Mixed case in the BODY on purpose: `str.lower()` then has to
#: allocate, so behavior 5's identity claim is not an artifact of an unchanged string.
PATTERN = "alpha"
BODY = "ALPHA and alpha\n"


# --- helpers ---------------------------------------------------------------


def _matches(pattern: str = PATTERN) -> dict:
    return {"kind": "content_matches", "pattern": pattern, "globs": ["*.txt"]}


def _absent(pattern: str = PATTERN) -> dict:
    return {"kind": "content_absent", "pattern": pattern, "globs": ["*.txt"]}


def _txt_target(tmp_path: pathlib.Path, body: str = BODY, name: str = "a.txt"):
    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text(body, encoding="utf-8")
    return target


def _substitute(monkeypatch, value):
    """Substitute the extractor ON THE MODULE -- `pm.md`'s late-bound seam."""
    monkeypatch.setattr(checks, "required_literals", lambda pattern: value)


def _fold_spy(monkeypatch) -> list[tuple[pathlib.Path, int]]:
    """Record `(path, id(folded))` for every fold, then delegate. Returns the log."""
    seen: list[tuple[pathlib.Path, int]] = []
    real = checks._folded

    def spy(path: pathlib.Path, text: str) -> str:
        out = real(path, text)
        seen.append((path, id(out)))
        return out

    monkeypatch.setattr(checks, "_folded", spy)
    return seen


# --- behavior 1: the prefilter is wired, and the seam is late-bound --------


def test_b1_a_proved_literal_absent_from_the_file_skips_the_regex(tmp_path, monkeypatch):
    """Behavior 1, first half: a literal the file cannot hold really does skip."""
    target = _txt_target(tmp_path)
    _substitute(monkeypatch, frozenset({IMPOSSIBLE_LITERAL}))

    hit = checks.evaluate(_matches(), target)

    assert hit.matched is False, (
        "behavior 1: the prefilter is not wired -- a pattern whose proved literal set "
        "is absent from the file still reached the regex and matched"
    )
    assert hit.locations == [], "behavior 1: a skipped file still reported a location"


def test_b1_an_unprovable_pattern_leaves_the_regex_path_intact(tmp_path, monkeypatch):
    """Behavior 1, second half: the skip is the PREFILTER's decision, not a broken
    regex path. Same call, same target, extractor returning `None`."""
    target = _txt_target(tmp_path)
    _substitute(monkeypatch, None)

    hit = checks.evaluate(_matches(), target)

    assert hit.matched is True, (
        "behavior 1: with the extractor returning None the regex path must run -- the "
        "skip in the sibling test would then be a broken content branch, not a prefilter"
    )
    assert len(hit.locations) == 1, hit.locations


def test_b1_the_unsubstituted_call_still_matches_and_the_pattern_is_provable(tmp_path):
    """Behavior 1, non-vacuity: with NO substitution the verdict is unchanged, and the
    real extractor does prove this pattern -- otherwise the guard could never fire in
    production and both halves above would be testing a stub against a stub."""
    target = _txt_target(tmp_path)

    proved = checks.required_literals(PATTERN)
    assert proved is not None, (
        "behavior 1: the real extractor cannot prove the fixture pattern, so this "
        "module would never exercise the live guard"
    )
    assert proved, "the published contract forbids an empty proved set"

    hit = checks.evaluate(_matches(), target)
    assert hit.matched is True
    assert len(hit.locations) == 1


# --- behavior 2: the skip serves `content_absent` too ---------------------


def test_b2_the_skip_serves_content_absent_too(tmp_path, monkeypatch):
    """Behavior 2: the guard lives in the SHARED content branch, so `content_absent`
    reads the pattern as absent when the prefilter rejects every file."""
    target = _txt_target(tmp_path)

    control = checks.evaluate(_absent(), target)
    assert control.matched is False, (
        "control: the pattern IS in the file, so content_absent must be False before "
        "any substitution -- otherwise behavior 2 proves nothing"
    )

    genuine = checks.evaluate(_absent(), _txt_target(tmp_path / "clean", body="zzz\n"))
    assert genuine.matched is True, "control: a genuinely absent pattern reads absent"

    _substitute(monkeypatch, frozenset({IMPOSSIBLE_LITERAL}))
    skipped = checks.evaluate(_absent(), target)

    assert skipped.matched is True, (
        "behavior 2: the guard is not in the shared content branch -- content_absent "
        "still ran the regex after the literal test rejected the file"
    )
    assert skipped.locations == genuine.locations, (
        "behavior 2: a prefilter skip must render exactly like a genuine miss, or the "
        f"skip is observable in the document -- {skipped.locations} vs "
        f"{genuine.locations}"
    )


# --- behavior 3: differential verdicts over the LIVE register -------------


def _scan_argv(*extra: str) -> list[str]:
    return ["scan", str(BOUNDED_TARGET), "--gaps", str(REPO_ROOT), *extra]


def test_b3_the_live_register_scan_is_byte_identical_with_the_prefilter_off(
        capsys, monkeypatch):
    """Behavior 3: no rendered byte and no exit code moves. The comparison is over the
    LIVE `gaps/` register and a bounded REAL target, with both non-vacuity floors."""
    domain = checks.tracked_files(BOUNDED_TARGET)
    assert len(domain) >= 8, (
        f"behavior 3 non-vacuity: the chosen domain holds only {len(domain)} file(s); "
        "a one-file comparison cannot certify a prefilter"
    )

    rc_live = main(_scan_argv())
    live = capsys.readouterr()

    _substitute(monkeypatch, None)
    rc_off = main(_scan_argv())
    off = capsys.readouterr()

    assert live.err == "" and off.err == "", (live.err, off.err)
    assert rc_live == rc_off, f"behavior 3: exit code moved, {rc_live} -> {rc_off}"
    assert live.out == off.out, (
        "behavior 3: the prefilter changed a rendered byte of `radar scan` over the "
        "live register -- an inverted verdict, which VISION.md calls a regression"
    )
    assert live.out.endswith("\n") and not live.out.endswith("\n\n")


def test_b3_the_live_register_json_is_byte_identical_and_reports_real_findings(
        capsys, monkeypatch):
    """Behavior 3, machine payload plus the findings floor: the compared document must
    be non-trivial, so an empty scan cannot certify this."""
    rc_live = main(_scan_argv("--json"))
    live = capsys.readouterr()

    payload = json.loads(live.out)
    assert payload["records_applied"] >= 1, payload["records_applied"]
    assert payload["counts"]["PRESENT"] >= 1, (
        "behavior 3 non-vacuity: the compared document reports no finding at all, so "
        f"byte-identity is worthless here -- counts were {payload['counts']}"
    )

    _substitute(monkeypatch, None)
    rc_off = main(_scan_argv("--json"))
    off = capsys.readouterr()

    assert live.err == "" and off.err == "", (live.err, off.err)
    assert rc_live == rc_off, f"behavior 3: exit code moved, {rc_live} -> {rc_off}"
    assert live.out == off.out, (
        "behavior 3: the prefilter changed a byte of the `--json` payload over the "
        "live register"
    )


# --- behavior 4: soundness sweep over the live register -------------------


def _collect_patterns(node, out: set[str]) -> None:
    """Every `pattern` under a content rule, at any nesting depth."""
    if isinstance(node, dict):
        pattern = node.get("pattern")
        if isinstance(pattern, str) and node.get("kind") in {
                "content_matches", "content_absent"}:
            out.add(pattern)
        for value in node.values():
            _collect_patterns(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_patterns(value, out)


def _live_content_patterns() -> list[str]:
    found: set[str] = set()
    for path in sorted(LIVE_GAPS.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        check = record.get("check")
        if not isinstance(check, dict):
            continue
        for key in ("applies_when", "present_when", "mitigated_when"):
            _collect_patterns(check.get(key), found)
    return sorted(found)


def _corpus() -> list[tuple[pathlib.Path, str]]:
    paths: set[pathlib.Path] = set()
    for sub in CORPUS_SUBTREES:
        paths |= set(checks.tracked_files(REPO_ROOT / sub))
    texts: list[tuple[pathlib.Path, str]] = []
    for path in sorted(paths):
        try:
            texts.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return texts


def _sweep(extractor) -> tuple[list[tuple[str, str]], int, int]:
    """Apply the one-directional guarantee to every (pattern, text) pair.

    Returns `(violations, rejected_pairs, unprovable_patterns)`. A violation is a pair
    the literal test REJECTED while the regex would in fact have matched -- the
    PRESENT-turned-ABSENT inversion this iteration must not introduce.
    """
    patterns = _live_content_patterns()
    corpus = _corpus()
    assert len(patterns) >= 50, f"only {len(patterns)} live content pattern(s) found"
    assert len(corpus) >= 8, f"only {len(corpus)} corpus file(s) found"

    violations: list[tuple[str, str]] = []
    rejected = 0
    unprovable = 0
    for pattern in patterns:
        literals = extractor(pattern)
        if literals is None:
            unprovable += 1
            continue
        compiled = re.compile(pattern, re.MULTILINE)
        for path, text in corpus:
            folded = text.lower()
            if any(literal in folded for literal in literals):
                continue
            rejected += 1
            if compiled.search(text) is not None:
                violations.append((pattern, path.name))
    return violations, rejected, unprovable


def test_b4_the_proved_literal_set_never_rejects_a_file_the_regex_would_match():
    """Behavior 4: zero counterexamples over the live register, with both non-vacuity
    counters asserted non-zero."""
    violations, rejected, unprovable = _sweep(checks.required_literals)

    assert violations == [], (
        "behavior 4: the literal test rejected a (pattern, file) pair the regex "
        f"MATCHES -- each one turns a PRESENT into an ABSENT: {violations[:5]}"
    )
    assert rejected > 0, (
        "behavior 4 non-vacuity: the literal test rejected NOTHING, so a sweep with "
        "zero violations proves nothing about the skip direction"
    )
    assert unprovable > 0, (
        "behavior 4 non-vacuity: no pattern took the unprovable branch, so this sweep "
        "says nothing about patterns the extractor cannot prove"
    )


def test_b4_the_sweep_can_see_an_unsound_literal_set():
    """Behavior 4, two-sided: the same probe, given a deliberately unsound extractor,
    must report violations. Without this, `violations == []` above is indistinguishable
    from a probe incapable of seeing unsoundness."""
    mutant_violations, mutant_rejected, _ = _sweep(
        lambda pattern: frozenset({IMPOSSIBLE_LITERAL}))

    assert mutant_rejected > 0
    assert mutant_violations, (
        "behavior 4 is not two-sided: an extractor claiming every pattern requires an "
        "impossible literal produced no violation, so the probe cannot see unsoundness"
    )


def test_b4_a_pattern_the_extractor_declines_is_never_treated_as_covered():
    """Behavior 4, the other side of the contract: `None` means unprovable, and the
    caller must not read it as an empty (always-rejecting) set."""
    patterns = _live_content_patterns()
    declined = [p for p in patterns if checks.required_literals(p) is None]
    assert declined, "no live pattern is unprovable; the branch is untested"
    for pattern in declined[:20]:
        assert checks.required_literals(pattern) is None, pattern


# --- behavior 5: the fold is memoised for exactly one scan ---------------


def test_b5_two_evaluations_in_one_scope_share_one_folded_object(tmp_path, monkeypatch):
    """Behavior 5: a scan folds a file once, not once per rule."""
    target = _txt_target(tmp_path)
    seen = _fold_spy(monkeypatch)

    with checks.read_cache_scope():
        checks.evaluate(_matches(PATTERN), target)
        checks.evaluate(_matches("beta"), target)

    folded_file = target / "a.txt"
    ids = {fid for path, fid in seen if path == folded_file}
    assert len(seen) >= 2, f"behavior 5: the fold seam was reached {len(seen)} time(s)"
    assert len(ids) == 1, (
        "behavior 5: two rule evaluations in ONE scope folded the same file into "
        f"{len(ids)} distinct objects -- the fold is not memoised per scan"
    )


def test_b5_the_identity_claim_is_not_free(tmp_path, monkeypatch):
    """Behavior 5, control: with NO scope open the same two evaluations produce TWO
    distinct folded objects. This is what makes the identity assertion above a
    measurement rather than an artifact of string interning."""
    target = _txt_target(tmp_path)
    assert BODY.lower() is not BODY.lower(), (
        "control: `str.lower()` returned the same object twice, so an identity "
        "assertion over folded text would pass without any memo"
    )
    seen = _fold_spy(monkeypatch)

    checks.evaluate(_matches(PATTERN), target)
    checks.evaluate(_matches("beta"), target)

    ids = {fid for _, fid in seen}
    assert len(seen) >= 2
    assert len(ids) == len(seen), (
        "control: outside a scope the folds must not be shared, otherwise the memo "
        f"outlives its scope -- {len(seen)} fold(s) produced {len(ids)} object(s)"
    )


def test_b5_no_scope_still_answers_correctly(tmp_path):
    """Behavior 5: the cache is an optimisation, never a precondition."""
    hit = checks.evaluate(_matches(), _txt_target(tmp_path, name="hit.txt"))
    miss = checks.evaluate(_matches(),
                           _txt_target(tmp_path / "other", body="zzz\n", name="m.txt"))
    assert hit.matched is True, "behavior 5: an out-of-scope evaluation lost a match"
    assert miss.matched is False, "behavior 5: an out-of-scope evaluation invented one"


def test_b5_a_fold_never_outlives_its_scope(tmp_path):
    """Behavior 5: the scope IS the invalidation. A second scan of a CHANGED file must
    never answer from the first scan's fold."""
    target = _txt_target(tmp_path, body="zzz\n")
    changed = target / "a.txt"

    with checks.read_cache_scope():
        first = checks.evaluate(_matches(), target)
    assert first.matched is False, "control: the pattern is absent from the first body"
    assert checks._FOLD_CACHE_STACK == [], (
        "behavior 5: the fold-cache stack is not empty after its scope exited, so a "
        "later scan can answer from a stale fold"
    )

    changed.write_text(BODY, encoding="utf-8")
    with checks.read_cache_scope():
        second = checks.evaluate(_matches(), target)
    assert second.matched is True, (
        "behavior 5: a second scope answered from the first scope's fold -- the "
        "process-lifetime staleness defect"
    )
    assert checks._FOLD_CACHE_STACK == []


# --- behavior 6: nothing about the truncation contract moves --------------


def test_b6_truncation_is_reported_identically_with_the_prefilter_off(
        tmp_path, monkeypatch):
    """Behavior 6: the read still happens before the literal test, so a file that is
    read today is still read and `truncated_files` is unchanged."""
    target = tmp_path / "many"
    target.mkdir()
    for index in range(5):
        (target / f"f{index}.txt").write_text("zzz\n", encoding="utf-8")
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)

    assert checks.required_literals(PATTERN) is not None, (
        "behavior 6 non-vacuity: the fixture pattern is unprovable, so the live run "
        "below would not exercise the guard at all"
    )
    live = checks.evaluate(_matches(), target)
    assert live.truncated_files > 0, (
        "behavior 6 non-vacuity: the domain did not exceed the cap, so this test "
        "compares two untruncated runs"
    )

    _substitute(monkeypatch, None)
    off = checks.evaluate(_matches(), target)

    assert live.truncated_files == off.truncated_files, (
        "behavior 6: the prefilter moved the truncation contract -- "
        f"{live.truncated_files} with it, {off.truncated_files} without"
    )
    assert live.matched is off.matched is False


@pytest.mark.parametrize("kind", ["content_matches", "content_absent"])
def test_b6_the_domain_size_a_skip_reports_is_the_domain_not_the_outcome(
        tmp_path, monkeypatch, kind):
    """Behavior 6, both content kinds: a skipped file is still a file in the domain."""
    target = tmp_path / "many"
    target.mkdir()
    for index in range(4):
        (target / f"f{index}.txt").write_text("zzz\n", encoding="utf-8")
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 1)
    rule = {"kind": kind, "pattern": PATTERN, "globs": ["*.txt"]}

    live = checks.evaluate(rule, target)
    _substitute(monkeypatch, None)
    off = checks.evaluate(rule, target)

    assert live.truncated_files == off.truncated_files == 4, (
        kind, live.truncated_files, off.truncated_files)


# --- second pass: rival rules that pass every test above ------------------
#
# The three tests below were found by enumerating rules that satisfy every assertion in
# this module while still violating `pm.md`. That is mutation testing done BLACK-BOX, with
# no access to the implementation: if a rival rule survives the suite, the suite has a hole
# regardless of how the shipped code happens to behave.
#
# Rival 1 -- the literal test reads `text` instead of the FOLDED text. Survives everything
#   above, because every fixture body holds its literal in both cases. Killed below.
# Rival 2 -- the extractor is called once per (pattern, file) pair instead of once per rule
#   evaluation. Verdict-identical, so no assertion above can see it, and it spends per file
#   exactly the cost the prefilter exists to save. Killed below.
# Rival 3 -- the prefilter is wired into a branch the LIVE scan never reaches. Behavior 3's
#   two documents would still be byte-identical, vacuously. Killed below.


#: A body whose only occurrence of the pattern differs from the proved literal in CASE, so
#: the proved literal is ABSENT from the raw body and PRESENT in its folded form.
CASE_ONLY_BODY = "ALPHA ONLY\n"

#: Both spellings that reach the same lower-cased literal: an upper-case pattern (which a
#: case-sensitive regex still matches), and the inline-flag pattern an author writes.
CASE_ONLY_PATTERNS = ("ALPHA", "(?i)alpha")


@pytest.mark.parametrize("kind", ["content_matches", "content_absent"])
@pytest.mark.parametrize("pattern", CASE_ONLY_PATTERNS)
def test_b1_the_literal_test_reads_folded_text_and_never_the_raw_text(
        tmp_path, monkeypatch, pattern, kind):
    """Behaviors 1 and 2, the soundness direction AT THE CALL SITE (kills rival 1).

    Behavior 4's sweep proves the EXTRACTOR sound by folding the text itself, so it is
    structurally blind to a call site that tests the proved literals against unfolded
    text. Such a call site skips this file and inverts its verdict -- a PRESENT read as
    ABSENT for `content_matches`, and the false-mitigation direction for `content_absent`,
    which is the inversion `VISION.md` calls a regression.

    The three preconditions are asserted rather than assumed: a fixture outside the
    discriminating range would let this test pass under either rule.
    """
    target = _txt_target(tmp_path, body=CASE_ONLY_BODY)
    rule = {"kind": kind, "pattern": pattern, "globs": ["*.txt"]}

    literals = checks.required_literals(pattern)
    assert literals, (
        "precondition: the extractor cannot prove this pattern, so the guard would never "
        "fire and this test would be comparing two plain regex runs"
    )
    assert all(literal not in CASE_ONLY_BODY for literal in literals), (
        "precondition: a proved literal occurs verbatim in the RAW body, so this fixture "
        f"cannot separate a folded literal test from a raw one -- {sorted(literals)}"
    )
    assert any(literal in CASE_ONLY_BODY.lower() for literal in literals), (
        "precondition: no proved literal occurs in the FOLDED body either, so this file "
        f"is a genuine miss and the comparison proves nothing -- {sorted(literals)}"
    )

    live = checks.evaluate(rule, target)

    _substitute(monkeypatch, None)
    off = checks.evaluate(rule, target)

    assert off.matched is (kind == "content_matches"), (
        "control: with the prefilter disabled the regex path itself disagrees about this "
        f"fixture, so the differential below would be meaningless -- kind={kind}, "
        f"matched={off.matched}"
    )
    assert live.matched is off.matched, (
        f"behavior 1/2: the literal test read the RAW body for kind={kind}, so a "
        "case-only difference skipped a file the regex matches -- matched "
        f"{live.matched} with the prefilter and {off.matched} without it"
    )
    assert live.locations == off.locations, (live.locations, off.locations)

    # Positive, EXECUTED proof that the folded text is what the literal test reads -- the
    # differential above is only a deduction on its own. An upper-cased literal set is
    # PRESENT in the raw body and ABSENT from its folded form, so a folding call site must
    # skip on it while a raw-text call site must find it and return `off`'s verdict.
    upper = frozenset(literal.upper() for literal in literals)
    assert all(member in CASE_ONLY_BODY for member in upper), (
        "precondition: the upper-cased probe set is not present in the raw body, so it "
        f"cannot separate the two rules -- {sorted(upper)}"
    )
    assert not any(member in CASE_ONLY_BODY.lower() for member in upper), (
        "precondition: the upper-cased probe set survives folding, so a folding call "
        f"site would not skip on it either -- {sorted(upper)}"
    )

    _substitute(monkeypatch, upper)
    skipped = checks.evaluate(rule, target)

    assert skipped.matched is not off.matched, (
        "behavior 1/2: a literal set present in the RAW body and absent from the FOLDED "
        f"body did not skip for kind={kind}, so the literal test reads raw text -- it "
        f"returned {skipped.matched}, the same verdict as with no prefilter at all"
    )


def test_b1_the_extractor_is_consulted_once_per_rule_not_once_per_file(
        tmp_path, monkeypatch):
    """Behavior 1's cost shape (kills rival 2).

    `pm.md`'s sketch hoists the extractor call ABOVE the file loop -- once per rule
    evaluation, not once per (pattern, file) pair. A per-pair call is verdict-identical,
    so every other assertion in this module is blind to it, while it spends per file
    exactly the cost the prefilter exists to save. It is observable through the same
    late-bound seam the substitution tests use.
    """
    target = tmp_path / "many"
    target.mkdir()
    bodies = {f"f{index}.txt": ("alpha here\n" if index == 5 else "zzz\n")
              for index in range(6)}
    for name, body in bodies.items():
        (target / name).write_text(body, encoding="utf-8")

    calls: list[str] = []
    real = checks.required_literals
    monkeypatch.setattr(
        checks,
        "required_literals",
        lambda pattern: (calls.append(pattern), real(pattern))[1],
    )

    hit = checks.evaluate(_matches(), target)

    assert hit.matched is True and hit.locations == ["f5.txt:1"], (
        "non-vacuity: the file loop never reached the one file holding the pattern, so a "
        f"per-file call count would not be {len(bodies)} either -- {hit.locations}"
    )
    assert len(calls) == 1, (
        f"behavior 1: the extractor was consulted {len(calls)} time(s) over a "
        f"{len(bodies)}-file domain -- the call belongs above the file loop, or the "
        "prefilter pays per file the cost it was added to save"
    )
    assert calls == [PATTERN], calls


def test_b3_the_prefilter_is_really_engaged_during_the_live_register_scan(
        capsys, monkeypatch):
    """Behavior 3's missing non-vacuity (kills rival 3).

    Two byte-identical documents prove nothing about a prefilter that never ran in that
    code path. This asserts it did, over the LIVE register and the same bounded real
    target, and that BOTH of its branches were taken: patterns it proved, and patterns it
    declined. Lower bounds only -- the register is grown by an outside research pass, so
    no count over it may be pinned as equality.
    """
    seen: list[bool] = []
    real = checks.required_literals

    def spy(pattern: str):
        proved = real(pattern)
        seen.append(proved is not None)
        return proved

    monkeypatch.setattr(checks, "required_literals", spy)

    rc = main(_scan_argv())
    out = capsys.readouterr()

    assert rc == 0 and out.err == "", (rc, out.err)
    assert out.out.strip(), "the scan rendered nothing, so nothing was scanned"
    assert len(seen) >= 8, (
        "behavior 3 non-vacuity: the live scan consulted the prefilter only "
        f"{len(seen)} time(s), so the byte-identity pair was compared over a code path "
        "the prefilter barely reaches"
    )
    assert sum(seen) >= 1, (
        "behavior 3 non-vacuity: the live scan proved NO pattern, so the skip branch "
        "could never fire and two identical documents are vacuous"
    )
    assert seen.count(False) >= 1, (
        "behavior 3 non-vacuity: every live pattern was provable, so the unprovable "
        "branch was never exercised in the real scan path"
    )


# --- third pass: one more rival rule that passes every test above ---------
#
# Rival 4 -- the skip condition requires EVERY member of the proved literal set to occur
#   instead of AT LEAST ONE. Every fixture above hands the call site a ONE-member set,
#   where `any` and `all` are the same function, so no assertion in this module can
#   separate them; behavior 4's sweep applies its own `any` to the text and therefore
#   measures the EXTRACTOR, not the call site. The rival skips a file whose text the regex
#   matches -- a PRESENT read as ABSENT, the inversion `VISION.md` calls a regression, and
#   the exact failure `pm.md`'s "Why" section says the dormant-first split existed to
#   prevent. Killed below, with the fixture asserted into the discriminating range.

#: A body the fixture pattern MATCHES, holding one probe member and not the other.
PARTIAL_BODY = "alpha only\n"

#: One member present in the folded body, one that cannot be: `any` keeps the file,
#: `all` drops it.
PARTIAL_SET = frozenset({PATTERN, IMPOSSIBLE_LITERAL})

#: A two-member set with NO member in the folded body. The control that proves the guard
#: reads multi-member sets at all -- without it, a call site that ignored every set of
#: size > 1 would pass the partial-set assertion for the wrong reason.
BOTH_ABSENT_SET = frozenset({IMPOSSIBLE_LITERAL, IMPOSSIBLE_LITERAL + "-2"})


@pytest.mark.parametrize("kind", ["content_matches", "content_absent"])
def test_b1_a_literal_set_is_satisfied_by_any_member_not_by_every_member(
        tmp_path, monkeypatch, kind):
    """Behaviors 1 and 2, the set semantics AT THE CALL SITE (kills rival 4).

    `required_literals` publishes a set whose guarantee is one-directional and
    disjunctive: if NO member occurs, the pattern cannot match. It does not promise that
    every member occurs, so a call site joining the membership tests with `all` skips
    files the regex matches.

    Both preconditions and the multi-member control are asserted, not assumed: a fixture
    outside the discriminating range would let this test pass under either rule.
    """
    target = _txt_target(tmp_path, body=PARTIAL_BODY)
    rule = {"kind": kind, "pattern": PATTERN, "globs": ["*.txt"]}
    folded = PARTIAL_BODY.lower()

    assert any(member in folded for member in PARTIAL_SET), (
        "precondition: no member of the probe set occurs in the folded body, so this "
        f"file is a genuine miss under either rule -- {sorted(PARTIAL_SET)}"
    )
    assert not all(member in folded for member in PARTIAL_SET), (
        "precondition: EVERY member of the probe set occurs in the folded body, so `any` "
        f"and `all` agree here and the differential is vacuous -- {sorted(PARTIAL_SET)}"
    )
    assert not any(member in folded for member in BOTH_ABSENT_SET), (
        "precondition: the both-absent control set is not absent from the folded body"
    )

    _substitute(monkeypatch, None)
    off = checks.evaluate(rule, target)
    assert off.matched is (kind == "content_matches"), (
        "control: with the prefilter disabled the regex path disagrees about this "
        f"fixture, so every differential below is meaningless -- kind={kind}, "
        f"matched={off.matched}"
    )

    _substitute(monkeypatch, BOTH_ABSENT_SET)
    none_present = checks.evaluate(rule, target)
    assert none_present.matched is not off.matched, (
        "control: a TWO-member set with no member in the folded body did not skip, so "
        "this test cannot separate an `any` call site from an `all` one -- the guard may "
        f"be ignoring every set larger than one member (kind={kind})"
    )

    _substitute(monkeypatch, PARTIAL_SET)
    partial = checks.evaluate(rule, target)

    assert partial.matched is off.matched, (
        "behavior 1/2: a literal set with ONE member present in the folded body was "
        "treated as unsatisfied, so the call site demands EVERY member instead of ANY -- "
        "that skips a file the regex matches and inverts the verdict, a PRESENT read as "
        f"ABSENT (kind={kind}): {partial.matched} with the set, {off.matched} without "
        "the prefilter"
    )
    assert partial.locations == off.locations, (partial.locations, off.locations)
