"""Brake: no test module may define a `base_src` fixture (iteration 362).

A `base_src` fixture extracts a frozen commit's `src/` and the tests that take it
assert "output equals the output of commit <sha>". That turns a one-time ship check
into a permanent invariant: any INTENDED output change then reddens every such test,
which is how an approved one-line fix was reverted at the gate. Determinism is
pinned HEAD-vs-HEAD instead, so the concept is retired and this brake keeps it out.

The checker is pure AST over files on disk: no subprocess, no git, no network.
"""

from __future__ import annotations

import ast
import pathlib
import sys

TESTS = pathlib.Path(__file__).resolve().parent
FORBIDDEN = "base_src"


def defines_forbidden(directory: pathlib.Path, *, skip: pathlib.Path | None = None) -> list[str]:
    """Names of `*.py` files under `directory` that define a `base_src` function.

    Sorted, so a failure message is byte-stable across runs and machines.
    """
    offenders = []
    for path in sorted(directory.glob("*.py")):
        if skip is not None and path.resolve() == skip.resolve():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == FORBIDDEN for node in ast.walk(tree)):
            offenders.append(path.name)
    return offenders


def test_b1_no_test_module_defines_base_src() -> None:
    offenders = defines_forbidden(TESTS, skip=pathlib.Path(__file__))
    assert offenders == [], (
        f"frozen-commit `{FORBIDDEN}` fixture is retired; pin determinism "
        f"HEAD-vs-HEAD instead. Offending file(s): {offenders}")


def test_b2_checker_reports_a_planted_base_src(tmp_path: pathlib.Path) -> None:
    (tmp_path / "test_planted.py").write_text("def base_src():\n    ...\n", encoding="utf-8")
    (tmp_path / "test_clean.py").write_text("def other():\n    ...\n", encoding="utf-8")
    assert defines_forbidden(tmp_path) == ["test_planted.py"]


def test_b3_checker_ignores_a_mere_mention(tmp_path: pathlib.Path) -> None:
    """Only a definition trips the brake; prose or an argument named alike does not."""
    (tmp_path / "test_mention.py").write_text(
        '"""base_src is retired."""\n\ndef test_x(base_src=None):\n    ...\n',
        encoding="utf-8")
    assert defines_forbidden(tmp_path) == []


# ---------------------------------------------------------------------------
# Tester black-box nodes (iteration 362): each drives the tree on disk or the
# public checker, offline -- no subprocess, no git, no network.

RETIRED_SCOPE = ("302", "303", "307", "322", "323", "324", "325", "326",
                 "341", "342", "344", "345", "347")
RETIRED_HELPERS = ("base_src", "_arm", "_ARM_SCRIPT", "_git", "_both_arms",
                   "_armed_control")


def _top_level_names(tree: ast.Module) -> dict[str, ast.AST]:
    names: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names[node.target.id] = node
    return names


def test_t1_literal_grep_finds_base_src_only_in_the_brake_file() -> None:
    """EB1 read literally: the token appears nowhere, comments included, but here."""
    hits = sorted(p.name for p in TESTS.glob("*.py")
                  if FORBIDDEN in p.read_text(encoding="utf-8"))
    assert hits == [pathlib.Path(__file__).name], hits


def test_t2_scoped_files_keep_tests_or_are_deleted() -> None:
    """EB4: a scoped file left with zero `test_*` functions must not survive."""
    empty = []
    for nn in RETIRED_SCOPE:
        path = TESTS / f"test_iter{nn}_behavior.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name.startswith("test_") for n in tree.body):
            empty.append(path.name)
    assert empty == [], empty


def test_t3_scoped_files_carry_no_orphan_retired_helper() -> None:
    """EB4: a retired harness helper may stay only if something still uses it."""
    orphans = []
    for nn in RETIRED_SCOPE:
        path = TESTS / f"test_iter{nn}_behavior.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        defined = _top_level_names(tree)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {a.arg for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 for a in n.args.args + n.args.kwonlyargs}
        for name in RETIRED_HELPERS:
            if name in defined and name not in used:
                orphans.append(f"{path.name}::{name}")
    assert orphans == [], orphans


def test_t4_brake_module_is_offline() -> None:
    """EB7: this module imports nothing that can spawn a process or open a socket."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"subprocess", "socket", "urllib", "http", "requests", "os"}
    assert imported & banned == set(), sorted(imported & banned)


def test_t5_checker_honours_skip_and_catches_async_and_nested(tmp_path: pathlib.Path) -> None:
    """EB5/EB6: every definition shape is caught, and only the skipped file is exempt."""
    (tmp_path / "test_async.py").write_text(
        "async def base_src():\n    ...\n", encoding="utf-8")
    (tmp_path / "test_nested.py").write_text(
        "class Holder:\n    def base_src(self):\n        ...\n", encoding="utf-8")
    me = tmp_path / "test_self.py"
    me.write_text("def base_src():\n    ...\n", encoding="utf-8")
    assert defines_forbidden(tmp_path, skip=me) == ["test_async.py", "test_nested.py"]
    assert defines_forbidden(tmp_path) == ["test_async.py", "test_nested.py", "test_self.py"]


def test_t6_checker_output_is_sorted_and_repeatable(tmp_path: pathlib.Path) -> None:
    """EB7: the offender list is byte-stable across runs regardless of write order."""
    for name in ("test_z.py", "test_a.py", "test_m.py"):
        (tmp_path / name).write_text("def base_src():\n    ...\n", encoding="utf-8")
    first = defines_forbidden(tmp_path)
    assert first == ["test_a.py", "test_m.py", "test_z.py"]
    assert defines_forbidden(tmp_path) == first


def test_t7_brake_failure_message_names_the_offending_file(tmp_path: pathlib.Path,
                                                            monkeypatch) -> None:
    """EB5: the brake's own assertion names the file, not just a count."""
    (tmp_path / "test_offender.py").write_text("def base_src():\n    ...\n",
                                               encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "TESTS", tmp_path, raising=True)
    try:
        test_b1_no_test_module_defines_base_src()
    except AssertionError as exc:
        assert "test_offender.py" in str(exc)
    else:
        raise AssertionError("brake did not fire on a planted base_src")
