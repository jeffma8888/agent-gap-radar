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
    python3 tools/verify_quotes.py --inbox <dir>              # report only
    python3 tools/verify_quotes.py --inbox <dir> --partition   # act per record

Exit 0 if every quote verifies, 1 if any did not, 2 on a usage error.

WHY `--partition` EXISTS, and it is the important part of this file. Report mode
returns ONE verdict for the whole directory, so a driver that treats a non-zero
exit as "do not promote anything" turns this tool into a RATCHET rather than a
filter: with a growing candidate pool and a non-zero per-quote failure rate, the
probability that SOME quote fails approaches 1 and stays there, so one bad quote
vetoes every good candidate behind it, forever. That is not a hypothetical - it
ran for eleven days and blocked 991 candidates, and fixing individual quotes
could never have cleared it, because each fix just exposes the next one.

`--partition` makes the verdict PER RECORD and acts on it:
  verified    -> left in place, so the offline gate sees only checked records
  quarantined -> a quote is genuinely not on its cited page; needs a human
  deferred    -> the page could not be fetched, which is NOT a verdict about the
                 record, so it is retried later instead of being condemned

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


#: Whitespace sitting immediately BEFORE closing punctuation. English prose never
#: contains it, so removing it can only move a string toward what a reader sees --
#: whereas leaving it in makes honest quotes unverifiable. It appears because every
#: tag outside `INLINE_ZERO_WIDTH_TAGS` is replaced by a space, and ordinary emphasis
#: markup like `<strong>restorable</strong>.` or `<em>alpha</em>,` puts a tag boundary
#: right before the punctuation. Deliberately CLOSING punctuation only: this never
#: joins two separate WORDS, which is the false-pass direction and the reason
#: `INLINE_ZERO_WIDTH_TAGS` is kept small.
_SPACE_BEFORE_PUNCT_RE = re.compile(r" +([,.;:!?)\]}])")


def _norm(text: str) -> str:
    """The ONE normaliser. Both the page and the quote must go through it.

    THIRD member of a family that has now cost real time three times, so the rule is
    worth restating: every difference between how the PAGE side and the QUOTE side are
    produced is a potential fail-CLOSED bug, where a correct excerpt is reported as
    absent. Curly quotes were the first, `<code>` spacing the second, and a tag
    boundary before punctuation the third -- found when a live pass quarantined two
    records whose quotes were in fact present character for character. Anything added
    here applies to BOTH sides by construction, which is the only reason that class of
    bug is fixable in one place.
    """
    for src, dst in _SUBS.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)


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


#: Classification of one evidence item against its cited page.
VERBATIM, PARTIAL, NOT_FOUND, UNREACHABLE = "verbatim", "partial", "not_found", "unreachable"


def classify(quote: str, page: str | None) -> str:
    if page is None:
        return UNREACHABLE
    q = _norm(quote)
    if q and q in page:
        return VERBATIM
    window = " ".join(q.split()[:PARTIAL_WINDOW])
    return PARTIAL if window and window in page else NOT_FOUND


def record_defects(gap: object) -> list[str]:
    """Shape problems that make a record UNJUDGEABLE. Empty list means judgeable.

    Candidates are written by unattended research agents, so "valid JSON that is not
    the expected shape" is a routine output rather than an edge case. Without this
    gate `partition` reaches an unguarded `.get` while collecting urls -- BEFORE it
    has judged anything -- so one malformed file aborts the entire pass with an
    AttributeError and reinstates the all-or-nothing veto that `--partition` exists
    to remove. The ratchet would come back wearing a traceback instead of an exit
    code, which is strictly worse, because a crash records no verdict at all.

    Returns a LIST of human-readable defects, not a bool, because the quarantine
    reason file is the only channel to the person who has to decide what to do.

    A record citing NO evidence is a defect too, and deliberately so: zero quotes
    trivially satisfies "no quote failed", so without this an unsupported record
    would promote on a technicality -- the opposite of what the register is for.

    Only `partition` uses this. `verify` stays defensive with `.get` on purpose: it
    is the REPORT path and is handed records that have not passed through here.
    """
    if not isinstance(gap, dict):
        return [f"record is a {type(gap).__name__}, not a JSON object"]
    evidence = gap.get("evidence", [])
    if not isinstance(evidence, list):
        return [f"'evidence' is a {type(evidence).__name__}, not a list"]
    if not evidence:
        return ["record cites no evidence, so no quote could be verified"]
    defects: list[str] = []
    for i, item in enumerate(evidence):
        if not isinstance(item, dict):
            defects.append(
                f"evidence[{i}] is a {type(item).__name__}, not an object")
            continue
        for field in ("locator", "quote"):
            value = item.get(field)
            if not isinstance(value, str):
                defects.append(
                    f"evidence[{i}].{field} is a {type(value).__name__}, "
                    f"not a string")
    return defects


