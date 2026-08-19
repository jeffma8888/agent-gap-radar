"""Iteration 20 behaviors: the on-disk record file becomes a documented, braked surface.

The feature under test: `docs/CONSUMER_CONTRACT.md` gains a `## The record file surface`
section that publishes the shape of one `gaps/*.json` record -- the ONE surface the
declared consumer actually reads -- and that section is braked so it cannot quietly lie
about the schema it describes.

ISOLATION CONTRACT HONORED. Nothing in this module reads `src/`, the engineer's notes,
the reviewer's notes, or any diff. Every assertion either reads a PUBLISHED document
(`docs/CONSUMER_CONTRACT.md`, via the shared reader in `tests/_surface_contract.py`),
introspects the PUBLIC models `agent_gap_radar.models.Gap` / `.Evidence` through
`model_fields` and `model_config`, or drives `agent_gap_radar.cli.main` and observes only
its return code and its stdout bytes.

WHERE THE ORACLES COME FROM
* No literal key list is an oracle. Every expected key set is `set(Model.model_fields)`
  and every expected `Required` cell is `model_fields[key].is_required()`, read at test
  time. Iteration 19's tester lesson applies verbatim: a retyped literal is a landmine
  the moment anyone adds a field, and a field ADDED to the schema must red this document
  rather than pass a stale list.
* The table reader is the SHARED one (`_surface_contract.gfm_table`, `GfmTable.column`).
  A second GFM parser one directory over is the duplicated invariant this product has
  paid three times to remove, and it would drift the way the hand-copied table did.
* Every check is proven TWO-SIDED against in-memory MODIFIED COPIES of the real
  document. The tracked file is never edited: `contract_text()` is mutated as a string,
  which is why every known-bad below is a pure function of the shipped bytes.
* Anti-vacuity is asserted, not assumed. An empty key set, a table with zero data rows
  and a deleted or duplicated heading are all required to FAIL rather than to agree with
  an empty expectation.

WHAT THIS MODULE DOES NOT PROVE, STATED RATHER THAN IMPLIED
The consumer-reads table mirrors code in a repository this suite cannot read, so what is
checked is the direction that IS decidable here: every key it names must still exist in
the model it names. The reverse direction -- that the table covers every key the consumer
reads -- is unprovable from this repo and the section says so; it stays a review
obligation. Behavior 8's "no `src/` change, no rendered bytes move" is likewise a
diff-scope claim outside this role's contract, so what is pinned instead is the
observable consequence: the previously published surface still agrees with the parser and
a renderer still ends in exactly one newline.

No network is touched. Nothing under the repo's own `gaps/` register is read to make an
assertion true -- that register is grown by an unattended research pass, so a keyed
expectation over it would go red against a CORRECT register.
"""

from __future__ import annotations

import re

import pytest

from _surface_contract import (CONTRACT_PATH, STABLE_SURFACE_HEADING,
                               SurfaceContractError, contract_text, gfm_table,
                               surface_violations)
from agent_gap_radar.cli import main
from agent_gap_radar.models import Evidence, Gap
from agent_gap_radar.scoring import confidence, priority
from agent_gap_radar.taxonomy import gap_type_names, layer_names

#: Behavior 1 and behaviors 2/3/5: the four headings this iteration publishes.
SECTION_HEADING = "## The record file surface"
GAP_HEADING = "### Gap record keys"
EVIDENCE_HEADING = "### Evidence item keys"
CONSUMER_HEADING = "### Keys the declared consumer reads"
NEW_HEADINGS = (SECTION_HEADING, GAP_HEADING, EVIDENCE_HEADING, CONSUMER_HEADING)

#: Behavior 5: the only two model names a consumer-reads row may name, mapped to the
#: live classes so "names a field that exists in that model" is decidable.
MODELS = {"Gap": Gap, "Evidence": Evidence}

#: The key tables are read by column NAME, which is the column the brake derives.
REQUIRED_COLUMN = "Required"
MODEL_COLUMN = "Model"

#: A first cell holding EXACTLY one backticked key name and nothing else.
_KEY_CELL = re.compile(r"^`([^`\s]+)`$")

