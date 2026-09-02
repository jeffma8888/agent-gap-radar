"""Iteration 93 behaviors: `checks.required_literals`, a DORMANT required-literal
extractor for register content patterns.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
as logic, nor the engineer's or the reviewer's notes, nor `IMPLEMENTATION.patch`, nor any
diff. Every expectation comes from `pm.md`'s Expected Behaviors and from the function's
own PUBLISHED docstring (`checks.required_literals.__doc__`), which is the contract a
caller is told to rely on. Every shape claim was measured by CALLING the public function,
by running the CLI verbs through `main`, or by reading `tests/` as data.

ONE DISCLOSURE, also carried in the tester report: behaviors 8 and 9 read the files under
`src/agent_gap_radar/` as TEXT and as an `ast` parse tree, because the spec defines them
that way -- behavior 8 is a differential probe that needs real text as a corpus, and
behavior 9 is a census of NAMES and CALL nodes. No assertion here encodes anything about
HOW the extractor works: the corpus is a haystack, and the census counts symbols.

Structural notes, so this file cannot lie later:

* **Every set-equality assertion is one of `pm.md`'s OWN examples**, or a direct
  instantiation of a rule the spec states in general. Cases invented beyond that assert
  the PUBLISHED GUARANTEE (non-empty, lowercase, and every match of the pattern contains
  a member) rather than a specific set, because the contract explicitly permits returning
  `None` -- or a shorter literal -- whenever the extractor cannot prove more. Pinning an
  invented set would pin an implementation quirk, which the isolation contract forbids.
* **Behavior 8 is proven TWO-SIDED by MUTATING the literal source, not by hoping.** One
  probe function is applied three times: to the real extractor (must report ZERO
  violations), to a mutant that swaps in a literal that cannot occur (must report at
  least one), and to a mutant that substitutes `frozenset()` wherever the real extractor
  returned `None` (must also report at least one). Without the mutants, a probe that only
  ever sees a sound extractor is indistinguishable from a probe incapable of seeing
  unsoundness -- and the second mutant IS the spec's other side, that a pattern returning
  `None` is never treated as covered.
* **Behavior 8 asserts NO COUNT of covered patterns, records or files.** The register is
  grown by an outside research pass, so a keyed or counted expectation over it would red
  this file on a CORRECT register (the iteration-09 landmine). What it does assert is
  NON-VACUITY as a strict lower bound: the probe must reach the "the regex matched"
  branch at least once, or "zero violations" is the green that means nothing.
* **The public-function census is APPEND-ONLY and spelled once.** `PUBLIC_CHECKS_FUNCTIONS`
  is DERIVED as `PRE_EXISTING_PUBLIC_CHECKS_FUNCTIONS + ["required_literals"]`, so one
  passing assert establishes both halves: no public function of `checks` was removed or
  renamed, and the extractor joined them. Private helper names are deliberately NOT
  pinned; they are the implementation's business.
* **The escape whitelist is spelled ONCE**, as `PUNCT_ESCAPES`, and both the per-character
  behavior-2 assertions and the behavior-6 docstring assertion are derived from it, so the
  two can never disagree about what the whitelist is.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every register and target a CLI verb runs over is built under
  pytest's `tmp_path`.
* **Nothing under `gaps/` is edited to make an assertion true**, and no record id from the
  live register is named.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main
from test_iter02_behavior import _record, _target, _write_register

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"
LIVE_GAPS = REPO_ROOT / "gaps"

#: Behavior 2's escape whitelist, spelled ONCE. Behavior 6 derives the docstring's
#: whitelist line from this same tuple, so the file cannot claim two whitelists.
PUNCT_ESCAPES = (".", "-", "_", "/", "(", ")", "[", "]", "{", "}",
                 "+", "*", "?", "|", "^", "$", "\\")

#: The published guarantee, quoted from `pm.md`'s contract blockquote with its line
#: breaks collapsed. Behavior 6 requires the shipped docstring to state it verbatim.
GUARANTEE = (
    "If it returns a set `L`, then `L` is non-empty and for every text `t`, if "
    "`re.compile(pattern, re.MULTILINE).search(t)` is not `None`, then at least one "
    "member of `L` is a substring of `t.lower()`."
)

#: Behavior 7's eight REQUIRED adversarial inputs, named by the spec.
SPEC_REQUIRED_ADVERSARIAL = ("", "(", "[a", "a\\", "(?i)", "|", "(?P<x>a)|b")

#: Behavior 7's committed adversarial list: the spec's eight (the eighth being a
#: 4,000-character pattern) plus every other malformed shape worth one call.
ADVERSARIAL = SPEC_REQUIRED_ADVERSARIAL + (
    "x" * 4000,
    ")", "[", "]", "{", "}", "\\", "*", "+", "?", "{2}", "a{", "a[", "((", "))",
    "(?", "(?i", "(?P", "(?P<", "(?P<x", "(?P=x)", "(?#c)", "(?=a)b", "(?!a)b",
    "[]", "[^]", "[a-", "a**", "a|[", "|||", "\\\\", "\\1", "\\x", "\\N{}",
    "a\n|b", "\t|\t", "ü|ö", "(?i)ı", "(" * 200, "a|" * 500, "[" + "a" * 500,
)

#: Behavior 9. The PUBLIC top-level functions `checks` exposed before this iteration,
#: measured by introspecting the module at HEAD. `required_literals` is APPENDED, so one
#: passing assert proves both halves: nothing public was removed or renamed, and the
#: extractor joined the surface. Private helpers are the implementation's business and
#: are deliberately not pinned.
PRE_EXISTING_PUBLIC_CHECKS_FUNCTIONS = [
    "evaluate", "file_cache_scope", "is_test_path", "iter_files",
    "read_cache_scope", "run_check", "tracked_files",
]
PUBLIC_CHECKS_FUNCTIONS = sorted(
    PRE_EXISTING_PUBLIC_CHECKS_FUNCTIONS + ["required_literals"])

#: Behavior 9. The verbs the spec names as keeping their exact surface.
SHIPPED_VERBS = ("scan", "report", "list", "show", "prd", "validate", "diff", "taxonomy")

#: A literal no source file can contain, used to mutate the probe in behavior 8.
IMPOSSIBLE_LITERAL = "gapradar-iter93-literal-that-cannot-occur"


# ---------------------------------------------------------------------------
# Corpus helpers. `gaps/` is read ONLY as a haystack of pattern strings; no record
# id, count or keyed value is asserted anywhere in this file.
# ---------------------------------------------------------------------------

def _collect_patterns(node, out):
    """Every `pattern` string anywhere inside a rule tree, at any nesting depth."""
    if isinstance(node, dict):
        pattern = node.get("pattern")
        if isinstance(pattern, str):
            out.add(pattern)
        for value in node.values():
            _collect_patterns(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_patterns(value, out)


def _distinct_content_patterns():
    """The live register's distinct content-rule patterns, sorted for determinism."""
    found = set()
    for path in sorted(LIVE_GAPS.glob("*.json")):
        check = json.loads(path.read_text(encoding="utf-8")).get("check")
        if not check:
            continue
        for slot in ("present_when", "mitigated_when", "applies_when"):
            if check.get(slot) is not None:
                _collect_patterns(check[slot], found)
    return sorted(found)


