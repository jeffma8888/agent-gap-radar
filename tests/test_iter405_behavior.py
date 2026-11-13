"""Iteration 405 behaviors: a per-scope `(pattern, path)` first-match memo.

Inside one `read_cache_scope()` (one scan) a content rule's per-file answer --
"line of the first match, or no match" -- is asked of the regex engine at most
once per `(pattern, path)`. Later rules asking the SAME question of the SAME
file are answered from the scope's memo, and no verdict, location or skip count
moves. Outside a scope there is no memo, and a new scope never replays an old
scope's answer.

The brake is a COUNTING seam, never a wall clock: `checks._cached_compile` is
wrapped so every compiled pattern it hands out tallies its regex passes
(`finditer`/`search`/`match`/`fullmatch`/`findall`). Every target is a tmp tree;
the one live-repo scan (behavior 9) compares memo-on against memo-off on the
SAME tree in the SAME process and asserts `<` only, never a pinned count.

Behavior 1 (scan byte-identical to the pre-change head) is proved by hand in
the tester report, deliberately NOT as a sha-pinned committed test.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
from collections import Counter

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]

_PASS_METHODS = ("finditer", "search", "match", "fullmatch", "findall")

#: Needs a regex pass: not a bare literal, so no pure-literal shortcut answers it.
PATTERN = r"danger\w+_call\("
OTHER = r"checkpoint\w+_write\("


class _CountingPattern:
    """A compiled pattern that tallies each regex pass and delegates the rest."""

    def __init__(self, real: re.Pattern[str], tally: Counter) -> None:
        self._real = real
        self._tally = tally

    def __getattr__(self, name: str):
        attr = getattr(self._real, name)
        if name in _PASS_METHODS:
            tally = self._tally
            pattern = self._real.pattern

            def counted(*args, **kwargs):
                tally[pattern] += 1
                tally["__all__"] += 1
                return attr(*args, **kwargs)

            return counted
        return attr


@pytest.fixture
def passes(monkeypatch: pytest.MonkeyPatch) -> Counter:
    """Install the counting `_cached_compile`; the Counter tallies regex passes."""
    tally: Counter = Counter()
    real = checks._cached_compile

    def counting_compile(pattern: str, flags: int = 0):
        return _CountingPattern(real(pattern, flags), tally)

    monkeypatch.setattr(checks, "_cached_compile", counting_compile)
    return tally


def _rule(pattern: str = PATTERN, kind: str = "content_matches",
          globs: tuple[str, ...] = ("**/*.py",)) -> dict:
    return {"kind": kind, "globs": list(globs), "pattern": pattern}


def _target(tmp_path: pathlib.Path, files: dict[str, bytes | str]) -> pathlib.Path:
    root = tmp_path / "target"
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
    return root


def _matching(tmp_path: pathlib.Path) -> pathlib.Path:
    return _target(tmp_path, {"a.py": "x = 1\ndangerous_call(1)\n"})


def _no_open_frame() -> None:
    assert checks._first_matches() is None
    assert checks._FIRST_MATCH_STACK == []


# --- behavior 2: a repeat question inside one scope runs no regex pass --------


def test_b2_repeat_question_in_one_scope_runs_no_regex_pass(
        tmp_path: pathlib.Path, passes: Counter) -> None:
    target = _matching(tmp_path)
    with checks.read_cache_scope():
        first = checks.evaluate(_rule(), target)
        after_first = passes["__all__"]
        second = checks.evaluate(_rule(), target)
        after_second = passes["__all__"]
    assert first.matched is True and first.locations == ["a.py:2"], first
    assert second == first
    assert after_first >= 1, "premise: the first ask must run a regex pass"
    assert after_second - after_first == 0, (
        f"the repeat ask re-ran {after_second - after_first} regex pass(es)")
    _no_open_frame()


def test_b2_counting_seam_is_live(tmp_path: pathlib.Path, passes: Counter) -> None:
    """Premise guard: the wrapper must see the pass, or every 0 above is vacuous."""
    target = _matching(tmp_path)
    checks.evaluate(_rule(), target)
    assert passes[PATTERN] >= 1, dict(passes)


# --- behavior 3: two rules with one pattern share the answer ------------------


@pytest.mark.parametrize("order", [("content_matches", "content_absent"),
                                   ("content_absent", "content_matches")])
@pytest.mark.parametrize("matching", [True, False], ids=["present", "absent"])
def test_b3_rules_sharing_a_pattern_share_the_answer(
        tmp_path: pathlib.Path, passes: Counter, order: tuple[str, str],
        matching: bool) -> None:
    body = "x = 1\ndangerous_call(1)\n" if matching else "x = 1\nsafe_call(1)\n"
    target = _target(tmp_path, {"a.py": body, "b.py": "y = 2\n"})
    fresh = {}
    for kind in order:
        with checks.read_cache_scope():
            fresh[kind] = checks.evaluate(_rule(kind=kind), target)
    passes.clear()
    shared = {}
    with checks.read_cache_scope():
        shared[order[0]] = checks.evaluate(_rule(kind=order[0]), target)
        after_first = passes["__all__"]
        shared[order[1]] = checks.evaluate(_rule(kind=order[1]), target)
        second_passes = passes["__all__"] - after_first
    assert shared == fresh
    assert fresh["content_matches"].matched is matching
    assert fresh["content_absent"].matched is (not matching)
    assert second_passes == 0, (
        f"the second rule with the same pattern re-ran {second_passes} pass(es)")


# --- behavior 4: no memo outside a scope --------------------------------------


def test_b4_no_memo_outside_a_scope(tmp_path: pathlib.Path, passes: Counter) -> None:
    _no_open_frame()
    target = _matching(tmp_path)
    first = checks.evaluate(_rule(), target)
    after_first = passes["__all__"]
    second = checks.evaluate(_rule(), target)
    after_second = passes["__all__"]
    assert first == second
    assert first.matched is True
    assert after_first >= 1
    assert after_second > after_first, "an un-scoped repeat was answered from a memo"


def test_b4_unscoped_sees_a_rewrite(tmp_path: pathlib.Path) -> None:
    target = _matching(tmp_path)
    assert checks.evaluate(_rule(), target).matched is True
    (target / "a.py").write_text("safe_call(1)\n", encoding="utf-8")
    assert checks.evaluate(_rule(), target).matched is False


# --- behavior 5: the scope is the invalidation --------------------------------


@pytest.mark.parametrize("start_matching", [True, False], ids=["hit-then-miss",
                                                              "miss-then-hit"])
def test_b5_new_scope_does_not_reuse_the_old_answer(
        tmp_path: pathlib.Path, passes: Counter, start_matching: bool) -> None:
    hit, miss = "x = 1\ndangerous_call(1)\n", "x = 1\nsafe_call(1)\n"
    target = _target(tmp_path, {"a.py": hit if start_matching else miss})
    with checks.read_cache_scope():
        before = checks.evaluate(_rule(), target)
    (target / "a.py").write_text(miss if start_matching else hit, encoding="utf-8")
    passes.clear()
    with checks.read_cache_scope():
        after = checks.evaluate(_rule(), target)
    assert before.matched is start_matching
    assert after.matched is (not start_matching), "the new scope replayed the old answer"
    assert after.locations == ([] if start_matching else ["a.py:2"])
    _no_open_frame()


def test_b5_frame_closes_on_exception(tmp_path: pathlib.Path, passes: Counter) -> None:
    target = _matching(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        with checks.read_cache_scope():
            assert checks._first_matches() is not None
            checks.evaluate(_rule(), target)
            raise RuntimeError("boom")
    _no_open_frame()
    passes.clear()
    one = checks.evaluate(_rule(), target)
    mid = passes["__all__"]
    two = checks.evaluate(_rule(), target)
    assert one == two and one.matched is True
    assert mid >= 1 and passes["__all__"] > mid


def test_b5_frames_nest_and_unwind(tmp_path: pathlib.Path) -> None:
    _no_open_frame()
    with checks.read_cache_scope():
        outer = checks._first_matches()
        assert outer is not None
        with checks.read_cache_scope():
            inner = checks._first_matches()
            assert inner is not None
        assert checks._first_matches() is outer
    _no_open_frame()


# --- behavior 6: a different pattern on the same file is not memo-answered ----


def test_b6_different_pattern_same_file_gets_its_own_verdict(
        tmp_path: pathlib.Path, passes: Counter) -> None:
    target = _matching(tmp_path)
    with checks.read_cache_scope():
        p1 = checks.evaluate(_rule(PATTERN), target)
        p2 = checks.evaluate(_rule(OTHER), target)
        p1_again = checks.evaluate(_rule(PATTERN), target)
    assert p1.matched is True and p1.locations == ["a.py:2"]
    assert p2.matched is False and p2.locations == [], p2
    assert p1_again == p1
    with checks.read_cache_scope():
        assert checks.evaluate(_rule(OTHER), target) == p2


def test_b6_second_pattern_that_matches_reports_its_own_line(
        tmp_path: pathlib.Path) -> None:
    target = _target(tmp_path, {"a.py": "dangerous_call(1)\nx = 2\ncheckpoint_db_write(3)\n"})
    with checks.read_cache_scope():
        p1 = checks.evaluate(_rule(PATTERN), target)
        p2 = checks.evaluate(_rule(OTHER), target)
    assert p1.locations == ["a.py:1"]
    assert p2.locations == ["a.py:3"], "P2 was answered with P1's line"


def test_b6_same_pattern_different_globs_scopes_per_path(
        tmp_path: pathlib.Path) -> None:
    target = _target(tmp_path, {"a.py": "dangerous_call(1)\n", "b.py": "safe(1)\n"})
    with checks.read_cache_scope():
        only_b = checks.evaluate(_rule(globs=("b.py",)), target)
        only_a = checks.evaluate(_rule(globs=("a.py",)), target)
        both = checks.evaluate(_rule(), target)
    assert only_b.matched is False
    assert only_a.locations == ["a.py:1"]
    assert both.locations == ["a.py:1"]


# --- behavior 7: a non-ASCII file keeps its verdict ---------------------------


@pytest.mark.parametrize("pattern,text", [
    (r"(?i)\bs\w*ure\b", "token = \u017fecure\n"),
    (r"(?i)\bs\w*ure\b", "token = plain\n"),
    (r"(?i)k\w+n_sign", "x = \u212aelvin_sign\n"),
])
def test_b7_non_ascii_file_keeps_its_verdict(
        tmp_path: pathlib.Path, pattern: str, text: str) -> None:
    target = _target(tmp_path, {"a.py": text})
    truth = re.compile(pattern, re.MULTILINE).search(text) is not None
    unscoped = checks.evaluate(_rule(pattern), target)
    with checks.read_cache_scope():
        first = checks.evaluate(_rule(pattern), target)
        second = checks.evaluate(_rule(pattern), target)
    assert unscoped.matched is truth, (pattern, text, unscoped)
    assert first == unscoped
    assert second == unscoped


# --- behavior 8: skip accounting is unchanged ---------------------------------


def _skip_domain(tmp_path: pathlib.Path) -> pathlib.Path:
    return _target(tmp_path, {
        "big.py": "y" * (checks.MAX_FILE_BYTES + 1),
        "bad.py": b"\xff\xfe\x00bad",
        "z.py": "x = 1\ndangerous_call(1)\n",
    })


@pytest.mark.parametrize("pair", [
    (("content_matches", PATTERN), ("content_matches", PATTERN)),
    (("content_matches", PATTERN), ("content_absent", PATTERN)),
    (("content_absent", PATTERN), ("content_matches", PATTERN)),
    (("content_matches", PATTERN), ("content_matches", OTHER)),
], ids=["same-rule", "matches-absent", "absent-matches", "two-patterns"])
def test_b8_skip_counts_unchanged_by_sharing_a_scope(
        tmp_path: pathlib.Path, pair) -> None:
    target = _skip_domain(tmp_path)
    alone = []
    for kind, pattern in pair:
        with checks.read_cache_scope():
            alone.append(checks.evaluate(_rule(pattern, kind), target))
    with checks.read_cache_scope():
        shared = [checks.evaluate(_rule(pattern, kind), target) for kind, pattern in pair]
    assert shared == alone
    for got, want in zip(shared, alone):
        assert (got.skipped_files, got.unreadable_files, got.truncated_files) == \
            (want.skipped_files, want.unreadable_files, want.truncated_files)
    matches = [h for (k, _), h in zip(pair, shared) if k == "content_matches"]
    assert matches and matches[0].skipped_files >= 1, "premise: a file must be skipped"


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                    reason="root reads a mode-000 file")
def test_b8_unreadable_counts_unchanged_by_sharing_a_scope(
        tmp_path: pathlib.Path) -> None:
    target = _target(tmp_path, {"locked.py": "dangerous_call(0)\n",
                                "z.py": "dangerous_call(1)\n"})
    locked = target / "locked.py"
    locked.chmod(0)
    try:
        alone = []
        for kind in ("content_matches", "content_absent"):
            with checks.read_cache_scope():
                alone.append(checks.evaluate(_rule(kind=kind), target))
        with checks.read_cache_scope():
            shared = [checks.evaluate(_rule(kind=kind), target)
                      for kind in ("content_matches", "content_absent")]
    finally:
        locked.chmod(0o644)
    assert shared == alone
    assert alone[0].unreadable_files >= 1, f"premise: {alone[0]}"


# --- behavior 9: a measurable reduction on the self-scan ----------------------


def _self_scan(*, memo: bool, tally: Counter) -> tuple[int, str]:
    real = checks._cached_compile

    def counting_compile(pattern: str, flags: int = 0):
        return _CountingPattern(real(pattern, flags), tally)

    out = io.StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(REPO)
        mp.setattr(checks, "_cached_compile", counting_compile)
        if not memo:
            mp.setattr(checks, "_first_matches", lambda: None)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(["scan", "."])
    return code, out.getvalue()


def test_b9_self_scan_runs_fewer_regex_passes_and_renders_the_same() -> None:
    on_tally: Counter = Counter()
    off_tally: Counter = Counter()
    on_code, on_doc = _self_scan(memo=True, tally=on_tally)
    off_code, off_doc = _self_scan(memo=False, tally=off_tally)
    assert on_code == off_code
    assert on_doc == off_doc, "the memo moved the scan document"
    assert on_doc.endswith("\n") and not on_doc.endswith("\n\n")
    assert off_tally["__all__"] > 0, "premise: the counting seam saw no pass"
    assert on_tally["__all__"] < off_tally["__all__"], (
        on_tally["__all__"], off_tally["__all__"])
    _no_open_frame()