#: A consumer-reads data row, recognised by its `| Gap |` / `| Evidence |` second cell.
#: Used only to LOCATE a line to mutate, never to decide whether the document is correct.
_CONSUMER_ROW = re.compile(r"^\|\s*`([^`\s]+)`\s*\|\s*(Gap|Evidence)\s*\|")

#: A name that is deliberately not a field of either model.
ABSENT_KEY = "not_a_field_xyz"

#: Behavior 6: sentences the section must state, normalised so the document's hard wraps
#: cannot make a present claim read as absent.
SECTION_CLAIMS = (
    "gaps/*.json",
    "not renamed and not removed without a Done-ledger row",
    "New fields MAY be added at any time",
    'extra="forbid"',
    "must not be edited to make a rename go green",
    "mirrors code in another repository",
    "the id is the file name's PREFIX",
    "deliberately NOT stored",
    "differing in BOTH class and source document",
)


# --------------------------------------------------------------------------- readers
# These read the document. They raise `SurfaceContractError` for a document whose SHAPE
# defeats the parse and return values otherwise, matching the shared reader's own split
# between "unreadable" and "read, and wrong".


def _normalised(text: str) -> str:
    """Whitespace-collapsed text, so a hard wrap cannot hide a present sentence."""
    return " ".join(text.split())


def heading_count(document: str, heading: str) -> int:
    return sum(1 for line in document.splitlines() if line.strip() == heading)


def documented_keys(document: str, heading: str) -> list[str]:
    """Every data row's first-cell key name under `heading`, in document order."""
    keys: list[str] = []
    for row in gfm_table(document, heading).rows:
        match = _KEY_CELL.fullmatch(row[0])
        if match is None:
            raise SurfaceContractError(
                f"first cell {row[0]!r} under {heading!r} is not exactly one "
                f"backticked key name")
        keys.append(match.group(1))
    return keys


def consumer_pairs(document: str) -> list[tuple[str, str]]:
    """Every (key, model name) pair the consumer-reads table publishes."""
    pairs: list[tuple[str, str]] = []
    table = gfm_table(document, CONSUMER_HEADING)
    keys = documented_keys(document, CONSUMER_HEADING)
    models = table.column(MODEL_COLUMN)
    by_position = tuple(row[1] for row in table.rows)
    if models != by_position:
        # Two readings of the same column disagreeing means the header moved; the spec
        # names the SECOND cell, the brake reads the NAMED column, and a document where
        # those differ is not one both can describe.
        raise SurfaceContractError(
            f"the {MODEL_COLUMN!r} column is not the second cell: named "
            f"{list(models)} vs positional {list(by_position)}")
    for key, model_name in zip(keys, models, strict=True):
        pairs.append((key, model_name))
    return pairs


def section_text(document: str) -> str:
    """The `## The record file surface` section, up to the next level-2 heading."""
    lines = document.splitlines()
    at = [i for i, line in enumerate(lines) if line.strip() == SECTION_HEADING]
    if len(at) != 1:
        raise SurfaceContractError(
            f"heading {SECTION_HEADING!r} occurs {len(at)} time(s), expected 1")
    end = next((j for j in range(at[0] + 1, len(lines))
                if lines[j].startswith("## ")), len(lines))
    return "\n".join(lines[at[0]:end])


# ------------------------------------------------------------------------- violations
# One collector per behavior, each returning a list of messages. Returning rather than
# asserting is what lets the SAME function be pointed at a known-bad copy: a check that
# can only be run against the good document can never be proven two-sided.


def heading_violations(document: str) -> list[str]:
    """Behavior 1, and the exactly-once guard behaviors 2/3/5 depend on."""
    return [f"heading {heading!r} occurs {count} time(s), expected exactly 1"
            for heading in NEW_HEADINGS
            if (count := heading_count(document, heading)) != 1]


