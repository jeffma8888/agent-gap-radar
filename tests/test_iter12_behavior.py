"""Iteration 12 behaviors: the RECOVERY iteration, whose only authored bytes are bookkeeping.

Iteration 11 built `radar diff OLD NEW`, it was reviewed APPROVE and tested green, and its
ship commit WAS created -- then the stage cap killed the final stage six seconds later, no
verdict token was written, and the loop reset the tree. A whole user-facing verb was absent
from the product while the roadmap still read `open`. This iteration restores that commit
unchanged and corrects the Done ledger so the hole it leaves in git history is explicable
from the published document alone.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every assertion either reads a
PUBLISHED document (`PRODUCT.md`, owned by the planning role) or runs the product in a
SEPARATE PROCESS and observes only its exit code, its stdout bytes and its stderr bytes.

What this module deliberately does NOT assert, and why. Both are spec behaviors that are
true only in the window between the engineer and the ship commit, so committing either one
would redden the suite the moment the gate commits:

* behavior 1 -- the eight restored paths are byte-identical to the orphaned commit -- names
  a DANGLING object. A committed test pinning that sha dies at the next `git gc --prune`,
  and reading the delta is what the isolation contract forbids. It is a one-shot
  measurement, reported in the tester note, never a suite assertion.
* behavior 10 -- `HEAD` unmoved and `git status --short` listing exactly nine paths --
  describes a DIRTY tree. Asserting it would assert that this iteration never ships.

Habits kept on purpose:

* every roadmap check is a pure function over text, and each is proven ARMED by re-running
  it over a MUTATION of the live document -- a reader that cannot fail is a comment. Every
  mutation asserts its own premise, so a silently no-op replace cannot turn a known-bad
  fixture into a copy of the known-good one;
* the arming half is a SWEEP, not a hand-picked case: every required token in each ledger
  row is deleted in turn and must be reported missing, so a reader that only ever looks at
  the first token cannot pass;
* the row counts are taken in TWO units -- ledger-section rows and raw whole-document
  occurrences -- because a check keyed on the ledger section cannot see a duplicate row
  pasted outside it;
* the process-boundary tests exist because iteration 11's own tests drive `main()`
  IN-PROCESS with `capsys`. That proves the function. It cannot prove that the exit code
  reaches a shell, that the real stdout stream ends in exactly ONE newline, or that a usage
  error writes ZERO bytes to stdout -- and the spec's behaviors 2, 3 and 5 are written as
  `uv run radar diff ...`, which is only observable across that boundary;
* the register pairs those tests run over are SYNTHETIC, never the live register. The live
  one is grown by a schedule, and a check whose expectation is keyed on today's records is
  the landmine roadmap row 27 exists to remove. The one test that does read the live
  register asserts a SELF-diff reports nothing, which stays true at any record count;
* every "nothing was reported" assertion has an anti-vacuity companion over the same shape
  with one closed field moved. `Changed (0)` is also what a verb that reports nothing at
  all prints.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "PRODUCT.md"

#: This iteration and the one it recovers. Behaviors 7 and 8 are written about these two.
THIS_ITERATION = "12"
PRIOR_ITERATION = "11"

LEDGER_HEADING = "## Done ledger"

#: What the installed console script does: `radar = agent_gap_radar.cli:main`. Spelled as
#: `-c` rather than the venv script so the process boundary is exercised without depending
#: on an installed entry point, and so `main()` is reached through its own `sys.argv` path.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

LEDGER_ROW = re.compile(r"^- iter (?P<iteration>\S+)(?: (?P<rest>.*))?$")
TABLE_ROW = re.compile(r"^\|(?P<cells>.*)\|$")
HEADING = re.compile(r"^## (?P<name>[A-Za-z]+) \((?P<count>\d+)\)$")
NESTED_ROW = re.compile(r"^  - (?P<field>[a-z_]+): (?P<old>.+) -> (?P<new>.+)$")

#: Behavior 8's content requirements, as patterns rather than verbatim prose: the spec
#: fixes what each row must SAY, not how it is worded. Each is swept as a known-bad.
ITER11_TOKENS = {
    "built": re.compile(r"built", re.IGNORECASE),
    "reviewed": re.compile(r"reviewed", re.IGNORECASE),
    "approve": re.compile(r"approve", re.IGNORECASE),
    "tested": re.compile(r"tested", re.IGNORECASE),
    "never-shipped": re.compile(r"orphan|never landed|did not land|was not landed",
                               re.IGNORECASE),
    "re-lander-named": re.compile(r"iter(?:ation)? 12", re.IGNORECASE),
}
ITER12_TOKENS = {
    "re-lands": re.compile(r"re-land", re.IGNORECASE),
    "unchanged": re.compile(r"unchanged", re.IGNORECASE),
    "no-new-behaviour": re.compile(r"(?:zero|no) new behaviou?r", re.IGNORECASE),
    "names-iteration-11": re.compile(r"iter(?:ation)? 11", re.IGNORECASE),
}

#: Behavior 9's preamble requirements. The forbidden phrase is the one the document
#: carried while it claimed one row per SHIPPED iteration and then grew a row for an
#: iteration that did not ship.
PREAMBLE_FORBIDDEN = re.compile(r"one row per shipped iteration", re.IGNORECASE)
PREAMBLE_REQUIRED = {
    "one-row-per-iteration": re.compile(r"one row per iteration", re.IGNORECASE),
    "explains-a-row-without-a-ship": re.compile(r"never landed|did not land", re.IGNORECASE),
    "names-the-one-directional-check": re.compile(r"one-directional", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# document plumbing -- pure functions over published text, so each can be armed
# ---------------------------------------------------------------------------

def _roadmap() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _mutate(text: str, old: str, new: str) -> str:
    """Replace `old` once, asserting it was there. Guards against a vacuous fixture."""
    assert old in text, f"fixture premise broken: {old!r} is not in the document"
    mutated = text.replace(old, new, 1)
    assert mutated != text, "mutation was a no-op, so the known-bad equals the known-good"
    return mutated


def _cells(line: str) -> list[str] | None:
    match = TABLE_ROW.match(line.strip())
    if not match:
        return None
    return [cell.strip() for cell in match["cells"].split("|")]


def _row_status(text: str, row_id: str) -> str | None:
    """Status cell of the roadmap row whose id cell is `row_id`; None if there is no row."""
    matched = [cells for line in text.splitlines()
               if (cells := _cells(line)) and len(cells) >= 3 and cells[0] == row_id]
    assert len(matched) <= 1, f"row {row_id} appears {len(matched)} times"
    return matched[0][2] if matched else None


def _ledger_section(text: str) -> str:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line.strip() == LEDGER_HEADING]
    assert len(starts) == 1, f"{LEDGER_HEADING!r} occurs {len(starts)} times, not once"
    body: list[str] = []
    for line in lines[starts[0] + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _ledger_rows(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in _ledger_section(text).splitlines():
        match = LEDGER_ROW.match(line.strip())
        if match:
            rows.append((match["iteration"], match["rest"] or ""))
    return rows


def _row_for(text: str, iteration: str) -> str:
    matched = [rest for number, rest in _ledger_rows(text) if number == iteration]
    assert len(matched) == 1, f"iter {iteration} has {len(matched)} ledger rows, not one"
    return matched[0]


def _sequence_findings(rows: list[tuple[str, str]]) -> list[str]:
    """Behavior 8's numbering rules, as findings so the reader can be shown to fire."""
    findings: list[str] = []
    seen: list[str] = []
    for iteration, _ in rows:
        if not (len(iteration) == 2 and iteration.isdigit()):
            findings.append(f"not-two-digit:{iteration}")
        elif iteration in seen:
            findings.append(f"duplicate:{iteration}")
        elif seen and seen[-1].isdigit() and int(iteration) <= int(seen[-1]):
            findings.append(f"not-ascending:{iteration}")
        seen.append(iteration)
    return findings


