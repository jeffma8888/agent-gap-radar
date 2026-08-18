"""Unit tests for the scan-scoped read memo in `checks`.

Scope: the cache PLUMBING only -- the frame stack, its lifetime, and what
`_read` does with a frame. The black-box behaviors (a scan decodes each file
once; a second `scan()` sees new content; `render_scan` bytes are unchanged)
are BEHAVIOR tests and belong to the test engineer.

Every claim here is asserted against a REAL file on disk rather than a stubbed
seam, because the defect this memo could introduce is returning stale or wrong
TEXT, and a stub cannot exhibit that. The decode count is observed by wrapping
`_decode`, which is the only place a real read happens.
"""

from __future__ import annotations

import pathlib

from agent_gap_radar import checks
from agent_gap_radar.checks import _READ_CACHE_STACK, MAX_FILE_BYTES, read_cache_scope


def _counted_decode(monkeypatch) -> list[str]:
    """Record every ACTUAL decode, then delegate. Returns the growing log."""
    seen: list[str] = []
    real = checks._decode

    def spy(path: pathlib.Path) -> str | None:
        seen.append(str(path))
        return real(path)

    monkeypatch.setattr(checks, "_decode", spy)
    return seen


def test_no_scope_means_no_memo(tmp_path, monkeypatch):
    """The default path must stay uncached: `run_check` is a public entry point,
    so a caller outside a scan has to see the file as it is now."""
    seen = _counted_decode(monkeypatch)
    f = tmp_path / "a.py"
    f.write_text("first\n", encoding="utf-8")

    assert checks._read(f) == "first\n"
    f.write_text("second\n", encoding="utf-8")
    assert checks._read(f) == "second\n", "an out-of-scope read answered from a cache"
    assert len(seen) == 2


def test_inside_a_scope_one_file_is_decoded_once(tmp_path, monkeypatch):
    """Must-reduce AND must-not-lie: the second read is free and identical."""
    seen = _counted_decode(monkeypatch)
    f = tmp_path / "a.py"
    f.write_text("body\n", encoding="utf-8")

    with read_cache_scope():
        first, second, third = checks._read(f), checks._read(f), checks._read(f)

    assert first == second == third == "body\n"
    assert seen == [str(f)], f"expected 1 decode, got {len(seen)}"


def test_a_scope_does_not_answer_the_next_scope(tmp_path, monkeypatch):
    """The scope IS the invalidation -- there is no mtime or hash check to be
    subtly wrong, so this is the only thing standing between a scan and stale
    content. Two scopes in one process, file changed in between."""
    seen = _counted_decode(monkeypatch)
    f = tmp_path / "a.py"
    f.write_text("before\n", encoding="utf-8")

    with read_cache_scope():
        assert checks._read(f) == "before\n"
    f.write_text("after\n", encoding="utf-8")
    with read_cache_scope():
        assert checks._read(f) == "after\n", "a later scope answered from an earlier one"
    assert len(seen) == 2


def test_none_is_stored_as_a_value_not_as_a_miss(tmp_path, monkeypatch):
    """An oversized file decodes to None. If None read as "absent from cache",
    the most expensive files in a repo would be re-stat'ed once per rule --
    the exact amplification this memo exists to remove."""
    seen = _counted_decode(monkeypatch)
    big = tmp_path / "big.py"
    big.write_text("y" * (MAX_FILE_BYTES + 1), encoding="utf-8")

    with read_cache_scope() as frame:
        assert checks._read(big) is None
        assert checks._read(big) is None
        assert big in frame and frame[big] is None

    assert seen == [str(big)], f"None was re-decoded: {len(seen)} decodes"


def test_a_missing_file_is_also_cached_as_none(tmp_path, monkeypatch):
    """`_decode` swallows OSError, so an absent path is a value like any other."""
    seen = _counted_decode(monkeypatch)
    ghost = tmp_path / "not-there.py"

    with read_cache_scope():
        assert checks._read(ghost) is None
        assert checks._read(ghost) is None

    assert len(seen) == 1


def test_nesting_keeps_the_frames_separate(tmp_path, monkeypatch):
    """An inner scan is a DIFFERENT scan: it gets its own snapshot, and leaving
    it must leave the enclosing snapshot intact rather than emptying it."""
    seen = _counted_decode(monkeypatch)
    f = tmp_path / "a.py"
    f.write_text("outer\n", encoding="utf-8")

    with read_cache_scope() as outer:
        assert checks._read(f) == "outer\n"
        assert set(outer) == {f}
        with read_cache_scope() as inner:
            assert inner is not outer
            assert inner == {}, "the inner frame inherited the outer one's entries"
            assert checks._read(f) == "outer\n"
            assert set(inner) == {f}
        assert set(outer) == {f}, "leaving the inner scope emptied the outer frame"
        assert checks._read(f) == "outer\n"

    assert len(seen) == 2, "each frame decodes once; got {}".format(len(seen))


def test_the_frame_is_popped_even_when_the_scan_raises(tmp_path):
    """A leaked frame would silently become a process-lifetime cache for the
    next scan -- the one failure mode this design exists to avoid."""
    depth = len(_READ_CACHE_STACK)
    try:
        with read_cache_scope():
            assert len(_READ_CACHE_STACK) == depth + 1
            raise RuntimeError("mid-scan failure")
    except RuntimeError:
        pass
    assert len(_READ_CACHE_STACK) == depth, "a frame survived an exception"


def test_the_stack_is_empty_between_tests():
    """Guards the module global itself: a frame left open by any earlier test
    would make every later read in this process answer from it."""
    assert _READ_CACHE_STACK == []
