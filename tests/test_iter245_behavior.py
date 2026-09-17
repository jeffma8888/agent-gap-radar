"""Iteration 245 behaviors: `checks._folded_fast_path`, a case-insensitivity fast
path that runs a globally-`(?i)` pattern's FLAG-STRIPPED body over the already
memoised folded copy of an ASCII file -- specified as an EQUALITY, so the whole
module is an oracle for "zero published bytes moved".

ISOLATION: black-box, and the contract is honored.  Nothing here read `src/`, any
`git diff`, or the engineer's, reviewer's or fix-reviewer's notes.  Every
expectation comes from `pm.md`'s Expected Behaviors, from other modules under
`tests/` (readable by contract), or from RUNNING the product.

WHY A PINNED PRE-CHANGE COMMIT AND NOT `HEAD`.  Behavior 7 is an equality across a
change, so it needs the OTHER side of the change.  `HEAD` cannot be that side: the
instant this iteration's commit lands, `HEAD` becomes the post-change tree and the
comparison silently degrades to new-vs-new -- green forever, measuring nothing.  So
the pre-change tree is named by CONSTANT (`PRECHANGE_COMMIT`), the same convention
`tests/test_iter219_behavior.py` established, and materialised out of this repo's
own object store with `git archive`.  Old and new are selected purely by
`PYTHONPATH`, and each subprocess prints its resolved `cli.__file__` to stderr so
the provenance of every byte compared is in the transcript.

Costs, stated as COUNTS per `tools/scan_cost.py`'s doctrine: this module runs
exactly TWO whole-register scans of the 267-file frozen corpus (behavior 6 -- one
live arm through a pass-through wrapper, one arm with the classifier stubbed to
`None`; the pair IS the anti-vacuity oracle and no third scan is paid), EIGHT
regex-only chunks of the register-wide equality oracle (behavior 3 -- it compiles
patterns and never runs a scan), and EIGHT scan-free CLI subprocesses (behavior 7,
four surfaces times two implementations).  Everything else runs in `tmp_path`.

Offline, deterministic, no network.  The product repo is only READ; every write
lands in a pytest-managed temporary directory.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import json
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import Verdict, run_check
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"

#: The tree this iteration's change is measured AGAINST, pinned by sha rather than
#: read as `HEAD` -- see the module docstring.  This is the commit that was `HEAD`
#: while the spec was written (iteration 242's ship).
PRECHANGE_COMMIT = "4f66cc6"

#: The frozen corpus iteration 220 committed, reused verbatim so that behavior 3's
#: oracle and behavior 6's scans cannot become a function of this repo's own growth.
FROZEN_COMMIT = "0356b8b"

#: The document echoes its target's resolved BASE NAME, so the frozen tree is
#: extracted into a directory spelled exactly this way.
FROZEN_DIR_NAME = "agent-gap-radar"

#: Behavior 3's oracle is split into this many chunks so `-n auto --dist worksteal`
#: can spread ~41k (pattern, file) comparisons across workers instead of parking
#: them all in one serial test item.  Coverage is unaffected: chunk `k` takes
#: `patterns[k::CHUNKS]`, so the union of the chunks is every accepted pattern.
CHUNKS = 8

#: Scan-free surfaces over the LIVE register, for behavior 7's old-vs-new equality.
SURFACE_ARGV: tuple[tuple[str, ...], ...] = (
    ("report", "gaps"),
    ("list", "gaps"),
    ("list", "gaps", "--json"),
    ("validate", "gaps"),
)


# --- helpers ---------------------------------------------------------------

def _extract(commit: str, into: pathlib.Path, paths: tuple[str, ...] = ()) -> pathlib.Path:
    """`git archive <commit>` from this repo, extracted under `into`."""
    into.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", commit, *paths],
        capture_output=True, check=False)
    assert archive.returncode == 0, (
        f"`git archive {commit}` failed: "
        f"{archive.stderr.decode('utf-8', 'replace')[:400]!r}")
    extract = subprocess.run(["tar", "-x", "-C", str(into)],
                             input=archive.stdout, capture_output=True, check=False)
    assert extract.returncode == 0, (
        f"extracting {commit} failed: "
        f"{extract.stderr.decode('utf-8', 'replace')[:400]!r}")
    return into


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


def _accepted_patterns() -> list[str]:
    return [p for p in _register_patterns() if checks._folded_fast_path(p) is not None]


@pytest.fixture(scope="module")
def frozen_corpus(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("frozen") / FROZEN_DIR_NAME
    return _extract(FROZEN_COMMIT, root)


@pytest.fixture(scope="module")
def frozen_ascii_texts(frozen_corpus) -> list[tuple[str, str]]:
    """(relative path, text) for every decodable ASCII file of the frozen corpus."""
    out: list[tuple[str, str]] = []
    for path in sorted(frozen_corpus.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if text.isascii():
            out.append((str(path.relative_to(frozen_corpus)), text))
    return out


@pytest.fixture(scope="module")
def prechange_src(tmp_path_factory) -> pathlib.Path:
    root = _extract(PRECHANGE_COMMIT, tmp_path_factory.mktemp("prechange"), ("src",))
    return root / "src"


def _run_surface(argv: tuple[str, ...], src_root: pathlib.Path) -> tuple[int, bytes, str]:
    """Run one CLI surface out of process, with `src_root` first on `PYTHONPATH`.

    Returns (exit code, stdout BYTES, resolved `cli.__file__`).  The provenance
    line is what proves old and new were really different implementations.
    """
    program = (
        "import sys, json\n"
        "from agent_gap_radar import cli\n"
        "print(cli.__file__, file=sys.stderr)\n"
        "sys.exit(cli.main(json.loads(sys.argv[1])))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", program, json.dumps(list(argv))],
        cwd=str(REPO), capture_output=True, check=False,
        env={"PATH": "", "PYTHONPATH": str(src_root), "PYTHONHASHSEED": "0",
             "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8"})
    provenance = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    return proc.returncode, proc.stdout, provenance[0] if provenance else ""


def _materialise(root: pathlib.Path, tree: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in tree.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def _content_check(pattern: str) -> dict:
    return {
        "id": "CHK-999",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": pattern},
        "manual_question": "Does this project do the thing?",
        "rationale": "Fixture-only check; exists to observe the reported locations.",
    }


# --- behavior 1: eligibility is a two-sided decision over the pattern text --

def test_b1_classifier_is_published_as_a_module_global():
    """Behaviors 1 and 6: the routing decision is a module GLOBAL, so it is a seam."""
    assert "_folded_fast_path" in vars(checks), (
        "`_folded_fast_path` is not a module global of `checks`, so behavior 6's "
        "substitution seam does not exist")
    assert callable(checks._folded_fast_path)


def test_b7_the_public_surface_of_checks_did_not_grow():
    """Behavior 7, and the reason iteration 244 was reverted.

    Iteration 244's spec demanded a PUBLIC `folded_fast_path` while its acceptance
    criteria forbade re-baselining any committed expectation -- and `checks.py`'s
    public function surface is pinned by EQUALITY in two committed places, so that
    pair was unimplementable.  Iteration 245 spends one underscore instead: the
    classifier is PRIVATE, so the live census must equal the committed constant
    EXACTLY, with the new name absent from it.

    This is the inverse of the assertion this module carried at iteration 244; it is
    two-sided in the same way, because a classifier that leaked out as a public name
    reds the equality just as a removed public helper would.

    The census is imported inside the test, not at module scope, so a `sys.path`
    surprise degrades to one red item instead of a collection error for the module.
    """
    from test_iter93_behavior import PUBLIC_CHECKS_FUNCTIONS

    live = sorted(name for name, obj in vars(checks).items()
                  if not name.startswith("_") and inspect.isfunction(obj)
                  and obj.__module__ == checks.__name__)
    assert live == sorted(PUBLIC_CHECKS_FUNCTIONS), (
        "the public function census of `checks` moved; behavior 7 requires it "
        f"UNCHANGED. live={live}")
    assert "_folded_fast_path" not in live, (
        "the classifier is published as a PUBLIC name, which is exactly the "
        "unimplementable shape that reverted iteration 244")
    assert "folded_fast_path" not in live, (
        "an un-underscored `folded_fast_path` is public on this tree, so the rename "
        "the re-land recipe calls for was not applied at the definition site")


CENSUS_PINS = (
    "tests/test_iter93_behavior.py",
    "tests/test_iter207_behavior.py",
)

#: The scan-digest pin module.  It used to sit in `CENSUS_PINS` under whole-file byte
#: equality; it is now held to the LINE-scoped rule below instead -- see
#: `test_b7_the_scan_digest_pin_module_moved_at_most_its_json_pin`.
DIGEST_PIN = "tests/test_iter219_behavior.py"

#: The `--json` document's pin AS THIS MODULE'S BASELINE COMMIT SPELLS IT: length, and
#: the 8-hex prefix the module's own comment abbreviates the digest to.  These two
#: tokens are the ONLY bytes of `DIGEST_PIN` a later iteration may move.
OLD_JSON_PIN_TOKENS = (b"129742", b"36cb0e85")

#: The markdown document's pin, which no iteration since has had cause to move.
MD_PIN_TOKENS = (b"25116", b"7dc7c366")


def _blob_at_prechange(rel: str) -> bytes:
    """`rel` as `PRECHANGE_COMMIT` committed it, read from this repo's object store."""
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{PRECHANGE_COMMIT}:{rel}"],
        capture_output=True, check=False)
    assert blob.returncode == 0, (
        f"cannot read {rel} at {PRECHANGE_COMMIT}: "
        f"{blob.stderr.decode('utf-8', 'replace')[:200]!r}")
    return blob.stdout