def key_set_violations(document: str, heading: str, model: type) -> list[str]:
    """Behaviors 2 and 3: the documented key set EQUALS the model's field set."""
    try:
        keys = documented_keys(document, heading)
    except SurfaceContractError as exc:
        return [str(exc)]
    if not keys:
        return [f"table under {heading!r} documents zero keys"]
    violations: list[str] = []
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        violations.append(f"{heading}: duplicated key row(s) {duplicated}")
    expected = set(model.model_fields)
    if set(keys) != expected:
        violations.append(
            f"{heading}: missing {sorted(expected - set(keys))}, "
            f"unexpected {sorted(set(keys) - expected)}")
    return violations


def required_violations(document: str, heading: str, model: type) -> list[str]:
    """Behavior 4: every `Required` cell is `yes`/`no` and matches `is_required()`."""
    try:
        keys = documented_keys(document, heading)
        required = gfm_table(document, heading).column(REQUIRED_COLUMN)
    except SurfaceContractError as exc:
        return [str(exc)]
    if len(keys) != len(required):
        return [f"{heading}: {len(keys)} key(s) but {len(required)} Required cell(s)"]
    violations: list[str] = []
    for key, cell in zip(keys, required, strict=True):
        if cell not in ("yes", "no"):
            violations.append(
                f"{heading}: {key!r} Required cell is {cell!r}, expected 'yes' or 'no'")
            continue
        field = model.model_fields.get(key)
        if field is None:
            continue  # an invented key is reported once, by key_set_violations
        expected = "yes" if field.is_required() else "no"
        if cell != expected:
            violations.append(
                f"{heading}: {key!r} documents Required={cell!r}, "
                f"the model says {expected!r}")
    return violations


def consumer_violations(document: str) -> list[str]:
    """Behavior 5: every published pair names a field that still exists."""
    try:
        pairs = consumer_pairs(document)
    except SurfaceContractError as exc:
        return [str(exc)]
    if not pairs:
        return ["the consumer-reads table publishes zero key/model pairs"]
    violations: list[str] = []
    for key, model_name in pairs:
        model = MODELS.get(model_name)
        if model is None:
            violations.append(
                f"consumer-reads row {key!r} names model {model_name!r}, "
                f"expected one of {sorted(MODELS)}")
            continue
        if key not in model.model_fields:
            violations.append(
                f"consumer-reads row {key!r} is not a field of {model_name} -- a "
                f"cross-repo break: the declared consumer will read a blank")
    return violations


def closure_violations() -> list[str]:
    """Behavior 6, the half that is about the MODELS rather than the prose."""
    return [f"{name}.model_config['extra'] is "
            f"{model.model_config.get('extra')!r}, expected 'forbid'"
            for name, model in MODELS.items()
            if model.model_config.get("extra") != "forbid"]


def prose_violations(document: str) -> list[str]:
    """Behavior 6, the half that is about the SECTION's own sentences."""
    try:
        section = _normalised(section_text(document))
    except SurfaceContractError as exc:
        return [str(exc)]
    return [f"the section does not state {claim!r}"
            for claim in SECTION_CLAIMS if claim not in section]


def all_violations(document: str) -> list[str]:
    """Every behavior 1-6 check, so one call decides a whole document."""
    return (heading_violations(document)
            + key_set_violations(document, GAP_HEADING, Gap)
            + key_set_violations(document, EVIDENCE_HEADING, Evidence)
            + required_violations(document, GAP_HEADING, Gap)
            + required_violations(document, EVIDENCE_HEADING, Evidence)
            + consumer_violations(document)
            + closure_violations()
            + prose_violations(document))


# --------------------------------------------------------------------------- mutators
# Behavior 7. Every known-bad is built in memory from the shipped bytes, and every
# mutator asserts it located EXACTLY ONE line before changing it -- a mutator that
# silently matched nothing would produce an unmodified copy, and the two-sidedness test
# would then be proving that the good document is good.


def _sole_line(document: str, predicate, what: str) -> tuple[int, str]:
    hits = [(i, line) for i, line in enumerate(document.splitlines())
            if predicate(line)]
    assert len(hits) == 1, f"expected exactly one {what}, found {len(hits)}"
    return hits[0]


def _rows_replaced(document: str, index: int, line: str | None) -> str:
    """The document with line `index` replaced, or dropped when `line` is None."""
    lines = document.splitlines()
    if line is None:
        del lines[index]
    else:
        lines[index] = line
    return "\n".join(lines) + "\n"


