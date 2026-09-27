"""Iteration 300 (re-land of iteration 299's tree): `radar scan --exit-code --baseline <prior scan --json file>`.

Black-box over the public CLI and the published documents. Every expectation comes from
`pm.md`'s Expected Behaviors 1-11; behavior 12 (flagless invariance) is carried by the
committed goldens and is not restated here. `docs/CONSUMER_CONTRACT.md` is read through
the oracle already committed at `tests/_surface_contract.py`, as the PUBLISHED DOCUMENT
behavior 1 legislates over.

Structural notes, so this file cannot lie later:

* **Every verdict claim is paired with its flagless twin in the same test.** A baseline
  test that only ran the flagged form could pass against a `scan` that returned 0
  unconditionally; behavior 3 runs `--exit-code` WITHOUT the baseline on the same tree and
  asserts it still exits 1, so the 0 is provably the baseline's doing.
* **The fixture verdicts are DERIVED and then ASSERTED, never assumed.** `test_b0_...`
  reads the verdict and confidence the tool itself publishes for every (target, record)
  pair the behaviors below lean on, so a check that stopped discriminating fails loudly
  instead of turning the gate sweeps into assertions about nothing.
* **Baselines are real `scan --json` stdout**, written to a file exactly as a consumer
  would write them; none is hand-typed, except the deliberately malformed documents of
  behavior 9, whose whole point is that they are not what the tool writes.
* **Registers and targets are built ONCE per module** under pytest's `tmp_path_factory`,
  three records and five two-file trees; no test scans this repository, so this module
  adds no live self-scan to the suite wall.
* **No absolute machine path and no personal identifier appears here.** Every path in an
  expected `Error: ` line is the SAME string the test passed as the argument, compared as
  a value and never spelled.

Fixture vocabulary: gap A (`GAP-701`, confidence 5) and gap B (`GAP-702`, confidence 5) each
have a check whose `present_when` matches its own signature token and whose
`mitigated_when` matches its own fix token, so a tree can make either one PRESENT or ABSENT
independently. Gap W (`GAP-703`) is the same shape at confidence 0 (`model-output`), so it is
PRESENT-but-below-floor whenever its signature is in the tree -- the record behavior 4 needs.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar import cli
from agent_gap_radar.cli import main
from test_iter02_behavior import _record
from _surface_contract import (contract_text, defaults_violations, gfm_table,
                              parser_surface, surface_table_cells, surface_violations,
                              DEFAULTS_HEADING)

#: The register floor when `--floor` is omitted; behavior 4 sweeps around it.
DEFAULT_FLOOR = 2

#: Tokens the fixture checks look for. `SIG` makes a gap PRESENT, `FIX` makes it ABSENT
#: (a positively identified mitigation); a tree carries exactly one of each pair.
SIG = {"A": "RADAR_I299_SIGNATURE_A", "B": "RADAR_I299_SIGNATURE_B",
       "W": "RADAR_I299_SIGNATURE_W"}
FIX = {"A": "RADAR_I299_MITIGATION_A", "B": "RADAR_I299_MITIGATION_B",
       "W": "RADAR_I299_MITIGATION_W"}
GAP = {"A": "GAP-701", "B": "GAP-702", "W": "GAP-703"}
CHK = {"A": "CHK-701", "B": "CHK-702", "W": "CHK-703"}

#: The three verdict codes the spec assigns. Named so nothing below invents a fourth.
NEW, CLEAN, REFUSED = 1, 0, 2

REQUIRES_EXIT_CODE = ("Error: --baseline requires --exit-code: a baseline only changes "
                      "the verdict, and without --exit-code there is no verdict to change")


def _check(letter: str) -> dict:
    """A two-sided check: PRESENT on the signature token, ABSENT on the mitigation token."""
    sig, fix = SIG[letter], FIX[letter]
    return {
        "id": CHK[letter], "rationale": "r",
        "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": sig},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": fix},
        "fixtures": {"bad": {"a.py": sig + "\n"}, "good": {"a.py": fix + "\n"}},
    }


def _gap(letter: str, classes: tuple[str, ...]) -> dict:
    rec = _record(GAP[letter], 4, 4, 4, classes, None)
    rec["check"] = _check(letter)
    return rec


REGISTER = [
    _gap("A", ("first-party-field",)),   # confidence 5
    _gap("B", ("first-party-field",)),   # confidence 5
    _gap("W", ("model-output",)),        # confidence 0: below the default floor
]

#: Every tree, as the set of letters whose SIGNATURE it carries; the other letters carry
#: their MITIGATION token, so every check verdicts PRESENT or ABSENT and never MANUAL.
TREES = {
    "only_a": {"A"},
    "a_and_b": {"A", "B"},
    "none": set(),
    "a_and_w": {"A", "W"},
    "b_only": {"B"},
}


def _run(argv):
    """Drive the public CLI entry point in-process; observe only code, stdout, stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _tree(root: pathlib.Path, present: set[str], name: str = "target") -> pathlib.Path:
    """A target directory named `name` carrying one .py file per fixture gap."""
    t = root / name
    (t / "app").mkdir(parents=True)
    for letter in SIG:
        token = SIG[letter] if letter in present else FIX[letter]
        (t / "app" / f"{letter.lower()}.py").write_text(token + "\n", encoding="utf-8")
    return t


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    """One register, five same-named target trees, two real baselines; built once."""
    root = tmp_path_factory.mktemp("iter299")
    reg = root / "reg" / "gaps"
    reg.mkdir(parents=True)
    for rec in REGISTER:
        (reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    trees = {label: _tree(root / label, present) for label, present in TREES.items()}
    # A tree whose BASE NAME differs from every baseline's `target_name`, for behavior 10.
    trees["renamed"] = _tree(root / "renamed", {"A"}, name="service")
    empty = root / "empty" / "gaps"
    empty.mkdir(parents=True)

    def baseline(label: str, *extra) -> pathlib.Path:
        rc, out, err = _run(["scan", str(trees[label]), "--gaps", str(reg), "--json", *extra])
        assert (rc, err) == (0, ""), (label, rc, err)
        path = root / f"baseline-{label}{'-' + '-'.join(extra) if extra else ''}.json"
        path.write_text(out, encoding="utf-8")
        return path

    return {
        "root": root, "reg": reg, "empty": empty, "trees": trees,
        "b_only_a": baseline("only_a"),
        # Written at an unclearable floor, so every PRESENT finding in it is below_floor.
        "b_a_and_w_floor6": baseline("a_and_w", "--floor", "6"),
    }


def _scan(bed, tree: str, *extra, register: str = "reg"):
    return _run(["scan", str(bed["trees"][tree]), "--gaps", str(bed[register]), *extra])


def _gate(bed, tree: str, baseline_key: str, *extra):
    """`scan T --gaps R --exit-code --baseline B [extra]`, asserting stderr is empty."""
    rc, out, err = _scan(bed, tree, "--exit-code", "--baseline", str(bed[baseline_key]),
                         *extra)
    assert err == "", (tree, baseline_key, err)
    return rc, out


def _verdicts(payload_text: str) -> dict[str, tuple[str, int, bool]]:
    return {f["gap_id"]: (f["verdict"], f["confidence"], f["below_floor"])
            for f in json.loads(payload_text)["findings"]}


def _last_stderr_line(err: str) -> str:
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, "stderr was empty where a refusal was expected"
    return lines[-1]


# ---------------------------------------------------------------------------
# Behavior 0 (guard, not a spec behavior) -- the fixtures verdict as the vocabulary says.
# ---------------------------------------------------------------------------

def test_b0_fixture_verdicts_are_what_the_tool_derives(bed):
    """Every sweep below is meaningless unless A/B are confidence-5 and W is 0, and unless
    each tree makes exactly its named letters PRESENT and the rest ABSENT."""
    for label, present in TREES.items():
        rc, out, err = _scan(bed, label, "--json")
        assert (rc, err) == (0, ""), (label, rc, err)
        seen = _verdicts(out)
        assert set(seen) == set(GAP.values()), label
        for letter, gid in GAP.items():
            verdict, confidence, below = seen[gid]
            assert verdict == ("PRESENT" if letter in present else "ABSENT"), (label, gid)
            assert confidence == (0 if letter == "W" else 5), (label, gid)
            assert below is (letter == "W"), (label, gid)
    # The two baselines really do carry what the behaviors assume of them.
    b1 = _verdicts(bed["b_only_a"].read_text(encoding="utf-8"))
    assert b1[GAP["A"]][0] == "PRESENT" and b1[GAP["B"]][0] == "ABSENT"
    assert b1[GAP["W"]][0] == "ABSENT"
    b6 = json.loads(bed["b_a_and_w_floor6"].read_text(encoding="utf-8"))
    assert b6["confidence_floor"] == 6
    assert {f["gap_id"]: (f["verdict"], f["below_floor"]) for f in b6["findings"]} == {
        GAP["A"]: ("PRESENT", True), GAP["B"]: ("ABSENT", True), GAP["W"]: ("PRESENT", True)}
    # Both baselines name the same resolved base name, which is what behavior 10 compares.
    assert json.loads(bed["b_only_a"].read_text(encoding="utf-8"))["target_name"] == "target"
    assert b6["target_name"] == "target"


# ---------------------------------------------------------------------------
# Behavior 1 -- parser surface: a plain option of `scan`, outside the exclusive group.
# ---------------------------------------------------------------------------

def _scan_parser():
    parser = cli.build_parser()
    sub = next(a for a in parser._actions
               if isinstance(a, cli.argparse._SubParsersAction))
    return sub.choices["scan"]


def test_b1_help_lists_baseline_with_its_metavar():
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as exc:
        main(["scan", "--help"])
    assert exc.value.code == 0
    assert "--baseline BASELINE" in out.getvalue()


def test_b1_baseline_is_a_plain_option_outside_the_exclusive_group():
    p = _scan_parser()
    action = next(a for a in p._actions if a.option_strings == ["--baseline"])
    assert action.metavar == "BASELINE"
    assert action.default is None
    assert action.nargs is None, "takes exactly one value"
    grouped = [g for g in p._mutually_exclusive_groups if action in g._group_actions]
    assert grouped == [], "--baseline must not join the --prd/--exit-code group"
    # The group itself is unchanged: `--prd` and `--exit-code` still exclude each other.
    verdict_group = [g for g in p._mutually_exclusive_groups
                     if {"--prd", "--exit-code"} <= {s for a in g._group_actions
                                                     for s in a.option_strings}]
    assert len(verdict_group) == 1


def test_b1_no_other_verb_gains_the_flag():
    surface = parser_surface()
    assert "--baseline" in surface["scan"].options
    assert surface["scan"].takes_value["--baseline"] is True
    for verb, measured in surface.items():
        if verb != "scan":
            assert "--baseline" not in measured.options, verb


def test_b1_contract_row_names_the_flag_after_exit_code_and_the_oracle_agrees():
    document = contract_text()
    scan_cell = next(c for c in surface_table_cells(document) if "radar scan" in c)
    assert "[--exit-code] [--baseline BASELINE]" in scan_cell
    assert surface_violations(document) == []
    assert defaults_violations(document) == []
    defaults = gfm_table(document, DEFAULTS_HEADING)
    assert not any("baseline" in cell for row in defaults.rows for cell in row), (
        "a None default earns no `## Defaults` row, exactly like `--gap`")


# ---------------------------------------------------------------------------
# Behaviors 2, 3 -- the verdict: new above-floor PRESENT -> 1; nothing new -> 0.
# ---------------------------------------------------------------------------

def test_b2_a_gap_the_baseline_did_not_carry_exits_1(bed):
    rc, _ = _gate(bed, "a_and_b", "b_only_a")
    assert rc == NEW


def test_b3_a_carried_backlog_exits_0_where_the_bare_gate_exits_1(bed):
    rc, _ = _gate(bed, "only_a", "b_only_a")
    assert rc == CLEAN
    bare_rc, _, bare_err = _scan(bed, "only_a", "--exit-code")
    assert (bare_rc, bare_err) == (NEW, ""), "without the baseline A alone is still red"


# ---------------------------------------------------------------------------
# Behavior 4 -- the baseline's PRESENT set ignores confidence; the floor gates only NOW.
# ---------------------------------------------------------------------------

def test_b4_a_below_floor_baseline_present_still_counts_as_carried(bed):
    # Baseline written at --floor 6: A and W are PRESENT with below_floor true. The same
    # tree now, at the default floor, has A above-floor PRESENT -- carried, not new.
    rc, out = _gate(bed, "a_and_w", "b_a_and_w_floor6")
    assert rc == CLEAN
    assert "carried PRESENT: 2; new above-floor PRESENT: 0 (none)" in out


def test_b4_only_the_current_scan_applies_the_floor(bed):
    # W (confidence 0) is newly PRESENT against a baseline that had it ABSENT. At the
    # default floor it is a research task, not a regression; at --floor 0 it is new.
    rc, out = _gate(bed, "a_and_w", "b_only_a")
    assert rc == CLEAN
    assert "new above-floor PRESENT: 0 (none)" in out
    rc0, out0 = _gate(bed, "a_and_w", "b_only_a", "--floor", "0")
    assert rc0 == NEW
    assert f"new above-floor PRESENT: 1 ({GAP['W']})" in out0


# ---------------------------------------------------------------------------
# Behavior 5 -- a fix is never bad news; ABSENT-then-PRESENT is a regression.
# ---------------------------------------------------------------------------

def test_b5_a_fixed_gap_is_not_new(bed):
    rc, out = _gate(bed, "none", "b_only_a")
    assert rc == CLEAN
    assert "carried PRESENT: 1; new above-floor PRESENT: 0 (none)" in out


def test_b5_absent_in_baseline_and_present_now_is_new(bed):
    rc, out = _gate(bed, "b_only", "b_only_a")
    assert rc == NEW
    assert f"new above-floor PRESENT: 1 ({GAP['B']})" in out


# ---------------------------------------------------------------------------
# Behavior 6 -- the document is the flagless document plus EXACTLY one line.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tree, expected_tail", [
    ("a_and_b", f"new above-floor PRESENT: 1 ({GAP['B']})"),
    ("only_a", "new above-floor PRESENT: 0 (none)"),
])
def test_b6_one_line_inserted_directly_after_the_no_check_census(bed, tree, expected_tail):
    plain_rc, plain_out, plain_err = _scan(bed, tree)
    assert (plain_rc, plain_err) == (0, "")
    _, flagged_out = _gate(bed, tree, "b_only_a")
    plain, flagged = plain_out.splitlines(), flagged_out.splitlines()
    assert len(flagged) == len(plain) + 1
    anchor = next(i for i, line in enumerate(plain)
                  if line.startswith("Gaps with no check yet: "))
    inserted = flagged[anchor + 1]
    assert flagged[:anchor + 1] == plain[:anchor + 1]
    assert flagged[anchor + 2:] == plain[anchor + 1:]
    assert inserted == (f"Baseline: {bed['b_only_a']} -- carried PRESENT: 1; "
                        + expected_tail)
    assert flagged_out.endswith("\n") and not flagged_out.endswith("\n\n")
    # Deterministic: a second run is byte-identical.
    assert _gate(bed, tree, "b_only_a")[1] == flagged_out


