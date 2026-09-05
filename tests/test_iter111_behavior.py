"""Iteration 111 behaviors: no verb pays for a module it does not use.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here read `src/`, the engineer's
or the reviewer's notes, `IMPLEMENTATION.patch`, or a diff of any source file. Every
expectation comes from `pm.md`'s Expected Behaviors, and every shape claim below was
MEASURED by running the tool: eight `sys.executable -c` child processes over the
no-document argv lists, one per document verb, and one dump of `build_parser()` through the
`tests/_surface_contract.py` oracle. (Two files under `tests/` were read as data, which the
contract permits: `_surface_contract.py` for the oracle it publishes and `test_iter73_*` for
the pin it keeps on the pydantic-free module set.)

Structural notes, so this file cannot lie later:

* **Every module claim is made in a CHILD process.** `sys.modules` is process-global and
  the pytest process has pydantic loaded before collection finishes, so an in-process
  assertion here would be meaningless. One `CHILD` program answers all of them: it imports
  `agent_gap_radar.cli`, optionally builds the parser, optionally dispatches an argv, and
  then writes its census to a FILE. The census going to a file and not to stdout is what
  lets the SAME child both introspect `sys.modules` and hand back the untouched stdout /
  stderr bytes a consumer would read.
* **NO WALL-CLOCK ASSERTION APPEARS ANYWHERE IN THIS FILE**, by acceptance criterion. The
  feature is an import-graph invariant, and a millisecond threshold would be flaky on a
  loaded machine and would rot on the next one. `timeout=` arguments to `subprocess.run`
  are a hang guard, not a speed assertion: they are two orders of magnitude above the
  measured cost and no test reads an elapsed time.
* **The module-set claim is two-sided and needs no list kept in sync.** Behavior 2 asserts
  set EQUALITY against `{package, cli, taxonomy}`, so it reds both when a deferred module is
  still eager and when `taxonomy` is deferred by mistake.
* **The absence claims are guarded against vacuity.** A test that only ever proves pydantic
  is ABSENT would also pass in a venv where pydantic is not installed at all, so behavior 6
  proves the complement in the same idiom: after a document verb the same child reports
  pydantic PRESENT, and the deferred module loaded.
* **Byte-identity is asserted as cross-route plus determinism, not as a new golden.** The
  spec's byte-neutrality is already pinned by ~3,340 existing assertions whose expected
  bytes this iteration may not touch; duplicating those goldens here would add suite
  wall-clock and a second literal to drift. What this file adds is the property those
  goldens cannot see: the CHILD process and the in-process `main()` route emit the same
  bytes and the same exit code, and a second spawn of the same argv is byte-identical. The
  old-tree-versus-working-tree comparison the spec also asks for is a one-off MEASUREMENT
  (`git archive HEAD`), reported in `tester.md`; it is deliberately not committed here,
  because after the ship commit `HEAD` IS this tree and such a test would pass vacuously
  forever.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; probe files are written under pytest's `tmp_path`.

ONE SPEC AMBIGUITY, also carried in the tester report: behaviors 5 and 7 say "byte-for-byte
what the CURRENT tree produces", which is a statement about two trees and therefore not
expressible as a committed assertion (see the previous note). Tested here as the two
durable halves of it -- route-identity and run-determinism -- with the two-tree half
measured once, by hand, and reported.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar import __version__
from agent_gap_radar import cli

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _surface_contract import parser_surface  # noqa: E402  (oracle, imported not rewritten)

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: Behavior 2's exact answer: the package, the entry point, and the one module the spec
#: keeps eager because `build_parser()` reads it and it was measured free (stdlib only).
ALLOWED_MODULES = {"agent_gap_radar", "agent_gap_radar.cli", "agent_gap_radar.taxonomy"}

#: Behavior 9. Names a consumer imports from `cli` without a document in sight.
EXIT_NAMES = ("EXIT_CODES", "EXIT_OK", "EXIT_GAPS_PRESENT", "EXIT_ERROR", "EXIT_BROKEN_PIPE")
PUBLIC_NAMES = (*EXIT_NAMES, "ListRow", "build_parser", "main")

#: `docs/CONSUMER_CONTRACT.md`'s published error channel, re-stated as the one string this
#: file needs; iteration 109 made all six structural doors speak it.
ERROR_PREFIX = "Error: "

#: Behaviors 4 and 5. Every argv that produces ZERO document bytes, with the exit code the
#: tree returns today. Six structural refusals, then the two zero-exit no-document paths.
NO_DOCUMENT_CASES = [
    ("unknown-verb", ["nosuchverb"], 2),
    ("show-missing-id", ["show"], 2),
    ("scan-missing-target", ["scan"], 2),
    ("diff-missing-operands", ["diff"], 2),
    ("report-bad-floor", ["report", "--floor", "x"], 2),
    ("unknown-option", ["--nosuchoption"], 2),
    ("version", ["--version"], 0),
    ("bare", [], 0),
]
REFUSALS = [case for case in NO_DOCUMENT_CASES if case[2] == 2]

#: A real gap id and a populated layer, read off the register as DATA so this file carries
#: no keyed expectation about a register an unattended research pass keeps growing.
REAL_GAP_ID = sorted(path.name[:7] for path in GAPS_DIR.glob("GAP-*.json"))[0]


def _a_populated_layer() -> str:
    """A layer that has at least one record, taken from the register itself."""
    for path in sorted(GAPS_DIR.glob("GAP-*.json")):
        layer = json.loads(path.read_text(encoding="utf-8")).get("layer")
        if layer:
            return str(layer)
    raise AssertionError("the live register published no record with a layer")


POPULATED_LAYER = _a_populated_layer()

#: Behavior 6. Each document verb and the module it may not run without. `taxonomy` is in
#: the list precisely because it is the verb with no register: it still renders, so it still
#: needs `render`, which is why the spec keeps it OUT of scope for pydantic-freedom.
ON_DEMAND_CASES = [
    ("taxonomy", ["taxonomy"], ["agent_gap_radar.render"]),
    ("list", ["list", "."], ["agent_gap_radar.registry", "agent_gap_radar.render"]),
    ("scan", ["scan", "."], ["agent_gap_radar.scan"]),
    ("diff", ["diff", ".", "."], ["agent_gap_radar.diff"]),
    ("prd", ["prd", "."], ["agent_gap_radar.prd"]),
]

#: Behavior 7. Every verb over the live register, as a consumer spells it.
DOCUMENT_INVOCATIONS = [
    ("validate", ["validate", "."]),
    ("list", ["list", "."]),
    ("list-json", ["list", ".", "--json"]),
    ("list-layer", ["list", ".", "--layer", POPULATED_LAYER]),
    ("list-layer-bogus", ["list", ".", "--layer", "no-such-layer-here"]),
    ("report", ["report", "."]),
    ("report-floor-4", ["report", ".", "--floor", "4"]),
    ("show-real", ["show", REAL_GAP_ID]),
    ("show-missing", ["show", "GAP-999"]),
    ("prd", ["prd", "."]),
    ("taxonomy", ["taxonomy"]),
    ("diff", ["diff", ".", "."]),
    ("diff-json", ["diff", ".", ".", "--json"]),
]

#: Behavior 8. `build_parser()`'s surface as it stands today, per verb:
#: (sorted option strings, positional count, sorted required dests, positional dests).
#: Compared through the oracle in `tests/_surface_contract.py` rather than re-derived here.
EXPECTED_SURFACE = {
    "diff": (["--json"], 2, ["new", "old"], ["old", "new"]),
    "list": (["--floor", "--json", "--layer"], 1, [], ["path"]),
    "prd": (["--gap", "--project"], 1, [], ["path"]),
    "report": (["--floor"], 1, [], ["path"]),
    "scan": (["--exit-code", "--gaps", "--json", "--prd"], 1, ["target"], ["target"]),
    "show": ([], 2, ["gap_id"], ["gap_id", "path"]),
    "taxonomy": ([], 0, [], []),
    "validate": ([], 1, [], ["path"]),
}

#: Behavior 8's second half, read off the raw actions: per verb, one row per argument as
#: (dest, sorted option strings, required, default, nargs). `"SUPPRESS"` stands for
#: `argparse.SUPPRESS`, which is the default argparse gives its own `-h`.
EXPECTED_ARGUMENTS = {
    "diff": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("old", [], True, None, None),
        ("new", [], True, None, None),
        ("json", ["--json"], False, False, 0),
    ],
    "list": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
        ("floor", ["--floor"], False, 2, None),
        ("json", ["--json"], False, False, 0),
        ("layer", ["--layer"], False, None, None),
    ],
    "prd": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
        ("gap_id", ["--gap"], False, None, None),
        ("project", ["--project"], False, "agent-gap-radar", None),
    ],
    "report": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
        ("floor", ["--floor"], False, 2, None),
    ],
    "scan": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("target", [], True, None, None),
        ("gaps", ["--gaps"], False, ".", None),
        ("json", ["--json"], False, False, 0),
        ("prd", ["--prd"], False, False, 0),
        ("exit_code", ["--exit-code"], False, False, 0),
    ],
    "show": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("gap_id", [], True, None, None),
        ("path", [], False, ".", "?"),
    ],
    "taxonomy": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
    ],
    "validate": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
    ],
}

# ---------------------------------------------------------------------------
# The child program. Every module claim in this file is answered by THIS.
# ---------------------------------------------------------------------------

CHILD = r'''
import json, sys
from pathlib import Path

spec = json.loads(sys.argv[1])
probe = sys.argv[2]

import agent_gap_radar.cli as cli

result = {"stage": "imported", "code": None, "error": None}
if spec.get("build_parser"):
    cli.build_parser()
    result["stage"] = "parser"
if spec.get("names"):
    result["names"] = {name: hasattr(cli, name) for name in spec["names"]}
if spec.get("argv") is not None:
    try:
        result["code"] = cli.main([str(token) for token in spec["argv"]])
    except SystemExit as exc:
        result["code"] = exc.code
    except BaseException as exc:
        # A NameError or UnboundLocalError here IS the defect behavior 6 hunts, so it is
        # recorded and handed back rather than allowed to look like a crashed child.
        result["error"] = type(exc).__name__ + ": " + str(exc)
    result["stage"] = "dispatched"
sys.stdout.flush()
sys.stderr.flush()
result["pydantic"] = "pydantic" in sys.modules
result["modules"] = sorted(name for name in sys.modules
                           if name == "agent_gap_radar"
                           or name.startswith("agent_gap_radar."))
Path(probe).write_text(json.dumps(result), encoding="utf-8")
'''


def child(tmp_path, label, *, argv=None, build_parser=False, names=()):
    """Run ONE child process and return its census plus its raw stdout / stderr bytes.

    `timeout` is a hang guard only: nothing in this file asserts on elapsed time.
    """
    spec = {"argv": argv, "build_parser": build_parser, "names": list(names)}
    probe = tmp_path / f"probe-{label}.json"
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, json.dumps(spec), str(probe)],
        capture_output=True, cwd=str(REPO_ROOT), timeout=600,
    )
    assert probe.exists(), (
        f"{label}: the child died before writing its census (rc={proc.returncode}); "
        f"stderr tail: {proc.stderr.decode(errors='replace')[-1500:]!r}"
    )
    census = json.loads(probe.read_text(encoding="utf-8"))
    census["stdout"] = proc.stdout
    census["stderr"] = proc.stderr
    census["proc_rc"] = proc.returncode
    return census


def in_process(argv):
    """The same argv driven through `cli.main` in THIS process: (code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([str(token) for token in argv])
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def nonempty_lines(text):
    return [line for line in text.splitlines() if line.strip()]


def assert_pydantic_free(census, label):
    """The two halves of the invariant, always asserted together."""
    assert census["error"] is None, f"{label}: the child raised {census['error']}"
    assert census["pydantic"] is False, (
        f"{label}: pydantic was imported anyway; agent_gap_radar modules loaded: "
        f"{census['modules']}"
    )
    assert set(census["modules"]) == ALLOWED_MODULES, (
        f"{label}: loaded {sorted(census['modules'])}, expected exactly "
        f"{sorted(ALLOWED_MODULES)}"
    )


# ---------------------------------------------------------------------------
# Behavior 1 -- importing the entry point does not load pydantic.
# ---------------------------------------------------------------------------


def test_behavior_1_importing_cli_does_not_import_pydantic(tmp_path):
    census = child(tmp_path, "b1")
    assert census["stage"] == "imported"
    assert census["pydantic"] is False, (
        "`import agent_gap_radar.cli` still pulled pydantic; modules loaded: "
        f"{census['modules']}"
    )


def test_behavior_1_the_absence_is_not_because_pydantic_is_unavailable(tmp_path):
    """Anti-vacuity for behavior 1: the SAME child, after one document verb, has it."""
    census = child(tmp_path, "b1-complement", argv=["taxonomy"])
    assert census["error"] is None, census["error"]
    assert census["pydantic"] is True, (
        "a document verb ran without pydantic ever being imported, so behavior 1's "
        "absence proves nothing about deferral -- check the venv, not the seam"
    )


# ---------------------------------------------------------------------------
# Behavior 2 -- the loaded module set is exactly package + cli + taxonomy.
# ---------------------------------------------------------------------------


def test_behavior_2_module_set_is_exactly_package_cli_and_taxonomy(tmp_path):
    census = child(tmp_path, "b2")
    loaded = set(census["modules"])
    assert loaded, "the child reported no agent_gap_radar module at all"
    assert loaded == ALLOWED_MODULES, (
        f"loaded {sorted(loaded)}; still eager: {sorted(loaded - ALLOWED_MODULES)}; "
        f"deferred by mistake: {sorted(ALLOWED_MODULES - loaded)}"
    )


def test_behavior_2_taxonomy_is_the_one_module_that_stays_eager(tmp_path):
    """The other side of the equality, spelled out: `taxonomy` must NOT be deferred."""
    census = child(tmp_path, "b2-taxonomy")
    assert "agent_gap_radar.taxonomy" in census["modules"], census["modules"]


@pytest.mark.parametrize("deferred", sorted(
    f"agent_gap_radar.{name}" for name in
    ("diff", "models", "prd", "registry", "render", "scan", "scoring")))
def test_behavior_2_each_named_module_is_absent_at_import(tmp_path, deferred):
    """One failing name per line, so a regression says WHICH import came back."""
    census = child(tmp_path, "b2-" + deferred.rsplit(".", 1)[-1])
    assert deferred not in census["modules"], (
        f"{deferred} is still imported at `import agent_gap_radar.cli` time"
    )


# ---------------------------------------------------------------------------
# Behavior 3 -- building the parser stays pure.
# ---------------------------------------------------------------------------


def test_behavior_3_build_parser_loads_nothing_more(tmp_path):
    census = child(tmp_path, "b3", build_parser=True)
    assert census["stage"] == "parser", census["stage"]
    assert_pydantic_free(census, "build_parser()")


# ---------------------------------------------------------------------------
# Behavior 4 -- every no-document path dispatches without the document stack.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,argv,expected_code", NO_DOCUMENT_CASES,
                         ids=[case[0] for case in NO_DOCUMENT_CASES])