@pytest.mark.parametrize("rel", CENSUS_PINS)
def test_b7_the_committed_pins_this_iteration_leans_on_are_unedited(rel: str):
    """Behavior 7 and its acceptance criterion: "not edited at all", measured.

    Both of these files pin the public surface of `checks` by EQUALITY off one
    derived constant, and that census genuinely must not move at all -- so
    whole-file byte equality against the pre-change tree is the right shape for
    them, and it stays.  A re-baselined pin would otherwise be invisible to a
    black-box test: the suite would be green and the guarantee gone.

    `DIGEST_PIN` was the third parameter here until iteration 252 and is now checked
    by the test below instead.  Whole-file equality was the WRONG shape for it: its
    job is to pin bytes `radar scan --json` renders, so freezing the whole file
    against a fixed past commit forbade those bytes from ever moving again -- an
    acceptance criterion scoped to one iteration's diff, enforced with unbounded
    lifetime.  That is iteration 244's unimplementable-pair shape, and iteration 252
    walked into it.
    """
    blob_bytes = _blob_at_prechange(rel)
    on_disk = (REPO / rel).read_bytes()
    assert on_disk == blob_bytes, (
        f"{rel} was EDITED relative to {PRECHANGE_COMMIT} "
        f"({len(blob_bytes)} B -> {len(on_disk)} B); this iteration's acceptance "
        "criteria forbid re-baselining any committed expectation")


