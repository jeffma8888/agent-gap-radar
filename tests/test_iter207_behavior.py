"""Iteration 207 behaviors: `checks.required_literal_sets`, a per-alternative literal
CONJUNCTION (a DNF) for the content prefilter, so a pattern with two mandatory runs can
skip a file on EITHER one missing.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
as logic, nor the engineer's or the reviewer's notes, nor `IMPLEMENTATION.patch`, nor any
diff. Every expectation comes from `pm.md`'s Expected Behaviors; every shape claim was
measured by CALLING the published function, by running the CLI verbs through `main`, by
running `tools/scan_cost.py`, or by reading `tests/` and `gaps/` as data.

TWO DISCLOSURES, both also carried in the tester report:

* Behavior 2's soundness probe reads the files under `src/agent_gap_radar/` as a TEXT
  HAYSTACK (via iteration 93's committed helper), because a guarantee quantified over
  "every text `t`" needs real texts. No assertion encodes anything about HOW the
  extractor works; the corpus is a haystack.
* Behavior 8's call-site census parses `src/agent_gap_radar/*.py` with `ast` and counts
  CALL NODES BY NAME, because the spec's acceptance criterion is literally "`evaluate`'s
  content branch is the only caller of the new accessor" -- a statement about names, not
  about logic. Iteration 93's module made the same disclosure for the same reason.

Structural notes, so this file cannot lie later:

* **Every set-equality assertion is one of `pm.md`'s OWN examples.** Cases invented
  beyond that assert the PUBLISHED GUARANTEE (non-empty tuple, non-empty lowercase sets,
  and every match covered) or SOUNDNESS BY ENUMERATION -- never an invented set, because
  the contract explicitly permits `None`, and pinning an invented set would pin an
  implementation quirk the isolation contract forbids.
* **Soundness is proven TWO-SIDED, by MUTATING the accessor, not by hoping.** One probe
  is applied three times: to the real accessor (must report ZERO violations), to a mutant
  that adds an impossible literal to every set (must report at least one), and to a mutant
  that answers a non-`None` set where the real one answered `None` (must also report at
  least one). Without the mutants, a probe that only ever sees a sound extractor is
  indistinguishable from a probe incapable of seeing unsoundness.
* **Behavior 6's byte comparison is proven SENSITIVE the same way**: the same fixture
  scanned through an UNSOUND accessor must produce DIFFERENT bytes, or "identical bytes"
  is a green that means nothing.
* **No COUNT over the live register is asserted anywhere.** The register grows by an
  outside research pass, so a keyed or counted expectation over it would red this file on
  a correct register (the iteration-09 landmine). What IS asserted over the register is
  NON-VACUITY as a strict lower bound.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every register and target a verb runs over is built under
  pytest's `tmp_path`.
* **Nothing under `gaps/` is edited to make an assertion true**, and no record id from
  the live register is named.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import json
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main
from test_iter02_behavior import MARKER, _record, _target, _write_register
from test_iter93_behavior import (ADVERSARIAL, PRE_EXISTING_PUBLIC_CHECKS_FUNCTIONS,
                                 PUBLIC_CHECKS_FUNCTIONS, _distinct_content_patterns,
                                 _tracked_src_texts)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"
TESTS_DIR = REPO_ROOT / "tests"
TOOL = REPO_ROOT / "tools" / "scan_cost.py"

#: A literal no file and no enumerated text can contain, used to mutate the probes.
IMPOSSIBLE_LITERAL = "gapradar-iter207-literal-that-cannot-occur"

#: Behavior 2's guarantee, as `pm.md` words it. The shipped docstring must state it, so
#: these fragments are spelled once here and asserted against `__doc__` with whitespace
#: collapsed. They are the SPEC's words, not the implementation's.
GUARANTEE_FRAGMENTS = (
    "non-empty",
    "for every text `t`",
    "`re.compile(pattern, re.MULTILINE).search(t)` is not `None`",
    "some set",
    "EVERY member",
    "a substring of `t.lower()`",
)

#: The skip rule the caller uses, also required to be published (behavior 2).
SKIP_RULE_FRAGMENTS = ("skipped iff", "EVERY set", "at least one of its literals")

#: Behavior 3's two examples, verbatim from `pm.md`.
GIT_PUSH = r"\s+git\s+push\b"
TWO_ALTERNATIVES = "(foo)|(bar)"

#: Behavior 5's seven optional-literal shapes, verbatim from `pm.md`, each with the
#: enumerated texts it is checked against. `texts` mixes matches and non-matches; the
#: probe uses only the ones the COMPILED pattern matches. `satisfiable=False` marks a
#: shape no text can match, where the soundness quantifier is vacuous by construction.
ENUMERATED_SHAPES = (
    ("(ab)?c", "abc", 4, (), True),
    ("a(b|c)d", "abcd", 4, (), True),
    ("abc*d", "abcd", 4, (), True),
    ("a[bc]d", "abcd", 4, (), True),
    ("a{2,3}b", "ab", 4, ("a" * 5 + "b",), True),
    (r"[^.\n]{0,70}rollback", ".\n", 3,
     ("rollback", "xrollback", ".rollback", "x" * 70 + "rollback", "rollbac",
      "roll\nback", "x" * 71 + "rollback"), True),
    ("(?=ab)c", "abc", 4, (), False),
)

#: Behavior 5's two named negative pins, verbatim from `pm.md`.
FORBIDDEN_CLAIMS = (("(ab)?c", "ab"), (r"[^.\n]{0,70}rollback", "0,70"))

#: Behavior 8. The census labels the committed instruments publish. Spelled here and
#: cross-checked against iterations 123 and 202's own constants, so this file and those
#: two can never disagree about what the published key set is.
EXPECTED_DOMAIN_LABELS = frozenset({
    "gap records", "content evaluations", "files in content domains", "decode calls",
    "distinct decoded paths", "literal-set proofs", "proofs that proved a set",
    "proofs that proved nothing",
})
EXPECTED_JSON_KEYS = frozenset(EXPECTED_DOMAIN_LABELS | {"keyings", "schema"})

#: Behavior 9's verbs, named by the spec as keeping their exact output bytes.
UNCHANGED_VERBS = ("report", "list", "show", "prd", "validate", "diff", "taxonomy")


# ---------------------------------------------------------------------------
# Corpora. `gaps/` is read ONLY as a haystack of pattern strings; `src/` ONLY as a
# haystack of texts. No record id, count or keyed value is asserted anywhere.
# ---------------------------------------------------------------------------

def _live_patterns():
    return _distinct_content_patterns()


def _corpus():
    """Every pattern behaviors 1, 4 and 7 quantify over: the committed adversarial
    corpus plus the LIVE register's content patterns plus this iteration's examples."""
    return list(ADVERSARIAL) + [GIT_PUSH, TWO_ALTERNATIVES] + [
        shape for shape, _a, _n, _t, _s in ENUMERATED_SHAPES] + _live_patterns()


def _texts():
    return [text for _rel, text in _tracked_src_texts()]


def _compiled(pattern):
    """The compiled form the guarantee is stated against, or None if it will not compile.

    A malformed pattern has no matches to be unsound about, so the probe skips it.
    """
    try:
        return re.compile(pattern, re.MULTILINE)
    except re.error:
        return None


def _shape_is_legal(answer):
    """Behavior 1's shape rule, applied to one answer."""
    if answer is None:
        return True
    if not isinstance(answer, tuple) or not answer:
        return False
    for member in answer:
        if not isinstance(member, frozenset) or not member:
            return False
        for literal in member:
            if not isinstance(literal, str) or not literal:
                return False
    return True


