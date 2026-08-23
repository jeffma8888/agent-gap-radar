"""Iteration 69 behaviors: ONE shared match loop, not two -- and the guards survive the merge.

`checks.iter_files` has two enumeration branches (what git tracks, and what a directory walk
finds). Iteration 26 made them answer alike; iteration 31 re-landed a containment guard one
branch had lost. Iteration 69's claim is that the shared tail of both branches is now ONE
function, so "these branches differ in ENUMERATION only" is structural rather than asserted
in prose -- and that collapsing it dropped neither the existence guard nor the two rationales
that each cost an iteration to learn.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors; every claim is measured by CALLING the
public `checks` interface, by RUNNING the packaged entry point, or by parsing the module with
`ast` INSIDE a test -- which is what behaviors 1-3 and 5 literally specify, and which is the
opposite of the author reading the file: the test derives the answer, so it cannot be written
around the implementation's shape.

Structural notes, so this file cannot lie later:

* **The shared matcher's NAME is never typed out.** Behavior 1 DERIVES it (the one
  module-level function whose body calls `_glob_regex`), and behaviors 3 and 5 consume that
  derivation. A hard-coded name would make this file a restatement of the diff and would pass
  a second matcher that happened to keep the old name.
* **Behavior 2 runs the real checker over SYNTHETIC source.** `_sole_glob_regex_caller` is the
  single implementation of behavior 1's rule; behavior 2 feeds it a module in which
  `_iter_walked` re-inlines its own `_glob_regex` loop and requires a violation. A
  hand-written expected value would prove the brake was declared, not that it has teeth.
* **Behavior 4 asserts its own premise.** `tracked_files` must name the deleted path -- without
  that control the test also passes on a fixture where git never knew about the file, i.e. on
  a build with no existence guard at all.
* **Behavior 6's A/B varies the BRANCH only.** Two directories hold identical bytes (asserted),
  one committed and one plain, and the branch selection is asserted on each side, because
  `checks._TRACKED_CACHE` is keyed on the resolved path for the life of the process.
* **No absolute machine path and no personal identifier appears here**; the repo root is
  derived from `__file__` and every fixture lives under pytest's `tmp_path_factory`.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar import checks

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`). Same boot line as `test_iter26_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: The per-pattern matcher whose single caller behavior 1 is about.
MATCHER_CALLEE = "_glob_regex"

#: The two enumeration branches that must both delegate.
ENUMERATION_BRANCHES = ("_iter_tracked", "_iter_walked")

#: Behavior 3: the only `bool` parameter the shared matcher may take.
ONLY_BOOL_PARAM = "exclude_tests"

#: Behavior 5: the two rationales that must survive inside the shared matcher, exact case.
#: Each cost an iteration to learn -- why containment compares resolved against resolved
#: (iteration 31), and why containment is settled per match rather than per walked path.
SURVIVING_RATIONALES = ("Resolved-vs-resolved", "per MATCH")


def _checks_source() -> str:
    """The module's own source, located through the imported module rather than a path."""
    return pathlib.Path(checks.__file__).read_text(encoding="utf-8")


