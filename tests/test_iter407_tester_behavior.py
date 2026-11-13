"""Iteration 407 tester behaviors: `radar validate [<repo>] --json` (roadmap row 126).

Black-box: every assertion drives the public CLI (`agent_gap_radar.cli.main`,
or a child interpreter for the pre-change comparison) and reads only stdout,
stderr and the exit code. Every register is a tmp dir built from copies of the
repo's own `gaps/` records; nothing touches the network.

Behavior 10 (the text dialect is byte-identical to before) is pinned against
the PRE-FEATURE commit `885fad0` -- never HEAD, which becomes the feature once
committed -- extracted with `git archive`; it skips when that commit is absent
(a shallow clone).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
PRE_FEATURE_SHA = "885fad0"

TOP_KEYS = ["valid", "records", "errors"]
ERROR_KEYS = ["kind", "file", "loc", "msg"]
KINDS = {"near-miss", "invalid-json", "duplicate-key", "schema", "duplicate-id"}


def _records() -> list[pathlib.Path]:
    return sorted(GAPS.glob("GAP-*.json"))


def _run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(args)
    return rc, out.getvalue(), err.getvalue()


def _valid_register(root: pathlib.Path) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for src in _records()[:2]:
        shutil.copy(src, root / src.name)
    return root


def _bad_register(root: pathlib.Path, *, extras: bool = False) -> pathlib.Path:
    """The spec's bad register: (i) valid, (ii) title-less + empty quote,
    (iii) truncated JSON, (iv) a duplicate of (i). `extras` adds a near-miss
    entry and a repeated-key file so all five kinds appear."""
    root.mkdir(parents=True, exist_ok=True)
    first, second = _records()[:2]
    shutil.copy(first, root / first.name)
    shutil.copy(first, root / (first.stem.split("-", 2)[0] + "-" + first.stem.split("-", 2)[1] + "-zz-copy.json"))
    data = json.loads(second.read_text(encoding="utf-8"))
    del data["title"]
    data["evidence"][0]["quote"] = ""
    (root / second.name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (root / "GAP-999-bad.json").write_text('{"id": "GAP-9', encoding="utf-8")
    if extras:
        (root / "GAP-123-x.json.bak").write_text("{}\n", encoding="utf-8")
        (root / "GAP-777-dup.json").write_text('{"id": "a", "id": "b"}\n', encoding="utf-8")
    return root


def _first_id() -> str:
    return json.loads(_records()[0].read_text(encoding="utf-8"))["id"]


def _list_dumps_settings() -> dict:
    """Detect the json.dumps settings `radar list --json` uses, from its output."""
    rc, out, _ = _run(["list", str(REPO), "--json"])
    assert rc == 0
    doc = json.loads(out)
    for kwargs in ({"indent": 2}, {"indent": 2, "ensure_ascii": False}, {}, {"ensure_ascii": False}):
        if json.dumps(doc, **kwargs) + "\n" == out:
            return kwargs
    raise AssertionError("could not reproduce `radar list --json` serialisation")


# ---- Behavior 1 -----------------------------------------------------------


def test_b1_valid_register_document_exact(tmp_path):
    reg = _valid_register(tmp_path / "reg")
    rc, out, err = _run(["validate", str(reg), "--json"])
    assert rc == 0
    assert err == ""
    doc = json.loads(out)
    assert doc == {"valid": True, "records": 2, "errors": []}
    assert list(doc) == TOP_KEYS
    assert out == json.dumps(doc, **_list_dumps_settings()) + "\n"
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b1_repo_root_layout_accepted(tmp_path):
    root = tmp_path / "repo"
    _valid_register(root / "gaps")
    rc, out, err = _run(["validate", str(root), "--json"])
    assert (rc, err) == (0, "")
    assert json.loads(out) == {"valid": True, "records": 2, "errors": []}


# ---- Behavior 2 / 3 -------------------------------------------------------


def test_b2_bad_register_document_shape(tmp_path):
    reg = _bad_register(tmp_path / "reg")
    rc, out, err = _run(["validate", str(reg), "--json"])
    assert rc == 2
    doc = json.loads(out)
    assert list(doc) == TOP_KEYS
    assert doc["valid"] is False
    assert doc["records"] == 2
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert out == json.dumps(doc, **_list_dumps_settings()) + "\n"


def test_b3_every_error_has_exact_keys_and_closed_kind(tmp_path):
    reg = _bad_register(tmp_path / "reg", extras=True)
    _, out, _ = _run(["validate", str(reg), "--json"])
    errors = json.loads(out)["errors"]
    assert errors
    for e in errors:
        assert list(e) == ERROR_KEYS
        assert e["kind"] in KINDS
    assert {e["kind"] for e in errors} == KINDS


# ---- Behavior 4 -----------------------------------------------------------


def test_b4_schema_errors_one_per_pydantic_error(tmp_path):
    reg = _bad_register(tmp_path / "reg")
    second = _records()[1].name
    _, out, err = _run(["validate", str(reg), "--json"])
    schema = [e for e in json.loads(out)["errors"] if e["kind"] == "schema"]
    assert [e["loc"] for e in schema] == ["title", "evidence.0.quote"]
    assert all(e["file"] == second for e in schema)
    # msg is verbatim: the text dialect prints `<loc>: <msg>` for each one.
    for e in schema:
        assert f"{e['loc']}: {e['msg']}" in err
        assert e["msg"]
    assert schema[0]["msg"] == "Field required"


def test_b4_record_level_schema_error_loc(tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    src = _records()[0]
    (reg / src.name).write_text("[]\n", encoding="utf-8")
    rc, out, err = _run(["validate", str(reg), "--json"])
    assert rc == 2
    errors = json.loads(out)["errors"]
    assert len(errors) == 1
    assert errors[0]["kind"] == "schema"
    assert errors[0]["loc"] == "<record>"
    assert errors[0]["file"] == src.name
    assert f"<record>: {errors[0]['msg']}" in err


# ---- Behavior 5 -----------------------------------------------------------


def _clause_after(err: str, name: str) -> str:
    line = err.removeprefix("Error: ").rstrip("\n")
    for clause in line.split("; "):
        if clause.startswith(name + ": "):
            return clause[len(name) + 2:]
    raise AssertionError(f"no clause for {name} in {err!r}")


def test_b5_invalid_json_object(tmp_path):
    reg = _bad_register(tmp_path / "reg")
    _, out, err = _run(["validate", str(reg), "--json"])
    bad = [e for e in json.loads(out)["errors"] if e["kind"] == "invalid-json"]
    assert len(bad) == 1
    assert bad[0]["file"] == "GAP-999-bad.json"
    assert bad[0]["loc"] is None
    assert bad[0]["msg"] == _clause_after(err, "GAP-999-bad.json")


def test_b5_duplicate_key_and_near_miss_objects(tmp_path):
    reg = _bad_register(tmp_path / "reg", extras=True)
    _, out, err = _run(["validate", str(reg), "--json"])
    errors = json.loads(out)["errors"]
    dk = [e for e in errors if e["kind"] == "duplicate-key"]
    assert len(dk) == 1
    assert dk[0]["file"] == "GAP-777-dup.json" and dk[0]["loc"] is None
    assert dk[0]["msg"] == _clause_after(err, "GAP-777-dup.json")
    nm = [e for e in errors if e["kind"] == "near-miss"]
    assert len(nm) == 1
    assert nm[0]["file"] == "GAP-123-x.json.bak" and nm[0]["loc"] is None
    assert nm[0]["msg"] == _clause_after(err, "GAP-123-x.json.bak")


# ---- Behavior 6 -----------------------------------------------------------


def test_b6_duplicate_id_objects_sorted_by_id(tmp_path):
    reg = _bad_register(tmp_path / "reg")
    # Duplicate a second id too, so the ascending order is observable.
    third = _records()[2]
    shutil.copy(third, reg / third.name)
    shutil.copy(third, reg / ("-".join(third.stem.split("-", 2)[:2]) + "-zz-copy.json"))
    _, out, _ = _run(["validate", str(reg), "--json"])
    dup = [e for e in json.loads(out)["errors"] if e["kind"] == "duplicate-id"]
    third_id = json.loads(third.read_text(encoding="utf-8"))["id"]
    assert [e["msg"] for e in dup] == sorted([_first_id(), third_id])
    for e in dup:
        assert e["file"] is None and e["loc"] == "id"


# ---- Behavior 7 -----------------------------------------------------------


def test_b7_error_order_matches_text_clauses_and_is_stable(tmp_path):
    reg = _bad_register(tmp_path / "reg", extras=True)
    rc1, out1, err1 = _run(["validate", str(reg), "--json"])
    rc2, out2, err2 = _run(["validate", str(reg), "--json"])
    assert (rc1, out1, err1) == (rc2, out2, err2)
    errors = json.loads(out1)["errors"]
    kinds = [e["kind"] for e in errors]
    # near-miss first, duplicate-id last, per-file objects between in filename order.
    assert kinds[0] == "near-miss" and kinds[-1] == "duplicate-id"
    per_file = [e["file"] for e in errors if e["kind"] in {"schema", "invalid-json", "duplicate-key"}]
    assert per_file == sorted(per_file)
    # Each object's msg appears in the Error: line in the same order.
    pos = 0
    for e in errors:
        idx = err1.find(e["msg"], pos)
        assert idx >= pos, (e, err1)
        pos = idx + len(e["msg"])


# ---- Behavior 8 -----------------------------------------------------------


def test_b8_stderr_identical_with_and_without_json(tmp_path):
    reg = _bad_register(tmp_path / "reg", extras=True)
    rc_t, out_t, err_t = _run(["validate", str(reg)])
    rc_j, out_j, err_j = _run(["validate", str(reg), "--json"])
    assert rc_t == rc_j == 2
    assert err_j == err_t
    assert err_j.startswith("Error: ") and err_j.count("\n") == 1
    assert out_t == ""
    json.loads(out_j)  # stdout is ONLY the document


# ---- Behavior 9 -----------------------------------------------------------


def _not_a_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "file.txt"
    p.write_text("x\n", encoding="utf-8")
    return p


def _empty(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "empty"
    p.mkdir()
    return p


@pytest.mark.parametrize("make", [_not_a_dir, _empty], ids=["not-a-dir", "empty-register"])
def test_b9_no_document_when_nothing_examined(tmp_path, make):
    target = make(tmp_path)
    rc_t, out_t, err_t = _run(["validate", str(target)])
    rc_j, out_j, err_j = _run(["validate", str(target), "--json"])
    assert rc_t == rc_j == 2
    assert out_j == "" and out_t == ""
    assert err_j == err_t
    assert err_j.startswith("Error: ")


def test_b9_empty_register_message(tmp_path):
    target = _empty(tmp_path)
    _, _, err = _run(["validate", str(target), "--json"])
    assert "no gap records found in" in err


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores chmod 000")
def test_b9_unreadable_directory_no_document(tmp_path):
    reg = _valid_register(tmp_path / "reg")
    reg.chmod(0)
    try:
        rc_t, out_t, err_t = _run(["validate", str(reg)])
        rc_j, out_j, err_j = _run(["validate", str(reg), "--json"])
    finally:
        reg.chmod(0o755)
    assert rc_t == rc_j == 2
    assert out_j == ""
    assert err_j == err_t and err_j.startswith("Error: ")


# ---- Behavior 10 ----------------------------------------------------------


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


_CHILD = (
    "import contextlib, io, json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from agent_gap_radar.cli import main\n"
    "res = []\n"
    "for target in sys.argv[2:]:\n"
    "    out, err = io.StringIO(), io.StringIO()\n"
    "    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):\n"
    "        try:\n"
    "            rc = main(['validate', target])\n"
    "        except SystemExit as exc:\n"
    "            rc = exc.code\n"
    "    res.append([rc, out.getvalue(), err.getvalue()])\n"
    "sys.stdout.write(json.dumps(res))\n"
)


def test_b10_text_dialect_byte_identical_to_pre_feature(tmp_path):
    src = _pre_feature_src(tmp_path)
    targets = [
        _valid_register(tmp_path / "valid"),
        _bad_register(tmp_path / "bad", extras=True),
        _empty(tmp_path),
    ]
    child = subprocess.run(
        [sys.executable, "-c", _CHILD, str(src), *map(str, targets)],
        capture_output=True, text=True, check=True, cwd=str(tmp_path),
    )
    old = json.loads(child.stdout)
    new = [list(_run(["validate", str(t)])) for t in targets]
    assert new == old
    assert new[0][0] == 0 and new[1][0] == 2 and new[2][0] == 2


def test_b10_help_lists_json():
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as exc:
        main(["validate", "--help"])
    assert exc.value.code == 0
    assert "--json" in out.getvalue()


# ---- Behavior 11 ----------------------------------------------------------


def _contract_validate_row() -> str:
    text = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    section = text.split("## The stable surface", 1)[1]
    rows = [ln for ln in section.splitlines() if ln.startswith("| `radar validate")]
    assert len(rows) == 1
    return rows[0]


def _ticks(fragment: str) -> list[str]:
    return re.findall(r"`([^`]+)`", fragment)


def test_b11_contract_row_signature():
    row = _contract_validate_row()
    assert row.startswith("| `radar validate [<repo>] [--json]` |")


def test_b11_contract_sets_equal_emitted_sets(tmp_path):
    row = _contract_validate_row()
    top = re.search(r"--\s*(`valid`.*?), in that order", row)
    assert top, row
    errs = re.search(r"`errors` carries (.*?), in that order", row)
    assert errs, row
    kinds = re.search(r"closed set (.*?);", row)
    assert kinds, row
    contract_top, contract_err, contract_kinds = _ticks(top.group(1)), _ticks(errs.group(1)), set(_ticks(kinds.group(1)))

    reg = _bad_register(tmp_path / "reg", extras=True)
    _, out, _ = _run(["validate", str(reg), "--json"])
    doc = json.loads(out)
    assert contract_top == list(doc)
    assert all(contract_err == list(e) for e in doc["errors"])
    assert contract_kinds == {e["kind"] for e in doc["errors"]}


def test_b11_contract_names_rule_9():
    row = _contract_validate_row()
    assert "NO document" in row or "no document" in row
    assert "empty stdout" in row.lower() or "stdout is empty" in row.lower()


# ---- Behavior 12 ----------------------------------------------------------


def test_b12_no_paths_and_location_independent(tmp_path):
    a = _bad_register(tmp_path / "loc-one-xyz", extras=True)
    b = _bad_register(tmp_path / "elsewhere" / "deeper-abc", extras=True)
    _, out_a, _ = _run(["validate", str(a), "--json"])
    _, out_b, _ = _run(["validate", str(b), "--json"])
    assert out_a == out_b
    for out, root in ((out_a, a), (out_b, b)):
        assert str(tmp_path) not in out
        assert root.name not in out
        assert tmp_path.name not in out
        for e in json.loads(out)["errors"]:
            assert e["file"] is None or ("/" not in e["file"] and "\\" not in e["file"])
