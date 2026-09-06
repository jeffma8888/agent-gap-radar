"""Iteration 117 behaviors: the required-literal prefilter proves a literal when an
alternative's LEADING run is empty.

Iterations 93/99 shipped `checks.required_literals` and its one call site. Its run
policy read only the literal run at the START of each alternative, so ONE leading
metacharacter made a whole pattern unprovable while a mandatory literal sat in plain
sight. This iteration widens the policy: when the leading run proves nothing, the
LONGEST unquantified depth-0 run ANYWHERE in the alternative is proved instead, an
offset inside a `{m,n}` count body is refused, and an alternative that already proves a
leading run keeps its exact answer.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
as logic, nor `engineer.md`, nor `reviewer.md`, nor `fix_review.md`, nor
`IMPLEMENTATION.patch`, nor any diff. Every expectation comes from `pm.md`'s Expected
Behaviors and from the function's own PUBLISHED docstring
(`checks.required_literals.__doc__`), which is the contract a caller is told to rely on.
Every shape claim in this module was measured by CALLING the public functions
(`checks.required_literals`, `checks.evaluate`) and by reading `gaps/*.json` as data.

TWO DISCLOSURES, also carried in the tester report:

* **Behavior 2's register-scale clause is tested in its INTENT-PRESERVING form, because
  the literal reading is FALSE against a correct extractor.** `pm.md` behavior 2 asks
  that across all live content patterns "no returned literal is a substring of the
  digits-and-comma alphabet only". Measured: two live patterns legitimately prove the
  literal `429` (from `\b429\b` and from `429|RateLimitError|...`), which is digits-only
  and has nothing to do with a brace body -- so the clause as written would red a correct
  implementation. The hazard it exists to catch is a `{m,n}` COUNT body leaking into a
  literal, so the clause is tested SCOPED to that hazard, two ways: (a) verbatim, no
  returned literal anywhere contains a comma; (b) for every pattern that carries a
  `{m,n}` body, no returned member is a substring of that body, and no returned member is
  drawn from the digits-and-comma alphabet only. Both are asserted non-vacuous.
* **Behavior 5 reads this repo's own tracked source and docs as a CORPUS**, not as logic
  -- a soundness probe needs real text to search, and the text is a haystack. No
  implementation fact is asserted about any of it.

Structural notes, so this file cannot lie later:

* **The live-pattern census is IMPORTED from `tests/test_iter99_behavior.py`**, whose
  `_live_content_patterns` is iteration 99's committed definition of "live content
  pattern". `pm.md` defines the term identically, and a second private copy of the walker
  could silently drift from the net that guards the whole register. The repo has the
  precedent committed: `tests/test_iter93_behavior.py` imports helpers from
  `tests/test_iter02_behavior.py`.
* **No new full-domain sweep is added.** Iteration 99's behavior-4 sweep stays the
  whole-register soundness net, untouched; behavior 5 here is a BOUNDED probe over 13
  files, and iteration 93's own differential probe is likewise untouched.
* **Every claim of soundness is proved TWO-SIDED.** Behavior 5 runs the same probe with
  the extractor substituted by one returning a literal that occurs in no file and
  requires it to report a violation -- without that, "zero violations" cannot be
  distinguished from a probe incapable of seeing unsoundness.
* **Every register count is a BOUND, never an equality.** The register is grown by an
  outside research pass. The one count `pm.md` states as an UPPER bound (at most 60
  unprovable patterns) is asserted with a message naming that fragility, because a
  research pass that adds unprovable patterns can red it without any code regressing.
* **No timing is asserted anywhere**, and no new live `radar scan` is run: `pm.md` forbids
  both, and the tester stage is the one with negative budget headroom.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every synthetic target is built under pytest's `tmp_path`.
* **Nothing under `gaps/` is edited to make an assertion true**, and no record id from the
  live register is named.
* **This module adds no autouse offline tripwire.** Nothing here opens a socket and no
  subprocess is spawned; `pm.md` records that consolidating the hand-copied tripwires
  needs a product decision about shared test helpers.
"""

from __future__ import annotations

import functools
import pathlib
import re

import pytest