def _row_predicate(key: str):
    return lambda line: line.strip().startswith(f"| `{key}` |")


def _table_only_key(document: str, heading: str) -> str:
    """A documented key that appears in exactly one of the three tables.

    Derived rather than named, so a schema change cannot leave this pointing at a key
    that has moved. Choosing a key unique to one table is what makes a plain line match
    unambiguous without a second table parser deciding anything.
    """
    tables = {GAP_HEADING: set(documented_keys(document, GAP_HEADING)),
              EVIDENCE_HEADING: set(documented_keys(document, EVIDENCE_HEADING))}
    consumer = {key for key, _ in consumer_pairs(document)}
    others = set().union(*(keys for name, keys in tables.items() if name != heading))
    candidates = sorted(tables[heading] - others - consumer)
    assert candidates, f"no key is unique to the table under {heading!r}"
    return candidates[0]


def _replace_key_in_table(document: str, heading: str) -> tuple[str, str]:
    key = _table_only_key(document, heading)
    index, line = _sole_line(document, _row_predicate(key), f"{key!r} row")
    return _rows_replaced(document, index, line.replace(f"`{key}`", f"`{ABSENT_KEY}`",
                                                        1)), key


def _delete_row_from_table(document: str, heading: str) -> tuple[str, str]:
    key = _table_only_key(document, heading)
    index, _line = _sole_line(document, _row_predicate(key), f"{key!r} row")
    return _rows_replaced(document, index, None), key


def _flip_required_cell(document: str, heading: str) -> tuple[str, str]:
    key = _table_only_key(document, heading)
    header = gfm_table(document, heading).header
    at = header.index(REQUIRED_COLUMN) + 1  # +1: the leading empty field before `|`
    index, line = _sole_line(document, _row_predicate(key), f"{key!r} row")
    fields = line.split("|")
    was = fields[at].strip()
    assert was in ("yes", "no"), f"{key!r} Required cell is {was!r}, cannot flip it"
    fields[at] = fields[at].replace(was, "no" if was == "yes" else "yes", 1)
    return _rows_replaced(document, index, "|".join(fields)), key


def _without_data_rows(document: str, heading: str) -> str:
    """A copy whose table under `heading` keeps its header and separator only."""
    lines = document.splitlines()
    at = [i for i, line in enumerate(lines) if line.strip() == heading]
    assert len(at) == 1
    cursor = at[0] + 1
    while cursor < len(lines) and not lines[cursor].strip():
        cursor += 1
    start = cursor
    while cursor < len(lines) and lines[cursor].strip().startswith("|"):
        cursor += 1
    assert cursor - start >= 3, "no header+separator+data table under the heading"
    return "\n".join(lines[:start + 2] + lines[cursor:]) + "\n"


# ------------------------------------------------------------------------------ tests


def test_the_tracked_document_passes_every_check_and_the_checks_are_not_empty():
    """Behaviors 1-6 over the shipped bytes, plus the anti-vacuity floor."""
    document = contract_text()
    assert all_violations(document) == []
    # A check whose expectation is an empty set agrees with anything.
    assert len(documented_keys(document, GAP_HEADING)) == len(Gap.model_fields) >= 10
    assert len(documented_keys(document, EVIDENCE_HEADING)) == len(
        Evidence.model_fields) >= 5
    assert len(consumer_pairs(document)) >= 5


@pytest.mark.parametrize("heading", NEW_HEADINGS)
def test_each_published_heading_occurs_exactly_once(heading):
    """Behavior 1, and the guard behaviors 2/3/5 stand on."""
    assert heading_count(contract_text(), heading) == 1


def test_the_gap_table_key_set_equals_the_live_model_fields():
    """Behavior 2: set EQUALITY -- an omitted field and an invented key both fail."""
    document = contract_text()
    assert set(documented_keys(document, GAP_HEADING)) == set(Gap.model_fields)
    assert key_set_violations(document, GAP_HEADING, Gap) == []


