"""Iteration 422 behaviors: one shared JSON-file read door (``registry.read_json_file``).

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-9.  No test was written from the implementation source,
the engineer's or reviewer's notes, or any diff.  Behavior 8 is a STRUCTURAL
spec requirement ("the consolidation is real"), so its tests parse the three
named src modules with ``ast`` at test time -- the expectations themselves are
the spec's sentences, not anything read from the implementation.

The CLI is driven in a CHILD interpreter for the refusal paths, so a crash
(traceback, rc 1) is observed end to end with stdout and stderr separated.

Ship-hazard notes: no commit sha, no file:line locator, no wall-clock bound,
no optional extra.  The spec's "net src delta vs HEAD <= +5" is NOT pinned
here: it needs a sha baseline (hazard H1) and is measured in the report.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar import registry

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
SRC = REPO / "src" / "agent_gap_radar"
LONG = "x" * 300
CHILD = (
    "import sys\n"
    "from agent_gap_radar.cli import main\n"
    "rc = main(sys.argv[1:])\n"
    "sys.exit(rc or 0)\n"
)


def _run(args: list[str], cwd: pathlib.Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _assert_clean_refusal(rc: int, out: str, err: str) -> None:
    assert rc == 2, (rc, err)
    assert out == "", out
    assert err.startswith("Error: "), err
    assert err.endswith("\n") and not err.endswith("\n\n"), repr(err)
    assert err.count("\n") == 1, repr(err)
    assert "Traceback" not in err, err
    assert "Errno" not in err, err


def _scan_baseline(cwd: pathlib.Path, baseline: str) -> tuple[int, str, str]:
    return _run(
        ["scan", "--gaps", str(GAPS), ".", "--exit-code", "--baseline", baseline],
        cwd,
    )


# --------------------------------------------------------------- behavior 1


def test_b1_overlong_baseline_name_is_a_clean_exit_2_not_a_rc1_crash(tmp_path):
    rc, out, err = _scan_baseline(tmp_path, LONG)
    _assert_clean_refusal(rc, out, err)
    assert "cannot read the file (" in err, err
    assert err.endswith("): " + LONG + "\n"), err


def test_b1_symlink_loop_baseline_is_a_clean_exit_2(tmp_path):
    # Stat-failure family (ELOOP).  Pathlib's errno handling is version
    # sensitive, so the hard contract is: rc 2, one Error: line, no traceback.
    loop = tmp_path / "loop.json"
    loop.symlink_to(loop.name)
    rc, out, err = _scan_baseline(tmp_path, "loop.json")
    _assert_clean_refusal(rc, out, err)
    assert ("not a scan document: loop.json" in err) or (
        "not a file: loop.json" in err
    ), err


# ----------------------------------------------------------- behaviors 2-3


def test_b2_missing_and_directory_baselines_keep_not_a_file(tmp_path):
    (tmp_path / "adir").mkdir()
    for spelling in ("missing.json", "adir", "./adir/"):
        rc, out, err = _scan_baseline(tmp_path, spelling)
        _assert_clean_refusal(rc, out, err)
        assert err == f"Error: not a file: {spelling}\n", (spelling, err)


def test_b3_unparseable_baseline_keeps_not_a_scan_document(tmp_path):
    (tmp_path / "bad.json").write_text("{not json\n", encoding="utf-8")
    rc, out, err = _scan_baseline(tmp_path, "bad.json")
    _assert_clean_refusal(rc, out, err)
    assert err == "Error: not a scan document: bad.json\n", err


# ----------------------------------------------------------- behaviors 4-5


def test_b4_prd_after_refusal_sentences(tmp_path):
    (tmp_path / "adir").mkdir()
    (tmp_path / "x.json").write_text("{x", encoding="utf-8")
    cases = {
        "nope.json": "Error: --after nope.json: cannot read the file "
        "(No such file or directory)\n",
        "adir": "Error: --after adir: cannot read the file (not a regular file)\n",
    }
    if hasattr(os, "mkfifo"):
        os.mkfifo(tmp_path / "ff")
        cases["ff"] = "Error: --after ff: cannot read the file (not a regular file)\n"
    for spelling, expected in cases.items():
        rc, out, err = _run(["prd", "--after", spelling], tmp_path)
        _assert_clean_refusal(rc, out, err)
        assert err == expected, (spelling, err)
    rc, out, err = _run(["prd", "--after", "x.json"], tmp_path)
    _assert_clean_refusal(rc, out, err)
    assert err.startswith("Error: --after x.json: not valid JSON ("), err


def test_b5_prd_after_overlong_name_is_strerror_not_traceback(tmp_path):
    rc, out, err = _run(["prd", "--after", LONG], tmp_path)
    _assert_clean_refusal(rc, out, err)
    assert err.startswith(f"Error: --after {LONG}: cannot read the file ("), err
    # The reason is the platform strerror for ENAMETOOLONG.
    assert os.strerror(36 if sys.platform.startswith("linux") else 63) in err or (
        "too long" in err.lower()
    ), err


# --------------------------------------------------------------- behavior 6


def _copy_one_record(dst: pathlib.Path) -> pathlib.Path:
    src = sorted(GAPS.glob("GAP-*.json"))[0]
    target = dst / src.name
    target.write_bytes(src.read_bytes())
    return target


@pytest.mark.parametrize("verb", ["validate", "list"])
def test_b6_directory_named_like_a_record_is_not_a_regular_file(tmp_path, verb):
    reg = tmp_path / "reg"
    reg.mkdir()
    _copy_one_record(reg)
    (reg / "GAP-999.json").mkdir()
    rc, out, err = _run([verb, "reg"], tmp_path)
    assert rc == 2, (rc, err)
    assert "Traceback" not in err and "Errno" not in err, err
    assert "Error: GAP-999.json: unreadable/invalid JSON: not a regular file" in err, err
    assert str(tmp_path) not in err, err


def test_b6_symlink_to_a_regular_record_is_still_read(tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    real = _copy_one_record(tmp_path)
    rec_id = json.loads(real.read_text(encoding="utf-8"))["id"]
    (reg / real.name).symlink_to(real)
    rc, out, err = _run(["list", "reg"], tmp_path)
    assert rc == 0, err
    assert rec_id in out, out
    # A second copy of the same id next to the link proves the link was READ.
    (reg / "GAP-copy.json").write_bytes(real.read_bytes())
    rc, out, err = _run(["validate", "reg"], tmp_path)
    assert rc == 2, (rc, out, err)
    assert "duplicate" in (out + err).lower(), (out, err)


# --------------------------------------------------------------- behavior 7


def test_b7_helper_returns_parsed_object(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text('{"a": [1, 2], "b": "c"}\n', encoding="utf-8")
    assert registry.read_json_file(p) == {"a": [1, 2], "b": "c"}


def test_b7_helper_missing_path_raises_not_a_regular_file(tmp_path):
    with pytest.raises(registry.NotARegularFile) as info:
        registry.read_json_file(tmp_path / "absent.json")
    exc = info.value
    assert exc.missing is True
    assert str(exc) == "not a regular file"
    assert isinstance(exc, OSError)


def test_b7_helper_directory_raises_not_a_regular_file(tmp_path):
    d = tmp_path / "adir.json"
    d.mkdir()
    with pytest.raises(registry.NotARegularFile) as info:
        registry.read_json_file(d)
    exc = info.value
    assert exc.missing is False
    assert str(exc) == "not a regular file"
    assert isinstance(exc, OSError)


def test_b7_helper_duplicate_key_raises_registry_error(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text('{"a": 1, "a": 2}\n', encoding="utf-8")
    with pytest.raises(registry.RegistryError):
        registry.read_json_file(p)


def test_b7_helper_bad_json_raises_value_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{x", encoding="utf-8")
    with pytest.raises(ValueError):
        registry.read_json_file(p)


# --------------------------------------------------------------- behavior 8

DOORS = {"registry.py": "load_all", "prd.py": "read_handoff", "scan.py": "load_baseline"}


def _tree(name: str) -> ast.Module:
    return ast.parse((SRC / name).read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.FunctionDef:
    found = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    assert len(found) == 1, (name, len(found))
    return found[0]


def _attr_calls(node: ast.AST, attr: str) -> int:
    return sum(
        1 for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == attr
    )


def _names_called(node: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def test_b8_the_rule_lives_once_in_the_helper():
    helper = _func(_tree("registry.py"), "read_json_file")
    assert _attr_calls(helper, "is_file") >= 1
    assert _attr_calls(helper, "read_text") >= 1
    assert "parse_record" in _names_called(helper)
    cls = [
        n for n in ast.walk(_tree("registry.py"))
        if isinstance(n, ast.ClassDef) and n.name == "NotARegularFile"
    ]
    assert len(cls) == 1


@pytest.mark.parametrize("module,door", sorted(DOORS.items()))
def test_b8_each_door_reads_through_the_helper_with_no_own_ladder(module, door):
    fn = _func(_tree(module), door)
    assert "read_json_file" in _names_called(fn), (module, door)
    assert _attr_calls(fn, "is_file") == 0, (module, door)
    assert _attr_calls(fn, "read_text") == 0, (module, door)
    assert "parse_record" not in _names_called(fn), (module, door)


@pytest.mark.parametrize("module", ["prd.py", "scan.py"])
def test_b8_prd_and_scan_no_longer_import_parse_record(module):
    imported = set()
    for n in ast.walk(_tree(module)):
        if isinstance(n, ast.ImportFrom):
            imported.update(a.name for a in n.names)
        elif isinstance(n, ast.Import):
            imported.update(a.name for a in n.names)
    assert "parse_record" not in imported, module
    assert "parse_record" not in _names_called(_tree(module)), module


def test_b8_src_module_count_unchanged():
    # `__init__` excluded, matching the existing module-count pin.
    mods = sorted(p.stem for p in SRC.glob("*.py") if p.stem != "__init__")
    assert len(mods) == 10, mods


# --------------------------------------------------------------- behavior 9


def test_b9_valid_baseline_round_trip_is_stable_and_single_newline(tmp_path):
    rc, payload, err = _run(["scan", "--gaps", str(GAPS), ".", "--json"], tmp_path)
    assert rc in (0, 1), err
    assert payload.endswith("\n") and not payload.endswith("\n\n")
    (tmp_path / "base.json").write_text(payload, encoding="utf-8")
    runs = [_scan_baseline(tmp_path, "base.json") for _ in range(2)]
    assert runs[0] == runs[1]
    rc, out, err = runs[0]
    assert rc == 0, (rc, err)
    assert "Traceback" not in err
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-5:])
