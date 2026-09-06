"""Iteration 118 behaviors: the consumer contract's `scan --json` key list is held to
the emitter in BOTH directions, over a sentence-scoped reader with zero exceptions.

Black-box, and the isolation contract is honored: nothing here reads `src/`, the
engineer's notes, the reviewer's notes, or a diff. Every assertion either drives the
public `scan` / `scan_json` API and reads the bytes it emitted, reads a PUBLISHED
document (`docs/CONSUMER_CONTRACT.md`), or reads a file under `tests/` -- the surfaces
the isolation contract names as readable.

No expected key SET is spelled here: the 20 keys are taken from the payload the tool
emitted, so a key renamed in the product moves no literal in this file. Three key names
do appear as SUBSCRIPTS (`findings`, `gap_id`, `below_floor`) because that is how the
per-finding census and the below-floor invariant are reached; behavior 2's census permits
a subscript by design and forbids exactly the shapes an exception list takes. This module
carries no per-token exception of any kind, which that AST census PROVES over its own
source rather than promising in prose.

Cost: one `scan` of a `tmp_path` target, built once per module. No subprocess is spawned
and no live scan of this repo is run (spec acceptance criterion: the tester stage's
median sits at the 600s cap, and those two are how a test module burns it).
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import scan, scan_json

from _key_enumeration import (backticked_tokens, contract_text, defect_message,
                              documented_keys, emitted_keys, enumeration_sentence,
                              key_set_defects)
from test_iter02_behavior import _record, _target, _write_register

TESTS_DIR = pathlib.Path(__file__).resolve().parent

#: Spec behavior 1, quoted from the spec and not from the document.
ANCHOR = "A gate gets a stable object:"
#: Spec behavior 1: the sentence ends with these exact 9 characters.
SENTENCE_TAIL = "`status`."
#: Spec behavior 2.
EXPECTED_KEY_COUNT = 20
#: Spec behavior 3: three tokens the tool does NOT emit. Each test asserts that premise.
NOT_EMITTED_TOKENS = ("score", "open", "rank")
#: Spec behavior 6: iteration 13's committed pin, byte-identical.
ITER13_OBLIGATION = "Every key the tool emits must appear in this list"
#: Spec behavior 7: the paragraph iteration 13's subset claim is scoped to.
PARAGRAPH_MARKER = "**`scan --json` SHIPPED.**"
#: Spec behavior 5(a): the refusal must be legible as a scope failure.
REFLOW_WORD = "reflow"

#: The two source files this iteration's oracle lives in. Behavior 2's census reads BOTH:
#: the spec scopes "no exception list" to the new module, but an exception would really
#: hide in the shared reader, so both are held to it.
ORACLE_SOURCES = ("test_iter118_behavior.py", "_key_enumeration.py")

#: An identifier carrying one of these reads as a per-token escape hatch.
FORBIDDEN_IDENT_MARKS = ("exclu", "allowlist", "allow_list", "whitelist", "exempt",
                         "special", "ignore", "skip", "waive")


# ---------------------------------------------------------------------------
# Fixture builders. `_record` / `_target` / `_write_register` come from
# tests/test_iter02_behavior.py, the shape every behavior module here uses: the check
# travels INSIDE the record, so the finding is PRESENT because of the fixture tree and
# never because of a committed register record.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def payload(tmp_path_factory):
    """`scan --json`'s own emitted bytes, decoded. Built once for the module."""
    root = tmp_path_factory.mktemp("iter118")
    reg = _write_register(root / "reg", [_record("GAP-800", 4, 3, 3, check_id="CHK-800")])
    emitted_bytes = scan_json(scan(load_all(reg), _target(root / "hit")))
    decoded = json.loads(emitted_bytes)
    assert decoded["findings"], (
        "premise: the payload carries at least one finding, so the per-finding key "
        "census is non-empty")
    return decoded


@pytest.fixture(scope="module")
def emitted(payload):
    """Every key the tool emitted: top level plus per finding."""
    keys = emitted_keys(payload)
    assert keys, "premise: the emitted key census is non-empty"
    return keys


@pytest.fixture()
def text():
    """The committed consumer contract, decoded, for in-memory mutation."""
    return contract_text()


def _first_key(sentence):
    """The first backticked token of the enumeration sentence, DERIVED not spelled."""
    match = re.search(r"`([^`\n]+)`", sentence)
    assert match is not None, "premise: the enumeration sentence backticks something"
    return match.group(1)


