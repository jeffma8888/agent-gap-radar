"""Iteration 301 behaviors: `radar scan <target> --gaps <reg> --prd` appends the scan's
own `finding` (verdict, confidence, floor status, pure locators) as a SIXTH top-level
key, after `stories`; `radar prd` is unchanged.

Black-box over the public CLI (`agent_gap_radar.cli.main`, in-process, the `_emit`
idiom of `tests/test_iter87_behavior.py`) and the published documents. Every
expectation comes from `pm.md`'s Expected Behaviors 1-7. No test here scans this
repository: registers and targets are built under `tmp_path`, so the module adds no
live self-scan to the suite wall.

Structural notes, so this file cannot lie later:

* **The `--json` sibling is the oracle for `finding`, never a hand-typed value.**
  Behavior 2 runs `scan --json` on the SAME target and register, selects the finding
  whose `gap_id` equals the prd's `sourceGap.id`, and compares the four fields one by
  one; a `finding` that was right by coincidence on one fixture would still have to
  agree with the sibling on the second register.
* **`radar prd` is compared to `scan --prd` two ways.** Re-serialised without
  `finding` (the spec's wording) AND as a raw byte prefix: `prd`'s document minus its
  closing brace must be a prefix of `scan --prd`'s bytes, which is what "the first
  five keys are byte-identical" means to a consumer diffing the two files.
* **Both refusals are pinned to their exact pre-existing message**, imported from
  `tests/test_iter02_behavior.py` fixtures (`WEAK`, `UNFIRED`, `FLOOR`) rather than
  restated, so a drift in either message fails here AND there.
* **No absolute machine path and no personal identifier appears here.**
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import (FLOOR, MARKER, UNFIRED, WEAK, _record, _target,
                                  _write_register)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
README = REPO_ROOT / "README.md"

#: Behavior 1 -- the published prd key sequence (iteration 23) plus the sixth key.
PRD_TOP_KEYS = ["project", "branchName", "description", "sourceGap", "stories"]
SCAN_PRD_TOP_KEYS = PRD_TOP_KEYS + ["finding"]

#: Behavior 2 -- the four keys of `finding`, in order.
FINDING_KEYS = ["verdict", "confidence", "below_floor", "locations"]

#: Behavior 3 -- a pure locator: a relative path, one colon, a positive line number.
#: No whitespace anywhere, so a prose entry ("see loop.py near the top") cannot pass.
LOCATOR = re.compile(r"^[^\s:]+(/[^\s:]+)*:[1-9][0-9]*$")

#: Two checked records that both fire on the `_target` tree; GAP-870 outranks GAP-871
#: (severity 5 vs 4), so the prd's `sourceGap.id` is GAP-870 and the sibling finding
#: the test must pick is NOT the first one in `findings` by accident of id order only.
RECORDS = [_record("GAP-870", 5, 3, 5, ("first-party-field",), "CHK-870"),
           _record("GAP-871", 4, 3, 3, ("first-party-field",), "CHK-871")]

#: A second register whose top record differs, so behavior 2 is proved on two
#: selections rather than one.
RECORDS_B = [_record("GAP-880", 3, 3, 3, ("first-party-field",), "CHK-880"),
             _record("GAP-881", 5, 5, 5, ("first-party-field",), "CHK-881")]


@pytest.fixture()
def reg(tmp_path):
    return _write_register(tmp_path / "reg", list(RECORDS))


@pytest.fixture()
def reg_b(tmp_path):
    return _write_register(tmp_path / "regb", list(RECORDS_B))


@pytest.fixture()
def target(tmp_path):
    return _target(tmp_path / "hit", body=MARKER)


@pytest.fixture()
def clean_target(tmp_path):
    return _target(tmp_path / "miss", "nothing interesting")


def _emit(capsys, argv):
    """stdout for a JSON-emitting invocation: exit 0, empty stderr, non-empty document."""
    rc = main(list(argv))
    cap = capsys.readouterr()
    assert rc == 0, f"{argv} exited {rc}; stderr={cap.err!r}"
    assert cap.err == "", f"{argv} wrote to stderr: {cap.err!r}"
    assert cap.out, f"{argv} produced an empty document"
    return cap.out


def _scan_prd(capsys, target, reg):
    return _emit(capsys, ["scan", str(target), "--gaps", str(reg), "--prd"])


def _scan_json(capsys, target, reg):
    return json.loads(_emit(capsys, ["scan", str(target), "--gaps", str(reg), "--json"]))


def _prd(capsys, reg, gid, project=None):
    """`radar prd --gap <gid>`; `project` is passed through when given.

    Behavior 5 names `radar prd . --gap <id>` against `radar scan . --gaps gaps --prd`: with
    `.` as both the register root and the target, the two surfaces derive the same
    `project` name. The fixtures here put the register and the target in DIFFERENT
    directories, so `prd` is told the target's name explicitly -- the same document the
    spec's `.`-for-both invocation produces, with the coincidence made explicit.
    """
    argv = ["prd", str(reg), "--gap", gid]
    if project is not None:
        argv += ["--project", project]
    return _emit(capsys, argv)


def _sibling(scan_doc, gid):
    hits = [f for f in scan_doc["findings"] if f["gap_id"] == gid]
    assert len(hits) == 1, f"expected exactly one `--json` finding for {gid}, got {hits}"
    return hits[0]


def _strings_under(value):
    """Every str leaf under a JSON value, depth-first."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings_under(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings_under(v)


