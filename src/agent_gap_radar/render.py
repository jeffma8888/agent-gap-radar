"""Markdown renderers. Output is deterministic and ends in exactly one newline."""

from __future__ import annotations

from .models import Check, Gap, detectability
from .scoring import (below_floor, confidence, priority,
                      promotion_options, rank, strongest_source)
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
    for i, ev in enumerate(gap.evidence, start=1):
        lines += [f"### {i}. {ev.title}", "",
                  f"- Source class: `{ev.source_class}`",
                  f"- Date: {ev.date}",
                  f"- Locator: {ev.locator}",
                  "", f"> {ev.quote}", ""]
        if ev.note:
            lines += [ev.note, ""]
    return document(lines)
