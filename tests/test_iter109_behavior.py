r"""Iteration 109 behaviours: EVERY exit-2 refusal `radar` can produce ends with the
`Error: `-prefixed line the consumer contract publishes -- including the five STRUCTURAL
refusals argparse used to answer in its own vocabulary.

WHAT THIS ITERATION CLAIMS, IN BEHAVIOURAL TERMS
`docs/CONSUMER_CONTRACT.md`'s code-`2` row tells a machine consumer that stderr's LAST
non-empty line begins `Error: ` and that stdout stays empty. Before this iteration that
promise held on ONE door (the register-load refusals routed through `cli._fail`) and was
false on the five structural ones -- a missing positional, an unknown verb, an unparseable
`--floor`, an unrecognized option -- which printed argparse's `<prog>: error: ...` line
instead. This module asserts the promise on ALL of them, asserts the `usage:` block still
precedes the prefixed line (that is the only place a caller learns the arity it got wrong),
and asserts the prefix keeps exactly ONE construction site in the package.

ISOLATION. This module honours the tester's isolation contract. It reads `pm.md`, this
repo's `tests/` conventions, and the PUBLISHED contract document (prose, not code), and it
observes the product only by IMPORTING its public names and RUNNING its CLI. It does not
read `src/`, the engineer's or the reviewer's notes, any patch, or any diff. The one place
it touches package source TEXT is the behaviour-3 census, which the spec asks for by name;
that census is an `ast` walk executed at test time, never a human read.

WHY EACH BEHAVIOUR IS PAIRED WITH A CONTROL, AND WHICH RIVAL RULE THE PAIR KILLS

* B1 captures each argv shape ONCE and asserts all three clauses off that single capture,
  per the spec's size self-check: 15 subprocess spawns is the shape that cap-killed the
  previous iteration's tester rounds. Two shapes are ALSO run at the process boundary, so
  the 0-byte stdout claim is measured where a consumer actually reads it (a redirected
  `StringIO` cannot see a write that bypasses `sys.stdout`).

* B1's clause (c) is the two-sided half: without it, an implementation that merely printed
  `Error: ...` and SWALLOWED the usage block would pass. The ordering assertion (`usage:`
  strictly above the prefixed line) kills the rival that appends usage after the error.

* B1's clause (c) also carries a MEASURED AMBIGUITY, pinned in code rather than argued in
  prose. The spec's regex for argparse's own spelling is `^\S+: error: `, but a subparser's
  `prog` contains a SPACE (`radar scan`), so that regex cannot anchor on four of the five
  doors -- it was already green at HEAD there. `test_b6_control_shows_the_narrow_regex_is
  _vacuous_on_subparser_doors` measures exactly which doors it discriminates on, and every
  clause-(c) assertion in B1 therefore ALSO uses a prog-aware regex that does bind.

* B3's oracle for the untouched `_fail` door is DERIVED (`"Error: " + cli._unknown_layer(
  "nope")`), never a copied literal, so a legitimate re-wording of the layer taxonomy
  cannot red this module, while a renderer that stopped routing through `_fail` does.

* B3's routing claim is measured STRUCTURALLY: `cli._fail` is replaced by a recording
  wrapper and a structural door is driven through it, so "routes through `_fail`" is
  observed rather than inferred from the message text agreeing.

* B3's census counts CONSTRUCTION SITES (non-docstring string literals in the `ast`), not
  text matches. Measured on a synthetic fixture, a naive text count reports 1 on a file
  whose only mention is inside a docstring while the census reports 0 -- so the census is
  the instrument the criterion needs, and the fixture proves it discriminates.

* B4 pins the codes this change must NOT move, including bare `radar` (exit 0), which the
  spec puts OUT of scope and records as roadmap row 99. A structural-refusal rewrite is
  exactly the change that could turn that 0 into a 2 by accident.

* B6's control restores argparse's DEFAULT `error()` onto the parser class the product
  builds, then re-runs the same five shapes. Every clause-(b) assertion in B1 is therefore
  proved non-vacuous against the real before-state rather than against a hand-written one.

TWO DELIBERATE NON-ASSERTIONS, NAMED SO A LATER ITERATION DOES NOT "FIX" THEM
1. The CONTENT of the `usage:` block -- its wrapping, its flag order, its verb order -- is
   not pinned here (iteration 87 owns that pin). This module asserts only that a `usage:`
   line EXISTS and precedes the prefixed line.
2. The wording after `Error: ` on the structural doors is not pinned. The spec reuses
   argparse's own sentence verbatim, and pinning it would make a stdlib rewording red.
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
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

ERROR_PREFIX = "Error: "
USAGE_PREFIX = "usage:"

#: The spec's regex for argparse's own refusal spelling.
NARROW_ARGPARSE_SPELLING = re.compile(r"^\S+: error: ")
#: The same rule, written so it also binds when `prog` contains a space (`radar scan`),
#: which is the case on every SUBPARSER door. See the module docstring.
PROG_AWARE_ARGPARSE_SPELLING = re.compile(r"^\S+(?: \S+)*: error: ")

#: The five structural argv shapes named in the spec's Expected Behaviors, S1-S5.
STRUCTURAL_SHAPES = {
    "S1": ("scan",),
    "S2": ("show",),
    "S3": ("diff",),
    "S4": ("bogusverb",),
    "S5": ("list", ".", "--floor", "abc"),
}
#: Behaviour 2's shape, refused by the TOP-LEVEL parser as `unrecognized arguments`.
UNKNOWN_OPTION_SHAPE = ("list", ".", "--nope")


def capture(argv):
    """Drive `cli.main` in-process, returning `(exit_code, stdout, stderr)`.

    A refusal reaches the caller as an exit CODE whether the CLI returned it or argparse
    raised `SystemExit`, so one helper covers both routes and no door can pass this module
    by escaping as an exception.
    """
    out, err = io.StringIO(), io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([str(token) for token in argv])
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def spawn(argv):
    """The same argv at the PROCESS boundary, in BYTES, so `0 bytes of stdout` is measured
    where a consumer reads it rather than inside a redirected `StringIO`."""
    return subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *[str(token) for token in argv]],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )


def nonempty_lines(stderr):
    return [line for line in stderr.splitlines() if line.strip()]


def assert_published_error_channel(label, code, stdout, stderr):
    """Behaviour 1's three clauses, asserted off ONE capture.

    (a) exit 2 and exactly 0 bytes of stdout; (b) the LAST non-empty stderr line begins
    `Error: ` and carries a non-empty message after the prefix; (c) at least one `usage:`
    line, every one of them ABOVE the prefixed line, and no line spelled the way argparse
    spells its own refusals.
    """
    # (a)
    assert code == 2, f"{label}: exit code was {code!r}, not 2; stderr={stderr!r}"
    assert stdout == "", f"{label}: stdout was not empty: {stdout[:200]!r}"
    # (b)
    lines = nonempty_lines(stderr)
    assert lines, f"{label}: stderr carried no non-empty line"
    last = lines[-1]
    assert last.startswith(ERROR_PREFIX), (
        f"{label}: last non-empty stderr line does not begin {ERROR_PREFIX!r}: {last!r}"
    )
    assert last[len(ERROR_PREFIX):].strip(), f"{label}: the prefix carried no message: {last!r}"
    # (c)
    all_lines = stderr.splitlines()
    usage_indexes = [i for i, line in enumerate(all_lines) if line.startswith(USAGE_PREFIX)]
    assert usage_indexes, f"{label}: no {USAGE_PREFIX!r} line survived: {stderr!r}"
    error_index = max(i for i, line in enumerate(all_lines) if line.startswith(ERROR_PREFIX))
    assert max(usage_indexes) < error_index, (
        f"{label}: a {USAGE_PREFIX!r} line appears at or below the {ERROR_PREFIX!r} line "
        f"(usage at {usage_indexes}, error at {error_index}): {stderr!r}"
    )
    for line in all_lines:
        assert not NARROW_ARGPARSE_SPELLING.match(line), (
            f"{label}: argparse's own spelling reached stderr (spec regex): {line!r}"
        )
        assert not PROG_AWARE_ARGPARSE_SPELLING.match(line), (
            f"{label}: argparse's own spelling reached stderr (prog-aware regex): {line!r}"
        )


# --------------------------------------------------------------------------------------
# Behaviour 1 -- one capture per shape, three clauses
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("label", sorted(STRUCTURAL_SHAPES))
def test_b1_each_structural_shape_ends_stderr_with_the_published_prefix(label):
    """S1-S5: exit 2, empty stdout, `usage:` above a non-empty `Error: ` last line, and
    argparse's own spelling nowhere. ONE capture, all three clauses."""
    code, out, err = capture(STRUCTURAL_SHAPES[label])
    assert_published_error_channel(label, code, out, err)


