#!/usr/bin/env python3
"""Prove the suite can FAIL. Plant one defect at a time and check a test catches it.

A green suite is not evidence that a behaviour exists. It is evidence that nothing
the suite looks at is broken, which is a much weaker claim -- and for a gate whose
whole job is to REFUSE things, the difference matters: a gate that accidentally
accepts everything passes every test that only submits good candidates.

So each entry below is a real defect, expressed as an exact source edit. The harness
applies one, runs the named test file, and requires it to go RED. A defect nothing
catches is reported as a hole in the suite, not as a pass.

Two of the entries here are not hypothetical. `cache_keyed_by_id` is the bug that
actually shipped into a live pass: it refused 849 of 859 candidates, every refusal
naming the same twin, because a refused candidate leaves its id unclaimed and the
next candidate is handed the same number. `silent_on_good_dropped` and
`advisory_threshold_zeroed` were both MISSED on the first run of this harness, and
the tests that now catch them exist because of it.

The three pre-flight predicates below -- `anchor_defects`, `residue_defects` and
`oracle_defects` -- are pure: they read text through an injected callable, write
nothing and spawn nothing. So the suite can assert that this harness is ARMED (every
anchor still resolves to exactly one site, no mutated form is sitting on disk, every
named oracle file exists) without planting a single defect. That is a brake against
the harness silently going offline. It is NOT a claim that the 20 defects are still
CAUGHT -- only a full run says that, and a full run is 20 suite invocations.

Usage:  uv run python tools/verify_mutations.py [--list]
Exit 0 = every planted defect was caught. Exit 1 = the suite is blind to something.
The original files are restored in a finally block and the restoration is verified
by content, not assumed.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: One planted defect: (name, file, old, new, test file that must go red).
Mutation = tuple[str, str, str, str, str]

MUTATIONS: list[Mutation] = [
    (
        "twins_gate_disabled",
        "tools/promote.py",
        "        mine = self._tree(gap)\n        if mine is None:\n            return None",
        "        mine = self._tree(gap)\n        if mine is None or True:\n            return None",
        "tests/test_promote_twins.py",
    ),
    (
        "twins_one_way_blocks",
        "tools/promote.py",
        "            if self._stands_in_for(mine, theirs) and self._stands_in_for(theirs, mine):",
        "            if self._stands_in_for(mine, theirs) or self._stands_in_for(theirs, mine):",
        "tests/test_promote_twins.py",
    ),
    (
        "twins_silent_on_good_dropped",
        "tools/promote.py",
        "        return (\n            run_check(spec, bad).verdict is Verdict.PRESENT\n"
        "            and run_check(spec, good).verdict is not Verdict.PRESENT\n        )",
        "        return run_check(spec, bad).verdict is Verdict.PRESENT",
        "tests/test_promote_twins.py",
    ),
    (
        "twins_unmeasurable_assumed_duplicate",
        "tools/promote.py",
        "        mine = self._tree(gap)\n        if mine is None:\n            return None",
        "        mine = self._tree(gap)\n        if mine is None:\n"
        "            return self._known[0] if self._known else None",
        "tests/test_promote_twins.py",
    ),
    (
        # The bug that actually shipped into a live pass.
        "twins_cache_keyed_by_id",
        "tools/promote.py",
        "        key = self._key(gap)",
        "        key = gap.id  # noqa",
        "tests/test_promote_twins.py",
    ),
    (
        "twins_register_not_compared",
        "tools/promote.py",
        "    for known in existing:\n        twins.remember(known)",
        "    for known in []:\n        twins.remember(known)",
        "tests/test_promote_twins.py",
    ),
    (
        "advisory_becomes_blocking",
        "tools/promote.py",
        "    for line in _advisory_lookalikes([g for _, g in accepted]):",
        "    for line in _advisory_lookalikes([g for _, g in accepted]):\n"
        '        refused.append((Path("x.json"), f"lookalike: {line}"))\n'
        "    for line in []:",
        "tests/test_promote_twins.py",
    ),
    (
        "advisory_threshold_zeroed",
        "tools/promote.py",
        "_LOOKALIKE_AT = 0.20",
        "_LOOKALIKE_AT = 0.0",
        "tests/test_promote_twins.py",
    ),
    (
        "advisory_reports_arbitrary_partner",
        "tools/promote.py",
        '            for x, y in ((a.id, b.id), (b.id, a.id)):\n'
        '                if overlap > best.get(x, (0.0, ""))[0]:\n'
        "                    best[x] = (overlap, y)",
        '            for x, y in ((a.id, b.id), (b.id, a.id)):\n'
        "                best[x] = (overlap, y)",
        "tests/test_promote_twins.py",
    ),
    (
        # The alphabetical cut that starved eight of eleven layers for weeks.
        "bounded_selection_alphabetical",
        "tools/verify_quotes.py",
        "        paths = select_bounded(paths, max_records)",
        "        paths = paths[:max_records]",
        "tests/test_verify_bounded_selection.py",
    ),
    (
        "bounded_selection_ignores_layer",
        "tools/verify_quotes.py",
        '        by_layer.setdefault(layer or "", []).append((-rank, path.name, path))',
        '        by_layer.setdefault("", []).append((-rank, path.name, path))',
        "tests/test_verify_bounded_selection.py",
    ),
    (
        "bounded_selection_ignores_evidence",
        "tools/verify_quotes.py",
        "(-rank, path.name, path))",
        "(0, path.name, path))",
        "tests/test_verify_bounded_selection.py",
    ),
    (
        # An unreadable candidate is the one a human most needs to see. Dropping it
        # here would leave it in the inbox forever, never quarantined.
        "bounded_selection_hides_unreadable",
        "tools/verify_quotes.py",
        "        except Exception:\n            pass",
        "        except Exception:\n            continue",
        "tests/test_verify_bounded_selection.py",
    ),
    (
        "bounded_selection_breaks_the_unbounded_path",
        "tools/verify_quotes.py",
        "    if limit <= 0 or limit >= len(paths):",
        "    if limit < 0 or limit >= len(paths):",
        "tests/test_verify_bounded_selection.py",
    ),
    (
        # The re-anchored format test must still fail on a real format change.
        "list_row_format_changed",
        "src/agent_gap_radar/cli.py",
        'f"{gap.id}  p={pri:>4.1f}  c={conf}  {gap.title}"',
        'f"{gap.id} p={pri:>4.1f} c={conf} {gap.title}"',
        "tests/test_iter01_behavior.py",
    ),
    (
        "advisory_prints_pair_twice",
        "tools/promote.py",
        "        pair = frozenset((gid, partner))\n        if pair in seen:\n            continue",
        "        pair = frozenset((gid, partner))\n        if False:\n            continue",
        "tests/test_promote_twins.py",
    ),
    (
        # Partition exists so ONE bad record cannot veto its neighbours.
        "partition_one_failure_vetoes_all",
        "tools/verify_quotes.py",
        "        if NOT_FOUND in kinds:",
        "        if NOT_FOUND in kinds or True:",
        "tests/test_verify_partition.py",
    ),
    (
        "partition_unreachable_is_condemned",
        "tools/verify_quotes.py",
        "        elif UNREACHABLE in kinds:",
        "        elif False:",
        "tests/test_verify_partition.py",
    ),
    (
        "promote_limit_ignored",
        "tools/promote.py",
        "        if len(accepted) >= budget:\n            break",
        "        if False:\n            break",
        "tests/test_promote_gate.py",
    ),
    (
        "promote_rank_ignores_confidence",
        "tools/promote.py",
        "        -(confidence(t[1]) if t[1] is not None else -1),",
        "        0 * (confidence(t[1]) if t[1] is not None else -1),",
        "tests/test_promote_gate.py",
    ),
]


def read_source(rel: str) -> str:
    """Return the UTF-8 text of the repo-relative path `rel`.

    A named seam rather than an inlined `read_text`, because `main` calls it BY BARE
    NAME: this harness plants defects in tracked files, so its own fail-closed
    pre-flight can only be proven by a test that substitutes the reader instead of
    writing to the tree.
    """
    return (REPO / rel).read_text(encoding="utf-8")


def anchor_defects(mutations: Iterable[Mutation], read: Callable[[str], str]) -> list[str]:
    """Name every mutation whose `old` anchor does not resolve to exactly one site.

    Two matches would silently mutate the wrong call site, so nothing may be written;
    zero matches means a refactor retired the anchor and that entry has quietly
    stopped proving anything -- the anchor set is hand-written against files this
    loop refactors on purpose, so drift is the expected failure, not the exotic one.
    """
    out: list[str] = []
    for name, rel, old, _new, _test in mutations:
        found = read(rel).count(old)
        if found != 1:
            out.append(f"anchor for {name} occurs {found} times in {rel}")
    return out


def residue_defects(mutations: Iterable[Mutation], read: Callable[[str], str]) -> list[str]:
    """Name every mutation whose defective `new` form is sitting on disk.

    Restoration happens in a `finally` block, which SIGKILL does not run, so an
    interrupted plant leaves a real defect in a tracked file, where the next stage's
    `git add -A` can sweep it into a release commit.
    """
    out: list[str] = []
    for name, rel, _old, new, _test in mutations:
        if new in read(rel):
            out.append(f"mutated form of {name} is present in {rel}")
    return out


def oracle_defects(mutations: Iterable[Mutation], exists: Callable[[str], bool]) -> list[str]:
    """Name every mutation whose named oracle test file is gone.

    A defect whose oracle was renamed or deleted can never be reported CAUGHT, so the
    entry reads as a hole in the suite when it is really a hole in this list.
    """
    out: list[str] = []
    for name, _rel, _old, _new, test in mutations:
        if not exists(test):
            out.append(f"oracle test file {test} for {name} is missing")
    return out


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="name the defects and exit")
    ap.add_argument("--only", help="run one defect by name")
    args = ap.parse_args(argv)

    if args.list:
        for name, rel, _, _, test in MUTATIONS:
            print(f"{name:38} {rel:24} -> {test}")
        return 0

    planned = [m for m in MUTATIONS if not args.only or m[0] == args.only]
    if not planned:
        print(f"Error: no defect named {args.only!r}", file=sys.stderr)
        return 2

    originals = {rel: read_source(rel) for _, rel, _, _, _ in planned}

    def in_hand(rel: str) -> str:
        """Serve the text already read, so the pre-flight judges what will be written."""
        return originals[rel]

    # An ambiguous anchor would silently mutate the wrong site, so every anchor must
    # resolve to exactly one occurrence BEFORE anything is written -- and one drifted
    # anchor vetoes the whole run, because a harness that half-runs proves nothing.
    defects = anchor_defects(planned, in_hand)
    if defects:
        print(f"Error: {defects[0]}", file=sys.stderr)
        return 2

    blind: list[str] = []
    try:
        for name, rel, old, new, test in planned:
            target = REPO / rel
            target.write_text(originals[rel].replace(old, new), encoding="utf-8")
            proc = subprocess.run(
                ["uv", "run", "pytest", test, "-q", "-p", "xdist", "-n", "0",
                 "--no-header", "-x", "--tb=no"],
                cwd=REPO, capture_output=True, text=True,
            )
            target.write_text(originals[rel], encoding="utf-8")
            caught = proc.returncode != 0
            print(f"{'CAUGHT ' if caught else 'MISSED!'} {name:38} {test}")
            if not caught:
                blind.append(name)
    finally:
        for rel, text in originals.items():
            path = REPO / rel
            path.write_text(text, encoding="utf-8")
            if _sha(path.read_text(encoding="utf-8")) != _sha(text):
                print(f"Error: FAILED TO RESTORE {rel}", file=sys.stderr)
                return 2

    print(f"\n{len(planned)} defect(s) planted, {len(blind)} uncaught")
    if blind:
        print("the suite is blind to: " + ", ".join(blind))
        return 1
    print("every planted defect was caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