def test_b6_the_line_echoes_the_path_as_typed(bed):
    # A RELATIVE spelling must be echoed relative, not resolved.
    relative = pathlib.Path(bed["b_only_a"].name)
    rc, out, err = _run(["scan", str(bed["trees"]["only_a"]), "--gaps", str(bed["reg"]),
                         "--exit-code", "--baseline", str(relative)])
    if rc == REFUSED:
        # The cwd is not the bed root, so the relative path does not resolve: the
        # refusal must still echo the spelling as typed.
        assert _last_stderr_line(err) == f"Error: not a file: {relative}"
    else:
        assert f"Baseline: {relative} -- " in out


# ---------------------------------------------------------------------------
# Behavior 7 -- `--json` payload untouched; the exit code still follows 2-5.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tree, expected_rc", [("a_and_b", NEW), ("only_a", CLEAN),
                                               ("none", CLEAN), ("b_only", NEW)])
def test_b7_json_payload_is_byte_identical_and_the_code_still_moves(bed, tree, expected_rc):
    plain_rc, plain_out, plain_err = _scan(bed, tree, "--json")
    assert (plain_rc, plain_err) == (0, "")
    rc, out = _gate(bed, tree, "b_only_a", "--json")
    assert out == plain_out
    assert rc == expected_rc
    assert "baseline" not in json.loads(out), "no new key"


