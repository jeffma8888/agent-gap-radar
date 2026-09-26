"""Iteration 294 behavior tests (black-box; spec: state/iter-294/pm.md).

Feature: ``radar prd`` accepts ``--floor N`` (default 2, mirroring ``list``/``report``/
``scan``), threads it into the top-ranked selection, and its refusal names the floor it
applied: ``Error: no gap clears the confidence floor N``. ``--gap`` stays the explicit
escape hatch and the PRD document itself gains no key.

ISOLATION CONTRACT HONORED: nothing here read ``src/``, the engineer's or reviewer's
notes, or a diff of any source file. Expectations come from ``pm.md``; shapes were
measured by RUNNING the tool and by reading files under ``tests/`` and the published
``docs/CONSUMER_CONTRACT.md``. The pre-change control arm is the product itself at the
commit before this iteration, extracted with ``git archive`` and EXECUTED, never read.

One spec deviation, recorded here so the PM sees it: the spec's ``REG_TWO`` fixture
(derived confidence 2) is UNREACHABLE on the published ladder -- ``radar taxonomy``
weights are {5, 4, 3, 1, 0} and the corroboration point needs two citations of
DIFFERENT classes, so a single citation derives {5, 4, 3, 1, 0} and no pair derives 2.
Behavior 1 is therefore probed at the nearest reachable rung: ``practitioner-report``
(derived 3) against ``--floor 4``.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The commit immediately before this iteration's change (control arm, iter-265 recipe).
PRECHANGE_COMMIT = "946ee04"

REFUSAL = "Error: no gap clears the confidence floor {floor}\n"
UNRECOGNIZED = "Error: unrecognized arguments: --floor"

#: One schema-valid record; the evidence list is what each fixture varies.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
}


def _citation(source_class: str, slug: str) -> dict:
    return {"source_class": source_class, "title": slug.upper(),
            "locator": f"https://example.invalid/{slug}", "date": "2026-01-02",
            "quote": "the verbatim line"}


def _register(root: pathlib.Path, name: str, source_class: str) -> pathlib.Path:
    reg = root / name
    (reg / "gaps").mkdir(parents=True)
    record = dict(RECORD, evidence=[_citation(source_class, name)])
    (reg / "gaps" / "GAP-001.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return reg


@pytest.fixture(scope="module")
def reg_low(tmp_path_factory) -> pathlib.Path:
    """One citable record whose only citation is the weakest citable class: derives 1."""
    return _register(tmp_path_factory.mktemp("reg294"), "low", "secondary-summary")


@pytest.fixture(scope="module")
def reg_three(tmp_path_factory) -> pathlib.Path:
    """One citable record whose only citation is `practitioner-report`: derives 3."""
    return _register(tmp_path_factory.mktemp("reg294"), "three", "practitioner-report")


@pytest.fixture(scope="module")
def reg_mixed(tmp_path_factory) -> pathlib.Path:
    """Two citable records: GAP-001 outranks GAP-002 on priority but derives only 1.

    GAP-001: severity/frequency/tractability 5/5/5, one `secondary-summary` citation
    (derives 1, below the default floor). GAP-002: 1/1/1, one `practitioner-report`
    citation (derives 3). So the DEFAULT floor must pick the lower-priority GAP-002 and
    `--floor 1` must flip the pick to GAP-001: the floor gates SELECTION, not ranking.
    """
    reg = tmp_path_factory.mktemp("reg294") / "mixed"
    (reg / "gaps").mkdir(parents=True)
    strong = dict(RECORD, id="GAP-001", severity=5, frequency=5, tractability=5,
                  evidence=[_citation("secondary-summary", "mixed-a")])
    weak = dict(RECORD, id="GAP-002", severity=1, frequency=1, tractability=1,
                evidence=[_citation("practitioner-report", "mixed-b")])
    for record in (strong, weak):
        (reg / "gaps" / f"{record['id']}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return reg


def _radar(*argv: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        cwd=str(REPO_ROOT), capture_output=True, env=env)


def _text(proc: subprocess.CompletedProcess) -> tuple[str, str]:
    return proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


def _derived_confidence(reg: pathlib.Path) -> int:
    proc = _radar("list", str(reg), "--json")
    assert proc.returncode == 0, proc.stderr
    (record,) = json.loads(proc.stdout.decode("utf-8"))["records"]
    return record["confidence"]


# --------------------------------------------------------------------------------------
# Behavior 1 -- a raised floor refuses a record the default would accept, naming the floor
# --------------------------------------------------------------------------------------

def test_iter294_b1_fixture_derives_confidence_3_and_clears_the_default(reg_three) -> None:
    """The fixture is what the deviation note says it is, measured through `list --json`."""
    assert _derived_confidence(reg_three) == 3
    proc = _radar("prd", str(reg_three))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8"))["sourceGap"]["id"] == "GAP-001"


def test_iter294_b1_prd_floor_above_the_derived_value_refuses_naming_that_floor(
        reg_three) -> None:
    proc = _radar("prd", str(reg_three), "--floor", "4")
    out, err = _text(proc)
    assert proc.returncode == 2
    assert out == ""
    assert err == REFUSAL.format(floor=4)


def test_iter294_b1_prd_floor_equal_to_the_derived_value_accepts(reg_three) -> None:
    """The floor is inclusive, as `list` shows the same record un-flagged at floor 3."""
    proc = _radar("prd", str(reg_three), "--floor", "3")
    out, err = _text(proc)
    assert proc.returncode == 0, err
    assert err == ""
    assert json.loads(out)["sourceGap"]["id"] == "GAP-001"
    listing = _radar("list", str(reg_three), "--floor", "3")
    assert listing.returncode == 0
    assert "[below-floor]" not in listing.stdout.decode("utf-8")


def _listing(reg: pathlib.Path, *extra: str) -> dict:
    proc = _radar("list", str(reg), "--json", *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.decode("utf-8"))


def test_iter294_b1_mixed_fixture_is_what_its_docstring_says(reg_mixed) -> None:
    listing = _listing(reg_mixed)
    by_id = {r["gap_id"]: r for r in listing["records"]}
    assert by_id["GAP-001"]["confidence"] == 1 and by_id["GAP-001"]["below_floor"] is True
    assert by_id["GAP-002"]["confidence"] == 3 and by_id["GAP-002"]["below_floor"] is False
    assert by_id["GAP-001"]["priority"] > by_id["GAP-002"]["priority"]
    # the register invariant: the below-floor record is DISPLAYED, never dropped
    assert listing["counts"] == {"total": 2, "ranked": 1, "below_floor": 1}
    assert "GAP-001" in _radar("list", str(reg_mixed)).stdout.decode("utf-8")


@pytest.mark.parametrize("floor, expected", [(None, "GAP-002"), (1, "GAP-001"),
                                             (2, "GAP-002"), (3, "GAP-002")])
def test_iter294_b1_the_floor_gates_selection_not_ranking(reg_mixed, floor, expected) -> None:
    """The top-PRIORITY record is skipped while it sits below the floor the caller set."""
    argv = ["prd", str(reg_mixed)] + ([] if floor is None else ["--floor", str(floor)])
    proc = _radar(*argv)
    out, err = _text(proc)
    assert proc.returncode == 0, err
    assert err == ""
    assert json.loads(out)["sourceGap"]["id"] == expected
    # and that pick is exactly the first record `list` ranks above the SAME floor
    listing = _listing(reg_mixed, *([] if floor is None else ["--floor", str(floor)]))
    ranked = [r["gap_id"] for r in listing["records"] if not r["below_floor"]]
    assert ranked[0] == expected
    assert listing["confidence_floor"] == (2 if floor is None else floor)


def test_iter294_b1_a_floor_no_record_clears_refuses_and_list_ranks_none(reg_mixed) -> None:
    proc = _radar("prd", str(reg_mixed), "--floor", "4")
    out, err = _text(proc)
    assert proc.returncode == 2
    assert out == ""
    assert err == REFUSAL.format(floor=4)
    listing = _listing(reg_mixed, "--floor", "4")
    assert listing["counts"]["ranked"] == 0
    assert listing["counts"]["below_floor"] == 2  # still displayed, both of them


def test_iter294_b1_the_refusal_is_one_line_with_the_error_prefix_and_one_newline(
        reg_three) -> None:
    err = _radar("prd", str(reg_three), "--floor", "5").stderr.decode("utf-8")
    assert err.startswith("Error: ")
    assert err.count("\n") == 1 and err.endswith("\n")
    assert err == REFUSAL.format(floor=5)


# --------------------------------------------------------------------------------------
# Behavior 2 -- the default refusal now names the default floor (2)
# --------------------------------------------------------------------------------------

def test_iter294_b2_fixture_derives_confidence_1_and_list_flags_it(reg_low) -> None:
    assert _derived_confidence(reg_low) == 1
    listing = _radar("list", str(reg_low))
    assert listing.returncode == 0
    assert "[below-floor]" in listing.stdout.decode("utf-8")


def test_iter294_b2_prd_without_the_flag_refuses_naming_floor_2(reg_low) -> None:
    proc = _radar("prd", str(reg_low))
    out, err = _text(proc)
    assert proc.returncode == 2
    assert out == ""
    assert err == REFUSAL.format(floor=2)


def test_iter294_b2_explicit_default_floor_is_byte_identical_to_the_bare_refusal(
        reg_low) -> None:
    bare = _radar("prd", str(reg_low))
    explicit = _radar("prd", str(reg_low), "--floor", "2")
    assert (bare.returncode, bare.stdout, bare.stderr) == \
        (explicit.returncode, explicit.stdout, explicit.stderr) == \
        (2, b"", REFUSAL.format(floor=2).encode("utf-8"))


#: The three EXACT pins the spec names as moved to the new sentence, and the two
#: SUBSTRING pins that need no edit because the old sentence is a prefix of the new one.
EXACT_PINS = (
    "test_iter02_behavior.py", "test_iter06_behavior.py", "test_iter125_behavior.py")
SUBSTRING_PINS = ("test_iter217_behavior.py", "test_iter217_fix_behavior.py")
OLD_SENTENCE = "no gap clears the confidence floor"


def test_iter294_b2_the_three_exact_pins_carry_the_floor_and_the_substring_pins_stay() -> None:
    """Cross-module sweep, read as TEXT: `tests/` is inside the contract."""
    exact = re.compile(r'"Error: no gap clears the confidence floor 2\\n"')
    for name in EXACT_PINS:
        text = (TESTS / name).read_text(encoding="utf-8")
        assert exact.search(text), f"{name}: the exact pin does not name floor 2"
        assert not re.search(r'floor\\n"', text), f"{name}: an old floorless pin survives"
    for name in SUBSTRING_PINS:
        text = (TESTS / name).read_text(encoding="utf-8")
        assert f'"{OLD_SENTENCE}"' in text, f"{name}: the substring pin should be untouched"
    # and no test module still pins the refusal as a STRING LITERAL without a floor number
    literal = re.compile(r'"Error: no gap clears the confidence floor([^"]*)"')
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue  # this module spells the pattern itself
        for line in path.read_text(encoding="utf-8").splitlines():
            for tail in literal.findall(line):
                assert re.match(r" (\d+|\{floor\})", tail), f"{path.name}: {line.strip()}"


# --------------------------------------------------------------------------------------
# Behavior 3 -- lowering the floor admits the record the default refuses
# --------------------------------------------------------------------------------------

def test_iter294_b3_prd_floor_1_emits_the_prd_document_for_the_below_default_record(
        reg_low) -> None:
    proc = _radar("prd", str(reg_low), "--floor", "1")
    out, err = _text(proc)
    assert proc.returncode == 0, err
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")
    doc = json.loads(out)
    assert doc["sourceGap"]["id"] == "GAP-001"
    assert doc["sourceGap"]["confidence"] == 1
    # the same register refuses at the default (behavior 2): the flag is what changed
    assert _radar("prd", str(reg_low)).returncode == 2


def test_iter294_b3_floor_0_also_admits_it_and_the_document_does_not_change(reg_low) -> None:
    """Selection only: two admitting floors produce the SAME bytes."""
    one = _radar("prd", str(reg_low), "--floor", "1")
    zero = _radar("prd", str(reg_low), "--floor", "0")
    assert one.returncode == zero.returncode == 0
    assert one.stdout == zero.stdout


# --------------------------------------------------------------------------------------
# Behavior 4 -- the explicit default is byte-identical to the bare verb; no new key
# --------------------------------------------------------------------------------------

PRD_TOP_LEVEL_KEYS = ["project", "branchName", "description", "sourceGap", "stories"]


def test_iter294_b4_prd_floor_2_on_the_live_register_is_byte_identical_to_bare_prd() -> None:
    bare = _radar("prd", ".")
    explicit = _radar("prd", ".", "--floor", "2")
    assert bare.returncode == 0, bare.stderr
    assert explicit.returncode == 0, explicit.stderr
    assert bare.stderr == explicit.stderr == b""
    assert bare.stdout == explicit.stdout
    assert bare.stdout.endswith(b"\n") and not bare.stdout.endswith(b"\n\n")


def test_iter294_b4_the_prd_document_gains_no_key() -> None:
    out = _radar("prd", ".", "--floor", "2").stdout.decode("utf-8")
    doc = json.loads(out)
    assert list(doc.keys()) == PRD_TOP_LEVEL_KEYS
    assert "confidence_floor" not in out
    assert "confidenceFloor" not in out
    assert "floor" not in json.dumps(list(doc.keys()) + list(doc["sourceGap"].keys()))


# --------------------------------------------------------------------------------------
# Behavior 5 -- `--gap` bypasses the floor entirely
# --------------------------------------------------------------------------------------

def test_iter294_b5_gap_with_floor_5_is_byte_identical_to_gap_alone() -> None:
    plain = _radar("prd", ".", "--gap", "GAP-001")
    floored = _radar("prd", ".", "--gap", "GAP-001", "--floor", "5")
    assert plain.returncode == floored.returncode == 0, (plain.stderr, floored.stderr)
    assert plain.stdout == floored.stdout
    assert json.loads(plain.stdout.decode("utf-8"))["sourceGap"]["id"] == "GAP-001"


def test_iter294_b5_gap_bypasses_a_floor_no_derived_confidence_can_reach() -> None:
    """Weights top out at 5 (`radar taxonomy`), so floor 6 clears nothing -- unless named."""
    named = _radar("prd", ".", "--gap", "GAP-001", "--floor", "6")
    plain = _radar("prd", ".", "--gap", "GAP-001")
    assert named.returncode == 0, named.stderr
    assert named.stdout == plain.stdout
    unnamed = _radar("prd", ".", "--floor", "6")
    out, err = _text(unnamed)
    assert unnamed.returncode == 2
    assert out == ""
    assert err == REFUSAL.format(floor=6)


def test_iter294_b5_gap_on_a_below_floor_record_still_bypasses(reg_low) -> None:
    """The fixture's record derives 1; naming it at the default floor still emits the PRD."""
    proc = _radar("prd", str(reg_low), "--gap", "GAP-001")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.decode("utf-8"))["sourceGap"]["id"] == "GAP-001"


