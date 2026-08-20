"""Iteration 25 behaviors: a reader that stops reading no longer decides the exit code.

A `radar` verb whose stdout pipe is gone returns **141** with an EMPTY stderr, instead of
CPython's shutdown code 120 plus an `Exception ignored on flushing sys.stdout` line, or
exit 1 plus a raw `BrokenPipeError` traceback once the document outgrows the pipe buffer.
`docs/CONSUMER_CONTRACT.md` publishes the complete code set, asserted EQUAL to
`cli.EXIT_CODES` in both directions.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every expectation comes from
`pm.md`'s Expected Behaviors; every claim was measured by RUNNING the packaged entry point,
calling `cli.main()` with a replaced `sys.stdout`, or reading `tests/` and
`docs/CONSUMER_CONTRACT.md` AS DATA.

Structural notes, so this file cannot lie later:

* **The over-the-pipe-buffer fixture has a MEASURED floor, and 65,536 is not it.** A
  buffered parent reader absorbs up to `io.DEFAULT_BUFFER_SIZE` more, so a 72,682-byte
  document read by a default `Popen` reader completes and BOTH code trees exit 0 -- the
  probe goes vacuous and reports "no defect". Measured this iteration: the same fixture
  read UNBUFFERED gives 1-plus-traceback before the change and 141 after. So the reader is
  `bufsize=0` AND the fixture must clear `PIPE_PLUS_READER_BYTES`, asserted before use.
* **Every broken-pipe assertion is paired with a live-reader CONTROL** in the same test or
  its immediate neighbour. A 141-only probe cannot tell "the guard ran" from "the verb was
  broken all along", so each fixture is first shown to exit 0 and produce bytes.
* **The guard's narrowness is pinned as behavior, not prose** (behavior 6): a non-EPIPE
  `OSError` must still propagate, so a successor cannot widen this into `except OSError`.
* **Nothing asserts a literal record count.** The register is fed by a recurring research
  pass, so record ids are DERIVED from the files on disk and sizes are derived from the
  rendered document.
* **"Byte-identical to HEAD" (behavior 7) cannot be observed by a test in one revision.**
  What is asserted here is the mechanism that would break first -- exit 0, exactly one
  trailing newline, and byte-determinism across two runs. The HEAD-vs-working-tree byte
  comparison across 11 invocations was run in the tester stage, with a positive control,
  and is reported in `tester.md`.
"""

from __future__ import annotations

import errno
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from agent_gap_radar import cli

from _surface_contract import SurfaceContractError, contract_text, gfm_table

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`). Same boot line as `test_iter12_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: Behavior 1 and the contract's own `## Exit codes` table.
EXPECTED_BROKEN_PIPE = 141

#: A pipe holds this much on the platforms this repo targets; the writer blocks past it.
PIPE_BUFFER_BYTES = 65536

#: MEASURED, and the reason behavior 3's fixture floor is not just the pipe buffer: a
#: default `Popen` reader slurps up to one buffer more before the test closes it, so a
#: document under `PIPE_BUFFER_BYTES + io.DEFAULT_BUFFER_SIZE` can be written IN FULL and
#: both code trees exit 0. 72,682 bytes did exactly that in this iteration.
PIPE_PLUS_READER_BYTES = PIPE_BUFFER_BYTES + io.DEFAULT_BUFFER_SIZE

#: The register's id format allows GAP-001..GAP-999, so this is its largest fixture.
BIG_REGISTER_RECORDS = 999

#: Behavior 2's forbidden stderr strings, quoted from the spec.
LEAKED_INTERNALS = ("Exception ignored on flushing sys.stdout", "BrokenPipeError",
                    "Traceback")

#: A backticked integer in the contract's Code column, e.g. `` `141` ``.
BACKTICKED_INT = re.compile(r"`(\d+)`")


def _record_ids() -> list[str]:
    """Every id in the live register, read off disk rather than hard-coded."""
    ids = []
    for path in sorted(LIVE_GAPS.glob("GAP-*.json")):
        ids.append(json.loads(path.read_text(encoding="utf-8"))["id"])
    assert ids, f"no records under {LIVE_GAPS.name}; every probe below would be vacuous"
    return sorted(ids)


