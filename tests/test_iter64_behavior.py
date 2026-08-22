"""Iteration 64 behaviors: the front door must state the corroboration rule the CODE enforces.

`VISION.md` names one invariant the register exists to protect -- a record's confidence is
DERIVED from its evidence ladder, never asserted in prose -- and `README.md` is the only place
a human reader meets it. Before this iteration that sentence said the point is earned when
"two independent classes add a point", the vocabulary that predates the pairwise rule: the
shipped scorer requires two citations differing in class AND in source document, so two labels
on one URL earn nothing. The README therefore promised a number the code does not return, and
it taught the exact anti-pattern the register was fixed to reject.

BLACK-BOX, AND THE ISOLATION CONTRACT IS HONORED. Every expectation here is taken from
`pm.md` (Feature / Why) and measured by CALLING the public library API -- `models.Gap`,
`scoring.confidence`, `cli.main` -- or by reading `README.md`, which is a published document.
Nothing in this file was read from `src/`, from the engineer's or reviewer's notes, from
`IMPLEMENTATION.patch`, or from any diff.

ONE DISCLOSURE, also carried in the tester report: `pm.md` was CUT SHORT at the stage cap and
its "Expected Behaviors" section reads `1-6: see refined section below` with no such section,
so no numbered list exists. The behaviors below are this file's reading of the Feature and Why
paragraphs, which are complete; the numbering is mine and the report says so.

STRUCTURAL CHOICES, so this file cannot lie later:

* **The requirement is DERIVED, never a keyword list.** Which halves of the pair the README
  must name is computed in this run from the real `confidence()` over a four-row truth table
  that varies exactly one half per row. If a future iteration made class difference sufficient
  on its own, this file would stop demanding the README mention the document.
* **The claim is isolated by EXTRACTION, not by deletion.** Only the clause that actually
  contains the point-earning phrase is searched for dimension words, so a neighbouring clause
  ("the strongest source class sets the ceiling") can never lend the claim a dimension it does
  not state. Deleting neighbours would need its own guard against deleting too much; extracting
  the one clause needs none.
* **Every checker assertion has a two-sided control** over fixtures written in this file: a
  known-good sentence must stay silent, and a known-bad sentence must fire in each dimension
  separately. Each bad fixture asserts it really differs from the good one, so a no-op mutation
  cannot turn a control into a copy of the thing it is controlling.
* **No live literal is written down.** No line number, no phrasing, no byte count and no gap id:
  the register is grown by unattended research passes, so a fixture pinned to today's numbers
  would red a correct repo tomorrow.
* **No absolute machine path and no personal identifier appears here.** The repo root is derived
  from `__file__`; fixture locators use `example.invalid`, which can never resolve.
"""

from __future__ import annotations

import pathlib
import re

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap
from agent_gap_radar.scoring import confidence

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"

#: Two distinct unresolvable documents and two distinct ladder rungs, so each truth-table row
#: below varies exactly one half of the corroboration pair.
DOC_A = "https://example.invalid/a"
DOC_B = "https://example.invalid/b"
CLASS_STRONG = "peer-reviewed"
CLASS_WEAK = "secondary-summary"
CLASS_MODEL = "model-output"

#: The formulation this iteration retires. Pinned as an ABSENCE only -- never as a required
#: phrasing -- because no honest rewrite reintroduces it.
RETIRED_CLAIM = "independent classes add a point"

#: dimension -> words that count as NAMING it. Bare "source" is deliberately NOT accepted for
#: the document half: "source class" contains it, so accepting it would let a class-only
#: sentence read as naming both halves. The known-bad control below proves that fires.
DIMENSION_WORDS: dict[str, tuple[str, ...]] = {
    "class": ("class",),
    "source document": ("source document", "document", "url", "locator"),
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT = re.compile(r"[;,:()]")
#: What it means to STATE the rule: naming what earns the point. Deliberately does NOT match a
#: bare mention of the word "corroboration": a document may discuss corroboration elsewhere
#: without restating the rule, and counting such a mention as a second claim would red an
#: honest document. The robustness control below measures exactly that case.
_EARNS_THE_POINT = re.compile(r"adds? a point|adds? one point", re.I)
#: Generous vocabulary for the CONSEQUENCE half of the rule (a same-document pair earns
#: nothing). Presence-only and sentence-scoped: this file does not claim to prove which case a
#: negation refers to, which is why the dimension check above is what carries the load.
_EARNS_NOTHING = re.compile(
    r"(earns?|adds?|scores?)\s+(nothing|no\s+point|zero)"
    r"|(does|do)\s+not\s+(earn|add|count)"
    r"|no\s+(extra|second|additional)\s+point",
    re.I,
)


def rule_claims(text: str) -> list[str]:
    """Every sentence in `text` that states what EARNS the corroboration point.

    A pure function over text, so it can be driven by planted fixtures. An absence is only
    evidence once the same function has been shown to produce a finding.
    """
    return [s for s in _SENTENCE_SPLIT.split(text) if _EARNS_THE_POINT.search(s)]


def earning_clause(sentence: str) -> str:
    """The one clause of `sentence` that contains the point-earning phrase.

    EXTRACTION, not deletion: a dimension word in a neighbouring clause cannot be credited to
    this claim, and there is no "deleted too much" failure mode to guard against.
    """
    parts = [p for p in _CLAUSE_SPLIT.split(sentence) if _EARNS_THE_POINT.search(p)]
    return " ".join(parts)


def unnamed_dimensions(sentence: str, required: tuple[str, ...]) -> tuple[str, ...]:
    """The required dimensions the claim in `sentence` fails to name, in `required` order."""
    folded = earning_clause(sentence).casefold()
    return tuple(d for d in required if not any(w in folded for w in DIMENSION_WORDS[d]))


def _gap(cites: tuple[tuple[str, str], ...]) -> Gap:
    """A schema-valid synthetic record whose citations are (source_class, locator) pairs."""
    return Gap.model_validate({
        "id": "GAP-902", "title": "t", "layer": "eval-verification",
        "gap_type": "unverifiable", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": sc, "title": "t", "locator": loc,
                      "date": "2026-01-02", "quote": "q"} for sc, loc in cites],
    })


