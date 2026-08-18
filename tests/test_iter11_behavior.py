"""Iteration 11 behaviors: `radar diff OLD NEW`, the register-change report.

The register is now grown by a schedule rather than by hand, and until this verb there
was no artifact anywhere saying what a pass changed. The corruption vector the diff
exists to make visible is a QUIET SCORE CHANGE -- a `severity` moved 3 -> 5, or a
citation dropped -- which changes what the build loop picks next and today leaves no
reviewable trace.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every assertion either runs
`agent_gap_radar.cli.main` and observes only its exit code, stdout and stderr, or calls
the public library API the spec names (`registry.load_all`, `scoring.priority`,
`scoring.confidence`, and the shared `tests/_surface_contract.py` oracle).

Habits kept on purpose, each one buying a specific fail-open back:

* NO expected field value is hand-written. Every `priority` and `confidence` the
  document is checked against is obtained by CALLING `scoring.priority()` /
  `scoring.confidence()` on the same record the register holds, which is exactly what
  behavior 5 requires of the renderer -- so a re-derivation drifting from the shipped
  scoring functions fails here rather than agreeing with a copy of itself;
* the section parser asserts headings are UNIQUE and that every `## ` line carries a
  count. A dict keyed on heading silently keeps only the LAST section of a given name,
  so a document rendering two `## Changed` sections would leave one unexamined while
  every assertion still passed;
* every "nothing was reported" assertion is paired with an ANTI-VACUITY companion over
  the same fixture with one closed field changed. `## Changed (0)` is the answer a verb
  that reports nothing at all also gives, so the empty result is only evidence once the
  non-empty one is proven reachable from the same shape;
* the filename-independence proof mutates FILENAMES ONLY and asserts the two documents
  are byte-identical, with the second naming scheme chosen so its sort order is the
  REVERSE of id order -- a walk that ordered by filename cannot pass both halves;
* the no-blend assertion drops any candidate blend that COINCIDES with a value the
  document legitimately reports (an old `priority` of 4.0 with an old `confidence` of 1
  has 4.0 as its own product), then asserts the surviving candidate set is NON-EMPTY
  before asserting it is absent. Asserting absence from an empty candidate set is the
  green that means nothing;
* the published-surface check is proven ARMED by mutation: the same call is re-run over
  a document whose `diff` row has had a positional deleted, and must then report a
  difference. A table that merely happens to agree today is indistinguishable from a
  live check until one of them is made to fail.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import NamedTuple

import pytest

from _surface_contract import (contract_text, documented_invocation, invocation_verb,
                               parser_surface, surface_table_cells, surface_violations)
from agent_gap_radar.cli import main
from agent_gap_radar.registry import RegistryError, load_all
from agent_gap_radar.scoring import confidence, priority

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

TITLE = "# Register diff"

#: Behavior 3 fixes both the membership and the ORDER of the three sections.
SECTION_ORDER = ("Added", "Removed", "Changed")

#: Behavior 5 fixes the compared fields AND the order their nested lines appear in.
COMPARED_FIELDS = ("status", "layer", "gap_type", "severity", "frequency",
                   "tractability", "priority", "confidence", "citations")

#: The single body line a section with no records renders (behavior 3).
EMPTY_BODY = "None."

#: Every `## ` line must match: a heading with no count is a shape violation, not a
#: section this parser is entitled to skip.
HEADING = re.compile(r"^## (?P<name>[A-Za-z]+) \((?P<count>\d+)\)$")

#: Behavior 2's line, asserted verbatim by shape and then by DERIVED counts.
DOMAIN_LINE = re.compile(r"^Old: (?P<old>\d+) record\(s\)\. New: (?P<new>\d+) record\(s\)\.$")

#: Behavior 4: two spaces between id and title, deliberately part of the assertion.
MEMBER_ROW = re.compile(r"^- (?P<id>GAP-\d+)  (?P<title>\S.*)$")
CHANGED_ROW = re.compile(r"^- (?P<id>GAP-\d+)$")
NESTED_ROW = re.compile(r"^  - (?P<field>[a-z_]+): (?P<old>.+) -> (?P<new>.+)$")

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
    return [{**EVIDENCE, "source_class": cls, "title": f"source {cls}"}
            for cls in classes]


def _record(gid: str, **over) -> dict:
    record = {
        "id": gid, "title": f"the {gid} problem", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": _evidence("first-party-field"),
    }
    record.update(over)
    return record


def _register(root: pathlib.Path, records, names=None) -> pathlib.Path:
    """Materialise `<root>/gaps/` and return `root` (a repo root, per behavior 10).

    `names` controls FILENAMES ONLY and is how behavior 8 is exercised: the record
    content is byte-identical between the two naming schemes.
    """
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    if names is not None:
        assert len(names) == len(records), (len(names), len(records))
    for index, record in enumerate(records):
        name = names[index] if names is not None else f"{record['id']}.json"
        (gaps / name).write_text(json.dumps(record), encoding="utf-8")
    return root


def _reverse_names(count: int) -> list[str]:
    """Filenames whose sort order is the REVERSE of the record order handed in."""
    return [f"{count - index:03d}-record.json" for index in range(count)]


def _rich_pair(tmp_path, *, reverse_names: bool = False):
    """A pair with three records in each section, plus one record that never changes."""
    unchanged = _record("GAP-001")
    changed_ids = ("GAP-002", "GAP-003", "GAP-010")
    removed_ids = ("GAP-005", "GAP-006", "GAP-009")
    added_ids = ("GAP-004", "GAP-007", "GAP-008")
    old_records = [unchanged, *(_record(g) for g in changed_ids),
                   *(_record(g) for g in removed_ids)]
    new_records = [unchanged, *(_record(g, status="addressed") for g in changed_ids),
                   *(_record(g) for g in added_ids)]
    old_names = _reverse_names(len(old_records)) if reverse_names else None
    new_names = _reverse_names(len(new_records)) if reverse_names else None
    old = _register(tmp_path / "old", old_records, old_names)
    new = _register(tmp_path / "new", new_records, new_names)
    return old, new


def _pair(tmp_path, old_records, new_records):
    return (_register(tmp_path / "old", old_records),
            _register(tmp_path / "new", new_records))


def _one(root: pathlib.Path, gid: str):
    """One loaded record, via the public loader -- the oracle for derived values."""
    matched = [gap for gap in load_all(root / "gaps") if gap.id == gid]
    assert len(matched) == 1, f"{gid} is not uniquely present under {root.name}/gaps"
    return matched[0]


# ---------------------------------------------------------------------------
# document plumbing -- run the product, parse only what it publishes
# ---------------------------------------------------------------------------

def _diff(capsys, old, new) -> str:
    assert main(["diff", str(old), str(new)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "", captured.err
    document = captured.out
    assert document.splitlines()[0] == TITLE, document[:80]
    assert document.endswith("\n") and not document.endswith("\n\n"), repr(document[-4:])
    return document


class Section(NamedTuple):
    name: str
    count: int
    body: tuple[str, ...]


def _sections(document: str) -> list[Section]:
    sections: list[Section] = []
    name: str | None = None
    count = 0
    body: list[str] = []
    for line in document.splitlines():
        if line.startswith("## "):
            if name is not None:
                sections.append(Section(name, count, tuple(body)))
            match = HEADING.match(line)
            assert match, (
                f"heading {line!r} is not `## <Name> (<n>)`; a section whose count is "
                "missing cannot be told from one whose count is zero")
            name, count, body = match["name"], int(match["count"]), []
        elif name is not None and line.strip():
            body.append(line)
    if name is not None:
        sections.append(Section(name, count, tuple(body)))
    names = [section.name for section in sections]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, (
        f"a heading is rendered twice ({duplicates}), so a name-keyed lookup leaves one "
        "section unexamined while every assertion below still passes")
    return sections


def _by_name(document: str) -> dict[str, Section]:
    return {section.name: section for section in _sections(document)}


def _member_ids(section: Section) -> list[str]:
    if section.body == (EMPTY_BODY,):
        return []
    ids = []
    for line in section.body:
        match = MEMBER_ROW.match(line)
        assert match, f"{section.name} body line {line!r} is not `- GAP-0NN  <title>`"
        ids.append(match["id"])
    return ids


def _changed_blocks(section: Section) -> dict[str, list[str]]:
    """id -> its nested difference lines, in document order."""
    if section.body == (EMPTY_BODY,):
        return {}
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.body:
        head = CHANGED_ROW.match(line)
        if head:
            current = head["id"]
            assert current not in blocks, f"{current} is listed twice under Changed"
            blocks[current] = []
            continue
        assert current is not None, f"nested line {line!r} precedes any record line"
        assert NESTED_ROW.match(line), (
            f"Changed body line {line!r} is neither `- GAP-0NN` nor "
            "`  - <field>: <old> -> <new>`")
        blocks[current].append(line)
    return blocks


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


def _expected_nested(old_gap, new_gap) -> list[str]:
    old_values, new_values = _field_values(old_gap), _field_values(new_gap)
    return [f"  - {field}: {old_values[field]} -> {new_values[field]}"
            for field in COMPARED_FIELDS if old_values[field] != new_values[field]]


# ---------------------------------------------------------------------------
# behavior 1 -- document shape
# ---------------------------------------------------------------------------

def test_b1_document_shape_over_a_rich_pair(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _diff(capsys, old, new)
    # `_diff` asserts exit 0, empty stderr, the exact first line and the single
    # trailing newline. Re-asserted here so the behavior owns a named test.
    assert document.startswith(TITLE + "\n")
    assert document.count(TITLE) == 1, "the title is rendered more than once"
    assert not document.endswith("\n\n")


def test_b1_all_three_counts_zero_still_exits_zero_and_emits_the_document(capsys, tmp_path):
    same = [_record("GAP-001"), _record("GAP-002")]
    old, new = _pair(tmp_path, same, [dict(record) for record in same])
    document = _diff(capsys, old, new)
    sections = _by_name(document)
    assert sorted(sections) == sorted(SECTION_ORDER)
    assert [sections[name].count for name in SECTION_ORDER] == [0, 0, 0]


# ---------------------------------------------------------------------------
# behavior 2 -- both domain sizes are stated
# ---------------------------------------------------------------------------

def test_b2_domain_line_states_both_derived_sizes(capsys, tmp_path):
    # Deliberately ASYMMETRIC: the rich pair happens to hold seven records on each
    # side, and over equal domains an implementation that printed one number twice
    # would satisfy every assertion below.
    old, new = _pair(tmp_path,
                     [_record("GAP-001"), _record("GAP-002")],
                     [_record("GAP-001"), _record("GAP-003"), _record("GAP-004")])
    document = _diff(capsys, old, new)
    matches = [DOMAIN_LINE.match(line) for line in document.splitlines()]
    found = [match for match in matches if match]
    assert len(found) == 1, "exactly one `Old: N record(s). New: M record(s).` line"
    expected_old = len(load_all(old / "gaps"))
    expected_new = len(load_all(new / "gaps"))
    assert (int(found[0]["old"]), int(found[0]["new"])) == (expected_old, expected_new)
    # Anti-vacuity: the two sides must differ in size here, or an implementation that
    # printed one number twice would satisfy the assertion above.
    assert expected_old != expected_new, (expected_old, expected_new)


def test_b2_emptied_old_side_reads_as_zero_not_as_everything_added(capsys, tmp_path):
    old = _register(tmp_path / "old", [])
    new = _register(tmp_path / "new", [_record("GAP-001"), _record("GAP-002")])
    document = _diff(capsys, old, new)
    assert "Old: 0 record(s). New: 2 record(s)." in document
    assert _by_name(document)["Added"].count == 2


# ---------------------------------------------------------------------------
# behavior 3 -- three sections, always present, in order
# ---------------------------------------------------------------------------

def test_b3_sections_are_present_in_the_fixed_order(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _diff(capsys, old, new)
    assert tuple(section.name for section in _sections(document)) == SECTION_ORDER


def test_b3_counts_match_their_own_bodies(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _diff(capsys, old, new)
    sections = _by_name(document)
    assert sections["Added"].count == len(_member_ids(sections["Added"]))
    assert sections["Removed"].count == len(_member_ids(sections["Removed"]))
    assert sections["Changed"].count == len(_changed_blocks(sections["Changed"]))
    # Anti-vacuity: all three are non-empty in this fixture, so the equalities above
    # are not three copies of `0 == 0`.
    assert all(sections[name].count > 0 for name in SECTION_ORDER)


def test_b3_empty_section_renders_none_and_is_never_omitted(capsys, tmp_path):
    old = _register(tmp_path / "old", [_record("GAP-001")])
    new = _register(tmp_path / "new", [_record("GAP-001"), _record("GAP-002")])
    document = _diff(capsys, old, new)
    sections = _by_name(document)
    assert sections["Added"].count == 1
    for empty in ("Removed", "Changed"):
        assert sections[empty].count == 0
        assert sections[empty].body == (EMPTY_BODY,), sections[empty].body


# ---------------------------------------------------------------------------
# behavior 4 -- Added / Removed membership and format
# ---------------------------------------------------------------------------

def test_b4_membership_is_the_set_difference_in_both_directions(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _diff(capsys, old, new)
    old_ids = {gap.id for gap in load_all(old / "gaps")}
    new_ids = {gap.id for gap in load_all(new / "gaps")}
    sections = _by_name(document)
    assert set(_member_ids(sections["Added"])) == new_ids - old_ids
    assert set(_member_ids(sections["Removed"])) == old_ids - new_ids
    # Anti-vacuity: both differences are non-empty, and the two are not the same set.
    assert new_ids - old_ids and old_ids - new_ids
    assert (new_ids - old_ids) != (old_ids - new_ids)


def test_b4_rows_carry_the_records_own_title_after_two_spaces(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _diff(capsys, old, new)
    sections = _by_name(document)
    for name, side in (("Added", new), ("Removed", old)):
        for line in sections[name].body:
            match = MEMBER_ROW.match(line)
            assert match, line
            expected = _one(side, match["id"]).title
            assert match["title"] == expected, (name, line, expected)
            assert line == f"- {match['id']}  {expected}", repr(line)


# ---------------------------------------------------------------------------
# behavior 5 -- Changed: fixed field order, derived values
# ---------------------------------------------------------------------------

def _all_fields_pair(tmp_path):
    """A pair whose one shared record differs on every one of the nine fields."""
    old_record = _record("GAP-002", severity=2, frequency=2, tractability=2,
                         evidence=_evidence("secondary-summary"))
    new_record = _record("GAP-002", status="addressed", layer="multi-agent",
                         gap_type="silent-failure", severity=5, frequency=4,
                         tractability=3,
                         evidence=_evidence("first-party-field", "peer-reviewed"))
    return _pair(tmp_path, [old_record], [new_record])


def test_b5_every_compared_field_is_reported_in_the_fixed_order(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    document = _diff(capsys, old, new)
    blocks = _changed_blocks(_by_name(document)["Changed"])
    assert list(blocks) == ["GAP-002"]
    expected = _expected_nested(_one(old, "GAP-002"), _one(new, "GAP-002"))
    # Anti-vacuity: this fixture is the one that exercises ALL nine fields, so if a
    # later edit weakens it the order assertion stops being about order at all.
    assert len(expected) == len(COMPARED_FIELDS), expected
    assert blocks["GAP-002"] == expected
    fields = [NESTED_ROW.match(line)["field"] for line in blocks["GAP-002"]]
    assert tuple(fields) == COMPARED_FIELDS


def test_b5_derived_values_are_the_scoring_modules_own_answers(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    document = _diff(capsys, old, new)
    reported = {NESTED_ROW.match(line)["field"]: NESTED_ROW.match(line)
                for line in _changed_blocks(_by_name(document)["Changed"])["GAP-002"]}
    old_gap, new_gap = _one(old, "GAP-002"), _one(new, "GAP-002")
    assert reported["priority"]["old"] == str(priority(old_gap))
    assert reported["priority"]["new"] == str(priority(new_gap))
    assert reported["confidence"]["old"] == str(confidence(old_gap))
    assert reported["confidence"]["new"] == str(confidence(new_gap))
    assert reported["citations"]["old"] == str(len(old_gap.evidence))
    assert reported["citations"]["new"] == str(len(new_gap.evidence))


def test_b5_raw_inputs_are_reported_even_when_priority_masks_them(capsys, tmp_path):
    """The masking case the spec names: `frequency -1` with `tractability +2`."""
    old_record = _record("GAP-002")
    new_record = _record("GAP-002", frequency=2, tractability=5)
    old, new = _pair(tmp_path, [old_record], [new_record])
    old_gap, new_gap = _one(old, "GAP-002"), _one(new, "GAP-002")
    assert priority(old_gap) == priority(new_gap), "the fixture no longer masks"
    document = _diff(capsys, old, new)
    blocks = _changed_blocks(_by_name(document)["Changed"])
    assert list(blocks) == ["GAP-002"]
    fields = [NESTED_ROW.match(line)["field"] for line in blocks["GAP-002"]]
    assert fields == ["frequency", "tractability"]
    assert not any(line.startswith("  - priority:") for line in blocks["GAP-002"])


def test_b5_record_with_no_differing_field_appears_in_no_section(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    document = _diff(capsys, old, new)
    sections = _by_name(document)
    unchanged_id = "GAP-001"
    assert unchanged_id in {gap.id for gap in load_all(old / "gaps")}
    assert unchanged_id in {gap.id for gap in load_all(new / "gaps")}
    assert unchanged_id not in _member_ids(sections["Added"])
    assert unchanged_id not in _member_ids(sections["Removed"])
    assert unchanged_id not in _changed_blocks(sections["Changed"])


# ---------------------------------------------------------------------------
# behavior 6 -- free prose is never diffed
# ---------------------------------------------------------------------------

PROSE_ID = "GAP-042"


def _prose_only_pair(tmp_path, *, also_change_status: bool = False):
    """Two sides differing ONLY in free prose -- optionally plus one closed field.

    The citation is rewritten in every text field it has (title, locator, date, quote)
    while keeping its `source_class` and the citation COUNT, so `confidence` and
    `citations` are identical by construction and the only differences are prose.
    """
    old_record = _record(
        PROSE_ID, title="the original wording", problem="the original problem statement",
        symptom="the operator sees nothing at all", why_now="because it is new",
        existing=["one partial solution, which falls short"],
        build_hypothesis="build the first thing", tags=["alpha", "beta"],
        check={"id": "CHK-042", "manual_question": "does the target do the thing?",
               "rationale": "the original rationale"},
        evidence=[{**EVIDENCE, "source_class": "first-party-field",
                   "title": "the original source title",
                   "locator": "https://example.invalid/original",
                   "date": "2026-01-02", "quote": "the original verbatim line"}])
    new_record = _record(
        PROSE_ID, title="the wording, rewritten from scratch",
        problem="a completely reworded problem statement",
        symptom="the operator observes nothing whatsoever",
        why_now="because it is still new, said differently",
        existing=["a different partial solution", "and a second one"],
        build_hypothesis="build a differently described thing", tags=["gamma"],
        check={"id": "CHK-042", "manual_question": "does the target really do it?",
               "rationale": "a reworded rationale"},
        evidence=[{**EVIDENCE, "source_class": "first-party-field",
                   "title": "the source title, renamed",
                   "locator": "https://example.invalid/moved",
                   "date": "2026-03-04", "quote": "a different verbatim line"}])
    if also_change_status:
        new_record["status"] = "addressed"
    return _pair(tmp_path, [old_record], [new_record])


def test_b6_prose_only_difference_is_not_a_change(capsys, tmp_path):
    old, new = _prose_only_pair(tmp_path)
    old_gap, new_gap = _one(old, PROSE_ID), _one(new, PROSE_ID)
    # The fixture's premise, asserted rather than assumed: the two records genuinely
    # differ, and they agree on every compared field.
    assert old_gap != new_gap, "the fixture no longer differs at all"
    assert _field_values(old_gap) == _field_values(new_gap)
    document = _diff(capsys, old, new)
    sections = _by_name(document)
    assert sections["Changed"].count == 0
    assert sections["Changed"].body == (EMPTY_BODY,)
    assert [sections[name].count for name in SECTION_ORDER] == [0, 0, 0]
    # No section names it, and the id does not appear anywhere in the document either:
    # a prose-diffing implementation cannot report a rewording without naming the record.
    for section in sections.values():
        assert PROSE_ID not in "\n".join(section.body)
    assert PROSE_ID not in document


def test_b6_the_same_pair_with_one_closed_field_change_is_reported(capsys, tmp_path):
    """Anti-vacuity for the test above: `## Changed (0)` must be reachable-from-not."""
    old, new = _prose_only_pair(tmp_path, also_change_status=True)
    document = _diff(capsys, old, new)
    blocks = _changed_blocks(_by_name(document)["Changed"])
    assert list(blocks) == [PROSE_ID]
    fields = [NESTED_ROW.match(line)["field"] for line in blocks[PROSE_ID]]
    assert fields == ["status"], "only the closed field, still no prose"


# ---------------------------------------------------------------------------
# behavior 7 -- the unblended invariant survives
# ---------------------------------------------------------------------------

def test_b7_priority_and_confidence_are_two_separate_lines(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    document = _diff(capsys, old, new)
    lines = _changed_blocks(_by_name(document)["Changed"])["GAP-002"]
    fields = [NESTED_ROW.match(line)["field"] for line in lines]
    assert fields.count("priority") == 1
    assert fields.count("confidence") == 1
    # Closed set: no third number can be reported alongside them.
    assert set(fields) <= set(COMPARED_FIELDS)


def test_b7_no_blended_figure_appears_anywhere(capsys, tmp_path):
    old, new = _all_fields_pair(tmp_path)
    old_gap, new_gap = _one(old, "GAP-002"), _one(new, "GAP-002")
    legitimate = {str(value) for gap in (old_gap, new_gap)
                  for value in _field_values(gap).values()}
    candidates = set()
    for gap in (old_gap, new_gap):
        p, c = priority(gap), confidence(gap)
        for blend in (p * c, p + c, (p + c) / 2):
            candidates.add(f"{blend:g}")
            candidates.add(f"{blend:.1f}")
            candidates.add(f"{blend:.2f}")
    # A candidate that COINCIDES with a value the document legitimately reports proves
    # nothing either way, so it is dropped -- an old priority of 4.0 with an old
    # confidence of 1 has 4.0 as its own product.
    candidates -= legitimate
    assert candidates, "no blend candidate survived; absence from an empty set is free"
    document = _diff(capsys, old, new)
    present = sorted(value for value in candidates if value in document)
    assert present == [], f"a blended figure appears in the document: {present}"


# ---------------------------------------------------------------------------
# behavior 8 -- determinism
# ---------------------------------------------------------------------------

def test_b8_two_consecutive_runs_are_byte_identical(capsys, tmp_path):
    old, new = _rich_pair(tmp_path)
    first = _diff(capsys, old, new)
    second = _diff(capsys, old, new)
    assert first == second


def test_b8_filenames_do_not_change_the_output(capsys, tmp_path):
    """The second naming scheme's sort order is the REVERSE of the record order."""
    plain_old, plain_new = _rich_pair(tmp_path / "plain")
    renamed_old, renamed_new = _rich_pair(tmp_path / "renamed", reverse_names=True)
    plain_names = sorted(path.name for path in (plain_old / "gaps").iterdir())
    renamed_names = sorted(path.name for path in (renamed_old / "gaps").iterdir())
    assert plain_names != renamed_names, "the fixture did not actually rename anything"
    assert _diff(capsys, plain_old, plain_new) == _diff(capsys, renamed_old, renamed_new)


