"""Iteration 206 -- this repo's own `tools/` refuse in the PUBLISHED `Error: ` vocabulary.

BLACK-BOX. Every assertion here is either a `subprocess` run of a tracked script, an AST
read of a tracked file, or one in-process call of a name the spec makes PUBLIC. Nothing
imports a private helper, no `radar` verb runs, no register record is touched, and the only
files written are fixtures under `tmp_path`.

WHAT THE SPEC PROMISES, in one sentence: over one invocation a refusal has exit code 2,
exactly zero stdout bytes, and a last non-empty stderr line beginning `Error: ` followed by
at least one non-space character. `docs/CONSUMER_CONTRACT.md` and the quality bar both
publish that sentence; before this iteration four of the seven `tools/` scripts answered a
mistyped invocation in argparse's own `<prog>: error: ...` dialect instead, so a consumer
implementing the published sentence got an empty match. The table in `test_b2_b3_*` states
the promise ONCE for all seven scripts -- the four that changed and the three that already
kept it -- which is why it is one parametrized table and not two.

DESIGN NOTES a later reader should not have to re-derive.

* NON-VACUITY IS MEASURED, NOT ASSERTED. Two directions of control are carried here.
  (a) `test_b2_control_the_argparse_dialect_regex_still_discriminates` feeds the regex a
  synthetic argparse line and a synthetic published line and pins that it matches the first
  and not the second -- so a regex that had rotted into matching nothing could not make the
  seven-tool table pass by accident. (b) Both AST censuses (`error_prefix_sites` for
  behaviour 1, `bare_argument_parser_sites` for behaviour 6) are run over inline fixtures
  that must count 1, 0 and 0 respectively before the same function is trusted to report 0
  over the tracked tree. Absence of a finding is evidence only from a function shown to
  produce one -- the rule `tests/test_roadmap_integrity.py` states in its own docstring.

* THE `usage:` ORDERING IS THE ANTI-RIVAL. A tool that printed `Error: ...` and swallowed
  the usage block would satisfy behaviour 2 while destroying the only place a caller learns
  the arity it got wrong. Behaviour 4 pins usage present AND strictly above the error line,
  the same ordering iteration 109 fixed for `radar`.

* THE REGEX IS SHARED VOCABULARY, NOT A RE-WRITE. Iteration 109 committed
  `PROG_AWARE_ARGPARSE_SPELLING`. Importing one test module from another is not a convention
  in this suite, so the pattern is re-declared here AND
  `test_b2_the_argparse_dialect_regex_is_the_one_iteration_109_committed` asserts the
  declared pattern string still appears verbatim in `tests/test_iter109_behavior.py`. That
  keeps one definition of the dialect and doubles as a brake on the acceptance criterion
  that iteration 109's module is edited ZERO times.

AMBIGUITY NOTED FOR THE PM (behaviour 5). The spec asks that
`python tools/roadmap_integrity.py` exit 0 "with byte-identical stdout to the pre-change
tree". As written that is not satisfiable, and not because of any engineer regression: that
script COUNTS `PRODUCT.md`, and the same spec's acceptance criteria require the PM to add
two table rows and one Done-ledger row to that file, so the reported counts move from
`115 table row(s), 91 ledger row(s)` to `117 table row(s), 92 ledger row(s)` BY DESIGN.
Tested here in the reading that is measurable and that carries the spec's real intent ("no
tool's SUCCESS path moves"): exit 0, zero stderr bytes, stdout byte-identical ACROSS TWO
RUNS (the pin comes from the run, never from a copied literal), stdout ending in exactly one
newline, `0 violation(s)` reported, and the row counts in the output equal to counts this
test re-derives from `PRODUCT.md` itself -- so the numbers are anchored to the document
rather than frozen, and a future roadmap row cannot red this module while a broken counter
still does.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import cli

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "src" / "agent_gap_radar"
TOOLS_DIR = REPO_ROOT / "tools"
ROADMAP = REPO_ROOT / "PRODUCT.md"
ITER109_MODULE = pathlib.Path(__file__).resolve().parent / "test_iter109_behavior.py"

ERROR_PREFIX = "Error: "
USAGE_PREFIX = "usage:"

#: Argparse's own refusal spelling, written so it also binds when `prog` contains a space.
#: Re-declared from `tests/test_iter109_behavior.py`; the pattern equality is ASSERTED below.
PROG_AWARE_ARGPARSE_SPELLING = re.compile(r"^\S+(?: \S+)*: error: ")

#: The four `tools/` scripts this iteration brings inside the published vocabulary.
ARGPARSE_TOOLS = (
    "promote.py",
    "scan_cost.py",
    "verify_mutations.py",
    "verify_quotes.py",
)
#: The three hand-parsed scripts that already kept the promise and are NOT modified here.
HAND_PARSED_TOOLS = (
    "check_locators.py",
    "check_public_safety.py",
    "roadmap_integrity.py",
)
#: Behaviours 2 and 3 are one table, so the promise is stated once for all seven doors.
ALL_TOOLS = ARGPARSE_TOOLS + HAND_PARSED_TOOLS

#: The single unrecognized option every probe passes -- the most common failure a consumer
#: can produce, and the shape the spec fixes on. Stated once so nobody re-derives it.
UNKNOWN_OPTION = "--zzz-not-a-flag"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def probe(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one tracked `tools/` script as a subprocess from the repo root."""
    return subprocess.run(
        [sys.executable, f"tools/{tool}", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def last_non_empty_line(text: str) -> str:
    """The last line of `text` that is not empty after stripping."""
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines, "expected at least one non-empty line, got none"
    return lines[-1]


def assert_refusal_shape(result: subprocess.CompletedProcess[str], label: str) -> str:
    """Assert the spec's refusal shape and return the `Error: ` line it found."""
    assert result.returncode == 2, (
        f"{label}: expected exit 2, got {result.returncode}; stderr={result.stderr!r}"
    )
    assert result.stdout == "", (
        f"{label}: a refusal must write ZERO stdout bytes, got {result.stdout!r}"
    )
    line = last_non_empty_line(result.stderr)
    assert line.startswith(ERROR_PREFIX), (
        f"{label}: last non-empty stderr line must start {ERROR_PREFIX!r}, got {line!r}"
    )
    detail = line[len(ERROR_PREFIX) :]
    assert detail and not detail[0].isspace(), (
        f"{label}: {ERROR_PREFIX!r} must be followed by a non-space character, got {line!r}"
    )
    return line


def error_prefix_sites(source: str) -> list[int]:
    """Line numbers where `source` CONSTRUCTS a string starting with `Error: `.

    A construction is a plain string literal or an f-string whose first piece carries the
    prefix. A mere mention inside a longer sentence is not a construction site, which is
    why the check is an AST read and not a text search.
    """
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value.startswith(ERROR_PREFIX):
                lines.append(node.lineno)
        elif isinstance(node, ast.JoinedStr):
            head = node.values[0] if node.values else None
            if (
                isinstance(head, ast.Constant)
                and isinstance(head.value, str)
                and head.value.startswith(ERROR_PREFIX)
            ):
                lines.append(node.lineno)
    return sorted(set(lines))


def _callee_name(call: ast.Call) -> str | None:
    """The trailing name of a call's callee: `argparse.ArgumentParser` -> `ArgumentParser`."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def calls_named(source: str, name: str) -> list[int]:
    """Line numbers of every `ast.Call` in `source` whose callee resolves to `name`."""
    return sorted(
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and _callee_name(node) == name
    )


def bare_argument_parser_sites(source: str) -> list[int]:
    """Line numbers where `source` constructs a bare `argparse.ArgumentParser(...)`."""
    return calls_named(source, "ArgumentParser")


def tracked_tools() -> list[pathlib.Path]:
    """Every `.py` file under `tools/`, so a script added later inherits the rules."""
    files = sorted(TOOLS_DIR.glob("*.py"))
    assert files, "no .py files found under tools/ -- the census would be vacuous"
    return files


def shallow_listing(directory: pathlib.Path) -> list[tuple[str, int]]:
    """`(name, size)` for every entry directly inside `directory`, sorted."""
    return sorted((p.name, p.stat().st_size if p.is_file() else -1) for p in directory.iterdir())


# ---------------------------------------------------------------------------
# Behaviour 1 -- `cli.py` publishes its two error names, aliases keep resolving
# ---------------------------------------------------------------------------


def test_b1_the_two_error_names_are_public_and_the_private_ones_are_aliases() -> None:
    fail = getattr(cli, "fail", None)
    parser_class = getattr(cli, "PublishedErrorParser", None)
    assert callable(fail), "cli.fail must be a public callable"
    assert isinstance(parser_class, type) and issubclass(parser_class, argparse.ArgumentParser), (
        "cli.PublishedErrorParser must be an argparse.ArgumentParser subclass"
    )
    # Aliases, not copies: every committed reference to the private names keeps working.
    assert cli._fail is cli.fail, "cli._fail must be the SAME object as cli.fail"
    assert cli._PublishedErrorParser is cli.PublishedErrorParser, (
        "cli._PublishedErrorParser must be the SAME object as cli.PublishedErrorParser"
    )
    assert cli.EXIT_ERROR == 2, f"the published refusal exit code is 2, got {cli.EXIT_ERROR!r}"


def test_b1_public_fail_writes_one_prefixed_line_and_returns_the_error_exit_code() -> None:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.fail("nope")
    assert err.getvalue() == f"{ERROR_PREFIX}nope\n", (
        f"cli.fail must write exactly {ERROR_PREFIX!r}<msg> plus ONE newline, "
        f"got {err.getvalue()!r}"
    )
    assert out.getvalue() == "", f"cli.fail must not touch stdout, got {out.getvalue()!r}"
    assert code == cli.EXIT_ERROR == 2, f"cli.fail must return {cli.EXIT_ERROR!r}, got {code!r}"


def test_b1_the_error_prefix_has_exactly_one_construction_site_and_it_is_in_cli() -> None:
    """The rename must not fork the emitter: still ONE door, still in `cli.py`."""
    census = {
        path.name: error_prefix_sites(path.read_text(encoding="utf-8"))
        for path in sorted(PACKAGE_DIR.glob("*.py"))
    }
    assert census, "no package modules found -- the census would be vacuous"
    with_sites = {name: lines for name, lines in census.items() if lines}
    assert list(with_sites) == ["cli.py"], (
        f"the {ERROR_PREFIX!r} prefix must be constructed in cli.py ONLY, found {with_sites}"
    )
    assert len(with_sites["cli.py"]) == 1, (
        f"expected exactly one construction site in cli.py, found lines {with_sites['cli.py']}"
    )


def test_b1_control_the_prefix_census_discriminates(tmp_path: pathlib.Path) -> None:
    constructs = tmp_path / "constructs.py"
    constructs.write_text('msg = f"Error: {thing} broke"\n', encoding="utf-8")
    mentions = tmp_path / "mentions.py"
    mentions.write_text(
        '"""Every refusal line starts with the Error: prefix."""\nx = "an Error: mid-sentence"\n',
        encoding="utf-8",
    )
    assert len(error_prefix_sites(constructs.read_text(encoding="utf-8"))) == 1
    assert error_prefix_sites(mentions.read_text(encoding="utf-8")) == []


# ---------------------------------------------------------------------------
# Behaviours 2 + 3 -- ONE table: all seven tools refuse in the published vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", ALL_TOOLS)
def test_b2_b3_every_tool_refuses_a_mistyped_invocation_in_the_published_vocabulary(
    tool: str,
) -> None:
    result = probe(tool, UNKNOWN_OPTION)
    line = assert_refusal_shape(result, f"tools/{tool} {UNKNOWN_OPTION}")
    assert not PROG_AWARE_ARGPARSE_SPELLING.match(line), (
        f"tools/{tool}: last non-empty stderr line still speaks argparse's dialect: {line!r}"
    )


def test_b2_control_the_argparse_dialect_regex_still_discriminates() -> None:
    """A regex that matched nothing would make the table above pass for free."""
    argparse_line = "promote.py: error: unrecognized arguments: --zzz-not-a-flag"
    subparser_line = "radar scan: error: unrecognized arguments: --nope"
    published_line = f"{ERROR_PREFIX}unrecognized arguments: --zzz-not-a-flag"
    assert PROG_AWARE_ARGPARSE_SPELLING.match(argparse_line)
    assert PROG_AWARE_ARGPARSE_SPELLING.match(subparser_line)
    assert not PROG_AWARE_ARGPARSE_SPELLING.match(published_line)


def test_b2_the_argparse_dialect_regex_is_the_one_iteration_109_committed() -> None:
    """One definition of the dialect, and a brake on editing iteration 109's module."""
    committed = ITER109_MODULE.read_text(encoding="utf-8")
    declaration = (
        "PROG_AWARE_ARGPARSE_SPELLING = "
        f're.compile(r"{PROG_AWARE_ARGPARSE_SPELLING.pattern}")'
    )
    assert declaration in committed, (
        "this module's dialect regex no longer matches the one committed in "
        "tests/test_iter109_behavior.py -- one of the two moved"
    )


def test_b2_the_four_changed_tools_construct_the_published_parser() -> None:
    """Behaviour 6's zero must not be reachable by having no parser at all."""
    for tool in ARGPARSE_TOOLS:
        source = (TOOLS_DIR / tool).read_text(encoding="utf-8")
        sites = calls_named(source, "PublishedErrorParser")
        assert sites, f"tools/{tool} constructs no PublishedErrorParser"


# ---------------------------------------------------------------------------
# Behaviour 4 -- the `usage:` block survives and stays ABOVE the `Error: ` line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", ARGPARSE_TOOLS)
def test_b4_usage_survives_and_is_printed_above_the_error_line(tool: str) -> None:
    result = probe(tool, UNKNOWN_OPTION)
    lines = result.stderr.splitlines()
    usage_indexes = [i for i, line in enumerate(lines) if line.startswith(USAGE_PREFIX)]
    assert usage_indexes, (
        f"tools/{tool}: the usage block was swallowed -- stderr={result.stderr!r}"
    )
    non_empty_indexes = [i for i, line in enumerate(lines) if line.strip()]
    assert usage_indexes[-1] < non_empty_indexes[-1], (
        f"tools/{tool}: usage must be printed ABOVE the error line -- stderr={result.stderr!r}"
    )
    assert lines[non_empty_indexes[-1]].startswith(ERROR_PREFIX)


# ---------------------------------------------------------------------------
# Behaviour 5 -- no tool's SUCCESS path moves
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool", ("verify_mutations.py", "scan_cost.py"))
def test_b5_help_still_exits_zero_with_usage_on_stdout_and_silent_stderr(tool: str) -> None:
    result = probe(tool, "--help")
    assert result.returncode == 0, f"tools/{tool} --help exited {result.returncode}"
    assert result.stdout.startswith(USAGE_PREFIX), (
        f"tools/{tool} --help must open with {USAGE_PREFIX!r}, got {result.stdout[:60]!r}"
    )
    assert result.stderr == "", f"tools/{tool} --help wrote stderr: {result.stderr!r}"


def test_b5_roadmap_integrity_happy_path_is_byte_stable_and_reports_no_violations() -> None:
    first = probe("roadmap_integrity.py")
    second = probe("roadmap_integrity.py")
    assert first.returncode == 0, f"exit {first.returncode}; stderr={first.stderr!r}"
    assert second.returncode == 0, f"exit {second.returncode}; stderr={second.stderr!r}"
    assert first.stderr == "" and second.stderr == ""
    # The pin comes from the run, not from a copied literal.
    assert first.stdout == second.stdout, "roadmap_integrity.py stdout is not byte-stable"
    assert first.stdout.endswith("\n") and not first.stdout.endswith("\n\n"), (
        f"stdout must end in exactly ONE newline, got {first.stdout[-4:]!r}"
    )
    assert "0 violation(s)" in first.stdout, f"unexpected report: {first.stdout!r}"
    # ...and the counts are anchored to the document, so a future roadmap row cannot red
    # this test while a broken counter still does.
    # Read the COMMITTED document directly, NOT through the module-level `ROADMAP`
    # seam: a no-argument run always inspects the committed file, so the comparison
    # has to as well. Iteration 62's durability sweep repoints `ROADMAP` at a grown
    # fixture, and reading it here would compare a grown document against a report
    # produced from the committed one.
    roadmap_lines = (REPO_ROOT / "PRODUCT.md").read_text(encoding="utf-8").splitlines()
    table_rows = [line for line in roadmap_lines if re.match(r"^\| \d+ \|", line)]
    ledger_rows = [line for line in roadmap_lines if re.match(r"^- iter \d+ ", line)]
    assert f"{len(table_rows)} table row(s), {len(ledger_rows)} ledger row(s)" in first.stdout, (
        f"reported counts do not match PRODUCT.md ({len(table_rows)} table / "
        f"{len(ledger_rows)} ledger); stdout={first.stdout!r}"
    )


def test_b5_roadmap_integrity_counts_follow_the_document_it_is_given() -> None:
    """Behaviour 5, growth-safe half: the report is a FUNCTION of its input document.

    The pin above fixes the no-argument happy path over the committed roadmap. This one
    hands the tool an explicit path and re-derives the counts from that SAME document, so
    the assertion holds over any ledger -- including the sparse, grown one iteration 62's
    durability sweep repoints `ROADMAP` at, which is what makes this module a measured
    member of that sweep instead of an exempted one.
    """
    first = probe("roadmap_integrity.py", str(ROADMAP))
    second = probe("roadmap_integrity.py", str(ROADMAP))
    assert first.returncode == 0, f"exit {first.returncode}; stderr={first.stderr!r}"
    assert first.stderr == "" and second.stderr == ""
    assert first.stdout == second.stdout, "the report is not byte-stable for one document"
    assert first.stdout.endswith("\n") and not first.stdout.endswith("\n\n"), (
        f"stdout must end in exactly ONE newline, got {first.stdout[-4:]!r}"
    )
    assert "0 violation(s)" in first.stdout, f"unexpected report: {first.stdout!r}"

    given = ROADMAP.read_text(encoding="utf-8").splitlines()
    table_rows = [line for line in given if re.match(r"^\| \d+ \|", line)]
    ledger_rows = [line for line in given if re.match(r"^- iter \d+ ", line)]
    assert f"{len(table_rows)} table row(s), {len(ledger_rows)} ledger row(s)" in first.stdout, (
        f"reported counts do not follow the document given ({len(table_rows)} table / "
        f"{len(ledger_rows)} ledger); stdout={first.stdout!r}"
    )


# ---------------------------------------------------------------------------
# Behaviour 6 -- a brake against the dialect coming back
# ---------------------------------------------------------------------------


def test_b6_no_tool_constructs_a_bare_argument_parser() -> None:
    offenders = {
        path.name: bare_argument_parser_sites(path.read_text(encoding="utf-8"))
        for path in tracked_tools()
    }
    offenders = {name: lines for name, lines in offenders.items() if lines}
    assert offenders == {}, (
        f"these tools/ scripts construct a bare argparse.ArgumentParser: {offenders} -- "
        "use agent_gap_radar.cli.PublishedErrorParser so refusals keep the published vocabulary"
    )


def test_b6_control_the_parser_census_discriminates(tmp_path: pathlib.Path) -> None:
    bare = tmp_path / "bare.py"
    bare.write_text(
        "import argparse\n\n\ndef main():\n    return argparse.ArgumentParser(prog='x')\n",
        encoding="utf-8",
    )
    published = tmp_path / "published.py"
    published.write_text(
        "from agent_gap_radar.cli import PublishedErrorParser\n\n\n"
        "def main():\n    return PublishedErrorParser(prog='x')\n",
        encoding="utf-8",
    )
    mention_only = tmp_path / "mention.py"
    mention_only.write_text(
        '"""This tool used argparse.ArgumentParser before iteration 206."""\n'
        "# argparse.ArgumentParser( is named here on purpose\n"
        "VALUE = 1\n",
        encoding="utf-8",
    )
    assert len(bare_argument_parser_sites(bare.read_text(encoding="utf-8"))) == 1
    assert bare_argument_parser_sites(published.read_text(encoding="utf-8")) == []
    assert bare_argument_parser_sites(mention_only.read_text(encoding="utf-8")) == []


def test_b6_the_census_covers_every_tracked_tool_including_the_seven_probed() -> None:
    names = {path.name for path in tracked_tools()}
    missing = set(ALL_TOOLS) - names
    assert missing == set(), f"probed tools missing from tools/: {sorted(missing)}"


# ---------------------------------------------------------------------------
# Behaviour 7 -- offline, deterministic, and it writes nothing outside tmp_path
# ---------------------------------------------------------------------------


def test_b7_the_probe_is_deterministic_and_leaves_the_tree_untouched() -> None:
    watched = [REPO_ROOT, TOOLS_DIR, REPO_ROOT / "gaps"]
    before = [shallow_listing(directory) for directory in watched]
    first = {tool: probe(tool, UNKNOWN_OPTION) for tool in ALL_TOOLS}
    second = {tool: probe(tool, UNKNOWN_OPTION) for tool in ALL_TOOLS}
    for tool in ALL_TOOLS:
        assert (first[tool].returncode, first[tool].stdout, first[tool].stderr) == (
            second[tool].returncode,
            second[tool].stdout,
            second[tool].stderr,
        ), f"tools/{tool} is not deterministic across two identical probes"
    after = [shallow_listing(directory) for directory in watched]
    assert before == after, "a probe wrote to the tracked tree; refusals must be read-only"


def test_b7_this_module_is_offline_and_touches_no_radar_verb() -> None:
    own_source = pathlib.Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(own_source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"socket", "urllib", "http", "requests", "httpx", "ssl", "ftplib", "smtplib"}
    assert imported & forbidden == set(), (
        f"this module must stay offline, but imports {sorted(imported & forbidden)}"
    )
    # Every subprocess this module starts must be a tracked script under `tools/`, never
    # the product CLI. The entry-point token is assembled rather than written, so this
    # check cannot be tripped by its own literal.
    entry_point = "ra" + "dar"
    argv_tokens: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _callee_name(node) == "run"):
            continue
        assert node.args, "a subprocess.run with no argv would escape this audit"
        argv = node.args[0]
        assert isinstance(argv, ast.List), "argv must be a literal list, so it is auditable"
        for element in argv.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                argv_tokens.append(element.value)
            elif isinstance(element, ast.JoinedStr):
                head = element.values[0] if element.values else None
                if isinstance(head, ast.Constant) and isinstance(head.value, str):
                    argv_tokens.append(head.value)
    assert argv_tokens, "no subprocess argv found -- this audit would be vacuous"
    assert entry_point not in argv_tokens, f"a subprocess invokes the product CLI: {argv_tokens}"
    assert any(token.startswith("tools/") for token in argv_tokens), (
        f"no subprocess targets a tracked tools/ script: {argv_tokens}"
    )
# ---------------------------------------------------------------------------
# EXTENSIONS (tester round 3) -- the mechanism behind the table, a SECOND
# failure kind, the success path of all four changed tools, one more control
# for the census, and a stronger read-only proof.
# ---------------------------------------------------------------------------


def test_b1_ext_the_published_parser_itself_carries_the_refusal_shape() -> None:
    """B1 x B2 x B4: the PUBLIC name, driven directly, must produce the whole shape.

    The seven-tool table proves the tools refuse correctly. It cannot tell WHY: a tool
    could satisfy it by hand-writing a compliant line and never reaching the published
    parser at all. Driving `cli.PublishedErrorParser` itself pins the shape at the one
    door the spec says the four tools now come through -- exit 2, zero stdout, usage
    ABOVE a single `Error: ` line, and never argparse's own dialect.
    """
    parser = cli.PublishedErrorParser(prog="fixture-tool")
    parser.add_argument("--real-flag")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        with pytest.raises(SystemExit) as raised:
            parser.parse_args([UNKNOWN_OPTION])
    assert raised.value.code == cli.EXIT_ERROR == 2, (
        f"the published parser must exit {cli.EXIT_ERROR}, got {raised.value.code!r}"
    )
    assert out.getvalue() == "", f"a refusal must write ZERO stdout bytes, got {out.getvalue()!r}"
    stderr = err.getvalue()
    lines = [line for line in stderr.splitlines() if line.strip()]
    assert lines, f"the published parser wrote no stderr at all: {stderr!r}"
    assert lines[-1].startswith(ERROR_PREFIX), (
        f"last non-empty stderr line must start {ERROR_PREFIX!r}, got {lines[-1]!r}"
    )
    assert not PROG_AWARE_ARGPARSE_SPELLING.match(lines[-1]), (
        f"the published parser fell back to argparse's dialect: {lines[-1]!r}"
    )
    usage_lines = [i for i, line in enumerate(lines) if line.startswith(USAGE_PREFIX)]
    assert usage_lines, f"usage: block was swallowed: {stderr!r}"
    assert max(usage_lines) < len(lines) - 1, (
        f"usage: must be printed ABOVE the Error: line, got {lines!r}"
    )
    assert sum(1 for line in lines if line.startswith(ERROR_PREFIX)) == 1, (
        f"exactly one Error: line expected, got {lines!r}"
    )


def value_taking_long_option(help_text: str, label: str) -> str:
    """A long option that REQUIRES a value, read out of the tool's own `--help`.

    Derived at run time from published output rather than written down, so this probe
    follows a tool that renames its flags instead of rotting into a no-op.
    """
    found = re.findall(r"(--[a-z][a-z0-9-]*) [A-Z][A-Z0-9_]*", help_text)
    assert found, f"{label}: no value-taking long option found in its own --help"
    return found[0]


@pytest.mark.parametrize("tool", ARGPARSE_TOOLS)
def test_b2_ext_a_second_failure_kind_is_refused_in_the_same_vocabulary(tool: str) -> None:
    """B2 generalised: the promise is about A MISTYPED INVOCATION, not one magic token.

    The table probes an UNRECOGNIZED option. This probes a recognised option with its
    value missing -- a different argparse error path, reached before any tool work runs.
    A fix that special-cased the one probed spelling would pass the table and fail here.
    """
    help_result = probe(tool, "--help")
    assert help_result.returncode == 0, f"{tool} --help must exit 0 to source a flag name"
    flag = value_taking_long_option(help_result.stdout, tool)
    result = probe(tool, flag)
    label = f"tools/{tool} {flag} (value missing)"
    line = assert_refusal_shape(result, label)
    assert not PROG_AWARE_ARGPARSE_SPELLING.match(line), (
        f"{label}: still answers in argparse's dialect: {line!r}"
    )
    stderr_lines = [ln for ln in result.stderr.splitlines() if ln.strip()]
    usage_at = [i for i, ln in enumerate(stderr_lines) if ln.startswith(USAGE_PREFIX)]
    assert usage_at, f"{label}: usage: block was swallowed: {result.stderr!r}"
    assert max(usage_at) < len(stderr_lines) - 1, (
        f"{label}: usage: must stay ABOVE the Error: line, got {stderr_lines!r}"
    )


@pytest.mark.parametrize("tool", ARGPARSE_TOOLS)
def test_b5_ext_every_changed_tool_keeps_its_help_success_path(tool: str) -> None:
    """B5 widened from the two tools the spec names to all FOUR it changes.

    The spec's clause is "no tool's SUCCESS path moves"; naming two of the four leaves
    two doors unasserted. Trailing-newline shape is pinned too: the quality bar wants
    exactly one, and swapping a parser class is exactly the kind of change that could
    add a second.
    """
    result = probe(tool, "--help")
    assert result.returncode == 0, f"{tool} --help: expected exit 0, got {result.returncode}"
    assert result.stderr == "", f"{tool} --help must be silent on stderr, got {result.stderr!r}"
    assert result.stdout.startswith(USAGE_PREFIX), (
        f"{tool} --help must write a usage: block to stdout, got {result.stdout[:80]!r}"
    )
    assert result.stdout.endswith("\n") and not result.stdout.endswith("\n\n"), (
        f"{tool} --help must end in exactly ONE newline, got {result.stdout[-20:]!r}"
    )


def test_b6_ext_the_census_catches_the_bare_name_import_form(tmp_path: pathlib.Path) -> None:
    """B6 hole check: `from argparse import ArgumentParser` then a bare-name call.

    The spec's three fixtures all spell the class through the module. A census that only
    resolved `ast.Attribute` callees would pass those three and still let the dialect
    back in through the bare-name import, so that form is pinned to count 1 -- and a
    subclass DEFINITION naming the class as a base, which constructs nothing, to count 0.
    """
    bare_name = tmp_path / "bare_name_import.py"
    bare_name.write_text(
        "from argparse import ArgumentParser\n\n\ndef build():\n"
        "    return ArgumentParser(prog='x')\n",
        encoding="utf-8",
    )
    subclass_only = tmp_path / "subclass_only.py"
    subclass_only.write_text(
        "import argparse\n\n\nclass Custom(argparse.ArgumentParser):\n"
        "    pass\n",
        encoding="utf-8",
    )
    assert len(bare_argument_parser_sites(bare_name.read_text(encoding="utf-8"))) == 1, (
        "the census misses the bare-name import form, so the brake has a hole"
    )
    assert bare_argument_parser_sites(subclass_only.read_text(encoding="utf-8")) == [], (
        "a subclass definition constructs nothing and must not count as a site"
    )


def deep_listing(directory: pathlib.Path) -> list[tuple[str, int, int]]:
    """`(relative path, size, mtime_ns)` for every file under `directory`, sorted."""
    return sorted(
        (str(p.relative_to(directory)), p.stat().st_size, p.stat().st_mtime_ns)
        for p in directory.rglob("*")
        if p.is_file()
    )


def test_b7_ext_the_register_is_untouched_by_the_whole_probe_table() -> None:
    """B7 sharpened: no register record is READ-MODIFIED by any refusal.

    The shallow `(name, size)` listing already committed here would miss a rewrite that
    preserved a file's length. This walks `gaps/` recursively and includes `mtime_ns`,
    so any write at all -- same length or not -- reds the test.
    """
    gaps = REPO_ROOT / "gaps"
    assert gaps.is_dir(), "gaps/ must exist for this proof to mean anything"
    before = deep_listing(gaps)
    assert before, "gaps/ holds no files -- this proof would be vacuous"
    for tool in ALL_TOOLS:
        assert_refusal_shape(probe(tool, UNKNOWN_OPTION), f"tools/{tool}")
    assert deep_listing(gaps) == before, "a refusal mutated the register; refusals are read-only"
