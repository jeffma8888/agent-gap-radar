"""Iteration 399: the scan prefilter proves through ONE mandatory group alternation.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from ``pm.md``'s
Expected Behaviors 1-13. Nothing here reads the implementation source, the engineer's or
reviewer's notes, or any diff. Behaviors are measured by CALLING the public prover
functions (``checks.required_literals``, ``checks.required_literal_sets``, and the ASCII
twin ``checks._required_literal_sets_ascii`` the spec names), by running
``tools/scan_cost.py`` and ``radar`` as black boxes, and -- for "unchanged versus HEAD"
-- by running the SAME inputs through a ``git archive 110d1d5 src`` extract in a child
process whose ``PYTHONPATH`` is pinned to that extract (the child echoes its module file
so the oracle tree is proven).

Structural notes:

* The live-pattern census is IMPORTED from ``tests/test_iter99_behavior.py``, the
  committed definition of "live register content pattern" (iteration 117 precedent).
* This repo's tracked files are read as a CORPUS (a haystack for the soundness oracle),
  never as logic. The corpus oracle runs over every live pattern HEAD could NOT prove
  (the only place a new answer can appear, per behavior 9); HEAD-provable answers are
  pinned identical to HEAD and stay under ``test_iter99``'s whole-register sweep.
* Behavior 12's fixture-arm clause ("every check's good/bad arm gives the same verdict as
  at HEAD") is already enforced by ``test_iter394_behavior.py``'s sharded sweep, which
  compares every fixture arm's scan output to a pre-change extract; re-running ~480 arms
  per tree here would add ~1 minute to a suite whose preship budget is nearly spent, so
  this module covers the self-scan verbs, ``validate`` and REGISTER.md instead.
* No duration is asserted anywhere. Offline; every path derives from ``__file__`` or
  ``tmp_path``.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import checks
from test_iter99_behavior import _live_content_patterns

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
TOOL = REPO / "tools" / "scan_cost.py"
BASE_SHA = "110d1d5"

RL = checks.required_literals
RLS = checks.required_literal_sets
ASC = checks._required_literal_sets_ascii
PROVERS = {"RL": RL, "RLS": RLS, "ASC": ASC}

LOOKAROUND_OPENERS = ("(?=", "(?!", "(?<=", "(?<!")


def _sets(answer) -> set[frozenset[str]] | None:
    return None if answer is None else set(answer)


# --- behaviors 1-3: a mandatory group alternation is proved -------------------------


def test_b1_capturing_group_proves():
    assert RL(r"[ab](foo|bar)") == {"foo", "bar"}
    assert _sets(RLS(r"[ab](foo|bar)")) == {frozenset({"foo"}), frozenset({"bar"})}
    assert _sets(ASC(r"[ab](foo|bar)")) == {frozenset({"foo"}), frozenset({"bar"})}


def test_b2_non_capturing_group_with_word_boundaries_drops_optional_tail():
    pattern = r"\b(?:benchmark|evals?|leaderboard)\b"
    assert RL(pattern) == {"benchmark", "eval", "leaderboard"}
    assert _sets(RLS(pattern)) == {frozenset({"benchmark"}), frozenset({"eval"}),
                                   frozenset({"leaderboard"})}


def test_b3_plus_quantified_group_qualifies():
    assert RL(r"[ab](foo|bar)+") == {"foo", "bar"}
    assert _sets(RLS(r"[ab](foo|bar)+")) == {frozenset({"foo"}), frozenset({"bar"})}


# --- behaviors 4-6: groups that never qualify ----------------------------------------

OPTIONAL_OR_COUNTED = (
    r"[ab](foo|bar)?", r"[ab](foo|bar)*", r"[ab](foo|bar){0,2}", r"[ab](foo|bar){1,2}",
    r"[ab](foo|bar)??", r"[ab](?:foo)?",
)
UNPROVABLE_INTERIOR = (r"[ab](foo|\w+)", r"[ab](foo|)")
OTHER_GROUP_KINDS = (
    r"[ab](?=foo)", r"[ab](?!foo)", r"[ab](?<=foo)", r"[ab](?<!foo)",
    r"[ab](?P<n>foo|bar)", r"[ab](?i:foo|bar)",
)


@pytest.mark.parametrize("pattern", OPTIONAL_OR_COUNTED)
@pytest.mark.parametrize("prover", sorted(PROVERS))
def test_b4_optional_or_counted_group_never_qualifies(prover, pattern):
    assert PROVERS[prover](pattern) is None


@pytest.mark.parametrize("pattern", UNPROVABLE_INTERIOR)
@pytest.mark.parametrize("prover", sorted(PROVERS))
def test_b5_interior_with_unprovable_alternative_never_qualifies(prover, pattern):
    assert PROVERS[prover](pattern) is None


@pytest.mark.parametrize("pattern", OTHER_GROUP_KINDS)
@pytest.mark.parametrize("prover", ["RL", "RLS"])
def test_b6_other_group_kinds_never_qualify(prover, pattern):
    assert PROVERS[prover](pattern) is None


# --- behavior 7: the fold is carried into the group ---------------------------------


def test_b7_fold_is_carried_into_the_group():
    assert RL(r"(?i)[ab](Foo|BAR)") == {"foo", "bar"}


def test_b7_fold_unsafe_fragment_policy_applies_inside_the_group_unchanged():
    assert RL(r"(?i)[ab](foo|pass)") == RL("(?i)foo") | RL("(?i)pass")


def test_b7_ascii_twin_proves_whole_runs_inside_a_folded_group():
    assert _sets(ASC(r"(?i)[ab](foo|pass)")) == {frozenset({"foo"}), frozenset({"pass"})}


# --- behavior 8: a verbose flag makes a pattern unprovable --------------------------

VERBOSE = ("(?x)foo bar", "(?ix)foo bar", "(?x) foo|bar", r"(?x)[ab](f o o|bar)",
           "(?x:f o o)bar")


@pytest.mark.parametrize("pattern", VERBOSE)
@pytest.mark.parametrize("prover", sorted(PROVERS))
def test_b8_verbose_flag_means_unprovable(prover, pattern):
    assert PROVERS[prover](pattern) is None


@pytest.mark.parametrize("pattern", VERBOSE[:3])
def test_b8_guard_the_hole_is_real_the_regex_matches_foobar(pattern):
    """The spec's premise: each of these matches a text the old literal set lacks."""
    assert re.compile(pattern, re.MULTILINE).search("foobar")
    assert "foo bar" not in "foobar"