# ---------------------------------------------------------------------------
# behavior 1 -- six top-level keys, in order, exit 0
# ---------------------------------------------------------------------------

def test_b1_scan_prd_has_exactly_six_top_level_keys_in_order(capsys, reg, target):
    doc = json.loads(_scan_prd(capsys, target, reg))
    assert list(doc) == SCAN_PRD_TOP_KEYS, list(doc)


def test_b1_holds_on_the_second_register_too(capsys, reg_b, target):
    doc = json.loads(_scan_prd(capsys, target, reg_b))
    assert list(doc) == SCAN_PRD_TOP_KEYS, list(doc)
    assert doc["sourceGap"]["id"] == "GAP-881", "premise: the higher-priority record leads"


# ---------------------------------------------------------------------------
# behavior 2 -- `finding` == the `--json` sibling selected by sourceGap.id
# ---------------------------------------------------------------------------

def test_b2_finding_has_exactly_the_four_keys_in_order(capsys, reg, target):
    finding = json.loads(_scan_prd(capsys, target, reg))["finding"]
    assert isinstance(finding, dict), type(finding).__name__
    assert list(finding) == FINDING_KEYS, list(finding)


@pytest.mark.parametrize("which", ["reg", "reg_b"])
def test_b2_each_finding_field_equals_the_json_siblings(capsys, request, target, which):
    reg = request.getfixturevalue(which)
    doc = json.loads(_scan_prd(capsys, target, reg))
    sibling = _sibling(_scan_json(capsys, target, reg), doc["sourceGap"]["id"])
    for key in FINDING_KEYS:
        assert doc["finding"][key] == sibling[key], (
            f"finding.{key} = {doc['finding'][key]!r} but the `--json` sibling says "
            f"{sibling[key]!r}")


def test_b2_finding_follows_the_floor_the_scan_was_given(capsys, reg, target):
    """"same target, same floor": with `--floor 5` only GAP-870 (confidence 5) clears,
    and the `--json` sibling run at the SAME floor must agree field by field."""
    argv = ["scan", str(target), "--gaps", str(reg), "--floor", "5"]
    doc = json.loads(_emit(capsys, argv + ["--prd"]))
    assert list(doc) == SCAN_PRD_TOP_KEYS, list(doc)
    sibling = _sibling(json.loads(_emit(capsys, argv + ["--json"])), doc["sourceGap"]["id"])
    assert list(doc["finding"]) == FINDING_KEYS
    for key in FINDING_KEYS:
        assert doc["finding"][key] == sibling[key], key
    assert doc["finding"]["confidence"] >= 5 and doc["finding"]["below_floor"] is False