def test_b1_the_five_shapes_are_the_five_the_spec_names():
    """A guard against this module silently shrinking its own domain: the parametrised set
    must stay exactly S1-S5, so a later edit that drops a door reds here."""
    assert sorted(STRUCTURAL_SHAPES) == ["S1", "S2", "S3", "S4", "S5"]
    assert STRUCTURAL_SHAPES["S1"] == ("scan",)
    assert STRUCTURAL_SHAPES["S4"] == ("bogusverb",)


@pytest.mark.parametrize("label", ["S1", "S4"])
def test_b1_the_zero_byte_stdout_holds_at_the_process_boundary(label):
    """The subparser route (S1) and the top-level route (S4) measured in BYTES across a
    real process, which is where the contract's `stdout stays empty` is read. Two spawns
    only -- the spec caps this module's subprocess budget."""
    proc = spawn(STRUCTURAL_SHAPES[label])
    assert proc.returncode == 2, (proc.returncode, proc.stderr.decode()[:300])
    assert proc.stdout == b"", f"{label}: {len(proc.stdout)} bytes reached stdout"
    err = proc.stderr.decode("utf-8")
    lines = nonempty_lines(err)
    assert lines and lines[-1].startswith(ERROR_PREFIX), repr(err)
    for line in err.splitlines():
        assert not PROG_AWARE_ARGPARSE_SPELLING.match(line), repr(line)