def _violations(accessor, patterns, texts, stop_after=None):
    """Every (pattern, text) pair where `accessor` breaks behavior 2's guarantee.

    Also returns how many pairs reached the "the regex matched" branch, which is the
    non-vacuity lower bound: zero matches makes "zero violations" meaningless.
    """
    found, matched = [], 0
    for pattern in patterns:
        rx = _compiled(pattern)
        if rx is None:
            continue
        answer = accessor(pattern)
        for text in texts:
            if rx.search(text) is None:
                continue
            matched += 1
            if answer is None:
                continue
            folded = text.lower()
            if not any(all(lit in folded for lit in group) for group in answer):
                found.append((pattern, answer))
                if stop_after is not None and len(found) >= stop_after:
                    return found, matched
    return found, matched


def _mutant_extra_literal(pattern):
    """Every proved set gains a literal that cannot occur -- so no set can be satisfied."""
    answer = checks.required_literal_sets(pattern)
    if answer is None:
        return None
    return tuple(frozenset(group | {IMPOSSIBLE_LITERAL}) for group in answer)


def _mutant_claims_where_real_declines(pattern):
    """`None` (honestly unprovable) is replaced by a claim -- the other side of the spec."""
    answer = checks.required_literal_sets(pattern)
    if answer is None:
        return (frozenset({IMPOSSIBLE_LITERAL}),)
    return answer


