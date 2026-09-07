"""Iteration 124 behaviors: the `--register-cap` stand-down reaches the ONE summary line.

Roadmap row 80, bite 1. `research/CANDIDATE_CONTRACT.md` promises two unconditional
census lines -- `examined N candidates in <inbox>` and `N accepted, M rejected` -- so an
unattended caller can tell "there was nothing to do" from "the tool died". The capacity
path was the one outcome where a whole batch survives un-promoted and a human must
intervene, and it printed the opening census, skipped the summary, and exited 0: the exact
signature the promise exists to rule out, at the moment it most needs to be believed.

ISOLATION CONTRACT HONORED. Nothing here reads the implementation source to DERIVE an
expectation, and nothing reads the engineer's notes, the reviewer's notes, or a diff.
Every behavioral expectation (1-4) was measured by RUNNING `tools/promote.py` and reading
its stdout, its return value and the on-disk state of the inbox / register / rejected
directories. Behavior 5 reads `tools/promote.py` as DATA and asserts two COUNTS, which the
spec asks for by name. Behavior 6's expectations are the four tokens the spec names
verbatim plus tolerant, two-sided readers over `research/CANDIDATE_CONTRACT.md`.

Three structural notes, all to stop this file from lying later:

* Behavior 5 is the point of the iteration. A LEXICAL emitter count (the iteration-22
  brake) cannot see an early return: it proves the format string exists once and says
  nothing about whether every path reaches it. That blind spot is what let this defect
  live 35 iterations past the row that named it, with the prose pinned at both ends and
  the behavior pinned at neither. So behavior 5 keeps the lexical count AND adds a
  STRUCTURAL one -- the function that prints the summary holds exactly one `return`, so
  no branch can announce a census and then leave without a summary.
* Every census in this file is proven TWO-SIDED in this run against planted samples, and
  each real assertion reports its domain size, so an empty or unreadable input can never
  read as "exactly one". A census that cannot fail on a known-bad sample certifies itself
  while blind.
* This module deliberately spells the censused literal in its own planted samples and in
  its expected output lines. The census domain is `tools/promote.py` ONLY. If a future
  iteration widens that census to `tests/`, these samples are the first false hits --
  widen the domain and the samples must move to a fixture file, not be silently "fixed".
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "promote.py"
CONTRACT = REPO_ROOT / "research" / "CANDIDATE_CONTRACT.md"

sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import promote  # noqa: E402

from test_promote_gate import _distinct, _fresh_register  # noqa: E402

#: The opening census line, as the spec states it: `examined N candidates in <inbox>`.
CENSUS_RE = re.compile(r"examined (\d+) candidates")
#: The single summary emitter, as the spec states it: `N accepted, M rejected`.
SUMMARY_RE = re.compile(r"(\d+) accepted, (\d+) rejected")
#: Behavior 5(a)'s censused literal -- the summary format string, one emitter only.
SUMMARY_FORMAT_LITERAL = "accepted, "
#: The truncation vocabulary the contract must publish (behaviors 1, 2, 4, 6).
DEFERRED_PHRASE = "left for a later pass"
#: The dry-run suffix, measured from a real run of the tool in this repo.
DRY_RUN_SUFFIX = "  (dry run - pass --apply to write)"


# --------------------------------------------------------------------------- helpers


def _seed_inbox(tmp_path: pathlib.Path, n: int) -> pathlib.Path:
    """`n` candidates, each with its own check signature so novelty never refuses one."""
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (inbox / f"c{i}.json").write_text(
            json.dumps(_distinct(f"Iteration 124 waiting gap {i}", f"marker_i124_{i}")),
            encoding="utf-8",
        )
    return inbox


def _run(argv: list[str]) -> tuple[int, str]:
    """Run the tool in-process, returning `(return value, stdout)`."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = promote.main(argv)
    return rc, buf.getvalue()


def _last_non_empty_line(out: str) -> str:
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines, f"stdout carried no content at all: {out!r}"
    return lines[-1]


def _first_non_empty_line(out: str) -> str:
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines, f"stdout carried no content at all: {out!r}"
    return lines[0]


