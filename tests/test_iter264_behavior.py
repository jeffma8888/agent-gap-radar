"""Iteration 264 behavior tests (black-box; spec: state/iter-264/pm.md).

Iteration 264 RE-LANDS iteration 262 (roadmap row 99): this module is that round's
approved test module carried under the new name, plus the iteration-264 additions at
the bottom (the contract's code-0 ``--help`` clause and the five-site pin sweep).

Feature: bare ``radar`` (no verb) is a structural refusal like the CLI's other doors --
exit 2, zero stdout bytes, the ``usage:`` block on stderr ABOVE one ``Error: `` line --
instead of exiting 0 with the usage text on stdout.

ISOLATION CONTRACT HONORED: nothing here read ``src/``, the engineer's or reviewer's notes,
``IMPLEMENTATION.patch``, or a diff of any source file. Expectations come from ``pm.md``;
shapes were measured by RUNNING the tool (``python -m agent_gap_radar.cli`` in child
processes and ``cli.main`` in-process) and by reading files under ``tests/`` and the
published ``docs/CONSUMER_CONTRACT.md``.

Structural notes:

* Behavior 3's control arm is the PRE-CHANGE tree, ``git archive ea5812b src`` extracted
  under ``tmp_path`` and imported through ``PYTHONPATH``; a probe asserts the child really
  imported the archived package, so the arm cannot silently compare the tree to itself.
* Behavior 6's module census runs in a CHILD process: ``sys.modules`` is process-global and
  the pytest process has pydantic loaded before collection ends.
* Behavior 5 reads the four re-baselined test modules as DATA (``ast``), which the contract
  permits; the ``NO_DOCUMENT_CASES`` table is extracted with ``ast.literal_eval`` rather than
  transcribed.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile

import pytest

from agent_gap_radar import cli

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The commit immediately before this iteration's change (spec behavior 3).
PRECHANGE_COMMIT = "ea5812b"

ERROR_PREFIX = "Error: "
USAGE_PREFIX = "usage: radar"
REQUIRED_VERB_LINE = ERROR_PREFIX + "the following arguments are required: command"
VERSION_BYTES = b"0.1.0\n"

#: Spec behavior 3: the eight verbs over the live register. ``show`` takes the first id
#: read from ``list .`` at test time (see ``first_gap_id``).
BYTE_CONTROL_VERBS = {
    "validate": ["validate", "."],
    "list": ["list", "."],
    "list-json": ["list", "--json", "."],
    "report": ["report", "."],
    "show": ["show", "<first-id>", "."],
    "prd": ["prd", "."],
    "scan": ["scan", "."],
    "taxonomy": ["taxonomy"],
}


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def capture(argv):
    """Drive ``cli.main`` in-process, returning ``(exit_code, stdout, stderr)``.

    A refusal reaches the caller as an exit CODE whether the CLI returned it or argparse
    raised ``SystemExit``; one helper covers both routes.
    """
    out, err = io.StringIO(), io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([str(token) for token in argv])
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def spawn(argv, *, env=None):
    """The same argv at the PROCESS boundary, in BYTES."""
    return subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *[str(token) for token in argv]],
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def nonempty_lines(text):
    return [line for line in text.splitlines() if line.strip()]


def assert_bare_refusal(code, out, err, *, label):
    """Spec behavior 1's shape, shared by both routes."""
    assert code == 2, f"{label}: bare radar exited {code!r}; stderr={err!r}"
    assert out == "" or out == b"", f"{label}: bare radar wrote to stdout: {out[:160]!r}"
    lines = nonempty_lines(err)
    assert lines, f"{label}: bare radar wrote nothing to stderr"
    assert lines[0].startswith(USAGE_PREFIX), (
        f"{label}: first non-empty stderr line is not the usage block: {lines[0]!r}"
    )
    assert lines[-1] == REQUIRED_VERB_LINE, (
        f"{label}: last non-empty stderr line is not the published sentence: {lines[-1]!r}"
    )


# --------------------------------------------------------------------------------------
# Behavior 1 -- bare `radar` refuses: exit 2, empty stdout, usage ABOVE one Error: line
# --------------------------------------------------------------------------------------


def test_b1_bare_radar_subprocess_exits_two_with_empty_stdout_and_usage_then_error():
    proc = spawn([])
    assert_bare_refusal(
        proc.returncode, proc.stdout, proc.stderr.decode("utf-8"), label="subprocess"
    )
    assert proc.stdout == b"", f"stdout carried {len(proc.stdout)} bytes"