def fetch_all(urls: list[str], workers: int = 8,
              fetch_fn: _FetchFn | None = None) -> dict[str, str | None]:
    """Fetch each UNIQUE url once.

    Candidates cite the same primary sources heavily (measured on a real backlog:
    3251 citations over 638 unique pages), so caching by url is a ~5x reduction
    in network work and is what makes verifying a large backlog feasible at all.
    """
    import concurrent.futures

    # Resolved at CALL time, not bound as a default: a default argument is
    # evaluated once at definition, so `fetch_fn=fetch` in the signature would
    # silently ignore any later substitution of the module-level fetch and every
    # page would read as unreachable. That failure looks like a dead network.
    fn = fetch_fn or fetch
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(urls, pool.map(fn, urls)))


def select_bounded(paths: list[pathlib.Path], limit: int) -> list[pathlib.Path]:
    """Choose WHICH records a bounded pass looks at, spreading across `layer`.

    A bounded pass used to take `sorted(paths)[:limit]`, which is alphabetical by
    filename, and filenames start with the research topic. That is not a neutral
    sample, it is a permanent bias: with a large backlog the pass can only ever reach
    the front of the alphabet, so the layers whose names sort late are never
    verified, never promoted, and silently absent from the register no matter how
    much research covers them.

    Measured when this was live: 861 queued candidates spanning all 11 layers
    (observability 136, multi-agent 95, tool-action 92, human-interface 86 ...), and
    a verified queue of 99 containing exactly THREE -- benchmarkgap, context and
    cost. The eight missing layers were not under-researched; they were unreachable.

    So take one record from each layer in turn, best-first inside a layer by evidence
    class, and cycle until the budget is spent. A layer with few candidates
    contributes all of them and stops; it never blocks the others. Records whose
    layer cannot be read are pooled under "" and still get their turn, because an
    unreadable record needs to reach the gate that quarantines it.
    """
    if limit <= 0 or limit >= len(paths):
        return paths

    by_layer: dict[str, list[tuple[int, str, pathlib.Path]]] = {}
    for path in paths:
        layer, rank = "", 0
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                layer = doc.get("layer") if isinstance(doc.get("layer"), str) else ""
                rank = _evidence_rank(doc)
        except Exception:
            pass
        by_layer.setdefault(layer or "", []).append((-rank, path.name, path))

    for bucket in by_layer.values():
        bucket.sort()

    chosen: list[pathlib.Path] = []
    order = sorted(by_layer)
    cursor = {layer: 0 for layer in order}
    while len(chosen) < limit:
        took = False
        for layer in order:
            if len(chosen) >= limit:
                break
            i = cursor[layer]
            if i < len(by_layer[layer]):
                chosen.append(by_layer[layer][i][2])
                cursor[layer] = i + 1
                took = True
        if not took:
            break
    return sorted(chosen)


def _evidence_rank(doc: dict) -> int:
    """Strongest evidence weight in a record, for ordering inside a layer.

    Kept local and deliberately crude rather than importing the register's scoring:
    this tool must run on a MALFORMED candidate without raising, and the real scorer
    validates its input. Getting the order slightly wrong costs nothing, because
    every selected record is verified identically; refusing to order at all is what
    would reinstate the filename bias.
    """
    weights = {"incident-postmortem": 5, "first-party-field": 5, "peer-reviewed": 4,
               "maintainer-primary": 4, "vendor-primary": 4, "practitioner-report": 3,
               "survey-aggregate": 3, "secondary-summary": 1, "model-output": 0}
    best = 0
    ev = doc.get("evidence")
    if isinstance(ev, list):
        for item in ev:
            if isinstance(item, dict):
                best = max(best, weights.get(item.get("source_class"), 0))
    return best


