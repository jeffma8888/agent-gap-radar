"""Iteration 410 tester behaviors: `radar prd --after FILE` (the hand-off round-trip).

Black-box: every assertion drives the public CLI (`agent_gap_radar.cli.main`
in-process, or a child interpreter for the pre-change comparison) and reads
only stdout, stderr and the exit code. Registers are tmp dirs holding copies
of a few committed records (never a live-register census); DONE files are
built from the tmp register's own `radar prd` output. Nothing touches the
network.

The "no flag means no change" oracle runs the PRE-FEATURE commit `daacbea`
extracted with `git archive` (an immutable ancestor, never HEAD); those nodes
skip when that commit is absent (a shallow clone).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
PRE_FEATURE_SHA = "daacbea"
# GAP-041 / GAP-003 are c=5, GAP-008 is c=4, GAP-010 is c=1 (below the default floor).
IDS = ("GAP-041", "GAP-003", "GAP-008", "GAP-010")


def _run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(args)
        except SystemExit as exc:  # argparse paths
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def _src(gap_id: str) -> pathlib.Path:
    (path,) = sorted(GAPS.glob(f"{gap_id}-*.json"))
    return path


def _register(root: pathlib.Path, ids=IDS) -> str:
    root.mkdir(parents=True, exist_ok=True)
    for gid in ids:
        src = _src(gid)
        (root / src.name).write_bytes(src.read_bytes())
    return root.name


def _status(gid: str) -> str:
    return json.loads(_src(gid).read_text(encoding="utf-8"))["status"]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _done(ws: pathlib.Path, reg: str, name: str = "done.json", *extra: str, passes=None) -> tuple[str, dict]:
    """Write REG's prd document with every story's passes set (default: all true)."""
    rc, out, err = _run(["prd", reg, *extra])
    assert rc == 0, err
    doc = json.loads(out)
    stories = doc["stories"]
    for i, story in enumerate(stories):
        story["passes"] = True if passes is None else passes[i]
    # any JSON formatting is allowed: write it compact, not as radar renders it
    (ws / name).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return name, doc


def _tree_digest(*roots: pathlib.Path) -> dict[str, str]:
    out = {}
    for root in roots:
        paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for p in paths:
            out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ---- B1 finished hand-off moves on ----------------------------------------


def test_b1_finished_handoff_equals_register_without_x(ws):
    reg = _register(ws / "reg")
    done, doc = _done(ws, reg)
    x = doc["sourceGap"]["id"]
    assert x == "GAP-041"  # premise: the top-ranked citable gap is the one handed off
    reg2 = _register(ws / "reg2", [g for g in IDS if g != x])
    rc, out, err = _run(["prd", reg, "--after", done])
    rc2, out2, err2 = _run(["prd", reg2])
    assert (rc, rc2) == (0, 0), err
    assert out == out2
    assert json.loads(out)["sourceGap"]["id"] != x
    n = len(doc["stories"])
    assert err == (
        f"Note: skipped {x} -- {done} reports {n}/{n} stories pass; "
        f"the register still records it as {_status(x)}\n"
    )
    assert out.endswith("}\n") and not out.endswith("\n\n")


def test_b1_note_names_file_as_typed_and_register_status(ws):
    reg = _register(ws / "reg")
    # a non-open status read from the register, not asserted by DONE
    rec = next((ws / "reg").glob("GAP-041-*.json"))
    data = json.loads(rec.read_text(encoding="utf-8"))
    (ws / "sub").mkdir()
    _, doc = _done(ws, reg, "sub/handoff.json")
    typed = "./sub/../sub/handoff.json"
    rc, _, err = _run(["prd", reg, "--after", typed])
    assert rc == 0
    n = len(doc["stories"])
    assert err == (
        f"Note: skipped GAP-041 -- {typed} reports {n}/{n} stories pass; "
        f"the register still records it as {data['status']}\n"
    )


# ---- B2 unfinished hand-off is refused ------------------------------------


@pytest.mark.parametrize("mask", ["first-only", "none", "last-false"])
def test_b2_pending_story_refused(ws, mask):
    reg = _register(ws / "reg")
    rc, out, _ = _run(["prd", reg])
    n = len(json.loads(out)["stories"])
    assert n >= 2  # premise: a multi-story document
    passes = {
        "first-only": [True] + [False] * (n - 1),
        "none": [False] * n,
        "last-false": [True] * (n - 1) + [False],
    }[mask]
    done, doc = _done(ws, reg, passes=passes)
    ids = [s["id"] for s in doc["stories"]]
    pending = [i for i, p in zip(ids, passes) if not p]
    rc, out, err = _run(["prd", reg, "--after", done])
    assert rc == 2
    assert out == ""
    assert err == (
        f"Error: hand-off not finished: {sum(passes)}/{n} stories pass "
        f"(pending: {', '.join(pending)})\n"
    )


# ---- B3 not a prd document ------------------------------------------------


def _good_doc(ws: pathlib.Path, reg: str) -> dict:
    return _done(ws, reg)[1]


def _malformed(doc: dict) -> dict[str, bytes | None]:
    def mut(fn):
        d = json.loads(json.dumps(doc))
        fn(d)
        return json.dumps(d).encode()

    cases: dict[str, bytes | None] = {
        "missing": None,
        "not-json": b"{not json",
        "non-utf8": b"\xff\xfe{",
        "top-list": b"[]",
        "top-string": b'"prd"',
        "no-sourcegap": mut(lambda d: d.pop("sourceGap")),
        "sourcegap-list": mut(lambda d: d.__setitem__("sourceGap", [])),
        "sourcegap-id-int": mut(lambda d: d["sourceGap"].__setitem__("id", 41)),
        "sourcegap-id-missing": mut(lambda d: d["sourceGap"].pop("id")),
        "no-stories": mut(lambda d: d.pop("stories")),
        "stories-object": mut(lambda d: d.__setitem__("stories", {})),
        "stories-empty": mut(lambda d: d.__setitem__("stories", [])),
        "story-not-object": mut(lambda d: d["stories"].__setitem__(0, "US-001")),
        "story-id-int": mut(lambda d: d["stories"][0].__setitem__("id", 1)),
        "passes-int": mut(lambda d: d["stories"][0].__setitem__("passes", 1)),
        "passes-string": mut(lambda d: d["stories"][0].__setitem__("passes", "true")),
        "passes-null": mut(lambda d: d["stories"][0].__setitem__("passes", None)),
        "passes-missing": mut(lambda d: d["stories"][0].pop("passes")),
    }
    return cases


CASES = list(_malformed({"sourceGap": {"id": "x"}, "stories": [{"id": "a", "passes": True}]}))


@pytest.mark.parametrize("case", CASES)
def test_b3_not_a_prd_document(ws, case):
    reg = _register(ws / "reg")
    payload = _malformed(_good_doc(ws, reg))[case]
    name = f"bad-{case}.json"
    if payload is not None:
        (ws / name).write_bytes(payload)
    rc, out, err = _run(["prd", reg, "--after", name])
    assert rc == 2
    assert out == ""
    assert err.startswith(f"Error: --after {name}: "), err
    assert err.count("\n") == 1 and err.endswith("\n")
    assert str(ws) not in err  # no absolute path leak beyond what was typed


def test_b3_directory_is_refused(ws):
    reg = _register(ws / "reg")
    (ws / "adir").mkdir()
    rc, out, err = _run(["prd", reg, "--after", "adir"])
    assert (rc, out) == (2, "")
    assert err.startswith("Error: --after adir: ") and err.count("\n") == 1


def test_b3_structural_check_outranks_pending(ws):
    # a document with a pending story AND a non-boolean passes is "not a prd
    # document" (B3), not "hand-off not finished" (B2)
    reg = _register(ws / "reg")
    doc = _good_doc(ws, reg)
    doc["stories"][0]["passes"] = False
    doc["stories"][-1]["passes"] = "true"
    (ws / "mixed.json").write_text(json.dumps(doc), encoding="utf-8")
    rc, out, err = _run(["prd", reg, "--after", "mixed.json"])
    assert (rc, out) == (2, "")
    assert err.startswith("Error: --after mixed.json: ")


# ---- B4 unknown source gap -------------------------------------------------


def test_b4_unknown_source_gap(ws):
    full = _register(ws / "full")
    done, _ = _done(ws, full)  # GAP-041 hand-off
    small = _register(ws / "small", ["GAP-003", "GAP-008"])
    rc, out, err = _run(["prd", small, "--after", done])
    assert (rc, out) == (2, "")
    assert err == f"Error: --after {done}: sourceGap.id GAP-041 is not in the register\n"
    # premise: the register that holds the record accepts the same file
    assert _run(["prd", full, "--after", done])[0] == 0


# ---- B5 --gap contradicts --after -----------------------------------------


@pytest.mark.parametrize("exists", [True, False])
def test_b5_gap_conflicts_with_after(ws, exists):
    reg = _register(ws / "reg")
    name = "done.json" if exists else "nope.json"
    if exists:
        _done(ws, reg)
    rc, out, err = _run(["prd", reg, "--gap", "GAP-003", "--after", name])
    assert (rc, out) == (2, "")
    assert err.startswith("Error: --gap names the record"), err
    first = err.splitlines()[0]
    assert "--after" in first


# ---- B6 composes with narrowing and the floor ------------------------------


def test_b6_composes_with_match(ws):
    reg = _register(ws / "reg")
    reg2 = _register(ws / "reg2", [g for g in IDS if g != "GAP-041"])
    term = "context"
    rc, out, _ = _run(["prd", reg, "--match", term])
    assert rc == 0 and json.loads(out)["sourceGap"]["id"] == "GAP-041"  # premise
    done, _ = _done(ws, reg, "done.json", "--match", term)
    a = _run(["prd", reg, "--match", term, "--after", done])
    b = _run(["prd", reg2, "--match", term])
    assert a[0] == b[0]
    assert a[1] == b[1]
    assert a[2].startswith("Note: skipped GAP-041 -- ")


def test_b6_composes_with_floor(ws):
    reg = _register(ws / "reg")
    reg2 = _register(ws / "reg2", [g for g in IDS if g != "GAP-041"])
    done, _ = _done(ws, reg)
    a = _run(["prd", reg, "--floor", "4", "--after", done])
    b = _run(["prd", reg2, "--floor", "4"])
    assert (a[0], a[1]) == (b[0], b[1])
    assert a[0] == 0


def test_b6_floor_exhausted_after_skip(ws):
    reg = _register(ws / "reg", ["GAP-041", "GAP-008", "GAP-010"])
    done, doc = _done(ws, reg)
    assert doc["sourceGap"]["id"] == "GAP-041"
    rc, out, err = _run(["prd", reg, "--floor", "5", "--after", done])
    assert rc == 2
    assert out == ""
    lines = err.splitlines()
    n = len(doc["stories"])
    assert lines[0] == (
        f"Note: skipped GAP-041 -- {done} reports {n}/{n} stories pass; "
        f"the register still records it as {_status('GAP-041')}"
    )
    # the existing refusal line, exactly as the register without X gives it
    reg2 = _register(ws / "reg2", ["GAP-008", "GAP-010"])
    rc2, out2, err2 = _run(["prd", reg2, "--floor", "5"])
    assert (rc2, out2) == (2, "")
    assert any(l.startswith("Error: no gap clears the confidence floor 5") for l in lines)
    assert "\n".join(lines[1:]) + "\n" == err2


# ---- B7 read-only, and no flag means no change -----------------------------


def test_b7_read_only(ws):
    reg = _register(ws / "reg")
    done, _ = _done(ws, reg)
    n = len(json.loads(_run(["prd", reg])[1])["stories"])
    _done(ws, reg, "pending.json", passes=[False] * n)
    before = _tree_digest(ws / "reg", ws / done, ws / "pending.json")
    for argv in (
        ["prd", reg, "--after", done],
        ["prd", reg, "--after", "pending.json"],
        ["prd", reg, "--floor", "5", "--after", done],
        ["prd", reg, "--match", "context", "--after", done],
    ):
        _run(argv)
    assert _tree_digest(ws / "reg", ws / done, ws / "pending.json") == before
    # display verbs still show X as recorded
    rc, out, _ = _run(["list", reg])
    assert rc == 0 and "GAP-041" in out


def _pre_feature_src(tmp_path: pathlib.Path) -> pathlib.Path:
    probe = subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"{PRE_FEATURE_SHA}^{{commit}}"],
        capture_output=True,
    )
    if probe.returncode != 0:
        pytest.skip(f"pre-feature commit {PRE_FEATURE_SHA} not available (shallow clone?)")
    tar_path = tmp_path / "pre.tar"
    with tar_path.open("wb") as fh:
        subprocess.run(
            ["git", "-C", str(REPO), "archive", PRE_FEATURE_SHA, "src"], stdout=fh, check=True
        )
    dest = tmp_path / "pre"
    with tarfile.open(tar_path) as tf:
        tf.extractall(dest, filter="data")
    return dest / "src"


_DRIVER = r"""
import contextlib, io, json, sys
from agent_gap_radar.cli import main
res = []
for argv in json.loads(sys.argv[1]):
    o, e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        try:
            rc = main(argv)
        except SystemExit as exc:
            rc = exc.code
    res.append([rc, o.getvalue(), e.getvalue()])