def _preamble(text: str) -> str:
    """The ledger section's prose, i.e. everything before its first `- iter` row."""
    section = _ledger_section(text)
    lines = section.splitlines()
    first_row = next((index for index, line in enumerate(lines)
                      if LEDGER_ROW.match(line.strip())), len(lines))
    return "\n".join(lines[:first_row])


def _preamble_findings(text: str) -> list[str]:
    preamble = _preamble(text)
    findings: list[str] = []
    if PREAMBLE_FORBIDDEN.search(preamble):
        findings.append("claims-one-row-per-shipped-iteration")
    findings.extend(name for name, pattern in PREAMBLE_REQUIRED.items()
                    if not pattern.search(preamble))
    return findings


def _missing_tokens(row: str, tokens: dict[str, re.Pattern[str]]) -> list[str]:
    return [name for name, pattern in tokens.items() if not pattern.search(row)]


# ---------------------------------------------------------------------------
# process plumbing -- the product is RUN, and only its bytes are read
# ---------------------------------------------------------------------------

def _run(*argv: str, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, "-c", BOOT, *argv],
                          cwd=str(cwd or REPO_ROOT), capture_output=True, timeout=180)


EVIDENCE = {
    "source_class": "first-party-field",
    "title": "an incident write-up",
    "locator": "https://example.invalid/inc",
    "date": "2026-01-02",
    "quote": "the verbatim line",
}


