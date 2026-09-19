"""Iteration 259 behaviors: `radar` writes UTF-8 bytes whatever the ambient locale says.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation is a clause of `pm.md`'s six numbered Expected Behaviors, and every claim is
measured by RUNNING the packaged entry point in a real `subprocess` -- except behavior 4,
which is in process BY CONSTRUCTION because it is about the in-process door itself.

Why a real child process is not a style choice here: iteration 258 recorded that an
`io.StringIO` capture is BLIND to this whole defect class, because a `StringIO` holds
`str` and never encodes. A test that captured in process would have passed on the broken
tree. So every byte and exit-code claim below owns an encoded stream leaving a real
process, with `PYTHONIOENCODING` set on the child's environment.

The one sweep that looks at the source tree (behavior 6) COUNTS token-matching lines and
never asserts on the code around them -- it is the `rg -c` sweep the spec names, not a
reading of the implementation.

Structural notes, so a green dot cannot mean less than it looks like:

* **Cost is bounded by construction** (`pm.md`'s `stage-budget: WARN` -- the tester seat
  is at the 600 s cap). Every arm runs over the register that is ALREADY on disk or over a
  ONE-record scratch register built from this module's own literal; nothing copies the
  120-record register; `radar scan` is deliberately out of scope. The module spends 15
  subprocess runs in total, each ~0.3 s, and every one is cached in a module-scoped
  fixture so no arm pays twice.
* **The negatives are load-bearing.** Behavior 3 rejects a LOSSY fix (`errors="replace"`
  or `"backslashreplace"` would satisfy "exit 0" while changing the bytes), behavior 4
  rejects a fix that reconfigures a stream the 50 in-process capture sites cannot
  reconfigure, and behavior 5 pins the SAME strictness on stderr, where CPython ships
  `backslashreplace` by default and a careless reconfigure silently revokes it.
* **Nothing may move on a UTF-8 machine**: behaviors 1-2 pin six documents to the byte
  counts `pm.md` recorded at HEAD, so this diff cannot have re-baselined a document.
* **No absolute machine path and no personal identifier appears here.** The scratch
  register lives under pytest's `tmp_path`; the repo is located relative to `__file__`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_PKG = REPO_ROOT / "src" / "agent_gap_radar"

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`). Same boot line as `test_iter258_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: `pm.md`'s two arms. ASCII is the hostile locale: on the pre-fix tree it made
#: `radar show` exit 1 with 0 B of stdout and a `UnicodeEncodeError` traceback.
ASCII = "ascii"
UTF8 = "utf-8"

#: LEFT DOUBLE QUOTATION MARK, the character `pm.md` names: it is what a verbatim quote
#: lifted from a real source actually contains, and it is what the crash tripped on.
CURLY_OPEN = "\u201c"
CURLY_OPEN_UTF8 = CURLY_OPEN.encode("utf-8")  # b"\xe2\x80\x9c"

#: The two LOSSY substitutions a non-fix would emit instead, as bytes.
REPLACE_MARK = b"?"
BACKSLASH_MARK = rb"\u201c"

#: `pm.md` behavior 2's four control verbs with the stdout byte counts it recorded at
#: HEAD `4735c85`. Pinned as equalities: if this diff moved a single document byte on a
#: UTF-8 machine, one of these four numbers changes and this module goes red.
CONTROL_VERBS = {
    "report": (("report", "."), 39022),
    "list": (("list", "."), 17446),
    "validate": (("validate", "."), 29),
    "taxonomy": (("taxonomy",), 2329),
}

#: Behavior 1's verb and the byte count `pm.md` recorded for it at the same HEAD.
SHOW_ARGV = ("show", "GAP-012", ".")
SHOW_BYTES = 7676

#: Behavior 6: the forced-encoding mechanism's own token. A stream's encoding can only be
#: changed after the fact through `TextIOWrapper.reconfigure`, so this is the token whose
#: line count answers "is the decision spelled exactly once?".
MECHANISM_TOKEN = "reconfigure"

#: The file `pm.md` names as the single legal home for that decision.
DECISION_FILE = "cli.py"

#: A record satisfying the shipped schema, kept as this module's OWN literal so the
#: scratch register of behavior 5 needs no fixture, no `copytree` and no other test module.
RECORD = {
    "id": "GAP-001",
    "title": "A thing is broken",
    "layer": "orchestration",
    "gap_type": "missing-contract",
    "status": "open",
    "problem": "p",
    "symptom": "s",
    "why_now": "w",
    "existing": ["partial fix one"],
    "severity": 5,
    "frequency": 4,
    "tractability": 3,
    "evidence": [
        {
            "source_class": "first-party-field",
            "title": "INC-1",
            "locator": "https://example.invalid/inc1",
            "date": "2026-01-02",
            "quote": "the verbatim line",
        }
    ],
    "build_hypothesis": "build a small wrapper",
    "tags": ["feedback-loop"],
    "check": {
        "id": "CHK-001",
        "manual_question": "Does the writer encode what the reader already decodes?",
        "rationale": "A record that cannot be written to stdout is not publishable.",
        "fixtures": {
            "bad": {"runner.py": "MARK259_BAD = 1\n"},
            "good": {"runner.py": "MARK259_GOOD = 2\n"},
        },
    },
}

#: Behavior 5's poison: a `source_class` value that is not a known class AND cannot be
#: encoded as ASCII. Two non-ASCII shapes on purpose -- a Latin-1-range letter and the
#: curly quote -- so a partial fix cannot pass by handling only one of them.
BAD_SOURCE_CLASS = "first-party-fi\u00e9ld" + CURLY_OPEN + "x\u201d"


def _run(argv, encoding, cwd=None):
    """Drive the PACKAGED entry point in a child whose stdout locale is `encoding`.

    `PYTHONIOENCODING` is set on the CHILD's environment only, which is the whole point:
    it is how a non-UTF-8 machine is reproduced without one existing on the test host.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = encoding
    return subprocess.run(
        [sys.executable, "-c", BOOT, *argv],
        capture_output=True,
        cwd=str(cwd or REPO_ROOT),
        env=env,
        check=False,
    )


