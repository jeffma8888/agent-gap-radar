"""Iteration 100 behaviours: the register publishes WHICH record statuses a citation may
be gated on, DERIVED from `taxonomy.STATUSES`, and the consumer contract's gate rule is
held to that vocabulary instead of to the fail-CLOSED "is `open`" sentence it replaced.

WHAT THIS ITERATION CLAIMS, IN BEHAVIOURAL TERMS
`taxonomy` exposes two zero-argument verbs, `citable_statuses()` and `terminal_statuses()`,
which partition `STATUSES` at CALL TIME; `radar taxonomy` publishes that partition under a
`## Citation gate` heading; and `docs/CONSUMER_CONTRACT.md`'s "never do" gate rule names
every citable status and no terminal one. The bite is fail-CLOSED behaviour: a gate that
implemented the old published sentence literally refused a TRUTHFUL citation of a
`partially-addressed` record, and the live register holds three of those.

ISOLATION. This module honours the tester's isolation contract. It reads `pm.md`, this
repo's `tests/` conventions, `docs/CONSUMER_CONTRACT.md` and `gaps/*.json` (published
artifacts, not implementation), and the product's own behaviour by IMPORTING its public
names and RUNNING its CLI. It does not read `src/`, the engineer's or the reviewer's notes,
`IMPLEMENTATION.patch`, or any diff. Where a document is inspected it is inspected as a
DOCUMENT -- headings and inline-code tokens -- never as source.

WHY EVERY CLAIM IS PAIRED, AND WHICH RIVAL RULE EACH PAIR KILLS
A "derived vocabulary" is the easiest kind of claim to satisfy dishonestly: a second
hand-written tuple spelling the same four names passes any assertion that only reads the
unpatched register. So each behaviour names the rival it excludes.

* B1 patches `STATUSES` in three shapes. ADDING a fifth name kills both a literal and an
  import-time snapshot. REORDERING kills `sorted()` and any fixed literal order -- the
  expected order `('partially-addressed', 'open')` is neither alphabetical nor the shipped
  order, and `test_b1_...order...` asserts that inequality itself so the fixture is proved
  to sit in the discriminating range. DROPPING `retired` from `STATUSES` kills a
  `terminal_statuses()` that returns `TERMINAL_STATUSES` raw: the name must go inert, or the
  two tuples can drift into a partition that over-counts.
* B2's property is checked through a helper that is ALSO fed three deliberately broken
  pairs and required to reject each. A green partition assertion measures nothing until its
  predicate is measured red on a known-bad input.
* B3 asserts the published section against the vocabulary derived at test time, and then
  RE-RENDERS under a patched vocabulary and requires the document to move. The paired
  control asserts the two documents DIFFER, so a comparison of two identical strings cannot
  pass as "the render tracks the vocabulary".
* B4's census is TOKEN-EXACT (inline-code spans), never substring, because
  `partially-addressed` CONTAINS `addressed`: a substring test for the terminal status
  `addressed` fires on the citable status the whole iteration exists to admit.
  `test_b4_naive_substring_check_would_false_positive` pins that trap so a later
  simplification back to `in` reds instead of silently inverting the rule.
* B4 also measures WHY the rule must be asserted against `taxonomy` and never against
  `gaps/`: the register carries zero `addressed` and zero `retired` records, so a
  register-derived expectation gives the "names no terminal status" half an EMPTY domain and
  passes vacuously.
* B5's byte-stability is measured both in-process and ACROSS PROCESSES under differing
  `PYTHONHASHSEED`, because the hazard a set-ordered vocabulary creates is invisible to a
  same-process double call: string hashing is seeded per interpreter run.

TWO DELIBERATE NON-ASSERTIONS, NAMED SO A LATER ITERATION DOES NOT "FIX" THEM
1. `## Record statuses` order is NOT pinned against a patched `STATUSES`. Measured through
   the CLI, the gloss section does NOT track a patched `STATUSES` while the `## Citation
   gate` section does; that asymmetry predates this iteration and the spec's Out of Scope
   does not open it. It is reported as PM feedback with no assertion, because pinning
   EITHER side would manufacture a red suite for whichever iteration legitimately picks.
2. The position of `## Citation gate` within the document is not pinned here. Section order
   is a publishing choice already carried by the whole-document equality test in
   `test_iter21_behavior.py`; duplicating it here would only double the cost of a legitimate
   reordering. This module pins that the heading occurs exactly ONCE.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
GAPS_DIR = REPO_ROOT / "gaps"

#: The verb section heading this iteration adds, and the two side labels under it. These are
#: PUBLISHING choices (what the document calls the partition), not vocabulary CONTENT, so
#: pinning them is the point; the statuses beside them are always derived.
CITATION_GATE_HEADING = "## Citation gate"
CITABLE_LABEL = "citable"
TERMINAL_LABEL = "terminal"

#: The contract bullet that carries the gate rule, identified by its opening imperative.
#: The rule's CONTENT is derived from `taxonomy`; only the locator is spelled out.
GATE_RULE_OPENER = "- **Never gate a citation"

#: B1's reordering fixture. Deliberately NOT alphabetical and NOT the shipped order, so the
#: expected citable side (`partially-addressed`, `open`) is reachable only by filtering
#: `STATUSES` in place. `retired` precedes `addressed` for the same reason on the other side.
REORDERED_STATUSES = ("partially-addressed", "open", "retired", "addressed")

#: B1's growth fixture: a name no gloss exists for. It is used only against the vocabulary
#: verbs, never against the renderer, because the gloss section's key lookup is not this
#: iteration's contract and a KeyError there would be testing someone else's feature.
GROWN_STATUS = "quarantined"


def _run_taxonomy(capsys) -> tuple[int, str, str]:
    """`radar taxonomy` through the published CLI entry point, as (rc, stdout, stderr)."""
    rc = main(["taxonomy"])
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _strip_fenced_blocks(text: str) -> str:
    """`text` with every fenced code block removed, fences included.

    An inline-code census over markdown is wrong BY CONSTRUCTION unless fences go first: a
    triple fence makes every later backtick pairing off-by-one, so the spans after it are
    the text BETWEEN real spans and the census reports absent tokens that are plainly
    present. `CONSUMER_CONTRACT.md` carries no fence today (measured: zero lines whose
    stripped form starts with three backticks), so this is a brake for the day it grows one
    rather than a live correction -- and `test_b4_span_census_survives_a_fenced_block`
    keeps the brake honest by feeding it a fence.
    """
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return "\n".join(out)


def _inline_spans(text: str) -> list[str]:
    """Every inline-code token in `text`, in document order, fences removed first.

    Matching is deliberately TOKEN-EXACT rather than by substring: the citable status
    `partially-addressed` contains the terminal status `addressed`, so a substring census
    cannot tell "this rule names a terminal status" from "this rule names the very status
    the iteration exists to admit".
    """
    return re.findall(r"`([^`\n]+)`", _strip_fenced_blocks(text))


def _contract_text() -> str:
    return CONTRACT_PATH.read_text(encoding="utf-8")


def _gate_rule_block() -> str:
    """The contract's gate-rule bullet: its opening line plus its indented continuation.

    Bounded by the NEXT top-level bullet rather than by a line count, so a rule that is
    rewritten longer or shorter is still read whole.
    """
    lines = _contract_text().splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(GATE_RULE_OPENER)]
    assert len(starts) == 1, (
        f"expected exactly one contract bullet opening {GATE_RULE_OPENER!r}, "
        f"found {len(starts)} at lines {[i + 1 for i in starts]}"
    )
    start = starts[0]
    ends = [i for i in range(start + 1, len(lines)) if lines[i].startswith("- ")]
    end = ends[0] if ends else len(lines)
    return "\n".join(lines[start:end])


def _citation_gate_section(document: str) -> str:
    """The `## Citation gate` section of a rendered taxonomy document, heading excluded.

    Bounded by the next `## ` heading or end of document, so a section that grows a bullet
    is still read whole and a section that gains a NEIGHBOUR does not leak into it.
    """
    marker = CITATION_GATE_HEADING + "\n"
    assert document.count(marker) == 1, (
        f"expected exactly one {CITATION_GATE_HEADING!r} heading line, "
        f"found {document.count(marker)}"
    )
    tail = document.split(marker, 1)[1]
    nxt = re.search(r"^## ", tail, flags=re.MULTILINE)
    return tail[: nxt.start()] if nxt else tail


def _side_bullet(statuses) -> str:
    """One side of the partition as the verb publishes it.

    The FORMAT is restated (that is the publishing choice under test); the CONTENT is always
    passed in derived. `(none)` is the documented rendering of an empty side -- a bare
    separator would leave trailing whitespace on a published line.
    """
    return ", ".join(f"`{status}`" for status in statuses) if statuses else "(none)"


def _is_partition(citable, terminal, statuses) -> bool:
    """True iff `citable` and `terminal` are an exhaustive, disjoint cover of `statuses`.

    Concatenation-then-length is what makes disjointness and duplicate-freedom ONE check: a
    name appearing on both sides, or twice on one side, shortens the set without shrinking
    the tuple. `test_b2_partition_predicate_is_falsifiable` measures this red on each of
    those shapes, because a green partition assertion proves nothing until its predicate is
    proved to reject a known-bad input.
    """
    both = tuple(citable) + tuple(terminal)
    return len(both) == len(set(both)) and set(both) == set(statuses)


def _register_statuses() -> collections.Counter:
    """How many records in `gaps/` carry each status, read as published JSON."""
    counts: collections.Counter = collections.Counter()
    for path in sorted(GAPS_DIR.glob("*.json")):
        counts[json.loads(path.read_text(encoding="utf-8"))["status"]] += 1
    return counts


# --------------------------------------------------------------------------------------
# Behaviour 1 -- a public, importable closed vocabulary DERIVED from `STATUSES` at call time
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("verb_name", ["citable_statuses", "terminal_statuses"])
def test_b1_partition_verbs_are_public_zero_arg_tuples_of_statuses(verb_name: str) -> None:
    verb = getattr(taxonomy, verb_name)
    assert callable(verb), f"taxonomy.{verb_name} is not callable"
    value = verb()
    assert isinstance(value, tuple), (
        f"taxonomy.{verb_name}() returned {type(value).__name__}, not a tuple -- a set or "
        "list makes the published order unstable or the vocabulary mutable by its caller"
    )
    assert all(isinstance(status, str) for status in value), (
        f"taxonomy.{verb_name}() members are not all str: {value!r}"
    )
    assert set(value) <= set(taxonomy.STATUSES), (
        f"taxonomy.{verb_name}() names {sorted(set(value) - set(taxonomy.STATUSES))!r}, "
        "which is not in STATUSES -- the vocabulary must be a filter, not an invention"
    )


def test_b1_citable_tracks_a_status_the_register_grows_later(monkeypatch) -> None:
    """A fifth status appears in the citable side without any edit to a second list.

    Kills two rivals at once: a hand-written literal (which could never see the new name)
    and a partition computed once at import (which would serve a snapshot taken before the
    patch). The new name is deliberately NOT added to `TERMINAL_STATUSES`, which is the
    contract's stated default -- a grown status stays citable until someone decides
    otherwise, rather than dropping out of the build pipeline unannounced.
    """
    grown = ("open", "partially-addressed", GROWN_STATUS, "addressed", "retired")
    assert GROWN_STATUS not in taxonomy.citable_statuses(), (
        "fixture precondition failed: the grown status is already citable before patching, "
        "so this test could pass without the derivation being live"
    )
    monkeypatch.setattr(taxonomy, "STATUSES", grown)
    assert taxonomy.citable_statuses() == ("open", "partially-addressed", GROWN_STATUS)
    assert taxonomy.terminal_statuses() == ("addressed", "retired")


def test_b1_both_sides_follow_statuses_order_not_a_sort_or_a_literal(monkeypatch) -> None:
    """Order is `STATUSES` order, measured on a fixture no sort and no literal can produce."""
    expected_citable = ("partially-addressed", "open")
    expected_terminal = ("retired", "addressed")
    # The fixture is proved to sit in the discriminating range: a `sorted()` implementation
    # and a fixed literal in shipped order would BOTH give the other answer.
    assert expected_citable != tuple(sorted(expected_citable))
    assert expected_terminal != tuple(sorted(expected_terminal))
    assert expected_citable != taxonomy.citable_statuses()
    assert expected_terminal != taxonomy.terminal_statuses()

    monkeypatch.setattr(taxonomy, "STATUSES", REORDERED_STATUSES)
    assert taxonomy.citable_statuses() == expected_citable
    assert taxonomy.terminal_statuses() == expected_terminal


def test_b1_a_terminal_name_absent_from_statuses_goes_inert(monkeypatch) -> None:
    """A `TERMINAL_STATUSES` member missing from `STATUSES` must not be published.

    Kills a `terminal_statuses()` that returns `TERMINAL_STATUSES` unfiltered. That rival
    reads identically on the shipped register and breaks behaviour 2 the moment the two
    tuples drift: the union would over-count `STATUSES` by the orphaned name.
    """
    shrunk = ("open", "partially-addressed", "addressed")
    assert "retired" in taxonomy.TERMINAL_STATUSES, (
        "fixture precondition failed: `retired` is not a terminal status, so dropping it "
        "from STATUSES no longer creates the orphan this test is about"
    )
    monkeypatch.setattr(taxonomy, "STATUSES", shrunk)
    assert taxonomy.terminal_statuses() == ("addressed",)
    assert "retired" not in taxonomy.citable_statuses()


# --------------------------------------------------------------------------------------
# Behaviour 2 -- the derived partition is exhaustive and disjoint over `STATUSES`
# --------------------------------------------------------------------------------------


def test_b2_partition_is_exhaustive_and_disjoint_on_the_shipped_vocabulary() -> None:
    citable, terminal = taxonomy.citable_statuses(), taxonomy.terminal_statuses()
    assert _is_partition(citable, terminal, taxonomy.STATUSES), (
        f"citable={citable!r} + terminal={terminal!r} is not a partition of "
        f"STATUSES={taxonomy.STATUSES!r}"
    )
    assert len(citable) + len(terminal) == len(taxonomy.STATUSES)
    assert set(citable) & set(terminal) == set()
    # Non-degenerate: both sides carry at least one status, so neither the exhaustiveness
    # nor the disjointness clause is being satisfied by an empty side.
    assert citable and terminal


@pytest.mark.parametrize(
    "statuses,terminal_names",
    [
        pytest.param(("open", "partially-addressed", "addressed", "retired"), None,
                     id="shipped"),
        pytest.param(("open", "partially-addressed", GROWN_STATUS, "addressed", "retired"),
                     None, id="grown-fifth-status"),
        pytest.param(REORDERED_STATUSES, None, id="reordered"),
        pytest.param(("open", "partially-addressed", "addressed"), None,
                     id="orphaned-terminal-name"),
        pytest.param(("open", "partially-addressed", "addressed", "retired"), ("retired",),
                     id="narrowed-terminal-set"),
        pytest.param(("open", "partially-addressed", "addressed", "retired"), (),
                     id="empty-terminal-set"),
        pytest.param(("addressed", "retired"), None, id="all-terminal"),
        pytest.param((), None, id="empty-vocabulary-degenerate"),
    ],
)
def test_b2_partition_property_holds_under_a_patched_vocabulary(
    monkeypatch, statuses, terminal_names
) -> None:
    """The partition property is a THEOREM about the derivation, not a fact about four names.

    The `empty-vocabulary-degenerate` case is labelled as such on purpose: it is satisfied by
    any implementation that returns two empty tuples, so it is included as an edge probe and
    never as the evidence. The cases that discriminate are the grown, reordered, orphaned and
    narrowed ones, each of which a second hand-written list gets wrong.
    """
    monkeypatch.setattr(taxonomy, "STATUSES", statuses)
    if terminal_names is not None:
        monkeypatch.setattr(taxonomy, "TERMINAL_STATUSES", terminal_names)
    citable, terminal = taxonomy.citable_statuses(), taxonomy.terminal_statuses()
    assert _is_partition(citable, terminal, statuses), (
        f"citable={citable!r} + terminal={terminal!r} is not a partition of {statuses!r}"
    )


def test_b2_partition_predicate_is_falsifiable() -> None:
    """The predicate behind behaviour 2 is measured RED on each shape it must reject."""
    statuses = ("open", "partially-addressed", "addressed", "retired")
    assert _is_partition(("open", "partially-addressed"), ("addressed", "retired"), statuses)
    # over-counting: a name on both sides
    assert not _is_partition(
        ("open", "partially-addressed"), ("addressed", "retired", "open"), statuses
    )
    # not exhaustive: a status covered by neither side
    assert not _is_partition(("open",), ("addressed", "retired"), statuses)
    # duplicated within one side
    assert not _is_partition(
        ("open", "open", "partially-addressed"), ("addressed", "retired"), statuses
    )
    # invented name not in the vocabulary
    assert not _is_partition(
        ("open", "partially-addressed", GROWN_STATUS), ("addressed", "retired"), statuses
    )


# --------------------------------------------------------------------------------------
# Behaviour 3 -- `radar taxonomy` publishes the partition, each side in `STATUSES` order
# --------------------------------------------------------------------------------------


def test_b3_document_publishes_the_partition_in_derived_order(capsys) -> None:
    rc, out, err = _run_taxonomy(capsys)
    assert rc == 0 and err == ""
    expected = (
        "\n"
        f"- `{CITABLE_LABEL}` -- {_side_bullet(taxonomy.citable_statuses())}\n"
        f"- `{TERMINAL_LABEL}` -- {_side_bullet(taxonomy.terminal_statuses())}\n"
    )
    section = _citation_gate_section(out)
    assert section == expected, (
        "the published `## Citation gate` section does not equal the derived partition\n"
        f"  published: {section!r}\n  derived:   {expected!r}"
    )


def test_b3_published_partition_tracks_a_patched_vocabulary(monkeypatch, capsys) -> None:
    """Re-rendering under a reordered vocabulary must MOVE the published section.

    The paired control is the inequality assertion: without it, a renderer that ignored the
    vocabulary entirely and printed a literal would pass, because both sides of a
    string comparison would be the same unchanging text.
    """
    rc, before, err = _run_taxonomy(capsys)
    assert rc == 0 and err == ""
    baseline = _citation_gate_section(before)

    monkeypatch.setattr(taxonomy, "STATUSES", REORDERED_STATUSES)
    rc, after, err = _run_taxonomy(capsys)
    assert rc == 0 and err == ""
    patched = _citation_gate_section(after)

    assert patched != baseline, (
        "the published section is byte-identical under a reordered vocabulary, so it is a "
        f"literal rather than a derivation: {patched!r}"
    )
    assert patched == (
        "\n"
        f"- `{CITABLE_LABEL}` -- `partially-addressed`, `open`\n"
        f"- `{TERMINAL_LABEL}` -- `retired`, `addressed`\n"
    )


def test_b3_every_status_is_published_exactly_once_in_the_gate_section(capsys) -> None:
    """Nothing is silently dropped from the published partition and nothing is double-listed.

    Counted over TOKEN-EXACT inline-code spans. A substring count would report `addressed`
    twice -- once inside `partially-addressed` -- and so could not tell a duplicated entry
    from the shipped, correct document.
    """
    rc, out, err = _run_taxonomy(capsys)
    assert rc == 0 and err == ""
    spans = _inline_spans(_citation_gate_section(out))
    for status in taxonomy.STATUSES:
        assert spans.count(status) == 1, (
            f"status {status!r} appears {spans.count(status)} times in the published "
            f"partition, expected exactly 1; spans={spans!r}"
        )
    assert spans.count(CITABLE_LABEL) == 1 and spans.count(TERMINAL_LABEL) == 1
    # No status is published that the vocabulary does not name.
    assert set(spans) - {CITABLE_LABEL, TERMINAL_LABEL} <= set(taxonomy.STATUSES)


# --------------------------------------------------------------------------------------
# Behaviour 4 -- the contract's gate rule names every citable status and no terminal one
# --------------------------------------------------------------------------------------


def test_b4_gate_rule_names_every_citable_status_as_a_code_token() -> None:
    spans = _inline_spans(_gate_rule_block())
    missing = [status for status in taxonomy.citable_statuses() if status not in spans]
    assert not missing, (
        f"the contract's gate rule does not name citable status(es) {missing!r}; a gate "
        f"implementing the rule as written would refuse a truthful citation. spans={spans!r}"
    )


def test_b4_gate_rule_names_no_terminal_status() -> None:
    spans = _inline_spans(_gate_rule_block())
    named = [status for status in taxonomy.terminal_statuses() if status in spans]
    assert not named, (
        f"the contract's gate rule names terminal status(es) {named!r} as citable material"
    )


def test_b4_naive_substring_check_would_false_positive() -> None:
    """The trap that forces a token-exact census, pinned so a later `in` reads red.

    `partially-addressed` CONTAINS `addressed`, so a substring test for the terminal status
    fires on the citable status this whole iteration exists to admit -- reporting the fixed
    contract as still broken, which points at the destructive repair of deleting the
    sentence that admits `partially-addressed`.
    """
    block = _gate_rule_block()
    assert "partially-addressed" in block
    assert "addressed" in block, "precondition: the substring is present"
    assert "addressed" not in _inline_spans(block), (
        "precondition failed: `addressed` is a token here, so this test no longer "
        "demonstrates the substring trap"
    )


def test_b4_span_census_survives_a_fenced_block() -> None:
    """The fence brake in `_strip_fenced_blocks` is measured, not asserted.

    Without stripping, the triple fence pairs with the following backtick and every later
    span is the text BETWEEN real spans -- the failure whose verdict is "the document never
    mentions this".
    """
    sample = "prose `alpha` then\n```\n`inside` fence\n```\nand `beta` after\n"
    assert _inline_spans(sample) == ["alpha", "beta"]
    naive = re.findall(r"`([^`\n]+)`", sample)
    assert naive != ["alpha", "beta"], (
        f"control failed: the naive census already agrees, so the brake is untested ({naive!r})"
    )


def test_b4_gate_rule_points_at_the_published_vocabulary_and_verb_section(capsys) -> None:
    """The rule tells a gate author where to READ the partition, and that place exists."""
    spans = _inline_spans(_gate_rule_block())
    assert "taxonomy.citable_statuses()" in spans
    assert CITATION_GATE_HEADING in spans, (
        f"the gate rule does not name the {CITATION_GATE_HEADING!r} heading a gate author "
        f"must read; spans={spans!r}"
    )
    rc, out, err = _run_taxonomy(capsys)
    assert rc == 0 and err == ""
    assert CITATION_GATE_HEADING + "\n" in out, (
        "the contract points at a heading the rendered document does not publish"
    )


def test_b4_the_terminal_half_of_the_rule_is_unmeasurable_from_the_register() -> None:
    """Why behaviour 4 must be asserted against `taxonomy` and never against `gaps/`.

    Measured, not argued: the live register carries zero records with a terminal status, so
    a register-derived expectation hands `test_b4_gate_rule_names_no_terminal_status` an
    EMPTY domain and it passes without reading the contract at all.
    """
    counts = _register_statuses()
    assert sum(counts.values()) > 0, "precondition: the register is non-empty"
    register_terminal = [s for s in counts if s in set(taxonomy.terminal_statuses())]
    assert register_terminal == [], (
        "the register now carries a terminal-status record, so this measurement is stale: "
        f"{register_terminal!r}"
    )
    assert set(counts) != set(taxonomy.STATUSES), (
        "the register now exhausts STATUSES, so a register-derived rule would be as strong "
        "as a vocabulary-derived one and this distinction needs re-measuring"
    )
    assert set(counts) <= set(taxonomy.citable_statuses()), (
        f"register statuses {sorted(counts)!r} are not all citable"
    )


# --------------------------------------------------------------------------------------
# Behaviour 5 -- renderer contract: one trailing newline, byte-stable, exit 0
# --------------------------------------------------------------------------------------


def test_b5_exit_zero_one_trailing_newline_and_empty_stderr(capsys) -> None:
    rc, out, err = _run_taxonomy(capsys)
    assert rc == 0
    assert err == "", f"stderr is not empty: {err!r}"
    assert out.endswith("\n") and not out.endswith("\n\n"), (
        f"document does not end in exactly one newline: tail={out[-8:]!r}"
    )
    assert out.startswith("# Taxonomy\n")


def test_b5_document_is_byte_stable_across_two_calls(capsys) -> None:
    _, first, _ = _run_taxonomy(capsys)
    _, second, _ = _run_taxonomy(capsys)
    assert first.encode("utf-8") == second.encode("utf-8")


def test_b5_document_is_byte_stable_across_processes_and_hash_seeds() -> None:
    """Cross-process byte-stability under differing `PYTHONHASHSEED`.

    A same-process double call CANNOT see this class of defect: string hashing is seeded once
    per interpreter run, so a set-ordered vocabulary is perfectly self-consistent within one
    process and varies between them. This is the only measurement in the module that can
    catch a partition derived through a set.
    """
    program = (
        "import sys\n"
        "from agent_gap_radar.cli import main\n"
        "sys.exit(main(['taxonomy']))\n"
    )
    outputs: dict[str, bytes] = {}
    for seed in ("0", "1", "2", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", program],
            cwd=str(REPO_ROOT), env=env, capture_output=True,
        )
        assert proc.returncode == 0, (
            f"seed {seed}: exit {proc.returncode}, stderr={proc.stderr.decode()!r}"
        )
        assert proc.stderr == b"", f"seed {seed}: stderr={proc.stderr!r}"
        outputs[seed] = proc.stdout
    distinct = set(outputs.values())
    assert len(distinct) == 1, (
        "the document is not byte-stable across interpreter hash seeds: "
        f"{ {seed: len(value) for seed, value in outputs.items()} }"
    )
    only = distinct.pop()
    assert only.endswith(b"\n") and not only.endswith(b"\n\n")
    assert b"## Citation gate\n" in only
