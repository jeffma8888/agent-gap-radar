"""Iteration 81 behaviors: GAP-109's zero-width lookahead pattern anchors to `\\A`.

Iteration 81's payload is register DATA: one anchor changes from `^` to `\\A` in GAP-109's
two zero-width pattern fields, and a suite-level census makes the whole SHAPE unmergeable.
The claim has two halves that fail in opposite directions, so both are asserted here:

* the SCAN gets cheap -- `checks` compiles content patterns with `re.MULTILINE`, so a `^`
  followed by two scan-to-end lookaheads is retried at every line start and a non-matching
  file is rescanned once per line;
* the DECISION does not move -- the whole pattern is zero-width, so a match exists at some
  line start iff a match exists at position 0, and the reported line is 1 either way.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source (`src/`, `tools/`), the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`,
or any diff. Every expectation comes from `pm.md`'s Expected Behaviors; every value is
measured by CALLING the public CLI (`cli.main`) or the public `checks`/`registry` API.

Structural notes, so this file cannot lie later:

* **No pattern text from the register is copied into this file.** Behaviors 3-5 navigate to
  "GAP-109's third `present_when` rule" and "GAP-109's `mitigated_when`" structurally, and
  the shape guards red if the record is reshaped, so this file cannot drift into asserting
  a pattern's literal bytes.
* **The census is proved two-sided three ways**: on planted bad patterns it must catch, on
  planted good patterns AND on the register's own legitimate lookahead-carrying patterns it
  must leave alone, and on a MODIFIED COPY of the real register with GAP-109 reverted to `^`
  it must fire with exactly the two offenders. A census whose predicate cannot fire reports
  a clean register it never examined -- the fail-open this product exists to refuse.
* **The predicate's specificity is asserted, not assumed.** A brake written as "carries a
  lookahead" would refuse legitimate shipped records; the count of those records is measured
  in the same test, so the loose predicate can never be substituted silently.
* **The census walk is anti-vacuous by DERIVED EQUALITY** against an independent count of
  `"pattern":` keys in the register's bytes, so a walker blind to a combinator cannot pass.
* **The equivalence claim is settled by EXECUTION, not by reading the regex** -- `evaluate`
  is run with both spellings over committed offline fixture trees.
* **No absolute machine path, no personal or employer identifier appears here**; the repo
  root is found relative to this file.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar.checks import evaluate
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_GAPS = REPO_ROOT / "gaps"

#: The record whose anchor moved, and the floors `pm.md` states. Floors, not equalities, so
#: the register may keep growing; their failure messages name the one legitimate way to red.
TARGET_ID = "GAP-109"
SPEC_MIN_RECORDS = 120
SPEC_MIN_PATTERNS = 506
#: `pm.md`: 5 shipped patterns carry a lookahead and only GAP-109's 2 carry the bad shape.
SPEC_MIN_LOOKAHEAD_PATTERNS = 3

#: The three check fields a rule can hang from, and the combinators the walk recurses into.
RULE_FIELDS = ("applies_when", "present_when", "mitigated_when")

#: An unbounded any-character scan, as it appears in a PATTERN's text: `[\\s\\S]*`,
#: `[\\S\\s]+`, `[^]*`. Written against the pattern's characters, not against what it matches.
_ANY_CHAR_SCAN = re.compile(r"(?:\[\\[sS]\\[sS]\]|\[\^\])[*+]")
#: A dot-star, only pathological when the pattern also turns on DOTALL.
_DOT_SCAN = re.compile(r"(?<!\\)\.[*+]")
_DOTALL_FLAG = re.compile(r"\(\?[aiLmux]*s[aiLmux]*[):]")


# --- pattern-shape primitives (pure text; no product code involved) --------------------

def _line_anchors(pattern: str) -> list[int]:
    """Offsets of every `^` in `pattern` that is a LINE ANCHOR.

    Skips an escaped `\\^`, skips anything inside a character class, and skips the leading
    `^` of a negated class -- those are not anchors and must not be censused.
    """
    out: list[int] = []
    i, n, in_class = 0, len(pattern), False
    while i < n:
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            if i < n and pattern[i] == "^":
                i += 1  # class negation, not an anchor
            continue
        if c == "^":
            out.append(i)
        i += 1
    return out


def _lookahead_bodies(pattern: str) -> list[str]:
    """The text of every look-around group in `pattern`, extracted by balanced parens."""
    bodies: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern[i] == "\\":
            i += 2
            continue
        if any(pattern.startswith(op, i) for op in ("(?=", "(?!", "(?<=", "(?<!")):
            depth, j, in_class = 0, i, False
            while j < n:
                ch = pattern[j]
                if ch == "\\":
                    j += 2
                    continue
                if in_class:
                    if ch == "]":
                        in_class = False
                    j += 1
                    continue
                if ch == "[":
                    in_class = True
                    j += 1
                    if j < n and pattern[j] == "^":
                        j += 1
                    continue
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            bodies.append(pattern[i:j])
            i += 3
            continue
        i += 1
    return bodies


def _offends(pattern: str) -> bool:
    """Behavior 4's predicate: a LINE anchor combined with a scan-to-end look-around.

    Deliberately NOT "carries a lookahead" and NOT "carries `[\\s\\S]*`": either alone is a
    legitimate shape that the shipped register uses. It is the pair that makes a zero-width
    pattern quadratic under `re.MULTILINE`, because every line start retries both scans.
    """
    if not _line_anchors(pattern):
        return False
    dotall = bool(_DOTALL_FLAG.search(pattern))
    for body in _lookahead_bodies(pattern):
        if _ANY_CHAR_SCAN.search(body):
            return True
        if dotall and _DOT_SCAN.search(body):
            return True
    return False


def _carries_lookahead(pattern: str) -> bool:
    """The NAIVE predicate, kept only so its over-reach can be measured against `_offends`."""
    return bool(_lookahead_bodies(pattern))


# --- register navigation ---------------------------------------------------------------

def _collect(check: dict) -> list[str]:
    """Every `pattern` string reachable from a check's three rule fields.

    Recurses into `any_of`/`all_of` (`rules`) and `not` (`rule`). Proved anti-vacuous by
    the derived equality in `test_iter81_b4_...census...`.
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
    """`(record id, pattern)` for every content pattern on disk.

    Takes a directory so the census can be proved against a MODIFIED COPY of the REAL
    register rather than only against planted strings.
    """
    pairs: list[tuple[str, str]] = []
    for gap in load_all(gaps_dir):
        if gap.check is None:
            continue
        for pattern in _collect(gap.check.model_dump(exclude_none=True)):
            pairs.append((gap.id, pattern))
    return pairs


