"""Iteration 413 tester behaviors: `radar prd --after FILE` is repeatable.

Before this iteration `--after` was last-wins: `--after d1 --after d2` silently
dropped d1 and re-emitted the gap the loop finished two hand-offs ago. These
nodes pin the repeatable form: every finished FILE's gap is skipped, one Note
per FILE in argv order, and any bad FILE refuses the whole invocation.

Black-box: drives the public CLI only (`agent_gap_radar.cli.main` in-process,
or a child interpreter calling it) and reads stdout, stderr and the exit code.
Registers are tmp dirs holding copies of committed records; hand-off FILEs are
built from the tmp register's own `radar prd` stdout and live OUTSIDE the
register dir (the loader reads every `*.json`). No commit sha, no line
number, no wall-clock bound, no network.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
# bare `prd` over a copy of these three selects GAP-041, then GAP-003, then GAP-016
IDS = ("GAP-041", "GAP-003", "GAP-016")


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


def _record(gid: str) -> dict:
    return json.loads(_src(gid).read_text(encoding="utf-8"))


def _register(root: pathlib.Path, ids=IDS) -> str:
    root.mkdir(parents=True, exist_ok=True)
    for gid in ids:
        src = _src(gid)
        (root / src.name).write_bytes(src.read_bytes())
    return root.name


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _doc(reg: str, *extra: str) -> dict:
    rc, out, err = _run(["prd", reg, *extra])
    assert rc == 0, err
    return json.loads(out)


def _write_done(ws: pathlib.Path, doc: dict, name: str, passes=None) -> str:
    doc = json.loads(json.dumps(doc))
    for i, story in enumerate(doc["stories"]):
        story["passes"] = True if passes is None else passes[i]
    path = ws / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return name


def _note(gid: str, typed: str, n: int) -> str:
    return (
        f"Note: skipped {gid} -- {typed} reports {n}/{n} stories pass; "
        f"the register still records it as {_record(gid)['status']}\n"
    )


@pytest.fixture
def loop(ws):
    """The fixture of the spec: reg (041/003/016), d1 = finished prd of GAP-041
    built by bare prd, d2 = finished prd of GAP-003 built by `prd --after d1`."""
    reg = _register(ws / "reg")
    doc1 = _doc(reg)
    assert doc1["sourceGap"]["id"] == "GAP-041"  # premise
    d1 = _write_done(ws, doc1, "d1.json")
    doc2 = _doc(reg, "--after", d1)
    assert doc2["sourceGap"]["id"] == "GAP-003"  # premise: the single-flag skip works
    d2 = _write_done(ws, doc2, "d2.json")
    return {
        "reg": reg, "d1": d1, "d2": d2, "doc1": doc1, "doc2": doc2,
        "n1": len(doc1["stories"]), "n2": len(doc2["stories"]),
    }


# ---- B1: both finished gaps leave the selection ------------------------------


def test_b1_two_finished_handoffs_select_the_third_gap(loop):
    rc, out, err = _run(["prd", loop["reg"], "--after", loop["d1"], "--after", loop["d2"]])
    assert rc == 0, err
    got = json.loads(out)["sourceGap"]["id"]
    assert got not in ("GAP-041", "GAP-003")  # the last-wins defect returned GAP-041
    assert got == "GAP-016"
    rc_g, out_g, _ = _run(["prd", loop["reg"], "--gap", "GAP-016"])
    assert rc_g == 0
    assert out == out_g  # byte-identical to the hand-picked document
    assert out.endswith("\n") and not out.endswith("\n\n")


# ---- B2: one Note per FILE, argv order, FILE as typed -------------------------


@pytest.mark.parametrize("order", ["d1-d2", "d2-d1"])
def test_b2_one_note_per_file_in_argv_order(loop, order):
    files = [loop["d1"], loop["d2"]] if order == "d1-d2" else [loop["d2"], loop["d1"]]
    argv = ["prd", loop["reg"]]
    for f in files:
        argv += ["--after", f]
    rc, out, err = _run(argv)
    assert rc == 0, err
    notes = {loop["d1"]: _note("GAP-041", loop["d1"], loop["n1"]),
             loop["d2"]: _note("GAP-003", loop["d2"], loop["n2"])}
    assert err == "".join(notes[f] for f in files)
    assert err.count("\n") == 2
    assert out == _run(["prd", loop["reg"], "--gap", "GAP-016"])[1]


def test_b2_file_is_spelled_as_typed(loop, ws):
    (ws / "sub").mkdir()
    (ws / "sub" / "x1.json").write_bytes((ws / loop["d1"]).read_bytes())
    typed1 = "./sub/../sub/x1.json"
    typed2 = str(ws / loop["d2"])  # absolute, as a caller could type it
    rc, out, err = _run(["prd", loop["reg"], "--after", typed1, "--after", typed2])
    assert rc == 0, err
    assert err == _note("GAP-041", typed1, loop["n1"]) + _note("GAP-003", typed2, loop["n2"])


# ---- B3: a single --after is unchanged ---------------------------------------


def test_b3_single_after_finished_and_refusals_unchanged(loop, ws):
    reg, d1 = loop["reg"], loop["d1"]
    # finished: the next gap, one Note
    rc, out, err = _run(["prd", reg, "--after", d1])
    assert (rc, err) == (0, _note("GAP-041", d1, loop["n1"]))
    assert out == _run(["prd", reg, "--gap", "GAP-003"])[1]
    # pending
    n = loop["n1"]
    pend = _write_done(ws, loop["doc1"], "pend.json", passes=[True] * (n - 1) + [False])
    last = loop["doc1"]["stories"][-1]["id"]
    assert _run(["prd", reg, "--after", pend]) == (
        2, "", f"Error: hand-off not finished: {n - 1}/{n} stories pass (pending: {last})\n")
    # not a prd document
    (ws / "junk.json").write_text("[1, 2]", encoding="utf-8")
    rc, out, err = _run(["prd", reg, "--after", "junk.json"])
    assert (rc, out) == (2, "") and err.startswith("Error: --after junk.json: ")
    assert err.count("\n") == 1
    # id not in the register
    ghost = json.loads(json.dumps(loop["doc1"]))
    ghost["sourceGap"]["id"] = "GAP-999"
    g = _write_done(ws, ghost, "ghost.json")
    assert _run(["prd", reg, "--after", g]) == (
        2, "", f"Error: --after {g}: sourceGap.id GAP-999 is not in the register\n")
    # beside --gap
    rc, out, err = _run(["prd", reg, "--gap", "GAP-003", "--after", d1])
    assert (rc, out) == (2, "")
    assert "--gap names the record, so it cannot be combined with --after" in err


# ---- B4: any pending FILE refuses the whole invocation -----------------------


@pytest.mark.parametrize("where", ["first", "after-a-finished-one"])
def test_b4_pending_file_refuses_whole_invocation(loop, ws, where):
    n = loop["n2"]
    passes = [False] + [True] * (n - 1)
    pend = _write_done(ws, loop["doc2"], "p2.json", passes=passes)
    first_id = loop["doc2"]["stories"][0]["id"]
    files = [pend, loop["d1"]] if where == "first" else [loop["d1"], pend]
    argv = ["prd", loop["reg"]]
    for f in files:
        argv += ["--after", f]
    rc, out, err = _run(argv)
    assert (rc, out) == (2, "")
    assert err == f"Error: hand-off not finished: {n - 1}/{n} stories pass (pending: {first_id})\n"
    assert "Note:" not in err


def test_b4_first_pending_file_in_argv_order_is_named(loop, ws):
    n1, n2 = loop["n1"], loop["n2"]
    p1 = _write_done(ws, loop["doc1"], "p1.json", passes=[False] * n1)
    p2 = _write_done(ws, loop["doc2"], "p2.json", passes=[True] * (n2 - 1) + [False])
    msg1 = (f"Error: hand-off not finished: 0/{n1} stories pass "
            f"(pending: {', '.join(s['id'] for s in loop['doc1']['stories'])})\n")
    msg2 = (f"Error: hand-off not finished: {n2 - 1}/{n2} stories pass "
            f"(pending: {loop['doc2']['stories'][-1]['id']})\n")
    assert msg1 != msg2  # premise: the two refusals are distinguishable
    assert _run(["prd", loop["reg"], "--after", p1, "--after", p2]) == (2, "", msg1)
    assert _run(["prd", loop["reg"], "--after", p2, "--after", p1]) == (2, "", msg2)


# ---- B5: an unreadable / non-prd FILE refuses, first in argv order -----------


def _single_err(reg: str, f: str) -> str:
    rc, out, err = _run(["prd", reg, "--after", f])
    assert (rc, out) == (2, "")
    assert err.startswith(f"Error: --after {f}: ") and err.count("\n") == 1
    return err


@pytest.mark.parametrize("kind", ["missing", "not-json", "not-a-prd"])
def test_b5_bad_file_after_a_finished_one(loop, ws, kind):
    bad = {"missing": "nope.json", "not-json": "broken.json", "not-a-prd": "obj.json"}[kind]
    if kind == "not-json":
        (ws / bad).write_text("{not json", encoding="utf-8")
    elif kind == "not-a-prd":
        (ws / bad).write_text('{"hello": 1}', encoding="utf-8")
    want = _single_err(loop["reg"], bad)
    for files in ([loop["d1"], bad], [bad, loop["d1"]], [loop["d1"], loop["d2"], bad]):
        argv = ["prd", loop["reg"]]
        for f in files:
            argv += ["--after", f]
        assert _run(argv) == (2, "", want), files


def test_b5_first_bad_file_in_argv_order_is_named(loop, ws):
    (ws / "a.json").write_text("{not json", encoding="utf-8")
    want_a = _single_err(loop["reg"], "a.json")
    want_b = _single_err(loop["reg"], "b-missing.json")
    assert want_a != want_b
    assert _run(["prd", loop["reg"], "--after", "a.json", "--after", "b-missing.json"]) == (2, "", want_a)
    assert _run(["prd", loop["reg"], "--after", "b-missing.json", "--after", "a.json"]) == (2, "", want_b)


def test_b5_files_are_read_before_the_register(loop, ws):
    (ws / "a.json").write_text("{not json", encoding="utf-8")
    want = _single_err(loop["reg"], "a.json")
    rc, out, err = _run(["prd", "no-such-register-dir", "--after", loop["d1"], "--after", "a.json"])
    assert (rc, out, err) == (2, "", want)


@pytest.mark.parametrize("order", ["bad-then-pending", "pending-then-bad"])
def test_b4_b5_mixed_bad_and_pending_first_in_argv_order_wins(loop, ws, order):
    # Spec ambiguity (reviewer NIT): b4 says "first PENDING file", b5 "first
    # INVALID file". Pinned reading: the first refusable FILE in argv order.
    n = loop["n1"]
    pend = _write_done(ws, loop["doc1"], "pend.json", passes=[True] * (n - 1) + [False])
    (ws / "bad.json").write_text("{not json", encoding="utf-8")
    bad_err = _single_err(loop["reg"], "bad.json")
    pend_err = _run(["prd", loop["reg"], "--after", pend])[2]
    assert pend_err.startswith("Error: hand-off not finished: ")
    files = ["bad.json", pend] if order == "bad-then-pending" else [pend, "bad.json"]
    want = bad_err if order == "bad-then-pending" else pend_err
    argv = ["prd", loop["reg"]]
    for f in files:
        argv += ["--after", f]
    assert _run(argv) == (2, "", want)


# ---- B6: an id outside the register refuses, with no Note --------------------


@pytest.mark.parametrize("where", ["last", "first", "middle"])
def test_b6_unknown_id_refuses_with_no_note(loop, ws, where):
    ghost = json.loads(json.dumps(loop["doc1"]))
    ghost["sourceGap"]["id"] = "GAP-999"
    g = _write_done(ws, ghost, "ghost.json")
    files = {"last": [loop["d1"], loop["d2"], g],
             "first": [g, loop["d1"]],
             "middle": [loop["d1"], g, loop["d2"]]}[where]
    argv = ["prd", loop["reg"]]
    for f in files:
        argv += ["--after", f]
    rc, out, err = _run(argv)
    assert (rc, out) == (2, "")
    assert err == f"Error: --after {g}: sourceGap.id GAP-999 is not in the register\n"
    assert "Note:" not in err


def test_b6_a_record_missing_from_this_register_is_unknown(loop, ws):
    # d2 names GAP-003, real in the repo register but absent from this copy
    reg2 = _register(ws / "reg2", ["GAP-041", "GAP-016"])
    rc, out, err = _run(["prd", reg2, "--after", loop["d1"], "--after", loop["d2"]])
    assert (rc, out) == (2, "")
    assert err == f"Error: --after {loop['d2']}: sourceGap.id GAP-003 is not in the register\n"


# ---- B7: two FILEs naming the same gap ---------------------------------------


def test_b7_same_gap_twice_skips_once_and_notes_twice(loop, ws):
    (ws / "again").mkdir()
    (ws / "again" / "d1.json").write_bytes((ws / loop["d1"]).read_bytes())
    other = "again/d1.json"
    rc, out, err = _run(["prd", loop["reg"], "--after", loop["d1"], "--after", other])
    assert rc == 0, err
    assert out == _run(["prd", loop["reg"], "--gap", "GAP-003"])[1]
    assert err == _note("GAP-041", loop["d1"], loop["n1"]) + _note("GAP-041", other, loop["n1"])


def test_b7_same_path_twice(loop):
    rc, out, err = _run(["prd", loop["reg"], "--after", loop["d1"], "--after", loop["d1"]])
    assert rc == 0, err
    assert json.loads(out)["sourceGap"]["id"] == "GAP-003"
    assert err == _note("GAP-041", loop["d1"], loop["n1"]) * 2


# ---- B8: skips that exhaust the floor ----------------------------------------


def test_b8_skips_exhaust_the_floor(loop, ws):
    reg2 = _register(ws / "reg2", ["GAP-041", "GAP-003"])
    rc, out, err = _run(["prd", reg2, "--after", loop["d1"], "--after", loop["d2"]])
    assert (rc, out) == (2, "")
    assert err == (_note("GAP-041", loop["d1"], loop["n1"])
                   + _note("GAP-003", loop["d2"], loop["n2"])
                   + "Error: no gap clears the confidence floor 2\n")


# ---- B9: --gap beside any --after refuses before reading a FILE --------------


@pytest.mark.parametrize("files", [["nope.json"], ["d1.json", "nope.json"], ["nope.json", "nope2.json"]])
def test_b9_gap_beside_after_refuses_before_reading(loop, files):
    argv = ["prd", loop["reg"], "--gap", "GAP-016"]
    for f in files:
        argv += ["--after", f]
    rc, out, err = _run(argv)
    assert (rc, out) == (2, "")
    ref = _run(["prd", loop["reg"], "--gap", "GAP-016", "--after", loop["d1"]])[2]
    assert "--gap names the record, so it cannot be combined with --after" in ref
    assert err == ref
    assert "nope" not in err


# ---- B10: --layer / --match compose; Note status from the WHOLE register -----


def test_b10_layer_composes_and_note_reports_whole_register_status(loop, ws):
    layer16 = _record("GAP-016")["layer"]
    assert layer16 not in (_record("GAP-041")["layer"], _record("GAP-003")["layer"])  # premise
    a = _run(["prd", loop["reg"], "--layer", layer16, "--after", loop["d1"], "--after", loop["d2"]])
    b = _run(["prd", loop["reg"], "--layer", layer16])
    assert a[0] == b[0] == 0, a[2]
    assert a[1] == b[1]
    # each Note names its record's status even though both are outside the layer
    assert a[2] == (_note("GAP-041", loop["d1"], loop["n1"])
                    + _note("GAP-003", loop["d2"], loop["n2"]))


def test_b10_layer_of_a_skipped_gap_then_floor(loop):
    layer3 = _record("GAP-003")["layer"]
    rc, out, err = _run(["prd", loop["reg"], "--layer", layer3,
                         "--after", loop["d1"], "--after", loop["d2"]])
    assert (rc, out) == (2, "")
    assert err == (_note("GAP-041", loop["d1"], loop["n1"])
                   + _note("GAP-003", loop["d2"], loop["n2"])
                   + "Error: no gap clears the confidence floor 2\n")


def test_b10_match_composes(loop, ws):
    word = _record("GAP-016")["title"].split()[-1]
    # premise: the --match narrows to a domain containing GAP-016
    assert _doc(loop["reg"], "--match", word)["sourceGap"]["id"] in IDS
    a = _run(["prd", loop["reg"], "--match", word, "--after", loop["d1"], "--after", loop["d2"]])
    reg3 = _register(ws / "reg3", ["GAP-016"])
    b = _run(["prd", reg3, "--match", word])
    assert a[0] == b[0] == 0, a[2]
    assert a[1] == b[1]
    assert a[2] == (_note("GAP-041", loop["d1"], loop["n1"])
                    + _note("GAP-003", loop["d2"], loop["n2"]))


def test_b10_partially_addressed_status_is_named(loop, ws):
    doc3 = _doc(loop["reg"], "--after", loop["d1"], "--after", loop["d2"])
    assert doc3["sourceGap"]["id"] == "GAP-016"
    d3 = _write_done(ws, doc3, "d3.json")
    reg4 = _register(ws / "reg4", [*IDS, "GAP-008"])
    rc, out, err = _run(["prd", reg4, "--after", loop["d1"], "--after", loop["d2"], "--after", d3])
    assert rc == 0, err
    assert json.loads(out)["sourceGap"]["id"] == "GAP-008"
    status16 = _record("GAP-016")["status"]
    assert err.splitlines()[2].endswith(f"the register still records it as {status16}")
    assert err.count("Note: skipped ") == 3


# ---- B11: help and contract --------------------------------------------------


def test_b11_help_lists_after_once():
    rc, out, _ = _run(["prd", "--help"])
    assert rc == 0
    option_lines = [ln for ln in out.splitlines() if re.match(r"^\s+--after\b", ln)]
    assert len(option_lines) == 1
    assert "[--after FILE]" in out


def test_b11_contract_row_says_after_repeats():
    text = CONTRACT.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| `radar prd [")]
    assert len(rows) == 1
    row = rows[0]
    synopsis = row.split("|")[1]
    assert "[--after FILE]" in synopsis and synopsis.count("--after") == 1
    body = row.lower()
    assert re.search(r"--after`? may be repeated", body)
    assert "argv order" in body
    assert "pending" in body and "refuses the whole invocation" in body


# ---- process boundary --------------------------------------------------------

_DRIVER = "import sys\nfrom agent_gap_radar.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"


def test_process_boundary_repeated_after(loop, ws):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), env.get("PYTHONPATH", "")])
    p = subprocess.run(
        [sys.executable, "-c", _DRIVER, "prd", loop["reg"], "--after", loop["d2"], "--after", loop["d1"]],
        capture_output=True, cwd=ws, env=env,
    )
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["sourceGap"]["id"] == "GAP-016"
    assert p.stdout.endswith(b"}\n") and not p.stdout.endswith(b"\n\n")
    assert p.stderr.decode() == (_note("GAP-003", loop["d2"], loop["n2"])
                                 + _note("GAP-041", loop["d1"], loop["n1"]))
