"""Iteration 421 behaviors: the re-landed ``radar show <ID> --json`` ``check`` key.

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-11 (identical to iter 420's).  No test reads the
implementation source, the engineer's or reviewer's notes, or any diff.

This module complements ``test_iter420_behavior.py`` with INDEPENDENT oracles:
- the expected ``check`` object of EVERY record is re-derived from the raw
  ``gaps/*.json`` data (id + declared rule slots/kinds), not from the CLI's
  markdown;
- the CLI is driven in a CHILD interpreter (fresh process, varied
  PYTHONHASHSEED) so byte-stability and the error path are measured end to end,
  stdout and stderr separately.

Ship-hazard notes: no commit sha, no file:line locator, no wall-clock bound,
no optional extra.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
SLOT_ORDER = ("applies_when", "present_when", "mitigated_when")
TOP_KEYS = [
    "gap_id", "title", "layer", "gap_type", "status", "priority",
    "confidence", "below_floor", "strongest_source", "problem", "symptom",
    "why_now", "existing", "build_hypothesis", "tags", "evidence", "check",
]
CHILD = (
    "import sys\n"
    "from agent_gap_radar.cli import main\n"
    "rc = main(sys.argv[1:])\n"
    "sys.exit(rc or 0)\n"
)


def _raw_records() -> dict[str, dict]:
    out = {}
    for p in sorted(GAPS.glob("GAP-*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[rec["id"]] = rec
    return out


RAW = _raw_records()


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = main(list(argv)) or 0
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    return rc, out.getvalue(), err.getvalue()


def _child(*argv: str, seed: str = "0") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    return subprocess.run(
        [sys.executable, "-c", CHILD, *argv],
        capture_output=True, cwd=str(REPO), env=env, timeout=120,
    )


@pytest.fixture(scope="module")
def all_json() -> dict[str, dict]:
    docs = {}
    for gid in RAW:
        rc, out, err = _run("show", gid, str(GAPS), "--json")
        assert rc == 0, (gid, rc, err)
        docs[gid] = json.loads(out)
    return docs


def test_premise_register_has_both_kinds_of_record():
    with_check = [g for g, r in RAW.items() if r.get("check")]
    without = [g for g, r in RAW.items() if not r.get("check")]
    assert len(RAW) >= 100
    assert with_check and without, (len(with_check), len(without))


def test_b1_every_record_has_exact_key_order(all_json):
    for gid, doc in all_json.items():
        assert list(doc) == TOP_KEYS, gid


def test_b2_gap041_check_exact_and_ordered(all_json):
    check = all_json["GAP-041"]["check"]
    assert check == {
        "id": "CHK-040",
        "detectability": "automated",
        "rules": [
            {"slot": "applies_when", "kind": "all_of"},
            {"slot": "present_when", "kind": "all_of"},
            {"slot": "mitigated_when", "kind": "content_matches"},
        ],
    }
    assert list(check) == ["id", "detectability", "rules"]
    assert all(list(r) == ["slot", "kind"] for r in check["rules"])


def test_b3_gap010_null_check_but_record_shown(all_json):
    doc = all_json["GAP-010"]
    assert "check" in doc and doc["check"] is None
    assert doc["below_floor"] is True
    assert len(doc["evidence"]) >= 1
    assert doc["gap_id"] == "GAP-010"


def test_b4_manual_checks(all_json):
    assert all_json["GAP-001"]["check"] == {
        "id": "CHK-001", "detectability": "manual", "rules": [],
    }
    c26 = all_json["GAP-026"]["check"]
    assert c26["id"] == "CHK-025"
    assert c26["detectability"] == "manual"
    assert c26["rules"] == [{"slot": "applies_when", "kind": "any_of"}]


def test_b5_check_rederived_from_raw_record_data(all_json):
    """Independent oracle: id and declared slots/kinds come from gaps/*.json."""
    for gid, rec in RAW.items():
        got = all_json[gid]["check"]
        raw = rec.get("check")
        if not raw:
            assert got is None, gid
            continue
        assert got is not None, gid
        assert got["id"] == raw["id"], gid
        want_rules = [
            {"slot": s, "kind": raw[s]["kind"]}
            for s in SLOT_ORDER
            if raw.get(s)
        ]
        assert got["rules"] == want_rules, gid
        # 'none' is spelled as null, never as an object.
        assert got["detectability"] in ("automated", "manual"), gid


def test_b5_both_detectability_values_occur(all_json):
    seen = {d["check"]["detectability"] for d in all_json.values() if d["check"]}
    assert seen == {"automated", "manual"}, seen


def test_b5_markdown_names_same_check(all_json):
    for gid in RAW:
        rc, md, err = _run("show", gid, str(GAPS))
        assert rc == 0, (gid, err)
        check = all_json[gid]["check"]
        lines = md.splitlines()
        if check is None:
            assert "- Check: none declared (detectability `none`)" in lines, gid
            assert not any(ln.startswith("- Rules declared: ") for ln in lines), gid
            continue
        assert (
            f"- Check: `{check['id']}` (detectability `{check['detectability']}`)"
            in lines
        ), gid
        rules_lines = [ln for ln in lines if ln.startswith("- Rules declared: ")]
        if not check["rules"]:
            assert rules_lines == [], gid
        else:
            assert len(rules_lines) == 1, gid
            for r in check["rules"]:
                assert f"`{r['slot']}` ({r['kind']})" in rules_lines[0], gid


def test_b6_prd_agrees_on_sample(all_json):
    compared = 0
    for gid in ("GAP-041", "GAP-001", "GAP-026"):
        rc, out, _ = _run("prd", str(GAPS), "--gap", gid)
        if rc != 0:
            continue
        src = json.loads(out)["sourceGap"]["check"]
        mine = all_json[gid]["check"]
        assert (mine["id"], mine["detectability"]) == (
            src["id"], src["detectability"],
        ), gid
        compared += 1
    assert compared >= 1


def test_b9_child_process_byte_stable_one_newline():
    a = _child("show", "GAP-041", str(GAPS), "--json", seed="0")
    b = _child("show", "GAP-041", str(GAPS), "--json", seed="12345")
    assert a.returncode == 0 and b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout == b.stdout
    assert a.stdout.endswith(b"\n") and not a.stdout.endswith(b"\n\n")
    assert a.stderr == b""
    assert json.loads(a.stdout)["check"]["id"] == "CHK-040"


def test_b10_child_process_unknown_id():
    r = _child("show", "GAP-999", str(GAPS), "--json")
    assert r.returncode == 2
    assert r.stdout == b""
    assert r.stderr.decode("utf-8").startswith("Error: ")


def test_b11_contract_row_lists_check_last():
    row = next(
        ln for ln in CONTRACT.read_text(encoding="utf-8").splitlines()
        if ln.startswith("| `radar show")
    )
    assert "`evidence`, `check`, in that order" in row
    assert "`id`, `detectability`, `rules`" in row
    assert "sourceGap.check" in row
    assert "`slot`, `kind`" in row
