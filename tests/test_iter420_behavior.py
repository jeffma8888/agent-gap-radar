"""Iteration 420 behaviors: ``radar show <ID> --json`` carries the record's check.

THE ISOLATION CONTRACT IS HONORED.  Every expectation below comes from
``pm.md``'s Expected Behaviors 1-11.  No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff.  Behavior is
measured by running the CLI (in process, or in a child interpreter over a
``git archive HEAD src`` tree for the pre-change comparison), and by reading
the shipped ``gaps/`` records and ``docs/CONSUMER_CONTRACT.md``.

Ship-hazard notes: no commit sha is pinned (the HEAD comparison pops ``check``
from BOTH sides, so it still holds after the ship commit moves HEAD), no
wall-clock bound, no optional extra.
"""

from __future__ import annotations

import io
import json
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
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
TIMEOUT = 300

PRIOR_KEYS = [
    "gap_id", "title", "layer", "gap_type", "status", "priority",
    "confidence", "below_floor", "strongest_source", "problem", "symptom",
    "why_now", "existing", "build_hypothesis", "tags", "evidence",
]
SLOT_ORDER = ["applies_when", "present_when", "mitigated_when"]

CHECK_LINE = re.compile(r"^- Check: `([^`]+)` \(detectability `([^`]+)`\)$")
NONE_LINE = "- Check: none declared (detectability `none`)"
RULES_PREFIX = "- Rules declared: "


def _cli(capsys, *argv):
    try:
        rc = main(list(argv)) or 0
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else 1
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _show_json(capsys, gap_id):
    rc, out, err = _cli(capsys, "show", gap_id, str(GAPS), "--json")
    assert rc == 0, (gap_id, rc, err)
    return json.loads(out)


def _record_ids():
    ids = []
    for p in sorted(GAPS.glob("GAP-*.json")):
        ids.append(json.loads(p.read_text(encoding="utf-8"))["id"])
    return ids


ALL_IDS = _record_ids()

# A child script that renders every record's show (markdown + --json) and
# returns one JSON doc; run against either the live src or a HEAD archive.
_CHILD = r"""
import contextlib, io, json, sys
from agent_gap_radar.cli import main
gaps, ids = sys.argv[1], sys.argv[2:]
res = {}
for gid in ids:
    entry = {}
    for mode, extra in (("md", []), ("json", ["--json"])):
        buf, ebuf = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(ebuf):
                rc = main(["show", gid, gaps] + extra) or 0
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
        entry[mode] = [rc, buf.getvalue(), ebuf.getvalue()]
    res[gid] = entry
sys.stdout.write(json.dumps(res))
"""


def _child_run(src_dir, cwd):
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(src_dir),
           "PYTHONHASHSEED": "0", "HOME": str(cwd)}
    p = subprocess.run([sys.executable, "-c", _CHILD, str(GAPS), *ALL_IDS],
                       capture_output=True, text=True, cwd=str(cwd), env=env,
                       timeout=TIMEOUT)
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


@pytest.fixture(scope="module")
def both_trees(tmp_path_factory):
    if shutil.which("git") is None:
        pytest.skip("no git binary")
    p = subprocess.run(["git", "-C", str(REPO), "archive", "HEAD", "src"],
                       capture_output=True, timeout=TIMEOUT)
    if p.returncode != 0:
        pytest.skip("git archive unavailable")
    base = tmp_path_factory.mktemp("iter420")
    old = base / "old"
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(old, filter="data")
    work = base / "cwd"
    work.mkdir()
    new = _child_run(REPO / "src", work)
    head = _child_run(old / "src", work)
    return new, head


@pytest.fixture(scope="module")
def live_docs():
    """Every record's live show --json + markdown, gathered in process."""
    import contextlib
    res = {}
    for gid in ALL_IDS:
        entry = {}
        for mode, extra in (("md", []), ("json", ["--json"])):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["show", gid, str(GAPS)] + extra) or 0
            assert rc == 0, (gid, mode)
            entry[mode] = buf.getvalue()
        res[gid] = entry
    return res


# ---------------------------------------------------------------- premise

def test_premise_register_population():
    assert len(ALL_IDS) >= 100
    for gid in ("GAP-001", "GAP-010", "GAP-026", "GAP-041"):
        assert gid in ALL_IDS


# ---------------------------------------------------------------- B1

def test_b1_key_order_check_last(capsys):
    doc = _show_json(capsys, "GAP-041")
    assert list(doc) == PRIOR_KEYS + ["check"]


# ---------------------------------------------------------------- B2

def test_b2_gap041_check_exact(capsys):
    doc = _show_json(capsys, "GAP-041")
    expected = {
        "id": "CHK-040",
        "detectability": "automated",
        "rules": [
            {"slot": "applies_when", "kind": "all_of"},
            {"slot": "present_when", "kind": "all_of"},
            {"slot": "mitigated_when", "kind": "content_matches"},
        ],
    }
    assert doc["check"] == expected
    assert list(doc["check"]) == ["id", "detectability", "rules"]
    for rule in doc["check"]["rules"]:
        assert list(rule) == ["slot", "kind"]


# ---------------------------------------------------------------- B3

def test_b3_gap010_check_null_record_still_shown(capsys):
    rc, out, err = _cli(capsys, "show", "GAP-010", str(GAPS), "--json")
    assert rc == 0, err
    assert '"check": null' in out
    doc = json.loads(out)
    assert "check" in doc and doc["check"] is None
    assert doc["gap_id"] == "GAP-010"
    assert doc["below_floor"] is True
    assert isinstance(doc["evidence"], list) and len(doc["evidence"]) >= 1


