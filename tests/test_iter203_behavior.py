"""Iteration 203 behaviors: the consumer contract publishes the per-rule search cap and
the ONE verdict transition it can force, and a brake pins the published integer to
`checks.MAX_SCAN_FILES` in BOTH directions.

ISOLATION CONTRACT HONORED. Nothing in this module reads the text of `src/`, the
engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s nine Expected Behaviors (including its
`[AMENDED IN FIX ROUND 203]` clause) plus this iteration's `PRODUCT.md` ledger row, and
every shape claim below was MEASURED -- either by reading the two committed documents this
brake governs, or by driving the public interface (`checks.MAX_SCAN_FILES`,
`checks.Verdict`, `checks.evaluate`, `checks.run_check`) over fixtures written under
pytest's `tmp_path`.

STRUCTURAL NOTES, so this file cannot lie later:

* **THE FIGURE IS NEVER HAND-TYPED.** No test and no fixture in this module contains the
  cap's value as a literal. Every expectation is built from `checks.MAX_SCAN_FILES`, and
  every known-bad figure is derived from it (`+ 1`), so changing the constant moves this
  module's expectations with it and a DRIFTED DOCUMENT is the only way to red the pin.
  The two verdict names are read from `Verdict` for the same reason: rename a verdict and
  behavior 3 reds instead of the contract quietly naming a verdict that no longer exists.

* **THE EXTRACTOR IS ANCHORED ON A DIGIT, and that is load-bearing.** Behavior 2 asks for
  "maximal runs of digits and commas, with commas stripped". Implemented literally as
  `[0-9,]+` it also matches the paragraph's PROSE commas, which strip to the empty string,
  so the set becomes `{'', <figure>}` and the both-directions equality FAILS on a correct
  document. The shipped extractor requires a LEADING DIGIT, so it yields exactly
  the figures. Measured on
  the committed paragraph: the digit-led form returns a set of ONE equal to the constant,
  while the comma-led form returns that figure plus an empty token. The tempting repair
  -- loosening the assertion to a substring test -- would discard the both-directions
  property that is the entire reason this brake exists, so
  `test_b2_the_extractor_is_anchored_on_a_digit_not_on_a_comma` pins the extractor itself.

* **THE SCOPE READER FAILS CLOSED, and is proved so on strings in memory** (behavior 6).
  A reader that silently returns the wrong span reports agreement between the wrong two
  things, which is worse than no check. Zero anchor occurrences RAISES (the paragraph was
  reworded away) and so do two or more (a pasted duplicate would let a stale copy answer
  for the live one). Every known-bad is a MUTATION of the committed paragraph that asserts
  its own premise -- a no-op `replace` would turn a bad fixture into a copy of the good
  one and the test would pass while measuring nothing.

* **BEHAVIOR 4's FALSE UNIVERSAL IS ASSERTED ABSENT, not present.** The spec's original
  clause "and no other verdict moves" was falsified in the fix round and struck; this
  module asserts the phrase does NOT occur, and asserts the replacement claim (PRESENT,
  MANUAL and NOT_APPLICABLE decided WITHOUT consulting the cut, so a `content_absent` cut
  head can read PRESENT) instead. Pinning the struck phrase would re-publish a falsehood.

* **BEHAVIOR 4's SURVIVING CLAIMS ARE MEASURED, not only grepped.** A soundness rule that
  is greppable and FALSE is worse than one that is missing, so every claim a gate author
  would act on is also driven through `run_check`: the `content_absent` cut head that reads
  PRESENT where a full read reads MANUAL (the over-report the paragraph admits); PRESENT,
  MANUAL and NOT_APPLICABLE unmoved in verdict AND in reason by a cut that provably
  happened; the MANUAL case doubling as proof that the downgrade needs BOTH halves of its
  condition (a cut domain with no mitigation stays MANUAL); and "per rule, not per scan"
  shown by a mitigation whose only hit sits in the SECOND file of its own domain, so one
  check reads twice the patched cap. Each live test asserts its own premise (the domain
  really exceeds the cap, the uncut side really reads the control verdict), because the
  measured failure mode of this fixture family is a REAL but unrelated verdict.

* **BEHAVIOR 5's FIXTURE GIVES THE MITIGATION ITS OWN GLOB.** Measured trap: with
  `present_when` and `mitigated_when` sharing one glob, a patched cap hides the MITIGATION
  too and `run_check` answers MANUAL ("no signature and no mitigation detected") -- a real
  verdict, and an unrelated one, so a test asserting only `verdict is not ABSENT` would
  pass while proving nothing about the transition under test. `code/*.py` (three files,
  cut) and `guard/*.py` (one file, never cut) keep the cap cutting the `present_when`
  domain ALONE, and the assertion names the exact verdict on both sides of the pair.

* **BEHAVIOR 7 (zero bytes under `src/`) IS A DIFF PROPERTY, so it is measured by the
  stage and not faked here.** A committed test cannot observe its own commit's diff, and
  this suite shells out to git nowhere. What IS committed is the observable consequence:
  behavior 5's pair proves the paragraph documents the SHIPPED behaviour, needing no
  source change to be true.

* **BEHAVIOR 8 IS PROVED BY DELETION, IN MEMORY.** Removing this iteration's paragraph
  from the document must leave iteration 118's enumeration sentence byte-identical -- which
  is stronger than a diff against HEAD, because it stays true and stays non-vacuous after
  this iteration commits. The scope reader from `tests/_key_enumeration.py` is REUSED
  rather than copied, so the two brakes cannot drift apart.

* **BEHAVIOR 9 IS PINNED AS "ONE DRIFT SURFACE", not as a second copy of iteration 70's
  bytes.** `tests/test_iter70_behavior.py:202` already byte-pins README's UNKNOWN row;
  re-asserting those bytes here would create the second pin the spec exists to avoid. This
  module instead asserts that README and VISION publish NEITHER the constant's name NOR its
  value NOR this paragraph's anchor, so the figure lives in exactly one place.

* **No absolute machine path, employer or personal identifier, or real name appears here.**
  The repo root is derived from `__file__`; every fixture lives under pytest's `tmp_path`.
  Nothing under `gaps/`, `src/`, `README.md` or `PRODUCT.md` is edited to make an
  assertion true.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import Verdict, evaluate, run_check

from _key_enumeration import enumeration_sentence

#: Repo root, derived from this file so no absolute machine path is written down.
REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final[pathlib.Path] = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
README_PATH: Final[pathlib.Path] = REPO_ROOT / "README.md"
VISION_PATH: Final[pathlib.Path] = REPO_ROOT / "VISION.md"

#: The paragraph anchor (behavior 1). It names neither a figure nor a verdict, so the
#: equalities below cannot be satisfied by the way this module LOCATES the prose.
ANCHOR: Final[str] = "The search cap and the one verdict it can change"

#: The constant's own name, the one token code and document must agree on (behavior 3).
CONSTANT_NAME: Final[str] = "MAX_SCAN_FILES"

#: Behavior 2's extractor: maximal runs of digits and commas that BEGIN with a digit.
#: See the module docstring on why the leading `\d` is load-bearing.
_FIGURE_RE: Final[re.Pattern[str]] = re.compile(r"\d[\d,]*")

#: Markers carry the iteration number so no other fixture in the suite can collide.
MARK: Final[str] = "GAPMARK203"
MITIG: Final[str] = "MITIGMARK203"


class CapParagraphError(Exception):
    """The paragraph could not be READ, so no verdict about it is available.

    Deliberately distinct from a defect, exactly as `_key_enumeration.KeyEnumerationError`
    is. A defect is a disagreement between a documented figure and the constant, both of
    which were understood; this is an input whose shape defeats the question -- a missing
    or duplicated anchor, or a document with no `## radar scan` section to hold it.
    """


# --------------------------------------------------------------------------------------
# Pure functions over text: every rule is drivable from a string in memory (behavior 6)
# --------------------------------------------------------------------------------------


def contract_text() -> str:
    """The committed consumer contract, as published bytes.

    A separate function so a caller can mutate the returned string IN MEMORY to build a
    known-bad, instead of editing the file on disk and having to put it back.
    """
    return CONTRACT_PATH.read_text(encoding="utf-8")


def scan_section_span(text: str) -> tuple[int, int]:
    """`(start, end)` byte offsets of the `## radar scan` section. FAILS CLOSED.

    Ends at the next level-2 heading, or at the end of the document. Raises when the
    section cannot be identified uniquely: an empty or ambiguous span would make
    "the paragraph is inside the section" pass for the wrong reason.
    """
    headings = [(m.start(), m.group(0)) for m in re.finditer(r"^## .*$", text, re.M)]
    if not headings:
        raise CapParagraphError(
            "no level-2 headings found: the document's shape defeats the reader, which is "
            "not the same as a document with nothing to flag")
    hits = [i for i, (_, line) in enumerate(headings) if "radar scan" in line]
    if len(hits) != 1:
        raise CapParagraphError(
            f"{len(hits)} level-2 heading(s) name `radar scan`, expected exactly 1 -- the "
            "section that must hold the cap paragraph cannot be located, so no claim about "
            "where the paragraph sits may be reported")
    i = hits[0]
    end = headings[i + 1][0] if i + 1 < len(headings) else len(text)
    return headings[i][0], end


def cap_paragraph_span(text: str) -> tuple[int, int]:
    """`(start, end)` of the blank-line-delimited paragraph carrying `ANCHOR`. FAILS CLOSED.

    Zero occurrences raises (the paragraph was reworded away); two or more raises (a pasted
    duplicate would let a stale copy answer for the live one).
    """
    hits = [m.start() for m in re.finditer(re.escape(ANCHOR), text)]
    if len(hits) != 1:
        raise CapParagraphError(
            f"the anchor {ANCHOR!r} occurs {len(hits)} time(s), expected exactly 1 -- the "
            "cap paragraph cannot be read, so no agreement between the published figure "
            f"and {CONSTANT_NAME} may be reported")
    start = text.rfind("\n\n", 0, hits[0])
    start = 0 if start < 0 else start + 2
    end = text.find("\n\n", hits[0])
    end = len(text) if end < 0 else end
    return start, end


def cap_paragraph(text: str) -> str:
    """The one paragraph that publishes the search cap, without its trailing blank line."""
    start, end = cap_paragraph_span(text)
    return text[start:end]


def documented_figures(paragraph: str) -> set[str]:
    """Every integer literal in `paragraph`: digit-led runs of digits and commas, commas
    stripped. Behavior 2's set, on the side the DOCUMENT owns."""
    return {match.group(0).replace(",", "") for match in _FIGURE_RE.finditer(paragraph)}


