"""Iteration 379 (tester, black-box): too-deeply-nested input is an ``Error:`` exit 2.

A gap-record file or a ``--baseline`` file nested past what the parser can read must be
refused by every verb with its ordinary ``Error:`` line and exit 2 -- never a
``RecursionError`` traceback with exit 1 (exit 1 is the gate's "new finding" code).

Black-box only: every assertion is on exit code / stdout / stderr of the public CLI,
driven in-process through ``main(argv)`` plus one real ``python -m`` subprocess. Every
fixture lives under ``tmp_path``; the committed register is only ever copied.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CLAUSE = "unreadable/invalid JSON: nested too deeply to read"


def deep_array(n: int) -> str:
    return "[" * n + "]" * n


def deep_object(n: int) -> str:
    return '{"a":' * n + "1" + "}" * n


def deep_in_title(n: int) -> str:
    """A deep value spliced into an otherwise-valid record's ``title`` field."""
    rec = json.loads(_first_record().read_text(encoding="utf-8"))
    marker = "__DEEP__"
    rec["title"] = marker
    return json.dumps(rec).replace(json.dumps(marker), deep_array(n))


def _first_record() -> pathlib.Path:
    return sorted(GAPS.glob("*.json"))[0]


DEEP = {
    "array1500": lambda: deep_array(1500),
    "array100000": lambda: deep_array(100_000),
    "object100000": lambda: deep_object(100_000),
    "title_array1500": lambda: deep_in_title(1500),
}