def _record(gid: str, **over) -> dict:
    record = {
        "id": gid, "title": f"the {gid} problem", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [dict(EVIDENCE)],
    }
    record.update(over)
    return record


def _register(root: pathlib.Path, records: list[dict], *, reverse_names: bool = False):
    """Materialise `<root>/gaps/` and return `root`. `reverse_names` touches FILENAMES only."""
    gaps = root / "gaps"
    gaps.mkdir(parents=True)
    total = len(records)
    for index, record in enumerate(records):
        name = f"{total - index:03d}-record.json" if reverse_names else f"{record['id']}.json"
        (gaps / name).write_text(json.dumps(record), encoding="utf-8")
    return root


def _pair(tmp_path: pathlib.Path, *, moved: bool, reverse_names: bool = False):
    """Two synthetic registers. `moved` shifts two DERIVED values on one record."""
    old = [_record("GAP-001"), _record("GAP-002")]
    if moved:
        new = [_record("GAP-001"),
               _record("GAP-002", severity=5,
                       evidence=[{**EVIDENCE, "source_class": "secondary-summary"}])]
    else:
        new = [_record("GAP-001"), _record("GAP-002")]
    suffix = "-alt" if reverse_names else ""
    return (_register(tmp_path / f"old{suffix}", old, reverse_names=reverse_names),
            _register(tmp_path / f"new{suffix}", new, reverse_names=reverse_names))


class _Section(tuple):
    pass


def _sections(document: str) -> list[tuple[str, int, tuple[str, ...]]]:
    sections: list[tuple[str, int, tuple[str, ...]]] = []
    name: str | None = None
    count = 0
    body: list[str] = []
    for line in document.splitlines():
        if line.startswith("## "):
            if name is not None:
                sections.append((name, count, tuple(body)))
            match = HEADING.match(line)
            assert match, f"heading {line!r} is not `## <Name> (<n>)`"
            name, count, body = match["name"], int(match["count"]), []
        elif name is not None and line.strip():
            body.append(line)
    if name is not None:
        sections.append((name, count, tuple(body)))
    return sections


def _document(proc: subprocess.CompletedProcess[bytes]) -> str:
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert proc.stderr == b"", proc.stderr.decode("utf-8", "replace")
    text = proc.stdout.decode("utf-8")
    assert text.startswith("# "), repr(text[:40])
    assert text.endswith("\n") and not text.endswith("\n\n"), repr(text[-4:])
    return text


# ---------------------------------------------------------------------------
# behavior 7 -- the roadmap row is flipped
# ---------------------------------------------------------------------------

def test_b7_roadmap_row_12_status_cell_is_exactly_shipped():
    assert _row_status(_roadmap(), THIS_ITERATION) == "shipped"


def test_b7_the_status_reader_is_armed_against_a_row_that_was_not_flipped():
    """The known-bad is DERIVED from the live document, not hand-written."""
    live = _roadmap()
    shipped_row = next(line for line in live.splitlines()
                       if (cells := _cells(line)) and cells[0] == THIS_ITERATION)
    mutated = _mutate(live, shipped_row, shipped_row.replace("| shipped |", "| open |", 1))
    assert _row_status(mutated, THIS_ITERATION) == "open"


# ---------------------------------------------------------------------------
# behavior 8 -- the ledger carries two rows and the iter-11 row tells the truth
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("iteration", [PRIOR_ITERATION, THIS_ITERATION])
def test_b8_exactly_one_ledger_row_per_iteration_in_both_units(iteration):
    """Section rows AND raw occurrences: a row pasted outside the section is invisible
    to the first unit, and a row quoted mid-line is invisible to the second."""
    live = _roadmap()
    assert [number for number, _ in _ledger_rows(live)].count(iteration) == 1
    assert live.count(f"- iter {iteration} ") == 1