def test_behavior_4_no_document_path_pays_for_no_document_module(
        tmp_path, label, argv, expected_code):
    census = child(tmp_path, "b4-" + label, argv=argv)
    assert census["stage"] == "dispatched", census["stage"]
    assert census["code"] == expected_code, (
        f"{label}: exit code {census['code']!r}, expected {expected_code}"
    )
    assert_pydantic_free(census, label)


# ---------------------------------------------------------------------------
# Behavior 5 -- the published bytes of those paths are unmoved.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,argv,expected_code", REFUSALS,
                         ids=[case[0] for case in REFUSALS])
def test_behavior_5_refusal_writes_usage_then_one_error_line_and_no_document(
        tmp_path, label, argv, expected_code):
    census = child(tmp_path, "b5-" + label, argv=argv)
    assert census["code"] == 2, (label, census["code"])
    assert census["stdout"] == b"", f"{label}: stdout was not empty: {census['stdout'][:200]!r}"
    stderr = census["stderr"].decode()
    lines = nonempty_lines(stderr)
    assert lines, f"{label}: stderr carried no non-empty line"
    assert lines[-1].startswith(ERROR_PREFIX), (
        f"{label}: last non-empty stderr line is not the published error line: {lines[-1]!r}"
    )
    assert lines[-1][len(ERROR_PREFIX):].strip(), f"{label}: no message after the prefix"
    usage = [index for index, line in enumerate(lines) if line.startswith("usage:")]
    assert usage, f"{label}: no usage block: {stderr!r}"
    assert max(usage) < len(lines) - 1, f"{label}: a usage line came AFTER the error line"