# --- HEAD extract oracle (behaviors 9, 11, 12) ---------------------------------------

_ANSWERS_DRIVER = r"""
import json, sys
import agent_gap_radar
from agent_gap_radar import checks
patterns = json.loads(sys.stdin.read())
def enc(a):
    if a is None:
        return None
    if isinstance(a, (set, frozenset)):
        return sorted(a)
    return [sorted(s) for s in a]
out = {}
for p in patterns:
    out[p] = [enc(checks.required_literals(p)), enc(checks.required_literal_sets(p)),
              enc(checks._required_literal_sets_ascii(p))]
print(json.dumps({"file": agent_gap_radar.__file__, "answers": out}))
"""

_CLI_DRIVER = r"""
import contextlib, io, json, sys
import agent_gap_radar
from agent_gap_radar.cli import main
jobs = json.loads(sys.stdin.read())
res = []
for argv in jobs:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    res.append([code, out.getvalue(), err.getvalue()])
print(json.dumps({"file": agent_gap_radar.__file__, "res": res}))
"""


@pytest.fixture(scope="module")
def head_src(tmp_path_factory) -> pathlib.Path:
    if not (REPO / ".git").exists():
        pytest.skip("no .git: cannot extract the pre-change tree")
    probe = subprocess.run(["git", "cat-file", "-e", f"{BASE_SHA}^{{commit}}"], cwd=REPO,
                           capture_output=True, check=False)
    if probe.returncode != 0:
        pytest.skip(f"{BASE_SHA} not available in this clone")
    dest = tmp_path_factory.mktemp("head_tree")
    archive = subprocess.run(["git", "archive", BASE_SHA, "src", "tools"], cwd=REPO,
                             capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
    return dest


def _run_child(src: pathlib.Path, driver: str, stdin: str) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(src)}
    return subprocess.Popen([sys.executable, "-c", driver], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=env, cwd=REPO)