def _run(capsys, argv: list) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _copy(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    dst = tmp_path / name / "gaps"
    shutil.copytree(GAPS, dst)
    return dst


def _assert_refused(code: int, out: str, err: str, filename: str) -> None:
    assert code == 2, (code, err[-400:])
    assert out == ""
    assert "Traceback" not in err and "RecursionError" not in err, err[-400:]
    lines = [ln for ln in err.splitlines() if ln.startswith("Error: ")]
    assert any(f"{filename}: {CLAUSE}" in ln for ln in lines), err[-600:]


@pytest.fixture
def clean(tmp_path):
    return _copy(tmp_path, "clean")


@pytest.fixture(params=sorted(DEEP))
def broken(request, tmp_path):
    reg = _copy(tmp_path, "broken")
    target = sorted(reg.glob("*.json"))[3]
    target.write_text(DEEP[request.param](), encoding="utf-8")
    return reg, target.name


# --- behavior 1: validate ----------------------------------------------------------

def test_b1_validate_refuses_deep_record(capsys, broken):
    reg, name = broken
    _assert_refused(*_run(capsys, ["validate", reg]), name)


# --- behavior 2: every register-reading verb -----------------------------------------

@pytest.mark.parametrize("verb", [["list"], ["report"], ["prd"]])
def test_b2_reading_verbs_refuse_deep_record(capsys, broken, verb):
    reg, name = broken
    _assert_refused(*_run(capsys, [*verb, reg]), name)


def test_b2_show_refuses_deep_record(capsys, broken):
    reg, name = broken
    _assert_refused(*_run(capsys, ["show", "GAP-001", reg]), name)


@pytest.mark.parametrize("json_flag", [[], ["--json"]])
@pytest.mark.parametrize("swap", [False, True])
def test_b2_diff_refuses_deep_record_on_either_side(capsys, broken, clean, swap, json_flag):
    reg, name = broken
    sides = [reg, clean] if swap else [clean, reg]
    _assert_refused(*_run(capsys, ["diff", *json_flag, *sides]), name)


def test_b1_moderately_deep_object_never_tracebacks(capsys, tmp_path):
    """Deep OBJECT 1500 is not in the spec's table; whatever clause it earns, it must
    still be an ``Error:`` line with exit 2 and no traceback."""
    reg = _copy(tmp_path, "obj1500")
    (reg / "GAP-OBJ.json").write_text(deep_object(1500), encoding="utf-8")
    code, out, err = _run(capsys, ["validate", reg])
    assert code == 2 and out == ""
    assert "Traceback" not in err and "RecursionError" not in err
    assert any(ln.startswith("Error: ") and "GAP-OBJ.json" in ln for ln in err.splitlines())


# --- behavior 3: byte-stable clause, no number --------------------------------------

def test_b3_stderr_identical_across_depths_and_shapes(capsys, tmp_path):
    errs = []
    for key in ("array1500", "array100000", "object100000", "title_array1500"):
        reg = _copy(tmp_path, key)
        (reg / "GAP-XYZ.json").write_text(DEEP[key](), encoding="utf-8")
        code, out, err = _run(capsys, ["validate", reg])
        _assert_refused(code, out, err, "GAP-XYZ.json")
        errs.append(err.replace(str(reg), "<R>"))
    assert len(set(errs)) == 1, errs
    clause_line = [ln for ln in errs[0].splitlines() if CLAUSE in ln][0]
    assert not any(ch.isdigit() for ch in clause_line.split("GAP-XYZ.json", 1)[1]), clause_line


# --- behavior 4: every bad file still reported ---------------------------------------

def test_b4_both_bad_files_named(capsys, tmp_path):
    reg = _copy(tmp_path, "two")
    recs = sorted(reg.glob("*.json"))
    deep, trunc = recs[1], recs[-1]
    deep.write_text(deep_array(1500), encoding="utf-8")
    trunc.write_text("{", encoding="utf-8")
    code, out, err = _run(capsys, ["validate", reg])
    _assert_refused(code, out, err, deep.name)
    assert trunc.name in err
    clauses = [c for ln in err.splitlines() for c in ln.split("; ")]
    trunc_clauses = [c for c in clauses if trunc.name in c]
    assert trunc_clauses and all(CLAUSE not in c for c in trunc_clauses), trunc_clauses
    assert [c for c in clauses if deep.name in c and CLAUSE in c], clauses


# --- behavior 5: deep --baseline -----------------------------------------------------

@pytest.fixture
def target(tmp_path):
    t = tmp_path / "target"
    t.mkdir()
    (t / "a.py").write_text("x = 1\n", encoding="utf-8")
    return t


@pytest.mark.parametrize("content", [deep_array(1500), deep_array(100_000),
                                     deep_object(100_000)],
                         ids=["array1500", "array100000", "object100000"])
@pytest.mark.parametrize("mode", [["--exit-code"], ["--exit-code", "--json"]],
                         ids=["exit-code", "exit-code-json"])
def test_b5_deep_baseline_is_exit_2(capsys, tmp_path, clean, target, content, mode):
    b = tmp_path / "baseline.json"
    b.write_text(content, encoding="utf-8")
    code, out, err = _run(capsys, ["scan", target, "--gaps", clean, *mode, "--baseline", b])
    assert code == 2, (code, err[-400:])
    assert out == ""
    assert "Traceback" not in err and "RecursionError" not in err
    assert f"Error: not a scan document: {b}" in err, err[-400:]


def test_b5_valid_baseline_control_is_not_refused(capsys, tmp_path, clean, target):
    """Control: the same call with a real scan document as baseline is accepted."""
    code, out, err = _run(capsys, ["scan", target, "--gaps", clean, "--json"])
    assert code == 0, err
    b = tmp_path / "good.json"
    b.write_text(out, encoding="utf-8")
    code, out2, err = _run(capsys, ["scan", target, "--gaps", clean, "--exit-code",
                                    "--baseline", b])
    assert code in (0, 1), err
    assert "Error:" not in err


def test_b5_real_process_exit_code(tmp_path, target):
    """A fresh interpreter: the default stack is the real one a CI gate sees."""
    clean = _copy(tmp_path, "proc")
    b = tmp_path / "deep.json"
    b.write_text(deep_array(1500), encoding="utf-8")
    p = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "scan", str(target), "--gaps",
         str(clean), "--exit-code", "--baseline", str(b)],
        capture_output=True, text=True, timeout=120,
    )
    assert p.returncode == 2, p.stderr[-400:]
    assert p.stdout == ""
    assert "Traceback" not in p.stderr
    assert f"Error: not a scan document: {b}" in p.stderr
    reg = _copy(tmp_path, "proc2")
    (reg / "GAP-DEEP.json").write_text(deep_array(998), encoding="utf-8")
    p = subprocess.run([sys.executable, "-m", "agent_gap_radar.cli", "validate", str(reg)],
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 2 and p.stdout == ""
    assert "Traceback" not in p.stderr and "Error: " in p.stderr


# --- behavior 6: no regression on readable input -------------------------------------

def test_b6_clean_validate_ok(capsys, clean):
    code, out, err = _run(capsys, ["validate", clean])
    assert (code, err) == (0, "")
    assert out.endswith("\n") and not out.endswith("\n\n")
    code2, out2, _ = _run(capsys, ["validate", clean])
    assert (code2, out2) == (code, out)


def test_b6_modest_depth_is_schema_error(capsys, tmp_path):
    reg = _copy(tmp_path, "modest")
    rec = sorted(reg.glob("*.json"))[0]
    rec.write_text(deep_in_title(50), encoding="utf-8")
    code, out, err = _run(capsys, ["validate", reg])
    assert code == 2 and out == ""
    assert "schema error(s)" in err and "nested too deeply" not in err, err[-400:]
    assert rec.name in err


def test_b6_duplicate_key_still_reported(capsys, tmp_path):
    reg = _copy(tmp_path, "dup")
    rec = sorted(reg.glob("*.json"))[0]
    text = rec.read_text(encoding="utf-8").strip()
    assert text.startswith("{")
    rec.write_text('{"title": "x", ' + text[1:], encoding="utf-8")
    code, out, err = _run(capsys, ["validate", reg])
    assert code == 2 and out == ""
    assert "duplicate JSON key(s)" in err and "nested too deeply" not in err