def figure_defects(paragraph: str, constant: int) -> list[str]:
    """Every disagreement between the paragraph's figures and `constant`, as readable lines.

    Both directions, and each message NAMES both sides: "the sets differ" would send a
    reader off to do by hand the comparison this brake exists to have already done.
    """
    documented = documented_figures(paragraph)
    expected = str(constant)
    if not documented:
        return [
            f"the cap paragraph publishes NO integer at all, so the value of {CONSTANT_NAME} "
            f"({expected}) reaches no reader: a consumer cannot size a target against prose"
        ]
    defects: list[str] = []
    for figure in sorted(documented - {expected}):
        defects.append(
            f"the cap paragraph publishes {figure}, which {CONSTANT_NAME} does not carry "
            f"(its value is {expected})")
    if expected not in documented:
        defects.append(
            f"{CONSTANT_NAME} is {expected} and the cap paragraph never publishes that "
            f"figure; it publishes {sorted(documented)}")
    return defects


def _normalised(chunk: str) -> str:
    """Whitespace collapsed to single spaces: the document is hard-wrapped, so every phrase
    a reader greps for may be split across a line break by a reflow that changed nothing."""
    return re.sub(r"\s+", " ", chunk).strip()


def _mutated(text: str, old: str, new: str) -> str:
    """Replace `old` once, asserting the mutation actually changed the text.

    A known-bad that silently no-ops reads exactly like a check that passed.
    """
    assert text.count(old) == 1, f"premise: {old!r} is not uniquely locatable"
    out = text.replace(old, new)
    assert out != text, f"premise: replacing {old!r} with {new!r} changed nothing"
    return out


# --------------------------------------------------------------------------------------
# Behavior 1: one bold-led paragraph, one anchor, inside `## radar scan`, no new heading
# --------------------------------------------------------------------------------------


def test_b1_the_anchor_occurs_exactly_once_in_the_contract() -> None:
    text = contract_text()
    assert text.count(ANCHOR) == 1, (
        f"the anchor {ANCHOR!r} occurs {text.count(ANCHOR)} time(s); the brake needs exactly "
        "one, since a duplicate lets a stale copy answer for the live one")


def test_b1_the_paragraph_lies_inside_the_radar_scan_section() -> None:
    text = contract_text()
    section_start, section_end = scan_section_span(text)
    para_start, para_end = cap_paragraph_span(text)
    assert section_start < para_start, (
        "the cap paragraph starts before the `## radar scan` heading, so a consumer reading "
        "that section never meets it")
    assert para_end <= section_end, (
        "the cap paragraph runs past the end of the `## radar scan` section, so it documents "
        "the verb from outside the verb's own section")