def _finish(proc: subprocess.Popen, stdin: str, src: pathlib.Path) -> dict:
    out, err = proc.communicate(stdin)
    assert proc.returncode == 0, err[-2000:]
    doc = json.loads(out)
    assert pathlib.Path(doc["file"]).resolve().is_relative_to(src.resolve()), doc["file"]
    return doc


def _both(head: pathlib.Path, driver: str, payload) -> tuple[dict, dict]:
    """Run one driver over HEAD's extract and over the worktree, concurrently."""
    work = REPO / "src"
    stdin = json.dumps(payload)
    p_head = _run_child(head / "src", driver, stdin)
    p_work = _run_child(work, driver, stdin)
    # communicate() on each in turn; the second child keeps running meanwhile, and its
    # pipes are drained by its own communicate() call.
    return _finish(p_head, stdin, head / "src"), _finish(p_work, stdin, work)


def _enc(answer):
    if answer is None:
        return None
    if isinstance(answer, (set, frozenset)):
        return sorted(answer)
    return [sorted(s) for s in answer]


@pytest.fixture(scope="module")
def head_answers(head_src) -> dict:
    patterns = _live_content_patterns()
    head, work = _both(head_src, _ANSWERS_DRIVER, patterns)
    return {"head": head["answers"], "work": work["answers"], "patterns": patterns}


# --- behavior 9: provable answers are byte-for-byte unchanged -----------------------


def test_b9_every_head_provable_answer_is_unchanged_including_tuple_order(head_answers):
    head, work = head_answers["head"], head_answers["work"]
    compared = 0
    moved = []
    for pattern in head_answers["patterns"]:
        for slot, name in enumerate(("RL", "RLS", "ASC")):
            if head[pattern][slot] is None:
                continue
            compared += 1
            if work[pattern][slot] != head[pattern][slot]:
                moved.append((name, pattern, head[pattern][slot], work[pattern][slot]))
    assert compared > 300, compared
    assert moved == [], moved[:5]


def test_b9_the_in_process_worktree_is_the_one_the_child_measured(head_answers):
    for pattern in head_answers["patterns"][:50]:
        assert head_answers["work"][pattern] == [_enc(RL(pattern)), _enc(RLS(pattern)),
                                                 _enc(ASC(pattern))]


def test_b9_the_new_answers_are_reached_only_where_head_answered_none(head_answers):
    """Non-vacuity: the descent changed SOMETHING, and only in HEAD's None slots."""
    head, work = head_answers["head"], head_answers["work"]
    newly = [p for p in head_answers["patterns"]
             if head[p][1] is None and work[p][1] is not None]
    assert len(newly) >= 20, len(newly)


# --- behavior 10: soundness oracle, two-sided ----------------------------------------

SYNTHETIC = {
    r"[ab](foo|bar)": ["afoo", "bbar"],
    r"\b(?:benchmark|evals?|leaderboard)\b": ["the evals run", "a leaderboard"],
    r"[ab](foo|bar)+": ["afoobar"],
    r"(?i)[ab](Foo|BAR)": ["aFOO", "bbar"],
    r"(?i)[ab](foo|pass)": ["apass", "BFOO"],
    "(?x)foo bar": ["foobar"],
    "(?ix)foo bar": ["FOObar"],
    "(?x) foo|bar": ["bar"],
    r"(?x)[ab](f o o|bar)": ["afoo"],
    "(?x:f o o)bar": ["foobar"],
}
for _p in OPTIONAL_OR_COUNTED + UNPROVABLE_INTERIOR:
    SYNTHETIC.setdefault(_p, ["afoo", "bbar", "a", "azz"])
for _p in OTHER_GROUP_KINDS:
    SYNTHETIC.setdefault(_p, ["afoo", "bbar", "foob", "xab"])


def _corpus() -> list[str]:
    texts = []
    for path in sorted(checks.tracked_files(REPO)):
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, IsADirectoryError):
            continue
    return texts


