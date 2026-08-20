"""Iteration 27 behaviors: no register content pattern opens with a quantified wildcard.

Iteration 27's payload is register DATA: one nine-character class prefix is deleted from
GAP-014 / CHK-013's first `present_when` pattern, and a suite-level census makes the whole
class unmergeable. The claim under test has two halves, and they fail in opposite
directions, so both are asserted here:

* the SCAN gets cheap -- a leading `*`-quantified wildcard in front of an unanchored
  `search` buys nothing and backtracks, and this record declares `**/*.js` in its own globs,
  so one minified bundle in a consumer repo turns a scan into an apparent hang;
* the DECISION does not move -- the class contains no newline and the evaluator publishes
  only `path:line`, so the same hits must be reported on the same lines.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source (`src/`, `tools/`), the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`,
or any diff. Every expectation comes from `pm.md`'s Expected Behaviors; every value is
measured by CALLING the public `checks` interface or by loading the register through
`registry.load_all`. The register is never read by eye and no pattern from it is copied
into this file -- behaviors 2-4 navigate to "GAP-014's first `present_when` rule"
structurally, so this file cannot drift into asserting a pattern's text.

Structural notes, so this file cannot lie later:

* **The census's anti-vacuity is a DERIVED EQUALITY, not only a floor.** The number of
  patterns the walker collects is compared against a second, independent measurement of the
  same quantity -- the raw count of `"pattern":` keys in the register's bytes. A census that
  stopped recursing into `any_of` / `all_of` / `not` would still clear any floor once the
  register grows; it cannot clear the equality. The spec's literal floors (>= 49 patterns,
  >= 12 ids) are asserted too, and their failure message names the one way they can red on a
  correct suite: a record being legitimately deleted.
* **The walker is itself proved two-sided on a synthetic check**, because the live register
  may not currently exercise every combinator. Without that, a walker blind to `not` would
  pass every assertion here and let the next `not`-nested pattern in unseen.
* **The banned-shape regex is proved two-sided**, on planted bad samples it must catch and
  on legitimate patterns it must leave alone. A census whose matcher cannot fire reports a
  clean register it never examined -- the fail-open this product exists to refuse.
* **Every performance bound carries a two-sided control in the same test.** A pattern that
  can no longer match anything is arbitrarily fast, so behavior 4 also asserts that adding
  one candidate line to the very same file makes the very same rule match it.
* **No absolute machine path and no personal identifier appears here**; the register is
  found relative to `__file__` and every fixture lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib
import re
import time

import pytest

from agent_gap_radar.checks import Verdict, evaluate, run_check
from agent_gap_radar.registry import load_all

#: The register, found relative to this file so no absolute machine path is written down.
REPO_GAPS = pathlib.Path(__file__).resolve().parents[1] / "gaps"

#: Behavior 1's banned shape, quoted from `pm.md`: an optional leading inline-flag group,
#: then a character class / a shorthand class / `.`, quantified by `*` or `+`.
BANNED_OPENING = re.compile(r"^(?:\(\?[aiLmsux]+\))?(?:\[[^\]]+\]|\\[wWsSdD]|\.)[*+]")

#: The three check fields a rule can hang from, per the spec.
RULE_FIELDS = ("applies_when", "present_when", "mitigated_when")

#: Behavior 1's floors, as `pm.md` states them. Named so the report can cite them.
SPEC_MIN_PATTERNS = 49
SPEC_MIN_IDS = 12

#: Behavior 4: 40 lines of exactly this many characters, all drawn from `[\w/.-]`.
LONG_LINE_CHARS = 3200
LONG_LINE_COUNT = 40
#: The bound the spec names. Measured today through `evaluate`: ~23 ms, so ~87x margin.
LONG_LINE_BUDGET_SECONDS = 2.0


def _collect(check: dict) -> list[str]:
    """Every `pattern` string reachable from a check's three rule fields.

    Recurses into `any_of` / `all_of` (their `rules` list) and `not` (its `rule` object),
    which is the walk `pm.md` specifies. Proved two-sided by
    `test_the_pattern_walker_reaches_every_combinator`.
    """
    found: list[str] = []

    def walk(rule: object) -> None:
        if not isinstance(rule, dict):
            return
        pattern = rule.get("pattern")
        if isinstance(pattern, str):
            found.append(pattern)
        for sub in rule.get("rules") or ():
            walk(sub)
        walk(rule.get("rule"))

    for field in RULE_FIELDS:
        walk(check.get(field))
    return found


def _register_patterns(gaps_dir: pathlib.Path = REPO_GAPS) -> list[tuple[str, str]]:
    """`(record id, pattern)` for every content pattern in every record on disk.

    Takes a directory so the census can be proved two-sided against a MODIFIED COPY of
    the real register, rather than only against planted strings.
    """
    pairs: list[tuple[str, str]] = []
    for gap in load_all(gaps_dir):
        if gap.check is None:
            continue
        for pattern in _collect(gap.check.model_dump(exclude_none=True)):
            pairs.append((gap.id, pattern))
    return pairs


def _raw_pattern_key_count() -> int:
    """A SECOND, independent measurement of the same quantity, from the bytes.

    Deliberately not a JSON walk: this must not share code, or a bug in the walker
    would move both sides together and the equality would prove nothing.
    """
    return sum(p.read_text(encoding="utf-8").count('"pattern":')
               for p in sorted(REPO_GAPS.glob("*.json")))


def _gap(gap_id: str):
    for gap in load_all(REPO_GAPS):
        if gap.id == gap_id:
            return gap
    raise AssertionError(f"{gap_id} is not in the register")


def _first_present_rule(check: dict) -> dict:
    """The record's FIRST `present_when` rule, reached structurally.

    `present_when` may be a single rule or a combinator; either way the spec means the
    first leaf rule the register declares, so a change to the record's shape surfaces
    as a failure here rather than silently evaluating something else.
    """
    rule = check["present_when"]
    while rule.get("rules"):
        rule = rule["rules"][0]
    assert rule.get("kind") == "content_matches", rule.get("kind")
    return rule


def _materialise(root: pathlib.Path, tree: dict[str, str]) -> pathlib.Path:
    for rel, content in tree.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


# --- Behavior 1: the register-wide census ----------------------------------------------

def test_no_register_content_pattern_opens_with_a_quantified_wildcard():
    """Behavior 1. The census, plus its anti-vacuity in the same test."""
    pairs = _register_patterns()
    offenders = [(gid, pat) for gid, pat in pairs if BANNED_OPENING.match(pat)]
    assert not offenders, (
        "content pattern(s) open with a quantified wildcard, which an unanchored "
        f"search already covers and which backtracks superlinearly in line length: "
        f"{offenders}")

    # Anti-vacuity, half one: a derived equality against an independent measurement.
    raw = _raw_pattern_key_count()
    assert len(pairs) == raw, (
        f"the census walked {len(pairs)} patterns but the register's bytes declare {raw} "
        f'"pattern" keys -- the walk is missing a combinator branch, so patterns nested '
        f"in it are never censused")

    # Anti-vacuity, half two: the spec's literal floors.
    ids = {gid for gid, _ in pairs}
    assert len(pairs) >= SPEC_MIN_PATTERNS, (
        f"census collected {len(pairs)} patterns, below the spec floor of "
        f"{SPEC_MIN_PATTERNS}. If a record was deliberately REMOVED from the register, "
        f"lower this floor; the equality assertion above is the growth-proof half.")
    assert len(ids) >= SPEC_MIN_IDS, (
        f"census spans {len(ids)} record ids, below the spec floor of {SPEC_MIN_IDS}: "
        f"{sorted(ids)}")


def test_the_pattern_walker_reaches_every_combinator():
    """The census's own two-sided proof, independent of what the register happens to hold.

    A walker blind to one combinator passes every register assertion until the first
    record uses that combinator, and then admits the banned class silently.
    """
    check = {
        "id": "CHK-000",
        "applies_when": {"kind": "content_matches", "globs": ["*"], "pattern": "APPLIES"},
        "present_when": {"kind": "all_of", "rules": [
            {"kind": "content_matches", "globs": ["*"], "pattern": "TOP_LEVEL"},
            {"kind": "any_of", "rules": [
                {"kind": "content_matches", "globs": ["*"], "pattern": "NESTED_ANY"},
                {"kind": "not", "rule": {"kind": "content_matches", "globs": ["*"],
                                         "pattern": "UNDER_NOT"}},
            ]},
        ]},
        "mitigated_when": {"kind": "content_matches", "globs": ["*"],
                           "pattern": "MITIGATED"},
        # Must NOT be collected: the census is scoped to the three rule fields.
        "fixtures": {"bad": {"a.py": '"pattern": "NOT_A_RULE"\n'}, "good": {"a.py": "x\n"}},
    }
    assert sorted(_collect(check)) == [
        "APPLIES", "MITIGATED", "NESTED_ANY", "TOP_LEVEL", "UNDER_NOT",
    ], _collect(check)


@pytest.mark.parametrize("pattern", [
    r"[\w/.-]*(feature|flag)",          # the exact shape this iteration deletes
    r"(?i)[\w/.-]*(feature|flag)",      # ... with an inline-flag group in front
    r"(?is)[\w/.-]+x",                  # multiple inline flags, `+` quantifier
    r".*schema_version",
    r".+schema_version",
    r"\s*validate_features",
    r"\S+validate_features",
    r"\w*MAX_FEATURES",
    r"\d+rows",
    r"[a-z]+bounds_check",
])
def test_the_banned_shape_regex_fires_on_a_planted_offender(pattern):
    """A matcher that cannot fire reports a clean register it never examined."""
    assert BANNED_OPENING.match(pattern), pattern


@pytest.mark.parametrize("pattern", [
    r"^[\w/.-]*features\.json",   # ANCHORED: here the quantifier is load-bearing
    r"(?i)(feature|flag)",
    r"features[\w/.-]*\.json",    # a TRAILING class is the load-bearing copy; not banned
    r"while True",
    r"importlib\.reload",
    r"\.json",
    r"[\w]",                      # unquantified class
    r"json_schema",
])
def test_the_banned_shape_regex_leaves_legitimate_patterns_alone(pattern):
    """The other side. A census that flagged these would be unusable and get deleted."""
    assert not BANNED_OPENING.match(pattern), pattern


#: The nine characters this iteration deletes, per `pm.md`'s acceptance criteria. Used ONLY
#: to re-admit them into a throwaway COPY of the register, never into the repo.
RE_ADMITTED_PREFIX = r"[\w/.-]*"

#: A leading inline-flag group, which must stay in front of the re-admitted class or the
#: reconstructed pattern would not be a legal regex (flags must open the expression).
_LEADING_FLAGS = re.compile(r"^(?:\(\?[aiLmsux]+\))?")


def _first_leaf(rule: dict) -> dict:
    while rule.get("rules"):
        rule = rule["rules"][0]
    return rule


def test_the_census_fires_when_the_banned_class_is_re_admitted(tmp_path):
    """The census, proved two-sided against the REAL register rather than planted strings.

    The regex tests above prove the MATCHER discriminates. They cannot prove the census
    reaches the register's own patterns: a loader change, a shape change, or a walk that
    missed this record's branch would leave every assertion above green while the class
    walked back in. So this copies the register, puts the deleted prefix back on GAP-014's
    first pattern, and asserts the census reports exactly that record.

    Nothing in the repo is touched -- the copy lives under `tmp_path`.
    """
    copied = tmp_path / "gaps"
    copied.mkdir()
    reconstructed: str | None = None
    for source in sorted(REPO_GAPS.glob("*.json")):
        record = json.loads(source.read_text(encoding="utf-8"))
        if record.get("id") == "GAP-014":
            leaf = _first_leaf(record["check"]["present_when"])
            cut = _LEADING_FLAGS.match(leaf["pattern"]).end()
            leaf["pattern"] = (leaf["pattern"][:cut] + RE_ADMITTED_PREFIX
                               + leaf["pattern"][cut:])
            reconstructed = leaf["pattern"]
        (copied / source.name).write_text(json.dumps(record, indent=2) + "\n",
                                         encoding="utf-8")
    assert reconstructed is not None, "GAP-014 was not found in the register"
    re.compile(reconstructed)  # the reconstructed pre-change pattern is a legal regex

    live = _register_patterns()
    copy = _register_patterns(copied)
    assert len(copy) == len(live), (
        f"the copied register lost patterns ({len(copy)} vs {len(live)}), so a clean "
        f"census over it would prove nothing")

    offenders = sorted(gid for gid, pat in copy if BANNED_OPENING.match(pat))
    assert offenders == ["GAP-014"], (
        f"the census did not report the re-admitted class on the real register: "
        f"{offenders}")


# --- Behavior 2: the record's own bad fixture still reports the same bytes -------------

def test_gap_014_bad_fixture_reports_the_same_locations(tmp_path):
    """Behavior 2. The non-regression control on the DECISION, not just the cost.

    Line 6 of that fixture is itself a class-prefixed case, so if deleting the prefix
    could move a reported line, this is where it would show.
    """
    check = _gap("GAP-014").check.model_dump(exclude_none=True)
    target = _materialise(tmp_path / "bad", check["fixtures"]["bad"])
    outcome = run_check(check, target)
    assert outcome.verdict is Verdict.PRESENT, (
        f"GAP-014's check no longer fires on its own known-bad fixture "
        f"({outcome.verdict.value}: {outcome.reason})")
    assert outcome.locations[:2] == ["app/scoring.py:6", "app/scoring.py:12"], (
        f"the reported location bytes moved: {outcome.locations[:2]}")


def test_gap_014_good_fixture_still_does_not_fire(tmp_path):
    """The two-sided half of behavior 2, so PRESENT above is a decision, not a constant."""
    check = _gap("GAP-014").check.model_dump(exclude_none=True)
    target = _materialise(tmp_path / "good", check["fixtures"]["good"])
    outcome = run_check(check, target)
    assert outcome.verdict is not Verdict.PRESENT, (
        f"GAP-014's check fired on its known-GOOD fixture at {outcome.locations}")


# --- Behavior 3: a class-prefixed candidate still matches, on its own line ------------

_B3_MATCHING = 'import json\n\nPATH = "/var/lib/agent/http_requests_features.json"\n'
_B3_CONTROL = 'import json\n\nPATH = "/var/lib/agent/http_requests_notes.txt"\n'


def test_a_class_prefixed_candidate_still_matches_on_its_own_line(tmp_path):
    """Behavior 3. 29 characters of `[\\w/.-]` precede the keyword, on line 3.

    This is the case the deleted prefix was nominally there to cover. An unanchored
    `search` already tries every offset, so the hit and its LINE must be unchanged.
    """
    rule = _first_present_rule(_gap("GAP-014").check.model_dump(exclude_none=True))
    hit = evaluate(rule, _materialise(tmp_path / "hit", {"svc/load.py": _B3_MATCHING}))
    assert hit.matched, "a candidate preceded by class characters was missed"
    assert hit.locations == ["svc/load.py:3"], hit.locations


def test_the_same_rule_stays_silent_without_a_candidate(tmp_path):
    """Behavior 3's two-sided control: one filename changed, nothing else."""
    rule = _first_present_rule(_gap("GAP-014").check.model_dump(exclude_none=True))
    hit = evaluate(rule, _materialise(tmp_path / "miss", {"svc/load.py": _B3_CONTROL}))
    assert not hit.matched, f"fired without a candidate artifact: {hit.locations}"
    assert hit.locations == [], hit.locations


