"""Iteration 370 behaviors: `checks._folded_fast_path` accepts three more
case-insensitive shapes by proven-equivalent rewriting -- uppercase letters inside
a class, a whole-span scoped `(?i:...)`, and doubled leading flag groups.

ISOLATION: black-box, and the contract is honored.  Nothing here read `src/`, any
`git diff`, or the engineer's or reviewer's notes.  Every expectation comes from
`pm.md`'s Expected Behaviors 1-10, from other modules under `tests/` (readable by
contract), or from RUNNING the product.

The oracle for every behavior is the spec's guarantee: when the classifier returns
`q` for `p`, then for every ASCII text `t` the spans of `re.compile(p, re.M)` over
`t` equal the spans of `re.compile(q, re.M)` over `t.lower()`; otherwise it returns
`None`.  `_differential` below is that oracle as a reusable helper, and behavior
10 proves it can go red by swapping deliberately unsound classifiers in.

Costs, as COUNTS: TWO whole-repo self-scans (behavior 9, `scan . --json`, the
live classifier vs the `lambda p: None` arm), four scans of a small synthetic
target in `tmp_path`, and EIGHT regex-only chunks of the register-wide span
differential over the repo's own ASCII `src/` and `tests/` files.  Offline,
deterministic, no network.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import random
import re

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CHUNKS = 8

#: The accepted count the spec measured at the pre-change head; behavior 8 asks
#: for at least 240 now (the prototype reached 248).
HEAD_ACCEPTED = 233
MIN_ACCEPTED = 240


#: The real classifier, captured at import so a monkeypatched variant can wrap it.
ORIGINAL = checks._folded_fast_path


def f(pattern: str):
    return checks._folded_fast_path(pattern)


def _register_patterns() -> list[str]:
    """Every distinct `pattern` string anywhere in the committed register."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            value = node.get("pattern")
            if isinstance(value, str):
                found.add(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for record in sorted(GAPS.glob("*.json")):
        walk(json.loads(record.read_text(encoding="utf-8")))
    return sorted(found)


def _spans(pattern: str, text: str) -> list[tuple[int, int]]:
    return [m.span() for m in re.compile(pattern, re.MULTILINE).finditer(text)]


def _differential(classifier, patterns, texts) -> list[str]:
    """The behavior 7 oracle: every pattern `classifier` accepts must give the
    raw pattern's span list on every text, run against the lowered text.  Returns
    one line per mismatch (empty list == sound on this corpus)."""
    bad = []
    for p in patterns:
        q = classifier(p)
        if q is None:
            continue
        raw = re.compile(p, re.MULTILINE)
        folded = re.compile(q, re.MULTILINE)
        for name, text in texts:
            a = [m.span() for m in raw.finditer(text)]
            b = [m.span() for m in folded.finditer(text.lower())]
            if a != b:
                bad.append(f"{p!r} -> {q!r} on {name}: {a[:3]} vs {b[:3]}")
    return bad


# --- synthetic mixed-case corpus that exercises each new shape -------------

SYNTHETIC = (
    ("otel", "OTEL_EXPORTER_X otel_x Otel_Abc_X OTEL_ x\n"),
    ("flags", "-r -R -f -F -rf -x\n"),
    ("env", "MY_ENV my_env Path_Env ENVX _env\n"),
    ("ranges", "a A z Z m M _ [ ] ^ ` @ { ~ 0 9 - / . ,\n"),
    ("scoped", "Foo FOO foo BAR bar Bar pass_rate PASSRATE Accuracy\n"),
    ("ab", "ab AB aB Ab xab XAB\n"),
    ("multi", "Foo\nbar\nFOO\n  foo bar\nA\nb\n"),
    ("dots", "a\nb aXb A.B a b\n"),
)


def _random_texts(n: int = 400, seed: int = 370) -> list[tuple[str, str]]:
    rng = random.Random(seed)
    alphabet = "aAbBfFrRxXzZoOtTeElL_-[]()^@`{~09 \n.\\/"
    return [(f"rand{i}", "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 40))))
            for i in range(n)]


SYNTHETIC_TEXTS = list(SYNTHETIC) + _random_texts()


# --- behavior 1: uppercase letter inside a class is lowercased ---------------

B1_ACCEPT = (
    (r"(?i)[A-Z]x", r"[a-z]x"),
    (r"(?i)[aB]", r"[ab]"),
    (r"(?i)[a-fA]", r"[a-fa]"),
    (r"(?i)OTEL_[A-Z_]*X", r"otel_[a-z_]*x"),
    (r"(?i)-[rRf]", r"-[rrf]"),
    (r"(?i)[A-Za-z_]*ENV", r"[a-za-z_]*env"),
    (r"(?i)[^A-Z]", r"[^a-z]"),
)


@pytest.mark.parametrize(("pattern", "expected"), B1_ACCEPT)
def test_b1_uppercase_in_class_lowercased(pattern: str, expected: str):
    assert f(pattern) == expected


@pytest.mark.parametrize(("pattern", "expected"), B1_ACCEPT)
def test_b1_rewrite_is_span_equal_on_mixed_case(pattern: str, expected: str):
    assert _differential(f, [pattern], SYNTHETIC_TEXTS) == []


# --- behavior 2: straddling ranges, unterminated classes, upper escapes ------

B2_REFUSE = (
    r"(?i)[@-_]", r"(?i)[!-~]", r"(?i)[0-z]", r"(?i)[A-z]", r"(?i)[A-f]",
    r"(?i)[a-Z]", r"(?i)[\--/]", r"(?i)[A-Z", r"(?i)x[ab", r"(?i)[\S]",
    r"(?i)[\s\S]",
)


@pytest.mark.parametrize("pattern", B2_REFUSE)
def test_b2_straddling_unterminated_and_escape_classes_refused(pattern: str):
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


@pytest.mark.parametrize("pattern", [r"(?i)[@-_]", r"(?i)[A-z]", r"(?i)[\S]"])
def test_b2_refusal_is_load_bearing(pattern: str):
    """Each refused class has a witness where the obvious lowercased rewrite would
    change the spans, so the refusal is not merely conservative."""
    naive = re.sub(r"\(\?i\)", "", pattern, count=1).lower()
    texts = [("w", "A a _ [ ` Z z s S \t\n")]
    assert _spans(pattern, texts[0][1]) != _spans(naive, texts[0][1].lower())
    assert f(pattern) is None


# --- behavior 3: whole-span scoped (?i:...) ----------------------------------

@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?i:Foo|bar)", r"foo|bar"),
    (r"(?i:pass_?rate|accuracy)", r"pass_?rate|accuracy"),
    (r"(?is:a.b)", r"(?s)a.b"),
])
def test_b3_whole_span_scoped_group_unwrapped(pattern: str, expected: str):
    assert f(pattern) == expected
    assert _differential(f, [pattern], SYNTHETIC_TEXTS) == []