def _swap_sentence(text, new_sentence):
    """A copy of the document whose enumeration sentence is `new_sentence`.

    Asserts its own premises: the sentence occurs exactly once (so the replace cannot
    hit a stale duplicate) and the result actually differs from the original (so a no-op
    replace cannot let a known-bad fixture pass as a copy of the known-good one).
    """
    sentence = enumeration_sentence(text)
    assert text.count(sentence) == 1, (
        "premise: the enumeration sentence appears exactly once in the document")
    mutated = text.replace(sentence, new_sentence, 1)
    assert mutated != text, "premise: the mutation changed the document"
    return mutated


def _defects(text, emitted):
    return key_set_defects(documented_keys(text), emitted)


# ---------------------------------------------------------------------------
# Behavior 1 -- the scope reader is anchored, total, and self-checking.
# ---------------------------------------------------------------------------

def test_b1_the_scope_starts_at_the_anchor_and_ends_at_the_terminating_period(text):
    sentence = enumeration_sentence(text)
    assert sentence.startswith(ANCHOR), (
        f"the scope must begin at {ANCHOR!r}; it begins {sentence[:40]!r}")
    assert sentence.endswith(SENTENCE_TAIL), (
        f"the scope must end at {SENTENCE_TAIL!r}; it ends {sentence[-40:]!r}")
    assert len(SENTENCE_TAIL) == 9, "spec behavior 1 prices the tail at 9 characters"


def test_b1_the_scope_holds_no_blank_line(text):
    """A blank line means the scope ran past its own paragraph."""
    sentence = enumeration_sentence(text)
    assert "\n\n" not in sentence
    assert sentence.strip() == sentence.rstrip(), "no leading whitespace in the scope"


def test_b1_the_scope_is_a_verbatim_substring_appearing_exactly_once(text):
    """The reader must SLICE the document, not paraphrase it."""
    sentence = enumeration_sentence(text)
    assert text.count(sentence) == 1


def test_b1_a_terminator_at_end_of_text_still_terminates_the_scope(text):
    """Spec behavior 1's second branch: `.` followed by whitespace OR by END OF TEXT.

    The committed document exercises only the whitespace branch, so the other branch is
    untested over it -- and an unread branch is where a reader stops being total.
    """
    first = _first_key(enumeration_sentence(text))
    minimal = ANCHOR + " `" + first + "`."
    assert not minimal.endswith(" "), "premise: the terminator IS the last character"
    assert enumeration_sentence(minimal) == minimal


def test_b1_a_scope_with_no_terminator_at_all_fails_closed(text):
    """Totality: an anchor with no sentence-terminating period after it has NO answer."""
    first = _first_key(enumeration_sentence(text))
    _refusal(ANCHOR + " `" + first + "`")


# ---------------------------------------------------------------------------
# Behavior 2 -- equality over the committed document, both directions, zero exclusions.
# ---------------------------------------------------------------------------

def test_b2_documented_equals_emitted_over_the_committed_document(text, emitted):
    documented = backticked_tokens(enumeration_sentence(text))
    missing, extra = key_set_defects(documented, emitted)
    assert (missing, extra) == ([], []), defect_message(missing, extra)
    assert documented == emitted


def test_b2_the_emitted_census_is_twenty_keys(emitted, payload):
    top = set(payload.keys())
    per_finding = set(payload["findings"][0].keys())
    assert top.isdisjoint(per_finding), (
        "premise: the two key sets are disjoint, so the union is a complete census")
    assert len(emitted) == EXPECTED_KEY_COUNT
    assert len(top) + len(per_finding) == EXPECTED_KEY_COUNT


def test_b2_documented_keys_is_exactly_the_sentence_scoped_token_set(text):
    """The composed entry point must use behavior 1's scope and nothing wider."""
    assert documented_keys(text) == backticked_tokens(enumeration_sentence(text))


def test_b2_no_exception_of_any_shape_names_an_emitted_key(emitted):
    """An exclusion set, allowlist or exception list is a COLLECTION OF KEY NAMES; a
    per-token special case is a COMPARISON against one. Both are censused here.

    The census runs over the AST of both oracle sources, so a comment or docstring that
    merely discusses exceptions can neither pass nor fail it -- only real code can. It is
    ARMED in-place first, against a synthetic module built from a key the tool really
    emits, because a census that cannot fail proves nothing about the file it scanned.
    A bare `payload["findings"]` is deliberately NOT a hit: that is how the per-finding
    census is reached, and banning it would need the exception list this forbids.
    """
    probe_key = sorted(emitted)[0]
    armed = ast.parse(
        f"BAD = {{{probe_key!r}}}\n"
        f"def f(k):\n    return k == {probe_key!r}\n")
    assert _named_keys(armed, emitted) == [probe_key], (
        "premise: the census reports a key named in a set literal or a comparison")

    for name in ORACLE_SOURCES:
        tree = ast.parse((TESTS_DIR / name).read_text(encoding="utf-8"), filename=name)
        found = _named_keys(tree, emitted)
        assert found == [], f"{name} special-cases emitted key(s): {found}"


