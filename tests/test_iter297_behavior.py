"""Iteration 297 behavior tests (black-box; spec: state/iter-297/pm.md).

Feature: the fixed-argv live self-scan spawn in `tests/test_iter91_behavior.py` is memoized at
module scope behind `_live_scan()`, with `fresh=True` as the escape the two tests whose claim
is about the SPAWN itself (determinism, writes-nothing) use so they still cause real processes.
No assertion in that file moves, no test is deleted, renamed or skipped, the process boundary
stays a `subprocess.run`, and nothing outside that file but the roadmap ledger changes.

ISOLATION CONTRACT HONORED: nothing here read `src/`, `tools/` text, the engineer's or
reviewer's notes, `IMPLEMENTATION.patch`, or a diff of any source file. Expectations come from
`pm.md`. The control arm is the TARGET TEST FILE ITSELF as `PRECHANGE_COMMIT` committed it,
read from this repo's object store with `git show` -- test text, which the contract names as
readable -- and compared by AST so comments and whitespace are not what is being graded. The
memo is proven by IMPORTING the target as a module and counting the calls its tests make to
`subprocess.run` under a counting stand-in, never by reading the helper as logic.

Behavior 5's WALL (serial duration before/after) is not asserted here: a duration taken under
the xdist suite's load is noise (a lone after-arm has read slower than the engineer's before).
It is MEASURED out-of-suite and quoted in `tester.md`; what this file pins is the MECHANISM
that makes the wall drop -- warm readers spawn zero processes, the memo hands back the identical
object, `fresh=True` neither reads nor writes it.

Behavior 7 (nothing outside the target and the ledger changes; `src/`, `docs/`, `tools/`,
`README.md` byte-identical to `PRECHANGE_COMMIT`) is a statement about THIS iteration's diff
and would go red the moment a later iteration touches `src/`, so it is measured once in
`tester.md` (blob hashes) rather than committed as a brake.
"""

from __future__ import annotations

import ast
import collections
import copy
import difflib
import importlib
import inspect
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TARGET_REL = "tests/test_iter91_behavior.py"
TARGET = REPO / TARGET_REL

#: The commit immediately before this iteration's change (control arm).
PRECHANGE_COMMIT = "34db28f"

#: Collected node count of the target at `PRECHANGE_COMMIT`, quoted by the spec and
#: re-derived below from the control arm's own AST (behavior 1).
PRECHANGE_COLLECTED = 107

HELPER = "_live_scan"
FRESH_KW = "fresh"

#: The two tests whose claim is about the SPAWN, so they must escape the memo (behaviors 3, 4).
DETERMINISM_TEST = "test_b1_the_scan_is_deterministic_across_runs"
WRITES_NOTHING_TEST = "test_b14_a_live_scan_writes_nothing_to_the_files_it_reads"


# ---------------------------------------------------------------------------
# helpers -- both arms of the target as text and as AST
# ---------------------------------------------------------------------------


def _prechange_text() -> str:
    """`TARGET_REL` as `PRECHANGE_COMMIT` committed it, from this repo's object store."""
    proc = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{PRECHANGE_COMMIT}:{TARGET_REL}"],
        capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, (
        f"cannot read {TARGET_REL} at {PRECHANGE_COMMIT}: {proc.stderr!r}")
    return proc.stdout


def _live_text() -> str:
    return TARGET.read_text(encoding="utf-8")


def _tests_of(mod: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in mod.body
            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def _top_functions(mod: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in mod.body if isinstance(n, ast.FunctionDef)}


def _helper_calls(node: ast.AST) -> list[ast.Call]:
    """Every `_live_scan(...)` call inside `node`, in source order."""
    return [c for c in ast.walk(node)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name) and c.func.id == HELPER]


def _spawn_calls(node: ast.AST) -> list[ast.Call]:
    """Every `subprocess.run(...)` call inside `node`."""
    return [c for c in ast.walk(node)
            if isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute) and c.func.attr == "run"
            and isinstance(c.func.value, ast.Name) and c.func.value.id == "subprocess"]


