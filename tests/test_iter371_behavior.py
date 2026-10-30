"""Iteration 371 behaviors: README's Quickstart shows every flag the parser accepts.

WHY THIS EXISTS
`docs/CONSUMER_CONTRACT.md` is held to `build_parser()` by a set-equality brake
(`tests/_surface_contract.py`), but README had no brake, so it drifted: at `00cf58b`
fourteen (verb, flag) pairs -- including iteration 366's headline `list --match` and the
confidence-floor knob `--floor` that the core invariant turns on -- appeared in no
README example a builder could copy.

WHY CONTAINMENT ONE WAY PLUS "NO INVENTED FLAGS", NOT SET EQUALITY
README is prose for a human: several flags may share one example line and a flag may be
shown more than once. So the rule is that every parser flag is SHOWN for its own verb
(forward), and that no example names a flag its verb does not accept (reverse).

WHY THE EXPECTATION IS INTROSPECTED
The expected pairs come from `parser_surface()`, never from a hand-written list: a
listed expectation is the same artifact as the hand-copied README, one directory over,
and would drift the same way. The mutation proofs below show the checker reports a
missing pair BY NAME, both when README loses a line and when the parser gains a flag.

WHY A SEGMENT, NOT A LINE
A line such as `scan ... --json > b.json && scan ... --baseline b.json` carries two
invocations; a flag counts only inside the `radar VERB` segment that owns it (up to the
next `&&` or `#`), so documentation of one verb cannot satisfy an assertion about
another, and a comment ABOUT a flag cannot satisfy an assertion about the invocation.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import pathlib
import re
import shlex
import sys

import pytest

from agent_gap_radar import cli

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _surface_contract import VerbSurface, parser_surface  # noqa: E402  (oracle)

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"

_INVOCATION = re.compile(r"(?<![\w-])radar ([a-z][\w-]*)(?![\w-])")
_FLAG = re.compile(r"(?<![\w-])(--[a-z][\w-]*)(?![\w-])")

#: Verbs whose example lines run against this repo's own register; `scan` and `diff`
#: name placeholder paths (`../my-service`, `OLD NEW`) and are out of scope.
_RUNNABLE_VERBS = frozenset({"validate", "list", "report", "show", "prd", "taxonomy"})


def readme_text() -> str:
    """README as read now; a function so a mutation can work on an in-memory copy."""
    return README.read_text(encoding="utf-8")


def fenced_lines(text: str) -> list[str]:
    """Every line strictly inside a ``` fence, in document order."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            lines.append(line)
    return lines


def quickstart_lines(text: str) -> list[str]:
    """The fenced lines of the first code block under `## Quickstart`."""
    _, _, after = text.partition("\n## Quickstart\n")
    assert after, "README has no `## Quickstart` heading"
    section = after.split("\n## ", 1)[0]
    return fenced_lines(section)


def invocations(line: str) -> list[tuple[str, str]]:
    """(verb, segment) for every `radar VERB` before the line's comment.

    A segment runs from the verb to the next `&&`; the comment is cut first, so a
    flag named in prose after `#` never counts as shown.
    """
    code = line.split("#", 1)[0]
    found: list[tuple[str, str]] = []
    for part in code.split("&&"):
        for match in _INVOCATION.finditer(part):
            found.append((match.group(1), part[match.end():]))
    return found


def shown_pairs(text: str) -> set[tuple[str, str]]:
    """Every (verb, flag) an example line in a fence actually carries."""
    return {(verb, flag)
            for line in fenced_lines(text)
            for verb, segment in invocations(line)
            for flag in _FLAG.findall(segment)}


def missing_pairs(text: str, surface: dict[str, VerbSurface]) -> set[tuple[str, str]]:
    """Parser (verb, option) pairs no README example shows: the forward rule."""
    expected = {(verb, option)
                for verb, verb_surface in surface.items()
                for option in verb_surface.options}
    return expected - shown_pairs(text)


def invented_pairs(text: str, surface: dict[str, VerbSurface]) -> set[tuple[str, str]]:
    """README (verb, flag) pairs the parser does not accept: the reverse rule."""
    return {(verb, flag) for verb, flag in shown_pairs(text)
            if verb not in surface or flag not in surface[verb].options}