def test_b1_the_paragraph_is_one_bold_led_paragraph_and_adds_no_heading() -> None:
    para = cap_paragraph(contract_text())
    assert para.startswith("**" + ANCHOR), (
        f"the paragraph must OPEN with the bold-led anchor; it opens {para[:60]!r}")
    assert "\n\n" not in para, "the span is one paragraph by construction"
    offenders = [line for line in para.splitlines() if line.startswith("#")]
    assert offenders == [], (
        f"the new text adds a heading {offenders}, so `tests/test_contract_verb_headings.py` "
        "would need an edit this iteration promised not to make")


def test_b1_the_paragraph_holds_no_heading_of_the_document() -> None:
    """The other direction of "no new `## ` heading": no heading the document HAS lives
    inside the span, so the paragraph cannot have swallowed one either."""
    text = contract_text()
    start, end = cap_paragraph_span(text)
    inside = [m.group(0) for m in re.finditer(r"^#+ .*$", text, re.M)
              if start <= m.start() < end]
    assert inside == [], f"a heading lies inside the cap paragraph: {inside}"


# --------------------------------------------------------------------------------------
# Behavior 2: the published figure set EQUALS {str(checks.MAX_SCAN_FILES)}, both ways
# --------------------------------------------------------------------------------------


def test_b2_the_published_figure_set_equals_the_constant() -> None:
    para = cap_paragraph(contract_text())
    assert documented_figures(para) == {str(checks.MAX_SCAN_FILES)}, (
        f"published figures {sorted(documented_figures(para))} against "
        f"{CONSTANT_NAME}={checks.MAX_SCAN_FILES}: "
        + "; ".join(figure_defects(para, checks.MAX_SCAN_FILES)))


def test_b2_the_committed_paragraph_reports_no_figure_defect() -> None:
    """The same equality through the reporting function, so its message path is exercised
    on the real document and not only on synthetic input."""
    assert figure_defects(cap_paragraph(contract_text()), checks.MAX_SCAN_FILES) == []


def test_b2_the_extractor_is_anchored_on_a_digit_not_on_a_comma() -> None:
    """The measured failure of the literal reading: `[0-9,]+` matches the paragraph's PROSE
    commas, which strip to the empty string, so the set gains `''` and the both-directions
    equality reds on a CORRECT document. The digit-anchored form is what makes the equality
    usable, so it is pinned rather than left to a future reader to rediscover."""
    para = cap_paragraph(contract_text())
    assert "," in para, "premise: the paragraph contains prose commas at all"
    naive = {run.replace(",", "") for run in re.findall(r"[0-9,]+", para)}
    assert "" in naive, (
        "premise: the comma-led form really does produce an empty token on this paragraph, "
        f"got {sorted(naive)}")
    assert "" not in documented_figures(para), (
        "the shipped extractor must not admit an empty token, or the equality against the "
        "constant can never hold")


def test_b2_a_paragraph_with_no_integer_is_a_defect() -> None:
    """The second direction the spec names explicitly: silence is a defect, not a pass."""
    text = contract_text()
    para = cap_paragraph(text)
    figure = str(checks.MAX_SCAN_FILES)
    stripped = _mutated(para, figure, "a bounded number of")
    assert documented_figures(stripped) == set(), (
        f"premise: the mutation removed every figure, got {documented_figures(stripped)}")
    defects = figure_defects(stripped, checks.MAX_SCAN_FILES)
    assert defects, "a paragraph publishing no integer passed as agreeing with the constant"
    assert any(figure in d and CONSTANT_NAME in d for d in defects), (
        f"the message must name the constant and its value; got {defects}")


# --------------------------------------------------------------------------------------
# Behavior 3: the constant's name, and the two verdict names read from the enum
# --------------------------------------------------------------------------------------


def test_b3_the_paragraph_names_the_constant_verbatim() -> None:
    para = cap_paragraph(contract_text())
    assert CONSTANT_NAME in para, (
        f"the paragraph publishes a figure without naming {CONSTANT_NAME}, so a reader "
        "cannot find the code the figure came from")


@pytest.mark.parametrize("verdict", [Verdict.ABSENT, Verdict.UNKNOWN])
def test_b3_both_verdict_names_are_the_enums_own_values(verdict: Verdict) -> None:
    """Read from the enum at test time, never hand-typed: renaming a verdict reds this
    brake instead of leaving the contract naming a verdict that no longer exists."""
    para = cap_paragraph(contract_text())
    assert verdict.value in para, (
        f"the paragraph never names {verdict.value!r}, which is the verdict the transition "
        "it documents runs between")


def test_b3_the_transition_is_written_in_the_enums_own_tokens() -> None:
    norm = _normalised(cap_paragraph(contract_text()))
    transition = f"{Verdict.ABSENT.value} -> {Verdict.UNKNOWN.value}"
    assert transition in norm, (
        f"the paragraph must state the transition as {transition!r} so a reader can grep it; "
        "a prose-only description leaves the direction ambiguous")
    assert f"{Verdict.UNKNOWN.value} -> {Verdict.ABSENT.value}" not in norm, (
        "the reverse transition is not a thing the cap can do, and publishing it would tell "
        "a gate that an incomplete search can become a safety claim")


# --------------------------------------------------------------------------------------
# Behavior 4: the claims a reader can act on -- and the struck universal, asserted ABSENT
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "claim, fragment",
    [
        ("the bound is per rule, not per scan", "per rule"),
        ("the bound is per rule, not per scan", "not per scan"),
        ("the cut is weighed in exactly one place", "the only place the cut is WEIGHED"),
        ("the other verdicts never consult the cut", "decided WITHOUT consulting the cut"),
        ("the rule kind whose positive is an absence is named", "`content_absent`"),
        ("a cut head can over-report", "can read PRESENT where a full read would not"),
        ("such an UNKNOWN means an incomplete search", "the search was incomplete"),
        ("it never means no gap here", "no gap here"),
        ("a gate must treat it as un-answered", "un-answered"),
        ("and never as a pass", "never as a pass"),
    ],
)
def test_b4_every_actionable_claim_is_present(claim: str, fragment: str) -> None:
    """Matched over whitespace-normalised text: the document is hard-wrapped, so a phrase a
    reader greps may be split across a line break by a reflow that changed nothing."""
    norm = _normalised(cap_paragraph(contract_text()))
    assert fragment in norm, f"the paragraph does not state {claim!r} (missing {fragment!r})"


@pytest.mark.parametrize(
    "verdict", [Verdict.PRESENT, Verdict.MANUAL, Verdict.NOT_APPLICABLE])
def test_b4_the_three_verdicts_decided_without_the_cut_are_named(verdict: Verdict) -> None:
    """The replacement for the struck universal: the paragraph must say WHICH verdicts do
    not consult the cut, by name, so a reader can check the claim instead of trusting it."""
    para = cap_paragraph(contract_text())
    assert verdict.value in para, (
        f"the paragraph claims some verdicts are decided without consulting the cut but "
        f"never names {verdict.value!r}")