def measured_scores() -> dict[str, int]:
    """The truth table, driven through the REAL `confidence()`.

    Each row differs from `both` in exactly one half of the pair, which is what makes the
    requirement below a measurement rather than a restatement of this docstring.
    """
    return {
        "one": confidence(_gap(((CLASS_STRONG, DOC_A),))),
        "both": confidence(_gap(((CLASS_STRONG, DOC_A), (CLASS_WEAK, DOC_B)))),
        "same_document": confidence(_gap(((CLASS_STRONG, DOC_A), (CLASS_WEAK, DOC_A)))),
        "same_class": confidence(_gap(((CLASS_STRONG, DOC_A), (CLASS_STRONG, DOC_B)))),
    }


def load_bearing_dimensions() -> tuple[str, ...]:
    """The halves of the pair the real scorer refuses to do without, in `DIMENSION_WORDS` order.

    `same_document` varies only the document, so losing the point there makes the document
    load-bearing; `same_class` varies only the class.
    """
    scored = measured_scores()
    necessary = {
        "class": scored["same_class"] < scored["both"],
        "source document": scored["same_document"] < scored["both"],
    }
    return tuple(d for d in DIMENSION_WORDS if necessary[d])


# ------------------------------------------------------------------- two-sided controls
#
# These ask "does the checker work?" and never read the committed document, so they hold
# whatever state `README.md` is in.

GOOD = ("the strongest source class sets the ceiling, two citations differing in both class "
        "and source document add a point, and model output scores zero.")
CLASS_ONLY = GOOD.replace(
    "two citations differing in both class and source document add a point",
    "two independent classes add a point")
DOCUMENT_ONLY = GOOD.replace(
    "two citations differing in both class and source document add a point",
    "two citations from different documents add a point")


def test_b7_each_bad_fixture_really_is_a_mutation_of_the_good_one():
    """Premise for the two controls below: a no-op replace would void both."""
    assert CLASS_ONLY != GOOD
    assert DOCUMENT_ONLY != GOOD
    assert CLASS_ONLY != DOCUMENT_ONLY


def test_b7_checker_fires_on_the_retired_class_only_sentence():
    """Known-bad: the retired rule must be reported as failing to name the document."""
    claims = rule_claims(CLASS_ONLY)
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], ("class", "source document")) == ("source document",)


def test_b7_checker_fires_on_a_document_only_sentence():
    """The mirror known-bad, so the checker is two-sided in BOTH dimensions.

    This is the row that proves clause EXTRACTION works: the sentence contains the word
    "class" in its ceiling clause, and the claim is still correctly reported as not naming it.
    """
    claims = rule_claims(DOCUMENT_ONLY)
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], ("class", "source document")) == ("class",)


def test_b7_checker_is_silent_on_a_sentence_naming_both_halves():
    """Known-good: a correct statement must not red the build."""
    claims = rule_claims(GOOD)
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], ("class", "source document")) == ()


def test_b7_checker_reports_nothing_in_prose_that_states_no_rule():
    """Domain control: the finder is selective, so the brake needs its own arming guard."""
    assert rule_claims("Priority is severity x frequency x tractability.") == []


def test_b7_an_added_mention_of_corroboration_is_not_counted_as_a_second_claim():
    """Robustness control: prose ABOUT corroboration is not a restatement of the rule.

    A matcher that counted a bare "corroborat" token would find two claims here and red a
    document whose only change was a pointer to the fuller explanation.
    """
    honest_addition = GOOD + " Corroboration is explained further in the consumer contract."
    assert len(rule_claims(honest_addition)) == 1, rule_claims(honest_addition)


