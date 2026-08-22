"""Iteration 66 behaviors: `radar list`'s text form reaches the published one-newline
tail, and ONE brake holds that guarantee across the whole verb surface.

`pm.md` measured every verb over a zero-record register and found exactly one breaking
the guarantee `VISION.md` publishes -- *every renderer's output ends in exactly one
newline*: `list` exits 0 having written ZERO stdout bytes, because its text form builds a
third private copy of the tail (`"".join(line + newline for ...)`) which returns the empty
string over zero rows, while the published renderer returns one newline. The durable half
is the brake: the iteration-21 census keys on the `join(...) + newline` idiom and is
therefore structurally BLIND to the per-line-append form, so a third copy survived a green
census. A census over source TEXT can always be evaded by a new construction; an assertion
over the BYTES of every exit-0 verb cannot.

BLACK-BOX, AND THE ISOLATION CONTRACT IS HONORED. Every expectation here comes from
`pm.md` (Feature / Why / Expected Behaviors) and is measured by RUNNING the product
through `cli.main` / `cli.build_parser`, or derived from the published `scoring` API and
the live register, which is published data. Nothing here was read from `src/`, from the
engineer's or the reviewer's notes, from `IMPLEMENTATION.patch`, or from any diff.

STRUCTURAL CHOICES, so this file cannot lie later:

* **No byte count is pinned for any document that embeds an input string.** Iteration 66's
  own reviewer measured three stages reporting three different sizes for the same `scan`
  invocation (837 / 841 / 892 B) -- the whole spread was `tmp_path` length, because `scan`
  prints its target twice. The brake asserts SHAPE (exit code, non-empty stdout, exactly
  one trailing newline, never two) and lets every count float. The one byte equality in
  this file is behavior 1's `stdout == "\n"`, which contains nothing derived from argv.
* **The brake's verb set is INTROSPECTED and compared BOTH WAYS.** It comes from
  `parser_surface()`, the helper that already fails closed when a parser registers no
  subcommands, so a ninth verb cannot ship unexercised and a retired verb cannot leave a
  dead row behind. A hand-written verb list in a test is the same drifting artifact as a
  hand-copied table one directory over.
* **The brake proves its own domain is non-empty before it certifies anything** (behavior
  7): at least six invocations must return 0, and the failure report names every
  invocation's exit code and stdout byte count. A table that silently exercised nothing
  fails here instead of passing green.
* **The one-newline checker is proved TWO-SIDED against planted results in this run** --
  zero bytes, a missing tail, a doubled tail, a non-empty stdout on an error exit and a
  stderr without the `Error: ` prefix are each shown to be CAUGHT. A checker that cannot
  fail is not evidence, and this file's central claim rests on it.
* **Behavior 5's expectation is DERIVED from `scoring.confidence`, never pinned to gap
  ids**, and it is swept across floors that witness 0, 1, 2 and all-16 below-floor records
  -- so a register that legitimately gains evidence cannot red a correct repo, and a
  checker that always answers "none" cannot pass.
* **Behavior 2's absence claim carries its own control**: the needle is EXTRACTED from
  `validate`'s live stderr and asserted to match there before it is asserted absent from
  `list`, so a broken matcher cannot read as silence.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; synthetic registers are built under `tmp_path` by copying a
  published record and rewriting its id, so no schema is restated.

AMBIGUITY NOTED FOR THE PM (behavior 6): `taxonomy` takes no register positional, so
"invoked over a zero-record register" is vacuous for it -- it is exercised with its bare
argv, which is the only reading available. Behavior 6 also says every exit-0 invocation
writes NON-EMPTY stdout; behavior 1 says `list`'s is exactly one newline. One newline is
non-empty, so the two agree, and this file asserts both rather than choosing.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from _surface_contract import parser_surface

from agent_gap_radar import cli, registry, scoring

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

REGISTER = registry.load_all(GAPS_DIR)
LIVE_IDS = frozenset(gap.id for gap in REGISTER)

#: Behavior 5's suffix, as the spec names it.
BELOW_FLOOR_SUFFIX = "[below-floor]"

#: The error contract the quality bar publishes: stderr prefixed, exit 2, stdout clean.
ERROR_PREFIX = "Error: "

#: The only exit codes any verb may return on the brake's inputs. Anything else -- an
#: uncaught traceback surfacing as 1, or a 130 -- is a finding, not a pass.
ALLOWED_EXITS = frozenset({0, 2})


def run(argv):
    """Drive the CLI in-process, returning `(exit_code, stdout, stderr)`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([str(token) for token in argv])
    return code, out.getvalue(), err.getvalue()