# ---------------------------------------------------------------------------
# Behavior 8 -- the flag without `--exit-code` is refused before anything is read.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [(), ("--prd",), ("--json",)])
def test_b8_baseline_without_exit_code_is_refused(bed, extra):
    rc, out, err = _scan(bed, "a_and_b", *extra, "--baseline", str(bed["b_only_a"]))
    assert rc == REFUSED
    assert out == ""
    assert _last_stderr_line(err) == REQUIRES_EXIT_CODE


# ---------------------------------------------------------------------------
# Behavior 9 -- not a file / not a scan document.
# ---------------------------------------------------------------------------

def test_b9_missing_baseline_is_not_a_file(bed):
    missing = str(bed["root"] / "no-such-baseline.json")
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", missing)
    assert (rc, out) == (REFUSED, "")
    assert _last_stderr_line(err) == f"Error: not a file: {missing}"


def test_b9_a_directory_is_not_a_file(bed):
    directory = str(bed["root"])
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", directory)
    assert (rc, out) == (REFUSED, "")
    assert _last_stderr_line(err) == f"Error: not a file: {directory}"


def _bad_documents(bed) -> dict[str, str]:
    root = bed["root"] / "bad"
    root.mkdir(exist_ok=True)
    docs = {
        "not-json": "{not json at all",
        "json-array": "[]",
        "no-findings": json.dumps({"target_name": "target"}),
        "no-target-name": json.dumps({"findings": []}),
        "repeated-key": ('{"target_name": "target", "findings": [], '
                         '"target_name": "target"}'),
    }
    # A `radar list --json` payload: JSON, an object, and not a scan document.
    rc, out, err = _run(["list", str(bed["reg"]), "--json"])
    assert (rc, err) == (0, ""), err
    docs["list-payload"] = out
    written = {}
    for name, text in docs.items():
        path = root / f"{name}.json"
        path.write_text(text, encoding="utf-8")
        written[name] = str(path)
    return written


