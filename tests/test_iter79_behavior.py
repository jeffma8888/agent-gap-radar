"""Iteration 79 behaviors: `tools/check_locators.py` publishes the CHECKED denominator,
refuses to report register health when it checked NOTHING, and gains an injectable checker
seam so every one of its verdicts -- summary, refusal and exit code -- is provable with no
socket.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/` or `tools/`
implementation logic, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any
diff. Every expectation comes from `pm.md`'s Expected Behaviors, and every claim is measured
by CALLING the public interface -- `check_locators.main` with an injected stub over a
register this file writes into `tmp_path`.

Structural notes, so this file cannot lie later:

* **The suite stays OFFLINE, and that is enforced rather than promised.** An autouse fixture
  installs a socket tripwire AND a `subprocess` tripwire for every test in this module, so a
  run that reached the network -- or that shelled out to `curl` -- fails loudly here instead
  of passing on a good network day. This file imports no `urllib` and opens no socket.
* **No test reads the live `gaps/` tree** (row 27's lesson). Every register is written by
  `_register()` into pytest's `tmp_path`, so a future research pass that adds records or
  rots a link cannot red this file.
* **`main`'s argv carries the program name at index 0.** Measured, and it matters: given a
  ONE-element argv the tool falls back to the default `gaps` directory relative to the
  process cwd, which is the LIVE register when pytest runs from the repo root. Every call
  here therefore goes through `_argv()`, which prepends a program-name slot, and
  `test_iter79_b0_...` pins that hazard so a later refactor of the argv contract cannot
  silently point this file at the live tree.
* **Behavior 1's seam test is the form that CAN fail.** A signature default bound at
  definition time would make `monkeypatch.setattr(module, "check", sentinel)` a no-op, so
  the assertion here is that a monkeypatched module-level `check` IS reached when no
  `check_fn` is passed -- call-time resolution is the only way that assertion passes.
* **Behavior 6 is the NEGATIVE CONTROL, and it is what makes the refusal attributable.** The
  same suite proves an all-skip register is REFUSED (rc 2) and that a PARTLY-skipped
  register is still REPORTED (rc 1, empty stderr, its BROKEN detail line intact), so
  "tightened exactly here" cannot be mistaken for "tightened broadly" (iter-78 lesson).
* **The four counts are parsed out of the summary line and re-checked arithmetically**, so
  behavior 4 (`checked + skipped == distinct`) is asserted over every run this file makes
  rather than being asserted once and hoped for.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; nothing is written outside `tmp_path`.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import re
import socket
import subprocess
import sys

import pytest

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import check_locators  # noqa: E402  (path is prepared immediately above)

#: The exit codes the tool's published contract allows.
PUBLISHED_EXIT_CODES = {0, 1, 2}

#: Every summary line this file observes, so the arithmetic pin can be a whole-file property.
_SUMMARY_RE = re.compile(
    r"^(\d+) distinct locator\(s\): (\d+) checked, (\d+) skipped \(non-http\), (\d+) broken$",
    re.MULTILINE,
)


class _NetworkAttempted(AssertionError):
    """Raised by the tripwire when a test tries to open a socket or shell out."""


@pytest.fixture(autouse=True)
def _offline_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance: every test here is offline, and that is enforced, not promised.

    Two-sided: it cannot pass vacuously, because a real check attempt -- including one
    reached through a def-time default that ignored our stub -- raises here.
    """

    def boom(*_args: object, **_kwargs: object) -> None:
        raise _NetworkAttempted("a test in this module attempted to reach the network")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "check_output", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(check_locators.subprocess, "run", boom)


# --------------------------------------------------------------------------- helpers

#: A schema-legal record with every required field, so no test depends on the live tree.
_RECORD_TEMPLATE: dict[str, object] = {
    "id": "GAP-001",
    "title": "A placeholder record used only to carry locators",
    "layer": "observability",
    "gap_type": "measurement-gap",
    "status": "open",
    "problem": "A fixture problem statement.",
    "symptom": "A fixture symptom.",
    "why_now": "A fixture rationale.",
    "existing": ["A fixture existing approach."],
    "severity": 4,
    "frequency": 5,
    "tractability": 3,
    "evidence": [],
    "build_hypothesis": "A fixture build hypothesis.",
    "tags": ["fixture"],
}


