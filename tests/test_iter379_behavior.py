"""Iteration 379: a too-deeply-nested record or baseline is an ``Error:`` exit 2, never a traceback.

Both the stdlib JSON scanner and ``registry.parse_record``'s duplicate-key walk recurse
once per nesting level, so a deep enough file used to escape as a ``RecursionError``
with exit 1 -- the code ``scan --exit-code`` reserves for "new PRESENT finding". Two
depths reach the two sources: 1,500 trips the product's own walk (the pytest stack is
deep, so the ~1,000 threshold is not used), 100,000 trips the C scanner itself.
"""

from __future__ import annotations

import json
import pathlib
import shutil

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
CLAUSE = "unreadable/invalid JSON: nested too deeply to read"


def _deep_array(depth: int) -> str:
    return "[" * depth + "]" * depth


def _deep_object(depth: int) -> str:
    return '{"a":' * depth + "1" + "}" * depth


DEEP = {
    "array-1500": _deep_array(1500),
    "array-100000": _deep_array(100_000),
    "object-100000": _deep_object(100_000),
}


def _run(capsys, argv: list[object]) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _copy_gaps(dest: pathlib.Path) -> pathlib.Path:
    """A private copy of the committed register, so breaking it never touches the repo."""
    shutil.copytree(REPO / "gaps", dest)
    return dest


def _first_record(gaps: pathlib.Path) -> pathlib.Path:
    return sorted(gaps.glob("*.json"))[0]


def _assert_refused(code: int, out: str, err: str, needle: str) -> None:
    assert code == 2, err
    assert out == ""
    assert any(line.startswith("Error: ") and needle in line for line in err.splitlines()), err
    assert "Traceback" not in err
    assert "RecursionError" not in err


@pytest.fixture
def broken(tmp_path: pathlib.Path, request) -> tuple[pathlib.Path, pathlib.Path, str]:
    """(clean register, register with one record replaced by deep content, that file's name)."""
    clean = _copy_gaps(tmp_path / "clean")
    bad = _copy_gaps(tmp_path / "bad")
    target = _first_record(bad)
    target.write_text(DEEP[request.param], encoding="utf-8")
    return clean, bad, target.name


@pytest.mark.parametrize("broken", sorted(DEEP), indirect=True)
def test_b1_validate_refuses_deep_record(capsys, broken) -> None:
    _, bad, name = broken
    _assert_refused(*_run(capsys, ["validate", bad]), f"{name}: {CLAUSE}")


@pytest.mark.parametrize("broken", sorted(DEEP), indirect=True)
@pytest.mark.parametrize("verb", ["list", "report"])
def test_b2_reading_verbs_refuse_deep_record(capsys, broken, verb: str) -> None:
    _, bad, name = broken
    _assert_refused(*_run(capsys, [verb, bad]), f"{name}: {CLAUSE}")


@pytest.mark.parametrize("broken", sorted(DEEP), indirect=True)
@pytest.mark.parametrize("swapped", [False, True])
def test_b2_diff_refuses_deep_record_on_either_side(capsys, broken, swapped: bool) -> None:
    clean, bad, name = broken
    sides = [bad, clean] if swapped else [clean, bad]
    _assert_refused(*_run(capsys, ["diff", *sides]), f"{name}: {CLAUSE}")


def test_b3_clause_is_byte_stable_across_depths(capsys, tmp_path: pathlib.Path) -> None:
    gaps = _copy_gaps(tmp_path / "gaps")
    target = _first_record(gaps)
    errs = []
    for depth in (1500, 100_000):
        target.write_text(_deep_array(depth), encoding="utf-8")
        code, _, err = _run(capsys, ["validate", gaps])
        assert code == 2
        errs.append(err)
    assert errs[0] == errs[1]
    assert not any(ch.isdigit() for ch in CLAUSE)


def test_b4_every_bad_file_is_still_named(capsys, tmp_path: pathlib.Path) -> None:
    gaps = _copy_gaps(tmp_path / "gaps")
    first, second = sorted(gaps.glob("*.json"))[:2]
    first.write_text(_deep_array(1500), encoding="utf-8")
    second.write_text("{", encoding="utf-8")
    code, out, err = _run(capsys, ["validate", gaps])
    _assert_refused(code, out, err, f"{first.name}: {CLAUSE}")
    assert second.name in err
    assert f"{second.name}: {CLAUSE}" not in err


@pytest.mark.parametrize("depth", [1500, 100_000])
def test_b5_deep_baseline_is_not_a_regression(capsys, tmp_path: pathlib.Path, depth: int) -> None:
    clean = _copy_gaps(tmp_path / "gaps")
    target = tmp_path / "T"
    target.mkdir()
    (target / "a.py").write_text("x = 1\n", encoding="utf-8")
    baseline = tmp_path / "B.json"
    baseline.write_text(_deep_array(depth), encoding="utf-8")
    argv = ["scan", target, "--gaps", clean, "--exit-code", "--baseline", baseline]
    _assert_refused(*_run(capsys, argv), f"not a scan document: {baseline}")


def test_b6_readable_input_is_unchanged(capsys, tmp_path: pathlib.Path) -> None:
    clean = _copy_gaps(tmp_path / "clean")
    code, out, err = _run(capsys, ["validate", clean])
    assert code == 0, err
    repo_code, repo_out, _ = _run(capsys, ["validate", REPO / "gaps"])
    assert repo_code == 0
    assert out.replace(str(clean), "<G>") == repo_out.replace(str(REPO / "gaps"), "<G>")

    shallow = _copy_gaps(tmp_path / "shallow")
    record = _first_record(shallow)
    data = json.loads(record.read_text(encoding="utf-8"))
    data["title"] = json.loads(_deep_array(50))
    record.write_text(json.dumps(data), encoding="utf-8")
    code, out, err = _run(capsys, ["validate", shallow])
    _assert_refused(code, out, err, "schema error(s)")
    assert "nested too deeply" not in err

    dup = _copy_gaps(tmp_path / "dup")
    record = _first_record(dup)
    text = record.read_text(encoding="utf-8").strip()
    record.write_text(text[:-1] + ', "title": "again"}', encoding="utf-8")
    code, out, err = _run(capsys, ["validate", dup])
    _assert_refused(code, out, err, "duplicate JSON key(s)")