def test_behavior_5_version_writes_the_version_to_stdout(tmp_path):
    census = child(tmp_path, "b5-version", argv=["--version"])
    assert census["code"] == 0, census["code"]
    assert census["stdout"] == f"{__version__}\n".encode(), census["stdout"]
    assert census["stderr"] == b"", census["stderr"]


def test_behavior_5_bare_radar_writes_usage_help_to_stdout(tmp_path):
    census = child(tmp_path, "b5-bare", argv=[])
    assert census["code"] == 0, census["code"]
    stdout = census["stdout"].decode()
    assert stdout.startswith("usage: radar"), stdout[:120]
    assert stdout.endswith("\n") and not stdout.endswith("\n\n"), repr(stdout[-4:])
    assert census["stderr"] == b"", census["stderr"]


@pytest.mark.parametrize("label,argv,expected_code", NO_DOCUMENT_CASES,
                         ids=[case[0] for case in NO_DOCUMENT_CASES])
def test_behavior_5_child_and_in_process_routes_agree_byte_for_byte(
        tmp_path, label, argv, expected_code):
    """Route-identity: the seam may not make the process boundary disagree with `main`."""
    census = child(tmp_path, "b5-route-" + label, argv=argv)
    code, out, err = in_process(argv)
    assert code == census["code"] == expected_code, (label, code, census["code"])
    assert out == census["stdout"].decode(), label
    assert err == census["stderr"].decode(), label


