"""Iteration 13 behaviors: `radar scan --json` publishes the confidence floor it applied.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every assertion either drives
the public CLI entry point (`main`) or the public `scan` / `scan_json` API and observes
only the exit code, the stdout bytes and the stderr bytes, or reads a PUBLISHED document
(`docs/CONSUMER_CONTRACT.md`).

The floor value is never written here. `CONFIDENCE_FLOOR_DEFAULT` is IMPORTED, and every
other floor is DERIVED from numbers the payload itself published, so a change to the
register's threshold moves one constant in the product and no literal in this file.

Fixture design, and why it is not the `model-output` shape every earlier module uses.
Behavior 3 needs a record that is below the floor while still carrying REAL evidence, so
the below-floor case cannot be dismissed as "the zero-weight class only". One
`secondary-summary` citation scores 1 -- above `model-output`'s 0 (pinned by
tests/test_scoring.py's `_ladder_rank` ordering) and below the default floor. Each
fixture asserts that premise from the payload rather than assuming it, so a future change
to the ladder cannot leave a one-sided register passing a two-sided assertion.

Registers and targets are built in `tmp_path`. Nothing under `gaps/` is read to make an
assertion true and no id census is taken over it: that register is grown by an unattended
research pass, which would turn a keyed expectation into a RED suite over a CORRECT
register.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import scan, scan_json
from agent_gap_radar.scoring import CONFIDENCE_FLOOR_DEFAULT
from test_iter02_behavior import _record, _target, _write_register

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The paragraph of the consumer contract that specifies this surface. Behavior 7.
MARKER_SENTENCE = "**`scan --json` SHIPPED.**"

#: Spec behavior 1 / 2: the ORDER is part of the contract, not just the key set.
TOP_KEYS = ["target", "target_name", "confidence_floor", "records_applied",
            "counts", "uncheckable", "findings"]
#: Re-baselined 12 -> 13 in iteration 92: `status` was APPENDED as the new last key.
#: The pin's intent is "no key renamed, removed or reordered" -- every pre-existing key
#: keeps its absolute index here, so this literal still refuses the changes it exists to
#: refuse while documenting growth by appending.
FINDING_KEYS = ["gap_id", "title", "layer", "gap_type", "verdict", "priority",
                "confidence", "below_floor", "reason", "question", "locations",
                "build_hypothesis", "status"]

#: Below the floor with real evidence: one `secondary-summary` citation scores 1.
WEAK = _record("GAP-500", 5, 3, 5, classes=("secondary-summary",), check_id="CHK-500")
#: Clears the floor: one `first-party-field` citation scores 5.
STRONG = _record("GAP-501", 4, 3, 3, classes=("first-party-field",), check_id="CHK-501")


# ---------------------------------------------------------------------------
# Fixture builders. `_record`, `_write_register` and `_target` come from
# tests/test_iter02_behavior.py; a plain tmp_path target is not a git repo, so those
# builders' SKIP_DIRS walk is what makes the fixture checks fire at all.
# ---------------------------------------------------------------------------

@pytest.fixture()
def target(tmp_path):
    """A target that trips every fixture check, so both records are PRESENT."""
    return _target(tmp_path / "hit")


def _reg(tmp_path, name, records):
    return _write_register(tmp_path / name, records)


def _cli_json(tmp_path, target, capsys, records=(WEAK, STRONG), name="mixed"):
    """Run `scan --json` through the CLI and return (payload, rc, stderr)."""
    reg = _reg(tmp_path, name, list(records))
    rc = main(["scan", str(target), "--gaps", str(reg), "--json"])
    captured = capsys.readouterr()
    return json.loads(captured.out), rc, captured.err


def _result(tmp_path, name, records):
    """A `ScanResult` for the API-level behavior 4 assertions."""
    return scan(load_all(_reg(tmp_path, name, list(records))), _target(tmp_path / name))


# ---------------------------------------------------------------------------
# Behavior 1 -- the floor is published, at a fixed position, and equals the constant.
# ---------------------------------------------------------------------------

def test_b1_scan_json_publishes_the_imported_confidence_floor(tmp_path, target, capsys):
    payload, rc, err = _cli_json(tmp_path, target, capsys)
    assert rc == 0
    assert err == "", "the machine surface must not narrate on stderr"
    assert payload["confidence_floor"] == CONFIDENCE_FLOOR_DEFAULT


def test_b1_top_level_key_order_is_the_contract(tmp_path, target, capsys):
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    assert list(payload.keys()) == TOP_KEYS


def test_b1_the_published_floor_is_a_plain_integer(tmp_path, target, capsys):
    """A stringified or float floor would break `confidence < floor` on the gate side."""
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    assert isinstance(payload["confidence_floor"], int)
    assert not isinstance(payload["confidence_floor"], bool)


def test_b1_counts_stays_a_pure_verdict_census(tmp_path, target, capsys):
    """Out of scope by name: no below-floor total may be smuggled into `counts`."""
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    assert "confidence_floor" not in payload["counts"]
    assert "below_floor" not in payload["counts"]
    assert payload["counts"]["PRESENT"] == 2, "premise: both fixture records fired"


# ---------------------------------------------------------------------------
# Behavior 2 -- every finding is flagged against the published floor.
# ---------------------------------------------------------------------------

def test_b2_every_finding_carries_a_boolean_below_floor(tmp_path, target, capsys):
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    assert payload["findings"], "premise: the fixture produced findings to flag"
    for finding in payload["findings"]:
        flag = finding["below_floor"]
        assert isinstance(flag, bool), f"{finding['gap_id']} emitted {flag!r}, not a bool"


def test_b2_per_finding_key_order_is_the_contract(tmp_path, target, capsys):
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    assert payload["findings"], "premise: there is a finding whose keys can be ordered"
    for finding in payload["findings"]:
        assert list(finding.keys()) == FINDING_KEYS


def test_b2_no_blended_score_key_appears_beside_the_flag(tmp_path, target, capsys):
    """The register's core invariant: priority and confidence stay unblended."""
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    for finding in payload["findings"]:
        assert "score" not in finding