SOME_ID = _record_ids()[0]

#: Behaviors 1-2 and 7: one invocation per shipped human/JSON surface, plus the implicit
#: help write argparse does for itself. `prd` keeps the spec's own `GAP-003` because it
#: must SUCCEED for the pipe to break at all -- if the register ever loses that record the
#: success-path test fails loudly instead of passing over a refusal.
def _argvs() -> list[list[str]]:
    repo = str(REPO_ROOT)
    return [
        ["report", repo],
        ["list", repo],
        ["list", repo, "--json"],
        ["show", SOME_ID, repo],
        ["validate", repo],
        ["taxonomy"],
        ["prd", repo, "--gap", "GAP-003"],
        ["scan", repo],
        [],
    ]


def _ids(argvs: list[list[str]]) -> list[str]:
    return [" ".join(a).replace(str(REPO_ROOT), "<repo>") or "<no args>" for a in argvs]


ARGVS = _argvs()


def _run(*argv: str) -> subprocess.CompletedProcess[bytes]:
    """The packaged entry point with a LIVE reader -- every probe's control."""
    return subprocess.run([sys.executable, "-c", BOOT, *argv],
                          cwd=str(REPO_ROOT), capture_output=True, timeout=180)


def _run_with_closed_reader(*argv: str) -> tuple[int, bytes]:
    """Spawn the CLI with a stdout pipe whose read end this process closes at once.

    `os.pipe()` rather than `stdout=PIPE` so the read end is closed by fd number before
    any Python-level buffer can absorb the document: once no reader holds the pipe, the
    child's first real write gets EPIPE no matter how small the document is.
    """
    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen([sys.executable, "-c", BOOT, *argv], stdout=write_fd,
                            stderr=subprocess.PIPE, cwd=str(REPO_ROOT))
    os.close(write_fd)
    os.close(read_fd)
    assert proc.stderr is not None
    err = proc.stderr.read()
    proc.stderr.close()
    return proc.wait(timeout=180), err


def _big_register(root: pathlib.Path) -> tuple[pathlib.Path, int]:
    """A register whose rendered report clears `PIPE_PLUS_READER_BYTES`, and that size.

    Built by duplicating a live record under fresh ids, so the fixture stays inside the
    schema the CLI enforces (`GAP-\\d{3}`) and needs no invented content.
    """
    source = json.loads(sorted(LIVE_GAPS.glob("GAP-*.json"))[0].read_text(encoding="utf-8"))
    gaps = root / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    for n in range(1, BIG_REGISTER_RECORDS + 1):
        record = json.loads(json.dumps(source))
        record["id"] = f"GAP-{n:03d}"
        (gaps / f"{record['id']}.json").write_text(json.dumps(record), encoding="utf-8")
    control = _run("report", str(root))
    assert control.returncode == 0, control.stderr
    size = len(control.stdout)
    assert size > PIPE_PLUS_READER_BYTES, (
        f"fixture renders {size} bytes, which a buffered reader can absorb whole "
        f"(floor {PIPE_PLUS_READER_BYTES}); pad the records or the probe is vacuous")
    return root, size


def _early_exiting_reader(target: str, lines: int = 2) -> tuple[int, bytes]:
    """Read `lines` lines, then close the pipe -- what `head -2` does to the writer.

    `bufsize=0`: a buffered reader would absorb up to one more buffer of the document and
    the writer could finish, which is exactly how this probe went vacuous when measured.
    """
    proc = subprocess.Popen([sys.executable, "-c", BOOT, "report", target],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                            cwd=str(REPO_ROOT))
    assert proc.stdout is not None and proc.stderr is not None
    read = [proc.stdout.readline() for _ in range(lines)]
    assert read[0], "the writer produced nothing, so nothing could break"
    proc.stdout.close()
    err = proc.stderr.read()
    proc.stderr.close()
    return proc.wait(timeout=180), err


# ------------------------------------------------ behavior 1: closed reader, exit code

