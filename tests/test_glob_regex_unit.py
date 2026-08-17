"""Unit tests for the internal glob->regex translation in `checks`.

Scope: the pure helper only. The differential proof that tracked-path matching
equals the old filesystem walk over the committed register is a BEHAVIOR test
and belongs to the test engineer.

Every semantic claim gets a must-match AND a must-not-match case in the same
test. A one-sided assertion cannot tell a working matcher from one that matches
everything, and a matcher that matches everything is exactly how a scan starts
reporting findings that are not there.
"""

from __future__ import annotations

import warnings

import pytest

from agent_gap_radar.checks import _component_regex, _glob_regex


def matches(pattern: str, rel: str) -> bool:
    return bool(_glob_regex(pattern).match(rel))


def test_star_does_not_cross_a_separator():
    """The bug `fnmatch.translate` would have shipped: `*` rendered as `.*`.

    `.` matches `/`, so `**/*eval*.json` would match `evals/basic.json` whose
    own filename contains no "eval". Measured: 2 of the register's 41 patterns.
    """
    assert matches("**/*eval*.json", "a_eval_b.json")
    assert matches("**/*eval*.json", "dir/deep/my_eval.json")
    assert not matches("**/*eval*.json", "evals/basic.json")


def test_trailing_double_star_matches_files_at_or_below():
    """Interpreter-independent by construction.

    `Path.glob("evals/**")` yields directories only on 3.12 and files as well
    on 3.13, so every register pattern ending in `/**` silently matched NOTHING
    on 3.12. A scan of one commit must return one answer.
    """
    assert matches("evals/**", "evals/basic.json")
    assert matches("evals/**", "evals/deep/nested/case.yaml")
    assert not matches("evals/**", "eval/legacy.py")
    assert not matches("evals/**", "notevals/x.py")


def test_interior_double_star_matches_zero_or_more_directories():
    assert matches("**/*.py", "top.py"), "zero directories must match"
    assert matches("**/*.py", "a/b/c.py")
    assert matches("**/evals/**", "evals/basic.json"), "zero directories"
    assert matches("**/evals/**", "pkg/evals/x.py")
    assert not matches("**/evals/**", "pkg/evaluations/x.py")


def test_matching_is_case_sensitive_on_the_tracked_path():
    """A verdict must not depend on whose filesystem ran the scan.

    `Path.glob` inherits the filesystem's case folding, so on macOS a pattern
    of `agents.md` matches a tracked `AGENTS.md` and on Linux it does not.
    The tracked path is what git recorded, so that is what is matched.
    """
    assert matches("AGENTS.md", "AGENTS.md")
    assert not matches("AGENTS.md", "agents.md")
    assert not matches("agents.md", "AGENTS.md")


def test_the_whole_relative_path_must_match():
    assert matches("src/app.py", "src/app.py")
    assert not matches("src/app.py", "x/src/app.py"), "unanchored prefix"
    assert not matches("src/app.py", "src/app.pyc"), "unanchored suffix"


def test_dot_is_literal_not_any_character():
    assert matches("**/*.py", "mod.py")
    assert not matches("**/*.py", "modxpy")


def test_regex_metacharacters_in_a_pattern_are_escaped():
    """A glob is not a regex; `+`, `(` and `$` are ordinary filename bytes."""
    assert matches("a+b.py", "a+b.py")
    assert not matches("a+b.py", "aab.py"), "'+' leaked through as a quantifier"
    assert matches("f(1).py", "f(1).py")
    assert matches("cost$.txt", "cost$.txt")


def test_question_mark_matches_exactly_one_non_separator():
    assert matches("a?.py", "ab.py")
    assert not matches("a?.py", "abc.py")
    assert not matches("a?.py", "a.py")
    assert not matches("a/?.py", "a/b/c.py")


def test_character_class_and_negation():
    assert matches("[ab].py", "a.py")
    assert not matches("[ab].py", "c.py")
    assert matches("[!a].py", "b.py")
    assert not matches("[!a].py", "a.py")