def test_b2_the_selected_finding_is_present_and_above_floor(capsys, reg, target):
    """`--prd` refuses below-floor and non-PRESENT selections (behavior 6), so the
    finding it DOES emit can only ever read PRESENT / below_floor false."""
    finding = json.loads(_scan_prd(capsys, target, reg))["finding"]
    assert finding["verdict"] == "PRESENT", finding
    assert finding["below_floor"] is False, finding
    assert isinstance(finding["confidence"], int) and finding["confidence"] >= FLOOR, finding


# ---------------------------------------------------------------------------
# behavior 3 -- pure `path:line` locators, no notes, no prose
# ---------------------------------------------------------------------------

def test_b3_locations_is_a_non_empty_list_of_pure_path_line_strings(capsys, reg, target):
    finding = json.loads(_scan_prd(capsys, target, reg))["finding"]
    locs = finding["locations"]
    assert isinstance(locs, list) and locs, locs
    for loc in locs:
        assert isinstance(loc, str) and LOCATOR.match(loc), f"not a pure path:line: {loc!r}"
    assert any(loc.startswith("app/loop.py:") for loc in locs), locs


def test_b3_no_location_notes_and_no_prose_anywhere_under_finding(capsys, reg, target):
    finding = json.loads(_scan_prd(capsys, target, reg))["finding"]
    leaves = list(_strings_under(finding))
    assert "location_notes" not in leaves, leaves
    assert not any("note" in s.lower() for s in leaves), leaves
    # Every string leaf is a key name, the verdict token, or a pure locator.
    allowed = set(FINDING_KEYS) | {"PRESENT"}
    stray = [s for s in leaves if s not in allowed and not LOCATOR.match(s)]
    assert stray == [], f"prose under `finding`: {stray!r}"


# ---------------------------------------------------------------------------
# behavior 4 -- `radar prd` keeps its five keys
# ---------------------------------------------------------------------------

def test_b4_prd_has_exactly_the_five_keys_and_no_finding(capsys, reg):
    doc = json.loads(_prd(capsys, reg, "GAP-870"))
    assert list(doc) == PRD_TOP_KEYS, list(doc)
    assert "finding" not in json.loads(_prd(capsys, reg, "GAP-871"))


def test_b4_prd_is_byte_deterministic(capsys, reg):
    assert _prd(capsys, reg, "GAP-870") == _prd(capsys, reg, "GAP-870")


# ---------------------------------------------------------------------------
# behavior 5 -- the first five keys are `radar prd --gap <sourceGap.id>`'s bytes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("which", ["reg", "reg_b"])
def test_b5_first_five_keys_reserialise_identically_to_prd(capsys, request, target, which):
    reg = request.getfixturevalue(which)
    scan_out = _scan_prd(capsys, target, reg)
    scan_doc = json.loads(scan_out)
    prd_out = _prd(capsys, reg, scan_doc["sourceGap"]["id"], project=target.name)
    prd_doc = json.loads(prd_out)
    assert prd_doc["project"] == scan_doc["project"] == target.name, "premise: same project"
    without = {k: v for k, v in scan_doc.items() if k != "finding"}
    assert json.dumps(without) == json.dumps(prd_doc)
    assert list(without) == list(prd_doc) == PRD_TOP_KEYS


def test_b5_prd_bytes_minus_the_closing_brace_are_a_prefix_of_scan_prd(capsys, reg, target):
    """What a consumer diffing the two files sees: identical up to where `finding`
    is appended after `stories`."""
    scan_out = _scan_prd(capsys, target, reg)
    prd_out = _prd(capsys, reg, json.loads(scan_out)["sourceGap"]["id"],
                   project=target.name)
    head, brace, tail = prd_out.rpartition("}")
    assert brace == "}" and tail == "\n", repr(prd_out[-4:])
    assert scan_out.startswith(head.rstrip()), (
        "scan --prd does not begin with prd's serialised first five keys")
    assert len(scan_out) > len(prd_out)