def runnable_argvs(text: str) -> list[list[str]]:
    """Quickstart examples that run in-process against this repo's own register."""
    argvs: list[list[str]] = []
    for line in quickstart_lines(text):
        if not line.startswith("uv run radar "):
            continue
        code = line.split("#", 1)[0]
        if any(token in code for token in (">", "|", "&&")):
            continue
        argv = shlex.split(code)[3:]
        if argv and argv[0] in _RUNNABLE_VERBS:
            argvs.append(argv)
    return argvs


# -- behavior 1: forward coverage ---------------------------------------------------

def test_b1_every_parser_flag_is_shown_for_its_own_verb():
    assert missing_pairs(readme_text(), parser_surface()) == set()


def test_b1_the_surface_is_not_empty_so_the_green_means_something():
    surface = parser_surface()
    assert sum(len(s.options) for s in surface.values()) > 0
    assert shown_pairs(readme_text())


# -- behavior 2: no invented flags --------------------------------------------------

def test_b2_no_example_names_a_flag_its_verb_does_not_accept():
    assert invented_pairs(readme_text(), parser_surface()) == set()


def test_b2_an_invented_flag_is_reported_by_name():
    text = readme_text().replace("uv run radar list .              #",
                                 "uv run radar list . --zzz        #", 1)
    assert invented_pairs(text, parser_surface()) == {("list", "--zzz")}


def test_b2_a_flag_in_a_comment_does_not_count_as_shown():
    assert invocations("uv run radar list .  # see --match") == [("list", " .  ")]


# -- behavior 3: introspected, with two mutation proofs -----------------------------

def test_b3a_removing_one_example_line_reports_exactly_that_pair():
    lines = readme_text().splitlines(keepends=True)
    target = [ln for ln in lines if ln.startswith("uv run radar list") and "--match" in ln]
    assert len(target) == 1, target
    text = "".join(ln for ln in lines if ln is not target[0])
    assert missing_pairs(text, parser_surface()) == {("list", "--match")}


def test_b3b_a_new_parser_flag_is_reported_until_readme_shows_it():
    surface = dict(parser_surface())
    surface["list"] = dataclasses.replace(
        surface["list"], options=surface["list"].options | {"--zzz"})
    assert missing_pairs(readme_text(), surface) == {("list", "--zzz")}


# -- behavior 4: the examples run ---------------------------------------------------

def _runnable_ids() -> list[str]:
    return [" ".join(argv) for argv in runnable_argvs(readme_text())]