_CORPUS: list[str] | None = None


def _texts() -> list[str]:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = _corpus()
    return _CORPUS


def _synthetic_texts() -> list[str]:
    out = []
    for texts in SYNTHETIC.values():
        for t in texts:
            out += [t, t.upper(), t.swapcase()]
    return out


def _violations(patterns, texts, rl, rls, asc) -> tuple[list, int]:
    """Pairs where the regex matches but the literal proof would have skipped the text."""
    bad, matched = [], 0
    for pattern in patterns:
        a_rl, a_rls, a_asc = rl(pattern), rls(pattern), asc(pattern)
        if a_rl is None and a_rls is None and a_asc is None:
            continue
        rx = re.compile(pattern, re.MULTILINE)
        for t in texts:
            low = t.lower()
            rl_ok = a_rl is None or any(lit in low for lit in a_rl)
            rls_ok = a_rls is None or any(all(m in low for m in s) for s in a_rls)
            asc_ok = a_asc is None or not t.isascii() or any(
                all(m in low for m in s) for s in a_asc)
            if rl_ok and rls_ok and asc_ok:
                if a_rl is not None and rx.search(t):
                    matched += 1
                continue
            if rx.search(t):
                matched += 1
                bad.append((pattern, t[:60], rl_ok, rls_ok, asc_ok))
    return bad, matched


def _newly_proved(head_answers) -> list[str]:
    """Live patterns HEAD's extract could not prove in at least one prover.

    Every pattern HEAD COULD prove keeps its exact answer (behavior 9), and those
    answers stay under iteration 99's committed whole-register soundness sweep, so the
    corpus oracle here spends its regex passes only where the answer is NEW."""
    head = head_answers["head"]
    return [p for p in head_answers["patterns"] if None in head[p]]


SHARDS = 3


@pytest.mark.parametrize("shard", range(SHARDS))
def test_b10_newly_proved_live_patterns_are_sound_over_the_tracked_corpus(
        head_answers, shard):
    patterns = _newly_proved(head_answers)[shard::SHARDS]
    assert patterns
    bad, _ = _violations(patterns, _texts() + _synthetic_texts(), RL, RLS, ASC)
    assert bad == [], bad[:5]


def test_b10_spec_patterns_are_sound_over_their_synthetic_texts():
    texts = _synthetic_texts()
    bad, matched = _violations(list(SYNTHETIC), texts, RL, RLS, ASC)
    assert bad == [], bad[:5]
    assert matched > 0


def test_b10_the_oracle_catches_an_impossible_literal_mutant():
    impossible = lambda p: frozenset({"\x00impossible"})  # noqa: E731
    impossible_sets = lambda p: (frozenset({"\x00impossible"}),)  # noqa: E731
    patterns = list(SYNTHETIC) + _live_content_patterns()[:40]
    bad, _ = _violations(patterns, _synthetic_texts() + _texts()[:40], impossible,
                         impossible_sets, impossible_sets)
    assert len(bad) >= 1


# --- behavior 11: measured count ------------------------------------------------------


def _census(text: str) -> dict[str, int]:
    rows = {}
    for line in text.splitlines():
        m = re.fullmatch(r"\| ([a-z -]+) \| (\d+) \|", line.strip())
        if m:
            rows[m.group(1)] = int(m.group(2))
    return rows


@pytest.fixture(scope="module")
def scan_cost_pair(head_src) -> tuple[dict, dict]:
    argv_head = [sys.executable, str(head_src / "tools" / "scan_cost.py"), "--target", "."]
    argv_work = [sys.executable, str(TOOL), "--target", "."]
    procs = []
    for src, argv in ((head_src / "src", argv_head), (REPO / "src", argv_work)):
        env = {**os.environ, "PYTHONPATH": str(src)}
        procs.append(subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, env=env, cwd=REPO))
    outs = []
    for proc in procs:
        out, err = proc.communicate()
        assert proc.returncode == 0, err[-2000:]
        outs.append(_census(out))
    return outs[0], outs[1]