sys.stdout.write(json.dumps(res))
"""


def _child(src: pathlib.Path, argvs, cwd) -> list:
    env = dict(os.environ, PYTHONPATH=str(src))
    proc = subprocess.run(
        [sys.executable, "-c", _DRIVER, json.dumps(argvs)],
        capture_output=True, text=True, cwd=cwd, env=env, check=True,
    )
    return json.loads(proc.stdout)


def test_b7_no_flag_byte_identical_to_pre_feature(ws):
    pre = _pre_feature_src(ws)
    reg = _register(ws / "reg")
    argvs = [
        ["prd", reg],
        ["prd", reg, "--floor", "4"],
        ["prd", reg, "--floor", "5"],
        ["prd", reg, "--floor", "9"],
        ["prd", reg, "--gap", "GAP-010"],
        ["prd", reg, "--gap", "GAP-003", "--with-fixtures"],
        ["prd", reg, "--gap", "GAP-999"],
        ["prd", reg, "--match", "context"],
        ["prd", reg, "--match", "zzzz-no-such-text"],
        ["prd", reg, "--layer", "observability"],
        ["prd", reg, "--gap", "GAP-003", "--match", "x"],
        ["prd", reg, "--project", "demo"],
        ["prd", "no-such-dir"],
        ["list", reg],
        ["report", reg],
        ["show", reg, "GAP-041"],
    ]
    old = _child(pre, argvs, ws)
    new = _child(REPO / "src", argvs, ws)
    for argv, o, n in zip(argvs, old, new):
        assert o == n, argv


# ---- B8 surface is published -----------------------------------------------


def test_b8_help_lists_after_with_metavar():
    rc, out, _ = _run(["prd", "--help"])
    assert rc == 0
    assert "[--after FILE]" in out
    assert re.search(r"^\s+--after FILE\b", out, re.M)


def test_b8_contract_row_and_readme():
    contract = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    rows = [l for l in contract.splitlines() if l.startswith("| `radar prd ")]
    assert len(rows) == 1
    cells = rows[0].split(" | ")
    assert "[--after FILE]" in cells[0]
    promise = " | ".join(cells[1:])
    assert "pending" in promise
    assert "hand-off not finished" in promise
    assert re.search(r"no (record and no )?status is changed", promise)
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert any("radar prd" in l and "--after" in l for l in readme.splitlines())


def test_b8_inventory_appends_after_last():
    sys.path.insert(0, str(REPO / "tests"))
    try:
        import _surface_inventory as inv  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    blob = repr(getattr(inv, "EXPECTED_ARGUMENTS", None) or vars(inv))
    assert "--after" in blob
    rc, out, _ = _run(["prd", "--help"])
    usage = out.split("\n\n")[0]
    flags = re.findall(r"\[(--[a-z-]+)", usage)
    assert flags[-1] == "--after", flags
    assert flags.index("--after") == flags.index("--match") + 1