@pytest.fixture(scope="module")
def show_arms():
    """Behavior 1's two streams: the same `show` under the hostile and the native locale."""
    return {enc: _run(SHOW_ARGV, enc) for enc in (ASCII, UTF8)}


@pytest.fixture(scope="module")
def control_arms():
    """Behavior 2's eight streams: four verbs x two locales, run once for the module."""
    return {
        (name, enc): _run(argv, enc)
        for name, (argv, _size) in CONTROL_VERBS.items()
        for enc in (ASCII, UTF8)
    }


@pytest.fixture(scope="module")
def surface_arms():
    """The acceptance criterion that the surface did not move: `--help` and `--version`."""
    return {flag: _run((flag,), ASCII) for flag in ("--help", "--version")}


@pytest.fixture(scope="module")
def refusal_arms(tmp_path_factory):
    """Behavior 5: a ONE-record scratch register whose record is poisoned, plus a control.

    The control arm (the SAME register with a legal `source_class`) is what proves the
    refusal is caused by the poison and not by the scratch register's mere existence.
    """
    root = tmp_path_factory.mktemp("iter259")
    arms = {}
    for name, value in (("bad", BAD_SOURCE_CLASS), ("good", "first-party-field")):
        rec = json.loads(json.dumps(RECORD))
        rec["evidence"][0]["source_class"] = value
        gaps = root / name / "gaps"
        gaps.mkdir(parents=True)
        (gaps / "GAP-001.json").write_text(
            json.dumps(rec, ensure_ascii=True), encoding="utf-8"
        )
        arms[name] = gaps.parent
    return {
        "bad_ascii": _run(("validate", str(arms["bad"])), ASCII),
        "bad_utf8": _run(("validate", str(arms["bad"])), UTF8),
        "good_ascii": _run(("validate", str(arms["good"])), ASCII),
    }