def test_b11_proved_nothing_at_most_two_and_literal_set_proofs_unchanged(scan_cost_pair):
    head, work = scan_cost_pair
    assert work["proofs that proved nothing"] <= 2, work
    assert work["proofs that proved nothing"] >= 1, "test_iter207 needs it non-zero"
    assert head["proofs that proved nothing"] >= 30, head
    # Same node on purpose: the pair costs two full scans, so one node consumes it.
    assert work["literal-set proofs"] == head["literal-set proofs"], (head, work)


SCOPED_FLAG_OPENER = re.compile(r"\(\?[aiLmsux-]+:")


def test_b11_every_still_unprovable_live_pattern_has_an_out_of_scope_opener():
    """AMBIGUITY, disclosed: `pm.md` says every still-unprovable live pattern holds a
    lookaround opener. Measured: 10 of the 11 unprovable live patterns instead begin
    with a SCOPED-FLAG group `(?i:...)`, which the spec's own Out of Scope forbids the
    descent to enter; they are not evaluated in a self-scan, which is why the scan_cost
    row reads 2. So the clause is tested in its intent-preserving reading: every
    unprovable live pattern holds a lookaround opener OR a scoped-flag group opener --
    the two group kinds the spec deliberately leaves unproved."""
    unprovable = [p for p in _live_content_patterns() if RLS(p) is None]
    assert unprovable, "test_iter99 b4 needs at least one unprovable live pattern"
    stray = [p for p in unprovable
             if not any(o in p for o in LOOKAROUND_OPENERS)
             and not SCOPED_FLAG_OPENER.search(p)]
    assert stray == [], stray
    assert any(any(o in p for o in LOOKAROUND_OPENERS) for p in unprovable)


def test_b11_the_spec_named_lookahead_pattern_is_still_unprovable():
    lookahead = [p for p in _live_content_patterns() if p.startswith(r"(?s)\A(?=")]
    assert lookahead
    assert all(RLS(p) is None for p in lookahead)


# --- behavior 12: scan bytes and verdicts unchanged ----------------------------------


@pytest.mark.parametrize("flags", [(), ("--json",), ("--prd",)],
                         ids=["markdown", "json", "prd"])
def test_b12_self_scan_stdout_and_exit_code_match_head(head_src, flags):
    jobs = [["scan", str(REPO), "--gaps", str(GAPS), *flags]]
    head, work = _both(head_src, _CLI_DRIVER, jobs)
    (h_code, h_out, _), = head["res"]
    (w_code, w_out, w_err), = work["res"]
    assert w_code == h_code
    assert w_out == h_out
    assert w_out.endswith("\n") and not w_out.endswith("\n\n")
    assert w_code in (0, 1), w_err[:500]


def test_b12_validate_and_register_doc_unchanged(head_src):
    jobs = [["validate", str(GAPS)]]
    head, work = _both(head_src, _CLI_DRIVER, jobs)
    assert work["res"] == head["res"]
    assert work["res"][0][0] == 0
    tool = REPO / "tools" / "check_register_doc.py"
    run = subprocess.run([sys.executable, str(tool)], cwd=REPO, capture_output=True,
                         text=True, check=False)
    assert run.returncode == 0, run.stdout[-1000:] + run.stderr[-1000:]


# --- behavior 13: bounded and total ---------------------------------------------------

DEEP = "[ab]" + "(" * 40 + "foo" + ")" * 40


@pytest.mark.parametrize("pattern", [DEEP, "", "[ab](foo|bar", "a\\"],
                         ids=["deep40", "empty", "unbalanced", "trailing-backslash"])
@pytest.mark.parametrize("prover", sorted(PROVERS))
def test_b13_provers_are_total(prover, pattern):
    answer = PROVERS[prover](pattern)
    assert answer is None or isinstance(answer, (set, frozenset, tuple)), answer


@pytest.mark.parametrize("prover", sorted(PROVERS))
def test_b13_deep_answer_is_none_or_sound(prover):
    answer = PROVERS[prover](DEEP)
    if answer is None:
        return
    members = answer if prover == "RL" else {m for s in answer for m in s}
    assert members and all(m in "afoo" for m in members), answer
