"""The published document renderers -- Markdown AND JSON. Output is deterministic
and ends in exactly one newline.

Both document kinds live here for one reason: the one-newline tail is a published
guarantee, so a second home for it would be a second implementation of it. See
`document` for the Markdown tail and `json_document` for the JSON tail.
"""

from __future__ import annotations

import json

from .models import Check, Gap, detectability
from .scoring import (aged_records, below_floor, confidence, distinct_register_sources,
                      distinct_sources, priority, promotion_options, rank,
                      records_on_shared_source, register_anchor_date, shared_sources,
                      sole_source_records, strongest_source)
from .taxonomy import LAYERS, SOURCE_WEIGHTS


def document(lines: list[str]) -> str:
    """Join to a document ending in exactly one newline.

    Section builders append a trailing "" as a separator, which would otherwise
    render as a blank final line. Normalising here keeps every renderer's
    contract identical instead of making each one remember.

    PUBLIC, and deliberately so: the one-newline rule is a published guarantee, so
    a renderer living in another module has to reach the same implementation rather
    than carry a second copy of it. Two independently written copies of one
    invariant is the shape this product has already had to fix twice -- the
    below-floor predicate and the strongest-source ordering -- where the rule held
    only while the copies happened to agree.
    """
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def json_document(obj: object) -> str:
    """Serialise to a JSON document ending in exactly one newline.

    PUBLIC, and the JSON sibling of `document` for exactly the reason that docstring
    argues against this repo: one invariant, one implementation. This expression had
    FOUR copies -- one per machine surface: the three `--json` verbs, plus the prd
    document that `radar prd` and `radar scan --prd` both emit -- and it ratcheted by one every time a new
    machine surface shipped, because the census that proves the MARKDOWN tail has a
    single implementation keys on the pop-the-blank-line prelude, which no
    `json.dumps` line can carry. So the guarantee was proven on one surface and
    unmeasured on the four that `docs/CONSUMER_CONTRACT.md` points a CI gate at.

    KEYS ARE NEVER SORTED. `sort_keys=False` is spelled out even though it is
    `json.dumps`'s own default, because it is the guarantee rather than an accident:
    every payload here publishes its keys in INSERTION order, so the sequence a
    caller writes is the sequence a consumer reads. Alphabetising them would silently
    reorder a published surface, and a consumer diffing two committed artifacts would
    see a field move for no reason in the register.

    `indent=2` matches the register's own on-disk records, so an emitted payload stays
    line-oriented and diffs against a committed artifact one field at a time.
    """
    return json.dumps(obj, indent=2, sort_keys=False) + "\n"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Markdown table lines: the header, the alignment rule, then one line per row.

    PUBLIC for the same reason as `document`, and said here rather than left to be
    inferred: a renderer living in another module has to reach this implementation
    rather than carry a second copy of the pipe-and-dash formatting. `scan.py` built
    its verdict table by hand until iteration 14 -- the same duplicated-invariant
    shape this product has already paid to fix twice, where the two copies agreed
    only by luck.
    """
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def _needs_cell(gap: Gap, confidence_floor: int) -> str:
    """One below-floor row's research prescription: what to go and find.

    Leads with the ladder weight so the reader can see WHY those classes are the
    cheapest option rather than taking the list on trust. Every option shares one
    weight by construction, so the first one's weight speaks for the group. An
    unreachable floor says so instead of rendering an empty cell, which would
    read as "nothing needed".
    """
    options = promotion_options(gap, confidence_floor)
    if not options:
        return f"no single citation reaches floor {confidence_floor}"
    return f"weight >= {SOURCE_WEIGHTS[options[0]]}: " + ", ".join(options)


#: Behavior 3's purpose line, verbatim, and the sentence that decides how a reader
#: is meant to act on this table. It says CHECK rather than delete or refresh because
#: the cheap way to clear an age threshold is to staple a recent link onto a sound
#: record, which improves the number and degrades the evidence ladder the whole
#: register is built on.
EVIDENCE_AGE_PURPOSE = (
    "An old citation is not a closed gap: evidence for a durable property does not "
    "weaken with age. This says where to go and CHECK, not what to delete and not "
    "what to pad with a fresher link.")

#: The anchor sentence. It publishes the anchor DATE and the reason it is not a clock
#: read, in the rendered document rather than only in a docstring: a reader comparing
#: two committed reports has to be able to tell an age that moved because evidence
#: changed from one that moved because time passed.
_EVIDENCE_AGE_ANCHOR = (
    "Ages are measured against {anchor}, the newest citation date in this register, "
    "so the same register always renders the same bytes; no clock is read.")

EVIDENCE_AGE_HEADING = "## Evidence age"


def _evidence_age_section(gaps: list[Gap]) -> list[str]:
    """The `## Evidence age` block: where this register's own evidence has gone quiet.

    WHY IT EXISTS. `Evidence.date` is required and ISO-validated on every citation and
    was read by nothing that aggregates or compares -- the live register carries 402
    citation dates and published none of them as a number. The consequence is the exact
    failure this section surfaces: the register can tell a builder, at the top of its
    own ranking, to work on a gap whose newest citation is more than a year old and
    whose own `status` field already says the industry has partly moved.

    A DISPLAY AND NOTHING MORE. No record is dropped, hidden or de-ranked by its age,
    and no age term reaches `priority`, `confidence`, `rank` or `below_floor`. The
    heading and both numeric column labels state facts -- `Newest citation`, `Age
    (days)` -- rather than a verdict, deliberately: a judgement word invites the wrong
    repair, and the never-drop rule this register protects applies to age exactly as it
    applies to a weak source class.

    THE EMPTY REGISTER renders the heading and `None found.` with NO anchor line. With
    zero records there is no citation to anchor on, so an anchor line there would have
    to invent a date -- and "no age is knowable" is a different statement from "nothing
    is old", which is why the two cases do not share their prose.
    """
    lines = [EVIDENCE_AGE_HEADING, ""]
    anchor = register_anchor_date(gaps)
    if anchor is None:
        lines += ["None found.", ""]
        return lines
    lines += [_EVIDENCE_AGE_ANCHOR.format(anchor=anchor), "",
              EVIDENCE_AGE_PURPOSE, ""]
    rows = aged_records(gaps)
    if rows:
        lines += table(["ID", "Newest citation", "Age (days)", "Title"],
                       [[gap.id, newest, str(age), gap.title]
                        for gap, newest, age in rows])
    else:
        # Same convention as `## Ranked gaps` and `## Below confidence floor`: an
        # empty result says so in words. A heading followed by nothing reads as a
        # renderer that failed rather than a register that is well maintained.
        lines.append("None found.")
    lines.append("")
    return lines


#: Behavior 2's census line. ONE template, so the two halves of the sentence cannot
#: drift apart, and PLURAL-FREE by construction: every noun is written for the count it
#: will never agree with, so no value of A, B, C or D changes the grammar. `_plural`
#: exists one screen down for the per-record line that DOES inflect; this line is
#: deliberately not built from it, because a census read by a diff should not change
#: shape when a count crosses 1.
_SOURCE_CENSUS = (
    "Sources cited by more than one record: {shared} of {sources} | records resting on "
    "a shared source: {resting} of {records}")

#: Behavior 5's line, verbatim up to the ids. The parenthetical is the whole reason the
#: line is worth printing: it names the CONSEQUENCE (one retraction voids the record's
#: entire basis) rather than labelling the record weak, because a single-source record
#: is a research task and this register never de-ranks one.
_SOLE_SOURCE_PREFIX = (
    "Records resting on exactly one distinct source (a single retraction voids the whole "
    "evidentiary basis of each): ")

#: The purpose line, and the sentence that decides how a reader is meant to act on the
#: table. It says a shared source is NOT a fault on purpose: with few primary sources in
#: a young field, the cheap way to "improve" a concentration number is to stop citing the
#: best available document, which degrades the evidence ladder the whole register rests
#: on. So the line states a fact, names the one actionable case, and explicitly refuses
#: to be read as a number to drive down -- the same refusal `## By layer`'s purpose line
#: makes about its zeros.
SOURCE_CONCENTRATION_PURPOSE = (
    "A shared source is not a fault -- a young field has few primary sources -- and "
    "nothing here derives a penalty: no count in this section reaches priority, "
    "confidence, the ranking or the floor, and none of them is a number to drive down. "
    "The actionable case is a record resting on ONE source, whose entire evidentiary "
    "basis a single retraction voids.")

SOURCE_CONCENTRATION_HEADING = "## Source concentration"


def _source_concentration_section(gaps: list[Gap]) -> list[str]:
    """The `## Source concentration` block: how independent this register actually is.

    WHY IT EXISTS. `confidence()` grants its corroboration point only for two citations
    differing in both class and SOURCE -- one document cited twice is not independent
    evidence -- and `radar show` publishes that denominator per record. Across records
    the same rule is neither enforced nor published, so a reader of a 120-row ranking
    cannot tell whether it rests on 120 documents or on a handful: measured on the
    register as this shipped, 61 of 167 distinct sources carry more than one record and
    the largest single source carries 13. The invitation to read N records as N
    independent findings is what this section removes, using evidence already stored.

    A DISPLAY AND NOTHING MORE. No record is dropped, hidden or de-ranked by how it is
    sourced, and no term here reaches `priority`, `confidence`, `rank` or `below_floor`.
    Every qualifying source is listed with NO cap: truncating the table would be the
    silent-drop shape `VISION.md` names as the one rule this register protects, and the
    long tail is exactly where a reader finds the source they had not noticed twice.

    THE EMPTY REGISTER renders the heading and `None found.` with nothing else -- no
    census, no purpose line, no sole-source line -- mirroring `_evidence_age_section`'s
    anchor-less case for the same reason: with no citations "no source is knowable" is a
    different claim from "nothing is shared", so the two cases do not share their prose.
    """
    lines = [SOURCE_CONCENTRATION_HEADING, ""]
    if not gaps:
        lines += ["None found.", ""]
        return lines
    # Computed ONCE and read three times below. `records_on_shared_source` derives its
    # answer from this same function rather than from a second predicate, so the census
    # count and the table under it agree by construction rather than by review.
    shared = shared_sources(gaps)
    lines += [_SOURCE_CENSUS.format(shared=len(shared),
                                    sources=distinct_register_sources(gaps),
                                    resting=len(records_on_shared_source(gaps)),
                                    records=len(gaps)), "",
              SOURCE_CONCENTRATION_PURPOSE, ""]
    if shared:
        lines += table(["Source", "Records", "IDs"],
                       [[key, str(len(ids)), ", ".join(ids)] for key, ids in shared])
    else:
        # Same convention as every other section here: an empty result says so in words,
        # because a heading followed by nothing reads as a renderer that failed rather
        # than as a register whose sources happen not to overlap.
        lines.append("None found.")
    lines.append("")
    sole = sole_source_records(gaps)
    lines += [_SOLE_SOURCE_PREFIX + (", ".join(gap.id for gap in sole)
                                     if sole else "none."), ""]
    return lines


def radar_report(gaps: list[Gap], confidence_floor: int = 2) -> str:
    """The ranked landscape view."""
    ranked = rank(gaps, confidence_floor)
    excluded = below_floor(gaps, confidence_floor)

    lines: list[str] = ["# Agent infrastructure gap radar", ""]
    lines += [f"Records: {len(gaps)} | ranked: {len(ranked)} | "
              f"below confidence floor ({confidence_floor}): {len(excluded)}", ""]

    lines += ["## Ranked gaps", ""]
    if ranked:
        lines += table(
            ["Rank", "ID", "Priority", "Confidence", "Layer", "Type", "Title"],
            [[str(i), g.id, f"{p:.1f}", str(c), g.layer, g.gap_type, g.title]
             for i, (g, p, c) in enumerate(ranked, start=1)])
    else:
        lines.append("None found.")
    lines.append("")

    lines += ["## By layer", "",
              "Every layer in the closed taxonomy is listed on purpose: a zero "
              "means the layer is unexamined, not that it is clean -- it is not "
              "a target to fill.", ""]
    counts = {layer: 0 for layer in LAYERS}
    for g in gaps:
        counts[g.layer] += 1
    # No `if n` filter here, and its absence is the feature: dropping zero-count
    # layers made "this layer is clean" and "nobody has looked at this layer"
    # render as identical bytes, which is the silent-drop shape `VISION.md` names
    # as the one rule this register protects. Publishing the denominator is the
    # whole point of a coverage view, so the purpose line above ships WITH the
    # zeros -- a bare zero invites the fill-every-layer throughput reading that
    # `docs/CONSUMER_CONTRACT.md` forbids by name.
    lines += table(["Layer", "Records"],
                   [[layer, str(n)] for layer, n in counts.items()])
    lines.append("")

    lines += _evidence_age_section(gaps)
    lines += _source_concentration_section(gaps)

    lines += ["## Below confidence floor", "",
              "Kept visible on purpose: a weakly-sourced gap is a research task, "
              "not a deletion.", ""]
    if excluded:
        lines += table(["ID", "Priority", "Confidence", "Title",
                        "Strongest source", "Needs"],
                       [[g.id, f"{p:.1f}", str(c), g.title,
                         strongest_source(g),
                         _needs_cell(g, confidence_floor)]
                        for g, p, c in excluded])
    else:
        lines.append("None found.")
    lines.append("")
    return document(lines)


#: One deterministic sentence per `DETECTABILITY_KINDS` value, saying what `radar
#: scan` will DO with a record. Deliberately NOT shared with
#: `prd.DETECTABILITY_DECLARATIONS`, which answers a different question over the same
#: key -- what the register holds towards REPRODUCING the gap inside a build loop --
#: so neither surface has to hedge to serve the other's reader. The CLASSIFIER is
#: shared (`models.detectability`) and the prose is per-surface;
#: `tests/test_detectability_unit.py` pins both dicts to the same closed vocabulary,
#: so a fourth kind cannot be answered by only one of the two surfaces.
DETECTION_STATEMENTS: dict[str, str] = {
    "automated": (
        "The register holds a static signature for this gap, so `radar scan` "
        "evaluates this record against a target and returns a verdict for it."),
    "manual": (
        "The register holds no static signature for this gap, so `radar scan` "
        "reports MANUAL by declaration rather than guessing."),
    "none": (
        "The register holds no check for this gap at all, so `radar scan` never "
        "applies this record and counts it among the gaps with no check yet."),
}

#: The rule slots a check may declare, in the order `checks.run_check` reads them:
#: `applies_when` gates the check, `present_when` can yield PRESENT, `mitigated_when`
#: is the only thing that can yield ABSENT. Naming the slots a record actually
#: declares is a fact about the record; what each one BUYS is the contract's job, so
#: this renderer states neither a judgement nor a second copy of the decision table.
_RULE_SLOTS: tuple[str, ...] = ("applies_when", "present_when", "mitigated_when")


def _detection_section(gap: Gap) -> list[str]:
    """The `## Detection` block: what the register holds to find this gap in a target.

    WHY IT EXISTS: `radar scan` returns a verdict only for a record carrying a rule,
    and over the live 16 records four carry none (three manual-only plus one with no
    check at all) -- yet this brief, the deep view a reader consults BEFORE starting
    work, rendered nothing from `gap.check`, so a record `scan` can never verdict read
    exactly like one it can. `scan.py` already publishes the count, but only to
    someone who already has a target to scan.

    The check id is printed because it is NOT derivable from the gap id: six of the
    sixteen live records are off by one (GAP-011 carries CHK-010), so a reader
    cross-referencing a scan finding back to a record cannot guess it.

    DECLARATION, never a judgement: the kind comes from `models.detectability`, the
    sentence from the closed `DETECTION_STATEMENTS` vocabulary, and the rule line
    names the slots the check declares without rating them. Nothing here can move
    `priority` or `confidence`.

    The last bullet is the ONE exception to "derived words only", and it is the reason
    the block is worth reading: `Check.rationale` is authored register prose saying WHY
    the signature indicates the gap, published verbatim. It is the block's own
    counterweight -- a derived `automated` reads as authority, and the rationale is
    where the check admits what it can get wrong.
    """
    check = gap.check
    kind = detectability(check)
    lines = ["## Detection", ""]
    if check is None:
        lines.append(f"- Check: none declared (detectability `{kind}`)")
    else:
        lines.append(f"- Check: `{check.id}` (detectability `{kind}`)")
    lines.append(f"- {DETECTION_STATEMENTS[kind]}")
    if check is not None:
        declared = _declared_rules(check)
        if declared:
            lines.append("- Rules declared: " + ", ".join(declared))
        if kind == "manual":
            # Keyed on the DERIVED kind, NEVER on `declared` being empty -- those are
            # different questions. `Check.is_automated` reads only `present_when`/
            # `mitigated_when`, so a check declaring `applies_when` alone is
            # schema-legal, LOADS, and classifies `manual` while `_declared_rules`
            # returns a NON-EMPTY list; an `else` here dropped the manual question,
            # the only actionable payload such a record carries.
            # The field is guaranteed non-empty for a manual check -- `Check`'s own
            # `_automated_checks_need_fixtures` refuses to LOAD one without it -- so
            # this reads an enforced invariant rather than guarding an empty string.
            # Rendered ONLY here, matching `prd._check_payload`: on an automated
            # check the same field is `scan`'s both-signatures escalation question,
            # which is a different job.
            lines.append(f"- Question a human must answer: {check.manual_question}")
        # LAST bullet of the block, and the only one that publishes authored register
        # prose rather than a derived word. Everything above states THAT a signature
        # exists; `rationale` is the sentence saying WHY it indicates the gap and what
        # it can get wrong, which is what a reader needs before trusting a verdict --
        # and it was the largest authored field in the register that no surface read.
        # VERBATIM: no wrap, no reflow, no truncation, and no re-quoting. The register
        # holds up to 1,206 characters here (GAP-032) and a reader who cannot see all
        # of it cannot audit the check. `Check._rationale_is_one_line` is what makes a
        # bare interpolation safe -- it refuses a value that would break this bullet.
        # DISPLAYED when empty, never omitted: an absent rationale is a fact about the
        # register, and a silently missing bullet reads as "this check is explained"
        # to anyone who does not diff two records. `.strip()` rather than truthiness
        # because the whitespace rule lives on the OTHER door: today the guard makes
        # `"   "` unloadable so the two agree, and if that guard is ever relaxed this
        # branch must still publish the absence instead of emitting a blank value.
        if check.rationale.strip():
            lines.append(f"- Rationale: {check.rationale}")
        else:
            lines.append("- Rationale: none recorded")
    lines.append("")
    return lines


def _declared_rules(check: Check) -> list[str]:
    """Each declared rule slot as `slot` (kind), in `_RULE_SLOTS` order.

    NOT a proxy for the automated/manual predicate, and the caller must not read it
    as one. `applies_when` is a rule slot that `Check.is_automated` does NOT read,
    so a check declaring `applies_when` alone is schema-legal, loads, classifies
    `manual`, and returns a NON-EMPTY list here -- measured through
    `Gap.model_validate`, which accepts that shape. The caller therefore keys the
    manual question on `models.detectability`; an earlier revision keyed it on this
    list being empty and silently dropped the question for exactly that record.
    """
    out: list[str] = []
    for slot in _RULE_SLOTS:
        rule = getattr(check, slot)
        if rule is not None:
            out.append(f"`{slot}` ({rule['kind']})")
    return out


def _plural(count: int, noun: str) -> str:
    """`<count> <noun>`, the noun pluralised against THAT count and no other.

    A function over one number so the two nouns in the evidence denominator
    cannot share a flag: GAP-015's live shape is `3 citations across 1 distinct
    source document`, and a single `if n == 1` covering both halves renders it
    wrong in precisely the case the line exists to expose.
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def gap_brief(gap: Gap) -> str:
    """The single-gap deep view: everything a builder needs to act on it."""
    lines = [f"# {gap.id}: {gap.title}", ""]
    lines += table(["Field", "Value"], [
        ["Layer", f"{gap.layer} -- {LAYERS[gap.layer]}"],
        ["Gap type", gap.gap_type],
        ["Status", gap.status],
        ["Priority", f"{priority(gap):.1f}"],
        ["Confidence", str(confidence(gap))],
        ["Severity / Frequency / Tractability",
         f"{gap.severity} / {gap.frequency} / {gap.tractability}"],
    ])
    lines += ["", "## Problem", "", gap.problem, "",
              "## Symptom", "", gap.symptom, "",
              "## Why this is still open", "", gap.why_now, ""]

    lines += ["## Existing partial solutions", ""]
    lines += [f"- {item}" for item in gap.existing] if gap.existing else ["None found."]
    lines.append("")

    if gap.build_hypothesis:
        lines += ["## Build hypothesis", "", gap.build_hypothesis, ""]

    lines += _detection_section(gap)

    lines += ["## Evidence", ""]
    # The count the corroboration rule keys on, beside the count a reader can
    # already see. Three excerpts of one postmortem render as three `###` blocks
    # whose class, date and locator are identical, so without this denominator
    # the page overstates its own independence in the scorer's own terms.
    lines += [f"{_plural(len(gap.evidence), 'citation')} across "
              f"{_plural(distinct_sources(gap), 'distinct source document')}. "
              "Independence is counted by document, not by citation.", ""]
    for i, ev in enumerate(gap.evidence, start=1):
        lines += [f"### {i}. {ev.title}", "",
                  f"- Source class: `{ev.source_class}`",
                  f"- Date: {ev.date}",
                  f"- Locator: {ev.locator}",
                  "", f"> {ev.quote}", ""]
        if ev.note:
            lines += [ev.note, ""]
    return document(lines)