# --------------------------------------------------------------------------------------
# Behaviour 2 -- unknown option, same rule
# --------------------------------------------------------------------------------------


def test_b2_unknown_option_obeys_the_same_rule():
    """`radar list . --nope` is refused by the TOP-LEVEL parser as `unrecognized
    arguments`, a route distinct from every S1-S5 shape, and must answer identically."""
    code, out, err = capture(UNKNOWN_OPTION_SHAPE)
    assert_published_error_channel("B2", code, out, err)
    assert "--nope" in nonempty_lines(err)[-1], (
        "the prefixed line should still name the offending token: " + repr(err)
    )


# --------------------------------------------------------------------------------------
# Behaviour 3 -- the `_fail` sites do not move, and the prefix keeps ONE site
# --------------------------------------------------------------------------------------


def test_b3_the_fail_door_is_unchanged_and_its_oracle_is_derived():
    """`radar list . --layer nope` stays EXACTLY one line, equal to `"Error: " +
    cli._unknown_layer("nope")`. The oracle is derived from the product's own taxonomy
    helper, so re-wording the layer list cannot drift this assertion."""
    code, out, err = capture(("list", ".", "--layer", "nope"))
    assert code == 2, (code, err)
    assert out == "", repr(out[:200])
    expected = ERROR_PREFIX + cli._unknown_layer("nope")
    assert err.splitlines() == [expected], f"stderr moved: {err!r}"
    assert USAGE_PREFIX not in err, "a register-load refusal must not grow a usage block"


def test_b3_a_structural_refusal_routes_through_fail():
    """Structural refusals must ROUTE THROUGH `_fail` rather than spell the prefix again.
    Measured by replacing `_fail` with a recording wrapper and driving S1 through it."""
    original = cli._fail
    calls = []

    def recording(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(cli, "_fail", recording)
        code, out, err = capture(STRUCTURAL_SHAPES["S1"])

    assert code == 2, (code, err)
    assert calls, "the structural refusal did not call cli._fail at all"
    assert nonempty_lines(err)[-1].startswith(ERROR_PREFIX), repr(err)


def error_prefix_construction_sites(paths):
    """Every non-docstring string literal containing `Error: `, as `(file, line, text)`.

    A CONSTRUCTION SITE is a string the code builds at runtime, so docstrings (prose about
    the rule) and comments (absent from the `ast` entirely) are excluded by construction.
    """
    sites = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstring_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", None)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    docstring_nodes.add(id(body[0].value))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in docstring_nodes
                and ERROR_PREFIX in node.value
            ):
                sites.append((path.name, node.lineno, node.value[:60]))
    return sites