def test_b4_the_struck_false_universal_does_not_appear() -> None:
    """`pm.md`'s `[AMENDED IN FIX ROUND 203]` clause: the original wording "and no other
    verdict moves" is FALSE -- a `content_absent` leaf returns the negation of what it
    found, so a cut head makes that rule's own positive MORE likely -- and the amended spec
    says the phrase is deliberately absent. Asserted here so a later edit cannot quietly
    re-publish the falsehood."""
    text = contract_text()
    assert "no other verdict moves" not in _normalised(text), (
        "the falsified universal is back in the contract; the true statement is that the "
        "cut is WEIGHED on one transition, not that no other verdict can move")


def test_b4_the_dropped_locators_are_explained_rather_than_silent() -> None:
    """The paragraph documents a verb whose UNKNOWN carries no locators (measured in
    behavior 5: `locations == []`). A document that published the transition and not the
    drop would leave a gate author expecting evidence that never arrives."""
    norm = _normalised(cap_paragraph(contract_text()))
    assert "locators are dropped" in norm, (
        "the paragraph never says the mitigation's locators are dropped with the verdict, "
        "which is observable behaviour a consumer will otherwise read as a bug")


# --------------------------------------------------------------------------------------
# Behavior 5: code and document agree, proved over a live invocation and its control
# --------------------------------------------------------------------------------------


def _downgrade_target(tmp_path: pathlib.Path) -> pathlib.Path:
    """Three clean `code/*.py` files (the domain the cap will cut) and ONE `guard/*.py`
    holding the mitigation (a domain of one, so no cap in this test can cut it).

    The separate glob is the whole point: sharing one glob lets a patched cap hide the
    MITIGATION too, and `run_check` then answers MANUAL -- a real verdict, and not the one
    under test. See the module docstring.
    """
    root = tmp_path / "target"
    (root / "code").mkdir(parents=True)
    (root / "guard").mkdir(parents=True)
    for i in (1, 2, 3):
        (root / "code" / f"f{i:02d}.py").write_text("a clean line\n", encoding="utf-8")
    (root / "guard" / "g.py").write_text(MITIG + "\n", encoding="utf-8")
    return root


def _downgrade_check() -> dict:
    return {
        "id": "CHK-9203",
        "present_when": {"kind": "content_matches", "globs": ["code/*.py"], "pattern": MARK},
        "mitigated_when": {"kind": "content_matches", "globs": ["guard/*.py"], "pattern": MITIG},
    }


def test_b5_the_control_over_the_whole_domain_is_absent(tmp_path) -> None:
    """The uncut side. Without it, the cut side's UNKNOWN could be a blanket downgrade
    rather than the transition the document publishes."""
    out = run_check(_downgrade_check(), _downgrade_target(tmp_path))
    assert out.verdict is Verdict.ABSENT, (
        f"a whole search that found no signature and a mitigation must stay "
        f"{Verdict.ABSENT.value}; got {out.verdict.value} ({out.reason!r})")
    assert out.locations == ["guard/g.py:1"], (
        f"premise: the mitigation IS findable, so the cut is what hides it; got {out.locations}")


