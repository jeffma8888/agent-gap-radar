"""Iteration 14 behaviors: `render_scan` reaches the published renderers, and the
one-newline tail has exactly one implementation under `src/`.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source to derive an expectation, and nothing reads the engineer's or the reviewer's notes
or a diff. Every behavioral assertion drives the public CLI entry point (`main`) or the
published `agent_gap_radar.render` API and observes only the exit code, the stdout bytes
and the stderr bytes.

Behaviors 4 and 5 are a SOURCE CENSUS, which the spec asks for by name. The census reads
`src/**/*.py` as DATA through one regex built from the spec's verbatim description of the
idiom; no expectation in this file was copied out of the implementation, and the census
reports its domain size so an empty walk can never read as clean.

Two orderings deliberately NOT hard-coded, because a literal here would be a second copy
of something the product already owns:

* The verdict ROW ORDER is derived from `list(Verdict)`. The spec's prose names the order
  as "PRESENT, ABSENT, MANUAL, NOT_APPLICABLE, UNKNOWN"; the shipped enum declares
  NOT_APPLICABLE BEFORE MANUAL, and the shipped document agrees with the enum. Testing the
  prose would be the fail-CLOSED shape: a red suite against correct code. The five verbatim
  MEANINGS from the spec are asserted, keyed by verdict value, so the wording is still
  pinned exactly.
* The verdict COUNTS are read out of the document under test and re-fed to `table`, so
  behavior 3 proves an equivalence rather than restating a fixture's arithmetic.

Registers and targets are built in `tmp_path`. Nothing under `gaps/` is read to make an
assertion true (that register is grown by an unattended research pass, so a keyed
expectation over it would go red against a CORRECT register); the two `radar report` runs
assert only table HEADER lines, which no record can move.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from agent_gap_radar.checks import UNKNOWN_MEANING, Verdict
from agent_gap_radar.cli import main
from agent_gap_radar.render import table
from test_iter02_behavior import MARKER, _record, _target, _write_register

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"

#: Behavior 1 -- the two fixed lines of the verdict table.
VERDICT_HEADER = "| Verdict | Count | Meaning |"
VERDICT_RULE = "| --- | --- | --- |"

#: Behavior 1 -- the five meanings keyed by verdict value. Four are verbatim from the
#: spec; UNKNOWN is DERIVED from `checks.UNKNOWN_MEANING`, because iteration 70 made
#: that constant the single published copy and a hand-copy here would be a second.
MEANINGS = {
    "PRESENT": "gap signature found in this target",
    "ABSENT": "a mitigation was positively identified",
    "MANUAL": "static analysis cannot decide; a human must answer",
    "NOT_APPLICABLE": "this gap cannot apply to this target",
    "UNKNOWN": UNKNOWN_MEANING,
}

#: Behavior 6 -- the two `radar report` table headers.
RANKED_HEADER = "| Rank | ID | Priority | Confidence | Layer | Type | Title |"
BY_LAYER_HEADER = "| Layer | Records |"

#: Two records that both carry a check, so every scan below checks exactly 2 gaps and
#: the verdict counts must sum to 2.
CHECKED = [
    _record("GAP-600", 5, 3, 3, ("first-party-field",), "CHK-600"),
    _record("GAP-601", 4, 3, 3, ("first-party-field",), "CHK-601"),
]


# ---------------------------------------------------------------------------
# Fixture builders. `MARKER`, `_record`, `_target` and `_write_register` come from
# tests/test_iter02_behavior.py; the fixture check fires on exactly MARKER, so
# "PRESENT" is a property of the fixture and never of the published register.
# ---------------------------------------------------------------------------

def _scan_stdout(tmp_path, capsys, name, body):
    """`radar scan` stdout for a tmp target. Asserts rc 0 and an empty stderr."""
    reg = _write_register(tmp_path / name, list(CHECKED))
    target = _target(tmp_path / name, body=body)
    rc = main(["scan", str(target), "--gaps", str(reg)])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    assert cap.err == ""
    return cap.out


@pytest.fixture()
def hit_stdout(tmp_path, capsys):
    """A target that trips both fixture checks -- at least one PRESENT."""
    return _scan_stdout(tmp_path, capsys, "hit", MARKER)


@pytest.fixture()
def clean_stdout(tmp_path, capsys):
    """A target that trips neither check -- zero PRESENT findings."""
    return _scan_stdout(tmp_path, capsys, "clean", "nothing to see here")


def _verdict_block(out):
    """The 7 lines of the verdict table, plus the line that follows it."""
    lines = out.split("\n")
    assert lines.count(VERDICT_HEADER) == 1, (
        f"expected exactly one verdict table, found {lines.count(VERDICT_HEADER)}")
    i = lines.index(VERDICT_HEADER)
    return lines[i:i + 7], lines[i + 7]


def _cells(row):
    """The three cells of a markdown row, without asserting anything about them."""
    assert row.startswith("| ") and row.endswith(" |"), f"not a table row: {row!r}"
    return row[2:-2].split(" | ")


def _counts(out):
    """{verdict value: int count} read out of the document under test."""
    block, _ = _verdict_block(out)
    return {c[0]: int(c[1]) for c in (_cells(r) for r in block[2:])}


# ---------------------------------------------------------------------------
# Behavior 1 -- the verdict table's bytes are unchanged.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [MARKER, "nothing to see here"])
def test_verdict_table_is_seven_fixed_lines(tmp_path, capsys, body):
    out = _scan_stdout(tmp_path, capsys, "b1", body)
    block, after = _verdict_block(out)

    assert len(block) == 7, block
    assert block[0] == VERDICT_HEADER
    assert block[1] == VERDICT_RULE
    assert not after.startswith("|"), f"an 8th table row followed the block: {after!r}"

    expected_order = [v.value for v in Verdict]
    assert [_cells(r)[0] for r in block[2:]] == expected_order

    for row, verdict in zip(block[2:], expected_order):
        value, count, meaning = _cells(row)
        assert value == verdict
        assert count.isdigit(), f"count cell is not a plain integer: {count!r}"
        assert meaning == MEANINGS[verdict], f"meaning drifted for {verdict}: {meaning!r}"


def test_verdict_counts_sum_to_the_number_of_checked_gaps(hit_stdout):
    assert sum(_counts(hit_stdout).values()) == len(CHECKED)


def test_the_five_meanings_cover_every_verdict_member(hit_stdout):
    """Two-sided on the taxonomy itself: no member is missing, none is invented."""
    assert sorted(MEANINGS) == sorted(v.value for v in Verdict)
    assert sorted(_counts(hit_stdout)) == sorted(v.value for v in Verdict)


# ---------------------------------------------------------------------------
# Behavior 2 -- the one-newline contract holds for the scan renderer.
# ---------------------------------------------------------------------------

def test_scan_ends_in_exactly_one_newline_with_findings(hit_stdout):
    assert _counts(hit_stdout)["PRESENT"] > 0, "premise: this target must yield a finding"
    assert hit_stdout.endswith("\n")
    assert not hit_stdout.endswith("\n\n")
    assert hit_stdout.splitlines()[-1].strip() != ""


def test_scan_ends_in_exactly_one_newline_with_no_findings(clean_stdout):
    assert _counts(clean_stdout)["PRESENT"] == 0, "premise: this target must yield none"
    assert clean_stdout.endswith("\n")
    assert not clean_stdout.endswith("\n\n")
    assert clean_stdout.splitlines()[-1].strip() != ""


# ---------------------------------------------------------------------------
# Behavior 3 -- `table` is a public name and reproduces the shipped bytes.
# ---------------------------------------------------------------------------

def test_table_is_importable_and_callable():
    from agent_gap_radar import render

    assert callable(render.table)
    assert getattr(render, "_table", None) is None, (
        "the private `_table` name survived the rename; the acceptance criterion is a "
        "rename, not an alias")


def test_table_reproduces_the_scan_verdict_table_byte_for_byte(hit_stdout):
    block, _ = _verdict_block(hit_stdout)
    counts = _counts(hit_stdout)
    rows = [[v.value, str(counts[v.value]), MEANINGS[v.value]] for v in Verdict]

    assert table(["Verdict", "Count", "Meaning"], rows) == block


def test_table_docstring_says_why_it_is_public():
    """Acceptance criterion: the docstring must say another module reaches it."""
    from agent_gap_radar import render

    doc = (render.table.__doc__ or "").lower()
    assert doc.strip(), "`table` has no docstring"
    assert "copy" in doc or "copies" in doc, (
        "`table`'s docstring does not say why it is public in the same terms as "
        f"`document` (another module must REACH it, not COPY it): {doc!r}")


# ---------------------------------------------------------------------------
# Behaviors 4 and 5 -- the one-newline tail has exactly ONE implementation.
#
# The pattern is built from the spec's verbatim description: a
# `while lines and lines[-1] == "":` loop whose body is `lines.pop()`, immediately
# followed by `return "\n".join(lines) + "\n"`. Note the doubled backslash: the regex
# must match a LITERAL backslash-n inside a string literal, not the newline
# metacharacter -- getting that wrong is a fail-CLOSED matcher that reports the idiom
# everywhere. Behavior 5's planted samples are what prove it two-sided.
# ---------------------------------------------------------------------------

TAIL_IDIOM = re.compile(
    r'''while\s+lines\s+and\s+lines\[-1\]\s*==\s*(?:""|'')\s*:'''
    r'''\s*lines\.pop\(\)'''
    r'''\s*return\s+(?:"\\n"|'\\n')\.join\(lines\)\s*\+\s*(?:"\\n"|'\\n')''')

#: Known-bad: the idiom itself. Must be seen exactly once.
PLANTED_BAD = (
    'def render_thing(lines):\n'
    '    lines.append("x")\n'
    '    while lines and lines[-1] == "":\n'
    '        lines.pop()\n'
    '    return "\\n".join(lines) + "\\n"\n'
)

#: Known-good: the convention this iteration installs. Must be seen zero times.
PLANTED_GOOD = (
    'def render_thing(lines):\n'
    '    lines.append("x")\n'
    '    return document(lines)\n'
)

#: Near-miss: the pop loop WITHOUT the join tail. Must be seen zero times, so a hit
#: cannot be scored on the loop alone.
PLANTED_NEAR_MISS = (
    'def render_thing(lines):\n'
    '    while lines and lines[-1] == "":\n'
    '        lines.pop()\n'
    '    return document(lines)\n'
)


def _census_in(root):
    """(files scanned, {filename: hits}) over `root/**/*.py`, `__pycache__` excluded."""
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    hits = {}
    for path in files:
        n = len(TAIL_IDIOM.findall(path.read_text(encoding="utf-8")))
        if n:
            hits[path.name] = n
    return files, hits


def _census():
    """The live census: `src/agent_gap_radar/**/*.py`."""
    return _census_in(SRC_DIR)


def test_one_newline_tail_has_exactly_one_implementation():
    files, hits = _census()
    total = sum(hits.values())
    assert total == 1, (
        f"the one-newline tail idiom occurs {total} time(s) across {len(files)} file(s) "
        f"under src/agent_gap_radar/, expected exactly 1: {hits}")
    assert list(hits) == ["render.py"], (
        f"the single implementation must live in render.py, found it in {list(hits)}")


def test_census_domain_is_non_empty_and_reported():
    """An empty walk must never read as clean (behavior 5)."""
    files, _ = _census()
    assert len(files) >= 8, (
        f"census domain collapsed to {len(files)} file(s) under {SRC_DIR.name}/; a small "
        "domain reads as health it never measured")
    assert all(p.suffix == ".py" for p in files)
    assert not any("__pycache__" in p.parts for p in files)


@pytest.mark.parametrize(
    "sample,expected",
    [(PLANTED_BAD, 1), (PLANTED_GOOD, 0), (PLANTED_NEAR_MISS, 0)],
    ids=["known-bad", "known-good", "near-miss-loop-without-tail"])
def test_census_matcher_is_two_sided(sample, expected):
    assert len(TAIL_IDIOM.findall(sample)) == expected


def _planted_tree(root, copies):
    """A synthetic src-shaped tree of 9 modules, `copies` of which carry the idiom."""
    root.mkdir(parents=True)
    for index in range(9):
        body = PLANTED_BAD if index < copies else PLANTED_GOOD
        (root / f"mod{index}.py").write_text(body, encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "mod0.py").write_text(PLANTED_BAD, encoding="utf-8")
    return root


def test_census_itself_is_two_sided_over_a_whole_tree(tmp_path):
    """The DOMAIN walk, not just the regex: the census must fire on a planted second
    copy, or behavior 4 passing over `src/` would be health it never measured."""
    files, hits = _census_in(_planted_tree(tmp_path / "one", copies=1))
    assert len(files) == 9 and sum(hits.values()) == 1 and list(hits) == ["mod0.py"]

    files, hits = _census_in(_planted_tree(tmp_path / "two", copies=2))
    assert len(files) == 9, "`__pycache__` leaked into the domain"
    assert sum(hits.values()) == 2, (
        "a second copy of the idiom did NOT raise the census count; behavior 4 would "
        f"pass with the duplicate still present: {hits}")

    files, hits = _census_in(_planted_tree(tmp_path / "none", copies=0))
    assert len(files) == 9 and hits == {}


# ---------------------------------------------------------------------------
# Behavior 6 -- the `_table` -> `table` rename moves no report bytes.
# ---------------------------------------------------------------------------

def _report_stdout(capsys, root):
    rc = main(["report", str(root)])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    return cap.out


def test_report_table_headers_unchanged_on_the_committed_register(capsys):
    out = _report_stdout(capsys, REPO_ROOT)
    lines = out.split("\n")
    assert lines.count(RANKED_HEADER) == 1, "ranked table header moved or duplicated"
    assert lines.count(BY_LAYER_HEADER) == 1, "by-layer table header moved or duplicated"
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_report_table_headers_unchanged_on_a_tmp_register(tmp_path, capsys):
    """The same two headers, on a register this test owns -- header stability is not a
    property of the committed records."""
    _write_register(tmp_path / "rep", list(CHECKED))
    out = _report_stdout(capsys, tmp_path / "rep")
    lines = out.split("\n")
    assert lines.count(RANKED_HEADER) == 1
    assert lines.count(BY_LAYER_HEADER) == 1


# ---------------------------------------------------------------------------
# Blast-radius guard, BEYOND the six numbered behaviors.
#
# The acceptance criteria demand zero byte change across seven verbs. A black-box test
# cannot compare against the pre-refactor bytes (that is the reviewer's before/after
# harness), so it asserts the INVARIANT those bytes carry instead: after a refactor whose
# whole point is that one implementation is now reached from two modules, EVERY renderer
# must still end in exactly one newline with a non-empty last line, and the refactored
# renderer must still be byte-deterministic across runs.
# ---------------------------------------------------------------------------

def _one_newline(out, label):
    assert out, f"{label}: empty document"
    assert out.endswith("\n"), f"{label}: document does not end in a newline"
    assert not out.endswith("\n\n"), f"{label}: document ends in a blank line"
    assert out.splitlines()[-1].strip() != "", f"{label}: last line is blank"


@pytest.fixture()
def register_root(tmp_path):
    """A root holding `gaps/`, for the root-taking verbs."""
    _write_register(tmp_path / "root", list(CHECKED))
    return tmp_path / "root"


@pytest.mark.parametrize(
    "argv_of",
    [
        lambda root, target, reg: ["validate", str(root)],
        lambda root, target, reg: ["list", str(root)],
        lambda root, target, reg: ["report", str(root)],
        lambda root, target, reg: ["show", "GAP-600", str(root)],
        lambda root, target, reg: ["prd", str(root)],
        lambda root, target, reg: ["taxonomy"],
        lambda root, target, reg: ["scan", str(target), "--gaps", str(reg)],
        lambda root, target, reg: ["scan", str(target), "--gaps", str(reg), "--json"],
    ],
    ids=["validate", "list", "report", "show", "prd", "taxonomy", "scan", "scan --json"])
def test_every_renderer_still_ends_in_exactly_one_newline(
        register_root, tmp_path, capsys, argv_of):
    reg = register_root / "gaps"
    target = _target(tmp_path / "root", body=MARKER)
    argv = argv_of(register_root, target, reg)
    rc = main(argv)
    cap = capsys.readouterr()
    assert rc == 0, f"{argv[0]} exited {rc}: {cap.err}"
    _one_newline(cap.out, argv[0])


def test_diff_still_ends_in_exactly_one_newline(tmp_path, capsys):
    _write_register(tmp_path / "old", list(CHECKED))
    _write_register(tmp_path / "new", [CHECKED[0]])
    rc = main(["diff", str(tmp_path / "old"), str(tmp_path / "new")])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    _one_newline(cap.out, "diff")


def test_scan_is_byte_deterministic_across_runs(tmp_path, capsys):
    first = _scan_stdout(tmp_path, capsys, "det1", MARKER)
    second = _scan_stdout(tmp_path, capsys, "det2", MARKER)
    assert first.replace("det1", "det2") == second
