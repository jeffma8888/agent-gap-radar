"""Iteration 419 behaviors: `radar diff` compares a record's distinct source documents.

Before this iteration a research pass could replace every source a record rests on --
same class, same count -- and `radar diff` read byte-identical to "nothing changed".
The tenth compared field, `sources`, reports the derivation's INPUT (the distinct
documents `confidence()` counts), not only its result.

Black-box, and the isolation contract is honored: nothing here reads the
implementation source, the engineer's or reviewer's notes, or a diff. Every assertion
runs `agent_gap_radar.cli.main` and observes exit code / stdout / stderr, or calls the
public names the spec publishes (`diff.COMPARED_FIELDS`, `diff.record_facts`,
`scoring.source_documents`, `scoring.distinct_sources`, `registry.load_all`).

Fixtures are tmp registers built by copying real records out of the committed
`gaps/` dir and mutating ONE thing, so every "no change" assertion is paired with an
anti-vacuity companion over the same base that IS reported as a change.
"""

from __future__ import annotations

import copy
import json
import pathlib
import re

import pytest

from agent_gap_radar import diff as diff_mod
from agent_gap_radar import scoring
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all

#: Repo root, relative to this file -- no absolute machine path.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO_ROOT / "gaps"

EXPECTED_FIELDS = ("status", "layer", "gap_type", "severity", "frequency",
                   "tractability", "priority", "confidence", "citations", "sources")

#: A single-citation record and a two-citation record from the committed register.
SINGLE_ID = "GAP-010"
MULTI_ID = "GAP-001"

NEW_DOC = "https://example.org/other-report"

HEADING = re.compile(r"^## (?P<name>[A-Za-z]+) \((?P<count>\d+)\)$")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _raw(gid: str) -> dict:
    matches = [p for p in sorted(GAPS.glob("*.json")) if p.name.startswith(gid + "-")
               or p.name == gid + ".json"]
    assert len(matches) == 1, (gid, [m.name for m in matches])
    return json.loads(matches[0].read_text(encoding="utf-8"))


def _independent_key(locator: str) -> str:
    """The spec's normalisation, written from the spec: drop #fragment, strip trailing
    '/', casefold."""
    return locator.split("#", 1)[0].rstrip("/").casefold()


def _register(root: pathlib.Path, records: list[dict]) -> pathlib.Path:
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    for record in records:
        (gaps / f"{record['id']}.json").write_text(json.dumps(record, indent=2),
                                                   encoding="utf-8")
    return root


def _pair(tmp_path, mutate) -> tuple[pathlib.Path, pathlib.Path]:
    """A two-record register pair; `mutate(records_by_id)` edits the NEW side only."""
    base = [_raw(SINGLE_ID), _raw(MULTI_ID)]
    old = _register(tmp_path / "old", base)
    new_records = {r["id"]: copy.deepcopy(r) for r in base}
    mutate(new_records)
    new = _register(tmp_path / "new", list(new_records.values()))
    return old, new


def _run(capsys, *argv) -> tuple[int, str, str]:
    rc = main(list(argv))
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _diff_ok(capsys, old, new, *flags) -> str:
    rc, out, err = _run(capsys, "diff", str(old), str(new), *flags)
    assert rc == 0, (rc, err)
    assert err == "", err
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-4:])
    return out


def _changed_section(document: str) -> tuple[int, list[str]]:
    count = None
    body: list[str] = []
    inside = False
    headings = []
    for line in document.splitlines():
        if line.startswith("## "):
            match = HEADING.match(line)
            assert match, line
            headings.append(match["name"])
            inside = match["name"] == "Changed"
            if inside:
                count = int(match["count"])
            continue
        if inside and line.strip():
            body.append(line)
    assert headings.count("Changed") == 1, headings
    assert count is not None
    return count, body


def _nested_for(body: list[str], gid: str) -> list[str]:
    lines: list[str] = []
    active = False
    for line in body:
        if line.startswith("- "):
            active = line == f"- {gid}"
            continue
        if active and line.startswith("  - "):
            lines.append(line)
    return lines


def _swap_only_locator(records):
    records[SINGLE_ID]["evidence"][0]["locator"] = NEW_DOC


# ---------------------------------------------------------------------------
# behavior 1 -- the field tuple
# ---------------------------------------------------------------------------

def test_b1_compared_fields_is_exactly_ten_with_sources_last():
    assert tuple(diff_mod.COMPARED_FIELDS) == EXPECTED_FIELDS
    assert len(diff_mod.COMPARED_FIELDS) == 10
    assert diff_mod.COMPARED_FIELDS[-1] == "sources"


# ---------------------------------------------------------------------------
# behavior 2 -- record_facts / source_documents / distinct_sources
# ---------------------------------------------------------------------------