def test_b5_the_cut_domain_downgrades_to_unknown_and_names_the_constant(
        tmp_path, monkeypatch) -> None:
    """The fixture recipe of `tests/test_iter112_behavior.py` and
    `tests/test_iter94_behavior.py`: `MAX_SCAN_FILES` monkeypatched small is the ONLY thing
    that moves between this test and the control above."""
    target = _downgrade_target(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    out = run_check(_downgrade_check(), target)
    assert out.verdict is Verdict.UNKNOWN, (
        f"a non-match over a domain the cap CUT cannot support {Verdict.ABSENT.value}; got "
        f"{out.verdict.value} ({out.reason!r})")
    assert CONSTANT_NAME in out.reason, (
        f"the reason must name the constant that caused the downgrade; got {out.reason!r}")
    assert out.locations == [], (
        f"a verdict that no longer claims safety has nothing to point at; got {out.locations}")


def test_b5_the_token_in_the_reason_is_the_token_in_the_document(tmp_path, monkeypatch) -> None:
    """The agreement the spec asks for, spelled as one assertion: the SAME token appears in
    the live `reason` and in the published paragraph, so a rename in either place reds."""
    target = _downgrade_target(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    reason = run_check(_downgrade_check(), target).reason
    para = cap_paragraph(contract_text())
    shared = {CONSTANT_NAME} & set(re.findall(r"[A-Z_]{4,}", reason)) & set(
        re.findall(r"[A-Z_]{4,}", para))
    assert shared == {CONSTANT_NAME}, (
        f"the live reason and the published paragraph must share the token {CONSTANT_NAME}; "
        f"reason={reason!r}")


def test_b5_the_mitigation_domain_is_never_the_cut_one(tmp_path, monkeypatch) -> None:
    """The fixture's own trap, asserted so a later edit cannot reintroduce it: under the
    patched cap the mitigation rule must still read its whole domain, or the UNKNOWN above
    would be MANUAL for an unrelated reason."""
    target = _downgrade_target(tmp_path)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    mitigation = evaluate(_downgrade_check()["mitigated_when"], target)
    assert mitigation.matched is True, "the mitigation must survive the cap"
    assert mitigation.truncated_files == 0, (
        f"the mitigation domain was cut ({mitigation.truncated_files} files), so this fixture "
        "no longer tests the transition it claims to")
    present = evaluate(_downgrade_check()["present_when"], target)
    assert present.matched is False and present.truncated_files == 3, (
        "premise: the present_when domain is the one the cap cut; got "
        f"matched={present.matched} truncated={present.truncated_files}")


# --------------------------------------------------------------------------------------
# Behavior 6: the scope reader fails closed, on synthetic strings
# --------------------------------------------------------------------------------------


def test_b6_zero_anchor_occurrences_raises() -> None:
    text = contract_text()
    bad = _mutated(text, ANCHOR, "Some other bold lead")
    assert ANCHOR not in bad, "premise: the anchor really is gone"
    with pytest.raises(CapParagraphError) as excinfo:
        cap_paragraph(bad)
    assert "0 time(s)" in str(excinfo.value)


def test_b6_two_anchor_occurrences_raise() -> None:
    text = contract_text()
    para = cap_paragraph(text)
    bad = _mutated(text, para, para + "\n\n" + para)
    assert bad.count(ANCHOR) == 2, f"premise: the duplicate landed, count={bad.count(ANCHOR)}"
    with pytest.raises(CapParagraphError) as excinfo:
        cap_paragraph(bad)
    assert "2 time(s)" in str(excinfo.value)


def test_b6_a_disagreeing_figure_is_reported_and_names_both_sides() -> None:
    """A defect, not an exception: the paragraph was READ, and what it says is wrong."""
    real = str(checks.MAX_SCAN_FILES)
    wrong = str(checks.MAX_SCAN_FILES + 1)
    para = _mutated(cap_paragraph(contract_text()), real, wrong)
    assert documented_figures(para) == {wrong}, (
        f"premise: the mutation moved the figure, got {documented_figures(para)}")
    defects = figure_defects(para, checks.MAX_SCAN_FILES)
    assert defects, "a documented figure the constant does not carry passed as agreement"
    joined = " ".join(defects)
    assert wrong in joined and real in joined, (
        f"the message must name the DOCUMENTED figure and the CONSTANT's value; got {defects}")
    assert CONSTANT_NAME in joined, f"the message must name the constant; got {defects}"


def test_b6_an_extra_figure_is_reported_even_when_the_right_one_is_there() -> None:
    """The subtler direction: the correct figure present AND a second one added. A subset
    check would pass this; the set equality must not."""
    real = str(checks.MAX_SCAN_FILES)
    extra = str(checks.MAX_SCAN_FILES + 7)
    para = _mutated(cap_paragraph(contract_text()), "A content rule reads",
                    f"A content rule reads (see also {extra})")
    figures = documented_figures(para)
    assert figures == {real, extra}, f"premise: both figures are present, got {figures}"
    defects = figure_defects(para, checks.MAX_SCAN_FILES)
    assert defects, "an extra documented figure passed as agreement with the constant"
    assert extra in " ".join(defects), f"the message must name the extra figure; got {defects}"


def test_b6_the_committed_paragraph_is_the_known_good_of_every_mutation() -> None:
    """Anti-vacuity for the four mutations above: the UNMUTATED paragraph must report no
    defect and must not raise, or "the bad fixture failed" would prove nothing."""
    text = contract_text()
    assert figure_defects(cap_paragraph(text), checks.MAX_SCAN_FILES) == []
    assert cap_paragraph(text).startswith("**")


def test_b6_the_section_reader_fails_closed_on_a_document_without_the_section() -> None:
    with pytest.raises(CapParagraphError):
        scan_section_span("# Doc\n\nprose only, no headings\n")
    with pytest.raises(CapParagraphError):
        scan_section_span("# Doc\n\n## Exit codes\n\nprose\n")
    doubled = "# Doc\n\n## `radar scan` one\n\np\n\n## `radar scan` two\n\np\n"
    with pytest.raises(CapParagraphError):
        scan_section_span(doubled)


def test_b6_the_readers_answer_a_synthetic_good_document() -> None:
    """The other side of fail-closed: a minimal document the rules ACCEPT, so the readers
    are rules rather than a blanket refusal. Built from the constant, never hand-typed."""
    figure = str(checks.MAX_SCAN_FILES)
    doc = (
        "# Doc\n\n## Exit codes\n\nprose\n\n## `radar scan` - the verb (SHIPPED)\n\n"
        f"**{ANCHOR}.** A content rule reads at most {figure} files per evaluation "
        f"(`{CONSTANT_NAME}`).\n\n## What a consumer must never do\n\nprose\n")
    section_start, section_end = scan_section_span(doc)
    para_start, para_end = cap_paragraph_span(doc)
    assert section_start < para_start and para_end <= section_end
    assert figure_defects(cap_paragraph(doc), checks.MAX_SCAN_FILES) == []


# --------------------------------------------------------------------------------------
# Behaviors 7 and 8: nothing else in the document or the product moved
# --------------------------------------------------------------------------------------


def test_b7_the_paragraph_documents_the_shipped_behaviour_so_no_source_change_is_needed(
        tmp_path, monkeypatch) -> None:
    """Behavior 7 is a DIFF property (zero bytes under `src/agent_gap_radar/`) and no test
    in this suite shells out to git. Its observable consequence is committed instead: the
    two verdicts the paragraph publishes are what the SHIPPED code already returns over one
    fixture, with the cap as the only variable -- so the document needed no code to change
    in order to be true."""
    target = _downgrade_target(tmp_path)
    whole = run_check(_downgrade_check(), target)
    monkeypatch.setattr(checks, "MAX_SCAN_FILES", 2)
    cut = run_check(_downgrade_check(), target)
    assert (whole.verdict, cut.verdict) == (Verdict.ABSENT, Verdict.UNKNOWN), (
        f"the documented transition is not what the code does: {whole.verdict.value} -> "
        f"{cut.verdict.value}")


def test_b8_removing_the_cap_paragraph_leaves_the_enumeration_sentence_byte_identical() -> None:
    """Iteration 118's `scan --json` key enumeration must be untouched, and unsatisfiable
    by this iteration's prose. Proved by DELETION in memory rather than by a diff against
    HEAD, so the assertion stays non-vacuous after this iteration commits.

    `enumeration_sentence` is imported from `tests/_key_enumeration.py` rather than
    reimplemented, so the two brakes cannot drift apart.
    """
    text = contract_text()
    start, end = cap_paragraph_span(text)
    without = text[:start] + text[min(end + 2, len(text)):]
    assert without != text, "premise: the deletion removed the paragraph"
    assert ANCHOR not in without, "premise: the whole paragraph went, not part of it"
    assert enumeration_sentence(without) == enumeration_sentence(text), (
        "this iteration's paragraph changed the bytes of the `scan --json` enumeration "
        "sentence, so iteration 118's both-directions key brake would need an edit")


def test_b8_the_two_spans_do_not_overlap() -> None:
    text = contract_text()
    sentence = enumeration_sentence(text)
    enum_start = text.index(sentence)
    enum_end = enum_start + len(sentence)
    para_start, para_end = cap_paragraph_span(text)
    assert para_end <= enum_start or enum_end <= para_start, (
        "the cap paragraph overlaps the enumeration sentence, so this iteration's prose "
        "could satisfy iteration 118's key equality")


def test_b8_the_cap_paragraph_contributes_no_key_name_to_the_enumeration() -> None:
    """The paragraph's own backticked tokens must not be key names of the payload, or a
    reader could mistake the cap's constant for a `scan --json` key."""
    para = cap_paragraph(contract_text())
    sentence = enumeration_sentence(contract_text())
    assert CONSTANT_NAME not in sentence, (
        f"{CONSTANT_NAME} appears in the enumeration sentence, which would publish it as a "
        "payload key it is not")
    assert str(checks.MAX_SCAN_FILES) not in sentence, (
        "the cap's figure appears inside the key enumeration sentence")
    assert CONSTANT_NAME in para, "premise: the token really is published in the paragraph"


# --------------------------------------------------------------------------------------
# Behavior 9: one drift surface -- the figure is published in exactly ONE document
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", [README_PATH, VISION_PATH])
def test_b9_the_figure_is_published_nowhere_else(path: pathlib.Path) -> None:
    """`README.md` is deliberately unchanged: its UNKNOWN row is already true of a truncated
    search and `tests/test_iter70_behavior.py:202` byte-pins it. Rather than re-pinning
    those bytes here (a SECOND pin on one sentence is the drift surface this iteration
    exists to avoid), this asserts the property the decision bought: neither the constant's
    name, nor its value, nor this paragraph's anchor appears outside the contract."""
    text = path.read_text(encoding="utf-8")
    figure = str(checks.MAX_SCAN_FILES)
    for token in (CONSTANT_NAME, figure, f"{figure[:1]},{figure[1:]}", ANCHOR):
        assert token not in text, (
            f"{path.name} publishes {token!r}: the figure now has two drift surfaces, and "
            "the second one is pinned by no brake")


def test_b9_the_readme_still_calls_an_unknown_an_incomplete_search() -> None:
    """The reason README needed no edit, asserted as a property and not as a byte pin: the
    row that describes UNKNOWN already covers a truncated search, so this iteration's
    paragraph and README agree without publishing the figure twice."""
    readme = _normalised(README_PATH.read_text(encoding="utf-8"))
    assert "its search was incomplete" in readme, (
        "README's UNKNOWN row no longer says a search can be incomplete, so the contract's "
        "new paragraph is the only place a consumer can learn it")


# --------------------------------------------------------------------------------------
# Behavior 4, LIVE: the paragraph's behavioural claims measured against the shipped code
#
# The block above proves the claims are PRESENT as prose. A published soundness rule that
# is greppable and false is worse than one that is missing, so each claim a consumer would
# act on is also driven through `run_check` here, on a fixture whose ONLY moving part is
# the patched cap. Every verdict below was MEASURED before it was asserted.
# --------------------------------------------------------------------------------------

#: The patched cap used by every live proof below. Small, and never the constant's value:
#: the fixtures are three-file domains, so a cap of 2 leaves a head of 2 and an unread tail.
CUT_CAP: Final[int] = 2

CLEAN: Final[str] = "a clean line\n"


def _target(tmp_path: pathlib.Path, tree: dict[str, str]) -> pathlib.Path:
    """Write `tree` (relative path -> content) under `tmp_path/target`, return the root."""
    root = tmp_path / "target"
    for rel, content in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _content_rule(kind: str, glob: str, pattern: str) -> dict:
    return {"kind": kind, "globs": [glob], "pattern": pattern}


def _domain_exceeds_the_cap(target: pathlib.Path, subdir: str) -> None:
    """Premise for every cut fixture: the domain really is larger than the patched cap, so
    a difference between the two sides is attributable to the cut and not to the tree."""
    files = sorted(p.name for p in (target / subdir).iterdir())
    assert len(files) > CUT_CAP, (
        f"premise: {subdir}/ holds {files}, which a cap of {CUT_CAP} does not cut, so no "
        "claim about a cut head could be attributed to the cap")


def test_b4_live_a_cut_head_can_read_present_where_a_full_read_would_not(
        tmp_path, monkeypatch) -> None:
    """The paragraph's sharpest claim, and the one a gate author is most likely to doubt:
    where a rule's own positive is an ABSENCE, the cap can OVER-report a gap.

    Measured on a `content_absent` rule whose disqualifying match sits in the TAIL file:
    over the whole domain the match is found and the rule's positive is false (MANUAL);
    over the head the match is unreachable and the same rule reports PRESENT. The direction
    is load-bearing -- with the match in the HEAD both sides answer MANUAL and the fixture
    proves nothing while looking healthy -- so the tail placement is asserted as a premise.
    """
    target = _target(tmp_path, {
        "code/f01.py": CLEAN,
        "code/f02.py": CLEAN,
        "code/f03.py": MARK + " here\n",
    })
    _domain_exceeds_the_cap(target, "code")
    check = {"id": "CHK-9203-ABS",
             "present_when": _content_rule("content_absent", "code/*.py", MARK)}

    full = run_check(check, target)
    assert full.verdict is Verdict.MANUAL, (
        "premise: over its WHOLE domain the rule meets the disqualifying match, so its own "
        f"positive (an absence) is false; got {full.verdict.value} ({full.reason!r})")

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", CUT_CAP)
    cut = run_check(check, target)
    assert cut.verdict is Verdict.PRESENT, (
        f"the contract publishes that a cut head 'can read {Verdict.PRESENT.value} where a "
        f"full read would not'; over the cut head this rule answered {cut.verdict.value} "
        f"({cut.reason!r}), so the published claim is not what the code does")
    assert CONSTANT_NAME not in cut.reason, (
        f"the paragraph says {Verdict.PRESENT.value} is decided WITHOUT consulting the cut; "
        f"a reason naming {CONSTANT_NAME} here would contradict it: {cut.reason!r}")


def _unweighed_case(name: str) -> tuple[dict, dict[str, str], Verdict]:
    """`(check, tree, expected)` for each verdict the paragraph says is decided WITHOUT
    consulting the cut. Every tree's searched domain is three files, i.e. cut by `CUT_CAP`."""
    clean_three = {f"code/f{i:02d}.py": CLEAN for i in (1, 2, 3)}
    if name == Verdict.PRESENT.value:
        tree = dict(clean_three, **{"code/f01.py": MARK + " here\n"})
        return ({"id": "CHK-9203-P",
                 "present_when": _content_rule("content_matches", "code/*.py", MARK)},
                tree, Verdict.PRESENT)
    if name == Verdict.MANUAL.value:
        # No signature AND no mitigation: the downgrade needs BOTH halves of the condition
        # the paragraph publishes, so a cut domain alone must NOT move this verdict.
        return ({"id": "CHK-9203-M",
                 "present_when": _content_rule("content_matches", "code/*.py", MARK),
                 "mitigated_when": _content_rule("content_matches", "guard/*.py", MITIG)},
                dict(clean_three, **{"guard/g.py": CLEAN}), Verdict.MANUAL)
    if name == Verdict.NOT_APPLICABLE.value:
        return ({"id": "CHK-9203-N",
                 "applies_when": _content_rule("content_matches", "code/*.py", MITIG),
                 "present_when": _content_rule("content_matches", "code/*.py", MARK)},
                clean_three, Verdict.NOT_APPLICABLE)
    raise AssertionError(f"no fixture for {name}")


@pytest.mark.parametrize(
    "verdict", [Verdict.PRESENT, Verdict.MANUAL, Verdict.NOT_APPLICABLE])
def test_b4_live_the_three_unweighed_verdicts_do_not_move_when_the_cap_cuts(
        verdict: Verdict, tmp_path, monkeypatch) -> None:
    """The replacement claim for the struck universal, proved rather than paraphrased: for
    each of the three verdicts the paragraph names, the cut changes NEITHER the verdict NOR
    the reason, and the reason never names the constant. This is weaker than "no other
    verdict moves" (which is false: the test above measures a PRESENT that the cut created)
    and it is exactly what the amended document claims -- these three are decided without
    the cut being WEIGHED, on a fixture where the domain provably was cut."""
    check, tree, expected = _unweighed_case(verdict.value)
    target = _target(tmp_path, tree)
    _domain_exceeds_the_cap(target, "code")

    full = run_check(check, target)
    assert full.verdict is expected, (
        f"premise: uncut, this fixture reads {expected.value}; got {full.verdict.value} "
        f"({full.reason!r})")

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", CUT_CAP)
    cut = run_check(check, target)
    assert (cut.verdict, cut.reason) == (full.verdict, full.reason), (
        f"the cap moved a verdict the contract says it never weighs: {full.verdict.value} "
        f"({full.reason!r}) -> {cut.verdict.value} ({cut.reason!r})")
    assert CONSTANT_NAME not in cut.reason, (
        f"{expected.value} is published as decided WITHOUT consulting the cut, yet its "
        f"reason names {CONSTANT_NAME}: {cut.reason!r}")


def test_b4_live_the_bound_is_per_rule_and_not_per_scan(tmp_path, monkeypatch) -> None:
    """"per rule on one record, not per scan": under ONE patched cap, two rules of the same
    check each get the whole budget over their OWN domain.

    The mitigation's only hit sits in the SECOND file of its own three-file domain, so
    reaching it means that rule read `CUT_CAP` files AFTER `present_when` had already read
    `CUT_CAP` files of another domain -- 2 x `CUT_CAP` files under a cap of `CUT_CAP`. A
    per-SCAN budget would have left the mitigation nothing to read, the mitigation would
    not have matched, and the verdict would be MANUAL instead of the published UNKNOWN.
    """
    target = _target(tmp_path, {
        "code/f01.py": CLEAN, "code/f02.py": CLEAN, "code/f03.py": CLEAN,
        "guard/g01.py": CLEAN, "guard/g02.py": MITIG + "\n", "guard/g03.py": CLEAN,
    })
    _domain_exceeds_the_cap(target, "code")
    _domain_exceeds_the_cap(target, "guard")
    check = {"id": "CHK-9203-PERRULE",
             "present_when": _content_rule("content_matches", "code/*.py", MARK),
             "mitigated_when": _content_rule("content_matches", "guard/*.py", MITIG)}

    full = run_check(check, target)
    assert full.verdict is Verdict.ABSENT, (
        f"premise: uncut, no signature plus a mitigation reads {Verdict.ABSENT.value}; got "
        f"{full.verdict.value} ({full.reason!r})")

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", CUT_CAP)
    mitigation = evaluate(check["mitigated_when"], target)
    assert mitigation.locations == ["guard/g02.py:1"], (
        f"the mitigation's only hit is in file {CUT_CAP} of its own domain; finding it is "
        "what proves the budget is per rule rather than shared across the check; got "
        f"{mitigation.locations}")
    cut = run_check(check, target)
    assert cut.verdict is Verdict.UNKNOWN, (
        f"with a per-rule budget the mitigation matches and the cut non-match downgrades to "
        f"{Verdict.UNKNOWN.value}; a shared per-scan budget would read "
        f"{Verdict.MANUAL.value}. Got {cut.verdict.value} ({cut.reason!r})")
    assert CONSTANT_NAME in cut.reason, (
        f"the one weighed transition must name {CONSTANT_NAME}; got {cut.reason!r}")


@pytest.mark.parametrize(
    "claim, fragment",
    [
        ("the bound is per record, not per target", "not per target"),
        ("the over-report is silent", "can over-report a gap silently"),
        ("only the safety-claiming verdict is protected",
         f"only {Verdict.ABSENT.value} is protected"),
        ("the reason is the channel that names the cut",
         "`reason` is where the cut is named"),
    ],
)
def test_b4_the_remaining_actionable_claims_are_published(claim: str, fragment: str) -> None:
    """The clauses that make the paragraph ACTIONABLE rather than merely true: a gate author
    needs to know the exposure is silent, that only one verdict is protected, and which
    field distinguishes this UNKNOWN from an UNKNOWN whose check never ran."""
    norm = _normalised(cap_paragraph(contract_text()))
    assert fragment in norm, f"the paragraph does not state {claim!r} (missing {fragment!r})"


def test_b4_no_payload_key_separates_the_two_causes_of_unknown() -> None:
    """The paragraph's closing claim, held against iteration 118's key enumeration: the
    `reason` string really is the only channel, because the published payload names no
    truncation key. The day one is added, this reds and the paragraph must be re-written --
    which is the point, since the sentence promises a consumer there is none YET."""
    sentence = enumeration_sentence(contract_text())
    for token in ("truncat", "domain_size", "capped", CONSTANT_NAME.lower()):
        assert token not in sentence.lower(), (
            f"the payload enumeration names {token!r}, so the contract's claim that the cut "
            "is only visible in `reason` is stale")
    assert "`reason`" in sentence, (
        "premise: `reason` IS a published payload key, which is what makes it usable as the "
        "channel the paragraph points a gate at")


# --------------------------------------------------------------------------------------
# Behavior 4, LIVE over the WHOLE VERB: the bound is not pooled per scan or per target,
# and a larger domain really is answered over its HEAD.
#
# Added in the third round of this stage. The two rounds before it left `not per target`
# and `answers over the head of it` pinned as TEXT ONLY -- and a published soundness claim
# that is greppable and false is worse than one that is missing, so both are measured here.
# The first drives `scan()` (the verb a gate consumes) over a two-record register, which is
# the only shape that can refute POOLING: `run_check` on its own cannot, since each call
# would get a fresh budget under a per-scan rule too.
# --------------------------------------------------------------------------------------


def _cap_record(gid: str, cid: str, guard_glob: str) -> dict:
    """A schema-valid record whose check has the downgrade shape: a `present_when` over the
    domain the cap will cut, and a `mitigated_when` over its OWN glob.

    The fixtures are two-sided (`models.Check` requires them whenever `present_when` is set)
    and they discriminate on the same glob the rule searches, so this record would survive
    the anti-fail-open harness if it were ever promoted -- it is not: it lives in `tmp_path`.
    """
    return {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}],
        "check": {
            "id": cid, "rationale": "r", "manual_question": "q",
            "present_when": _content_rule("content_matches", "code/*.py", MARK),
            "mitigated_when": _content_rule("content_matches", guard_glob, MITIG),
            "fixtures": {"bad": {"code/a.py": MARK + "\n"},
                         "good": {"code/a.py": CLEAN}},
        },
    }


