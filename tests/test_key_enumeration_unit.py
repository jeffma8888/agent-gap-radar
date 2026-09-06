"""Unit tests for the `_key_enumeration` oracle: does the checker actually check?

These ask ONE question -- does each rule fire on a known-bad and stay silent on a known-good
-- and they never read the committed `docs/CONSUMER_CONTRACT.md`, so they hold whatever state
that document is in. That separation is the point: the committed file can only ever
demonstrate the PASSING side of a set equality, so absence of a defect over it is evidence
only once the same function has been shown to produce one.

Every bad fixture is a MUTATION of the good one and asserts its own premise. A silently
no-op replace would turn a known-bad fixture into a copy of the known-good one, and the test
would then pass while measuring nothing -- the fail-open this product has already paid for on
other surfaces.

The token names here are deliberately NOT this product's key names. A fixture that reused
them could pass because the oracle hard-coded the real contract somewhere, which is the one
thing a derived brake must never do.
"""

from __future__ import annotations

import pytest

from _key_enumeration import (
    ENUMERATION_ANCHOR,
    KeyEnumerationError,
    backticked_tokens,
    defect_message,
    documented_keys,
    emitted_keys,
    enumeration_sentence,
    key_set_defects,
)

#: A document shaped like the real one: prose before the anchor, a hard-wrapped enumeration
#: sentence, and prose after it that backticks tokens which are NOT in the list. The tokens
#: outside the sentence are what makes the scope decision visible at all.
GOOD = (
    "Prose before the anchor names `before_token` and ends here.\n"
    "\n"
    "**a marker.** " + ENUMERATION_ANCHOR + " `alpha`, `beta`,\n"
    "`gamma`. `gamma` is discussed after the list, next to `after_token`.\n"
)
SENTENCE = ENUMERATION_ANCHOR + " `alpha`, `beta`,\n`gamma`."
LISTED = {"alpha", "beta", "gamma"}


def _finding(**extra: object) -> dict[str, object]:
    """A payload finding. Keys are fixture names, never this product's real ones."""
    return {"f_one": 1, "f_two": 2, **extra}


def _payload(**extra: object) -> dict[str, object]:
    return {"t_one": 1, "findings": [_finding()], **extra}


# --------------------------------------------------------------------------- the scope

def test_the_sentence_is_the_anchored_span_terminator_included():
    assert enumeration_sentence(GOOD) == SENTENCE
    assert enumeration_sentence(GOOD).startswith(ENUMERATION_ANCHOR)
    assert enumeration_sentence(GOOD).endswith("`gamma`.")


def test_the_sentence_stops_before_the_prose_that_follows_it():
    """The whole value of the scope: `after_token` is backticked and is not a key."""
    assert "`after_token`" in GOOD, "premise: the fixture has a token after the sentence"
    assert "after_token" not in documented_keys(GOOD)


def test_a_terminator_at_the_very_end_of_the_text_still_terminates():
    """A document whose last character is the period; there is no whitespace to look at."""
    text = "**a marker.** " + ENUMERATION_ANCHOR + " `alpha`."
    assert not text.endswith("\n"), "premise: nothing follows the terminating period"
    assert enumeration_sentence(text) == ENUMERATION_ANCHOR + " `alpha`."


def test_a_period_not_followed_by_whitespace_does_not_end_the_sentence():
    """A decimal or an abbreviation inside the list must not truncate the scope."""
    text = "**a marker.** " + ENUMERATION_ANCHOR + " `alpha` (see 3.5), `beta`. After.\n"
    assert "3.5" in text, "premise: the fixture carries a mid-sentence period"
    assert backticked_tokens(enumeration_sentence(text)) == {"alpha", "beta"}


def test_deleting_the_terminator_grows_the_scope_rather_than_shrinking_it():
    """Fail-closed direction: a reflow that loses the period must ADD tokens, not lose them.

    Growth is reported as an EXTRA by `key_set_defects`, so the answer is a disagreement. A
    reader is told the scope is wrong; they are never told everything is fine.
    """
    mutated = GOOD.replace("`gamma`.", "`gamma`")
    assert mutated != GOOD, "premise: the terminating period was actually removed"
    grown = backticked_tokens(enumeration_sentence(mutated))
    assert LISTED < grown, grown
    assert "after_token" in grown


def test_truncating_the_sentence_shrinks_the_scope_and_loses_a_token():
    mutated = GOOD.replace("`alpha`, `beta`,\n`gamma`.", "`alpha`.")
    assert mutated != GOOD, "premise: the list was actually truncated"
    assert backticked_tokens(enumeration_sentence(mutated)) == {"alpha"}