def test_b7_the_scan_digest_pin_module_moved_at_most_its_json_pin():
    """`DIGEST_PIN` may re-baseline its `--json` pin and NOTHING else, ever.

    The guarantee whole-file equality bought -- an invisible re-baseline reds the
    suite -- is kept, narrowed to the one expectation that is allowed to move, so
    that ONE declared re-baseline is expressible and a second, undeclared one is
    not.  Four clauses, each two-sided on the live file:

    1. No line is added or removed, so the module's shape is frozen.
    2. Every line whose bytes differ from `PRECHANGE_COMMIT` SPELLS the old `--json`
       pin, so no other line of the module can move under cover of this one.
    3. The old `--json` tokens are absent from the file afterwards, so a re-baseline
       must be COMPLETE -- the module cannot state two values for one pin, which is
       precisely what a value line edited without its explanatory comment leaves
       behind.
    4. The MARKDOWN pin's tokens still appear on exactly the same lines: `--json` is
       the only surface whose bytes this rule frees, and re-baselining the markdown
       document would drop its length or digest from the line that spells it.  Line
       INDICES rather than whole moved lines, because the module carries one comment
       that abbreviates BOTH pins, so "a moved line may not mention markdown" would
       forbid the very comment clause 3 exists to force into agreement.
    """
    before = _blob_at_prechange(DIGEST_PIN).splitlines(keepends=True)
    after = (REPO / DIGEST_PIN).read_bytes().splitlines(keepends=True)
    assert len(before) == len(after), (
        f"{DIGEST_PIN} changed line COUNT ({len(before)} -> {len(after)}) relative "
        f"to {PRECHANGE_COMMIT}; only its `--json` pin may move")

    moved = [i for i, (was, now) in enumerate(zip(before, after)) if was != now]
    for i in moved:
        assert any(token in before[i] for token in OLD_JSON_PIN_TOKENS), (
            f"{DIGEST_PIN}:{i + 1} moved and does not spell the `--json` pin, so it "
            f"is an undeclared re-baseline: {before[i]!r} -> {after[i]!r}")

    whole = b"".join(after)
    for token in OLD_JSON_PIN_TOKENS:
        assert token not in whole, (
            f"{DIGEST_PIN} still spells the pre-change `--json` pin {token!r} "
            "somewhere, so the re-baseline is incomplete and the module now states "
            "two values for one document")

    for token in MD_PIN_TOKENS:
        was = [i for i, line in enumerate(before) if token in line]
        now = [i for i, line in enumerate(after) if token in line]
        assert was and was == now, (
            f"the MARKDOWN pin token {token!r} appears on lines {was} at "
            f"{PRECHANGE_COMMIT} and {now} now; this rule frees the `--json` bytes "
            "only, and a markdown re-baseline would drop the token from its line")