@pytest.mark.parametrize("argv", ARGVS, ids=_ids(ARGVS))
def test_b1_a_closed_reader_makes_every_verb_exit_141(argv):
    """Behavior 1. At HEAD all of these exit 120; the spec fixes 141."""
    control = _run(*argv)
    assert control.returncode == 0, control.stderr
    assert control.stdout, "no document, so no write could break"
    code, _err = _run_with_closed_reader(*argv)
    assert code == EXPECTED_BROKEN_PIPE, f"{argv} exited {code}, expected 141"


# ------------------------------------------------ behavior 2: closed reader, silent stderr

@pytest.mark.parametrize("argv", ARGVS, ids=_ids(ARGVS))
def test_b2_a_closed_reader_leaks_nothing_to_stderr(argv):
    """Behavior 2: stderr is zero bytes -- no shutdown notice, no exception name."""
    code, err = _run_with_closed_reader(*argv)
    assert code == EXPECTED_BROKEN_PIPE, code
    assert err == b"", f"{argv} wrote {err!r} to stderr"
    for leaked in LEAKED_INTERNALS:
        assert leaked.encode() not in err, leaked


def test_b2_the_probe_can_see_a_leak_when_there_is_one():
    """Positive control for behavior 2's emptiness assertion.

    `err == b""` proves nothing unless the harness is known to CAPTURE stderr, so the same
    reader is pointed at a refusal, which must produce a non-empty `Error: ` line.
    """
    code, err = _run_with_closed_reader("validate", str(REPO_ROOT / "no-such-dir"))
    assert code == 2, code
    assert err.startswith(b"Error: "), err


# ------------------------- behavior 3: an early-exiting reader above the pipe buffer

def test_b3_an_early_exiting_reader_above_the_pipe_buffer_gets_141(tmp_path):
    """Behavior 3, the form that is LATENT at today's register size."""
    target, size = _big_register(tmp_path)
    code, err = _early_exiting_reader(str(target))
    assert code == EXPECTED_BROKEN_PIPE, f"{size}-byte document exited {code}, expected 141"
    assert b"Traceback" not in err, err
    assert b"BrokenPipeError" not in err, err
    assert err == b"", err


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("head")),
                    reason="needs a shell with PIPESTATUS and head to read the writer's code")
def test_b3_a_real_head_2_pipeline_reports_141_for_the_radar_process(tmp_path):
    """Behavior 3 through the literal command the spec names, `... | head -2`.

    The pure-Python reader above is the portable version; this one proves the code a real
    shell pipeline observes, read out of `PIPESTATUS[0]` so `head`'s own 0 cannot mask it.
    """
    target, _size = _big_register(tmp_path)
    script = ('set -o pipefail; "$1" -c "$2" report "$3" | head -2 >/dev/null; '
              'echo "RC=${PIPESTATUS[0]}"')
    proc = subprocess.run(["bash", "-c", script, "bash", sys.executable, BOOT, str(target)],
                          capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT))
    assert proc.stdout.strip().endswith(f"RC={EXPECTED_BROKEN_PIPE}"), (
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "BrokenPipeError" not in proc.stderr, proc.stderr


def test_b3_the_big_fixture_is_a_normal_document_with_a_live_reader(tmp_path):
    """Control for behavior 3: the same fixture read to the end is an ordinary success."""
    target, size = _big_register(tmp_path)
    proc = _run("report", str(target))
    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout) == size
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")
    assert proc.stderr == b""


# ------------------- behavior 4: a departing reader is never reported as this tool's error

@pytest.mark.parametrize("argv", ARGVS, ids=_ids(ARGVS))
def test_b4_a_departing_reader_is_never_an_error_of_this_tool(argv):
    """Behavior 4 for the closed-reader form: no `Error: `, and the code is not 2."""
    code, err = _run_with_closed_reader(*argv)
    assert b"Error: " not in err, err
    assert code != 2, "exit 2 is reserved for a refusal the tool explains in words"
    assert code == EXPECTED_BROKEN_PIPE, code


def test_b4_a_departing_reader_above_the_buffer_is_never_an_error_either(tmp_path):
    """Behavior 4 for the over-the-buffer form."""
    target, _size = _big_register(tmp_path)
    code, err = _early_exiting_reader(str(target))
    assert b"Error: " not in err, err
    assert code != 2
    assert code == EXPECTED_BROKEN_PIPE, code