def test_b8_every_section_is_in_ascending_id_order(capsys, tmp_path):
    for reverse in (False, True):
        old, new = _rich_pair(tmp_path / f"pair-{reverse}", reverse_names=reverse)
        document = _diff(capsys, old, new)
        sections = _by_name(document)
        for name in ("Added", "Removed"):
            ids = _member_ids(sections[name])
            assert len(ids) > 1, (name, ids)
            assert ids == sorted(ids), (name, ids)
        changed = list(_changed_blocks(sections["Changed"]))
        assert len(changed) > 1, changed
        assert changed == sorted(changed), changed


# ---------------------------------------------------------------------------
# behavior 9 -- both paths are required
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("given", [1, 0], ids=["one-positional", "no-positional"])
def test_b9_a_missing_side_exits_2_with_usage_on_stderr(capsys, tmp_path, given):
    old = _register(tmp_path / "old", [_record("GAP-001")])
    argv = ["diff", *([str(old)] if given else [])]
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == "", captured.out
    assert "usage" in captured.err.lower(), captured.err


def test_b9_the_two_positional_form_is_the_one_that_works(capsys, tmp_path):
    """Control for the test above: exit 2 is about arity, not a broken verb.

    A `nargs="?" default="."` positional would make the one-argument invocation exit 0
    over whatever register sits in the caller's working directory -- the silent wrong
    answer iteration 10 documented. Here the SAME path is accepted only when given twice.
    """
    old = _register(tmp_path / "old", [_record("GAP-001")])
    document = _diff(capsys, old, old)
    assert "Old: 1 record(s). New: 1 record(s)." in document


