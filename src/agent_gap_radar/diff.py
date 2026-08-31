"""What changed between two register states.

WHY THIS EXISTS
The register is grown by a schedule rather than by hand, and until now no artifact
anywhere said what a pass changed. `README.md` already sells deterministic output
"so a report can be committed and diffed", while the register's own change history
was unreviewable -- and this loop has already paid for that once: a research pass
wrote a new record, a live-register assertion went red, and the iteration was spent
on the mystery instead of on the test.

WHY THE COMPARED FIELD SET IS CLOSED
Every field in `COMPARED_FIELDS` is a closed-vocabulary string, a bounded integer,
or a value DERIVED by `scoring`. That is the property that keeps this verb a change
report rather than a prose review: free text (`title`, `problem`, `symptom`,
`why_now`, `existing`, `build_hypothesis`, `tags`, `check`, and the text of a
citation) is deliberately never compared, because a diff that reports rewording
buries the one change that matters.

WHY `severity`, `frequency` AND `tractability` ARE COMPARED SEPARATELY FROM `priority`
`priority` is a weighted sum (3/2/1), so it can MASK a change in its own inputs: a
record losing one `frequency` point and gaining two `tractability` points has an
identical priority. Reporting only the derived number would call that record
unchanged.

WHY THE DERIVED NUMBERS ARE CALLED, NEVER RE-DERIVED
`priority` and `confidence` come from `scoring.priority()` / `scoring.confidence()`.
Re-implementing either arithmetic here would let this report disagree with every
other view of the same record, and `confidence` in particular is the register's core
invariant: derived from the evidence ladder, never asserted.

Pure by contract: no file is read, no clock is consulted, nothing is written. The
caller loads both sides through `registry.load_all`, which is also the only
duplicate-id gate -- this module deliberately does not carry a second one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Gap
from .render import document, json_document
from .scoring import confidence, priority

#: The compared fields, in the ONE order the report emits them. A single tuple
#: rather than a per-section decision, so the nested lines of every changed record
#: read in the same order and two runs cannot order them differently.
COMPARED_FIELDS: tuple[str, ...] = (
    "status",
    "layer",
    "gap_type",
    "severity",
    "frequency",
    "tractability",
    "priority",
    "confidence",
    "citations",
)


@dataclass(frozen=True, slots=True)
class RecordRef:
    """A record named in the Added or Removed section: its id and its title."""

    gap_id: str
    title: str


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One compared field that differs, with both sides already formatted."""

    field: str
    old: str
    new: str


@dataclass(frozen=True, slots=True)
class RecordChange:
    """A record present on both sides with at least one differing compared field."""

    gap_id: str
    changes: tuple[FieldChange, ...]


@dataclass(frozen=True, slots=True)
class RegisterDiff:
    """The whole comparison, ready to render and inspectable by a test.

    Carries both domain SIZES, not just the differences. A moved, emptied or
    one-level-too-high OLD path otherwise reads as "every record was added", and a
    count is what lets a reader see that instead of inferring it.
    """

    old_count: int
    new_count: int
    added: tuple[RecordRef, ...]
    removed: tuple[RecordRef, ...]
    changed: tuple[RecordChange, ...]


def record_facts(gap: Gap) -> dict[str, str]:
    """Every compared field of one record, formatted as it will be printed.

    Formatting happens HERE, before comparison, so a difference is exactly a string
    inequality and the value a reader sees is the value that was compared. The
    alternative -- compare raw, format later -- lets two values that print
    identically be reported as a change, which is the shape a reader cannot check.

    `citations` is the COUNT of a record's evidence, never its text: a dropped or
    added citation moves `confidence`, and that is the corruption worth seeing.
    """
    return {
        "status": gap.status,
        "layer": gap.layer,
        "gap_type": gap.gap_type,
        "severity": str(gap.severity),
        "frequency": str(gap.frequency),
        "tractability": str(gap.tractability),
        # One decimal, matching every other view of a priority in this product.
        "priority": f"{priority(gap):.1f}",
        "confidence": str(confidence(gap)),
        "citations": str(len(gap.evidence)),
    }


def _changes(old: Gap, new: Gap) -> tuple[FieldChange, ...]:
    """Differing compared fields of one record, in `COMPARED_FIELDS` order.

    Iterates the constant rather than the fact dict, so the emitted order is owned
    by one declaration instead of by a dict literal's layout.
    """
    old_facts, new_facts = record_facts(old), record_facts(new)
    return tuple(
        FieldChange(field, old_facts[field], new_facts[field])
        for field in COMPARED_FIELDS
        if old_facts[field] != new_facts[field]
    )


def diff_registers(old: list[Gap], new: list[Gap]) -> RegisterDiff:
    """Compare two loaded registers. Pure, and ordered by id on every axis.

    Ordering by id is what makes the report independent of the FILENAMES records
    happen to be stored under: `registry.load_all` walks a directory in filename
    order, so a renamed file changes the input order, and a report that inherited it
    would differ for two identical registers.
    """
    old_by_id = {gap.id: gap for gap in old}
    new_by_id = {gap.id: gap for gap in new}

    added = tuple(RecordRef(gap_id, new_by_id[gap_id].title)
                  for gap_id in sorted(new_by_id.keys() - old_by_id.keys()))
    removed = tuple(RecordRef(gap_id, old_by_id[gap_id].title)
                    for gap_id in sorted(old_by_id.keys() - new_by_id.keys()))

    changed: list[RecordChange] = []
    for gap_id in sorted(old_by_id.keys() & new_by_id.keys()):
        field_changes = _changes(old_by_id[gap_id], new_by_id[gap_id])
        if field_changes:
            changed.append(RecordChange(gap_id, field_changes))

    return RegisterDiff(
        old_count=len(old),
        new_count=len(new),
        added=added,
        removed=removed,
        changed=tuple(changed),
    )