def test_b1_bare_radar_in_process_exits_two_with_empty_stdout_and_usage_then_error():
    code, out, err = capture([])
    assert_bare_refusal(code, out, err, label="in-process")


def test_b1_subprocess_and_in_process_routes_agree_on_stderr_text():
    proc = spawn([])
    code, out, err = capture([])
    assert proc.returncode == code == 2
    assert proc.stderr.decode("utf-8") == err, (
        "the two routes disagree on the refusal text:\n"
        f"subprocess={proc.stderr!r}\nin-process={err!r}"
    )


def test_b1_refusal_speaks_the_published_prefix_once_and_never_argparses_own_spelling():
    proc = spawn([])
    lines = nonempty_lines(proc.stderr.decode("utf-8"))
    prefixed = [line for line in lines if line.startswith(ERROR_PREFIX)]
    assert len(prefixed) == 1, f"expected exactly one `Error: ` line, got {prefixed!r}"
    assert prefixed[0] == lines[-1], "the `Error: ` line must be the LAST non-empty line"
    assert not any(re.match(r"^\S+: error:", line) for line in lines), (
        f"argparse's own `<prog>: error:` spelling reached stderr: {lines!r}"
    )
    usage_indexes = [i for i, line in enumerate(lines) if line.startswith("usage:")]
    assert usage_indexes and max(usage_indexes) < len(lines) - 1, (
        f"every `usage:` line must sit ABOVE the `Error: ` line: {lines!r}"
    )


def test_b1_refusal_usage_line_is_the_same_usage_line_help_prints():
    """The refusal's ``usage:`` block is the same vocabulary ``--help`` publishes."""
    bare = spawn([])
    helped = spawn(["--help"])
    assert helped.returncode == 0
    bare_first = nonempty_lines(bare.stderr.decode("utf-8"))[0]
    help_first = nonempty_lines(helped.stdout.decode("utf-8"))[0]
    assert bare_first == help_first, f"{bare_first!r} != {help_first!r}"


# --------------------------------------------------------------------------------------
# Behavior 2 -- `--help` and `--version` are unchanged
# --------------------------------------------------------------------------------------