def test_b3_the_prefix_has_exactly_one_construction_site_in_the_package():
    """The census the acceptance criterion names, over the whole package."""
    sources = list(PACKAGE_DIR.rglob("*.py"))
    assert len(sources) >= 2, f"the census found no package sources under {PACKAGE_DIR.name}"
    sites = error_prefix_construction_sites(sources)
    assert len(sites) == 1, f"the {ERROR_PREFIX!r} prefix has {len(sites)} construction sites: {sites}"
    assert sites[0][0] == "cli.py", f"the single site moved out of cli.py: {sites}"


def test_b3_the_census_counts_construction_sites_not_text_mentions(tmp_path):
    """The census instrument, measured on fixtures so its discriminating power is observed.

    A file whose ONLY mention lives in a docstring counts 0 while a naive text count
    reports 1; a file with a second `f"Error: ..."` counts 2. Without this fixture the
    criterion could be satisfied (or broken) by prose, which is what the spec's
    `variant that writes its own "Error: " string` control is for.
    """
    quote = '"'
    docstring_only = tmp_path / "prose_only.py"
    docstring_only.write_text(
        '"""a note mentioning ' + quote + ERROR_PREFIX + quote + ' inside prose."""\n',
        encoding="utf-8",
    )
    assert error_prefix_construction_sites([docstring_only]) == []
    naive = docstring_only.read_text(encoding="utf-8").count(quote + ERROR_PREFIX)
    assert naive == 1, "the fixture must be a text match the census refuses to count"

    one_site = tmp_path / "one_site.py"
    one_site.write_text('def f(m):\n    return f"' + ERROR_PREFIX + '{m}"\n', encoding="utf-8")
    assert len(error_prefix_construction_sites([one_site])) == 1

    two_sites = tmp_path / "two_sites.py"
    two_sites.write_text(
        'def f(m):\n    return f"' + ERROR_PREFIX + '{m}"\n'
        'def g(m):\n    return "' + ERROR_PREFIX + '" + m\n',
        encoding="utf-8",
    )
    assert len(error_prefix_construction_sites([two_sites])) == 2


# --------------------------------------------------------------------------------------
# Behaviour 4 -- nothing that exits non-2 moves
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--help", "--version"])
def test_b4_help_and_version_still_exit_zero_with_clean_stderr(flag):
    code, out, err = capture((flag,))
    assert code == 0, (flag, code, err)
    assert out.strip(), f"{flag} wrote nothing to stdout"
    assert err == "", f"{flag} wrote to stderr: {err!r}"


def test_b4_report_still_exits_zero_with_a_document_and_clean_stderr():
    code, out, err = capture(("report", str(REPO_ROOT)))
    assert code == 0, (code, err)
    assert err == "", repr(err)
    assert out.startswith("#") and out.endswith("\n") and not out.endswith("\n\n"), repr(out[:80])


def test_b4_bare_radar_still_exits_zero_and_is_out_of_scope():
    """Pinned, not fixed: the spec records bare `radar` (exit 0 with usage on STDOUT) as
    roadmap row 99, out of scope here, so this change must not turn that 0 into a 2."""
    code, out, err = capture(())
    assert code == 0, f"bare radar exited {code!r} -- row 99 was changed by accident: {err!r}"
    assert out.strip(), "bare radar stopped writing its usage to stdout"
    assert err == "", repr(err)


# --------------------------------------------------------------------------------------
# Behaviour 5 -- the contract states the rule the CLI now holds
# --------------------------------------------------------------------------------------


def exit_code_table_rows():
    """The `## Exit codes` table rows, as `{code_int: (when_cell, consumer_cell)}`.

    Read from the published document immediately under its heading, so a table moved away
    from the heading fails closed exactly as the document itself promises.
    """
    lines = CONTRACT.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Exit codes")
    rows = {}
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`(\d+)`", cells[0])
        if match:
            rows[int(match.group(1))] = (cells[1], cells[2])
    return rows


