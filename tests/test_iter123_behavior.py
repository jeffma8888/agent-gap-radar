"""Iteration 123 behaviors: the scan cost census (`tools/scan_cost.py`).

Seven shipped roadmap rows and three open ones were priced by figures a scout
produced in a throwaway script that was then deleted, so row 35 has been priced
three times in three non-comparable units. This iteration commits the instrument
instead of the figure: a deterministic, offline, COUNT-ONLY census of one real
`scan()`, emitting no duration, so the repo can re-derive its own cost claims.

ISOLATION CONTRACT HONORED. Nothing in this module reads the text of `src/`, of
`tools/scan_cost.py`, of `IMPLEMENTATION.patch`, of the engineer's or reviewer's
notes, or of any diff. Every expectation comes from `pm.md`'s eight Expected
Behaviors, and every claim is measured by RUNNING the tool as a subprocess or by
CALLING / INTROSPECTING its public interface (`census`, `main`, `render_markdown`,
`render_json`) plus the library globals behavior 8 names.

STRUCTURAL NOTES, so this file cannot lie later:

* **The fixture is deliberately NON-EMPTY, and one test asserts that.** A target
  with no content-rule work makes every counter `0`, and then behaviors 2 and 3
  hold vacuously: `0 == 0 - 0` for all four keyings, and `0 >= 0`. So the fixture
  copies real register records (register DATA, not implementation text) into
  `tmp_path` and plants a synthetic target that trips their `content_matches`
  rules, and `test_b2_fixture_is_not_vacuous` pins `content evaluations > 0`. If a
  future refactor makes the fixture inert, that test fails instead of the suite
  going quietly green on nothing.
* **Counts are asserted as INVARIANTS, never as today's magic numbers.** The live
  register's own figures (254 evaluations, 231 distinct keys without
  `boolean_only`) are properties of 120 records at one moment; pinning them would
  make this module fail on the next research pass. What is pinned is the identity
  `duplicate calls == content evaluations - distinct keys` per keying, and that
  the complete key dominates every degraded key.
* **The keying arithmetic is checked in BOTH output forms**, because a renderer is
  free to disagree with the census object it renders, and the JSON form is the one
  a release gate parses.
* **Behavior 8's restoration test substitutes the seam with a SENTINEL of its
  own** and asserts the sentinel is what comes back. Asserting only "the global is
  callable" or "equals the module's original" would pass against a tool that
  restores from a snapshot taken at import time, which silently discards any
  outer monkeypatch. The exception is driven through the `scan_fn` seam so that
  propagation is deterministic rather than dependent on how `scan()` handles a
  raising rule.
* **`git diff --stat HEAD -- src/` is NOT asserted here.** It is an acceptance
  criterion for THIS iteration, not a behavior of the product: a committed
  assertion that `src/` is unmodified would fail forever in the next iteration
  that legitimately edits `src/`. The tester verified it out-of-band and recorded
  the measurement in the iteration report.
* **Only one test runs the real 120-record register** (`test_b1_repo_root_default`,
  a few seconds). Every other test uses the tiny fixture, so the module stays
  cheap under `-n auto`.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "scan_cost.py"
sys.path.insert(0, str(REPO / "tools"))

import scan_cost as sc  # noqa: E402

# Behavior 2's labels, verbatim.
DOMAIN_LABELS = (
    "gap records",
    "content evaluations",
    "decode calls",
    "distinct decoded paths",
    "literal-set proofs",
    "proofs that proved a set",
    "proofs that proved nothing",
)
# Behavior 3's keyings, verbatim.
KEYINGS = ("complete", "without boolean_only", "without exclude_tests", "without kind")
KEY_COLUMNS = ("distinct keys", "duplicate calls")

# Register records whose `check` carries content rules, so the census has work to do.
RECORD_PREFIXES = ("GAP-003", "GAP-004", "GAP-006", "GAP-007", "GAP-008", "GAP-009")

# A synthetic target that trips those rules from both sides: `subprocess.run(...,
# timeout=)` with no checkpoint token, `while True` with no reload token, plus a
# test-shaped file so `exclude_tests` is not a constant over the run.
TARGET_FILES = {
    "runner.py": (
        "import subprocess\n\n\n"
        "def step(cmd):\n"
        "    return subprocess.run(cmd, capture_output=True, timeout=600)\n"
    ),
    "loop.py": ("import worker\n\n\ndef main():\n    while True:\n        worker.tick()\n"),
    "agent.py": (
        "import json\nimport subprocess\n\n\n"
        "def run(cmd):\n"
        "    proc = subprocess.Popen(cmd)\n"
        "    return json.dumps({'pid': proc.pid})\n"
    ),
    "notes.md": "# notes\n\nA target document with no code in it.\n",
    "tests/test_planted.py": (
        "import importlib\n\n\n"
        "def test_reload_is_only_mentioned_in_a_test():\n"
        "    assert importlib is not None\n"
    ),
}


def _build_fixture(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Plant (target, gaps) under `root`. Both are returned as absolute paths."""
    gaps = root / "register"
    gaps.mkdir(parents=True)
    copied = 0
    for path in sorted((REPO / "gaps").glob("*.json")):
        if path.name.startswith(RECORD_PREFIXES):
            shutil.copyfile(path, gaps / path.name)
            copied += 1
    assert copied == len(RECORD_PREFIXES), f"fixture expected {len(RECORD_PREFIXES)} records, copied {copied}"
    target = root / "subject"
    for rel, text in TARGET_FILES.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return target, gaps


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    return _build_fixture(tmp_path)


