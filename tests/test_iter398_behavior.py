"""Iteration 398: `scan --name NAME` pins the target's reported identity.

Black-box over the public CLI (`cli.main` in-process), one expectation per Expected
Behavior 1-8 of the iteration's spec. The register and targets are synthetic `tmp_path`
builds: one record (`GAP-981`) that reads PRESENT on a signature token, confidence 4,
so every target here carries exactly one above-floor PRESENT finding (asserted in
`test_b0`, never assumed). `myrepo/` and `app/` are byte-identical trees, so the only
difference between their scans is the directory name a baseline compares.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import _record

GAP_ID = "GAP-981"
SIGNATURE = "RADAR_I398_SIGNATURE"
MITIGATION = "RADAR_I398_MITIGATION"
NAME_ERROR = ("Error: --name needs a non-blank printable NAME with no leading or "
              "trailing whitespace; omit the flag to use the target's directory name")
INVALID_NAMES = ["", "   ", " svc", "svc ", "a\nb", "a\tb"]


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _document(code: int, out: str, err: str) -> str:
    """A rc 0/1 run is a document: it ends in exactly one newline."""
    assert code in (0, 1), (code, err)
    assert out.endswith("\n") and not out.endswith("\n\n"), out[-4:]
    return out


def _refused(code: int, out: str, err: str) -> str:
    """A refusal: exit 2, empty stdout, last stderr line starting `Error: `."""
    assert code == 2, (code, out)
    assert out == ""
    last = [line for line in err.splitlines() if line.strip()][-1]
    assert last.startswith("Error: "), err
    return last


def _gap_record() -> dict:
    rec = _record(GAP_ID, 4, 4, 4, ("first-party-field",), None)
    rec["check"] = {
        "id": "CHK-981", "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": SIGNATURE},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": MITIGATION},
        "fixtures": {"bad": {"a.py": SIGNATURE + "\n"},
                     "good": {"a.py": MITIGATION + "\n"}},
    }
    return rec


@pytest.fixture(scope="module")
def bed(tmp_path_factory) -> dict[str, pathlib.Path]:
    root = tmp_path_factory.mktemp("iter398")
    reg = root / "reg" / "gaps"
    reg.mkdir(parents=True)
    (reg / f"{GAP_ID}.json").write_text(json.dumps(_gap_record()), encoding="utf-8")
    trees = {}
    for name in ("myrepo", "app"):
        tree = root / name
        (tree / "src").mkdir(parents=True)
        (tree / "src" / "main.py").write_text(SIGNATURE + "\n", encoding="utf-8")
        trees[name] = tree
    return {"root": root, "reg": reg, **trees}


def _scan(bed, tree: str, *extra: str) -> tuple[int, str, str]:
    return _run(["scan", str(bed[tree]), "--gaps", str(bed["reg"]), *extra])


def _write_baseline(bed, tree: str, filename: str, *extra: str) -> pathlib.Path:
    out = _document(*_scan(bed, tree, "--json", *extra))
    path = bed["root"] / filename
    path.write_text(out, encoding="utf-8")
    return path


def test_b0_the_bed_has_one_above_floor_present_finding(bed):
    for tree in ("myrepo", "app"):
        payload = json.loads(_document(*_scan(bed, tree, "--json")))
        assert payload["counts"]["PRESENT"] == 1
        (finding,) = payload["findings"]
        assert finding["gap_id"] == GAP_ID and finding["verdict"] == "PRESENT"
        assert finding["below_floor"] is False


def test_b1_markdown_heading_is_the_name_and_nothing_else_moves(bed):
    plain = _document(*_scan(bed, "myrepo"))
    named = _document(*_scan(bed, "myrepo", "--name", "svc"))
    assert named.splitlines()[0] == "# Gap scan: svc"
    assert plain.splitlines()[0] == "# Gap scan: myrepo"
    assert named.splitlines()[1:] == plain.splitlines()[1:]
    assert f"Target: `{bed['myrepo']}`" in named


def test_b2_json_target_name_is_the_name_and_the_shape_is_unchanged(bed):
    plain = json.loads(_document(*_scan(bed, "myrepo", "--json")))
    named = json.loads(_document(*_scan(bed, "myrepo", "--json", "--name", "svc")))
    assert named["target_name"] == "svc"
    assert list(named) == list(plain)
    assert named["target"] == plain["target"] == str(bed["myrepo"])
    assert {k: v for k, v in named.items() if k != "target_name"} == {
        k: v for k, v in plain.items() if k != "target_name"}


@pytest.mark.parametrize("extra", [[], ["--json"], ["--exit-code"]])
def test_b3_naming_the_basename_is_a_byte_identical_no_op(bed, extra):
    assert _scan(bed, "myrepo", *extra, "--name", "myrepo") == _scan(bed, "myrepo", *extra)


def test_b4_a_named_baseline_gates_a_differently_named_checkout(bed):
    base = _write_baseline(bed, "myrepo", "base-svc.json", "--name", "svc")
    carried = sum(1 for f in json.loads(base.read_text())["findings"]
                  if f["verdict"] == "PRESENT")
    code, out, err = _scan(bed, "app", "--exit-code", "--baseline", str(base),
                           "--name", "svc")
    assert code == 0, err
    doc = _document(code, out, err)
    assert doc.splitlines()[0] == "# Gap scan: svc"
    (line,) = [ln for ln in doc.splitlines() if ln.startswith("Baseline: ")]
    assert f"carried PRESENT: {carried};" in line
    assert "new above-floor PRESENT: 0 (none)" in line

    code, out, err = _scan(bed, "app", "--exit-code", "--baseline", str(base),
                           "--name", "svc", "--json")
    payload = json.loads(_document(code, out, err))
    assert code == 0
    assert payload["target_name"] == "svc" and payload["baseline"] is not None


def test_b5_without_the_flag_the_mismatch_refuses_as_before(bed):
    base = _write_baseline(bed, "myrepo", "base-plain.json")
    last = _refused(*_scan(bed, "app", "--exit-code", "--baseline", str(base)))
    assert last == "Error: baseline target mismatch: myrepo (baseline) vs app (target)"


def test_b6_the_name_renames_and_never_waives(bed):
    named = _write_baseline(bed, "myrepo", "base-svc6.json", "--name", "svc")
    plain = _write_baseline(bed, "myrepo", "base-plain6.json")
    cases = [
        (named, [], "svc (baseline) vs app (target)"),
        (named, ["--name", "other"], "svc (baseline) vs other (target)"),
        (plain, ["--name", "svc"], "myrepo (baseline) vs svc (target)"),
    ]
    for base, extra, tail in cases:
        last = _refused(*_scan(bed, "app", "--exit-code", "--baseline", str(base), *extra))
        assert last == f"Error: baseline target mismatch: {tail}", extra


def test_b7_prd_project_is_the_name(bed):
    named = json.loads(_document(*_scan(bed, "myrepo", "--prd", "--name", "svc")))
    plain = json.loads(_document(*_scan(bed, "myrepo", "--prd")))
    assert named["project"] == "svc"
    assert plain["project"] == "myrepo"


@pytest.mark.parametrize("surface", [[], ["--json"], ["--prd"], ["--exit-code"]])
@pytest.mark.parametrize("value", INVALID_NAMES)
def test_b8_an_invalid_name_is_refused_on_every_surface(bed, surface, value):
    assert _refused(*_scan(bed, "myrepo", *surface, "--name", value)) == NAME_ERROR


def test_b8_interior_spaces_are_accepted_and_a_prefix_is_not_a_flag(bed):
    doc = _document(*_scan(bed, "myrepo", "--name", "my svc"))
    assert doc.splitlines()[0] == "# Gap scan: my svc"
    err = io.StringIO()
    with contextlib.redirect_stderr(err), pytest.raises(SystemExit) as exc:
        main(["scan", str(bed["myrepo"]), "--gaps", str(bed["reg"]), "--nam", "svc"])
    assert exc.value.code == 2
    assert "unrecognized arguments" in err.getvalue()
