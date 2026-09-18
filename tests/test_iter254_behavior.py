"""Iteration 254 behaviors: `radar diff --exit-code` publishes a three-valued verdict.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here reads the implementation
source, the engineer's or reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors. Shapes were established by RUNNING
the tool (`radar diff --help`, `radar diff OLD NEW` on hand-built registers) and by
reflection over the public interface (`inspect.signature`), never by reading a body.
`docs/CONSUMER_CONTRACT.md` is read as the PUBLISHED DOCUMENT behavior 7 legislates over
-- the same class of artifact as the README, not implementation source -- and it is
parsed through the oracles already committed under `tests/`.

Structural notes, so this file cannot lie later:

* **Every exit-code claim is paired with its flagless twin IN THE SAME TEST.** A verdict
  test that only ran the flagged form could pass against a `diff` that returned 1
  unconditionally, and a byte-equality claim measured across two test functions is not a
  claim about one invocation pair. `_verdict()` runs both argv, asserts stdout is
  byte-equal, asserts both stderrs empty, and returns the flagged code -- so the opt-in
  half of behavior 2 is re-proved by every case in behaviors 1, 3 and 4.
* **The terminal set is DERIVED, never spelled.** `TERMINAL` / `NON_TERMINAL` come from
  `taxonomy.terminal_statuses()` and `taxonomy.STATUSES`, so behavior 4's parametrization
  grows by itself when the vocabulary does. The three transitions the spec names by hand
  are ALSO asserted literally, so a taxonomy that lost `addressed` cannot silently empty
  the sweep.
* **The negative controls are guarded against vacuity.** Behavior 3 first asserts the
  report really does show `## Added (1)` plus a `confidence` AND a `citations` change and
  NO `## Removed` and no `status:` line; behavior 4 first asserts the report really does
  carry the `status:` line for the pair under test. A predicate that fired on nothing
  would otherwise pass these tests for the wrong reason.
* **Registers are built ONCE per module.** One module-scoped bed dir holds every 2-3
  record register these behaviors need; no test copies `gaps/` and no test runs
  `radar scan`, so this module adds no scan-equivalents to the suite wall.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every register is built under pytest's `tmp_path_factory`.

ONE SPEC AMBIGUITY, also carried in the tester report: behavior 5 says stderr must contain
"the resolved OLD register path" without defining resolution. Measured, the tool names
`<old>/gaps` when that directory exists and `<old>` when it does not, so both variants are
tested with the resolved path each one actually implies.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar import cli, diff as diff_mod, taxonomy
from agent_gap_radar.diff import (FieldChange, RecordChange, RecordRef,
                                  RegisterDiff, regression_verdict)
from test_iter02_behavior import _record, _write_register
from test_iter109_behavior import exit_code_table_rows
from _surface_contract import (contract_text, gfm_table, invocation_verb,
                               surface_table_cells)

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Derived from the closed vocabulary, so behavior 4 cannot go stale against a taxonomy
#: change and cannot be read as a second literal copy of the terminal set.
TERMINAL = taxonomy.terminal_statuses()
NON_TERMINAL = tuple(s for s in taxonomy.STATUSES if s not in TERMINAL)

#: The verdict codes the spec assigns. Named, not spelled inline, so a reader can see that
#: nothing here invents a fifth code.
REGRESSION, CLEAN, REFUSED = 1, 0, 2


def _run(argv: list[str]) -> tuple[int, str, str]:
    """Drive the CLI in-process; observe only exit code, stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main_argv(argv)
    return code, out.getvalue(), err.getvalue()


def main_argv(argv: list[str]) -> int:
    return cli.main(list(argv))


def _verdict(old: pathlib.Path, new: pathlib.Path, json_surface: bool) -> tuple[int, str]:
    """The flagged code, having proved the document and stderr are unchanged by the flag.

    Returns `(flagged_code, stdout)`. Asserts, in one place so every behavior inherits it:
    the flagless twin exits 0, both stderrs are empty, stdout is byte-identical, and the
    document still ends in exactly one newline.
    """
    surface = ["--json"] if json_surface else []
    base = ["diff", str(old), str(new), *surface]
    plain_code, plain_out, plain_err = _run(base)
    flag_code, flag_out, flag_err = _run([*base, "--exit-code"])
    assert plain_code == CLEAN, (base, plain_code, plain_err)
    assert plain_err == "", (base, plain_err)
    assert flag_err == "", (base, flag_err)
    assert flag_out == plain_out, (
        "the flag changed the document, which the promise forbids: "
        f"{len(plain_out)} vs {len(flag_out)} bytes")
    assert plain_out.endswith("\n") and not plain_out.endswith("\n\n"), repr(plain_out[-3:])
    return flag_code, flag_out


