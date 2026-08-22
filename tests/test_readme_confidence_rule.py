"""A DERIVED brake: the front door must name every half of the corroboration pair.

WHAT THIS PROTECTS. `VISION.md` names one rule the register exists to protect --
confidence is DERIVED from evidence, never asserted -- and `README.md` is the only place
a human reader meets it. Until this iteration that line said the point is earned when
"two independent classes add a point", the vocabulary the code used BEFORE iteration 18
made the rule pairwise. The shipped rule needs two citations differing in class AND in
source document, so the README promised 4 where `confidence()` returns 3, and it taught
the precise defect iteration 18 removed. The register is also fed by unattended research
passes whose candidates are written from documents, so a wrong README is an input to the
gate and not merely a reader's problem.

WHY THIS IS DERIVED RATHER THAN A KEYWORD LIST. The requirement is not "the sentence must
contain these words". It is measured, in this run, through the real `scoring.confidence()`:
`_load_bearing_dimensions()` asks whether the point survives dropping the second SOURCE and
whether it survives dropping the second CLASS, and the README is then required to name only
the halves the scorer actually refuses to do without. If a future iteration made class
difference sufficient on its own, this brake would stop demanding that the README mention
the document -- the code decides what the prose owes, which is the direction of dependence
the register's core invariant requires.

WHAT IT DELIBERATELY DOES NOT PIN. No phrasing, no line number, no section: the checker
accepts any sentence that states what earns the point and names both dimensions in any
words, so an honest rewrite cannot red a correct document. The one literal it does pin is
an ABSENCE -- the retired class-only formulation -- which no honest rewrite reintroduces.

WHY THE CEILING CLAUSE IS EXCLUDED, AND THE FAIL-OPEN THAT FORCED IT. MEASURED in this
run: the mirror known-bad fixture -- a sentence that states the point in terms of DOCUMENTS
alone -- did not fire at sentence scope, because the neighbouring clause "the strongest
source class sets the ceiling" supplies the word "class" for a DIFFERENT rule. A claim
cannot be credited with a dimension it borrowed from the ceiling, so `_claim_scope` drops
any clause that names the ceiling WITHOUT stating the point; both known-bad fixtures then
fire, one per dimension. A clause that does both is kept, so the narrowing can only ever
widen what must be named, never manufacture a violation.

Two more deliberate choices in the same direction. The document-dimension vocabulary
excludes bare "source", because "source class" contains it and accepting it would let the
pre-iteration-18 sentence read as though it named both halves. And the retired formulation
is ALSO asserted absent, which is the one check that does not depend on scoping at all.

ISOLATION. Reads `README.md` and the public library API (`models.Gap`, `scoring.confidence`)
only. No network, no absolute machine path, no subprocess.
"""

from __future__ import annotations

import pathlib
import re

from agent_gap_radar.models import Gap
from agent_gap_radar.scoring import confidence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"

#: Two DIFFERENT documents and two DIFFERENT class labels, so each probe below varies
#: exactly one half of the pair. `example.invalid` can never resolve, which keeps a
#: fixture locator from reading as a citation anyone could fetch.
DOC = "https://example.invalid/p"
OTHER_DOC = "https://example.invalid/q"
CLASS_A = "peer-reviewed"
CLASS_B = "secondary-summary"

#: The pre-iteration-18 formulation. Pinned as an ABSENCE, never as a required phrasing.
RETIRED_CLAIM = "independent classes add a point"

#: dimension -> the vocabulary that counts as NAMING it. Bare "source" is deliberately
#: absent from the document row: "source class" contains it, so a class-only sentence
#: would falsely read as naming both halves (the known-bad fixture proves it fires).
DIMENSION_TOKENS: dict[str, tuple[str, ...]] = {
    "class": ("class",),
    "source document": ("source document", "document", "url", "locator"),
}