def _summary_line(out: str) -> str:
    """The one line matching the summary shape. Exactly one must exist."""
    hits = [ln for ln in out.splitlines() if SUMMARY_RE.search(ln)]
    assert len(hits) == 1, f"expected exactly one summary line, got {hits}\n{out}"
    return hits[0]


def _summary_counts(out: str) -> tuple[int, int]:
    m = SUMMARY_RE.search(out)
    assert m, f"no summary line at all in:\n{out}"
    return int(m.group(1)), int(m.group(2))


def _at_capacity(tmp_path: pathlib.Path, candidates: int):
    """A copied register of E records plus an inbox, wired so the cap is already met."""
    gaps = _fresh_register(tmp_path)
    existing = len(list(gaps.glob("*.json")))
    assert existing > 0, f"the copied register is empty: {gaps}"
    inbox = _seed_inbox(tmp_path, candidates)
    return gaps, existing, inbox


# ------------------------------------------------ behaviors 1-4: the PRE-FIX control


#: The capacity run's stdout as the spec records it being reproduced BEFORE this row:
#: opening census printed, announcement printed, ranked waiting list printed, summary
#: ABSENT, exit 0. Reproduced from the spec's own account of the defect, not from the
#: implementation. It exists so the behavioral readers below cannot pass while blind: a
#: test that asserts a line is PRESENT proves nothing until it is shown rejecting the
#: output that lacks it.
_PRE_FIX_CAPACITY_STDOUT = (
    "examined 3 candidates in /inbox\n"
    "REGISTER AT CAPACITY: 120 records, cap 120. 3 candidate(s) waiting; "
    "NOTHING was discarded.\n"
    "A human decides what the register carries from here. "
    "Strongest waiting candidates by evidence class:\n"
    "  c4 p 6.0  c0.json\n"
    "  c4 p 6.0  c1.json\n"
    "  c4 p 6.0  c2.json\n"
    "\n"
)


def test_b1_control_the_readers_reject_the_recorded_pre_fix_output():
    """Behaviors 1-2, control: the SAME readers must fail on the defect's own output.

    Every green assertion in this section is a substring or last-line check, and both
    kinds pass vacuously on a report that simply stops early -- which is precisely how a
    passing suite coexisted with this defect for 35 iterations. So the readers are run
    against the recorded pre-fix stdout here, in this run, and must reject it.
    """
    # The pre-fix output satisfies everything the OLD tests asserted...
    assert "examined 3 candidates" in _PRE_FIX_CAPACITY_STDOUT
    assert "REGISTER AT CAPACITY" in _PRE_FIX_CAPACITY_STDOUT
    assert "NOTHING was discarded" in _PRE_FIX_CAPACITY_STDOUT
    # ...and fails the two this iteration adds.
    assert SUMMARY_RE.search(_PRE_FIX_CAPACITY_STDOUT) is None, (
        "the pre-fix sample already carries a summary, so it cannot control anything"
    )
    assert _last_non_empty_line(_PRE_FIX_CAPACITY_STDOUT) != (
        f"0 accepted, 0 rejected, 3 {DEFERRED_PHRASE}{DRY_RUN_SUFFIX}"
    )
    with pytest.raises(AssertionError):
        _summary_line(_PRE_FIX_CAPACITY_STDOUT)
    with pytest.raises(AssertionError):
        _summary_counts(_PRE_FIX_CAPACITY_STDOUT)


# ------------------------------------- behavior 1: capacity, dry run, non-empty inbox


def test_b1_capacity_dry_run_keeps_census_announcement_waiting_list_and_summary(tmp_path):
    """Behavior 1: nothing the capacity path already said is lost, and the summary lands.

    This is the regression that matters: before this row the run below printed the census
    and the announcement, then returned before the summary, and exited 0.
    """
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    rc, out = _run(
        ["--inbox", str(inbox), "--gaps", str(gaps), "--register-cap", str(existing)]
    )
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert f"examined 3 candidates in {inbox}" in out, out
    assert f"REGISTER AT CAPACITY: {existing} records, cap {existing}." in out, out
    assert "NOTHING was discarded" in out, out
    for i in range(3):
        assert f"c{i}.json" in out, f"the ranked waiting list dropped c{i}.json\n{out}"
    assert _last_non_empty_line(out) == (
        f"0 accepted, 0 rejected, 3 {DEFERRED_PHRASE}{DRY_RUN_SUFFIX}"
    ), out