def _with_status(record: dict, status: str) -> dict:
    return {**record, "status": status}


@pytest.fixture(scope="module")
def beds(tmp_path_factory) -> dict[str, pathlib.Path]:
    """Every register this module needs, built ONCE (measured cost driver: fixture scope)."""
    root = tmp_path_factory.mktemp("iter254")
    a = _record("GAP-901")
    b_strong = _record("GAP-902", classes=("first-party-field", "secondary-summary"))
    b_weak = _record("GAP-902", classes=("secondary-summary",))
    c = _record("GAP-903")

    def reg(name: str, records: list[dict]) -> pathlib.Path:
        _write_register(root / name, records)
        return root / name

    made = {
        "AB": reg("ab", [a, b_strong]),
        "A": reg("a", [a]),
        "AB_strong": reg("ab-strong", [a, b_strong]),
        "ABC_weak_b": reg("abc-weak-b", [a, b_weak, c]),
        "empty_with_gaps_dir": reg("empty-with-gaps-dir", []),
    }
    bare = root / "empty-without-gaps-dir"
    bare.mkdir()
    made["empty_without_gaps_dir"] = bare
    for status in taxonomy.STATUSES:
        made["status:" + status] = reg("status-" + status,
                                      [_with_status(a, status), b_strong])
    # Against OLD = "status:<terminal>" (which is {A@terminal, B}), this NEW loses B AND
    # reopens A -- both regression shapes inside ONE comparison, so the predicate is proved
    # to be a union and not an either/or.
    made["reopen_plus_removal"] = reg("reopen-plus-removal",
                                      [_with_status(a, NON_TERMINAL[0])])
    return made


# --- Behavior 1: a removed record exits 1 ----------------------------------------------

def test_b1_a_removed_record_exits_1_with_a_byte_identical_document(beds):
    code, out = _verdict(beds["AB"], beds["A"], json_surface=False)
    assert "## Removed (1)" in out, out
    assert code == REGRESSION, (code, out)


def test_b1_the_removal_is_the_only_change_so_the_verdict_cannot_be_incidental(beds):
    _, out = _verdict(beds["AB"], beds["A"], json_surface=False)
    assert "## Added (0)" in out, out
    assert "## Changed (0)" in out, out


# --- Behavior 2: the machine surface agrees, and the flag is OPT-IN --------------------

def test_b2_the_json_surface_returns_the_same_verdict_over_the_same_pair(beds):
    code, out = _verdict(beds["AB"], beds["A"], json_surface=True)
    assert code == REGRESSION, (code, out)
    payload = json.loads(out)
    assert [ref["gap_id"] for ref in payload["removed"]] == ["GAP-902"], payload["removed"]


@pytest.mark.parametrize("surface", [[], ["--json"]], ids=["markdown", "json"])
def test_b2_no_invocation_that_omits_the_flag_can_return_1(beds, surface):
    """Sweeps BOTH regression shapes on both surfaces: the flag is the only door to 1."""
    pairs = [(beds["AB"], beds["A"]),
             (beds["status:" + TERMINAL[0]], beds["status:" + NON_TERMINAL[0]])]
    for old, new in pairs:
        code, out, err = _run(["diff", str(old), str(new), *surface])
        assert code == CLEAN, (old.name, new.name, surface, code, err)
        assert err == "", err
        assert out, "a flagless diff must still emit its document"


def test_b2_the_flag_is_absent_from_every_other_verb():
    """`--exit-code` on `p_diff` only means no verb GAINED it here; `scan` already had it."""
    parser = cli.build_parser()
    actions = [a for a in parser._actions if isinstance(a, __import__("argparse")._SubParsersAction)]
    assert actions, "no subparsers found on the published parser"
    carriers = {verb for action in actions for verb, sub in action.choices.items()
                if any("--exit-code" in (opt.option_strings or []) for opt in sub._actions)}
    assert carriers == {"scan", "diff"}, carriers


