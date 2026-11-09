"""Iteration 376 behaviors: the literal prefilter is memoised per (path, literal).

Inside one `read_cache_scope` (one scan) each `literal in folded` prefilter
question for a given (path, literal) pair is answered at most once, and the
scan's output does not move by a byte. The brake is a COUNTING seam, never a
wall-clock assertion: a `str` subclass returned from a monkeypatched
`checks._folded` counts `__contains__` per pair.

Every live-repo scan here is a monkeypatch/counting site, so it runs direct
in-process `cli.main` and deliberately bypasses `tests/_selfscan.py`'s cache.
The shared `live` fixture is lazy, scanning only the arms a node reads, because
a module scope is per worker under `--dist worksteal`.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
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


#: Every real scan the lazy fixture makes, keyed by (argv, memo): the counting brake.
SCANS: Counter = Counter()

_ARMS: dict[str, tuple[list[str], bool, bool]] = {
    "text_on": (["scan", "."], True, True),
    "text_off": (["scan", "."], False, True),
    "json_on": (["scan", ".", "--json"], True, False),
    "json_off": (["scan", ".", "--json"], False, False),
}
_TALLY_OF = {"on_tally": "text_on", "off_tally": "text_off"}
_TALLY_KEY = {arm: key for key, arm in _TALLY_OF.items()}


class _LazyLive:
    """Each arm is scanned the first time a node reads it, at most once.

    A module scope is per WORKER under `--dist worksteal`, so an eager fixture
    made every worker that drew any of b1-b4 pay all four scans; now a worker
    pays only for the arms its own nodes read.
    """

    def __init__(self, counter: Counter) -> None:
        self.counter = counter
        self._done: dict[str, object] = {}

    def __getitem__(self, key: str) -> object:
        arm = _TALLY_OF.get(key, key)
        if arm not in self._done:
            argv, memo, counted = _ARMS[arm]
            tally: Counter | None = Counter() if counted else None
            self.counter[(tuple(argv), memo)] += 1
            self._done[arm] = _scan(argv, memo=memo, tally=tally)
            if tally is not None:
                self._done[_TALLY_KEY[arm]] = tally
        return self._done[key]


@pytest.fixture(scope="module")
def live() -> _LazyLive:
    """The four live scans shared by behaviors 1-4, computed lazily per arm."""
    return _LazyLive(SCANS)


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


def test_b9_each_arm_scanned_at_most_once_per_worker(live) -> None:
    for key in ("text_on", "on_tally", "text_on"):
        live[key]
    assert SCANS, "the lazy fixture made no scan at all"
    assert {k: n for k, n in SCANS.items() if n > 1} == {}


def test_b9_laziness_not_vacuous(monkeypatch) -> None:
    monkeypatch.setattr(sys.modules[__name__], "_scan", lambda argv, *, memo, tally=None: (0, "{}"))
    own: Counter = Counter()
    lazy = _LazyLive(own)
    lazy["json_on"]
    assert own == Counter({(("scan", ".", "--json"), True): 1})


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


# --- Tester (iter 388): the lazy fixture, black-box over a stubbed scan -------

#: The node names HEAD `2c01af8` collected from this module (behavior 1).
_HEAD_NODES = frozenset({
    "test_b1_text_byte_identical_memo_on_and_off",
    "test_b2_json_byte_identical_memo_on_and_off",
    "test_b3_each_pair_asked_at_most_once",
    "test_b4_census_not_vacuous",
    "test_b5_scope_lifetime",
    "test_b5_stack_empty_after_a_scan",
    "test_b6_no_scope_no_memo",
    "test_b7_fresh_text_per_scope",
    "test_b7_fresh_text_per_scope_present_then_absent",
    "test_b8_memo_answers_equal_direct_answers",
})

_TEXT_ON = (("scan", "."), True)
_TEXT_OFF = (("scan", "."), False)
_JSON_ON = (("scan", ".", "--json"), True)
_JSON_OFF = (("scan", ".", "--json"), False)


def _stubbed(monkeypatch) -> tuple[_LazyLive, Counter, list]:
    """A fresh lazy instance over a stub `_scan` that records each real call."""
    calls: list = []

    def fake(argv, *, memo, tally=None):
        calls.append((tuple(argv), memo, tally is not None))
        if tally is not None:
            tally[("p", "lit", len(calls))] += 1
        return len(calls), f"out-{len(calls)}"

    monkeypatch.setattr(sys.modules[__name__], "_scan", fake)
    own: Counter = Counter()
    return _LazyLive(own), own, calls


def test_tester_b1_head_nodes_all_still_defined() -> None:
    here = {name for name in globals() if name.startswith("test_")}
    assert _HEAD_NODES <= here
    new = here - _HEAD_NODES
    assert all(n.startswith(("test_b9_", "test_tester_")) for n in new), new


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("json_on", "json_off"), {_JSON_ON: 1, _JSON_OFF: 1}),
        (("on_tally",), {_TEXT_ON: 1}),
        (("text_on",), {_TEXT_ON: 1}),
        (("on_tally", "text_on"), {_TEXT_ON: 1}),
        (("off_tally", "on_tally"), {_TEXT_ON: 1, _TEXT_OFF: 1}),
        (("json_on",), {_JSON_ON: 1}),
    ],
)
def test_tester_b3_only_the_read_arms_are_scanned(monkeypatch, keys, expected) -> None:
    lazy, own, calls = _stubbed(monkeypatch)
    for key in keys:
        lazy[key]
    assert own == Counter(expected)
    assert len(calls) == sum(expected.values())


def test_tester_b3_json_reads_trigger_zero_text_scans(monkeypatch) -> None:
    lazy, own, calls = _stubbed(monkeypatch)
    lazy["json_on"], lazy["json_off"]
    assert [c for c in calls if "--json" not in c[0]] == []
    assert all(not counted for _, _, counted in calls)


def test_tester_b4_whole_module_reads_cost_exactly_four(monkeypatch) -> None:
    lazy, own, calls = _stubbed(monkeypatch)
    for _ in range(3):
        for key in ("text_on", "text_off", "json_on", "json_off",
                    "on_tally", "off_tally"):
            lazy[key]
    assert own == Counter({_TEXT_ON: 1, _TEXT_OFF: 1, _JSON_ON: 1, _JSON_OFF: 1})
    assert len(calls) == 4
    # only the text arms are scanned with a tally
    assert sorted(c for _, _, c in calls) == [False, False, True, True]


def test_tester_b4_repeat_reads_return_the_same_objects(monkeypatch) -> None:
    lazy, _own, _calls = _stubbed(monkeypatch)
    first = lazy["text_on"]
    tally = lazy["on_tally"]
    assert lazy["text_on"] is first
    assert lazy["on_tally"] is tally
    assert isinstance(tally, Counter) and tally


def test_tester_b4_tally_belongs_to_its_own_text_arm(monkeypatch) -> None:
    lazy, _own, _calls = _stubbed(monkeypatch)
    off = lazy["off_tally"]
    on = lazy["on_tally"]
    assert on is not off
    assert lazy["text_off"][0] == 1  # the off tally came from the first scan
    assert lazy["text_on"][0] == 2


def test_tester_b5_instances_do_not_share_state(monkeypatch) -> None:
    lazy_a, own_a, calls = _stubbed(monkeypatch)
    lazy_a["json_on"]
    own_b: Counter = Counter()
    lazy_b = _LazyLive(own_b)
    lazy_b["json_on"]
    assert own_a == Counter({_JSON_ON: 1})
    assert own_b == Counter({_JSON_ON: 1})
    assert len(calls) == 2


def test_tester_b5_unknown_arm_is_a_key_error(monkeypatch) -> None:
    lazy, own, calls = _stubbed(monkeypatch)
    with pytest.raises(KeyError):
        lazy["text_sideways"]
    assert calls == [] and sum(own.values()) == 0


def test_tester_b5_counting_nodes_never_time() -> None:
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(sys.modules[__name__]))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    clocks = {"time", "timeit", "datetime"}
    assert imported & clocks == set()


def test_tester_b8_docstring_keeps_bypass_and_gains_lazy_reason() -> None:
    doc = " ".join((sys.modules[__name__].__doc__ or "").split())
    assert "bypasses `tests/_selfscan.py`'s cache" in doc
    assert "monkeypatch/counting site" in doc
    assert "lazy" in doc
    assert "per worker" in doc and "worksteal" in doc