def _register(tmp_path: pathlib.Path, locators: list[str], name: str = "reg") -> pathlib.Path:
    """Write a one-record register under `tmp_path` whose evidence carries `locators`."""
    gaps_dir = tmp_path / name
    gaps_dir.mkdir(parents=True, exist_ok=True)
    record = json.loads(json.dumps(_RECORD_TEMPLATE))
    record["evidence"] = [
        {
            "source_class": "peer-reviewed",
            "title": f"Fixture source {i}",
            "locator": locator,
            "date": "2026-01-01",
            "quote": "a fixture quote",
        }
        for i, locator in enumerate(locators)
    ]
    (gaps_dir / "GAP-001-fixture.json").write_text(json.dumps(record, indent=2) + "\n")
    return gaps_dir


def _argv(gaps_dir: pathlib.Path) -> list[str]:
    """argv as the tool consumes it: a program-name slot, then the register directory.

    Measured, and load-bearing: a one-element argv makes the tool fall back to its default
    `gaps` directory relative to the process cwd -- the LIVE register under pytest.
    """
    return ["check_locators.py", str(gaps_dir)]


class _Stub:
    """A caller-supplied checker. Records every url it is asked about."""

    def __init__(self, replies: dict[str, str] | None = None, default: str = "200") -> None:
        self.replies = replies or {}
        self.default = default
        self.calls: list[str] = []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        return self.replies.get(url, self.default)


def _run(
    capsys: pytest.CaptureFixture[str],
    gaps_dir: pathlib.Path,
    stub: _Stub | None,
    **kwargs: object,
) -> tuple[int, str, str]:
    """Drive `main` and return (rc, stdout, stderr), asserting the whole-file properties."""
    if stub is not None:
        kwargs["check_fn"] = stub
    rc = check_locators.main(_argv(gaps_dir), **kwargs)  # type: ignore[arg-type]
    captured = capsys.readouterr()
    assert rc in PUBLISHED_EXIT_CODES, f"exit code {rc!r} is outside {PUBLISHED_EXIT_CODES}"
    _assert_counts_reconcile(captured.out)
    return rc, captured.out, captured.err


def _summary_of(stdout: str) -> tuple[int, int, int, int]:
    """Return (distinct, checked, skipped, broken) parsed from the one summary line."""
    matches = [(line, _SUMMARY_RE.match(line)) for line in stdout.splitlines()]
    hits = [m for _line, m in matches if m is not None]
    assert len(hits) == 1, (
        "expected exactly one summary line naming distinct/checked/skipped/broken; "
        f"stdout was {stdout!r}"
    )
    m = hits[0]
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def _assert_counts_reconcile(stdout: str) -> None:
    """Behavior 4, asserted on EVERY run this file makes rather than once."""
    if not _SUMMARY_RE.search(stdout):
        return  # a run that refused before reporting (behavior 7) prints no summary
    distinct, checked, skipped, _broken = _summary_of(stdout)
    assert checked + skipped == distinct, (
        f"checked ({checked}) + skipped ({skipped}) != distinct ({distinct})"
    )


# ------------------------------------------------------- behavior 0 (fixture integrity)


def test_iter79_b0_a_one_element_argv_would_silently_read_the_default_register() -> None:
    """Fixture integrity: argv[0] is a program-name slot, so `_argv` must prepend one.

    This is not one of the eight spec behaviors; it pins the hazard that would make every
    other test in this file secretly measure the live `gaps/` tree. It is asserted WITHOUT
    calling the tool, by reading the parameter contract only.
    """
    assert _argv(pathlib.Path("x")) == ["check_locators.py", "x"]
    assert len(_argv(pathlib.Path("x"))) == 2


# --------------------------------------------------------------------- behavior 1: seam


def test_iter79_b1_main_accepts_an_injectable_checker_as_a_keyword_argument() -> None:
    """Behavior 1: the seam is a keyword parameter on `main` whose default is None."""
    params = inspect.signature(check_locators.main).parameters
    assert "check_fn" in params, f"no check_fn seam on main; parameters were {list(params)}"
    seam = params["check_fn"]
    assert seam.default is None, (
        "the seam's default must be None so it can resolve at CALL time; "
        f"found default {seam.default!r}"
    )
    assert seam.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )


