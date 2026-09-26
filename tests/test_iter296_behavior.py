"""Iteration 296 (re-land of the iteration-295 tree) behavior tests (black-box; spec: state/iter-296/pm.md).

Feature: every long flag answers ONLY to its exact spelling. `PublishedErrorParser`
defaults `allow_abbrev=False`, so a strict prefix of any long flag (`--flo`, `--exit`,
`--ga`, `--he`) is the published structural refusal -- exit 2, 0 B stdout, last stderr
line `Error: unrecognized arguments: ...` -- on all 8 verbs and on the `tools/` parsers
that reuse the class. Exact spellings and every emitted document are byte-identical to
the commit before this iteration.

ISOLATION CONTRACT HONORED: nothing here read `src/`, `tools/`, the engineer's or
reviewer's notes, or a diff of any source file. Expectations come from `pm.md`; shapes
were measured by RUNNING the tool and by reading files under `tests/` and the published
`docs/CONSUMER_CONTRACT.md`. The pre-change control arm is the product itself at the
commit before this iteration, extracted with `git archive` and EXECUTED, never read.

Behavior 1 derives its inventory from `build_parser()` through the same oracle
`tests/_surface_contract.py` uses (`parser_surface()`), so a flag added later is covered
by construction rather than by someone remembering to extend a hand list. The census
below (behavior 8) reads `tests/*.py` as TEXT, which the contract names as readable.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile

import pytest

from _surface_contract import parser_surface
from agent_gap_radar.cli import PublishedErrorParser, build_parser

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The commit immediately before this iteration's change (control arm).
PRECHANGE_COMMIT = "3eea489"

UNRECOGNIZED = "Error: unrecognized arguments: "
MISSING_COMMAND = "Error: the following arguments are required: command"

#: A dummy value token for a value-taking flag's prefix. Not a number that argparse could
#: read as a negative-number-looking option, not a path the verb could accept early.
DUMMY = "3"

#: Valid positionals per verb, read off each verb's `usage:` line (`radar <verb> --help`).
POSITIONALS: dict[str, tuple[str, ...]] = {
    "list": (".",),
    "report": (".",),
    "prd": (".",),
    "scan": (".",),
    "diff": ("gaps", "gaps"),
    "validate": (".",),
    "show": ("GAP-001", "."),
    "taxonomy": (),
}

#: One live value of the closed layer vocabulary, as `list --layer zzz` names it.
LIVE_LAYER = "orchestration"


def _radar(*argv: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        cwd=str(REPO_ROOT), capture_output=True, env=env)


def _tail(stderr: bytes) -> str:
    lines = [ln for ln in stderr.decode("utf-8").splitlines() if ln.strip()]
    assert lines, "stderr carried no non-empty line"
    return lines[-1]


def _assert_structural_refusal(proc: subprocess.CompletedProcess, tokens: str) -> None:
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert proc.stdout == b"", proc.stdout
    assert _tail(proc.stderr) == UNRECOGNIZED + tokens, repr(proc.stderr)


def _verb_subparsers() -> dict[str, argparse.ArgumentParser]:
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("build_parser() registers no subcommands")


# --------------------------------------------------------------------------------------
# Behavior 1 -- every strict prefix of every long flag, on every verb, derived from the
# parser: exit 2, 0 B stdout, `Error: unrecognized arguments: <P>[ <value>]`
# --------------------------------------------------------------------------------------

def _prefix_cases() -> list[tuple[str, str, bool]]:
    """(verb, prefix, takes_value) for every strict prefix of every long flag.

    `parser_surface()` already drops `-h`/`--help` (behavior 2 covers those) and reports
    whether each option consumes a value. A prefix that is ITSELF an exact option of the
    verb (`scan --gap` under `--gaps`) is not a refusal case and is excluded here.
    """
    cases: dict[tuple[str, str], bool] = {}
    for verb, surface in parser_surface().items():
        exact = set(surface.options)
        long_flags = sorted(o for o in exact if o.startswith("--"))
        for flag in long_flags:
            for length in range(3, len(flag)):
                prefix = flag[:length]
                if prefix in exact:
                    continue
                cases[(verb, prefix)] = cases.get((verb, prefix), False) or bool(
                    surface.takes_value[flag])
    return [(verb, prefix, takes) for (verb, prefix), takes in sorted(cases.items())]


PREFIX_CASES = _prefix_cases()


def test_iter296_b1_the_derived_inventory_is_the_spec_s_sixteen_flags() -> None:
    """The oracle sees what the spec hand-listed at the pre-change commit."""
    per_verb = {verb: sorted(o for o in s.options if o.startswith("--"))
                for verb, s in parser_surface().items()}
    assert per_verb == {
        "list": ["--floor", "--json", "--layer"],
        "report": ["--floor"],
        "prd": ["--floor", "--gap", "--project", "--with-fixtures"],
        "scan": ["--exit-code", "--floor", "--gap", "--gaps", "--json", "--prd"],
        "diff": ["--exit-code", "--json"],
        "validate": [], "show": [], "taxonomy": [],
    }
    assert sum(len(v) for v in per_verb.values()) == 16
    assert len(PREFIX_CASES) >= 60, len(PREFIX_CASES)
    # The exclusion rule, by construction: `--gap` is exact on `scan`, so it is not a case.
    assert ("scan", "--gap") not in {(v, p) for v, p, _ in PREFIX_CASES}
    assert ("scan", "--ga") in {(v, p) for v, p, _ in PREFIX_CASES}


@pytest.mark.parametrize(
    ("verb", "prefix", "takes_value"), PREFIX_CASES,
    ids=[f"{verb}:{prefix}" for verb, prefix, _ in PREFIX_CASES])
def test_iter296_b1_every_strict_prefix_is_a_structural_refusal(
        verb: str, prefix: str, takes_value: bool) -> None:
    argv = [verb, *POSITIONALS[verb], prefix]
    tokens = prefix
    if takes_value:
        argv.append(DUMMY)
        tokens = f"{prefix} {DUMMY}"
    _assert_structural_refusal(_radar(*argv), tokens)


def test_iter296_b1_prd_flo_3_is_a_structural_refusal_naming_both_tokens() -> None:
    """The spec's own worked example, spelled out so a reader sees the shape once."""
    _assert_structural_refusal(_radar("prd", ".", "--flo", "3"), "--flo 3")