# --- Behavior 4: a long line of class characters no longer costs seconds ---------------

def _long_line() -> str:
    line = ("abc/def-ghi." * 267)[:LONG_LINE_CHARS]
    assert len(line) == LONG_LINE_CHARS
    assert not BANNED_OPENING.match(line)  # sanity: this is data, not a pattern
    return line


def test_a_long_class_character_line_is_no_longer_seconds_of_backtracking(tmp_path):
    """Behavior 4. Times ONLY the `evaluate` call the assertion names.

    The margin is asserted against `evaluate`, not against the bare regex: roughly
    25 ms of the measured cost is per-call overhead (the `git ls-files` probe, the walk,
    the read) that the pattern cannot explain, so a bound justified by a component
    measurement would be justified by the wrong number.
    """
    target = _materialise(
        tmp_path / "bundle",
        {"bundle.js": "\n".join([_long_line()] * LONG_LINE_COUNT) + "\n"},
    )
    rule = _first_present_rule(_gap("GAP-014").check.model_dump(exclude_none=True))

    started = time.perf_counter()
    hit = evaluate(rule, target)
    elapsed = time.perf_counter() - started

    assert not hit.matched, f"the long-line fixture holds no candidate: {hit.locations}"
    assert elapsed < LONG_LINE_BUDGET_SECONDS, (
        f"{LONG_LINE_COUNT} lines of {LONG_LINE_CHARS} class characters took "
        f"{elapsed:.3f}s, over the {LONG_LINE_BUDGET_SECONDS}s budget -- a leading "
        f"quantified wildcard is backtracking again")

    # Two-sided control on the SAME file: a bound met by a pattern that can no longer
    # match anything would be worthless.
    with (target / "bundle.js").open("a", encoding="utf-8") as handle:
        handle.write('var p = "prompt_bundle.json";\n')
    control = evaluate(rule, target)
    assert control.matched, "the rule stopped matching a real candidate entirely"
    assert control.locations == [f"bundle.js:{LONG_LINE_COUNT + 1}"], control.locations