def test_the_evidence_table_key_set_equals_the_live_model_fields():
    """Behavior 3."""
    document = contract_text()
    assert set(documented_keys(document, EVIDENCE_HEADING)) == set(
        Evidence.model_fields)
    assert key_set_violations(document, EVIDENCE_HEADING, Evidence) == []


@pytest.mark.parametrize("heading,model", [(GAP_HEADING, Gap),
                                          (EVIDENCE_HEADING, Evidence)])
def test_every_required_cell_matches_is_required_on_the_model(heading, model):
    """Behavior 4, with both answers present so neither is proven by a constant."""
    document = contract_text()
    assert required_violations(document, heading, model) == []
    cells = set(gfm_table(document, heading).column(REQUIRED_COLUMN))
    assert cells <= {"yes", "no"}
    # Derived, not asserted as a literal: these models really do have both kinds of
    # field, so a table of all-`yes` cells could not pass by accident.
    expected = {"yes" if f.is_required() else "no" for f in model.model_fields.values()}
    assert cells == expected


def test_the_consumer_reads_table_names_only_live_fields():
    """Behavior 5, the cross-repo brake."""
    document = contract_text()
    pairs = consumer_pairs(document)
    assert pairs, "an empty pair list would make this brake vacuous"
    assert consumer_violations(document) == []
    for key, model_name in pairs:
        assert model_name in MODELS
        assert key in MODELS[model_name].model_fields


def test_the_closure_guarantee_is_stated_and_actually_holds():
    """Behavior 6: the prose claim and the models are checked in the SAME test."""
    assert Gap.model_config["extra"] == "forbid"
    assert Evidence.model_config["extra"] == "forbid"
    assert closure_violations() == []
    assert prose_violations(contract_text()) == []


def test_the_section_states_the_frozen_text_rule_in_prose():
    """Behavior 6's second half: the do-not-edit-to-go-green rule is written down."""
    section = _normalised(section_text(contract_text()))
    assert "must not be edited to make a rename go green" in section
    assert "mirrors code in another repository" in section


# ----------------------------------------------------------- behavior 7: two-sidedness


def test_a_mutation_helper_that_changes_nothing_would_be_caught():
    """The two-sidedness harness is itself checked: a no-op rebuild is byte-identical."""
    document = contract_text()
    index, line = _sole_line(document, lambda l: l.strip() == GAP_HEADING, "heading")
    assert _rows_replaced(document, index, line) == document


@pytest.mark.parametrize("heading,model", [(GAP_HEADING, Gap),
                                          (EVIDENCE_HEADING, Evidence)])
def test_replacing_a_documented_key_with_an_absent_name_fails(heading, model):
    """Behavior 7a."""
    document = contract_text()
    mutated, key = _replace_key_in_table(document, heading)
    assert mutated != document
    violations = key_set_violations(mutated, heading, model)
    assert violations, f"replacing {key!r} with {ABSENT_KEY!r} was not caught"
    assert any(ABSENT_KEY in message for message in violations)
    assert all_violations(mutated) != []


@pytest.mark.parametrize("heading,model", [(GAP_HEADING, Gap),
                                          (EVIDENCE_HEADING, Evidence)])
def test_deleting_one_data_row_fails(heading, model):
    """Behavior 7b."""
    document = contract_text()
    mutated, key = _delete_row_from_table(document, heading)
    assert mutated != document
    violations = key_set_violations(mutated, heading, model)
    assert violations, f"deleting the {key!r} row was not caught"
    assert any(key in message for message in violations)


@pytest.mark.parametrize("heading,model", [(GAP_HEADING, Gap),
                                          (EVIDENCE_HEADING, Evidence)])
def test_flipping_one_required_cell_fails(heading, model):
    """Behavior 7c."""
    document = contract_text()
    mutated, key = _flip_required_cell(document, heading)
    assert mutated != document
    violations = required_violations(mutated, heading, model)
    assert violations, f"flipping the {key!r} Required cell was not caught"
    assert any(key in message for message in violations)
    # The key-set check is blind to this on purpose; only the Required brake sees it.
    assert key_set_violations(mutated, heading, model) == []