def test_iter296_b1_scan_exit_no_longer_runs_the_ci_gate() -> None:
    """At the pre-change commit `scan . --exit` RAN the gate; now it is refused."""
    _assert_structural_refusal(_radar("scan", ".", "--exit"), "--exit")


@pytest.mark.parametrize(
    ("argv", "tokens"),
    [(("prd", ".", "--flo=3"), "--flo=3"),
     (("list", ".", "--lay=" + LIVE_LAYER), "--lay=" + LIVE_LAYER)],
    ids=["prd:--flo=3", "list:--lay=<layer>"])
def test_iter296_b1_the_equals_form_of_a_prefix_is_refused_as_one_token(
        argv: tuple[str, ...], tokens: str) -> None:
    """`--flo=3` is one token, so the refusal names it whole (no split at `=`)."""
    _assert_structural_refusal(_radar(*argv), tokens)


@pytest.mark.parametrize(
    ("argv", "tokens"),
    [(("list", ".", "--json", "--flo", "2"), "--flo 2"),
     (("scan", ".", "--gaps", "gaps", "--exit"), "--exit"),
     (("scan", ".", "--gaps", "gaps", "--json", "--flo", "2"), "--flo 2")],
    ids=["list --json then --flo 2", "scan --gaps gaps then --exit",
         "scan --gaps gaps --json then --flo 2"])
def test_iter296_b1_a_prefix_after_an_exact_flag_is_still_refused_naming_only_itself(
        argv: tuple[str, ...], tokens: str) -> None:
    """An exact flag earlier on the line parses; only the prefix tokens are unrecognized."""
    _assert_structural_refusal(_radar(*argv), tokens)


# --------------------------------------------------------------------------------------
# Behavior 2 -- prefixes of `--help` refuse the same way; `-h`/`--help` still help
# --------------------------------------------------------------------------------------