#: Sentence splitting is good enough here because the document is authored one paragraph
#: per line and the rule is one sentence; the domain guard below asserts exactly one hit
#: rather than assuming the split behaved.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_STATES_THE_POINT = re.compile(r"adds? a point|corroborat", re.I)
_CLAUSE_END = re.compile(r"[;,]")
_STATES_THE_CEILING = re.compile(r"ceiling", re.I)


def corroboration_claims(text: str) -> list[str]:
    """Every sentence in `text` that states what EARNS the corroboration point.

    A pure function over text so it can be driven by known-bad and known-good fixtures.
    Absence of a finding is only evidence once the same function is shown to produce one.
    """
    return [sentence for sentence in _SENTENCE_END.split(text)
            if _STATES_THE_POINT.search(sentence)]


def claim_scope(sentence: str) -> str:
    """`sentence` with the clauses that state only the CEILING rule removed.

    The ceiling rule names the evidence CLASS for its own purposes, so leaving it in scope
    lets a corroboration claim be credited with a dimension it never mentioned -- measured
    here, and the reason the document-only fixture below could not fire without this. A
    clause that names the ceiling AND states the point is KEPT, so narrowing can only widen
    what the claim must name for itself; it can never invent a violation.
    """
    kept = [clause for clause in _CLAUSE_END.split(sentence)
            if _STATES_THE_POINT.search(clause) or not _STATES_THE_CEILING.search(clause)]
    return " ".join(kept)


def unnamed_dimensions(sentence: str, required: tuple[str, ...]) -> tuple[str, ...]:
    """The required dimensions the claim in `sentence` does NOT name, in `required` order.

    Scopes the sentence itself rather than trusting the caller to do it, because a caller
    that forgot would silently credit the ceiling clause and the check would read as health.
    """
    folded = claim_scope(sentence).casefold()
    return tuple(dimension for dimension in required
                 if not any(token in folded for token in DIMENSION_TOKENS[dimension]))


def _gap(cites: tuple[tuple[str, str], ...]) -> Gap:
    """A schema-valid synthetic record whose citations are (source_class, locator) pairs.

    Synthetic rather than a live `GAP-NNN`: the register is grown by an unattended research
    pass, so a fixture pinned to a real id would red this file against a CORRECT register.
    The record shape mirrors the one iteration 18's tests already prove valid.
    """
    return Gap.model_validate({
        "id": "GAP-901", "title": "t", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": source_class, "title": "t", "locator": locator,
                      "date": "2026-01-02", "quote": "q"} for source_class, locator in cites],
    })


def _measured_scores() -> dict[str, int]:
    """The four-row truth table, driven through the REAL `confidence()`.

    Each row differs from `both` in exactly one half of the pair, which is what makes the
    derivation below a measurement rather than a restatement of the docstring.
    """
    return {
        "ceiling": confidence(_gap(((CLASS_A, DOC),))),
        "both": confidence(_gap(((CLASS_A, DOC), (CLASS_B, OTHER_DOC)))),
        "class_only": confidence(_gap(((CLASS_A, DOC), (CLASS_B, DOC)))),
        "source_only": confidence(_gap(((CLASS_A, DOC), (CLASS_A, OTHER_DOC)))),
    }


def _load_bearing_dimensions() -> tuple[str, ...]:
    """The halves of the pair the real scorer refuses to do without, in doc order.

    `class_only` varies only the SOURCE, so losing the point there makes the source
    document load-bearing; `source_only` varies only the CLASS. Returned in
    `DIMENSION_TOKENS` order so the value is deterministic.
    """
    scored = _measured_scores()
    necessary = {
        "class": scored["source_only"] < scored["both"],
        "source document": scored["class_only"] < scored["both"],
    }
    return tuple(dimension for dimension in DIMENSION_TOKENS if necessary[dimension])


# --------------------------------------------------------------------- two-sided controls
#
# These ask "does the checker work?" and never read the committed document, so they hold
# whatever state `README.md` is in. Each bad fixture is a mutation of the good one and
# asserts its own premise: a silently no-op replace would turn a known-bad fixture into a
# copy of the known-good one and the test would pass while measuring nothing.

