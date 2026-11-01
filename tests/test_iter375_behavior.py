"""Iter 375 brake: the cross-worker self-scan cache in `tests/_selfscan.py`.

Behaviors 1-5 of the iter-375 spec, pinned on a small temp tree wherever the behavior
allows, so the brake itself never pays for a whole-repo scan except where behavior 1
demands byte-identity with the real CLI on the real repo.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

import _selfscan
from _selfscan import cache_key, fingerprint, run_direct, selfscan

TESTS = pathlib.Path(__file__).resolve().parent


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "tree"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    for skipped in (".git", ".venv", "__pycache__", ".pytest_cache"):
        (root / skipped).mkdir()
        (root / skipped / "noise").write_text("n\n", encoding="utf-8")
    return root


class Counter:
    """A `compute` seam that records every real computation."""

    def __init__(self, value=(0, "doc\n", "")):
        self.calls: list[tuple[str, ...]] = []
        self.value = value

    def __call__(self, argv, root):
        self.calls.append(tuple(argv))
        return self.value


# behavior 1 -- byte-identical to a direct in-process run of the same argv

@pytest.mark.parametrize("argv", [("--gaps", "gaps"), ("--gaps", "gaps", "--json"),
                                  ("--gaps", "gaps", "--floor", "5")],
                         ids=["markdown", "json", "floor"])
def test_b1_cached_value_equals_a_direct_run(argv, tmp_path):
    first = selfscan(argv, cache_dir=tmp_path)
    again = selfscan(argv, cache_dir=tmp_path)
    assert first == again == run_direct(argv)
    assert first[1].endswith("\n") and not first[1].endswith("\n\n")


# behavior 2 -- key covers argv and the fingerprint; exclusions hold

def test_b2_fingerprint_skips_vcs_venv_and_caches(tmp_path):
    root = _tree(tmp_path)
    assert [row[0] for row in fingerprint(root)] == ["pkg/a.py"]


def test_b2_argv_and_any_file_change_change_the_key(tmp_path):
    root = _tree(tmp_path)
    base = cache_key(("--json",), root)
    assert cache_key(("--json",), root) == base
    assert cache_key(("--json", "--x"), root) != base
    (root / "pkg" / "a.py").write_text("x = 22\n", encoding="utf-8")
    edited = cache_key(("--json",), root)
    assert edited != base
    st = (root / "pkg" / "a.py").stat()
    os.utime(root / "pkg" / "a.py", ns=(st.st_atime_ns, st.st_mtime_ns + 1))
    assert cache_key(("--json",), root) != edited
    (root / ".git" / "noise").write_text("changed\n", encoding="utf-8")
    assert cache_key(("--json",), root) == cache_key(("--json",), root)


def test_b2_an_edited_tree_is_recomputed_never_served_stale(tmp_path):
    root, counter = _tree(tmp_path), Counter()
    selfscan(("a",), cache_dir=tmp_path / "c", root=root, compute=counter)
    (root / "pkg" / "b.py").write_text("y\n", encoding="utf-8")
    selfscan(("a",), cache_dir=tmp_path / "c", root=root, compute=counter)
    assert counter.calls == [("a",), ("a",)]


# behavior 3 -- one shared directory; nothing written into the scanned tree

def test_b3_entries_live_only_in_the_cache_dir(tmp_path):
    root, cache = _tree(tmp_path), tmp_path / "cache"
    before = fingerprint(root)
    selfscan(("a",), cache_dir=cache, root=root, compute=Counter())
    assert fingerprint(root) == before
    assert sorted(p.suffix for p in cache.iterdir()) == [".claim", ".json"]


def test_b3_the_autouse_fixture_points_at_the_run_directory(selfscan_run_cache_dir):
    base = selfscan_run_cache_dir
    assert _selfscan._cache_dir is not None
    assert _selfscan._cache_dir.parent in (base, base.parent)


@pytest.fixture()
def selfscan_run_cache_dir(tmp_path_factory, request):
    request.getfixturevalue("selfscan_run_cache")
    return tmp_path_factory.getbasetemp()


from _selfscan import selfscan_run_cache  # noqa: E402,F401  (fixture under test)


# behavior 4 -- one computation across processes; bounded wait, never raises

CHILD = """
import pathlib, sys
sys.path.insert(0, {tests!r})
import _selfscan
calls = []
def compute(argv, root):
    calls.append(1)
    return (0, "doc\\n", "")
print(_selfscan.selfscan(("a",), cache_dir=pathlib.Path({cache!r}),
      root=pathlib.Path({root!r}), compute=compute), len(calls))
"""


def test_b4_two_processes_compute_the_same_key_once(tmp_path):
    root, cache = _tree(tmp_path), tmp_path / "cache"
    code = CHILD.format(tests=str(TESTS), cache=str(cache), root=str(root))
    procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
             for _ in range(2)]
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    assert all(o.startswith("(0, 'doc\\n', '')") for o in outs), outs
    assert sorted(int(o.rsplit(" ", 1)[1]) for o in outs) == [0, 1], outs


def test_b4_a_claim_without_a_result_times_out_into_a_local_compute(tmp_path):
    root, cache, counter = _tree(tmp_path), tmp_path / "cache", Counter()
    cache.mkdir()
    key = cache_key(("a",), root)
    (cache / f"{key}.claim").write_text(str(os.getpid()), encoding="ascii")
    assert selfscan(("a",), cache_dir=cache, root=root, compute=counter,
                    wait_seconds=0.2) == counter.value
    assert counter.calls == [("a",)]


def test_b4_the_wait_bound_is_at_most_120_seconds():
    assert 0 < _selfscan.WAIT_SECONDS <= 120


# behavior 5 -- corrupt entries are misses; failing scans are cached values

@pytest.mark.parametrize("junk", ["{not json", "[0, 1]", '{"rc": 0}', '["0", "a", "b"]', ""])
def test_b5_a_corrupt_entry_is_recomputed(junk, tmp_path):
    root, cache, counter = _tree(tmp_path), tmp_path / "cache", Counter()
    cache.mkdir()
    (cache / f"{cache_key(('a',), root)}.json").write_text(junk, encoding="utf-8")
    assert selfscan(("a",), cache_dir=cache, root=root, compute=counter) == counter.value
    assert counter.calls == [("a",)]
    assert json.loads((cache / f"{cache_key(('a',), root)}.json").read_text()) == [0, "doc\n", ""]


def test_b5_a_failing_scan_is_cached_like_a_success(tmp_path):
    root, counter = _tree(tmp_path), Counter((2, "", "Error: boom\n"))
    for _ in range(2):
        assert selfscan(("a",), cache_dir=tmp_path / "c", root=root,
                        compute=counter) == (2, "", "Error: boom\n")
    assert counter.calls == [("a",)]