def _raw_pattern_key_count(gaps_dir: pathlib.Path = REPO_GAPS) -> int:
    """A SECOND, independent measurement of the same quantity, straight from the bytes.

    Deliberately not a JSON walk: sharing code with `_collect` would move both sides of the
    equality together and prove nothing.
    """
    return sum(p.read_text(encoding="utf-8").count('"pattern":')
               for p in sorted(gaps_dir.glob("*.json")))


def _gap(gap_id: str, gaps_dir: pathlib.Path = REPO_GAPS):
    for gap in load_all(gaps_dir):
        if gap.id == gap_id:
            return gap
    raise AssertionError(f"{gap_id} is not in the register")


def _zero_width_fields(gaps_dir: pathlib.Path = REPO_GAPS) -> tuple[str, str]:
    """GAP-109's two zero-width pattern fields, reached STRUCTURALLY.

    The shape is asserted first so that reshaping the record reds here instead of silently
    letting the behaviors below test some other rule.
    """
    check = _gap(TARGET_ID, gaps_dir).check.model_dump(exclude_none=True)
    present = check["present_when"]
    assert present.get("kind") == "all_of", (
        f"{TARGET_ID}.present_when is no longer an all_of ({present.get('kind')!r}); "
        f"behaviors 3-5 navigate to rules[2] and must be re-pointed")
    rules = present["rules"]
    assert len(rules) == 3, f"{TARGET_ID}.present_when has {len(rules)} rules, expected 3"
    third = rules[2]
    assert third.get("kind") == "content_absent", third.get("kind")
    mitigated = check["mitigated_when"]
    assert mitigated.get("kind") == "content_matches", mitigated.get("kind")
    return third["pattern"], mitigated["pattern"]