def _register(root: pathlib.Path, records: list[dict]) -> pathlib.Path:
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    for rec in records:
        (gaps / f"{rec['id']}.json").write_text(__import__("json").dumps(rec, sort_keys=True),
                                                encoding="utf-8")
    return gaps


def test_b4_live_the_bound_is_not_pooled_per_scan_or_per_target(tmp_path, monkeypatch) -> None:
    """"not per scan and not per target", proved on the verb rather than on one check.

    ONE scan, ONE target, TWO records, ONE patched cap of `CUT_CAP`. Record A's rules read
    `CUT_CAP` files of `code/` plus its guard file; record B's rules then read `CUT_CAP` more
    files of `code/` and reach a mitigation whose only hit sits in the SECOND file of its own
    domain. That is ~3x `CUT_CAP` files inside one scan of one target, so a budget pooled per
    scan or per target would have left record B's mitigation unread -- its verdict would be
    MANUAL ("no signature and no mitigation detected") instead of the published UNKNOWN.
    Both records must therefore report the SAME downgrade, and the assertion names it.
    """
    from agent_gap_radar.registry import load_all
    from agent_gap_radar.scan import scan

    target = _target(tmp_path, {
        "code/f01.py": CLEAN, "code/f02.py": CLEAN, "code/f03.py": CLEAN,
        "guardA/g.py": MITIG + "\n",
        "guardB/g01.py": CLEAN, "guardB/g02.py": MITIG + "\n", "guardB/g03.py": CLEAN,
    })
    _domain_exceeds_the_cap(target, "code")
    _domain_exceeds_the_cap(target, "guardB")
    gaps = _register(tmp_path, [_cap_record("GAP-921", "CHK-921", "guardA/*.py"),
                                _cap_record("GAP-922", "CHK-922", "guardB/*.py")])
    records = load_all(gaps)
    assert len(records) == 2, f"premise: the register holds both records, got {len(records)}"

    whole = {f.gap.id: f.outcome for f in scan(records, target).findings}
    assert {gid: o.verdict for gid, o in whole.items()} == {
        "GAP-921": Verdict.ABSENT, "GAP-922": Verdict.ABSENT}, (
        "premise: uncut, every record of this register reads "
        f"{Verdict.ABSENT.value}; got {[(g, o.verdict.value) for g, o in whole.items()]}")

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", CUT_CAP)
    cut = {f.gap.id: f.outcome for f in scan(records, target).findings}
    assert sorted(cut) == ["GAP-921", "GAP-922"], (
        f"both records must still be reported after the cut; got {sorted(cut)}")
    for gid, outcome in sorted(cut.items()):
        assert outcome.verdict is Verdict.UNKNOWN, (
            f"{gid} read {outcome.verdict.value} ({outcome.reason!r}): with a budget pooled "
            f"per scan or per target the second record's mitigation would be unread and its "
            f"verdict would be {Verdict.MANUAL.value}, which is what the contract's "
            "'not per scan and not per target' denies")
        assert CONSTANT_NAME in outcome.reason, (
            f"{gid}: the one weighed transition must name the constant; got {outcome.reason!r}")
        assert outcome.locations == [], (
            f"{gid}: a verdict that no longer claims safety has nothing to point at; got "
            f"{outcome.locations}")


