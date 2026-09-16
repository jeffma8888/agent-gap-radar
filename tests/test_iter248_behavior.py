"""Iteration 248 behaviors: `tools/check_locators.py` skips a locator iff it fails the
product's ONE resolvable-locator rule, so `curl` is never spent -- and `BROKEN` never
blamed -- on a shape the ingest gate refuses.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/` or `tools/`
implementation logic, the engineer's or reviewer's notes, `IMPLEMENTATION.patch`, or any
diff. Every expectation comes from `pm.md`'s Expected Behaviors, and every claim is
measured by CALLING the public interface -- `check_locators.main` through its `check_fn`
seam, over a register this file writes into pytest's `tmp_path`. Behavior 8's two claims
are read out of the SHIPPED ARTIFACTS the README publishes about (the tool's import list,
parsed with `ast`, and the README sentence itself), which is what the spec names as the
observable, not implementation logic.

Structural notes, so this file cannot lie later:

* **The suite stays OFFLINE, and that is enforced rather than promised.** An autouse
  fixture installs a socket tripwire AND a `subprocess` tripwire for every test in this
  module (including on the tool's own `subprocess` reference), so a run that reached the
  network -- or shelled out to `curl` -- fails loudly here instead of passing on a good
  network day. This file imports no `urllib` and opens no socket.
* **No test reads the live `gaps/` tree** (row 27's lesson). Every register is written by
  `_register()` into `tmp_path`, so a research pass that adds records or rots a link
  cannot red this file.
* **`main`'s argv carries the program name at index 0.** A one-element argv makes the tool
  fall back to its default `gaps` directory relative to the process cwd -- the LIVE
  register under pytest. Every call goes through `_argv()`, and `test_iter248_b0_...` pins
  that hazard without calling the tool.
* **Behavior 2 is proven NON-VACUOUS before it is measured.** `test_iter248_b1_...
  _the_eight_divergent_shapes_are_exactly_the_ones_the_old_rule_accepted` asserts that all
  eight fixtures are True under the DISCARDED `startswith("http")` spelling and False under
  the canonical rule, so "the stub was called 0 times" proves the tightening happened
  rather than proving the fixtures were never http-ish in the first place.
* **Behavior 7 is asserted on EVERY run this file makes**, inside `_run`, rather than once
  in one test -- the whole-file-property shape `tests/test_iter79_behavior.py` established,
  and `test_iter248_the_arithmetic_guard_in_this_file_is_not_vacuous` pins that guard in
  both directions so it cannot pass by matching nothing.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; nothing is written outside `tmp_path`.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import socket
import subprocess
import sys

import pytest

from agent_gap_radar import models

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import check_locators  # noqa: E402  (path is prepared immediately above)

#: The exit codes the tool's published contract allows.
PUBLISHED_EXIT_CODES = {0, 1, 2}

#: The summary line, anchored, so the arithmetic pin is a whole-file property.
_SUMMARY_RE = re.compile(
    r"^(\d+) distinct locator\(s\): (\d+) checked, (\d+) skipped \(not resolvable\), (\d+) broken$"
)

#: Behavior 3, verbatim from the spec.
_REFUSAL = (
    "Error: 0 checked of 8 distinct locator(s) -- no locator is resolvable by shape, "
    "so this run cannot report register health"
)

#: The eight shapes `pm.md`'s `## Why` measured as splitting the two spellings.
DIVERGENT_SHAPES = [
    "http:/nohost",
    "httpx://a/b",
    "http",
    "https",
    "http://",
    "https://x.com/p ",
    "http://a b/c",
    "https://x.com/a\nb",
]

#: Behavior 1's corpus: (value, expected answer under the canonical rule).
CANONICAL_CORPUS: list[tuple[str, bool]] = [
    ("https://ok.example/p", True),
    ("http://ok.example/p", True),
    ("http:/nohost", False),
    ("httpx://a/b", False),
    ("http", False),
    ("https", False),
    ("http://", False),
    ("https://x.com/p ", False),
    ("http://a b/c", False),
    ("https://x.com/a\nb", False),
    ("doi:10.0000/x", False),
    ("HTTP://X.com/", False),
    ("ftp://x/y", False),
    ("", False),
    ("   ", False),
]

#: The sentence `README.md` publishes and `test_iter122_behavior.py` pins verbatim.
PORTED_VERBATIM_CLAIM = (
    "`tools/check_locators.py` originated here and is ported verbatim into the practice "
    "index, so both registers prove their citations resolve the same way"
)


class _NetworkAttempted(AssertionError):
    """Raised by the tripwire when a test tries to open a socket or shell out."""


@pytest.fixture(autouse=True)
def _offline_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Acceptance: every test here is offline, and that is enforced, not promised.

    Two-sided: it cannot pass vacuously, because a real check attempt -- including one
    reached because the tool ignored the seam -- raises here rather than silently passing.
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

    Load-bearing: a one-element argv makes the tool fall back to its default `gaps`
    directory relative to the process cwd -- the LIVE register when pytest runs from the
    repo root (`test_iter79_behavior.py` measured this and pins it too).
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


def _summary_of(stdout: str) -> tuple[int, int, int, int]:
    """Return (distinct, checked, skipped, broken) parsed from the one summary line."""
    hits = [m for m in (_SUMMARY_RE.match(ln) for ln in stdout.splitlines()) if m is not None]
    assert len(hits) == 1, (
        "expected exactly one summary line naming distinct/checked/skipped/broken; "
        f"stdout was {stdout!r}"
    )
    m = hits[0]
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def _assert_counts_reconcile(stdout: str) -> None:
    """Behavior 7, asserted on EVERY run this file makes rather than once."""
    if not any(_SUMMARY_RE.match(ln) for ln in stdout.splitlines()):
        return  # a run that refused before reporting prints no summary
    distinct, checked, skipped, _broken = _summary_of(stdout)
    assert checked + skipped == distinct, (
        f"checked ({checked}) + skipped ({skipped}) != distinct ({distinct}); "
        f"stdout was {stdout!r}"
    )


def _run(
    capsys: pytest.CaptureFixture[str],
    gaps_dir: pathlib.Path,
    stub: _Stub | None,
) -> tuple[int, str, str]:
    """Drive `main` and return (rc, stdout, stderr), asserting the whole-file properties."""
    kwargs: dict[str, object] = {}
    if stub is not None:
        kwargs["check_fn"] = stub
    rc = check_locators.main(_argv(gaps_dir), **kwargs)  # type: ignore[arg-type]
    captured = capsys.readouterr()
    assert rc in PUBLISHED_EXIT_CODES, f"exit code {rc!r} is outside {PUBLISHED_EXIT_CODES}"
    _assert_counts_reconcile(captured.out)
    return rc, captured.out, captured.err


def _skip_lines(stdout: str) -> list[str]:
    """Every physical line that OPENS a SKIP entry.

    Deliberately not `len(stdout.splitlines())`: one spec fixture is a locator with an
    EMBEDDED newline, so its single SKIP entry occupies two physical lines. Counting the
    opening prefix is the reading of "one SKIP line per distinct locator" that survives
    that fixture.
    """
    return [ln for ln in stdout.splitlines() if ln.startswith("  SKIP  ")]


# ------------------------------------------------- behavior 0 (fixture integrity)


def test_iter248_b0_a_one_element_argv_would_silently_read_the_default_register() -> None:
    """Fixture integrity: argv[0] is a program-name slot, so `_argv` must prepend one.

    Not one of the eight spec behaviors; it pins the hazard that would make every other
    test in this file secretly measure the live `gaps/` tree. Asserted WITHOUT calling the
    tool, by reading the argv contract only.
    """
    assert _argv(pathlib.Path("x")) == ["check_locators.py", "x"]
    assert len(_argv(pathlib.Path("x"))) == 2


def test_iter248_b0_the_fixture_register_is_written_under_tmp_path_only(
    tmp_path: pathlib.Path,
) -> None:
    """Fixture integrity: the register this file drives is inside `tmp_path`, not `gaps/`."""
    gaps_dir = _register(tmp_path, ["https://ok.example/p"])
    assert gaps_dir.is_relative_to(tmp_path)
    assert not gaps_dir.is_relative_to(REPO_ROOT / "gaps")
    assert [p.name for p in sorted(gaps_dir.iterdir())] == ["GAP-001-fixture.json"]


# ------------------------------------ behavior 1: the predicate is the canonical one


def test_iter248_b1_the_tool_exposes_a_module_level_resolvable_locator_predicate() -> None:
    """Behavior 1: `is_resolvable_locator(url: str) -> bool` is a module-level name."""
    pred = getattr(check_locators, "is_resolvable_locator", None)
    assert pred is not None, (
        "check_locators exposes no module-level `is_resolvable_locator`; public names were "
        f"{sorted(n for n in vars(check_locators) if not n.startswith('_'))}"
    )
    assert callable(pred)
    assert isinstance(pred("https://ok.example/p"), bool), (
        "the predicate must answer with a bool, not a truthy match object; got "
        f"{pred('https://ok.example/p')!r}"
    )


@pytest.mark.parametrize("value, expected", CANONICAL_CORPUS, ids=repr)
def test_iter248_b1_the_tools_answer_equals_the_canonical_models_answer(
    value: str, expected: bool
) -> None:
    """Behavior 1: one ANSWER for the whole product, over all 15 enumerated values.

    Two-sided: the corpus carries two True cases and thirteen False ones, so a predicate
    stuck at either constant fails here. The `expected` column is the spec's own reading,
    so this also fails if BOTH spellings drift together.
    """
    theirs = models.is_resolvable_locator(value)
    ours = check_locators.is_resolvable_locator(value)
    assert theirs == expected, (
        f"the canonical rule's answer for {value!r} moved: models says {theirs}, the spec "
        f"says {expected}"
    )
    assert ours == theirs, (
        f"divergent locator dialects for {value!r}: tools/check_locators says {ours}, "
        f"agent_gap_radar.models says {theirs}"
    )


def test_iter248_b1_the_eight_divergent_shapes_are_exactly_the_ones_the_old_rule_accepted() -> None:
    """Behavior 1/2 non-vacuity: every behavior-2 fixture WAS accepted by the old spelling.

    This is what makes "the stub was called 0 times" attributable to the tightening. Under
    the discarded `url.startswith("http")` rule all eight are True (so all eight would have
    been fetched, counted into `checked` and printed `BROKEN`); under the canonical rule all
    eight are False. The comparison string is spelled out here rather than imported, so no
    surviving copy of the old rule is needed for this file to prove the claim.
    """
    for value in DIVERGENT_SHAPES:
        assert value.startswith("http"), (
            f"{value!r} is not an http-prefixed shape, so it cannot demonstrate the "
            "divergence the fix removes"
        )
        assert check_locators.is_resolvable_locator(value) is False, (
            f"{value!r} is still resolvable by shape, so it would still be fetched"
        )
        assert models.is_resolvable_locator(value) is False
    assert len(set(DIVERGENT_SHAPES)) == 8


# ------------------------ behavior 2: an http-prefixed unfetchable shape is SKIPPED


def test_iter248_b2_no_divergent_shape_is_ever_offered_to_the_checker(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 2: 0 checker calls, one SKIP entry per distinct locator, exit 2."""
    stub = _Stub()
    gaps_dir = _register(tmp_path, DIVERGENT_SHAPES)

    rc, out, _err = _run(capsys, gaps_dir, stub)

    assert stub.calls == [], (
        "an http-prefixed but unresolvable shape was offered to the checker, so `curl` "
        f"would be spent on a guaranteed 000: {stub.calls!r}"
    )
    assert rc == 2, f"a register with nothing resolvable must exit 2, got {rc}"
    assert len(_skip_lines(out)) == 8, (
        f"expected one SKIP entry per distinct locator; SKIP lines were {_skip_lines(out)!r}"
    )
    assert _summary_of(out) == (8, 0, 8, 0)
    assert "BROKEN" not in out, f"nothing was fetched, so nothing may be blamed: {out!r}"
    assert out.endswith("\n") and not out.endswith("\n\n")