def _zero_record_register(root):
    """A register directory whose `gaps/` exists and holds no record files."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "gaps").mkdir(parents=True, exist_ok=True)
    return root


def _register_with(root, count):
    """A register holding `count` records, cloned from a PUBLISHED record.

    Cloning keeps this file from restating the record schema -- which would be reading
    the implementation's shape and pinning it -- while still giving behavior 4 a register
    whose size this file controls.
    """
    source = sorted(GAPS_DIR.glob("*.json"))[0]
    payload = json.loads(source.read_text(encoding="utf-8"))
    root.mkdir(parents=True, exist_ok=True)
    gaps = root / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    ids = []
    for index in range(count):
        clone = dict(payload)
        clone["id"] = f"GAP-9{index:02d}"
        ids.append(clone["id"])
        (gaps / f"{clone['id']}.json").write_text(
            json.dumps(clone, indent=2) + "\n", encoding="utf-8"
        )
    return root, ids


def _default_floor():
    """`list`'s own `--floor` default, read from the parser rather than restated."""
    import argparse

    parser = cli.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for candidate in action.choices["list"]._actions:
                if "--floor" in candidate.option_strings:
                    return candidate.default
    raise AssertionError(
        "could not read `list --floor`'s default from build_parser(); behavior 5's "
        "default-floor expectation would otherwise be a restated literal"
    )


# ---------------------------------------------------------------------------
# Behavior 1 -- `list` over a zero-record register is exactly one newline.
# ---------------------------------------------------------------------------


def test_list_over_zero_record_register_writes_exactly_one_newline(tmp_path):
    """Behavior 1: exit 0, stdout exactly `"\\n"` (1 byte), stderr empty."""
    register = _zero_record_register(tmp_path / "empty")
    code, out, err = run(("list", register))

    assert code == 0, f"expected exit 0 over a zero-record register, got {code}; stderr={err!r}"
    assert err == "", f"behavior 1 requires empty stderr, got {err!r}"
    assert out == "\n", (
        "behavior 1: `list` over a zero-record register must write exactly one newline, "
        f"got {len(out)} byte(s): {out!r}. Zero bytes is the defect this iteration "
        "closes; two newlines is the over-correction."
    )
    # Stated separately so a regression report says WHICH half broke.
    assert out.endswith("\n") and not out.endswith("\n\n")


# ---------------------------------------------------------------------------
# Behavior 2 -- the zero-record MESSAGE stays a `validate`-only message.
# ---------------------------------------------------------------------------