# --------------------------------------------------------------------------------------
# Behavior 6 -- help text and the parser census
# --------------------------------------------------------------------------------------

def _floor_help_line(verb: str) -> str:
    """The whole `--floor` help ENTRY, argparse continuation lines joined with a space.

    `scan --floor`'s text wraps onto three lines, so reading only the line that starts
    with `--floor` would miss its `(default 2)` tail.
    """
    proc = _radar(verb, "--help")
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.decode("utf-8").splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("--floor")]
    assert len(starts) == 1, proc.stdout
    i = starts[0]
    entry = [lines[i].rstrip()]
    indent = len(lines[i]) - len(lines[i].lstrip())
    for ln in lines[i + 1:]:
        # a continuation line is indented deeper than the option column and is not an option
        if ln.strip() and not ln.lstrip().startswith("-") and \
                len(ln) - len(ln.lstrip()) > indent:
            entry.append(ln.strip())
        else:
            break
    return " ".join(entry)


def test_iter294_b6_prd_help_lists_floor_with_default_2_mirroring_report() -> None:
    prd_line = _floor_help_line("prd")
    assert prd_line.endswith("(default 2)"), prd_line
    assert _floor_help_line("report").endswith("(default 2)")
    usage = _radar("prd", "--help").stdout.decode("utf-8")
    assert "[--floor FLOOR]" in usage