@pytest.mark.parametrize("pattern", [
    r"(?i:a\)b)", r"(?i:[)]b)", r"(?i:a(?:b|c))", r"(?i:\(x)",
])
def test_b3_escaped_and_class_parens_do_not_end_the_group(pattern: str):
    """Paren matching skips `\\)` and characters inside a class; whatever comes
    back must be sound (accepted ones must pass the differential)."""
    got = f(pattern)
    if got is not None:
        assert _differential(f, [pattern], SYNTHETIC_TEXTS + [("p", "a)b A)B )b (x (X abc ABC")]) == []


def test_b3_escaped_paren_group_is_accepted():
    assert f(r"(?i:a\)b)") == r"a\)b"


# --- behavior 4: non-whole-span scoped groups and flag-OFF stay refused ------

@pytest.mark.parametrize("pattern", [
    r"(?i:a)b", r"(?i:a)|(b)", r"(?i:a)+", r"(?i:a)(?i:b)", r"x(?i:a)",
    r"(?i:a(?-i:b))", r"(?-i:a)", r"(?i-s:a)", r"(?i:a(?s-i:b))",
])
def test_b4_partial_scoped_and_flag_off_refused(pattern: str):
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


def test_b4_partial_scope_refusal_is_load_bearing():
    """`(?i:a)b` leaves `b` case-sensitive: unwrapping it would match `AB`."""
    assert _spans(r"(?i:a)b", "AB") == []
    assert _spans(r"ab", "AB".lower()) == [(0, 2)]


