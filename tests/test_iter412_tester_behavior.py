"""Iteration 412 tester behaviors: the re-landed `radar prd --after FILE`.

Complements `test_iter410_tester_behavior.py` (which this iteration re-lands)
with arms that module does not exercise: a hand-off whose source gap is NOT
the top-ranked one (so "skip the top row" cannot pass), pending ids in
DOCUMENT order on a reordered story list, composition with `--layer`,
`--with-fixtures` and `--project`, an extra-key / pretty-printed DONE file,
and a real child process so stdout/stderr/exit-code separation is observed
at the process boundary.

Black-box: drives the public CLI only (`agent_gap_radar.cli.main` in-process,
or a child interpreter calling it) and reads stdout, stderr and the exit
code. Registers are tmp dirs holding copies of a few committed records; DONE
files are built from the tmp register's own `radar prd` stdout. No commit sha,
no line number, no wall-clock bound, no network.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
# GAP-041 (observability) and GAP-003 (orchestration) are c=5, GAP-008 is c=4,
# GAP-010 is c=1 (below the default floor of 2).
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


def _layer(gid: str) -> str:
    return json.loads(_src(gid).read_text(encoding="utf-8"))["layer"]


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _doc(reg: str, *extra: str) -> dict:
    rc, out, err = _run(["prd", reg, *extra])
    assert rc == 0, err
    return json.loads(out)


def _write_done(ws: pathlib.Path, doc: dict, name: str, passes=None, **dump) -> str:
    doc = json.loads(json.dumps(doc))
    for i, story in enumerate(doc["stories"]):
        story["passes"] = True if passes is None else passes[i]
    (ws / name).write_text(json.dumps(doc, **dump), encoding="utf-8")
    return name


def _note(x: str, typed: str, n: int) -> str:
    return (
        f"Note: skipped {x} -- {typed} reports {n}/{n} stories pass; "
        f"the register still records it as {_status(x)}\n"
    )


# ---- B1: the skipped id is DONE's sourceGap.id, not "the top row" ----------


def test_b1_non_top_source_gap_is_the_one_skipped(ws):
    reg = _register(ws / "reg")
    # premise: GAP-003 is not what an unflagged run selects
    assert _doc(reg)["sourceGap"]["id"] == "GAP-041"
    doc3 = _doc(reg, "--gap", "GAP-003")
    assert doc3["sourceGap"]["id"] == "GAP-003"
    done = _write_done(ws, doc3, "done3.json")
    reg2 = _register(ws / "reg2", [g for g in IDS if g != "GAP-003"])
    rc, out, err = _run(["prd", reg, "--after", done])
    rc2, out2, _ = _run(["prd", reg2])
    assert (rc, rc2) == (0, 0), err
    assert out == out2
    # skipping a NON-top record leaves the top record selected
    assert json.loads(out)["sourceGap"]["id"] == "GAP-041"
    assert err == _note("GAP-003", done, len(doc3["stories"]))


def test_b1_pretty_printed_done_with_extra_keys_is_accepted(ws):
    reg = _register(ws / "reg")
    doc = _doc(reg)
    doc["consumerNote"] = {"loop": "finished"}  # a key radar never writes
    done = _write_done(ws, doc, "pretty.json", indent=4, sort_keys=True)
    (ws / done).write_text((ws / done).read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    reg2 = _register(ws / "reg2", [g for g in IDS if g != "GAP-041"])
    a = _run(["prd", reg, "--after", done])
    b = _run(["prd", reg2])
    assert (a[0], a[1]) == (b[0], b[1]) and a[0] == 0
    assert a[2] == _note("GAP-041", done, len(doc["stories"]))


def test_b1_stdout_single_trailing_newline(ws):
    reg = _register(ws / "reg")
    done = _write_done(ws, _doc(reg), "d.json")
    rc, out, _ = _run(["prd", reg, "--after", done])
    assert rc == 0
    assert out.endswith("\n") and not out.endswith("\n\n")
    json.loads(out)  # stdout carries only the document


# ---- B2: pending ids follow DOCUMENT order ---------------------------------


def test_b2_pending_ids_in_document_order_not_sorted(ws):
    reg = _register(ws / "reg")
    doc = _doc(reg)
    n = len(doc["stories"])
    assert n >= 3  # premise: enough stories for an order to be observable
    doc["stories"] = list(reversed(doc["stories"]))
    passes = [False, True] + [False] * (n - 2)
    done = _write_done(ws, doc, "rev.json", passes=passes)
    ids = [s["id"] for s in doc["stories"]]
    pending = [i for i, p in zip(ids, passes) if not p]
    assert pending != sorted(pending)  # premise: document order != sorted order
    rc, out, err = _run(["prd", reg, "--after", done])
    assert (rc, out) == (2, "")
    assert err == f"Error: hand-off not finished: 1/{n} stories pass (pending: {', '.join(pending)})\n"


# ---- B3/B4: refusals --------------------------------------------------------


def test_b4_unknown_string_id(ws):
    reg = _register(ws / "reg")
    doc = _doc(reg)
    doc["sourceGap"]["id"] = "GAP-999"
    done = _write_done(ws, doc, "ghost.json")
    rc, out, err = _run(["prd", reg, "--after", done])
    assert (rc, out) == (2, "")
    assert err == f"Error: --after {done}: sourceGap.id GAP-999 is not in the register\n"


def test_b3_passes_false_string_is_structural_not_pending(ws):
    reg = _register(ws / "reg")
    doc = _doc(reg)
    n = len(doc["stories"])
    done = _write_done(ws, doc, "strfalse.json", passes=["false"] + [True] * (n - 1))
    rc, out, err = _run(["prd", reg, "--after", done])
    assert (rc, out) == (2, "")
    assert err.startswith(f"Error: --after {done}: ") and err.count("\n") == 1
    assert "hand-off not finished" not in err


# ---- B6: composes with --layer, --with-fixtures, --project ------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["--with-fixtures"],
        ["--project", "demo"],
        ["--layer", "observability"],
        ["--layer", "orchestration"],
    ],
    ids=["with-fixtures", "project", "layer-of-x", "layer-other"],
)
def test_b6_composes_with_other_prd_flags(ws, extra):
    reg = _register(ws / "reg")
    reg2 = _register(ws / "reg2", [g for g in IDS if g != "GAP-041"])
    assert _layer("GAP-041") == "observability"  # premise for the layer arms
    done = _write_done(ws, _doc(reg), "done.json")
    a = _run(["prd", reg, *extra, "--after", done])
    b = _run(["prd", reg2, *extra])
    assert a[0] == b[0]
    assert a[1] == b[1]
    if extra == ["--layer", "observability"]:
        # X is the only citable record in its layer: X is removed AFTER the
        # narrowing and BEFORE the floor (contract), so the run reports the
        # skip and then the existing floor refusal (default floor 2, per --help)
        assert (a[0], a[1]) == (2, "")
        n = len(_doc(reg)["stories"])
        assert a[2] == _note("GAP-041", done, n) + "Error: no gap clears the confidence floor 2\n"
    else:
        assert a[0] == 0
        assert a[2] == _note("GAP-041", done, len(_doc(reg)["stories"]))


# ---- B7: read-only; list/show still display the recorded status --------------


def _digest(*roots: pathlib.Path) -> dict[str, str]:
    out = {}
    for root in roots:
        paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for p in paths:
            out[str(p.relative_to(root.parent))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_b7_views_unchanged_after_a_skip(ws):
    reg = _register(ws / "reg")
    done = _write_done(ws, _doc(reg), "done.json")
    before = _digest(ws / "reg", ws / done)
    views = [["list", reg, "--floor", "0"], ["show", reg, "GAP-041"], ["report", reg]]
    pre = [_run(v) for v in views]
    for _ in range(2):
        assert _run(["prd", reg, "--after", done])[0] == 0
    _run(["prd", reg, "--after", "missing.json"])
    assert [_run(v) for v in views] == pre
    assert _digest(ws / "reg", ws / done) == before
    assert "GAP-041" in pre[0][1]  # list still shows the skipped record


# ---- process boundary --------------------------------------------------------

_DRIVER = "import sys\nfrom agent_gap_radar.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"


def _proc(ws: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), env.get("PYTHONPATH", "")])
    return subprocess.run(
        [sys.executable, "-c", _DRIVER, *args],
        capture_output=True, cwd=ws, env=env,
    )


def test_process_boundary_success_and_refusal(ws):
    reg = _register(ws / "reg")
    doc = _doc(reg)
    done = _write_done(ws, doc, "done.json")
    n = len(doc["stories"])
    pend = _write_done(ws, doc, "pend.json", passes=[True] * (n - 1) + [False])
    ok = _proc(ws, "prd", reg, "--after", done)
    assert ok.returncode == 0, ok.stderr
    assert ok.stdout.endswith(b"}\n") and not ok.stdout.endswith(b"\n\n")
    assert ok.stderr.decode() == _note("GAP-041", done, n)
    bad = _proc(ws, "prd", reg, "--after", pend)
    assert bad.returncode == 2
    assert bad.stdout == b""
    assert bad.stderr.startswith(b"Error: hand-off not finished: ")
    clash = _proc(ws, "prd", reg, "--gap", "GAP-003", "--after", "nope.json")
    assert (clash.returncode, clash.stdout) == (2, b"")
    assert clash.stderr.startswith(b"Error: --gap names the record")