# --------------------- behavior 3: the refusal names the SHAPE rule, not the scheme


def test_iter248_b3_the_refusal_is_one_line_and_blames_the_shape_rule(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 3: stderr is exactly the spec's line plus exactly one newline."""
    gaps_dir = _register(tmp_path, DIVERGENT_SHAPES)

    rc, _out, err = _run(capsys, gaps_dir, _Stub())

    assert rc == 2
    assert err == _REFUSAL + "\n", f"stderr is not the published refusal, byte for byte: {err!r}"
    assert len(err.splitlines()) == 1
    assert err.startswith("Error: ")
    assert err.count("\n") == 1
    assert "non-http" not in err, (
        "the refusal still blames the SCHEME, which is the misattribution row 109 names: "
        f"{err!r}"
    )
    assert "resolvable by shape" in err


# ------------------------------------------------------ behavior 4: the SKIP format


@pytest.mark.parametrize(
    "locator, times",
    [("doi:10.0000/x", 1), ("doi:10.0000/x", 2), ("http://", 1), ("http://", 3)],
    ids=["doi-x1", "doi-x2", "http-prefixed-x1", "http-prefixed-x3"],
)
def test_iter248_b4_a_skipped_locator_prints_the_published_line_verbatim(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    locator: str,
    times: int,
) -> None:
    """Behavior 4: the SKIP line's exact bytes, for a non-http AND an http-prefixed shape.

    The count is exercised at more than 1 so the `x{N}` slot cannot be a frozen literal,
    and both fixture classes take the SAME arm -- which is the point of the fix.
    """
    gaps_dir = _register(tmp_path, [locator] * times)

    _rc, out, _err = _run(capsys, gaps_dir, _Stub())

    expected = f"  SKIP  x{times}  {locator} (not a resolvable locator)"
    lines = out.splitlines()
    assert lines[0] == expected, (
        f"the SKIP line is not the published format; expected {expected!r}, got {lines[0]!r}"
    )
    assert _summary_of(out) == (1, 0, 1, 0)


# ----------------- behavior 5: a resolvable locator is still checked exactly once


def test_iter248_b5_a_resolvable_locator_is_checked_once_and_counted(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 5: the negative control -- the fix tightened HERE, not broadly.

    One resolvable locator cited twice plus one http-prefixed unresolvable one: exactly one
    call, with exactly the resolvable url, rc 0, and the summary as the last stdout line.
    """
    stub = _Stub()
    gaps_dir = _register(tmp_path, ["https://ok.example/p", "https://ok.example/p", "http://"])

    rc, out, err = _run(capsys, gaps_dir, stub)

    assert stub.calls == ["https://ok.example/p"], (
        f"expected exactly one call, for the resolvable locator only; got {stub.calls!r}"
    )
    assert rc == 0, f"a register whose one checked locator answered 200 must exit 0, got {rc}"
    assert err == "", f"a reported run writes nothing to stderr: {err!r}"
    lines = out.splitlines()
    assert lines[-1] == (
        "2 distinct locator(s): 1 checked, 1 skipped (not resolvable), 0 broken"
    ), f"stdout's last line is not the published summary: {lines[-1]!r}"
    assert _summary_of(out) == (2, 1, 1, 0)
    assert out.endswith("\n") and not out.endswith("\n\n")


# -------------- behavior 6: BROKEN is reachable only for what the gate accepts


def test_iter248_b6_only_a_fetched_locator_is_ever_blamed(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Behavior 6: rc 1, the summary counts 1 broken, and the blame names only the fetch."""
    stub = _Stub(replies={"https://rot.example/p": "404"})
    gaps_dir = _register(tmp_path, ["https://rot.example/p", "http://"])

    rc, out, err = _run(capsys, gaps_dir, stub)

    assert stub.calls == ["https://rot.example/p"]
    assert rc == 1, f"a broken checked locator must exit 1, got {rc}"
    assert err == "", f"link rot is a report, not an error: {err!r}"
    summary = [ln for ln in out.splitlines() if _SUMMARY_RE.match(ln)]
    assert summary == [
        "2 distinct locator(s): 1 checked, 1 skipped (not resolvable), 1 broken"
    ], f"the summary is not the published line: {summary!r}"

    blame_lines = [ln for ln in out.splitlines() if ln.startswith("  BROKEN")]
    assert blame_lines, f"a broken locator must be named in a BROKEN line: {out!r}"
    for line in blame_lines:
        assert "http://" not in line, (
            "a skipped shape is blamed as BROKEN, which sends a maintainer to a link-rot "
            f"repair for a record-shape problem: {line!r}"
        )
    assert any("https://rot.example/p" in ln for ln in blame_lines)


# ------------------------------------------ behavior 7: the partition by construction


@pytest.mark.parametrize(
    "locators, expected",
    [
        (["https://ok.example/p", "doi:10.0000/x", "http://"], (3, 1, 2, 0)),
        (["doi:10.0000/x"], (1, 0, 1, 0)),
        (["https://ok.example/p"], (1, 1, 0, 0)),
        (DIVERGENT_SHAPES, (8, 0, 8, 0)),
    ],
    ids=["mixed-three", "all-non-http", "all-resolvable", "all-http-prefixed-unresolvable"],
)
def test_iter248_b7_checked_plus_skipped_equals_distinct(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    locators: list[str],
    expected: tuple[int, int, int, int],
) -> None:
    """Behavior 7: the identity holds on every arm, including the spec's mixed register.

    `_run` already asserts the identity for every call this file makes; this pins the exact
    four integers as well, so a partition that reconciles at the WRONG totals still fails.
    """
    gaps_dir = _register(tmp_path, locators)

    _rc, out, _err = _run(capsys, gaps_dir, _Stub())

    distinct, checked, skipped, broken = _summary_of(out)
    assert (distinct, checked, skipped, broken) == expected
    assert checked + skipped == distinct
    assert len(_skip_lines(out)) == skipped, (
        f"the skipped COUNT and the SKIP entries disagree: {skipped} vs {_skip_lines(out)!r}"
    )


# ------------------------- behavior 8: the tool stays stdlib-pure, so the claim holds


def test_iter248_b8_the_tool_imports_nothing_outside_the_standard_library() -> None:
    """Behavior 8: `ast`-parsed imports name no `agent_gap_radar` and nothing third-party.

    Under row 109's shapes (a) and (b) the file could no longer RUN as the single ported
    file the README advertises, so this is the brake that keeps the published claim true.
    """
    source = (TOOLS_DIR / "check_locators.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, (
                f"a relative import makes the ported single file unrunnable: level {node.level}"
            )
            if node.module:
                roots.add(node.module.split(".")[0])

    assert roots, "no imports were parsed at all, so this check would pass vacuously"
    assert "agent_gap_radar" not in roots, (
        f"the tool imports this package, so the ported copy cannot run: {sorted(roots)}"
    )
    outside = sorted(r for r in roots if r not in sys.stdlib_module_names)
    assert outside == [], f"the tool imports outside the standard library: {outside}"


def test_iter248_b8_the_tool_mutates_no_import_path() -> None:
    """Behavior 8: no `sys.path` shim (row 109 shape (b), explicitly out of scope)."""
    source = (TOOLS_DIR / "check_locators.py").read_text(encoding="utf-8")
    assert "sys.path" not in source, (
        "a sys.path mutation is the shape the spec refused; the ported file must run as-is"
    )


def test_iter248_b8_the_ported_verbatim_readme_claim_is_byte_identical() -> None:
    """Behavior 8: `README.md` still publishes the ported-verbatim sentence, unchanged."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert PORTED_VERBATIM_CLAIM in readme, (
        "the README sentence this iteration promised NOT to touch is gone or reworded"
    )


# ---------------------------------- acceptance: no hand-spelled dialect survives


def test_iter248_no_hand_spelled_locator_dialect_remains_under_tools() -> None:
    """Acceptance criterion 1, measured over the shipped tree instead of by `rg` in prose.

    Read as text over `tools/*.py`, so it is an observable of the repo rather than of any
    module's logic. This is the check that would have caught the defect row 109 filed.
    """
    offenders: dict[str, list[int]] = {}
    for path in sorted(TOOLS_DIR.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if 'startswith("http' in line or "startswith('http" in line:
                offenders.setdefault(path.name, []).append(lineno)
    assert offenders == {}, (
        "a hand-spelled locator dialect survives, so the product still has two answers to "
        f"one question: {offenders}"
    )


# ------------------------------------- this file's own guard, proven two-sided


def test_iter248_the_arithmetic_guard_in_this_file_is_not_vacuous() -> None:
    """`_assert_counts_reconcile` runs on every `_run` above, so it must be able to FAIL.

    A guard whose regex silently matched nothing would pass every run vacuously. Pinned in
    both directions here over literal strings, and the SKIP-line counter is pinned against
    the embedded-newline fixture that makes naive line counting wrong.
    """
    consistent = (
        "  SKIP  x1  doi:10.0000/x (not a resolvable locator)\n"
        "2 distinct locator(s): 1 checked, 1 skipped (not resolvable), 0 broken\n"
    )
    _assert_counts_reconcile(consistent)  # must not raise
    assert _summary_of(consistent) == (2, 1, 1, 0)

    inconsistent = "9 distinct locator(s): 1 checked, 1 skipped (not resolvable), 0 broken\n"
    with pytest.raises(AssertionError):
        _assert_counts_reconcile(inconsistent)

    embedded_newline = (
        "  SKIP  x1  https://x.com/a\nb (not a resolvable locator)\n"
        "  SKIP  x1  http:// (not a resolvable locator)\n"
    )
    assert len(embedded_newline.splitlines()) == 3
    assert len(_skip_lines(embedded_newline)) == 2, (
        "the SKIP counter must count entries, not physical lines, or the embedded-newline "
        "fixture makes behavior 2 unmeasurable"
    )
