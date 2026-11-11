"""Iteration 398 (tester): `radar scan T --name NAME` -- black-box, spec behaviours 1-8.

Written from the spec alone (no implementation source read). Drives the public CLI
in-process (`cli.main`) over a synthetic two-PRESENT + one-ABSENT register built in
`tmp_path`, and two byte-identical target trees `myrepo/` and `app/`, so a scan of one
differs from a scan of the other only in the directory name. `test_b0` derives the
verdict mix before any other node relies on it.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import _record

PRESENT_IDS = ("GAP-971", "GAP-972")
ABSENT_ID = "GAP-973"
SIG = "RADAR_T398_SIG"
FIX = "RADAR_T398_FIX"
NAME_ERR = ("Error: --name needs a non-blank printable NAME with no leading or "
            "trailing whitespace; omit the flag to use the target's directory name")
BAD_NAMES = ["", "   ", " svc", "svc ", "a\nb", "a\tb", "a\x1bb", "\nsvc"]


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as exc:  # argparse refusals exit through SystemExit
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def _doc(code, out, err):
    assert code in (0, 1), (code, err)
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-6:])
    return out


def _refused(code, out, err):
    assert code == 2, (code, out[:200])
    assert out == ""
    lines = [ln for ln in err.splitlines() if ln.strip()]
    assert lines and lines[-1].startswith("Error: "), err
    return lines[-1]


def _rec(gid, token_present, token_fix):
    rec = _record(gid, 4, 4, 4, ("first-party-field",), None)
    rec["check"] = {
        "id": "CHK-" + gid[4:], "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": token_present},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": token_fix},
        "fixtures": {"bad": {"a.py": token_present + "\n"},
                     "good": {"a.py": token_fix + "\n"}},
    }
    return rec


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    root = tmp_path_factory.mktemp("t398")
    reg = root / "register" / "gaps"
    reg.mkdir(parents=True)
    for i, gid in enumerate(PRESENT_IDS):
        (reg / f"{gid}.json").write_text(
            json.dumps(_rec(gid, f"{SIG}_{i}", f"{FIX}_{i}")), encoding="utf-8")
    (reg / f"{ABSENT_ID}.json").write_text(
        json.dumps(_rec(ABSENT_ID, f"{SIG}_X", f"{FIX}_X")), encoding="utf-8")
    body = f"{SIG}_0\n{SIG}_1\n{FIX}_X\n"
    trees = {}
    for name in ("myrepo", "app"):
        t = root / name
        (t / "pkg").mkdir(parents=True)
        (t / "pkg" / "core.py").write_text(body, encoding="utf-8")
        trees[name] = t
    return {"root": root, "reg": reg, **trees}


def _scan(bed, tree, *extra):
    return _run(["scan", bed[tree], "--gaps", bed["reg"], *extra])


def test_b0_bed_has_two_present_and_one_absent(bed):
    payload = json.loads(_doc(*_scan(bed, "myrepo", "--json")))
    verdicts = {f["gap_id"]: f["verdict"] for f in payload["findings"]}
    assert verdicts == {"GAP-971": "PRESENT", "GAP-972": "PRESENT", "GAP-973": "ABSENT"}
    assert payload["target_name"] == "myrepo"


# --- 1. markdown heading -----------------------------------------------------------

@pytest.mark.parametrize("name", ["svc", "my svc", "Svc-2.0_x"])
def test_b1_heading_is_the_name_and_rest_identical(bed, name):
    named = _doc(*_scan(bed, "myrepo", "--name", name)).split("\n")
    plain = _doc(*_scan(bed, "myrepo")).split("\n")
    assert named[0] == f"# Gap scan: {name}"
    assert plain[0] == "# Gap scan: myrepo"
    assert named[1:] == plain[1:]
    target_lines = [ln for ln in named if ln.startswith("Target:")]
    assert target_lines and str(bed["myrepo"]) in target_lines[0]


# --- 2. JSON identity -------------------------------------------------------------

def test_b2_json_target_name_only_value_changes(bed):
    named_raw = _doc(*_scan(bed, "myrepo", "--json", "--name", "svc"))
    plain_raw = _doc(*_scan(bed, "myrepo", "--json"))
    named, plain = json.loads(named_raw), json.loads(plain_raw)
    assert named["target_name"] == "svc"
    assert list(named) == list(plain)
    assert named["target"] == plain["target"]
    assert {k: v for k, v in named.items() if k != "target_name"} == \
        {k: v for k, v in plain.items() if k != "target_name"}


# --- 3. no-op when NAME == basename -----------------------------------------------

@pytest.mark.parametrize("surface", [[], ["--json"], ["--exit-code"], ["--prd"]])
def test_b3_name_equal_to_basename_is_byte_identical(bed, surface):
    assert _scan(bed, "app", *surface, "--name", "app") == _scan(bed, "app", *surface)


def test_b3_exit_code_with_present_is_one_either_way(bed):
    a = _scan(bed, "app", "--exit-code")
    b = _scan(bed, "app", "--exit-code", "--name", "svc")
    assert a[0] == b[0] == 1
    assert a[1].split("\n")[1:] == b[1].split("\n")[1:]


# --- 4. baseline survives a differently named checkout ----------------------------

def _baseline(bed, tree, *name):
    raw = _doc(*_scan(bed, tree, "--json", *name))
    path = bed["root"] / f"base-{tree}-{'-'.join(name) or 'plain'}.json"
    path.write_text(raw, encoding="utf-8")
    return path


def test_b4_named_baseline_gates_other_dir_markdown(bed):
    base = _baseline(bed, "myrepo", "--name", "svc")
    carried = sum(1 for f in json.loads(base.read_text())["findings"]
                  if f["verdict"] == "PRESENT")
    assert carried == 2
    code, out, err = _scan(bed, "app", "--exit-code", "--baseline", base, "--name", "svc")
    assert code == 0, err
    _doc(code, out, err)
    assert out.split("\n")[0] == "# Gap scan: svc"
    lines = [ln for ln in out.splitlines() if ln.startswith("Baseline:")]
    assert len(lines) == 1
    assert "new above-floor PRESENT: 0 (none)" in lines[0]
    assert f"carried PRESENT: {carried}" in lines[0]


def test_b4_named_baseline_gates_other_dir_json(bed):
    base = _baseline(bed, "myrepo", "--name", "svc")
    code, out, err = _scan(bed, "app", "--exit-code", "--json", "--baseline", base,
                           "--name", "svc")
    assert code == 0, err
    payload = json.loads(_doc(code, out, err))
    assert payload["target_name"] == "svc"
    assert payload["baseline"] is not None


def test_b4_flag_order_is_free(bed):
    base = _baseline(bed, "myrepo", "--name", "svc")
    code, _, err = _run(["scan", "--name", "svc", bed["app"], "--baseline", base,
                         "--gaps", bed["reg"], "--exit-code"])
    assert code == 0, err


# --- 5. no flag: mismatch refuses as today ----------------------------------------

def test_b5_plain_mismatch_still_refuses(bed):
    base = _baseline(bed, "myrepo")
    last = _refused(*_scan(bed, "app", "--exit-code", "--baseline", base))
    assert last == "Error: baseline target mismatch: myrepo (baseline) vs app (target)"


# --- 6. renames, never waives -----------------------------------------------------

@pytest.mark.parametrize("written, read, expect", [
    (("--name", "svc"), (), "svc (baseline) vs app (target)"),
    (("--name", "svc"), ("--name", "other"), "svc (baseline) vs other (target)"),
    ((), ("--name", "svc"), "myrepo (baseline) vs svc (target)"),
])
@pytest.mark.parametrize("json_flag", [[], ["--json"]])
def test_b6_mismatch_names_effective_names(bed, written, read, expect, json_flag):
    base = _baseline(bed, "myrepo", *written)
    last = _refused(*_scan(bed, "app", "--exit-code", *json_flag, "--baseline", base,
                           *read))
    assert last == f"Error: baseline target mismatch: {expect}"


# --- 7. --prd project -------------------------------------------------------------

def test_b7_prd_project(bed):
    code, out, err = _scan(bed, "myrepo", "--prd", "--name", "svc")
    assert code == 0, err
    assert json.loads(_doc(code, out, err))["project"] == "svc"
    code, out, err = _scan(bed, "myrepo", "--prd")
    assert code == 0, err
    assert json.loads(_doc(code, out, err))["project"] == "myrepo"


# --- 8. invalid NAME refused on every surface -------------------------------------

@pytest.mark.parametrize("surface", [[], ["--json"], ["--prd"], ["--exit-code"]])
@pytest.mark.parametrize("bad", BAD_NAMES, ids=[repr(b) for b in BAD_NAMES])
def test_b8_invalid_name_refused(bed, surface, bad):
    last = _refused(*_scan(bed, "myrepo", *surface, "--name", bad))
    assert last == NAME_ERR


def test_b8_invalid_name_refused_even_with_baseline(bed):
    base = _baseline(bed, "myrepo", "--name", "svc")
    last = _refused(*_scan(bed, "app", "--exit-code", "--baseline", base, "--name", " svc"))
    assert last == NAME_ERR


def test_b8_interior_space_accepted(bed):
    out = _doc(*_scan(bed, "myrepo", "--name", "my svc"))
    assert out.split("\n")[0] == "# Gap scan: my svc"


def test_b8_strict_prefix_is_unrecognized(bed):
    code, out, err = _scan(bed, "myrepo", "--nam", "svc")
    assert code == 2 and out == ""
    assert "unrecognized arguments" in err
