"""Unit: the prose a check writes beside its locators is tagged where it is written.

Not a behavior file. The `scan --json` shape (pure locators in `locations`, prose in
`location_notes`) belongs to the test engineer; what is pinned here is the internal
mechanism an engineer's refactor can break silently:

* Both prose producers in `checks` -- `_scope_note` for an absence witness and
  `_rank_locations` for the cap's suppressed remainder -- return a `LocationNote`, and
  the locators they rank do not. `scan._split_locations` partitions by that TYPE and
  never by the string's shape, so a third dialect that forgets the tag would leak into
  `locations` unseen by any regex; this file is where that omission reds first.
* `LocationNote` is a `str` in every way an existing reader uses it: equality, prefix
  tests and f-string rendering are unchanged, which is what keeps the markdown brief and
  every committed reader of `RuleHit.locations` byte-identical.
* The partition keeps order within each half and is a conservation law: the two halves
  interleave back into the input, so nothing is dropped and nothing is invented.

Offline; every input is built in memory.
"""

from __future__ import annotations

import json

import pytest

from agent_gap_radar.checks import (MAX_LOCATIONS, LocationNote, _rank_locations,
                                    _scope_note)
from agent_gap_radar.scan import _split_locations

GLOBS = ["**/*.py", "**/*.ts"]


@pytest.mark.parametrize("pattern", [None, r"retry\(", r"(?i)\bfoo\b"])
def test_scope_note_is_tagged_for_both_dialects(pattern):
    note = _scope_note(GLOBS, pattern)
    assert isinstance(note, LocationNote)
    expected_head = "(no match) searched" if pattern else "(no files) searched"
    assert note.startswith(expected_head)


def test_rank_locations_tags_only_the_remainder():
    code = [f"src/m{i}.py:{i + 1}" for i in range(MAX_LOCATIONS + 3)]
    tests = ["tests/test_m.py:7", "tests/test_n.py:9"]
    ranked = _rank_locations(code, tests)
    assert len(ranked) == MAX_LOCATIONS + 1
    shown, tail = ranked[:-1], ranked[-1]
    assert not any(isinstance(loc, LocationNote) for loc in shown)
    assert isinstance(tail, LocationNote)
    assert tail == "(+5 more matches, 2 in test files)"


def test_rank_locations_under_the_cap_writes_no_note():
    ranked = _rank_locations(["a.py:1", "b.py:2"], ["tests/t.py:3"])
    assert ranked == ["a.py:1", "b.py:2", "tests/t.py:3"]
    assert not any(isinstance(loc, LocationNote) for loc in ranked)


def test_location_note_reads_as_its_plain_string():
    """Every existing reader of the list sees no change: the tag is invisible to str APIs."""
    note = LocationNote("(+3 more matches)")
    assert note == "(+3 more matches)"
    assert note.startswith("(+3 more")
    assert f"  - `{note}`" == "  - `(+3 more matches)`"
    assert json.dumps([note]) == json.dumps(["(+3 more matches)"])


def test_split_locations_partitions_by_type_and_conserves_order():
    entries = ["src/a.py:1", LocationNote("(no match) searched **/*.py for /x/"),
               "src/b.py:2", "tests/t.py:3", LocationNote("(+4 more matches)")]
    locators, notes = _split_locations(entries)
    assert locators == ["src/a.py:1", "src/b.py:2", "tests/t.py:3"]
    assert notes == ["(no match) searched **/*.py for /x/", "(+4 more matches)"]
    assert len(locators) + len(notes) == len(entries)
    # Plain `str` on both sides: the payload carries no subclass of its own.
    assert all(type(x) is str for x in locators + notes)


def test_split_locations_does_not_classify_by_shape():
    """A prose-looking plain string stays a locator; a locator-looking note stays a note.

    The partition is a statement about WHO wrote the entry, not what it looks like, so
    the regex a consumer might reach for is deliberately not what decides it.
    """
    locators, notes = _split_locations(["(weird).py:3", LocationNote("x.py:1")])
    assert locators == ["(weird).py:3"]
    assert notes == ["x.py:1"]


def test_split_locations_of_nothing_is_two_empty_lists():
    assert _split_locations([]) == ([], [])