class _DropHelperKeywords(ast.NodeTransformer):
    """Erase the keywords of `_live_scan(...)` calls, so `fresh=True` is the ONE thing a
    test body may differ by."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == HELPER:
            node.keywords = []
        return node


def _normalized(node: ast.AST) -> str:
    return ast.dump(_DropHelperKeywords().visit(copy.deepcopy(node)))


def _literal_constants(mod: ast.Module) -> dict[str, object]:
    """Module-level `NAME = <literal>` bindings, so a parametrize that names a constant
    (`PATH_RULE_NAMES`) can be sized without importing the module."""
    out: dict[str, object] = {}
    for n in mod.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name):
            try:
                out[n.targets[0].id] = ast.literal_eval(n.value)
            except ValueError:
                continue
    return out


def _expansion(func: ast.FunctionDef, consts: dict[str, object]) -> int:
    """How many nodes pytest collects from `func`: the product of its parametrize arities."""
    n = 1
    for deco in func.decorator_list:
        if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                and deco.func.attr == "parametrize"):
            values = deco.args[1] if len(deco.args) > 1 else next(
                kw.value for kw in deco.keywords if kw.arg in ("argvalues", "values"))
            if isinstance(values, ast.Name):
                n *= len(consts[values.id])
            else:
                assert isinstance(values, (ast.List, ast.Tuple)), ast.dump(deco)
                n *= len(values.elts)
    return n


def _collected(mod: ast.Module) -> int:
    consts = _literal_constants(mod)
    return sum(_expansion(f, consts) for f in _tests_of(mod).values())


def _is_fresh_true(call: ast.Call) -> bool:
    return (not call.args and len(call.keywords) == 1
            and call.keywords[0].arg == FRESH_KW
            and isinstance(call.keywords[0].value, ast.Constant)
            and call.keywords[0].value.value is True)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def prechange() -> ast.Module:
    return ast.parse(_prechange_text())


@pytest.fixture(scope="module")
def live() -> ast.Module:
    return ast.parse(_live_text())


@pytest.fixture(scope="module")
def t91():
    """The target imported as a module: the same object pytest's collector holds, so the
    memo dict this file inspects is the one the target's own tests fill."""
    return importlib.import_module("test_iter91_behavior")


@pytest.fixture(scope="module")
def cache_name(prechange, live) -> str:
    """The ONE module-level name this iteration added (behavior 2), found structurally."""
    def names(mod):
        out = []
        for n in mod.body:
            if isinstance(n, ast.Assign):
                out += [t.id for t in n.targets if isinstance(t, ast.Name)]
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                out.append(n.target.id)
            elif isinstance(n, ast.FunctionDef):
                out.append(n.name)
        return out
    added = [n for n in names(live) if n not in names(prechange)]
    assert len(added) == 1, f"expected exactly one added module-level name, got {added}"
    return added[0]


@pytest.fixture(scope="module")
def warm(t91, cache_name) -> subprocess.CompletedProcess:
    """One REAL memoized spawn, so every reader below can be graded on a warm memo."""
    proc = t91._live_scan()
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    cache = getattr(t91, cache_name)
    assert isinstance(cache, dict) and cache, "the warm spawn did not fill the module memo"
    return proc


@pytest.fixture(scope="module")
def serial_run() -> subprocess.CompletedProcess:
    """`pytest <target> -n 0 -q` as the spec quotes it, with the ini `addopts` cleared so
    the nested run does not inherit `-n auto` and prints its ONE summary line."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", TARGET_REL, "-n", "0", "-q",
         "-p", "no:cacheprovider", "-o", "addopts="],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")


def _counting_run(recorded: list, factory):
    """A `subprocess.run` stand-in that records every argv and returns `factory()`."""
    def run(argv, **kwargs):
        recorded.append((list(argv), kwargs))
        return factory()
    return run


def _fake_proc() -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="fake\n", stderr="")


# ===========================================================================
# B1  The file still runs green serially with the pre-change collected count,
#     and no test is deleted, renamed or skipped.
# ===========================================================================


def test_b1_the_target_runs_green_serially_with_the_prechange_count(serial_run):
    tail = [ln for ln in serial_run.stdout.splitlines() if ln.strip()]
    assert serial_run.returncode == 0, (
        f"stdout tail={tail[-5:]!r} stderr={serial_run.stderr!r}")
    summary = tail[-1]
    m = re.fullmatch(r"(\d+) passed in [0-9.]+s", summary)
    assert m, f"summary line is not `N passed in Xs`: {summary!r}"
    assert int(m.group(1)) == PRECHANGE_COLLECTED
    for word in ("skipped", "xfailed", "deselected", "error", "failed"):
        assert word not in summary


def test_b1_the_prechange_arm_collects_the_quoted_count(prechange):
    """The 107 is re-derived from the control arm's own AST, not trusted from the spec."""
    assert _collected(prechange) == PRECHANGE_COLLECTED