def test_iter79_b1_the_default_resolves_at_call_time_to_the_module_level_check(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 1: with NO check_fn passed, a monkeypatched module-level `check` is reached.

    This is the form that can FAIL. Were the default bound at definition time
    (`check_fn=check` in the signature), this monkeypatch would be a no-op and the real
    network path would run -- which the autouse tripwire turns into a loud failure rather
    than a silent pass.
    """
    sentinel = _Stub()
    monkeypatch.setattr(check_locators, "check", sentinel)
    gaps_dir = _register(tmp_path, ["https://call-time.example/a"])

    rc, out, err = _run(capsys, gaps_dir, None)

    assert sentinel.calls == ["https://call-time.example/a"], (
        "the module-level `check` was not reached, so the default is bound at definition "
        f"time rather than resolved at call time; calls were {sentinel.calls!r}"
    )
    assert rc == 0
    assert err == ""
    assert _summary_of(out) == (1, 1, 0, 0)


def test_iter79_b1_the_stub_is_called_exactly_once_per_distinct_http_locator(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 1: one call per DISTINCT http locator, and never for a non-http one."""
    stub = _Stub()
    gaps_dir = _register(
        tmp_path,
        [
            "https://b.example/two",
            "https://a.example/one",
            "https://b.example/two",  # a duplicate: still one call
            "doi:10.0000/not-a-url",  # non-http: never offered to the checker
        ],
    )

    rc, out, _err = _run(capsys, gaps_dir, stub)

    assert stub.calls == ["https://a.example/one", "https://b.example/two"], (
        f"expected one sorted call per distinct http locator; got {stub.calls!r}"
    )
    assert len(stub.calls) == len(set(stub.calls))
    assert rc == 0
    assert _summary_of(out) == (3, 2, 1, 0)


def test_iter79_b1_a_stub_driven_run_never_shells_out(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 1: `subprocess` is not invoked when a stub is supplied.

    The autouse tripwire has already replaced `subprocess.run` with a raiser, so this test
    fails loudly if the tool ignores the seam and shells out anyway.
    """
    stub = _Stub()
    gaps_dir = _register(tmp_path, ["https://never-shelled.example/a"])

    rc, _out, err = _run(capsys, gaps_dir, stub)

    assert rc == 0
    assert err == ""
    assert stub.calls == ["https://never-shelled.example/a"]


# ------------------------------------------- behavior 2: the all-skip run is REFUSED


def test_iter79_b2_an_all_non_http_register_is_refused_with_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 2: nothing checkable => exit 2, one `Error: ` line naming BOTH counts."""
    stub = _Stub()
    gaps_dir = _register(tmp_path, ["doi:10.0000/not-a-url", "isbn:978-0-000-00000-0"])

    rc, out, err = _run(capsys, gaps_dir, stub)

    assert rc == 2, f"an all-skip register must exit 2, got {rc}"
    assert stub.calls == [], f"nothing was checkable, so the checker must not run: {stub.calls!r}"

    err_lines = err.splitlines()
    assert len(err_lines) == 1, f"expected exactly one stderr line, got {err_lines!r}"
    assert err_lines[0].startswith("Error: "), f"stderr must be prefixed 'Error: ': {err!r}"
    assert "0 checked" in err_lines[0], f"stderr must state 0 checked: {err_lines[0]!r}"
    assert "2 distinct" in err_lines[0], f"stderr must state the N distinct: {err_lines[0]!r}"

    assert _summary_of(out) == (2, 0, 2, 0)


def test_iter79_b2_the_refused_run_still_prints_its_skip_lines_and_summary_and_nothing_else(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 2: stdout for the refused run is exactly the SKIP lines plus the summary."""
    gaps_dir = _register(tmp_path, ["doi:10.0000/not-a-url"])

    _rc, out, _err = _run(capsys, gaps_dir, _Stub())

    lines = out.splitlines()
    assert len(lines) == 2, f"expected one SKIP line and one summary line, got {lines!r}"
    assert "SKIP" in lines[0] and "doi:10.0000/not-a-url" in lines[0]
    assert _SUMMARY_RE.match(lines[1]), f"line 2 is not the summary: {lines[1]!r}"
    assert out.endswith("\n") and not out.endswith("\n\n")


# -------------------------------------------- behavior 3: the summary names the denominator


def test_iter79_b3_the_summary_is_one_line_naming_all_four_counts(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 3: distinct / CHECKED / SKIPPED / BROKEN, in one deterministic line.

    A reader must not have to subtract to learn the denominator, so `checked` and `skipped`
    are each required to appear as their own named count.
    """
    gaps_dir = _register(
        tmp_path, ["https://a.example/one", "https://b.example/two", "doi:10.0000/x"]
    )

    _rc, out, _err = _run(capsys, gaps_dir, _Stub())

    summary = [ln for ln in out.splitlines() if _SUMMARY_RE.match(ln)]
    assert len(summary) == 1, f"expected exactly one summary line, got {summary!r}"
    line = summary[0]
    for token in ("distinct", "checked", "skipped", "broken"):
        assert token in line, f"the summary must name {token!r}: {line!r}"
    assert line == line.rstrip(), f"the summary line carries trailing whitespace: {line!r}"
    assert _summary_of(out) == (3, 2, 1, 0)


def test_iter79_b3_locator_lines_are_emitted_in_sorted_order(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 3 / determinism: output order does not depend on record or dict order."""
    locators = [
        "https://z.example/last",
        "https://m.example/middle",
        "https://a.example/first",
    ]
    gaps_dir = _register(tmp_path, locators)

    _rc, out, _err = _run(capsys, gaps_dir, _Stub())

    seen = [loc for loc in sorted(locators) if loc in out]
    positions = [out.index(loc) for loc in seen]
    assert seen == sorted(locators)
    assert positions == sorted(positions), f"locator lines are not in sorted order: {out!r}"


# ---------------------------------- behavior 4: the counts reconcile on every path


@pytest.mark.parametrize(
    "locators, expected",
    [
        (["doi:10.0000/x"], (1, 0, 1, 0)),  # the all-skip run of behavior 2
        (["https://a.example/one"], (1, 1, 0, 0)),  # the all-http run of behavior 5
        (["https://a.example/one", "doi:10.0000/x"], (2, 1, 1, 0)),  # mixed
    ],
)
def test_iter79_b4_checked_plus_skipped_equals_distinct(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    locators: list[str],
    expected: tuple[int, int, int, int],
) -> None:
    """Behavior 4: the identity holds for every run, including both extremes."""
    gaps_dir = _register(tmp_path, locators)

    _rc, out, _err = _run(capsys, gaps_dir, _Stub())

    distinct, checked, skipped, broken = _summary_of(out)
    assert (distinct, checked, skipped, broken) == expected
    assert checked + skipped == distinct


# -------------------------------------------------- behavior 5: the healthy all-http run


def test_iter79_b5_an_all_http_register_that_resolves_exits_0_with_empty_stderr(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 5: checked == distinct, skipped 0, broken 0, rc 0, stderr empty."""
    stub = _Stub(default="200")
    gaps_dir = _register(
        tmp_path, ["https://a.example/one", "https://b.example/two", "https://c.example/three"]
    )

    rc, out, err = _run(capsys, gaps_dir, stub)

    assert rc == 0, f"a fully healthy register must exit 0, got {rc}"
    assert err == "", f"stderr must be empty on the healthy path: {err!r}"
    distinct, checked, skipped, broken = _summary_of(out)
    assert (distinct, checked, skipped, broken) == (3, 3, 0, 0)
    assert checked == distinct
    assert len(stub.calls) == 3
    assert "BROKEN" not in out


# ------------------- behavior 6: the NEGATIVE CONTROL -- a partly-skipped run is reported


def test_iter79_b6_a_partly_skipped_register_reports_its_break_instead_of_being_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 6 -- THE NEGATIVE CONTROL for behavior 2.

    The vacuity refusal must NOT broaden into refusing any run that skipped something.
    Without this pin, "tightened exactly here" is indistinguishable from "tightened
    broadly" (iter-78 tester lesson). So: one http locator that 404s plus one non-http
    locator must yield exit 1 -- the BROKEN verdict -- and NOT exit 2, with stderr empty
    and the per-locator BROKEN detail line still printed.
    """
    url = "https://a.example/gone"
    stub = _Stub(replies={url: "404"})
    gaps_dir = _register(tmp_path, [url, "doi:10.0000/not-a-url"])

    rc, out, err = _run(capsys, gaps_dir, stub)

    assert rc == 1, (
        f"a partly-skipped register that found a break must exit 1 (BROKEN), not {rc}; "
        "exit 2 here would mean the vacuity refusal broadened"
    )
    assert rc != 2
    assert err == "", f"a reported run must not write to stderr: {err!r}"
    assert _summary_of(out) == (2, 1, 1, 1)
    assert f"BROKEN 404: {url}" in out, (
        f"the trailing BROKEN detail line for the http locator is missing: {out!r}"
    )
    assert "SKIP" in out, "the non-http locator must still be reported as a SKIP"
    assert stub.calls == [url]


def test_iter79_b6_a_partly_skipped_register_whose_http_locator_resolves_exits_0(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 6, second control: skipping something is not by itself a failure.

    Distinguishes "the refusal fires on any skip" from "the refusal fires only when NOTHING
    was checked": one healthy http locator beside a non-http one is a clean run.
    """
    gaps_dir = _register(tmp_path, ["https://a.example/fine", "doi:10.0000/not-a-url"])

    rc, out, err = _run(capsys, gaps_dir, _Stub(default="200"))

    assert rc == 0, f"one healthy checked locator beside a skip must exit 0, got {rc}"
    assert err == ""
    assert _summary_of(out) == (2, 1, 1, 0)


# ------------------------------------------- behavior 7: the two pre-existing refusals


def test_iter79_b7_a_gaps_dir_that_is_not_a_directory_is_refused_unchanged(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 7: `Error: not a directory: <path>` on stderr, exit 2, empty stdout."""
    missing = tmp_path / "no-such-register"

    rc, out, err = _run(capsys, missing, _Stub())

    assert rc == 2
    assert out == "", f"a usage refusal must print no document: {out!r}"
    assert err == f"Error: not a directory: {missing}\n", f"message changed: {err!r}"


def test_iter79_b7_a_register_with_no_evidence_locators_is_refused_unchanged(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 7: `Error: no evidence locators found in <path>` on stderr, exit 2."""
    gaps_dir = _register(tmp_path, [])

    rc, out, err = _run(capsys, gaps_dir, _Stub())

    assert rc == 2
    assert out == "", f"a usage refusal must print no document: {out!r}"
    assert err == f"Error: no evidence locators found in {gaps_dir}\n", f"message changed: {err!r}"


def test_iter79_b7_the_zero_locator_refusal_is_distinct_from_the_all_skip_refusal(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 7 vs 2: both exit 2, and their messages must not have collapsed into one."""
    empty = _register(tmp_path, [], name="empty")
    all_skip = _register(tmp_path, ["doi:10.0000/x"], name="skips")

    rc_empty, _out_empty, err_empty = _run(capsys, empty, _Stub())
    rc_skip, out_skip, err_skip = _run(capsys, all_skip, _Stub())

    assert rc_empty == rc_skip == 2
    assert err_empty != err_skip, "the two causes of exit 2 must remain distinguishable"
    assert "no evidence locators found" in err_empty
    assert "no evidence locators found" not in err_skip
    assert _SUMMARY_RE.search(out_skip), "the all-skip refusal still publishes its counts"


# ---------------------------------------- behavior 8: the published contract agrees


def test_iter79_b8_the_module_docstring_exit_codes_line_names_the_new_cause_of_2() -> None:
    """Behavior 8: the tool's own published `Exit codes:` line cannot disagree with its code.

    Measured through the public `__doc__` attribute, not by reading the source file.
    """
    doc = check_locators.__doc__ or ""
    lines = [ln.strip() for ln in doc.splitlines() if ln.strip().startswith("Exit codes:")]
    assert len(lines) == 1, f"expected exactly one 'Exit codes:' line, found {lines!r}"
    line = lines[0].lower()

    for code in ("0", "1", "2"):
        assert code in line, f"exit code {code} is unpublished: {lines[0]!r}"
    assert "check" in line, (
        f"the line must scope success to what was CHECKED: {lines[0]!r}"
    )
    # Both causes of 2 must be named: the pre-existing usage cause and the new vacuity cause.
    assert "usage" in line, f"the usage cause of exit 2 is unpublished: {lines[0]!r}"
    assert "checkable" in line or "nothing was checked" in line, (
        f"the new cause of exit 2 (nothing was checkable) is unpublished: {lines[0]!r}"
    )


# ------------------------------------- this file's own guard, proven two-sided


def test_iter79_the_arithmetic_guard_in_this_file_is_not_vacuous() -> None:
    """Behavior 4's guard must be able to FAIL, or it proves nothing about the tool.

    `_assert_counts_reconcile` runs on every `_run` above. A guard whose regex silently
    matches nothing would pass every run vacuously -- which is exactly what an unanchored
    multi-line pattern did on the first draft of this file. So the guard is pinned in both
    directions here, over literal strings: it accepts a consistent summary and RAISES on an
    inconsistent one.
    """
    consistent = (
        "  SKIP  x1  doi:10.0000/x (non-http locator)\n"
        "2 distinct locator(s): 1 checked, 1 skipped (non-http), 0 broken\n"
    )
    _assert_counts_reconcile(consistent)  # must not raise
    assert _summary_of(consistent) == (2, 1, 1, 0)

    inconsistent = "9 distinct locator(s): 1 checked, 1 skipped (non-http), 0 broken\n"
    with pytest.raises(AssertionError):
        _assert_counts_reconcile(inconsistent)
