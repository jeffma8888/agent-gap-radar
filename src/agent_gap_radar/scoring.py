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


def _ladder_rank(source_class: str) -> int:
    """Position on the evidence ladder, strongest rung first.

    A class absent from `SOURCE_CLASSES` ranks AFTER every known one instead of
    raising. The loader validates `source_class`, so nothing loaded from
    `gaps/` can reach that branch; keeping the function total means a renderer
    never has to guard a lookup it did not perform.
    """
    try:
        return SOURCE_CLASSES.index(source_class)
    except ValueError:
        return len(SOURCE_CLASSES)


def strongest_source(gap: Gap) -> str:
    """The `source_class` of the record's best citation, chosen by ladder rung.

    Read alphabetically -- which is what a bare `min()` over the class NAME
    does -- `model-output` beats `secondary-summary` and `maintainer-primary`
    beats `peer-reviewed`. So a report could name, as a record's strongest
    evidence, the one class `taxonomy` annotates "NEVER sufficient on its own"
    and that `confidence()` scores 0. Ranking on `SOURCE_CLASSES` makes the
    displayed source and the derived confidence read the same ordering, which
    is the register's core invariant rather than a presentation detail.

    Ranks on the RUNG, not the weight: `peer-reviewed` and `maintainer-primary`
    both weigh 4 and the ladder still orders them, so the answer cannot depend
    on the order citations happen to sit in a record.

    Total: a record with no evidence returns `""`. The loader requires at least
    one citation, so that input is unreachable through `registry` -- this
    mirrors the totality `promotion_options` already documents.
    """
    if not gap.evidence:
        return ""
    return min(gap.evidence, key=lambda e: _ladder_rank(e.source_class)).source_class


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


def _partition(
    gaps: list[Gap], confidence_floor: int
) -> tuple[list[tuple[Gap, float, int]], list[tuple[Gap, float, int]]]:
    """Score every record ONCE and put it on exactly one side of the floor.

    Returns `(at_or_above, below)` of scored rows, unsorted -- the two public
    views order differently (priority-first vs id), so ordering belongs to the
    caller that names it.

    Why one pass and not two filters. The register has exactly one protected
    rule: a below-floor record is DISPLAYED, never silently dropped, and
    `rank()` / `below_floor()` are its only two views. Written as two
    independently authored comprehensions -- one keeping `confidence(g) >=
    floor`, one keeping `confidence(g) < floor` -- that rule held only because
    the predicates happened to remain exact complements. Nothing asserted it, so
    the way it breaks is an edit to one filter alone: a record falls out of one
    view and appears in neither, which is precisely the drop this product already
    had to fix once. Deciding each side exactly once here makes "every record
    lands in exactly one view" a property of the code instead of a coincidence
    between two functions.

    A side effect worth naming because a test pins it: the old form evaluated
    `confidence()` once per record in the filter and again per survivor when
    building the row, so one call cost N + kept. Here it is exactly N. Fresh
    lists are returned on every call -- there is deliberately no cache, so two
    calls cost 2N and no caller can observe a stale score.
    """
    at_or_above: list[tuple[Gap, float, int]] = []
    below: list[tuple[Gap, float, int]] = []
    for gap in gaps:
        score = confidence(gap)
        row = (gap, priority(gap), score)
        if score >= confidence_floor:
            at_or_above.append(row)
        else:
            below.append(row)
    return at_or_above, below


def rank(gaps: list[Gap], confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT
         ) -> list[tuple[Gap, float, int]]:
    """Sorted best-first. Ties break on id so the order is total and stable.

    The complement of this view is `below_floor()`; both read the same single
    `_partition()` pass, so no second below-floor predicate exists.
    """
    rows, _ = _partition(gaps, confidence_floor)
    rows.sort(key=lambda r: (-r[1], -r[2], r[0].id))
    return rows


def below_floor(gaps: list[Gap], confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT
                ) -> list[tuple[Gap, float, int]]:
    """Records excluded from the ranking. Shown, never silently dropped.

    The complement of `rank()`, from the same single `_partition()` pass.
    """
    _, rows = _partition(gaps, confidence_floor)
    rows.sort(key=lambda r: r[0].id)
    return rows