def test_replacing_a_consumer_reads_key_with_a_nonexistent_name_fails():
    """Behavior 7d, the cross-repo brake proven to fire."""
    document = contract_text()
    index, line = _consumer_row_to_break(document)
    mutated = _rows_replaced(document, index,
                            re.sub(r"`[^`\s]+`", f"`{ABSENT_KEY}`", line, count=1))
    assert mutated != document
    violations = consumer_violations(mutated)
    assert violations, "a consumer-reads row naming a dead field was not caught"
    assert any(ABSENT_KEY in message for message in violations)


def _consumer_row_to_break(document: str) -> tuple[int, str]:
    """One consumer-reads data row, located by its `| Evidence |` model cell.

    The `Evidence`-model row is chosen because it is the one whose key cannot also
    appear as a `Gap` row, which keeps the line match unambiguous.
    """
    evidence_keys = [key for key, model_name in consumer_pairs(document)
                     if model_name == "Evidence"]
    assert evidence_keys, "no consumer-reads row names the Evidence model"
    key = sorted(evidence_keys)[0]
    return _sole_line(
        document,
        lambda line: bool(match := _CONSUMER_ROW.match(line.strip()))
        and match.group(1) == key,
        f"consumer-reads row for {key!r}")


@pytest.mark.parametrize("heading", NEW_HEADINGS)
def test_a_deleted_heading_fails_rather_than_passing_vacuously(heading):
    """Behavior 7e, deletion half."""
    document = contract_text()
    index, _line = _sole_line(document, lambda l: l.strip() == heading, "heading")
    mutated = _rows_replaced(document, index, None)
    assert mutated != document
    assert heading_count(mutated, heading) == 0
    violations = all_violations(mutated)
    assert violations, f"deleting {heading!r} was not caught"
    assert any(heading in message for message in violations)


@pytest.mark.parametrize("heading", NEW_HEADINGS)
def test_a_duplicated_heading_fails_rather_than_passing_vacuously(heading):
    """Behavior 7e, duplication half: one whole table would go unexamined."""
    document = contract_text()
    mutated = document + f"\n{heading}\n"
    assert heading_count(mutated, heading) == 2
    violations = all_violations(mutated)
    assert violations, f"duplicating {heading!r} was not caught"
    assert any(heading in message for message in violations)


@pytest.mark.parametrize("heading,model", [(GAP_HEADING, Gap),
                                          (EVIDENCE_HEADING, Evidence)])
def test_a_table_with_zero_data_rows_fails_rather_than_agreeing_with_nothing(
        heading, model):
    """Behavior 7f: the empty-set green is the green that means nothing."""
    document = contract_text()
    mutated = _without_data_rows(document, heading)
    assert mutated != document
    assert key_set_violations(mutated, heading, model) != []
    assert required_violations(mutated, heading, model) != []


def test_a_consumer_reads_table_with_zero_data_rows_fails():
    """Behavior 7f for the third table, whose emptiness is a silent brake removal."""
    mutated = _without_data_rows(contract_text(), CONSUMER_HEADING)
    assert consumer_violations(mutated) != []


# --------------------------------------------- the surfaces this iteration must not move


def test_the_previously_published_stable_surface_still_agrees_with_the_parser():
    """Acceptance: the existing `## The stable surface` behaviour is unchanged."""
    document = contract_text()
    assert surface_violations(document) == []
    assert heading_count(document, STABLE_SURFACE_HEADING) == 1
    # The shared reader's DEFAULT heading must still resolve the old table, or every
    # existing caller has silently moved to a different table.
    assert gfm_table(document).heading == STABLE_SURFACE_HEADING
    assert gfm_table(document).rows


@pytest.mark.parametrize("heading", NEW_HEADINGS)
def test_no_new_heading_spells_a_radar_verb_in_backticks(heading):
    """Acceptance: iteration 16's heading brake is lexical over exactly that shape."""
    assert "`radar " not in heading