@pytest.mark.parametrize("argv_text", _runnable_ids())
def test_b4_every_runnable_quickstart_example_exits_zero_with_output(
        argv_text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(shlex.split(argv_text))
    assert code == 0, argv_text
    assert out.getvalue().strip(), argv_text


def test_b4_the_new_flag_examples_are_among_the_runnable_ones():
    flagged = {argv[0] for argv in runnable_argvs(readme_text())
               if any(token.startswith("--") for token in argv)}
    assert {"list", "report", "prd"} <= flagged


# -- behavior 6: existing lines survive, only lines are added -----------------------

#: The Quickstart lines that predate iteration 371, in order. Pinned as a SUBSEQUENCE:
#: new example lines may sit between them, but none of these may change or move.
PRE_371_LINES = (
    "uv sync",
    "uv run radar validate .          # schema-check every record; exit 2 on any problem or on zero records",
    "uv run radar list .              # one line per record, below-floor rows flagged",
    "uv run radar report .            # the full ranked radar (markdown)",
    "uv run radar show GAP-003 .      # one gap in depth, with evidence and quotes",
    "uv run radar show GAP-003 . --json  # the same gap as a stable JSON object, for a consumer",
    "uv run radar prd .               # emit a build-loop prd.json for the top gap",
    "uv run radar taxonomy            # the fixed vocabularies",
    "uv run radar taxonomy --json     # the same vocabularies as one object, for a consumer",
    "uv run radar diff OLD NEW        # what changed between two register states (two directories you materialise)",
)


def test_b6_pre_existing_quickstart_lines_are_unchanged_and_in_order():
    remaining = iter(quickstart_lines(readme_text()))
    for expected in PRE_371_LINES:
        assert any(line == expected for line in remaining), expected


def test_b6_validate_and_taxonomy_lines_were_not_multiplied():
    lines = quickstart_lines(readme_text())
    assert sum(ln.startswith("uv run radar validate") for ln in lines) == 1
    assert sum(ln.startswith("uv run radar taxonomy") for ln in lines) == 2


def test_b6_no_new_comment_claims_a_record_count():
    for line in quickstart_lines(readme_text()):
        comment = line.split("#", 1)[1] if "#" in line else ""
        assert not re.search(r"\b\d+\s+(records?|gaps?)\b", comment), line


# == tester section (black-box, independent parsers) ===============================
#
# The checks above use regexes over the line. The checks below re-derive the same
# rules with a DIFFERENT tokenizer (`shlex`) and a DIFFERENT surface reader (walking
# `cli.build_parser()` directly, not `_surface_contract`), so one parser's blind spot
# cannot make both halves green. They then drive the behavior each new comment claims.

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402


def _tester_surface() -> dict[str, set[str]]:
    """verb -> long options, read straight off argparse (help excluded)."""
    parser = cli.build_parser()
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert subs, "build_parser() exposes no subcommands"
    return {verb: {opt for action in sub._actions for opt in action.option_strings
                   if opt.startswith("--") and opt != "--help"}
            for verb, sub in subs[0].choices.items()}


def _tester_segments(line: str) -> list[tuple[str, list[str]]]:
    """(verb, tokens) per `radar VERB` invocation, via shlex, comment and `&&` cut."""
    code = line.split("#", 1)[0]
    out: list[tuple[str, list[str]]] = []
    for part in code.split("&&"):
        try:
            tokens = shlex.split(part)
        except ValueError:
            continue
        for i, tok in enumerate(tokens[:-1]):
            if tok == "radar":
                out.append((tokens[i + 1], tokens[i + 2:]))
    return out


def _tester_shown(text: str) -> set[tuple[str, str]]:
    return {(verb, tok.split("=", 1)[0])
            for line in fenced_lines(text)
            for verb, tokens in _tester_segments(line)
            for tok in tokens if tok.startswith("--")}


def test_t1_shlex_coverage_every_build_parser_flag_is_shown():
    surface = _tester_surface()
    expected = {(v, f) for v, flags in surface.items() for f in flags}
    assert len(expected) >= 14
    assert expected - _tester_shown(readme_text()) == set()


def test_t1_the_two_surface_readers_agree():
    ours = _tester_surface()
    theirs = parser_surface()
    assert set(ours) == set(theirs)
    for verb in ours:
        assert ours[verb] == {o for o in theirs[verb].options if o.startswith("--")}, verb


def test_t2_shlex_reverse_no_example_names_an_unknown_verb_or_flag():
    surface = _tester_surface()
    bad = {(v, f) for v, f in _tester_shown(readme_text())
           if v not in surface or f not in surface[v]}
    assert bad == set()


def test_t2_a_flag_after_hash_is_not_shown_by_the_shlex_reader():
    assert _tester_shown("```\nuv run radar list .  # try --match\n```\n") == set()


def test_t3_dropping_any_single_flag_line_is_detected():
    """Every quickstart line that carries a flag is load-bearing OR redundant; the
    forward rule must name a pair for each flag that only one line shows."""
    text = readme_text()
    lines = text.splitlines(keepends=True)
    surface = parser_surface()
    detected = 0
    for idx, line in enumerate(lines):
        if not line.startswith("uv run radar ") or "--" not in line.split("#", 1)[0]:
            continue
        mutated = "".join(lines[:idx] + lines[idx + 1:])
        lost = missing_pairs(mutated, surface)
        others = shown_pairs(mutated)
        assert all(pair not in others for pair in lost)
        detected += bool(lost)
    assert detected >= 5


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, str]:
    monkeypatch.chdir(REPO_ROOT)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return code, out.getvalue()


def _comments_of(flag: str) -> list[str]:
    found = []
    for line in quickstart_lines(readme_text()):
        if "#" in line and any(flag in toks for _, toks in _tester_segments(line)):
            found.append(line.split("#", 1)[1])
    return found