@pytest.mark.parametrize(("pattern", "why"), [
    (r"os\.walk\(", "no leading global inline flag group -- condition 1(a)"),
    (r"(?m)foo", "flag group carries no `i` -- condition 1(b)"),
    (r"(?i)VectorStore", "body carries A-Z, so the fold is not span-safe -- 1(c)"),
    (r"(?i)a(?-i:b)", "a scoped flag-OFF re-enables case sensitivity the fold has "
                      "already destroyed -- condition 1(d)"),
])
def test_b1_rejections_each_have_their_own_case(pattern: str, why: str):
    assert checks._folded_fast_path(pattern) is None, (
        f"{pattern!r} was ACCEPTED but must be rejected: {why}")


def test_b1_accepts_a_lowercase_body_behind_a_global_i():
    assert checks._folded_fast_path(r"(?i)os\.walk\(") == r"os\.walk\("


@pytest.mark.parametrize("pattern", [
    r"(?i)", r"(?I)foo", r"(?ix)foo", r"(?ai)foo", r"x(?i)foo", r" (?i)foo",
])
def test_b1_edge_shapes_are_not_silently_accepted(pattern: str):
    """`\\A\\(\\?[ims]+\\)` is the whole grammar: any other opening is not eligible.

    `(?i)` with an EMPTY body is admitted or refused at the implementation's
    discretion -- the assertion only demands that whatever comes back is either
    `None` or a string whose recompilation is span-identical, which an empty body
    trivially is.  Every other shape here carries a flag letter outside `[ims]` or
    text before the group, so it must be `None`.
    """
    result = checks._folded_fast_path(pattern)
    if pattern == r"(?i)":
        assert result is None or result == ""
        return
    assert result is None, (
        f"{pattern!r} does not match the declared grammar `\\A\\(\\?[ims]+\\)` "
        f"with an i, yet it was accepted as {result!r}")


# --- behavior 1(d), read for its PURPOSE rather than its spelling -----------

#: Patterns whose remainder re-enables a case distinction the fold has already
#: destroyed.  Condition 1(d) is SPELLED "the remainder contains no `(?-`", but
#: Python's inline-flag grammar also allows flags BEFORE the minus (`(?s-i:...)`,
#: `(?m-i:...)`, `(?sm-i:...)`), none of which contain the two-character sequence
#: `(?-`.  Read literally, the spec would ACCEPT those and the fold would invert a
#: verdict; read for its stated PURPOSE it must refuse them.  Tested against the
#: purpose, and the divergence is reported to the PM as an ambiguity.
SCOPED_FLAG_OFF_PATTERNS = (
    r"(?i)a(?-i:b)",
    r"(?i)a(?s-i:b)",
    r"(?i)a(?m-i:b)",
    r"(?i)a(?sm-i:b)",
    r"(?i)a(?-i:b)c",
)


