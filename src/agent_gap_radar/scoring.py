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

from .models import Gap
from .taxonomy import SOURCE_WEIGHTS

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