def test_t5_every_floor_comment_names_the_parser_default():
    defaults = {v: cli.build_parser().parse_args([v, "."] if v not in ("diff",) else [v, "a", "b"])
                for v in ("list", "report", "prd")}
    for ns in defaults.values():
        assert ns.floor == 2
    comments = _comments_of("--floor")
    assert len(comments) >= 3, comments
    for comment in comments:
        assert "default 2" in comment, comment


def test_t5_match_comment_names_casefold_literal_and_below_floor():
    comments = _comments_of("--match")
    assert comments
    joined = " ".join(comments).lower()
    for phrase in ("case-folded", "literal substring", "below-floor"):
        assert phrase in joined, phrase


def test_t5_match_is_case_folded_in_behavior(monkeypatch):
    lower = _run(["list", ".", "--match", "memory"], monkeypatch)
    upper = _run(["list", ".", "--match", "MEMORY"], monkeypatch)
    assert lower[0] == upper[0] == 0
    assert lower[1] == upper[1] and lower[1].strip()


def test_t5_list_floor_flags_rows_never_drops_them(monkeypatch):
    base = _run(["list", "."], monkeypatch)
    for floor in ("3", "9"):
        code, out = _run(["list", ".", "--floor", floor], monkeypatch)
        assert code == 0
        assert len(out.splitlines()) == len(base[1].splitlines()), floor


def test_t5_floor_is_not_a_noop_on_the_documented_list_and_report_lines(monkeypatch):
    for argv in (["list", "."], ["report", ".", "--layer", "context-memory"]):
        low = _run(argv + ["--floor", "2"], monkeypatch)[1]
        high = _run(argv + ["--floor", "9"], monkeypatch)[1]
        assert low != high, argv


def test_t5_with_fixtures_inlines_contents_and_project_is_used(monkeypatch):
    plain = json.loads(_run(["prd", ".", "--gap", "GAP-003"], monkeypatch)[1])
    rich = json.loads(_run(["prd", ".", "--gap", "GAP-003", "--project", "my-agent",
                            "--with-fixtures"], monkeypatch)[1])
    assert rich["project"] == "my-agent"
    assert "badFixtures" not in json.dumps(plain)
    sample = rich["sourceGap"]["check"]["reproductionSample"]
    assert sample["badFixtures"] and sample["goodFixtures"]
    comment = " ".join(_comments_of("--with-fixtures"))
    assert "contents" in comment


def _register_copy(root: pathlib.Path, name: str, drop: int = 0) -> pathlib.Path:
    target = root / name / "gaps"
    target.mkdir(parents=True)
    records = sorted((REPO_ROOT / "gaps").glob("*.json"))
    for path in records[drop:]:
        shutil.copy(path, target / path.name)
    return root / name


def test_t5_diff_exit_code_matches_its_comment(tmp_path, monkeypatch):
    old = _register_copy(tmp_path, "old")
    lost = _register_copy(tmp_path, "lost", drop=1)
    empty = tmp_path / "empty"
    (empty / "gaps").mkdir(parents=True)
    assert _run(["diff", str(old), str(old), "--exit-code"], monkeypatch)[0] == 0
    assert _run(["diff", str(old), str(lost), "--exit-code"], monkeypatch)[0] == 1
    assert _run(["diff", str(empty), str(old), "--exit-code"], monkeypatch)[0] == 2
    comment = " ".join(_comments_of("--exit-code")[:1] + [
        c for c in _comments_of("--exit-code") if "OLD" in c])
    assert "exit 1" in comment and "2" in comment and "empty" in comment


def test_t5_diff_json_is_one_stable_object(tmp_path, monkeypatch):
    old = _register_copy(tmp_path, "old")
    lost = _register_copy(tmp_path, "lost", drop=1)
    first = _run(["diff", str(old), str(lost), "--json"], monkeypatch)
    again = _run(["diff", str(old), str(lost), "--json"], monkeypatch)
    assert first == again and first[0] == 0
    assert first[1].endswith("}\n") and not first[1].endswith("\n\n")
    assert len(json.loads(first[1])["removed"]) == 1


def test_t7_b12b_still_pins_exactly_one_bare_list_line():
    bare = [ln for ln in readme_text().splitlines()
            if ln.startswith("uv run radar list") and "--" not in ln.split("#", 1)[0]]
    assert len(bare) == 1 and "one line per record" in bare[0]
    assert "one line per ranked gap" not in readme_text()