def test_b2_no_identifier_reads_as_a_per_token_escape_hatch(emitted):
    for name in ORACLE_SOURCES:
        tree = ast.parse((TESTS_DIR / name).read_text(encoding="utf-8"), filename=name)
        hits = sorted({ident for ident in _identifiers(tree)
                       for mark in FORBIDDEN_IDENT_MARKS if mark in ident.lower()})
        assert hits == [], f"{name} carries escape-hatch identifier(s): {hits}"


_COLLECTION_NODES = (ast.Set, ast.List, ast.Tuple, ast.Dict)


def _named_keys(tree, emitted):
    """Sorted emitted keys spelled inside a collection display or a comparison."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, _COLLECTION_NODES):
            children = ast.iter_child_nodes(node)
        elif isinstance(node, ast.Compare):
            children = [node.left, *node.comparators]
        else:
            continue
        for child in children:
            if isinstance(child, ast.Constant) and child.value in emitted:
                out.add(child.value)
    return sorted(out)


def _identifiers(tree):
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
        elif isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
        elif isinstance(node, ast.arg):
            out.append(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            out.append(node.arg)
        elif isinstance(node, ast.alias):
            out.append(node.asname or node.name)
    return out


# ---------------------------------------------------------------------------
# Behavior 3 -- armed in the NEW direction: a documented name with no key behind it.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token", NOT_EMITTED_TOKENS)
def test_b3_a_documented_token_the_tool_never_emits_is_reported_as_extra(
        text, emitted, token):
    assert token not in emitted, f"premise: the tool emits no {token!r} key"
    sentence = enumeration_sentence(text)
    mutated = _swap_sentence(text, sentence[:-1] + ", `" + token + "`.")
    missing, extra = _defects(mutated, emitted)
    assert extra == [token], f"inserting `{token}` must be reported as EXTRA"
    assert missing == []
    assert token in defect_message(missing, extra), (
        "the failure message must NAME the offending token")


# ---------------------------------------------------------------------------
# Behavior 4 -- armed in the OLD direction, once per emitted key.
# ---------------------------------------------------------------------------

def test_b4_un_backticking_each_emitted_key_is_reported_as_missing(text, emitted):
    sentence = enumeration_sentence(text)
    for key in sorted(emitted):
        mutated = _swap_sentence(text, sentence.replace("`" + key + "`", key))
        missing, extra = _defects(mutated, emitted)
        assert missing == [key], f"un-backticking {key} must be reported as MISSING"
        assert extra == []
        assert key in defect_message(missing, extra)


# ---------------------------------------------------------------------------
# Behavior 5 -- the scope fails CLOSED on reflow, never into agreement.
# ---------------------------------------------------------------------------

def _refusal(bad_text):
    """`enumeration_sentence` must REFUSE, legibly, and not return a wrong answer."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 -- the type is not the spec
        enumeration_sentence(bad_text)
    assert type(excinfo.value).__module__ != "builtins", (
        "a builtin exception is a crash, not a deliberate refusal")
    message = str(excinfo.value)
    assert ANCHOR in message, f"the refusal must quote the anchor; got {message!r}"
    assert REFLOW_WORD in message, f"the refusal must name reflow; got {message!r}"


def test_b5a_zero_anchor_occurrences_fails_closed(text):
    bad = text.replace(ANCHOR, ANCHOR.replace(":", ";"))
    assert bad.count(ANCHOR) == 0, "premise: the anchor is gone"
    assert bad != text
    _refusal(bad)


def test_b5a_two_anchor_occurrences_fails_closed(text):
    sentence = enumeration_sentence(text)
    bad = text + "\n\n" + ANCHOR + " `" + _first_key(sentence) + "`.\n"
    assert bad.count(ANCHOR) == 2, "premise: the anchor now appears twice"
    _refusal(bad)


