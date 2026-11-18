"""Iteration 416 behaviors: iter303 b6's append-only whole-suite module census is deleted,
so adding a test module no longer forces an edit to a module about iteration 303.

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors; nothing here reads `src/`, the engineer's or reviewer's
notes, or a diff. Sibling TEST modules are read as text and AST -- they are the object
under test this iteration.

Structural notes, so this file cannot lie later:

* **The deleted names are assembled from fragments**, so a text census of `tests/` never
  finds this module as its own hit.
* **Every "finds nothing" census has a control** that finds a name which must still
  exist, so an empty census proves a deletion, not a probe that matches nothing.
* **No commit sha, line number or `file:line` locator is pinned**, so HEAD moving at ship
  time cannot red this module. The probe run (behavior 7) works on a COPY of the live
  tree under `tmp_path`, using the real object store only through `GIT_DIR`, so it never
  writes into the live `tests/` dir that other parallel nodes census.
* **This module adds no census of its own**: no allowlist of module names.
* **No absolute machine path and no personal identifier appears here.**
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
M303 = "test_iter303_behavior.py"
M386 = "test_iter386_behavior.py"

#: Behavior 1 -- the deleted node, assembled so this module is not a literal hit.
DELETED_B6 = "_".join(["test", "b6", "the", "whole", "suite", "node", "set", "moved",
                       "by", "exactly", "the", "three", "named", "edits"])

#: Behavior 3 -- names that must be gone, and names that must stay.
GONE_NAMES = {"RETIRED" + "_362_302", "_test" + "_files"}
KEPT_NAMES = {"RETIRED_386", "DELETED_300"}

#: Behavior 4 -- every other top-level test of the 303 module.
KEPT_303_TESTS = {
    "test_b1_the_inventory_pins_the_eight_verbs_and_equals_the_prechange_literals",
    "test_b2_long_flags_and_verbs_without_are_read_off_the_inventory",
    "test_b2_the_derivations_agree_with_the_live_parser",
    "test_b3_test_iter111_imports_the_inventory_and_keeps_its_node_ids",
    "test_b4_test_iter296_b1_derives_from_the_inventory_and_pins_no_count",
    "test_b5_test_iter77_parametrizes_the_json_refusers_from_the_inventory",
    "test_b6_test_iter300_deletes_the_text_pin_and_keeps_the_four_tests_and_helpers",
    "test_b7_a_flag_added_to_the_scan_subparser_reds_exactly_the_two_truths",
}

#: Behavior 2 -- the census-set assignment opener.
CENSUS_SET = re.compile(r"^\s*iter\d+" + "_new" + r" = ", re.M)

#: Behavior 5 -- the 386 b8 node, and the assert that was removed from it.
B8_386 = "test_behavior8_the_tracker_lists_exactly_these_removed_and_added_names"
REMOVED_ASSERT = re.compile(
    r"assert\s+[\"']test_iter386" + r"_behavior\.py[\"']\s+in\s+_text\(\s*[\"']test_iter303")


def _text(name: str) -> str:
    return (TESTS / name).read_text(encoding="utf-8")


def _top_functions(text: str) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}


def _top_assigned(text: str) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = node.value
    return out


# ---------------------------------------------------------------------------
# Behavior 1 -- the census node is gone, and its name survives nowhere under tests/.
# ---------------------------------------------------------------------------

def test_b1_the_303_module_no_longer_defines_the_census_node():
    functions = _top_functions(_text(M303))
    assert DELETED_B6 not in functions, sorted(functions)
    # Control: the reading finds the sibling b6 node that must survive.
    assert any(name.startswith("test_b6_") for name in functions), sorted(functions)


def test_b1_no_test_file_spells_the_deleted_name():
    files = sorted(TESTS.glob("*.py"))
    assert len(files) > 50, len(files)
    hits = [p.name for p in files if DELETED_B6 in p.read_text(encoding="utf-8")]
    assert hits == [], hits
    # Control: the same scan finds a name that must still be spelled.
    control = [p.name for p in files
               if "test_b6_test_iter300_deletes_the_text_pin" in p.read_text(encoding="utf-8")]
    assert M303 in control, control
    # And this module, which names the deleted node, is not a hit: it assembles the name.
    assert DELETED_B6 not in pathlib.Path(__file__).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Behavior 2 -- no `iterNNN_new = ` census sets remain in the 303 module.
# ---------------------------------------------------------------------------

def test_b2_the_303_module_carries_no_census_set_assignment():
    hits = CENSUS_SET.findall(_text(M303))
    assert hits == [], hits
    # Control: the probe really matches the deleted shape, indented or not.
    sample = "    iter" + "415" + "_new = {1}\n" + "iter" + "303" + "_new = set()\n"
    assert len(CENSUS_SET.findall(sample)) == 2


# ---------------------------------------------------------------------------
# Behavior 3 -- the census-only constant and helper are gone; RETIRED_386 and
# DELETED_300 stay, and RETIRED_386 is still a three-module literal table.
# ---------------------------------------------------------------------------

def test_b3_census_only_names_are_gone_and_the_shared_ones_stay():
    text = _text(M303)
    assigned = _top_assigned(text)
    functions = _top_functions(text)
    defined = set(assigned) | set(functions)
    assert not (GONE_NAMES & defined), sorted(GONE_NAMES & defined)
    for name in GONE_NAMES:
        assert re.search(r"\b" + re.escape(name) + r"\b", text) is None, name
    assert KEPT_NAMES <= set(assigned), sorted(KEPT_NAMES - set(assigned))
    # Control: the defined-name reading sees the module's helpers at all.
    assert "_test_names" in functions and "head_tests" in functions, sorted(functions)


def test_b3_retired_386_is_still_a_three_module_literal_table():
    table = ast.literal_eval(_top_assigned(_text(M303))["RETIRED_386"])
    assert set(table) == {"test_iter264_behavior.py", "test_iter265_behavior.py",
                          "test_iter296_behavior.py"}, sorted(table)
    for module, (removed, added) in table.items():
        assert removed and all(n.startswith("test_") for n in removed), module
        assert len(added) == 1 and added[0].startswith("test_"), module
    deleted = ast.literal_eval(_top_assigned(_text(M303))["DELETED_300"])
    assert deleted.startswith("test_b13_"), deleted


# ---------------------------------------------------------------------------
# Behavior 4 -- every other top-level 303 test still exists; and nothing new appeared.
# ---------------------------------------------------------------------------

def test_b4_every_other_303_test_still_exists():
    tests = {n for n in _top_functions(_text(M303)) if n.startswith("test_")}
    assert tests == KEPT_303_TESTS, (sorted(KEPT_303_TESTS - tests), sorted(tests - KEPT_303_TESTS))


# ---------------------------------------------------------------------------
# Behavior 5 -- iter386 b8 survives without its final cross-module text assert.
# ---------------------------------------------------------------------------

def test_b5_iter386_b8_survives_without_the_cross_module_assert():
    text = _text(M386)
    functions = _top_functions(text)
    assert B8_386 in functions, sorted(functions)
    body = ast.get_source_segment(text, functions[B8_386]) or ""
    assert "RETIRED_386" in body and "literal_eval" in body, body
    assert REMOVED_ASSERT.search(body) is None, body
    assert REMOVED_ASSERT.search(text) is None
    # Control: the probe matches the removed line's shape.
    line = 'assert "test_iter386' + '_behavior.py" in _text("test_iter303' + '_behavior.py")'
    assert REMOVED_ASSERT.search(line), line


# ---------------------------------------------------------------------------
# Behavior 7 -- a brand-new test module no longer reds the 303 module.
# ---------------------------------------------------------------------------

def test_b7_a_new_probe_module_leaves_the_303_module_green(tmp_path):
    root = tmp_path / "tree"
    root.mkdir()
    # The whole working tree (sibling modules read gaps/, docs/, README at import time),
    # minus the object store, the venv and caches.
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for entry in sorted(REPO_ROOT.iterdir()):
        if entry.name in {".git", ".venv", ".pytest_cache", "__pycache__"}:
            continue
        if entry.is_dir():
            shutil.copytree(entry, root / entry.name, ignore=ignore, symlinks=True)
        elif entry.is_file():
            shutil.copy2(entry, root / entry.name)
    probe = root / "tests" / "test_zz_probe_behavior.py"
    probe.write_text("def test_ok():\n    pass\n", encoding="utf-8")
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    # The copy is not a checkout; point git at the real object store (read-only use).
    # `rev-parse` also resolves a worktree's `.git` file to its real object store.
    git_dir = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--absolute-git-dir"],
                             capture_output=True, text=True, timeout=60)
    assert git_dir.returncode == 0, git_dir.stderr
    env["GIT_DIR"] = git_dir.stdout.strip()
    env["PYTHONPATH"] = str(root / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/" + M303, "tests/" + probe.name,
         "-p", "no:xdist", "-p", "no:cacheprovider", "-o", "addopts=", "-rA"],
        capture_output=True, cwd=str(root), env=env, timeout=600)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, f"rc {proc.returncode}:\n{out[-2500:]}"
    passed = {ln.split()[1] for ln in out.splitlines() if ln.startswith("PASSED ")}
    # Control: the probe really was collected in the copied tree, next to the 303 nodes.
    assert "tests/test_zz_probe_behavior.py::test_ok" in passed, sorted(passed)
    assert {f"tests/{M303}::{n}" for n in KEPT_303_TESTS} <= passed, sorted(passed)
    assert not (REPO_ROOT / "tests" / probe.name).exists(), "the probe leaked into the live tree"
