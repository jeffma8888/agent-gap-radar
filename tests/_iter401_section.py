"""Subtract iteration 401's appended `## Identical evidence sets` block from a report.

Several committed pins compare `radar report` against a document rendered by an
implementation that no longer runs -- a sha256 captured before iteration 218, a
`git archive` of an older commit, the committed `REGISTER.md` at a past commit. Those
witnesses must not be re-captured from the working tree, because that is the one move
that would let a rendering regression re-baseline itself (the rule `_appended_fragment`
states for `prd`). Iteration 401 legitimately INSERTS one section between
`## Tag coverage` and `## Below confidence floor`, so the honest update keeps each
historical witness and removes the new block as a measured term: every byte the block
did not add must still match.

Removal is EXACT and two-sided. The block is cut from its heading line up to, not
including, the `## Below confidence floor` heading that always follows it, so a stray
byte inserted anywhere else still reds the pin; and a document carrying the heading
twice is refused rather than half-cleaned. A document WITHOUT the block (an older tree
rendering the same register) is returned unchanged, so one helper serves both sides of
an old-vs-new comparison.
"""

from __future__ import annotations

HEADING_LINE = b"## Identical evidence sets\n"
NEXT_HEADING_LINE = b"## Below confidence floor\n"


def without_identical_evidence_section(doc: bytes) -> bytes:
    """`doc` with its one `## Identical evidence sets` block removed, if it has one."""
    count = doc.count(HEADING_LINE)
    assert count <= 1, f"the identical-evidence heading occurs {count} times"
    if count == 0:
        return doc
    start = doc.index(HEADING_LINE)
    assert start == 0 or doc[start - 2:start] == b"\n\n", "block is not its own section"
    end = doc.index(NEXT_HEADING_LINE, start)
    return doc[:start] + doc[end:]


def has_identical_evidence_section(doc: bytes) -> bool:
    """Whether `doc` carries the block exactly once -- the precondition a pin asserts
    before subtracting, so a renderer that silently dropped the section cannot pass a
    historical comparison by having nothing to subtract."""
    return doc.count(HEADING_LINE) == 1
