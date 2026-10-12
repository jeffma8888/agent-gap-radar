"""Iteration 310 behaviors: stale count removed from CONSUMER_CONTRACT.

The NOT_APPLICABLE paragraph no longer restates a count that decays.
The replacement sentence directs the reader to ``radar scan . --json``
instead, matching the convention lines 332-335 already established.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-6. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Every
behavioral claim is measured by reading the live document or by running
the CLI, both of which are inside the contract.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

_NOT_APPLICABLE_RE = re.compile(
    r"A `NOT_APPLICABLE` finding NAMES THE RULE THAT FAILED.*?(?=\n\n)",
    re.DOTALL,
)


def _paragraph() -> str:
    text = CONTRACT.read_text()
    m = _NOT_APPLICABLE_RE.search(text)
    assert m, "NOT_APPLICABLE paragraph not found in CONSUMER_CONTRACT.md"
    return m.group()


# -- B1: stale count removed ---------------------------------------------------

def test_b1_stale_ratio_string_absent():
    para = _paragraph()
    assert "62 of 119" not in para, "stale '62 of 119' count still present"


def test_b1_stale_multiplier_absent():
    para = _paragraph()
    assert "2.7x" not in para, "stale '2.7x' ratio still present"


# -- B2: no bare integer in the paragraph (outside backticks) -------------------

def test_b2_no_bare_integer_outside_backticks():
    para = _paragraph()
    stripped = re.sub(r"`[^`]*`", "", para)
    bare = re.findall(r"\b\d+\b", stripped)
    assert not bare, f"bare integers found outside backticks: {bare}"


# -- B3: convention alignment - directs reader to `radar scan . --json` ---------

def test_b3_command_reference_present():
    para = _paragraph()
    assert "radar scan . --json" in para, (
        "paragraph must direct reader to `radar scan . --json`"
    )


# -- B4: surrounding prose intact (every other line byte-identical to HEAD) -----
# B4 cannot be tested in pure black-box without reading the diff or the
# implementation source. The tester contract forbids both. The closest
# black-box assertion is that the document still parses and the paragraph
# exists, which B1-B3 already cover. Noted as an acknowledged gap.


# -- B5: regression test - no bare integer is the ongoing brake -----------------
# B5 IS the test: B2 above is the regression brake the spec asks for. It reads
# the live file, not a fixture, so future edits that reintroduce a bare integer
# will be caught.


# -- B6: full suite green (asserted by running the suite, not by a single test) -
# The tester runs `uv run pytest` as a separate step and reports the outcome
# in tester.md. No single test can assert "the full suite passed".


# -- Additional: the full document is well-formed after the edit ----------------

def test_document_starts_with_heading():
    text = CONTRACT.read_text()
    assert text.startswith("# "), "CONSUMER_CONTRACT.md must start with a heading"


def test_document_ends_with_one_newline():
    raw = CONTRACT.read_bytes()
    assert raw.endswith(b"\n"), "document must end with a newline"
    assert not raw.endswith(b"\n\n"), "document must not end with two newlines"


def test_not_applicable_paragraph_describes_most_common_verdict():
    para = _paragraph()
    assert "most common verdict" in para.lower() or "most common" in para.lower(), (
        "replacement must describe NOT_APPLICABLE as the most common verdict"
    )