def test_b7_clause_extraction_keeps_only_the_clause_that_earns_the_point():
    """Two-sided control for the isolation step itself."""
    assert "ceiling" not in earning_clause(GOOD)
    assert "add a point" in earning_clause(GOOD)
    both_jobs = "the ceiling is the strongest class and a second class at a second url adds a point"
    assert unnamed_dimensions(both_jobs, ("class", "source document")) == ()


# --------------------------------------------------------------------------- derivation


def test_b3_the_real_scorer_makes_both_halves_of_the_pair_load_bearing():
    """The measurement every requirement below is derived from, asserted in the open."""
    scored = measured_scores()
    assert scored["both"] == scored["one"] + 1, scored
    assert scored["same_document"] == scored["one"], scored
    assert scored["same_class"] == scored["one"], scored
    assert load_bearing_dimensions() == ("class", "source document")


def test_b6_model_output_only_scores_zero_however_many_citations_there_are():
    """The README's third promise, measured: volume never buys a model-output-only record."""
    assert confidence(_gap(((CLASS_MODEL, DOC_A),))) == 0
    many = tuple((CLASS_MODEL, f"https://example.invalid/{n}") for n in range(4))
    assert confidence(_gap(many)) == 0


# -------------------------------------------------------------------------- the brakes


def test_b1_the_readme_states_the_corroboration_rule_exactly_once():
    """Arming guard: every naming assertion below is vacuous over zero claims."""
    claims = rule_claims(README.read_text(encoding="utf-8"))
    assert len(claims) == 1, claims


def test_b2_the_readme_names_every_load_bearing_half_of_the_pair():
    """The brake. Requires only what the scorer was MEASURED to require, in any words."""
    required = load_bearing_dimensions()
    assert required, "no dimension is load-bearing; this brake would be vacuous"
    claims = rule_claims(README.read_text(encoding="utf-8"))
    assert len(claims) == 1, claims
    assert unnamed_dimensions(claims[0], required) == (), claims[0]


def test_b4_the_readme_no_longer_carries_the_retired_class_only_rule():
    """An absence: the one literal worth pinning, because no rewrite reintroduces it."""
    assert RETIRED_CLAIM not in README.read_text(encoding="utf-8")


def test_b5_the_readme_states_that_a_same_document_pair_earns_nothing():
    """Derived: this is required ONLY because the same-document row was measured to score no point."""
    scored = measured_scores()
    if scored["same_document"] == scored["both"]:
        return  # the code would no longer justify the claim
    claims = rule_claims(README.read_text(encoding="utf-8"))
    assert len(claims) == 1, claims
    assert _EARNS_NOTHING.search(claims[0]), claims[0]


# ----------------------------------------------------------- docs-only, no regression


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_b8_the_register_verbs_still_succeed_and_stay_byte_stable(capsys):
    """A README-only change may not move any renderer: same bytes twice, exit 0, clean stderr."""
    for verb in ("validate", "list", "report"):
        first_code, first_out, first_err = _run([verb, str(REPO_ROOT)], capsys)
        second_code, second_out, second_err = _run([verb, str(REPO_ROOT)], capsys)
        assert first_code == 0, (verb, first_err)
        assert second_code == 0, (verb, second_err)
        assert first_err == "" and second_err == "", (verb, first_err, second_err)
        assert first_out == second_out, verb
        assert first_out.endswith("\n") and not first_out.endswith("\n\n"), verb


def test_b8_the_readme_is_not_part_of_any_rendered_document(capsys):
    """The changed sentence must not leak into stdout: the README is documentation, not output."""
    claim = rule_claims(README.read_text(encoding="utf-8"))[0].strip()
    probe = claim[:40]
    for verb in ("list", "report", "taxonomy"):
        argv = [verb] if verb == "taxonomy" else [verb, str(REPO_ROOT)]
        code, out, err = _run(argv, capsys)
        assert code == 0, (verb, err)
        assert probe not in out, verb


# --------------------------------------------------------------- public-repo quality bar


def test_b9_the_changed_document_carries_no_machine_path_or_personal_identifier():
    """The repo is public: a docs edit is exactly where a local path or an address slips in."""
    text = README.read_text(encoding="utf-8")
    for banned in ("/Users/", "/home/", "file://", "C:\\", "@gmail", "@outlook", "@amazon"):
        assert banned not in text, banned


def test_b9_the_rule_sentence_is_pure_ascii():
    """Smart quotes and dashes are how a hand-edited sentence stops being byte-stable."""
    claim = rule_claims(README.read_text(encoding="utf-8"))[0]
    non_ascii = sorted({c for c in claim if ord(c) > 127})
    assert non_ascii == [], non_ascii