def test_b4_live_a_larger_domain_is_answered_over_its_head(tmp_path, monkeypatch) -> None:
    """"a rule whose domain is larger answers over the head of it", measured at the rule.

    Two trees identical but for WHERE the only match sits. Under the same patched cap the
    match in the HEAD is still found, at its own location, and the match in the TAIL is not
    found at all -- so the unread part is the tail in path order and not an arbitrary subset,
    which is what makes the published word "head" honest. `truncated_files` reports the
    DOMAIN SIZE rather than the unread remainder, so it is asserted as the domain size.
    """
    rule = _content_rule("content_matches", "code/*.py", MARK)
    trees = {
        "head": {"code/f01.py": MARK + " here\n", "code/f02.py": CLEAN, "code/f03.py": CLEAN},
        "tail": {"code/f01.py": CLEAN, "code/f02.py": CLEAN, "code/f03.py": MARK + " here\n"},
    }
    targets = {where: _target(tmp_path / where, tree) for where, tree in trees.items()}
    for where, target in targets.items():
        _domain_exceeds_the_cap(target, "code")
        full = evaluate(rule, target)
        assert (full.matched, full.truncated_files) == (True, 0), (
            f"premise: over the WHOLE domain the {where} match is found and nothing is cut; "
            f"got matched={full.matched} truncated={full.truncated_files}")

    monkeypatch.setattr(checks, "MAX_SCAN_FILES", CUT_CAP)
    head = evaluate(rule, targets["head"])
    tail = evaluate(rule, targets["tail"])
    assert head.locations == ["code/f01.py:1"], (
        f"the head of the domain must still be searched; got {head.locations}")
    assert (tail.matched, tail.locations) == (False, []), (
        f"the tail past the cap must be unread, so its match is invisible; got "
        f"matched={tail.matched} locations={tail.locations}")
    assert head.truncated_files == tail.truncated_files == 3, (
        "both sides must report the size of the domain they were HANDED, or a cut answer "
        f"could pass as a complete one; got {head.truncated_files} and "
        f"{tail.truncated_files}")