def test_b5_the_code_two_row_states_the_last_line_rule():
    rows = exit_code_table_rows()
    assert 2 in rows, f"no code-2 row under ## Exit codes: {sorted(rows)}"
    when, consumer = rows[2]
    assert "LAST" in when or "last" in when, f"the code-2 row does not name the LAST line: {when!r}"
    assert "`" + ERROR_PREFIX + "`" in when, f"the code-2 row dropped the prefix: {when!r}"
    assert "last" in consumer.lower(), (
        "the consumer cell must point at the LAST line, not at 'the stderr line': "
        + repr(consumer)
    )
    # "No longer promises a SINGLE line" is a claim about what the row ASSERTS, not about
    # which words it contains: the row may (and does) mention the single-line reading in
    # order to DENY it. So every mention must sit inside a negation.
    for match in re.finditer(r"(?i)\bsingle line\b|\bone line\b", when):
        window = when[max(0, match.start() - 48) : match.start()].lower()
        assert "not" in window or "never" in window or "no longer" in window, (
            "the code-2 row still PROMISES stderr is a single line, which behaviour 1 "
            f"deliberately no longer holds: {when[max(0, match.start() - 48) : match.end()]!r}"
        )
    assert re.search(r"(?i)not promised as a single line", when), (
        "the code-2 row must say out loud that the single-line reading is withdrawn, or a "
        "consumer that already implemented it has no way to learn otherwise: " + repr(when)
    )
    assert "`usage:`" in when and "ABOVE" in when, (
        "the code-2 row must say the usage block prints ABOVE the prefixed line, which is "
        "the substantive change behaviour 1 makes: " + repr(when)
    )


def test_b5_the_table_still_equals_cli_exit_codes_in_both_directions():
    """Iteration 25's invariant, re-asserted here because behaviour 5 edits that table."""
    assert set(exit_code_table_rows()) == set(cli.EXIT_CODES)


# --------------------------------------------------------------------------------------
# Behaviour 6 -- two-sided: the control fails what the product passes
# --------------------------------------------------------------------------------------


def control_capture(argv):
    """The SAME parser the product builds, with argparse's DEFAULT `error()` restored.

    This is the before-state, produced from the product's own `build_parser()` rather than
    from a hand-written parser, so a clause that passes on the product and fails here is
    proved to be measuring THIS iteration's change.
    """
    parser_class = type(cli.build_parser())
    assert "error" in vars(parser_class), (
        "the product's parser class does not override error(); behaviour 6's control "
        "would then be identical to the product and every clause below would be vacuous"
    )
    out, err = io.StringIO(), io.StringIO()
    code = None
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(parser_class, "error", argparse.ArgumentParser.error)
        parser = cli.build_parser()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                parser.parse_args([str(token) for token in argv])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("label", sorted(STRUCTURAL_SHAPES))
def test_b6_control_fails_clause_b_on_every_structural_shape(label):
    """With the default `error()` restored, NO shape ends stderr with the published prefix
    -- so every clause-(b) assertion in B1 is measuring this iteration's change."""
    code, out, err = control_capture(STRUCTURAL_SHAPES[label])
    assert code == 2, f"{label}: the control did not refuse: {code!r}"
    lines = nonempty_lines(err)
    assert lines, f"{label}: the control wrote nothing to stderr"
    assert not lines[-1].startswith(ERROR_PREFIX), (
        f"{label}: the control ALREADY ends with the prefix, so clause (b) is vacuous: "
        f"{lines[-1]!r}"
    )
    with pytest.raises(AssertionError):
        assert_published_error_channel(label, code, out, err)


def test_b6_control_shows_the_narrow_regex_is_vacuous_on_subparser_doors():
    """A MEASURED ambiguity in the spec, pinned so a later reader does not re-derive it.

    Clause (c) forbids any line matching `^\\S+: error: `. A SUBPARSER's `prog` contains a
    space (`radar scan`), so on the before-state that regex matches only the TOP-LEVEL
    doors: four of the five clause-(c) halves were green before this iteration. The
    prog-aware regex binds on all five, which is why `assert_published_error_channel`
    asserts both.
    """
    narrow_hits, prog_hits = set(), set()
    for label, argv in STRUCTURAL_SHAPES.items():
        _, _, err = control_capture(argv)
        for line in err.splitlines():
            if NARROW_ARGPARSE_SPELLING.match(line):
                narrow_hits.add(label)
            if PROG_AWARE_ARGPARSE_SPELLING.match(line):
                prog_hits.add(label)
    assert prog_hits == set(STRUCTURAL_SHAPES), (
        "the prog-aware regex must bind on the before-state of every door, or clause (c) "
        f"is untested somewhere: bound on {sorted(prog_hits)}"
    )
    assert narrow_hits == {"S4"}, (
        "measured: the spec's narrow regex discriminates only on the top-level door; "
        f"it bound on {sorted(narrow_hits)}"
    )