# ---------------------------------------------------------------------------
# behavior 6 -- one trailing newline; refusals unchanged
# ---------------------------------------------------------------------------

def test_b6_scan_prd_ends_in_exactly_one_newline(capsys, reg, target):
    out = _scan_prd(capsys, target, reg)
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-4:])
    assert out == out.rstrip("\n") + "\n"


def test_b6_scan_prd_two_runs_are_byte_identical(capsys, reg, target):
    assert _scan_prd(capsys, target, reg) == _scan_prd(capsys, target, reg)


def test_b6_floor_refusal_is_unchanged(tmp_path, target, capsys):
    reg = _write_register(tmp_path / "weak", list(WEAK))
    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    cap = capsys.readouterr()
    assert rc == 2
    assert cap.out == "", "a refusal must not emit a document"
    assert cap.err == (
        f"Error: no PRESENT finding clears the confidence floor {FLOOR}: "
        "GAP-700 (confidence 0), GAP-701 (confidence 0). Strengthen the evidence, "
        "or name it explicitly with 'radar prd --gap GAP-700'.\n")


def test_b6_no_present_refusal_is_unchanged(tmp_path, clean_target, capsys):
    reg = _write_register(tmp_path / "unfired", list(UNFIRED))
    rc = main(["scan", str(clean_target), "--gaps", str(reg), "--prd"])
    cap = capsys.readouterr()
    assert rc == 2
    assert cap.out == ""
    assert cap.err == ("Error: no PRESENT finding to build against; run without --prd "
                       "to see MANUAL questions\n")


# ---------------------------------------------------------------------------
# behavior 7 -- the published contract says so
# ---------------------------------------------------------------------------

def _section(text, heading):
    """Body of the markdown section opened by `heading`, up to the next `## `."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def _prd_table_cell():
    rows = [ln for ln in CONTRACT.read_text(encoding="utf-8").splitlines()
            if ln.startswith("| `radar prd ")]
    assert len(rows) == 1, rows
    return rows[0]


def test_b7_contract_prd_cell_names_the_five_keys_and_the_appended_sixth():
    cell = _prd_table_cell()
    assert "five prd keys" in cell, cell
    assert "sixth top-level key, `finding`, last" in cell, cell
    assert "`radar scan` section" in cell, cell


def test_b7_contract_scan_section_documents_finding_with_its_four_keys_in_order():
    body = _section(CONTRACT.read_text(encoding="utf-8"), "\n## `radar scan`")
    assert "`scan --prd` carries the finding it built against." in body
    order = [body.index(f"`{k}`", body.index("`finding`")) for k in FINDING_KEYS]
    assert order == sorted(order), "the four keys are not documented in emitted order"
    assert "`location_notes` is NOT carried" in body


def test_b7_contract_five_key_paragraph_is_still_exactly_the_five_keys():
    """The paragraph `test_iter68` b7 collects must still equal `radar prd`'s keys."""
    body = _section(CONTRACT.read_text(encoding="utf-8"),
                    "\n## The prd payload -- the five top-level keys, published")
    spans = re.findall(r"`([A-Za-z]+)`", body.split("\n\n")[1])
    assert spans == PRD_TOP_KEYS, spans
    assert "`finding`" not in body.split("\n\n")[1]


def test_b7_readme_names_finding_beside_scan_prd():
    lines = [ln for ln in README.read_text(encoding="utf-8").splitlines()
             if "--prd" in ln and "finding" in ln]
    assert lines, "README does not mention `finding` beside `scan --prd`"
    assert any('"finding"' in ln or "`finding`" in ln for ln in lines), lines
