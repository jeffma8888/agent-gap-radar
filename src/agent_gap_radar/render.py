"""Markdown renderers. Output is deterministic and ends in exactly one newline."""

from __future__ import annotations

from .models import Gap
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

    lines += ["## By layer", ""]
    counts = {layer: 0 for layer in LAYERS}
    for g in gaps:
        counts[g.layer] += 1
    lines += table(["Layer", "Records"],
                   [[layer, str(n)] for layer, n in counts.items() if n])
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
