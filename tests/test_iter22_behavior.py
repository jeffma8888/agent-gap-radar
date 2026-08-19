"""Iteration 22 behaviors: `tools/promote.py` always publishes what it examined.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source to DERIVE an expectation, and nothing reads the engineer's or the reviewer's notes
or a diff. Every behavioral expectation below was measured by RUNNING the tool and reading
its stdout; the one lexical assertion (behavior 7) reads `tools/promote.py` as DATA and
asserts a COUNT only, which the spec asks for by name.

Two structural notes, both to stop this file from lying later:

* Behavior 7's matcher is proven TWO-SIDED in this run against planted samples holding
  two, one and zero occurrences, and the real assertion reports the domain size, so an
  empty or unreadable file can never read as "exactly one emitter". A census that cannot
  fail on a known-bad sample certifies itself while blind.
* This module deliberately spells the censused literal in its own planted samples. The
  census domain is `tools/promote.py` ONLY. If a future iteration widens that census to
  `tests/`, these samples are the first false hits -- widen the domain and the samples
  must move to a fixture file, not be silently "fixed".

Behavior 9 is asserted against `research/CANDIDATE_CONTRACT.md` with tolerant matchers
(paragraph-scoped, negation-aware) rather than pinned sentences: the point is that the
document STATES the two facts, not that it states them in one particular wording.
"""

from __future__ import annotations

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

from test_promote_gate import _candidate  # noqa: E402  reuse the known-good builder

#: The census line's shape, as the spec states it: `examined N candidates in <inbox>`.
CENSUS_RE = re.compile(r"examined (\d+) candidates")
#: The single pre-existing summary emitter, as the spec states it: `N accepted, M rejected`.
SUMMARY_RE = re.compile(r"(\d+) accepted, (\d+) rejected")
#: Behavior 7's censused literal -- the summary format string, one emitter only.
SUMMARY_FORMAT_LITERAL = "accepted, "


# --------------------------------------------------------------------------- helpers


def _quote_too_short():
    """A known-bad candidate: real shape, excerpt too short to be evidence."""
    doc = _candidate(title="Quote too short to be an excerpt")
    doc["evidence"][0]["quote"] = "it broke"
    return doc


def _model_output_only():
    """A known-bad candidate: every evidence item is a zero-weight source class."""
    return _candidate(
        title="Asserted by a model and nothing else",
        evidence=[
            {
                "source_class": "model-output",
                "title": "x",
                "locator": "https://example.com/b",
                "date": "2026-01-01",
                "quote": "one two three four five six",
            }
        ],
    )