# ---------------------------------------------------------------------------
# behavior 10 -- unloadable sides fail closed, in the shipped vocabulary
# ---------------------------------------------------------------------------

BREAKAGES = ("not-a-directory", "invalid-json", "schema-violation", "duplicate-ids")


def _breakage(root: pathlib.Path, kind: str):
    """Materialise one unloadable side; return (path to pass, loader domain or None)."""
    if kind == "not-a-directory":
        root.mkdir(parents=True)
        path = root / "a-file"
        path.write_text("x", encoding="utf-8")
        return path, None
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    if kind == "invalid-json":
        (gaps / "broken.json").write_text("{not json", encoding="utf-8")
    elif kind == "schema-violation":
        (gaps / "GAP-001.json").write_text(
            json.dumps(_record("GAP-001", severity=9)), encoding="utf-8")
    elif kind == "duplicate-ids":
        for name in ("one.json", "two.json"):
            (gaps / name).write_text(json.dumps(_record("GAP-001")), encoding="utf-8")
    else:  # pragma: no cover -- an unknown kind must fail loudly, not silently pass
        raise AssertionError(f"unknown breakage {kind!r}")
    return root, gaps


@pytest.mark.parametrize("side", ("old", "new"))
@pytest.mark.parametrize("kind", BREAKAGES)
def test_b10_an_unloadable_side_fails_closed(capsys, tmp_path, kind, side):
    good = _register(tmp_path / "good", [_record("GAP-001")])
    bad, domain = _breakage(tmp_path / "bad", kind)
    assert (domain is not None) == (kind != "not-a-directory"), kind
    argv = [str(bad), str(good)] if side == "old" else [str(good), str(bad)]
    assert main(["diff", *argv]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", captured.out
    assert captured.err.startswith("Error: "), captured.err
    assert captured.err.count("\n") == 1, repr(captured.err)
    if domain is not None:
        # The failing side's OWN loader message is carried through: no new error
        # vocabulary is introduced by this verb.
        with pytest.raises(RegistryError) as excinfo:
            load_all(domain)
        assert str(excinfo.value) in captured.err, (str(excinfo.value), captured.err)


def test_b10_a_side_holding_zero_records_is_not_an_error(capsys, tmp_path):
    old = _register(tmp_path / "old", [])
    new = _register(tmp_path / "new", [])
    document = _diff(capsys, old, new)
    assert "Old: 0 record(s). New: 0 record(s)." in document
    assert [_by_name(document)[name].count for name in SECTION_ORDER] == [0, 0, 0]


# ---------------------------------------------------------------------------
# behavior 11 -- the published surface stays derived
# ---------------------------------------------------------------------------

def _diff_cell() -> str:
    cells = [cell for cell in surface_table_cells(contract_text())
             if invocation_verb(cell) == "diff"]
    assert len(cells) == 1, f"the stable-surface table documents `diff` {len(cells)} time(s)"
    return cells[0]


def test_b11_the_published_surface_reports_no_violations():
    assert surface_violations(contract_text()) == []


def test_b11_the_diff_row_documents_two_positionals_and_no_options():
    surface = parser_surface()
    assert "diff" in surface, "build_parser() no longer registers the verb"
    cell = _diff_cell()
    claimed = documented_invocation(cell, surface["diff"].takes_value)
    assert claimed.positionals == 2, cell
    assert claimed.options == frozenset(), cell
    assert claimed.positionals == surface["diff"].positionals
    assert "[" not in cell and "]" not in cell, (
        f"{cell!r} brackets a positional the parser requires")


def test_b11_the_surface_check_is_armed_against_this_row():
    """Two-sided: a table that merely agrees today looks exactly like a live check."""
    document = contract_text()
    cell = _diff_cell()
    mutated = document.replace(cell, cell.replace(" <new>", "", 1), 1)
    assert mutated != document, "the mutation did not change the document"
    violations = surface_violations(mutated)
    assert violations, "deleting a documented positional was not reported"
    assert any("diff" in violation for violation in violations), violations


# ---------------------------------------------------------------------------
# the live register -- real data, and an assertion that survives it growing
# ---------------------------------------------------------------------------

def test_live_register_diffed_against_itself_reports_no_change(capsys):
    document = _diff(capsys, REPO_ROOT, REPO_ROOT)
    count = len(load_all(REPO_ROOT / "gaps"))
    assert count > 0, "an empty register makes every assertion below free"
    assert f"Old: {count} record(s). New: {count} record(s)." in document
    for section in _sections(document):
        assert section.count == 0, section
        assert section.body == (EMPTY_BODY,), section


def test_no_test_in_this_module_stands_down():
    """A skipped test is invisible in a suite total, so this module may not skip."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for marker in ("pytest.mark." + "skip", "pytest.mark." + "xfail",
                   "pytest." + "skip("):
        assert marker not in source, marker