def test_b1_no_test_is_deleted_renamed_or_re_parametrized(prechange, live):
    before, after = _tests_of(prechange), _tests_of(live)
    assert list(before) == list(after), (
        f"missing={sorted(set(before) - set(after))} "
        f"added={sorted(set(after) - set(before))}")
    bc, ac = _literal_constants(prechange), _literal_constants(live)
    for name, func in before.items():
        assert _expansion(func, bc) == _expansion(after[name], ac), name
    assert _collected(live) == PRECHANGE_COLLECTED


def test_b1_no_skip_or_xfail_entered_the_target(live):
    text = _live_text()
    assert not re.search(r"\b(skip|skipif|xfail|importorskip)\b", text)
    for func in _tests_of(live).values():
        assert all(not (isinstance(d, ast.Attribute) and d.attr in ("skip", "xfail"))
                   for d in ast.walk(ast.Module(body=func.decorator_list, type_ignores=[])))


# ---- B1 by pytest's OWN collection. The 107 above is re-derived by THIS file's model of
#      `parametrize` arities on both arms, so a parametrize the model mis-sizes would agree
#      with itself; `--collect-only -q` on the live target is the thing itself.


@pytest.fixture(scope="module")
def collected() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", TARGET_REL, "--collect-only", "-q",
         "-p", "no:cacheprovider", "-o", "addopts="],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8")


def _node_ids(collected: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in collected.stdout.splitlines() if ln.startswith(f"{TARGET_REL}::")]


def test_b1_pytest_itself_collects_the_quoted_count_from_the_live_target(collected):
    assert collected.returncode == 0, collected.stderr
    ids = _node_ids(collected)
    assert len(ids) == PRECHANGE_COLLECTED, len(ids)
    tail = [ln for ln in collected.stdout.splitlines() if ln.strip()][-1]
    m = re.fullmatch(r"(\d+) tests? collected in [0-9.]+s", tail)
    assert m and int(m.group(1)) == PRECHANGE_COLLECTED, tail
    assert "deselected" not in tail and "error" not in tail


def test_b1_pytest_collection_names_the_prechange_tests_with_their_prechange_arities(
        collected, prechange):
    """Per test function, the number of node ids pytest collects equals the arity the
    control arm's AST predicts: the same tests, each expanded the same number of times."""
    per_test = collections.Counter(nid.split("::", 1)[1].split("[", 1)[0]
                                   for nid in _node_ids(collected))
    consts = _literal_constants(prechange)
    expected = {name: _expansion(f, consts) for name, f in _tests_of(prechange).items()}
    assert dict(per_test) == expected, {
        "missing": sorted(set(expected) - set(per_test)),
        "added": sorted(set(per_test) - set(expected)),
        "resized": sorted(n for n in expected if n in per_test and per_test[n] != expected[n])}
    # pytest saw every collected id as runnable: nothing in the file is marked skip/xfail
    assert all(("skip" not in nid.lower() and "xfail" not in nid.lower())
               for nid in _node_ids(collected))


# ===========================================================================
# B2  Every assertion body is unchanged: the only deltas are the helper, ONE
#     module-level cache, and call sites that now pass `fresh=True`.
# ===========================================================================


def test_b2_every_test_body_is_unchanged_up_to_the_fresh_keyword(prechange, live):
    before, after = _tests_of(prechange), _tests_of(live)
    changed = [n for n in before if _normalized(before[n]) != _normalized(after[n])]
    assert changed == [], changed


def test_b2_every_assert_statement_is_byte_for_byte_the_same_ast(prechange, live):
    """Stronger than the normalized compare for the statements that GRADE: no `assert`
    gained, lost, or reworded anywhere in the file."""
    def asserts(mod):
        return [ast.dump(a) for a in ast.walk(mod) if isinstance(a, ast.Assert)]
    assert asserts(prechange) == asserts(live)


def test_b2_the_only_call_sites_that_moved_pass_fresh_true(prechange, live):
    before, after = _tests_of(prechange), _tests_of(live)
    moved = []
    for name in before:
        b, a = _helper_calls(before[name]), _helper_calls(after[name])
        assert len(b) == len(a), f"{name}: helper call count moved {len(b)} -> {len(a)}"
        for x, y in zip(b, a):
            if ast.dump(x) != ast.dump(y):
                assert not x.keywords, f"{name}: the pre-change call already had keywords"
                assert _is_fresh_true(y), f"{name}: moved call is not `{HELPER}(fresh=True)`"
                moved.append(name)
    assert sorted(set(moved)) == sorted({DETERMINISM_TEST, WRITES_NOTHING_TEST})


