"""Iteration 400 guard: self-scan determinism nodes run ONE fresh scan, not two.

Why a static guard: the saving is invisible to a behavior test -- a node that quietly
goes back to two fresh scans still passes, it just costs another ~10 worker-seconds and
pushes the suite back past preship's budget. So the shape is pinned in the source: each
target node makes exactly one `run_direct` call (the fresh side) and at least one
`selfscan` call (the cached side), and no other scan path.

iter28's parametrized node also covers three cheap non-scan verbs, which keep their
two-run `main` path; for it the guard pins that the fresh/cached pair sits under an
`if argv[0] == "scan":` branch and `main` only under its `else`.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import _selfscan

TESTS = pathlib.Path(__file__).resolve().parent

TARGETS = (
    ("test_iter298_behavior.py", "test_b7_b9_scan_is_deterministic_and_ends_in_one_newline"),
    ("test_iter342_behavior.py", "test_b10_scan_json_deterministic"),
    ("test_iter345_behavior.py", "test_b3_scan_determinism"),
    ("test_iter394_behavior.py", "test_b8_self_scan_twice_byte_identical"),
    ("test_iter28_behavior.py", "test_verb_is_deterministic_and_ends_in_one_newline"),
)

#: Callees that would compute a scan outside the fresh/cached pair.
FORBIDDEN = frozenset({"main", "_cli", "_run", "_scan", "subprocess.run"})


def _callee(call: ast.Call) -> str:
    """Dotted name of a call's callee (`_selfscan.run_direct`, `main`), else ''."""
    parts: list[str] = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _calls(nodes: list[ast.stmt] | ast.AST) -> list[str]:
    roots = nodes if isinstance(nodes, list) else [nodes]
    return [_callee(n) for root in roots for n in ast.walk(root) if isinstance(n, ast.Call)]


def _function(module: str, name: str) -> ast.FunctionDef:
    tree = ast.parse((TESTS / module).read_text(encoding="utf-8"))
    found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(found) == 1, f"{module}::{name} defined {len(found)} times"
    return found[0]


def _is_scan_branch(test: ast.expr) -> bool:
    """True for exactly `argv[0] == "scan"`."""
    return (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and ast.unparse(test.left) == "argv[0]"
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "scan")


@pytest.mark.parametrize("module,name", TARGETS, ids=[t[0][:-3] for t in TARGETS])
def test_target_runs_one_fresh_scan_and_one_cached(module: str, name: str) -> None:
    calls = _calls(_function(module, name))
    fresh = [c for c in calls if c.endswith("run_direct")]
    assert fresh == ["_selfscan.run_direct"], f"{name}: fresh calls {fresh}"
    assert "selfscan" in calls, f"{name}: no cached `selfscan` side"
    if module != "test_iter28_behavior.py":
        assert not FORBIDDEN & set(calls), f"{name}: extra scan path {FORBIDDEN & set(calls)}"


def test_iter28_keeps_main_only_for_the_non_scan_verbs() -> None:
    fn = _function("test_iter28_behavior.py",
                   "test_verb_is_deterministic_and_ends_in_one_newline")
    branches = [n for n in ast.walk(fn) if isinstance(n, ast.If) and _is_scan_branch(n.test)]
    assert len(branches) == 1, "expected one `if argv[0] == \"scan\":` branch"
    scan_calls, other_calls = _calls(branches[0].body), _calls(branches[0].orelse)
    assert "_selfscan.run_direct" in scan_calls and "selfscan" in scan_calls
    assert not FORBIDDEN & set(scan_calls), scan_calls
    assert other_calls.count("main") == 2, other_calls
    anywhere = [c for c in _calls(fn) if c in FORBIDDEN]
    assert anywhere == ["main", "main"], f"scan paths outside the else branch: {anywhere}"


def test_run_direct_counts_exactly_one_computation(tmp_path: pathlib.Path) -> None:
    # An empty root keeps this cheap: the seam counts the computation whatever its rc.
    before = _selfscan.compute_count
    _selfscan.run_direct((), root=tmp_path)
    assert _selfscan.compute_count == before + 1