def test_b1_capacity_dry_run_census_precedes_the_summary(tmp_path):
    """Behavior 1, ordering: the census opens the report and the summary closes it.

    A summary that appeared BEFORE the census would satisfy a substring check and still
    leave a reader unable to bracket the run.
    """
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    _rc, out = _run(
        ["--inbox", str(inbox), "--gaps", str(gaps), "--register-cap", str(existing)]
    )
    assert out.index("examined 3 candidates") < out.index("0 accepted, 0 rejected"), out


def test_b1_capacity_dry_run_opens_with_the_census_line(tmp_path):
    """Behavior 1, the word "opens": the census is the FIRST content line, not just present.

    An unattended caller brackets a run by its first and last lines, and a substring check
    cannot tell an opening census from one buried under a banner.
    """
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    _rc, out = _run(
        ["--inbox", str(inbox), "--gaps", str(gaps), "--register-cap", str(existing)]
    )
    assert _first_non_empty_line(out) == f"examined 3 candidates in {inbox}", out


@pytest.mark.parametrize("waiting", [1, 2, 5])
def test_b1_capacity_deferred_count_is_derived_from_the_inbox(tmp_path, waiting):
    """Behavior 1, the counts are DERIVED rather than spelled for one sample size.

    Every other assertion in this file compares the summary against a line built for an
    inbox of 3, and a hardcoded `3` would satisfy all of them. Measured here at 1, 2 and 5:
    the deferred count follows the inbox, and both verdict counts stay 0.
    """
    gaps, existing, inbox = _at_capacity(tmp_path, waiting)
    rc, out = _run(
        ["--inbox", str(inbox), "--gaps", str(gaps), "--register-cap", str(existing)]
    )
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert _first_non_empty_line(out) == f"examined {waiting} candidates in {inbox}", out
    assert _summary_counts(out) == (0, 0), out
    assert _last_non_empty_line(out) == (
        f"0 accepted, 0 rejected, {waiting} {DEFERRED_PHRASE}{DRY_RUN_SUFFIX}"
    ), out
    assert len(list(inbox.glob("*.json"))) == waiting, (
        f"a dry run moved a candidate out of the inbox\n{out}"
    )


def test_b1_capacity_dry_run_as_a_subprocess_signals_a_live_run(tmp_path):
    """Behavior 1 through the door the unattended consumer actually uses.

    The declared research driver runs this tool as a child process and treats a missing
    summary as "the tool died", so the process-level facts are the contract: exit status
    0, a census on stdout, and a summary on stdout.
    """
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    proc = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--inbox",
            str(inbox),
            "--gaps",
            str(gaps),
            "--register-cap",
            str(existing),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr!r}\nstdout={proc.stdout!r}"
    assert "REGISTER AT CAPACITY" in proc.stdout, proc.stdout
    assert SUMMARY_RE.search(proc.stdout), (
        "a capacity run printed no summary through the process boundary, which is the "
        f"exact signature the contract promises to rule out:\n{proc.stdout}"
    )


# ------------------------------------------------------ behavior 2: capacity, --apply


def test_b2_capacity_apply_prints_the_summary_without_the_dry_run_suffix(tmp_path):
    """Behavior 2: `--apply` at capacity reports the same three counts, no suffix."""
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    rejected = tmp_path / "rejected"
    rc, out = _run(
        [
            "--inbox",
            str(inbox),
            "--gaps",
            str(gaps),
            "--apply",
            "--register-cap",
            str(existing),
            "--rejected",
            str(rejected),
        ]
    )
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert _last_non_empty_line(out) == f"0 accepted, 0 rejected, 3 {DEFERRED_PHRASE}", out
    assert "dry run" not in out, out