def _section(heading: str, record_count: int, body: list[str]) -> list[str]:
    """One always-present section: a counted heading and a body that is never empty.

    `record_count` is passed rather than measured from `body` because the Changed
    section's body carries nested lines too, so its line count is not its record
    count. A section with nothing to report says `None.` instead of being omitted,
    so "nothing changed" stays distinguishable from "the tool did not look".
    """
    return [f"## {heading} ({record_count})", ""] + (body or ["None."]) + [""]


def render_diff(diff: RegisterDiff) -> str:
    """The markdown change report. Deterministic, ending in exactly one newline.

    `priority` and `confidence` are emitted as two separate nested lines and never
    combined: a blended figure here would launder the one distinction the register
    exists to preserve, in the very document a reviewer reads to approve a change.
    """
    lines: list[str] = [
        "# Register diff",
        "",
        f"Old: {diff.old_count} record(s). New: {diff.new_count} record(s).",
        "",
    ]
    lines += _section(
        "Added", len(diff.added),
        [f"- {ref.gap_id}  {ref.title}" for ref in diff.added])
    lines += _section(
        "Removed", len(diff.removed),
        [f"- {ref.gap_id}  {ref.title}" for ref in diff.removed])

    changed_body: list[str] = []
    for record in diff.changed:
        changed_body.append(f"- {record.gap_id}")
        changed_body += [f"  - {change.field}: {change.old} -> {change.new}"
                         for change in record.changes]
    lines += _section("Changed", len(diff.changed), changed_body)

    return document(lines)


def _ref_json(ref: RecordRef) -> dict[str, str]:
    """One Added/Removed entry. Its id AND its title, matching the markdown line.

    The title is carried even though a gate keys on the id: a consumer reporting a
    reintroduced gap has to name it to a human, and the alternative -- a second
    `radar show` call per id, across a repo boundary -- is a second read of a
    register that may already have moved.
    """
    return {"gap_id": ref.gap_id, "title": ref.title}


def diff_json(diff: RegisterDiff) -> str:
    """The comparison as a stable object for a machine consumer (a CI gate).

    WHY THIS EXISTS SEPARATELY FROM `render_diff`
    `docs/CONSUMER_CONTRACT.md` binds a consumer to gate on non-regression -- "the
    diff did not reintroduce a known gap" -- and until now `render_diff` was this
    verb's only surface. A gate that regex-scrapes prose breaks the first time a
    heading is reworded, so half of a rule this product publishes across a repo
    boundary had no surface any test here could protect.

    PURE OVER THE DATACLASS, AND THAT IS THE POINT
    Nothing is re-read and nothing is re-derived: every value is already inside
    `RegisterDiff`, which took `priority` and `confidence` from `scoring`. A
    serializer that recomputed either would give this payload a second opinion about
    the register's core invariant, and it could then disagree with the markdown
    report emitted from the same comparison.

    WHY EVERY `old`/`new` IS A STRING
    `record_facts` formats before comparing, so the values a `FieldChange` carries
    ARE the compared strings. Parsing `"8.3"` back to a float here would re-derive a
    number this module deliberately does not own, and it would type one field
    differently from its eight siblings -- a consumer switching on `field` would then
    need a per-field type table. The payload reports what was compared.

    NO BLENDED SCORE, ASSERTED BY ABSENCE OF THE KEY
    `priority` and `confidence` appear as two distinct `field` entries, exactly as
    the markdown emits them, and no object at any depth carries a composite `score`.
    Laundering the two into one figure here would erase the one distinction the
    register exists to preserve, on the surface a gate reads automatically -- where
    no human sees it happen.
    """
    payload = {
        # Both domain SIZES first, for the reason `RegisterDiff` carries them: an
        # emptied or one-level-too-high OLD path otherwise reads as "every record
        # was added", and a gate keyed on `added` would fire on a path typo.
        "counts": {"old": diff.old_count, "new": diff.new_count},
        "added": [_ref_json(ref) for ref in diff.added],
        "removed": [_ref_json(ref) for ref in diff.removed],
        "changed": [
            {
                "gap_id": record.gap_id,
                # `COMPARED_FIELDS` order, inherited from `_changes` rather than
                # re-sorted here, so the payload and the markdown list one record's
                # fields in the same order and neither owns a second opinion.
                "changes": [
                    {"field": change.field, "old": change.old, "new": change.new}
                    for change in record.changes
                ],
            }
            for record in diff.changed
        ],
    }
    # One published tail for every `--json` surface: `render.json_document` owns the
    # indent, the INSERTION key order and the single trailing newline, so the key
    # sequence above is the published one and this verb cannot drift from
    # `scan --json` or `list --json` by carrying its own copy of the expression.
    return json_document(payload)