# --------------------------------------------------------------------------------------
# The module itself
# --------------------------------------------------------------------------------------


def test_the_cap_value_is_never_hand_typed_in_this_module() -> None:
    """The pin's whole value is that it is DERIVED: a hand-typed copy of the figure would
    let this brake agree with a stale document the day the constant changes. So the value
    appears NOWHERE in this file -- not in an assertion, not in a comment, not in prose.

    The premise keeps the guard from colliding with the small integers this module's
    fixtures legitimately contain (a patched cap of 2, a domain of 3 files): it holds only
    while the constant is a figure no fixture would spell. If the constant is ever set
    below that, this test reds LOUDLY with the reason instead of silently weakening.
    """
    figure = str(checks.MAX_SCAN_FILES)
    assert checks.MAX_SCAN_FILES >= 100, (
        f"premise: {CONSTANT_NAME} is {figure}, small enough to collide with this module's "
        "fixture integers -- rescope this guard rather than deleting it")
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    occurrences = [
        f"line {n}: {line.strip()}" for n, line in enumerate(source.splitlines(), start=1)
        if figure in line
    ]
    assert occurrences == [], (
        f"the constant's value {figure} is written literally at: {occurrences}")


def test_no_test_in_this_module_stands_down() -> None:
    """A stood-down test is invisible in a suite total, so none is allowed here."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    # Assembled from fragments so this check cannot match its own literals -- a
    # self-matching guard fails on a healthy file, which is a fail-CLOSED detector.
    banned = ("pytest." + "skip(", "pytest." + "xfail(", "mark." + "skip", "mark." + "xfail")
    for token in banned:
        assert token not in source, f"a test stands down via {token}"
    assert "mark.parametrize" in source, "anti-vacuity: the guard must read real markers"
