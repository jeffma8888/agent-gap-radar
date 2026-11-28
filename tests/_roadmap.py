"""The roadmap as ONE text: `PRODUCT.md` with its archived Done-ledger rows spliced back in.

WHY THIS EXISTS
Iteration 428 moved the oldest Done-ledger rows out of `PRODUCT.md` into `PRODUCT_ARCHIVE.md`,
byte-for-byte, so the file every planning stage reads stays short. The ledger is still one
history: a row in either file records a ship, and fifteen modules pin claims about rows that now
live in the archive ("iteration 31's row says ...", "the historical run is the ledger's ordered
prefix"). Those claims are about the HISTORY, not about which file holds it, so they read the
history through this one door instead of each module learning the split on its own.

WHY A SPLICE AND NOT A CONCATENATION
`tools/roadmap_integrity.ledger_union` concatenates, which is right for coverage (a set claim)
and wrong for the order and prefix claims the tests make: the archive's rows are the OLDER ones
and belong where the pointer line stands. Removing the pointer and the blank line after it, and
inserting the archive's rows there, reproduces the pre-split document byte-for-byte -- the
property `tests/test_iter428_behavior.py` pins against git -- so every pre-split assertion runs
on exactly the text it was written against.

WHY THE ARCHIVE IS FOUND BESIDE THE PATH
The same rule as `roadmap_integrity.archive_beside`: a test that points its `ROADMAP` handle at a
scratch copy reads that copy alone unless a copy of the archive sits next to it. A scratch file
holding an already-whole document therefore needs no archive and is returned unchanged.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The committed roadmap index.
ROADMAP = REPO_ROOT / "PRODUCT.md"

#: Kept equal to `tools/roadmap_integrity.ARCHIVE_NAME`, which `tests/test_iter428_behavior.py`
#: asserts; not imported, so this helper needs no `sys.path` edit to be importable.
ARCHIVE_NAME = "PRODUCT_ARCHIVE.md"

#: The archive's ledger heading; every non-blank line after it is a ledger row.
ARCHIVE_HEADING = "## Done ledger (archive)"

#: The index's pointer line. A pattern, not a literal, so a later paydown that archives more rows
#: rewrites the range in one document without touching this helper.
POINTER_RE = re.compile(r"^Rows iter \d+\.\.\d+ are archived verbatim in `PRODUCT_ARCHIVE\.md`\.$")


def archive_rows(archive_text: str) -> list[str]:
    """The archive's ledger rows, in file order: every non-blank line after its heading."""
    lines = archive_text.split("\n")
    assert ARCHIVE_HEADING in lines, f"{ARCHIVE_NAME} has no {ARCHIVE_HEADING!r} heading"
    return [line for line in lines[lines.index(ARCHIVE_HEADING) + 1 :] if line]


def rejoin(index_text: str, archive_text: str) -> str:
    """Splice the archive's rows into the index at its pointer line, dropping the pointer.

    Fails loudly rather than guessing when the pointer is missing or not followed by its blank
    line: a split document that cannot be rejoined is a defect, never a single-file document.
    """
    lines = index_text.split("\n")
    at = [i for i, line in enumerate(lines) if POINTER_RE.match(line)]
    assert len(at) == 1, f"expected exactly one archive pointer line, found {len(at)}"
    pointer = at[0]
    assert lines[pointer + 1] == "", "the archive pointer line must be followed by a blank line"
    return "\n".join(lines[:pointer] + archive_rows(archive_text) + lines[pointer + 2 :])


def rejoined_roadmap(path: pathlib.Path = ROADMAP) -> str:
    """`path`'s text with the archive beside it spliced back in; unchanged when none sits there."""
    text = path.read_text(encoding="utf-8")
    archive = path.parent / ARCHIVE_NAME
    if not archive.is_file():
        return text
    return rejoin(text, archive.read_text(encoding="utf-8"))


def git_tracks(path: pathlib.Path) -> bool | None:
    """Whether git tracks `path` in this checkout, or `None` when git cannot answer.

    `None` is distinct from `False` so a caller skips loudly instead of reading a missing git
    (an exported tarball, no `git` binary) as an untracked file: `git ls-files` exits non-zero
    outside a work tree and prints nothing, with exit 0, for an untracked path.
    """
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--", path.relative_to(REPO_ROOT).as_posix()],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return bool(proc.stdout.strip())