VERBS = tuple(POSITIONALS)


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("prefix", ["--h", "--he", "--hel"])
def test_iter296_b2_help_prefix_is_refused_on_every_verb(verb: str, prefix: str) -> None:
    _assert_structural_refusal(_radar(verb, *POSITIONALS[verb], prefix), prefix)


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("spelling", ["-h", "--help"])
def test_iter296_b2_exact_help_still_prints_help_and_exits_0(verb: str, spelling: str) -> None:
    proc = _radar(verb, spelling)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith(f"usage: radar {verb}".encode("utf-8")), proc.stdout[:80]
    assert proc.stderr == b"", proc.stderr


# --------------------------------------------------------------------------------------
# Behavior 3 -- exact spellings are byte-identical to the pre-change commit (two trees,
# ONE target: both emitters read the same working tree, so locators agree)
# --------------------------------------------------------------------------------------

def _env(src: pathlib.Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    return env


@pytest.fixture(scope="module")
def prechange_src(tmp_path_factory) -> pathlib.Path:
    """`git archive PRECHANGE_COMMIT src` under a tmp dir, probed to be what is imported."""
    root = tmp_path_factory.mktemp("prechange296")
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


def test_iter296_b3_the_control_arm_is_really_the_pre_change_build(prechange_src) -> None:
    """At the pre-change commit `prd . --flo 3` was a working alias of `--floor 3`."""
    old = _radar("prd", ".", "--flo", "3", env=_env(prechange_src))
    assert old.returncode == 0, old.stderr
    assert old.stdout == _radar("prd", ".", "--floor", "3", env=_env(prechange_src)).stdout
    # and the working tree refuses the same tokens
    _assert_structural_refusal(_radar("prd", ".", "--flo", "3"), "--flo 3")


CONTROL_CASES = (
    ("list", ".", "--floor", "2", "--json"),
    ("list", ".", "--layer", LIVE_LAYER),
    ("report", ".", "--floor", "2"),
    ("prd", ".", "--gap", "GAP-003", "--floor", "2", "--project", "agent-gap-radar"),
    ("prd", ".", "--gap", "GAP-003", "--with-fixtures"),
    ("scan", ".", "--gaps", "gaps", "--json"),
    ("scan", ".", "--gaps", "gaps", "--floor", "2"),
    ("diff", "gaps", "gaps", "--json"),
    # verbs with NO long flags: the change must not have touched their documents either
    ("taxonomy",),
    ("validate", "."),
    ("show", "GAP-001", "."),
)


@pytest.mark.parametrize("argv", CONTROL_CASES, ids=[" ".join(c) for c in CONTROL_CASES])
def test_iter296_b3_exact_spelling_is_byte_identical_to_the_pre_change_commit(
        argv: tuple[str, ...], prechange_src) -> None:
    new = _radar(*argv)
    old = _radar(*argv, env=_env(prechange_src))
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)
    assert new.stdout.endswith(b"\n") and not new.stdout.endswith(b"\n\n"), new.stdout[-3:]


def test_iter296_b3_the_equals_form_still_parses_and_matches_the_space_form() -> None:
    equals = _radar("prd", ".", "--floor=2", "--gap", "GAP-003")
    space = _radar("prd", ".", "--floor", "2", "--gap", "GAP-003")
    assert equals.returncode == 0, equals.stderr
    assert (equals.returncode, equals.stdout) == (space.returncode, space.stdout)
    assert equals.stdout != b""


# --------------------------------------------------------------------------------------
# Behavior 4 -- `scan`'s `--gap`/`--gaps` pair keeps both exact meanings
# --------------------------------------------------------------------------------------

def test_iter296_b4_scan_gap_and_gaps_keep_both_exact_meanings(prechange_src) -> None:
    argv = ("scan", ".", "--gaps", "gaps", "--gap", "GAP-003", "--json")
    new = _radar(*argv)
    old = _radar(*argv, env=_env(prechange_src))
    assert new.returncode == old.returncode, new.stderr
    assert new.stdout == old.stdout
    payload = json.loads(new.stdout.decode("utf-8"))
    assert payload["records_applied"] == 1


# --------------------------------------------------------------------------------------
# Behavior 5 -- spelled once and inherited; a caller's explicit True is honoured
# --------------------------------------------------------------------------------------

def test_iter296_b5_the_class_defaults_allow_abbrev_false() -> None:
    assert PublishedErrorParser(prog="x").allow_abbrev is False