def test_b2_help_exits_zero_with_help_on_stdout_and_empty_stderr():
    proc = spawn(["--help"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith(b"usage: radar"), proc.stdout[:80]
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n"), (
        f"help must end in exactly one newline: {proc.stdout[-8:]!r}"
    )
    assert proc.stderr == b"", proc.stderr


def test_b2_help_in_process_exits_zero_on_stdout_only():
    code, out, err = capture(["--help"])
    assert code == 0
    assert out.startswith("usage: radar")
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert err == ""


def test_b2_version_exits_zero_with_the_version_on_stdout_and_empty_stderr():
    proc = spawn(["--version"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == VERSION_BYTES, proc.stdout
    assert proc.stderr == b"", proc.stderr


# --------------------------------------------------------------------------------------
# Behavior 3 -- byte control: eight verbs identical to the pre-change tree
# --------------------------------------------------------------------------------------


def first_gap_id():
    """The first gap id ``list .`` prints today, read from the working tree."""
    proc = spawn(["list", "."])
    assert proc.returncode == 0, proc.stderr
    match = re.search(rb"GAP-\d{3}", proc.stdout)
    assert match, f"`list .` printed no GAP-NNN id: {proc.stdout[:200]!r}"
    return match.group(0).decode("ascii")


def resolve(argv):
    return [first_gap_id() if token == "<first-id>" else token for token in argv]


@pytest.fixture(scope="module")
def prechange_src(tmp_path_factory):
    """``git archive PRECHANGE_COMMIT src`` extracted under a module-scoped tmp dir,
    plus a probe that the archived package is what ``PYTHONPATH`` makes importable."""
    root = tmp_path_factory.mktemp("prechange")
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", PRECHANGE_COMMIT, "src"],
        capture_output=True,
    )
    assert archive.returncode == 0, (
        f"`git archive {PRECHANGE_COMMIT} src` failed: {archive.stderr.decode('utf-8', 'replace')}"
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(root, filter="data")
    src = root / "src"
    env = prechange_env(src)
    probe = subprocess.run(
        [sys.executable, "-c", "import agent_gap_radar; print(agent_gap_radar.__file__)"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip().startswith(str(src)), (
        "the control arm did not import the archived package; PYTHONPATH lost to the "
        f"installed one: {probe.stdout!r}"
    )
    return src


def prechange_env(src):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    return env


@pytest.mark.parametrize("label", list(BYTE_CONTROL_VERBS), ids=list(BYTE_CONTROL_VERBS))
def test_b3_verb_stdout_and_exit_code_are_byte_identical_to_the_prechange_tree(
    label, prechange_src
):
    argv = resolve(BYTE_CONTROL_VERBS[label])
    now = spawn(argv)
    before = spawn(argv, env=prechange_env(prechange_src))
    assert now.returncode == before.returncode, (
        f"{label}: exit code moved {before.returncode} -> {now.returncode}; "
        f"stderr now={now.stderr[:300]!r}"
    )
    assert now.stdout == before.stdout, (
        f"{label}: stdout moved ({len(before.stdout)} -> {len(now.stdout)} bytes)"
    )


def test_b3_the_prechange_tree_exited_zero_on_bare_radar_and_the_tree_now_refuses(
    prechange_src,
):
    """Two-sided: the control arm is proven to be the OLD behaviour, not a copy of today's."""
    before = spawn([], env=prechange_env(prechange_src))
    now = spawn([])
    assert before.returncode == 0, f"pre-change bare radar did not exit 0: {before.stderr!r}"
    assert before.stdout.startswith(b"usage: radar"), before.stdout[:80]
    assert now.returncode == 2 and now.stdout == b""


def test_b3_register_doc_checker_still_passes():
    proc = subprocess.run(
        [sys.executable, "tools/check_register_doc.py"],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"tools/check_register_doc.py exited {proc.returncode}: "
        f"{proc.stdout.decode('utf-8', 'replace')}{proc.stderr.decode('utf-8', 'replace')}"
    )


# --------------------------------------------------------------------------------------
# Behavior 4 -- the contract's code-2 cell names the missing verb
# --------------------------------------------------------------------------------------


def exit_code_table_rows():
    """``## Exit codes`` rows as ``{code_int: (when_cell, consumer_cell)}``."""
    lines = CONTRACT.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Exit codes")
    rows = {}
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        match = re.fullmatch(r"`(\d+)`", cells[0])
        if match:
            rows[int(match.group(1))] = (cells[1], cells[2])
    return rows


def test_b4_code_two_when_cell_names_the_missing_verb_door():
    when, _consumer = exit_code_table_rows()[2]
    assert "missing verb" in when, f"the code-2 cell does not name the missing verb: {when!r}"
    assert re.search(r"bare `radar`", when), (
        f"the code-2 cell does not name bare `radar` as the door: {when!r}"
    )


def test_b4_code_two_when_cell_keeps_every_token_iteration_109_reads():
    when, consumer = exit_code_table_rows()[2]
    assert "LAST" in when, when
    assert "`" + ERROR_PREFIX + "`" in when, when
    assert re.search(r"(?i)not promised as a single line", when), when
    assert "`usage:`" in when and "ABOVE" in when, when
    assert "last" in consumer.lower(), consumer


def test_b4_the_table_still_equals_cli_exit_codes_in_both_directions():
    assert set(exit_code_table_rows()) == set(cli.EXIT_CODES)


# --------------------------------------------------------------------------------------
# Behavior 5 -- the four old-behaviour pins are re-baselined in place, not deleted
# --------------------------------------------------------------------------------------

OLD_NAMES = {
    "test_cli.py": "test_no_command_prints_help_and_exits_zero",
    "test_iter16_behavior.py": "test_behavior10_help_and_bare_invocation_still_exit_zero",
    "test_iter109_behavior.py": "test_b4_bare_radar_still_exits_zero_and_is_out_of_scope",
    "test_iter111_behavior.py": "test_behavior_5_bare_radar_writes_usage_help_to_stdout",
}

#: A re-baselined name must state the NEW contract: a refusal / exit two, and never the
#: old one (help on stdout, exit zero).
NEW_CONTRACT_WORDS = re.compile(r"refus|exit(?:s)?_two|two\b")
#: Matched against the part of the name AFTER `bare`/`no_command`, so `--help`'s own
#: still-exits-zero clause in the same name does not count against it.
OLD_CONTRACT_WORDS = re.compile(r"exits?_zero|prints_help|help_to_stdout|still_exit")


def collect_test_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


@pytest.mark.parametrize("module", sorted(OLD_NAMES), ids=sorted(OLD_NAMES))
def test_b5_old_pin_is_replaced_by_a_name_stating_the_new_contract(module):
    names = collect_test_names(TESTS / module)
    old = OLD_NAMES[module]
    assert old not in names, f"{module} still carries the old-behaviour pin {old!r}"
    stem = re.match(r"(test_(?:no_command|behavior10|b4|behavior_5)).*", old).group(1)
    bare_names = [
        name for name in names
        if name.startswith(stem) and ("bare" in name or "no_command" in name)
    ]
    assert bare_names, f"{module}: no {stem}* test about the bare invocation remains: {names}"
    assert any(NEW_CONTRACT_WORDS.search(name) for name in bare_names), (
        f"{module}: the bare-invocation pin does not state the new contract: {bare_names}"
    )
    tails = [re.split(r"bare|no_command", name, maxsplit=1)[1] for name in bare_names]
    assert not any(OLD_CONTRACT_WORDS.search(tail) for tail in tails), (
        f"{module}: a bare-invocation pin still states the old contract: {bare_names}"
    )


def no_document_cases():
    """``NO_DOCUMENT_CASES`` from ``test_iter111_behavior.py``, extracted mechanically."""
    tree = ast.parse((TESTS / "test_iter111_behavior.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "NO_DOCUMENT_CASES" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("NO_DOCUMENT_CASES not found in test_iter111_behavior.py")


def test_b5_iter111_bare_case_is_code_two_and_therefore_in_the_refusal_sweep():
    cases = no_document_cases()
    bare = [case for case in cases if case[0] == "bare"]
    assert bare == [("bare", [], 2)], f"the bare case was not re-baselined to 2: {bare!r}"
    refusals = [case for case in cases if case[2] == 2]
    assert ("bare", [], 2) in refusals


@pytest.mark.parametrize("module", sorted(OLD_NAMES), ids=sorted(OLD_NAMES))
def test_b5_re_baselined_module_keeps_at_least_the_prechange_test_count(module):
    """Re-baselined IN PLACE, not deleted: no module lost a test against the pre-change tree."""
    shown = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{PRECHANGE_COMMIT}:tests/{module}"],
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, shown.stderr
    before = [
        node.name for node in ast.parse(shown.stdout).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    now = collect_test_names(TESTS / module)
    assert len(now) >= len(before), (
        f"{module}: {len(before)} tests at {PRECHANGE_COMMIT}, {len(now)} now -- "
        f"missing: {sorted(set(before) - set(now))}"
    )


# --------------------------------------------------------------------------------------
# Behavior 6 -- the refusal path constructs no pydantic model
# --------------------------------------------------------------------------------------

CENSUS_CHILD = r"""
import json, sys
from agent_gap_radar import cli
code = None
try:
    code = cli.main([])
except SystemExit as exc:
    code = exc.code
loaded = sorted(name for name in sys.modules if name == "pydantic" or name.startswith("pydantic."))
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump({"code": code, "pydantic": loaded}, handle)
"""


def test_b6_bare_refusal_loads_no_pydantic_module(tmp_path):
    census = tmp_path / "census.json"
    proc = subprocess.run(
        [sys.executable, "-c", CENSUS_CHILD, str(census)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert census.exists(), f"child did not write its census: {proc.stderr!r}"
    data = json.loads(census.read_text(encoding="utf-8"))
    assert data["code"] == 2, data
    assert data["pydantic"] == [], (
        f"the bare refusal loaded pydantic before answering: {data['pydantic']}"
    )
    assert proc.stdout == b"", proc.stdout
    assert nonempty_lines(proc.stderr.decode("utf-8"))[-1] == REQUIRED_VERB_LINE


# --------------------------------------------------------------------------------------
# Retry-round extensions (same spec, same behaviors; grouped by behavior number)
# --------------------------------------------------------------------------------------

#: Spec "Why": the bare door joins the structural refusals the CLI already has. Two of
#: them are named there and reproduced here as siblings: an unknown verb and a verb
#: missing its positional.
SIBLING_DOORS = {
    "unknown-verb": ["bogus"],
    "show-missing-gap-id": ["show"],
}


def refusal_shape(proc):
    """``(exit, stdout_bytes, first_usage_line, last_line)`` of a refusal, for comparison."""
    lines = nonempty_lines(proc.stderr.decode("utf-8"))
    return proc.returncode, len(proc.stdout), lines[0] if lines else None, lines[-1] if lines else None


@pytest.mark.parametrize("label", sorted(SIBLING_DOORS), ids=sorted(SIBLING_DOORS))
def test_b1_bare_radar_has_the_same_refusal_shape_as_its_sibling_doors(label):
    """Exit 2, zero stdout bytes, a ``usage:`` first line, one ``Error: `` last line -- the
    same envelope the pre-existing refusals publish."""
    bare = refusal_shape(spawn([]))
    sibling = refusal_shape(spawn(SIBLING_DOORS[label]))
    assert bare[0] == sibling[0] == 2, (bare, sibling)
    assert bare[1] == sibling[1] == 0, (bare, sibling)
    assert bare[2] is not None and bare[2].startswith("usage: radar"), bare
    assert sibling[2] is not None and sibling[2].startswith("usage: radar"), sibling
    assert bare[3].startswith(ERROR_PREFIX) and sibling[3].startswith(ERROR_PREFIX), (bare, sibling)


def test_b1_bare_radar_and_show_without_gap_id_share_the_argparse_sentence_shape():
    """Spec behavior 1: the sentence is the one ``radar show`` already emits for ``gap_id``;
    the two differ only in the name of the missing argument."""
    bare_last = nonempty_lines(spawn([]).stderr.decode("utf-8"))[-1]
    show_last = nonempty_lines(spawn(["show"]).stderr.decode("utf-8"))[-1]
    template = re.compile(r"^Error: the following arguments are required: (\S+)$")
    bare_match, show_match = template.match(bare_last), template.match(show_last)
    assert bare_match, bare_last
    assert show_match, show_last
    assert bare_match.group(1) == "command"
    assert show_match.group(1) == "gap_id"


def test_b1_unknown_verb_refusal_is_unmoved_by_the_change():
    """Adding the missing-verb door must not re-route the unknown-verb door: it still names
    the offending token and lists the verbs, exit 2, empty stdout."""
    proc = spawn(["bogus"])
    assert proc.returncode == 2
    assert proc.stdout == b""
    last = nonempty_lines(proc.stderr.decode("utf-8"))[-1]
    assert last.startswith(ERROR_PREFIX), last
    assert "'bogus'" in last and "invalid choice" in last, last


@pytest.mark.parametrize(
    "label,argv",
    [("unquoted-empty-var", []), ("quoted-empty-var", [""])],
    ids=["unquoted-empty-var", "quoted-empty-var"],
)
def test_b1_ci_step_with_an_empty_verb_variable_can_no_longer_read_a_silent_success(label, argv):
    """Spec "Why": ``radar $VERB`` with an empty variable. Unquoted, the shell passes no token
    (bare); quoted, it passes one empty token. Neither may exit 0 with usage as its document."""
    proc = spawn(argv)
    assert proc.returncode == 2, f"{label}: exit {proc.returncode}, stderr={proc.stderr!r}"
    assert proc.stdout == b"", f"{label}: stdout carried {len(proc.stdout)} bytes"
    lines = nonempty_lines(proc.stderr.decode("utf-8"))
    assert lines and lines[0].startswith("usage: radar"), lines[:1]
    assert lines[-1].startswith(ERROR_PREFIX), lines[-1]


def test_b1_bare_refusal_stderr_is_byte_deterministic_across_runs():
    """Two independent child processes publish identical refusal bytes."""
    first, second = spawn([]), spawn([])
    assert first.returncode == second.returncode == 2
    assert first.stderr == second.stderr
    assert first.stdout == second.stdout == b""


def test_b2_version_in_process_exits_zero_with_only_the_version_on_stdout():
    code, out, err = capture(["--version"])
    assert code == 0
    assert out == VERSION_BYTES.decode("ascii"), out
    assert err == ""


def test_b2_short_help_flag_still_exits_zero_on_stdout_only():
    proc = spawn(["-h"])
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith(b"usage: radar"), proc.stdout[:80]
    assert proc.stderr == b"", proc.stderr


def test_b2_help_bytes_are_identical_to_the_prechange_tree(prechange_src):
    """Spec Out-of-Scope: ``--help`` / ``--version`` channels AND bytes are untouched."""
    for argv in (["--help"], ["--version"]):
        now = spawn(argv)
        before = spawn(argv, env=prechange_env(prechange_src))
        assert now.returncode == before.returncode == 0, argv
        assert now.stdout == before.stdout, f"{argv}: stdout bytes moved"
        assert now.stderr == before.stderr == b"", argv


STAGED_CENSUS_CHILD = r"""
import json, sys
result = {"stage": "imported", "code": None}
from agent_gap_radar import cli
try:
    result["code"] = cli.main([])
except SystemExit as exc:
    result["code"] = exc.code
result["stage"] = "dispatched"
result["pydantic"] = "pydantic" in sys.modules
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(result, handle)
"""


def test_b6_bare_refusal_reaches_the_dispatched_stage_pydantic_free(tmp_path):
    """Spec behavior 6 in iteration 111's own terms: ``stage == "dispatched"`` and no
    pydantic in ``sys.modules`` once ``cli.main([])`` has answered."""
    census = tmp_path / "staged-census.json"
    proc = subprocess.run(
        [sys.executable, "-c", STAGED_CENSUS_CHILD, str(census)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert census.exists(), f"child died before writing its census: {proc.stderr!r}"
    data = json.loads(census.read_text(encoding="utf-8"))
    assert data["stage"] == "dispatched", data
    assert data["code"] == 2, data
    assert data["pydantic"] is False, "the bare refusal paid for pydantic"


# --------------------------------------------------------------------------------------
# Behavior 5, fifth site -- SPEC OMISSION found by the full suite (retry round)
# --------------------------------------------------------------------------------------
#
# Spec behavior 5 enumerates four committed pins of the old behaviour. The full suite at
# this round found a FIFTH: ``tests/test_iter25_behavior.py`` enrols ``[]`` in its
# ``_argvs()`` SUCCESS-path table ("the implicit help write argparse does for itself"),
# which drives four parametrized ``<no args>`` nodes (b1 closed-reader 141, b2 silent
# stderr, b4 no ``Error: ``, b7 exit 0) plus the named
# ``test_b7_no_arguments_still_prints_help_and_exits_0``. The spec's rule for the four
# ("re-baselined in place, not deleted; keeps its name or gains a name stating the new
# contract") is applied here to the fifth under the same reading.

FIFTH_SITE = "test_iter25_behavior.py"
FIFTH_OLD_NAME = "test_b7_no_arguments_still_prints_help_and_exits_0"
BARE_TOKENS = re.compile(r"bare|no_command|no_arg")


def test_b5_iter25_no_arguments_pin_is_re_baselined_to_the_refusal_contract():
    names = collect_test_names(TESTS / FIFTH_SITE)
    assert FIFTH_OLD_NAME not in names, (
        f"{FIFTH_SITE} still pins bare `radar` at exit 0 via {FIFTH_OLD_NAME!r}"
    )
    bare_names = [n for n in names if n.startswith("test_b7") and BARE_TOKENS.search(n)]
    assert bare_names, f"{FIFTH_SITE}: no test_b7* pin about the bare invocation remains: {names}"
    assert any(NEW_CONTRACT_WORDS.search(n) for n in bare_names), bare_names
    tails = [BARE_TOKENS.split(n, maxsplit=1)[1] for n in bare_names]
    assert not any(OLD_CONTRACT_WORDS.search(t) for t in tails), bare_names


def test_b5_iter25_success_path_table_no_longer_enrols_the_bare_invocation():
    """``[]`` cannot sit in a table whose every row must exit 0 with a document."""
    tree = ast.parse((TESTS / FIFTH_SITE).read_text(encoding="utf-8"))
    argvs_fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_argvs"
    )
    empty_lists = [
        node for node in ast.walk(argvs_fn)
        if isinstance(node, ast.List) and not node.elts
    ]
    assert not empty_lists, (
        f"{FIFTH_SITE}::_argvs() still enrols the bare invocation ([]) as a success path"
    )


def test_b5_iter25_module_keeps_at_least_the_prechange_test_count():
    shown = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{PRECHANGE_COMMIT}:tests/{FIFTH_SITE}"],
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, shown.stderr
    before = [
        node.name for node in ast.parse(shown.stdout).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    now = collect_test_names(TESTS / FIFTH_SITE)
    assert len(now) >= len(before), sorted(set(before) - set(now))


# --------------------------------------------------------------------------------------
# Iteration 264 additions -- behavior 4's code-0 clause and behavior 5's five-site sweep
# --------------------------------------------------------------------------------------


def test_b4_code_zero_when_cell_keeps_its_sentence_and_gains_the_help_clause():
    """Spec behavior 4 (iteration 264): the code-0 row keeps ``the verb produced its
    document`` and gains a clause carrying the token ``--help``, so a usage block on
    stdout under exit 0 can only ever be the help the caller asked for."""
    rows = exit_code_table_rows()
    assert 0 in rows, f"no three-cell code-0 row in the table: {sorted(rows)}"
    when, consumer = rows[0]
    assert "produced its document" in when, when
    assert "`--help`" in when, f"the code-0 cell gained no `--help` clause: {when!r}"
    assert re.search(r"(?i)usage", when), f"the clause does not speak of usage text: {when!r}"
    assert "stdout" in consumer.lower(), consumer


def test_b4_code_zero_clause_is_true_of_the_tool():
    """The clause the row states must hold at the process boundary: ``--help`` is the ONLY
    argv of the bare/help pair that exits 0 with usage on stdout."""
    helped, bare = spawn(["--help"]), spawn([])
    assert helped.returncode == 0 and helped.stdout.startswith(b"usage: radar")
    assert bare.returncode == 2 and bare.stdout == b""


#: Spec behavior 5's sweep clause, applied to every module under ``tests/``: a test whose
#: NAME speaks of the bare invocation must not state the old contract after the pivot.
SWEEP_PIVOT = re.compile(r"bare_radar|bare_invocation|no_arguments|no_command|bare")


def test_b5_sweep_no_test_module_pins_bare_radar_as_a_success():
    offenders = []
    for path in sorted(TESTS.glob("test_*.py")):
        for name in collect_test_names(path):
            match = SWEEP_PIVOT.search(name)
            if not match:
                continue
            tail = name[match.end():]
            if OLD_CONTRACT_WORDS.search(tail):
                offenders.append(f"{path.name}::{name}")
    assert not offenders, f"bare-`radar` success pins survive the sweep: {offenders}"


def test_b5_sweep_all_five_named_pins_are_gone():
    """The spec names five old pins by module and function; none may remain anywhere."""
    gone = dict(OLD_NAMES)
    gone[FIFTH_SITE] = FIFTH_OLD_NAME
    survivors = [
        f"{module}::{name}"
        for module, name in gone.items()
        if name in collect_test_names(TESTS / module)
    ]
    assert not survivors, survivors


def test_b5_iter25_module_test_count_is_unchanged():
    """Spec behavior 5 (iteration 264): ``test_iter25`` re-baselines its pin under a new
    name and drops ``[]`` from ``_argvs()``; its module-level test-function count is
    UNCHANGED against the pre-change tree (not merely >=)."""
    shown = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{PRECHANGE_COMMIT}:tests/{FIFTH_SITE}"],
        capture_output=True,
        text=True,
    )
    assert shown.returncode == 0, shown.stderr
    before = [
        node.name for node in ast.parse(shown.stdout).body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    now = collect_test_names(TESTS / FIFTH_SITE)
    assert len(now) == len(before), (
        f"{FIFTH_SITE}: {len(before)} test functions at {PRECHANGE_COMMIT}, {len(now)} now"
    )


def test_b5_iter25_refusal_pin_drives_the_bare_door_and_asserts_the_refusal():
    """The re-baselined ``test_b7`` pin is a REFUSAL-shape test, not a renamed no-op: its
    source drives the bare invocation and asserts exit 2 / the ``Error: `` line."""
    tree = ast.parse((TESTS / FIFTH_SITE).read_text(encoding="utf-8"))
    pins = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_b7")
        and BARE_TOKENS.search(node.name)
    ]
    assert pins, "no test_b7 bare-invocation pin in test_iter25_behavior.py"
    source = "\n".join(ast.get_source_segment(
        (TESTS / FIFTH_SITE).read_text(encoding="utf-8"), pin) for pin in pins)
    assert re.search(r"_run\(\)|\[\]|main\(\)", source), (
        "the pin never drives the bare invocation (no argv tokens)"
    )
    assert re.search(r"==\s*2\b|EXIT_USAGE|exit.*2", source), (
        "the pin does not assert the exit-2 refusal"
    )
    assert "Error: " in source, "the pin does not read the `Error: ` line"
