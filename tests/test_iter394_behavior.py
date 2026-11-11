"""Iteration 394: one ``relative_to`` per tracked file per scan; scan output unchanged.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from ``pm.md``'s
Expected Behaviors 1 and 3-8 (behavior 2 is the re-pin inside
``test_iter322_behavior.py``). No test here reads the implementation source, the
engineer's or reviewer's notes, or any diff. Behaviors are measured by running
``cli.main`` in process, by counting calls to the stdlib
``PurePosixPath.relative_to``, and -- for "output unchanged" -- by running the SAME
fixture trees through a ``git archive cbf1426`` extract of the pre-change tree in a
child process with ``PYTHONPATH`` pinned to that extract. Offline; every path is
derived from this file's location or from ``tmp_path``.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import unittest.mock

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
BASE_SHA = "cbf1426"

_DRIVER = r"""
import contextlib, io, json, sys
import agent_gap_radar
from agent_gap_radar.cli import main
jobs = json.loads(sys.stdin.read())
res = []
for argv in jobs:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    res.append([code, out.getvalue()])
print(json.dumps({"file": agent_gap_radar.__file__, "res": res}))
"""


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _git(cwd: pathlib.Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, env=env)


def _materialise(root: pathlib.Path, files: dict[str, str], *, git: bool) -> pathlib.Path:
    root.mkdir(parents=True)
    for rel, text in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    if git:
        _git(root, "init", "-q")
        _git(root, "add", "-A")
        _git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
    return root


def _records() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(GAPS.glob("GAP-*.json"))]


def _bad(gap: str) -> dict[str, str]:
    (rec,) = [r for r in _records() if r["id"] == gap]
    return rec["check"]["fixtures"]["bad"]


def _run_tree(src: pathlib.Path, jobs: list[list[str]]) -> list[list]:
    env = {**os.environ, "PYTHONPATH": str(src)}
    proc = subprocess.run([sys.executable, "-c", _DRIVER], input=json.dumps(jobs),
                          capture_output=True, text=True, env=env, check=False)
    assert proc.returncode == 0, proc.stderr[-2000:]
    doc = json.loads(proc.stdout)
    assert pathlib.Path(doc["file"]).resolve().is_relative_to(src.resolve()), doc["file"]
    return doc["res"]


@pytest.fixture(scope="module")
def head_src(tmp_path_factory) -> pathlib.Path:
    if not (REPO / ".git").exists():
        pytest.skip("no .git: cannot extract the pre-change tree")
    probe = subprocess.run(["git", "cat-file", "-e", f"{BASE_SHA}^{{commit}}"], cwd=REPO,
                           capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip(f"{BASE_SHA} not available in this clone")
    dest = tmp_path_factory.mktemp("head_tree")
    archive = subprocess.run(["git", "archive", BASE_SHA, "src"], cwd=REPO,
                             capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return dest / "src"


def _count_relative_to(*argv: str) -> tuple[int, int, str]:
    calls = 0
    original = pathlib.PurePosixPath.relative_to

    def counting(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    with unittest.mock.patch.object(pathlib.PurePosixPath, "relative_to", counting):
        code, out, err = _run(*argv)
    assert err == "", err[:500]
    return code, calls, out


# ---- Behaviors 1 and 3: the call count is bounded by the tracked count ------------------


@pytest.mark.parametrize("fmt", [(), ("--json",)], ids=["markdown", "json"])
def test_b1_b3_self_scan_relative_to_bounded_by_tracked_count(fmt):
    code, calls, out = _count_relative_to("scan", str(REPO), "--gaps", str(GAPS), *fmt)
    assert code == 0
    assert out.endswith("\n") and not out.endswith("\n\n")
    ceiling = len(checks.tracked_files(REPO)) + 200
    assert 0 < calls < ceiling, f"relative_to called {calls} times, ceiling {ceiling}"


# ---- Behavior 4: is_test_path keeps its direct-call behaviour ---------------------------


@pytest.mark.parametrize("rel,expected", [
    ("tests/x.py", True), ("a/test_foo.py", True), ("foo_test.go", True),
    ("web/a.spec.ts", True), ("conftest.py", True),
    ("src/app.py", False), ("latest/x.py", False),
])
def test_b4_is_test_path_direct(tmp_path, rel, expected):
    assert checks.is_test_path(tmp_path, tmp_path / rel) is expected


def test_b4_is_test_path_outside_target_falls_back_to_posix(tmp_path):
    assert checks.is_test_path(tmp_path / "a", pathlib.Path("/elsewhere/tests/x.py")) is True
    assert checks.is_test_path(tmp_path / "a", pathlib.Path("/elsewhere/src/x.py")) is False


# ---- Behavior 5: every register fixture arm scans identically to the pre-change tree ----


_SHARDS = 12


@pytest.mark.parametrize("shard", range(_SHARDS))
def test_b5_fixture_arms_match_pre_change_tree(tmp_path, head_src, shard):
    # Sharded so xdist spreads the ~480 arm scans; together the shards cover every record.
    jobs: list[list[str]] = []
    for rec in _records()[shard::_SHARDS]:
        fixtures = (rec.get("check") or {}).get("fixtures") or {}
        for arm in ("bad", "good"):
            files = fixtures.get(arm)
            if not files:
                continue
            for git in (False, True):
                d = _materialise(tmp_path / f"{rec['id']}-{arm}-{'git' if git else 'plain'}",
                                 files, git=git)
                jobs.append(["scan", str(d), "--gaps", str(GAPS), "--gap", rec["id"], "--json"])
    assert jobs and len(jobs) % 2 == 0, len(jobs)  # every arm runs plain AND git
    head = _run_tree(head_src, jobs)
    now = _run_tree(REPO / "src", jobs)
    diffs = [j[4] + " " + j[1].rsplit("/", 1)[-1] for j, h, n in zip(jobs, head, now) if h != n]
    assert diffs == []
    # Non-vacuous: the shard's arms really produced evidence locators to compare.
    assert any(json.loads(n[1])["findings"][0]["locations"] for n in now)


# ---- Behavior 6: a test-file copy of a hit is never code evidence ------------------------


@pytest.mark.parametrize("mitigated_in_test", [False, True], ids=["plain", "test-mitigation"])
def test_b6_test_copy_is_not_code_evidence(tmp_path, head_src, mitigated_in_test):
    (loop_py,) = _bad("GAP-009").values()
    test_text = loop_py + ("import importlib\nimportlib.reload(worker)\n" if mitigated_in_test else "")
    d = _materialise(tmp_path / "svc", {"app.py": loop_py, "tests/test_app.py": test_text}, git=True)
    argv = ["scan", str(d), "--gaps", str(GAPS), "--gap", "GAP-009", "--json"]
    code, out, err = _run(*argv)
    assert err == ""
    (finding,) = json.loads(out)["findings"]
    if mitigated_in_test:
        # CHK-009: a mitigation named only in a test file never certifies ABSENT.
        assert finding["verdict"] != "ABSENT", finding
    else:
        assert finding["verdict"] == "PRESENT"
        assert any(loc.startswith("app.py:") for loc in finding["locations"]), finding
    (head,) = _run_tree(head_src, [argv])
    assert head == [code, out]


# ---- Behavior 7: no memo outlives the scan; a second target starts clean -----------------


def test_b7_stacks_restored_and_no_carry_over(tmp_path):
    # GAP-009 loop plus its mitigation: in CODE it is mitigation evidence, in a TEST
    # path it never is -- so a carried-over "not a test" verdict would flip B to ABSENT.
    (loop_py,) = _bad("GAP-009").values()
    gate_py = loop_py + "import importlib\nimportlib.reload(worker)\n"
    a = _materialise(tmp_path / "repo_a", {"src/gate.py": gate_py}, git=True)
    b = _materialise(tmp_path / "repo_b", {"tests/gate.py": gate_py}, git=True)
    argv_b = ["scan", str(b), "--gaps", str(GAPS), "--gap", "GAP-009", "--json"]
    file_before = len(checks._FILE_CACHE_STACK)
    rel_before = len(checks._RELATIVES_CACHE_STACK)
    code_a, out_a, _ = _run("scan", str(a), "--gaps", str(GAPS), "--gap", "GAP-009", "--json")
    assert len(checks._FILE_CACHE_STACK) == file_before
    assert len(checks._RELATIVES_CACHE_STACK) == rel_before
    code_b, out_b, _ = _run(*argv_b)
    assert len(checks._FILE_CACHE_STACK) == file_before
    assert len(checks._RELATIVES_CACHE_STACK) == rel_before
    (fa,) = json.loads(out_a)["findings"]
    (fb,) = json.loads(out_b)["findings"]
    assert fa["verdict"] == "ABSENT", fa
    assert fb["verdict"] != "ABSENT", fb
    # Oracle: B alone, in a fresh process of the same (worktree) tree.
    (alone,) = _run_tree(REPO / "src", [argv_b])
    assert alone == [code_b, out_b]


# ---- Behavior 8: two self-scans in a row are byte-identical ------------------------------


def test_b8_self_scan_twice_byte_identical():
    first = _run("scan", str(REPO), "--gaps", str(GAPS), "--json")
    second = _run("scan", str(REPO), "--gaps", str(GAPS), "--json")
    assert first == second
    assert first[1].endswith("\n") and not first[1].endswith("\n\n")