def _tracked_src_texts():
    """`(relative path, text)` for every TRACKED file under `src/agent_gap_radar/`."""
    listing = subprocess.run(
        ["git", "ls-files", "src/agent_gap_radar"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.split()
    return [(rel, (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace"))
            for rel in sorted(listing)]


def _every_pattern_this_file_uses():
    return list(ADVERSARIAL) + [
        "(?i)(budget|allowance|quota)", "(foo)|(bar)", "a[|]b|cd", "foobar?|baz",
        "ab{0,3}c|de", "foo|", "Foo|BAR", "foo+|bar", "a?bc|de", "x{2}y|z",
        r"os\.walk\(|glob\.glob\(", r"\bfoo|bar", r"foo|\w+", r"foo\wbar|baz",
        r"a\|b|cd",
    ] + _distinct_content_patterns()


# ---------------------------------------------------------------------------
# Behavior 1 -- top-level alternation of plain literals.
# ---------------------------------------------------------------------------

def test_b1_top_level_alternation_yields_one_lowercased_member_per_alternative():
    assert checks.required_literals("(?i)(budget|allowance|quota)") == frozenset(
        {"budget", "allowance", "quota"})


@pytest.mark.parametrize(
    "flags", ["", "(?i)", "(?s)", "(?m)", "(?is)", "(?im)", "(?sm)", "(?ims)", "(?msi)"])
def test_b1_a_leading_inline_flag_group_is_stripped_before_the_split(flags):
    assert checks.required_literals(flags + "(budget|allowance|quota)") == frozenset(
        {"budget", "allowance", "quota"})


@pytest.mark.parametrize("shape", ["%s", "(%s)", "(?:%s)"])
def test_b1_at_most_one_fully_wrapping_group_is_stripped(shape):
    assert checks.required_literals(shape % "budget|allowance|quota") == frozenset(
        {"budget", "allowance", "quota"})


def test_b1_a_wrapper_that_does_not_enclose_the_whole_pattern_is_not_stripped():
    assert checks.required_literals("(foo)|(bar)") == frozenset({"foo", "bar"})


# ---------------------------------------------------------------------------
# Behavior 2 -- escapes.
# ---------------------------------------------------------------------------

def test_b2_escaped_punctuation_contributes_its_literal_character():
    assert checks.required_literals(r"os\.walk\(|glob\.glob\(") == frozenset(
        {"os.walk(", "glob.glob("})


@pytest.mark.parametrize("ch", PUNCT_ESCAPES)
def test_b2_every_whitelisted_punctuation_escape_contributes_itself(ch):
    got = checks.required_literals("a\\" + ch + "z|qq")
    assert got is not None, ch
    assert ("a" + ch + "z") in got, (ch, got)


@pytest.mark.parametrize(
    "esc", [r"\b", r"\B", r"\w", r"\W", r"\d", r"\D", r"\s", r"\S", r"\A", r"\Z", r"\1"])
def test_b2_an_alternative_opening_with_a_class_or_assertion_escape_has_no_literal(esc):
    assert checks.required_literals(esc + "foo|bar") is None


def test_b2_a_class_escape_ends_a_run_without_voiding_the_prefix_before_it():
    assert checks.required_literals(r"foo\wbar|baz") == frozenset({"foo", "baz"})


# ---------------------------------------------------------------------------
# Behavior 3 -- the run stops at a metacharacter; the split ignores a class pipe.
# ---------------------------------------------------------------------------

def test_b3_run_stops_at_the_first_metacharacter_and_the_split_skips_a_class_pipe():
    assert checks.required_literals("a[|]b|cd") == frozenset({"a", "cd"})


def test_b3_an_escaped_pipe_is_not_a_split_point():
    assert checks.required_literals(r"a\|b|cd") == frozenset({"a|b", "cd"})


# ---------------------------------------------------------------------------
# Behavior 4 -- an optional last character is dropped.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pattern,expected", [
    ("foobar?|baz", frozenset({"fooba", "baz"})),
    ("ab{0,3}c|de", frozenset({"a", "de"})),
    ("foobar*|baz", frozenset({"fooba", "baz"})),
])
def test_b4_a_run_whose_last_character_may_be_optional_loses_that_character(
        pattern, expected):
    assert checks.required_literals(pattern) == expected


def test_b4_a_plus_quantifier_keeps_the_character_it_repeats():
    assert checks.required_literals("foo+|bar") == frozenset({"foo", "bar"})


@pytest.mark.parametrize("pattern", ["a?bc|de", "x{2}y|z", "a*bc|de"])
def test_b4_when_dropping_empties_the_run_the_whole_pattern_is_unprovable(pattern):
    assert checks.required_literals(pattern) is None


# ---------------------------------------------------------------------------
# Behavior 5 -- one unprovable alternative voids the pattern; never the empty set.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", ["foo|", r"foo|\w+", "", "?"])
def test_b5_one_alternative_without_a_mandatory_literal_voids_the_whole_pattern(pattern):
    assert checks.required_literals(pattern) is None


def test_b5_the_empty_frozenset_is_never_returned():
    corpus = _every_pattern_this_file_uses()
    assert corpus, "vacuous corpus"
    for pattern in corpus:
        got = checks.required_literals(pattern)
        assert got is None or (isinstance(got, frozenset) and got), repr(pattern)


# ---------------------------------------------------------------------------
# Behavior 6 -- lowercasing, and the docstring that justifies it.
# ---------------------------------------------------------------------------

def test_b6_case_is_folded_to_lower():
    assert checks.required_literals("Foo|BAR") == frozenset({"foo", "bar"})


def test_b6_every_member_of_every_returned_set_is_already_lowercase():
    proved = 0
    for pattern in _every_pattern_this_file_uses():
        got = checks.required_literals(pattern)
        if got is None:
            continue
        proved += 1
        for member in got:
            assert member == member.lower(), (pattern, member)
    assert proved > 0, "no pattern proved a literal, so nothing was checked"


def test_b6_the_docstring_publishes_the_guarantee_the_whitelist_and_the_direction():
    doc = " ".join((checks.required_literals.__doc__ or "").split())
    assert GUARANTEE in doc
    assert " ".join(PUNCT_ESCAPES) in doc
    assert "sound in the REJECTION direction" in doc
    assert "`text.lower()`" in doc
    assert "can never reject a file the regex would have matched" in doc
    assert "never `frozenset()`" in doc


# ---------------------------------------------------------------------------
# Behavior 7 -- totality.
# ---------------------------------------------------------------------------

def test_b7_the_committed_adversarial_list_holds_the_inputs_the_spec_names():
    assert set(SPEC_REQUIRED_ADVERSARIAL) <= set(ADVERSARIAL)
    assert any(len(pattern) == 4000 for pattern in ADVERSARIAL)


@pytest.mark.parametrize("pattern", ADVERSARIAL)
def test_b7_no_adversarial_input_raises(pattern):
    got = checks.required_literals(pattern)
    assert got is None or isinstance(got, frozenset)
    assert got is None or got


def test_b7_no_live_register_pattern_raises_or_returns_the_empty_set():
    patterns = _distinct_content_patterns()
    assert patterns, "the live register exposed no content pattern to probe"
    for pattern in patterns:
        got = checks.required_literals(pattern)
        assert got is None or (isinstance(got, frozenset) and got), repr(pattern)


# ---------------------------------------------------------------------------
# Behavior 8 -- differential soundness over real patterns and real text, two-sided.
# ---------------------------------------------------------------------------

def _probe(literals_for):
    """Run the soundness probe with `literals_for` as the literal source.

    Returns `(violations, reached)`: the `(pattern, path)` pairs where the compiled
    pattern MATCHED a file but no proved literal was present in its lowercased text,
    and how many times the "matched" branch was reached at all. `reached` is what makes
    an empty violation list mean something.
    """
    violations, reached = [], 0
    texts = _tracked_src_texts()
    for pattern in _distinct_content_patterns():
        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error:
            continue
        literals = literals_for(pattern)
        if literals is None:
            continue
        for rel, text in texts:
            if regex.search(text) is None:
                continue
            reached += 1
            lowered = text.lower()
            if not any(member in lowered for member in literals):
                violations.append((pattern, rel))
    return violations, reached


def _impossible_literal_mutant(pattern):
    """Sound extractor, then the literal replaced by one no file can contain."""
    real = checks.required_literals(pattern)
    return None if real is None else frozenset({IMPOSSIBLE_LITERAL})


def _empty_for_unprovable_mutant(pattern):
    """`None` treated AS COVERED, by the empty set -- the failure behavior 5 forbids."""
    real = checks.required_literals(pattern)
    return frozenset() if real is None else real


def test_b8_the_probe_reaches_the_matched_branch_so_zero_violations_means_something():
    _, reached = _probe(checks.required_literals)
    assert reached > 0, "no proved pattern matched any tracked src file"


def test_b8_no_proved_literal_is_ever_absent_from_a_file_its_pattern_matches():
    violations, _ = _probe(checks.required_literals)
    assert violations == []


def test_b8_the_probe_detects_an_unsound_literal():
    violations, _ = _probe(_impossible_literal_mutant)
    assert violations, "the probe cannot see an unsound literal, so it proves nothing"


def test_b8_treating_an_unprovable_pattern_as_covered_is_detected_as_a_violation():
    violations, _ = _probe(_empty_for_unprovable_mutant)
    assert violations, "the probe cannot see `None` being treated as covered"


def test_b8_the_live_register_holds_both_a_proved_and_an_unprovable_pattern():
    results = [checks.required_literals(p) for p in _distinct_content_patterns()]
    assert any(r is not None for r in results)
    assert any(r is None for r in results)


# ---------------------------------------------------------------------------
# Behavior 9 -- dormancy.
# ---------------------------------------------------------------------------

def _src_modules():
    return sorted(SRC_DIR.glob("*.py"))


def _callee_name(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_b9_only_checks_names_the_extractor_anywhere_under_src():
    modules = _src_modules()
    assert modules, "no module found to census"
    naming = [p.name for p in modules
              if "required_literals" in p.read_text(encoding="utf-8")]
    assert naming == ["checks.py"]


def test_b9_checks_defines_the_extractor_and_calls_it_once_through_the_module_global():
    """Iteration 93 pinned `calls == []` to hold the extractor DORMANT for one bite.
    Iteration 99 ships the single call site, so the pin INVERTS rather than retires:
    the count still forbids a SECOND caller, and the bare-`ast.Name` callee pins the
    late-bound module-global lookup that every substitution test depends on -- a
    `checks.required_literals(...)` attribute call or an aliased import would break
    that seam while leaving every other assertion in this module green.
    """
    tree = ast.parse((SRC_DIR / "checks.py").read_text(encoding="utf-8"))
    defined = [n.name for n in tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert "required_literals" in defined
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and _callee_name(n) == "required_literals"]
    assert len(calls) == 1, [n.lineno for n in calls]
    assert isinstance(calls[0].func, ast.Name), ast.dump(calls[0].func)


def test_b9_the_public_function_surface_of_checks_grew_by_exactly_the_extractor():
    tree = ast.parse((SRC_DIR / "checks.py").read_text(encoding="utf-8"))
    public = sorted(n.name for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not n.name.startswith("_"))
    assert public == PUBLIC_CHECKS_FUNCTIONS


def test_b9_the_extractor_is_reachable_on_the_public_module_and_is_callable():
    assert callable(checks.required_literals)


def test_b9_every_shipped_verb_still_answers_with_a_document_ending_in_one_newline(
        tmp_path, capsys):
    old, new = tmp_path / "old", tmp_path / "new"
    _write_register(old, [_record("GAP-001", check_id="CHK-001")])
    _write_register(new, [_record("GAP-001", check_id="CHK-001"),
                          _record("GAP-002", check_id="CHK-002")])
    target = _target(new)
    invocations = [
        ["taxonomy"],
        ["validate", str(new)],
        ["list", str(new)],
        ["report", str(new)],
        ["show", "GAP-001", str(new)],
        ["prd", str(new)],
        ["diff", str(old), str(new)],
        ["scan", str(target), "--gaps", str(new)],
        ["scan", str(target), "--gaps", str(new), "--json"],
    ]
    assert {argv[0] for argv in invocations} == set(SHIPPED_VERBS)
    for argv in invocations:
        assert main(argv) == 0, argv
        captured = capsys.readouterr()
        assert captured.err == "", argv
        assert captured.out.strip(), argv
        assert captured.out.endswith("\n"), argv
        assert not captured.out.endswith("\n\n"), argv
