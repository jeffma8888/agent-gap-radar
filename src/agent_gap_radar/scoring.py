"""Deterministic ranking.

Two numbers come out of a gap, and they are deliberately NOT combined:

  priority   -- how much it would matter to fix (severity x frequency x tractability)
  confidence -- how well we actually know it is true (derived from evidence only)

Blending them produces the classic failure where a well-cited small problem
outranks a poorly-cited large one, and nobody can see which input moved.
A reader who wants a single ordering gets priority, filtered by a confidence
floor -- an explicit, visible choice instead of a hidden weighting.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Gap
from .taxonomy import SOURCE_CLASSES, SOURCE_WEIGHTS

# Weights are integers and the divisor is exact, so scores are reproducible
# across machines and Python versions (no float accumulation order effects).
W_SEVERITY = 3
W_FREQUENCY = 2
W_TRACTABILITY = 1
_MAX_WEIGHTED = 5 * (W_SEVERITY + W_FREQUENCY + W_TRACTABILITY)

CONFIDENCE_FLOOR_DEFAULT = 2


def priority(gap: Gap) -> float:
    """0.0-10.0, rounded to one decimal. Higher = fix this sooner."""
    weighted = (
        gap.severity * W_SEVERITY
        + gap.frequency * W_FREQUENCY
        + gap.tractability * W_TRACTABILITY
    )
    return round(10.0 * weighted / _MAX_WEIGHTED, 1)


def confidence(gap: Gap) -> int:
    """0-5, derived ONLY from evidence quality and independence.

    Rules, in order:
      * the strongest single source sets the ceiling,
      * two or more INDEPENDENT source classes add one point (corroboration),
      * evidence that is exclusively model-output scores 0 regardless of volume.
    """
    if not gap.evidence:
        return 0
    weights = [SOURCE_WEIGHTS[e.source_class] for e in gap.evidence]
    best = max(weights)
    if best == 0:
        return 0
    distinct_real = {e.source_class for e in gap.evidence
                     if SOURCE_WEIGHTS[e.source_class] > 0}
    corroborated = 1 if len(distinct_real) >= 2 else 0
    return min(5, best + corroborated)


@dataclass(frozen=True, slots=True)
class _ClassOnly:
    """Minimal stand-in for a citation, carrying the one field scoring reads.

    Simulating a promotion by cloning a real `Evidence` would need a locator, a
    quote and a date that do not exist yet, and inventing those would put
    fictional evidence one copy away from the register. `confidence()` reads only
    `source_class`, so that is all this carries.
    """

    source_class: str


def _confidence_with(gap: Gap, extra_class: str) -> int:
    """`confidence()` of `gap` as if it held ONE further citation of that class.

    Goes through the real `confidence()` rather than re-deriving the arithmetic,
    so a prescription can never disagree with the score it is prescribing for.
    The probe copy is unvalidated on purpose and never leaves this module.
    """
    probe = gap.model_copy(update={"evidence": [*gap.evidence, _ClassOnly(extra_class)]})
    return confidence(probe)


def promotion_options(gap: Gap, confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT
                      ) -> tuple[str, ...]:
    """The cheapest source classes that would lift `gap` to `confidence_floor`.

    A below-floor record is a research task, and a research task that does not
    say what to look for sends the reader back to the source code. This answers
    that question WITHOUT letting a record author answer it: the result is
    simulated from `confidence()` and the `SOURCE_WEIGHTS` ladder alone, so it
    reports the scoring rule instead of adding a field anyone can assert.

    Returns every class of the LOWEST ladder weight whose addition as one
    further citation makes `confidence()` reach the floor, in ladder order
    (`SOURCE_CLASSES`, strongest rung first), or `()` when no single citation
    can reach it. `model-output` is never offered: it weighs 0, and evidence
    that is exclusively model-output scores 0 regardless of volume, so it can
    lift nothing.

    Total and pure: reads no file, raises for no input, and accepts a record
    with no evidence at all even though the loader cannot produce one.
    """
    reachable = tuple(source_class for source_class in SOURCE_CLASSES
                      if SOURCE_WEIGHTS[source_class] > 0
                      and _confidence_with(gap, source_class) >= confidence_floor)
    if not reachable:
        return ()
    cheapest = min(SOURCE_WEIGHTS[source_class] for source_class in reachable)
    return tuple(source_class for source_class in reachable
                 if SOURCE_WEIGHTS[source_class] == cheapest)


def rank(gaps: list[Gap], confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT
         ) -> list[tuple[Gap, float, int]]:
    """Sorted best-first. Ties break on id so the order is total and stable."""
    rows = [(g, priority(g), confidence(g)) for g in gaps
            if confidence(g) >= confidence_floor]
    rows.sort(key=lambda r: (-r[1], -r[2], r[0].id))
    return rows


def below_floor(gaps: list[Gap], confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT
                ) -> list[tuple[Gap, float, int]]:
    """Records excluded from the ranking. Shown, never silently dropped."""
    rows = [(g, priority(g), confidence(g)) for g in gaps
            if confidence(g) < confidence_floor]
    rows.sort(key=lambda r: r[0].id)
    return rows