@pytest.mark.parametrize("pattern", SCOPED_FLAG_OFF_PATTERNS)
def test_b1d_a_scoped_flag_off_is_refused_however_it_is_spelled(pattern: str):
    """A scoped `-i` is unrecoverable once the text is folded, so `None` is the
    ONLY sound answer -- no rewrite of the pattern can restore a case distinction
    the fold destroyed in the TEXT.
    """
    assert checks._folded_fast_path(pattern) is None, (
        f"{pattern!r} was accepted; a scoped flag-OFF re-enables case sensitivity "
        "that the folded text can no longer express, so the folded arm can report "
        "a match the raw arm does not -- a FALSE PRESENT")


#: (pattern, text) counterexamples for which a naive `(?-` substring test is
#: provably wrong: the raw arm finds NOTHING and a folded arm finds a match.
FALSE_PRESENT_COUNTEREXAMPLES = (
    (r"(?i)a(?s-i:b)", "aB"),
    (r"(?i)a(?m-i:b)", "aB"),
    (r"(?i)a(?-i:b)", "aB"),
)


@pytest.mark.parametrize(("pattern", "text"), FALSE_PRESENT_COUNTEREXAMPLES)
def test_b1d_no_accepted_pattern_can_manufacture_a_match(pattern: str, text: str):
    """The property behind the previous test, asserted as an EQUALITY rather than
    as a classification, so it holds no matter how the classifier is written.

    If the classifier declines (`None`), the pattern runs exactly as authored and
    there is nothing to prove.  If it accepts, the folded arm's spans must equal
    the raw arm's -- and on these inputs the raw arm's span list is EMPTY, so any
    acceptance that yields a span is a false PRESENT, the one direction this
    iteration forbids.
    """
    assert text.isascii(), "the counterexample must reach the per-file ASCII gate"
    rewritten = checks._folded_fast_path(pattern)
    raw = [m.span() for m in re.compile(pattern, re.MULTILINE).finditer(text)]
    assert raw == [], f"fixture is wrong: the raw arm already matches {raw}"
    if rewritten is None:
        return
    folded = [m.span() for m in re.compile(rewritten, re.MULTILINE).finditer(text.lower())]
    assert folded == raw, (
        f"{pattern!r} -> {rewritten!r} on {text!r}: raw {raw} but folded {folded}; "
        "the fast path manufactured a match the authored pattern does not make")


#: Adversarial (pattern, text) pairs that are NOT expected to be refused -- the
#: point is the differential, not the classification.  Each text is ASCII and
#: mixed-case, so it exercises the exact arm the scan takes.
DIFFERENTIAL_PAIRS = (
    (r"(?i)os\.walk\(", "OS.walk(x)\nos.WALK(y)\n"),
    (r"(?i)while\s+true", "WHILE   TRUE\nwhile\ttrue\n"),
    (r"(?im)^import\s+\w+", "IMPORT os\nimport SYS\n"),
    (r"(?is)begin.*end", "BEGIN\nmiddle\nEnd\n"),
    (r"(?i)\bopen\b", "Open OPEN opener\n"),
    (r"(?i)a{2,3}b?", "AAAB aab Ab\n"),
    (r"(?i)(?:x|yy)+z", "XYYz yyXz\n"),
    (r"(?i)[a-f]+\d*", "AbCdEf12 ghi\n"),
)


@pytest.mark.parametrize(("pattern", "text"), DIFFERENTIAL_PAIRS)
def test_b1_accepted_patterns_are_span_equal_on_adversarial_mixed_case(
        pattern: str, text: str):
    """Behavior 3's oracle, narrowed to hand-built worst cases.

    The frozen corpus is real source and therefore mostly lower-case; these texts
    are deliberately mixed-case at the match sites, which is where a fold either
    holds exactly or does not hold at all.
    """
    rewritten = checks._folded_fast_path(pattern)
    raw = [m.span() for m in re.compile(pattern, re.MULTILINE).finditer(text)]
    if rewritten is None:
        return
    folded = [m.span() for m in re.compile(rewritten, re.MULTILINE).finditer(text.lower())]
    assert folded == raw, (
        f"{pattern!r} -> {rewritten!r} on {text!r}: raw {raw} vs folded {folded}")


