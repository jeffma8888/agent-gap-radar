"""Unit: the detectability classifier has ONE copy, and both surfaces answer all of it.

Not a behavior file. `radar show`'s rendered `## Detection` section belongs to the test
engineer; what is pinned here is the internal consistency an engineer's refactor can
break silently:

* `models.detectability` is the single copy of the three-value mapping. Iteration 23
  put the automated/manual PREDICATE in one place (`Check.is_automated`, PRODUCT.md
  row 53) and left the `none` limb to each caller; iteration 29 added a second caller,
  so the mapping itself now needs the same treatment.
* Two surfaces hold prose keyed by that vocabulary -- `prd.DETECTABILITY_DECLARATIONS`
  (what the register holds towards reproducing the gap) and `render.DETECTION_STATEMENTS`
  (what `radar scan` does with the record). A fourth kind added to the vocabulary must be
  answered by BOTH, so the key sets are compared by EQUALITY in both directions rather
  than by containment: an omitted key and an invented key both fail.
* The `## Detection` branch that emits the manual question is keyed on the DERIVED kind,
  not on the rule-slot list being empty. Those two readings diverge on a shape the loader
  ACCEPTS -- a check declaring `applies_when` alone -- and no live record has it, so this
  is precisely the class of defect every green signal over the live register is blind to.

Offline, and every synthetic input is built in memory. The one live-register assertion is
an IDENTITY (every record classifies into the closed set) plus an anti-vacuity floor, so a
research pass landing new records cannot redden this file.
"""

from __future__ import annotations

import pathlib

import pytest

from agent_gap_radar.models import (DETECTABILITY_KINDS, Check, Gap,
                                    detectability)
from agent_gap_radar.prd import DETECTABILITY_DECLARATIONS
from agent_gap_radar.registry import load_all
from agent_gap_radar.render import DETECTION_STATEMENTS, gap_brief

LIVE_GAPS = pathlib.Path(__file__).resolve().parent.parent / "gaps"

#: A minimal automated check: one rule plus the two-sided fixtures the schema demands.
_RULE = {"kind": "file_exists", "globs": ["*.py"]}
_FIXTURES = {"bad": {"a.py": "x"}, "good": {"b.txt": "y"}}


def _automated() -> Check:
    return Check(id="CHK-901", present_when=dict(_RULE), fixtures=dict(_FIXTURES))


def _mitigated_only() -> Check:
    """The second limb of the predicate: a mitigation rule and no present rule."""
    return Check(id="CHK-902", mitigated_when=dict(_RULE), fixtures=dict(_FIXTURES))


def _manual() -> Check:
    return Check(id="CHK-903", manual_question="Ask a human this.")


def test_the_three_shapes_classify_into_the_closed_vocabulary() -> None:
    assert detectability(_automated()) == "automated"
    assert detectability(_mitigated_only()) == "automated"
    assert detectability(_manual()) == "manual"
    assert detectability(None) == "none"


def test_the_vocabulary_is_exactly_the_three_kinds() -> None:
    """Anti-vacuity: a shrunk vocabulary would make every set comparison below cheap."""
    assert DETECTABILITY_KINDS == ("automated", "manual", "none")


@pytest.mark.parametrize("name,prose", [("prd", DETECTABILITY_DECLARATIONS),
                                        ("render", DETECTION_STATEMENTS)])
def test_each_surface_answers_every_kind_and_invents_none(name: str,
                                                          prose: dict[str, str]) -> None:
    assert set(prose) == set(DETECTABILITY_KINDS), (name, sorted(prose))
    for kind, text in prose.items():
        assert text.strip() and text.endswith("."), (name, kind, text)
        assert ". " not in text, f"{name}/{kind} is more than one sentence: {text!r}"
    assert len(set(prose.values())) == len(DETECTABILITY_KINDS), name


def test_the_two_surfaces_hold_DIFFERENT_prose_for_the_same_key() -> None:
    """The duplication is deliberate, so it is asserted rather than left to be assumed.

    If these ever converge, the right fix is one shared dict -- not two copies of one
    sentence, which is the shape this product has already paid three times to remove.
    """
    assert not (set(DETECTABILITY_DECLARATIONS.values())
                & set(DETECTION_STATEMENTS.values()))


def test_every_live_record_classifies_into_the_closed_set() -> None:
    """An identity over live data, never a pinned count: new records cannot break it."""
    gaps = load_all(LIVE_GAPS)
    assert len(gaps) >= 2, "anti-vacuity: the live register is too small to classify"
    kinds = {detectability(g.check) for g in gaps}
    assert kinds <= set(DETECTABILITY_KINDS), sorted(kinds)
    assert len(kinds) >= 2, f"only {sorted(kinds)} present; the branch is untested live"
#: The smallest record `Gap.model_validate` accepts, so a synthetic check can be pushed
#: through the REAL loader rather than constructed past it. Reachability is the whole
#: claim below: the shape must be admissible, not merely expressible.
_RECORD: dict = {
    "id": "GAP-900", "title": "t", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 3, "frequency": 3, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}


def _detection_block(doc: str) -> str:
    """The rendered `## Detection` section, sliced out of a real `gap_brief` document.

    Asserted through the PUBLIC renderer, never through the private section builder: a
    refactor that moved the question onto some other line would then still have to put
    it in the document a reader sees, which is what the behavior actually promises.
    """
    return doc[doc.index("## Detection"):doc.index("## Evidence")]


@pytest.mark.parametrize("check,wants_question", [
    ({"id": "CHK-903", "manual_question": "Ask a human this."}, True),
    ({"id": "CHK-904", "manual_question": "Ask a human this.",
      "applies_when": dict(_RULE)}, True),
    ({"id": "CHK-901", "manual_question": "Ask a human this.",
      "present_when": dict(_RULE), "fixtures": dict(_FIXTURES)}, False),
])
def test_the_manual_question_follows_the_KIND_not_the_rule_slot_count(
        check: dict, wants_question: bool) -> None:
    """A manual check that ALSO declares `applies_when` must keep its question.

    `Check.is_automated` reads only `present_when`/`mitigated_when`, so a check
    declaring `applies_when` alone loads, classifies `manual`, and leaves a NON-EMPTY
    rule-slot list behind it. A branch keyed on that list being empty therefore drops
    the manual question -- the only actionable payload such a record carries -- while
    printing "holds no static signature" directly above "Rules declared". The third
    case is the other side: on an automated check the same field is `scan`'s
    both-signatures escalation question and must NOT reach this section.

    0 of the live records carry the middle shape, which is why the register cannot
    witness this and a synthetic one has to.
    """
    gap = Gap.model_validate({**_RECORD, "check": check})
    assert detectability(gap.check) == ("automated" if wants_question is False
                                        else "manual")
    section = _detection_block(gap_brief(gap))
    line = "- Question a human must answer: Ask a human this."
    assert (line in section) is wants_question, section
    # Anti-vacuity for the middle case: the slot really is declared, so a future
    # `_declared_rules` that skipped `applies_when` could not make this pass by luck.
    if "applies_when" in check:
        assert "- Rules declared: `applies_when` (file_exists)" in section, section