def test_b5b_growing_the_scope_yields_an_extra(text, emitted):
    """Delete the terminating period: the scope runs on into the following prose."""
    sentence = enumeration_sentence(text)
    grown = _swap_sentence(text, sentence[:-1])
    assert len(enumeration_sentence(grown)) > len(sentence), (
        "premise: the scope actually GREW")
    missing, extra = _defects(grown, emitted)
    assert extra != [], "a run-on scope must be reported, not tolerated"
    assert defect_message(missing, extra) != ""


def test_b5b_the_prose_just_past_the_scope_backticks_a_non_key(text, emitted):
    """Behavior 5(b)'s arming PREMISE, made explicit rather than assumed.

    The grow-direction defect exists only because the sentences after the scope backtick
    a word that is not a key. If a reflow ever left that prose key-only, 5(b) would go
    vacuous while still passing, so the premise is asserted here in its own right.
    """
    sentence = enumeration_sentence(text)
    tail = text.split(sentence, 1)[1]
    grown = enumeration_sentence(_swap_sentence(text, sentence[:-1]))
    added = backticked_tokens(grown) - backticked_tokens(sentence)
    assert tail, "premise: the document continues past the enumeration sentence"
    assert added - emitted != set(), (
        "the prose the grown scope swallows must contain a non-key backticked token")


def test_b5c_shrinking_the_scope_yields_a_missing(text, emitted):
    """Truncate after the first key: the scope no longer covers the list."""
    sentence = enumeration_sentence(text)
    first = _first_key(sentence)
    assert first in emitted, f"premise: {first!r} is an emitted key"
    shrunk = _swap_sentence(text, ANCHOR + " `" + first + "`.")
    assert len(enumeration_sentence(shrunk)) < len(sentence), (
        "premise: the scope actually SHRANK")
    missing, extra = _defects(shrunk, emitted)
    assert missing != [], "a truncated scope must be reported, not tolerated"
    assert extra == [], "truncation removes names, it does not invent them"


def test_b5_neither_scope_changing_reflow_reports_agreement(text, emitted):
    """The two reflows that MOVE THE BOUNDARY both report a defect, never `([], [])`."""
    sentence = enumeration_sentence(text)
    first = _first_key(sentence)
    reflows = {
        "period deleted (scope grows)": sentence[:-1],
        "truncated after the first key (scope shrinks)": ANCHOR + " `" + first + "`.",
    }
    for label, new_sentence in reflows.items():
        mutated = _swap_sentence(text, new_sentence)
        missing, extra = _defects(mutated, emitted)
        assert (missing, extra) != ([], []), f"{label} reported agreement"


def test_b5_rewrapping_the_sentence_is_not_a_defect(text, emitted):
    """AMBIGUITY, tested on the reasonable reading and reported to the PM.

    Spec behavior 5 ends "No reflow can produce `([], [])`". Read as a UNIVERSAL that is
    false and should be: a reflow that only moves a line break preserves every token, and
    a brake that reddened on line rewrapping would be a brake nobody can edit the
    document around. What must hold -- and what is asserted above -- is that no reflow
    which MOVES THE SCOPE BOUNDARY reports agreement. This test pins the benign case, so
    the two claims are visibly different tests rather than one over-broad one.
    """
    sentence = enumeration_sentence(text)
    assert "\n" in sentence, "premise: the sentence spans a line break to begin with"
    rewrapped = _swap_sentence(text, sentence.replace("\n", " ", 1))
    missing, extra = _defects(rewrapped, emitted)
    assert (missing, extra) == ([], []), defect_message(missing, extra)


# ---------------------------------------------------------------------------
# Behavior 6 -- the document states the obligation it is now held to.
# ---------------------------------------------------------------------------

def _paragraph(text):
    blocks = [b for b in text.split("\n\n") if b.lstrip().startswith(PARAGRAPH_MARKER)]
    assert len(blocks) == 1, (
        f"expected exactly one paragraph opening {PARAGRAPH_MARKER!r}, found "
        f"{len(blocks)}")
    return blocks[0]


def test_b6_iteration13s_obligation_sentence_is_byte_identical(text):
    assert ITER13_OBLIGATION in _paragraph(text)


def test_b6_the_converse_obligation_is_stated(text):
    """The list must also promise it names nothing the tool does not emit."""
    paragraph = _paragraph(text)
    match = re.search(r"no key\b[^.]*\bdoes not emit", paragraph)
    assert match is not None, (
        "the paragraph must state the converse: the list names no key the tool does "
        "not emit")