def _run(args: list[str], cwd: pathlib.Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_fixture(fixture, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    target, gaps = fixture
    return _run(["--target", str(target), "--gaps", str(gaps), *(extra or [])])


def _ends_in_exactly_one_newline(text: str) -> bool:
    return text.endswith("\n") and not text.endswith("\n\n")


def _rows(markdown: str) -> list[list[str]]:
    """Every markdown table row as its stripped cells, separator rows dropped."""
    out: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue
        out.append(cells)
    return out


def _two_column(markdown: str) -> dict[str, str]:
    return {cells[0]: cells[1] for cells in _rows(markdown) if len(cells) == 2}


def _three_column(markdown: str) -> dict[str, tuple[str, str]]:
    return {cells[0]: (cells[1], cells[2]) for cells in _rows(markdown) if len(cells) == 3}


def _leaves(obj, path: str = "$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaves(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _leaves(value, f"{path}[{index}]")
    else:
        yield path, obj


def _key_orders(obj, path: str = "$"):
    if isinstance(obj, dict):
        yield path, list(obj)
        for key, value in obj.items():
            yield from _key_orders(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _key_orders(value, f"{path}[{index}]")


# --------------------------------------------------------------------------
# Behavior 1: success shape.
# --------------------------------------------------------------------------


def test_b1_repo_root_default_exits_zero_clean_stdout_only():
    """The documented invocation: no arguments, from the repo root.

    Behavior 6's leak guard is folded in here rather than given its own test:
    this is the module's ONLY run over the real 120-record register (~11 s), and
    the documented no-argument invocation is precisely the one whose output a
    maintainer pastes into a roadmap row, so it is the run that must not carry
    a checkout path.
    """
    proc = _run([])
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert proc.stdout
    assert _ends_in_exactly_one_newline(proc.stdout)
    assert str(REPO) not in proc.stdout, "the checkout path leaked into the default document"
    assert "/Users" not in proc.stdout
    # Deliberately NOT asserted: that `REPO.name` is absent. The checkout directory
    # is named after the PRODUCT, so a title or a schema string may legitimately
    # carry that word; only the PATH is a leak, and `str(REPO)` is what pins it.
    for token in proc.stdout.split():
        assert not token.strip("|`\"',.()").startswith("/"), f"absolute-looking token {token!r}"


def test_b1_fixture_run_exits_zero_clean_stdout_only(fixture):
    proc = _run_fixture(fixture)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert _ends_in_exactly_one_newline(proc.stdout)


def test_b1_default_gaps_is_resolved_under_the_target(tmp_path):
    """`--gaps` defaults to 'gaps' under the target, so this run needs neither flag."""
    root = tmp_path / "cwd"
    target, gaps = _build_fixture(root)
    gaps.rename(target / "gaps")
    proc = _run([], cwd=target)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert _ends_in_exactly_one_newline(proc.stdout)
    assert _two_column(proc.stdout)["gap records"] == str(len(RECORD_PREFIXES))


def test_b1_json_form_exits_zero_clean_stdout_only(fixture):
    proc = _run_fixture(fixture, ["--json"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert _ends_in_exactly_one_newline(proc.stdout)


# --------------------------------------------------------------------------
# Behavior 2: domain and read counters.
# --------------------------------------------------------------------------


def test_b2_every_domain_label_is_a_row_with_a_decimal_integer(fixture):
    table = _two_column(_run_fixture(fixture).stdout)
    for label in DOMAIN_LABELS:
        assert label in table, f"missing domain label {label!r}; saw {sorted(table)}"
        assert re.fullmatch(r"[0-9]+", table[label]), f"{label!r} -> {table[label]!r} is not a decimal integer"


def test_b2_proof_outcomes_partition_the_proofs(fixture):
    table = _two_column(_run_fixture(fixture).stdout)
    assert int(table["proofs that proved a set"]) + int(table["proofs that proved nothing"]) == int(
        table["literal-set proofs"]
    )


def test_b2_fixture_is_not_vacuous(fixture):
    """Guard against an inert fixture making behaviors 2 and 3 hold on all-zeroes."""
    table = _two_column(_run_fixture(fixture).stdout)
    assert int(table["gap records"]) == len(RECORD_PREFIXES)
    assert int(table["content evaluations"]) > 0
    assert int(table["decode calls"]) > 0
    assert int(table["distinct decoded paths"]) > 0
    assert int(table["literal-set proofs"]) > 0


def test_b2_in_process_census_agrees_with_the_rendered_document(fixture):
    """The in-process path and the CLI path must be the same document, byte for byte.

    The inherited version of this test only asserted that each domain label held
    SOME integer, which its own name overstated: a `census()` that disagreed with
    the subprocess would still have passed. Both renderers are compared to the
    real stdout instead, so a divergence between the library entry point the tests
    drive and the command a maintainer runs cannot hide.
    """
    target, gaps = fixture
    document = sc.render_markdown(sc.census(target, gaps))
    table = _two_column(document)
    for label in DOMAIN_LABELS:
        assert re.fullmatch(r"[0-9]+", table[label])
    assert document == _run_fixture(fixture).stdout
    assert sc.render_json(sc.census(target, gaps)) == _run_fixture(fixture, ["--json"]).stdout


def test_b2_read_counters_are_functions_of_the_target_not_constants(tmp_path):
    """A counter wired to nothing still satisfies behaviors 2 and 3.

    `test_b2_fixture_is_not_vacuous` pins `> 0`, which a hard-coded constant also
    passes. This drives the same register over two targets that differ ONLY by two
    extra decodable files and asserts the read counters MOVE, which no constant and
    no cached-from-elsewhere figure can do. Growth is asserted as strict inequality,
    not as a delta, so a legitimate change to which files the scan enumerates does
    not turn this into a false failure.
    """
    small_target, small_gaps = _build_fixture(tmp_path / "small")
    big_target, big_gaps = _build_fixture(tmp_path / "big")
    (big_target / "extra_runner.py").write_text(
        "import subprocess\n\n\ndef go(cmd):\n    return subprocess.run(cmd, timeout=30)\n",
        encoding="utf-8",
    )
    (big_target / "extra_loop.py").write_text(
        "def spin():\n    while True:\n        pass\n", encoding="utf-8"
    )
    small = json.loads(_run(["--target", str(small_target), "--gaps", str(small_gaps), "--json"]).stdout)
    big = json.loads(_run(["--target", str(big_target), "--gaps", str(big_gaps), "--json"]).stdout)
    assert small["gap records"] == big["gap records"] == len(RECORD_PREFIXES)
    assert big["decode calls"] > small["decode calls"], (small["decode calls"], big["decode calls"])
    assert big["distinct decoded paths"] > small["distinct decoded paths"], (
        small["distinct decoded paths"],
        big["distinct decoded paths"],
    )


# --------------------------------------------------------------------------
# Behavior 3: the keying table.
# --------------------------------------------------------------------------


def test_b3_markdown_carries_one_row_per_keying(fixture):
    table = _three_column(_run_fixture(fixture).stdout)
    for keying in KEYINGS:
        assert keying in table, f"missing keying row {keying!r}; saw {sorted(table)}"
        for cell in table[keying]:
            assert re.fullmatch(r"[0-9]+", cell), f"{keying!r} -> {cell!r} is not a decimal integer"


def test_b3_markdown_duplicate_calls_is_evaluations_minus_distinct_keys(fixture):
    stdout = _run_fixture(fixture).stdout
    evaluations = int(_two_column(stdout)["content evaluations"])
    keyings = _three_column(stdout)
    for keying in KEYINGS:
        distinct, duplicates = (int(cell) for cell in keyings[keying])
        assert duplicates == evaluations - distinct, f"{keying}: {duplicates} != {evaluations} - {distinct}"


def test_b3_complete_key_dominates_every_degraded_key(fixture):
    keyings = _three_column(_run_fixture(fixture).stdout)
    complete = int(keyings["complete"][0])
    for keying in KEYINGS:
        assert complete >= int(keyings[keying][0]), f"complete {complete} < {keying} {keyings[keying][0]}"
    assert int(keyings["complete"][1]) == 0


def test_b3_json_carries_the_same_arithmetic(fixture):
    payload = json.loads(_run_fixture(fixture, ["--json"]).stdout)
    evaluations = payload["content evaluations"]
    keyings = payload["keyings"]
    assert sorted(keyings) == sorted(KEYINGS)
    for keying in KEYINGS:
        row = keyings[keying]
        assert sorted(row) == sorted(KEY_COLUMNS)
        assert row["duplicate calls"] == evaluations - row["distinct keys"]
        assert keyings["complete"]["distinct keys"] >= row["distinct keys"]


def test_b3_markdown_and_json_report_identical_numbers(fixture):
    markdown = _run_fixture(fixture).stdout
    payload = json.loads(_run_fixture(fixture, ["--json"]).stdout)
    table = _two_column(markdown)
    for label in DOMAIN_LABELS:
        assert int(table[label]) == payload[label], label
    keyings = _three_column(markdown)
    for keying in KEYINGS:
        distinct, duplicates = (int(cell) for cell in keyings[keying])
        assert distinct == payload["keyings"][keying]["distinct keys"]
        assert duplicates == payload["keyings"][keying]["duplicate calls"]


# --------------------------------------------------------------------------
# Behavior 4: determinism.
# --------------------------------------------------------------------------


def test_b4_markdown_is_byte_identical_across_runs(fixture):
    first = _run_fixture(fixture)
    second = _run_fixture(fixture)
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


def test_b4_json_is_byte_identical_across_runs(fixture):
    first = _run_fixture(fixture, ["--json"])
    second = _run_fixture(fixture, ["--json"])
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


def test_b4_output_is_identical_from_a_different_working_directory(fixture, tmp_path):
    """Determinism has to survive the cwd, or the document is not re-derivable.

    Behavior 4 says two runs over the same target and gaps produce byte-identical
    stdout. The cheapest way for a census to violate that while passing a
    same-cwd comparison is to relativise a path against `os.getcwd()`, which also
    breaks behavior 6. Both forms are run from the repo root and from an unrelated
    directory with identical ABSOLUTE arguments.
    """
    target, gaps = fixture
    args = ["--target", str(target), "--gaps", str(gaps)]
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    for extra in ([], ["--json"]):
        here = _run([*args, *extra])
        there = _run([*args, *extra], cwd=outside)
        assert here.returncode == there.returncode == 0, (here.stderr, there.stderr)
        assert here.stdout == there.stdout, f"cwd changed the document (form={extra})"


def test_b4_in_process_renderers_are_byte_stable(fixture):
    target, gaps = fixture
    one, two = sc.census(target, gaps), sc.census(target, gaps)
    assert sc.render_markdown(one) == sc.render_markdown(two)
    assert sc.render_json(one) == sc.render_json(two)


# --------------------------------------------------------------------------
# Behavior 5: --json.
# --------------------------------------------------------------------------


def test_b5_json_is_one_object_with_sorted_keys_everywhere(fixture):
    stdout = _run_fixture(fixture, ["--json"]).stdout
    assert _ends_in_exactly_one_newline(stdout)
    payload = json.loads(stdout)
    assert isinstance(payload, dict)
    # One object: nothing but whitespace may follow the first decoded value.
    decoder = json.JSONDecoder()
    _, end = decoder.raw_decode(stdout)
    assert stdout[end:].strip() == ""
    for path, keys in _key_orders(payload):
        assert keys == sorted(keys), f"{path} keys are not sorted: {keys}"


def test_b5_json_carries_the_domain_integers_and_one_entry_per_keying(fixture):
    payload = json.loads(_run_fixture(fixture, ["--json"]).stdout)
    for label in DOMAIN_LABELS:
        assert label in payload, f"missing {label!r}; saw {sorted(payload)}"
        assert isinstance(payload[label], int) and not isinstance(payload[label], bool)
    assert sorted(payload["keyings"]) == sorted(KEYINGS)


def test_b5_no_leaf_is_a_float(fixture):
    payload = json.loads(_run_fixture(fixture, ["--json"]).stdout)
    for path, value in _leaves(payload):
        assert not isinstance(value, float), f"{path} is a float: {value!r}"
        assert not isinstance(value, bool), f"{path} is a bool: {value!r}"
        assert isinstance(value, (int, str)), f"{path} is neither int nor str: {type(value).__name__}"


# --------------------------------------------------------------------------
# Behavior 6: committable in a public repo.
# --------------------------------------------------------------------------

_TIME_CELL = re.compile(r"[0-9]+\s*(s|ms|sec|secs|second|seconds|min|minutes)\b", re.IGNORECASE)


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_b6_no_filesystem_path_leaks_even_with_absolute_arguments(fixture, tmp_path, extra):
    target, gaps = fixture
    proc = _run_fixture(fixture, extra)
    stdout = proc.stdout
    assert str(target) not in stdout
    assert str(gaps) not in stdout
    assert str(tmp_path) not in stdout
    assert tmp_path.name not in stdout
    assert "/Users" not in stdout
    for token in stdout.split():
        assert not token.strip("|`\"',.()").startswith("/"), f"absolute-looking token {token!r}"


def test_b6_no_output_value_is_a_wall_clock_time(fixture):
    """Prose may say 'duration'; a VALUE may not be one. Cells are integers only."""
    stdout = _run_fixture(fixture).stdout
    for cells in _rows(stdout):
        for cell in cells[1:]:
            if re.fullmatch(r"[0-9]+", cell):
                continue
            assert not _TIME_CELL.search(cell), f"time-looking value cell {cell!r}"
    for _path, value in _leaves(json.loads(_run_fixture(fixture, ["--json"]).stdout)):
        if isinstance(value, str):
            assert not _TIME_CELL.search(value), f"time-looking json value {value!r}"


# --------------------------------------------------------------------------
# Behavior 7: error contract.
# --------------------------------------------------------------------------


def _assert_error_contract(proc: subprocess.CompletedProcess[str]) -> None:
    assert proc.returncode == 2, f"rc={proc.returncode} stderr={proc.stderr!r}"
    assert proc.stdout == "", f"stdout not empty: {proc.stdout!r}"
    lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one stderr line, got {lines!r}"
    assert lines[0].strip().startswith("Error: "), lines[0]


def test_b7_missing_target(fixture, tmp_path):
    _target, gaps = fixture
    _assert_error_contract(_run(["--target", str(tmp_path / "nope"), "--gaps", str(gaps)]))


def test_b7_missing_gaps(fixture, tmp_path):
    target, _gaps = fixture
    _assert_error_contract(_run(["--target", str(target), "--gaps", str(tmp_path / "nope")]))


def test_b7_target_is_a_file(fixture):
    target, gaps = fixture
    _assert_error_contract(_run(["--target", str(target / "runner.py"), "--gaps", str(gaps)]))


def test_b7_gaps_is_a_file(fixture):
    """Behavior 7's symmetric case, MEASURED before it was pinned.

    The spec spells out "a `--target` that exists but is a file" and is silent on
    the same mistake made with `--gaps`. That silence is the ambiguity; the
    reasonable reading is that a register argument pointing at a record instead of
    at the directory of records is the same class of error. Probed out of band
    first: it already exits 2 with one `Error: not a directory: ...` line and no
    stdout, so pinning it locks in behavior the tool already has rather than
    inventing a requirement.
    """
    _target, gaps = fixture
    record = sorted(gaps.glob("*.json"))[0]
    _assert_error_contract(_run(["--target", str(_target), "--gaps", str(record)]))


def test_b7_error_contract_holds_in_the_json_form(fixture, tmp_path):
    _target, gaps = fixture
    _assert_error_contract(
        _run(["--target", str(tmp_path / "nope"), "--gaps", str(gaps), "--json"])
    )


# MEASURED, and an AMBIGUITY worth PM attention: `tools/scan_cost.py`'s `main`
# takes a `sys.argv`-shaped list (it slices off element 0), while the product's own
# entry point `agent_gap_radar.cli.main` takes the arguments BARE -- probed, not
# read: `cli.main(["--version"])` prints `0.1.0`, `cli.main(["radar","--version"])`
# exits 2 on `unrecognized arguments`. The spec only says "a thin `main(argv)`", so
# neither reading is a behavior failure and behaviors 1-7 are all pinned over the
# real CLI by subprocess. `_main` therefore adapts, and ONE dedicated test pins
# which convention is live so a silent flip cannot pass unnoticed.
PROG = "scan_cost.py"
MAIN_TAKES_PROGRAM_NAME = True


def _main(args: list[str]) -> int:
    return sc.main([PROG, *args] if MAIN_TAKES_PROGRAM_NAME else list(args))


def test_b7_main_argv_convention_is_the_one_this_module_assumes(fixture):
    """Pin the live convention: it is `sys.argv`-shaped, unlike `cli.main`'s."""
    target, gaps = fixture
    sys_argv_shaped = ["--target", str(target), "--gaps", str(gaps)]
    if MAIN_TAKES_PROGRAM_NAME:
        assert sc.main([PROG, *sys_argv_shaped]) == 0
        with pytest.raises(SystemExit) as excinfo:
            sc.main(sys_argv_shaped)
        assert excinfo.value.code == 2
    else:  # pragma: no cover - flip the constant if the convention is changed
        assert sc.main(sys_argv_shaped) == 0


def test_b7_main_returns_two_without_raising(fixture, tmp_path, capsys):
    _target, gaps = fixture
    code = _main(["--target", str(tmp_path / "nope"), "--gaps", str(gaps)])
    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip().startswith("Error: ")


def test_b7_main_returns_zero_on_success(fixture, capsys):
    target, gaps = fixture
    assert _main(["--target", str(target), "--gaps", str(gaps)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert _ends_in_exactly_one_newline(captured.out)


# --------------------------------------------------------------------------
# Behavior 8: the library is observed, never changed, and every seam is restored.
# --------------------------------------------------------------------------

SEAMS = ("evaluate", "_read", "required_literal_sets")


def _seam_ids(module) -> dict[str, int]:
    return {name: id(getattr(module, name)) for name in SEAMS}


def test_b8_seams_are_the_same_objects_after_a_successful_census(fixture):
    from agent_gap_radar import checks

    target, gaps = fixture
    before = _seam_ids(checks)
    sc.census(target, gaps)
    assert _seam_ids(checks) == before


def test_b8_seams_are_restored_when_the_scan_raises(fixture, monkeypatch):
    from agent_gap_radar import checks

    target, gaps = fixture

    def sentinel_evaluate(*args, **kwargs):  # pragma: no cover - identity probe only
        raise AssertionError("sentinel must never be called")

    monkeypatch.setattr(checks, "evaluate", sentinel_evaluate)
    before = _seam_ids(checks)
    assert before["evaluate"] == id(sentinel_evaluate)

    boom = RuntimeError("scan blew up mid-census")

    def raising_scan(*args, **kwargs):
        raise boom

    with pytest.raises(RuntimeError) as excinfo:
        sc.census(target, gaps, scan_fn=raising_scan)
    assert excinfo.value is boom
    assert _seam_ids(checks) == before
    assert getattr(checks, "evaluate") is sentinel_evaluate


def test_b8_the_seams_are_actually_wrapped_during_the_census(fixture):
    """Observation is real: the tool must REPLACE the seam while the scan runs."""
    from agent_gap_radar import checks

    target, gaps = fixture
    originals = {name: getattr(checks, name) for name in SEAMS}
    seen: dict[str, object] = {}

    def probing_scan(*args, **kwargs):
        for name in SEAMS:
            seen[name] = getattr(checks, name)
        return None

    try:
        sc.census(target, gaps, scan_fn=probing_scan)
    except Exception:  # noqa: BLE001 - a None scan result may be rejected; seams still matter
        pass
    assert set(seen) == set(SEAMS), f"scan_fn seam was never invoked: {sorted(seen)}"
    for name in SEAMS:
        assert seen[name] is not originals[name], f"{name} was not wrapped during the census"
        assert getattr(checks, name) is originals[name], f"{name} was not restored"


def test_b8_tool_imports_only_stdlib_and_the_product_package():
    """Acceptance criterion, checked by introspection rather than by reading source."""
    import types

    allowed_roots = set(sys.stdlib_module_names) | {"agent_gap_radar", "scan_cost"}
    offenders = []
    for name, value in vars(sc).items():
        if isinstance(value, types.ModuleType):
            root = value.__name__.split(".")[0]
            if root not in allowed_roots:
                offenders.append((name, value.__name__))
    assert offenders == [], f"non-stdlib, non-product imports: {offenders}"