# ------------------------------------------------------------------- the scope fails closed

@pytest.mark.parametrize("count", [0, 2])
def test_an_anchor_that_is_not_unique_is_refused(count: int):
    """Zero occurrences means the sentence was reworded away; two means a pasted duplicate."""
    if count == 0:
        text = GOOD.replace(ENUMERATION_ANCHOR, "some other lead-in:")
    else:
        text = GOOD + "\n" + GOOD
    assert text.count(ENUMERATION_ANCHOR) == count, "premise: the fixture has that many"
    with pytest.raises(KeyEnumerationError) as caught:
        enumeration_sentence(text)
    assert ENUMERATION_ANCHOR in str(caught.value)
    assert "reflow" in str(caught.value)


def test_an_unterminated_sentence_is_refused():
    text = ENUMERATION_ANCHOR + " `alpha`, `beta`\n"
    assert "." not in text, "premise: the fixture has no period at all"
    with pytest.raises(KeyEnumerationError) as caught:
        enumeration_sentence(text)
    assert ENUMERATION_ANCHOR in str(caught.value)
    assert "reflow" in str(caught.value)


# ---------------------------------------------------------------- the token rule, unfiltered

@pytest.mark.parametrize("token", [".", "score", "open", "rank", "a b c", "not-an-ident"])
def test_no_token_shape_is_privileged_or_excluded(token: str):
    """No allowlist, no exclusion set, no identifier filter: the SCOPE is the only rule.

    A shape filter would silently drop a drift that spells a key with a space, a dot or a
    hyphen -- which is exactly the misspelling a consumer meets as a lookup failure.
    """
    assert backticked_tokens("prose `" + token + "` prose") == {token}


def test_a_token_wrapped_across_a_line_break_is_not_a_token():
    """A reader cannot grep it, so the document does not get credit for it."""
    assert backticked_tokens("`wrapped\nacross`") == set()


def test_documented_keys_is_the_sentence_scope_and_nothing_else():
    assert documented_keys(GOOD) == LISTED


# ------------------------------------------------------------------------ the emitted side

def test_emitted_keys_unions_the_top_level_and_the_per_finding_keys():
    assert emitted_keys(_payload()) == {"t_one", "findings", "f_one", "f_two"}


def test_emitted_keys_unions_over_every_finding_not_just_the_first():
    payload = {"t_one": 1, "findings": [_finding(), _finding(f_three=3)]}
    assert "f_three" in emitted_keys(payload)


@pytest.mark.parametrize("findings", [[], None, "not a list"])
def test_a_payload_without_findings_is_refused(findings: object):
    """It supplies no per-finding key, so answering would report correct names as EXTRA."""
    payload: dict[str, object] = {"t_one": 1}
    if findings is not None:
        payload["findings"] = findings
    with pytest.raises(KeyEnumerationError) as caught:
        emitted_keys(payload)
    assert "findings" in str(caught.value)


def test_a_finding_that_is_not_an_object_is_refused():
    with pytest.raises(KeyEnumerationError) as caught:
        emitted_keys({"t_one": 1, "findings": ["a string"]})
    assert "str" in str(caught.value)


# ------------------------------------------------------------------------ the two directions

def test_agreement_reports_no_defect():
    assert key_set_defects(LISTED, LISTED) == ([], [])


def test_the_missing_direction_is_reported_and_sorted():
    missing, extra = key_set_defects({"beta"}, {"alpha", "beta", "gamma"})
    assert (missing, extra) == (["alpha", "gamma"], [])


def test_the_extra_direction_is_reported_and_sorted():
    missing, extra = key_set_defects({"alpha", "beta", "zulu"}, {"alpha", "beta"})
    assert (missing, extra) == ([], ["zulu"])


def test_both_directions_are_reported_at_once():
    missing, extra = key_set_defects({"alpha", "zulu"}, {"alpha", "beta"})
    assert (missing, extra) == (["beta"], ["zulu"])


def test_an_empty_emitted_set_is_refused():
    """Two empty sets agree with each other; that green means nothing."""
    with pytest.raises(KeyEnumerationError) as caught:
        key_set_defects(set(), set())
    assert "empty" in str(caught.value)


# --------------------------------------------------------------------------- the message

def test_the_message_names_every_offending_token():
    text = defect_message(["beta"], ["zulu"])
    assert "beta" in text and "zulu" in text
    assert "NOT named in the enumeration sentence" in text
    assert "NOT emitted by the tool" in text


def test_the_message_of_no_defect_states_the_equality():
    assert defect_message([], []) == "the documented key set equals the emitted key set"
