"""Iteration 426 behaviors: ``scan --exit-code --baseline`` refuses an ``--exclude`` drift.

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-8 and from running the CLI; no test was written from the
implementation source, the engineer's or reviewer's notes, or any diff.

Ship hazards: no sha, no ``git show HEAD`` baseline, no file:line locator of a
ship-rewritten file (H1) -- "unchanged" is pinned as an invariance against
fixed literals and against the same build's own documents.  No wall-clock bound
(H2), no extras (H3).

The CLI runs in ONE child interpreter per batch (iter425 precedent): the child
takes a JSON job list on stdin, runs ``main()`` per job with stdout/stderr
redirected, and returns ``[rc, out, err]`` per job.
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

FILES = {
    "app/loop.py": "import agent\nwhile True:\n    agent.step()\n",
    "vendor/v.py": "x = 1\n",
    "README.md": "hi\n",
}

TAIL = "; write the baseline with the same --exclude globs\n"
PREFIX = "Error: baseline exclude mismatch: "

# The top-level --json key list of a flagless scan (fixed literal).
FLAGLESS_KEYS = [
    "target", "target_name", "confidence_floor", "layer", "records_applied",
    "counts", "uncheckable", "findings", "baseline",
]


def _batch(jobs: list[list[str]], seed: str = "0") -> list[tuple[int, str, str]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        input=json.dumps(jobs),
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    return [tuple(r) for r in json.loads(proc.stdout)]


def _scan(target: pathlib.Path, *extra: str) -> list[str]:
    return ["scan", str(target), "--gaps", str(REPO), *extra]


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git unavailable")
    root = tmp_path_factory.mktemp("i426")
    t = root / "T"
    for rel, body in FILES.items():
        p = t / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=t, env=env, check=True, capture_output=True)
    r0, r1 = _batch([
        _scan(t, "--json"),
        _scan(t, "--json", "--exclude", "vendor/**", "--exclude", "app/**"),
    ])
    assert r0[0] == 0 and r1[0] == 0, (r0, r1)
    base = root / "base.json"
    bx = root / "bx.json"
    base.write_text(r0[1], encoding="utf-8")
    bx.write_text(r1[1], encoding="utf-8")
    return t, base, bx, json.loads(r0[1]), json.loads(r1[1])


def _verdict(doc: dict, gid: str) -> str:
    (f,) = [f for f in doc["findings"] if f["gap_id"] == gid]
    return f["verdict"]


def test_fixture_premises(fx):
    _t, _base, _bx, d0, d1 = fx
    assert "exclude" not in d0
    assert list(d0) == FLAGLESS_KEYS
    assert _verdict(d0, "GAP-009") == "PRESENT"
    assert d1["exclude"]["globs"] == ["app/**", "vendor/**"]


# Behavior 1 -- the measured fail-open is refused (markdown and --json alike).
def test_b1_measured_fail_open_refused(fx):
    t, base, _bx, _d0, _d1 = fx
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(base), "--exclude", "app/**"),
        _scan(t, "--exit-code", "--json", "--baseline", str(base), "--exclude", "app/**"),
    ])
    want = PREFIX + "(none) (baseline) vs `app/**` (scan)" + TAIL
    for rc, out, err in r:
        assert rc == 2
        assert out == ""
        assert err == want, err
    assert r[0] == r[1]


# Behavior 2 -- every mismatch direction is refused.
@pytest.mark.parametrize("which,extra,line", [
    ("bx", [], "`app/**`, `vendor/**` (baseline) vs (none) (scan)"),
    ("bx", ["--exclude", "app/**"], "`app/**`, `vendor/**` (baseline) vs `app/**` (scan)"),
    ("base", ["--exclude", "vendor/**"], "(none) (baseline) vs `vendor/**` (scan)"),
    ("bx", ["--exclude", "vendor/**", "--exclude", "docs/**", "--exclude", "app/**"],
     "`app/**`, `vendor/**` (baseline) vs `app/**`, `docs/**`, `vendor/**` (scan)"),
])
def test_b2_every_direction_refused(fx, which, extra, line):
    t, base, bx, _d0, _d1 = fx
    b = base if which == "base" else bx
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(b), *extra),
        _scan(t, "--exit-code", "--json", "--baseline", str(b), *extra),
    ])
    for rc, out, err in r:
        assert rc == 2, (rc, err)
        assert out == ""
        assert err == PREFIX + line + TAIL, err
        assert err.count("\n") == 1


# Behavior 3 -- equal sets pass, byte-identical across order and repeats.
def test_b3_equal_sets_pass_unchanged(fx):
    t, _base, bx, _d0, _d1 = fx
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(bx), "--exclude", "app/**", "--exclude", "vendor/**"),
        _scan(t, "--exit-code", "--baseline", str(bx), "--exclude", "vendor/**",
              "--exclude", "app/**", "--exclude", "app/**"),
        _scan(t, "--exit-code", "--json", "--baseline", str(bx), "--exclude", "app/**",
              "--exclude", "vendor/**"),
        _scan(t, "--exit-code", "--json", "--baseline", str(bx), "--exclude", "vendor/**",
              "--exclude", "app/**", "--exclude", "app/**"),
    ])
    for rc, out, err in r:
        assert rc == 0, err
        assert err == ""
        assert out.endswith("\n") and not out.endswith("\n\n")
    assert r[0][1] == r[1][1]
    assert r[2][1] == r[3][1]
    assert "\nBaseline: " in r[0][1]
    assert "Excluded: `app/**`, `vendor/**`" in r[0][1]
    d = json.loads(r[2][1])
    assert d["exclude"]["globs"] == ["app/**", "vendor/**"]
    assert d["baseline"] is not None


# Behavior 4 -- the flagless pair is unchanged; a document with no exclude key is "no exclusion".
def test_b4_flagless_pair_unchanged(fx):
    t, base, _bx, d0, _d1 = fx
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(base)),
        _scan(t, "--exit-code", "--json", "--baseline", str(base)),
        _scan(t),
        _scan(t, "--json"),
    ])
    for rc, _out, err in r:
        assert rc == 0, err
        assert err == ""
    d = json.loads(r[1][1])
    assert list(d) == FLAGLESS_KEYS
    assert "exclude" not in d
    # Only the baseline key differs from the same invocation without the flag.
    plain = json.loads(r[3][1])
    assert {k: v for k, v in d.items() if k != "baseline"} == {
        k: v for k, v in plain.items() if k != "baseline"}
    assert d["baseline"] is not None
    assert d["findings"] == d0["findings"]
    # Markdown: exactly one extra Baseline: line versus the flagless scan.
    md_b, md_p = r[0][1].split("\n"), r[2][1].split("\n")
    extra = [ln for ln in md_b if ln not in md_p]
    assert len(md_b) == len(md_p) + 1
    assert len(extra) == 1 and extra[0].startswith("Baseline: ")
    assert "Excluded:" not in r[0][1]


# Behavior 5 -- refusal precedence: target mismatch and the older refusals win.
def test_b5_target_mismatch_reported_first(fx):
    t, _base, bx, _d0, _d1 = fx
    r = _batch([
        _scan(t, "--exit-code", "--name", "other", "--baseline", str(bx), "--exclude", "app/**"),
    ])
    rc, out, err = r[0]
    assert rc == 2 and out == ""
    assert err == "Error: baseline target mismatch: T (baseline) vs other (target)\n", err
    assert "exclude mismatch" not in err


def test_b5_older_refusals_keep_precedence(fx, tmp_path):
    t, _base, bx, _d0, _d1 = fx
    missing = tmp_path / "nope.json"
    notdoc = tmp_path / "notdoc.json"
    notdoc.write_text("[]\n", encoding="utf-8")
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(missing), "--exclude", "app/**"),
        _scan(t, "--exit-code", "--baseline", str(notdoc), "--exclude", "app/**"),
        _scan(t, "--baseline", str(bx), "--exclude", "app/**"),
        _scan(t, "--exit-code", "--match", "zzqq-no-record-matches-this", "--baseline", str(bx),
              "--exclude", "app/**"),
        _scan(t, "--exit-code", "--match", "zzqq-no-record-matches-this"),
    ])
    for rc, out, _err in r:
        assert rc == 2 and out == ""
    assert r[0][2] == f"Error: not a file: {missing}\n"
    assert r[1][2] == f"Error: not a scan document: {notdoc}\n"
    assert r[2][2] == ("Error: --baseline requires --exit-code: a baseline only changes "
                       "the verdict, and without --exit-code there is no verdict to change\n")
    assert r[3][2].startswith("Error: scan applied 0 register records")
    assert r[3][2] == r[4][2]
    for res in r:
        assert "exclude mismatch" not in res[2]


# Behavior 6 -- only the globs are compared, never the files count.
def test_b6_files_count_drift_not_refused(fx, tmp_path):
    t, _base, _bx, _d0, d1 = fx
    doc = json.loads(json.dumps(d1))
    assert doc["exclude"]["files"] != 99
    doc["exclude"]["files"] = 99
    b99 = tmp_path / "b99.json"
    b99.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(b99), "--exclude", "app/**", "--exclude", "vendor/**"),
    ])
    rc, out, err = r[0]
    assert rc == 0, err
    assert err == ""
    assert "\nBaseline: " in out


# Behavior 7 -- a malformed exclude key is not a scan document.
@pytest.mark.parametrize("value", ["app/**", None, {"files": 1}, {"globs": [1]}],
                         ids=["string", "null", "no-globs", "int-glob"])
def test_b7_malformed_exclude_not_a_scan_document(fx, tmp_path, value):
    t, _base, _bx, d0, _d1 = fx
    doc = json.loads(json.dumps(d0))
    doc["exclude"] = value
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(doc) + "\n", encoding="utf-8")
    r = _batch([
        _scan(t, "--exit-code", "--baseline", str(p)),
        _scan(t, "--exit-code", "--baseline", str(p), "--exclude", "app/**"),
    ])
    for rc, out, err in r:
        assert rc == 2
        assert out == ""
        assert err == f"Error: not a scan document: {p}\n", err


# Byte stability of the refusal across hash seeds.
def test_refusal_byte_stable_across_hash_seeds(fx):
    t, _base, bx, _d0, _d1 = fx
    job = [_scan(t, "--exit-code", "--baseline", str(bx), "--exclude", "app/**")]
    a = _batch(job, seed="1")
    b = _batch(job, seed="4242")
    assert a == b
    assert a[0][0] == 2


# Behavior 8 -- the contract cell names the refusal, the default and the set comparison.
def test_b8_contract_cell():
    rows = [ln for ln in CONTRACT.read_text(encoding="utf-8").split("\n")
            if ln.startswith("| `radar scan ")]
    assert len(rows) == 1
    row = rows[0]
    assert "Error: baseline exclude mismatch: " in row
    i = row.index("Error: baseline exclude mismatch: ")
    window = row[max(0, i - 400): i + 400]
    assert "as a set" in window
    assert "no `exclude` key" in window
    assert "none" in window