def partition(
    inbox: pathlib.Path,
    quarantine: pathlib.Path,
    deferred: pathlib.Path,
    max_records: int = 0,
    workers: int = 8,
    fetch_fn: _FetchFn | None = None,
    verified: pathlib.Path | None = None,
) -> int:
    """Verify per record and move each record according to its OWN result.

    Returns 0 even when records are quarantined: partitioning is this tool doing
    its job, and a non-zero exit is exactly what let a caller build the
    all-or-nothing veto that this mode exists to remove.

    `verified` is optional and changes nothing when omitted -- records that pass stay
    in the inbox, which is correct when a pass covers the WHOLE inbox, because then
    "still in the inbox" and "verified" are the same set. Under `max_records` they are
    NOT the same set: the unprocessed tail is also still there, and a driver that
    promotes the inbox afterwards would promote records whose quotes were never
    checked. Passing `verified` makes the distinction explicit, so bounding a pass and
    promoting only checked work are safe to combine.
    """
    paths = sorted(inbox.glob("*.json"))
    if max_records:
        paths = select_bounded(paths, max_records)
    if not paths:
        print(f"No candidates in {inbox}")
        return 0

    loaded: list[tuple[pathlib.Path, dict]] = []
    malformed: list[tuple[pathlib.Path, str]] = []
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            malformed.append((path, f"not valid JSON: {exc}"))
            continue
        defects = record_defects(doc)
        if defects:
            malformed.append((path, "\n".join(defects)))
        else:
            loaded.append((path, doc))

    # Indexed rather than `.get`-ed: `record_defects` has already established that
    # every survivor is an object whose `evidence` is a non-empty list of objects
    # with string `locator` and `quote`. A defensive `.get` here would hide a future
    # regression in that gate behind a silently empty url set.
    urls = sorted({
        ev["locator"]
        for _, gap in loaded
        for ev in gap["evidence"]
        if ev["locator"].startswith(("http://", "https://"))
    })
    print(f"{len(loaded)} judgeable record(s), {len(malformed)} malformed, "
          f"{len(urls)} unique page(s) to fetch")
    pages = fetch_all(urls, workers=workers, fetch_fn=fetch_fn)

    def move(path: pathlib.Path, dest: pathlib.Path, reason: str | None) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        if reason is not None:
            (dest / (path.stem + ".reason.txt")).write_text(
                path.name + "\n\n" + reason + "\n", encoding="utf-8")
        path.replace(dest / path.name)

    kept = quarantined = deferred_n = 0
    for path, gap in loaded:
        verdicts = []
        for ev in gap["evidence"]:
            url, quote = ev["locator"], ev["quote"]
            if not url.startswith(("http://", "https://")):
                verdicts.append((NOT_FOUND, url, quote))
            else:
                verdicts.append((classify(quote, pages.get(url)), url, quote))

        kinds = {v for v, _, _ in verdicts}
        if NOT_FOUND in kinds:
            move(path, quarantine, "\n\n".join(
                f"quote not found at {u}\n    {q}"
                for v, u, q in verdicts if v == NOT_FOUND))
            quarantined += 1
            print(f"QUARANTINE  {path.name}")
        elif UNREACHABLE in kinds:
            # NOT a verdict about the record. A rate-limited or JS-rendered page
            # is not evidence that a citation is fake, so retry it on a later
            # pass rather than condemning a good record.
            move(path, deferred, None)
            deferred_n += 1
            print(f"DEFER       {path.name}  (a cited page could not be fetched)")
        else:
            kept += 1
            if verified is not None:
                move(path, verified, None)
            print(f"VERIFIED    {path.name}")

    for path, reason in malformed:
        move(path, quarantine, reason)
        quarantined += 1
        print(f"QUARANTINE  {path.name}  ({reason.splitlines()[0]})")

    remaining = len(list(inbox.glob("*.json")))
    tail = ("unprocessed by this pass" if verified is not None
            else "left in the inbox")
    print(f"\npartition: {kept} verified, {quarantined} quarantined, "
          f"{deferred_n} deferred; {remaining} file(s) {tail}")
    return 0


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
    ap.add_argument("--partition", action="store_true",
                    help="act per record: quarantine failures, defer unreachable")
    ap.add_argument("--quarantine", type=pathlib.Path)
    ap.add_argument("--deferred", type=pathlib.Path)
    ap.add_argument("--verified", type=pathlib.Path,
                    help="move records that pass here (required to combine "
                         "--max-records with a promote step)")
    ap.add_argument("--max-records", type=int, default=0,
                    help="bound one pass (0 = all)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    directory = args.gaps or args.inbox
    if not directory.is_dir():
        print(f"Error: not a directory: {directory}", file=sys.stderr)
        return 2
    if args.partition:
        if args.gaps:
            print("Error: --partition operates on an --inbox, not a register",
                  file=sys.stderr)
            return 2
        return partition(
            directory,
            args.quarantine or directory.parent / "quarantine",
            args.deferred or directory.parent / "deferred",
            max_records=args.max_records,
            workers=args.workers,
            verified=args.verified,
        )

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