from agent_gap_radar import checks
from test_iter99_behavior import _live_content_patterns

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Behavior 5's fixed domain, exactly as `pm.md` names it.
PROBE_SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"
PROBE_EXTRA_FILES = (REPO_ROOT / "README.md", REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md")

#: A literal that occurs in no file of the probe domain, so an extractor returning it
#: forces the skip branch on every pair. Spelled once.
IMPOSSIBLE_LITERAL = "qzx-absent-literal"

#: `pm.md` behavior 1: four shapes drawn from the live register's failure classes. Each
#: row is (pattern, expected member set, a string the pattern MATCHES). The sample is the
#: non-vacuity half: it proves the claimed literal really is implied by a match, so a
#: green set-equality cannot be a green over a literal the pattern does not require.
BEHAVIOR_1_CASES = [
    ('["\']--hard["\']', {"--hard"}, "reset: '--hard' set here"),
    (r"\s+git\s+push\b", {"push"}, "run git push now"),
    (r"(?:foo|bar)\s+rollback", {"rollback"}, "bar rollback now"),
    (
        r"(?i)(do not|do NOT)[^.\n]{0,70}rollback",
        {"rollback"},
        "do not ever rollback",
    ),
]

#: The fourth case above, the one carrying a `{m,n}` count body. Spelled once so
#: behaviors 1 and 2 can never disagree about which pattern they mean.
BRACE_PATTERN = BEHAVIOR_1_CASES[3][0]

#: `pm.md` behavior 4: answers the SHIPPED extractor already gave, quirks included.
BEHAVIOR_4_CASES = [
    (r"os\.walk\(", {"os.walk("}, "for root in os.walk(path)"),
    ("(?i)sk_live_", {"k_l"}, "token SK_LIVE_abc here"),
]

#: A `{m,n}` count body, for behavior 2's scoped clause.
_BRACE_BODY = re.compile(r"\{(\d+(?:,\d*)?)\}")

#: The digits-and-comma alphabet a count body is drawn from.
_COUNT_ALPHABET = frozenset("0123456789,")


# --- helpers ---------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _live_answers() -> tuple[tuple[str, frozenset[str] | None], ...]:
    """Every live content pattern paired with `required_literals`' answer for it.

    Cached: the census is pure and the extractor is consulted once per pattern per
    worker process, so the whole register costs one pass no matter how many tests read
    it. Returned as a tuple of pairs so a cached value cannot be mutated by a caller.
    """
    patterns = _live_content_patterns()
    assert len(patterns) >= 300, (
        f"non-vacuity: only {len(patterns)} live content pattern(s) found -- `pm.md` "
        "measured 361, so the census walker is rooted at the wrong node and every "
        "register-scale claim below would pass vacuously"
    )
    return tuple((pattern, checks.required_literals(pattern)) for pattern in patterns)


@functools.lru_cache(maxsize=1)
def _probe_domain() -> tuple[tuple[str, str, str], ...]:
    """`pm.md` behavior 5's domain as (name, text, folded), each read and lowered ONCE."""
    paths = sorted(PROBE_SRC_DIR.glob("*.py")) + list(PROBE_EXTRA_FILES)
    for path in PROBE_EXTRA_FILES:
        assert path.is_file(), f"behavior 5's domain is missing {path.name}"
    assert len(paths) >= 10, (
        f"non-vacuity: behavior 5's domain holds only {len(paths)} file(s)"
    )
    out = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        out.append((path.name, text, text.lower()))
    assert sum(len(text) for _, text, _ in out) >= 50_000, (
        "non-vacuity: behavior 5's domain is too small to be a haystack"
    )
    return tuple(out)


def _probe(extractor, *, stop_at_first: bool = False) -> dict[str, object]:
    """Apply the published one-directional guarantee over behavior 5's bounded domain.

    For every live content pattern whose answer is a set `L` and every file text `t`: if
    no member of `L` occurs in `t.lower()`, the regex must not match `t`. Returns the
    violations plus the two non-vacuity counters -- how many pairs the literal test
    REJECTED, and how many times the regex actually matched -- so a green result can be
    told apart from a probe that never reached either branch.
    """
    violations: list[tuple[str, str, list[str]]] = []
    skipped = 0
    matched = 0
    compile_failures: list[str] = []
    for pattern, _shipped in _live_answers():
        literals = extractor(pattern)
        if literals is None:
            continue
        try:
            compiled = re.compile(pattern, re.MULTILINE)
        except re.error:
            compile_failures.append(pattern)
            continue
        for name, text, folded in _probe_domain():
            if any(member in folded for member in literals):
                if compiled.search(text) is not None:
                    matched += 1
                continue
            skipped += 1
            if compiled.search(text) is not None:
                violations.append((pattern, name, sorted(literals)))
                if stop_at_first:
                    return {
                        "violations": violations,
                        "skipped": skipped,
                        "matched": matched,
                        "compile_failures": compile_failures,
                    }
    return {
        "violations": violations,
        "skipped": skipped,
        "matched": matched,
        "compile_failures": compile_failures,
    }


def _target(tmp_path: pathlib.Path, body: str, name: str = "a.txt") -> pathlib.Path:
    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    (target / name).write_text(body, encoding="utf-8")
    return target


# --- behavior 1: a leading metacharacter no longer defeats the proof -------


@pytest.mark.parametrize(
    "pattern,expected,sample",
    BEHAVIOR_1_CASES,
    ids=["class-leading", "escape-leading-longest-run", "group-leading", "brace-body"],
)
def test_b1_a_leading_metacharacter_no_longer_defeats_the_proof(
        pattern, expected, sample):
    """Behavior 1: each of `pm.md`'s four shapes proves exactly the stated member set."""
    answer = checks.required_literals(pattern)

    assert answer is not None, (
        "behavior 1: a pattern whose LEADING literal run is empty is still unprovable, "
        f"so the widened run policy is not in effect -- {pattern!r} returned None while "
        f"the mandatory literal {sorted(expected)} sits in plain sight"
    )
    assert answer == frozenset(expected), (
        f"behavior 1: {pattern!r} proved {sorted(answer)}, expected {sorted(expected)}"
    )

    # Non-vacuity 1: the answer is NOT the leading run, which is what the widening buys.
    assert all(not pattern.startswith(member) for member in answer), (
        f"non-vacuity: {pattern!r} leads with its own proved literal, so this row does "
        "not exercise the empty-leading-run branch at all"
    )
    # Non-vacuity 2: the claim is SOUND on a string the pattern really matches, so a
    # green set-equality cannot be green over a literal the pattern does not require.
    assert re.compile(pattern, re.MULTILINE).search(sample) is not None, (
        f"fixture error: the sample {sample!r} does not match {pattern!r}, so it cannot "
        "witness the proved literal"
    )
    assert any(member in sample.lower() for member in answer), (
        f"behavior 1: {pattern!r} matches {sample!r} yet no member of {sorted(answer)} "
        "occurs in its folded text -- the published guarantee is violated and this "
        "literal would skip a file the regex matches"
    )


def test_b1_the_longest_depth_zero_run_wins_not_the_first():
    r"""Behavior 1, second row, stated as its own property.

    `\s+git\s+push\b` has TWO mandatory runs, `git` and `push`. The spec requires the
    LONGEST, and a first-run rule would answer `{"git"}` -- sound, but a strictly weaker
    prefilter. Pinned separately because a set equality inside a parametrized row reads
    as an example, and this is the rule.
    """
    answer = checks.required_literals(r"\s+git\s+push\b")

    assert answer == frozenset({"push"}), (
        "behavior 1: the widened policy must prove the LONGEST depth-0 run, so "
        f"`\\s+git\\s+push\\b` proves {{'push'}}, not {sorted(answer or [])}"
    )


# --- behavior 2: a `{m,n}` quantifier body is never read as a literal ------


def test_b2_a_brace_count_body_is_never_read_as_a_literal():
    """Behavior 2, the spec's own case: none of `0,70`, `0`, `70`, `,` is proved."""
    answer = checks.required_literals(BRACE_PATTERN)

    assert answer == frozenset({"rollback"}), (
        f"behavior 2: {BRACE_PATTERN!r} proved {sorted(answer or [])}, expected "
        "{'rollback'}"
    )
    for member in answer:
        for forbidden in ("0,70", "0", "70", ","):
            assert forbidden not in member, (
                f"behavior 2: the proved literal {member!r} carries {forbidden!r} from "
                "the `{0,70}` REPEAT COUNT -- a count body is not a literal, and "
                "claiming it would skip every file that does not spell the count"
            )


def test_b2_no_live_pattern_ever_proves_a_comma():
    """Behavior 2 at register scale, the clause verbatim: no proved literal holds a comma.

    A comma is the shape a leaked `{m,n}` body has, so this is the register-wide form of
    the case above. Asserted non-vacuous: the register must actually carry brace-quantified
    patterns, and at least one of them must prove something.
    """
    answers = _live_answers()
    braced = [(pattern, answer) for pattern, answer in answers
              if _BRACE_BODY.search(pattern)]

    assert braced, (
        "non-vacuity: no live content pattern carries a `{m,n}` count body, so this "
        "clause cannot see a leaked count body"
    )
    assert any(answer for _pattern, answer in braced), (
        f"non-vacuity: none of the {len(braced)} brace-quantified live pattern(s) proves "
        "any literal, so the count-body refusal is never exercised over the register"
    )

    offenders = sorted(
        (pattern, member)
        for pattern, answer in answers
        if answer
        for member in answer
        if "," in member
    )
    assert offenders == [], (
        "behavior 2: proved literal(s) carry a comma, which is the signature of a "
        f"`{{m,n}}` count body read as text -- {offenders[:5]}"
    )


def test_b2_no_proved_literal_comes_out_of_its_own_patterns_count_body():
    """Behavior 2 at register scale, INTENT-PRESERVING form (see the module disclosure).

    The literal clause -- no proved literal is drawn from the digits-and-comma alphabet
    only -- is false against a correct extractor: two live patterns legitimately prove
    `429`. Scoped to the hazard it exists to catch, it holds: for a pattern carrying a
    count body, no proved member is a substring of that body, and no proved member is
    digits-and-commas only.
    """
    answers = _live_answers()
    checked = 0
    offenders: list[tuple[str, str, str]] = []
    for pattern, answer in answers:
        bodies = _BRACE_BODY.findall(pattern)
        if not bodies or not answer:
            continue
        checked += 1
        for member in answer:
            if frozenset(member) <= _COUNT_ALPHABET:
                offenders.append((pattern, member, "digits-and-commas only"))
            for body in bodies:
                if member in body:
                    offenders.append((pattern, member, body))

    assert checked >= 1, (
        "non-vacuity: no live pattern both carries a `{m,n}` body and proves a literal, "
        "so nothing was checked"
    )
    assert offenders == [], (
        "behavior 2: a proved literal was taken from its own pattern's repeat COUNT -- "
        f"{offenders[:5]}"
    )


# --- behavior 3: the fail-open default is preserved, not replaced ----------


@pytest.mark.parametrize("pattern", ["[ab](?:foo)?", "[ab](foo|bar)"])
def test_b3_an_alternative_with_no_depth_zero_literal_still_returns_none(pattern):
    """Behavior 3: a widening is not a licence to invent. No depth-0 literal, no claim.

    Both patterns hold literal TEXT (`foo`, `bar`), but only inside an optional atom or a
    nested alternation, so neither is mandatory. Claiming one would skip a file the regex
    matches -- the PRESENT-turned-ABSENT inversion.
    """
    assert checks.required_literals(pattern) is None, (
        f"behavior 3: {pattern!r} has no mandatory depth-0 literal run, yet the "
        f"extractor claimed {sorted(checks.required_literals(pattern) or [])} -- that "
        "claim skips files the regex matches"
    )


def test_b3_the_unprovable_branch_is_still_reachable_over_the_live_register():
    """Behavior 3: at least ONE live content pattern still returns `None`.

    Iteration 99's committed
    `test_b4_a_pattern_the_extractor_declines_is_never_treated_as_covered` needs the
    unprovable branch to be reachable over the live register, so a fallback that made
    every pattern provable would leave that net asserting nothing.
    """
    unprovable = [pattern for pattern, answer in _live_answers() if answer is None]

    assert unprovable, (
        "behavior 3: EVERY live content pattern is now provable, so the fail-open branch "
        "is unreachable over the register and iteration 99's decline-path net is vacuous"
    )


# --- behavior 4: an already-provable pattern's answer is unchanged ---------


@pytest.mark.parametrize("pattern,expected,sample", BEHAVIOR_4_CASES,
                         ids=["punct-escape-run", "ignorecase-fold"])
def test_b4_an_already_provable_patterns_answer_is_unchanged(pattern, expected, sample):
    """Behavior 4: the two answers `pm.md` pins from the SHIPPED extractor, quirks kept.

    `os\\.walk\\(` keeps its whitelisted trailing escape and `(?i)sk_live_` keeps the
    `i`/`s`-free fold. Both patterns prove a LEADING run, so the fallback must not be
    consulted for them at all, and each quirk is cross-checked for SOUNDNESS on a string
    the pattern really matches -- the fold quirk in particular is only sound because
    membership is tested against folded text.
    """
    answer = checks.required_literals(pattern)

    assert answer == frozenset(expected), (
        f"behavior 4: {pattern!r} already proved {sorted(expected)} before this "
        f"iteration and now proves {sorted(answer or [])} -- the fallback must be "
        "consulted ONLY when the leading run is empty, so no already-provable answer moves"
    )
    assert re.compile(pattern, re.MULTILINE).search(sample) is not None, (
        f"fixture error: the sample {sample!r} does not match {pattern!r}"
    )
    assert any(member in sample.lower() for member in answer), (
        f"behavior 4: {pattern!r} matches {sample!r} yet no member of {sorted(answer)} "
        "occurs in its folded text -- the preserved quirk is unsound"
    )


def test_b4_the_census_moved_at_least_fifty_patterns_out_of_unprovable():
    """Behavior 4's register-scale half.

    `pm.md` measured 116 of 361 live patterns unprovable BEFORE this iteration and
    requires the count to fall to at most 60 with no already-provable answer moving --
    equivalently at least 50 patterns move from `None` to a non-empty set, so the
    provable count is at least 245 + 50.
    """
    answers = _live_answers()
    total = len(answers)
    unprovable = [pattern for pattern, answer in answers if answer is None]
    provable = total - len(unprovable)

    assert len(unprovable) <= 60, (
        f"behavior 4: {len(unprovable)} of {total} live content pattern(s) are still "
        "unprovable, against `pm.md`'s bound of 60 (measured 45 in the PM stage, down "
        "from 116). FRAGILITY, if the code did not regress: this is an UPPER bound over "
        "a register an outside research pass grows, so a batch of newly added patterns "
        "with no depth-0 literal can red this without any code change -- check the "
        "PROVABLE floor below before blaming the extractor"
    )
    assert provable >= 295, (
        f"behavior 4: only {provable} of {total} live content pattern(s) prove a "
        "literal; 245 did before this iteration and at least 50 more must move out of "
        "None, so the floor is 295 -- an already-provable pattern's answer has been "
        "turned into None, which is the one regression the cut policy exists to prevent"
    )


def test_b4_every_answer_still_honours_the_published_return_contract():
    """Behavior 4's other half: the widening did not change the SHAPE of an answer.

    The docstring publishes `None` or a NON-EMPTY frozenset of lowercase literals. A
    fallback that returned `frozenset()` for a pattern it could not prove would read as
    "skip nothing" to one caller and "skip everything" to another.
    """
    offenders = []
    for pattern, answer in _live_answers():
        if answer is None:
            continue
        if not isinstance(answer, frozenset) or not answer:
            offenders.append((pattern, answer, "not a non-empty frozenset"))
            continue
        for member in answer:
            if member != member.lower():
                offenders.append((pattern, member, "not lowercase"))

    assert offenders == [], (
        f"behavior 4: the published return contract is broken -- {offenders[:5]}"
    )


# --- behavior 5: every claimed literal is sound over a bounded real domain --


def test_b5_every_claimed_literal_is_sound_over_the_bounded_domain():
    """Behavior 5, first half: no proved literal set rejects a file the regex matches."""
    result = _probe(checks.required_literals)

    assert result["compile_failures"] == [], (
        f"a live content pattern does not compile -- {result['compile_failures'][:3]}"
    )
    assert result["skipped"] >= 100, (
        f"non-vacuity: the literal test rejected only {result['skipped']} pair(s), so "
        "'zero violations' is a green over a probe that barely reached the skip branch"
    )
    assert result["matched"] >= 1, (
        "non-vacuity: the regex never matched ANY file in the domain, so the probe could "
        "not have seen an inverted verdict even if one existed"
    )
    assert result["violations"] == [], (
        "behavior 5: a proved literal set is absent from a file the pattern's regex "
        "MATCHES, so the prefilter would skip it and turn a PRESENT into an ABSENT -- "
        f"{result['violations'][:3]}"
    )


def test_b5_the_same_probe_reports_a_violation_for_an_unsound_extractor():
    """Behavior 5, second half: the probe can SEE unsoundness.

    Same probe, same domain, extractor substituted by one claiming a literal that occurs
    in no file. Every pair is then rejected, so any pattern the regex matches anywhere in
    the domain is a violation. Without this the green above is indistinguishable from a
    probe incapable of failing.
    """
    domain = _probe_domain()
    assert not any(IMPOSSIBLE_LITERAL in folded for _name, _text, folded in domain), (
        "fixture error: the impossible literal occurs in the probe domain"
    )

    result = _probe(lambda pattern: frozenset({IMPOSSIBLE_LITERAL}),
                    stop_at_first=True)

    assert result["violations"], (
        "behavior 5: an extractor claiming a literal that occurs in NO file of the "
        "domain produced zero violations, so the probe cannot see unsoundness and its "
        "green in the sibling test means nothing"
    )


# --- behavior 6: the real caller's verdict does not move -------------------

#: (widened pattern with an empty leading run, an equivalent pattern LEADING with the
#: proved literal, a body whose line 3 matches both, a body neither matches).
BEHAVIOR_6_CASES = [
    (
        r"\s+git\s+push",
        "push --force",
        "line one\nline two\nrun: git push --force\nline four\n",
        "line one\nline two\nnothing to see\nline four\n",
    ),
    (
        '["\']--hard["\']',
        "--hard",
        "line one\nline two\nreset: '--hard' set\nline four\n",
        "line one\nline two\nreset: soft set\nline four\n",
    ),
    (
        r"(?:foo|bar)\s+rollback",
        "rollback now",
        "line one\nline two\nbar rollback now\nline four\n",
        "line one\nline two\nbar commit now\nline four\n",
    ),
]


@pytest.mark.parametrize("kind", ["content_matches", "content_absent"])
@pytest.mark.parametrize("widened,leading,hit_body,miss_body", BEHAVIOR_6_CASES,
                         ids=["escape-leading", "class-leading", "group-leading"])
def test_b6_the_real_callers_verdict_does_not_move(
        tmp_path, kind, widened, leading, hit_body, miss_body):
    """Behavior 6: a file matching ONLY through a non-leading literal is still reported.

    The widened claim is exercised through the real caller, `checks.evaluate`. Its verdict
    and its locations must equal those of a pattern that LEADS with the same literal --
    the answer the shipped extractor could already prove -- so the widening can never turn
    a PRESENT into an ABSENT. Both rule kinds are driven: for `content_absent` the same
    inversion shows up as a false claim of mitigation.
    """
    proved = checks.required_literals(widened)
    assert proved, (
        f"precondition: {widened!r} proves nothing, so `evaluate` never reaches the "
        "prefilter's skip branch for it and this row is vacuous"
    )
    assert all(not widened.startswith(member) for member in proved), (
        f"precondition: {widened!r} leads with its proved literal, so this row does not "
        "test the widened branch"
    )
    assert checks.required_literals(leading), (
        f"precondition: the control pattern {leading!r} proves nothing"
    )

    hit_target = _target(tmp_path / "hit", hit_body)
    miss_target = _target(tmp_path / "miss", miss_body)

    widened_hit = checks.evaluate({"kind": kind, "pattern": widened,
                                   "globs": ["*.txt"]}, hit_target)
    leading_hit = checks.evaluate({"kind": kind, "pattern": leading,
                                   "globs": ["*.txt"]}, hit_target)

    assert leading_hit.matched is (kind == "content_matches"), (
        "fixture error: the control pattern's verdict on the hit body is not the one a "
        f"MATCHING body must produce for kind={kind}, so the differential below is "
        f"meaningless -- matched={leading_hit.matched}"
    )
    if kind == "content_matches":
        assert leading_hit.locations == ["a.txt:3"], (
            "fixture error: the control pattern does not match line 3 of the hit body, "
            f"so the location differential is meaningless -- {leading_hit.locations}"
        )
    assert widened_hit.matched is leading_hit.matched, (
        f"behavior 6: for kind={kind} the widened pattern {widened!r} reported "
        f"matched={widened_hit.matched} on a file the pattern MATCHES, while the "
        f"equivalent leading-literal pattern {leading!r} reported "
        f"{leading_hit.matched} -- the widened claim moved a real verdict"
    )
    assert widened_hit.locations == leading_hit.locations, (
        f"behavior 6: same verdict, different locations for kind={kind} -- "
        f"{widened_hit.locations} vs {leading_hit.locations}"
    )

    # The other direction: a body neither pattern matches must stay a genuine miss, and
    # it must be a miss because the REGEX does not match, not because a literal was
    # wrongly claimed.
    assert re.compile(widened, re.MULTILINE).search(miss_body) is None, (
        "fixture error: the miss body matches the widened pattern"
    )
    widened_miss = checks.evaluate({"kind": kind, "pattern": widened,
                                    "globs": ["*.txt"]}, miss_target)
    leading_miss = checks.evaluate({"kind": kind, "pattern": leading,
                                    "globs": ["*.txt"]}, miss_target)

    assert widened_miss.matched is leading_miss.matched, (
        f"behavior 6: the two patterns disagree about a genuine miss for kind={kind} -- "
        f"{widened_miss.matched} vs {leading_miss.matched}"
    )
    if kind == "content_matches":
        assert widened_miss.locations == leading_miss.locations == [], (
            "behavior 6: a non-matching body reported a location -- "
            f"{widened_miss.locations} vs {leading_miss.locations}"
        )
    else:
        # MEASURED, not assumed: a satisfied `content_absent` rule reports an evidence
        # line that NAMES the pattern it searched for, so the two strings differ by
        # construction and a raw cross-pattern equality here would be a fixture bug. The
        # invariant that survives is the COUNT and the shape.
        assert len(widened_miss.locations) == len(leading_miss.locations) == 1, (
            "behavior 6: a satisfied `content_absent` rule lost its evidence line -- "
            f"{widened_miss.locations} vs {leading_miss.locations}"
        )
        assert widened in widened_miss.locations[0], (
            "behavior 6: the `content_absent` evidence line does not name the pattern it "
            f"searched -- {widened_miss.locations[0]!r}"
        )


# --- acceptance criterion: the published docstring states the new rule -----


def test_ac_the_published_docstring_states_the_new_run_policy():
    """`pm.md` acceptance criterion: the docstring states the new rule AND keeps the old
    guarantee true. The docstring is the contract a caller is told to rely on, so a
    widened extractor whose published rule still says "leading run only" is a lie in the
    one place a caller reads.
    """
    doc = checks.required_literals.__doc__ or ""
    low = doc.lower()

    assert "longest" in low, (
        "acceptance criterion: the docstring does not state the new longest-run rule"
    )
    assert "depth-0" in low or "depth 0" in low, (
        "acceptance criterion: the docstring does not say the new run is read at depth 0"
    )
    assert "{m,n}" in doc, (
        "acceptance criterion: the docstring does not state the `{m,n}` count-body refusal"
    )
    assert "non-empty" in low and "t.lower()" in doc, (
        "acceptance criterion: the docstring's PUBLISHED one-directional guarantee (a "
        "non-empty set, membership tested against `t.lower()`) is no longer stated, so "
        "the widening rewrote the contract instead of extending it"
    )


# --- acceptance criterion: the fallback fires ONLY when the leading run is empty ---
#
# `pm.md` picks the CUT of scout B's candidate, and its stated reason is that the cut
# "consults the new fallback ONLY when the leading run is empty, so the 245 patterns that
# prove a literal today keep a byte-identical answer". Nothing above pins that, and the
# omission is load-bearing: every other assertion in this module, and every committed
# assertion iterations 93/99 left behind, is ALSO satisfied by the FULL policy (longest run
# everywhere, for every alternative). So the one property that distinguishes what the spec
# ordered from what the spec put OUT OF SCOPE has no test at all. These two cases are the
# converse of `test_b1_the_longest_depth_zero_run_wins_not_the_first`: there the leading run
# is empty and the LONGEST run must win; here the leading run is non-empty and it must win
# even though a strictly LONGER depth-0 run sits later in the same alternative.

# (pattern, expected answer, the strictly longer depth-0 run the FULL policy would prefer,
#  a string the pattern really matches)
CUT_POLICY_CASES = (
    (r"git\s+rollback", frozenset({"git"}), "rollback", "please git   rollback now"),
    (r"push\s+--force\s+origin\s+main", frozenset({"push"}), "--force",
     "push --force origin main"),
    (r"do\s+not[^.\n]{0,70}rollback", frozenset({"do"}), "rollback",
     "do not ever rollback the release"),
)


@pytest.mark.parametrize("pattern,expected,longer_later,sample", CUT_POLICY_CASES,
                         ids=[case[0] for case in CUT_POLICY_CASES])
def test_ac_the_fallback_is_consulted_only_when_the_leading_run_is_empty(
    pattern, expected, longer_later, sample
):
    r"""Acceptance criterion: an alternative that ALREADY proves a leading run keeps it.

    `pm.md` puts the full policy explicitly Out of Scope ("the longest run for an
    alternative that ALREADY proves a leading run ... re-baselines all 245 provable
    answers"). A shipped extractor that widened unconditionally would be a scope
    over-reach that no other assertion in this repo can see, because taking a LONGER
    mandatory run is still SOUND -- so no soundness probe, and no `None`-count census,
    can distinguish it. Only an exact answer on a pattern whose leading run is not the
    longest one can, and that is what these rows are.
    """
    answer = checks.required_literals(pattern)

    assert answer == expected, (
        f"acceptance criterion: {pattern!r} proves a LEADING literal run, so the fallback "
        f"must not be consulted at all and the answer must stay {sorted(expected)}; got "
        f"{sorted(answer) if answer is not None else None}. Answering "
        f"{{{longer_later!r}}} means the longest-run policy was applied "
        "UNCONDITIONALLY -- the full candidate `pm.md` deferred, which re-baselines every "
        "already-provable answer in the register"
    )

    # Non-vacuity 1: the row only exercises the forbidden branch if the leading run really
    # is non-empty, i.e. the pattern OPENS with the literal it proves.
    member = next(iter(answer))
    assert pattern.startswith(member), (
        f"non-vacuity: {pattern!r} does not open with its proved literal {member!r}, so "
        "this row does not test an alternative whose LEADING run is non-empty and cannot "
        "detect an unconditional widening"
    )

    # Non-vacuity 2: the deferred policy would genuinely answer differently here -- the
    # later run must be strictly LONGER, and must really be present in the pattern.
    assert longer_later in pattern, (
        f"non-vacuity: {longer_later!r} is not in {pattern!r}, so this row's control "
        "literal is fictional and the row proves nothing about the deferred policy"
    )
    assert len(longer_later) > max(len(m) for m in answer), (
        f"non-vacuity: {longer_later!r} is not strictly longer than the proved "
        f"{sorted(answer)}, so the two policies AGREE on {pattern!r} and this row cannot "
        "tell them apart"
    )

    # And the weaker answer is still SOUND: the published guarantee must hold on a string
    # the pattern really matches, or the cut bought scope safety at the cost of a wrong skip.
    assert re.compile(pattern, re.MULTILINE).search(sample) is not None, (
        f"fixture bug: {pattern!r} does not match {sample!r}, so the soundness half of "
        "this row is vacuous"
    )
    assert any(m in sample.lower() for m in answer), (
        f"{pattern!r} matches {sample!r} yet no member of {sorted(answer)} occurs in its "
        "folded text -- keeping the leading run must stay SOUND, not merely narrow"
    )


# (pattern, expected answer, sample matching ONLY the empty-leading-run alternative,
#  sample matching ONLY the already-provable alternative)
MIXED_ALTERNATION_CASES = (
    (r"\s+push|rollback", frozenset({"push", "rollback"}), " push", "rollback"),
    (r"os\.walk\(|\s+git\s+push", frozenset({"os.walk(", "push"}), "os.walk(path)",
     " git push"),
    (r"[ab]foo|bar", frozenset({"foo", "bar"}), "afoo", "bar"),
)


@pytest.mark.parametrize("pattern,expected,only_widened,only_leading",
                         MIXED_ALTERNATION_CASES,
                         ids=[case[0] for case in MIXED_ALTERNATION_CASES])
def test_b4_the_fallback_is_applied_per_alternative_not_per_pattern(
    pattern, expected, only_widened, only_leading
):
    r"""Behaviors 1 and 4 combined on the shape the spec's own rows never cover: a top-level
    alternation whose alternatives DISAGREE about whether their leading run is empty.

    Every behavior-1 row is a single depth-0 alternative, so all of them are answered by one
    decision. A mixed alternation needs two, and the prefilter is only sound if it proves a
    literal for EVERY alternative -- dropping one lets a file that matches only the dropped
    branch be skipped, which is exactly the false claim of safety `VISION.md` and the
    `checks.py` header exist to prevent. A per-PATTERN reading of the fallback ("the leading
    run of the pattern is non-empty, so do not widen") would return the already-provable
    alternative's literal alone, and it would be green against a corpus that never spells
    the other branch.
    """
    answer = checks.required_literals(pattern)

    assert answer == expected, (
        f"behaviors 1/4: {pattern!r} must prove one literal per alternative, "
        f"{sorted(expected)}; got {sorted(answer) if answer is not None else None}. A "
        "subset here is UNSOUND (a file matching the missing alternative is skipped); "
        "`None` means one empty leading run still defeated the whole pattern"
    )

    # The soundness that the union buys, one alternative at a time. Each sample matches the
    # pattern through exactly ONE branch, so a dropped literal shows up as a wrong skip.
    compiled = re.compile(pattern, re.MULTILINE)
    for sample, which in ((only_widened, "the widened (empty leading run) alternative"),
                          (only_leading, "the already-provable alternative")):
        assert compiled.search(sample) is not None, (
            f"fixture bug: {pattern!r} does not match {sample!r}, so the {which} is not "
            "actually exercised by this row"
        )
        assert any(m in sample.lower() for m in answer), (
            f"{pattern!r} matches {sample!r} via {which}, yet no member of "
            f"{sorted(answer)} occurs in its folded text -- the prefilter would skip a "
            "file the regex matches"
        )

    # Non-vacuity: the row is only a MIXED alternation if one branch needed the fallback.
    # The first alternative is the widened one by construction, so it must not open with a
    # literal, while the pattern as a whole must still prove something for it.
    first_alternative = pattern.split("|")[0]
    assert not any(first_alternative.startswith(m) for m in answer), (
        f"non-vacuity: the first alternative of {pattern!r} already opens with a proved "
        "literal, so no alternative in this row needed the fallback and the row does not "
        "test a MIXED alternation"
    )
