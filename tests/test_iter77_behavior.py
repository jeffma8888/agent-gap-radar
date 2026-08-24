"""Iteration 77 behaviors: `radar diff OLD NEW --json` answers a machine consumer.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every assertion drives the
public interface (`cli.main` in-process, and the installed `main()` across a real process
boundary) and observes only stdout bytes, stderr bytes, exit codes, and the two published
module attributes the spec itself names (`diff.COMPARED_FIELDS`, `scoring.priority` /
`scoring.confidence`).

Three deliberate design choices, each because the obvious version would be vacuous:

* **Asymmetric domains.** `counts` is exercised over an OLD of 2 and a NEW of 5. Over the
  equal-sized pair the rest of this file uses, an implementation that printed one number
  twice would satisfy every other assertion in the module.
* **A key walker with a planted positive control.** Behavior 6 forbids a `score` key at any
  depth. A recursive walker that returned an empty set would pass that for free, so the
  walker is first proven to FIND a planted `score` at three different depths (top level,
  inside an `added` member, inside a nested `change`) before its silence over the real
  payload is believed.
* **Filenames whose sort order is the REVERSE of the record order.** Behavior 3 pins element
  order against the markdown report; with `GAP-00N.json` names, directory order and record
  order coincide, so the order assertion would be true by accident.

The markdown report is used as the ORACLE for order and for change values rather than being
re-derived here, which is what makes the JSON and markdown surfaces provably the same answer
in two encodings. The nine compared fields are ALSO pinned as a literal in this file and then
asserted equal to the published `diff.COMPARED_FIELDS`, so a silent reorder of the published
tuple reds this suite instead of quietly re-pointing a consumer's field list.

What this file does NOT prove, stated so a green dot cannot be mistaken for it: it cannot
compare the markdown bytes against the bytes the PREVIOUS commit produced, because only one
tree is importable from inside the suite. Behavior 9's "unchanged" half is pinned here as
byte equality against a document RECONSTRUCTED from the published grammar (title, domain
line, three counted sections, member rows, nested rows), which reds if any part of that
grammar moves. The cross-commit byte equality was measured out of band in a temp clone of
HEAD and is reported in the tester report.

Nothing under `gaps/` is read to make an assertion true -- that register is grown by an
unattended research pass, so a keyed expectation over it would go red against a CORRECT
register. The one test that touches the live register asserts a SELF-diff reports nothing,
which stays true at any record count.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.diff import COMPARED_FIELDS as PUBLISHED_COMPARED_FIELDS
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import confidence, priority

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: What the installed console script does (`radar = agent_gap_radar.cli:main`). Spelled as
#: `-c` so the process boundary is exercised without depending on an installed entry point.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

# --- the key sequences behavior 2/3/4 pin -----------------------------------

TOP_LEVEL_KEYS = ["counts", "added", "removed", "changed"]
COUNTS_KEYS = ["old", "new"]
MEMBER_KEYS = ["gap_id", "title"]
CHANGED_KEYS = ["gap_id", "changes"]
CHANGE_KEYS = ["field", "old", "new"]

#: Behavior 5 fixes membership AND order. Pinned as a literal here, then asserted equal to
#: the published tuple, so a reorder of either side reds rather than silently re-pointing a
#: consumer's field list.
COMPARED_FIELDS = ("status", "layer", "gap_type", "severity", "frequency",
                   "tractability", "priority", "confidence", "citations")

#: The forbidden key of behavior 6, by name.
BLENDED_KEY = "score"

# --- the markdown grammar the JSON must agree with (behavior 3, 5, 9) -------

TITLE = "# Register diff"
EMPTY_BODY = "None."
SECTION_ORDER = ("Added", "Removed", "Changed")
HEADING = re.compile(r"^## (?P<name>[A-Za-z]+) \((?P<count>\d+)\)$")
MEMBER_ROW = re.compile(r"^- (?P<id>GAP-\d+)  (?P<title>\S.*)$")
CHANGED_ROW = re.compile(r"^- (?P<id>GAP-\d+)$")
NESTED_ROW = re.compile(r"^  - (?P<field>[a-z_]+): (?P<old>.+) -> (?P<new>.+)$")

ERROR_PREFIX = "Error: "

EVIDENCE = {
    "source_class": "first-party-field",
    "title": "an incident write-up",
    "locator": "https://example.invalid/inc",
    "date": "2026-01-02",
    "quote": "the verbatim line",
}


# ---------------------------------------------------------------------------
# fixtures -- registers are materialised on disk, records are plain data
# ---------------------------------------------------------------------------

def _evidence(*classes: str) -> list[dict]:
    return [{**EVIDENCE, "source_class": cls, "title": f"source {cls}"} for cls in classes]


def _record(gid: str, **over) -> dict:
    record = {
        "id": gid, "title": f"the {gid} problem", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": _evidence("first-party-field"),
    }
    record.update(over)
    return record


def _register(root: pathlib.Path, records, *, reverse_names: bool = False) -> pathlib.Path:
    """Materialise `<root>/gaps/` and return `root`. `reverse_names` touches FILENAMES only."""
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    total = len(records)
    for index, record in enumerate(records):
        name = f"{total - index:03d}-record.json" if reverse_names else f"{record['id']}.json"
        (gaps / name).write_text(json.dumps(record), encoding="utf-8")
    return root


def _pair(tmp_path, old_records, new_records, *, reverse_names: bool = False):
    return (_register(tmp_path / "old", old_records, reverse_names=reverse_names),
            _register(tmp_path / "new", new_records, reverse_names=reverse_names))


def _rich_pair(tmp_path, *, reverse_names: bool = False):
    """Two records in each of the three sections, plus one record that never changes."""
    unchanged = _record("GAP-001")
    old_records = [unchanged, _all_fields_old(), _record("GAP-005"), _record("GAP-006")]
    new_records = [unchanged, _all_fields_new(), _record("GAP-004"), _record("GAP-007")]
    return _pair(tmp_path, old_records, new_records, reverse_names=reverse_names)


def _all_fields_old() -> dict:
    return _record("GAP-002", severity=2, frequency=2, tractability=2,
                   evidence=_evidence("secondary-summary"))


def _all_fields_new() -> dict:
    return _record("GAP-002", status="addressed", layer="multi-agent",
                   gap_type="silent-failure", severity=5, frequency=4, tractability=3,
                   evidence=_evidence("first-party-field", "peer-reviewed"))


def _all_fields_pair(tmp_path):
    """A pair whose one shared record differs on every one of the nine compared fields."""
    return _pair(tmp_path, [_all_fields_old()], [_all_fields_new()])


def _partial_pair(tmp_path):
    """A pair whose one shared record differs on SOME compared fields only.

    `severity` moves, which also moves the derived `priority`; `layer`, `gap_type`,
    `frequency`, `tractability`, `status`, `confidence` and `citations` are held fixed.
    """
    return _pair(tmp_path,
                 [_record("GAP-003", severity=2)],
                 [_record("GAP-003", severity=5)])


def _one(root: pathlib.Path, gid: str):
    """One loaded record, via the public loader -- the oracle for derived values."""
    matched = [gap for gap in load_all(root / "gaps") if gap.id == gid]
    assert len(matched) == 1, f"{gid} is not uniquely present under {root.name}/gaps"
    return matched[0]


# ---------------------------------------------------------------------------
# drivers -- run the product, parse only what it publishes
# ---------------------------------------------------------------------------

def _payload(capsys, old, new) -> dict:
    """`diff --json` through `main()`: exit 0, clean stderr, one trailing newline, an object."""
    assert main(["diff", str(old), str(new), "--json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    out = captured.out
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-4:])
    payload = json.loads(out)
    assert isinstance(payload, dict), type(payload).__name__
    return payload


def _markdown(capsys, old, new) -> str:
    assert main(["diff", str(old), str(new)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    document = captured.out
    assert document.splitlines()[0] == TITLE, document[:80]
    assert document.endswith("\n") and not document.endswith("\n\n"), repr(document[-4:])
    return document


def _run(*argv: str, cwd: pathlib.Path | None = None):
    return subprocess.run([sys.executable, "-c", BOOT, *argv],
                          cwd=str(cwd or REPO_ROOT), capture_output=True, timeout=180)


def _sections(document: str) -> dict[str, list[str]]:
    """name -> its non-blank body lines, in document order."""
    sections: dict[str, list[str]] = {}
    name: str | None = None
    for line in document.splitlines():
        if line.startswith("## "):
            match = HEADING.match(line)
            assert match, f"heading {line!r} is not `## <Name> (<n>)`"
            name = match["name"]
            assert name not in sections, f"a heading is rendered twice ({name})"
            sections[name] = []
        elif name is not None and line.strip():
            sections[name].append(line)
    return sections


def _markdown_member_ids(document: str, section: str) -> list[str]:
    body = _sections(document)[section]
    if body == [EMPTY_BODY]:
        return []
    ids = []
    for line in body:
        match = MEMBER_ROW.match(line)
        assert match, f"{section} body line {line!r} is not `- GAP-0NN  <title>`"
        ids.append(match["id"])
    return ids


def _markdown_changed(document: str) -> dict[str, list[tuple[str, str, str]]]:
    """id -> [(field, old, new)], in document order."""
    body = _sections(document)["Changed"]
    if body == [EMPTY_BODY]:
        return {}
    blocks: dict[str, list[tuple[str, str, str]]] = {}
    current: str | None = None
    for line in body:
        head = CHANGED_ROW.match(line)
        if head:
            current = head["id"]
            assert current not in blocks, f"{current} is listed twice under Changed"
            blocks[current] = []
            continue
        nested = NESTED_ROW.match(line)
        assert nested, f"Changed body line {line!r} is not `  - <field>: <old> -> <new>`"
        assert current is not None, f"nested line {line!r} precedes any record line"
        blocks[current].append((nested["field"], nested["old"], nested["new"]))
    return blocks


def _walk_keys(node) -> list[str]:
    """Every mapping key at every depth, so behavior 6 can be asserted BY NAME."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            found.append(key)
            found.extend(_walk_keys(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_keys(item))
    return found


def _field_values(gap) -> dict[str, object]:
    """Every compared field, with the two derived ones CALLED, never re-derived here."""
    return {
        "status": gap.status,
        "layer": gap.layer,
        "gap_type": gap.gap_type,
        "severity": gap.severity,
        "frequency": gap.frequency,
        "tractability": gap.tractability,
        "priority": priority(gap),
        "confidence": confidence(gap),
        "citations": len(gap.evidence),
    }


# ---------------------------------------------------------------------------
# behavior 0 -- the published field tuple this file is written against
# ---------------------------------------------------------------------------

def test_the_pinned_field_tuple_equals_the_published_one():
    """Both membership and ORDER. Either side moving reds here, not at a consumer."""
    assert tuple(PUBLISHED_COMPARED_FIELDS) == COMPARED_FIELDS
    assert len(COMPARED_FIELDS) == 9


# ---------------------------------------------------------------------------
# behavior 1 -- a JSON object on stdout, exit 0
# ---------------------------------------------------------------------------

def test_the_key_sequence_comparison_is_order_sensitive():
    """Armed control for every `list(obj) == KEYS` assertion below.

    Mutation-verified rather than assumed: a reordered mapping has the same key SET, so
    without this control a set-comparison typo in any sequence test would read as a passing
    order assertion. This is the cheapest form of the discipline -- plant the defect the
    assertion exists to catch and confirm the assertion notices.
    """
    reordered = {"new": 1, "old": 2}
    assert set(reordered) == set(COUNTS_KEYS)
    assert list(reordered) != COUNTS_KEYS
    swapped = {"title": "t", "gap_id": "GAP-001"}
    assert set(swapped) == set(MEMBER_KEYS)
    assert list(swapped) != MEMBER_KEYS


def test_b1_json_document_parses_as_an_object_and_exits_zero(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    assert set(payload) == set(TOP_LEVEL_KEYS)


def test_b1_stdout_carries_only_the_document(tmp_path):
    """Across a real process boundary: stdout is parseable JSON with nothing prepended."""
    old, new = _rich_pair(tmp_path)
    proc = _run("diff", str(old), str(new), "--json")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert proc.stderr == b"", proc.stderr.decode("utf-8", "replace")
    text = proc.stdout.decode("utf-8")
    assert json.loads(text)
    assert text.startswith("{"), repr(text[:40])


# ---------------------------------------------------------------------------
# behavior 2 -- the top-level key SEQUENCE, and both domain sizes
# ---------------------------------------------------------------------------

def test_b2_top_level_key_sequence_is_exact(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    assert list(payload) == TOP_LEVEL_KEYS


def test_b2_counts_key_sequence_is_old_then_new(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    assert isinstance(payload["counts"], dict)
    assert list(payload["counts"]) == COUNTS_KEYS


def test_b2_counts_are_both_domain_sizes_over_asymmetric_domains(capsys, tmp_path):
    """ASYMMETRIC on purpose: over an equal pair, one number printed twice would pass."""
    old_records = [_record("GAP-001"), _record("GAP-002")]
    new_records = [_record(f"GAP-0{index:02d}") for index in range(1, 6)]
    old, new = _pair(tmp_path, old_records, new_records)
    payload = _payload(capsys, old, new)
    assert payload["counts"] == {"old": 2, "new": 5}
    assert payload["counts"]["old"] != payload["counts"]["new"]


def test_b2_counts_agree_with_the_markdown_domain_line(capsys, tmp_path):
    old, new = _pair(tmp_path, [_record("GAP-001")],
                     [_record("GAP-001"), _record("GAP-002"), _record("GAP-003")])
    payload = _payload(capsys, old, new)
    document = _markdown(capsys, old, new)
    stated = f"Old: {payload['counts']['old']} record(s). "
    stated += f"New: {payload['counts']['new']} record(s)."
    assert stated in document.splitlines(), document


def test_b2_an_empty_old_register_reports_zero_rather_than_the_new_size(capsys, tmp_path):
    """The mis-levelled-OLD case the spec names: counts must not both read as the NEW size."""
    old, new = _pair(tmp_path, [], [_record("GAP-001"), _record("GAP-002")])
    payload = _payload(capsys, old, new)
    assert payload["counts"] == {"old": 0, "new": 2}
    assert [member["gap_id"] for member in payload["added"]] == ["GAP-001", "GAP-002"]


# ---------------------------------------------------------------------------
# behavior 3 -- added / removed are arrays of {gap_id, title}, in report order
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("section", ["added", "removed"])
def test_b3_member_element_key_sequence_is_exact(capsys, tmp_path, section):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    members = payload[section]
    assert isinstance(members, list)
    assert len(members) == 2, members  # anti-vacuity: an empty list pins nothing
    for member in members:
        assert list(member) == MEMBER_KEYS, member


@pytest.mark.parametrize(("section", "heading"), [("added", "Added"), ("removed", "Removed")])
def test_b3_member_order_matches_the_markdown_report(capsys, tmp_path, section, heading):
    """Filenames sort in the REVERSE of record order, so this cannot pass by accident."""
    old, new = _rich_pair(tmp_path, reverse_names=True)
    payload = _payload(capsys, old, new)
    document = _markdown(capsys, old, new)
    assert [member["gap_id"] for member in payload[section]] == \
        _markdown_member_ids(document, heading)


def test_b3_member_titles_are_the_records_own_titles(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    for member in payload["added"]:
        assert member["title"] == _one(new, member["gap_id"]).title
    for member in payload["removed"]:
        assert member["title"] == _one(old, member["gap_id"]).title


# ---------------------------------------------------------------------------
# behavior 4 -- changed elements and their nested change objects
# ---------------------------------------------------------------------------

def test_b4_changed_element_key_sequence_is_exact(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    assert isinstance(payload["changed"], list)
    assert len(payload["changed"]) == 1, payload["changed"]
    for element in payload["changed"]:
        assert list(element) == CHANGED_KEYS, element


def test_b4_change_object_key_sequence_is_exact_and_changes_are_non_empty(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    payload = _payload(capsys, old, new)
    element = payload["changed"][0]
    assert element["gap_id"] == "GAP-002"
    assert isinstance(element["changes"], list)
    assert element["changes"], "a changed record with an empty `changes` array says nothing"
    for change in element["changes"]:
        assert list(change) == CHANGE_KEYS, change


def test_b4_a_record_present_and_identical_on_both_sides_is_not_listed(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    listed = ([element["gap_id"] for element in payload["changed"]]
              + [member["gap_id"] for member in payload["added"]]
              + [member["gap_id"] for member in payload["removed"]])
    assert "GAP-001" not in listed, listed


def test_b4_changed_element_order_matches_the_markdown_report(capsys, tmp_path):
    """TWO changed records, because one cannot pin an order at all.

    Every other `changed` assertion in this file runs over a fixture with a single changed
    record, where any element order whatsoever satisfies them. Here two records change and
    the filenames sort in the REVERSE of record order, so the JSON element order is checked
    against the markdown report as the oracle rather than against directory listing order.
    """
    old, new = _pair(tmp_path,
                     [_record("GAP-002", severity=2), _record("GAP-003", frequency=2)],
                     [_record("GAP-002", severity=5), _record("GAP-003", frequency=5)],
                     reverse_names=True)
    payload = _payload(capsys, old, new)
    blocks = _markdown_changed(_markdown(capsys, old, new))
    ids = [element["gap_id"] for element in payload["changed"]]
    # Anti-vacuity: with fewer than two elements this test is about nothing.
    assert len(ids) == 2, ids
    assert payload["added"] == [] and payload["removed"] == []
    assert ids == list(blocks)
    for element in payload["changed"]:
        from_json = [(change["field"], str(change["old"]), str(change["new"]))
                     for change in element["changes"]]
        assert from_json == blocks[element["gap_id"]], element["gap_id"]


# ---------------------------------------------------------------------------
# behavior 5 -- only differing fields, in COMPARED_FIELDS order
# ---------------------------------------------------------------------------

def test_b5_all_nine_fields_appear_in_compared_fields_order(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    payload = _payload(capsys, old, new)
    fields = [change["field"] for change in payload["changed"][0]["changes"]]
    # Anti-vacuity: this fixture is the one that moves ALL nine, so if a later edit
    # weakens it the order assertion stops being about order at all.
    assert len(fields) == len(COMPARED_FIELDS), fields
    assert tuple(fields) == COMPARED_FIELDS


def test_b5_an_unchanged_compared_field_is_absent(capsys, tmp_path):
    old, new = _partial_pair(tmp_path)
    payload = _payload(capsys, old, new)
    fields = [change["field"] for change in payload["changed"][0]["changes"]]
    expected = [field for field in COMPARED_FIELDS
                if _field_values(_one(old, "GAP-003"))[field]
                != _field_values(_one(new, "GAP-003"))[field]]
    # Anti-vacuity in BOTH directions: some fields must move and some must not.
    assert 0 < len(expected) < len(COMPARED_FIELDS), expected
    assert fields == expected
    for absent in set(COMPARED_FIELDS) - set(expected):
        assert absent not in fields, absent


def test_b5_every_field_value_is_a_published_compared_field(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    fields = {change["field"] for element in payload["changed"]
              for change in element["changes"]}
    assert fields, "no change entries were emitted, so this asserts nothing"
    assert fields <= set(COMPARED_FIELDS), sorted(fields - set(COMPARED_FIELDS))


def test_b5_json_change_entries_agree_with_the_markdown_report(capsys, tmp_path):
    """One answer in two encodings: same fields, same order, same old/new values."""
    old, new = _all_fields_pair(tmp_path)
    payload = _payload(capsys, old, new)
    blocks = _markdown_changed(_markdown(capsys, old, new))
    assert list(blocks) == [element["gap_id"] for element in payload["changed"]]
    for element in payload["changed"]:
        from_json = [(change["field"], str(change["old"]), str(change["new"]))
                     for change in element["changes"]]
        assert from_json == blocks[element["gap_id"]]


def test_b5_derived_values_are_the_scoring_modules_own_answers(capsys, tmp_path):
    """`priority` and `confidence` are CALLED, not re-derived by the serializer."""
    old, new = _all_fields_pair(tmp_path)
    payload = _payload(capsys, old, new)
    reported = {change["field"]: change for change in payload["changed"][0]["changes"]}
    old_values = _field_values(_one(old, "GAP-002"))
    new_values = _field_values(_one(new, "GAP-002"))
    for field in ("priority", "confidence"):
        assert str(reported[field]["old"]) == str(old_values[field]), field
        assert str(reported[field]["new"]) == str(new_values[field]), field


# ---------------------------------------------------------------------------
# behavior 6 -- two distinct numbers, and no blended key anywhere
# ---------------------------------------------------------------------------

def test_b6_priority_and_confidence_are_two_distinct_entries(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    payload = _payload(capsys, old, new)
    fields = [change["field"] for change in payload["changed"][0]["changes"]]
    assert fields.count("priority") == 1, fields
    assert fields.count("confidence") == 1, fields


def test_b6_the_key_walker_finds_a_planted_score_key_at_three_depths(capsys, tmp_path):
    """Positive control. Without it, a walker returning nothing would pass behavior 6."""
    old, new = _all_fields_pair(tmp_path)
    payload = _payload(capsys, old, new)
    assert BLENDED_KEY not in _walk_keys(payload)  # premise of the three plants below

    top = dict(payload, score=1.0)
    assert _walk_keys(top).count(BLENDED_KEY) == 1

    member = json.loads(json.dumps(payload))
    member["added"].append({"gap_id": "GAP-999", "title": "t", BLENDED_KEY: 1.0})
    assert _walk_keys(member).count(BLENDED_KEY) == 1

    nested = json.loads(json.dumps(payload))
    nested["changed"][0]["changes"][0][BLENDED_KEY] = 1.0
    assert _walk_keys(nested).count(BLENDED_KEY) == 1


def test_b6_no_blended_score_key_at_any_depth(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    keys = _walk_keys(payload)
    assert keys, "the walker saw nothing, so its silence is not evidence"
    assert BLENDED_KEY not in keys, sorted(set(keys))


def test_b6_no_key_anywhere_is_outside_the_published_vocabulary(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    payload = _payload(capsys, old, new)
    allowed = set(TOP_LEVEL_KEYS) | set(COUNTS_KEYS) | set(MEMBER_KEYS) \
        | set(CHANGED_KEYS) | set(CHANGE_KEYS)
    assert set(_walk_keys(payload)) <= allowed, sorted(set(_walk_keys(payload)) - allowed)


# ---------------------------------------------------------------------------
# behavior 7 -- one trailing newline, byte-stable
# ---------------------------------------------------------------------------

def test_b7_exactly_one_trailing_newline(tmp_path):
    old, new = _rich_pair(tmp_path)
    text = _run("diff", str(old), str(new), "--json").stdout.decode("utf-8")
    assert text.endswith("\n"), repr(text[-4:])
    assert not text.endswith("\n\n"), repr(text[-4:])


def test_b7_two_runs_over_identical_inputs_are_byte_identical(tmp_path):
    old, new = _rich_pair(tmp_path)
    first = _run("diff", str(old), str(new), "--json")
    second = _run("diff", str(old), str(new), "--json")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stdout, "an empty payload would make byte-stability vacuous"


def test_b7_filename_order_does_not_move_a_byte(tmp_path):
    """The payload is a function of record CONTENT, not of directory listing order."""
    plain_old, plain_new = _rich_pair(tmp_path / "plain")
    reversed_old, reversed_new = _rich_pair(tmp_path / "reversed", reverse_names=True)
    plain = _run("diff", str(plain_old), str(plain_new), "--json").stdout
    alternate = _run("diff", str(reversed_old), str(reversed_new), "--json").stdout
    assert plain == alternate


# ---------------------------------------------------------------------------
# behavior 8 -- identical register states
# ---------------------------------------------------------------------------

def test_b8_identical_registers_yield_three_empty_arrays_and_equal_counts(capsys, tmp_path):
    records = [_record("GAP-001"), _record("GAP-002"), _record("GAP-003")]
    old, new = _pair(tmp_path, records, [dict(record) for record in records])
    payload = _payload(capsys, old, new)
    assert payload["added"] == []
    assert payload["removed"] == []
    assert payload["changed"] == []
    assert payload["counts"] == {"old": 3, "new": 3}
    assert payload["counts"]["old"] == len(records)  # anti-vacuity: not zero records


def test_b8_the_live_register_diffed_against_itself_reports_nothing(tmp_path):
    """The one test that touches `gaps/`; true at any record count, so it cannot go stale."""
    proc = _run("diff", ".", ".", "--json")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["added"] == payload["removed"] == payload["changed"] == []
    assert payload["counts"]["old"] == payload["counts"]["new"]
    assert payload["counts"]["old"] > 0, "the live register is empty, so this asserts nothing"


# ---------------------------------------------------------------------------
# behavior 9 -- regression guards, both directions
# ---------------------------------------------------------------------------

def _expected_markdown(old, new) -> str:
    """The markdown document RECONSTRUCTED from the published grammar, not a golden blob."""
    old_gaps = {gap.id: gap for gap in load_all(old / "gaps")}
    new_gaps = {gap.id: gap for gap in load_all(new / "gaps")}
    added = [gid for gid in new_gaps if gid not in old_gaps]
    removed = [gid for gid in old_gaps if gid not in new_gaps]
    changed = []
    for gid in old_gaps:
        if gid not in new_gaps:
            continue
        before, after = _field_values(old_gaps[gid]), _field_values(new_gaps[gid])
        rows = [f"  - {field}: {before[field]} -> {after[field]}"
                for field in COMPARED_FIELDS if before[field] != after[field]]
        if rows:
            changed.append((gid, rows))
    lines = [TITLE, "",
             f"Old: {len(old_gaps)} record(s). New: {len(new_gaps)} record(s).", ""]
    for name, ids in (("Added", added), ("Removed", removed)):
        source = new_gaps if name == "Added" else old_gaps
        lines += [f"## {name} ({len(ids)})", ""]
        lines += [f"- {gid}  {source[gid].title}" for gid in ids] or [EMPTY_BODY]
        lines += [""]
    lines += [f"## Changed ({len(changed)})", ""]
    if changed:
        for gid, rows in changed:
            lines += [f"- {gid}", *rows]
    else:
        lines += [EMPTY_BODY]
    return "\n".join(lines) + "\n"


def test_b9_the_markdown_default_surface_is_byte_for_byte_the_published_grammar(capsys,
                                                                               tmp_path):
    old, new = _rich_pair(tmp_path)
    assert _markdown(capsys, old, new) == _expected_markdown(old, new)


def test_b9_the_markdown_reconstruction_is_armed(capsys, tmp_path):
    """Known-bad control: the comparison above must be able to FAIL."""
    old, new = _rich_pair(tmp_path)
    document = _markdown(capsys, old, new)
    mutated = _expected_markdown(old, new).replace("## Added (2)", "## Added (3)", 1)
    assert document != mutated


def test_b9_the_default_surface_emits_no_json(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _markdown(capsys, old, new)
    with pytest.raises(json.JSONDecodeError):
        json.loads(document)


@pytest.mark.parametrize("side", ["old", "new"])
def test_b9_a_nonexistent_path_with_json_writes_nothing_to_stdout_and_exits_two(tmp_path,
                                                                               side):
    present = _register(tmp_path / "present", [_record("GAP-001")])
    missing = tmp_path / "absent"
    args = (missing, present) if side == "old" else (present, missing)
    proc = _run("diff", str(args[0]), str(args[1]), "--json")
    assert proc.returncode == 2, proc.returncode
    assert proc.stdout == b"", proc.stdout
    stderr = proc.stderr.decode("utf-8")
    assert stderr.startswith(ERROR_PREFIX), repr(stderr[:80])
    assert stderr.endswith("\n"), repr(stderr[-4:])


# ---------------------------------------------------------------------------
# acceptance criterion -- `--json` landed on the `diff` subparser ONLY
# ---------------------------------------------------------------------------

UNRECOGNIZED = "unrecognized arguments: --json"


def _a_live_gap_id() -> str:
    """A real id, read from the product's own `list --json`, so `show` is driven correctly."""
    proc = _run("list", ".", "--json")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    rows = json.loads(proc.stdout.decode("utf-8"))["records"]
    assert rows, "the live register is empty, so `show` cannot be driven"
    return rows[0]["gap_id"]


@pytest.mark.parametrize("verb", ["validate", "report", "show", "prd", "taxonomy"])
def test_no_other_verb_gained_a_json_flag(verb):
    """Non-vacuous on purpose: each argv is otherwise VALID and the refusal must NAME the
    flag. Measured first -- `show --json` on its own fails with `the following arguments
    are required: gap_id`, so without a real gap id that case would pass for the wrong
    reason and would keep passing even if `show` DID gain `--json`.
    """
    if verb == "show":
        argv = ["show", _a_live_gap_id(), ".", "--json"]
    elif verb == "taxonomy":
        argv = ["taxonomy", "--json"]
    else:
        argv = [verb, ".", "--json"]
    proc = _run(*argv)
    assert proc.returncode != 0, f"`{' '.join(argv)}` was accepted"
    assert proc.stdout == b"", proc.stdout
    assert UNRECOGNIZED in proc.stderr.decode("utf-8"), proc.stderr.decode("utf-8")[-200:]


def test_the_argv_the_flag_guard_builds_is_otherwise_valid():
    """Control for the test above: strip `--json` and every one of those argvs succeeds."""
    for argv in (["validate", "."], ["report", "."], ["taxonomy"],
                 ["show", _a_live_gap_id(), "."]):
        proc = _run(*argv)
        assert proc.returncode == 0, (argv, proc.stderr.decode("utf-8", "replace")[-200:])


@pytest.mark.parametrize("verb", ["list", "diff"])
def test_the_verbs_that_already_published_json_still_do(verb, tmp_path):
    argv = ["list", ".", "--json"] if verb == "list" else ["diff", ".", ".", "--json"]
    proc = _run(*argv)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert json.loads(proc.stdout.decode("utf-8")) is not None