def test_list_does_not_borrow_validates_zero_record_message(tmp_path):
    """Behavior 2: neither stream of `list` carries `validate`'s zero-record message.

    The needle is EXTRACTED from `validate`'s live stderr and asserted to match there
    first, so a matcher that has silently stopped matching cannot read as silence.
    """
    register = _zero_record_register(tmp_path / "empty")

    validate_code, validate_out, validate_err = run(("validate", register))
    assert validate_code == 2, (
        f"control invocation changed: `validate` over a zero-record register returned "
        f"{validate_code}, so behavior 2 has no message to compare against"
    )
    assert validate_out == "", f"`validate` wrote {len(validate_out)} stdout byte(s)"

    #: The product's own WORDING, with no path in it: everything before the first path
    #: separator, minus the error prefix. Taking a PREFIX rather than substituting the
    #: register path matters -- the message names `<register>/gaps`, not `<register>`, so
    #: a substitution of the register path alone leaves a path fragment behind and the
    #: needle stops matching its own source. This keeps the needle a substring of the
    #: real stderr, which is what makes the control below meaningful.
    message = validate_err.strip()
    separator = chr(47)
    needle = message.split(separator)[0].removeprefix(ERROR_PREFIX).strip()
    assert len(needle) >= 10, (
        f"needle collapsed to {needle!r} after stripping the path and the error prefix; "
        "behavior 2's absence check would then be vacuous"
    )
    # Two-sided control: the needle must be FOUND where it belongs.
    assert needle in validate_err, (
        f"needle {needle!r} does not match `validate`'s own stderr {validate_err!r}; "
        "the extractor is broken, so the absence assertion below proves nothing"
    )

    list_code, list_out, list_err = run(("list", register))
    assert list_code == 0
    assert needle not in list_out, (
        f"behavior 2: `list` stdout carries `validate`'s zero-record message {needle!r}: "
        f"{list_out!r}"
    )
    assert needle not in list_err, (
        f"behavior 2: `list` stderr carries `validate`'s zero-record message {needle!r}: "
        f"{list_err!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 3 -- `list --json` is unchanged.
# ---------------------------------------------------------------------------


def test_list_json_over_zero_record_register_is_unchanged(tmp_path):
    """Behavior 3: exit 0, parses as JSON, `counts.total == 0`, one trailing newline."""
    register = _zero_record_register(tmp_path / "empty")
    code, out, err = run(("list", register, "--json"))

    assert code == 0, f"expected exit 0, got {code}; stderr={err!r}"
    assert err == "", f"behavior 3 requires empty stderr, got {err!r}"
    payload = json.loads(out)
    assert payload["counts"]["total"] == 0, (
        f"behavior 3: counts.total must be 0 over a zero-record register, got "
        f"{payload['counts']['total']!r}"
    )
    assert out.endswith("\n"), "behavior 3: `list --json` must end in a newline"
    assert not out.endswith("\n\n"), (
        "behavior 3: `list --json` must end in EXACTLY one newline, not two: "
        f"{out[-4:]!r}"
    )


# ---------------------------------------------------------------------------
# Behavior 4 -- one line per record, no blank first or last line.
# ---------------------------------------------------------------------------


def _assert_one_line_per_record(out, expected_ids, label):
    """Behavior 4's shape, applied to any register's `list` text output."""
    assert out.endswith("\n"), f"{label}: output must end in a newline, got {out[-4:]!r}"
    assert not out.endswith("\n\n"), (
        f"{label}: output must end in EXACTLY one newline, got {out[-4:]!r}"
    )
    parts = out.split("\n")
    assert parts[-1] == "", f"{label}: split on newline must end in one empty element"
    lines = parts[:-1]
    assert len(lines) == len(expected_ids), (
        f"{label}: expected exactly {len(expected_ids)} line(s), one per record, got "
        f"{len(lines)}: {lines[:3]!r}..."
    )
    assert all(line.strip() != "" for line in lines), (
        f"{label}: a rendered row is blank, so `document()`'s trailing-blank "
        f"normalisation could swallow it: {[i for i, l in enumerate(lines) if not l.strip()]!r}"
    )
    assert lines[0].strip() != "", f"{label}: blank FIRST line"
    assert lines[-1].strip() != "", f"{label}: blank LAST line"

    leading = [line.split()[0] if line.split() else "" for line in lines]
    assert set(leading) == set(expected_ids), (
        f"{label}: the set of leading record ids does not equal the register's ids; "
        f"missing={sorted(set(expected_ids) - set(leading))!r} "
        f"unexpected={sorted(set(leading) - set(expected_ids))!r}"
    )
    for line, first in zip(lines, leading):
        assert line.startswith(first), f"{label}: row does not begin with its id: {line!r}"


def test_list_on_the_live_register_renders_one_line_per_record():
    """Behavior 4 on the live register: N non-empty lines, one trailing newline."""
    assert len(REGISTER) >= 1, "live register is empty, so behavior 4 has no witness"
    code, out, err = run(("list", REPO_ROOT))
    assert code == 0, f"expected exit 0 on the live register, got {code}; stderr={err!r}"
    assert err == ""
    _assert_one_line_per_record(out, LIVE_IDS, "live register")


@pytest.mark.parametrize("count", [1, 2, 3])
def test_list_on_a_synthetic_register_renders_one_line_per_record(tmp_path, count):
    """Behavior 4 for small N, including N == 1 -- the boundary next to zero."""
    register, ids = _register_with(tmp_path / f"n{count}", count)
    code, out, err = run(("list", register))
    assert code == 0, f"expected exit 0 for N={count}, got {code}; stderr={err!r}"
    assert err == ""
    _assert_one_line_per_record(out, ids, f"synthetic register N={count}")


# ---------------------------------------------------------------------------
# Behavior 5 -- below-floor records are DISPLAYED, never dropped.
# ---------------------------------------------------------------------------


def _below_floor_ids(floor):
    """The register's own answer, derived from the published scorer."""
    return frozenset(gap.id for gap in REGISTER if scoring.confidence(gap) < floor)


@pytest.mark.parametrize("floor", [0, 1, 2, 3, 4, 5, 6])
def test_below_floor_records_are_displayed_with_their_suffix(floor):
    """Behavior 5: suffix count == below-floor count, and total lines == total records."""
    code, out, err = run(("list", REPO_ROOT, "--floor", floor))
    assert code == 0, f"expected exit 0 at --floor {floor}, got {code}; stderr={err!r}"
    assert err == ""

    lines = out.split("\n")[:-1]
    assert len(lines) == len(REGISTER), (
        f"--floor {floor}: {len(lines)} row(s) rendered for {len(REGISTER)} record(s) -- "
        "a below-floor record was DROPPED, which is the core invariant failing"
    )

    expected = _below_floor_ids(floor)
    marked = frozenset(
        line.split()[0]
        for line in lines
        if BELOW_FLOOR_SUFFIX in line and line.split()
    )
    assert marked == expected, (
        f"--floor {floor}: rows carrying {BELOW_FLOOR_SUFFIX} do not match the records "
        f"whose derived confidence is below it; missing={sorted(expected - marked)!r} "
        f"unexpected={sorted(marked - expected)!r}"
    )
    assert sum(1 for line in lines if BELOW_FLOOR_SUFFIX in line) == len(expected), (
        f"--floor {floor}: suffix appears on a different NUMBER of rows than the "
        f"{len(expected)} below-floor record(s)"
    )


def test_the_floor_sweep_witnesses_both_ends():
    """Behavior 5's checker is not vacuous: the sweep must witness 0, some and all.

    Without this, a `list` that had stopped emitting the suffix entirely would pass every
    parametrised case whose expectation happened to be the empty set.
    """
    counts = {floor: len(_below_floor_ids(floor)) for floor in (0, 1, 2, 3, 4, 5, 6)}
    assert min(counts.values()) == 0, (
        f"no floor in the sweep yields ZERO below-floor records: {counts!r}"
    )
    assert max(counts.values()) == len(REGISTER), (
        f"no floor in the sweep marks EVERY record below-floor: {counts!r}"
    )
    middles = sorted({n for n in counts.values() if 0 < n < len(REGISTER)})
    assert len(middles) >= 2, (
        f"the sweep never witnesses a PARTIAL split, so the suffix-set equality is only "
        f"ever asserted against the empty or the full set: {counts!r}"
    )


def test_default_floor_marks_and_keeps_every_record():
    """Behavior 5 on the DEFAULT floor, read from the parser rather than restated."""
    floor = _default_floor()
    assert isinstance(floor, int), f"`list --floor` default is {floor!r}, not an int"
    code, out, err = run(("list", REPO_ROOT))
    assert code == 0 and err == ""
    lines = out.split("\n")[:-1]
    assert len(lines) == len(REGISTER)
    marked = frozenset(
        line.split()[0] for line in lines if BELOW_FLOOR_SUFFIX in line and line.split()
    )
    assert marked == _below_floor_ids(floor), (
        f"default floor {floor}: suffix set {sorted(marked)!r} != derived below-floor "
        f"set {sorted(_below_floor_ids(floor))!r}"
    )


# ---------------------------------------------------------------------------
# Behaviors 6 and 7 -- the surface-wide brake.
# ---------------------------------------------------------------------------

#: The minimal argv for every verb, over a zero-record register. Keyed by the LABEL an
#: operator reads in a failure report; `verb` is what the parser registers, so the
#: `--json` twins share a verb with their plain form.
BRAKE_TABLE = (
    ("validate", "validate", lambda e, e2: ("validate", e)),
    ("list", "list", lambda e, e2: ("list", e)),
    ("list --json", "list", lambda e, e2: ("list", e, "--json")),
    ("report", "report", lambda e, e2: ("report", e)),
    ("prd", "prd", lambda e, e2: ("prd", e)),
    ("show", "show", lambda e, e2: ("show", "GAP-001", e)),
    ("taxonomy", "taxonomy", lambda e, e2: ("taxonomy",)),
    ("diff", "diff", lambda e, e2: ("diff", e, e2)),
    ("scan", "scan", lambda e, e2: ("scan", e, "--gaps", e)),
    ("scan --json", "scan", lambda e, e2: ("scan", e, "--gaps", e, "--json")),
)


def _brake_results(tmp_path):
    """Run every row of the brake table, returning `(label, exit, stdout, stderr)`."""
    first = _zero_record_register(tmp_path / "e")
    second = _zero_record_register(tmp_path / "e2")
    results = []
    for label, _verb, argv in BRAKE_TABLE:
        code, out, err = run(argv(first, second))
        results.append((label, code, out, err))
    return results


def _brake_report(results):
    """Every invocation's exit code and stdout byte count, as behavior 7 requires."""
    return "; ".join(
        f"{label}: exit={code} stdout={len(out)}B" for label, code, out, _err in results
    )


def _one_newline_violations(results):
    """The brake's judgement. Returns a list of human-readable violations.

    Factored out so the checker itself can be proved two-sided against planted results
    in this same run -- a checker that cannot fail is not evidence.
    """
    violations = []
    for label, code, out, err in results:
        if code not in ALLOWED_EXITS:
            violations.append(f"{label}: exit {code} is neither 0 nor 2")
            continue
        if code == 0:
            if out == "":
                violations.append(f"{label}: exit 0 wrote ZERO stdout bytes")
            elif not out.endswith("\n"):
                violations.append(f"{label}: exit 0 stdout does not end in a newline")
            elif out.endswith("\n\n"):
                violations.append(f"{label}: exit 0 stdout ends in TWO newlines")
        else:
            if out != "":
                violations.append(
                    f"{label}: exit 2 wrote {len(out)} stdout byte(s); stdout must carry "
                    "only the document"
                )
            if not err.startswith(ERROR_PREFIX):
                violations.append(
                    f"{label}: exit 2 stderr does not begin {ERROR_PREFIX!r}: {err[:60]!r}"
                )
    return violations


def test_brake_table_covers_exactly_the_parsers_verbs():
    """Behavior 6: the brake's verb set EQUALS `build_parser()`'s subparser choices.

    Both directions, so a ninth verb cannot ship unexercised and a retired verb cannot
    leave a dead row behind.
    """
    registered = frozenset(parser_surface())
    assert registered, "parser_surface() returned no verbs, so this comparison is vacuous"
    exercised = frozenset(verb for _label, verb, _argv in BRAKE_TABLE)
    assert exercised == registered, (
        f"brake domain drifted from the parser: unexercised verb(s)="
        f"{sorted(registered - exercised)!r}, invented verb(s)="
        f"{sorted(exercised - registered)!r}"
    )


def test_every_exit_zero_verb_ends_in_exactly_one_newline(tmp_path):
    """Behaviors 6 and 7: the brake itself, with its domain asserted non-empty first."""
    results = _brake_results(tmp_path)
    report = _brake_report(results)

    green = [row for row in results if row[1] == 0]
    assert len(green) >= 6, (
        f"brake domain collapsed: only {len(green)} invocation(s) returned 0, so the "
        f"one-newline assertion is nearly vacuous. {report}"
    )

    violations = _one_newline_violations(results)
    assert violations == [], (
        "the one-newline guarantee fails on the verb surface: "
        + " | ".join(violations)
        + f". Full domain: {report}"
    )


def test_brake_report_names_every_invocation_exit_and_byte_count(tmp_path):
    """Behavior 7: the failure message names every invocation's exit and stdout size."""
    results = _brake_results(tmp_path)
    report = _brake_report(results)
    for label, code, out, _err in results:
        assert label in report, f"report omits invocation {label!r}: {report}"
        assert f"exit={code}" in report, f"report omits {label!r}'s exit {code}: {report}"
        assert f"{len(out)}B" in report, (
            f"report omits {label!r}'s stdout byte count {len(out)}: {report}"
        )
    assert len(report.split(";")) == len(BRAKE_TABLE), (
        f"report has {len(report.split(';'))} field group(s) for {len(BRAKE_TABLE)} "
        f"invocation(s): {report}"
    )


@pytest.mark.parametrize(
    "planted, expect_fragment",
    [
        ([("v", 0, "", "")], "ZERO stdout bytes"),
        ([("v", 0, "body", "")], "does not end in a newline"),
        ([("v", 0, "body\n\n", "")], "TWO newlines"),
        ([("v", 2, "leaked\n", "Error: x\n")], "stdout byte(s)"),
        ([("v", 2, "", "boom\n")], "does not begin"),
        ([("v", 1, "", "")], "neither 0 nor 2"),
    ],
)
def test_one_newline_checker_is_two_sided_on_planted_results(planted, expect_fragment):
    """The checker must FIRE on each shape it exists to catch."""
    violations = _one_newline_violations(planted)
    assert violations, f"checker passed a known-bad result {planted!r}"
    assert any(expect_fragment in v for v in violations), (
        f"checker fired but named the wrong thing for {planted!r}: {violations!r}"
    )


def test_one_newline_checker_passes_known_good_results():
    """...and must NOT fire on the shapes the contract allows."""
    good = [
        ("ok-doc", 0, "one line\n", ""),
        ("ok-bare-newline", 0, "\n", ""),
        ("ok-error", 2, "", "Error: no gap records found\n"),
    ]
    assert _one_newline_violations(good) == [], (
        f"checker rejected contract-conforming results: {_one_newline_violations(good)!r}"
    )


def test_no_absolute_machine_path_or_home_dir_is_written_down():
    """Public-repo bar: this file must name no machine path and no user identifier.

    The forbidden tokens are ASSEMBLED from character codes rather than written as
    literals. Spelling them out makes the check fail on its own payload -- a fail-CLOSED
    detector that blocks a correct file, which is this product's own recorded failure
    shape -- and it would also put the very strings the public-repo bar forbids into a
    public file.
    """
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    slash, backslash = chr(47), chr(92)
    forbidden = (
        f"{slash}Users{slash}",
        f"{slash}home{slash}",
        f"{slash}var{slash}folders{slash}",
        f"C:{backslash}",
    )
    # Two-sided: the matcher must FIRE on a planted sample, or its silence means nothing.
    planted = f"prefix{forbidden[0]}someone{slash}repo"
    assert any(token in planted for token in forbidden), (
        "the forbidden-token matcher does not fire on a planted absolute path, so its "
        "verdict about this file is not evidence"
    )
    for token in forbidden:
        assert token not in text, f"absolute machine path {token!r} in this file"
    # The register path this file prints in failure messages is always a `tmp_path`
    # produced at run time, never a literal, so there is nothing else to redact.
    assert re.search(r"parents\[1\]", text), (
        "the repo root must stay derived from __file__, not written down"
    )