def test_b8_the_iter_11_row_states_built_reviewed_tested_and_never_shipped():
    assert _missing_tokens(_row_for(_roadmap(), PRIOR_ITERATION), ITER11_TOKENS) == []


def test_b8_the_iter_12_row_states_an_unchanged_re_land_with_no_new_behaviour():
    assert _missing_tokens(_row_for(_roadmap(), THIS_ITERATION), ITER12_TOKENS) == []


@pytest.mark.parametrize("iteration,tokens",
                         [(PRIOR_ITERATION, ITER11_TOKENS), (THIS_ITERATION, ITER12_TOKENS)])
def test_b8_every_required_token_is_swept_as_a_known_bad(iteration, tokens):
    """Delete each required token in turn: a reader that checks only the first token, or
    a token that is matched by unrelated prose elsewhere in the row, fails here."""
    row = _row_for(_roadmap(), iteration)
    for name, pattern in tokens.items():
        stripped = pattern.sub("", row, count=1)
        assert stripped != row, f"premise broken: {name} did not match the live row"
        assert name in _missing_tokens(stripped, tokens), name


def test_b8_ledger_numbers_are_two_digit_unique_and_strictly_ascending():
    """The ledger's numbering rules, plus the historical run as an ordered PREFIX.

    Contiguity over the WHOLE ledger used to be asserted here. That was a second landmine of
    the same family as the one roadmap row 27 removed: it is derived from `len(numbers)`, so
    it looks self-updating, but it demands that the ledger be GAPLESS -- and an iteration
    that ships nothing writes no row, so the first sparse ledger reds this file from a clean
    clone of a ship commit it knows nothing about. What is actually a rule: every number is
    two-digit, unique and ascending (`_sequence_findings`, armed below), the ledger only
    grows, and the run up to this file's own iteration is contiguous and in order.
    """
    rows = _ledger_rows(_roadmap())
    assert len(rows) >= int(THIS_ITERATION), f"only {len(rows)} ledger rows"
    assert _sequence_findings(rows) == []
    numbers = [number for number, _ in rows]
    assert THIS_ITERATION in numbers, numbers
    historical = numbers[:int(THIS_ITERATION)]
    expected = [f"{index:02d}" for index in range(1, int(THIS_ITERATION) + 1)]
    assert historical == expected, historical


@pytest.mark.parametrize("kind,replacement", [
    ("duplicate", f"- iter {PRIOR_ITERATION} a duplicated row"),
    # `duplicate` and `not-ascending` OVERLAP: a fixture that reuses an existing number
    # only ever proves the duplicate branch, leaving not-ascending unproven. Two fresh
    # numbers in the wrong order isolate it.
    ("not-ascending", "- iter 14 landed\n- iter 13 recorded late"),
    ("not-two-digit", "- iter 9 a one-digit row"),
])
def test_b8_the_sequence_reader_is_armed(kind, replacement):
    live = _roadmap()
    last_row = f"- iter {THIS_ITERATION} " + _row_for(live, THIS_ITERATION)
    mutated = _mutate(live, last_row, replacement)
    findings = _sequence_findings(_ledger_rows(mutated))
    assert any(finding.startswith(kind) for finding in findings), findings


# ---------------------------------------------------------------------------
# behavior 9 -- the brake stays green and the document stops contradicting itself
# ---------------------------------------------------------------------------

def test_b9_the_roadmap_brake_reports_no_violations_at_the_process_boundary():
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "roadmap_integrity.py")],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 violation(s)" in proc.stdout, proc.stdout


def test_b9_the_brake_reports_nothing_about_this_iteration():
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "roadmap_integrity.py")],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180)
    offending = [line for line in proc.stdout.splitlines()
                 if "violation" in line.lower() and line.strip()[:1] not in {"0", ""}]
    assert offending == [], offending


def test_b9_the_ledger_preamble_no_longer_claims_one_row_per_shipped_iteration():
    assert _preamble_findings(_roadmap()) == []


def test_b9_the_preamble_reader_is_armed_against_the_wording_it_replaced():
    live = _roadmap()
    preamble = _preamble(live)
    mutated = _mutate(live, preamble,
                      _mutate(preamble, "One row per iteration",
                              "One row per shipped iteration"))
    findings = _preamble_findings(mutated)
    assert "claims-one-row-per-shipped-iteration" in findings, findings
    assert "one-row-per-iteration" in findings, findings