# ------------------- behavior 5: the guard is on the packaged entry point, in-process

#: The heading the contract publishes its code table under, and that table's key column.
EXIT_CODES_HEADING = "## Exit codes"
CODE_COLUMN = "Code"


class _RaisingStdout(io.StringIO):
    """A `sys.stdout` whose every write raises, the way a closed pipe's does.

    A `StringIO` subclass on purpose: its inherited `fileno()` raises
    `io.UnsupportedOperation`, which is exactly the "no real `fileno()`" case the spec
    says the guard must survive without raising. `writes` is counted so a probe can tell
    "the guard swallowed the error" from "nothing was ever written".
    """

    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self._exc = exc
        self.writes = 0

    def write(self, s):  # type: ignore[override]
        self.writes += 1
        raise self._exc


def _main_with_raising_stdout(exc: BaseException,
                              argv: list[str]) -> tuple[int, _RaisingStdout]:
    """`cli.main(argv)` with a stdout that raises `exc`, fd 1 restored afterwards.

    fd 1 is duplicated and put back in `finally` because the spec's own acceptance
    criteria have the 141 path point the PROCESS's stdout descriptor at the null device.
    That is right for a real run and would silence the rest of this pytest worker, so the
    descriptor is restored whether the call returns or raises.
    """
    fake = _RaisingStdout(exc)
    real, saved_fd = sys.stdout, os.dup(1)
    sys.stdout = fake
    try:
        return cli.main(argv), fake
    finally:
        sys.stdout = real
        os.dup2(saved_fd, 1)
        os.close(saved_fd)


def test_b5_main_returns_141_in_process_and_says_nothing(capsys):
    """Behavior 5: the guard lives in `main`, so the packaged entry point returns 141.

    `project.scripts` binds `radar` to `agent_gap_radar.cli:main`, so a guard confined to
    an `if __name__ == "__main__"` block would leave the installed console script -- and
    any in-process consumer -- with the raw exception this asserts is absorbed.
    """
    capsys.readouterr()
    code, fake = _main_with_raising_stdout(
        BrokenPipeError(errno.EPIPE, "Broken pipe"), ["report", str(REPO_ROOT)])
    captured = capsys.readouterr()
    assert code == EXPECTED_BROKEN_PIPE, code
    assert code == cli.EXIT_BROKEN_PIPE
    assert fake.writes >= 1, "stdout was never written, so no pipe error could be raised"
    assert captured.err == "", f"the guard wrote {captured.err!r} to stderr"


def test_b5_the_in_process_probe_can_see_a_return_value_it_did_not_force(capsys):
    """Positive control for behavior 5: the same harness with a WORKING stdout is a 0.

    Without this, `== 141` cannot be told from a harness that returns 141 for anything.
    """
    capsys.readouterr()
    real, saved_fd = sys.stdout, os.dup(1)
    sink = io.StringIO()
    sys.stdout = sink
    try:
        code = cli.main(["report", str(REPO_ROOT)])
    finally:
        sys.stdout = real
        os.dup2(saved_fd, 1)
        os.close(saved_fd)
    assert code == cli.EXIT_OK == 0, code
    assert sink.getvalue().endswith("\n")


# ------------------------- behavior 6: the guard is narrow -- only a broken pipe is absorbed

def test_b6_a_non_epipe_oserror_still_propagates(capsys):
    """Behavior 6, two-sided against an over-broad `except OSError`.

    A permission error on stdout is a real fault a consumer must see; converting it to
    141 would report the reader as gone when the reader is fine.
    """
    capsys.readouterr()
    with pytest.raises(OSError) as raised:
        _main_with_raising_stdout(OSError(errno.EACCES, "boom"), ["report", str(REPO_ROOT)])
    assert not isinstance(raised.value, BrokenPipeError)
    assert raised.value.errno == errno.EACCES
    assert "boom" in str(raised.value)


# ------------------------- behavior 7: every success path is unchanged and byte-stable

