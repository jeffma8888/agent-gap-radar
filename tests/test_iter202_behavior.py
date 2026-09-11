"""Iteration 202 behaviors: the scan-cost census refuses nothing, and attributes.

The committed instrument `tools/scan_cost.py` prices every performance decision
this loop makes. Iteration 202 closes two holes in it: a census taken over a
register holding ZERO records used to exit 0 with an all-zero document, which
reads as "a clean scan" while measuring nothing; and the decode amplification the
tool exists to price was un-attributed, because the size of the file domain each
content-rule evaluation was HANDED was never published.

ISOLATION CONTRACT HONORED. Nothing in this module reads the text of `src/`, of
`tools/scan_cost.py`, of the engineer's or the reviewer's notes, or of any diff.
Every expectation comes from `pm.md`'s two Expected Behaviors plus the roadmap
ledger row for this iteration in `PRODUCT.md` (which the contract permits), and
every claim is MEASURED by running the tool as a subprocess or by calling its
public interface (`census`, `main`, `render_markdown`, `render_json`).

STRUCTURAL NOTES, so this file cannot lie later:

* **Behavior 1 is pinned two-sidedly.** A refusal test alone passes against a
  tool that refuses EVERYTHING, so every refusal case is paired with a control
  over the same target whose only difference is that the register holds one real
  record, and the control asserts exit 0 with a document.
* **Behavior 1's "no scan attempted" limb is measured, not argued.** The refusal
  is driven through the `scan_fn` seam with a sentinel that raises if called, so
  a tool that ran the scan first and only then noticed the empty register would
  fail here even though its exit code and stderr were right.
* **Behavior 2's counter is pinned as an INVARIANT and as a FUNCTION OF THE
  TARGET, never as today's magic number.** The live register's figures are
  properties of 120 records at one moment. What is pinned is that the published
  domain total BOUNDS the decode row beneath it (the census document says so in
  its own prose), and that adding decodable files to the target MOVES the number
  -- which no hard-coded constant and no figure cached from elsewhere can do.
* **The label is not invented here.** `files in content domains` is the row this
  iteration's `PRODUCT.md` ledger row names verbatim, and it is what the tool
  prints; this module pins the documented name so a silent rename is a red test
  rather than a broken roadmap claim.
* **AMBIGUITY, recorded for the PM.** Behavior 2 says "the per-evaluation
  `iter_files` domain size", which reads as a mean; what is published is the SUM
  over content evaluations, with the evaluation count beside it so a reader can
  divide. The sum is the reading tested, because a mean would be a float leaf and
  the census forbids those. See `test_b2_ambiguity_the_published_figure_is_a_sum_not_a_mean`.
* **Only one test runs the real 120-record register.** Every other test uses the
  tiny fixture, so the module stays cheap under `-n auto`.
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

# Behavior 2's row, named verbatim by this iteration's `PRODUCT.md` ledger row.
DOMAIN_FILES = "files in content domains"
# The neighbours it is arithmetically related to (all inherited from iteration 123).
EVALUATIONS = "content evaluations"
DECODES = "decode calls"
DISTINCT_PATHS = "distinct decoded paths"

# Records whose `check` carries content rules, so a census has work to do.
RECORD_PREFIXES = ("GAP-003", "GAP-004", "GAP-006", "GAP-007", "GAP-008", "GAP-009")

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


def _plant_target(root: pathlib.Path) -> pathlib.Path:
    target = root / "subject"
    for rel, text in TARGET_FILES.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return target


def _plant_register(root: pathlib.Path, prefixes=RECORD_PREFIXES) -> pathlib.Path:
    gaps = root / "register"
    gaps.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted((REPO / "gaps").glob("*.json")):
        if prefixes and path.name.startswith(tuple(prefixes)):
            shutil.copyfile(path, gaps / path.name)
            copied += 1
    assert copied == len(prefixes), f"fixture expected {len(prefixes)} records, copied {copied}"
    return gaps


def _build_fixture(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Plant (target, non-empty register) under `root`. Absolute paths."""
    return _plant_target(root), _plant_register(root)


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