def _called_names(node: ast.AST) -> set[str]:
    """Every name that is CALLED anywhere inside `node`.

    A call, not a mention: `_glob_regex` is named in several docstrings today, so a
    source-text census cannot tell a delegation from a comment about one.
    """
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _module_functions(source: str) -> dict[str, ast.FunctionDef]:
    """Module-level `def`s only, by name (a nested helper is not a module-level function)."""
    return {
        node.name: node
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _glob_regex_callers(source: str) -> set[str]:
    """Behavior 1's rule, over arbitrary source: which module-level functions CALL the matcher."""
    return {
        name
        for name, node in _module_functions(source).items()
        if MATCHER_CALLEE in _called_names(node)
    }


def _sole_glob_regex_caller(source: str) -> tuple[str | None, list[str]]:
    """Behavior 1 as a checker: `(shared_matcher_name, violations)`.

    Returns the derived name only when the rule holds, so a caller cannot accidentally
    consume a name derived from a module that has two match loops.
    """
    callers = _glob_regex_callers(source)
    violations: list[str] = []
    if len(callers) != 1:
        violations.append(
            f"{len(callers)} module-level function(s) call {MATCHER_CALLEE}: "
            f"{sorted(callers)} -- expected exactly 1 shared matcher"
        )
        return None, violations
    shared = sorted(callers)[0]
    functions = _module_functions(source)
    for branch in ENUMERATION_BRANCHES:
        if branch not in functions:
            violations.append(f"{branch} is not a module-level function")
            continue
        if shared not in _called_names(functions[branch]):
            violations.append(f"{branch} does not call the shared matcher {shared}")
    return (shared if not violations else None), violations


#: Behavior 2's synthetic module: `_iter_walked` re-inlines its own matcher loop, which is
#: exactly the drift that has already happened twice in this repo's shipped history.
SYNTHETIC_TWO_LOOPS = '''
def _glob_regex(pattern):
    return pattern


def _match(target, relatives, patterns, exclude_tests):
    seen = set()
    for pattern in patterns:
        regex = _glob_regex(pattern)
        for rel in relatives:
            if regex == rel:
                seen.add(target / rel)
    return sorted(seen)


def _iter_tracked(target, patterns, exclude_tests):
    return _match(target, ["a.py"], patterns, exclude_tests)


def _iter_walked(target, patterns, exclude_tests):
    seen = set()
    for pattern in patterns:
        regex = _glob_regex(pattern)
        for rel in ["a.py"]:
            if regex == rel:
                seen.add(target / rel)
    return sorted(seen)
'''

#: The good half of behavior 2's control: the same synthetic module with one matcher.
SYNTHETIC_ONE_LOOP = '''
def _glob_regex(pattern):
    return pattern


def _match(target, relatives, patterns, exclude_tests):
    seen = set()
    for pattern in patterns:
        regex = _glob_regex(pattern)
        for rel in relatives:
            if regex == rel:
                seen.add(target / rel)
    return sorted(seen)


def _iter_tracked(target, patterns, exclude_tests):
    return _match(target, ["a.py"], patterns, exclude_tests)


def _iter_walked(target, patterns, exclude_tests):
    return _match(target, ["a.py"], patterns, exclude_tests)
'''


# --- Behavior 1: one matcher, derived from the module's AST ----------------

def test_b1_exactly_one_module_level_function_calls_the_glob_matcher() -> None:
    shared, violations = _sole_glob_regex_caller(_checks_source())
    assert violations == [], "; ".join(violations)
    assert shared is not None
    assert shared not in ENUMERATION_BRANCHES, (
        f"the sole {MATCHER_CALLEE} caller is {shared}, which IS one of the enumeration "
        "branches -- so one branch still owns the match loop the other must borrow"
    )


def test_b1_both_enumeration_branches_delegate_to_that_one_matcher() -> None:
    """Restated as the acceptance criterion promises it, with the branch named on failure."""
    source = _checks_source()
    shared, violations = _sole_glob_regex_caller(source)
    assert violations == [], "; ".join(violations)
    functions = _module_functions(source)
    for branch in ENUMERATION_BRANCHES:
        assert shared in _called_names(functions[branch]), (
            f"{branch} does not call {shared}; calls are "
            f"{sorted(_called_names(functions[branch]))}"
        )


# --- Behavior 2: that brake can fail (two-sided control) ------------------

def test_b2_the_brake_reports_a_violation_when_the_walked_branch_re_inlines_the_loop() -> None:
    """The REAL checker over SYNTHETIC source, which is the only thing that proves teeth."""
    shared, violations = _sole_glob_regex_caller(SYNTHETIC_TWO_LOOPS)
    assert shared is None, (
        "the brake derived a shared matcher from a module with TWO match loops"
    )
    assert violations, "the brake reported no violation for a re-inlined match loop"
    assert any(MATCHER_CALLEE in v for v in violations), (
        f"the violation text never names {MATCHER_CALLEE}: {violations}"
    )
    assert any("_iter_walked" in v for v in violations), (
        f"the violation text never names the offending branch: {violations}"
    )


def test_b2_control_the_brake_passes_the_synthetic_module_that_shares_one_loop() -> None:
    """The other side of the control: the brake is not simply always-red."""
    shared, violations = _sole_glob_regex_caller(SYNTHETIC_ONE_LOOP)
    assert violations == [], "; ".join(violations)
    assert shared == "_match", f"derived {shared!r} from the one-loop synthetic module"


def test_b2_control_a_docstring_mention_is_not_counted_as_a_call() -> None:
    """Behavior 1 specifies an AST walk BECAUSE a text census cannot make this distinction."""
    mentioning = (
        SYNTHETIC_ONE_LOOP
        + '\n\ndef _iter_extra(target):\n    """Matching goes through _glob_regex."""\n'
        + "    return _match(target, [], [], False)\n"
    )
    assert MATCHER_CALLEE in mentioning
    shared, violations = _sole_glob_regex_caller(mentioning)
    assert violations == [], (
        f"a docstring mention of {MATCHER_CALLEE} was counted as a call: {violations}"
    )
    assert shared == "_match"


# --- Behavior 3: no branch-selecting flag ---------------------------------

def _bool_parameters(node: ast.FunctionDef) -> list[str]:
    """Every parameter of `node` annotated exactly `bool`, in declaration order."""
    args = node.args
    every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg is not None:
        every.append(args.vararg)
    if args.kwarg is not None:
        every.append(args.kwarg)
    return [
        a.arg
        for a in every
        if a.annotation is not None and ast.unparse(a.annotation).strip() == "bool"
    ]


def test_b3_the_shared_matcher_has_exactly_one_bool_parameter_named_exclude_tests() -> None:
    source = _checks_source()
    shared, violations = _sole_glob_regex_caller(source)
    assert violations == [], "; ".join(violations)
    bools = _bool_parameters(_module_functions(source)[shared])
    assert bools == [ONLY_BOOL_PARAM], (
        f"{shared} declares bool parameter(s) {bools}, expected exactly [{ONLY_BOOL_PARAM!r}] "
        "-- a second bool re-introduces the branch special case the collapse removed"
    )


def test_b3_control_the_bool_parameter_reader_can_see_a_second_flag() -> None:
    """Anti-vacuity: `_bool_parameters` is not simply blind to extra flags."""
    synthetic = (
        "def f(target, patterns, exclude_tests: bool = False, "
        "check_exists: bool = True, name: str = 'x') -> None:\n    return None\n"
    )
    node = _module_functions(synthetic)["f"]
    assert _bool_parameters(node) == [ONLY_BOOL_PARAM, "check_exists"]


# --- fixtures for behaviors 4 and 6 ---------------------------------------
# Behavior 6's A/B varies the enumeration BRANCH only, so the two roots hold identical bytes
# (asserted below) and are two DIFFERENT directories rather than one that gains and loses
# `.git`: `checks._TRACKED_CACHE` is keyed on the resolved path for the life of the process.

#: Behavior 6's shared tree. It carries a nested directory (so a nested-reaching glob has
#: something to reach) and a test path (so `exclude_tests` has something to drop).
TREE: dict[str, str] = {
    "pkg/a.py": "def a():\n    return 1\n",
    "pkg/deep/b.py": "def b():\n    return 2\n",
    "tests/test_a.py": "def test_a():\n    assert True\n",
    "notes.md": "# not python\n",
}

#: Behavior 6's expectations, typed out rather than computed from `Path.glob`, so this file
#: cannot inherit the interpreter semantics whose divergence is why the matcher exists.
PY_EXPECTED = ("pkg/a.py", "pkg/deep/b.py", "tests/test_a.py")
PY_EXPECTED_NO_TESTS = ("pkg/a.py", "pkg/deep/b.py")
NESTED_GLOB = "pkg/deep/**"
NESTED_EXPECTED = ("pkg/deep/b.py",)

#: Behavior 4's fixture: two committed `.py` files, one then deleted from disk.
KEPT = "kept.py"
GONE = "gone.py"


def _git_commit(root: pathlib.Path) -> None:
    """`git init` plus a real commit, because `tracked_files` returns None for an empty repo.

    Identity is supplied per-command so nothing reads or writes a global git config, and no
    credential or authentication command is ever run.
    """
    env_args = ["-c", "user.email=fixture@example.invalid", "-c", "user.name=fixture"]
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), *env_args, "commit", "-q", "-m", "fixture"],
                   check=True, capture_output=True)