# ---------------------------------------------------------------------------
# Behavior 6 -- each document verb loads what it needs, on demand.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,argv,required", ON_DEMAND_CASES,
                         ids=[case[0] for case in ON_DEMAND_CASES])
def test_behavior_6_document_verb_loads_its_module_on_demand(
        tmp_path, label, argv, required):
    census = child(tmp_path, "b6-" + label, argv=argv)
    assert census["error"] is None, (
        f"{label}: the deferred import did not reach its user: {census['error']}"
    )
    assert isinstance(census["code"], int), (label, census["code"])
    missing = [name for name in required if name not in census["modules"]]
    assert not missing, f"{label}: never loaded {missing}; loaded {census['modules']}"


@pytest.mark.parametrize("label,argv,required", ON_DEMAND_CASES,
                         ids=[case[0] for case in ON_DEMAND_CASES])
def test_behavior_6_no_verb_raises_a_deferred_import_name_error(
        tmp_path, label, argv, required):
    """The failure mode a move-the-import change actually produces, named explicitly."""
    census = child(tmp_path, "b6-name-" + label, argv=argv)
    error = census["error"] or ""
    assert not error.startswith(("NameError", "UnboundLocalError")), f"{label}: {error}"


# ---------------------------------------------------------------------------
# Behavior 7 -- every verb's published bytes are unmoved.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,argv", DOCUMENT_INVOCATIONS,
                         ids=[case[0] for case in DOCUMENT_INVOCATIONS])
def test_behavior_7_document_verb_bytes_agree_across_routes(tmp_path, label, argv):
    census = child(tmp_path, "b7-" + label, argv=argv)
    code, out, err = in_process(argv)
    assert code == census["code"], (label, code, census["code"])
    assert out == census["stdout"].decode(), f"{label}: stdout differs between routes"
    assert err == census["stderr"].decode(), f"{label}: stderr differs between routes"


@pytest.mark.parametrize("label,argv", DOCUMENT_INVOCATIONS,
                         ids=[case[0] for case in DOCUMENT_INVOCATIONS])
def test_behavior_7_document_verb_is_deterministic_and_ends_in_one_newline(
        tmp_path, label, argv):
    first = child(tmp_path, "b7a-" + label, argv=argv)
    second = child(tmp_path, "b7b-" + label, argv=argv)
    assert first["stdout"] == second["stdout"], f"{label}: stdout is not byte-stable"
    assert first["stderr"] == second["stderr"], f"{label}: stderr is not byte-stable"
    assert first["code"] == second["code"], label
    stdout = first["stdout"].decode()
    if stdout:
        assert stdout.endswith("\n") and not stdout.endswith("\n\n"), repr(stdout[-4:])


# ---------------------------------------------------------------------------
# Behavior 8 -- the parser surface is unchanged.
# ---------------------------------------------------------------------------


def test_behavior_8_verb_set_and_per_verb_surface_are_unchanged():
    surface = parser_surface(cli.build_parser())
    assert sorted(surface) == sorted(EXPECTED_SURFACE), sorted(surface)
    for verb, (options, positionals, required, dests) in sorted(EXPECTED_SURFACE.items()):
        measured = surface[verb]
        assert sorted(measured.options) == options, (verb, sorted(measured.options))
        assert measured.positionals == positionals, (verb, measured.positionals)
        assert sorted(measured.required) == required, (verb, sorted(measured.required))
        assert list(measured.positional_dests) == dests, (verb, measured.positional_dests)


