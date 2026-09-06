"""Oracle for the `scan --json` key enumeration that `docs/CONSUMER_CONTRACT.md` publishes.

WHY THIS EXISTS
That document is the one the vision points a release gate and a build loop at, and it
asserts an obligation it was not held to: "Every key the tool emits must appear in this
list: the drift this paragraph already suffered was omission, so the list is the contract
and not a summary of it." The committed check (`tests/test_iter13_behavior.py`, behavior 7)
asserts only the SUBSET direction -- every emitted key is named. So the document may name a
key the tool does not emit, and nothing in this repo can see it. The consumer meets that as
a lookup failure on ITS side of the boundary, where the failure reads as the consumer's bug
and not as ours. The sibling prd enumeration in the same document is already held in both
directions (iteration 68); this module is the same brake for the payload a gate actually
reads.

WHY THE SCOPE IS ONE SENTENCE AND NOT THE PARAGRAPH
Measured over the committed document: the `scan --json` PARAGRAPH carries 25 distinct
backticked tokens, the enumeration SENTENCE carries exactly 20, and the 20 are exactly the
emitter's top-level keys plus its per-finding keys. The five the paragraph adds are prose --
`.`, `open`, `radar scan .`, `scan --json`, `score` -- and at least one of them is backticked
precisely in order to say that no such key exists. Equality over the paragraph is therefore
only reachable through an exception list naming those five, and an exception list is where a
real drift hides: the day a key is renamed, the stale name is a plausible thing to park in
that list, and the brake then certifies the drift it exists to catch. The sentence scope
needs ZERO exclusions, so this module contains no exclusion set, no allowlist and no
per-token special case, and the equality is total over its scope.

WHY THE TOKEN RULE HAS NO SHAPE FILTER EITHER
Iteration 68's prd collector keeps only code spans that look like a bare identifier. That
filter is a silent exclusion rule: it drops `radar scan .` and `.` by SHAPE, which also
drops any future drift that spells a key with a space, a dot or a hyphen -- exactly the
misspelling a consumer would meet as a lookup failure. Because the scope is one sentence,
the filter buys nothing, so a token here is the widest thing a reader can grep: a run
containing neither a backtick nor a newline.

WHY THE SENTENCE IS FOUND BY AN ANCHOR AND A PERIOD, NOT BY LINE NUMBERS
The document is hard-wrapped, so every reflow moves the line numbers and no line range
survives an edit that changes nothing semantically. The anchor names WHICH sentence is the
contract and contains no key name, so the brake cannot be satisfied by the way this file
locates the prose.

WHY THE READER FAILS CLOSED, AND ON WHAT
A scope reader that silently returns the wrong span reports agreement between the wrong two
sets, which is worse than no check: a reflow that shrank the scope would drop a documented
key from view, and the answer would read as "nothing wrong". Two inputs are unanswerable
rather than wrong, so they raise: an anchor occurring zero times (the sentence was reworded
away) or more than once (a pasted duplicate would let a stale copy answer for the live one),
and an anchor with no sentence terminator after it at all. `key_set_defects` raises on an
empty emitted set for the same reason -- two empty sets agree with each other, and that
green means nothing.

WHY `emitted_keys` REFUSES A FINDINGS-LESS PAYLOAD
The per-finding keys exist only inside `findings`, so a payload built over an empty register
supplies 7 of the 20 keys. The comparison would then report the other 13 as EXTRA, and the
repair a reader would draw from that report is to DELETE thirteen correct names from the
published contract. The wrong reading is the reassuring one, so the input is refused instead
of answered.

WHY THE FUNCTIONS ARE PURE OVER THEIR INPUTS
The committed document can only ever demonstrate the PASSING side of an equality, so every
rule here has to be drivable from synthetic input to be proved two-sided at all. Taking the
text and the two key sets as arguments is what makes a known-bad fixture a string in memory
instead of an edit to a file on disk that has to be put back.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final[pathlib.Path] = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The sentence anchor. A hand-written anchor is unavoidable -- something must say WHICH
#: sentence is the contract -- but it names no key, so the equality below cannot be
#: satisfied by the way this module locates the prose.
ENUMERATION_ANCHOR: Final[str] = "A gate gets a stable object:"

#: The sentence ends at the first period that closes a sentence: one followed by whitespace,
#: or one at the very end of the text. A period followed by a non-space (a decimal, a version,
#: an abbreviation glued to a word) is not a terminator, so the scope does not stop early on
#: prose a later edit may add.
_TERMINATOR: Final[re.Pattern[str]] = re.compile(r"\.(?=\s|\Z)")

#: A token is a run containing neither a backtick nor a newline. Widest possible on purpose:
#: see the module docstring on why there is no identifier filter. A token wrapped across a
#: line break is not one, because a reader cannot grep it.
_TOKEN: Final[re.Pattern[str]] = re.compile(r"`([^`\n]+)`")

#: Named in the failure messages so a reader who hits one knows the answer is UNAVAILABLE
#: rather than negative, and knows which kind of edit produced it.
_REFLOW: Final[str] = "reflow"


class KeyEnumerationError(Exception):
    """The enumeration could not be READ, so no verdict about it is available.

    Distinct from a defect on purpose. A defect is a difference between two key sets that
    were both understood; this is an input whose shape defeats the question -- a missing or
    duplicated anchor, a sentence with no terminator, or a key set that is empty. Raising
    rather than returning empty defect lists keeps an unanswerable question from being
    indistinguishable from a document with nothing wrong.
    """


def contract_text() -> str:
    """The committed consumer contract, decoded.

    A separate function so a caller can mutate the returned string in memory to build a
    known-bad, instead of editing the file on disk and having to put it back.
    """
    return CONTRACT_PATH.read_text(encoding="utf-8")


def enumeration_sentence(text: str) -> str:
    """The one sentence that enumerates `scan --json`'s keys, terminating period included.

    Begins at `ENUMERATION_ANCHOR` and ends at the first sentence-terminating period after
    it. Fails closed rather than guessing: see the module docstring on why a silently wrong
    span is worse than no check at all.
    """
    hits = [match.start() for match in re.finditer(re.escape(ENUMERATION_ANCHOR), text)]
    if len(hits) != 1:
        raise KeyEnumerationError(
            f"the anchor {ENUMERATION_ANCHOR!r} occurs {len(hits)} time(s), expected "
            f"exactly 1 -- a {_REFLOW} or a reword moved the enumeration sentence, so its "
            "key set cannot be read and no agreement with the emitter may be reported")
    start = hits[0]
    end = _TERMINATOR.search(text, start + len(ENUMERATION_ANCHOR))
    if end is None:
        raise KeyEnumerationError(
            f"no sentence-terminating period follows the anchor {ENUMERATION_ANCHOR!r} -- a "
            f"{_REFLOW} left the enumeration sentence unterminated, so its end is unknown "
            "and no agreement with the emitter may be reported")
    return text[start:end.end()]


def backticked_tokens(chunk: str) -> set[str]:
    """Every distinct token in `chunk`. The scope decides what counts, not the token shape."""
    return set(_TOKEN.findall(chunk))


def documented_keys(text: str) -> set[str]:
    """The key set the document PUBLISHES: the enumeration sentence's tokens."""
    return backticked_tokens(enumeration_sentence(text))