@pytest.mark.parametrize("argv", ARGVS, ids=_ids(ARGVS))
def test_b7_every_success_path_exits_0_and_ends_in_exactly_one_newline(argv):
    """Behavior 7's assertable half: exit 0, one trailing newline, identical bytes twice.

    "Byte-identical to HEAD" cannot be observed by a test living in ONE revision, so what
    is pinned here is the mechanism that would break first if the guard leaked into the
    success path: the code, the single trailing newline this repo's quality bar names, and
    determinism across two runs. The HEAD-vs-working-tree byte diff is a stage-level A/B
    and is reported in the tester report.
    """
    first = _run(*argv)
    assert first.returncode == 0, first.stderr
    assert first.stdout, "a success path produced no document"
    assert first.stdout.endswith(b"\n"), "document does not end in a newline"
    assert not first.stdout.endswith(b"\n\n"), "document ends in more than one newline"
    second = _run(*argv)
    assert second.stdout == first.stdout, "two runs of the same verb differ"
    assert second.returncode == 0


def test_b7_no_arguments_still_prints_help_and_exits_0():
    """Behavior 7's last clause: argparse's own help write is inside the guard's reach."""
    proc = _run()
    assert proc.returncode == 0, proc.stderr
    assert b"usage:" in proc.stdout
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")


# ------------------------- behavior 8: every failure path still exits 2 with one Error: line

def test_b8_validate_over_an_empty_directory_exits_2_with_one_error_line(tmp_path):
    """Behavior 8: a refusal the tool can explain in words keeps its documented shape."""
    proc = _run("validate", str(tmp_path))
    assert proc.returncode == cli.EXIT_ERROR == 2, proc.returncode
    assert proc.stdout == b"", f"stdout carried {proc.stdout!r} on a refusal"
    lines = proc.stderr.decode().splitlines()
    assert len(lines) == 1, lines
    assert lines[0] == f"Error: no gap records found in {tmp_path}", lines[0]


def test_b8_a_nonexistent_gaps_path_exits_2_with_one_error_line(tmp_path):
    """Behavior 8's second clause, on the `--gaps` option a gate passes."""
    missing = tmp_path / "no-such-register"
    proc = _run("scan", str(REPO_ROOT), "--gaps", str(missing))
    assert proc.returncode == cli.EXIT_ERROR == 2, proc.returncode
    lines = proc.stderr.decode().splitlines()
    assert len(lines) == 1, lines
    assert lines[0].startswith("Error: "), lines[0]
    assert str(missing) in lines[0], lines[0]


# ------------------------- behaviors 9 and 10: the CLI declares its codes, the doc publishes them

def test_b9_the_cli_publishes_its_exit_codes_as_module_constants():
    """Behavior 9: the codes are named values, so a document can be checked against them."""
    assert cli.EXIT_OK == 0
    assert cli.EXIT_ERROR == 2
    assert cli.EXIT_BROKEN_PIPE == EXPECTED_BROKEN_PIPE == 141
    assert cli.EXIT_CODES == (cli.EXIT_OK, cli.EXIT_ERROR, cli.EXIT_BROKEN_PIPE)
    assert len(set(cli.EXIT_CODES)) == len(cli.EXIT_CODES), "a code is listed twice"
    assert 1 not in cli.EXIT_CODES, "1 is reserved for the floor-gated verdict code"


def test_b9_fail_returns_the_named_error_code(capsys):
    """Behavior 9's last clause: the refusal path returns the constant, not a literal."""
    capsys.readouterr()
    assert cli._fail("probe") == cli.EXIT_ERROR
    assert capsys.readouterr().err == "Error: probe\n"


def _documented_code_cells(document: str) -> tuple[str, ...]:
    """The `Code` column of the contract's exit-code table, via the SHARED reader.

    `_surface_contract.gfm_table` is reused rather than a second markdown parser: that
    module's own docstring warns a duplicate "would drift exactly the way the hand-copied
    table did", and it already fails closed on a missing, duplicated or ragged table.
    """
    return gfm_table(document, EXIT_CODES_HEADING).column(CODE_COLUMN)