def test_b2_source_documents_is_sorted_normalised_distinct_keys_for_every_record():
    gaps = load_all(GAPS)
    assert len(gaps) > 10
    multi_doc_seen = False
    for gap in gaps:
        docs = scoring.source_documents(gap)
        assert isinstance(docs, tuple), (gap.id, type(docs))
        expected = tuple(sorted({_independent_key(e.locator) for e in gap.evidence}))
        assert docs == expected, gap.id
        assert scoring.distinct_sources(gap) == len(docs), gap.id
        multi_doc_seen |= len(docs) > 1
    assert multi_doc_seen, "no multi-document record: the sort/join arms are vacuous"


def test_b2_record_facts_sources_is_comma_space_join_of_source_documents():
    for gap in load_all(GAPS):
        facts = diff_mod.record_facts(gap)
        assert set(EXPECTED_FIELDS) <= set(facts), (gap.id, sorted(facts))
        assert facts["sources"] == ", ".join(scoring.source_documents(gap)), gap.id


def test_b2_normalisation_drops_fragment_trailing_slash_and_case(tmp_path):
    record = _raw(SINGLE_ID)
    second = copy.deepcopy(record["evidence"][0])
    second["locator"] = "HTTPS://A.Example/X/#frag"
    third = copy.deepcopy(record["evidence"][0])
    third["locator"] = "https://a.example/x"
    record["evidence"] = [second, third]
    root = _register(tmp_path / "r", [record])
    (gap,) = load_all(root / "gaps")
    assert scoring.source_documents(gap) == ("https://a.example/x",)
    assert scoring.distinct_sources(gap) == 1


# ---------------------------------------------------------------------------
# behaviors 3 + 4 -- a swapped only-source is reported, markdown and JSON
# ---------------------------------------------------------------------------

def test_b3_swapping_the_only_locator_is_one_sources_line(capsys, tmp_path):
    old, new = _pair(tmp_path, _swap_only_locator)
    old_key = _independent_key(_raw(SINGLE_ID)["evidence"][0]["locator"])
    document = _diff_ok(capsys, old, new)
    count, body = _changed_section(document)
    assert count == 1, document
    assert f"- {SINGLE_ID}" in body, body
    assert _nested_for(body, SINGLE_ID) == [f"  - sources: {old_key} -> {NEW_DOC}"], body
    assert not any(line.startswith("  - confidence:") or line.startswith("  - citations:")
                   for line in body), body


def test_b3_both_sides_still_validate(capsys, tmp_path):
    old, new = _pair(tmp_path, _swap_only_locator)
    for side in (old, new):
        rc, out, err = _run(capsys, "validate", str(side / "gaps"))
        assert rc == 0, (side.name, out, err)


def test_b4_json_changes_is_exactly_one_sources_entry(capsys, tmp_path):
    old, new = _pair(tmp_path, _swap_only_locator)
    old_key = _independent_key(_raw(SINGLE_ID)["evidence"][0]["locator"])
    out = _diff_ok(capsys, old, new, "--json")
    payload = json.loads(out)
    assert list(payload) == ["counts", "added", "removed", "changed", "ranking"]
    changed = payload["changed"]
    assert len(changed) == 1, changed
    entry = changed[0]
    assert SINGLE_ID in entry.values(), entry
    assert entry["changes"] == [{"field": "sources", "old": old_key, "new": NEW_DOC}]


# ---------------------------------------------------------------------------
# behavior 5 -- an added document lists both keys, after the citations line
# ---------------------------------------------------------------------------

def test_b5_added_second_document_lists_both_keys_after_citations(capsys, tmp_path):
    def mutate(records):
        ev = records[SINGLE_ID]["evidence"]
        ev[0]["locator"] = "https://a.example/x"
        extra = copy.deepcopy(ev[0])
        extra["locator"] = "https://b.example/y"
        ev.append(extra)

    def base_only(records):
        records[SINGLE_ID]["evidence"][0]["locator"] = "https://a.example/x"

    # old side: the same record resting on a.example only
    old_records = {r["id"]: r for r in (_raw(SINGLE_ID), _raw(MULTI_ID))}
    base_only(old_records)
    old = _register(tmp_path / "old", list(old_records.values()))
    new_records = copy.deepcopy(old_records)
    mutate(new_records)
    new = _register(tmp_path / "new", list(new_records.values()))

    document = _diff_ok(capsys, old, new)
    count, body = _changed_section(document)
    assert count == 1, document
    nested = _nested_for(body, SINGLE_ID)
    assert nested[-1] == "  - sources: https://a.example/x -> https://a.example/x, https://b.example/y", nested
    fields = [line[len("  - "):].split(":", 1)[0] for line in nested]
    assert "citations" in fields, nested
    assert fields.index("citations") < fields.index("sources"), nested
    assert fields == [f for f in EXPECTED_FIELDS if f in fields], fields