# --- behavior 2: the flag group is rewritten, the body is never touched -----

@pytest.mark.parametrize(("pattern", "expected"), [
    (r"(?i)x", r"x"),
    (r"(?is)x", r"(?s)x"),
    (r"(?im)x", r"(?m)x"),
    (r"(?si)x", r"(?s)x"),
])
def test_b2_flag_group_is_rewritten_never_dropped_wholesale(pattern: str, expected: str):
    assert checks._folded_fast_path(pattern) == expected


@pytest.mark.parametrize("body", [
    r"a\\b[^\]]+", r"(?:x|y)\d{2,}", r"\bword\b", r"[\t\n]+", r"a{1,3}?b*?c+?",
    r"os\.walk\(", r"while\s+true",
])
def test_b2_no_character_of_the_body_is_altered(body: str):
    """The check is character-for-character, not case-insensitive: the accepted
    rewrite must be the ORIGINAL body bytes, so a lower-casing implementation fails
    here even though it would still compile.
    """
    accepted = checks._folded_fast_path("(?i)" + body)
    assert accepted == body, (
        f"body was altered: expected {body!r}, got {accepted!r}")
    for flags, prefix in ((r"(?is)", "(?s)"), (r"(?im)", "(?m)")):
        assert checks._folded_fast_path(flags + body) == prefix + body


@pytest.mark.parametrize("body", [
    r"\S+end", r"\B\W", r"pre\Zpost", r"\Astart", r"\D+", r"x\Ky",
])
def test_b2_an_inverting_escape_is_refused_not_rewritten(body: str):
    """Behaviors 1(c) and 2 read together.  `\\S`, `\\B`, `\\W`, `\\A`, `\\Z` and `\\D`
    are the escapes whose SENSE would invert if a body were lower-cased, and each of
    them carries an `A-Z` character -- so condition 1(c) refuses the whole pattern
    rather than the implementation having to reason about escapes at all.  That is
    the ONE-DIRECTIONAL guard: it can only ever decline a speedup.
    """
    assert checks._folded_fast_path("(?i)" + body) is None, (
        f"{body!r} carries an uppercase escape, so condition 1(c) must refuse it")


# --- behavior 3: register-wide equality oracle ------------------------------

def test_b3_the_oracle_is_not_vacuous(frozen_ascii_texts):
    """A pair count of zero would make every chunk below pass while measuring nothing."""
    patterns = _register_patterns()
    accepted = _accepted_patterns()
    assert len(patterns) >= 100, f"only {len(patterns)} distinct register patterns"
    assert len(accepted) > 0, (
        "no committed register pattern is accepted by `_folded_fast_path`, so the "
        "fast path is dead code and behavior 3's oracle is vacuous")
    assert len(frozen_ascii_texts) > 100, (
        f"only {len(frozen_ascii_texts)} ASCII files in the frozen corpus")
    print(f"\n[iter245 b3] {len(accepted)} accepted / {len(patterns)} distinct "
          f"patterns x {len(frozen_ascii_texts)} ASCII frozen files "
          f"= {len(accepted) * len(frozen_ascii_texts)} pairs")


@pytest.mark.parametrize("chunk", range(CHUNKS))
def test_b3_folded_arm_span_lists_equal_raw_arm_span_lists(chunk, frozen_ascii_texts):
    """Full SPAN LISTS, not counts and not booleans: an equality this strict is the
    only form in which "the verdict is unchanged" can be asserted rather than hoped.
    """
    accepted = _accepted_patterns()[chunk::CHUNKS]
    assert accepted, f"chunk {chunk} of {CHUNKS} is empty -- the split is vacuous"
    pairs = 0
    divergences: list[str] = []
    for pattern in accepted:
        rewritten = checks._folded_fast_path(pattern)
        raw = re.compile(pattern, re.MULTILINE)
        folded = re.compile(rewritten, re.MULTILINE)
        for name, text in frozen_ascii_texts:
            pairs += 1
            expected = [m.span() for m in raw.finditer(text)]
            got = [m.span() for m in folded.finditer(text.lower())]
            if expected != got:
                divergences.append(
                    f"{pattern!r} -> {rewritten!r} on {name}: "
                    f"raw {expected[:4]} vs folded {got[:4]}")
    print(f"\n[iter245 b3 chunk {chunk}] {len(accepted)} patterns, {pairs} pairs, "
          f"{len(divergences)} divergences")
    assert pairs > 0, f"chunk {chunk} compared nothing"
    assert not divergences, (
        f"{len(divergences)} span divergence(s) between the raw and folded arms; "
        f"first 3: {divergences[:3]}")