def test_b2_capacity_apply_writes_absolutely_nothing(tmp_path):
    """Behavior 2, the on-disk half: a stand-down must not touch a single file."""
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    rejected = tmp_path / "rejected"
    before = sorted(p.name for p in inbox.glob("*.json"))
    rc, out = _run(
        [
            "--inbox",
            str(inbox),
            "--gaps",
            str(gaps),
            "--apply",
            "--register-cap",
            str(existing),
            "--rejected",
            str(rejected),
        ]
    )
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert sorted(p.name for p in inbox.glob("*.json")) == before, (
        f"candidates moved out of the inbox on a stand-down\n{out}"
    )
    assert len(before) == 3, before
    assert len(list(gaps.glob("*.json"))) == existing, (
        f"the register grew past its cap\n{out}"
    )
    assert not rejected.exists(), (
        f"a stand-down created the rejected directory {rejected}, which tells a reader "
        f"something was refused\n{out}"
    )


@pytest.mark.parametrize("apply_", [False, True])
def test_b2_capacity_prints_no_per_candidate_verdict_at_all(tmp_path, apply_):
    """Behaviors 1-2: the run must not contradict its own `0 accepted, 0 rejected`.

    The two counts are a claim about what happened, and the per-candidate decision lines
    are the other half of the same report. A stand-down decided nothing, so neither an
    `ACCEPT` nor a `REJECT` line may appear beside a summary that says zero of each --
    otherwise a reader has to guess which half of one report to believe.
    """
    gaps, existing, inbox = _at_capacity(tmp_path, 3)
    argv = ["--inbox", str(inbox), "--gaps", str(gaps), "--register-cap", str(existing)]
    if apply_:
        argv += ["--apply", "--rejected", str(tmp_path / "rejected")]
    rc, out = _run(argv)
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert _summary_counts(out) == (0, 0), out
    assert out.count("ACCEPT") == 0, f"a stand-down announced an accept\n{out}"
    assert out.count("REJECT") == 0, f"a stand-down announced a reject\n{out}"


# -------------------------------------------------- behavior 3: capacity, empty inbox


@pytest.mark.parametrize("apply_", [False, True])
def test_b3_capacity_empty_inbox_summary_omits_the_deferred_clause(tmp_path, apply_):
    """Behavior 3: zero examined, zero accepted, zero rejected, and nothing deferred.

    The deferred clause counts candidates a human must come back to. With an empty inbox
    there are none, so printing it would invent work.
    """
    gaps = _fresh_register(tmp_path)
    existing = len(list(gaps.glob("*.json")))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    argv = ["--inbox", str(inbox), "--gaps", str(gaps), "--register-cap", str(existing)]
    if apply_:
        argv += ["--apply", "--rejected", str(tmp_path / "rejected")]
    rc, out = _run(argv)
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert f"examined 0 candidates in {inbox}" in out, out
    line = _summary_line(out)
    assert _summary_counts(out) == (0, 0), out
    assert DEFERRED_PHRASE not in line, (
        f"an empty inbox deferred something: {line!r}\n{out}"
    )


# ------------------------------- behavior 4: truncation is neither accept nor reject


def test_b4_limit_defers_the_remainder_without_accepting_or_rejecting_it(tmp_path):
    """Behavior 4: below capacity, `--limit 1` over 3 candidates.

    One lands, two WAIT. The two are not refusals: they keep their inbox file and get no
    reason file, so a reader who does not find an ACCEPT line for their filename has not
    been told no.
    """
    gaps = _fresh_register(tmp_path)
    existing = len(list(gaps.glob("*.json")))
    inbox = _seed_inbox(tmp_path, 3)
    rejected = tmp_path / "rejected"
    rc, out = _run(
        [
            "--inbox",
            str(inbox),
            "--gaps",
            str(gaps),
            "--apply",
            "--limit",
            "1",
            "--rejected",
            str(rejected),
        ]
    )
    assert rc == 0, f"rc={rc!r}\n{out}"
    assert out.count("ACCEPT") == 1, out
    assert _summary_line(out) == f"1 accepted, 0 rejected, 2 {DEFERRED_PHRASE}", out
    assert len(list(gaps.glob("*.json"))) == existing + 1, (
        f"the register should grow by exactly one\n{out}"
    )
    assert len(list(inbox.glob("*.json"))) == 2, (
        f"the two deferred candidates must survive in the inbox\n{out}"
    )
    assert list(rejected.glob("**/*.reason.txt")) == [], (
        f"a deferred candidate was given a refusal reason\n{out}"
    )


