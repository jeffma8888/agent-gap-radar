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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: (name, file, old, new, test file that must go red)
MUTATIONS: list[tuple[str, str, str, str, str]] = [
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

    originals = {rel: (REPO / rel).read_text(encoding="utf-8") for _, rel, _, _, _ in planned}
    for rel, text in originals.items():
        # An ambiguous anchor would silently mutate the wrong site, so every anchor
        # must occur exactly once BEFORE anything is written.
        for name, r, old, _, _ in planned:
            if r == rel and text.count(old) != 1:
                print(f"Error: anchor for {name} occurs {text.count(old)} times in {rel}",
                      file=sys.stderr)
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
