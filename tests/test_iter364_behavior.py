"""Iteration 364 behaviors: `checks._folded_fast_path` lexes the pattern body and
refuses by default.

ISOLATION: black-box, and the contract is honored.  Nothing here read `src/`, any
`git diff`, or the engineer's or reviewer's notes.  Every expectation comes from
`pm.md`'s Expected Behaviors 1-10, from other modules under `tests/` (readable by
contract), or from RUNNING the product.

Behavior 7 needs the classifier as it stood BEFORE this iteration.  The spec bars a
frozen-commit source arm, so the old rule is RE-STATED inline (`_old_rule`) from
the iteration-245 grammar the committed tests pin: a leading `(?[ims]+)` group that
carries an `i`, an ASCII body with no `A-Z` and no scoped flag-OFF group, and the
`i` stripped from the flag group.  The restatement is held to the literal count
the spec measured at the pre-change head (160 of 361), so a restatement that
drifted from the real old rule reds instead of silently comparing to itself.

Costs, as COUNTS: TWO whole-repo self-scans in one module fixture (behavior 10,
markdown) plus TWO more (`--json`), and EIGHT regex-only chunks of the
register-wide span oracle (behavior 9) over the frozen corpus iteration 245
already uses.  Offline, deterministic, no network; writes land in `tmp_path`.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main
from test_iter245_behavior import (
    FROZEN_COMMIT,
    FROZEN_DIR_NAME,
    _extract,
    _register_patterns,
)

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CHUNKS = 8

#: Measured by the PM at the pre-change head; pinned literally per behavior 7.
#: Re-baseline BOTH together if a later iteration grows the register.
OLD_ACCEPTED = 160
REGISTER_DISTINCT = 361


def f(pattern: str):
    return checks._folded_fast_path(pattern)


def _old_rule(pattern: str):
    """The pre-iteration classifier, re-stated from the iteration-245 grammar."""
    head = re.match(r"\(\?([ims]+)\)", pattern)
    if head is None or "i" not in head.group(1):
        return None
    body = pattern[head.end():]
    if not body.isascii() or re.search(r"[A-Z]", body):
        return None
    if re.search(r"\(\?[a-z]*-", body):
        return None
    flags = head.group(1).replace("i", "")
    return (f"(?{flags})" if flags else "") + body


def _spans(pattern: str, text: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.compile(pattern, re.MULTILINE).finditer(text)]


# --- behavior 1: holes closed ----------------------------------------------

#: The four measured pre-change counterexamples (pm.md table), plus the spec's
#: two siblings of the same escape family.
HOLES = (
    (r"(?i)\x4a", "J"),
    (r"(?i)\u004a", "J"),
    (r"(?i)\U0000004a", "J"),
    (r"(?i)\112", "J"),
    (r"(?i)\N{LATIN SMALL LETTER J}", "J"),
    (r"(?i)[@-_]", "a"),
)


@pytest.mark.parametrize(("pattern", "text"), HOLES)
def test_b1_hole_is_refused(pattern: str, text: str):
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


#: Inverting witnesses: the four pm.md counterexamples plus two siblings.  (The
#: spec's `\N{LATIN SMALL LETTER J}` is refused too, but names a LOWERCASE letter,
#: so it is not an inversion witness; the CAPITAL spelling is.)
INVERSIONS = (
    (r"(?i)\x4a", "J"),
    (r"(?i)\u004a", "J"),
    (r"(?i)\U0000004a", "J"),
    (r"(?i)\112", "J"),
    (r"(?i)\N{LATIN CAPITAL LETTER J}", "J"),
    (r"(?i)[@-_]", "a"),
)


@pytest.mark.parametrize(("pattern", "text"), INVERSIONS)
def test_b1_hole_raw_matches_so_a_fold_would_have_inverted(pattern: str, text: str):
    """Regression shape: the raw pattern MATCHES, and the naive folded rewrite (flag
    stripped, body untouched) MISSES on the lowered text -- the inverted verdict
    the refusal above prevents.
    """
    assert _spans(pattern, text) == [(0, 1)], "fixture: raw arm must match"
    naive = pattern[len("(?i)"):]
    assert _spans(naive, text.lower()) == [], "fixture: naive fold must miss"
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


@pytest.mark.parametrize("escape", [
    r"\x4a", r"\u004a", r"\U0000004a", r"\112", r"\N{LATIN SMALL LETTER J}",
    r"\0", r"\1", r"\7",
])
@pytest.mark.parametrize("where", ["outside", "inside"])
def test_b1_numeric_and_named_escapes_refused_everywhere(escape: str, where: str):
    body = f"x{escape}y" if where == "outside" else f"x[{escape}q]y"
    if escape == r"\1" and where == "outside":
        body = f"(a){escape}"
    pattern = "(?i)" + body
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


# --- behavior 2: class-range rule -------------------------------------------

@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?i)[a-f]+", "[a-f]+"),
    (r"(?i)[0-9_]", "[0-9_]"),
    (r"(?i)[-a]", "[-a]"),
    (r"(?i)[a-]", "[a-]"),
    (r"(?i)[^a-z0-9]", "[^a-z0-9]"),
])
def test_b2_class_accepted_verbatim(pattern: str, expected: str):
    assert f(pattern) == expected


@pytest.mark.parametrize("pattern", [
    r"(?i)[!-~]", r"(?i)[0-z]", r"(?i)[\--/]", r"(?i)[A-Z]", r"(?i)[aB]",
    r"(?i)[a-fA]", r"(?i)[a-z", r"(?i)x[ab", r"(?i)[@-_]",
])
def test_b2_class_refused(pattern: str):
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


# --- behavior 3: uppercase plain literals are lowercased ---------------------

@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?i)MaxTurnsExceeded", "maxturnsexceeded"),
    (r"(?i)VectorStore", "vectorstore"),
    (r"(?is)OTEL_\w+", r"(?s)otel_\w+"),
    (r"(?i)Foo\s+Bar", r"foo\s+bar"),
    (r"(?im)^Import\b", r"(?m)^import\b"),
])
def test_b3_uppercase_literals_lowercased_and_nothing_else(pattern: str, expected: str):
    assert f(pattern) == expected


# --- behavior 4: uppercase escapes are still refused --------------------------

@pytest.mark.parametrize("body", [
    r"\S+end", r"\B\W", r"pre\Zpost", r"\Astart", r"\D+", r"x\Ky",
    r"Foo\S", r"[\W]",
])
def test_b4_uppercase_escape_refused(body: str):
    assert f("(?i)" + body) is None, f"{body!r} accepted as {f('(?i)' + body)!r}"


# --- behavior 5: group extensions ------------------------------------------

@pytest.mark.parametrize("body", [
    r"(?:x|y)", r"a(?=b)", r"a(?!b)", r"(?<=a)b", r"(?<!a)b",
])
def test_b5_allowed_group_openers_pass_through(body: str):
    assert f("(?i)" + body) == body


@pytest.mark.parametrize("body", [
    r"(?P<Name>x)", r"(?P<name>x)", r"(?P<n>x)(?P=n)", r"(?#Comment)x",
    r"(?#comment)x", r"(?s:x)", r"(?m:x)", r"a(?-i:b)", r"a(?s-i:b)",
    r"a(?m-i:b)", r"a(?sm-i:b)", r"(?>x)",
])
def test_b5_other_group_extensions_refused(body: str):
    assert f("(?i)" + body) is None, f"{body!r} accepted as {f('(?i)' + body)!r}"


# --- behavior 6: existing guarantees unchanged ---------------------------------

@pytest.mark.parametrize("pattern", [
    r"(?I)foo", r"(?ix)foo", r"(?ai)foo", r"x(?i)foo", r" (?i)foo", r"(?m)foo",
    r"foo", "(?i)caf\u00e9", "(?i)\u017fecret",
])
def test_b6_flag_and_ascii_refusals_hold(pattern: str):
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?i)x", "x"), (r"(?is)x", "(?s)x"), (r"(?im)x", "(?m)x"), (r"(?si)x", "(?s)x"),
])
def test_b6_flag_rewrite_holds(pattern: str, expected: str):
    assert f(pattern) == expected


@pytest.mark.parametrize("body", [
    r"a\\b[^\]]+", r"(?:x|y)\d{2,}", r"\bword\b", r"[\t\n]+", r"a{1,3}?b*?c+?",
    r"os\.walk\(", r"while\s+true",
])
def test_b6_lowercase_bodies_returned_byte_for_byte(body: str):
    assert f("(?i)" + body) == body
    assert f("(?is)" + body) == "(?s)" + body


# --- behavior 7: no regression on the live register -------------------------

def test_b7_old_rule_restatement_matches_the_measured_head_count():
    patterns = _register_patterns()
    old = [p for p in patterns if _old_rule(p) is not None]
    assert len(patterns) == REGISTER_DISTINCT, len(patterns)
    assert len(old) == OLD_ACCEPTED, (
        f"the inline old rule accepts {len(old)}, the spec measured {OLD_ACCEPTED}")


def test_b7_every_old_accepted_pattern_keeps_its_exact_rewrite():
    changed = [(p, _old_rule(p), f(p)) for p in _register_patterns()
               if _old_rule(p) is not None and f(p) != _old_rule(p)]
    assert changed == [], f"{len(changed)} rewrite(s) moved; first 3: {changed[:3]}"


def test_b7_accepted_bodies_without_uppercase_are_untouched():
    moved = []
    for p in _register_patterns():
        got = f(p)
        if got is None:
            continue
        head = re.match(r"\(\?([ims]+)\)", p)
        assert head is not None and "i" in head.group(1), p
        body = p[head.end():]
        if re.search(r"[A-Z]", body):
            continue
        flags = head.group(1).replace("i", "")
        if got != (f"(?{flags})" if flags else "") + body:
            moved.append((p, got))
    assert moved == [], moved[:3]


# --- behavior 8: wider acceptance -----------------------------------------

def test_b8_at_least_225_live_patterns_accepted():
    patterns = _register_patterns()
    accepted = [p for p in patterns if f(p) is not None]
    print(f"\n[iter364 b8] {len(accepted)} accepted / {len(patterns)} distinct")
    assert len(accepted) >= 225, f"only {len(accepted)} of {len(patterns)} accepted"


def test_b8_every_accepted_rewrite_is_flag_strip_plus_lowercased_body():
    """Behavior 3's "nothing else in the body changes", over the live register:
    an accepted body can only hold uppercase as plain literals (escapes and
    classes with `A-Z` are refused), so the rewrite is exactly the stripped flag
    group plus `body.lower()`."""
    bad = []
    for p in _register_patterns():
        got = f(p)
        if got is None:
            continue
        head = re.match(r"\(\?([ims]+)\)", p)
        body = p[head.end():]
        flags = head.group(1).replace("i", "")
        if got != (f"(?{flags})" if flags else "") + body.lower():
            bad.append((p, got))
    assert bad == [], bad[:3]


# --- behavior 9: span equality -----------------------------------------------

@pytest.fixture(scope="module")
def frozen_texts(tmp_path_factory) -> list[tuple[str, str]]:
    root = _extract(FROZEN_COMMIT, tmp_path_factory.mktemp("frozen364") / FROZEN_DIR_NAME)
    out = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if text.isascii():
            out.append((str(path.relative_to(root)), text))
    assert len(out) > 100, len(out)
    return out


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_b9_span_equality_over_frozen_corpus(chunk: int, frozen_texts):
    accepted = [p for p in _register_patterns() if f(p) is not None][chunk::CHUNKS]
    assert accepted, f"chunk {chunk} is empty"
    bad = []
    for p in accepted:
        raw = re.compile(p, re.MULTILINE)
        folded = re.compile(f(p), re.MULTILINE)
        for name, text in frozen_texts:
            a = [m.span() for m in raw.finditer(text)]
            b = [m.span() for m in folded.finditer(text.lower())]
            if a != b:
                bad.append(f"{p!r} on {name}: {a[:3]} vs {b[:3]}")
    assert bad == [], f"{len(bad)} divergence(s); first 3: {bad[:3]}"


@pytest.mark.parametrize(("pattern", "text"), [
    (r"(?i)MaxTurnsExceeded", "raise MAXTURNSEXCEEDED; maxturnsexceeded MaxTurnsExceeded\n"),
    (r"(?i)Foo\s+Bar", "FOO bar foo  BAR\n"),
])
def test_b9_named_span_pairs(pattern: str, text: str):
    rewritten = f(pattern)
    assert rewritten is not None
    raw = _spans(pattern, text)
    assert len(raw) == 3 if "Max" in pattern else len(raw) == 2
    assert _spans(rewritten, text.lower()) == raw


# --- behavior 10: scan output byte-identical, real vs stubbed classifier -------

def _scan(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


@pytest.fixture(scope="module", params=["markdown", "json"])
def scan_pair(request):
    argv = ["scan", str(REPO), "--gaps", str(GAPS)]
    if request.param == "json":
        argv.append("--json")
    original = checks._folded_fast_path
    accepts = 0

    def counting(p):
        nonlocal accepts
        r = original(p)
        if r is not None:
            accepts += 1
        return r

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(checks, "_folded_fast_path", counting, raising=True)
        live = _scan(argv)
        mp.setattr(checks, "_folded_fast_path", lambda p: None, raising=True)
        stub = _scan(argv)
    finally:
        mp.undo()
    return request.param, live, stub, accepts


def test_b10_scan_bytes_identical_real_vs_stub(scan_pair):
    kind, (lcode, ldoc), (scode, sdoc), accepts = scan_pair
    assert accepts > 0, "the classifier never accepted during the live scan"
    assert lcode == scode == 0, (lcode, scode)
    assert ldoc == sdoc, f"{kind} scan bytes moved under the fast path"
    assert ldoc.endswith("\n") and not ldoc.endswith("\n\n")
    if kind == "json":
        json.loads(ldoc)


def test_no_absolute_machine_path_in_this_module():
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for needle in ("/" + "Users" + "/", "/" + "home" + "/", "C" + ":\\"):
        assert needle not in source, needle