def test_iter296_b5_every_subparser_inherits_allow_abbrev_false() -> None:
    subparsers = _verb_subparsers()
    assert set(subparsers) == set(VERBS)
    assert build_parser().allow_abbrev is False
    for verb, sub in subparsers.items():
        assert sub.allow_abbrev is False, verb


def test_iter296_b5_an_explicit_true_is_honoured_because_it_is_a_default() -> None:
    assert PublishedErrorParser(prog="x", allow_abbrev=True).allow_abbrev is True


def test_iter296_b5_a_tools_parser_reports_false_and_refuses_its_own_prefix(tmp_path) -> None:
    """`tools/promote.py` imports the same class; its own long flags refuse prefixes."""
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import promote  # noqa: PLC0415 -- the tool is a script, imported the way its tests do
    finally:
        sys.path.pop(0)
    assert promote.PublishedErrorParser is PublishedErrorParser
    assert promote.PublishedErrorParser(prog="promote").allow_abbrev is False
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for prefix, tokens in (("--lim", f"--lim {DUMMY}"), ("--app", "--app")):
        argv = [sys.executable, str(REPO_ROOT / "tools" / "promote.py"),
                "--inbox", str(inbox), prefix]
        if prefix == "--lim":
            argv.append(DUMMY)
        proc = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True)
        _assert_structural_refusal(proc, tokens)


#: (script, argv, refused tokens) -- one strict prefix of one of the script's OWN long
#: flags, as `tools/<script> --help` lists them. `{inbox}` is a tmp dir the test creates.
TOOL_PREFIX_CASES = (
    ("check_register_doc.py", ("--fil", "README.md"), "--fil README.md"),
    ("scan_cost.py", ("--tar", "."), "--tar ."),
    ("scan_cost.py", ("--gaps", "gaps", "--jso"), "--jso"),
    ("verify_mutations.py", ("--lis",), "--lis"),
    ("verify_mutations.py", ("--onl", "x"), "--onl x"),
    ("verify_quotes.py", ("--gaps", "gaps", "--wor", "1"), "--wor 1"),
    ("verify_quotes.py", ("--gaps", "gaps", "--verif"), "--verif"),
    ("promote.py", ("--inbox", "{inbox}", "--reg", "5"), "--reg 5"),
)

TOOL_SCRIPTS = tuple(sorted({script for script, _, _ in TOOL_PREFIX_CASES}))


def _tool(script: str, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / script), *argv],
        cwd=str(REPO_ROOT), capture_output=True)


@pytest.mark.parametrize(
    ("script", "argv", "tokens"), TOOL_PREFIX_CASES,
    ids=[f"{s}:{tokens.split()[0]}" for s, _, tokens in TOOL_PREFIX_CASES])