GOOD_FIXTURE = ("the strongest source class sets the ceiling, two citations differing in "
                "both class and source document add a point, and model output scores zero.")
CLASS_ONLY_FIXTURE = GOOD_FIXTURE.replace(
    "two citations differing in both class and source document add a point",
    "two independent classes add a point")
SOURCE_ONLY_FIXTURE = GOOD_FIXTURE.replace(
    "two citations differing in both class and source document add a point",
    "two citations from different documents add a point")


def test_each_bad_fixture_really_is_a_mutation_of_the_good_one():
    """Premise for the two controls below; a no-op replace would void both."""
    assert CLASS_ONLY_FIXTURE != GOOD_FIXTURE
    assert SOURCE_ONLY_FIXTURE != GOOD_FIXTURE
    assert CLASS_ONLY_FIXTURE != SOURCE_ONLY_FIXTURE


def test_the_checker_fires_on_the_retired_class_only_sentence():
    """Known-bad: the pre-iteration-18 rule must be reported as missing the document."""
    claims = corroboration_claims(CLASS_ONLY_FIXTURE)
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], ("class", "source document")) == ("source document",)


def test_the_checker_fires_on_a_document_only_sentence():
    """The mirror known-bad, so the checker is two-sided in BOTH dimensions."""
    claims = corroboration_claims(SOURCE_ONLY_FIXTURE)
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], ("class", "source document")) == ("class",)


def test_the_checker_is_silent_on_a_sentence_naming_both_halves():
    """Known-good: a correct statement must not red the build."""
    claims = corroboration_claims(GOOD_FIXTURE)
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], ("class", "source document")) == ()


def test_the_ceiling_clause_is_dropped_but_never_a_clause_that_states_the_point():
    """Two-sided control for the narrowing itself, in both directions.

    Dropping too much is the dangerous half: it would credit nothing and fire on a correct
    document, so a clause doing both jobs must survive.
    """
    assert "ceiling" not in claim_scope(GOOD_FIXTURE)
    assert "add a point" in claim_scope(GOOD_FIXTURE)
    both_jobs = "the ceiling is the strongest class and a second class at a second document adds a point."
    assert claim_scope(both_jobs) == both_jobs
    assert unnamed_dimensions(both_jobs, ("class", "source document")) == ()


def test_the_claim_finder_reports_nothing_in_prose_that_states_no_rule():
    """Domain control: the finder is selective, so the brake needs its own guard."""
    assert corroboration_claims("Priority is severity x frequency x tractability.") == []


# ----------------------------------------------------------------------------- derivation


def test_the_real_scorer_makes_both_halves_of_the_pair_load_bearing():
    """The measurement the brake's requirement is derived from, asserted in the open."""
    scored = _measured_scores()
    assert scored["both"] == scored["ceiling"] + 1, scored
    assert scored["class_only"] == scored["ceiling"], scored
    assert scored["source_only"] == scored["ceiling"], scored
    assert _load_bearing_dimensions() == ("class", "source document")


# ----------------------------------------------------------------------------- the brake


def test_the_readme_states_the_corroboration_rule_exactly_once():
    """Armed instrument: the naming assertion below is vacuous over zero claims."""
    claims = corroboration_claims(README.read_text(encoding="utf-8"))
    assert len(claims) == 1, claims


def test_the_readme_names_every_load_bearing_half_of_the_pair():
    """The brake. Requires only what the scorer was measured to require, in any words."""
    required = _load_bearing_dimensions()
    assert required, "no dimension is load-bearing; the brake would be vacuous"
    claims = corroboration_claims(README.read_text(encoding="utf-8"))
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], required) == (), claims[0]


def test_the_readme_no_longer_carries_the_retired_class_only_rule():
    """An absence, which is the only literal worth pinning: no rewrite reintroduces it."""
    assert RETIRED_CLAIM not in README.read_text(encoding="utf-8")