def test_b6_the_converse_clause_lies_outside_the_scope(text, emitted):
    """The new prose must not join the list it describes."""
    paragraph = _paragraph(text)
    match = re.search(r"no key\b[^.]*\bdoes not emit", paragraph)
    assert match is not None, "premise: behavior 6's converse clause is present"
    sentence = enumeration_sentence(text)
    assert match.group(0) not in sentence
    missing, extra = _defects(text, emitted)
    assert (missing, extra) == ([], []), defect_message(missing, extra)


# ---------------------------------------------------------------------------
# Behavior 7 -- nothing that already worked moves.
# ---------------------------------------------------------------------------

ITER13_MODULE = "test_iter13_behavior.py"
ITER13_B7_TESTS = (
    "test_b7_every_emitted_key_is_documented_in_the_contract_paragraph",
    "test_b7_the_documentation_check_is_armed_for_every_key",
    "test_b7_the_contract_paragraph_appears_exactly_once",
    "test_b7_the_paragraph_states_the_obligation_not_a_claim_about_a_test",
)


def test_b7_iteration13s_four_paragraph_tests_are_all_still_defined():
    tree = ast.parse((TESTS_DIR / ITER13_MODULE).read_text(encoding="utf-8"))
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    missing = sorted(t for t in ITER13_B7_TESTS if t not in defined)
    assert missing == [], f"iteration 13 lost paragraph test(s): {missing}"
    assert len([t for t in defined if t.startswith("test_b7_")]) == 4


def test_b7_the_whole_paragraph_subset_claim_is_still_true(text, emitted):
    """The substance of the four tests above, re-derived independently here."""
    documented = backticked_tokens(_paragraph(text))
    undocumented = sorted(k for k in emitted if k not in documented)
    assert undocumented == []
    assert documented - emitted != set(), (
        "premise: the PARAGRAPH scope is strictly wider than the key set, which is why "
        "iteration 13's claim stays one-directional and this iteration's is not")


def test_b7_the_stale_comment_no_longer_denies_the_reverse_direction():
    source = (TESTS_DIR / ITER13_MODULE).read_text(encoding="utf-8")
    assert "deliberately not asserted" not in source, (
        "the comment still claims the reverse direction is unasserted")
    assert "test_iter118_behavior" in source, (
        "the comment must name the module that now asserts the reverse direction")

# ===========================================================================
# ROUND-2 EXTENSIONS (tester retry, iteration 118).
#
# Round 1 was cut short by the stage cap with a green module and a green full suite.
# Nothing in the tree changed, so this round bought its time back by looking for the
# HOLES in that module rather than re-deriving its greens. Each block below closes one
# claim the previous round asserted only over the committed document, where two
# different readings of the spec are indistinguishable.
# ===========================================================================


# --- Behavior 1: "the FIRST `.` FOLLOWED BY WHITESPACE" has two weaker readings that
# --- the committed sentence cannot tell apart, because it holds exactly one period.

def test_b1_the_scope_ends_at_the_first_terminator_and_not_a_later_one(text):
    """A greedy reader agrees with the spec over the committed document and disagrees
    here, so FIRSTness is untested until a second terminator exists."""
    first = _first_key(enumeration_sentence(text))
    head = ANCHOR + " `" + first + "`."
    synthetic = head + " A later sentence also names `" + first + "` and ends here."
    got = enumeration_sentence(synthetic)
    assert got == head, (
        f"the scope must stop at the FIRST terminator; it returned {got!r}")
    assert len(got) < len(synthetic), "premise: a later terminator existed to run on to"


def test_b1_a_period_not_followed_by_whitespace_does_not_terminate_the_scope(text):
    """The rule is a `.` followed by WHITESPACE (or end of text), not any `.` at all.
    A reader that stopped at every period would still pass over the committed sentence."""
    first = _first_key(enumeration_sentence(text))
    synthetic = ANCHOR + " version 1.5 of the payload lists `" + first + "`."
    got = enumeration_sentence(synthetic)
    assert got == synthetic, f"a decimal point must not end the sentence; got {got!r}"
    assert first in backticked_tokens(got), (
        "the key after the decimal point must stay inside the scope")


