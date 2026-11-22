"""Iteration 425 behaviors: ``radar scan --exclude GLOB``.

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-11 and from running the CLI; no test was written from the
implementation source, the engineer's or reviewer's notes, or any diff.

Ship hazards: no sha, no ``git show HEAD`` baseline and no file:line locator of
a ship-rewritten file (H1) -- "unchanged by default" is pinned as an invariance
(the flagless document equals the zero-match-exclusion document minus its one
echo line / key, and carries a FIXED key list).  No wall-clock bound (H2), no
extras (H3).

The CLI runs in ONE child interpreter per test: the child takes a JSON job list
on stdin, runs ``main()`` per job with stdout/stderr redirected, and returns
``[rc, out, err]`` per job.  Running several scans in one process also proves an
exclusion does not leak into the next (flagless) scan.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
README = REPO / "README.md"

CHILD = r"""
import contextlib, io, json, os, sys
from agent_gap_radar.cli import main
jobs = json.loads(sys.stdin.read())
res = []
for args in jobs:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(args)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    res.append([rc or 0, out.getvalue(), err.getvalue()])
sys.stdout.write(json.dumps(res))
"""

LOOP = "def run(agent):\n    while True:\n        agent.step()\n"
RELOAD = "import importlib\ndef r(m):\n    return importlib.reload(m)\n"
OTHER = "x=1\n"
NOLOOP = "def run(agent):\n    return agent.step()\n"

# The top-level --json key list of a flagless scan (fixed literal, behavior 1).
FLAGLESS_KEYS = [
    "target", "target_name", "confidence_floor", "layer", "records_applied",
    "counts", "uncheckable", "findings", "baseline",
]


def _batch(jobs: list[list[str]], cwd: pathlib.Path, seed: str = "0") -> list[tuple[int, str, str]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        input=json.dumps(jobs),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    return [tuple(r) for r in json.loads(proc.stdout)]


def _git_target(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True)
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=root, env=env, check=True, capture_output=True)
    return root


def _plain_target(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


VENDORED = {"app/loop.py": LOOP, "vendor/lib/reloader.py": RELOAD, "vendor/lib/other.py": OTHER}
INVERTED = {"app/loop.py": NOLOOP, "vendor/lib/loop.py": LOOP, "vendor/lib/other.py": OTHER}


@pytest.fixture
def vend(tmp_path):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git unavailable")
    return _git_target(tmp_path / "vt", VENDORED)


def _scan(target: pathlib.Path, *extra: str) -> list[str]:
    return ["scan", str(target), "--gaps", str(REPO), "--gap", "GAP-009", *extra]


def _finding(doc: dict) -> dict:
    (f,) = [f for f in doc["findings"] if f["gap_id"] == "GAP-009"]
    return f


def _refusal(res: tuple[int, str, str]) -> str:
    rc, out, err = res
    assert rc == 2, res
    assert out == "", out
    assert err.startswith("Error: "), err
    assert err.endswith("\n") and err.count("\n") == 1, repr(err)
    assert "Traceback" not in err
    return err


# -- 1 + 2: default unchanged; the fail-open is closed (regression fixture) --
def test_b1_b2_vendored_mitigation_absent_by_default_present_with_exclude(vend):
    r = _batch([
        _scan(vend, "--json"),
        _scan(vend, "--exit-code"),
        _scan(vend, "--json", "--exclude", "vendor/**"),
        _scan(vend, "--exit-code", "--exclude", "vendor/**"),
        _scan(vend, "--json"),  # after an excluded scan: no leak
        _scan(vend),
    ], vend.parent)
    d0 = json.loads(r[0][1])
    assert list(d0) == FLAGLESS_KEYS
    assert "exclude" not in d0
    assert _finding(d0)["verdict"] == "ABSENT"
    assert _finding(d0)["locations"] == ["vendor/lib/reloader.py:3"]
    assert r[1][0] == 0, r[1]
    d1 = json.loads(r[2][1])
    assert r[2][0] == 0
    assert _finding(d1)["verdict"] == "PRESENT"
    assert _finding(d1)["locations"] == ["app/loop.py:2"]
    assert r[3][0] == 1, r[3]
    assert r[4][1] == r[0][1], "an exclusion leaked into the next flagless scan"
    assert "Excluded:" not in r[5][1]
    assert r[5][1].endswith("\n") and not r[5][1].endswith("\n\n")


# -- 3: JSON echo --
def test_b3_json_exclude_key_position_value_sorted_dedup(vend):
    r = _batch([
        _scan(vend, "--json", "--exclude", "vendor/**"),
        _scan(vend, "--json", "--exclude", "vendor/**", "--exclude", "vendor/**"),
        _scan(vend, "--json", "--match", "reload", "--exclude", "vendor/**"),
    ], vend.parent)
    d = json.loads(r[0][1])
    assert list(d) == FLAGLESS_KEYS[:4] + ["exclude"] + FLAGLESS_KEYS[4:]
    assert d["exclude"] == {"globs": ["vendor/**"], "files": 2}
    assert list(d["exclude"]) == ["globs", "files"]
    d3 = json.loads(r[1][1])
    assert d3["exclude"] == {"globs": ["vendor/**"], "files": 2}
    assert r[2][0] == 0, r[2]
    d4 = json.loads(r[2][1])
    keys = list(d4)
    assert "match" in keys
    i = keys.index("exclude")
    assert keys[i - 1] == "match" and keys[i + 1] == "records_applied", keys


def test_b3_two_globs_partial_count(tmp_path):
    t = _git_target(tmp_path / "t", {**VENDORED, "lib/a.py": OTHER, "lib/b.py": OTHER})
    (r,) = _batch([_scan(t, "--json", "--exclude", "vendor/**", "--exclude", "lib/a.py")], tmp_path)
    assert r[0] == 0, r
    assert json.loads(r[1])["exclude"] == {"globs": ["lib/a.py", "vendor/**"], "files": 3}


def test_b3_count_is_enumerated_files_only_untracked_not_counted(vend):
    (vend / "vendor" / "lib" / "untracked.py").write_text(OTHER, encoding="utf-8")
    (r,) = _batch([_scan(vend, "--json", "--exclude", "vendor/**")], vend.parent)
    assert json.loads(r[1])["exclude"]["files"] == 2


def test_b3_non_git_target_counts_walked_files_outside_pruned_dirs(tmp_path):
    t = _plain_target(tmp_path / "plain", {**VENDORED, "vendor/node_modules/x.py": OTHER})
    r = _batch([_scan(t, "--json", "--exclude", "vendor/**"), _scan(t, "--json")], tmp_path)
    d = json.loads(r[0][1])
    assert d["exclude"] == {"globs": ["vendor/**"], "files": 2}
    assert _finding(d)["verdict"] == "PRESENT"
    assert _finding(json.loads(r[1][1]))["verdict"] == "ABSENT"


# -- 4: markdown echo --
def test_b4_markdown_excluded_line_directly_after_target(vend):
    r = _batch([
        _scan(vend),
        _scan(vend, "--exclude", "vendr/**"),
        _scan(vend, "--exclude", "vendor/**"),
    ], vend.parent)
    lines = r[2][1].split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.startswith("Target: "))
    assert lines[i + 1] == "Excluded: `vendor/**` -- 2 target file(s) not scanned"
    assert sum(ln.startswith("Excluded:") for ln in lines) == 1
    assert r[2][1].endswith("\n") and not r[2][1].endswith("\n\n")
    # every other line unchanged: zero-match exclusion minus its echo == flagless
    base, typo = r[0][1].split("\n"), r[1][1].split("\n")
    j = next(k for k, ln in enumerate(typo) if ln.startswith("Target: "))
    assert typo[j + 1] == "Excluded: `vendr/**` -- 0 target file(s) not scanned"
    assert typo[: j + 1] + typo[j + 2:] == base


def test_b4_multi_glob_markdown_order(tmp_path):
    t = _git_target(tmp_path / "t", {**VENDORED, "keep.py": OTHER})
    (r,) = _batch([_scan(t, "--exclude", "vendor/**", "--exclude", "app/**")], tmp_path)
    assert r[0] == 0, r
    assert "\nExcluded: `app/**`, `vendor/**` -- 3 target file(s) not scanned\n" in r[1]


# -- 5: the register's glob dialect --
@pytest.mark.parametrize(
    "glob, files, verdict",
    [
        ("vendor/**", 2, "PRESENT"),
        ("**/reloader.py", 1, "PRESENT"),
        ("vendor/lib/reloader.py", 1, "PRESENT"),
        ("*.py", 1, "ABSENT"),  # only the top-level top.py
        ("VENDOR/**", 0, "ABSENT"),  # case-sensitive
        ("vendor", 0, "ABSENT"),  # a bare dir name is a full-match glob, not a prefix
    ],
)
def test_b5_glob_dialect(tmp_path, glob, files, verdict):
    t = _git_target(tmp_path / "t", {**VENDORED, "top.py": OTHER})
    (r,) = _batch([_scan(t, "--json", "--exclude", glob)], tmp_path)
    assert r[0] == 0, r
    d = json.loads(r[1])
    assert d["exclude"] == {"globs": [glob], "files": files}
    assert _finding(d)["verdict"] == verdict


# -- 6: a glob that matches nothing is displayed, not refused --
def test_b6_zero_match_glob_same_verdicts_and_exit(vend):
    r = _batch([
        _scan(vend, "--json"),
        _scan(vend, "--json", "--exclude", "vendr/**"),
        _scan(vend, "--exit-code"),
        _scan(vend, "--exit-code", "--exclude", "vendr/**"),
    ], vend.parent)
    d0, d1 = json.loads(r[0][1]), json.loads(r[1][1])
    assert d1.pop("exclude") == {"globs": ["vendr/**"], "files": 0}
    assert d1 == d0
    assert list(d1) == list(d0)
    assert r[2][0] == r[3][0] == 0
    assert "Excluded: `vendr/**` -- 0 target file(s) not scanned" in r[3][1]


# -- 7: excluding the only file that holds the signature --
def test_b7_inverted_layout_present_becomes_not_applicable(tmp_path):
    t = _git_target(tmp_path / "inv", INVERTED)
    r = _batch([
        _scan(t, "--json"),
        _scan(t, "--exit-code"),
        _scan(t, "--json", "--exclude", "vendor/**"),
        _scan(t, "--exit-code", "--exclude", "vendor/**"),
    ], tmp_path)
    assert _finding(json.loads(r[0][1]))["verdict"] == "PRESENT"
    assert r[1][0] == 1
    assert _finding(json.loads(r[2][1]))["verdict"] == "NOT_APPLICABLE"
    assert r[3][0] == 0, r[3]


# -- 8: an exclusion that leaves nothing to scan is refused --
def test_b8_exclude_everything_refused_on_every_surface(vend):
    surfaces = [[], ["--json"], ["--prd"], ["--exit-code"], ["--exit-code", "--json"]]
    jobs = [_scan(vend, *s, "--exclude", "**") for s in surfaces]
    jobs.append(_scan(vend, "--json", "--exclude", "app/**", "--exclude", "vendor/**"))
    for res in _batch(jobs, vend.parent):
        err = _refusal(res)
        assert err.startswith("Error: --exclude matched every file in the target"), err
        assert err.rstrip("\n").endswith("nothing is left to scan"), err


def test_b8_empty_target_keeps_todays_behavior(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _batch([_scan(empty, "--json"), _scan(empty, "--json", "--exclude", "**")], tmp_path)
    assert r[1][0] == r[0][0]
    assert "matched every file" not in r[1][2]
    if r[0][0] == 0:
        d0, d1 = json.loads(r[0][1]), json.loads(r[1][1])
        assert d1.pop("exclude") == {"globs": ["**"], "files": 0}
        assert d1 == d0
    else:
        assert r[1][1:] == r[0][1:]


# -- 9: blank glob refused before any directory is read --
@pytest.mark.parametrize("blank", ["", "   "])
def test_b9_blank_glob_refused_even_for_missing_target(tmp_path, blank):
    want = "Error: --exclude needs a non-blank GLOB; omit the flag to scan every file\n"
    r = _batch([
        _scan(tmp_path / "does-not-exist", "--exclude", blank),
        _scan(tmp_path / "does-not-exist", "--json", "--exclude", "vendor/**", "--exclude", blank),
    ], tmp_path)
    for res in r:
        assert _refusal(res) == want


# -- 10: composes, changes no other surface --
def test_b10_baseline_computed_from_excluded_scan(vend):
    base = vend.parent / "B.json"
    (b0,) = _batch([_scan(vend, "--json")], vend.parent)
    base.write_text(b0[1], encoding="utf-8")  # GAP-009 ABSENT in the baseline
    exb = vend.parent / "BX.json"
    (b1,) = _batch([_scan(vend, "--json", "--exclude", "vendor/**")], vend.parent)
    exb.write_text(b1[1], encoding="utf-8")  # carries an "exclude" key, GAP-009 PRESENT
    # iter 426 re-pin: a baseline whose --exclude globs differ from the scan's is
    # refused (exit 2, stdout empty) -- the narrowed domain must not gate green or red.
    # Matching pairs keep their codes, and the Baseline: line is still computed from
    # the excluded scan.
    r = _batch([
        _scan(vend, "--exit-code", "--baseline", str(base), "--exclude", "vendor/**"),
        _scan(vend, "--exit-code", "--baseline", str(exb), "--exclude", "vendor/**"),
        _scan(vend, "--exit-code", "--json", "--baseline", str(exb)),
        _scan(vend, "--exit-code", "--json", "--baseline", str(base), "--exclude", "vendor/**"),
        _scan(vend, "--exit-code", "--json", "--baseline", str(exb), "--exclude", "vendor/**"),
        _scan(vend, "--exit-code", "--baseline", str(base)),
    ], vend.parent)
    for i in (0, 2, 3):  # mismatched pairs
        assert r[i][0] == 2 and r[i][1] == "", r[i]
        assert r[i][2].startswith("Error: baseline exclude mismatch: "), r[i]
    assert r[1][0] == 0, r[1]  # baseline with an exclude key accepted, nothing new
    assert r[4][0] == 0, r[4]
    d = json.loads(r[4][1])
    assert d["exclude"] == {"globs": ["vendor/**"], "files": 2}
    assert d["baseline"] is not None
    assert "\nBaseline:" in r[1][1] and "Excluded: `vendor/**`" in r[1][1]
    (bl_x,) = [ln for ln in r[1][1].split("\n") if ln.startswith("Baseline:")]
    (bl_0,) = [ln for ln in r[5][1].split("\n") if ln.startswith("Baseline:")]
    assert r[5][0] == 0
    assert bl_x != bl_0, "the Baseline: line must be computed from the excluded scan"


def test_b10_composes_with_other_flags(vend):
    r = _batch([
        _scan(vend, "--json", "--exclude", "vendor/**", "--layer", "lifecycle-deploy",
              "--floor", "1", "--name", "svc"),
        _scan(vend, "--prd", "--exclude", "vendor/**"),
        ["scan", str(vend), "--gaps", str(REPO), "--json", "--exclude", "vendor/**"],
    ], vend.parent)
    d = json.loads(r[0][1])
    assert r[0][0] == 0 and d["target_name"] == "svc" and d["layer"] == "lifecycle-deploy"
    assert d["confidence_floor"] == 1
    assert d["exclude"] == {"globs": ["vendor/**"], "files": 2}
    assert _finding(d)["verdict"] == "PRESENT"
    assert r[1][0] == 0, r[1]
    assert "GAP-009" in r[1][1]  # the excluded scan's PRESENT finding drives --prd
    json.loads(r[1][1])
    assert r[2][0] == 0, r[2]
    full = json.loads(r[2][1])
    assert full["exclude"] == {"globs": ["vendor/**"], "files": 2}


def test_b10_other_verbs_reject_exclude(tmp_path):
    r = _batch([
        ["list", "--exclude", "x"],
        ["report", "--exclude", "x"],
        ["prd", "GAP-009", "--exclude", "x"],
        ["validate", "--exclude", "x"],
        ["taxonomy", "--exclude", "x"],
    ], REPO)
    for res in r:
        assert res[0] == 2, res
        assert res[1] == ""
        assert "--exclude" in res[2]


def test_b10_byte_stable_across_hash_seeds(vend):
    jobs = [_scan(vend, "--json", "--exclude", "vendor/**", "--exclude", "app/x/**"),
            _scan(vend, "--exclude", "vendor/**", "--exclude", "app/x/**")]
    a = _batch(jobs, vend.parent, seed="1")
    b = _batch(jobs, vend.parent, seed="4242")
    assert a == b
    assert json.loads(a[0][1])["exclude"]["globs"] == ["app/x/**", "vendor/**"]


# -- 11: documented --
def test_b11_contract_cell_and_prose():
    text = CONTRACT.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| `radar scan <target>")]
    assert len(rows) == 1, rows
    usage = rows[0].split("`")[1]
    assert usage.endswith("[--exclude GLOB]"), usage
    for token in ("--exclude", "exclude", "globs", "files", "Excluded:",
                  "--exclude needs a non-blank GLOB",
                  "--exclude matched every file in the target"):
        assert token in text, token
    assert "`exclude`" in text or '"exclude"' in text


def test_b11_readme_and_help():
    readme = README.read_text(encoding="utf-8")
    (para,) = [p for p in readme.split("\n\n") if p.startswith("**What a scan reads.**")]
    assert "vendored" in para and "by default" in para
    assert "--exclude GLOB" in para
    assert "display" in para
    (r,) = _batch([["scan", "--help"]], REPO)
    assert r[0] == 0
    assert "--exclude GLOB" in r[1]