def test_behavior_8_per_argument_required_default_and_nargs_are_unchanged():
    measured = {}
    for action in cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            for verb, subparser in action.choices.items():
                measured[verb] = [
                    (item.dest, sorted(item.option_strings), bool(item.required),
                     "SUPPRESS" if item.default is argparse.SUPPRESS else item.default,
                     item.nargs)
                    for item in subparser._actions
                ]
    assert measured, "build_parser() registered no subcommands"
    assert sorted(measured) == sorted(EXPECTED_ARGUMENTS), sorted(measured)
    for verb in sorted(EXPECTED_ARGUMENTS):
        assert measured[verb] == EXPECTED_ARGUMENTS[verb], (verb, measured[verb])


# ---------------------------------------------------------------------------
# Behavior 9 -- the published names survive the seam.
# ---------------------------------------------------------------------------


def test_behavior_9_public_names_import_with_pydantic_absent(tmp_path):
    census = child(tmp_path, "b9", names=PUBLIC_NAMES)
    assert_pydantic_free(census, "public names")
    missing = [name for name, present in census["names"].items() if not present]
    assert not missing, f"these names vanished from `cli`: {missing}"


def test_behavior_9_exit_code_values_are_unmoved():
    """The names alone are not the contract: their VALUES are what a consumer branches on."""
    assert cli.EXIT_OK == 0, cli.EXIT_OK
    assert cli.EXIT_GAPS_PRESENT == 1, cli.EXIT_GAPS_PRESENT
    assert cli.EXIT_ERROR == 2, cli.EXIT_ERROR
    assert cli.EXIT_BROKEN_PIPE == 141, cli.EXIT_BROKEN_PIPE
    assert tuple(cli.EXIT_CODES) == (0, 1, 2, 141), cli.EXIT_CODES
    # `ListRow`'s parameter is allowed to have become a forward reference (`'Gap'`), which
    # is exactly how a pydantic-free module can still publish the alias; the spec only
    # forbids the NAME vanishing, so the value is asserted present, not spelled out.
    assert cli.ListRow is not None


# ---------------------------------------------------------------------------
# Behavior 4, extended -- the `--help` family, which the spec's own `## Why`
# names among the no-document paths (`--version`, `--help`, bare `radar`) but
# whose argv list omits. Measured before it was asserted: all ten of these
# report the same `{package, cli, taxonomy}` census as a bare import.
# ---------------------------------------------------------------------------

#: Root help, its short spelling, and every verb's help. Each is a no-document path: it
#: writes a usage block to stdout and exits 0 without a register ever being read.
HELP_CASES = [("root-help", ["--help"]), ("root-h", ["-h"])] + [
    (f"{verb}-help", [verb, "--help"]) for verb in sorted(EXPECTED_SURFACE)
]


@pytest.mark.parametrize("label,argv", HELP_CASES, ids=[case[0] for case in HELP_CASES])
def test_behavior_4_help_is_a_no_document_path_too(tmp_path, label, argv):
    """`radar --help` and `radar <verb> --help` may not pay for the document stack."""
    census = child(tmp_path, "b4-" + label, argv=argv)
    assert census["stage"] == "dispatched", census["stage"]
    assert census["code"] == 0, f"{label}: exit code {census['code']!r}, expected 0"
    assert_pydantic_free(census, label)


@pytest.mark.parametrize("label,argv", HELP_CASES, ids=[case[0] for case in HELP_CASES])
def test_behavior_5_help_writes_a_usage_block_to_stdout_and_nothing_to_stderr(
        tmp_path, label, argv):
    census = child(tmp_path, "b5-" + label, argv=argv)
    stdout = census["stdout"].decode()
    assert stdout.startswith("usage: radar"), f"{label}: {stdout[:120]!r}"
    assert stdout.endswith("\n") and not stdout.endswith("\n\n"), repr(stdout[-4:])
    assert census["stderr"] == b"", f"{label}: {census['stderr'][:200]!r}"


# ---------------------------------------------------------------------------
# Behavior 5, extended -- `docs/CONSUMER_CONTRACT.md` publishes exit 2 as ONE
# stderr line beginning `Error: `. The inherited assertion pinned only that the
# LAST non-empty line speaks it, which a second `Error: ` line would satisfy.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,argv,expected_code", REFUSALS,
                         ids=[case[0] for case in REFUSALS])