def test_iter294_b6_argument_census_gains_the_floor_row_after_gap_id() -> None:
    text = (TESTS / "test_iter111_behavior.py").read_text(encoding="utf-8")
    start = text.index('"prd": [')
    end = text.index("\n    ],", start)
    block = text[start:end]
    gap_row = '("gap_id", ["--gap"], False, None, None)'
    floor_row = '("floor", ["--floor"], False, 2, None)'
    assert gap_row in block and floor_row in block, block
    assert block.index(gap_row) < block.index(floor_row)
    project_row = '("project", ["--project"]'
    assert block.index(floor_row) < block.index(project_row)


def test_iter294_b6_a_non_integer_floor_is_a_usage_error_on_stderr_with_exit_2() -> None:
    """Mirrors `list --floor x`: argparse's type error, stdout empty."""
    prd = _radar("prd", ".", "--floor", "x")
    lst = _radar("list", ".", "--floor", "x")
    assert prd.returncode == lst.returncode == 2
    assert prd.stdout == lst.stdout == b""
    assert b"invalid int value: 'x'" in prd.stderr
    assert prd.stderr.decode("utf-8").rstrip("\n").splitlines()[-1].startswith("Error: ")


FLOOR_VERBS = ("list", "prd", "report", "scan")


def test_iter294_b6_all_four_floor_verbs_publish_the_same_default_in_help(reg_three) -> None:
    """`prd` now mirrors `list`/`report`/`scan`: one spelling, one default, all four."""
    for verb in FLOOR_VERBS:
        line = _floor_help_line(verb)
        assert line.lstrip().startswith("--floor FLOOR"), (verb, line)
        assert line.endswith("(default 2)"), (verb, line)
    # and the default `prd` applies is the one `list --json` echoes as `confidence_floor`
    assert _listing(reg_three)["confidence_floor"] == 2