# ---------------------------- behavior 5: the promise is structural, not per-path


def _own_nodes(func: ast.AST):
    """Every node inside `func` that is NOT inside a nested function or class.

    A nested helper's `return` belongs to the helper, not to the emitter.
    """
    boundary = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
    out = []
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        out.append(node)
        if isinstance(node, boundary):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return out


def _emitter_functions(source: str) -> list[tuple[str, int]]:
    """`(function name, count of its own `return` statements)` for each summary emitter.

    A function is an emitter when one of ITS OWN string constants carries the summary
    format literal. Returns one entry per emitter, so a second emitter is visible here
    as a second entry rather than being silently collapsed.
    """
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        own = _own_nodes(node)
        prints_summary = any(
            isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and SUMMARY_FORMAT_LITERAL in n.value
            for n in own
        )
        if not prints_summary:
            continue
        returns = sum(1 for n in own if isinstance(n, ast.Return))
        found.append((node.name, returns))
    return found


_TWO_RETURN_EMITTER = (
    "def main(argv=None):\n"
    "    if at_capacity:\n"
    "        print('REGISTER AT CAPACITY')\n"
    "        return 0\n"
    "    print(f'{n} accepted, {m} rejected')\n"
    "    return 0\n"
)
_ONE_RETURN_EMITTER = (
    "def main(argv=None):\n"
    "    if at_capacity:\n"
    "        print('REGISTER AT CAPACITY')\n"
    "    print(f'{n} accepted, {m} rejected')\n"
    "    return 0\n"
)
_NESTED_HELPER_EMITTER = (
    "def main(argv=None):\n"
    "    def score(x):\n"
    "        return x * 2\n"
    "    print(f'{n} accepted, {m} rejected')\n"
    "    return 0\n"
)
_NO_EMITTER = "def main(argv=None):\n    print('nothing to report')\n    return 0\n"


def test_b5_control_the_return_census_is_two_sided_and_boundary_aware():
    """Behavior 5, control: the structural counter must fire on the KNOWN-BAD shape.

    Proven here, in this run, against a planted early-return-before-the-summary sample
    that is the defect this row fixes. A census that cannot fail on a known-bad sample
    certifies itself while blind.
    """
    assert _emitter_functions(_TWO_RETURN_EMITTER) == [("main", 2)], _TWO_RETURN_EMITTER
    assert _emitter_functions(_ONE_RETURN_EMITTER) == [("main", 1)], _ONE_RETURN_EMITTER
    assert _emitter_functions(_NESTED_HELPER_EMITTER) == [("main", 1)], (
        "a nested helper's return must not be charged to the emitter"
    )
    assert _emitter_functions(_NO_EMITTER) == [], _NO_EMITTER


def test_b5_control_the_lexical_census_is_two_sided():
    """Behavior 5(a), control: the iteration-22 lexical matcher, re-proven here."""
    assert _TWO_RETURN_EMITTER.count(SUMMARY_FORMAT_LITERAL) == 1
    assert (_ONE_RETURN_EMITTER + _TWO_RETURN_EMITTER).count(SUMMARY_FORMAT_LITERAL) == 2
    assert _NO_EMITTER.count(SUMMARY_FORMAT_LITERAL) == 0


def test_b5_promote_holds_exactly_one_summary_emitter_lexically():
    """Behavior 5(a): the format literal occurs once, as the iteration-22 brake asserts.

    Kept here because 5(b) is only meaningful once 5(a) pins the emitter to a single
    site: two literals would mean the structural count below was measuring one of two.
    """
    text = TOOL.read_text(encoding="utf-8")
    assert len(text) > 1000, f"census domain looks empty: {len(text)} bytes of {TOOL.name}"
    found = text.count(SUMMARY_FORMAT_LITERAL)
    assert found == 1, (
        f"{TOOL.name} spells {SUMMARY_FORMAT_LITERAL!r} {found} times; the summary must "
        "have exactly one emitter"
    )