def _enumerated_texts(alphabet, max_len, extra):
    out = [""]
    for size in range(1, max_len + 1):
        out.extend("".join(combo) for combo in itertools.product(alphabet, repeat=size))
    out.extend(extra)
    return out


# ---------------------------------------------------------------------------
# Behavior 1 -- the accessor is published, its shape is legal, and it is TOTAL.
# ---------------------------------------------------------------------------

def test_b1_the_accessor_is_published_on_checks_with_one_pattern_parameter():
    assert callable(checks.required_literal_sets)
    params = list(inspect.signature(checks.required_literal_sets).parameters)
    assert params == ["pattern"], params


def test_b1_the_public_surface_of_checks_gained_exactly_this_one_name():
    """The census is append-only, so one assert proves both halves."""
    public = sorted(name for name, obj in vars(checks).items()
                    if not name.startswith("_") and inspect.isfunction(obj)
                    and obj.__module__ == checks.__name__)
    assert public == PUBLIC_CHECKS_FUNCTIONS
    added = set(PUBLIC_CHECKS_FUNCTIONS) - set(PRE_EXISTING_PUBLIC_CHECKS_FUNCTIONS)
    assert added == {"required_literals", "required_literal_sets"}, added


@pytest.mark.parametrize("pattern", _corpus())
def test_b1_every_answer_is_none_or_a_nonempty_tuple_of_nonempty_frozensets(pattern):
    answer = checks.required_literal_sets(pattern)
    assert _shape_is_legal(answer), f"{pattern!r} -> {answer!r}"


@pytest.mark.parametrize("pattern", ADVERSARIAL)
def test_b1_the_accessor_is_total_over_the_committed_adversarial_corpus(pattern):
    checks.required_literal_sets(pattern)  # must simply not raise


def test_b1_the_adversarial_corpus_still_carries_its_stress_shapes():
    """Totality is only interesting if the corpus still holds the hard inputs."""
    assert any(len(pattern) == 4000 for pattern in ADVERSARIAL)
    assert any(pattern.count("|") >= 500 for pattern in ADVERSARIAL)
    assert any(pattern.count("(") >= 200 for pattern in ADVERSARIAL)


def test_b1_every_proved_literal_is_lowercase():
    for pattern in _corpus():
        answer = checks.required_literal_sets(pattern)
        if answer is None:
            continue
        for group in answer:
            for literal in group:
                assert literal == literal.lower(), (pattern, literal)


# ---------------------------------------------------------------------------
# Behavior 2 -- the published guarantee is STATED, and it is TRUE of the answers.
# ---------------------------------------------------------------------------

def test_b2_the_docstring_states_the_guarantee_the_spec_requires():
    doc = " ".join((checks.required_literal_sets.__doc__ or "").split())
    for fragment in GUARANTEE_FRAGMENTS:
        assert fragment in doc, f"missing guarantee fragment {fragment!r}"