def test_unterminated_character_class_is_a_literal_bracket():
    """A malformed glob matches a weird filename; it never raises.

    `a[b.py` has no closing bracket at all, so the `[` is emitted literally.
    The forms that DID raise before this fix (`[]]`, `[!]`, `[a-\\]`) are pinned
    in `test_malformed_character_class_never_raises` below -- a raise there did
    not degrade one check to UNKNOWN, it escaped `run_check` entirely and
    terminated the process.
    """
    assert matches("a[b.py", "a[b.py")
    assert not matches("a[b.py", "ab.py")


def test_closing_bracket_in_first_body_position_is_a_literal():
    """POSIX: a `]` right after `[` or `[!` is a class MEMBER, not the terminator.

    Searching for the first `]` from the body start instead built the empty
    class `[]`, which is not valid regex -- the crash this test guards.
    """
    assert matches("[]].py", "].py")
    assert not matches("[]].py", "a.py")
    assert matches("[]a].py", "].py")
    assert matches("[]a].py", "a.py")
    assert not matches("[]a].py", "b.py")
    assert matches("[!]a].py", "b.py"), "negated class with a literal ]"
    assert not matches("[!]a].py", "].py")


def test_class_body_is_escaped_not_spliced_raw():
    """Regex syntax must not leak out of a glob character class.

    Two concrete leaks the raw splice had: `[[]x` produced `[[]`, which emits
    `FutureWarning: Possible nested set` (this tool contracts that stderr
    carries `Error: ` lines only, so a warning there is a defect in itself);
    and because glob spells negation `!`, a `^` in the body is an ordinary
    member -- `[^a]` means "caret or a", which the raw splice inverted into
    "anything but a".
    """
    assert matches("[[]x", "[x")
    assert not matches("[[]x", "x")
    assert matches("[^a].py", "^.py")
    assert matches("[^a].py", "a.py")
    assert not matches("[^a].py", "b.py")
    assert matches("[a-c].py", "b.py"), "`-` still means range"
    assert not matches("[a-c].py", "d.py")


def test_malformed_character_class_never_raises():
    """A register is DATA that consumers write and share, so a broken class is
    reachable input, not a hypothetical.

    Measured on the pre-fix tree: `[]]`, `[!]` and `[a-\\]` raised
    `re.PatternError` out of `iter_files` and out of the CLI -- exit 1, a
    traceback on stderr, zero bytes of stdout -- which is none of the three
    things the contract promises (`Error: ` prefix, exit 2, stdout carries only
    the document). `re.error` is NOT a `ValueError`, so no upstream
    `except ValueError` caught it. The lenient reading matches nothing real.
    """
    for pattern in ("[]]", "[!]", "[a-\\]", "[", "[a-", "[!"):
        _glob_regex(pattern)  # must not raise
        assert not matches(pattern, "src/app.py"), pattern
        assert not matches(pattern, "README.md"), pattern


def test_translation_emits_no_warnings():
    """stderr is contractual, so a `FutureWarning` on the success path is a bug.

    Known-bad control for this assertion: before the body-escaping fix, `[[]x`
    raised `FutureWarning: Possible nested set at position 2` here.
    """
    _glob_regex.cache_clear()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning becomes a failure
        for pattern in ("[[]x", "[]]", "[!]", "[a-\\]", "**/*.py", "[!a].py"):
            _glob_regex(pattern)
    _glob_regex.cache_clear()


@pytest.mark.parametrize("part,expected", [
    ("*", "[^/]*"),
    ("?", "[^/]"),
    ("a.b", "a\\.b"),
    ("[!x]", "[^x]"),
])
def test_component_regex_fragments(part, expected):
    assert _component_regex(part) == expected


def test_translation_is_cached_by_pattern():
    """The cache is load-bearing, not decorative: a scan evaluates the same
    handful of register patterns against every tracked path, many times over."""
    assert _glob_regex("**/*.py") is _glob_regex("**/*.py")