def _run_rc(tmp_path, candidates, apply=False, gaps=None):
    """`test_promote_gate._run`, but returning main()'s EXIT CODE as well as stdout.

    The existing harness discards the return value, and behaviors 2 and 5 are entirely
    about it. Returns `(rc, stdout, inbox_path)`.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name, doc in candidates.items():
        (inbox / name).write_text(json.dumps(doc), encoding="utf-8")
    argv = ["--inbox", str(inbox), "--gaps", str(gaps or (REPO_ROOT / "gaps"))]
    if apply:
        argv += ["--apply", "--rejected", str(tmp_path / "rejected")]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = promote.main(argv)
    return rc, buf.getvalue(), inbox


def _register_copy(tmp_path):
    """A COPY of the real register, so an `--apply` behavior cannot mutate `gaps/`."""
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    for src in (REPO_ROOT / "gaps").glob("*.json"):
        (gaps / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return gaps


def _census_count(out):
    """The single `examined N candidates` census, or fail loudly."""
    hits = CENSUS_RE.findall(out)
    assert len(hits) == 1, f"expected exactly one census line, found {hits}\n{out}"
    return int(hits[0])


def _summary_counts(out):
    """The single `N accepted, M rejected` summary, or fail loudly."""
    hits = SUMMARY_RE.findall(out)
    assert len(hits) == 1, f"expected exactly one summary line, found {hits}\n{out}"
    return int(hits[0][0]), int(hits[0][1])


def _summary_line(out):
    for line in out.splitlines():
        if SUMMARY_RE.search(line):
            return line
    raise AssertionError(f"no summary line in output:\n{out}")


# ------------------------------------------------------- behavior 1, 2, 4: vacuous run


def test_vacuous_run_publishes_a_zero_census_naming_the_inbox(tmp_path):
    """Behavior 1: an empty inbox still reports `examined 0 candidates` + the path."""
    _rc, out, inbox = _run_rc(tmp_path, {})
    assert "examined 0 candidates" in out, out
    assert str(inbox) in out, f"census must name the inbox it examined\n{out}"


def test_vacuous_run_no_longer_falls_silent_on_the_old_early_return(tmp_path):
    """Behavior 1, other side: the old `No candidates in ...` early return is GONE.

    Its presence would mean the summary is still being skipped by a second path.
    """
    _rc, out, _inbox = _run_rc(tmp_path, {})
    assert "No candidates in" not in out, out


def test_vacuous_run_exit_code_is_unchanged_zero(tmp_path):
    """Behavior 2: the vacuous run still exits 0 (unchanged from before this row)."""
    rc, out, _ = _run_rc(tmp_path, {})
    assert rc == 0, f"rc={rc!r}\n{out}"


def test_vacuous_run_reaches_the_zero_zero_summary_line(tmp_path):
    """Behavior 4: the vacuous run falls through to `0 accepted, 0 rejected`."""
    _rc, out, _ = _run_rc(tmp_path, {})
    assert _summary_counts(out) == (0, 0), out


def test_vacuous_run_as_a_subprocess_signals_a_live_run_to_its_consumer(tmp_path):
    """Behaviors 1+2+4 through the door the unattended consumer actually uses.

    The declared research driver runs this tool as a child process and treats a missing
    summary as "the tool died", so the process-level facts are the contract: exit status
    0, a census on stdout, and a summary on stdout.
    """
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--inbox", str(inbox), "--gaps", str(REPO_ROOT / "gaps")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr!r}\nstdout={proc.stdout!r}"
    assert "examined 0 candidates" in proc.stdout, proc.stdout
    assert SUMMARY_RE.search(proc.stdout), proc.stdout


# --------------------------------------------------- behavior 3: non-vacuous still fine


def test_three_candidates_report_a_census_of_three_and_keep_the_summary(tmp_path):
    """Behavior 3: `examined 3 candidates`, and the pre-existing summary still appears."""
    rc, out, _ = _run_rc(
        tmp_path,
        {
            "ok.json": _candidate(title="First distinct gap for the census"),
            "b1.json": _quote_too_short(),
            "b2.json": _model_output_only(),
        },
    )
    assert "examined 3 candidates" in out, out
    assert SUMMARY_RE.search(out), f"summary line vanished\n{out}"
    assert rc == 0, f"one candidate was accepted, so rc should be 0; rc={rc!r}\n{out}"


# ------------------------------------------------------ behavior 5: exit-code semantics


def test_exit_zero_when_at_least_one_candidate_is_accepted(tmp_path):
    """Behavior 5a: >=1 accepted -> 0, even with rejections alongside."""
    rc, out, _ = _run_rc(
        tmp_path,
        {"ok.json": _candidate(title="An accepted gap beside a refusal"), "b1.json": _quote_too_short()},
    )
    assert (1, 1) == _summary_counts(out), out
    assert rc == 0, f"rc={rc!r}\n{out}"


def test_exit_one_when_everything_was_refused(tmp_path):
    """Behavior 5b: >=1 refused and none accepted -> 1."""
    rc, out, _ = _run_rc(tmp_path, {"b1.json": _quote_too_short()})
    assert (0, 1) == _summary_counts(out), out
    assert rc == 1, f"rc={rc!r}\n{out}"


# ------------------------------------------- behavior 6: census reconciles with summary


@pytest.mark.parametrize(
    "name,candidates",
    [
        ("vacuous", {}),
        ("one-accepted", {"ok.json": _candidate(title="A reconciliation gap one")}),
        ("all-refused", {"b1.json": _quote_too_short()}),
        (
            "mixed-three",
            {
                "ok.json": _candidate(title="A reconciliation gap two"),
                "b1.json": _quote_too_short(),
                "b2.json": _model_output_only(),
            },
        ),
    ],
)
def test_census_equals_accepted_plus_rejected(tmp_path, name, candidates):
    """Behavior 6: the published denominator equals the numbers it is the denominator of.

    This is what makes the census a MEASUREMENT rather than a decoration: a candidate
    that is silently neither accepted nor rejected would show up here as a mismatch.
    """
    _rc, out, _ = _run_rc(tmp_path, candidates)
    examined = _census_count(out)
    accepted, rejected = _summary_counts(out)
    assert examined == accepted + rejected, (
        f"[{name}] census says {examined}, summary says {accepted}+{rejected}\n{out}"
    )
    assert examined == len(candidates), f"[{name}] census miscounted the inbox\n{out}"


# --------------------------------------------------- behavior 7: ONE summary emitter


def test_summary_emitter_census_matcher_is_two_sided():
    """Behavior 7, control: the counter must fire on a planted duplicate emitter.

    Proven here, in this run, so the real assertion below cannot pass while blind.
    """
    known_bad = (
        'print(f"{len(a)} accepted, {len(r)} rejected")\n'
        'print(f"0 accepted, 0 rejected")\n'
    )
    known_good = 'print(f"{len(a)} accepted, {len(r)} rejected")\n'
    known_absent = 'print("nothing to report")\n'
    assert known_bad.count(SUMMARY_FORMAT_LITERAL) == 2, known_bad
    assert known_good.count(SUMMARY_FORMAT_LITERAL) == 1, known_good
    assert known_absent.count(SUMMARY_FORMAT_LITERAL) == 0, known_absent


def test_promote_holds_exactly_one_summary_emitter():
    """Behavior 7: the vacuous case reaches the summary by FALLING THROUGH.

    LEXICAL and one-directional by construction: it can prove there is a single emitter
    and cannot prove that emitter is correct, which is why behaviors 1-6 are behavioral.
    """
    text = TOOL.read_text(encoding="utf-8")
    assert len(text) > 1000, f"census domain looks empty: {len(text)} bytes of {TOOL.name}"
    found = text.count(SUMMARY_FORMAT_LITERAL)
    assert found == 1, (
        f"expected exactly 1 occurrence of {SUMMARY_FORMAT_LITERAL!r} in {TOOL.name}, "
        f"found {found} over {len(text)} bytes -- a second emitter means the vacuous "
        f"case got its own copy instead of falling through"
    )


# ------------------------------------------------------- behavior 8: the dry-run note


def test_dry_run_summary_carries_the_dry_run_note(tmp_path):
    """Behavior 8a: without `--apply`, the summary line says it wrote nothing."""
    _rc, out, _ = _run_rc(tmp_path, {"ok.json": _candidate(title="A dry run note gap")})
    line = _summary_line(out)
    assert "dry run" in line.lower(), f"summary line lost its dry-run note: {line!r}\n{out}"


def test_apply_summary_drops_the_dry_run_note(tmp_path):
    """Behavior 8b: with `--apply`, the note is gone -- and `gaps/` is NOT touched.

    The apply run is pointed at a COPY of the register, and the real register is asserted
    unchanged afterwards, so verifying a writing behavior stays non-destructive.
    """
    before = {p.name for p in (REPO_ROOT / "gaps").glob("*.json")}
    gaps = _register_copy(tmp_path)
    _rc, out, _ = _run_rc(
        tmp_path, {"ok.json": _candidate(title="An apply mode note gap")}, apply=True, gaps=gaps
    )
    line = _summary_line(out)
    assert "dry run" not in line.lower(), f"apply run still claims to be a dry run: {line!r}"
    after = {p.name for p in (REPO_ROOT / "gaps").glob("*.json")}
    assert before == after, "an --apply behavior test mutated the real register"


# --------------------------------------- behavior 9: the contract states what it signals


def _paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def _census_claim_paragraphs(text):
    """Paragraphs stating that the `examined N` census is printed on EVERY run."""
    return [
        p
        for p in _paragraphs(text)
        if "examined" in p and re.search(r"every run", p, re.I)
    ]


#: "exit 0" / "exits 0" / "exit code of 0" / "exit code `0`" all count. Deliberately
#: tolerant: it is ANDed with three other conditions below, and a narrow version of this
#: is what the two-sided control caught -- `exit\s+(?:code\s+)?0` misses "exit code of 0",
#: so a legitimately reworded contract would have failed a green document.
EXIT_ZERO_RE = re.compile(r"exit\w*[^.\n]{0,24}?\b0\b", re.I)


def _exit_code_claim_paragraphs(text):
    """Paragraphs stating that exit 0 alone is not acceptance, so find your own line."""
    out = []
    for p in _paragraphs(text):
        if not EXIT_ZERO_RE.search(p):
            continue
        if "ACCEPT" not in p:
            continue
        if not re.search(r"\bnot\b|\balone\b", p, re.I):
            continue
        if not re.search(r"file\s?name", p, re.I):
            continue
        out.append(p)
    return out


#: Behavior 9 controls. A tolerant matcher that cannot FAIL proves nothing about the
#: document, so both readers run over a planted doc that omits the two facts and a
#: planted doc that states them, through the SAME functions the real assertions use.
_DEFICIENT_CONTRACT = (
    "# Candidate contract\n"
    "\n"
    "Submit one JSON document per candidate into the inbox directory.\n"
    "\n"
    "The tool exits 0 on success and writes nothing unless you pass --apply.\n"
)
_SUFFICIENT_CONTRACT = (
    "# Candidate contract\n"
    "\n"
    "Every run publishes what it looked at: `examined N candidates in <inbox>`,\n"
    "including a run over an empty inbox.\n"
    "\n"
    "An exit code of 0 does NOT mean your candidate was accepted -- it means the run\n"
    "completed. Find your own filename on an ACCEPT line to know it landed.\n"
)


def test_contract_readers_are_two_sided():
    """Behavior 9, control: both readers stay silent on a doc that omits the facts."""
    assert _census_claim_paragraphs(_DEFICIENT_CONTRACT) == []
    assert _exit_code_claim_paragraphs(_DEFICIENT_CONTRACT) == []
    assert _census_claim_paragraphs(_SUFFICIENT_CONTRACT), _SUFFICIENT_CONTRACT
    assert _exit_code_claim_paragraphs(_SUFFICIENT_CONTRACT), _SUFFICIENT_CONTRACT
    # The exit-code pattern alone, over the phrasings a contract may reasonably use.
    for phrasing in ("exit 0", "exits 0", "exit code of 0", "exit code `0`"):
        assert EXIT_ZERO_RE.search(phrasing), phrasing
    for miss in ("exit 1", "exited with an error"):
        assert not EXIT_ZERO_RE.search(miss), miss


def test_contract_states_every_run_reports_a_census():
    """Behavior 9a: the document says the census is published on EVERY run."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert len(text) > 500, f"contract looks empty: {len(text)} bytes"
    mentions = [p for p in _paragraphs(text) if "examined" in p]
    assert mentions, f"contract never mentions the `examined N` census\n{text[:400]}"
    assert _census_claim_paragraphs(text), (
        "contract mentions the census but never says every run reports it:\n"
        + "\n---\n".join(mentions)
    )


def test_contract_says_exit_zero_alone_is_not_acceptance():
    """Behavior 9b: exit 0 is not acceptance; find your own filename on an ACCEPT line."""
    text = CONTRACT.read_text(encoding="utf-8")
    mentions = [p for p in _paragraphs(text) if EXIT_ZERO_RE.search(p)]
    assert mentions, f"contract never states what exit 0 means\n{text[:400]}"
    assert _exit_code_claim_paragraphs(text), (
        "no paragraph ties exit 0 to 'not acceptance' AND to finding your own filename "
        "on an ACCEPT line:\n" + "\n---\n".join(mentions)
    )
