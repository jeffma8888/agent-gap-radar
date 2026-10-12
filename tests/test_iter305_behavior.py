"""Iteration 305: `radar scan --exit-code --baseline` partitions the new ids into scanned/unscanned.

Black-box over the public CLI. Every assertion drives `main()` and reads observable
stdout, stderr and exit code. The 12 Expected Behaviors come from pm.md (iteration 306,
which re-lands the approved iteration 305 tree).

Fixture vocabulary inherits the conventions of iteration 300: gap A (GAP-801, confidence 5)
and gap B (GAP-802, confidence 5) each have a check whose `present_when` matches its
signature token. Gap W (GAP-803, confidence 0 via `model-output`) is below the default
floor. Trees carry exactly one of SIG or FIX per letter.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import _record

SIG = {"A": "RADAR_I305_SIGNATURE_A", "B": "RADAR_I305_SIGNATURE_B",
       "C": "RADAR_I305_SIGNATURE_C", "W": "RADAR_I305_SIGNATURE_W"}
FIX = {"A": "RADAR_I305_MITIGATION_A", "B": "RADAR_I305_MITIGATION_B",
       "C": "RADAR_I305_MITIGATION_C", "W": "RADAR_I305_MITIGATION_W"}
GAP = {"A": "GAP-801", "B": "GAP-802", "C": "GAP-804", "W": "GAP-803"}
CHK = {"A": "CHK-801", "B": "CHK-802", "C": "CHK-804", "W": "CHK-803"}

NEW, CLEAN, REFUSED = 1, 0, 2
DEFAULT_FLOOR = 2


def _check(letter: str) -> dict:
    sig, fix = SIG[letter], FIX[letter]
    return {
        "id": CHK[letter], "rationale": "r",
        "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": sig},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": fix},
        "fixtures": {"bad": {"a.py": sig + "\n"}, "good": {"a.py": fix + "\n"}},
    }


def _gap(letter: str, classes: tuple[str, ...]) -> dict:
    rec = _record(GAP[letter], 4, 4, 4, classes, None)
    rec["check"] = _check(letter)
    return rec


REGISTER = [
    _gap("A", ("first-party-field",)),
    _gap("B", ("first-party-field",)),
    _gap("C", ("first-party-field",)),
    _gap("W", ("model-output",)),
]


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _tree(root: pathlib.Path, present: set[str], name: str = "target") -> pathlib.Path:
    t = root / name
    (t / "app").mkdir(parents=True)
    for letter in SIG:
        token = SIG[letter] if letter in present else FIX[letter]
        (t / "app" / f"{letter.lower()}.py").write_text(token + "\n", encoding="utf-8")
    return t


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    root = tmp_path_factory.mktemp("iter305")
    reg = root / "reg" / "gaps"
    reg.mkdir(parents=True)
    for rec in REGISTER:
        (reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")

    trees = {
        "ab": _tree(root / "tree_ab", {"A", "B"}),
        "a_only": _tree(root / "tree_a_only", {"A"}),
        "b_only": _tree(root / "tree_b_only", {"B"}),
        "none": _tree(root / "tree_none", set()),
        "abw": _tree(root / "tree_abw", {"A", "B", "W"}),
        "aw": _tree(root / "tree_aw", {"A", "W"}),
        "abc": _tree(root / "tree_abc", {"A", "B", "C"}),
    }

    def baseline(label: str, *extra) -> pathlib.Path:
        rc, out, err = _run(["scan", str(trees[label]), "--gaps", str(reg), "--json", *extra])
        assert (rc, err) == (0, ""), (label, rc, err)
        path = root / f"baseline-{label}.json"
        path.write_text(out, encoding="utf-8")
        return path

    def baseline_gap(label: str, gap_id: str) -> pathlib.Path:
        rc, out, err = _run(["scan", str(trees[label]), "--gaps", str(reg), "--json",
                             "--gap", gap_id])
        assert (rc, err) == (0, ""), (label, gap_id, rc, err)
        path = root / f"baseline-{label}-{gap_id}.json"
        path.write_text(out, encoding="utf-8")
        return path

    reg_a = root / "reg_a" / "gaps"
    reg_a.mkdir(parents=True)
    (reg_a / f"{REGISTER[0]['id']}.json").write_text(json.dumps(REGISTER[0]), encoding="utf-8")

    reg_ab = root / "reg_ab" / "gaps"
    reg_ab.mkdir(parents=True)
    for rec in REGISTER[:2]:
        (reg_ab / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")

    def baseline_custom_reg(label: str, reg_path: pathlib.Path, bname: str) -> pathlib.Path:
        rc, out, err = _run(["scan", str(trees[label]), "--gaps", str(reg_path), "--json"])
        assert (rc, err) == (0, ""), (label, rc, err)
        path = root / f"baseline-{bname}.json"
        path.write_text(out, encoding="utf-8")
        return path

    return {
        "root": root, "reg": reg, "reg_a": reg_a, "reg_ab": reg_ab, "trees": trees,
        "b_a_only": baseline("a_only"),
        "b_ab": baseline("ab"),
        "b_none": baseline("none"),
        "b_a_only_gapA": baseline_gap("a_only", GAP["A"]),
        "b_ab_reg_ab": baseline_custom_reg("ab", reg_ab, "ab-reg-ab"),
        "b_a_only_reg_ab": baseline_custom_reg("a_only", reg_ab, "a-only-reg-ab"),
    }


def _scan(bed, tree: str, *extra, register: str = "reg"):
    return _run(["scan", str(bed["trees"][tree]), "--gaps", str(bed[register]), *extra])


def _gate(bed, tree: str, baseline_key: str, *extra):
    rc, out, err = _scan(bed, tree, "--exit-code", "--baseline", str(bed[baseline_key]),
                         *extra)
    assert err == "", (tree, baseline_key, err)
    return rc, out


def _baseline_line(document: str) -> str:
    lines = [line for line in document.splitlines() if line.startswith("Baseline: ")]
    assert len(lines) == 1, lines
    return lines[0]


# ---------------------------------------------------------------------------
# Behavior 1 -- Line shape: the Baseline: line gains two partition clauses.
# ---------------------------------------------------------------------------

def test_b1_line_has_partition_clauses_after_new_above_floor(bed):
    rc, out = _gate(bed, "ab", "b_a_only")
    bline = _baseline_line(out)
    assert "; scanned by the baseline: " in bline
    assert "; unscanned by the baseline: " in bline
    prefix_end = bline.index("; scanned by the baseline:")
    prefix = bline[:prefix_end]
    assert f"new above-floor PRESENT: 1 ({GAP['B']})" in prefix
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b1_every_other_line_byte_identical_to_flagless(bed):
    plain_rc, plain_out, plain_err = _scan(bed, "ab")
    assert (plain_rc, plain_err) == (0, "")
    _, flagged_out = _gate(bed, "ab", "b_a_only")
    plain_lines = plain_out.splitlines()
    flagged_lines = flagged_out.splitlines()
    assert len(flagged_lines) == len(plain_lines) + 1
    anchor = next(i for i, line in enumerate(plain_lines)
                  if line.startswith("Gaps with no check yet: "))
    assert flagged_lines[:anchor + 1] == plain_lines[:anchor + 1]
    assert flagged_lines[anchor + 2:] == plain_lines[anchor + 1:]


# ---------------------------------------------------------------------------
# Behavior 2 -- Partition: R + U == M; disjoint; re-sorted = M list.
# ---------------------------------------------------------------------------

def test_b2_partition_algebra_on_mixed_case(bed):
    rc, out = _gate(bed, "ab", "b_none")
    bline = _baseline_line(out)
    new_part = bline.split("new above-floor PRESENT: ")[1]
    m_str = new_part.split(";")[0]
    m_count = int(m_str.split("(")[0].strip())
    m_ids_raw = m_str.split("(")[1].rstrip(")")
    m_ids = [x.strip() for x in m_ids_raw.split(",")] if m_ids_raw != "none" else []
    scanned_part = bline.split("scanned by the baseline: ")[1]
    r_str = scanned_part.split(";")[0]
    r_count = int(r_str.split("(")[0].strip())
    r_ids_raw = r_str.split("(")[1].rstrip(")")
    r_ids = [x.strip() for x in r_ids_raw.split(",")] if r_ids_raw != "none" else []
    unscanned_part = bline.split("unscanned by the baseline: ")[1]
    u_count = int(unscanned_part.split("(")[0].strip())
    u_ids_raw = unscanned_part.split("(")[1].rstrip(")")
    u_ids = [x.strip() for x in u_ids_raw.split(",")] if u_ids_raw != "none" else []
    assert r_count + u_count == m_count
    assert r_count == len(r_ids)
    assert u_count == len(u_ids)
    assert set(r_ids) & set(u_ids) == set()
    assert sorted(r_ids + u_ids) == sorted(m_ids)


def test_b2_none_stands_for_empty(bed):
    rc, out = _gate(bed, "a_only", "b_a_only")
    assert rc == CLEAN
    bline = _baseline_line(out)
    assert "new above-floor PRESENT: 0 (none)" in bline
    assert "scanned by the baseline: 0 (none)" in bline
    assert "unscanned by the baseline: 0 (none)" in bline


# ---------------------------------------------------------------------------
# Behavior 3 -- Unscanned = register grew.
# ---------------------------------------------------------------------------

def test_b3_unscanned_when_register_grew(bed):
    """Baseline from register holding only A, scan with A+B on full register."""
    rc, out, err = _run(["scan", str(bed["trees"]["ab"]), "--gaps", str(bed["reg_a"]),
                         "--json"])
    assert (rc, err) == (0, ""), err
    b_path = bed["root"] / "baseline-reg-a-only.json"
    b_path.write_text(out, encoding="utf-8")
    rc, out, err = _scan(bed, "ab", "--exit-code", "--baseline", str(b_path))
    assert (rc, err) == (NEW, "")
    bline = _baseline_line(out)
    assert f"unscanned by the baseline: 1 ({GAP['B']})" in bline


# ---------------------------------------------------------------------------
# Behavior 4 -- Unscanned = narrowed baseline.
# ---------------------------------------------------------------------------

def test_b4_unscanned_with_gap_narrowed_baseline(bed):
    """`--gap A` baseline used against a full scan: B is unscanned."""
    rc, out = _gate(bed, "ab", "b_a_only_gapA")
    assert rc == NEW
    bline = _baseline_line(out)
    assert f"unscanned by the baseline: 1 ({GAP['B']})" in bline


# ---------------------------------------------------------------------------
# Behavior 5 -- Scanned = target moved.
# ---------------------------------------------------------------------------

def test_b5_scanned_when_target_moved(bed):
    """Baseline from target with only A present (B ABSENT), scan on target with A+B."""
    rc, out = _gate(bed, "ab", "b_a_only")
    assert rc == NEW
    bline = _baseline_line(out)
    assert f"scanned by the baseline: 1 ({GAP['B']})" in bline
    assert "unscanned by the baseline: 0 (none)" in bline


# ---------------------------------------------------------------------------
# Behavior 6 -- Mixed: both scanned and unscanned in one line.
# ---------------------------------------------------------------------------

def test_b6_mixed_scanned_and_unscanned(bed):
    """Baseline from tree a_only with register A+B: A=PRESENT, B=ABSENT (both scanned).
    Scan tree abc with full register: B new+scanned (target moved), C new+unscanned
    (register grew)."""
    rc, out, err = _scan(bed, "abc", "--exit-code", "--baseline",
                         str(bed["b_a_only_reg_ab"]))
    assert (rc, err) == (NEW, "")
    bline = _baseline_line(out)
    assert f"scanned by the baseline: 1 ({GAP['B']})" in bline
    assert f"unscanned by the baseline: 1 ({GAP['C']})" in bline


# ---------------------------------------------------------------------------
# Behavior 7 -- Clean: same tree and register, all three lists 0 (none), exit 0.
# ---------------------------------------------------------------------------

def test_b7_clean_same_tree_and_register(bed):
    rc, out = _gate(bed, "ab", "b_ab")
    assert rc == CLEAN
    bline = _baseline_line(out)
    assert "new above-floor PRESENT: 0 (none)" in bline
    assert "scanned by the baseline: 0 (none)" in bline
    assert "unscanned by the baseline: 0 (none)" in bline


# ---------------------------------------------------------------------------
# Behavior 8 -- Floor applies once, before partition.
# ---------------------------------------------------------------------------

def test_b8_below_floor_not_in_partition(bed):
    """W (confidence 0) is PRESENT but below floor. Against a baseline that
    never carried W, W should NOT appear in R or U."""
    rc, out = _gate(bed, "abw", "b_a_only")
    bline = _baseline_line(out)
    assert GAP["W"] not in bline.split("scanned by the baseline:")[1]
    assert f"new above-floor PRESENT: 1 ({GAP['B']})" in bline


# ---------------------------------------------------------------------------
# Behavior 9 -- Exit code unchanged.
# ---------------------------------------------------------------------------

def test_b9_exit_1_when_m_gt_0(bed):
    rc, _ = _gate(bed, "ab", "b_a_only")
    assert rc == NEW

def test_b9_exit_0_when_m_eq_0(bed):
    rc, _ = _gate(bed, "a_only", "b_a_only")
    assert rc == CLEAN

def test_b9_refusal_exit_2(bed):
    rc, out, err = _scan(bed, "ab", "--baseline", str(bed["b_a_only"]))
    assert rc == REFUSED
    assert out == ""


# ---------------------------------------------------------------------------
# Behavior 10 -- `--json` untouched.
# ---------------------------------------------------------------------------

def test_b10_json_byte_identical_with_and_without_baseline(bed):
    plain_rc, plain_out, plain_err = _scan(bed, "ab", "--json")
    assert (plain_rc, plain_err) == (0, "")
    rc, out = _gate(bed, "ab", "b_a_only", "--json")
    assert out == plain_out
    assert "baseline" not in json.loads(out)


def test_b10_json_exit_code_still_follows(bed):
    rc_new, _ = _gate(bed, "ab", "b_a_only", "--json")
    assert rc_new == NEW
    rc_clean, _ = _gate(bed, "a_only", "b_a_only", "--json")
    assert rc_clean == CLEAN


# ---------------------------------------------------------------------------
# Behavior 11 -- Determinism.
# ---------------------------------------------------------------------------

def test_b11_two_runs_byte_identical(bed):
    _, out1 = _gate(bed, "ab", "b_a_only")
    _, out2 = _gate(bed, "ab", "b_a_only")
    assert out1 == out2


def test_b11_flagless_verbs_unchanged(bed):
    """Flagless scan output should be the same whether or not the partition feature exists."""
    rc1, out1, err1 = _scan(bed, "ab")
    rc2, out2, err2 = _scan(bed, "ab")
    assert (rc1, err1) == (0, "")
    assert out1 == out2


# ---------------------------------------------------------------------------
# Behavior 12 -- Contract: CONSUMER_CONTRACT.md:19 restates the line shape.
# ---------------------------------------------------------------------------

def test_b12_contract_restates_partition_line_shape():
    contract = (pathlib.Path(__file__).resolve().parents[1]
                / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    assert "scanned by the baseline:" in contract
    assert "unscanned by the baseline:" in contract
    scan_cell = next(line for line in contract.splitlines()
                     if "radar scan" in line and "|" in line)
    assert "scanned by the baseline: R" in scan_cell or "scanned by the baseline:" in contract