# ---------------------------------------------------------------------------
# behavior 6 -- prose, order and same-document respelling are NOT changes
# ---------------------------------------------------------------------------

def _prose_only(records):
    ev = records[SINGLE_ID]["evidence"][0]
    ev["title"] = ev["title"] + " (renamed)"
    ev["quote"] = ev["quote"] + " Reworded."
    ev["date"] = "2026-04-12"


def _reverse_order(records):
    records[MULTI_ID]["evidence"].reverse()


def _respell_same_document(records):
    records[SINGLE_ID]["evidence"][0]["locator"] = "https://example.invalid/Original/#renamed-section"


@pytest.mark.parametrize("mutate", [_prose_only, _reverse_order], ids=["prose", "order"])
def test_b6_prose_and_order_are_not_changes(capsys, tmp_path, mutate):
    old, new = _pair(tmp_path, mutate)
    old_bytes = sorted(p.read_bytes() for p in (old / "gaps").iterdir())
    new_bytes = sorted(p.read_bytes() for p in (new / "gaps").iterdir())
    assert old_bytes != new_bytes, "premise: the mutation must actually change a file"
    document = _diff_ok(capsys, old, new)
    count, body = _changed_section(document)
    assert count == 0, document
    assert body == ["None."], body


def test_b6_order_premise_record_has_two_distinct_documents():
    gap = [g for g in load_all(GAPS) if g.id == MULTI_ID][0]
    assert len(scoring.source_documents(gap)) == 2


def test_b6_same_document_respelling_is_not_a_change(capsys, tmp_path):
    def base(records):
        records[SINGLE_ID]["evidence"][0]["locator"] = "https://example.invalid/original"

    old_records = {r["id"]: r for r in (_raw(SINGLE_ID), _raw(MULTI_ID))}
    base(old_records)
    old = _register(tmp_path / "old", list(old_records.values()))
    new_records = copy.deepcopy(old_records)
    _respell_same_document(new_records)
    new = _register(tmp_path / "new", list(new_records.values()))
    document = _diff_ok(capsys, old, new)
    count, body = _changed_section(document)
    assert count == 0, document
    assert body == ["None."], body

    # anti-vacuity: the same base with a DIFFERENT document is reported
    other_records = copy.deepcopy(old_records)
    other_records[SINGLE_ID]["evidence"][0]["locator"] = "https://example.invalid/originals"
    other = _register(tmp_path / "other", list(other_records.values()))
    document = _diff_ok(capsys, old, other)
    count, body = _changed_section(document)
    assert count == 1, document
    assert _nested_for(body, SINGLE_ID) == [
        "  - sources: https://example.invalid/original -> https://example.invalid/originals"]


# ---------------------------------------------------------------------------
# behavior 7 -- --exit-code is unchanged by a sources-only change
# ---------------------------------------------------------------------------

def test_b7_exit_code_sources_only_change_exits_zero_with_same_stdout(capsys, tmp_path):
    old, new = _pair(tmp_path, _swap_only_locator)
    plain = _diff_ok(capsys, old, new)
    rc, out, err = _run(capsys, "diff", "--exit-code", str(old), str(new))
    assert rc == 0, (rc, err)
    assert err == ""
    assert out == plain
    assert "  - sources: " in out


def test_b7_exit_code_still_fires_on_a_removed_record(capsys, tmp_path):
    """Anti-vacuity: --exit-code is armed on the same fixture family."""
    old, new = _pair(tmp_path, _swap_only_locator)
    (next((new / "gaps").glob(f"{MULTI_ID}*.json"))).unlink()
    plain = _diff_ok(capsys, old, new)
    rc, out, err = _run(capsys, "diff", "--exit-code", str(old), str(new))
    assert rc == 1, (rc, err)
    assert out == plain


# ---------------------------------------------------------------------------
# behavior 8 -- identical sides; one trailing newline everywhere
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("flags", [(), ("--json",)], ids=["md", "json"])
def test_b8_committed_register_against_itself_reports_no_change(capsys, flags):
    out = _diff_ok(capsys, REPO_ROOT, REPO_ROOT, *flags)
    if flags:
        assert json.loads(out)["changed"] == []
    else:
        count, body = _changed_section(out)
        assert count == 0 and body == ["None."], body


def test_b8_gaps_dir_form_also_reports_no_change(capsys):
    out = _diff_ok(capsys, GAPS, GAPS)
    count, body = _changed_section(out)
    assert count == 0 and body == ["None."]