def test_a_renderer_still_ends_in_exactly_one_newline(capsys):
    """Acceptance, observable half: a doc-only change moves no rendered bytes."""
    assert main(["taxonomy"]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert not out.endswith("\n\n")
# ------------------------------------- the section's declarative claims, EXECUTED
# A doc-only diff has no compiler, so a sentence nobody ran is a sentence nobody
# reviewed. Each test below turns one claim of the new section into a probe against the
# live code or the tracked register, so the document cannot merely be self-consistent.

REPO_ROOT = CONTRACT_PATH.parent.parent
REGISTER_DIR = REPO_ROOT / "gaps"


def _record(**overrides):
    """A minimal VALID record, vocabulary read from the public taxonomy.

    `layer_names()[0]` and `gap_type_names()[0]` rather than retyped strings: a closed
    vocabulary that is edited must not red this module for a reason it is not about.
    """
    fields = dict(id="GAP-999", title="a gap", layer=layer_names()[0],
                  gap_type=gap_type_names()[0], problem="p", symptom="s", why_now="w",
                  severity=3, frequency=3, tractability=3,
                  evidence=[_evidence("https://example.invalid/a")])
    fields.update(overrides)
    return Gap.model_validate(fields)


def _evidence(locator: str, source_class: str = "vendor-primary") -> dict:
    return dict(source_class=source_class, title="a source", locator=locator,
                date="2026-01-01", quote="a verbatim excerpt")


def test_the_two_derived_scores_are_not_stored_keys_as_the_section_claims():
    """Claim: `priority` and `confidence` are deliberately NOT stored."""
    assert "priority" not in Gap.model_fields
    assert "confidence" not in Gap.model_fields
    assert "deliberately NOT stored" in _normalised(section_text(contract_text()))


def test_the_id_is_the_prefix_of_every_tracked_record_file_name():
    """Claim: records are stored at `gaps/<ID>-<slug>.json`, id being the PREFIX.

    Asserted as a STRUCTURAL property over whatever the register holds -- never as a
    count or an id census -- so the unattended research pass that grows `gaps/` cannot
    red this over a CORRECT register, while a wrongly-named file, which breaks the
    documented layout the declared consumer globs, does red it.
    """
    import json

    files = sorted(REGISTER_DIR.glob("*.json"))
    assert files, "no tracked record files, so this claim would pass vacuously"
    offenders = [file.name for file in files
                 if not file.name.startswith(
                     json.loads(file.read_text(encoding="utf-8"))["id"] + "-")]
    assert offenders == []


def test_priority_is_computed_from_exactly_the_three_documented_integers():
    """Claim: severity, frequency and tractability are the WHOLE input to `priority`."""
    base = priority(_record())
    # Every other stored field moved at once: the score must not notice.
    assert priority(_record(status="open", tags=["t"], existing=["e"],
                            build_hypothesis="h", title="a different title")) == base
    # And each documented input must actually move it, or the claim is half true.
    assert priority(_record(severity=5)) != base
    assert priority(_record(frequency=5)) != base
    assert priority(_record(tractability=5)) != base


def test_confidence_needs_two_source_documents_not_two_labels_on_one_url():
    """Claim: corroboration requires citations differing in BOTH class and document."""
    one = _record(evidence=[_evidence("https://a.invalid/p")])
    same_document = _record(evidence=[_evidence("https://a.invalid/p"),
                                      _evidence("https://a.invalid/p",
                                                "practitioner-report")])
    two_documents = _record(evidence=[_evidence("https://a.invalid/p"),
                                      _evidence("https://b.invalid/q",
                                                "practitioner-report")])
    assert confidence(same_document) == confidence(one), (
        "two labels on one URL earned a corroboration point")
    assert confidence(two_documents) > confidence(one)


def test_a_record_whose_only_rung_is_model_output_carries_confidence_zero():
    """Claim: `model-output` alone carries confidence 0 BY CONSTRUCTION."""
    only = _record(evidence=[_evidence("https://c.invalid/r", "model-output")])
    doubled = _record(evidence=[_evidence("https://c.invalid/r", "model-output"),
                                _evidence("https://d.invalid/s", "model-output")])
    assert confidence(only) == 0
    assert confidence(doubled) == 0, "two zero-weight rungs corroborated each other"
    # Two-sided: the same shape with a weighted rung is NOT zero, so the assertion
    # above is not passing because `confidence` returns 0 for everything.
    assert confidence(_record(evidence=[_evidence("https://c.invalid/r")])) > 0