def test_behavior_5_refusal_speaks_the_error_prefix_exactly_once(
        tmp_path, label, argv, expected_code):
    census = child(tmp_path, "b5-once-" + label, argv=argv)
    lines = nonempty_lines(census["stderr"].decode())
    spoken = [line for line in lines if line.startswith(ERROR_PREFIX)]
    assert len(spoken) == 1, (
        f"{label}: the contract publishes ONE `{ERROR_PREFIX}` line, saw {len(spoken)}: "
        f"{spoken!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 2, anti-vacuity -- the set equality only has teeth if the seven
# names it EXCLUDES are reachable at all. A venv missing them, or a `cli` that
# silently swallowed an ImportError, would satisfy behavior 2 and mean nothing.
# ---------------------------------------------------------------------------

#: The seven module-level imports the first acceptance criterion removes from `cli.py`.
DEFERRED_MODULES = tuple(sorted(
    f"agent_gap_radar.{name}"
    for name in ("diff", "models", "prd", "registry", "render", "scan", "scoring")))


def test_behavior_2_every_deferred_module_is_still_reachable_after_a_document_verb(
        tmp_path):
    """Measured: one document verb pulls all seven back, so the absence above is deferral."""
    census = child(tmp_path, "b2-antivacuity", argv=["list", "."])
    assert census["error"] is None, census["error"]
    unreachable = [name for name in DEFERRED_MODULES if name not in census["modules"]]
    assert not unreachable, (
        "these modules never loaded even on a document path, so behavior 2's absence "
        f"proves nothing about the seam: {unreachable}; loaded {census['modules']}"
    )
    assert census["pydantic"] is True, "a document verb ran with pydantic never imported"


# ---------------------------------------------------------------------------
# Acceptance criteria this file is itself the subject of. Nothing else in the
# suite can see them, so they are asserted over this file's own source text.
# ---------------------------------------------------------------------------

#: Criterion: "with NO wall-clock assertion anywhere in the file". Each needle is spelled
#: as two fragments JOINED AT RUNTIME, so the literal it hunts never appears in this file
#: and the guard cannot red on its own definition -- the first draft did exactly that.
#: `subprocess`'s `timeout=` is a hang guard and is deliberately not a needle. Only clock
#: APIs are listed: the prose words "elapsed"/"duration" appear in this file's own notes
#: explaining why no clock is read, and a needle that fires on an explanation is a lint,
#: not a brake.
WALL_CLOCK_TOKENS = tuple(left + right for left, right in (
    ("perf_", "counter"),
    ("mono", "tonic"),
    ("process_", "time"),
    ("time", ".time("),
    ("time", ".sleep"),
    ("time", "it"),
    ("import ", "time"),
    ("datetime.", "now"),
))


def test_acceptance_this_file_asserts_no_wall_clock_time():
    """The one acceptance criterion no other test in the suite can see."""
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    spoken = sorted(token for token in WALL_CLOCK_TOKENS if token in source)
    assert not spoken, (
        "the feature is an import-graph invariant, so a millisecond threshold here would "
        f"be flaky and would rot on the next machine; found {spoken}"
    )


def test_acceptance_the_wall_clock_guard_is_not_vacuous():
    """Anti-vacuity: the needles are joined at runtime, so prove they still MATCH text."""
    assert len(WALL_CLOCK_TOKENS) == 8, WALL_CLOCK_TOKENS
    needle = WALL_CLOCK_TOKENS[0]
    assert needle == "perf_" + "counter", needle
    sample = "start = " + needle + "()"
    fired = [token for token in WALL_CLOCK_TOKENS if token in sample]
    assert fired == [needle], fired


# The public-repo bar (no absolute machine path, no personal identifier) is deliberately
# NOT re-asserted here: `tests/test_iter91_behavior.py` runs `tools/check_public_safety.py`
# over the whole git-tracked tree and is already proven two-sided. Its domain is the git
# INDEX, so it covers this file from the ship commit onward, not while it is untracked --
# checked by hand for this round and reported in the tester notes.


# ---------------------------------------------------------------------------
# Acceptance criteria 1 and 3, which no numbered behavior states plainly: the
# seam is FUNCTION-LOCAL, and `Gap` is `TYPE_CHECKING`-only. Behaviors 1-3 pin
# what is in `sys.modules`; they are SILENT on what is in `vars(cli)`, and two
# other ways of building this feature satisfy every one of them: a module
# `__getattr__` (criterion 3 forbids it by name) and a lazy loader that rebinds
# module globals. Either makes `cli.registry` an accidental public name a
# consumer can come to depend on, and makes the module's attribute set depend
# on which verb ran first. Every census below was MEASURED in a real child
# before it was asserted, including the anchor that keeps it from being blind.
# ---------------------------------------------------------------------------

#: Criterion 1's seven names, spelled as the BARE attributes a module-global rebinding
#: would leave behind. Behavior 2's `DEFERRED_MODULES` spells the same seven dotted, for
#: `sys.modules`; these two constants answer different questions and neither implies the
#: other -- a local `import x` inside a function loads `sys.modules["pkg.x"]` and creates
#: NO module attribute, while `global x; import x` creates both.
DEFERRED_ATTRS = ("diff", "models", "prd", "registry", "render", "scan", "scoring")

#: Criterion 1's other half: `Gap` is imported under `if TYPE_CHECKING:` only, so it is a
#: name for a type checker and never a runtime attribute -- not at import, and not after
#: the seam has been taken. `from __future__ import annotations` is what makes that legal.
TYPE_ONLY_ATTRS = ("Gap",)

#: The ANTI-VACUITY anchor for the whole `vars()` census, and simultaneously criterion 2's
#: own claim. Criterion 2 keeps the `taxonomy` import and `from . import __version__` at
#: module level because `build_parser()`, `_unknown_layer()` and `_status_list()` read them
#: and both were measured free. Measured: `taxonomy` is imported for its NAMES, so the
#: module object itself is absent from `vars(cli)` while its published vocabulary is
#: present. Asserting these are visible proves a `vars()` census can see a module-level
#: import at all -- without it, "the deferred names are absent" would also hold for a
#: census that returned nothing.
EAGER_ATTRS = ("__version__", "LAYERS", "GAP_TYPES", "STATUSES")

#: One census per child, over both sides of the seam. `None` means "import and stop".
SEAM_CASES = [
    ("at-import", None),
    ("after-list", ["list", "."]),
    ("after-taxonomy", ["taxonomy"]),
]

VARS_CHILD = r'''
import json, sys
from pathlib import Path

spec = json.loads(sys.argv[1])
probe = sys.argv[2]

import agent_gap_radar.cli as cli

# Read BEFORE dispatching: a module `__getattr__` would be visible here, and an inert
# attribute lookup must stay inert, so the bogus name is probed while the census is clean.
result = {
    "vars_before": sorted(name for name in vars(cli) if not name.startswith("__")),
    "dunders_before": sorted(name for name in vars(cli) if name.startswith("__")),
    "getattr_before": "__getattr__" in vars(cli),
    "importlib_before": "importlib" in sys.modules,
    "pydantic_before": "pydantic" in sys.modules,
    "version": getattr(cli, "__version__", None),
    "code": None,
    "error": None,
}
try:
    getattr(cli, spec["bogus"])
    result["bogus"] = "NO RAISE"
except AttributeError as exc:
    result["bogus"] = "AttributeError: " + str(exc)
except BaseException as exc:
    result["bogus"] = type(exc).__name__ + ": " + str(exc)
result["pydantic_after_bogus"] = "pydantic" in sys.modules
result["modules_after_bogus"] = sorted(
    name for name in sys.modules
    if name == "agent_gap_radar" or name.startswith("agent_gap_radar."))

if spec.get("argv") is not None:
    try:
        result["code"] = cli.main([str(token) for token in spec["argv"]])
    except SystemExit as exc:
        result["code"] = exc.code
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
sys.stdout.flush()
sys.stderr.flush()
result["vars_after"] = sorted(name for name in vars(cli) if not name.startswith("__"))
result["dunders_after"] = sorted(name for name in vars(cli) if name.startswith("__"))
result["getattr_after"] = "__getattr__" in vars(cli)
result["importlib_after"] = "importlib" in sys.modules
result["pydantic_after"] = "pydantic" in sys.modules
result["modules_after"] = sorted(
    name for name in sys.modules
    if name == "agent_gap_radar" or name.startswith("agent_gap_radar."))
Path(probe).write_text(json.dumps(result), encoding="utf-8")
'''

#: A name no module may plausibly publish, used to prove attribute lookup loads nothing.
BOGUS_ATTR = "no_such_attribute_here"


def vars_child(tmp_path, label, *, argv=None):
    """Run ONE child and return its `vars(cli)` census on both sides of the seam.

    A second child program rather than an extra key on `CHILD`: the inherited program is
    what 76 green assertions above already depend on, and this one has to read `vars(cli)`
    both BEFORE and AFTER a dispatch, which is a different shape, not another field.
    `timeout` is a hang guard; nothing here reads an elapsed measurement.
    """
    spec = {"argv": argv, "bogus": BOGUS_ATTR}
    probe = tmp_path / f"vars-{label}.json"
    proc = subprocess.run(
        [sys.executable, "-c", VARS_CHILD, json.dumps(spec), str(probe)],
        capture_output=True, cwd=str(REPO_ROOT), timeout=600,
    )
    assert probe.exists(), (
        f"{label}: the child died before writing its census (rc={proc.returncode}); "
        f"stderr tail: {proc.stderr.decode(errors='replace')[-1500:]!r}"
    )
    census = json.loads(probe.read_text(encoding="utf-8"))
    census["stdout"] = proc.stdout
    census["stderr"] = proc.stderr
    return census


@pytest.mark.parametrize("label,argv", SEAM_CASES, ids=[case[0] for case in SEAM_CASES])
def test_criterion_1_the_census_can_see_a_module_level_import(tmp_path, label, argv):
    """ANTI-VACUITY FIRST, and criterion 2: the eager names are visible on both sides."""
    census = vars_child(tmp_path, "anchor-" + label, argv=argv)
    assert census["error"] is None, f"{label}: the child raised {census['error']}"
    for side in ("before", "after"):
        visible = set(census[f"vars_{side}"]) | set(census[f"dunders_{side}"])
        missing = [name for name in EAGER_ATTRS if name not in visible]
        assert not missing, (
            f"{label}/{side}: criterion 2 keeps the taxonomy vocabulary and `__version__` "
            f"module-level, and a census that cannot see them cannot prove any absence "
            f"below; missing {missing}"
        )


@pytest.mark.parametrize("label,argv", SEAM_CASES, ids=[case[0] for case in SEAM_CASES])
def test_criterion_3_the_deferred_names_never_become_module_attributes(
        tmp_path, label, argv):
    """The seam is a local import in a function, not a rebinding of module globals."""
    census = vars_child(tmp_path, "local-" + label, argv=argv)
    assert census["error"] is None, f"{label}: the child raised {census['error']}"
    for side in ("before", "after"):
        leaked = [name for name in DEFERRED_ATTRS if name in census[f"vars_{side}"]]
        assert not leaked, (
            f"{label}/{side}: {leaked} became attributes of `cli`, so the deferral rebinds "
            f"module globals instead of importing locally -- that publishes an accidental "
            f"public name and makes the attribute set depend on which verb ran first"
        )


@pytest.mark.parametrize("label,argv", SEAM_CASES, ids=[case[0] for case in SEAM_CASES])
def test_criterion_1_gap_is_a_type_checking_only_name(tmp_path, label, argv):
    """`Gap` is imported under `if TYPE_CHECKING:`, so it never exists at run."""
    census = vars_child(tmp_path, "gap-" + label, argv=argv)
    assert census["error"] is None, f"{label}: the child raised {census['error']}"
    assert "TYPE_CHECKING" in census["vars_before"], (
        "the `if TYPE_CHECKING:` guard criterion 1 names is not even imported, so the "
        "absence of `Gap` below is not evidence of the guard"
    )
    for side in ("before", "after"):
        runtime_names = [name for name in TYPE_ONLY_ATTRS
                         if name in census[f"vars_{side}"]]
        assert not runtime_names, (
            f"{label}/{side}: {runtime_names} exist at run, so the annotation import is "
            f"not under `if TYPE_CHECKING:` -- which is how a pydantic model class gets "
            f"built on a path that emits no document"
        )


@pytest.mark.parametrize("label,argv", SEAM_CASES, ids=[case[0] for case in SEAM_CASES])
def test_criterion_3_there_is_no_module_getattr_hook(tmp_path, label, argv):
    """Criterion 3 forbids a module `__getattr__`; it would satisfy behaviors 1-3."""
    census = vars_child(tmp_path, "hook-" + label, argv=argv)
    assert census["error"] is None, f"{label}: the child raised {census['error']}"
    assert census["getattr_before"] is False, (
        "`cli` defines a module `__getattr__`, which criterion 3 forbids by name: it makes "
        "every absence above a lie waiting for the first attribute read"
    )
    assert census["getattr_after"] is False, f"{label}: a `__getattr__` appeared after"


def test_criterion_3_an_attribute_lookup_loads_nothing(tmp_path):
    """The complement of the hook test, from the consumer side rather than the module's."""
    census = vars_child(tmp_path, "inert")
    assert census["bogus"].startswith("AttributeError: "), (
        f"reading an unknown attribute did not raise `AttributeError`: {census['bogus']!r} "
        f"-- a lazy hook is the usual reason"
    )
    assert BOGUS_ATTR in census["bogus"], census["bogus"]
    assert census["pydantic_after_bogus"] is False, (
        "an attribute lookup pulled pydantic in, so the module set of behavior 2 is only "
        "true until a consumer touches the module"
    )
    assert set(census["modules_after_bogus"]) == ALLOWED_MODULES, (
        f"an attribute lookup changed the module census to "
        f"{census['modules_after_bogus']}"
    )


# ---------------------------------------------------------------------------
# Criterion 3's remaining clause -- "no `importlib`". Measured: `importlib` is
# absent from a BARE interpreter's `sys.modules` (the import machinery
# registers `importlib._bootstrap`, not the package), so its absence is a real
# observation about this module and not a tautology. Anti-vacuity comes free:
# the document path below pulls it in, so the needle demonstrably fires.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label,argv,expected_code", NO_DOCUMENT_CASES,
                         ids=[case[0] for case in NO_DOCUMENT_CASES])