def test_b1_the_committed_sentence_holds_exactly_one_period(text):
    """AMBIGUITY, tested on the reasonable reading and reported to the PM as a
    doc-authoring constraint the spec states only implicitly.

    Behavior 1's rule makes `e.g. ` a sentence terminator, so an abbreviation placed
    INSIDE the enumeration sentence silently shrinks the scope -- and a shrunk scope is
    the direction that reports MISSING, so it fails closed rather than into agreement.
    The safe invariant is therefore that the committed sentence carries exactly one
    period, its own terminator; that is asserted here, and the consequence it protects
    against is demonstrated on a synthetic copy so a future author can see the cost."""
    sentence = enumeration_sentence(text)
    assert sentence.count(".") == 1, (
        "the enumeration sentence must hold exactly one period (its terminator); any "
        f"internal period truncates the scope. Sentence: {sentence!r}")
    first = _first_key(sentence)
    abbreviated = ANCHOR + " for instance e.g. `" + first + "`."
    truncated = enumeration_sentence(abbreviated)
    assert truncated.endswith("e.g."), (
        f"spec rule: `e.g. ` terminates the sentence; got {truncated!r}")
    assert first not in backticked_tokens(truncated), (
        "an abbreviation inside the enumeration sentence drops every key after it")


# --- Behavior 2: the census was taken from ONE finding of a ONE-finding payload, and
# --- set equality cannot see a key the document lists twice.

@pytest.fixture(scope="module")
def floor_payload(tmp_path_factory):
    """`scan --json` over a register whose third record sits BELOW the confidence floor.

    A lone `model-output` citation scores 0 against the register's floor of 2
    (tests/test_iter02_behavior.py's module docstring), so GAP-802 is a below-floor
    record. The register's core invariant is that such a record is DISPLAYED, never
    silently dropped -- so the payload a release gate reads carries findings the
    single-finding fixture above never produces, and the document's list has to be
    right for those too."""
    root = tmp_path_factory.mktemp("iter118floor")
    reg = _write_register(root / "reg", [
        _record("GAP-800", 4, 3, 3, check_id="CHK-800"),
        _record("GAP-801", 2, 2, 2, check_id="CHK-801"),
        _record("GAP-802", 5, 5, 5, classes=("model-output",), check_id="CHK-802"),
    ])
    decoded = json.loads(scan_json(scan(load_all(reg), _target(root / "hit"))))
    assert len(decoded["findings"]) == 3, (
        "premise (the register's core invariant): every registered record is DISPLAYED, "
        "including the one below the confidence floor")
    return decoded


def test_b2_the_below_floor_finding_is_displayed_and_keyed_identically(floor_payload):
    findings = floor_payload["findings"]
    assert sorted(f["gap_id"] for f in findings) == ["GAP-800", "GAP-801", "GAP-802"], (
        "a below-floor record must be DISPLAYED, never silently dropped")
    flagged = [f for f in findings if f["below_floor"]]
    assert len(flagged) == 1, (
        f"premise: exactly one of the three records sits below the floor, got "
        f"{len(flagged)}")
    shapes = {frozenset(f.keys()) for f in findings}
    assert len(shapes) == 1, (
        "every finding must carry the SAME key set: if a below-floor finding is keyed "
        "differently, the documented list is wrong for exactly the records the "
        "register's core invariant promises to show")


def test_b2_the_documented_list_also_equals_a_below_floor_payloads_keys(
        text, floor_payload):
    """Behavior 2 re-measured against a payload that is not the single-finding one."""
    emitted_now = emitted_keys(floor_payload)
    missing, extra = key_set_defects(documented_keys(text), emitted_now)
    assert (missing, extra) == ([], []), defect_message(missing, extra)
    assert len(emitted_now) == EXPECTED_KEY_COUNT


def test_b2_the_sentence_lists_each_key_exactly_once(text, emitted):
    """`documented` is a SET, so a key the document names twice is invisible to
    behaviors 2, 3, 4 and 5 alike -- equality still holds over a list that has grown a
    duplicate. Counted here as runs, not as a set."""
    sentence = enumeration_sentence(text)
    runs = re.findall(r"`([^`\n]+)`", sentence)
    duplicated = sorted({run for run in runs if runs.count(run) > 1})
    assert duplicated == [], (
        f"the enumeration sentence names key(s) more than once: {duplicated}")
    assert len(runs) == len(emitted) == EXPECTED_KEY_COUNT, (
        f"the sentence holds {len(runs)} backticked runs for {len(emitted)} keys")


# --- Behaviors 3 and 4: every armed mutation produces exactly ONE defect, so
# --- "each sorted" and "the message names the token" are untested for plural input.