# --------------------------------------------------------------------------------------
# Behavior 7 -- the published Defaults table
# --------------------------------------------------------------------------------------

def _defaults_rows() -> list[tuple[str, str, str]]:
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index("\n## Defaults\n")
    end = text.find("\n## ", start + 1)
    section = text[start:end if end != -1 else None]
    rows = []
    for line in section.splitlines():
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells == ["Verb", "Argument", "Default"]:
            continue
        rows.append(tuple(c.strip("`") for c in cells))
    return rows


def test_iter294_b7_defaults_table_has_eleven_sorted_triples_with_the_prd_floor_row() -> None:
    rows = _defaults_rows()
    assert len(rows) == 11, rows
    assert rows == sorted(rows), "the table is sorted by verb then argument"
    assert ("prd", "--floor", "2") in rows
    i = rows.index(("prd", "--floor", "2"))
    assert rows[i + 1][:2] == ("prd", "--project")
    floors = {verb for verb, arg, default in rows if arg == "--floor"}
    assert floors == {"list", "prd", "report", "scan"}
    assert {default for verb, arg, default in rows if arg == "--floor"} == {"2"}


def test_iter294_b7_defaults_sentence_and_the_synopsis_cell_agree_with_help() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "Every value-bearing argument every VERB defaults is above" in text
    synopsis = [ln for ln in text.splitlines() if ln.startswith("| `radar prd ")]
    assert len(synopsis) == 1
    assert "[--floor N]" in synopsis[0]