def test_b2_module_level_changed_only_by_the_helper_and_one_cache(prechange, live, cache_name):
    def rest(mod):
        out = []
        for n in mod.body:
            if isinstance(n, ast.FunctionDef) and (n.name.startswith("test_") or n.name == HELPER):
                continue
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                    and n.target.id == cache_name:
                continue
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == cache_name for t in n.targets):
                continue
            out.append(ast.dump(n))
        return out
    assert rest(prechange) == rest(live), "a module-level statement outside the bite moved"
    assert HELPER in _top_functions(live) and HELPER in _top_functions(prechange)


def test_b2_the_cache_is_a_module_level_dict(t91, cache_name):
    assert isinstance(getattr(t91, cache_name), dict)


# ---- B2 at LINE level: the spec's literal statement ("touches only the helper definition,
#      a module-level cache, and call sites that pass fresh=True"). The AST compares above
#      would let a stray comment or docstring edit elsewhere in the file through; this one
#      would not. Both arms are TEST text; the diff is computed here, not read from git.


def _span(node: ast.AST) -> range:
    return range(node.lineno, node.end_lineno + 1)


def _is_cache_binding(n: ast.stmt, cache_name: str) -> bool:
    if isinstance(n, ast.AnnAssign):
        return isinstance(n.target, ast.Name) and n.target.id == cache_name
    if isinstance(n, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == cache_name for t in n.targets)
    return False


def _allowed_after_lines(live: ast.Module, live_lines: list[str], cache_name: str) -> set[int]:
    """1-based line numbers of the AFTER arm a changed line may land on: the helper body,
    the cache binding, and the run of `#` comment lines that introduces the cache (the most
    reasonable reading of "a module-level cache" includes the comment attached to it)."""
    allowed: set[int] = set(_span(_top_functions(live)[HELPER]))
    for n in live.body:
        if _is_cache_binding(n, cache_name):
            allowed |= set(_span(n))
            i = n.lineno - 1
            while i >= 1 and live_lines[i - 1].lstrip().startswith("#"):
                allowed.add(i)
                i -= 1
    return allowed


def test_b2_every_changed_line_is_inside_the_helper_the_cache_or_a_fresh_call_site(
        prechange, live, cache_name):
    before_lines, after_lines = _prechange_text().splitlines(), _live_text().splitlines()
    allowed_before = set(_span(_top_functions(prechange)[HELPER]))
    allowed_after = _allowed_after_lines(live, after_lines, cache_name)
    fresh_site, plain_site = f"{HELPER}({FRESH_KW}=True)", f"{HELPER}()"
    sm = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)
    offenders: list[tuple[str, int, str]] = []
    call_site_lines: list[int] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        removed = [(i + 1, before_lines[i]) for i in range(i1, i2)]
        added = [(j + 1, after_lines[j]) for j in range(j1, j2)]
        # a call-site hunk: same line count and each pair differs ONLY by the fresh keyword
        if tag == "replace" and len(removed) == len(added) and all(
                fresh_site in a and a.replace(fresh_site, plain_site) == b
                for (_, b), (_, a) in zip(removed, added)):
            call_site_lines += [ln for ln, _ in added]
            continue
        offenders += [("-", ln, t) for ln, t in removed if t.strip() and ln not in allowed_before]
        offenders += [("+", ln, t) for ln, t in added if t.strip() and ln not in allowed_after]
    assert offenders == [], offenders
    # the call-site lines are exactly the fresh=True calls the AST tests located
    fresh_call_lines = sorted(
        c.lineno for func in _tests_of(live).values()
        for c in _helper_calls(func) if _is_fresh_true(c))
    assert sorted(set(call_site_lines)) == sorted(set(fresh_call_lines))


def test_b2_the_prechange_helper_took_no_arguments_and_the_live_one_takes_only_fresh(
        prechange, t91):
    """The escape is NEW and it is the ONLY thing the helper's interface gained."""
    before = _top_functions(prechange)[HELPER].args
    assert not (before.args or before.kwonlyargs or before.vararg or before.kwarg)
    sig = inspect.signature(t91._live_scan)
    assert list(sig.parameters) == [FRESH_KW]
    param = sig.parameters[FRESH_KW]
    assert param.default is False, "the default path must be the memo, not the spawn"
    assert param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD)