@pytest.mark.parametrize("name", ["not-json", "json-array", "no-findings",
                                  "no-target-name", "repeated-key", "list-payload"])
def test_b9_anything_but_a_scan_document_is_refused(bed, name):
    path = _bad_documents(bed)[name]
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", path)
    assert (rc, out) == (REFUSED, ""), (name, err)
    assert _last_stderr_line(err) == f"Error: not a scan document: {path}"


def test_b9_repeated_key_is_refused_even_though_json_loads_accepts_it(bed):
    """The vacuity guard for the strict-parser clause: stdlib would have read it."""
    text = ('{"target_name": "target", "findings": [], "target_name": "target"}')
    assert json.loads(text)["target_name"] == "target"  # stdlib keeps the last copy
    path = _bad_documents(bed)["repeated-key"]
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", path)
    assert rc == REFUSED and out == ""


# ---------------------------------------------------------------------------
# Behavior 10 -- target mismatch names both sides.
# ---------------------------------------------------------------------------

def test_b10_target_name_mismatch_is_refused(bed):
    rc, out, err = _scan(bed, "renamed", "--exit-code", "--baseline", str(bed["b_only_a"]))
    assert (rc, out) == (REFUSED, "")
    assert _last_stderr_line(err) == (
        "Error: baseline target mismatch: target (baseline) vs service (target)")


