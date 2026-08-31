"""Iteration 87 behaviors: `render` publishes the JSON document tail, so the four
`--json`-shaped emitters reach ONE implementation instead of carrying four copies of
`json.dumps(payload, indent=2, sort_keys=False) + "\n"`, and a census can see a fifth
copy arrive.

Black-box, and the ISOLATION CONTRACT IS HONORED: no implementation module under `src/`
or `tools/` was read to derive any expectation here, and neither the engineer's notes,
the reviewer's notes, `IMPLEMENTATION.patch` nor any diff was opened. Every expectation
comes from `pm.md`'s Expected Behaviors. Every behavioral claim is measured by CALLING
the public interface (`agent_gap_radar.cli.main`, `agent_gap_radar.render.json_document`)
or by reading a PUBLISHED document, exactly the latitude `tests/test_iter14_behavior.py`
and `tests/test_iter86_behavior.py` take.

Structural notes, so this file cannot lie later:

* **Behaviors 3 and 4 are a SOURCE CENSUS, which the spec asks for by name.** The census
  reads `src/agent_gap_radar/**/*.py` as DATA through `ast`, and no expectation in this
  file was copied out of what it found: the counts (`1` call, in `render.py`; `2` modules
  importing `json`) are the spec's acceptance criteria, written before the walk ran. The
  census must be AST-based rather than textual because the helper's own docstring names
  `json.dumps` in prose and a text census would count that sentence.
* **The census closes the obvious evasion.** A bare `dumps(...)` call is counted too, so
  `from json import dumps` cannot hide a fifth copy from the call census -- and such a
  module would ALSO raise the import census past two, so the two rules are tight in
  opposite directions.
* **Behavior 2 proves the tail by RE-SERIALISING, not by grepping.** For each of the four
  surfaces, stdout is required to be byte-EQUAL to `render.json_document(json.loads(stdout))`.
  That is a single assertion that pins indent width, key ORDER, ASCII escaping and the
  single trailing newline on that surface simultaneously, and it goes red if any one
  emitter keeps its own copy of the tail and that copy drifts.
* **Anti-vacuity.** Every surface asserts its payload is non-trivial before any claim is
  made about its bytes, and the planted-tree census is required to COUNT UP when a second
  copy is planted -- an assertion that a count is `1` proves nothing unless a planted
  duplicate is shown to make it `2`.
* **No absolute path is spelled as a literal.** Every path is derived from `tmp_path` or
  from `REPO_ROOT`, so this module carries no machine path (an acceptance criterion of the
  quality bar in its own right).
* **Behavior 5's honest limit is stated, not hidden.** A black-box test cannot compare
  today's bytes against the pre-change bytes -- that before/after harness belongs to the
  reviewer and the final gate. What is asserted here instead: the verb/flag surface, the
  four published key SEQUENCES cross-checked against the pins committed by earlier
  iterations, the error path's exit code and `Error: ` prefix, determinism across two runs
  of the two markdown surfaces, and that importing `render` still pulls no new third-party
  and no network-capable module.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar import render
from agent_gap_radar.cli import main
from test_iter02_behavior import MARKER, _record, _target, _write_register
from test_iter13_behavior import TOP_KEYS as ITER13_SCAN_TOP_KEYS
from test_iter23_behavior import PRE_EXISTING_TOP_KEYS as ITER23_PRD_TOP_KEYS
from test_iter77_behavior import TOP_LEVEL_KEYS as ITER77_DIFF_TOP_KEYS

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"

#: Behavior 5 -- the eight verbs, in the order the usage line publishes them.
VERBS = ["validate", "list", "report", "show", "prd", "scan", "diff", "taxonomy"]

#: Behavior 5 -- the four published top-level key SEQUENCES, spelled here independently
#: and cross-checked below against the constants earlier iterations committed.
LIST_TOP_KEYS = ["confidence_floor", "counts", "records"]
PRD_TOP_KEYS = ["project", "branchName", "description", "sourceGap", "stories"]
SCAN_TOP_KEYS = ["target", "target_name", "confidence_floor", "records_applied",
                 "counts", "uncheckable", "findings"]
DIFF_TOP_KEYS = ["counts", "added", "removed", "changed"]

#: Two checked records that both fire on the `_target` tree, so every scan below has
#: findings and every listing has records.
RECORDS = [_record("GAP-870", 5, 3, 5, ("first-party-field",), "CHK-870"),
           _record("GAP-871", 4, 3, 3, ("first-party-field",), "CHK-871")]

#: A deliberately UNSORTED, nested payload. `"b"` before `"a"` at two depths, so a
#: sorting implementation cannot pass behavior 1, and mixed value kinds so the round
#: trip is not a string-only proof.
NESTED = {"b": {"d": [1, {"f": 2, "e": 3}], "c": True},
          "a": [None, "x", 1.5],
          "0": {}}


# ---------------------------------------------------------------------------
# Fixtures. `MARKER`, `_record`, `_target` and `_write_register` come from
# tests/test_iter02_behavior.py, as in every module since iteration 02.
# ---------------------------------------------------------------------------

@pytest.fixture()
def reg(tmp_path):
    return _write_register(tmp_path / "reg", list(RECORDS))


@pytest.fixture()
def target(tmp_path):
    return _target(tmp_path / "hit", body=MARKER)


@pytest.fixture()
def diff_pair(tmp_path):
    """Two register states that differ in every reported way: added, removed, changed."""
    old = _write_register(tmp_path / "old", [_record("GAP-870", 5, 3, 5),
                                             _record("GAP-872", 2, 2, 2)])
    new = _write_register(tmp_path / "new", [_record("GAP-870", 4, 3, 5),
                                             _record("GAP-873", 3, 3, 3)])
    return old, new


def _emit(capsys, argv):
    """stdout for a JSON-emitting invocation: exit 0, empty stderr, non-empty document."""
    rc = main(list(argv))
    cap = capsys.readouterr()
    assert rc == 0, f"{argv} exited {rc}; stderr={cap.err!r}"
    assert cap.err == "", f"{argv} wrote to stderr: {cap.err!r}"
    assert cap.out, f"{argv} produced an empty document"
    return cap.out


# ---------------------------------------------------------------------------
# behavior 1 -- the published helper
# ---------------------------------------------------------------------------

def test_b1_json_document_is_a_str_with_exactly_one_trailing_newline():
    out = render.json_document(NESTED)
    assert isinstance(out, str), type(out).__name__
    assert out.endswith("\n"), repr(out[-4:])
    assert not out.endswith("\n\n"), repr(out[-4:])
    assert out.splitlines()[-1].strip() != "", "document ends on a blank line"


def test_b1_json_document_round_trips_to_the_object_it_was_given():
    assert json.loads(render.json_document(NESTED)) == NESTED


def test_b1_json_document_is_indented_two_spaces_per_level():
    out = render.json_document({"l1": {"l2": {"l3": 1}}})
    lines = out.split("\n")
    for key, depth in (("l1", 1), ("l2", 2), ("l3", 3)):
        line = next(l for l in lines if f'"{key}"' in l)
        want = " " * (2 * depth)
        assert line.startswith(want + f'"{key}"'), (
            f'"{key}" sits at depth {depth} and must carry {2 * depth} spaces of indent, '
            f"got {line!r}")


def test_b1_json_document_is_the_two_space_indented_spelling_of_the_payload():
    """The whole tail in one assertion, spelled from the spec's prose (two-space indent,
    insertion order, one trailing newline) through the stdlib rather than through the
    implementation."""
    obj = {"a": {"b": [1]}}
    assert render.json_document(obj) == '{\n  "a": {\n    "b": [\n      1\n    ]\n  }\n}\n'


def test_b1_json_document_preserves_insertion_order():
    out = render.json_document({"b": 1, "a": 2})
    assert out.index('"b"') < out.index('"a"'), out
    assert list(json.loads(out)) == ["b", "a"], list(json.loads(out))


def test_b1_insertion_order_claim_is_not_vacuous():
    """A sorting implementation must FAIL behavior 1: the sorted spelling of the same
    object is a different string, and the helper must not emit it."""
    obj = {"b": 1, "a": 2}
    sorted_spelling = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    assert sorted_spelling.index('"a"') < sorted_spelling.index('"b"'), (
        "premise: the sorted spelling must order these keys the other way")
    assert render.json_document(obj) != sorted_spelling


def test_b1_nested_insertion_order_is_preserved_too():
    out = render.json_document(NESTED)
    payload = json.loads(out)
    assert list(payload) == list(NESTED)
    assert list(payload["b"]) == list(NESTED["b"])
    assert list(payload["b"]["d"][1]) == list(NESTED["b"]["d"][1])


def test_b1_docstring_states_that_keys_are_never_sorted():
    doc = render.json_document.__doc__ or ""
    assert doc.strip(), "`json_document` has no docstring"
    low = " ".join(doc.lower().split())
    assert "never" in low and "sort" in low, (
        "the docstring must state that keys are NEVER SORTED -- it is the only place the "
        f"insertion-order guarantee is written down: {low!r}")


def test_b1_json_document_is_public_and_callable():
    assert callable(getattr(render, "json_document", None)), (
        "`render.json_document` is not a public callable")
    assert getattr(render, "_json_document", None) is None, (
        "a private `_json_document` alias survived; the criterion is a PUBLISHED helper")


# ---------------------------------------------------------------------------
# behavior 2 -- byte-stability of the four emitted documents
# ---------------------------------------------------------------------------

def _assert_tail_is_the_published_one(out, label):
    payload = json.loads(out)
    assert isinstance(payload, dict) and payload, f"{label}: trivial payload {payload!r}"
    assert len(out) > 80, f"{label}: document too small to be a real proof: {out!r}"
    assert render.json_document(payload) == out, (
        f"{label}: stdout is NOT the published tail's spelling of its own payload -- this "
        "emitter still carries its own copy of the indent/key-order/newline rule")


def test_b2_list_json_is_the_published_tail(capsys, reg):
    out = _emit(capsys, ["list", str(reg), "--json"])
    _assert_tail_is_the_published_one(out, "radar list --json")
    assert json.loads(out)["records"], "premise: the listing must carry records"


def test_b2_prd_is_the_published_tail(capsys, reg):
    out = _emit(capsys, ["prd", str(reg)])
    _assert_tail_is_the_published_one(out, "radar prd")
    assert json.loads(out)["stories"], "premise: the prd must carry stories"


def test_b2_scan_json_is_the_published_tail(capsys, reg, target):
    out = _emit(capsys, ["scan", str(target), "--gaps", str(reg), "--json"])
    _assert_tail_is_the_published_one(out, "radar scan --json")
    assert json.loads(out)["findings"], "premise: the scan must carry findings"


def test_b2_diff_json_is_the_published_tail(capsys, diff_pair):
    old, new = diff_pair
    out = _emit(capsys, ["diff", str(old), str(new), "--json"])
    _assert_tail_is_the_published_one(out, "radar diff --json")
    payload = json.loads(out)
    assert payload["added"] and payload["removed"] and payload["changed"], (
        "premise: this pair must differ in all three ways")


def test_b2_scan_prd_is_the_published_tail_too(capsys, reg, target):
    """The FIFTH JSON-emitting surface, which the spec's list of four does not name.

    `pm.md` enumerates `radar list --json`, `radar prd`, `radar scan --json` and
    `radar diff --json`, and argues the ratchet as "one copy per `--json` verb". But
    `radar scan --prd` emits a prd document INSTEAD of the report, so it is a JSON surface
    reached by a FLAG rather than by a verb, and it is absent from that count. Measured
    here rather than assumed: every JSON-emitting surface the CLI publishes must carry the
    one published tail, not just the four the spec happened to list. Logged as PM feedback.
    """
    out = _emit(capsys, ["scan", str(target), "--gaps", str(reg), "--prd"])
    _assert_tail_is_the_published_one(out, "radar scan --prd")
    payload = json.loads(out)
    assert payload["stories"], "premise: the emitted prd must carry stories"
    assert list(payload) == PRD_TOP_KEYS, (
        f"`scan --prd` must publish the prd key sequence, got {list(payload)}")


def test_b2_prd_with_its_flags_is_the_published_tail(capsys, reg):
    """`prd` is the one site whose serialised EXPRESSION differed from the other three --
    `pm.md` measured it passing `prd_for(gap, project)` where the others pass `payload` --
    so its FLAGGED form is driven too and not only its default form."""
    out = _emit(capsys, ["prd", str(reg), "--gap", "GAP-870", "--project", "acme-widgets"])
    _assert_tail_is_the_published_one(out, "radar prd --gap --project")
    payload = json.loads(out)
    assert payload["project"] == "acme-widgets", payload["project"]
    assert payload["sourceGap"]["id"] == "GAP-870", payload["sourceGap"]
    assert payload["stories"], "premise: the flagged prd must carry stories"


def test_b2_holds_on_the_committed_register_too(capsys):
    """The real payload, not a fixture: 120-odd records exercise ASCII escaping and
    every value kind the register actually contains."""
    out = _emit(capsys, ["list", str(REPO_ROOT), "--json"])
    _assert_tail_is_the_published_one(out, "radar list --json (committed register)")
    assert len(json.loads(out)["records"]) >= 10, "premise: a real register was read"


@pytest.mark.parametrize("emitter", ["list", "prd", "scan", "scan-prd", "diff"])
def test_b2_two_runs_of_each_emitter_are_byte_identical(capsys, tmp_path, emitter):
    reg = _write_register(tmp_path / "det", list(RECORDS))
    tgt = _target(tmp_path / "dethit", body=MARKER)
    old = _write_register(tmp_path / "detold", [_record("GAP-870", 5, 3, 5)])
    argv = {"list": ["list", str(reg), "--json"],
            "prd": ["prd", str(reg)],
            "scan": ["scan", str(tgt), "--gaps", str(reg), "--json"],
            "scan-prd": ["scan", str(tgt), "--gaps", str(reg), "--prd"],
            "diff": ["diff", str(old), str(reg), "--json"]}[emitter]
    first = _emit(capsys, argv)
    second = _emit(capsys, argv)
    assert first == second, f"{emitter} is not byte-deterministic across two runs"


# ---------------------------------------------------------------------------
# behaviors 3 and 4 -- ONE implementation, and a census that can see a second
#
# AST, not text: the helper's own docstring names `json.dumps` in prose, and a textual
# census would count that sentence and read as broken against correct code.
# ---------------------------------------------------------------------------

def _modules_in(root):
    """Every `*.py` under `root`, `__pycache__` excluded, sorted."""
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _tree_of(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=path.name)


def _dumps_calls(path):
    """How many calls in this module serialise via json.dumps, however it was imported.

    `json.dumps(...)` is counted, and so is a bare `dumps(...)`, so `from json import
    dumps` cannot hide a copy from this census.
    """
    count = 0
    for node in ast.walk(_tree_of(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "dumps"
                and isinstance(func.value, ast.Name) and func.value.id == "json"):
            count += 1
        elif isinstance(func, ast.Name) and func.id == "dumps":
            count += 1
    return count


def _imports_json(path):
    for node in ast.walk(_tree_of(path)):
        if isinstance(node, ast.Import):
            if any(a.name == "json" or a.name.startswith("json.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "json" or module.startswith("json."):
                return True
    return False


def _census_in(root):
    """(modules walked, {name: dumps calls}, [names importing json]) under `root`."""
    modules = _modules_in(root)
    calls = {p.name: _dumps_calls(p) for p in modules}
    return modules, {k: v for k, v in calls.items() if v}, [p.name for p in modules
                                                            if _imports_json(p)]


def test_b3_exactly_one_json_dumps_call_under_src_and_it_is_in_render():
    modules, calls, _ = _census_in(SRC_DIR)
    total = sum(calls.values())
    assert total == 1, (
        f"the JSON document tail is serialised {total} time(s) across {len(modules)} "
        f"module(s) under src/agent_gap_radar/, expected exactly 1: {calls}")
    assert list(calls) == ["render.py"], (
        f"the single implementation must live in render.py, found it in {list(calls)}")


def test_b3_exactly_two_modules_import_json():
    modules, _, importers = _census_in(SRC_DIR)
    assert importers == ["registry.py", "render.py"], (
        f"exactly two modules may import `json` -- render.py (dumps) and registry.py "
        f"(loads); {len(modules)} module(s) walked, importers were {importers}")


#: Behavior 4 -- the floor the live census must clear before any count it reports means
#: anything. Named once, so the guard the live tree passes is the SAME callable the
#: collapsed tree is required to trip.
DOMAIN_FLOOR = 8


def _assert_domain_is_real(modules, where):
    assert len(modules) >= DOMAIN_FLOOR, (
        f"census domain collapsed to {len(modules)} module(s) under {where}; a small "
        "domain reads as health it never measured")


def test_b4_census_domain_is_non_empty_and_reported():
    modules, calls, importers = _census_in(SRC_DIR)
    _assert_domain_is_real(modules, f"{SRC_DIR.name}/")
    assert all(p.suffix == ".py" for p in modules)
    assert not any("__pycache__" in p.parts for p in modules)
    print(f"census domain: {len(modules)} modules, dumps calls {calls}, "
          f"json importers {importers}")


#: Known-bad: a fifth copy of the tail. Must count 1.
PLANTED_DUMPS = (
    "import json\n"
    "\n"
    "\n"
    "def emit(payload):\n"
    '    return json.dumps(payload, indent=2, sort_keys=False) + "\\n"\n'
)

#: Known-good: the convention this iteration installs. Must count 0.
PLANTED_HELPER = (
    "from agent_gap_radar.render import json_document\n"
    "\n"
    "\n"
    "def emit(payload):\n"
    "    return json_document(payload)\n"
)

#: Near-miss: `json` imported and used, but only to PARSE. Must count 0 calls while
#: still registering as an importer, so the two census rules are independent.
PLANTED_LOADS = (
    "import json\n"
    "\n"
    "\n"
    "def read(text):\n"
    "    return json.loads(text)\n"
)

#: Evasion: the same serialisation reached through `from json import dumps`.
PLANTED_ALIASED = (
    "from json import dumps\n"
    "\n"
    "\n"
    "def emit(payload):\n"
    '    return dumps(payload, indent=2, sort_keys=False) + "\\n"\n'
)


@pytest.mark.parametrize(
    "sample,expected",
    [(PLANTED_DUMPS, 1), (PLANTED_HELPER, 0), (PLANTED_LOADS, 0), (PLANTED_ALIASED, 1)],
    ids=["known-bad", "known-good", "near-miss-loads-only", "evasion-from-json-import"])
def test_b4_call_matcher_is_two_sided(tmp_path, sample, expected):
    module = tmp_path / "sample.py"
    module.write_text(sample, encoding="utf-8")
    assert _dumps_calls(module) == expected


def _planted_tree(root, copies, filler=PLANTED_HELPER):
    """A src-shaped tree of 9 modules, `copies` of which carry the tail."""
    root.mkdir(parents=True)
    for index in range(9):
        body = PLANTED_DUMPS if index < copies else filler
        (root / f"mod{index}.py").write_text(body, encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "mod0.py").write_text(PLANTED_DUMPS, encoding="utf-8")
    return root


def test_b4_census_counts_up_when_a_second_copy_is_planted(tmp_path):
    """The DOMAIN walk, not just the matcher: a returning copy must be DETECTED, or
    behavior 3 passing over `src/` is health it never measured."""
    modules, calls, _ = _census_in(_planted_tree(tmp_path / "one", copies=1))
    assert len(modules) == 9, "`__pycache__` leaked into the domain"
    assert sum(calls.values()) == 1 and list(calls) == ["mod0.py"], calls

    modules, calls, _ = _census_in(_planted_tree(tmp_path / "two", copies=2))
    assert len(modules) == 9
    assert sum(calls.values()) == 2, (
        "a second copy of the tail did NOT raise the census count; behavior 3 would pass "
        f"with the duplicate still present: {calls}")

    modules, calls, _ = _census_in(_planted_tree(tmp_path / "none", copies=0))
    assert len(modules) == 9 and calls == {}, calls


def test_b4_import_census_counts_up_and_is_not_fooled_by_a_parse_only_module(tmp_path):
    root = _planted_tree(tmp_path / "imports", copies=1, filler=PLANTED_HELPER)
    (root / "reader.py").write_text(PLANTED_LOADS, encoding="utf-8")
    modules, calls, importers = _census_in(root)
    assert len(modules) == 10
    assert sum(calls.values()) == 1, calls
    assert importers == ["mod0.py", "reader.py"], (
        "the import census must see BOTH the serialiser and the parse-only module; a "
        f"parse-only module counts as an importer and not as a copy: {importers}")


def test_b4_census_fails_when_the_walk_collapses(tmp_path):
    """The domain guard itself is two-sided, and this is the SILENT half.

    Asserting only that a tiny tree measures below the floor restates the premise and
    proves nothing about the guard: it would pass with `DOMAIN_FLOOR` set to zero. So the
    guard is EXERCISED here -- the same `_assert_domain_is_real` the live census calls must
    RAISE on the collapsed tree, and must not raise on the real one.
    """
    tiny = tmp_path / "tiny"
    tiny.mkdir()
    (tiny / "only.py").write_text(PLANTED_HELPER, encoding="utf-8")
    modules, _, _ = _census_in(tiny)
    assert len(modules) < DOMAIN_FLOOR, "premise: this tree is below the floor"
    with pytest.raises(AssertionError, match="census domain collapsed"):
        _assert_domain_is_real(modules, "tiny/")
    _assert_domain_is_real(_modules_in(SRC_DIR), "src/")


# ---------------------------------------------------------------------------
# behavior 5 -- no emitted byte and no CLI surface moves
# ---------------------------------------------------------------------------

def test_b5_the_verb_set_is_unchanged(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for verb in VERBS:
        assert verb in out, f"verb `{verb}` vanished from the usage line"
    assert "{" + ",".join(VERBS) + "}" in out, (
        f"the published verb SEQUENCE moved; usage was:\n{out}")


@pytest.mark.parametrize("verb,flags", [("list", ["--floor", "--json", "--layer"]),
                                        ("prd", ["--gap", "--project"]),
                                        ("scan", ["--gaps", "--json", "--prd",
                                                  "--exit-code"]),
                                        ("diff", ["--json"])])
def test_b5_each_emitting_verb_keeps_its_flags(capsys, verb, flags):
    with pytest.raises(SystemExit) as exit_info:
        main([verb, "--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for flag in flags:
        assert flag in out, f"`radar {verb}` lost `{flag}`:\n{out}"


def test_b5_the_four_key_sequences_are_unchanged(capsys, tmp_path, reg, target,
                                                 diff_pair):
    old, new = diff_pair
    measured = {
        "list": json.loads(_emit(capsys, ["list", str(reg), "--json"])),
        "prd": json.loads(_emit(capsys, ["prd", str(reg)])),
        "scan": json.loads(_emit(capsys, ["scan", str(target), "--gaps", str(reg),
                                          "--json"])),
        "diff": json.loads(_emit(capsys, ["diff", str(old), str(new), "--json"])),
    }
    expected = {"list": LIST_TOP_KEYS, "prd": PRD_TOP_KEYS, "scan": SCAN_TOP_KEYS,
                "diff": DIFF_TOP_KEYS}
    for surface, payload in measured.items():
        assert list(payload) == expected[surface], (
            f"`{surface}`'s published key ORDER is part of the contract; "
            f"got {list(payload)}")


def test_b5_the_key_pins_committed_by_earlier_iterations_are_not_edited():
    """Cross-check, not a bare re-import: editing an older pin to match a changed
    payload would red THIS test, which a re-import alone could not detect."""
    assert list(ITER13_SCAN_TOP_KEYS) == SCAN_TOP_KEYS, list(ITER13_SCAN_TOP_KEYS)
    assert list(ITER23_PRD_TOP_KEYS) == PRD_TOP_KEYS, list(ITER23_PRD_TOP_KEYS)
    assert list(ITER77_DIFF_TOP_KEYS) == DIFF_TOP_KEYS, list(ITER77_DIFF_TOP_KEYS)


@pytest.mark.parametrize("argv_tail", [["list", "--json"], ["prd"]])
def test_b5_the_error_path_is_unchanged(capsys, tmp_path, argv_tail):
    missing = tmp_path / "no-such-register"
    verb, *flags = argv_tail
    rc = main([verb, str(missing), *flags])
    cap = capsys.readouterr()
    assert rc == 2, f"a missing register must exit 2, got {rc}"
    assert cap.out == "", f"stdout must carry only the document: {cap.out!r}"
    assert cap.err.startswith("Error: "), f"diagnostic must be prefixed: {cap.err!r}"


def test_b5_report_over_the_committed_register_is_deterministic_and_ends_in_one_newline(
        capsys):
    """`radar report .`: the markdown surface this iteration must not move, driven over
    the COMMITTED register so the document under test is the published one."""
    first = _emit(capsys, ["report", str(REPO_ROOT)])
    second = _emit(capsys, ["report", str(REPO_ROOT)])
    assert first == second, "`radar report` is not byte-deterministic across two runs"
    assert first.endswith("\n") and not first.endswith("\n\n"), repr(first[-4:])
    assert len(first) > 200, "`radar report` produced a suspiciously small document"


def test_b5_scan_markdown_over_the_committed_register_is_deterministic(capsys, tmp_path):
    """`radar scan`'s markdown document, with the COMMITTED register applied to a small
    target. The target is a `tmp_path` tree rather than the repo on purpose: pointing the
    walk at the whole repository costs ~54s of serialised suite time (measured), and
    `SPEED_STORY_NEEDED.md` is already open at 132.58s against a 120.00s threshold -- the
    property under test is determinism of the renderer, which the register's size
    exercises and the target's size does not."""
    victim = _target(tmp_path / "real", body=MARKER)
    argv = ["scan", str(victim), "--gaps", str(REPO_ROOT)]
    first = _emit(capsys, argv)
    second = _emit(capsys, argv)
    assert first == second, "`radar scan` is not byte-deterministic across two runs"
    assert first.endswith("\n") and not first.endswith("\n\n"), repr(first[-4:])
    assert len(first) > 200, "`radar scan` produced a suspiciously small document"
    assert "| Verdict | Count | Meaning |" in first, (
        "the scan document lost its verdict table")


def test_b5_importing_render_pulls_no_new_third_party_and_nothing_network_capable():
    code = ("import json, sys\n"
            "import agent_gap_radar.render\n"
            "tops = sorted({name.split('.')[0] for name in sys.modules})\n"
            "extra = [t for t in tops\n"
            "         if t not in sys.stdlib_module_names and not t.startswith('_')]\n"
            "print(json.dumps({'extra': extra, 'loaded': sorted(sys.modules)}))\n")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    seen = json.loads(proc.stdout.decode("utf-8"))
    allowed = {"agent_gap_radar", "pydantic", "pydantic_core", "annotated_types",
               "typing_extensions", "typing_inspection", "sitecustomize"}
    assert set(seen["extra"]) <= allowed, (
        f"importing `render` pulled a new third-party module: "
        f"{sorted(set(seen['extra']) - allowed)}")
    banned = {"socket", "http.client", "urllib.request", "ssl", "requests", "httpx"}
    assert not banned & set(seen["loaded"]), (
        "importing `render` pulled a network-capable module: "
        f"{sorted(banned & set(seen['loaded']))}")