def test_b2_the_docstring_states_the_skip_rule_a_caller_uses():
    doc = " ".join((checks.required_literal_sets.__doc__ or "").split())
    for fragment in SKIP_RULE_FRAGMENTS:
        assert fragment in doc, f"missing skip-rule fragment {fragment!r}"


def test_b2_the_guarantee_holds_over_the_live_register_against_real_texts():
    found, matched = _violations(checks.required_literal_sets, _corpus(), _texts())
    assert found == [], f"{len(found)} unsound answer(s), first: {found[:1]}"
    assert matched > 0, "the probe never reached a matching text; zero violations is vacuous"


def test_b2_the_probe_catches_a_set_that_gained_an_impossible_literal():
    found, matched = _violations(_mutant_extra_literal, _corpus(), _texts(), stop_after=1)
    assert matched > 0
    assert found, "the probe cannot see an unsatisfiable set; it proves nothing"


def test_b2_the_probe_catches_a_claim_where_the_real_accessor_declines():
    found, matched = _violations(
        _mutant_claims_where_real_declines, _corpus(), _texts(), stop_after=1)
    assert matched > 0
    assert found, "the probe cannot see a claim invented for an unprovable pattern"


# ---------------------------------------------------------------------------
# Behavior 3 -- both mandatory runs of one alternative are proved.
# ---------------------------------------------------------------------------

def test_b3_both_mandatory_runs_of_one_alternative_are_proved():
    answer = checks.required_literal_sets(GIT_PUSH)
    assert answer is not None
    assert len(answer) == 1, answer
    assert {"git", "push"} <= answer[0], answer[0]


def test_b3_one_set_per_alternative_in_source_order():
    assert checks.required_literal_sets(TWO_ALTERNATIVES) == (
        frozenset({"foo"}), frozenset({"bar"}))


def test_b3_the_dnf_is_strictly_stronger_than_the_old_answer_on_the_spec_example():
    """The whole point of the increment, stated as a comparison the spec implies."""
    old = checks.required_literals(GIT_PUSH)
    new = checks.required_literal_sets(GIT_PUSH)
    assert old is not None and new is not None
    assert len(new[0]) > len(old), (old, new)


# ---------------------------------------------------------------------------
# Behavior 4 -- MONOTONICITY against the shipped extractor, over the LIVE register.
#
# (b) is asserted in the two forms that are OBSERVABLE without knowing how the
# implementation splits alternatives: every returned set INTERSECTS the old answer (so
# the new skip rule skips every text the old one skipped), and every literal of the old
# answer appears SOMEWHERE in the DNF (so no proved literal was dropped). See the tester
# report for the alignment ambiguity this reading resolves.
# ---------------------------------------------------------------------------

def test_b4a_provability_is_never_lost():
    lost = [p for p in _corpus()
            if checks.required_literals(p) is not None
            and checks.required_literal_sets(p) is None]
    assert lost == [], f"provability lost for {lost[:3]}"


def test_b4b_every_returned_set_intersects_the_old_answer():
    weaker = []
    for pattern in _corpus():
        old = checks.required_literals(pattern)
        new = checks.required_literal_sets(pattern)
        if old is None or new is None:
            continue
        for group in new:
            if not (group & old):
                weaker.append((pattern, group, old))
    assert weaker == [], f"a set proves nothing the old filter proved: {weaker[:3]}"


def test_b4b_no_literal_the_old_extractor_proved_is_dropped():
    dropped = []
    for pattern in _corpus():
        old = checks.required_literals(pattern)
        new = checks.required_literal_sets(pattern)
        if old is None or new is None:
            continue
        union = frozenset().union(*new)
        if not old <= union:
            dropped.append((pattern, old - union))
    assert dropped == [], f"old literals absent from the DNF: {dropped[:3]}"