# ---------------------------------------------------------------------------
# Behavior 11 -- the zero-records refusal still fires first; the baseline is never read.
# ---------------------------------------------------------------------------

def test_b11_zero_records_refusal_precedes_the_baseline(bed):
    missing = str(bed["root"] / "never-read.json")
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", missing,
                         register="empty")
    assert (rc, out) == (REFUSED, "")
    last = _last_stderr_line(err)
    assert last.startswith("Error: scan applied 0 register records")
    assert "baseline" not in err.lower() and missing not in err


# ===========================================================================
# Tester round (iteration 299) -- black-box extensions past the module above.
#
# Each test below closes a corner the numbered behaviors legislate over but no test
# above reaches: K = 0 with M >= 2 (the `, ` join and its order), `--floor` composing
# with the inserted line, the "resolved base name" of behavior 10 under three spellings
# of the same target, the success arm of "path as typed" (the test above only reaches its
# refusal arm when cwd is not the bed), refusal ORDER where the spec leaves it open (noted
# as an ambiguity in the tester report), two more not-a-scan-document shapes, the closed
# refusal list of behavior 9 read together with behavior 4, and the published prose the
# acceptance criteria name. No live self-scan is spawned here either.
# ===========================================================================

import os  # noqa: E402  (tester section; kept beside its only users)


def _baseline_line(document: str) -> str:
    """The ONE `Baseline:` line of a flagged document; more or fewer than one is a fail."""
    lines = [line for line in document.splitlines() if line.startswith("Baseline: ")]
    assert len(lines) == 1, lines
    return lines[0]


@pytest.fixture(scope="module")
def b_none(bed):
    """A real baseline that carries NOTHING PRESENT (K = 0), written from `scan --json`."""
    rc, out, err = _scan(bed, "none", "--json")
    assert (rc, err) == (0, ""), err
    assert all(f["verdict"] == "ABSENT" for f in json.loads(out)["findings"])
    path = bed["root"] / "baseline-none.json"
    path.write_text(out, encoding="utf-8")
    return path


# --- Behavior 6: the `, ` join, ascending, and a zero carry ----------------------------

def test_t6_two_new_ids_join_ascending_after_a_zero_carry(bed, b_none):
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", str(b_none))
    assert (rc, err) == (NEW, "")
    assert GAP["A"] < GAP["B"], "the fixture must sort the way the line is expected to"
    assert _baseline_line(out) == (f"Baseline: {b_none} -- carried PRESENT: 0; "
                                   f"new above-floor PRESENT: 2 ({GAP['A']}, {GAP['B']})")
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_t6_floor_composes_with_the_line_and_gates_only_the_current_set(bed, b_none):
    """At `--floor 6` nothing clears, so two PRESENT gaps the baseline never carried are
    still not "new"; the document is the flagless `--floor 6` document plus one line."""
    plain_rc, plain_out, plain_err = _scan(bed, "a_and_b", "--floor", "6")
    assert (plain_rc, plain_err) == (0, "")
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", str(b_none),
                         "--floor", "6")
    assert (rc, err) == (CLEAN, "")
    plain, flagged = plain_out.splitlines(), out.splitlines()
    assert len(flagged) == len(plain) + 1
    anchor = next(i for i, line in enumerate(plain)
                  if line.startswith("Gaps with no check yet: "))
    assert flagged[:anchor + 1] == plain[:anchor + 1]
    assert flagged[anchor + 2:] == plain[anchor + 1:]
    assert flagged[anchor + 1] == (f"Baseline: {b_none} -- carried PRESENT: 0; "
                                   "new above-floor PRESENT: 0 (none)")
    # The same tree at the default floor IS red against this baseline: the 0 was the floor.
    assert _scan(bed, "a_and_b", "--exit-code", "--baseline", str(b_none))[0] == NEW


# --- Behavior 10: "resolved base name" -- three spellings of one target -------------

def test_t10_trailing_slash_spelling_resolves_to_the_same_base_name(bed):
    rc, out, err = _run(["scan", str(bed["trees"]["only_a"]) + os.sep, "--gaps",
                         str(bed["reg"]), "--exit-code", "--baseline", str(bed["b_only_a"])])
    assert (rc, err) == (CLEAN, "")
    assert _baseline_line(out).startswith(f"Baseline: {bed['b_only_a']} -- carried PRESENT: 1;")


def test_t10_dot_from_inside_the_tree_resolves_to_the_same_base_name(bed, monkeypatch):
    monkeypatch.chdir(bed["trees"]["only_a"])
    rc, out, err = _run(["scan", ".", "--gaps", str(bed["reg"]), "--exit-code",
                         "--baseline", str(bed["b_only_a"])])
    assert (rc, err) == (CLEAN, "")
    assert _baseline_line(out) == (f"Baseline: {bed['b_only_a']} -- carried PRESENT: 1; "
                                   "new above-floor PRESENT: 0 (none)")