def test_b3_b4_plural_defects_are_sorted_named_and_leave_their_inputs_alone():
    documented = {"zulu", "alpha", "mike", "delta"}
    emitted_side = {"zulu", "yankee", "bravo", "delta"}
    before = (set(documented), set(emitted_side))
    missing, extra = key_set_defects(documented, emitted_side)
    assert missing == ["bravo", "yankee"], "missing must be sorted"
    assert extra == ["alpha", "mike"], "extra must be sorted"
    assert len(missing) > 1 and len(extra) > 1, "premise: both sides are plural"
    message = defect_message(missing, extra)
    unnamed = sorted(n for n in missing + extra if n not in message)
    assert unnamed == [], f"the failure message names no {unnamed}"
    assert (documented, emitted_side) == before, (
        "key_set_defects must be pure: it mutated an argument")


# --- Behavior 5: the mutation NO key-set assertion can see is the TWO-PART one.

def test_b5_the_two_part_reflow_is_caught_only_by_behavior_1s_tail_pin(text, emitted):
    """Delete the terminating period AND un-backtick the prose token the grown scope
    swallows: the key sets AGREE again over a scope that silently covers extra
    sentences. Behaviors 2-5 are all blind to that state -- behavior 1's tail pin is
    the brake that sees it, so the arming is asserted here rather than argued."""
    sentence = enumeration_sentence(text)
    grown_text = _swap_sentence(text, sentence[:-1])
    grown = enumeration_sentence(grown_text)
    added = backticked_tokens(grown) - backticked_tokens(sentence)
    prose = sorted(added - emitted)
    assert prose != [], "premise: the grown scope swallows a backticked non-key"
    two_part = grown_text
    for token in prose:
        two_part = two_part.replace("`" + token + "`", token)
    assert two_part != grown_text, "premise: the second half of the mutation landed"
    missing, extra = key_set_defects(documented_keys(two_part), emitted)
    assert (missing, extra) == ([], []), (
        "premise, and the whole point: the two-part mutation makes the key sets AGREE, "
        f"so no behavior 2/3/4/5 assertion can see it. Got {(missing, extra)!r}")
    two_part_sentence = enumeration_sentence(two_part)
    assert len(two_part_sentence) > len(sentence), "premise: the scope really is wider"
    assert not two_part_sentence.endswith(SENTENCE_TAIL), (
        "behavior 1's tail pin is the only brake on the two-part reflow and it must "
        f"REJECT this scope; it ends {two_part_sentence[-30:]!r}")


# --- Behavior 7: "the four bodies are unedited" is not decidable without a diff, which
# --- the isolation contract forbids. A body GUTTED to `pass` is decidable.

def test_b7_iteration13s_four_paragraph_tests_still_carry_assertions():
    tree = ast.parse((TESTS_DIR / ITER13_MODULE).read_text(encoding="utf-8"))
    bodies = {node.name: node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name in ITER13_B7_TESTS}
    assert sorted(bodies) == sorted(ITER13_B7_TESTS), "premise: all four are present"
    for name, node in sorted(bodies.items()):
        asserts = [inner for inner in ast.walk(node) if isinstance(inner, ast.Assert)]
        assert asserts != [], f"{name} no longer asserts anything"


# ===========================================================================
# ROUND-3 EXTENSIONS (tester retry 2, iteration 118).
#
# Rounds 1 and 2 were both cut short by the stage cap, each leaving a green module and
# (round 2) a green full suite whose log its own report never got to read. Nothing in the
# tree changed, so this round again spent its time on the HOLE rather than on re-deriving
# settled greens. The hole is behavior 2's TOKEN RULE.
#
# Behavior 2 defines a token as "a run containing neither a backtick nor a newline".
# NOTHING in the committed scope exercises either exclusion: all 20 keys are single words,
# and the one backticked token in this document that holds a space (`scan --json`) sits in
# the MARKER sentence, outside behavior 1's scope -- which is precisely the measurement the
# spec's Triage used to drop scout B's exclusion. So a tokenizer that split runs on
# whitespace, or one that matched word characters only, is indistinguishable from the
# spec's tokenizer on every assertion above it -- and it silently BLINDS behavior 4, because
# a documented PHRASE would then satisfy the key it merely contains.
# ===========================================================================


def test_b2_a_backticked_run_holding_a_space_is_ONE_token_not_several(text, emitted):
    """The spec's token is a RUN, so a multi-word backticked run is a single EXTRA."""
    phrase = "not a key"
    assert phrase not in emitted, f"premise: the tool emits no {phrase!r} key"
    for word in phrase.split():
        assert word not in emitted, f"premise: {word!r} is not an emitted key either"
    sentence = enumeration_sentence(text)
    mutated = _swap_sentence(text, sentence[:-1] + ", `" + phrase + "`.")
    missing, extra = _defects(mutated, emitted)
    assert missing == [], f"the insertion removed nothing; got missing={missing!r}"
    assert extra == [phrase], (
        "a backticked run containing a space is ONE token: a tokenizer that split it on "
        f"whitespace reports its words separately instead. Got extra={extra!r}")
    assert phrase in defect_message(missing, extra), (
        "the failure message must name the offending run in full")


