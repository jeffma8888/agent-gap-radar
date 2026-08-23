"""Deterministic ranking.

Two numbers come out of a gap, and they are deliberately NOT combined:

  priority   -- how much it would matter to fix (weighted sum: severity x3
                + frequency x2 + tractability x1, normalised to 0.0-10.0)
  confidence -- how well we actually know it is true (derived from evidence only)

Blending them produces the classic failure where a well-cited small problem
outranks a poorly-cited large one, and nobody can see which input moved.
A reader who wants a single ordering gets priority, filtered by a confidence
floor -- an explicit, visible choice instead of a hidden weighting.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .taxonomy import SOURCE_CLASSES, SOURCE_WEIGHTS

if TYPE_CHECKING:
    # Typing-only, so this module imports with pydantic absent. `models` IS the
    # pydantic schema, and importing it for annotations alone made the whole
    # scorer unreachable to the one declared consumer, which reads
    # `gaps/*.json` as plain local JSON with no pydantic on its path -- so it
    # ranked records by the STORED integers and disagreed with us about which
    # records its own top five names. `from __future__ import annotations` is
    # already in force above, so every `Gap` annotation below stays a string at
    # runtime and needs no quoting.
    from .models import Gap

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


_PROBE_LOCATOR = "urn:agent-gap-radar:promotion-probe"


def _source_key(citation: object) -> str:
    """Identity of the DOCUMENT a citation points at, for the independence test.

    A `#fragment` names a section of the same document and a trailing `/` is the
    same page, so both are dropped and the rest is case-folded: `.../p`, `.../p/`
    and `.../P#s2` are ONE source, which is how one URL arrives from three
    different readers. Nothing beyond that is merged -- two paths in one repo, or
    two DOIs on one host, stay DISTINCT sources deliberately, because collapsing
    a host would WITHHOLD a corroboration point that was honestly earned.

    Total on purpose: a citation stand-in carrying no `locator` (see
    `_ClassOnly`) reads as the empty key instead of raising, so `confidence()`
    stays callable on any object with a `source_class`. That default can only
    withhold the point, never grant one, which keeps the failure direction safe.
    """
    locator = getattr(citation, "locator", "")
    return locator.split("#", 1)[0].rstrip("/").casefold()


def distinct_sources(gap: Gap) -> int:
    """How many DISTINCT DOCUMENTS a record's citations rest on.

    The denominator `confidence()`'s corroboration rule already keys on, exposed
    so a surface can print it. It CALLS `_source_key` instead of repeating that
    normalisation, so a published count cannot disagree with the point the
    scorer grants or withholds: two fragments of one page, or one URL entered
    with and without a trailing slash, count ONCE in both places by construction.

    Total for the same reason `_source_key` is total -- an empty `evidence` list
    returns 0 rather than raising -- so a renderer may print the number without
    first asking whether the record carries any citations at all.

    Feeds no score and enters no ordering: it is a denominator, and a source
    count read as a target is the Goodhart shape this register forbids by name.
    """
    return len({_source_key(e) for e in gap.evidence})


def confidence(gap: Gap) -> int:
    """0-5, derived ONLY from evidence quality and independence.

    Rules, in order:
      * the strongest single source sets the ceiling,
      * two citations differing in BOTH source class and SOURCE add one point
        (corroboration),
      * evidence that is exclusively model-output scores 0 regardless of volume.

    Independence is two SOURCES, not two labels. This rule used to key on the set
    of `source_class` values alone, so ONE document cited twice under two labels
    -- the same URL entered as `practitioner-report` and again as
    `secondary-summary` -- earned the corroboration point with no second source
    behind it, and that point is exactly what moves a record across the
    confidence floor. Confidence is DERIVED from evidence; a point granted by
    relabelling is that invariant failing quietly, which is worse than a visible
    error because the number still looks derived.

    The pair is tested pairwise rather than as "two classes and two sources".
    Those two forms happen to be equivalent over any set of citations, but the
    equivalence needs a proof, and the pairwise form simply IS the rule.
    """
    if not gap.evidence:
        return 0
    weights = [SOURCE_WEIGHTS[e.source_class] for e in gap.evidence]
    best = max(weights)
    if best == 0:
        return 0
    # Weight-0 evidence scores 0 on its own, so it may supply NEITHER half of a
    # corroborating pair -- filtering first states that once instead of twice.
    real = [e for e in gap.evidence if SOURCE_WEIGHTS[e.source_class] > 0]
    corroborated = 1 if any(
        a.source_class != b.source_class and _source_key(a) != _source_key(b)
        for a, b in itertools.combinations(real, 2)
    ) else 0
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

    Simulating a promotion by cloning a real `Evidence` would need a quote and a
    date that do not exist yet, and inventing those would put fictional evidence
    one copy away from the register. So this carries only what `confidence()`
    reads: the class, and a source identity.

    The locator is a `urn:` no citation can hold -- the promotion gate requires a
    fetchable URL -- which is what makes the probe read as a NEW source. The
    question being simulated is "what would one FURTHER source do", so a probe
    that collided with a locator the record already cites would silently withhold
    the corroboration point and understate every prescription.
    """

    source_class: str
    locator: str = _PROBE_LOCATOR


@dataclass(frozen=True, slots=True)
class _EvidenceOnly:
    """Minimal stand-in for a RECORD, carrying the one field `confidence()` reads.

    The same idiom as `_ClassOnly` one level up: build the smallest object the
    scorer actually reads instead of copying a validated model. This used to be
    a pydantic clone of the record: correct, and the one pydantic-only call in
    the module, which is what made the whole scorer unimportable for the
    consumer `docs/CONSUMER_CONTRACT.md` declares -- that consumer reads record
    files as plain JSON and has no pydantic to clone with. `confidence()` reads
    `evidence` off a record and nothing else, so that is the entire surface a
    probe needs.

    Deliberately NOT a `Gap`: a probe is a hypothetical, and building it as a
    real record would put an unvalidated record one copy away from the register.
    """

    evidence: tuple[object, ...]


def _confidence_with(gap: Gap, extra_class: str) -> int:
    """`confidence()` of `gap` as if it held ONE further citation of that class.

    Goes through the real `confidence()` rather than re-deriving the arithmetic,
    so a prescription can never disagree with the score it is prescribing for.
    The probe never leaves this module.

    `confidence()` is annotated `Gap` because that is the only record shape the
    register can PRODUCE, not the only one it accepts: it reads `evidence`, each
    item's `source_class`, and `_source_key`, all of which are documented total
    over any object carrying those attributes. Passing a stand-in here is that
    documented totality being used, not bypassed -- the same relationship
    `_ClassOnly` already has with the `Evidence` annotations.
    """
    probe = _EvidenceOnly((*gap.evidence, _ClassOnly(extra_class)))
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