def test_b4b_the_monotonicity_checks_run_over_a_non_empty_live_register():
    """Behavior 4 is required to run over the LIVE register, not a fixture list."""
    live = _live_patterns()
    assert live, "no content patterns found under gaps/; behavior 4 would be vacuous"
    proved = [p for p in live if checks.required_literal_sets(p) is not None]
    assert proved, "no live pattern is provable; the monotonicity checks are vacuous"
    conjunctions = [p for p in live
                    if any(len(g) > 1 for g in (checks.required_literal_sets(p) or ()))]
    assert conjunctions, "no live pattern yields a CONJUNCTION; the increment is inert here"


def test_b4c_no_literal_escapes_the_audited_leading_run_primitive():
    """Every proved literal is a value the audited primitive returns for SOME suffix.

    The primitive carries this module family's Unicode and escape-whitelist refusals, so
    a literal that never comes out of it is a claim nothing audited stands behind. The
    corpus is bounded to patterns of at most 300 characters purely for cost -- the two
    stress shapes it excludes are the 4,000-character and 500-repeat inputs, whose
    totality behavior 1 already covers.

    RANGE, not one call: the primitive's second parameter is a fold flag (read from
    `inspect.signature`, not from its body -- runtime introspection, no source read), and
    a caller picks the flag from the pattern's own inline flags. "A value the primitive
    returns for SOME suffix" therefore means its range over BOTH flag values, so the
    reachable set is built from both. Pinning one value would assert a call convention
    this test cannot observe, which is an implementation quirk, not the spec.
    """
    primitive = getattr(checks, "_leading_literal_run", None)
    if primitive is None:
        pytest.skip("the audited primitive `_leading_literal_run` is not exposed")
    escaped = []
    for pattern in _corpus():
        if len(pattern) > 300:
            continue
        answer = checks.required_literal_sets(pattern)
        if answer is None:
            continue
        reachable = set()
        for start in range(len(pattern)):
            for fold in (False, True):
                try:
                    run = primitive(pattern[start:], fold)
                except Exception:  # noqa: BLE001 - a refusal is not a reachable value
                    continue
                if run:
                    reachable.add(run)
        for group in answer:
            for literal in group:
                if literal not in reachable:
                    escaped.append((pattern, literal))
    assert escaped == [], f"literals no audited run produced: {escaped[:3]}"


# ---------------------------------------------------------------------------
# Behavior 5 -- SOUNDNESS BY ENUMERATION for the optional-literal shapes.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("shape", "alphabet", "max_len", "extra", "satisfiable"),
                         ENUMERATED_SHAPES)
def test_b5_no_returned_literal_is_absent_from_a_text_the_pattern_matches(
        shape, alphabet, max_len, extra, satisfiable):
    rx = re.compile(shape, re.MULTILINE)
    answer = checks.required_literal_sets(shape)
    texts = _enumerated_texts(alphabet, max_len, extra)
    matches = [t for t in texts if rx.search(t) is not None]
    assert bool(matches) == satisfiable, f"{shape!r}: matches={matches[:3]}"
    if answer is None:
        return
    for group in answer:
        for literal in group:
            missing = [t for t in matches if literal not in t.lower()]
            assert missing == [], f"{shape!r} claims {literal!r}, absent from {missing[:3]}"


@pytest.mark.parametrize(("shape", "forbidden"), FORBIDDEN_CLAIMS)
def test_b5_the_optional_or_count_body_is_never_claimed(shape, forbidden):
    answer = checks.required_literal_sets(shape)
    assert answer is not None, shape
    for group in answer:
        assert forbidden not in group, f"{shape!r} claims {forbidden!r}"


def test_b5_the_enumerated_shapes_are_the_seven_the_spec_names():
    assert len(ENUMERATED_SHAPES) == 7
    assert {shape for shape, *_rest in ENUMERATED_SHAPES} == {
        "(ab)?c", "a(b|c)d", "abc*d", "a[bc]d", "a{2,3}b",
        r"[^.\n]{0,70}rollback", "(?=ab)c"}