def test_b4_a_documented_PHRASE_does_not_satisfy_the_key_it_merely_contains(text, emitted):
    """The false negative the token rule exists to prevent.

    Un-backtick a real key and name it inside a backticked phrase instead. Under the
    spec's run-based token that is MISSING plus EXTRA -- fail closed. Under a
    whitespace-splitting tokenizer the phrase's words would cover the key, `missing` would
    be empty, and behavior 4's entire direction would go blind on exactly the drift a
    reflowed sentence produces.
    """
    key = sorted(emitted)[0]
    for word in ("the", "field"):
        assert word not in emitted, f"premise: {word!r} is not an emitted key"
    sentence = enumeration_sentence(text)
    assert "`" + key + "`" in sentence, f"premise: the scope backticks {key!r}"
    phrase = "the " + key + " field"
    unbackticked = sentence.replace("`" + key + "`", key)
    assert unbackticked != sentence, "premise: the un-backticking landed"
    mutated = _swap_sentence(text, unbackticked[:-1] + ", `" + phrase + "`.")
    missing, extra = _defects(mutated, emitted)
    assert missing == [key], (
        f"a backticked phrase that merely CONTAINS {key!r} must not satisfy it; got "
        f"missing={missing!r}")
    assert extra == [phrase], f"the phrase itself is the EXTRA; got extra={extra!r}"


def test_b4_a_key_whose_backticks_wrap_across_a_line_break_fails_CLOSED(text, emitted):
    """The token rule's other exclusion. A run holding a newline is not a token, so a
    reflow that breaks a line INSIDE a key's backticks reads as MISSING rather than
    silently counting as documented. The surviving backticks may re-pair with their
    neighbours, so the exact EXTRA is not fixed by the spec and is not asserted; what is
    asserted is that the key is reported and that agreement is impossible.
    """
    key = sorted(k for k in emitted if len(k) >= 4)[0]
    sentence = enumeration_sentence(text)
    wrapped = "`" + key[:2] + "\n" + key[2:] + "`"
    unwrapped_count = sentence.count("`" + key + "`")
    assert unwrapped_count == 1, f"premise: the scope backticks {key!r} exactly once"
    mutated = _swap_sentence(text, sentence.replace("`" + key + "`", wrapped))
    scope = enumeration_sentence(mutated)
    assert "\n\n" not in scope, (
        "premise: the wrap added no BLANK line, so behavior 1's scope still reads")
    missing, extra = _defects(mutated, emitted)
    assert key in missing, (
        f"a key whose backticks span a line break must read as MISSING; got "
        f"missing={missing!r}, extra={extra!r}")
    assert (missing, extra) != ([], []), "the wrap must never read as agreement"
    carries_newline = sorted(n for n in missing + extra if "\n" in n)
    assert carries_newline == [], (
        f"a run containing a newline is not a token, so no defect name may carry one; "
        f"got {carries_newline!r}")


def test_b2_the_space_holding_fixture_really_discriminates_the_token_rule(text, emitted):
    """Arming for the two rows above, asserted rather than argued.

    A mutation both readings answer identically tests nothing, so prove this fixture
    SEPARATES the spec's run-based token from the whitespace-splitting reading -- on the
    token set and on the reported defects alike. The weaker reading is built here from the
    spec's own words, not read out of the oracle.
    """
    phrase = "not a key"
    sentence = enumeration_sentence(text)
    scope = enumeration_sentence(_swap_sentence(text, sentence[:-1] + ", `" + phrase + "`."))
    spec_tokens = backticked_tokens(scope)
    split_on_space = {word for run in re.findall(r"`([^`\n]+)`", scope)
                      for word in run.split()}
    assert spec_tokens != split_on_space, (
        "premise: the fixture must tell the two readings apart, or the rows above pass "
        "under either one")
    assert key_set_defects(spec_tokens, emitted) != key_set_defects(split_on_space, emitted), (
        "premise: the two readings must report DIFFERENT defects on this fixture")
    assert key_set_defects(spec_tokens, emitted) == ([], [phrase]), (
        "the spec's reading reports the run whole")