def test_criterion_3_no_document_path_reaches_for_importlib(
        tmp_path, label, argv, expected_code):
    """`importlib` is not the deferral mechanism on any path that emits no document."""
    census = vars_child(tmp_path, "il-" + label, argv=argv)
    assert census["error"] is None, f"{label}: the child raised {census['error']}"
    assert census["code"] == expected_code, f"{label}: exit {census['code']!r}"
    assert census["importlib_before"] is False, "`cli` imported `importlib` eagerly"
    assert census["importlib_after"] is False, (
        f"{label}: `importlib` loaded on a path that emitted no document, which is the "
        f"mechanism criterion 3 rules out"
    )
    assert census["pydantic_after"] is False, f"{label}: pydantic loaded anyway"


def test_criterion_3_the_importlib_needle_is_not_vacuous(tmp_path):
    """A document verb DOES pull `importlib` in, so the absence above has teeth."""
    census = vars_child(tmp_path, "il-antivacuity", argv=["list", "."])
    assert census["error"] is None, census["error"]
    assert census["code"] == 0, census["code"]
    assert census["importlib_before"] is False, "`cli` imported `importlib` eagerly"
    assert census["importlib_after"] is True, (
        "no path in this tree loads `importlib`, so asserting its absence above proves "
        "nothing -- re-anchor the needle on something the document stack really pulls"
    )