def _code_table_violations(document: str, expected: tuple[int, ...]) -> list[str]:
    """Every way the published table and `expected` disagree, in BOTH directions."""
    problems: list[str] = []
    documented: set[int] = set()
    for cell in _documented_code_cells(document):
        found = BACKTICKED_INT.findall(cell)
        if len(found) != 1:
            problems.append(
                f"Code cell {cell!r} carries {len(found)} backticked integer(s), "
                f"expected exactly 1")
            continue
        documented.add(int(found[0]))
    if not documented:
        return problems + ["the exit-code table documents no codes at all"]
    missing = sorted(set(expected) - documented)
    surplus = sorted(documented - set(expected))
    if missing:
        problems.append(f"the CLI can return {missing} but the table omits them")
    if surplus:
        problems.append(f"the table lists {surplus} which the CLI cannot return")
    return problems


def _code_row(document: str, code: int) -> str:
    """The one table line whose Code cell is `code`, so a mutation can target it."""
    prefix = f"| `{code}` |"
    matches = [line for line in document.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1, f"{len(matches)} row(s) start {prefix!r}, expected 1"
    return matches[0]


def test_b10_the_contract_publishes_exactly_the_codes_the_cli_can_return():
    """Behavior 10, forward direction, against the TRACKED document."""
    document = contract_text()
    cells = _documented_code_cells(document)
    assert cells, "the exit-code table has no data rows; the comparison would be vacuous"
    assert len(cells) == len(cli.EXIT_CODES), (
        f"{len(cells)} row(s) for {len(cli.EXIT_CODES)} code(s); the spec says one each")
    assert _code_table_violations(document, cli.EXIT_CODES) == []


def test_b10_a_code_the_cli_gained_but_the_document_omits_fails():
    """Behavior 10's first negative side, proved by MUTATING the text, never the file."""
    document = contract_text()
    without_141 = document.replace(_code_row(document, 141) + "\n", "", 1)
    assert without_141 != document, "the mutation did not change the document"
    problems = _code_table_violations(without_141, cli.EXIT_CODES)
    assert problems, "an omitted code passed the brake"
    assert any("omits" in p and "141" in p for p in problems), problems


def test_b10_a_row_for_a_code_the_cli_cannot_return_also_fails():
    """Behavior 10's second negative side: the table may not over-promise either."""
    document = contract_text()
    row = _code_row(document, 141)
    with_bogus = document.replace(row, row + "\n| `7` | invented | do nothing |", 1)
    assert with_bogus != document
    problems = _code_table_violations(with_bogus, cli.EXIT_CODES)
    assert problems, "a surplus row passed the brake"
    assert any("cannot return" in p and "7" in p for p in problems), problems


def test_b10_an_emptied_table_fails_closed_rather_than_passing_vacuously():
    """Behavior 10's anti-vacuity side: no rows must be an ERROR, not zero violations."""
    document = contract_text()
    emptied = document
    for code in cli.EXIT_CODES:
        emptied = emptied.replace(_code_row(document, code) + "\n", "", 1)
    assert emptied != document
    with pytest.raises(SurfaceContractError):
        _code_table_violations(emptied, cli.EXIT_CODES)


def test_b9_the_heading_names_exit_codes_and_spells_no_verb_in_backticks():
    """Behavior 9's heading clause, and iteration 16's verb-heading brake stays quiet.

    A `##` heading spelling a backticked `radar <verb>` is required by
    `tests/test_contract_verb_headings.py` to carry a SHIPPED / TO BUILD / NOT PLANNED
    status; this heading describes a code set, not a verb, so it must carry no backticks.
    """
    document = contract_text()
    assert "exit code" in EXIT_CODES_HEADING.lower()
    assert [line for line in document.splitlines()
            if line.strip() == EXIT_CODES_HEADING], "the heading is not in the document"
    assert "`" not in EXIT_CODES_HEADING


def test_b9_the_guarantees_paragraph_points_at_the_code_table():
    """The published `Error: `/exit-2 promise must not read as the whole failure story."""
    document = contract_text()
    paragraphs = [p for p in document.split("\n\n")
                  if "stdout carries only the document" in p]
    assert len(paragraphs) == 1, f"{len(paragraphs)} guarantee paragraph(s) found"
    assert "Exit codes" in paragraphs[0], paragraphs[0]
