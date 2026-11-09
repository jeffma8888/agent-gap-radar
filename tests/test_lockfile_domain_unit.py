"""Unit pins for the lockfile-domain helpers in `checks`.

The behaviour (a lockfile swept in by a wildcard glob is never mitigation
evidence, and never read by a `content_absent` rule) is the test engineer's to
pin end to end. These nodes pin only the two pure helpers it rests on, so a
regression in the literal-glob predicate is named here rather than diagnosed
from a verdict flip three layers up.
"""

from __future__ import annotations

import pathlib

import pytest

from agent_gap_radar import checks


@pytest.mark.parametrize(("glob", "literal"), [
    ("**/package-lock.json", True),
    ("package-lock.json", True),
    ("web/package-lock.json", True),
    ("**/*.json", False),
    ("**/*", False),
    ("**/package-lock.*", False),
    ("**/Package-Lock.json", False),
])
def test_names_literally_is_a_plain_last_segment_compare(glob: str,
                                                         literal: bool) -> None:
    assert checks._names_literally(glob, "package-lock.json") is literal


def test_every_lockfile_basename_is_stored_lower_cased() -> None:
    assert all(name == name.lower() for name in checks.LOCKFILE_BASENAMES)


def test_drop_keeps_non_lockfiles_and_literal_asks(tmp_path: pathlib.Path) -> None:
    lock = tmp_path / "package-lock.json"
    other = tmp_path / "config" / "policy.json"
    other.parent.mkdir()
    for path in (lock, other):
        path.write_text("{}\n", encoding="utf-8")  # the literal ask is matched on disk
    files = [other, lock]
    assert checks._drop_wildcard_lockfiles(tmp_path, files, ["**/*.json"]) == [other]
    assert checks._drop_wildcard_lockfiles(
        tmp_path, files, ["**/*.json", "**/package-lock.json"]) == files


def test_a_literal_glob_that_does_not_match_the_path_keeps_nothing(
        tmp_path: pathlib.Path) -> None:
    """Judged per glob: `web/package-lock.json` names the basename but not
    the root lockfile, so only the wildcard reached it and it is dropped."""
    lock = tmp_path / "package-lock.json"
    assert checks._drop_wildcard_lockfiles(
        tmp_path, [lock], ["**/*.json", "web/package-lock.json"]) == []


def test_drop_matches_basenames_case_insensitively(tmp_path: pathlib.Path) -> None:
    assert checks._drop_wildcard_lockfiles(
        tmp_path, [tmp_path / "Cargo.LOCK"], ["**/*"]) == []