# ===========================================================================
# B3  The determinism test still performs TWO real spawns: both of its calls
#     are `_live_scan(fresh=True)`, and under a counting `subprocess.run`
#     it spawns exactly twice without touching the memo.
# ===========================================================================


def test_b3_the_determinism_test_calls_the_helper_twice_with_fresh_true(live):
    calls = _helper_calls(_tests_of(live)[DETERMINISM_TEST])
    assert len(calls) == 2
    assert all(_is_fresh_true(c) for c in calls)


def test_b3_a_grep_of_the_determinism_test_shows_exactly_two_fresh_calls(live):
    seg = ast.get_source_segment(_live_text(), _tests_of(live)[DETERMINISM_TEST])
    assert seg.count(f"{HELPER}({FRESH_KW}=True)") == 2
    assert seg.count(f"{HELPER}()") == 0


def test_b3_the_determinism_test_spawns_twice_and_leaves_the_memo_alone(
        t91, cache_name, warm, monkeypatch):
    cache = getattr(t91, cache_name)
    snapshot = dict(cache)
    recorded: list = []
    monkeypatch.setattr(t91.subprocess, "run", _counting_run(recorded, _fake_proc))
    getattr(t91, DETERMINISM_TEST)()
    assert len(recorded) == 2, f"expected two spawns, saw {len(recorded)}"
    for argv, kwargs in recorded:
        assert argv == [sys.executable, str(t91.TOOL), str(REPO)], argv
        assert kwargs.get("cwd") == str(REPO)
    assert cache == snapshot and all(cache[k] is snapshot[k] for k in snapshot), (
        "fresh=True must neither read nor write the memo")


# ===========================================================================
# B4  The writes-nothing test calls `_live_scan(fresh=True)`: a memoized
#     result cannot observe a write, so it must cause exactly one spawn.
# ===========================================================================


def test_b4_the_writes_nothing_test_calls_the_helper_once_with_fresh_true(live):
    calls = _helper_calls(_tests_of(live)[WRITES_NOTHING_TEST])
    assert len(calls) == 1 and _is_fresh_true(calls[0])


def test_b4_the_writes_nothing_test_spawns_once_on_a_warm_memo(
        t91, cache_name, warm, monkeypatch):
    cache = getattr(t91, cache_name)
    snapshot = dict(cache)
    recorded: list = []
    monkeypatch.setattr(t91.subprocess, "run", _counting_run(recorded, _fake_proc))
    getattr(t91, WRITES_NOTHING_TEST)()
    assert len(recorded) == 1, f"expected one spawn, saw {len(recorded)}"
    assert recorded[0][0] == [sys.executable, str(t91.TOOL), str(REPO)]
    assert cache == snapshot and all(cache[k] is snapshot[k] for k in snapshot)


def test_b4_only_the_two_spawn_claim_tests_escape_the_memo(live):
    """Every OTHER caller reads the memo; the escape is not sprinkled where it buys nothing."""
    fresh_callers = sorted(
        name for name, func in _tests_of(live).items()
        if any(_is_fresh_true(c) for c in _helper_calls(func)))
    assert fresh_callers == sorted({DETERMINISM_TEST, WRITES_NOTHING_TEST})
    for name, func in _tests_of(live).items():
        for c in _helper_calls(func):
            assert not c.args, f"{name}: the helper takes no positional argument"
            assert _is_fresh_true(c) or not c.keywords, f"{name}: unexpected keywords"


# ===========================================================================
# B5  The mechanism behind the lower wall: a warm memo hands its readers the
#     identical object and they spawn NOTHING; `fresh=True` returns a new
#     object whose bytes agree with the memo (the product's determinism).
#     The wall itself is measured out-of-suite and quoted in tester.md.
# ===========================================================================


def _memo_readers(live: ast.Module) -> list[str]:
    return [name for name, func in _tests_of(live).items()
            if _helper_calls(func) and not any(_is_fresh_true(c) for c in _helper_calls(func))]


def test_b5_the_target_still_has_readers_that_share_the_memo(live):
    readers = _memo_readers(live)
    assert len(readers) >= 4, readers
    for name in readers:
        assert not _tests_of(live)[name].args.args, f"{name} takes fixtures; cannot be called bare"