# ---------------------------------------------------------------------------
# Behavior 3 -- two-sided over real records, and consistent with the payload's own
# published integers.
# ---------------------------------------------------------------------------

def test_b3_the_flag_is_two_sided_over_one_register(tmp_path, target, capsys):
    payload, rc, err = _cli_json(tmp_path, target, capsys)
    assert rc == 0 and err == ""
    by_id = {f["gap_id"]: f for f in payload["findings"]}
    assert set(by_id) == {"GAP-500", "GAP-501"}, "a below-floor record was DROPPED"
    assert by_id["GAP-500"]["below_floor"] is True
    assert by_id["GAP-501"]["below_floor"] is False


def test_b3_the_below_floor_fixture_carries_real_evidence_not_a_zero(
        tmp_path, target, capsys):
    """The fixture's premise, measured: 0 < weak confidence < floor <= strong confidence.

    Without this, a ladder change that re-weighted `secondary-summary` would leave the
    two-sidedness assertion above passing over a register that is no longer two-sided.
    """
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    by_id = {f["gap_id"]: f["confidence"] for f in payload["findings"]}
    floor = payload["confidence_floor"]
    assert 0 < by_id["GAP-500"] < floor, "the weak fixture is not a below-floor record"
    assert by_id["GAP-501"] >= floor, "the strong fixture does not clear the floor"


def test_b3_every_flag_agrees_with_arithmetic_on_the_published_integers(
        tmp_path, target, capsys):
    """Left side is the product's claim; right side is arithmetic on two printed ints.

    Both are read out of the SERIALISED payload, so they can disagree -- which is what
    makes the clause worth asserting rather than a restatement of the same expression.
    """
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    floor = payload["confidence_floor"]
    assert payload["findings"], "premise: there is a finding to cross-check"
    for finding in payload["findings"]:
        derived = finding["confidence"] < floor
        assert finding["below_floor"] == derived, (
            f"{finding['gap_id']}: emitted below_floor={finding['below_floor']} but "
            f"confidence {finding['confidence']} vs floor {floor} implies {derived}")
    assert {f["below_floor"] for f in payload["findings"]} == {True, False}, (
        "the cross-check ran over a one-sided register, so it proved nothing")


def test_b3_the_below_floor_record_is_displayed_never_dropped(tmp_path, target, capsys):
    """VISION.md's protected rule: flagged, not filtered."""
    payload, _, _ = _cli_json(tmp_path, target, capsys)
    assert [f["gap_id"] for f in payload["findings"]] == ["GAP-500", "GAP-501"]
    assert payload["findings"][0]["verdict"] == "PRESENT"


# ---------------------------------------------------------------------------
# Behavior 4 -- an explicit floor is honoured; the default keeps callers working.
# ---------------------------------------------------------------------------

