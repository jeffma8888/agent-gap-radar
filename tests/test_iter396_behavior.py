"""Iteration 396: `scan --baseline` names each carried gap that is no longer PRESENT.

Black-box over the public CLI (`cli.main` in-process) and the published contract. Every
expectation is taken from `pm.md`'s Expected Behaviors 1-9. Registers and targets are
synthetic `tmp_path` builds, except behavior 1, which uses GAP-016's own `check.fixtures`
from the committed register (no live-register id census).

Fixture vocabulary (synthetic register):
* `GAP-961` / `GAP-962`: two-sided checks, PRESENT on a signature token, ABSENT on a fix
  token, confidence 5.
* `GAP-963`: same shape, but a tree carrying neither token reads MANUAL (derived and
  asserted in `test_b0`, never assumed).
* `GAP-964`: guarded by `applies_when` (a `*.cfg` file must exist); a tree without it reads
  NOT_APPLICABLE.
Every verdict the behaviors lean on is DERIVED from `--json` and asserted in `test_b0`.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import _record

REPO = pathlib.Path(__file__).resolve().parent.parent
REGISTER = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"

IDS = {"A": "GAP-961", "B": "GAP-962", "M": "GAP-963", "N": "GAP-964"}
SIG = {k: f"RADAR_I396_SIGNATURE_{k}" for k in IDS}
FIX = {k: f"RADAR_I396_MITIGATION_{k}" for k in IDS}

#: The pre-iteration line shape (HEAD 2daf422), the prefix every flagged line must keep.
PREFIX_RE = re.compile(
    r"^Baseline: (?P<path>.+) -- carried PRESENT: (?P<carried>\d+); "
    r"new above-floor PRESENT: \d+ \((?:none|[A-Z0-9, -]+)\); "
    r"scanned by the baseline: \d+ \((?:none|[A-Z0-9, -]+)\); "
    r"unscanned by the baseline: \d+ \((?:none|[A-Z0-9, -]+)\)"
)
CLAUSE_RE = re.compile(r"; no longer PRESENT: (?P<n>\d+) \((?P<body>[^()]*)\)$")
VERDICTS = {"ABSENT", "NOT_APPLICABLE", "MANUAL", "UNKNOWN"}


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _check(k: str) -> dict:
    chk = {
        "id": IDS[k].replace("GAP", "CHK"), "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": SIG[k]},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": FIX[k]},
        "fixtures": {"bad": {"a.py": SIG[k] + "\n"}, "good": {"a.py": FIX[k] + "\n"}},
    }
    if k == "N":
        chk["applies_when"] = {"kind": "file_exists", "globs": ["**/*.cfg"]}
        chk["fixtures"] = {"bad": {"a.py": SIG[k] + "\n", "n.cfg": "x\n"},
                           "good": {"a.py": FIX[k] + "\n", "n.cfg": "x\n"}}
    return chk


def _gap(k: str) -> dict:
    rec = _record(IDS[k], 4, 4, 4, ("first-party-field",), None)
    rec["check"] = _check(k)
    return rec


def _tree(root: pathlib.Path, state: dict[str, str], name: str = "t") -> pathlib.Path:
    """`state[k]` is 'sig', 'fix' or 'none'; N also gets its .cfg unless 'na'."""
    t = root / name
    (t / "app").mkdir(parents=True)
    for k in IDS:
        s = state.get(k, "fix")
        body = {"sig": SIG[k], "fix": FIX[k]}.get(s, "neutral")
        (t / "app" / f"{k.lower()}.py").write_text(body + "\n", encoding="utf-8")
    if state.get("N") != "na":
        (t / "app" / "n.cfg").write_text("x\n", encoding="utf-8")
    return t


TREES = {
    "all_present": {"A": "sig", "B": "sig", "M": "sig", "N": "sig"},
    "a_fixed": {"A": "fix", "B": "sig", "M": "sig", "N": "sig"},
    "mixed": {"A": "fix", "B": "sig", "M": "none", "N": "na"},
    "b_fixed_m_manual": {"A": "sig", "B": "fix", "M": "none", "N": "sig"},
}


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    root = tmp_path_factory.mktemp("iter396")
    reg = root / "reg" / "gaps"
    reg.mkdir(parents=True)
    for k in IDS:
        rec = _gap(k)
        (reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    trees = {label: _tree(root / label, st) for label, st in TREES.items()}
    rc, out, err = _run(["scan", str(trees["all_present"]), "--gaps", str(reg), "--json"])
    assert (rc, err) == (0, ""), err
    base = root / "base-all.json"
    base.write_text(out, encoding="utf-8")
    return {"root": root, "reg": reg, "trees": trees, "base": base}


def _gate(bed, tree, *extra, baseline=None):
    return _run(["scan", str(bed["trees"][tree]), "--gaps", str(bed["reg"]), "--exit-code",
                 "--baseline", str(baseline or bed["base"]), *extra])


def _line(doc: str) -> str:
    lines = [ln for ln in doc.splitlines() if ln.startswith("Baseline: ")]
    assert len(lines) == 1, lines
    return lines[0]


def _clause(doc: str) -> tuple[int, str]:
    m = CLAUSE_RE.search(_line(doc))
    assert m, _line(doc)
    return int(m["n"]), m["body"]


def _verdicts(bed, tree) -> dict[str, str]:
    rc, out, err = _run(["scan", str(bed["trees"][tree]), "--gaps", str(bed["reg"]), "--json"])
    assert (rc, err) == (0, "")
    return {f["gap_id"]: f["verdict"] for f in json.loads(out)["findings"]}


# --------------------------------------------------------------------------- b0 guard
def test_b0_fixture_verdicts_are_what_the_tool_derives(bed):
    assert _verdicts(bed, "all_present") == {i: "PRESENT" for i in IDS.values()}
    assert _verdicts(bed, "a_fixed")[IDS["A"]] == "ABSENT"
    mixed = _verdicts(bed, "mixed")
    assert mixed == {IDS["A"]: "ABSENT", IDS["B"]: "PRESENT", IDS["M"]: "MANUAL",
                     IDS["N"]: "NOT_APPLICABLE"}
    other = _verdicts(bed, "b_fixed_m_manual")
    assert other == {IDS["A"]: "PRESENT", IDS["B"]: "ABSENT", IDS["M"]: "MANUAL",
                     IDS["N"]: "PRESENT"}


# --------------------------------------------------------------------------- b1 GAP-016
@pytest.fixture(scope="module")
def gap016(tmp_path_factory):
    (path,) = sorted(REGISTER.glob("GAP-016*.json"))
    rec = json.loads(path.read_text(encoding="utf-8"))
    fx = rec["check"]["fixtures"]
    root = tmp_path_factory.mktemp("iter396_g16")

    def write(arm: str) -> pathlib.Path:
        t = root / arm / "t"
        for rel, body in fx[arm].items():
            p = t / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
        return t

    bad, good = write("bad"), write("good")
    rc, out, err = _run(["scan", str(bad), "--gaps", str(REGISTER), "--gap", "GAP-016",
                         "--json"])
    assert (rc, err) == (0, "")
    assert [f["verdict"] for f in json.loads(out)["findings"]] == ["PRESENT"]
    base = root / "base.json"
    base.write_text(out, encoding="utf-8")
    return {"bad": bad, "good": good, "base": base}


def _g16(gap016, arm, *extra):
    return _run(["scan", str(gap016[arm]), "--gaps", str(REGISTER), "--gap", "GAP-016",
                 "--baseline", str(gap016["base"]), "--exit-code", *extra])


def test_b1_closed_gap016_is_named_with_absent_and_exit_0(gap016):
    rc, out, err = _g16(gap016, "good")
    assert (rc, err) == (0, "")
    line = _line(out)
    expected_prefix = (f"Baseline: {gap016['base']} -- carried PRESENT: 1; "
                       "new above-floor PRESENT: 0 (none); scanned by the baseline: 0 (none); "
                       "unscanned by the baseline: 0 (none)")
    assert line == expected_prefix + "; no longer PRESENT: 1 (GAP-016 ABSENT)"


# --------------------------------------------------------------------------- b2 nothing
def test_b2_nothing_closed_reads_zero_none_and_rc_unchanged(gap016, bed):
    rc, out, err = _g16(gap016, "bad")
    assert (rc, err) == (0, "")
    assert _line(out).endswith("; unscanned by the baseline: 0 (none); no longer PRESENT: 0 (none)")
    rc, out, err = _gate(bed, "all_present")
    assert (rc, err) == (0, "")
    assert PREFIX_RE.match(_line(out))
    assert _clause(out) == (0, "none")


def test_b2_new_present_still_exits_1_and_clause_is_appended(bed, tmp_path):
    # A baseline from a_fixed (A ABSENT) gated against all_present: A is NEW -> rc 1.
    rc, out, err = _run(["scan", str(bed["trees"]["a_fixed"]), "--gaps", str(bed["reg"]),
                         "--json"])
    base = tmp_path / "base.json"
    base.write_text(out, encoding="utf-8")
    rc, out, err = _gate(bed, "all_present", baseline=base)
    assert (rc, err) == (1, "")
    assert PREFIX_RE.match(_line(out))
    assert "new above-floor PRESENT: 1 (GAP-961)" in _line(out)
    assert _clause(out) == (0, "none")


# --------------------------------------------------------------------------- b3/b4 verdicts
def test_b3_b4_current_verdict_listed_ascending_never_as_fixed(bed):
    rc, out, err = _gate(bed, "mixed")
    assert (rc, err) == (0, "")
    assert PREFIX_RE.match(_line(out))
    assert _line(out).endswith(
        "; no longer PRESENT: 3 (GAP-961 ABSENT, GAP-963 MANUAL, GAP-964 NOT_APPLICABLE)")


def test_b4_entries_ascending_and_count_matches(bed):
    rc, out, err = _gate(bed, "b_fixed_m_manual")
    assert (rc, err) == (0, "")
    n, body = _clause(out)
    entries = body.split(", ")
    assert n == len(entries) == 2
    assert entries == ["GAP-962 ABSENT", "GAP-963 MANUAL"]
    ids = [e.split(" ")[0] for e in entries]
    assert ids == sorted(ids)
    for e in entries:
        assert e.split(" ")[1] in VERDICTS


def test_b3_non_absent_is_never_listed_as_absent(bed):
    rc, out, _ = _gate(bed, "mixed")
    body = _clause(out)[1]
    assert "GAP-963 ABSENT" not in body and "GAP-964 ABSENT" not in body
    assert "PRESENT" not in body  # GAP-962 is still PRESENT: never listed


def test_b3_still_present_below_floor_is_not_listed(tmp_path):
    # GAP-965 is confidence 0 (model-output): PRESENT but below the default floor in both
    # scans. Still PRESENT -> never listed; GAP-961 fixed -> listed ABSENT.
    reg = tmp_path / "gaps"
    reg.mkdir()
    a = _gap("A")
    w = _record("GAP-965", 4, 4, 4, ("model-output",), None)
    w["check"] = {**_check("B"), "id": "CHK-965"}
    for rec in (a, w):
        (reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    bad = _tree(tmp_path / "bad", {"A": "sig", "B": "sig"})
    good = _tree(tmp_path / "good", {"A": "fix", "B": "sig"})
    rc, out, err = _run(["scan", str(bad), "--gaps", str(reg), "--json"])
    found = {f["gap_id"]: (f["verdict"], f["below_floor"]) for f in json.loads(out)["findings"]}
    assert found == {"GAP-961": ("PRESENT", False), "GAP-965": ("PRESENT", True)}
    base = tmp_path / "base.json"
    base.write_text(out, encoding="utf-8")
    rc, out, err = _run(["scan", str(good), "--gaps", str(reg), "--exit-code",
                         "--baseline", str(base)])
    assert (rc, err) == (0, "")
    assert PREFIX_RE.match(_line(out))["carried"] == "2"
    assert _clause(out) == (1, "GAP-961 ABSENT")


# --------------------------------------------------------------------------- b5 unscanned
def test_b5_gap_narrowing_does_not_close_unscanned_ids(bed):
    rc, out, err = _gate(bed, "all_present", "--gap", "GAP-962")
    assert (rc, err) == (0, "")
    line = _line(out)
    m = PREFIX_RE.match(line)
    assert m and m["carried"] == "4"
    assert _clause(out) == (0, "none")
    for gid in ("GAP-961", "GAP-963", "GAP-964"):
        assert gid not in CLAUSE_RE.search(line)["body"]


def test_b5_narrowed_to_a_closed_gap_lists_only_it(bed):
    rc, out, err = _gate(bed, "mixed", "--gap", "GAP-961")
    assert (rc, err) == (0, "")
    assert PREFIX_RE.match(_line(out))["carried"] == "4"
    assert _clause(out) == (1, "GAP-961 ABSENT")


# --------------------------------------------------------------------------- b6 json
def _json_gate(bed, tree, *extra):
    rc, out, err = _gate(bed, tree, "--json", *extra)
    assert err == ""
    assert out.endswith("}\n") and not out.endswith("\n\n")
    return rc, json.loads(out)


def test_b6_json_key_is_last_and_mirrors_the_markdown(bed):
    for tree in TREES:
        rc_md, md, _ = _gate(bed, tree)
        rc_js, payload = _json_gate(bed, tree)
        assert rc_md == rc_js
        b = payload["baseline"]
        assert list(b)[-1] == "no_longer_present"
        assert list(b)[-2] == "unscanned"
        n, body = _clause(md)
        expected = [] if body == "none" else [
            {"gap_id": e.split(" ")[0], "verdict": e.split(" ")[1]} for e in body.split(", ")]
        assert b["no_longer_present"] == expected
        assert len(expected) == n
        for entry in b["no_longer_present"]:
            assert list(entry) == ["gap_id", "verdict"]


def test_b6_json_mixed_value(bed):
    _, payload = _json_gate(bed, "mixed")
    assert payload["baseline"]["no_longer_present"] == [
        {"gap_id": "GAP-961", "verdict": "ABSENT"},
        {"gap_id": "GAP-963", "verdict": "MANUAL"},
        {"gap_id": "GAP-964", "verdict": "NOT_APPLICABLE"},
    ]


def test_b6_json_other_payload_keys_equal_the_unflagged_scan(bed):
    rc, plain, err = _run(["scan", str(bed["trees"]["mixed"]), "--gaps", str(bed["reg"]),
                           "--json"])
    _, flagged = _json_gate(bed, "mixed")
    plain = json.loads(plain)
    assert list(flagged) == list(plain)
    assert plain["baseline"] is None and flagged["baseline"] is not None
    for k in plain:
        if k != "baseline":
            assert flagged[k] == plain[k], k


def test_b6_gap016_json(gap016):
    rc, out, err = _g16(gap016, "good", "--json")
    assert (rc, err) == (0, "")
    b = json.loads(out)["baseline"]
    assert list(b) == ["path", "carried", "new", "scanned", "unscanned", "no_longer_present"]
    assert b["no_longer_present"] == [{"gap_id": "GAP-016", "verdict": "ABSENT"}]
    assert b["carried"] == ["GAP-016"] and b["new"] == []


# --------------------------------------------------------------------------- b7 exit code
@pytest.mark.parametrize("tree,extra,expected", [
    ("all_present", (), 0), ("a_fixed", (), 0), ("mixed", (), 0),
    ("b_fixed_m_manual", (), 0), ("all_present", ("--gap", "GAP-962"), 0),
])
def test_b7_exit_code_is_the_partition_rule_alone(bed, tree, extra, expected):
    rc, out, err = _gate(bed, tree, *extra)
    assert (rc, err) == (expected, "")
    # The flagless twin exits 1 on every tree here (something is PRESENT above floor),
    # so the 0 is the baseline's doing, and the closure clause changes nothing.
    rc_bare, _, _ = _run(["scan", str(bed["trees"][tree]), "--gaps", str(bed["reg"]),
                          "--exit-code", *extra])
    assert rc_bare == 1


# --------------------------------------------------------------------------- b8 no baseline
def test_b8_no_baseline_output_has_no_clause_and_one_newline(bed):
    for tree in TREES:
        for extra in ((), ("--json",)):
            rc, out, err = _run(["scan", str(bed["trees"][tree]), "--gaps", str(bed["reg"]),
                                 *extra])
            assert (rc, err) == (0, "")
            assert "no longer PRESENT" not in out and "no_longer_present" not in out
            assert "Baseline:" not in out
            assert out.endswith("\n") and not out.endswith("\n\n")


def test_b8_flagged_markdown_ends_in_one_newline(bed):
    rc, out, _ = _gate(bed, "mixed")
    assert out.endswith("\n") and not out.endswith("\n\n")


@pytest.mark.parametrize("case", ["missing", "dir", "notdoc", "mismatch", "noexit"])
def test_b8_refusals_unchanged(bed, tmp_path, case):
    t, reg = str(bed["trees"]["mixed"]), str(bed["reg"])
    argv = ["scan", t, "--gaps", reg, "--exit-code", "--baseline"]
    if case == "missing":
        argv.append(str(tmp_path / "nope.json"))
        needle = "not a file"
    elif case == "dir":
        argv.append(str(tmp_path))
        needle = "not a file"
    elif case == "notdoc":
        p = tmp_path / "x.json"
        p.write_text("[]\n", encoding="utf-8")
        argv.append(str(p))
        needle = "not a scan document"
    elif case == "mismatch":
        other = _tree(tmp_path, TREES["all_present"], name="service")
        argv = ["scan", str(other), "--gaps", reg, "--exit-code", "--baseline",
                str(bed["base"])]
        needle = "target mismatch"
    else:
        argv = ["scan", t, "--gaps", reg, "--baseline", str(bed["base"])]
        needle = "--baseline requires --exit-code"
    rc, out, err = _run(argv)
    assert rc == 2 and out == ""
    assert err.startswith("Error: ") and needle in err


# --------------------------------------------------------------------------- b9 contract
def _baseline_paragraphs() -> list[str]:
    text = CONTRACT.read_text(encoding="utf-8")
    return [p for p in text.split("\n\n") if "--baseline" in p]


def test_b9_contract_documents_clause_key_and_honesty():
    joined = "\n".join(_baseline_paragraphs())
    assert "no longer PRESENT" in joined
    assert "no_longer_present" in joined
    flat = " ".join(joined.split())
    assert "ABSENT" in flat
    assert re.search(r"only `?ABSENT`?", flat), "contract must say only ABSENT means fixed"
    assert re.search(r"no (current )?finding in this scan|no current finding", flat), \
        "contract must say an id with no current finding is not listed"