# ---------------------------------------------------------------- B4

def test_b4_manual_no_rules(capsys):
    doc = _show_json(capsys, "GAP-001")
    assert doc["check"] == {"id": "CHK-001", "detectability": "manual",
                            "rules": []}


def test_b4_manual_with_applies_when_only(capsys):
    doc = _show_json(capsys, "GAP-026")
    assert doc["check"]["id"] == "CHK-025"
    assert doc["check"]["detectability"] == "manual"
    assert doc["check"]["rules"] == [{"slot": "applies_when", "kind": "any_of"}]


# ---------------------------------------------------------------- B5

def test_b5_markdown_json_parity_every_record(live_docs):
    seen_null = seen_rules = seen_empty = 0
    for gid, entry in live_docs.items():
        check = json.loads(entry["json"])["check"]
        lines = entry["md"].splitlines()
        check_lines = [ln for ln in lines if ln.startswith("- Check: ")]
        rules_lines = [ln for ln in lines if ln.startswith(RULES_PREFIX)]
        assert len(check_lines) == 1, (gid, check_lines)
        if check is None:
            seen_null += 1
            assert check_lines[0] == NONE_LINE, gid
            assert rules_lines == [], gid
            continue
        m = CHECK_LINE.match(check_lines[0])
        assert m, (gid, check_lines[0])
        assert (m.group(1), m.group(2)) == (check["id"],
                                            check["detectability"]), gid
        slots = [r["slot"] for r in check["rules"]]
        assert slots == [s for s in SLOT_ORDER if s in slots], gid
        if check["rules"] == []:
            seen_empty += 1
            assert rules_lines == [], gid
        else:
            seen_rules += 1
            assert len(rules_lines) == 1, gid
            rendered = ", ".join(f"`{r['slot']}` ({r['kind']})"
                                 for r in check["rules"])
            assert rules_lines[0] == RULES_PREFIX + rendered, gid
    # premise: the sweep exercised all three branches
    assert seen_null >= 1 and seen_rules >= 100 and seen_empty >= 1


def test_b5_rules_mirror_record_slots(live_docs):
    """Declared slots and kinds come from the record's own check object."""
    for p in sorted(GAPS.glob("GAP-*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        check = json.loads(live_docs[rec["id"]]["json"])["check"]
        raw = rec.get("check")
        if not raw:
            assert check is None, rec["id"]
            continue
        assert check["id"] == raw["id"], rec["id"]
        want = [{"slot": s, "kind": raw[s]["kind"]} for s in SLOT_ORDER
                if raw.get(s)]
        assert check["rules"] == want, rec["id"]


# ---------------------------------------------------------------- B6

def test_b6_prd_source_gap_check_agrees(capsys, live_docs):
    compared = 0
    for gid, entry in live_docs.items():
        check = json.loads(entry["json"])["check"]
        if check is None:
            continue
        rc, out, _err = _cli(capsys, "prd", str(GAPS), "--gap", gid)
        if rc != 0:
            continue
        src = json.loads(out)["sourceGap"]["check"]
        assert (check["id"], check["detectability"]) == (
            src["id"], src["detectability"]), gid
        compared += 1
    assert compared >= 1


# ---------------------------------------------------------------- B7 / B8

def test_b7_json_minus_check_equals_head(both_trees):
    new, head = both_trees
    for gid in ALL_IDS:
        rc_n, out_n, _ = new[gid]["json"]
        rc_h, out_h, _ = head[gid]["json"]
        assert rc_n == rc_h == 0, gid
        doc_n, doc_h = json.loads(out_n), json.loads(out_h)
        assert "check" in doc_n, gid
        doc_n.pop("check")
        doc_h.pop("check", None)  # HEAD moves at ship; compare prior keys only
        assert list(doc_n) == list(doc_h) == PRIOR_KEYS, gid
        assert doc_n == doc_h, gid


def test_b8_markdown_byte_identical_to_head(both_trees):
    new, head = both_trees
    for gid in ALL_IDS:
        assert new[gid]["md"][0] == head[gid]["md"][0] == 0, gid
        assert new[gid]["md"][1] == head[gid]["md"][1], gid


# ---------------------------------------------------------------- B9

def test_b9_byte_stable_one_newline(capsys):
    _rc1, out1, _ = _cli(capsys, "show", "GAP-041", str(GAPS), "--json")
    _rc2, out2, _ = _cli(capsys, "show", "GAP-041", str(GAPS), "--json")
    assert out1 == out2
    assert out1.endswith("\n") and not out1.endswith("\n\n")


# ---------------------------------------------------------------- B10

def test_b10_unknown_id_unchanged(capsys):
    rc, out, err = _cli(capsys, "show", "GAP-999", str(GAPS), "--json")
    assert rc == 2
    assert err.startswith("Error: ")
    assert out == ""


# ---------------------------------------------------------------- B11

def test_b11_consumer_contract_row():
    text = CONTRACT.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines()
            if ln.startswith("|") and "radar show" in ln and "check" in ln]
    assert rows, "no CONSUMER_CONTRACT row for radar show mentions check"
    row = rows[0]
    for word in ("null", "detectability", "rules", "slot", "kind",
                 "sourceGap"):
        assert word in row, word
    # check named as the last top-level key: it follows evidence in the row
    assert row.index("evidence") < row.rindex("check")
