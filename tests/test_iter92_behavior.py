"""Iteration 92 behaviors: `scan --json` findings and `prd`'s `sourceGap` publish the
register record's own `status`.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors, and every shape claim was measured by
RUNNING the tool -- `radar --help` and each verb's `--help` for the surface, `radar
taxonomy` for the closed status vocabulary, and one `prd --gap` per status -- or by reading
`tests/` and the PUBLISHED `docs/CONSUMER_CONTRACT.md` as data. ONE DISCLOSURE, also carried
in the tester report: while establishing the `scan()` / `scan_json()` call convention two
probes raised TypeErrors whose tracebacks printed three fragmentary lines of `scan.py`. No
assertion in this file was taken from them; the convention used below is the one
`tests/test_iter13_behavior.py` already uses.

Structural notes, so this file cannot lie later:

* **The append-only claim is spelled ONCE.** `FINDING_KEYS` and `SOURCE_GAP_KEYS` are
  DERIVED as `PRE_EXISTING_... + ["status"]`, so a test that passes proves both halves the
  spec asks for at once: every pre-existing key keeps its absolute index, and `status` is
  last. There is no second literal that could drift from the first.
* **The status vocabulary is IMPORTED, never written down.** `models.STATUSES` drives the
  per-status table, so a future status lands in these tests without an edit and a removed
  one reds them.
* **Every fixture asserts its own premise.** The `UNKNOWN` case asserts the SAME fixture
  returns a different verdict uncut, so "UNKNOWN" is attributable to the truncated domain
  rather than to a typo in a marker. The `MANUAL` case asserts the verdict it claims. The
  byte-identity pair asserts the differing status string occurs exactly once before
  substituting it.
* **Behavior 5 is proven TWO-SIDED by mutating the payload, not by hoping.**
  `_selection_facts` is applied to the real pair (must be equal) AND to two mutants of the
  same payload -- an emitter that DROPS non-`open` findings, and one that DEPRIORITISES them
  to the end -- each of which must make the comparison unequal. Without the mutants, a
  comparison that only ever sees a non-filtering emitter is indistinguishable from a
  comparison that cannot see filtering at all.
* **The frozen table is asserted as CONFINEMENT, not as a HEAD comparison.** HEAD moves the
  moment this iteration lands, so `== git show HEAD` would be vacuous from the next
  iteration onwards (the reasoning `tests/test_iter29_behavior.py` records). The byte-for-byte
  pre-iteration comparison is measured once, out of band, in the tester's report. What is
  durable and asserted here: the frozen table's ten row keys in order, its `status` row
  verbatim, and that none of this iteration's payload vocabulary leaked into it.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every register and target is built under pytest's `tmp_path`.
* **Nothing under `gaps/` is read to make an assertion true.** That register is grown by an
  unattended research pass, so a keyed expectation over it would red on a CORRECT register.
  The two live-register tests assert only properties that must hold for ANY record, and each
  guards against a vacuous domain first.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main
from agent_gap_radar.models import STATUSES
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import scan, scan_json
from test_iter02_behavior import MARKER, _record, _target, _write_register

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
LIVE_GAPS = REPO_ROOT / "gaps"

#: The paragraph of the consumer contract that specifies the `scan --json` surface.
SCAN_JSON_MARKER = "**`scan --json` SHIPPED.**"

#: Behavior 1. The twelve per-finding keys that pre-date this iteration, in emitted order
#: (measured by running `scan --json` at HEAD before writing this file). `status` is
#: APPENDED, so this literal keeps recording what pre-existed and the tail below documents
#: append-only growth in order.
PRE_EXISTING_FINDING_KEYS = [
    "gap_id", "title", "layer", "gap_type", "verdict", "priority", "confidence",
    "below_floor", "reason", "question", "locations", "build_hypothesis",
]
FINDING_KEYS = PRE_EXISTING_FINDING_KEYS + ["status"]

#: Behavior 3. Same shape of claim for `sourceGap`'s seven pre-existing inner keys.
PRE_EXISTING_SOURCE_GAP_KEYS = [
    "id", "layer", "gapType", "priority", "confidence", "evidence", "check",
]
SOURCE_GAP_KEYS = PRE_EXISTING_SOURCE_GAP_KEYS + ["status"]

#: Behavior 7. `list --json` already published `status` (at index 4) before this iteration;
#: it must not move. Measured by running `radar list . --json`.
LIST_RECORD_KEYS = ["gap_id", "title", "layer", "gap_type", "status", "priority",
                    "confidence", "below_floor"]

#: Behavior 2. The value a record that OMITS the key must publish.
DEFAULT_STATUS = "open"
#: A status that is valid, stored, and not the default. Asserted to be in `STATUSES`.
OTHER_STATUS = "partially-addressed"

#: Behavior 6. The frozen table, pinned by its ROW KEYS and by the one row this iteration
#: is about, so a rename, a removal or a reorder reds here after the commit lands too.
FROZEN_HEADING = "### Keys the declared consumer reads"
FROZEN_ROW_KEYS = ["id", "status", "layer", "severity", "frequency", "tractability",
                   "title", "gap_type", "evidence", "source_class"]
FROZEN_STATUS_ROW = "| `status` | Gap | required; the consumer selects on it |"

#: The two markers behavior 2's UNKNOWN fixture needs. `mitigated_when` is credited only
#: from code that runs, so neither file is named like a test.
TAIL_SIGNATURE = "GAPRADAR_ITER92_TAIL_SIGNATURE"
HEAD_MITIGATION = "GAPRADAR_ITER92_HEAD_MITIGATION"


# --------------------------------------------------------------------------- fixtures
#
# `MARKER`, `_record`, `_write_register` and `_target` come from
# tests/test_iter02_behavior.py. `_record` never sets `status`, so a record built by it is
# exactly behavior 2's "record file that OMITS status" case.


def _with_status(record, status):
    return {**record, "status": status}


def _manual_check(cid):
    """A check carrying only a question -- no static signature, so the verdict is MANUAL.

    This is the shape the live register's manual-only records use (measured as data).
    """
    return {"id": cid, "rationale": "r", "manual_question": "q"}


def _manual_record(gid, sev=3, freq=3, tract=3):
    rec = _record(gid, sev, freq, tract, classes=("first-party-field",))
    rec["check"] = _manual_check(f"CHK-{gid[-3:]}")
    return rec


def _truncatable_check(cid):
    """PRESENT lives in the tail of the file list, the mitigation in the head.

    Uncut the domain reaches both; cut to one file it reaches only the mitigation, which is
    the shape iteration 63 converts from a safety claim into `UNKNOWN`.
    """
    return {
        "id": cid, "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": TAIL_SIGNATURE},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": HEAD_MITIGATION},
        "fixtures": {"bad": {"a.py": TAIL_SIGNATURE + "\n"},
                     "good": {"a.py": HEAD_MITIGATION + "\n"}},
    }


def _split_target(root):
    """Two files whose sorted order puts the mitigation first and the signature last."""
    t = root / "target"
    (t / "app").mkdir(parents=True)
    (t / "app" / "a_runtime.py").write_text(HEAD_MITIGATION + "\n", encoding="utf-8")
    (t / "app" / "z_runtime.py").write_text(TAIL_SIGNATURE + "\n", encoding="utf-8")
    return t


def _reg(tmp_path, name, records):
    return _write_register(tmp_path / name, list(records))


def _cli_json(tmp_path, name, records, target, capsys):
    """`scan --json` through the CLI. Returns (raw stdout, payload, rc, stderr)."""
    reg = _reg(tmp_path, name, records)
    rc = main(["scan", str(target), "--gaps", str(reg), "--json"])
    cap = capsys.readouterr()
    return cap.out, json.loads(cap.out), rc, cap.err


def _cli_prd(argv, capsys):
    rc = main(argv)
    cap = capsys.readouterr()
    return cap.out, json.loads(cap.out) if cap.out else None, rc, cap.err


def _statuses(payload):
    return {f["gap_id"]: f["status"] for f in payload["findings"]}


def _contract_section(heading):
    """The text from `heading` up to the next heading of the same or shallower depth."""
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    start = text.index(heading)
    depth = len(heading) - len(heading.lstrip("#"))
    rest = text[start + len(heading):]
    ends = [rest.index(mark) for mark in ("\n" + "#" * d + " " for d in range(1, depth + 1))
            if mark in rest]
    return heading + (rest[:min(ends)] if ends else rest)


# --------------------------------------------------------------------------- registers
#
# GAP-500 is the record whose status varies across the behavior-5 pair. It is deliberately
# the TOP-RANKED record and the FIRST finding, so an emitter that dropped it or pushed it
# down the order changes something this file asserts.

TOP = _record("GAP-500", 5, 5, 5, classes=("first-party-field",), check_id="CHK-500")
SECOND = _record("GAP-501", 4, 3, 3, classes=("first-party-field",), check_id="CHK-501")
NO_CHECK = _record("GAP-502", 2, 2, 2, classes=("first-party-field",))

OPEN_PAIR = [_with_status(TOP, DEFAULT_STATUS), SECOND, NO_CHECK]
OTHER_PAIR = [_with_status(TOP, OTHER_STATUS), SECOND, NO_CHECK]


@pytest.fixture()
def target(tmp_path):
    """A target that trips the fixture checks, so the checked records are PRESENT."""
    return _target(tmp_path / "hit")


def test_premise_the_status_vocabulary_is_what_this_file_assumes():
    """If either constant left the closed vocabulary, every table below is meaningless."""
    assert DEFAULT_STATUS in STATUSES, STATUSES
    assert OTHER_STATUS in STATUSES, STATUSES
    assert DEFAULT_STATUS != OTHER_STATUS


# ---------------------------------------------------------------------------
# Behavior 1 -- 13 finding keys, in order, `status` appended last.
# ---------------------------------------------------------------------------


def test_b1_every_finding_carries_the_thirteen_keys_in_order(tmp_path, target, capsys):
    _raw, payload, rc, err = _cli_json(tmp_path, "b1", OPEN_PAIR, target, capsys)
    assert rc == 0
    assert err == "", "the machine surface must not narrate on stderr"
    assert payload["findings"], "premise: the register must produce at least one finding"
    for finding in payload["findings"]:
        assert list(finding.keys()) == FINDING_KEYS, (finding["gap_id"], list(finding))


def test_b1_the_pre_existing_keys_keep_their_absolute_index(tmp_path, target, capsys):
    """Growth by APPENDING: even a positional reader of the old twelve is unbroken."""
    _raw, payload, _rc, _err = _cli_json(tmp_path, "b1idx", OPEN_PAIR, target, capsys)
    for finding in payload["findings"]:
        keys = list(finding.keys())
        assert keys[:len(PRE_EXISTING_FINDING_KEYS)] == PRE_EXISTING_FINDING_KEYS, keys
        assert keys[-1] == "status", keys
        for index, key in enumerate(PRE_EXISTING_FINDING_KEYS):
            assert keys[index] == key, (index, key, keys[index])


def test_b1_no_pre_existing_finding_key_was_renamed_or_removed(tmp_path, target, capsys):
    _raw, payload, _rc, _err = _cli_json(tmp_path, "b1keep", OPEN_PAIR, target, capsys)
    for finding in payload["findings"]:
        missing = [k for k in PRE_EXISTING_FINDING_KEYS if k not in finding]
        assert missing == [], missing
        added = [k for k in finding if k not in FINDING_KEYS]
        assert added == [], added


def test_b1_status_is_a_plain_non_empty_string(tmp_path, target, capsys):
    """A `null` or an absent key breaks `status == "open"` on the gate side."""
    _raw, payload, _rc, _err = _cli_json(tmp_path, "b1str", OPEN_PAIR, target, capsys)
    for finding in payload["findings"]:
        assert isinstance(finding["status"], str), finding["status"]
        assert finding["status"], finding["gap_id"]


# ---------------------------------------------------------------------------
# Behavior 2 -- the value is the record's own, pass-through; omission means `open`.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", STATUSES)
def test_b2_each_finding_publishes_its_own_records_stored_status(
        status, tmp_path, target, capsys):
    records = [_with_status(TOP, status), _with_status(SECOND, DEFAULT_STATUS)]
    _raw, payload, rc, _err = _cli_json(tmp_path, f"b2-{status}", records, target, capsys)
    assert rc == 0
    got = _statuses(payload)
    assert got["GAP-500"] == status, got
    assert got["GAP-501"] == DEFAULT_STATUS, got


def test_b2_a_record_file_that_omits_status_publishes_open(tmp_path, target, capsys):
    """Never `null`, never an absent key: `open` is the resolved value of the field."""
    assert "status" not in TOP, "premise: the shared builder must not set a status"
    _raw, payload, rc, _err = _cli_json(tmp_path, "b2omit", [TOP, SECOND], target, capsys)
    assert rc == 0
    for finding in payload["findings"]:
        assert "status" in finding, list(finding)
        assert finding["status"] is not None, finding["gap_id"]
        assert finding["status"] == DEFAULT_STATUS, (finding["gap_id"], finding["status"])


def test_b2_the_key_is_present_on_a_manual_finding(tmp_path, target, capsys):
    manual = _with_status(_manual_record("GAP-510"), OTHER_STATUS)
    _raw, payload, rc, _err = _cli_json(tmp_path, "b2man", [manual], target, capsys)
    assert rc == 0
    finding = payload["findings"][0]
    assert finding["verdict"] == "MANUAL", finding["verdict"]
    assert list(finding.keys()) == FINDING_KEYS, list(finding)
    assert finding["status"] == OTHER_STATUS, finding["status"]


def test_b2_the_key_is_present_on_an_unknown_finding(tmp_path, monkeypatch):
    """A truncated domain converts the safety claim to UNKNOWN; `status` still ships.

    The uncut control over the SAME fixture is the premise: without it, a pass could mean
    nothing was ever found rather than that the cut was reported.
    """
    record = _with_status(_record("GAP-520", 4, 4, 4, classes=("first-party-field",)),
                          OTHER_STATUS)
    record["check"] = _truncatable_check("CHK-520")
    gaps = load_all(_reg(tmp_path, "b2unk", [record]))
    target = _split_target(tmp_path / "b2unk")

    uncut = json.loads(scan_json(scan(gaps, target)))["findings"][0]
    assert uncut["verdict"] != "UNKNOWN", uncut["verdict"]

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 1)
    cut = json.loads(scan_json(scan(gaps, target)))["findings"][0]
    assert cut["verdict"] == "UNKNOWN", cut["verdict"]
    assert list(cut.keys()) == FINDING_KEYS, list(cut)
    assert cut["status"] == OTHER_STATUS, cut["status"]


def test_b2_the_published_value_is_the_records_own_over_the_live_register():
    """A property true of ANY record, so a research pass cannot red this."""
    gaps = load_all(LIVE_GAPS)
    assert gaps, "premise: the committed register must load at least one record"
    stored = {}
    for path in sorted(LIVE_GAPS.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        stored[raw["id"]] = raw.get("status", DEFAULT_STATUS)
    target = REPO_ROOT
    payload = json.loads(scan_json(scan(gaps, target)))
    assert payload["findings"], "premise: scanning this repo must produce findings"
    for finding in payload["findings"]:
        assert finding["status"] == stored[finding["gap_id"]], finding["gap_id"]


# ---------------------------------------------------------------------------
# Behavior 3 -- `sourceGap` carries eight keys in order, and both doors agree.
# ---------------------------------------------------------------------------


def test_b3_prd_source_gap_carries_the_eight_keys_in_order(tmp_path, capsys):
    reg = _reg(tmp_path, "b3", [_with_status(TOP, OTHER_STATUS)])
    _raw, doc, rc, err = _cli_prd(["prd", str(reg), "--gap", "GAP-500"], capsys)
    assert rc == 0
    assert err == ""
    assert list(doc["sourceGap"].keys()) == SOURCE_GAP_KEYS, list(doc["sourceGap"])
    keys = list(doc["sourceGap"].keys())
    assert keys[:len(PRE_EXISTING_SOURCE_GAP_KEYS)] == PRE_EXISTING_SOURCE_GAP_KEYS, keys
    assert keys[-1] == "status", keys


def test_b3_both_prd_doors_publish_the_same_status(tmp_path, target, capsys):
    """`prd` and `scan --prd` for one selected record must agree on the value."""
    reg = _reg(tmp_path, "b3doors", [_with_status(TOP, OTHER_STATUS)])
    _raw_a, door_prd, rc_a, err_a = _cli_prd(["prd", str(reg), "--gap", "GAP-500"], capsys)
    _raw_b, door_scan, rc_b, err_b = _cli_prd(
        ["scan", str(target), "--gaps", str(reg), "--prd"], capsys)
    assert (rc_a, rc_b) == (0, 0)
    assert err_a == "" and err_b == ""
    assert door_scan["sourceGap"]["id"] == door_prd["sourceGap"]["id"] == "GAP-500"
    assert list(door_scan["sourceGap"].keys()) == SOURCE_GAP_KEYS
    assert door_scan["sourceGap"]["status"] == door_prd["sourceGap"]["status"] == OTHER_STATUS
    assert door_scan["sourceGap"] == door_prd["sourceGap"]


def test_b3_scan_prd_source_gap_carries_the_eight_keys_in_order(tmp_path, target, capsys):
    reg = _reg(tmp_path, "b3scan", [_with_status(TOP, DEFAULT_STATUS)])
    _raw, doc, rc, _err = _cli_prd(
        ["scan", str(target), "--gaps", str(reg), "--prd"], capsys)
    assert rc == 0
    assert list(doc["sourceGap"].keys()) == SOURCE_GAP_KEYS, list(doc["sourceGap"])


# ---------------------------------------------------------------------------
# Behavior 4 -- one stored status per emitted status, and nothing else moves.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", STATUSES)
def test_b4_prd_gap_publishes_the_stored_status_verbatim(status, tmp_path, capsys):
    reg = _reg(tmp_path, f"b4-{status}", [_with_status(TOP, status)])
    _raw, doc, rc, err = _cli_prd(["prd", str(reg), "--gap", "GAP-500"], capsys)
    assert rc == 0, err
    assert doc["sourceGap"]["status"] == status, doc["sourceGap"]["status"]


def test_b4_status_changes_no_other_emitted_key_and_no_exit_code(tmp_path, capsys):
    """Strip the one key and the two documents must be byte-identical."""
    docs, codes = {}, {}
    for status in STATUSES:
        reg = _reg(tmp_path, f"b4strip-{status}", [_with_status(TOP, status)])
        raw, doc, rc, _err = _cli_prd(["prd", str(reg), "--gap", "GAP-500"], capsys)
        codes[status] = rc
        assert doc["sourceGap"].pop("status") == status
        docs[status] = doc
    assert set(codes.values()) == {0}, codes
    first = docs[STATUSES[0]]
    for status, doc in docs.items():
        assert doc == first, status


def test_b4_a_partially_addressed_record_is_still_selected_and_still_exits_zero(
        tmp_path, capsys):
    """The out-of-scope line made explicit: publishing is not selecting."""
    reg = _reg(tmp_path, "b4sel", [_with_status(TOP, OTHER_STATUS), SECOND])
    _raw, doc, rc, err = _cli_prd(["prd", str(reg)], capsys)
    assert rc == 0, err
    assert doc["sourceGap"]["id"] == "GAP-500", doc["sourceGap"]["id"]
    assert doc["sourceGap"]["status"] == OTHER_STATUS


# ---------------------------------------------------------------------------
# Behavior 5 -- publishing `status` changes NO selection. Proven two-sided.
# ---------------------------------------------------------------------------


def _selection_facts(payload):
    """Everything about a scan payload that publishing `status` must not move."""
    return {
        "gap_ids": [f["gap_id"] for f in payload["findings"]],
        "verdicts": [f["verdict"] for f in payload["findings"]],
        "counts": payload["counts"],
        "uncheckable": payload["uncheckable"],
        "records_applied": payload["records_applied"],
    }


def _dropping_mutant(payload):
    """What the payload would look like if the emitter FILTERED non-`open` findings."""
    kept = [f for f in payload["findings"] if f["status"] == DEFAULT_STATUS]
    counts = dict.fromkeys(payload["counts"], 0)
    for finding in kept:
        counts[finding["verdict"]] = counts.get(finding["verdict"], 0) + 1
    return {**payload, "findings": kept, "counts": counts,
            "records_applied": len(kept) + len(payload["uncheckable"])}


def _deprioritising_mutant(payload):
    """What it would look like if the emitter merely pushed non-`open` findings last."""
    findings = sorted(payload["findings"], key=lambda f: f["status"] != DEFAULT_STATUS)
    return {**payload, "findings": findings}


def _pair(tmp_path, target, capsys):
    raw_open, open_payload, rc_a, err_a = _cli_json(
        tmp_path, "b5open", OPEN_PAIR, target, capsys)
    raw_other, other_payload, rc_b, err_b = _cli_json(
        tmp_path, "b5other", OTHER_PAIR, target, capsys)
    assert (rc_a, rc_b) == (0, 0)
    assert err_a == "" and err_b == ""
    return (raw_open, open_payload), (raw_other, other_payload)


def test_b5_the_varying_record_is_load_bearing(tmp_path, target, capsys):
    """Premise for the two mutants: GAP-500 is PRESENT, and it is NOT the last finding."""
    _open, (_raw, other) = _pair(tmp_path, target, capsys)
    ids = [f["gap_id"] for f in other["findings"]]
    assert len(ids) >= 2, ids
    assert ids[0] == "GAP-500", ids
    assert ids[-1] != "GAP-500", ids
    assert _statuses(other)["GAP-500"] == OTHER_STATUS
    assert other["uncheckable"], "premise: the pair must exercise `uncheckable` too"


def test_b5_no_selection_moves_when_one_records_status_changes(tmp_path, target, capsys):
    (_ro, open_payload), (_rt, other_payload) = _pair(tmp_path, target, capsys)
    assert _selection_facts(open_payload) == _selection_facts(other_payload)


def test_b5_the_two_payloads_differ_in_exactly_that_one_status_value(
        tmp_path, target, capsys):
    (raw_open, _o), (raw_other, _t) = _pair(tmp_path, target, capsys)
    needle = f'"status": "{OTHER_STATUS}"'
    assert raw_other.count(needle) == 1, raw_other.count(needle)
    assert raw_other != raw_open, "premise: the pair must actually differ"
    substituted = raw_other.replace(needle, f'"status": "{DEFAULT_STATUS}"')
    assert substituted == raw_open, "the payloads differ somewhere other than that value"


def test_b5_prd_selects_the_same_record_whatever_the_status_says(tmp_path, capsys):
    picks = {}
    for name, records in (("open", OPEN_PAIR), ("other", OTHER_PAIR)):
        reg = _reg(tmp_path, f"b5prd-{name}", records)
        _raw, doc, rc, err = _cli_prd(["prd", str(reg)], capsys)
        assert rc == 0, err
        picks[name] = doc["sourceGap"]["id"]
    assert picks["open"] == picks["other"] == "GAP-500", picks


def test_b5_a_filtering_emitter_would_red_this_files_comparison(
        tmp_path, target, capsys):
    """TWO-SIDED. The comparison above must be able to SEE a filter, not merely pass."""
    (_ro, open_payload), (_rt, other_payload) = _pair(tmp_path, target, capsys)
    dropped = _dropping_mutant(other_payload)
    assert dropped["findings"] != other_payload["findings"], \
        "premise: the mutant must actually remove the non-`open` finding"
    assert _selection_facts(dropped) != _selection_facts(open_payload), \
        "a filtering emitter would pass -- the comparison is blind to filtering"


def test_b5_a_deprioritising_emitter_would_red_this_files_comparison(
        tmp_path, target, capsys):
    """TWO-SIDED for the softer failure: reordering rather than dropping."""
    (_ro, open_payload), (_rt, other_payload) = _pair(tmp_path, target, capsys)
    moved = _deprioritising_mutant(other_payload)
    assert [f["gap_id"] for f in moved["findings"]] != \
        [f["gap_id"] for f in other_payload["findings"]], \
        "premise: the mutant must actually reorder"
    assert _selection_facts(moved) != _selection_facts(open_payload), \
        "a deprioritising emitter would pass -- the comparison is blind to reordering"


# ---------------------------------------------------------------------------
# Behavior 6 -- the published contract names the new key; the frozen table is untouched.
# ---------------------------------------------------------------------------


def test_b6_the_scan_json_section_names_status_among_the_finding_keys():
    section = _contract_section(SCAN_JSON_MARKER)
    assert "`status`" in section, section
    for key in FINDING_KEYS:
        assert f"`{key}`" in section, key


def test_b6_every_emitted_finding_key_is_named_in_that_section(tmp_path, target, capsys):
    """The section states its own rule: every key the tool emits must appear in the list."""
    _raw, payload, _rc, _err = _cli_json(tmp_path, "b6", OPEN_PAIR, target, capsys)
    section = _contract_section(SCAN_JSON_MARKER)
    for key in payload["findings"][0]:
        assert f"`{key}`" in section, key
    for key in payload:
        assert f"`{key}`" in section, key


def test_b6_the_prd_payload_section_names_status_inside_source_gap(tmp_path, capsys):
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "`sourceGap`" in text
    section = next(
        (_contract_section(line) for line in text.splitlines()
         if line.startswith("#") and "sourceGap" in line), None)
    assert section is not None, "no heading documents the `sourceGap` object"
    for key in SOURCE_GAP_KEYS:
        assert f"`{key}`" in section, key
    lowered = section.lower()
    assert "read from the register" in lowered or "read from the record" in lowered, section


def test_b6_the_frozen_consumer_table_is_confined_and_unchanged():
    """Asserted as CONFINEMENT: the row keys, the `status` row, and no new vocabulary."""
    section = _contract_section(FROZEN_HEADING)
    rows = [line for line in section.splitlines()
            if line.startswith("| `") and line.endswith("|")]
    keys = [line.split("|")[1].strip().strip("`") for line in rows]
    assert keys == FROZEN_ROW_KEYS, keys
    assert FROZEN_STATUS_ROW in section, [r for r in rows if "`status`" in r]
    for leaked in ("sourceGap", "findings", "build_hypothesis", "below_floor"):
        assert leaked not in section, leaked


# ---------------------------------------------------------------------------
# Behavior 7 -- no regression on the three published surfaces.
# ---------------------------------------------------------------------------


def test_b7_each_payload_is_one_json_document_ending_in_one_newline(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "b7", OPEN_PAIR)
    doors = {
        "scan --json": ["scan", str(target), "--gaps", str(reg), "--json"],
        "prd": ["prd", str(reg)],
        "scan --prd": ["scan", str(target), "--gaps", str(reg), "--prd"],
        "list --json": ["list", str(reg), "--json"],
    }
    for label, argv in doors.items():
        rc = main(argv)
        cap = capsys.readouterr()
        assert rc == 0, (label, rc, cap.err)
        assert cap.err == "", (label, cap.err)
        assert cap.out.endswith("\n"), label
        assert not cap.out.endswith("\n\n"), label
        json.loads(cap.out)  # exactly one document, or this raises


def test_b7_list_json_records_keep_their_eight_keys_unchanged(tmp_path, capsys):
    reg = _reg(tmp_path, "b7list", OPEN_PAIR)
    rc = main(["list", str(reg), "--json"])
    cap = capsys.readouterr()
    assert rc == 0
    payload = json.loads(cap.out)
    assert payload["records"], "premise: the listing must carry records"
    for record in payload["records"]:
        assert list(record.keys()) == LIST_RECORD_KEYS, list(record)


def test_b7_the_three_payloads_stay_byte_stable_across_runs(tmp_path, target, capsys):
    reg = _reg(tmp_path, "b7stable", OPEN_PAIR)
    for argv in (["scan", str(target), "--gaps", str(reg), "--json"],
                 ["prd", str(reg)],
                 ["scan", str(target), "--gaps", str(reg), "--prd"]):
        main(argv)
        first = capsys.readouterr().out
        main(argv)
        assert capsys.readouterr().out == first, argv