# --------------------------------------------------------------------------------------
# EXTENSIONS (second tester round) -- the Feature sentence is "EVERY exit-2 refusal
# `radar` can produce", so the doors are enumerated from the product's own help text
# rather than from the five shapes the spec quotes, and the SPLIT between a structural
# refusal (usage above the prefix) and a semantic one (exactly one line, no usage) is
# pinned in both directions. The first round left the S1-S5 matrix; these add the census.
# --------------------------------------------------------------------------------------


def declared_verbs():
    """The verb list DERIVED from `radar --help` stdout, never hard-coded here.

    The spec names five shapes; the FEATURE sentence covers every exit-2 refusal the CLI
    can produce, so the door set has to grow by itself when a verb is added. A hard-coded
    list would silently stop covering verb nine.
    """
    code, out, err = capture(("--help",))
    assert code == 0 and err == "", (code, err)
    match = re.search(r"\{([a-z0-9,\-]+)\}", out)
    assert match, "could not find the verb choice set in `radar --help`: " + repr(out[:200])
    return match.group(1).split(",")


def test_e1_the_verb_census_is_derived_from_help_and_covers_the_published_set():
    verbs = declared_verbs()
    assert len(verbs) >= 8, f"the derived verb set shrank: {verbs}"
    for named in ("list", "report", "show", "scan", "diff", "validate", "taxonomy"):
        assert named in verbs, f"{named} vanished from the derived verb set: {verbs}"


def test_e1_every_verb_has_an_exit_two_door_that_obeys_the_published_channel():
    """One unknown-flag door per VERB, not per named shape.

    `radar <verb> --zzz-nope` is the door every consumer can reach on every verb, and it
    exercises both routes at once: the verbs with a required positional refuse in the
    SUBPARSER before the flag is ever reached, the rest reach the TOP-LEVEL
    `unrecognized arguments` refusal. All of them must end stderr with the published
    prefix, or the Feature sentence ("every exit-2 refusal") is false for that verb.
    """
    verbs = declared_verbs()
    for verb in verbs:
        code, out, err = capture((verb, "--zzz-nope"))
        assert_published_error_channel("verb " + verb + " --zzz-nope", code, out, err)


def test_e2_bare_verbs_either_produce_a_document_or_refuse_with_the_published_channel():
    """Every verb invoked bare: exit 0 with a clean stderr, or exit 2 obeying the channel.

    This is where a per-verb `error()` that someone forgot to wire would show up, and the
    exit-2 count is asserted non-zero so the test cannot pass by every verb succeeding.
    """
    refused = []
    for verb in declared_verbs():
        code, out, err = capture((verb,))
        if code == 2:
            refused.append(verb)
            assert_published_error_channel("bare " + verb, code, out, err)
        else:
            assert code == 0, f"bare {verb} exited {code!r}: {err!r}"
            assert err == "", f"bare {verb} wrote to stderr: {err!r}"
            assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-40:])
    assert len(refused) >= 3, (
        "fewer than three bare verbs refused, so this census is close to vacuous: "
        + repr(refused)
    )


#: Doors that refuse for a REGISTER/PATH reason rather than a structural one. Each is a
#: `_fail` site: the spec forbids any change to their exactly-one-line shape.
SEMANTIC_DOORS = {
    "no such gap": ("show", "GAP-999999", "."),
    "not an id": ("show", "not-an-id", "."),
    "not a directory": ("list", "./does-not-exist-xyz"),
    "diff bad paths": ("diff", "./nope-a.json", "./nope-b.json"),
}


