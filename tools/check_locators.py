#!/usr/bin/env python3
"""Verify every evidence locator in the register still resolves.

This script is DELIBERATELY NOT part of the test suite. The suite is offline by
contract, and a test that needs the network is a test that fails on a plane, in
CI without egress, and on the day someone's blog goes down -- which teaches the
team to ignore red. So link-rot is checked out of band, on purpose.

Usage:
    python3 tools/check_locators.py [gaps_dir]

Exit codes: 0 all locators resolve, 1 at least one does not, 2 bad usage.
"""

from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys

TIMEOUT_S = 45


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


def main(argv: list[str]) -> int:
    gaps_dir = pathlib.Path(argv[1] if len(argv) > 1 else "gaps")
    if not gaps_dir.is_dir():
        sys.stderr.write(f"Error: not a directory: {gaps_dir}\n")
        return 2

    locators = collect(gaps_dir)
    if not locators:
        sys.stderr.write(f"Error: no evidence locators found in {gaps_dir}\n")
        return 2

    broken = []
    for url, count in sorted(locators.items()):
        if not url.startswith("http"):
            print(f"  SKIP  x{count}  {url} (non-http locator)")
            continue
        code = check(url)
        marker = "ok" if code.startswith("2") else "BROKEN"
        if marker == "BROKEN":
            broken.append((url, code))
        print(f"  {code} {marker:>6}  x{count}  {url}")

    print(f"\n{len(locators)} distinct locator(s), {len(broken)} broken")
    for url, code in broken:
        print(f"  BROKEN {code}: {url}")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