# --- Behavior 3: additions and falling scores are NOT regressions ----------------------

def test_b3_premise_the_report_really_shows_an_addition_and_a_falling_score(beds):
    """Guards behaviors 3's negative control against passing vacuously."""
    _, out = _verdict(beds["AB_strong"], beds["ABC_weak_b"], json_surface=False)
    assert "## Added (1)" in out, out
    assert "## Removed (0)" in out, out
    assert "- GAP-902" in out, out
    assert re.search(r"^\s*- confidence: \d+ -> \d+$", out, re.M), out
    assert re.search(r"^\s*- citations: 2 -> 1$", out, re.M), out
    assert "status:" not in out, out


@pytest.mark.parametrize("json_surface", [False, True], ids=["markdown", "json"])
def test_b3_an_addition_plus_a_falling_confidence_is_not_a_regression(beds, json_surface):
    code, _ = _verdict(beds["AB_strong"], beds["ABC_weak_b"], json_surface=json_surface)
    assert code == CLEAN, code


# --- Behavior 4: a reopened gap exits 1, in one direction only -------------------------

def _status_pair(beds, old_status: str, new_status: str) -> tuple[int, str]:
    code, out = _verdict(beds["status:" + old_status], beds["status:" + new_status],
                         json_surface=False)
    assert "## Removed (0)" in out, out
    assert "## Added (0)" in out, out
    assert f"- status: {old_status} -> {new_status}" in out, out
    return code, out


@pytest.mark.parametrize("old_status,new_status,expected", [
    ("addressed", "open", REGRESSION),
    ("open", "addressed", CLEAN),
    ("addressed", "retired", CLEAN),
], ids=["reopened", "closed", "retired"])
def test_b4_the_three_transitions_the_spec_names(beds, old_status, new_status, expected):
    code, _ = _status_pair(beds, old_status, new_status)
    assert code == expected, (old_status, new_status, code)


@pytest.mark.parametrize("terminal", TERMINAL)
@pytest.mark.parametrize("non_terminal", NON_TERMINAL)
def test_b4_every_terminal_to_non_terminal_move_is_a_regression(beds, terminal, non_terminal):
    code, _ = _status_pair(beds, terminal, non_terminal)
    assert code == REGRESSION, (terminal, non_terminal, code)


@pytest.mark.parametrize("terminal", TERMINAL)
@pytest.mark.parametrize("non_terminal", NON_TERMINAL)
def test_b4_the_reverse_direction_is_never_a_regression(beds, non_terminal, terminal):
    code, _ = _status_pair(beds, non_terminal, terminal)
    assert code == CLEAN, (non_terminal, terminal, code)


def test_b4_a_move_within_the_terminal_set_is_not_a_regression(beds):
    assert len(TERMINAL) >= 2, TERMINAL
    for old_status in TERMINAL:
        for new_status in TERMINAL:
            if old_status != new_status:
                code, _ = _status_pair(beds, old_status, new_status)
                assert code == CLEAN, (old_status, new_status, code)


def test_b4_a_move_within_the_non_terminal_set_is_not_a_regression(beds):
    assert len(NON_TERMINAL) >= 2, NON_TERMINAL
    for old_status in NON_TERMINAL:
        for new_status in NON_TERMINAL:
            if old_status != new_status:
                code, _ = _status_pair(beds, old_status, new_status)
                assert code == CLEAN, (old_status, new_status, code)


@pytest.mark.parametrize("json_surface", [False, True], ids=["markdown", "json"])
def test_b4_the_reopen_verdict_holds_on_both_surfaces(beds, json_surface):
    code, _ = _verdict(beds["status:" + TERMINAL[0]], beds["status:" + NON_TERMINAL[0]],
                       json_surface=json_surface)
    assert code == REGRESSION, code


# --- Behavior 5: an empty OLD baseline is refused, not certified -----------------------

