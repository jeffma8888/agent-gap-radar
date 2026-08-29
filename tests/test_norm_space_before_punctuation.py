"""A tag boundary before punctuation must not make an honest quote unverifiable.

THIRD instance of the fail-CLOSED family this module's own docstring records. The
first was curly quotes normalised on one side only; the second was `<code>` tags
replaced by a space, so `<code>outputSchema</code>:` read as `outputschema :`. This
is the same shape one step out: the tags whose removal inserts a space are not only
`code`, they are every tag NOT in INLINE_ZERO_WIDTH_TAGS -- and `<strong>x</strong>.`
or `<em>y</em>,` are ordinary formatting that appears in normal prose.

The consequence was measured, not imagined. A real partition pass over the live
backlog quarantined exactly two records, and BOTH were false accusations: the quotes
are present on their cited pages, character for character, and differ from the
normalised page only by a space sitting before a colon or a full stop. That is worse
than the ratchet it replaced, because a veto blocks work whereas a false quarantine
files honest research as fabricated.

The fixtures below are real page text, taken from the two pages that were wrongly
accused, and the quotes are the ones the records actually cite.
"""

from __future__ import annotations

import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import verify_quotes as vq  # noqa: E402


def test_a_space_before_a_colon_does_not_hide_a_real_quote():
    """openai-agents-python encrypted_session: `<strong>Automatic expiration</strong>:`"""
    page = vq.page_text(
        "<li><strong>Automatic expiration</strong>: Old items are silently "
        "skipped when TTL expires</li>")
    quote = "Automatic expiration: Old items are silently skipped when TTL expires"
    assert vq.classify(quote, page) == vq.VERBATIM


def test_a_space_before_a_full_stop_does_not_hide_a_real_quote():
    """Manus blog: `<strong>restorable</strong>.`"""
    page = vq.page_text(
        "<p>Our compression strategies are always designed to be "
        "<strong>restorable</strong>. For instance, the content of a web page can "
        "be dropped from the context as long as the URL is preserved</p>")
    quote = ("Our compression strategies are always designed to be restorable. "
             "For instance, the content of a web page can be dropped from the "
             "context as long as the URL is preserved")
    assert vq.classify(quote, page) == vq.VERBATIM


def test_the_same_holds_for_the_other_common_punctuation():
    for markup, quote in [
        ("<em>alpha</em>, then beta", "alpha, then beta"),
        ("<b>gamma</b>; then delta", "gamma; then delta"),
        ("<i>epsilon</i>! loud", "epsilon! loud"),
        ("<span>zeta</span>? asking", "zeta? asking"),
        ("<a href='#'>eta</a>: defined", "eta: defined"),
    ]:
        assert vq.classify(quote, vq.page_text(f"<p>{markup}</p>")) == vq.VERBATIM, markup


def test_normalisation_is_applied_to_BOTH_sides():
    """The one-normaliser rule: a quote may carry the stray space instead."""
    page = vq.page_text("<p>Old items are silently skipped.</p>")
    assert vq.classify("Old items are silently skipped .", page) == vq.VERBATIM


def test_a_genuinely_absent_quote_is_still_not_found():
    """The repair must not buy a false PASS: this is the property being protected."""
    page = vq.page_text("<p>Old items are silently skipped when TTL expires</p>")
    assert vq.classify("Old items are retained forever regardless of TTL", page) \
        == vq.NOT_FOUND


def test_words_are_not_merged_across_a_block_boundary():
    """Collapsing space before punctuation must not also join two separate words,
    which is the FALSE-pass direction and the reason the zero-width tag set is small."""
    page = vq.page_text("<td>alpha</td><td>beta</td>")
    assert vq.classify("alphabeta", page) == vq.NOT_FOUND
