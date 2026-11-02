"""Iteration 376 behaviors: the literal prefilter is memoised per (path, literal).

Inside one `read_cache_scope` (one scan) each `literal in folded` prefilter
question for a given (path, literal) pair is answered at most once, and the
scan's output does not move by a byte. The brake is a COUNTING seam, never a
wall-clock assertion: a `str` subclass returned from a monkeypatched
`checks._folded` counts `__contains__` per pair.

Every live-repo scan here is a monkeypatch/counting site, so it runs direct
in-process `cli.main` and deliberately bypasses `tests/_selfscan.py`'s cache.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
from collections import Counter

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]


class _CountingStr(str):
    """A fold that tallies every `literal in self` against its path."""

    path: pathlib.Path
    tally: Counter

    def __contains__(self, literal: object) -> bool:
        self.tally[(self.path, literal)] += 1
        return str.__contains__(self, literal)


def _scan(argv: list[str], *, memo: bool, tally: Counter | None = None) -> tuple[int, str]:
    """One in-process scan of the live repo, memo on or off, optionally counted."""
    real_folded = checks._folded

    def counting_folded(path: pathlib.Path, text: str) -> str:
        folded = _CountingStr(real_folded(path, text))
        folded.path = path
        folded.tally = tally
        return folded

    out = io.StringIO()
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(REPO)
        if not memo:
            mp.setattr(checks, "_literal_hits", lambda path: None)
        if tally is not None:
            mp.setattr(checks, "_folded", counting_folded)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main(argv)
    return code, out.getvalue()


@pytest.fixture(scope="module")
def live() -> dict[str, object]:
    """Four live scans shared by behaviors 1-4: memo on/off x text/json."""
    on_tally: Counter = Counter()
    off_tally: Counter = Counter()
    return {
        "text_on": _scan(["scan", "."], memo=True, tally=on_tally),
        "text_off": _scan(["scan", "."], memo=False, tally=off_tally),
        "json_on": _scan(["scan", ".", "--json"], memo=True),
        "json_off": _scan(["scan", ".", "--json"], memo=False),
        "on_tally": on_tally,
        "off_tally": off_tally,
    }


# --- Behaviors 1-4: live repo -------------------------------------------------


def test_b1_text_byte_identical_memo_on_and_off(live) -> None:
    code_on, out_on = live["text_on"]
    code_off, out_off = live["text_off"]
    assert out_on, "the live text scan printed nothing"
    assert out_on.encode() == out_off.encode()
    assert code_on == code_off


def test_b2_json_byte_identical_memo_on_and_off(live) -> None:
    code_on, out_on = live["json_on"]
    code_off, out_off = live["json_off"]
    assert out_on.lstrip().startswith("{")
    assert out_on.encode() == out_off.encode()
    assert code_on == code_off


def test_b3_each_pair_asked_at_most_once(live) -> None:
    tally: Counter = live["on_tally"]
    assert tally, "the counting harness saw no prefilter test at all"
    repeated = {pair: n for pair, n in tally.items() if n > 1}
    assert repeated == {}


def test_b4_census_not_vacuous(live) -> None:
    on_tally: Counter = live["on_tally"]
    off_tally: Counter = live["off_tally"]
    assert max(off_tally.values()) >= 2
    assert sum(on_tally.values()) < sum(off_tally.values())
    # Same questions asked, only fewer times: the memo drops no pair.
    assert set(on_tally) == set(off_tally)


# --- Behaviors 5-8: scope and unit semantics ------------------------------------


def test_b5_scope_lifetime() -> None:
    assert checks._LITERAL_HIT_STACK == []
    with checks.read_cache_scope():
        assert len(checks._LITERAL_HIT_STACK) == 1
        outer = checks._LITERAL_HIT_STACK[0]
        with checks.read_cache_scope():
            assert len(checks._LITERAL_HIT_STACK) == 2
            assert checks._LITERAL_HIT_STACK[-1] is not outer
        assert len(checks._LITERAL_HIT_STACK) == 1
        assert checks._LITERAL_HIT_STACK[0] is outer
    assert checks._LITERAL_HIT_STACK == []
    with pytest.raises(RuntimeError):
        with checks.read_cache_scope():
            raise RuntimeError("boom")
    assert checks._LITERAL_HIT_STACK == []


def test_b5_stack_empty_after_a_scan(tmp_path: pathlib.Path, capsys) -> None:
    (tmp_path / "agent.py").write_text("print('hello')\n", encoding="utf-8")
    assert checks._LITERAL_HIT_STACK == []
    main(["scan", str(tmp_path)])
    capsys.readouterr()
    assert checks._LITERAL_HIT_STACK == []


def _rule() -> dict:
    return {"kind": "content_matches", "globs": ["**/*.py"],
            "pattern": "dangerous_call"}


def test_b6_no_scope_no_memo(tmp_path: pathlib.Path) -> None:
    assert checks._LITERAL_HIT_STACK == []
    assert checks._literal_hits(tmp_path / "any.py") is None
    assert checks._contains("abc", "b", None) is True
    assert checks._contains("abc", "z", None) is False
    source = tmp_path / "agent.py"
    source.write_text("dangerous_call()\n", encoding="utf-8")
    assert checks.evaluate(_rule(), tmp_path).matched is True
    source.write_text("safe_call()\n", encoding="utf-8")
    assert checks.evaluate(_rule(), tmp_path).matched is False


def test_b7_fresh_text_per_scope(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "agent.py"
    source.write_text("safe_call()\n", encoding="utf-8")
    with checks.read_cache_scope():
        assert checks.evaluate(_rule(), tmp_path).matched is False
    source.write_text("dangerous_call()\n", encoding="utf-8")
    with checks.read_cache_scope():
        # a memo carried across scopes would replay the scope-1 False and
        # skip the file: a fail-open false negative
        assert checks.evaluate(_rule(), tmp_path).matched is True


def test_b7_fresh_text_per_scope_present_then_absent(
        tmp_path: pathlib.Path) -> None:
    source = tmp_path / "agent.py"
    source.write_text("dangerous_call()\n", encoding="utf-8")
    with checks.read_cache_scope():
        assert checks.evaluate(_rule(), tmp_path).matched is True
    source.write_text("safe_call()\n", encoding="utf-8")
    with checks.read_cache_scope():
        assert checks.evaluate(_rule(), tmp_path).matched is False


def test_b8_memo_answers_equal_direct_answers(tmp_path: pathlib.Path) -> None:
    folded = "def run(): dangerous_call()\n"
    with checks.read_cache_scope():
        hits = checks._literal_hits(tmp_path / "agent.py")
        assert hits == {}
        assert checks._literal_hits(tmp_path / "agent.py") is hits
        for literal in ("dangerous_call", "checkpoint_write"):
            first = checks._contains(folded, literal, hits)
            assert first is (literal in folded)
            assert hits[literal] is first
            assert checks._contains(folded, literal, hits) is first