def test_b4_a_floor_above_every_record_flags_every_finding(tmp_path):
    result = _result(tmp_path, "above", (WEAK, STRONG))
    baseline = json.loads(scan_json(result))
    above_all = max(f["confidence"] for f in baseline["findings"]) + 1

    payload = json.loads(scan_json(result, confidence_floor=above_all))
    assert payload["confidence_floor"] == above_all
    assert len(payload["findings"]) == len(baseline["findings"]) == 2
    assert all(f["below_floor"] is True for f in payload["findings"])


def test_b4_a_zero_floor_flags_nothing(tmp_path):
    result = _result(tmp_path, "zero", (WEAK, STRONG))
    payload = json.loads(scan_json(result, confidence_floor=0))
    assert payload["confidence_floor"] == 0
    assert len(payload["findings"]) == 2
    assert all(f["below_floor"] is False for f in payload["findings"])


def test_b4_the_default_call_publishes_the_register_default(tmp_path):
    """`scan_json(result)` -- the call `cli.py` already makes -- keeps working."""
    result = _result(tmp_path, "default", (WEAK, STRONG))
    payload = json.loads(scan_json(result))
    assert payload["confidence_floor"] == CONFIDENCE_FLOOR_DEFAULT
    assert [f["below_floor"] for f in payload["findings"]] == [True, False]


def test_b4_the_explicit_default_and_the_implicit_one_are_byte_identical(tmp_path):
    result = _result(tmp_path, "same", (WEAK, STRONG))
    assert scan_json(result) == scan_json(
        result, confidence_floor=CONFIDENCE_FLOOR_DEFAULT)


def test_b4_the_boundary_is_strict_less_than(tmp_path):
    """A record AT the floor clears it. `<=` would silently disqualify the boundary."""
    result = _result(tmp_path, "boundary", (WEAK, STRONG))
    at_the_weak_value = json.loads(scan_json(result))["findings"][0]["confidence"]
    payload = json.loads(scan_json(result, confidence_floor=at_the_weak_value))
    by_id = {f["gap_id"]: f["below_floor"] for f in payload["findings"]}
    assert by_id["GAP-500"] is False, "a record whose confidence EQUALS the floor is in"


# ---------------------------------------------------------------------------
# Behavior 5 -- one floor story across the two surfaces.
# ---------------------------------------------------------------------------

_REFUSAL = re.compile(
    r"^Error: no PRESENT finding clears the confidence floor (\d+): ")