def _materialise(root: pathlib.Path, tree: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _rel(target: pathlib.Path, paths: list[pathlib.Path]) -> tuple[str, ...]:
    """Absolute results as target-relative POSIX strings, in the order returned."""
    return tuple(p.relative_to(target).as_posix() for p in paths)


@pytest.fixture(scope="module")
def walked_target(tmp_path_factory) -> pathlib.Path:
    """The shared tree as a plain directory: no `.git`, so the walked branch is selected."""
    return _materialise(tmp_path_factory.mktemp("iter69_walked") / "target", TREE)


@pytest.fixture(scope="module")
def git_target(tmp_path_factory) -> pathlib.Path:
    """The same bytes, committed: `git ls-files` succeeds, so the tracked branch is used."""
    root = _materialise(tmp_path_factory.mktemp("iter69_tracked") / "target", TREE)
    _git_commit(root)
    return root


@pytest.fixture(scope="module")
def deleted_tracked_target(tmp_path_factory) -> pathlib.Path:
    """Behavior 4: both `.py` files committed, then `gone.py` removed from the worktree."""
    root = _materialise(
        tmp_path_factory.mktemp("iter69_deleted") / "target",
        {KEPT: "def kept():\n    return 1\n", GONE: "def gone():\n    return 2\n"},
    )
    _git_commit(root)
    (root / GONE).unlink()
    return root


# --- Behavior 4: a tracked path gone from disk is not published -----------

def test_b4_control_git_still_names_the_deleted_path(deleted_tracked_target):
    """The PREMISE, without which the assertion below also passes on a build with no guard.

    If git had forgotten `gone.py`, "the scan does not publish it" would be a statement about
    the fixture rather than about the existence check.
    """
    tracked = checks.tracked_files(deleted_tracked_target)
    assert tracked is not None, "the committed fixture reports no tracked files at all"
    names = {p.relative_to(deleted_tracked_target).as_posix() for p in tracked}
    assert names == {KEPT, GONE}, (
        f"git tracks {sorted(names)}; the fixture needs BOTH {KEPT} and {GONE} tracked, "
        f"with {GONE} deleted from disk, or behavior 4 proves nothing"
    )
    assert not (deleted_tracked_target / GONE).is_file(), f"{GONE} is still on disk"
    assert (deleted_tracked_target / KEPT).is_file(), f"{KEPT} is missing from disk"


def test_b4_a_tracked_path_missing_from_disk_is_not_published(deleted_tracked_target):
    got = _rel(deleted_tracked_target,
               checks.iter_files(deleted_tracked_target, ["**/*.py"]))
    assert got == (KEPT,), (
        f"iter_files published {got}; expected only ({KEPT!r},) -- a path git still names "
        f"but that is absent from disk must not be published as a locator"
    )


# --- Behavior 5: both recorded rationales survive inside the shared matcher ---

def test_b5_the_shared_matcher_carries_both_measured_rationales() -> None:
    """`inspect.getsource` of the DERIVED shared matcher, per the spec.

    Most of the collapsed lines were comments, and these two carry lessons that cost an
    iteration each. A deletion that drops them destroys reasoning, which is worse than the
    duplication it removed.
    """
    source = _checks_source()
    shared, violations = _sole_glob_regex_caller(source)
    assert violations == [], "; ".join(violations)
    fn = getattr(checks, shared, None)
    assert fn is not None, f"{shared} is not reachable as an attribute of the module"
    text = inspect.getsource(fn)
    for rationale in SURVIVING_RATIONALES:
        assert rationale in text, (
            f"{rationale!r} is absent from the source of {shared}; the rationale that "
            "explains the containment guard did not survive the collapse"
        )


def test_b5_control_the_rationales_are_not_everywhere_in_the_module() -> None:
    """Anti-vacuity: the strings are specific, so behavior 5 is not satisfied by any function.

    If either rationale occurred in every function, `inspect.getsource` of ANY function would
    contain it and behavior 5 would be untestable.
    """
    source = _checks_source()
    functions = _module_functions(source)
    for rationale in SURVIVING_RATIONALES:
        carriers = [
            name for name, node in functions.items()
            if rationale in (ast.get_source_segment(source, node) or "")
        ]
        assert 0 < len(carriers) < len(functions), (
            f"{rationale!r} appears in {len(carriers)} of {len(functions)} module-level "
            "functions, so behavior 5 cannot discriminate"
        )


# --- Behavior 6: both branches still answer identically -------------------

def test_b6_premise_plain_directory_selects_the_walked_branch(walked_target):
    assert checks.tracked_files(walked_target) is None, (
        "the plain fixture reports tracked files, so every 'walked branch' assertion here "
        "would actually be exercising the tracked branch"
    )


def test_b6_premise_committed_directory_selects_the_tracked_branch(git_target):
    tracked = checks.tracked_files(git_target)
    assert tracked is not None, (
        "the committed fixture reports no tracked files, so the git side of the A/B would "
        "fall back to the walked branch and the comparison would be vacuous"
    )
    assert tracked, "tracked file list is empty"


def test_b6_premise_both_fixtures_hold_the_same_bytes(walked_target, git_target):
    """The A/B varies the BRANCH only.

    Iterated over the DECLARED tree rather than `rglob`, because the git half carries `.git`
    objects the plain half cannot and a whole-tree comparison could never be equal.
    """
    for rel in TREE:
        assert (walked_target / rel).read_bytes() == (git_target / rel).read_bytes(), rel


@pytest.mark.parametrize("exclude_tests", [False, True])
def test_b6_recursive_python_glob_answers_the_same_on_both_branches(
        walked_target, git_target, exclude_tests):
    expected = PY_EXPECTED_NO_TESTS if exclude_tests else PY_EXPECTED
    walked = _rel(walked_target,
                  checks.iter_files(walked_target, ["**/*.py"], exclude_tests=exclude_tests))
    tracked = _rel(git_target,
                   checks.iter_files(git_target, ["**/*.py"], exclude_tests=exclude_tests))
    assert walked == tracked, (
        f"exclude_tests={exclude_tests}: walked={walked} tracked={tracked} -- one commit "
        "scanned to two answers"
    )
    assert walked == expected, f"'**/*.py' returned {walked}, expected {expected}"


@pytest.mark.parametrize("exclude_tests", [False, True])
def test_b6_nested_reaching_glob_answers_the_same_on_both_branches(
        walked_target, git_target, exclude_tests):
    walked = _rel(walked_target,
                  checks.iter_files(walked_target, [NESTED_GLOB],
                                    exclude_tests=exclude_tests))
    tracked = _rel(git_target,
                   checks.iter_files(git_target, [NESTED_GLOB],
                                     exclude_tests=exclude_tests))
    assert walked == tracked, (
        f"{NESTED_GLOB!r} exclude_tests={exclude_tests}: walked={walked} tracked={tracked}"
    )
    assert walked == NESTED_EXPECTED, (
        f"{NESTED_GLOB!r} returned {walked}, expected {NESTED_EXPECTED} -- the glob no "
        "longer reaches into the nested directory"
    )


def test_b6_control_exclude_tests_changes_the_answer_on_each_branch(
        walked_target, git_target):
    """Without this the True/False pair above could both be the same list on both branches."""
    for name, target in (("walked", walked_target), ("tracked", git_target)):
        with_tests = _rel(target, checks.iter_files(target, ["**/*.py"]))
        without = _rel(target, checks.iter_files(target, ["**/*.py"], exclude_tests=True))
        assert with_tests != without, (
            f"{name} branch: exclude_tests made no difference ({with_tests}), so the "
            "parametrised A/B is exercising one code path twice"
        )
        assert "tests/test_a.py" in with_tests and "tests/test_a.py" not in without


def test_b6_results_are_sorted_on_both_branches(walked_target, git_target):
    """Byte-stable output depends on this; it is the first thing an unordered merge breaks."""
    for target in (walked_target, git_target):
        for globs in (["**/*.py"], [NESTED_GLOB]):
            got = _rel(target, checks.iter_files(target, globs))
            assert list(got) == sorted(got), f"{globs} returned unsorted paths: {got}"


# --- the published surface is unchanged (spec's Out of Scope, restated as tests) ---

def _scan(target: pathlib.Path, *extra: str) -> subprocess.CompletedProcess[bytes]:
    """`radar scan <target>` through the packaged entry point, live register."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, "scan", str(target), *extra],
        cwd=str(REPO_ROOT), capture_output=True, timeout=180)


def test_scan_on_a_plain_target_is_byte_stable_across_two_runs(walked_target):
    first = _scan(walked_target)
    second = _scan(walked_target)
    assert first.returncode == 0, (
        f"exit {first.returncode}; stderr={first.stderr.decode()!r}")
    assert first.stdout == second.stdout, "two runs of one scan produced different bytes"
    assert first.stdout.endswith(b"\n") and not first.stdout.endswith(b"\n\n"), (
        "the scan document does not end in exactly one newline")


def test_scan_on_this_repo_still_succeeds_quietly():
    """The tracked branch against the live register, which is what a consumer runs."""
    proc = _scan(REPO_ROOT)
    assert proc.stderr == b"", f"stderr not empty:\n{proc.stderr.decode()}"
    assert proc.returncode == 0, f"exit {proc.returncode}"
    assert proc.stdout.startswith(b"# Gap scan:"), (
        f"stdout is not a scan document: {proc.stdout[:80]!r}")
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")