def test_t6_relative_baseline_is_echoed_as_typed_on_the_success_arm(bed, monkeypatch):
    """The refusal arm of "as typed" is pinned above; this is the arm that verdicts."""
    monkeypatch.chdir(bed["root"])
    typed = bed["b_only_a"].name                       # a bare relative file name
    target = os.path.relpath(bed["trees"]["only_a"], bed["root"])
    rc, out, err = _run(["scan", target, "--gaps", str(bed["reg"]), "--exit-code",
                         "--baseline", typed])
    assert (rc, err) == (CLEAN, "")
    assert _baseline_line(out) == (f"Baseline: {typed} -- carried PRESENT: 1; "
                                   "new above-floor PRESENT: 0 (none)")
    assert str(bed["b_only_a"]) not in out, "resolved, not as typed"


# --- Refusal ORDER the spec leaves open (most reasonable reading; see tester report) ---

def test_t8_the_usage_refusal_outranks_a_missing_file(bed):
    """`--baseline <missing>` without `--exit-code`: the argv-level refusal (8) fires
    before any file is looked at (9), so the message names the flag, not the file."""
    missing = str(bed["root"] / "never-opened.json")
    rc, out, err = _scan(bed, "only_a", "--baseline", missing)
    assert (rc, out) == (REFUSED, "")
    assert _last_stderr_line(err) == REQUIRES_EXIT_CODE
    assert missing not in err


def test_t11_an_unscannable_target_is_refused_before_the_baseline_is_read(bed):
    missing = str(bed["root"] / "never-opened-either.json")
    rc, out, err = _run(["scan", str(bed["root"] / "no-such-target"), "--gaps",
                         str(bed["reg"]), "--exit-code", "--baseline", missing])
    assert (rc, out) == (REFUSED, "")
    last = _last_stderr_line(err)
    assert last.startswith("Error: ")
    assert not last.startswith(("Error: not a file:", "Error: not a scan document:",
                                "Error: baseline target mismatch:"))
    assert last != REQUIRES_EXIT_CODE
    assert missing not in err and "baseline" not in err.lower()


# --- Behavior 9: two more shapes that are not a scan document --------------------------

@pytest.mark.parametrize("name, text", [
    ("empty-file", ""),
    ("findings-not-a-list", json.dumps({"target_name": "target", "findings": {}})),
])
def test_t9_more_shapes_that_are_not_a_scan_document(bed, name, text):
    path = bed["root"] / f"tester-{name}.json"
    path.write_text(text, encoding="utf-8")
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", str(path))
    assert (rc, out) == (REFUSED, ""), (name, err)
    assert _last_stderr_line(err) == f"Error: not a scan document: {path}"


# --- Behaviors 4 + 9 together: PRESENT carries on `verdict` alone --------------------

def test_t4_a_present_entry_without_confidence_keys_still_carries(bed):
    """Behavior 9 closes the refusal list (missing `target_name`/`findings`, bad JSON,
    repeated key), and behavior 4 says the baseline's PRESENT set ignores confidence;
    read together, an entry carrying only `gap_id` and `verdict` is a carried PRESENT."""
    path = bed["root"] / "tester-verdict-only.json"
    path.write_text(json.dumps({"target_name": "target",
                                "findings": [{"gap_id": GAP["B"], "verdict": "PRESENT"}]}),
                    encoding="utf-8")
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", str(path))
    assert (rc, err) == (NEW, "")
    assert _baseline_line(out) == (f"Baseline: {path} -- carried PRESENT: 1; "
                                   f"new above-floor PRESENT: 1 ({GAP['A']})")


# --- Composition with `--gap`: the current set is the narrowed domain ------------------

@pytest.mark.parametrize("letter, expected_rc, tail", [
    ("A", CLEAN, "new above-floor PRESENT: 0 (none)"),
    ("B", NEW, f"new above-floor PRESENT: 1 ({GAP['B']})"),
])
def test_t2_gap_narrowing_leaves_only_that_record_in_the_current_set(bed, letter,
                                                                     expected_rc, tail):
    rc, out, err = _scan(bed, "a_and_b", "--gap", GAP[letter], "--exit-code",
                         "--baseline", str(bed["b_only_a"]))
    assert (rc, err) == (expected_rc, "")
    assert _baseline_line(out) == f"Baseline: {bed['b_only_a']} -- carried PRESENT: 1; {tail}"


# --- The published prose the acceptance criteria name --------------------------------