def test_b5_the_prd_refusal_names_the_same_integer_the_json_publishes(
        tmp_path, target, capsys):
    reg = _reg(tmp_path, "weakonly", [WEAK])

    assert main(["scan", str(target), "--gaps", str(reg), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["PRESENT"] == 1, (
        "premise: a PRESENT finding exists, so this is the FLOOR refusal path and not "
        "the no-PRESENT-finding one")
    assert payload["findings"][0]["below_floor"] is True

    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == "", "a refusal must not emit a PRD for a build loop to run"
    match = _REFUSAL.match(captured.err)
    assert match, f"unexpected refusal message: {captured.err!r}"
    assert int(match.group(1)) == payload["confidence_floor"]


def test_b5_the_refusal_is_not_the_no_present_finding_message(tmp_path, target, capsys):
    """Arming: exit 2 alone cannot tell the floor refusal from the empty-scan one."""
    reg = _reg(tmp_path, "weakonly", [WEAK])
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 2
    err = capsys.readouterr().err
    assert "no PRESENT finding to build against" not in err
    assert "confidence floor" in err


def test_b5_a_register_that_clears_the_floor_reaches_no_refusal(tmp_path, target, capsys):
    """The other side of behavior 5: the shared floor does not refuse everything."""
    reg = _reg(tmp_path, "strongonly", [STRONG])
    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["sourceGap"]["id"] == "GAP-501"
    assert "confidence floor" not in captured.err


# ---------------------------------------------------------------------------
# Behavior 6 -- the human surface and the quality bar are untouched.
# ---------------------------------------------------------------------------

def test_b6_the_markdown_surface_mentions_neither_new_key(tmp_path, target, capsys):
    reg = _reg(tmp_path, "md", [WEAK, STRONG])
    rc = main(["scan", str(target), "--gaps", str(reg)])
    captured = capsys.readouterr()
    assert rc == 0 and captured.err == ""
    assert "confidence_floor" not in captured.out
    assert "below_floor" not in captured.out
    # Anti-vacuity: an empty report would satisfy the two clauses above trivially.
    assert "GAP-500" in captured.out and "GAP-501" in captured.out
    assert "evidence confidence 1" in captured.out, "the human surface lost confidence"


def test_b6_scan_json_is_byte_stable_across_calls(tmp_path):
    result = _result(tmp_path, "stable", (WEAK, STRONG))
    first = scan_json(result)
    assert scan_json(result) == first


def test_b6_scan_json_ends_in_exactly_one_newline(tmp_path):
    result = _result(tmp_path, "newline", (WEAK, STRONG))
    doc = scan_json(result)
    assert doc.endswith("\n") and not doc.endswith("\n\n")


@pytest.mark.parametrize("argv_extra", [[], ["--json"]])
def test_b6_stdout_carries_only_the_document(argv_extra, tmp_path, target, capsys):
    reg = _reg(tmp_path, "onlydoc", [WEAK, STRONG])
    assert main(["scan", str(target), "--gaps", str(reg), *argv_extra]) == 0
    out = capsys.readouterr().out
    assert "Error:" not in out and "Note:" not in out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b6_the_two_surfaces_stay_separate(tmp_path, target, capsys):
    """The JSON gained the axis; the markdown did not. Measured in one test."""
    reg_md = _reg(tmp_path, "sep_md", [WEAK, STRONG])
    assert main(["scan", str(target), "--gaps", str(reg_md)]) == 0
    md = capsys.readouterr().out
    reg_js = _reg(tmp_path, "sep_js", [WEAK, STRONG])
    assert main(["scan", str(target), "--gaps", str(reg_js), "--json"]) == 0
    js = capsys.readouterr().out
    assert "below_floor" in js and "below_floor" not in md


# ---------------------------------------------------------------------------
# Behavior 7 -- the contract documents every key the tool emits.
#
# Asserted ONE-directionally: the emitted keys are a subset of the paragraph's
# backticked tokens. The reverse is deliberately not asserted, because the paragraph
# legitimately backticks `score` while stating that no such key exists.
# ---------------------------------------------------------------------------

def _contract_paragraph(text=None):
    """The single `scan --json` paragraph of the consumer contract."""
    text = CONTRACT_DOC.read_text(encoding="utf-8") if text is None else text
    blocks = [b for b in text.split("\n\n") if b.lstrip().startswith(MARKER_SENTENCE)]
    assert len(blocks) == 1, (
        f"expected exactly one paragraph opening {MARKER_SENTENCE!r}, found "
        f"{len(blocks)}")
    return blocks[0]


def _backticked(paragraph):
    """Tokens a reader can grep. A token wrapped across a line break is not one."""
    return set(re.findall(r"`([^`\n]+)`", paragraph))


def _emitted_keys(tmp_path):
    """Every key `scan_json` actually emits, top level and per finding."""
    payload = json.loads(scan_json(_result(tmp_path, "keys", (WEAK, STRONG))))
    keys = set(payload.keys())
    for finding in payload["findings"]:
        keys |= set(finding.keys())
    return keys


def test_b7_every_emitted_key_is_documented_in_the_contract_paragraph(tmp_path):
    emitted = _emitted_keys(tmp_path)
    assert len(emitted) == len(TOP_KEYS) + len(FINDING_KEYS), (
        "premise: the payload's two key sets are disjoint, so the census is complete")
    documented = _backticked(_contract_paragraph())
    missing = sorted(k for k in emitted if k not in documented)
    assert missing == [], f"emitted by the tool and absent from the contract: {missing}"


def test_b7_the_documentation_check_is_armed_for_every_key(tmp_path):
    """Delete one key's backticks at a time; each deletion must be REPORTED.

    A one-directional subset check passes trivially over a paragraph that happens to
    contain every token, so the value of the check rests entirely on it being able to
    fail. Each mutation asserts its own premise, so a no-op replace cannot turn a
    known-bad fixture into a copy of the known-good one.
    """
    emitted = _emitted_keys(tmp_path)
    paragraph = _contract_paragraph()
    for key in sorted(emitted):
        mutated = paragraph.replace("`" + key + "`", key)
        assert mutated != paragraph, f"premise: {key} is backticked in the paragraph"
        missing = sorted(k for k in emitted if k not in _backticked(mutated))
        assert key in missing, f"un-backticking {key} was not reported as missing"


def test_b7_the_contract_paragraph_appears_exactly_once(tmp_path):
    """A pasted duplicate would let a stale copy answer for the live one."""
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert text.count(MARKER_SENTENCE) == 1
    _contract_paragraph(text)


def test_b7_the_paragraph_states_the_obligation_not_a_claim_about_a_test(tmp_path):
    """The doc must impose the rule; the enforcing check lives in this file."""
    paragraph = _contract_paragraph()
    assert "Every key the tool emits must appear in this list" in paragraph