# --------------------------------------------------------------------------------------
# Behavior 8 -- byte-control arm against the pre-change commit
# --------------------------------------------------------------------------------------

def _env(src: pathlib.Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    return env


@pytest.fixture(scope="module")
def prechange_src(tmp_path_factory) -> pathlib.Path:
    """`git archive PRECHANGE_COMMIT src` under a tmp dir, probed to be what is imported."""
    root = tmp_path_factory.mktemp("prechange294")
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", PRECHANGE_COMMIT, "src"], capture_output=True)
    assert archive.returncode == 0, archive.stderr.decode("utf-8", "replace")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(root, filter="data")
    src = root / "src"
    probe = subprocess.run(
        [sys.executable, "-c", "import agent_gap_radar; print(agent_gap_radar.__file__)"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=_env(src))
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip().startswith(str(src)), probe.stdout
    return src


def test_iter294_b8_the_control_arm_is_really_the_pre_change_build(prechange_src) -> None:
    """At the pre-change commit `prd --floor` is the defect the spec re-confirmed."""
    proc = _radar("prd", ".", "--floor", "3", env=_env(prechange_src))
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert UNRECOGNIZED in proc.stderr.decode("utf-8")
    # and the working tree accepts it
    assert _radar("prd", ".", "--floor", "3").returncode == 0


CONTROL_CASES = (
    ("list", "."),
    ("report", "."),
    ("scan", ".", "--gaps", ".", "--json"),
    ("show", "GAP-001", "."),
    ("validate", "."),
    ("prd", "."),
    ("prd", ".", "--gap", "GAP-001"),
)


@pytest.mark.parametrize("argv", CONTROL_CASES, ids=lambda a: " ".join(a))
def test_iter294_b8_stdout_and_exit_code_match_the_pre_change_commit(
        prechange_src, argv) -> None:
    before = _radar(*argv, env=_env(prechange_src))
    now = _radar(*argv, env=_env(REPO_ROOT / "src"))
    assert before.returncode == now.returncode, (before.stderr, now.stderr)
    assert before.stdout == now.stdout, argv
    assert now.stdout.endswith(b"\n") and not now.stdout.endswith(b"\n\n")


def test_iter294_b8_register_doc_is_untouched() -> None:
    before = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{PRECHANGE_COMMIT}:REGISTER.md"],
        capture_output=True)
    assert before.returncode == 0, before.stderr
    assert (REPO_ROOT / "REGISTER.md").read_bytes() == before.stdout


def test_iter294_b8_register_doc_brake_stays_green() -> None:
    proc = subprocess.run(
        [sys.executable, "tools/check_register_doc.py"], capture_output=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, (
        f"tools/check_register_doc.py exited {proc.returncode}: "
        f"{proc.stdout.decode('utf-8', 'replace')}{proc.stderr.decode('utf-8', 'replace')}")


def test_iter294_b8_no_machine_paths_or_identifiers_in_this_module() -> None:
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    # markers assembled from parts so the check cannot trip on its own spelling
    for marker in ("/" + "Users" + "/", "/" + "home" + "/", "C:" + "\\"):
        assert marker not in text, marker