def emitted_keys(payload: Mapping[str, object]) -> set[str]:
    """The key set the tool EMITS: top-level keys plus per-finding keys, from real bytes.

    Refuses a payload with no findings; see the module docstring on why answering that input
    would point a reader at the wrong repair.
    """
    findings = payload.get("findings")
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)) or not findings:
        raise KeyEnumerationError(
            "the payload carries no findings, so it supplies none of the per-finding keys; "
            "answering would report every one of them as an EXTRA and invite a reader to "
            "delete correct names from the published contract")
    keys = set(payload)
    for finding in findings:
        if not isinstance(finding, Mapping):
            raise KeyEnumerationError(
                f"a finding is {type(finding).__name__}, not an object, so its key set "
                "cannot be read")
        keys |= set(finding)
    return keys


def key_set_defects(
    documented: Iterable[str], emitted: Iterable[str]
) -> tuple[list[str], list[str]]:
    """`(missing, extra)`, each sorted: the two directions of the contract's obligation.

    `missing` is the OLD direction iteration 13 already asserted -- emitted and undocumented.
    `extra` is the NEW one -- documented and not emitted, the name that outlived its key.
    """
    documented_set = set(documented)
    emitted_set = set(emitted)
    if not emitted_set:
        raise KeyEnumerationError(
            "the emitted key set is empty, so every documented list would agree with it; "
            "refusing to report agreement between two empty sets")
    return sorted(emitted_set - documented_set), sorted(documented_set - emitted_set)


def defect_message(missing: Sequence[str], extra: Sequence[str]) -> str:
    """A failure message that NAMES every offending token, in both directions.

    The token name is the whole value of the report: "the sets differ" tells a reader to go
    diff two lists by hand, which is the work the brake exists to have already done.
    """
    parts: list[str] = []
    if missing:
        parts.append(
            "emitted by the tool and NOT named in the enumeration sentence: "
            + ", ".join(missing))
    if extra:
        parts.append(
            "named in the enumeration sentence and NOT emitted by the tool: "
            + ", ".join(extra))
    if not parts:
        return "the documented key set equals the emitted key set"
    return "; ".join(parts)
