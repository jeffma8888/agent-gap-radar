"""Iteration 415 behaviors: one unreadable entry no longer aborts `radar scan`.

A scan target holding an entry that cannot be stat'ed (a symlink into a
mode-000 directory in walked mode, or a tracked file under a mode-000
directory in git mode) used to abort the whole run with
`Error: cannot scan target: <root>` at exit 2. The entry is now admitted as
unread and disclosed through the contract's channel: `skipped_files` and an
`applies_when unreadable:` UNKNOWN, never a silent NOT_APPLICABLE.

Black-box: every call is a child interpreter driving the public CLI entry
point (`agent_gap_radar.cli.main`) with `timeout=10`. Fixtures live in
tmp_path, permissions are restored in a finalizer. No commit sha, no line
number, no wall-clock ratio, no network, no absolute machine path.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
TIMEOUT = 10
RUNNER = "import subprocess\nsubprocess.run(cmd, timeout=600)\n"
UNREAD = "applies_when unreadable:"

_DRIVER = "import sys\nfrom agent_gap_radar.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"

pytestmark = [
    pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0,
                       reason="root ignores mode 000; POSIX only"),
]


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), env.get("PYTHONPATH", "")])
    return env


def _radar(args: list[str], cwd: pathlib.Path):
    p = subprocess.run(
        [sys.executable, "-c", _DRIVER, *args],
        capture_output=True, cwd=cwd, env=_env(), timeout=TIMEOUT,
    )
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


def _git(root: pathlib.Path, *args: str) -> None:
    env = dict(os.environ)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "-c", "commit.gpgsign=false", *args],
        cwd=root, capture_output=True, check=True, env=env, timeout=TIMEOUT,
    )


@pytest.fixture
def trees(tmp_path):
    """Build w/ (walked) and g/ (git); yield (tmp, w, g, lock, unlock)."""
    w = tmp_path / "w"
    (w / "locked").mkdir(parents=True)
    (w / "runner.py").write_text(RUNNER, encoding="utf-8")
    (w / "locked" / "y.py").write_text("x = 1\n", encoding="utf-8")
    (w / "link.py").symlink_to(pathlib.Path("locked") / "y.py")

    g = tmp_path / "g"
    (g / "sub").mkdir(parents=True)
    (g / "runner.py").write_text(RUNNER, encoding="utf-8")
    (g / "sub" / "y.py").write_text("x = 1\n", encoding="utf-8")
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    _git(g, "init", "-q")
    _git(g, "add", "runner.py", "sub/y.py")
    _git(g, "commit", "-q", "-m", "init")

    dirs = [w / "locked", g / "sub"]

    def lock():
        for d in dirs:
            d.chmod(0o000)

    def unlock():
        for d in dirs:
            d.chmod(0o755)

    try:
        yield tmp_path, w, g, lock, unlock
    finally:
        unlock()


def _scan_json(target: pathlib.Path, cwd: pathlib.Path):
    rc, out, err = _radar(["scan", str(target), "--gaps", str(GAPS), "--json"], cwd)
    assert "Traceback" not in err, err
    assert "cannot scan target" not in err, err
    assert rc == 0, (rc, err)
    doc = json.loads(out)
    assert isinstance(doc["findings"], list) and doc["findings"]
    return doc


def _by_id(doc: dict) -> dict:
    return {f["gap_id"]: f for f in doc["findings"]}


def _assert_disclosed(doc: dict) -> None:
    g3 = _by_id(doc)["GAP-003"]
    assert g3["verdict"] == "PRESENT", g3
    assert g3["skipped_files"] >= 1, g3
    unread = [f for f in doc["findings"]
              if f["verdict"] == "UNKNOWN" and f["reason"].startswith(UNREAD)
              and f["skipped_files"] >= 1]
    assert unread, [(f["gap_id"], f["verdict"], f["reason"]) for f in doc["findings"]]
    # Fail-closed: no finding may be NOT_APPLICABLE while carrying unread files.
    na_over_unread = [f["gap_id"] for f in doc["findings"]
                      if f["verdict"] == "NOT_APPLICABLE" and f["skipped_files"] >= 1]
    assert na_over_unread == [], na_over_unread


# -- premise ---------------------------------------------------------------

def test_premise_lock_makes_entries_unstattable(trees):
    tmp, w, g, lock, _ = trees
    lock()
    with pytest.raises(PermissionError):
        os.stat(w / "link.py")
    with pytest.raises(PermissionError):
        os.stat(g / "sub" / "y.py")


# -- behaviors 1-3: walked target ------------------------------------------

def test_b1_walked_unreadable_link_scans_rc0_json(trees):
    tmp, w, _, lock, _ = trees
    lock()
    doc = _scan_json(w, tmp)
    assert "GAP-003" in _by_id(doc)


def test_b2_b3_walked_discloses_unread(trees):
    tmp, w, _, lock, _ = trees
    lock()
    _assert_disclosed(_scan_json(w, tmp))


# -- behavior 4: git target ------------------------------------------------

def test_b4_git_tracked_file_under_locked_dir(trees):
    tmp, _, g, lock, _ = trees
    lock()
    _assert_disclosed(_scan_json(g, tmp))


# -- behavior 5: markdown ---------------------------------------------------

def test_b5_markdown_discloses_unread(trees):
    tmp, w, _, lock, _ = trees
    lock()
    rc, out, err = _radar(["scan", str(w), "--gaps", str(GAPS)], tmp)
    assert "Traceback" not in err, err
    assert rc == 0, (rc, err)
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-20:])
    assert UNREAD in out


# -- behavior 6: invariance when every file reads ---------------------------

@pytest.mark.parametrize("which", ["w", "g"])
def test_b6_readable_trees_disclose_nothing(trees, which):
    tmp, w, g, lock, unlock = trees
    lock()
    unlock()  # the same trees, permissions restored
    target = w if which == "w" else g
    doc = _scan_json(target, tmp)
    assert [f["gap_id"] for f in doc["findings"] if f["skipped_files"] != 0] == []
    assert [f["gap_id"] for f in doc["findings"] if f["reason"].startswith(UNREAD)] == []
    assert _by_id(doc)["GAP-003"]["verdict"] == "PRESENT"


# -- behavior 7: bad root refusal unchanged ---------------------------------

def test_b7_missing_root_refusal_unchanged(tmp_path):
    target = str(tmp_path / "does-not-exist")
    rc, out, err = _radar(["scan", target, "--gaps", str(GAPS)], tmp_path)
    assert rc == 2
    assert out == ""
    assert err == f"Error: cannot scan target: {target}\n"