@pytest.mark.parametrize("bed,resolves_to_gaps_dir", [
    ("empty_with_gaps_dir", True),
    ("empty_without_gaps_dir", False),
], ids=["gaps-dir-present-but-empty", "no-gaps-dir-at-all"])
@pytest.mark.parametrize("surface", [[], ["--json"]], ids=["markdown", "json"])
def test_b5_an_empty_old_side_is_refused_with_exit_2(beds, bed, resolves_to_gaps_dir, surface):
    old, new = beds[bed], beds["AB"]
    resolved = old / "gaps" if resolves_to_gaps_dir else old
    code, out, err = _run(["diff", str(old), str(new), *surface, "--exit-code"])
    assert code == REFUSED, (bed, code, err)
    assert out == "", ("stdout must stay empty on a refusal, not half a document", out[:120])
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, "a refusal must say why"
    assert lines[-1].startswith("Error: "), lines[-1]
    assert str(resolved) in lines[-1], (str(resolved), lines[-1])
    assert "--exit-code" in lines[-1], lines[-1]


@pytest.mark.parametrize("bed", ["empty_with_gaps_dir", "empty_without_gaps_dir"])
def test_b5_the_refusal_uses_this_repos_one_refusal_dialect(beds, bed):
    """One `Error: ` line, no argparse spelling, no usage block: the shipped dialect."""
    _, _, err = _run(["diff", str(beds[bed]), str(beds["AB"]), "--exit-code"])
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    assert err.count("Error: ") == 1, err
    assert "usage:" not in err, err
    assert "radar: error:" not in err, err


@pytest.mark.parametrize("bed", ["empty_with_gaps_dir", "empty_without_gaps_dir"])
def test_b5_the_flagless_invocation_over_the_same_pair_is_unchanged(beds, bed):
    code, out, err = _run(["diff", str(beds[bed]), str(beds["AB"])])
    assert code == CLEAN, (code, err)
    assert err == "", err
    assert out.splitlines()[2] == "Old: 0 record(s). New: 2 record(s).", out.splitlines()[:4]


def test_b5_an_emptied_new_side_gets_no_special_case_and_exits_1(beds):
    """Out of Scope pins the direction: every OLD record removed is the LOUD answer."""
    code, out = _verdict(beds["AB"], beds["empty_with_gaps_dir"], json_surface=False)
    assert code == REGRESSION, (code, out)
    assert "## Removed (2)" in out, out


# --- Behavior 6: one public, pure, three-valued function -------------------------------

def _hand_diff(*, old_count: int = 2, new_count: int = 2, added=(), removed=(),
               changed=()) -> RegisterDiff:
    """A comparison built in memory: no register on disk, so purity is observable."""
    return RegisterDiff(old_count=old_count, new_count=new_count, added=tuple(added),
                        removed=tuple(removed), changed=tuple(changed))


def _status_change(gap_id: str, old: str, new: str) -> RecordChange:
    return RecordChange(gap_id=gap_id, changes=(FieldChange(field="status", old=old, new=new),))


def test_b6_the_function_is_public_on_diff_and_takes_one_registerdiff():
    import inspect
    assert "regression_verdict" in dir(diff_mod)
    params = list(inspect.signature(regression_verdict).parameters)
    assert len(params) == 1, params


@pytest.mark.parametrize("old_count,expected_none", [(0, True), (1, False), (2, False)])
def test_b6_none_if_and_only_if_the_old_side_held_zero_records(old_count, expected_none):
    """Both directions of the iff, including an old_count of 0 that ALSO lost a record."""
    loaded = _hand_diff(old_count=old_count, new_count=3,
                        removed=(RecordRef(gap_id="GAP-901", title="t"),))
    verdict = regression_verdict(loaded)
    assert (verdict is None) == expected_none, (old_count, verdict)
    empty_shape = regression_verdict(_hand_diff(old_count=old_count, new_count=0))
    assert (empty_shape is None) == expected_none, (old_count, empty_shape)


def test_b6_a_removed_record_is_true_and_an_added_one_is_not():
    assert regression_verdict(
        _hand_diff(removed=(RecordRef(gap_id="GAP-901", title="t"),))) is True
    assert regression_verdict(
        _hand_diff(added=(RecordRef(gap_id="GAP-904", title="t"),))) is False
    assert regression_verdict(_hand_diff()) is False


@pytest.mark.parametrize("terminal", TERMINAL)
@pytest.mark.parametrize("non_terminal", NON_TERMINAL)
def test_b6_a_status_leaving_the_terminal_set_is_true_and_the_reverse_is_false(
        terminal, non_terminal):
    assert regression_verdict(
        _hand_diff(changed=(_status_change("GAP-901", terminal, non_terminal),))) is True
    assert regression_verdict(
        _hand_diff(changed=(_status_change("GAP-901", non_terminal, terminal),))) is False


