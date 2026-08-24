"""Unit tests for the scan-scoped enumeration memo in `checks`.

Scope: the memo PLUMBING only -- the frame stack, its lifetime, its key, and
what `iter_files` hands back. The black-box behaviors (a scan walks each domain
once; `radar scan` bytes are unchanged) are BEHAVIOR tests and belong to the
test engineer.

Every claim is asserted against a REAL directory on disk rather than a stubbed
seam, because the defect this memo could introduce is returning the WRONG file
list -- a stale one, or one belonging to a different question -- and a stub
cannot exhibit that. The enumeration count is observed by wrapping
`_enumerate_files`, which is the only place a real walk happens.

`tmp_path` is not a git repo, so every tree here answers through the walked
branch. That is deliberate: the walked branch re-reads the filesystem on every
call, so a file added between two calls is visible unless the memo hid it,
which is what makes "the memo is not consulted" falsifiable at all.
"""

from __future__ import annotations

import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import _FILE_CACHE_STACK, file_cache_scope, iter_files

PY_GLOBS = ["**/*.py"]


@pytest.fixture()
def target(tmp_path: pathlib.Path) -> pathlib.Path:
    """A non-git tree holding one code file and one test file.

    The test file is what gives `exclude_tests` two different answers to key on.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    pass\n",
                                                  encoding="utf-8")
    (tmp_path / "notes.md").write_text("# not python\n", encoding="utf-8")
    return tmp_path


def _counted_enumeration(monkeypatch) -> list[tuple[str, tuple[str, ...], bool]]:
    """Record every ACTUAL enumeration, then delegate. Returns the growing log."""
    seen: list[tuple[str, tuple[str, ...], bool]] = []
    real = checks._enumerate_files

    def spy(target: pathlib.Path, globs: list[str],
            exclude_tests: bool) -> list[pathlib.Path]:
        seen.append((str(target), tuple(globs), exclude_tests))
        return real(target, globs, exclude_tests)

    monkeypatch.setattr(checks, "_enumerate_files", spy)
    return seen


def _names(target: pathlib.Path, paths: list[pathlib.Path]) -> list[str]:
    return sorted(p.relative_to(target).as_posix() for p in paths)


def test_no_scope_means_no_memo(target, monkeypatch):
    """The default path must stay uncached: `iter_files` is a public entry point,
    so a caller outside a scan has to see the tree as it is now."""
    seen = _counted_enumeration(monkeypatch)

    before = _names(target, iter_files(target, PY_GLOBS))
    (target / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    after = _names(target, iter_files(target, PY_GLOBS))

    assert before == ["pkg/a.py", "tests/test_a.py"]
    assert after == ["pkg/a.py", "pkg/b.py", "tests/test_a.py"], (
        "an out-of-scope enumeration answered from a cache")
    assert len(seen) == 2


def test_inside_a_scope_one_domain_is_enumerated_once(target, monkeypatch):
    """Must-reduce AND must-not-lie: the second ask is free and identical."""
    seen = _counted_enumeration(monkeypatch)

    with file_cache_scope():
        first = iter_files(target, PY_GLOBS)
        second = iter_files(target, PY_GLOBS)
        third = iter_files(target, PY_GLOBS)

    assert _names(target, first) == _names(target, second) == _names(target, third)
    assert _names(target, first) == ["pkg/a.py", "tests/test_a.py"]
    assert len(seen) == 1, f"expected 1 enumeration, got {len(seen)}"


def test_a_scope_does_not_answer_the_next_scope(target, monkeypatch):
    """The scope IS the invalidation -- there is no mtime or directory-hash check
    to be subtly wrong, so this is the only thing standing between a later scan
    and a stale file list. Two scopes in one process, tree changed in between."""
    seen = _counted_enumeration(monkeypatch)

    with file_cache_scope():
        assert _names(target, iter_files(target, PY_GLOBS)) == ["pkg/a.py",
                                                               "tests/test_a.py"]
    (target / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    with file_cache_scope():
        assert _names(target, iter_files(target, PY_GLOBS)) == [
            "pkg/a.py", "pkg/b.py", "tests/test_a.py"
        ], "a later scope answered from an earlier one"

    assert len(seen) == 2


def test_the_key_separates_the_two_exclude_tests_answers(target, monkeypatch):
    """The fail-open this key exists to prevent. Measured on the real register, 3
    of 8 glob sets are asked under BOTH values in one scan and all 3 answer
    differently, so a globs-only key would hand the narrowed domain to a rule
    that asked for the wide one."""
    seen = _counted_enumeration(monkeypatch)

    with file_cache_scope():
        wide = _names(target, iter_files(target, PY_GLOBS))
        narrow = _names(target, iter_files(target, PY_GLOBS, exclude_tests=True))
        assert _names(target, iter_files(target, PY_GLOBS)) == wide
        assert _names(target, iter_files(target, PY_GLOBS,
                                        exclude_tests=True)) == narrow

    assert wide == ["pkg/a.py", "tests/test_a.py"]
    assert narrow == ["pkg/a.py"], "exclude_tests did not narrow the domain"
    assert len(seen) == 2, (
        "the two exclude_tests values shared one cache entry: "
        f"{len(seen)} enumerations for 4 asks over 2 keys")


def test_the_key_separates_two_glob_sets(target, monkeypatch):
    """Two questions, two answers: a key that collapsed them would answer one
    rule's glob set with another's file list."""
    seen = _counted_enumeration(monkeypatch)

    with file_cache_scope():
        py = _names(target, iter_files(target, PY_GLOBS))
        md = _names(target, iter_files(target, ["**/*.md"]))
        assert _names(target, iter_files(target, PY_GLOBS)) == py

    assert py == ["pkg/a.py", "tests/test_a.py"]
    assert md == ["notes.md"]
    assert len(seen) == 2


def test_the_returned_list_is_never_the_cached_one(target, monkeypatch):
    """A caller that sorted or truncated the result in place would silently narrow
    every later rule asking the same question. Paths are immutable, so a shallow
    copy is enough -- what must not be shared is the LIST."""
    seen = _counted_enumeration(monkeypatch)

    with file_cache_scope() as frame:
        first = iter_files(target, PY_GLOBS)
        first.clear()
        first.append(target / "fabricated.py")
        second = iter_files(target, PY_GLOBS)

        assert _names(target, second) == ["pkg/a.py", "tests/test_a.py"], (
            "mutating one result corrupted the snapshot")
        assert second is not first
        cached = frame[(str(target), tuple(PY_GLOBS), False)]
        assert cached is not first and cached is not second, (
            "the cached list itself was handed to a caller")

    assert len(seen) == 1


def test_nesting_keeps_the_frames_separate(target, monkeypatch):
    """An inner scan is a DIFFERENT scan: it gets its own snapshot, and leaving it
    must leave the enclosing snapshot intact rather than emptying it."""
    seen = _counted_enumeration(monkeypatch)
    key = (str(target), tuple(PY_GLOBS), False)

    with file_cache_scope() as outer:
        assert _names(target, iter_files(target, PY_GLOBS)) == ["pkg/a.py",
                                                               "tests/test_a.py"]
        assert set(outer) == {key}
        with file_cache_scope() as inner:
            assert inner is not outer
            assert inner == {}, "the inner frame inherited the outer one's entries"
            assert _names(target, iter_files(target, PY_GLOBS)) == ["pkg/a.py",
                                                                   "tests/test_a.py"]
            assert set(inner) == {key}
        assert set(outer) == {key}, "leaving the inner scope emptied the outer frame"
        assert _names(target, iter_files(target, PY_GLOBS)) == ["pkg/a.py",
                                                               "tests/test_a.py"]

    assert len(seen) == 2, f"each frame enumerates once; got {len(seen)}"


def test_the_frame_is_popped_even_when_the_scan_raises(target):
    """A leaked frame would silently become a process-lifetime cache for the next
    scan -- the one failure mode this design exists to avoid."""
    depth = len(_FILE_CACHE_STACK)
    try:
        with file_cache_scope():
            assert len(_FILE_CACHE_STACK) == depth + 1
            iter_files(target, PY_GLOBS)
            raise RuntimeError("mid-scan failure")
    except RuntimeError:
        pass
    assert len(_FILE_CACHE_STACK) == depth, "a frame survived an exception"


def test_the_stack_is_empty_between_tests():
    """Guards the module global itself: a frame left open by any earlier test would
    make every later enumeration in this process answer from it."""
    assert _FILE_CACHE_STACK == []
