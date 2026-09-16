#!/usr/bin/env python3
"""Verify every evidence locator in the register still resolves.

This script is DELIBERATELY NOT part of the test suite. The suite is offline by
contract, and a test that needs the network is a test that fails on a plane, in
CI without egress, and on the day someone's blog goes down -- which teaches the
team to ignore red. So link-rot is checked out of band, on purpose.

The VERDICT logic is nonetheless reachable from an offline suite, through `main`'s
`check_fn` seam: exactly one line of this tool touches the network, and injecting
that line makes every summary, refusal and exit code provable with no socket.

Usage:
    python3 tools/check_locators.py [gaps_dir]

Exit codes: 0 every CHECKED locator resolves, 1 at least one does not, 2 bad usage or nothing was checkable.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys
from collections.abc import Callable

TIMEOUT_S = 45

#: The ONE resolvable-locator rule, spelled here in the standard library alone.
#:
#: This is `agent_gap_radar.models.RESOLVABLE_LOCATOR_RE` character for character, and it is
#: COPIED rather than imported on purpose. `README.md` publishes this file as ported VERBATIM
#: into a sibling public register, so it has to keep RUNNING as a single stdlib-only script;
#: importing the package would drag pydantic across that port and make the published claim
#: false. A copy is only safe while it cannot drift, so the suite -- not this comment -- holds
#: the two spellings to one ANSWER over an enumerated corpus, and pins this file's stdlib
#: purity so the reason for the copy stays enforced instead of merely stated.
_RESOLVABLE_LOCATOR_RE = re.compile(r"https?://\S+$")

#: A locator checker: takes one url, returns an HTTP status code as a string ("000" when
#: the request never completed). `main` takes one of these as a SEAM, which is the whole
#: reason its verdicts are reachable from a suite that is offline by contract.
_CheckFn = Callable[[str], str]


def is_resolvable_locator(url: str) -> bool:
    """True when `url` has the SHAPE the ingest gate requires of a citation.

    SHAPE only, never a dereference -- that is `check` below. The distinction is the whole
    point of asking here: `curl` cannot even attempt a locator with no host, an embedded
    space or a bare `http`, so offering one to the network buys a guaranteed `000`, a
    `BROKEN` verdict and an exit 1 that blames LINK ROT for what is really a malformed
    record. `tools/promote.py` refuses those shapes at ingest, so this tool must agree with
    it or it reports a register as rotting for a defect the register cannot contain.

    `re.match` with a trailing `$` (not `fullmatch`) is deliberate: it is byte-for-byte the
    ingest gate's predicate, quirks included, so adopting it moves no locator this tool
    already fetched into the skip arm.
    """
    return bool(_RESOLVABLE_LOCATOR_RE.match(url))


def collect(gaps_dir: pathlib.Path) -> collections.Counter:
    locators: collections.Counter = collections.Counter()
    for path in sorted(gaps_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for item in record.get("evidence", []):
            locators[item["locator"]] += 1
    return locators


def check(url: str) -> str:
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-L", url],
            capture_output=True, text=True, timeout=TIMEOUT_S)
        return result.stdout.strip() or "000"
    except (OSError, subprocess.TimeoutExpired):
        return "000"


def main(argv: list[str], check_fn: _CheckFn | None = None) -> int:
    """Report every locator's reachability, and refuse to report health vacuously.

    Two things make the report honest rather than merely present.

    The summary publishes the CHECKED count next to the DISTINCT one, because those two
    numbers used to be the same number: a non-http locator was printed as a SKIP and then
    never counted anywhere, so a register in which NOTHING was checkable still printed
    "N distinct locator(s), 0 broken" and exited 0 -- a clean bill of health over zero
    work. `checked + skipped == distinct` holds by construction below, so a reader never
    has to subtract to learn the denominator the other numbers are relative to.

    And a run that checked nothing returns 2 rather than 0. This tool is the only thing
    standing behind the register's locators, so "no breaks found" from a run that looked
    at none of them is the register telling its curator that unverifiable evidence is
    verified evidence -- the same vacuous success `radar validate` was made to refuse over
    a zero-record domain, arriving through a different door.

    `check_fn` is a SEAM resolved at CALL time, never bound as a signature default: a
    default argument is evaluated once at definition, so `check_fn=check` in the signature
    would capture this module's `check` forever and silently ignore any later substitution
    of it. That failure reads as a dead network rather than as an unusable seam.
    """
    gaps_dir = pathlib.Path(argv[1] if len(argv) > 1 else "gaps")
    if not gaps_dir.is_dir():
        sys.stderr.write(f"Error: not a directory: {gaps_dir}\n")
        return 2

    locators = collect(gaps_dir)
    if not locators:
        sys.stderr.write(f"Error: no evidence locators found in {gaps_dir}\n")
        return 2

    fn = check_fn or check
    broken: list[tuple[str, str]] = []
    checked = skipped = 0
    for url, count in sorted(locators.items()):
        if not is_resolvable_locator(url):
            # Locator SHAPE stays this tool's business to REPORT and nobody's here to
            # reject: the schema accepts any non-blank locator deliberately, so a DOI or
            # a stable local path is legal data. It is COUNTED rather than merely
            # printed, which is the difference between a skip a summary can own up to and
            # a skip that disappears into a healthy-looking zero.
            #
            # The question asked is the SHAPE rule, not the scheme. A scheme test admits
            # `http://` with no host, `httpx://a/b`, `http://a b/c` and the bare word
            # `http` -- every one unfetchable AND refused at ingest, so every one used to
            # spend a request, land in the `checked` denominator that exists to stop a
            # register reporting health over no work, and print as `BROKEN`. That names
            # link rot for a record-shape defect and sends the curator to the wrong repair.
            skipped += 1
            print(f"  SKIP  x{count}  {url} (not a resolvable locator)")
            continue
        checked += 1
        code = fn(url)
        marker = "ok" if code.startswith("2") else "BROKEN"
        if marker == "BROKEN":
            broken.append((url, code))
        print(f"  {code} {marker:>6}  x{count}  {url}")

    # The loop's two arms PARTITION the distinct locators, so `checked + skipped` equals
    # `len(locators)` for every run rather than by agreement between two tallies.
    print(f"{len(locators)} distinct locator(s): {checked} checked, "
          f"{skipped} skipped (not resolvable), {len(broken)} broken")
    for url, code in broken:
        print(f"  BROKEN {code}: {url}")

    if not checked:
        sys.stderr.write(
            f"Error: 0 checked of {len(locators)} distinct locator(s) -- no locator is "
            f"resolvable by shape, so this run cannot report register health\n")
        return 2
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