# ---------------------------------------------------------------------------
# Behavior 6 -- VERDICT INVARIANCE. The prefilter is an optimisation, never a verdict.
# ---------------------------------------------------------------------------

@pytest.fixture()
def scan_fixture(tmp_path):
    reg = _write_register(
        tmp_path, [_record("GAP-700", 5, 5, 5, ("first-party-field",), "CHK-700")])
    return _target(tmp_path), reg


def _scan_bytes(target, reg, capsys):
    code = main(["scan", str(target), "--gaps", str(reg)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_b6_the_fixture_target_produces_at_least_one_present_verdict(scan_fixture, capsys):
    target, reg = scan_fixture
    code, out, err = _scan_bytes(target, reg, capsys)
    assert code == 0, err
    assert "| PRESENT | 1 |" in out, out
    assert MARKER.lower() != "", "the fixture marker must be a real content literal"


def test_b6_a_prefilter_that_skips_nothing_produces_byte_identical_stdout(
        scan_fixture, capsys, monkeypatch):
    target, reg = scan_fixture
    baseline_code, baseline_out, _err = _scan_bytes(target, reg, capsys)
    monkeypatch.setattr(checks, "required_literal_sets", lambda pattern: None)
    forced_code, forced_out, forced_err = _scan_bytes(target, reg, capsys)
    assert forced_code == baseline_code
    assert forced_out == baseline_out, "the prefilter changed the document"
    assert forced_err == ""


def test_b6_the_substitution_bites_because_evaluate_reads_the_global_at_call_time(
        scan_fixture, capsys, monkeypatch):
    target, reg = scan_fixture
    real = checks.required_literal_sets
    calls = []

    def counting(pattern):
        calls.append(pattern)
        return real(pattern)

    monkeypatch.setattr(checks, "required_literal_sets", counting)
    code, _out, err = _scan_bytes(target, reg, capsys)
    assert code == 0, err
    assert calls, "a scan never consulted the accessor; behavior 6 would be vacuous"


def test_b6_the_byte_comparison_can_see_a_difference(scan_fixture, capsys, monkeypatch):
    """An UNSOUND accessor makes the prefilter skip everything, so the verdict moves.

    Without this control, "identical bytes" would also be the answer if the prefilter
    were never consulted at all.
    """
    target, reg = scan_fixture
    _code, baseline_out, _err = _scan_bytes(target, reg, capsys)
    monkeypatch.setattr(checks, "required_literal_sets",
                        lambda pattern: (frozenset({IMPOSSIBLE_LITERAL}),))
    _code2, unsound_out, _err2 = _scan_bytes(target, reg, capsys)
    assert unsound_out != baseline_out, "the comparison cannot detect a moved verdict"
    assert "| PRESENT | 0 |" in unsound_out, unsound_out


# ---------------------------------------------------------------------------
# Behavior 7 -- `required_literals` is UNCHANGED, and only the registration edits
# touched the old test modules.
# ---------------------------------------------------------------------------

def test_b7_the_old_extractor_keeps_its_signature_and_return_contract():
    params = list(inspect.signature(checks.required_literals).parameters)
    assert params == ["pattern"], params
    for pattern in _corpus():
        answer = checks.required_literals(pattern)
        assert answer is None or (isinstance(answer, frozenset) and answer), (
            f"{pattern!r} -> {answer!r}")
        if answer is not None:
            for literal in answer:
                assert isinstance(literal, str) and literal == literal.lower()


@pytest.mark.parametrize(("pattern", "expected"), [
    ("(?i)(budget|allowance|quota)", frozenset({"budget", "allowance", "quota"})),
    ("(foo)|(bar)", frozenset({"foo", "bar"})),
    ("", None),
    ("(", None),
])
def test_b7_the_old_extractor_still_answers_its_published_examples(pattern, expected):
    assert checks.required_literals(pattern) == expected


def test_b7_the_two_accessors_are_distinct_objects_with_distinct_return_shapes():
    assert checks.required_literals is not checks.required_literal_sets
    assert isinstance(checks.required_literals(TWO_ALTERNATIVES), frozenset)
    assert isinstance(checks.required_literal_sets(TWO_ALTERNATIVES), tuple)


def test_b7_every_committed_seam_tuple_names_the_accessor_the_scan_calls():
    """The registration edit, read out of `tests/` as data.

    A seam tuple is a registry of module globals a tool rebinds; a renamed seam breaks
    once per copy. Every copy must name the NEW accessor and none may still name the old
    one, or `tools/scan_cost.py` would price a function the scan no longer calls.
    """
    seam_lines = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if re.match(r"^(SEAMS|seams|REQUIRED_LITERALS_SEAM)\s*=\s*\(", stripped):
                seam_lines.append((path.name, stripped))
    assert seam_lines, "no seam tuple found in tests/; this pin would be vacuous"
    for name, line in seam_lines:
        assert '"required_literal_sets"' in line, f"{name}: {line}"
        assert '"required_literals"' not in line, f"{name} still names the old seam: {line}"


# ---------------------------------------------------------------------------
# Behavior 8 -- `tools/scan_cost.py` prices the accessor `evaluate` actually calls.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cost_tool():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    import scan_cost  # noqa: PLC0415

    return scan_cost


@pytest.fixture()
def cost_fixture(tmp_path):
    reg = _write_register(
        tmp_path, [_record("GAP-701", 4, 4, 4, ("first-party-field",), "CHK-701")])
    return _target(tmp_path), reg


def test_b8_the_census_wraps_the_new_accessor_and_restores_it_in_a_finally(
        cost_tool, cost_fixture, monkeypatch):
    """A delegate installed FIRST proves both halves at once.

    If the census wraps the CURRENT global, the delegate is called; if it restores in a
    `finally`, the delegate is still installed afterwards.
    """
    target, reg = cost_fixture
    real = checks.required_literal_sets
    calls = []

    def delegate(pattern):
        calls.append(pattern)
        return real(pattern)

    monkeypatch.setattr(checks, "required_literal_sets", delegate)
    cost_tool.census(target, reg)
    assert calls, "the census did not consult the accessor the scan calls"
    assert checks.required_literal_sets is delegate, "a seam survived the census"


def test_b8_the_census_does_not_leave_the_old_accessor_wrapped(cost_tool, cost_fixture):
    target, reg = cost_fixture
    before = checks.required_literals
    cost_tool.census(target, reg)
    assert checks.required_literals is before


def test_b8_the_published_key_set_is_unchanged(cost_tool, cost_fixture):
    target, reg = cost_fixture
    census = cost_tool.census(target, reg)
    payload = json.loads(cost_tool.render_json(census))
    assert frozenset(payload) == EXPECTED_JSON_KEYS, sorted(payload)
    assert frozenset(census.domain) == EXPECTED_DOMAIN_LABELS, sorted(census.domain)


def test_b8_the_key_set_this_file_pins_is_the_one_the_older_modules_pin():
    """Spelled once, cross-checked -- iterations 123 and 202 must agree with this file."""
    from test_iter123_behavior import DOMAIN_LABELS  # noqa: PLC0415
    from test_iter202_behavior import DOMAIN_FILES  # noqa: PLC0415

    assert frozenset(DOMAIN_LABELS) | {DOMAIN_FILES} == EXPECTED_DOMAIN_LABELS


def test_b8_the_proof_counts_keep_their_published_meanings(cost_tool, cost_fixture):
    """calls made == calls that proved a set + calls that proved nothing, all non-zero."""
    target, reg = cost_fixture
    domain = cost_tool.census(target, reg).domain
    made = int(domain["literal-set proofs"])
    proved = int(domain["proofs that proved a set"])
    nothing = int(domain["proofs that proved nothing"])
    assert made > 0, domain
    assert proved > 0, domain
    assert proved + nothing == made, domain


def test_b8_the_tool_exits_zero_over_a_fixture_target_with_a_non_zero_proof_count(
        cost_fixture):
    target, reg = cost_fixture
    run = subprocess.run(
        [sys.executable, str(TOOL), "--target", str(target), "--gaps", str(reg)],
        capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    assert run.returncode == 0, run.stderr
    assert run.stderr == ""
    assert run.stdout.endswith("\n") and not run.stdout.endswith("\n\n")
    row = re.search(r"^\| literal-set proofs \| ([0-9]+) \|$", run.stdout, re.MULTILINE)
    assert row is not None, run.stdout
    assert int(row.group(1)) > 0, run.stdout


def test_b8_a_positional_target_is_still_refused_in_the_published_vocabulary():
    """`scan_cost.py .` is NOT a valid invocation -- it never was.

    The tool takes `--target`; iteration 206 made every `tools/` script refuse an
    unknown argument in this repo's `Error: ` vocabulary. This iteration's acceptance
    criterion spells the command with a positional `.`, so the honest pin is the refusal
    the tool actually publishes. See the tester report.
    """
    run = subprocess.run([sys.executable, str(TOOL), "."],
                         capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    assert run.returncode == 2
    assert run.stdout == ""
    assert any(line.startswith("Error: ") for line in run.stderr.splitlines())


def test_b8_evaluates_content_branch_is_the_only_caller_of_the_new_accessor():
    """A CALL-NODE census by NAME. See the module docstring's second disclosure."""
    callers = []
    for path in sorted(SRC_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        stack: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node):  # noqa: N802
                stack.append(node.name)
                self.generic_visit(node)
                stack.pop()

            def visit_Call(self, node):  # noqa: N802
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name == "required_literal_sets":
                    callers.append((path.name, tuple(stack)))
                self.generic_visit(node)

        Visitor().visit(tree)
    assert callers, "nothing in src/ calls the new accessor; the increment is dead code"
    assert {stack[-1] for _name, stack in callers if stack} == {"evaluate"}, callers


# ---------------------------------------------------------------------------
# Behavior 9 -- unchanged surfaces.
# ---------------------------------------------------------------------------

@pytest.fixture()
def register(tmp_path):
    return _write_register(
        tmp_path, [_record("GAP-800", 5, 4, 3, ("first-party-field",), None),
                   _record("GAP-801", 2, 2, 2, ("first-party-field",), None)])


def _argv(verb, register_dir):
    root = str(register_dir.parent)
    if verb == "show":
        return ["show", "GAP-800", root]
    if verb == "diff":
        return ["diff", root, root]
    if verb == "taxonomy":
        return ["taxonomy"]
    return [verb, root]


@pytest.mark.parametrize("verb", UNCHANGED_VERBS)
def test_b9_every_renderer_exits_zero_and_ends_in_exactly_one_newline(
        verb, register, capsys):
    code = main(_argv(verb, register))
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.err == ""
    assert captured.out, f"{verb} produced no document"
    assert captured.out.endswith("\n"), f"{verb} does not end in a newline"
    assert not captured.out.endswith("\n\n"), f"{verb} ends in more than one newline"


def test_b9_a_failure_still_speaks_the_error_vocabulary_on_stderr(register, capsys):
    code = main(["show", "GAP-404", str(register.parent)])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.startswith("Error: ")
    assert captured.err.endswith("\n") and not captured.err.endswith("\n\n")


def test_b9_no_new_dependency_and_no_network_capable_import_in_src():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    runtime = re.search(r"dependencies\s*=\s*\[(.*?)\]", pyproject, re.DOTALL)
    assert runtime is not None
    names = re.findall(r'"([A-Za-z0-9_.-]+)', runtime.group(1))
    assert [n.lower() for n in names] == ["pydantic"], names
    forbidden = ("socket", "urllib", "http.client", "requests", "httpx", "ftplib")
    offenders = []
    for path in sorted(SRC_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [(path.name, a.name) for a in node.names
                              if a.name.split(".")[0] in forbidden]
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".")[0] in forbidden:
                    offenders.append((path.name, node.module))
    assert offenders == [], offenders
