"""Verify every evidence quote is really on the page it cites. NETWORK, out of band.

The offline gate (`tools/promote.py`) can check that a locator LOOKS like a URL and
that a quote is long enough to be an excerpt. It cannot check whether the words
are actually there. That gap matters most for unattended research: a fabricated
quote attached to a REAL, resolving URL is the failure mode that survives review,
because every cheap signal about it looks correct.

`fetch` is deliberately not part of the test suite, and it is the ONLY line here that
is not: it is the one line that needs the network, and a network check in a suite that is
offline by contract would fail on a plane and pass on a bad day. Everything around it IS
reachable -- `verify` takes `fetch` as a seam and `page_text` normalises a page from a
string -- so the four verdicts, the PARTIAL window, the non-URL refusal and the exit code
are all provable with no socket.

    python3 tools/verify_quotes.py --gaps gaps
    python3 tools/verify_quotes.py --inbox <dir>     # before promoting

Exit 0 if every quote verifies, 1 if any did not, 2 on a usage error.

A LESSON ABOUT THIS TOOL, kept because it cost real time: the first version
normalised curly quotes in the QUOTE but not in the PAGE, so an honest verbatim
excerpt containing a typographic quote was reported NOT FOUND. That is a
fail-CLOSED detector - the checker was broken and it accused correct data.
Normalisation must be applied to BOTH sides by the same function, which is why
there is exactly one `_norm` here and both sides call it.

That family has now bitten TWICE, and the SECOND instance is why `page_text` exists: the
page side replaced EVERY tag with a space, so a page rendering `<code>outputSchema</code>:`
normalised to `outputschema : ...` while the honest, character-perfect quote normalised to
`outputschema: ...`, and the excerpt was reported NOT ON PAGE -- fail-CLOSED again -- while
plain prose from the same paragraph verified. Same shape as the curly-quote bug: the two
sides were normalised by rules that differ. So the members of `INLINE_ZERO_WIDTH_TAGS` are
removed with NO separator, because that is what a reader sees, and every other tag still
becomes a space, because collapsing block boundaries would buy a FALSE pass in exchange.
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
from collections.abc import Callable

UA = "Mozilla/5.0 (compatible; agent-gap-radar quote verifier)"
TIMEOUT = 30
#: Words of the quote that must appear contiguously for a PARTIAL pass. A quote
#: with an elided middle is legitimate; a quote sharing no long run with the page
#: is not.
PARTIAL_WINDOW = 12
#: Inline elements a READER sees as zero width. A page rendering `<code>x</code>: y` shows no
#: space before the colon, so replacing these tags with a space is what made an honest quote
#: report NOT ON PAGE. Deliberately CLOSED and deliberately small: every member added widens
#: the surface on which two separate words merge into one and buy a FALSE pass, which is the
#: opposite and worse failure. `span`, `em`, `strong` and `a` are NOT here on purpose.
INLINE_ZERO_WIDTH_TAGS = frozenset({"code", "kbd", "samp", "var", "tt"})

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


#: Built FROM the published constant, so the set is authoritative rather than a comment
#: about a hand-written pattern. `\b` keeps `<codex>` out of the `code` case; `[^>]*` lets
#: attributes through (`<code class="x">`); `(?i)` covers `<CODE>`; `</?` covers both forms.
_ZERO_WIDTH_RE = re.compile(
    r"(?is)</?(?:" + "|".join(sorted(INLINE_ZERO_WIDTH_TAGS)) + r")\b[^>]*>"
)


def page_text(raw: str) -> str:
    """Normalise an HTML page to the visible text a quote is compared against.

    Published rather than `_`-private because it is HALF of every verdict this tool
    prints: a caller who cannot reproduce this normalisation cannot audit, or test, the
    NOT ON PAGE it produced. It is also the seam that makes the whole verdict path
    reachable offline, from a literal HTML string.
    """
    raw = re.sub(r"(?is)<(script|style|svg|noscript)\b.*?</\1>", " ", raw)
    raw = _ZERO_WIDTH_RE.sub("", raw)
    return _norm(html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw)))


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(
            req, timeout=TIMEOUT, context=ssl.create_default_context()
        ) as resp:
            return page_text(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


#: The one line that needs a socket, hoisted into a type so a caller can substitute it.
_FetchFn = Callable[[str], str | None]


def verify(records: list[tuple[str, dict]], fetch: _FetchFn = fetch) -> int:
    """Print a verdict per quote and return 0 only if every one of them is accounted for.

    `fetch` is a SEAM, defaulting to the module function so the CLI is unchanged. Without
    it, the single networked line quarantined the ENTIRE verdict path -- the four labels,
    the PARTIAL window, the non-URL refusal, the exit code -- from a suite that is offline
    by contract, which left the central honesty claim of the register with no test at all.

    Pages are memoised per URL, so a locator cited by two records is fetched ONCE. That was
    always true of the network and is now observable through the seam.
    """
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