# --- behavior 4: a non-ASCII text keeps today's verdict ---------------------

NON_ASCII_FOLD_TRAP = "\u017fecret = 1\n"


def test_b4_non_ascii_text_keeps_todays_verdict(tmp_path):
    """U+017F LATIN SMALL LETTER LONG S matches `(?i)s` in RAW text, and
    `str.lower()` leaves it unchanged, so a folded arm would find nothing and flip
    PRESENT to ABSENT.  The fast path must therefore not be taken for that file.
    """
    target = _materialise(tmp_path / "nonascii", {"a.py": NON_ASCII_FOLD_TRAP})
    outcome = run_check(_content_check("(?i)secret"), target)
    assert outcome.verdict is Verdict.PRESENT, (
        "the non-ASCII fold trap lost its match, so the fast path was taken for a "
        f"file whose text is not ASCII (got {outcome.verdict.value}: {outcome.reason})")
    assert outcome.locations == ["a.py:1"], outcome.locations


@pytest.mark.parametrize("body", ["secret = 1\n", "SECRET = 1\n", "Secret = 1\n"])
def test_b4_ascii_siblings_report_the_same_shape(tmp_path, body: str):
    """The two-sided half: an ASCII sibling takes the fast path and reports the
    same shape the raw arm would have.
    """
    target = _materialise(tmp_path / body[:3].lower(), {"a.py": body})
    outcome = run_check(_content_check("(?i)secret"), target)
    assert outcome.verdict is Verdict.PRESENT
    assert outcome.locations == ["a.py:1"], outcome.locations


# --- behavior 5: reported locations are unchanged, position for position ----

MIXED_CASE_TREE = {
    #: Same token, three different cases, three different LINE numbers.  One file
    #: per line because a `content_matches` rule reports one location per FILE
    #: (measured, not assumed: a single 12-line fixture yields exactly `f:1`), so a
    #: three-file tree is the only shape in which lines 7 and 12 are observable.
    "one.py": "Secret = 1\n",
    "seven.py": "filler\n" * 6 + "SECRET = 2\n",
    "twelve.py": "filler\n" * 11 + "secret = 3\n",
}


def test_b5_locations_are_position_for_position(tmp_path):
    """ASCII `str.lower()` is length-preserving, so lines 1, 7 and 12 stay 1, 7, 12
    and no reported string moves by a character.
    """
    target = _materialise(tmp_path / "lines", MIXED_CASE_TREE)
    outcome = run_check(_content_check("(?i)secret"), target)
    assert outcome.verdict is Verdict.PRESENT
    assert sorted(outcome.locations) == ["one.py:1", "seven.py:7", "twelve.py:12"], (
        f"reported locations moved: {outcome.locations}")


def test_b5_a_line_offset_by_multibyte_ascii_neighbours_is_still_exact(tmp_path):
    """A second shape: the match is not on line 1 and the file has CRLF-free but
    long preceding lines, so an off-by-one in the fold would be visible.
    """
    text = "x" * 200 + "\n" + "y" * 200 + "\nTOKEN_HERE\n"
    target = _materialise(tmp_path / "offset", {"deep/nested/f.py": text})
    outcome = run_check(_content_check("(?i)token_here"), target)
    assert outcome.locations == ["deep/nested/f.py:3"], outcome.locations


# --- behavior 6: the fast path is not vacuous, and the routing is THIS call --

def _scan_bytes(target: pathlib.Path) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(["scan", str(target), "--gaps", "gaps"])
    return code, buffer.getvalue()