def test_b5_the_summary_emitting_function_has_exactly_one_return():
    """Behavior 5(b): NO branch can reach the census line and skip the summary.

    A LEXICAL emitter count cannot see an early return -- it proves the format string
    exists once and says nothing about which paths reach it. That blind spot is what let
    this defect live 35 iterations past the row that named it: the prose was pinned at
    both ends and the behavior at neither. One `return` in the emitting function makes
    the promise structural instead of per-path, so a future branch cannot re-open it
    without turning this test red.
    """
    text = TOOL.read_text(encoding="utf-8")
    assert len(text) > 1000, f"census domain looks empty: {len(text)} bytes of {TOOL.name}"
    emitters = _emitter_functions(text)
    assert len(emitters) == 1, (
        f"expected exactly one function to print the summary, found {emitters}"
    )
    name, returns = emitters[0]
    assert returns == 1, (
        f"{TOOL.name}:{name}() holds {returns} return statements; more than one means a "
        "branch can announce a census and then leave without a summary, which is the "
        "defect roadmap row 80 names"
    )


# ------------------------- behavior 6: the contract publishes the deferred outcome


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _normalized(text: str) -> str:
    """Whitespace-collapsed view of a document.

    A documented token that a line wrap splits is invisible to a raw `token in text`
    check, and a markdown reader joins those lines anyway -- so the honest question is
    whether the DOCUMENT names the token, not whether the bytes happen to keep it on one
    line. Normalizing is strictly more permissive than raw matching, so it cannot pass a
    document that omits a token.
    """
    return re.sub(r"\s+", " ", text)


def _unconditional_paragraphs(text: str, marker: str) -> list[str]:
    """Paragraphs promising `marker` on EVERY run, in tolerant wording."""
    return [
        p
        for p in _paragraphs(text)
        if marker in _normalized(p)
        and re.search(r"every run|always|unconditional|in all cases|no matter", p, re.I)
    ]


def _weakened_paragraphs(text: str) -> list[str]:
    """Paragraphs that promise a census line and then carve out the capacity case.

    This row DECIDED that the code falls through rather than the contract gaining an
    except-at-capacity clause, because a promise read by unattended agents may not buy
    its own accuracy by retracting the guarantee its readers depend on.
    """
    out = []
    for p in _paragraphs(text):
        flat = _normalized(p)
        if "examined" not in flat and SUMMARY_FORMAT_LITERAL not in flat:
            continue
        if not re.search(r"\bexcept\b|\bunless\b", flat, re.I):
            continue
        if not re.search(r"capacit|\bcap\b|--register-cap", flat, re.I):
            continue
        out.append(p)
    return out


_WEAKENED_CONTRACT = (
    "# Candidate contract\n"
    "\n"
    "Every run prints `examined N candidates in <inbox>` and a summary line, except\n"
    "when the register is at capacity, where the run stands down early.\n"
)
_UNCONDITIONAL_CONTRACT = (
    "# Candidate contract\n"
    "\n"
    "Every run prints `examined N candidates in <inbox>`, including a run over an\n"
    "empty inbox and a run that stands down at capacity.\n"
    "\n"
    "Every run also closes with `N accepted, M rejected`, so a missing summary means\n"
    "the tool died rather than that it had nothing to do.\n"
)


def test_b6_control_the_contract_readers_are_two_sided():
    """Behavior 6, control: both readers proven on planted documents in this run."""
    assert _unconditional_paragraphs(_WEAKENED_CONTRACT, "examined"), _WEAKENED_CONTRACT
    assert _weakened_paragraphs(_WEAKENED_CONTRACT), (
        "the weakening reader missed an explicit except-at-capacity clause"
    )
    assert _unconditional_paragraphs(_UNCONDITIONAL_CONTRACT, "examined")
    assert _unconditional_paragraphs(_UNCONDITIONAL_CONTRACT, SUMMARY_FORMAT_LITERAL)
    assert _weakened_paragraphs(_UNCONDITIONAL_CONTRACT) == []
    assert _unconditional_paragraphs("# c\n\nexamined N candidates.\n", "examined") == []