@pytest.mark.parametrize("label", sorted(SEMANTIC_DOORS))
def test_e3_semantic_refusals_stay_one_line_and_grow_no_usage_block(label):
    """The other side of behaviour 1 clause (c), and the rival it kills.

    An over-fix that made `error()` the ONLY exit-2 route -- or that printed the usage
    block on every refusal -- would pass every clause in B1 and still break the contract's
    12 `_fail` doors, which promise a single greppable line and nothing else. So each
    semantic door is asserted at EXACTLY one line, prefixed, with no `usage:` anywhere.
    """
    code, out, err = capture(SEMANTIC_DOORS[label])
    assert code == 2, (label, code, err)
    assert out == "", repr(out[:200])
    lines = err.splitlines()
    assert len(lines) == 1, f"{label}: a semantic refusal grew to {len(lines)} lines: {err!r}"
    assert lines[0].startswith(ERROR_PREFIX), repr(lines[0])
    assert USAGE_PREFIX not in err, f"{label}: a usage block reached a semantic refusal: {err!r}"
    assert not PROG_AWARE_ARGPARSE_SPELLING.match(lines[0]), repr(lines[0])


def test_e4_every_verbs_help_still_exits_zero_with_an_empty_stderr():
    """The change writes the usage block to STDERR, so `--help` is the regression that
    would hurt most: a subparser whose help leaked to stderr still exits 0 and would pass
    behaviour 4's top-level check. Asserted per verb."""
    for verb in declared_verbs():
        code, out, err = capture((verb, "--help"))
        assert code == 0, f"{verb} --help exited {code!r}: {err!r}"
        assert out.strip(), f"{verb} --help wrote nothing to stdout"
        assert err == "", f"{verb} --help leaked to stderr: {err!r}"


@pytest.mark.parametrize(
    "label", sorted(STRUCTURAL_SHAPES) + ["B2"]
)
def test_e5_the_refusal_is_byte_stable_across_two_invocations(label):
    """Byte-stable output is a product-wide quality bar and the error channel is part of
    it: a consumer that diffs two runs of the same bad invocation must see nothing."""
    argv = UNKNOWN_OPTION_SHAPE if label == "B2" else STRUCTURAL_SHAPES[label]
    first = capture(argv)
    second = capture(argv)
    assert first == second, f"{label}: the refusal is not byte-stable: {first!r} vs {second!r}"


def test_e6_the_fail_door_bytes_at_the_process_boundary_end_in_exactly_one_newline():
    """The third and last subprocess of this module (the spec caps the budget at two or
    three). The `_fail` door's stderr is asserted in BYTES against a DERIVED oracle, so
    the one-line promise is measured including its single trailing newline."""
    proc = spawn(("list", ".", "--layer", "nope"))
    assert proc.returncode == 2, (proc.returncode, proc.stderr[:200])
    assert proc.stdout == b"", f"{len(proc.stdout)} bytes reached stdout"
    expected = (ERROR_PREFIX + cli._unknown_layer("nope")).encode("utf-8") + b"\n"
    assert proc.stderr == expected, (proc.stderr, expected)


def test_e7_the_census_discriminates_on_a_copy_of_the_real_package(tmp_path):
    """Behaviour 6's second control, run against the REAL package shape.

    The first round proved the census on synthetic one-line fixtures. This copies the
    package as it ships, re-runs the census (still 1), then adds ONE module that spells
    the prefix itself -- the exact variant the spec names -- and shows the census reports
    2. So the acceptance criterion is falsifiable on the tree it is asserted over, not
    only on a fixture.
    """
    copy_root = tmp_path / "agent_gap_radar"
    copy_root.mkdir()
    for source in sorted(PACKAGE_DIR.rglob("*.py")):
        target = copy_root / source.relative_to(PACKAGE_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    baseline = error_prefix_construction_sites(list(copy_root.rglob("*.py")))
    assert len(baseline) == 1, f"the copy does not reproduce the shipped census: {baseline}"

    rogue = copy_root / "rogue_prefix.py"
    rogue.write_text(
        'def shout(message):\n    return f"' + ERROR_PREFIX + '{message}"\n',
        encoding="utf-8",
    )
    after = error_prefix_construction_sites(list(copy_root.rglob("*.py")))
    assert len(after) == 2, f"the census did not see the rogue construction site: {after}"