@pytest.mark.parametrize("name", sorted(PREAMBLE_REQUIRED))
def test_b9_every_required_preamble_clause_is_swept_as_a_known_bad(name):
    live = _roadmap()
    preamble = _preamble(live)
    match = PREAMBLE_REQUIRED[name].search(preamble)
    assert match, f"premise broken: {name} does not match the live preamble"
    # Scoped to the preamble: the same phrase may legitimately appear in a row note, and
    # deleting THAT occurrence would leave the preamble intact and this sweep vacuous.
    mutated = _mutate(live, preamble, PREAMBLE_REQUIRED[name].sub("", preamble, count=1))
    assert name in _preamble_findings(mutated), _preamble_findings(mutated)


# ---------------------------------------------------------------------------
# behaviors 2-6 at the PROCESS boundary -- iteration 11 proves them in-process
# ---------------------------------------------------------------------------

def test_b2_the_verb_emits_one_document_over_a_valid_pair(tmp_path):
    old, new = _pair(tmp_path, moved=True)
    document = _document(_run("diff", str(old), str(new)))
    assert len(document.splitlines()) > 1, document


@pytest.mark.parametrize("sides", [0, 1], ids=["zero-positionals", "one-positional"])
def test_b3_a_missing_side_exits_2_with_usage_and_zero_stdout_bytes(tmp_path, sides):
    old, _ = _pair(tmp_path, moved=False)
    proc = _run("diff", *([str(old)] if sides else []))
    assert proc.returncode == 2, (proc.returncode, proc.stderr.decode())
    assert proc.stdout == b"", proc.stdout[:120]
    assert b"usage" in proc.stderr.lower(), proc.stderr[:200]


def test_b4_the_live_register_diffed_against_itself_reports_no_change():
    document = _document(_run("diff", ".", "."))
    sections = _sections(document)
    assert len(sections) == 3, [name for name, _, _ in sections]
    for name, count, body in sections:
        assert count == 0, (name, count)
        assert body, f"section {name} rendered no body; an omitted empty section cannot be"
    assert re.findall(r"GAP-\d+", document) == [], document


def test_b4_anti_vacuity_the_same_shape_reports_a_change_when_a_closed_field_moves(tmp_path):
    old, new = _pair(tmp_path, moved=True)
    document = _document(_run("diff", str(old), str(new)))
    counts = {name: count for name, count, _ in _sections(document)}
    assert sum(counts.values()) == 1, counts
    assert "GAP-002" in document, document


def test_b5_two_runs_over_the_same_pair_are_byte_identical(tmp_path):
    old, new = _pair(tmp_path, moved=True)
    first = _run("diff", str(old), str(new))
    second = _run("diff", str(old), str(new))
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout


def test_b5_the_directory_and_file_names_neither_appear_in_nor_alter_the_output(tmp_path):
    plain_old, plain_new = _pair(tmp_path, moved=True)
    alt_old, alt_new = _pair(tmp_path, moved=True, reverse_names=True)
    plain = _run("diff", str(plain_old), str(plain_new)).stdout
    alternate = _run("diff", str(alt_old), str(alt_new)).stdout
    assert plain == alternate, (plain[:400], alternate[:400])
    text = plain.decode("utf-8")
    for leaked in (plain_old.name, plain_new.name, alt_old.name, alt_new.name,
                   "001-record.json", str(tmp_path)):
        assert leaked not in text, leaked


def test_b6_priority_and_confidence_are_two_separate_lines_and_are_never_blended(tmp_path):
    old, new = _pair(tmp_path, moved=True)
    document = _document(_run("diff", str(old), str(new)))
    fields = [match["field"] for line in document.splitlines()
              if (match := NESTED_ROW.match(line))]
    assert fields.count("priority") == 1, fields
    assert fields.count("confidence") == 1, fields
    assert not any("priority" in line and "confidence" in line
                   for line in document.splitlines()), document
    for blended in ("combined", "blended", "overall", "composite"):
        assert blended not in document.lower(), blended


# ---------------------------------------------------------------------------
# behaviors 2-4 continued -- the ANTI-VACUITY half the moved-field pair cannot reach,
# and the product quality bar on the new verb's error paths
# ---------------------------------------------------------------------------