def _mutated_register(tmp_path: pathlib.Path) -> pathlib.Path:
    """A copy of the REAL register with GAP-109's two anchors reverted `\\A` -> `^`.

    Rewritten through `json`, never by patching file bytes, so JSON escaping cannot make the
    mutation silently miss and hand back a false clean.
    """
    dest = tmp_path / "reverted-gaps"
    dest.mkdir(parents=True, exist_ok=True)
    reverted = 0
    for src in sorted(REPO_GAPS.glob("*.json")):
        record = json.loads(src.read_text(encoding="utf-8"))
        if record.get("id") == TARGET_ID:
            check = record["check"]
            for holder, key in ((check["present_when"]["rules"][2], "pattern"),
                                (check["mitigated_when"], "pattern")):
                pattern = holder[key]
                assert "\\A" in pattern, f"nothing to revert in {pattern!r}"
                holder[key] = pattern.replace("\\A", "^", 1)
                reverted += 1
        (dest / src.name).write_text(json.dumps(record), encoding="utf-8")
    assert reverted == 2, f"reverted {reverted} anchors, expected 2"
    return dest


# --- offline fixture trees (multi-line, markers deliberately off line 1) ----------------

APPLIES = "from openai import OpenAI\n"
PROMPT_MARK = 'PROMPT_VERSION = "7"\n'
MODEL_MARK = 'model_version = "2026-01-02"\n'
FILLER = "# padding line so the markers do not sit on line 1\n"