def _assert_one_trailing_newline(raw, label):
    """Every renderer ends in exactly ONE newline (the product's standing quality bar)."""
    assert raw.endswith(b"\n"), f"{label}: stdout must end in a newline, got {raw[-40:]!r}"
    assert not raw.endswith(b"\n\n"), (
        f"{label}: stdout must end in exactly ONE newline, got {raw[-40:]!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 1: the crashing invocation now emits its already-specified bytes.
# ---------------------------------------------------------------------------


def test_b1_show_under_ascii_exits_zero_with_a_silent_stderr(show_arms):
    """Behavior 1, clause by clause: exit 0 and 0 bytes of stderr under ASCII.

    The pre-fix failure `pm.md` reproduced was exit 1, 0 B of stdout and a 12-line
    traceback, so the exit code and the SILENCE of stderr are both load-bearing: a
    traceback's last line contains the substring `Error: `, which is how a crash could
    be mistaken by a consumer for a well-formed refusal.
    """
    proc = show_arms[ASCII]
    err = proc.stderr.decode("utf-8", "backslashreplace")
    assert proc.returncode == 0, f"expected exit 0 under ASCII, got {proc.returncode}; stderr={err!r}"
    assert proc.stderr == b"", f"stderr must be 0 bytes, got {err!r}"
    assert "Traceback" not in err, f"a traceback leaked: {err!r}"
    assert "UnicodeEncodeError" not in err, f"the codec exception leaked: {err!r}"


def test_b1_show_bytes_are_identical_under_both_locales(show_arms):
    """Behavior 1: the ASCII stdout bytes EQUAL the UTF8 stdout bytes, exactly.

    Byte equality, not "both non-empty": it is the only assertion that refuses a fix
    which produces a document under ASCII by degrading it.
    """
    ascii_out = show_arms[ASCII].stdout
    utf8_out = show_arms[UTF8].stdout
    assert show_arms[UTF8].returncode == 0, "the UTF8 control arm must itself be green"
    assert ascii_out == utf8_out, (
        "show stdout must be byte-identical under both locales; "
        f"ascii={len(ascii_out)} B utf8={len(utf8_out)} B"
    )
    assert len(ascii_out) == SHOW_BYTES, (
        f"pm.md records {SHOW_BYTES} B for `show GAP-012 .`; got {len(ascii_out)} B"
    )
    _assert_one_trailing_newline(ascii_out, "show/ascii")


# ---------------------------------------------------------------------------
# Behavior 2: nothing else moves -- the increment's own control arm.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CONTROL_VERBS))
def test_b2_control_verbs_are_byte_identical_and_unmoved(control_arms, name):
    """Behavior 2: `report`, `list`, `validate`, `taxonomy` -- same bytes, same size.

    The pinned sizes are `pm.md`'s HEAD measurements. They double as the acceptance
    criterion "no committed byte-pin is re-baselined": a diff that moved a document
    byte on a UTF-8 machine cannot keep these four numbers.
    """
    _argv, expected = CONTROL_VERBS[name]
    a = control_arms[(name, ASCII)]
    u = control_arms[(name, UTF8)]
    for enc, proc in ((ASCII, a), (UTF8, u)):
        err = proc.stderr.decode("utf-8", "backslashreplace")
        assert proc.returncode == 0, f"{name}/{enc}: expected exit 0, got {proc.returncode}; stderr={err!r}"
        assert proc.stderr == b"", f"{name}/{enc}: stderr must be 0 bytes, got {err!r}"
    assert a.stdout == u.stdout, (
        f"{name}: stdout must be byte-identical under both locales; "
        f"ascii={len(a.stdout)} B utf8={len(u.stdout)} B"
    )
    assert len(a.stdout) == expected, (
        f"{name}: pm.md records {expected} B at HEAD; got {len(a.stdout)} B"
    )
    _assert_one_trailing_newline(a.stdout, f"{name}/ascii")


# ---------------------------------------------------------------------------
# Behavior 3: strict, not lossy.
# ---------------------------------------------------------------------------


def test_b3_the_ascii_document_carries_real_utf8_not_a_substitution(show_arms):
    """Behavior 3: U+201C survives as its UTF-8 bytes; no `?` and no `\\u201c` escape.

    This is the arm that separates a FIX from a workaround. `errors="replace"` and
    `errors="backslashreplace"` both make the crash of behavior 1 disappear while
    changing the document, so "exit 0" alone would have been satisfied by a defect.
    """
    ascii_out = show_arms[ASCII].stdout
    utf8_out = show_arms[UTF8].stdout
    assert CURLY_OPEN_UTF8 in ascii_out, (
        "the ASCII-locale document must contain U+201C as real UTF-8 bytes "
        f"{CURLY_OPEN_UTF8!r}; it does not"
    )
    assert BACKSLASH_MARK not in ascii_out, (
        f"a backslashreplace escape {BACKSLASH_MARK!r} leaked into the document"
    )
    assert ascii_out.count(REPLACE_MARK) == utf8_out.count(REPLACE_MARK), (
        "the ASCII arm introduced `?` characters the UTF8 arm does not have: "
        f"{ascii_out.count(REPLACE_MARK)} vs {utf8_out.count(REPLACE_MARK)}"
    )
    assert ascii_out.count(REPLACE_MARK) == 0, (
        "this document contains no question mark at HEAD, so any `?` is a substitution: "
        f"{ascii_out.count(REPLACE_MARK)} found"
    )
    assert ascii_out.count(CURLY_OPEN_UTF8) == utf8_out.count(CURLY_OPEN_UTF8), (
        "the two locales must carry the same NUMBER of curly quotes"
    )


# ---------------------------------------------------------------------------
# Behavior 4: the in-process door is not asked to reconfigure anything.
# ---------------------------------------------------------------------------


def test_b4_in_process_stringio_capture_still_works():
    """Behavior 4: `main` under `redirect_stdout(StringIO())` returns 0 and raises nothing.

    `io.StringIO` has no `reconfigure`, and 34 test modules already capture this way at
    50 sites, so an unguarded reconfigure at the `main` boundary would raise
    `AttributeError` across a quarter of the suite. The assertion names that exception
    explicitly because it is the specific way the one-line fix goes wrong.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = main(["show", "GAP-012", str(REPO_ROOT)])
    except AttributeError as exc:  # pragma: no cover - the failure this arm exists for
        pytest.fail(f"the in-process door was asked to reconfigure a StringIO: {exc!r}")
    text = buf.getvalue()
    assert rc == 0, f"in-process show must return 0, got {rc!r}"
    assert text, "in-process show captured no document"
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        f"captured text must end in exactly one newline, got {text[-40:]!r}"
    )
    assert CURLY_OPEN in text, "the in-process document must still carry U+201C"


def test_b4_in_process_capture_of_both_streams_still_works(tmp_path):
    """Behavior 4, the stderr half: capturing BOTH streams as `StringIO` must also work.

    `pm.md` behavior 5 puts the refusal path on stderr, so the fix necessarily touches
    that stream too. A guard written for stdout alone would pass the arm above and fail
    here, which is why this arm exists rather than trusting symmetry.
    """
    gaps = tmp_path / "reg" / "gaps"
    gaps.mkdir(parents=True)
    rec = json.loads(json.dumps(RECORD))
    rec["evidence"][0]["source_class"] = BAD_SOURCE_CLASS
    (gaps / "GAP-001.json").write_text(json.dumps(rec, ensure_ascii=True), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["validate", str(gaps.parent)])
    except AttributeError as exc:  # pragma: no cover - the failure this arm exists for
        pytest.fail(f"the in-process door was asked to reconfigure a StringIO: {exc!r}")
    assert rc == 2, f"a poisoned record must be refused with exit 2, got {rc!r}"
    assert out.getvalue() == "", f"stdout must stay empty on refusal, got {out.getvalue()!r}"
    assert err.getvalue().startswith("Error: "), (
        f"the refusal must keep its prefix in process, got {err.getvalue()!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 5: the refusal path is unchanged under ASCII.
# ---------------------------------------------------------------------------


def test_b5_refusal_shape_under_ascii(refusal_arms):
    """Behavior 5: exit 2, 0 B of stdout, exactly ONE stderr line, prefixed `Error: `."""
    proc = refusal_arms["bad_ascii"]
    err = proc.stderr.decode("utf-8", "backslashreplace")
    assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}; stderr={err!r}"
    assert proc.stdout == b"", f"stdout must be 0 bytes, got {proc.stdout[:200]!r}"
    assert proc.stderr.endswith(b"\n"), f"stderr must end in a newline: {err!r}"
    assert proc.stderr.count(b"\n") == 1, f"stderr must be exactly ONE line: {err!r}"
    assert err.startswith("Error: "), f"missing the 'Error: ' prefix: {err!r}"
    assert "Traceback" not in err, f"a traceback leaked: {err!r}"
    assert "UnicodeEncodeError" not in err, f"the codec exception leaked: {err!r}"


def test_b5_the_refusal_is_caused_by_the_poison_not_the_scratch_register(refusal_arms):
    """Behavior 5's control arm: the same register with a legal value validates clean."""
    proc = refusal_arms["good_ascii"]
    err = proc.stderr.decode("utf-8", "backslashreplace")
    assert proc.returncode == 0, f"the control register must validate; stderr={err!r}"
    assert proc.stderr == b"", f"the control arm must be silent on stderr: {err!r}"
    _assert_one_trailing_newline(proc.stdout, "validate/control")


def test_b5_stderr_is_utf8_too_and_not_backslashreplaced(refusal_arms):
    """Behavior 5, the strictness clause read onto stderr, where the trap is real.

    CPython ships `sys.stderr` with `errors="backslashreplace"` so a diagnostic is
    always deliverable, and `reconfigure(encoding=...)` RESETS `errors` to `strict`. So
    the error channel has two ways to fail after this fix: crash while reporting, or
    report `\\xe9` where the value has a letter. The refusal here echoes the offending
    value, which makes this measurable: the ASCII stderr bytes must equal the UTF8
    stderr bytes and must carry the real UTF-8 encoding of the value.
    """
    bad_ascii = refusal_arms["bad_ascii"]
    bad_utf8 = refusal_arms["bad_utf8"]
    assert bad_utf8.returncode == 2, "the UTF8 control arm must also refuse"
    assert bad_ascii.stderr == bad_utf8.stderr, (
        "the refusal line must be byte-identical under both locales; "
        f"ascii={bad_ascii.stderr!r} utf8={bad_utf8.stderr!r}"
    )
    assert BAD_SOURCE_CLASS.encode("utf-8") in bad_ascii.stderr, (
        "the refusal must echo the offending value as real UTF-8 bytes; "
        f"got {bad_ascii.stderr!r}"
    )
    assert rb"\xe9" not in bad_ascii.stderr, (
        f"a backslashreplace escape leaked onto stderr: {bad_ascii.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 6: the decision is spelled ONCE.
# ---------------------------------------------------------------------------


def test_b6_the_forced_encoding_site_is_one_line_in_one_file():
    """Behavior 6: the mechanism's token occurs on exactly one line, in `cli.py`.

    This is the `rg -c` sweep `pm.md` names, done in Python so it needs no tool on the
    host. It COUNTS matching lines and asserts nothing about the code around them, so it
    stays inside the isolation contract: a stream's encoding cannot be forced after the
    fact by any other mechanism, so one line is the whole decision.
    """
    hits = {}
    for path in sorted(SRC_PKG.rglob("*.py")):
        lines = [
            n
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if MECHANISM_TOKEN in line
        ]
        if lines:
            hits[path.name] = lines
    assert list(hits) == [DECISION_FILE], (
        f"the {MECHANISM_TOKEN!r} decision must live in exactly one file "
        f"({DECISION_FILE}); found it in {hits!r}"
    )
    assert len(hits[DECISION_FILE]) == 1, (
        f"the decision must be spelled on exactly ONE line of {DECISION_FILE}; "
        f"found lines {hits[DECISION_FILE]!r}"
    )


def test_b6_the_encoding_named_is_on_that_same_line():
    """Behavior 6, sharpened: the encoding literal sits on the decision's own line.

    A module constant plus a call would spell the decision twice while still passing a
    bare token count. Line NUMBERS are compared, never line content.
    """
    text = (SRC_PKG / DECISION_FILE).read_text(encoding="utf-8").splitlines()
    mech = {n for n, line in enumerate(text, 1) if MECHANISM_TOKEN in line}
    enc = {n for n, line in enumerate(text, 1) if "utf-8" in line or "utf8" in line}
    assert mech == enc, (
        f"the encoding name and {MECHANISM_TOKEN!r} must share one line in "
        f"{DECISION_FILE}; mechanism on {sorted(mech)}, encoding on {sorted(enc)}"
    )


# ---------------------------------------------------------------------------
# Acceptance criterion: no new flag, verb or exit code; the surface still boots.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_surface_flags_still_exit_zero_under_ascii(surface_arms, flag):
    """`radar --help` and `--version` still exit 0, and under the hostile locale too."""
    proc = surface_arms[flag]
    err = proc.stderr.decode("utf-8", "backslashreplace")
    assert proc.returncode == 0, f"{flag}: expected exit 0, got {proc.returncode}; stderr={err!r}"
    assert proc.stderr == b"", f"{flag}: stderr must be 0 bytes, got {err!r}"
    _assert_one_trailing_newline(proc.stdout, flag)