@pytest.mark.parametrize(
    "token",
    ["--register-cap", "--limit", "REGISTER AT CAPACITY", DEFERRED_PHRASE],
)
def test_b6_contract_names_the_capacity_and_truncation_vocabulary(token):
    """Behavior 6: the four tokens the spec names, each present in the contract."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert len(text) > 1000, f"contract looks empty: {len(text)} bytes"
    assert token in _normalized(text), (
        f"{CONTRACT.name} never names {token!r}, so a research pass reading only the "
        "contract cannot recognise the outcome when it happens"
    )


def test_b6_contract_keeps_both_census_promises_unconditional():
    """Behavior 6: the promise is KEPT, not weakened -- no except-at-capacity clause."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert _unconditional_paragraphs(text, "examined"), (
        f"{CONTRACT.name} no longer promises the `examined N candidates` line on every run"
    )
    assert _unconditional_paragraphs(text, SUMMARY_FORMAT_LITERAL), (
        f"{CONTRACT.name} no longer promises the summary line on every run"
    )
    weakened = _weakened_paragraphs(text)
    assert weakened == [], (
        "the contract bought its own accuracy by retracting the guarantee its readers "
        f"depend on:\n{weakened}"
    )


#: The three facts behavior 6 requires the contract to state about a deferred candidate,
#: each as a TOLERANT reader. Deliberately wide: these are ANDed, they are scoped to the
#: paragraphs that already use the phrase, and a narrow version is a false red on a
#: correctly-written document. The middle one earned its width in this run -- the first
#: draft demanded "stays in the inbox" and the contract says "its file is still in the
#: inbox", which states the same fact.
_NOT_A_VERDICT_RE = re.compile(
    r"neither accepted nor rejected|not[^.]{0,40}accepted[^.]{0,40}rejected", re.I
)
_STILL_IN_INBOX_RE = re.compile(
    r"(?:stays?|remains?|still|sits|left|waits?)\b[^.]{0,40}in the inbox", re.I
)
_NO_REASON_FILE_RE = re.compile(
    r"no reason file|without a reason file|gets? no[^.]{0,20}reason|"
    r"no[^.]{0,20}reason file is written",
    re.I,
)

_DEFERRED_SILENT = (
    "At capacity the run reports every candidate as `left for a later pass` and exits 0.\n"
)
_DEFERRED_EXPLAINED = (
    "A candidate counted as `left for a later pass` was neither accepted NOR rejected:\n"
    "its file is still in the inbox, no reason file is written for it under the\n"
    "rejected directory, and a later pass will judge it unchanged.\n"
)


def test_b6_control_the_deferred_meaning_readers_are_two_sided():
    """Behavior 6, control: the three readers, proven on planted documents in this run.

    A tolerant matcher that cannot FAIL proves nothing about the document.
    """
    for reader in (_NOT_A_VERDICT_RE, _STILL_IN_INBOX_RE, _NO_REASON_FILE_RE):
        assert reader.search(_DEFERRED_EXPLAINED), reader.pattern
        assert not reader.search(_DEFERRED_SILENT), (
            f"{reader.pattern!r} fires on a document that explains nothing"
        )
    # The width the real contract needed, and the width it must NOT have: "in the inbox"
    # alone would pass a document that says a deferred file is DELETED from the inbox.
    assert _STILL_IN_INBOX_RE.search("its file is still in the inbox")
    assert _STILL_IN_INBOX_RE.search("the candidate stays in the inbox")
    assert not _STILL_IN_INBOX_RE.search("the file is removed from the inbox")


def test_b6_contract_states_a_deferred_candidate_is_not_a_refusal():
    """Behavior 6: what `left for a later pass` MEANS, in the document's own words.

    Three facts, tolerantly matched inside the paragraph(s) that use the phrase: the
    candidate was neither accepted nor rejected, it stays in the inbox for a later pass,
    and it gets no reason file -- so no ACCEPT line for your filename is not a refusal.
    """
    text = CONTRACT.read_text(encoding="utf-8")
    scoped = [p for p in _paragraphs(text) if DEFERRED_PHRASE in _normalized(p)]
    assert scoped, f"{CONTRACT.name} never uses {DEFERRED_PHRASE!r} in a paragraph"
    blob = _normalized("\n".join(scoped))
    assert _NOT_A_VERDICT_RE.search(blob), blob
    assert _STILL_IN_INBOX_RE.search(blob), blob
    assert _NO_REASON_FILE_RE.search(blob), blob