def _run_pair(
    target: pathlib.Path, gaps: pathlib.Path, extra: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    return _run(["--target", str(target), "--gaps", str(gaps), *(extra or [])])


def _ends_in_exactly_one_newline(text: str) -> bool:
    return text.endswith("\n") and not text.endswith("\n\n")


def _rows(markdown: str) -> list[list[str]]:
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


def _leaves(obj, path: str = "$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaves(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _leaves(value, f"{path}[{index}]")
    else:
        yield path, obj


def _assert_refusal(proc: subprocess.CompletedProcess[str]) -> str:
    """Behavior 1's contract, verbatim: exit 2, one `Error: ` line, no census."""
    assert proc.returncode == 2, f"rc={proc.returncode} stderr={proc.stderr!r}"
    assert proc.stdout == "", f"a census was printed anyway: {proc.stdout!r}"
    lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one stderr line, got {lines!r}"
    assert lines[0].startswith("Error: "), lines[0]
    return lines[0]


# --------------------------------------------------------------------------
# Behavior 1: a census over zero records refuses instead of certifying zeroes.
# --------------------------------------------------------------------------


def test_b1_empty_register_refuses_in_the_markdown_form(tmp_path):
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    line = _assert_refusal(_run_pair(target, empty))
    assert "record" in line.lower(), f"the refusal does not name its cause: {line!r}"


def test_b1_empty_register_refuses_in_the_json_form(tmp_path):
    """The machine form must refuse too, or a release gate parses an all-zero object."""
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    _assert_refusal(_run_pair(target, empty, ["--json"]))


def test_b1_a_register_holding_only_non_records_refuses(tmp_path):
    """"Zero records" is about RECORDS, not about an empty directory.

    A register directory that exists and is non-empty but holds no gap record
    yields the same all-zero census, so it is the same defect. Measured before it
    was pinned: this already refuses.
    """
    target = _plant_target(tmp_path)
    decoys = tmp_path / "decoys"
    decoys.mkdir()
    (decoys / "README.md").write_text("not a record\n", encoding="utf-8")
    (decoys / "notes.txt").write_text("also not a record\n", encoding="utf-8")
    _assert_refusal(_run_pair(target, decoys))


def test_b1_one_record_over_the_same_target_still_succeeds(tmp_path):
    """The control that makes the refusal a discrimination and not a blanket no.

    Same target, same flags; the ONLY difference is that the register holds one
    real record. A tool that refused every census would pass every test above and
    fail this one.
    """
    target = _plant_target(tmp_path)
    one = _plant_register(tmp_path, prefixes=("GAP-003",))
    proc = _run_pair(target, one)
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert _ends_in_exactly_one_newline(proc.stdout)
    assert int(_two_column(proc.stdout)["gap records"]) == 1


def test_b1_the_accidental_route_refuses_too(tmp_path):
    """`--gaps` defaults to `gaps` UNDER `--target`, so this is reachable by mistake.

    Run with NO arguments from a directory that has an empty `gaps/` in it: the
    zero-record census is what a maintainer gets by pointing the tool at the wrong
    checkout, which is why the refusal matters at all.
    """
    target = _plant_target(tmp_path)
    (target / "gaps").mkdir()
    _assert_refusal(_run([], cwd=target))


def test_b1_census_raises_rather_than_returning_an_all_zero_census(tmp_path):
    """The library entry point refuses as well, so an in-process caller cannot
    obtain the all-zero object the CLI now withholds."""
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - the class is not the contract
        sc.census(target, empty)
    assert not isinstance(excinfo.value, AssertionError)
    assert "record" in str(excinfo.value).lower(), str(excinfo.value)


def test_b1_no_scan_is_attempted_over_an_empty_register(tmp_path):
    """The refusal precedes the work, measured through the `scan_fn` seam.

    A tool that scanned first and refused afterwards would satisfy every exit-code
    assertion above while still paying for a measurement it then discards. The
    sentinel raises `AssertionError`; the refusal must arrive instead.
    """
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    calls: list[int] = []

    def sentinel_scan(*args, **kwargs):
        calls.append(1)
        raise AssertionError("the scan must not run over a zero-record register")

    with pytest.raises(Exception) as excinfo:  # noqa: PT011
        sc.census(target, empty, scan_fn=sentinel_scan)
    assert not isinstance(excinfo.value, AssertionError), "the scan ran before the refusal"
    assert calls == [], "scan_fn was invoked over a zero-record register"


def test_b1_the_seams_are_untouched_by_a_refused_census(tmp_path, monkeypatch):
    """No counting wrapper survives the refusal.

    A sentinel is installed at each observed seam FIRST; if the refused census
    installed wrappers and forgot to restore them, the sentinel would be gone.
    """
    from agent_gap_radar import checks

    seams = ("evaluate", "_read", "required_literal_sets", "iter_files")
    sentinels = {}
    for name in seams:
        original = getattr(checks, name)

        def sentinel(*args, _original=original, **kwargs):  # pragma: no cover - identity probe
            raise AssertionError("sentinel must never be called")

        monkeypatch.setattr(checks, name, sentinel)
        sentinels[name] = sentinel

    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(Exception):  # noqa: PT011, B017
        sc.census(target, empty)
    for name in seams:
        assert getattr(checks, name) is sentinels[name], f"{name} was replaced by the refusal path"


def test_b1_main_returns_two_and_prints_one_error_line(tmp_path, capsys):
    """The `main` door agrees with the subprocess door."""
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    code = sc.main(["scan_cost.py", "--target", str(target), "--gaps", str(empty)])
    assert code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = [line for line in captured.err.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    assert lines[0].startswith("Error: ")


# --------------------------------------------------------------------------
# Behavior 2: the census publishes the `iter_files` domain size.
# --------------------------------------------------------------------------


def test_b2_markdown_carries_the_domain_row_as_a_decimal_integer(fixture):
    table = _two_column(_run_pair(*fixture).stdout)
    assert DOMAIN_FILES in table, f"missing {DOMAIN_FILES!r}; saw {sorted(table)}"
    assert re.fullmatch(r"[0-9]+", table[DOMAIN_FILES]), table[DOMAIN_FILES]


def test_b2_json_carries_the_domain_size_as_an_int(fixture):
    payload = json.loads(_run_pair(*fixture, ["--json"]).stdout)
    assert DOMAIN_FILES in payload, f"missing {DOMAIN_FILES!r}; saw {sorted(payload)}"
    value = payload[DOMAIN_FILES]
    assert isinstance(value, int) and not isinstance(value, bool), repr(value)


def test_b2_markdown_and_json_agree_on_the_domain_size(fixture):
    markdown = int(_two_column(_run_pair(*fixture).stdout)[DOMAIN_FILES])
    payload = json.loads(_run_pair(*fixture, ["--json"]).stdout)
    assert markdown == payload[DOMAIN_FILES]


def test_b2_the_domain_is_not_vacuous_on_this_fixture(fixture):
    """Guard against an inert fixture letting the bound below hold on zeroes."""
    payload = json.loads(_run_pair(*fixture, ["--json"]).stdout)
    assert payload[EVALUATIONS] > 0
    assert payload[DECODES] > 0
    assert payload[DOMAIN_FILES] > 0


def test_b2_the_domain_total_bounds_the_reads_beneath_it(fixture):
    """The census's own prose says the domain row bounds the decode row.

    That is the whole point of publishing it: the difference between the two is
    what the first-hit exit and the file cap never reached, so a domain smaller
    than the decode count would make the attribution incoherent.
    """
    payload = json.loads(_run_pair(*fixture, ["--json"]).stdout)
    assert payload[DOMAIN_FILES] >= payload[DECODES], (payload[DOMAIN_FILES], payload[DECODES])
    assert payload[DOMAIN_FILES] >= payload[DISTINCT_PATHS]


def test_b2_the_domain_size_is_a_function_of_the_target_not_a_constant(tmp_path):
    """The counter is wired to the run, measured by making the run bigger.

    Two censuses over the SAME register and two targets differing only by two
    extra decodable files. A hard-coded constant, or a figure cached from another
    measurement, passes every `> 0` assertion above and fails this one. Strict
    inequality rather than a delta, so a legitimate change to what the scan
    enumerates does not turn this into a false failure.
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
    small = json.loads(_run_pair(small_target, small_gaps, ["--json"]).stdout)
    big = json.loads(_run_pair(big_target, big_gaps, ["--json"]).stdout)
    assert small["gap records"] == big["gap records"]
    assert big[DOMAIN_FILES] > small[DOMAIN_FILES], (small[DOMAIN_FILES], big[DOMAIN_FILES])


def test_b2_ambiguity_the_published_figure_is_a_sum_not_a_mean(fixture):
    """AMBIGUITY in behavior 2, resolved by measurement and recorded for the PM.

    "the per-evaluation `iter_files` domain size" reads as a mean. What is
    published is the TOTAL over content evaluations, and this test pins that
    reading: the figure is at least the evaluation count on a fixture where every
    evaluation is handed a non-empty domain, which a mean could not be, and it is
    an integer, which a mean of unequal domains would not be.
    """
    payload = json.loads(_run_pair(*fixture, ["--json"]).stdout)
    assert payload[DOMAIN_FILES] >= payload[EVALUATIONS], (
        payload[DOMAIN_FILES],
        payload[EVALUATIONS],
    )
    assert isinstance(payload[DOMAIN_FILES], int)


def test_b2_no_leaf_of_the_json_form_is_a_float(fixture):
    """The new row may not be published as a rate, or the document stops being
    byte-stable across platforms."""
    payload = json.loads(_run_pair(*fixture, ["--json"]).stdout)
    for path, value in _leaves(payload):
        assert not isinstance(value, float), f"{path} is a float: {value!r}"
        assert not isinstance(value, bool), f"{path} is a bool: {value!r}"
        assert isinstance(value, (int, str)), f"{path} is {type(value).__name__}"


def test_b2_the_in_process_census_renders_the_same_document(fixture):
    """The library path and the command a maintainer runs are one document."""
    target, gaps = fixture
    result = sc.census(target, gaps)
    assert sc.render_markdown(result) == _run_pair(target, gaps).stdout
    assert sc.render_json(result) == _run_pair(target, gaps, ["--json"]).stdout


def test_b2_both_forms_stay_deterministic_and_end_in_one_newline(fixture):
    for extra in ([], ["--json"]):
        first = _run_pair(*fixture, extra)
        second = _run_pair(*fixture, extra)
        assert first.returncode == second.returncode == 0, (first.stderr, second.stderr)
        assert first.stdout == second.stdout, f"non-deterministic (form={extra})"
        assert _ends_in_exactly_one_newline(first.stdout)


def test_b2_the_domain_row_leaks_no_path_on_the_real_register():
    """The one run over the live 120-record register: the documented invocation.

    This is the run whose output a maintainer pastes into a roadmap row, so it is
    the run that must carry no checkout path, and it is where the new row's
    non-vacuity on real data is measured.
    """
    proc = _run([])
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    assert _ends_in_exactly_one_newline(proc.stdout)
    assert str(REPO) not in proc.stdout
    assert "/Users" not in proc.stdout
    table = _two_column(proc.stdout)
    assert re.fullmatch(r"[0-9]+", table[DOMAIN_FILES])
    assert int(table[DOMAIN_FILES]) >= int(table[DECODES]) > 0
    for token in proc.stdout.split():
        assert not token.strip("|`\"',.()").startswith("/"), f"absolute-looking token {token!r}"


def test_b2_attribution_a_register_with_no_content_rules_publishes_a_zero_domain(tmp_path):
    """The published domain is the CONTENT branch's, not every `iter_files` call.

    `iter_files` also serves the `file_exists` / `file_absent` branch, and its
    arguments never name its caller, so a tool that simply summed every
    enumeration would publish a number that no longer bounds the decode row and no
    longer prices the decode amplification. Measured two-sidedly in one run: the
    register's only record is rewritten to carry `file_exists` / `file_absent`
    rules and NO content rule, a counting delegate is installed at the published
    `checks.iter_files` seam BEFORE the census so the tool wraps it and this test
    can see the real call stream, and then the enumeration provably HAPPENS while
    the published domain stays 0.
    """
    from agent_gap_radar import checks

    target = _plant_target(tmp_path)
    gaps = tmp_path / "register"
    gaps.mkdir()
    source = sorted((REPO / "gaps").glob("GAP-003*.json"))[0]
    record = json.loads(source.read_text(encoding="utf-8"))
    record["check"]["applies_when"] = {"kind": "file_exists", "globs": ["**/*.py"]}
    record["check"]["present_when"] = {"kind": "file_absent", "globs": ["**/*.md"]}
    record["check"].pop("mitigated_when", None)
    (gaps / source.name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    original = checks.iter_files
    enumerations: list[int] = []

    def counting_iter_files(*args, **kwargs):
        files = original(*args, **kwargs)
        enumerations.append(len(files))
        return files

    checks.iter_files = counting_iter_files
    try:
        payload = json.loads(sc.render_json(sc.census(target, gaps)))
    finally:
        checks.iter_files = original

    assert payload["gap records"] == 1
    assert enumerations, "no enumeration happened at all, so the zero below proves nothing"
    assert sum(enumerations) > 0, enumerations
    assert payload[EVALUATIONS] == 0, "the fixture was supposed to carry no content rule"
    assert payload[DOMAIN_FILES] == 0, (
        f"{DOMAIN_FILES} counted {payload[DOMAIN_FILES]} files from a non-content branch "
        f"that enumerated {sum(enumerations)}"
    )


def test_b2_attribution_a_mixed_register_counts_only_the_content_branch(tmp_path):
    """The complement of the zero-domain test: with BOTH branches live, the
    published domain is STRICTLY smaller than every enumeration the scan performed.

    The zero test proves the non-content branch is not counted when it is the ONLY
    branch, which already rules out "sum every enumeration". What it cannot see is
    an attribution that LEAKS when the two branches interleave -- a per-kind
    marker set for a content rule and not cleared before a `file_exists` rule
    enumerates, so a non-content domain is billed to the content row. On a
    register where no content rule ever runs, nothing is ever mis-attributed and
    that defect publishes the correct 0. So the same counting delegate runs over a
    two-record register -- one record exactly as shipped (content rules), one
    rewritten to `file_exists` / `file_absent` -- and the surplus is measured: the
    scan must enumerate strictly MORE files than the census attributes to content
    evaluations.
    """
    from agent_gap_radar import checks

    target = _plant_target(tmp_path)
    gaps = tmp_path / "register"
    gaps.mkdir()
    content_src = sorted((REPO / "gaps").glob("GAP-003*.json"))[0]
    (gaps / content_src.name).write_bytes(content_src.read_bytes())
    other_src = sorted((REPO / "gaps").glob("GAP-004*.json"))[0]
    record = json.loads(other_src.read_text(encoding="utf-8"))
    record["check"]["applies_when"] = {"kind": "file_exists", "globs": ["**/*.py"]}
    record["check"]["present_when"] = {"kind": "file_absent", "globs": ["**/*.md"]}
    record["check"].pop("mitigated_when", None)
    (gaps / other_src.name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    original = checks.iter_files
    enumerations: list[int] = []

    def counting_iter_files(*args, **kwargs):
        files = original(*args, **kwargs)
        enumerations.append(len(files))
        return files

    checks.iter_files = counting_iter_files
    try:
        payload = json.loads(sc.render_json(sc.census(target, gaps)))
    finally:
        checks.iter_files = original

    assert payload["gap records"] == 2
    # Premises: both branches did work, so neither side of the comparison is vacuous.
    assert payload[EVALUATIONS] > 0, "no content rule was evaluated"
    assert payload[DOMAIN_FILES] > 0, "the content branch published nothing to compare"
    assert len(enumerations) > payload[EVALUATIONS], (
        "the non-content record enumerated nothing, so the surplus below proves nothing: "
        f"{enumerations} against {payload[EVALUATIONS]} content evaluations"
    )
    assert sum(enumerations) > payload[DOMAIN_FILES], (
        f"{DOMAIN_FILES} ({payload[DOMAIN_FILES]}) swallowed the whole enumeration "
        f"({sum(enumerations)} over {enumerations}), so it counts non-content calls too"
    )


def test_b2_a_second_census_in_the_same_process_publishes_the_same_domain(fixture):
    """The counter is per-census, not a module-level accumulator.

    A figure gathered at a module global is the classic place to leak state
    between calls: a counter installed once and never reset publishes N on the
    first census and 2N on the second, which is invisible to every subprocess
    test in this file because each of those gets a fresh interpreter. Two
    censuses over one fixture must render the SAME document.
    """
    target, gaps = fixture
    first = json.loads(sc.render_json(sc.census(target, gaps)))
    second = json.loads(sc.render_json(sc.census(target, gaps)))
    assert first[DOMAIN_FILES] == second[DOMAIN_FILES], (
        first[DOMAIN_FILES],
        second[DOMAIN_FILES],
    )
    assert first == second, "a second in-process census disagrees with the first"


def test_b1_a_refused_census_leaves_the_next_one_measuring_correctly(tmp_path):
    """Behavior 1 must not poison behavior 2: the refusal is inert.

    The seam test proves no wrapper survives a refusal by identity. This proves
    it by MEASUREMENT and one level up: after a refused census, a real census in
    the same process must agree byte-for-byte with the same census run in a fresh
    interpreter. A refusal that had installed a counter, or bumped one, would
    differ here while every seam still looked untouched.
    """
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    one = _plant_register(tmp_path, prefixes=("GAP-003",))

    with pytest.raises(Exception):  # noqa: PT011, B017 - the class is not the contract
        sc.census(target, empty)

    after = json.loads(sc.render_json(sc.census(target, one)))
    fresh = json.loads(_run_pair(target, one, ["--json"]).stdout)
    assert after[DOMAIN_FILES] == fresh[DOMAIN_FILES], (after[DOMAIN_FILES], fresh[DOMAIN_FILES])
    assert after == fresh, "a census following a refusal disagrees with a fresh one"


def test_b1_a_missing_register_directory_is_refused_not_censused(tmp_path):
    """The neighbouring route to a zero-record census: the directory is not there.

    Pinned as the refusal SHAPE only (exit 2, one `Error: ` line, no document),
    not by cause: measured, this arrives as a path diagnostic rather than the
    zero-record one, and the spec does not say which should win. What must never
    happen is the third outcome -- an all-zero census at exit 0 -- and that is
    what this pins.
    """
    target = _plant_target(tmp_path)
    _assert_refusal(_run_pair(target, tmp_path / "absent-register"))


def test_b1_the_refusal_is_deterministic_and_the_same_in_both_forms(tmp_path):
    """One document, one diagnostic: byte-stability applies to stderr too.

    Two runs of the refused census must produce identical stderr, and `--json`
    must not grow a second wording of it -- otherwise the one line a maintainer
    greps for depends on the flag they happened to pass.
    """
    target = _plant_target(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    first = _run_pair(target, empty)
    second = _run_pair(target, empty)
    as_json = _run_pair(target, empty, ["--json"])
    assert first.stderr == second.stderr, (first.stderr, second.stderr)
    assert first.stderr == as_json.stderr, (first.stderr, as_json.stderr)
    assert _ends_in_exactly_one_newline(first.stderr)


# --------------------------------------------------------------------------
# Behavior 2, sharpened: the attribution as an EQUALITY, and the domain as the
# domain each evaluation was HANDED rather than the size of the target.
# --------------------------------------------------------------------------


def _census_counting_enumerations(
    target: pathlib.Path, gaps: pathlib.Path
) -> tuple[dict, list[int]]:
    """Census `target` against `gaps` with a counting delegate at the published seam.

    Returns the parsed JSON census and the sizes of every file domain the scan
    enumerated, in call order. The delegate is installed BEFORE the census so the
    tool wraps it and the real call stream is observable, and it is always removed.
    """
    from agent_gap_radar import checks

    original = checks.iter_files
    enumerations: list[int] = []

    def counting_iter_files(*args, **kwargs):
        files = original(*args, **kwargs)
        enumerations.append(len(files))
        return files

    checks.iter_files = counting_iter_files
    try:
        payload = json.loads(sc.render_json(sc.census(target, gaps)))
    finally:
        checks.iter_files = original
    return payload, enumerations


def _write_non_content_record(gaps: pathlib.Path, source: pathlib.Path) -> None:
    """Copy `source` into `gaps` with its content rules replaced by path rules."""
    record = json.loads(source.read_text(encoding="utf-8"))
    record["check"]["applies_when"] = {"kind": "file_exists", "globs": ["**/*.py"]}
    record["check"]["present_when"] = {"kind": "file_absent", "globs": ["**/*.md"]}
    record["check"].pop("mitigated_when", None)
    (gaps / source.name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def test_b2_attribution_the_content_domain_is_invariant_to_a_non_content_record(tmp_path):
    """The exact attribution: adding a non-content record moves the row by ZERO.

    The mixed-register test above pins a one-sided surplus -- the scan enumerated
    strictly more files than the census billed to content. That inequality is
    satisfied by an attribution that leaks a LITTLE, so this pins the same fixture
    as an EQUALITY instead: two registers over the SAME target, one holding a
    content record alone and one holding that identical record PLUS a record whose
    rules are `file_exists` / `file_absent`, must publish the SAME content domain
    and the same evaluation count, while `gap records` provably differs.

    The premise that makes the equality non-vacuous is measured, not argued: the
    two-record register must enumerate strictly more calls AND strictly more files
    than the one-record register, so there really was extra enumeration available
    to be mis-billed.
    """
    target = _plant_target(tmp_path)
    content_src = sorted((REPO / "gaps").glob("GAP-003*.json"))[0]
    other_src = sorted((REPO / "gaps").glob("GAP-004*.json"))[0]

    alone = tmp_path / "alone"
    alone.mkdir()
    (alone / content_src.name).write_bytes(content_src.read_bytes())

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / content_src.name).write_bytes(content_src.read_bytes())
    _write_non_content_record(mixed, other_src)

    one, one_calls = _census_counting_enumerations(target, alone)
    two, two_calls = _census_counting_enumerations(target, mixed)

    # Premises, so neither side of the equality is empty and the extra work is real.
    assert one["gap records"] == 1 and two["gap records"] == 2
    assert one[EVALUATIONS] > 0, "the content record evaluated nothing"
    assert one[DOMAIN_FILES] > 0, "the content record published an empty domain"
    assert len(two_calls) > len(one_calls), (
        "the non-content record enumerated nothing, so the equality below is vacuous: "
        f"{two_calls} against {one_calls}"
    )
    assert sum(two_calls) > sum(one_calls), (two_calls, one_calls)

    assert two[EVALUATIONS] == one[EVALUATIONS], (
        f"a non-content record changed {EVALUATIONS!r}: {one[EVALUATIONS]} -> {two[EVALUATIONS]}"
    )
    assert two[DOMAIN_FILES] == one[DOMAIN_FILES], (
        f"{DOMAIN_FILES!r} absorbed {two[DOMAIN_FILES] - one[DOMAIN_FILES]} files from the "
        f"non-content branch ({one[DOMAIN_FILES]} -> {two[DOMAIN_FILES]}, enumerations "
        f"{one_calls} -> {two_calls})"
    )


def test_b2_a_content_rule_handed_an_empty_domain_publishes_zero_not_the_target_size(tmp_path):
    """The row is the domain each evaluation was HANDED, not the size of the target.

    This is the defect no other test in this module can see. A tool that published
    `content evaluations x (files under the target)` -- the cheap approximation of
    "per-evaluation domain size" that never touches the seam at all -- passes the
    non-vacuity tests, passes the bound over the decode row, passes the
    function-of-the-target test (it grows when the target grows), and passes the
    invariance test above (a non-content record adds no content evaluation). It is
    separated only by a fixture where a content rule RUNS and is handed NOTHING:
    the target still holds files, the evaluation still happens, and the honest
    figure is 0.

    The register's only record keeps its content rules and has every glob narrowed
    to an extension no file in the target carries.
    """
    target = _plant_target(tmp_path)
    planted = len(TARGET_FILES)
    assert planted > 0, "the target must hold files, or 0 is the trivial answer"

    gaps = tmp_path / "register"
    gaps.mkdir()
    source = sorted((REPO / "gaps").glob("GAP-003*.json"))[0]
    record = json.loads(source.read_text(encoding="utf-8"))
    narrowed = 0
    for key in ("applies_when", "present_when", "mitigated_when"):
        rule = record["check"].get(key)
        if isinstance(rule, dict) and "globs" in rule:
            rule["globs"] = ["**/*.nosuchextension"]
            narrowed += 1
    assert narrowed > 0, "the fixture narrowed no glob, so nothing is being measured"
    (gaps / source.name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    payload, enumerations = _census_counting_enumerations(target, gaps)

    assert payload["gap records"] == 1
    # The premise: a content rule really was evaluated, so 0 is not "no work ran".
    assert payload[EVALUATIONS] > 0, (
        "no content rule was evaluated, so this fixture cannot distinguish an "
        "empty domain from an absent branch"
    )
    assert enumerations == [0] * len(enumerations), (
        f"the narrowed globs were supposed to match nothing, but enumeration saw {enumerations}"
    )
    assert payload[DOMAIN_FILES] == 0, (
        f"{DOMAIN_FILES!r} published {payload[DOMAIN_FILES]} for "
        f"{payload[EVALUATIONS]} evaluation(s) that were each handed an empty domain "
        f"(the target holds {planted} files, so a target-size proxy would print "
        f"about {payload[EVALUATIONS] * planted})"
    )
    assert payload[DECODES] == 0, payload[DECODES]