# --- behavior 5: doubled leading flag groups merged ----------------------------

@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?is)(?i)Foo", r"(?s)foo"),
    (r"(?i)(?m)X", r"(?m)x"),
])
def test_b5_doubled_flag_groups_merged(pattern: str, expected: str):
    assert f(pattern) == expected
    assert _differential(f, [pattern], SYNTHETIC_TEXTS) == []


def test_b5_merged_set_without_i_refused():
    assert f(r"(?m)(?s)x") is None


# --- behavior 6: previous rewrites and refusals hold ---------------------------

@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?i)x", "x"), (r"(?is)x", "(?s)x"), (r"(?im)x", "(?m)x"), (r"(?si)x", "(?s)x"),
    (r"(?i)os\.walk\(", r"os\.walk\("),
    (r"(?i)MaxTurnsExceeded", "maxturnsexceeded"),
    (r"(?is)OTEL_\w+", r"(?s)otel_\w+"),
    (r"(?im)^Import\b", r"(?m)^import\b"),
    (r"(?i)[a-f]+", "[a-f]+"),
    (r"(?i)(?:x|y)", "(?:x|y)"),
])
def test_b6_previous_rewrites_unchanged(pattern: str, expected: str):
    assert f(pattern) == expected


@pytest.mark.parametrize("pattern", [
    r"(?i)\x4a", r"(?i)\u004a", r"(?i)\U0000004a", r"(?i)\112",
    r"(?i)\N{LATIN CAPITAL LETTER J}", r"(?I)foo", r"(?ix)foo", r"(?ai)foo",
    r"x(?i)foo", r" (?i)foo", r"(?m)foo", r"(?i)a(?-i:b)", "(?i)caf\u00e9",
    "(?i)\u017fecret", r"foo", r"(?i)\S+end",
])
def test_b6_previous_refusals_hold(pattern: str):
    assert f(pattern) is None, f"{pattern!r} accepted as {f(pattern)!r}"


def _flags_and_body(p: str) -> tuple[str, str]:
    """Flag letters and body of an accepted pattern, parsed without the classifier:
    leading `(?flags)` groups merge first-seen; failing those, one whole-span
    `(?flags:...)`."""
    letters, rest = "", p
    while (head := re.match(r"\(\?([ims]+)\)", rest)) is not None:
        letters += "".join(ch for ch in head.group(1) if ch not in letters)
        rest = rest[head.end():]
    if letters:
        return letters, rest
    scoped = re.match(r"\(\?([ims]+):", p)
    assert scoped is not None and p.endswith(")"), p
    return scoped.group(1), p[scoped.end():-1]


def test_b6_every_accepted_live_rewrite_is_merged_flags_plus_lowered_body():
    bad = []
    for p in _register_patterns():
        got = f(p)
        if got is None:
            continue
        letters, body = _flags_and_body(p)
        if "i" not in letters:
            bad.append((p, got, "no i"))
            continue
        flags = letters.replace("i", "")
        if got != (f"(?{flags})" if flags else "") + body.lower():
            bad.append((p, got))
    assert bad == [], bad[:3]


def test_b6_docstring_describes_the_new_rules():
    doc = checks._folded_fast_path.__doc__ or ""
    assert "(?i:" in doc, "docstring does not mention the whole-span scoped rule"


# --- behavior 7: differential soundness over the live register -----------------

