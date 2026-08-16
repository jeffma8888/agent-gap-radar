"""Verify every evidence quote is really on the page it cites. NETWORK, out of band.

The offline gate (`tools/promote.py`) can check that a locator LOOKS like a URL and
that a quote is long enough to be an excerpt. It cannot check whether the words
are actually there. That gap matters most for unattended research: a fabricated
quote attached to a REAL, resolving URL is the failure mode that survives review,
because every cheap signal about it looks correct.

Deliberately not part of the test suite. The suite is offline by contract, and a
network check in it would fail on a plane and pass on a bad day.

    python3 tools/verify_quotes.py --gaps gaps
    python3 tools/verify_quotes.py --inbox <dir>     # before promoting

Exit 0 if every quote verifies, 1 if any did not, 2 on a usage error.

A LESSON ABOUT THIS TOOL, kept because it cost real time: the first version
normalised curly quotes in the QUOTE but not in the PAGE, so an honest verbatim
excerpt containing a typographic quote was reported NOT FOUND. That is a
fail-CLOSED detector - the checker was broken and it accused correct data.
Normalisation must be applied to BOTH sides by the same function, which is why
there is exactly one `_norm` here and both sides call it.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import ssl
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; agent-gap-radar quote verifier)"
TIMEOUT = 30
#: Words of the quote that must appear contiguously for a PARTIAL pass. A quote
#: with an elided middle is legitimate; a quote sharing no long run with the page
#: is not.
PARTIAL_WINDOW = 12

_SUBS = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " ",
    "\u200b": "", "\u2011": "-", "\u00ad": "",
}


def _norm(text: str) -> str:
    """The ONE normaliser. Both the page and the quote must go through it."""
    for src, dst in _SUBS.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text).strip().lower()


def _visible_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|svg|noscript)\b.*?</\1>", " ", raw)
    return _norm(html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw)))


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(
            req, timeout=TIMEOUT, context=ssl.create_default_context()
        ) as resp:
            return _visible_text(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def verify(records: list[tuple[str, dict]]) -> int:
    pages: dict[str, str | None] = {}
    verbatim = partial = missing = unreachable = 0
    problems: list[str] = []

    for name, gap in records:
        for ev in gap.get("evidence", []):
            url, quote = ev.get("locator", ""), ev.get("quote", "")
            if not url.startswith(("http://", "https://")):
                missing += 1
                problems.append(f"{name}: locator is not a URL: {url!r}")
                continue
            if url not in pages:
                pages[url] = fetch(url)
            page = pages[url]
            if page is None:
                unreachable += 1
                print(f"UNREACHABLE  {name}  {url}")
                continue
            q = _norm(quote)
            if q and q in page:
                verbatim += 1
                print(f"VERBATIM     {name}  {q[:58]}")
                continue
            window = " ".join(q.split()[:PARTIAL_WINDOW])
            if window and window in page:
                partial += 1
                print(f"PARTIAL      {name}  {q[:58]}")
                continue
            missing += 1
            print(f"NOT ON PAGE  {name}  {q[:58]}")
            problems.append(f"{name}: quote not found at {url}\n    {quote}")

    print(
        f"\n{verbatim} verbatim, {partial} partial, {missing} not found, "
        f"{unreachable} unreachable"
    )
    if unreachable:
        print(
            "NOTE: unreachable is not a verdict. A page may be rate-limiting or "
            "JS-rendered; re-check by hand before deleting a record."
        )
    if problems:
        print("\nProblems, each of which needs a human decision:")
        for p in problems:
            print("  - " + p)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--gaps", type=pathlib.Path, help="a register directory")
    src.add_argument("--inbox", type=pathlib.Path, help="a candidate inbox")
    args = ap.parse_args(argv)
    directory = args.gaps or args.inbox
    if not directory.is_dir():
        print(f"Error: not a directory: {directory}", file=sys.stderr)
        return 2
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append((path.stem[:26], json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError as exc:
            print(f"Error: {path.name}: {exc}", file=sys.stderr)
            return 2
    if not records:
        print(f"No records in {directory}")
        return 0
    return verify(records)


if __name__ == "__main__":
    raise SystemExit(main())