@pytest.fixture(scope="module")
def scan_arms(frozen_corpus, request):
    """The TWO scans this module pays for, both in one module-scoped fixture.

    Arm LIVE goes through a pass-through wrapper, so its bytes ARE the live bytes
    while also counting how often the classifier accepted.  Arm STUB substitutes a
    function that always returns `None`, which is exactly the pre-change routing.
    """
    original = checks._folded_fast_path
    accepts = 0

    def counting(pattern: str):
        nonlocal accepts
        rewritten = original(pattern)
        if rewritten is not None:
            accepts += 1
        return rewritten

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(checks, "_folded_fast_path", counting, raising=True)
        live_code, live_doc = _scan_bytes(frozen_corpus)
        live_accepts = accepts
        monkey.setattr(checks, "_folded_fast_path", lambda pattern: None, raising=True)
        stub_code, stub_doc = _scan_bytes(frozen_corpus)
    finally:
        monkey.undo()
    assert checks._folded_fast_path is original
    return {"live": (live_code, live_doc), "stub": (stub_code, stub_doc),
            "accepts": live_accepts}


def test_b6_the_classifier_is_reached_as_a_module_global_at_call_time(scan_arms):
    """If the scan path captured the function at import time, or inlined it, the
    wrapper would never be consulted and this count would be zero.
    """
    assert scan_arms["accepts"] > 0, (
        "a scan of the 267-file frozen corpus never accepted a single pattern "
        "through the module global, so either the seam is not a module global or "
        "the fast path is dead")
    print(f"\n[iter245 b6] {scan_arms['accepts']} accepting returns during one "
          f"frozen-corpus scan")


def test_b6_stubbing_the_classifier_to_none_moves_no_byte(scan_arms):
    """The equality the whole iteration is specified as."""
    live_code, live_doc = scan_arms["live"]
    stub_code, stub_doc = scan_arms["stub"]
    assert live_code == stub_code == 0
    assert live_doc == stub_doc, (
        "the folded fast path changed the rendered scan document; first divergence "
        f"at byte {next((i for i, (a, b) in enumerate(zip(live_doc, stub_doc)) if a != b), min(len(live_doc), len(stub_doc)))}")
    assert live_doc.endswith("\n") and not live_doc.endswith("\n\n")


# --- behavior 7: byte-identity on every surface, old vs new -----------------

@pytest.mark.parametrize("argv", SURFACE_ARGV, ids=lambda a: "-".join(a))
def test_b7_scan_free_surfaces_are_byte_identical_old_vs_new(argv, prechange_src):
    """Old and new are selected purely by `PYTHONPATH`; the provenance of each
    side is asserted, so a mis-pointed run cannot masquerade as an equality.
    """
    old_code, old_out, old_from = _run_surface(argv, prechange_src)
    new_code, new_out, new_from = _run_surface(argv, REPO / "src")
    assert old_from and new_from and old_from != new_from, (
        f"both arms resolved the same `cli.py` ({old_from!r} vs {new_from!r}), so "
        "this comparison is new-vs-new and measures nothing")
    assert str(prechange_src) in old_from, old_from
    assert old_code == new_code, (
        f"{argv} exit code moved: {old_code} -> {new_code}")
    assert old_out == new_out, (
        f"{argv} stdout moved: {len(old_out)} -> {len(new_out)} bytes")


@pytest.mark.parametrize("argv", SURFACE_ARGV, ids=lambda a: "-".join(a))
def test_b7_every_surface_ends_in_exactly_one_newline(argv):
    code, out, _ = _run_surface(argv, REPO / "src")
    assert code == 0, f"{argv} exited {code}"
    assert out.endswith(b"\n"), f"{argv} does not end in a newline"
    assert not out.endswith(b"\n\n"), f"{argv} ends in more than one newline"


def test_b7_no_absolute_machine_path_is_embedded_in_this_module():
    """PUBLIC REPO rule, pinned inside the very file it constrains.

    The needles are ASSEMBLED at runtime: a contiguous literal here would make
    this assertion trip on its own source.  See the iteration 242 lesson.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    needles = ("/" + "Users" + "/", "/" + "home" + "/", "/" + "root" + "/", "C" + ":\\")
    for needle in needles:
        assert needle not in source, f"absolute machine path {needle!r} committed"
