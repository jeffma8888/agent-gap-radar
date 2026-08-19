"""Iteration 19 behaviors: `radar scan` states how many register records it applied.

The feature under test: a scan over a moved, emptied or one-level-too-high register used
to print an all-zero verdict census and exit 0, which is indistinguishable from "this
target exhibits none of the register's gaps". Both published surfaces now state the
denominator -- how many register records the scan actually applied -- and the markdown
brief says outright that a zero census is vacuous.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, the engineer's notes,
the reviewer's notes, or any diff. Every assertion either drives `agent_gap_radar.cli.main`
and observes only the exit code, the stdout bytes and the stderr bytes, calls the public
`scan` / `scan_json` API, or reads a PUBLISHED document (`docs/CONSUMER_CONTRACT.md`).

WHERE THE ORACLES COME FROM
* The count's expected value is never a bare literal: it is either arithmetic on integers
  the payload itself published (`sum(counts.values()) + len(uncheckable)`) or the size of a
  register this file built in `tmp_path`. So the register's real size, which an unattended
  research pass changes, cannot make a keyed expectation go red over a CORRECT register.
* `VACUITY_LINE` is the spec's verbatim sentence. It was extracted from the spec file
  mechanically at authoring time, not retyped, because a single missing space would
  satisfy a human reading and silently weaken the assertion.
* Two-sidedness is asserted for every claim of ABSENCE. `VACUITY_LINE not in doc` over a
  populated register proves nothing unless the same line is proven PRESENT over an empty
  one in the same test, and every "counts stayed clean" clause is paired with an
  anti-vacuity assertion that the document was not simply empty.

Nothing under `gaps/` is read to make an assertion true, no id census is taken over it,
and no network is touched. Registers and targets are built in `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import scan, scan_json
from test_iter02_behavior import _record, _target, _write_register

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The paragraph of the consumer contract that specifies the machine surface (behavior 6).
MARKER_SENTENCE = "**`scan --json` SHIPPED.**"

COUNT_PREFIX = "Register records applied: "
NO_CHECK_PREFIX = "Gaps with no check yet: "
TABLE_HEADER = "| Verdict | Count | Meaning |"

#: Spec behavior 3, verbatim.
VACUITY_LINE = "**No records were applied, so this scan verdicted nothing.** An all-zero census is vacuous here, not a clean target: check the register path."

#: Spec behavior 4: the ORDER is the contract, not merely the key set.
TOP_KEYS = ["target", "target_name", "confidence_floor", "records_applied",
            "counts", "uncheckable", "findings"]

#: Three records that carry a check (they become findings) and two that do not (they
#: become `uncheckable`), so `records_applied` must be 5 while `len(findings)` is 3.
CHECKED = tuple(_record("GAP-19%d" % i, 4, 3, 3, classes=("first-party-field",),
                        check_id="CHK-19%d" % i) for i in range(3))
UNCHECKED = tuple(_record("GAP-18%d" % i, 4, 3, 3, classes=("first-party-field",))
                  for i in range(2))
POPULATED = CHECKED + UNCHECKED
EXPECTED_APPLIED = len(POPULATED)


# ---------------------------------------------------------------------------
# Fixture builders. `_record`, `_write_register` and `_target` come from
# tests/test_iter02_behavior.py; a plain tmp_path target is not a git repo, so those
# builders' walk is what makes the fixture checks fire at all.
# ---------------------------------------------------------------------------

def _register(root, records):
    """A register directory holding `records`; an empty tuple means an EMPTY register."""
    if records:
        return _write_register(root, list(records))
    d = root / "gaps"
    d.mkdir(parents=True)
    return d


def _fixture(tmp_path, name, records):
    """(register dir, target dir) under a private subdirectory of tmp_path."""
    root = tmp_path / name
    return _register(root, records), _target(root)


def _cli(tmp_path, capsys, name, records, extra=()):
    """Run `radar scan` through the CLI. Returns (rc, stdout, stderr)."""
    reg, target = _fixture(tmp_path, name, records)
    rc = main(["scan", str(target), "--gaps", str(reg), *extra])
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _api_result(tmp_path, name, records):
    reg, target = _fixture(tmp_path, name, records)
    return scan(load_all(reg), target)


# ---------------------------------------------------------------------------
# Document readers. Positions are MEASURED off the emitted lines; a claim about a
# document's content is never read off a rendered diff.
# ---------------------------------------------------------------------------

def _sole_index(lines, predicate, what):
    hits = [i for i, line in enumerate(lines) if predicate(line)]
    assert len(hits) == 1, "expected exactly one %s line, found %r" % (what, hits)
    return hits[0]


def _count_index(lines):
    return _sole_index(lines, lambda l: l.startswith(COUNT_PREFIX), COUNT_PREFIX)


def _no_check_index(lines):
    return _sole_index(lines, lambda l: l.startswith(NO_CHECK_PREFIX), NO_CHECK_PREFIX)


def _count_value(doc):
    lines = doc.split("\n")
    return int(lines[_count_index(lines)][len(COUNT_PREFIX):])


def _table_last_row(lines):
    """Index of the final row of the verdict table (its contiguous run of pipe lines)."""
    i = _sole_index(lines, lambda l: l == TABLE_HEADER, "verdict table header")
    while i + 1 < len(lines) and lines[i + 1].startswith("|"):
        i += 1
    return i


# ---------------------------------------------------------------------------
# Behavior 1 -- ScanResult.records_applied is derived from the two collections,
# and read-only.
# ---------------------------------------------------------------------------

def test_b1_three_findings_and_two_uncheckable_report_five(tmp_path):
    result = _api_result(tmp_path, "b1_five", POPULATED)
    assert len(result.findings) == 3, "premise: the checked records produced findings"
    assert len(result.uncheckable) == 2, "premise: the uncheckable records were kept"
    assert result.records_applied == 5


def test_b1_an_empty_register_reports_zero(tmp_path):
    result = _api_result(tmp_path, "b1_zero", ())
    assert (result.findings, list(result.uncheckable)) == ([], [])
    assert result.records_applied == 0


def test_b1_the_number_is_derived_and_cannot_disagree_with_its_collections(tmp_path):
    """Shrink each collection in turn; a STORED field would keep answering 5."""
    result = _api_result(tmp_path, "b1_derived", POPULATED)
    assert result.records_applied == len(result.findings) + len(result.uncheckable)

    result.findings = result.findings[:1]
    assert result.records_applied == 3, "the count ignored a change to `findings`"
    result.uncheckable = list(result.uncheckable)[:1]
    assert result.records_applied == 2, "the count ignored a change to `uncheckable`"
    result.findings = []
    result.uncheckable = []
    assert result.records_applied == 0


def test_b1_records_applied_is_read_only(tmp_path):
    """A settable count is a second source of the number, which behavior 1 forbids."""
    result = _api_result(tmp_path, "b1_ro", POPULATED)
    with pytest.raises(AttributeError):
        result.records_applied = 99
    assert result.records_applied == EXPECTED_APPLIED


# ---------------------------------------------------------------------------
# Behavior 2 -- one new line, in a pinned position, on the markdown brief.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("records,expected", [(POPULATED, EXPECTED_APPLIED), ((), 0)])
def test_b2_the_brief_states_the_count_once_and_correctly(
        records, expected, tmp_path, capsys):
    rc, out, err = _cli(tmp_path, capsys, "b2_once%d" % expected, records)
    assert (rc, err) == (0, "")
    assert _count_value(out) == expected


def test_b2_the_count_line_sits_immediately_before_the_no_check_line(tmp_path, capsys):
    _, out, _ = _cli(tmp_path, capsys, "b2_before", POPULATED)
    lines = out.split("\n")
    assert _count_index(lines) + 1 == _no_check_index(lines)


def test_b2_the_count_line_follows_the_verdict_tables_trailing_blank_line(
        tmp_path, capsys):
    _, out, _ = _cli(tmp_path, capsys, "b2_table", POPULATED)
    lines = out.split("\n")
    last_row = _table_last_row(lines)
    assert lines[last_row + 1] == "", "the table lost its trailing blank line"
    assert _count_index(lines) == last_row + 2


def test_b2_the_no_check_line_keeps_its_wording_and_stays_after_the_table(
        tmp_path, capsys):
    """Its offset from the table necessarily grows by one; its wording and order do not."""
    _, out, _ = _cli(tmp_path, capsys, "b2_nocheck", POPULATED)
    lines = out.split("\n")
    idx = _no_check_index(lines)
    assert lines[idx] == NO_CHECK_PREFIX + str(len(UNCHECKED)), (
        "premise + wording: the fixture's uncheckable records are the ones counted")
    assert idx > _table_last_row(lines)


def test_b2_the_position_oracles_are_armed_against_the_pre_change_shape(
        tmp_path, capsys):
    """Reconstruct the document as it was BEFORE this iteration and re-run the oracles.

    Every position assertion above is worthless unless it can fail, and a black-box test
    cannot execute the old tree. Deleting the count line from a REAL brief is the closest
    available known-bad sample: the count oracle must refuse it, the no-check line must
    move back to the table's blank line + 1, and a synthetic value must be read rather
    than defaulted.
    """
    _, out, _ = _cli(tmp_path, capsys, "b2_armed", POPULATED)
    lines = out.split("\n")
    assert _count_index(lines) == _table_last_row(lines) + 2, "premise: the line is there"

    pre_change = [l for l in lines if not l.startswith(COUNT_PREFIX)]
    with pytest.raises(AssertionError):
        _count_index(pre_change)
    assert _no_check_index(pre_change) == _table_last_row(pre_change) + 2, (
        "premise: removing one line is exactly what moved the no-check line")

    doubled = lines[:1] + [COUNT_PREFIX + "7"] + lines
    with pytest.raises(AssertionError):
        _count_index(doubled), "a duplicated count line must not pass as one"
    assert _count_value("\n".join([COUNT_PREFIX + "7"])) == 7, (
        "the value oracle defaulted instead of reading the emitted integer")


# ---------------------------------------------------------------------------
# Behavior 3 -- the empty-register statement, asserted in BOTH directions.
# ---------------------------------------------------------------------------

def test_b3_the_vacuity_statement_is_two_sided(tmp_path, capsys):
    """One test, both directions: a warning that is really a constant fails here."""
    _, empty_doc, _ = _cli(tmp_path, capsys, "b3_empty", ())
    _, populated_doc, _ = _cli(tmp_path, capsys, "b3_pop", POPULATED)

    assert empty_doc.count(VACUITY_LINE) == 1
    assert VACUITY_LINE not in populated_doc
    # Anti-vacuity: the populated document is a real brief, not an empty string.
    assert _count_value(populated_doc) == EXPECTED_APPLIED
    assert "GAP-190" in populated_doc


def test_b3_the_empty_brief_reports_zero_and_states_the_vacuity_verbatim(
        tmp_path, capsys):
    rc, out, err = _cli(tmp_path, capsys, "b3_verbatim", ())
    assert (rc, err) == (0, "")
    lines = out.split("\n")
    assert lines[_count_index(lines)] == COUNT_PREFIX + "0"
    assert lines[_no_check_index(lines)] == NO_CHECK_PREFIX + "0"
    assert lines[_no_check_index(lines) + 1] == VACUITY_LINE


def test_b3_the_vacuity_line_does_not_name_a_register_path(tmp_path, capsys):
    """Out of scope by name: `scan()` receives records, so it cannot claim a path."""
    reg, target = _fixture(tmp_path, "b3_path", ())
    assert main(["scan", str(target), "--gaps", str(reg)]) == 0
    out = capsys.readouterr().out
    assert VACUITY_LINE in out
    assert str(reg) not in VACUITY_LINE


# ---------------------------------------------------------------------------
# Behavior 4 -- the machine surface publishes the count, in the pinned key order.
# ---------------------------------------------------------------------------

def test_b4_the_top_level_key_order_is_the_contract(tmp_path, capsys):
    _, out, err = _cli(tmp_path, capsys, "b4_order", POPULATED, extra=("--json",))
    assert err == ""
    assert list(json.loads(out).keys()) == TOP_KEYS


def test_b4_the_published_count_equals_the_results_own_number(tmp_path):
    result = _api_result(tmp_path, "b4_equal", POPULATED)
    payload = json.loads(scan_json(result))
    assert payload["records_applied"] == result.records_applied == EXPECTED_APPLIED


def test_b4_the_count_is_a_plain_integer(tmp_path):
    """A bool or a stringified count would break `records_applied == 0` on a gate."""
    payload = json.loads(scan_json(_api_result(tmp_path, "b4_int", ())))
    assert isinstance(payload["records_applied"], int)
    assert not isinstance(payload["records_applied"], bool)


def test_b4_counts_stays_a_pure_verdict_census(tmp_path):
    """Asserted on the RAW text too: a dict-level check cannot see a nested duplicate."""
    raw = scan_json(_api_result(tmp_path, "b4_counts", POPULATED))
    payload = json.loads(raw)
    assert set(payload["counts"]) == {"PRESENT", "ABSENT", "NOT_APPLICABLE",
                                      "MANUAL", "UNKNOWN"}
    assert raw.count('"records_applied"') == 1
    start = raw.index('"counts"')
    block = raw[start:raw.index("}", start)]
    assert "records_applied" not in block, "the count was smuggled into `counts`"


# ---------------------------------------------------------------------------
# Behavior 5 -- the two surfaces and the two collections agree, at BOTH sizes.
# ---------------------------------------------------------------------------

def test_b5_both_surfaces_agree_with_the_arithmetic_at_both_register_sizes(
        tmp_path, capsys):
    observed = []
    for name, records in (("b5_empty", ()), ("b5_pop", POPULATED)):
        _, js, err_j = _cli(tmp_path, capsys, name + "_j", records, extra=("--json",))
        payload = json.loads(js)
        derived = sum(payload["counts"].values()) + len(payload["uncheckable"])
        assert payload["records_applied"] == derived, (
            "%s: published %r but counts+uncheckable imply %r"
            % (name, payload["records_applied"], derived))

        _, md, err_m = _cli(tmp_path, capsys, name + "_m", records)
        assert _count_value(md) == payload["records_applied"], (
            "%s: the brief and the JSON disagree" % name)
        assert (err_j, err_m) == ("", "")
        observed.append(payload["records_applied"])

    assert len(observed) == 2, "the sweep did not run over both register sizes"
    assert 0 in observed, "the sweep never saw an EMPTY register"
    assert any(v > 0 for v in observed), (
        "the sweep never saw a POPULATED register, so it proved nothing")


# ---------------------------------------------------------------------------
# Behavior 6 -- the consumer contract names every key the tool emits.
# ---------------------------------------------------------------------------

def _contract_paragraph():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    blocks = [b for b in text.split("\n\n") if b.lstrip().startswith(MARKER_SENTENCE)]
    assert len(blocks) == 1, "expected exactly one `scan --json` paragraph"
    return blocks[0]


def _backticked(paragraph):
    import re
    return set(re.findall(r"`([^`\n]+)`", paragraph))


def test_b6_the_contract_paragraph_names_records_applied(tmp_path, capsys):
    _, out, _ = _cli(tmp_path, capsys, "b6_named", POPULATED, extra=("--json",))
    emitted = set(json.loads(out).keys())
    assert "records_applied" in emitted, "premise: the tool emits the key"
    documented = _backticked(_contract_paragraph())
    missing = sorted(k for k in emitted if k not in documented)
    assert missing == [], "emitted by the tool and absent from the contract: %r" % missing


def test_b6_the_documentation_census_is_armed(tmp_path, capsys):
    """Un-backtick the new key; the census must REPORT it, or it proves nothing."""
    _, out, _ = _cli(tmp_path, capsys, "b6_armed", POPULATED, extra=("--json",))
    emitted = set(json.loads(out).keys())
    paragraph = _contract_paragraph()
    mutated = paragraph.replace("`records_applied`", "records_applied")
    assert mutated != paragraph, "premise: records_applied is backticked"
    missing = sorted(k for k in emitted if k not in _backticked(mutated))
    assert "records_applied" in missing


# ---------------------------------------------------------------------------
# Behavior 7 -- exit codes do not move. Row 25's decision is not taken here.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_b7_an_empty_register_still_exits_zero(extra, tmp_path, capsys):
    rc, out, err = _cli(tmp_path, capsys, "b7_empty%d" % len(extra), (), extra=extra)
    assert rc == 0
    assert err == "", "the success path must not narrate on stderr"
    assert "Error:" not in out


@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_b7_a_populated_register_still_exits_zero(extra, tmp_path, capsys):
    rc, _, err = _cli(tmp_path, capsys, "b7_pop%d" % len(extra), POPULATED, extra=extra)
    assert (rc, err) == (0, "")


# ---------------------------------------------------------------------------
# Behavior 8 -- non-regression on the sibling flag.
# ---------------------------------------------------------------------------

PRD_REFUSAL = ("Error: no PRESENT finding to build against; "
               "run without --prd to see MANUAL questions\n")


def test_b8_prd_over_an_empty_register_still_refuses_with_exit_two(tmp_path, capsys):
    reg, target = _fixture(tmp_path, "b8_prd", ())
    rc = main(["scan", str(target), "--gaps", str(reg), "--prd"])
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.out == "", "a refusal must not emit a PRD for a build loop to run"
    assert captured.err.startswith("Error: ")
    assert captured.err == PRD_REFUSAL
    assert list(tmp_path.rglob("prd.json")) == [], "a refusal wrote a prd.json anyway"


def test_b8_the_refusal_is_not_the_new_vacuity_statement(tmp_path, capsys):
    """The brief warns; the machine path still refuses in its own words."""
    reg, target = _fixture(tmp_path, "b8_words", ())
    assert main(["scan", str(target), "--gaps", str(reg), "--prd"]) == 2
    err = capsys.readouterr().err
    assert VACUITY_LINE not in err
    assert COUNT_PREFIX not in err


# ---------------------------------------------------------------------------
# Behavior 9 -- both surfaces stay byte-stable and end in exactly one newline.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("records", [POPULATED, ()])
@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_b9_two_runs_over_one_fixture_are_byte_identical(
        records, extra, tmp_path, capsys):
    reg, target = _fixture(tmp_path, "b9", records)
    argv = ["scan", str(target), "--gaps", str(reg), *extra]

    assert main(argv) == 0
    first = capsys.readouterr()
    assert main(argv) == 0
    second = capsys.readouterr()

    assert first.out == second.out
    assert (first.err, second.err) == ("", "")
    assert first.out.endswith("\n") and not first.out.endswith("\n\n")
    assert first.out.strip() != "", "anti-vacuity: byte-stable emptiness is not stability"