def _readme_text() -> str:
    return (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8")


def test_tdoc_readme_quickstart_shows_the_baseline_flow_on_exactly_one_line():
    lines = [line for line in _readme_text().splitlines() if "--baseline" in line]
    assert len(lines) == 1, lines
    (line,) = lines
    assert "--json > baseline.json" in line
    assert "--exit-code --baseline baseline.json" in line
    assert line.index("--json > baseline.json") < line.index("--exit-code --baseline")


def test_tdoc_contract_exit_1_row_and_gate_paragraph_name_the_baseline_half():
    document = contract_text()
    exit_rows = [row for row in gfm_table(document, "## Exit codes").rows
                 if row and row[0].strip("` ") == "1"]
    assert len(exit_rows) == 1
    assert ("with `--baseline`, 1 means a PRESENT gap that clears the floor is not "
            "PRESENT in the baseline") in exit_rows[0][1]
    start = document.index("\n## Exit codes\n")        # the heading line, not a mention
    section = document[start:document.index("\n## ", start + 1)]
    assert "scan --exit-code --baseline" in section.replace("\n", " ")
    assert "diff --exit-code" in section


# ===========================================================================
# Tester retry round (iteration 299) -- corners the first tester round left open.
# ===========================================================================

@pytest.fixture(scope="module")
def reg_a_only(bed):
    """A register holding ONLY record A: the baseline a consumer wrote before B existed."""
    reg = bed["root"] / "reg-a-only" / "gaps"
    reg.mkdir(parents=True)
    (reg / f"{GAP['A']}.json").write_text(json.dumps(REGISTER[0]), encoding="utf-8")
    return reg


def test_t2_a_record_added_since_the_baseline_makes_its_present_finding_new(bed, reg_a_only):
    """pm.md Out of Scope: `records_applied` mismatch is NOT a refusal -- "the register
    growing is the normal case; a new record's PRESENT finding is legitimately new"."""
    rc, out, err = _run(["scan", str(bed["trees"]["a_and_b"]), "--gaps", str(reg_a_only),
                         "--json"])
    assert (rc, err) == (0, ""), err
    payload = json.loads(out)
    assert [f["gap_id"] for f in payload["findings"]] == [GAP["A"]]
    path = bed["root"] / "baseline-register-a-only.json"
    path.write_text(out, encoding="utf-8")
    rc, out, err = _scan(bed, "a_and_b", "--exit-code", "--baseline", str(path))
    assert (rc, err) == (NEW, "")
    assert _baseline_line(out) == (f"Baseline: {path} -- carried PRESENT: 1; "
                                   f"new above-floor PRESENT: 1 ({GAP['B']})")
    # The same tree against the same baseline with the register that WROTE it: clean.
    rc, out, err = _run(["scan", str(bed["trees"]["a_and_b"]), "--gaps", str(reg_a_only),
                         "--exit-code", "--baseline", str(path)])
    assert (rc, err) == (CLEAN, "")


def test_t7_json_payload_identity_holds_with_floor_and_the_code_follows_behavior_4(bed):
    plain_rc, plain_out, plain_err = _scan(bed, "a_and_w", "--json", "--floor", "0")
    assert (plain_rc, plain_err) == (0, "")
    rc, out = _gate(bed, "a_and_w", "b_only_a", "--json", "--floor", "0")
    assert out == plain_out
    assert rc == NEW, "W (confidence 0) is new at --floor 0 even in the --json form"
    rc_default, out_default = _gate(bed, "a_and_w", "b_only_a", "--json")
    assert rc_default == CLEAN
    assert out_default == _scan(bed, "a_and_w", "--json")[1]


def test_t6_carried_count_is_the_baseline_present_count_not_the_current_one(bed):
    """K counts the BASELINE's PRESENT findings (2 at floor 6: A and W); the current tree
    `only_a` has one PRESENT, and M is 0 because A is carried."""
    rc, out = _gate(bed, "only_a", "b_a_and_w_floor6")
    assert rc == CLEAN
    assert _baseline_line(out) == (f"Baseline: {bed['b_a_and_w_floor6']} -- carried "
                                   "PRESENT: 2; new above-floor PRESENT: 0 (none)")


def test_t1_baseline_without_a_value_is_a_parser_refusal(bed):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            pytest.raises(SystemExit) as exc:
        main(["scan", str(bed["trees"]["only_a"]), "--gaps", str(bed["reg"]),
              "--exit-code", "--baseline"])
    assert exc.value.code == REFUSED
    assert out.getvalue() == ""
    assert "--baseline" in err.getvalue()


# ===========================================================================
# Tester round (iteration 300) -- behavior 13: the old `scan` cell is gone from the
# SUITE, not just the document. pm.md names two `rg -F` completeness proofs and asks for
# at least one test that reads the two re-pinned test modules and the contract as TEXT.
# The probes below are assembled from fragments (never spelled contiguously) so this
# module can never be the one line its own census finds; and every file is searched
# twice -- as written, and with adjacent string literals glued across a line break --
# because iteration 300's engineer found one pin split as `"... [--prd] "` newline
# `"[--exit-code]\`"`, which no single-line census can see.
# ===========================================================================

import re  # noqa: E402  (tester section; kept beside its only users)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The old `scan` cell ends `[--exit-code]` + backtick; the new one continues with
#: ` [--baseline BASELINE]`, so this tail is a probe for the OLD spelling only.
OLD_CELL_TAIL = "[--prd] [--exit-code]" + chr(96)

#: The old hand-spelled flag inventory row for `scan` (its first flag was `--exit-code`).
#: Assembled so that no quote-delimited window in THIS file reads as a strict prefix of a
#: live flag: iteration 296's b8 census treats such a window as a kept-alive abbreviation.
OLD_SCAN_ROW = '"scan": ["' + "-" + "-exit-code" + '"'

#: Where pm.md's two `rg` proofs look: `tests/ docs/ README.md src/ tools/`.
CENSUS_ROOTS = ("tests", "docs", "README.md", "src", "tools")

_GLUE = re.compile(r"""["']\s*\n\s*["']""")


def _census_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in CENSUS_ROOTS:
        path = REPO_ROOT / root
        if path.is_file():
            files.append(path)
            continue
        files.extend(p for p in sorted(path.rglob("*"))
                     if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix not in {".pyc", ".pyo"})
    assert len(files) > 50, "the census walked almost nothing"
    return files


def _texts() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in _census_files():
        try:
            out[str(path.relative_to(REPO_ROOT))] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return out


def test_b13_the_old_scan_cell_survives_nowhere_as_text():
    """pm.md's first `rg -n -F` proof (the old cell's tail, backtick included) over
    `tests/ docs/ README.md src/ tools/` -> nothing; the same census is repeated with
    adjacent string literals glued across a newline."""
    hits = sorted(name for name, text in _texts().items()
                  if OLD_CELL_TAIL in text or OLD_CELL_TAIL in _GLUE.sub("", text))
    assert hits == []


def test_b13_the_old_scan_flag_row_survives_nowhere_under_tests():
    """pm.md's second `rg -n -F` proof (the `scan` inventory row opening with the flag
    that used to sort first) over `tests/` -> nothing, glued form included."""
    hits = sorted(name for name, text in _texts()
                  .items() if name.startswith("tests/")
                  and (OLD_SCAN_ROW in text or OLD_SCAN_ROW in _GLUE.sub("", text)))
    assert hits == []


def _new_scan_cell() -> str:
    """The `scan` cell as PUBLISHED -- read from the contract through the committed oracle,
    never hand-spelled here, so this module adds no eighth pin of the same fact."""
    cells = [c for c in surface_table_cells(contract_text()) if "radar scan" in c]
    assert len(cells) == 1, cells
    (cell,) = cells
    assert cell.endswith("[--prd] [--exit-code] [--baseline BASELINE]" + chr(96)), cell
    return cell


def test_b13_the_contract_spells_the_new_scan_cell_exactly_once():
    cell = _new_scan_cell()
    assert contract_text().count(cell) == 1
    assert contract_text().count(OLD_CELL_TAIL) == 0


def test_b13_the_re_pinned_modules_spell_the_published_cell_and_the_seventeen_flags():
    """Reads `tests/test_iter88_behavior.py`, `tests/test_iter296_behavior.py` and
    `tests/test_surface_contract_unit.py` as text: every hand-spelled `scan` cell is the
    published one, the unit pin is contiguous exactly once, and the flag inventory row
    for `scan` opens with `--baseline` and sums to seventeen."""
    cell = _new_scan_cell()
    texts = _texts()
    iter88 = texts["tests/test_iter88_behavior.py"]
    # Cells: the EXPECTED_CELLS index-5 pin, the contiguous b3 literal, the b5 row's
    # `old` and the b7 plant's `old` -- four spellings, all of them the published cell.
    assert iter88.count(cell) == 4, iter88.count(cell)
    assert OLD_CELL_TAIL not in _GLUE.sub("", iter88)
    # Their `new` twins (the planted known-bad) keep the flag too, so the plant differs
    # from the document ONLY by `[<target>]`: the requiredness defect it exists to plant.
    planted = cell.replace("radar scan <target>", "radar scan [<target>]")
    assert iter88.count(planted) == 2, iter88.count(planted)
    unit = texts["tests/test_surface_contract_unit.py"]
    assert unit.count(cell) == 1 and OLD_CELL_TAIL not in _GLUE.sub("", unit)
    iter296 = texts["tests/test_iter296_behavior.py"]
    derived = {verb: sorted(o for o in s.options if o.startswith("--"))
               for verb, s in parser_surface().items()}
    scan_row = '"scan": ' + json.dumps(derived["scan"])
    assert derived["scan"][0] == "--baseline"
    assert sum(len(v) for v in derived.values()) == 17
    assert iter296.count(scan_row) == 1, scan_row
    assert "== 17" in iter296 and "== 16" not in iter296
    assert OLD_SCAN_ROW not in _GLUE.sub("", iter296)


def test_b13_the_two_re_pinned_modules_import_and_their_cell_pins_agree_with_the_document():
    """The pins are not only spelled, they are the ones the modules RUN: `EXPECTED_CELLS`
    of iteration 88 is exactly the published stable-surface table, cell for cell."""
    from test_iter88_behavior import EXPECTED_CELLS
    assert list(surface_table_cells(contract_text())) == EXPECTED_CELLS
    assert EXPECTED_CELLS[5] == _new_scan_cell()