def _tree(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _both_markers_late() -> str:
    return APPLIES + FILLER * 40 + PROMPT_MARK + FILLER * 40 + MODEL_MARK + FILLER * 40


def _one_marker_only() -> str:
    return APPLIES + FILLER * 40 + PROMPT_MARK + FILLER * 40


# --- Behavior 1: validate is unchanged --------------------------------------------------

def test_iter81_b1_validate_exits_zero_and_reports_every_record(capsys) -> None:
    """Behavior 1. Exit 0, the record count on stdout, empty stderr, exactly one newline."""
    expected = len(load_all(REPO_GAPS))
    rc = main(["validate", str(REPO_ROOT)])
    captured = capsys.readouterr()
    assert rc == 0, f"validate exited {rc}; stderr={captured.err!r}"
    assert captured.err == "", f"validate wrote to stderr: {captured.err!r}"
    assert captured.out == f"OK: {expected} gap record(s) valid.\n", repr(captured.out)
    assert expected >= SPEC_MIN_RECORDS, (
        f"the register holds {expected} records, below the spec floor of "
        f"{SPEC_MIN_RECORDS}. If records were deliberately RETIRED, lower this floor.")


# --- Behavior 2: the scan document does not move ----------------------------------------

def test_iter81_b2_the_scan_document_is_byte_identical_under_both_anchors(
        tmp_path, capsys) -> None:
    """Behavior 2. The same target scanned with the shipped register and with a register
    whose GAP-109 anchors are reverted must produce the SAME document, byte for byte.

    This is the in-suite, offline form of the acceptance criterion that the tool's claims
    about a target did not move. The repo-scale comparison against a pre-change baseline is
    a stage measurement, not something a test may reach for -- it needs git history.
    """
    target = _tree(tmp_path / "svc", {
        "app/agent.py": _both_markers_late(),
        "app/other.py": _one_marker_only(),
        "README.md": "# a service\n",
    })
    reverted = _mutated_register(tmp_path)

    assert main(["scan", str(target), "--gaps", str(REPO_GAPS)]) == 0
    shipped_out = capsys.readouterr()
    assert main(["scan", str(target), "--gaps", str(reverted)]) == 0
    reverted_out = capsys.readouterr()

    assert shipped_out.err == "" and reverted_out.err == "", (
        f"scan wrote to stderr: {shipped_out.err!r} / {reverted_out.err!r}")
    assert shipped_out.out, "premise: the scan produced a document"
    assert shipped_out.out.endswith("\n") and not shipped_out.out.endswith("\n\n"), \
        "the renderer must end in exactly one newline"
    assert shipped_out.out == reverted_out.out, (
        "the anchor change moved the scan document; the increment was supposed to change "
        "cost only")


# --- Behavior 3: the two fields anchor to the input start -------------------------------

def test_iter81_b3_gap109_zero_width_fields_anchor_to_the_input_start() -> None:
    """Behavior 3. Both fields open with `\\A`, neither with a line anchor, and the two
    remain byte-identical to each other."""
    third, mitigated = _zero_width_fields()
    for label, pattern in (("present_when.rules[2]", third), ("mitigated_when", mitigated)):
        body = pattern[len("(?s)"):] if pattern.startswith("(?s)") else pattern
        assert body.startswith("\\A"), f"{label} does not anchor to input start: {pattern!r}"
        assert not body.startswith("^"), f"{label} still opens with a line anchor: {pattern!r}"
        assert not _line_anchors(pattern), (
            f"{label} still contains a line anchor at {_line_anchors(pattern)}: {pattern!r}")
    assert third == mitigated, (
        "the two zero-width fields diverged; they describe the same condition and a "
        "difference means one of them was edited alone")


def test_iter81_b3_no_other_record_carries_the_reverted_anchor_shape() -> None:
    """Behavior 3's register-wide half: GAP-109's two patterns are the only ones the fix
    touched, so no OTHER record may now hold the shape the fix removed."""
    offenders = sorted({gid for gid, pat in _register_patterns() if _offends(pat)})
    assert offenders == [], f"records still carrying the pathological shape: {offenders}"


# --- Behavior 4: the census brake -------------------------------------------------------

def test_iter81_b4_no_register_pattern_combines_a_line_anchor_with_a_scan_to_end_lookahead(
) -> None:
    """Behavior 4. The census, plus its anti-vacuity in the same test."""
    pairs = _register_patterns()
    offenders = [(gid, pat) for gid, pat in pairs if _offends(pat)]
    assert not offenders, (
        "content pattern(s) combine a line-anchoring `^` with a look-around that scans to "
        "end of input. Under `re.MULTILINE` that is retried at every line start, so a "
        f"non-matching file is rescanned once per line: {offenders}")

    # Anti-vacuity, half one: a derived equality against an independent measurement.
    raw = _raw_pattern_key_count()
    assert len(pairs) == raw, (
        f"the census walked {len(pairs)} patterns but the register's bytes declare {raw} "
        f'"pattern" keys -- the walk is missing a combinator branch, so patterns nested '
        f"in it are never censused")

    # Anti-vacuity, half two: the spec's floor.
    assert len(pairs) >= SPEC_MIN_PATTERNS, (
        f"census collected {len(pairs)} patterns, below the spec floor of "
        f"{SPEC_MIN_PATTERNS}. If a record was deliberately REMOVED, lower this floor; "
        f"the equality above is the growth-proof half.")


def test_iter81_b4_the_census_predicate_is_narrower_than_carries_a_lookahead() -> None:
    """Behavior 4's specificity clause, measured on the SHIPPED register.

    `pm.md` states that a brake written as "carries a lookahead" refuses legitimate
    records. That over-reach is measured here so the loose predicate can never be
    substituted for the shape predicate without reding a named test.
    """
    pairs = _register_patterns()
    loose = sorted({gid for gid, pat in pairs if _carries_lookahead(pat)})
    strict = sorted({gid for gid, pat in pairs if _offends(pat)})
    assert strict == [], f"the shape predicate fires on the shipped register: {strict}"
    assert len(loose) >= SPEC_MIN_LOOKAHEAD_PATTERNS, (
        f"only {len(loose)} shipped record(s) carry a look-around ({loose}); the "
        f"specificity claim needs at least {SPEC_MIN_LOOKAHEAD_PATTERNS} legitimate "
        f"carriers to be worth anything")


@pytest.mark.parametrize("pattern", [
    r"^(?=[\s\S]*ALPHA)",
    r"(?s)^(?=[\S\s]+BETA)(?=[\s\S]*GAMMA)",
    r"(?s)^(?=.*DELTA)",
    r"(?m)^(?![\s\S]*EPSILON)",
    r"foo\n^(?=[\s\S]*ZETA)",
])
def test_iter81_b4_the_predicate_catches_every_planted_bad_shape(pattern) -> None:
    """Behavior 4, two-sided half one: a predicate that cannot fire proves nothing."""
    assert _offends(pattern), f"the census would admit {pattern!r}"


@pytest.mark.parametrize("pattern", [
    r"(?s)\A(?=[\s\S]*ALPHA)",          # the fixed shape: anchored to input start
    r"(?=[\s\S]*BETA)",                  # a lookahead with no line anchor
    r"^\s*def [a-z_]+\(",                # a line anchor with no lookahead
    r"^(?=\w{3,8}:)",                    # a line anchor with a BOUNDED lookahead
    r"[^*]+\*",                          # a negated class, not an anchor
    r"\^(?=[\s\S]*GAMMA)",               # an ESCAPED caret, not an anchor
    r"(?i)(alpha|beta)",                 # neither
])
def test_iter81_b4_the_predicate_leaves_every_planted_good_shape_alone(pattern) -> None:
    """Behavior 4, two-sided half two: it must not refuse legitimate shapes."""
    assert not _offends(pattern), f"the census would refuse {pattern!r}"


def test_iter81_b4_the_census_fires_on_the_real_register_with_gap109_reverted(
        tmp_path) -> None:
    """Behavior 4's mutation proof, run against a MODIFIED COPY of the REAL register.

    Planted strings prove the predicate; only the real register reverted proves the census
    is wired to the data that actually ships.
    """
    reverted = _mutated_register(tmp_path)
    pairs = _register_patterns(reverted)
    offenders = [(gid, pat) for gid, pat in pairs if _offends(pat)]
    assert len(offenders) == 2, (
        f"reverting {TARGET_ID}'s two anchors produced {len(offenders)} offender(s); the "
        f"census is not reading the shipped register: {[g for g, _ in offenders]}")
    assert {gid for gid, _ in offenders} == {TARGET_ID}, sorted({g for g, _ in offenders})
    # The copy is otherwise the real register, so the walk size must be unchanged.
    assert len(pairs) == len(_register_patterns()), \
        "the mutated copy lost or gained patterns; the mutation was not surgical"


# --- Behavior 5: the two spellings agree, proved by execution ---------------------------

def _spelling(pattern: str, anchor: str) -> str:
    assert pattern.count("\\A") == 1, f"expected exactly one `\\A` in {pattern!r}"
    return pattern.replace("\\A", anchor)


#: A `RuleHit` location that names a real hit looks like `path:line`. When a rule finds
#: nothing, this product instead reports a DIAGNOSTIC that echoes the pattern it searched
#: for -- measured this iteration. That echo makes literal `locations` equality unreachable
#: across two spellings BY CONSTRUCTION, so the comparison is split in two: the locators
#: that make a claim about the TARGET are compared verbatim, and the diagnostics are
#: compared with the anchor spelling normalised away. Both must agree; neither alone is
#: enough, because dropping the diagnostics would stop noticing a rule that started
#: searching a different domain.
_DIAGNOSTIC_PREFIX = "(no match)"


def _target_locators(hit) -> list[str]:
    """Only the locations that make a claim about the scanned target."""
    return [loc for loc in hit.locations if not loc.startswith(_DIAGNOSTIC_PREFIX)]


def _anchor_normalised(hit) -> list[str]:
    """Every location, with the anchor spelling collapsed so an echoed pattern compares."""
    return [loc.replace("\\A", "^") for loc in hit.locations]


@pytest.mark.parametrize("field", ["present_when.rules[2]", "mitigated_when"])
@pytest.mark.parametrize("kind,files,name", [
    ("matching", {"app/agent.py": _both_markers_late()}, "hit"),
    ("non-matching", {"app/agent.py": _one_marker_only()}, "miss"),
])
def test_iter81_b5_both_anchors_return_the_same_verdict_and_locations(
        tmp_path, field, kind, files, name) -> None:
    """Behavior 5. `evaluate` with `^` and with `\\A` must agree on `matched` and on
    `locations`, over committed offline fixture trees. No network, no dependence on the
    live repo's contents."""
    third, mitigated = _zero_width_fields()
    check = _gap(TARGET_ID).check.model_dump(exclude_none=True)
    rule = dict(check["present_when"]["rules"][2]) if field.startswith("present") \
        else dict(check["mitigated_when"])
    shipped_pattern = third if field.startswith("present") else mitigated

    target = _tree(tmp_path / f"{name}-{field.split('.')[0]}", files)
    decisions, normalised = {}, {}
    for anchor in ("\\A", "^"):
        probe = dict(rule)
        probe["pattern"] = _spelling(shipped_pattern, anchor)
        hit = evaluate(probe, target)
        decisions[anchor] = (hit.matched, _target_locators(hit))
        normalised[anchor] = (hit.matched, _anchor_normalised(hit))

    assert decisions["\\A"] == decisions["^"], (
        f"{field} on the {kind} fixture disagrees between anchors: {decisions}")
    assert normalised["\\A"] == normalised["^"], (
        f"{field} on the {kind} fixture: the searched DOMAIN differs between anchors, "
        f"which the pattern echo alone cannot explain: {normalised}")


def test_iter81_b5_the_fixtures_are_discriminating_not_vacuous(tmp_path) -> None:
    """Behavior 5's anti-vacuity: two spellings agree trivially if neither ever matches.

    So the SAME `content_matches` rule must MATCH the two-marker fixture, report a
    non-empty location, and stay SILENT on the one-marker fixture -- under both spellings.
    """
    _, mitigated = _zero_width_fields()
    check = _gap(TARGET_ID).check.model_dump(exclude_none=True)
    rule = dict(check["mitigated_when"])

    hit_tree = _tree(tmp_path / "discriminating-hit", {"app/agent.py": _both_markers_late()})
    miss_tree = _tree(tmp_path / "discriminating-miss", {"app/agent.py": _one_marker_only()})

    for anchor in ("\\A", "^"):
        probe = dict(rule)
        probe["pattern"] = _spelling(mitigated, anchor)
        hit = evaluate(probe, hit_tree)
        assert hit.matched, f"anchor {anchor!r}: the two-marker fixture did not match"
        assert hit.locations == ["app/agent.py:1"], (
            f"anchor {anchor!r}: a zero-width whole-input pattern must report line 1, got "
            f"{hit.locations}")
        miss = evaluate(probe, miss_tree)
        assert not miss.matched, (
            f"anchor {anchor!r}: the one-marker fixture matched at {miss.locations}")
        assert _target_locators(miss) == [], (
            f"anchor {anchor!r}: a non-matching rule named a location in the target: "
            f"{miss.locations}")


# --- Behavior 6: the error contract is unchanged ----------------------------------------

MALFORMED = "(unclosed"


def _register_with_a_malformed_pattern(tmp_path: pathlib.Path) -> pathlib.Path:
    """One REAL record, copied, with its `applies_when` pattern replaced by a bad regex.

    Copied rather than hand-written so the record stays schema-valid in every other field,
    which is what makes the pattern the only reason the tool can refuse it.
    """
    dest = tmp_path / "malformed" / "gaps"
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(REPO_GAPS.glob("*.json")):
        record = json.loads(src.read_text(encoding="utf-8"))
        check = record.get("check") or {}
        applies = check.get("applies_when")
        if isinstance(applies, dict) and isinstance(applies.get("pattern"), str):
            applies["pattern"] = MALFORMED
            (dest / "MALFORMED.json").write_text(json.dumps(record), encoding="utf-8")
            return dest
    raise AssertionError("no register record carries an applies_when pattern to corrupt")


@pytest.mark.parametrize("verb", ["validate", "scan"])
def test_iter81_b6_a_malformed_pattern_exits_two_with_one_error_line(
        tmp_path, capsys, verb) -> None:
    """Behavior 6. Exit 2, nothing on stdout, exactly one `Error: `-prefixed stderr line."""
    gaps = _register_with_a_malformed_pattern(tmp_path)
    target = _tree(tmp_path / "svc6", {"app/agent.py": _both_markers_late()})
    argv = [verb, str(gaps.parent)] if verb == "validate" \
        else [verb, str(target), "--gaps", str(gaps)]

    rc = main(argv)
    captured = capsys.readouterr()
    assert rc == 2, f"{verb} exited {rc}, expected 2; stderr={captured.err!r}"
    assert captured.out == "", f"{verb} wrote a document to stdout: {captured.out!r}"
    lines = captured.err.splitlines()
    assert len(lines) == 1, f"{verb} wrote {len(lines)} stderr line(s): {captured.err!r}"
    assert lines[0].startswith("Error: "), repr(lines[0])
    assert captured.err.endswith("\n"), "the error line must be newline-terminated"


def test_iter81_b6_the_same_register_is_accepted_once_the_pattern_is_valid(
        tmp_path, capsys) -> None:
    """Behavior 6's two-sided control: the refusal must be caused by the PATTERN.

    Without this, a test asserting exit 2 passes for any reason at all -- a missing field, a
    bad path -- and stops being evidence about pattern compilation.
    """
    gaps = _register_with_a_malformed_pattern(tmp_path)
    path = gaps / "MALFORMED.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["check"]["applies_when"]["pattern"] == MALFORMED, "premise: it is corrupt"
    record["check"]["applies_when"]["pattern"] = "(closed)"
    path.write_text(json.dumps(record), encoding="utf-8")

    rc = main(["validate", str(gaps.parent)])
    captured = capsys.readouterr()
    assert rc == 0, f"the repaired register was still refused: {captured.err!r}"
    assert captured.err == "" and captured.out.endswith("\n"), repr(captured)