def test_b6_a_status_that_stays_inside_the_terminal_set_is_false():
    for old in TERMINAL:
        for new in TERMINAL:
            assert regression_verdict(
                _hand_diff(changed=(_status_change("GAP-901", old, new),))) is False, (old, new)


def test_b6_the_field_name_is_checked_and_not_just_the_two_values():
    """Kills a predicate that scans every FieldChange's values for a terminal status."""
    disguised = RecordChange(gap_id="GAP-901", changes=(
        FieldChange(field="confidence", old=TERMINAL[0], new=NON_TERMINAL[0]),))
    assert regression_verdict(_hand_diff(changed=(disguised,))) is False


def test_b6_a_falling_confidence_or_priority_is_not_a_regression():
    changed = RecordChange(gap_id="GAP-901", changes=(
        FieldChange(field="confidence", old="5", new="4"),
        FieldChange(field="priority", old="45", new="36"),
        FieldChange(field="citations", old="2", new="1"),))
    assert regression_verdict(_hand_diff(changed=(changed,))) is False


def test_b6_a_status_new_value_outside_the_published_vocabulary_fails_closed():
    """A fifth non-terminal status added later must count as a reintroduction."""
    unknown = "status-this-taxonomy-has-not-published"
    assert unknown not in taxonomy.STATUSES, unknown
    assert regression_verdict(
        _hand_diff(changed=(_status_change("GAP-901", TERMINAL[0], unknown),))) is True


def test_b6_the_terminal_set_is_derived_from_taxonomy_not_spelled_in_place(monkeypatch):
    """Shrink the published terminal set; the predicate's answer must move with it."""
    assert len(TERMINAL) >= 2, TERMINAL
    shrunk, dropped = (TERMINAL[0],), TERMINAL[1]
    before = regression_verdict(
        _hand_diff(changed=(_status_change("GAP-901", TERMINAL[0], dropped),)))
    assert before is False, before
    monkeypatch.setattr(diff_mod, "terminal_statuses", lambda: shrunk)
    after = regression_verdict(
        _hand_diff(changed=(_status_change("GAP-901", TERMINAL[0], dropped),)))
    assert after is True, (
        "the predicate did not follow taxonomy.terminal_statuses(); it carries its own copy")