def test_iter296_b5_every_argparse_tool_refuses_a_prefix_of_its_own_flag(
        script: str, argv: tuple[str, ...], tokens: str, tmp_path) -> None:
    """The spec names 5 `tools/` parsers on the class; each refuses its own prefixes."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    argv = tuple(str(inbox) if a == "{inbox}" else a for a in argv)
    _assert_structural_refusal(_tool(script, *argv), tokens)


@pytest.mark.parametrize("script", TOOL_SCRIPTS)
def test_iter296_b5_every_argparse_tool_still_answers_exact_help(script: str) -> None:
    proc = _tool(script, "--help")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith(f"usage: {script}".encode("utf-8")), proc.stdout[:60]
    assert proc.stderr == b"", proc.stderr


def test_iter296_b5_the_tool_inventory_is_the_five_parsers_the_spec_names() -> None:
    assert TOOL_SCRIPTS == (
        "check_register_doc.py", "promote.py", "scan_cost.py",
        "verify_mutations.py", "verify_quotes.py")
    for script in TOOL_SCRIPTS:
        assert (REPO_ROOT / "tools" / script).is_file(), script


# --------------------------------------------------------------------------------------
# Behavior 6 -- top level unchanged: bare `radar` and `radar --he` want a command first
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [(), ("--he",), ("--hel",)], ids=["bare", "--he", "--hel"])
def test_iter296_b6_top_level_refusal_still_names_the_missing_command(
        argv: tuple[str, ...]) -> None:
    proc = _radar(*argv)
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert _tail(proc.stderr) == MISSING_COMMAND, repr(proc.stderr)


# --------------------------------------------------------------------------------------
# Behavior 7 (record) -- the one named pin was re-baselined in place, not deleted
# --------------------------------------------------------------------------------------

def test_iter296_b7_the_iter120_pin_now_asserts_the_exact_new_line() -> None:
    text = (TESTS / "test_iter120_behavior.py").read_text(encoding="utf-8")
    assert "def test_b6_the_now_ambiguous_short_abbreviation_fails_loudly_too" in text
    assert '"Error: unrecognized arguments: --ga ./"' in text
    asserting_ambiguous = [ln for ln in text.splitlines()
                           if ln.lstrip().startswith("assert") and "ambiguous" in ln]
    assert asserting_ambiguous == [], asserting_ambiguous


# --------------------------------------------------------------------------------------
# Behavior 8 -- no test keeps an abbreviation alive; the contract publishes the rule
# --------------------------------------------------------------------------------------

def test_iter296_b8_no_test_spells_a_live_prefix_except_as_a_refusal_probe() -> None:
    """Every `--xyz` literal under tests/ that is a strict prefix of a live flag sits in a
    module that treats it as a refusal (`unrecognized arguments`), never as an alias."""
    live = {o for s in parser_surface().values() for o in s.options if o.startswith("--")}
    live.add("--help")
    offenders: list[tuple[str, str]] = []
    for path in sorted(TESTS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        literals = set(re.findall(r'["\'](--[a-z][a-z-]*)["\']', text))
        prefixes = {lit for lit in literals
                    if lit not in live and len(lit) >= 3
                    and any(flag.startswith(lit) for flag in live)}
        if prefixes and "unrecognized arguments" not in text:
            offenders.extend((path.name, lit) for lit in sorted(prefixes))
    assert offenders == [], offenders


def test_iter296_b8_the_contract_publishes_the_prefix_refusal() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "strict prefix of a long flag" in text
    assert "`Error: unrecognized arguments: ...`" in text
    assert "exit 2" in text


# --------------------------------------------------------------------------------------
# Behavior 9 -- ONE added sentence, in the exit-2 row; README makes no claim about this
# --------------------------------------------------------------------------------------

def _exit_code_rows() -> dict[str, str]:
    """Table rows of the contract keyed by their first cell (`0`, `1`, `2`, ...)."""
    rows: dict[str, str] = {}
    for line in CONTRACT.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and re.fullmatch(r"`\d`", cells[0]):
            rows[cells[0].strip("`")] = line
    return rows


def test_iter296_b9_the_prefix_sentence_lives_once_and_in_the_exit_2_row() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert text.count("strict prefix of a long flag") == 1
    rows = _exit_code_rows()
    assert "2" in rows, sorted(rows)
    assert "strict prefix of a long flag" in rows["2"]
    assert "`Error: unrecognized arguments: ...`" in rows["2"]
    for code, row in rows.items():
        if code != "2":
            assert "strict prefix" not in row, code


def test_iter296_b9_the_exit_2_row_names_the_two_worked_prefixes_as_refusals() -> None:
    row = _exit_code_rows()["2"]
    for prefix, flag in (("--flo", "--floor"), ("--exit", "--exit-code")):
        assert f"`{prefix}` for `{flag}`" in row, (prefix, flag)
        # and the product agrees with its own contract, on the verb that owns the flag
        verb = "prd" if flag == "--floor" else "scan"
        argv = [verb, *POSITIONALS[verb], prefix]
        tokens = prefix
        if flag == "--floor":
            argv.append(DUMMY)
            tokens = f"{prefix} {DUMMY}"
        _assert_structural_refusal(_radar(*argv), tokens)


def test_iter296_b9_readme_makes_no_claim_about_abbreviations_or_prefixes() -> None:
    """The spec pins `rg -in 'abbrev|prefix' README.md` = 0: README is untouched because
    it never described this surface; the contract is the only place the rule is published."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert re.findall(r"abbrev|prefix", text, flags=re.IGNORECASE) == []