def _triple(tmp_path: pathlib.Path):
    """A pair that populates ALL THREE sections at once: one added, one removed, one
    changed. The `moved`-only pair reaches `Changed` and nothing else, so `Added` and
    `Removed` are proven to render their EMPTY form (behavior 4) and never their full
    one -- a renderer that hard-coded `None.` for those two would pass every other test
    in this module."""
    old = [_record("GAP-001"), _record("GAP-002")]
    new = [_record("GAP-002", severity=5), _record("GAP-003")]
    return (_register(tmp_path / "three-old", old),
            _register(tmp_path / "three-new", new))


def _entries(body: tuple[str, ...]) -> list[str]:
    """Top-level record entries in a section body, excluding nested `  - field:` rows."""
    return [line for line in body if line.startswith("- ")]


@pytest.mark.parametrize("section", ["Added", "Removed", "Changed"])
def test_b4_anti_vacuity_every_section_renders_a_NON_empty_form_too(tmp_path, section):
    """Behavior 4 fixes the empty form. Its companion: each section must also be able to
    carry a record, and its heading count must equal what its body actually lists."""
    old, new = _triple(tmp_path)
    document = _document(_run("diff", str(old), str(new)))
    found = {name: (count, body) for name, count, body in _sections(document)}
    assert section in found, sorted(found)
    count, body = found[section]
    assert count == 1, (section, count, body)
    assert len(_entries(body)) == 1, (section, body)
    assert "None." not in body, (section, body)


def test_b4_the_three_sections_report_disjoint_records_in_a_fixed_order(tmp_path):
    """An added id may not also be reported as changed, and the order is part of the
    byte-stable contract behavior 5 rests on."""
    old, new = _triple(tmp_path)
    document = _document(_run("diff", str(old), str(new)))
    order = [name for name, _, _ in _sections(document)]
    assert order == ["Added", "Removed", "Changed"], order
    per_section = {name: set(re.findall(r"GAP-\d+", "\n".join(body)))
                   for name, _, body in _sections(document)}
    assert per_section == {"Added": {"GAP-003"}, "Removed": {"GAP-001"},
                           "Changed": {"GAP-002"}}, per_section


@pytest.mark.parametrize("kind", ["invalid-json", "missing-directory"])
def test_the_error_paths_hold_the_product_bar_exit_2_error_prefix_and_empty_stdout(
        tmp_path, kind):
    """Product quality bar, on surface this iteration lands: errors go to stderr prefixed
    `Error: ` with exit 2, and stdout carries ONLY a document -- so a failed run must emit
    ZERO stdout bytes rather than a half-written one. Behavior 3 covers only the argparse
    usage path, which never reaches the register loader at all."""
    _, new = _triple(tmp_path)
    if kind == "invalid-json":
        broken = _register(tmp_path / "broken", [])
        (broken / "gaps" / "GAP-009.json").write_text("{ not json", encoding="utf-8")
        left = broken
    else:
        left = tmp_path / "absent-directory"
        assert not left.exists()
    proc = _run("diff", str(left), str(new))
    assert proc.returncode == 2, (proc.returncode, proc.stderr.decode("utf-8", "replace"))
    assert proc.stdout == b"", proc.stdout[:200]
    assert proc.stderr.startswith(b"Error: "), proc.stderr[:200]


def test_b3_exactly_two_positionals_a_third_is_also_a_usage_error(tmp_path):
    """Behavior 3 forbids fewer than two sides. The upper bound matters for the same
    reason: a silently ignored third path would let a caller believe it was compared."""
    old, new = _triple(tmp_path)
    proc = _run("diff", str(old), str(new), str(old))
    assert proc.returncode == 2, (proc.returncode, proc.stderr.decode("utf-8", "replace"))
    assert proc.stdout == b"", proc.stdout[:200]
    assert b"usage" in proc.stderr.lower(), proc.stderr[:200]


# ---------------------------------------------------------------------------
# this module may not stand down
# ---------------------------------------------------------------------------

def test_no_test_in_this_module_stands_down():
    """A skipped test is invisible in a suite total, so this module may not skip."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for marker in ("pytest.mark." + "skip", "pytest.mark." + "xfail",
                   "pytest." + "skip(", "pytest." + "xfail("):
        assert marker not in source, marker
