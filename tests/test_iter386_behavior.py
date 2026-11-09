"""Iteration 386 -- black-box pins for retiring the frozen-commit arms of iter264/265/296.

Tests only: the three modules lose their `git archive PRECHANGE_COMMIT` control arms
and gain live HEAD pins. This module checks that from the OUTSIDE: the module text,
the collected node ids (`pytest --collect-only`, a cheap subprocess that runs no test),
and one cheap in-process verb run. It never builds a frozen tree and never scans.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
MODULES = ("test_iter264_behavior.py", "test_iter265_behavior.py", "test_iter296_behavior.py")

#: Behavior 2, spelled from the spec (not imported from the module that tracks it).
DELETED = {
    "test_iter264_behavior.py": {
        "test_b3_verb_stdout_and_exit_code_are_byte_identical_to_the_prechange_tree",
        "test_b3_the_prechange_tree_exited_zero_on_bare_radar_and_the_tree_now_refuses",
        "test_b2_help_bytes_are_identical_to_the_prechange_tree",
    },
    "test_iter265_behavior.py": {
        "test_iter265_b2_location_notes_is_appended_last_and_prior_keys_keep_their_order",
        "test_iter265_b3_locations_and_notes_partition_the_prechange_list_in_order",
        "test_iter265_b3_two_sided_the_prechange_tree_mixed_prose_into_locations",
        "test_iter265_b3_every_other_finding_key_and_the_top_level_are_unchanged",
        "test_iter265_b4_markdown_brief_is_byte_identical_to_the_prechange_tree",
    },
    "test_iter296_behavior.py": {
        "test_iter296_b3_the_control_arm_is_really_the_pre_change_build",
        "test_iter296_b3_exact_spelling_is_byte_identical_to_the_pre_change_commit",
    },
}

#: Behaviors 3, 4, 6 -- the new live node per module.
ADDED = {
    "test_iter264_behavior.py": "test_b3_control_verb_runs_clean_at_head",
    "test_iter265_behavior.py":
        "test_iter265_b2_location_notes_and_skipped_files_are_the_last_two_finding_keys",
    "test_iter296_behavior.py": "test_iter296_b3_exact_spelling_runs_clean_at_head",
}

#: Behavior 7 -- the exact collected node counts.
EXPECTED_COUNTS = {
    "test_iter264_behavior.py": 47,
    "test_iter265_behavior.py": 14,
    # Iteration 389: +4, the `--m`..`--matc` strict prefixes of scan's new `--match`.
    "test_iter296_behavior.py": 195,
}

#: Files that legitimately spell the deleted names: the tracker table and this module.
NAME_TRACKERS = {"test_iter303_behavior.py", pathlib.Path(__file__).name}


def _text(name: str) -> str:
    return (TESTS / name).read_text(encoding="utf-8")


def _functions(name: str) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(_text(name))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


@pytest.fixture(scope="module")
def collected() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--collect-only", "-q",
         "-p", "no:cacheprovider", *(f"tests/{m}" for m in MODULES)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    return [line for line in proc.stdout.splitlines() if "::" in line]


def _ids(collected: list[str], module: str, func: str) -> list[str]:
    prefix = f"tests/{module}::{func}"
    out = []
    for node in collected:
        if node == prefix:
            out.append("")
        elif node.startswith(prefix + "["):
            out.append(node[len(prefix) + 1:-1])
    return out


# Behavior 1 -------------------------------------------------------------------------
@pytest.mark.parametrize("module", MODULES)
def test_behavior1_no_frozen_tree_machinery_remains(module):
    hits = [f"{i}: {line}" for i, line in enumerate(_text(module).splitlines(), 1)
            if re.search(r'prechange_src|prechange_scan_json|tarfile|"archive"', line)]
    assert hits == [], hits


# Behavior 2 -------------------------------------------------------------------------
@pytest.mark.parametrize("module", MODULES)
def test_behavior2_the_named_nodes_are_gone_from_their_module(module, collected):
    assert DELETED[module].isdisjoint(_functions(module)), module
    assert not [n for n in collected
                if n.split("::")[1].split("[")[0] in DELETED[module]]


def test_behavior2_no_deleted_name_survives_anywhere_in_the_suite():
    every = set().union(*DELETED.values())
    hits = sorted(
        f"{path.name}: {name}"
        for path in TESTS.glob("*.py") if path.name not in NAME_TRACKERS
        for name in every if name in path.read_text(encoding="utf-8")
    )
    assert hits == [], hits


# Behavior 3 -------------------------------------------------------------------------
def test_behavior3_iter264_live_node_covers_every_control_verb_but_scan(collected):
    ids = _ids(collected, "test_iter264_behavior.py", ADDED["test_iter264_behavior.py"])
    assert sorted(ids) == sorted(["validate", "list", "report", "show", "prd", "taxonomy"])
    assert "scan" not in ids


# Behavior 4 -------------------------------------------------------------------------
def test_behavior4_iter296_live_node_has_eight_params_and_no_floor_scan(collected):
    ids = _ids(collected, "test_iter296_behavior.py", ADDED["test_iter296_behavior.py"])
    assert len(ids) == 8, ids
    assert len(set(ids)) == 8, ids
    assert not [i for i in ids if "floor" in i and "scan" in i], ids


def test_behavior4_diff_json_stdout_parses_and_ranking_is_the_last_key(
        capsys, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    rc = main(["diff", "gaps", "gaps", "--json"])
    out, err = capsys.readouterr()
    assert rc in (0, None)
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert list(json.loads(out))[-1] == "ranking"


# Behavior 5 -------------------------------------------------------------------------
def test_behavior5_iter296_b4_keeps_its_name_and_takes_no_fixture():
    fn = _functions("test_iter296_behavior.py")[
        "test_iter296_b4_scan_gap_and_gaps_keep_both_exact_meanings"]
    assert [a.arg for a in fn.args.args] == []
    body = ast.get_source_segment(_text("test_iter296_behavior.py"), fn) or ""
    assert "GAP-003" in body and "records_applied" in body


# Behavior 6 -------------------------------------------------------------------------
def test_behavior6_iter265_new_node_uses_the_self_scan_json_fixture():
    fn = _functions("test_iter265_behavior.py")[ADDED["test_iter265_behavior.py"]]
    assert [a.arg for a in fn.args.args] == ["self_scan_json"]
    body = ast.get_source_segment(_text("test_iter265_behavior.py"), fn) or ""
    assert "location_notes" in body and "skipped_files" in body


# Behavior 7 -------------------------------------------------------------------------
@pytest.mark.parametrize("module", MODULES)
def test_behavior7_collected_node_counts_are_exact(module, collected):
    count = sum(1 for n in collected if n.startswith(f"tests/{module}::"))
    assert count == EXPECTED_COUNTS[module], (module, count)


def test_behavior7_total_collected_is_256(collected):
    assert len(collected) == 256


def test_behavior7_kept_shared_names_and_blob_pins_survive():
    t265 = ast.parse(_text("test_iter265_behavior.py"))
    top = {n.name for n in t265.body if isinstance(n, ast.FunctionDef)}
    top |= {t.id for n in t265.body if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name)}
    top |= {n.target.id for n in t265.body
            if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    assert {"NOTE_DIALECTS", "_is_note", "LOCATOR"} <= top
    t264 = _text("test_iter264_behavior.py")
    assert '"show"' in t264 and "PRECHANGE_COMMIT" in t264


@pytest.mark.parametrize("module", MODULES)
def test_behavior7_every_new_live_node_is_collected(module, collected):
    assert _ids(collected, module, ADDED[module]), (module, ADDED[module])


# Behavior 8 -------------------------------------------------------------------------
def test_behavior8_the_tracker_lists_exactly_these_removed_and_added_names():
    tree = ast.parse(_text("test_iter303_behavior.py"))
    [node] = [n for n in tree.body if isinstance(n, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "RETIRED_386" for t in n.targets)]
    table = ast.literal_eval(node.value)
    assert set(table) == set(MODULES)
    for module in MODULES:
        removed, added = table[module]
        assert set(removed) == DELETED[module], module
        assert added == [ADDED[module]], module
    assert "test_iter386_behavior.py" in _text("test_iter303_behavior.py")