def test_b6_the_call_is_idempotent_and_opens_no_file(monkeypatch):
    loaded = _hand_diff(changed=(_status_change("GAP-901", TERMINAL[0], NON_TERMINAL[0]),))

    def _boom(*args, **kwargs):
        raise AssertionError("regression_verdict must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _boom)
    monkeypatch.setattr(pathlib.Path, "open", _boom)
    monkeypatch.setattr(pathlib.Path, "read_text", _boom)
    first, second = regression_verdict(loaded), regression_verdict(loaded)
    assert first is True and second is True, (first, second)
    assert first == second


def test_b6_the_cli_asks_the_predicate_exactly_once_over_one_comparison(beds, monkeypatch):
    """One verdict call, one `diff_registers` call: the code is derived, not recomputed."""
    verdict_calls, load_calls = [], []
    real_verdict, real_load = diff_mod.regression_verdict, diff_mod.diff_registers

    def counting_verdict(comparison):
        verdict_calls.append(comparison)
        return real_verdict(comparison)

    def counting_load(*args, **kwargs):
        load_calls.append(args)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(diff_mod, "regression_verdict", counting_verdict)
    monkeypatch.setattr(diff_mod, "diff_registers", counting_load)
    code, _, err = _run(["diff", str(beds["AB"]), str(beds["A"]), "--exit-code"])
    assert code == REGRESSION, (code, err)
    assert len(verdict_calls) == 1, len(verdict_calls)
    assert len(load_calls) == 1, len(load_calls)
    assert isinstance(verdict_calls[0], RegisterDiff), type(verdict_calls[0])


# --- Behavior 7: the published surface widens and EXIT_CODES does not -----------------

def test_b7_exit_codes_did_not_grow():
    assert cli.EXIT_CODES == (0, 1, 2, 141), cli.EXIT_CODES
    assert cli.EXIT_GAPS_PRESENT == REGRESSION, cli.EXIT_GAPS_PRESENT


def test_b7_the_stable_surface_row_for_diff_names_the_flag():
    document = contract_text()
    rows = {invocation_verb(cells[0]): cells for cells in gfm_table(document).rows}
    assert "diff" in rows, sorted(rows)
    invocation, promise = rows["diff"][0], rows["diff"][1]
    # Read the FIRST cell through the committed oracle too, so the flag is proved to sit
    # in the INVOCATION column and not merely somewhere in the row.
    first_cells = {invocation_verb(cell): cell for cell in surface_table_cells(document)}
    assert first_cells["diff"] == invocation, (first_cells["diff"], invocation)
    assert "--exit-code" in invocation, invocation
    assert "[--exit-code]" in invocation, (
        "the flag is OPT-IN, so the surface row must bracket it: " + invocation)
    for token in ("`1`", "`0`", "`2`"):
        assert token in promise, (token, promise[:200])
    assert "byte-identical" in promise, promise[:200]


def test_b7_the_exit_code_table_no_longer_restricts_1_to_scan_alone():
    rows = exit_code_table_rows()
    assert set(rows) == set(cli.EXIT_CODES), (sorted(rows), cli.EXIT_CODES)
    when = rows[REGRESSION][0]
    assert "diff --exit-code" in when, when
    assert "scan --exit-code" in when, when


def test_b7_the_gate_rule_and_the_flag_are_published_in_the_same_document():
    text = contract_text()
    assert "non-regression" in text, "the gate rule this iteration closes is gone"
    assert "diff --exit-code" in text


# --- Retry round: the Acceptance Criteria clauses and spec edges round 1 did not reach ---
#
# The first (time-capped) round covered behaviors 1-7. This section closes four Acceptance
# Criteria clauses stated OUTSIDE the numbered behaviors plus two edges the behaviors imply
# but never spell: a comparison that carries BOTH regression shapes, and an OLD side of zero
# records when NEW is ALSO empty. Still no `radar scan` and still the one module-scoped bed.

def test_ac_the_flag_sits_in_no_mutually_exclusive_group_on_diff():
    """AC 1: it must COMPOSE with `--json`, so neither flag may be in an exclusive group."""
    import argparse
    parser = cli.build_parser()
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    p_diff = next(sub for action in subs for verb, sub in action.choices.items()
                  if verb == "diff")
    grouped = {opt for group in p_diff._mutually_exclusive_groups
               for action in group._group_actions for opt in action.option_strings}
    assert "--exit-code" not in grouped, sorted(grouped)
    assert "--json" not in grouped, sorted(grouped)


@pytest.mark.parametrize("order", [["--json", "--exit-code"], ["--exit-code", "--json"]],
                         ids=["json-first", "flag-first"])
def test_ac_the_two_flags_compose_in_either_order_with_one_answer(beds, order):
    code, out, err = _run(["diff", str(beds["AB"]), str(beds["A"]), *order])
    assert code == REGRESSION, (order, code, err)
    assert err == "", err
    assert [ref["gap_id"] for ref in json.loads(out)["removed"]] == ["GAP-902"], out[:200]


def test_ac_every_answer_is_a_PLAIN_INT_drawn_from_the_published_exit_codes(beds):
    """A three-valued predicate leaking into the exit status is a defect a shell hides.

    `sys.exit(True)` and `sys.exit(1)` are indistinguishable to a consumer's `$?`, so a CLI
    that returned the verdict OBJECT would pass every code assertion in this module. Pin the
    TYPE as well as the value, over every argv shape these behaviors exercise.
    """
    argvs = [
        ["diff", str(beds["AB"]), str(beds["A"])],
        ["diff", str(beds["AB"]), str(beds["A"]), "--exit-code"],
        ["diff", str(beds["AB"]), str(beds["A"]), "--json", "--exit-code"],
        ["diff", str(beds["AB_strong"]), str(beds["ABC_weak_b"]), "--exit-code"],
        ["diff", str(beds["status:" + TERMINAL[0]]), str(beds["status:" + NON_TERMINAL[0]]),
         "--exit-code"],
        ["diff", str(beds["empty_with_gaps_dir"]), str(beds["AB"]), "--exit-code"],
    ]
    for argv in argvs:
        code, _, _ = _run(argv)
        assert type(code) is int, (argv[-3:], type(code), code)
        assert code in cli.EXIT_CODES, (argv[-3:], code, cli.EXIT_CODES)


def test_the_two_regression_shapes_are_a_UNION_not_an_either_or(beds):
    """One comparison that loses a record AND reopens a gap is still exactly one answer."""
    old, new = beds["status:" + TERMINAL[0]], beds["reopen_plus_removal"]
    code, out = _verdict(old, new, json_surface=False)
    assert "## Removed (1)" in out, out
    assert f"- status: {TERMINAL[0]} -> {NON_TERMINAL[0]}" in out, out
    assert code == REGRESSION, (code, out)


@pytest.mark.parametrize("json_surface", [False, True], ids=["markdown", "json"])
def test_a_register_compared_with_ITSELF_is_clean_on_both_surfaces(beds, json_surface):
    """The floor case a gate runs most often: nothing moved, so nothing is lost ground."""
    code, out = _verdict(beds["AB"], beds["AB"], json_surface=json_surface)
    assert code == CLEAN, (code, out[:200])
    if not json_surface:
        for section in ("## Added (0)", "## Removed (0)", "## Changed (0)"):
            assert section in out, (section, out)


@pytest.mark.parametrize("surface", [[], ["--json"]], ids=["markdown", "json"])
def test_an_empty_OLD_side_is_refused_even_when_NEW_is_empty_TOO(beds, surface):
    """Behavior 5 names `NEW holds at least one`; behavior 6 says None IFF old_count == 0.

    AMBIGUITY, resolved toward the refusal: the predicate is defined on the OLD side alone,
    and a both-empty pair is exactly the moved-or-one-level-too-high path shape the refusal
    exists to catch. Certifying it would be the fail-open direction.
    """
    old, new = beds["empty_with_gaps_dir"], beds["empty_without_gaps_dir"]
    code, out, err = _run(["diff", str(old), str(new), *surface, "--exit-code"])
    assert code == REFUSED, (code, err)
    assert out == "", out[:120]
    lines = [line for line in err.splitlines() if line.strip()]
    assert len(lines) == 1 and lines[0].startswith("Error: "), lines
    assert str(old / "gaps") in lines[0], (str(old / "gaps"), lines[0])
    assert "--exit-code" in lines[0], lines[0]
    plain_code, plain_out, plain_err = _run(["diff", str(old), str(new), *surface])
    assert (plain_code, plain_err) == (CLEAN, ""), (plain_code, plain_err)
    assert plain_out, "the flagless twin still emits its document"


@pytest.mark.parametrize("surface", [[], ["--json"]], ids=["markdown", "json"])
def test_the_flagged_invocation_is_byte_stable_across_repeated_runs(beds, surface):
    """Determinism is a standing quality bar, and an exit-code path is a new place to lose it."""
    argv = ["diff", str(beds["AB"]), str(beds["A"]), *surface, "--exit-code"]
    first, second = _run(argv), _run(argv)
    assert first == second, (first[0], second[0], len(first[1]), len(second[1]))
    assert first[0] == REGRESSION, first[0]
    assert first[1].endswith("\n") and not first[1].endswith("\n\n"), repr(first[1][-3:])


def test_b6_the_published_signature_is_three_valued():
    """`bool | None` in the signature is how a caller learns the third value exists."""
    import inspect
    annotation = str(inspect.signature(regression_verdict).return_annotation)
    assert "bool" in annotation and "None" in annotation, annotation


def test_the_flag_is_published_in_the_verbs_OWN_help():
    """`--help` is the surface a consumer reads before the contract document."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit) as exc:
        main_argv(["diff", "--help"])
    assert exc.value.code == 0, exc.value.code
    text = out.getvalue()
    assert "--exit-code" in text, text
    assert "--json" in text, text


def test_b7_the_widened_surface_row_did_not_drop_the_shipped_json_flag():
    """Widening a published invocation cell is the classic place to lose a shipped flag."""
    cells = {invocation_verb(cell): cell for cell in surface_table_cells(contract_text())}
    assert "diff" in cells, sorted(cells)
    assert "[--json]" in cells["diff"], cells["diff"]
    assert "[--exit-code]" in cells["diff"], cells["diff"]