def test_b5_warm_readers_spawn_zero_processes(t91, live, warm, monkeypatch):
    """Readers may still ask git for the domain (`git ls-files`); what they may not do is
    spawn the TOOL again, so only the radar argv is refused and everything else passes
    through to the real `subprocess.run`."""
    real_run = subprocess.run

    def refuse_tool(argv, **kwargs):
        argv = list(argv)
        if argv[:1] == [sys.executable] and str(t91.TOOL) in argv:
            raise AssertionError(f"a memo reader spawned the tool: {argv!r}")
        return real_run(argv, **kwargs)
    monkeypatch.setattr(t91.subprocess, "run", refuse_tool)
    # the readers that only ever needed the RESULT must pass on the memo alone
    for name in _memo_readers(live):
        getattr(t91, name)()


def test_b5_the_memo_returns_the_identical_object_and_fresh_returns_a_new_one(t91, warm):
    a, b = t91._live_scan(), t91._live_scan()
    assert a is b is warm
    c = t91._live_scan(fresh=True)
    assert c is not a
    assert (c.stdout, c.stderr, c.returncode) == (a.stdout, a.stderr, a.returncode) == (
        a.stdout, "", 0)


def test_b5_the_memo_holds_exactly_the_one_fixed_argv_result(t91, cache_name, warm):
    cache = getattr(t91, cache_name)
    assert len(cache) == 1
    assert next(iter(cache.values())) is warm


def test_b5_a_cold_memo_spawns_exactly_once_however_many_plain_readers_follow(
        t91, cache_name, warm, monkeypatch):
    """The warm-memo tests above prove identity on a memo the fixture filled; this one starts
    COLD under a counting stand-in, so the spawn count itself is the assertion: one spawn
    for three plain calls, one entry, and `fresh=True` on top still spawns per call."""
    cache = getattr(t91, cache_name)
    saved = dict(cache)
    recorded: list = []
    monkeypatch.setattr(t91.subprocess, "run", _counting_run(recorded, _fake_proc))
    cache.clear()
    try:
        first = t91._live_scan()
        second, third = t91._live_scan(), t91._live_scan()
        assert len(recorded) == 1, f"a cold memo must spawn exactly once, saw {len(recorded)}"
        assert recorded[0][0] == [sys.executable, str(t91.TOOL), str(REPO)]
        assert first is second is third
        assert len(cache) == 1 and next(iter(cache.values())) is first
        a, b = t91._live_scan(fresh=True), t91._live_scan(fresh=True)
        assert len(recorded) == 3, f"two fresh calls must add two spawns, saw {len(recorded)}"
        assert a is not b and a is not first
        assert len(cache) == 1 and next(iter(cache.values())) is first, (
            "fresh=True must not overwrite the memo")
    finally:
        cache.clear()
        cache.update(saved)
    assert next(iter(cache.values())) is warm


# ===========================================================================
# B6  The process boundary is kept: the spawn is still `subprocess.run`
#     inside `_live_scan`, and nothing in the file was converted to an
#     in-process `main`.
# ===========================================================================


def test_b6_the_spawn_is_still_inside_the_live_scan_helper(live):
    helper = _top_functions(live)[HELPER]
    spawns = _spawn_calls(helper)
    assert len(spawns) == 1, "the helper must own exactly one `subprocess.run`"
    for c in ast.walk(helper):
        if isinstance(c, ast.Call):
            target = ast.dump(c.func)
            assert "'main'" not in target and "_run_main" not in target, (
                f"the helper was converted to an in-process call: {target}")


def test_b6_a_grep_for_subprocess_run_hits_the_helper(live):
    text = _live_text()
    seg = ast.get_source_segment(text, _top_functions(live)[HELPER])
    assert "subprocess.run(" in seg


def test_b6_no_spawn_anywhere_in_the_file_was_converted(prechange, live):
    assert len(_spawn_calls(live)) == len(_spawn_calls(prechange))
    assert _live_text().count("subprocess.run(") == _prechange_text().count("subprocess.run(")
    # the same tests that spawned directly before still spawn directly now
    def spawners(mod):
        return sorted(n for n, f in _tests_of(mod).items() if _spawn_calls(f))
    assert spawners(live) == spawners(prechange)


def test_b6_the_helper_returns_a_completed_process_from_a_real_boundary(warm):
    assert isinstance(warm, subprocess.CompletedProcess)
    assert warm.returncode == 0 and warm.stderr == ""
    assert warm.stdout.endswith("\n") and warm.stdout.count("\n") == 1