# ---------------------------------------------------------------------------
# Criterion 2, the half a `sys.modules` census cannot reach: `from . import
# __version__` STAYS module-level. Behavior 4 proves `--version` exits 0 with
# pydantic absent, which a deferred version import would also satisfy; what
# makes the import module-level is that the value is readable with nothing
# dispatched at all, and that it is the same value the verb publishes.
# ---------------------------------------------------------------------------


def test_criterion_2_version_is_readable_with_nothing_dispatched(tmp_path):
    census = vars_child(tmp_path, "version-eager")
    assert census["pydantic_before"] is False, "pydantic was loaded before any dispatch"
    assert isinstance(census["version"], str) and census["version"], (
        f"`cli.__version__` is not a non-empty string at import: {census['version']!r} -- "
        f"criterion 2 keeps that import module-level"
    )
    assert census["version"] == __version__, (
        f"the entry point publishes {census['version']!r} while the package publishes "
        f"{__version__!r}"
    )


def test_criterion_2_the_eager_version_is_what_the_verb_prints(tmp_path):
    """Two-sided: the module-level value and the document-free stdout are one value."""
    census = vars_child(tmp_path, "version-verb", argv=["--version"])
    assert census["code"] == 0, census["code"]
    stdout = census["stdout"].decode()
    assert census["version"] in stdout, (
        f"`--version` wrote {stdout!r}, which does not carry the module-level "
        f"{census['version']!r}"
    )
    assert stdout.endswith("\n") and not stdout.endswith("\n\n"), repr(stdout[-4:])
    assert census["stderr"] == b"", repr(census["stderr"][:200])