@pytest.fixture(scope="module")
def repo_ascii_texts() -> list[tuple[str, str]]:
    out = []
    for top in ("src", "tests"):
        for path in sorted((REPO / top).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if text.isascii():
                out.append((str(path.relative_to(REPO)), text))
    assert len(out) > 100, len(out)
    return out + SYNTHETIC_TEXTS


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_b7_live_register_span_differential(chunk: int, repo_ascii_texts):
    accepted = [p for p in _register_patterns() if f(p) is not None][chunk::CHUNKS]
    assert accepted, f"chunk {chunk} is empty"
    bad = _differential(f, accepted, repo_ascii_texts)
    assert bad == [], f"{len(bad)} divergence(s); first 3: {bad[:3]}"


def test_b7_differential_is_not_vacuous(repo_ascii_texts):
    """At least one new-shape live pattern actually MATCHES something in the corpus,
    so span equality is exercised on non-empty span lists."""
    hits = 0
    for p in _register_patterns():
        if f(p) is not None and _NEW_SHAPE(p) and any(_spans(p, t) for _, t in repo_ascii_texts):
            hits += 1
    assert hits >= 1, hits


# --- behavior 8: more patterns accepted ------------------------------------------

def _class_letters(body: str) -> list[str]:
    """Unescaped characters inside every character class of `body`, lexed
    test-locally: outside a class `\\x` is skipped; inside, a leading `^` and a
    first `]` are literal, `\\x` is skipped, and `]` closes."""
    out, i, n = [], 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "\\":
            i += 2
            continue
        if ch != "[":
            i += 1
            continue
        i += 1
        if i < n and body[i] == "^":
            i += 1
        first = True
        while i < n and (body[i] != "]" or first):
            if body[i] == "\\":
                i += 2
            else:
                out.append(body[i])
                i += 1
            first = False
        i += 1
    return out


def _upper_in_class(p: str) -> bool:
    _, body = _flags_and_body(p)
    return any("A" <= c <= "Z" for c in _class_letters(body))


def _whole_span(p: str) -> bool:
    return re.match(r"\(\?[ims]+:", p) is not None


def _doubled(p: str) -> bool:
    return re.match(r"\(\?[ims]+\)\(\?[ims]+\)", p) is not None


def _NEW_SHAPE(p: str) -> bool:
    return _upper_in_class(p) or _whole_span(p) or _doubled(p)


def test_b8_accepted_count_grew():
    patterns = _register_patterns()
    accepted = [p for p in patterns if f(p) is not None]
    print(f"\n[iter370 b8] {len(accepted)} accepted / {len(patterns)} distinct")
    assert len(accepted) >= MIN_ACCEPTED > HEAD_ACCEPTED, len(accepted)


@pytest.mark.parametrize("shape", ["upper_in_class", "whole_span", "doubled"])
def test_b8_each_new_shape_has_a_live_acceptance(shape: str):
    pred = {"upper_in_class": _upper_in_class, "whole_span": _whole_span,
            "doubled": _doubled}[shape]
    hits = [p for p in _register_patterns() if f(p) is not None and pred(p)]
    assert hits, f"no accepted live pattern of shape {shape}"


# --- behavior 9: scan output byte-identity ----------------------------------------

def _scan(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue()


def _two_arms(argv: list[str], cwd: pathlib.Path):
    """Run `argv` with the classifier forced to `None`, then with the live one; each
    arm is wrapped in a call counter so a cache that bypassed the seam is caught."""
    original = checks._folded_fast_path
    calls = {"stub": 0, "live": 0, "accepted": 0}

    def stub(p):
        calls["stub"] += 1
        return None

    def live(p):
        calls["live"] += 1
        r = original(p)
        if r is not None:
            calls["accepted"] += 1
        return r

    mp = pytest.MonkeyPatch()
    old = os.getcwd()
    try:
        os.chdir(cwd)
        mp.setattr(checks, "_folded_fast_path", stub, raising=True)
        stubbed = _scan(argv)
        mp.setattr(checks, "_folded_fast_path", live, raising=True)
        real = _scan(argv)
    finally:
        mp.undo()
        os.chdir(old)
    return real, stubbed, calls


@pytest.fixture(scope="module")
def self_scan_json():
    return _two_arms(["scan", ".", "--gaps", str(GAPS), "--json"], REPO)


def test_b9_self_scan_json_byte_identical(self_scan_json):
    (rcode, rdoc), (scode, sdoc), calls = self_scan_json
    assert calls["stub"] > 0 and calls["live"] > 0, calls
    assert calls["accepted"] > 0, calls
    assert rcode == scode, (rcode, scode)
    assert rdoc == sdoc, "self-scan --json bytes moved under the fast path"
    assert rdoc.endswith("\n") and not rdoc.endswith("\n\n")
    json.loads(rdoc)


SYNTHETIC_TARGET = {
    "pkg/telemetry.py": "import os\nOTEL_EXPORTER_OTLP_ENDPOINT = os.environ['OTEL_X']\n",
    "pkg/runner.py": "def Run():\n    PASS_RATE = 0.5\n    return Accuracy\n",
    "pkg/shell.sh": "rm -Rf build\nMY_APP_ENV=1\n",
    "README.md": "# Demo\nFoo Bar MaxTurnsExceeded VectorStore\n",
}


@pytest.fixture(scope="module", params=["markdown", "json"])
def synthetic_scan(request, tmp_path_factory):
    root = tmp_path_factory.mktemp("iter370target")
    for rel, text in SYNTHETIC_TARGET.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    argv = ["scan", str(root), "--gaps", str(GAPS)]
    if request.param == "json":
        argv.append("--json")
    return request.param, _two_arms(argv, REPO)


def test_b9_synthetic_target_scan_byte_identical(synthetic_scan):
    kind, ((rcode, rdoc), (scode, sdoc), calls) = synthetic_scan
    assert calls["stub"] > 0 and calls["accepted"] > 0, calls
    assert rcode == scode
    assert rdoc == sdoc, f"{kind} scan of the synthetic target moved"
    assert rdoc.endswith("\n") and not rdoc.endswith("\n\n")


# --- behavior 10: mutation guard ---------------------------------------------------

MUTATION_PATTERNS = (r"(?i)foo\S+", r"(?i:a)b", r"(?i)x[A-z]", r"(?i)[\s\S]a")


def _unsound_escape_lowering(p: str):
    """Lowercases an uppercase escape (`\\S` -> `\\s`) before classifying."""
    return ORIGINAL(p.replace("\\S", "\\s"))


def _unsound_partial_unwrap(p: str):
    """Treats a LEADING `(?i:...)` as global even when it does not span the pattern."""
    m = re.match(r"\(\?i:([^()]*)\)(.*)\Z", p, re.S)
    if m is not None:
        return (m.group(1) + m.group(2)).lower()
    return ORIGINAL(p)


def _unsound_straddle(p: str):
    """Accepts a straddling `A-z` range by lowercasing it."""
    return ORIGINAL(p.replace("[A-z]", "[A-Z]"))


@pytest.mark.parametrize("variant", [
    _unsound_escape_lowering, _unsound_partial_unwrap, _unsound_straddle,
], ids=["escape", "partial_unwrap", "straddle"])
def test_b10_oracle_goes_red_on_unsound_variant(variant, monkeypatch):
    monkeypatch.setattr(checks, "_folded_fast_path", variant, raising=True)
    patterns = _register_patterns() + list(MUTATION_PATTERNS)
    assert _differential(checks._folded_fast_path, patterns, SYNTHETIC_TEXTS), (
        "the differential stayed green on a deliberately unsound classifier")


def test_b10_oracle_green_on_real_classifier_over_mutation_patterns():
    assert _differential(f, list(MUTATION_PATTERNS), SYNTHETIC_TEXTS) == []


def test_no_absolute_machine_path_in_this_module():
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for needle in ("/" + "Users" + "/", "/" + "home" + "/", "C" + ":\\"):
        assert needle not in source, needle
