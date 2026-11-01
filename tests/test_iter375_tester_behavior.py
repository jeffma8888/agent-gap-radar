"""Iteration 375 (tester): black-box pins for the cross-worker self-scan cache.

Drives the public surface of `tests/_selfscan.py` (`selfscan`, `cache_key`,
`fingerprint`, `configure`, the autouse `selfscan_run_cache` fixture) and the real CLI on
small temp trees. The oracle for "byte-identical to a direct run" is THIS module's own
in-process `cli.main` call, not the helper's `run_direct`, so a helper that drifted from
the CLI could not agree with itself. Cache entries are located by CONTENT (the published
value), never by file name, so the pins do not depend on how entries are spelled.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import textwrap
import time

import pytest

import _selfscan
from _selfscan import cache_key, configure, fingerprint, selfscan
from _selfscan import selfscan_run_cache  # noqa: F401  (autouse: behavior 3 probe)

TESTS = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS.parent
SIX = ("25", "265", "364", "28", "342", "298")


def _direct(argv, root):
    """Independent oracle: in-process `radar scan . *argv` with cwd = root."""
    from agent_gap_radar.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        try:
            code = main(["scan", ".", *argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return int(code or 0), out.getvalue(), err.getvalue()


@pytest.fixture(scope="module")
def scan_tree(tmp_path_factory):
    """A small scannable tree: the live register plus one source file."""
    root = tmp_path_factory.mktemp("t375scan") / "tree"
    shutil.copytree(REPO_ROOT / "gaps", root / "gaps")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("import importlib\nimportlib.reload(x)\n",
                                         encoding="utf-8")
    return root


def _tree(tmp_path):
    root = tmp_path / "tree"
    (root / "pkg" / "__pycache__").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "pkg" / "__pycache__" / "a.pyc").write_bytes(b"\0")
    for skipped in (".git", ".venv", ".pytest_cache"):
        (root / skipped).mkdir()
        (root / skipped / "noise").write_text("n\n", encoding="utf-8")
    return root


class Counter:
    def __init__(self, value=(0, "doc\n", "")):
        self.calls = 0
        self.value = value

    def __call__(self, argv, root):
        self.calls += 1
        return self.value


def _entries(cache_dir, value):
    """Files in cache_dir whose content parses to `value` (located by content)."""
    found = []
    for path in pathlib.Path(cache_dir).rglob("*"):
        if not path.is_file():
            continue
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if parsed == list(value):
            found.append(path)
    return found


def _git_status():
    return subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=True).stdout


# ------------------------------------------------ behavior 1: byte-identical to direct

ARGVS = [("--gaps", "gaps"), ("--gaps", "gaps", "--json"),
         ("--gaps", "gaps", "--floor", "3"), ("--gaps", "gaps", "--json", "--floor", "1")]


@pytest.mark.parametrize("argv", ARGVS, ids=["md", "json", "floor3", "json-floor1"])
def test_b1_miss_and_hit_are_both_byte_identical_to_the_cli(argv, scan_tree, tmp_path):
    want = _direct(argv, scan_tree)
    assert want[0] == 0 and want[1], want[2]
    miss = selfscan(argv, cache_dir=tmp_path / "c", root=scan_tree)
    hit = selfscan(argv, cache_dir=tmp_path / "c", root=scan_tree)
    assert miss == want
    assert hit == want
    assert type(hit[0]) is int and type(hit[1]) is str and type(hit[2]) is str
    assert hit[1].endswith("\n") and not hit[1].endswith("\n\n")


def test_b1_the_floor_variant_is_a_distinct_document(scan_tree, tmp_path):
    """Anti-vacuity: the floor variant really is a different value, cached separately."""
    a = selfscan(("--gaps", "gaps", "--json", "--floor", "1"), cache_dir=tmp_path, root=scan_tree)
    b = selfscan(("--gaps", "gaps", "--json", "--floor", "9"), cache_dir=tmp_path, root=scan_tree)
    assert a[1] != b[1]
    assert json.loads(a[1])["confidence_floor"] != json.loads(b[1])["confidence_floor"]


def test_b1_an_error_run_is_byte_identical_too(scan_tree, tmp_path):
    argv = ("--gaps", "no-such-register")
    want = _direct(argv, scan_tree)
    assert want[0] == 2 and want[1] == "" and want[2].startswith("Error: "), want
    assert selfscan(argv, cache_dir=tmp_path, root=scan_tree) == want
    assert selfscan(argv, cache_dir=tmp_path, root=scan_tree) == want


def test_b1_no_cache_configured_is_a_plain_pass_through(tmp_path, monkeypatch):
    monkeypatch.setattr(_selfscan, "_cache_dir", _selfscan._cache_dir)  # restore after
    configure(None)
    root = _tree(tmp_path)
    before = sorted(p for p in tmp_path.rglob("*"))
    counter = Counter()
    assert selfscan(("--x",), root=root, compute=counter) == counter.value
    assert selfscan(("--x",), root=root, compute=counter) == counter.value
    assert counter.calls == 2, "with no cache dir every call must compute"
    assert sorted(p for p in tmp_path.rglob("*")) == before, "pass-through wrote files"


# ------------------------------------------------ behavior 2: key = argv + fingerprint

def test_b2_fingerprint_rows_are_sorted_relative_size_mtime(tmp_path):
    root = _tree(tmp_path)
    (root / "z.txt").write_text("zz\n", encoding="utf-8")
    (root / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (root / ".github").mkdir()
    (root / ".github" / "ci.yml").write_text("on: push\n", encoding="utf-8")
    rows = [tuple(r) for r in fingerprint(root)]
    assert rows == sorted(rows)
    paths = [r[0] for r in rows]
    assert paths == sorted([".github/ci.yml", ".gitignore", "pkg/a.py", "z.txt"]), paths
    for rel, size, mtime in rows:
        st = (root / rel).stat()
        assert (size, mtime) == (st.st_size, st.st_mtime_ns), rel


@pytest.mark.parametrize("change", ["touch", "same-size-edit", "add", "delete",
                                    "dotfile", "lookalike-dir"])
def test_b2_any_fingerprinted_change_changes_the_key(change, tmp_path):
    root = _tree(tmp_path)
    argv = ("--gaps", "gaps")
    before = cache_key(argv, root)
    target = root / "pkg" / "a.py"
    if change == "touch":
        st = target.stat()
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    elif change == "same-size-edit":
        st = target.stat()
        target.write_text("x = 2\n", encoding="utf-8")  # same size; a real write moves mtime
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 1))
    elif change == "add":
        (root / "pkg" / "b.py").write_text("", encoding="utf-8")
    elif change == "delete":
        target.unlink()
    elif change == "dotfile":
        (root / ".gitignore").write_text("x\n", encoding="utf-8")
    elif change == "lookalike-dir":
        (root / ".github").mkdir()
        (root / ".github" / "w.yml").write_text("w\n", encoding="utf-8")
    assert cache_key(argv, root) != before, change


@pytest.mark.parametrize("where", [".git", ".venv", ".pytest_cache", "pkg/__pycache__",
                                   "deep/nested/__pycache__"])
def test_b2_excluded_dirs_never_change_the_key(where, tmp_path):
    root = _tree(tmp_path)
    before = cache_key(("--json",), root)
    d = root / where
    d.mkdir(parents=True, exist_ok=True)
    (d / "fresh").write_text("new\n", encoding="utf-8")
    if (d / "noise").exists():
        (d / "noise").write_text("changed noise\n", encoding="utf-8")
    assert cache_key(("--json",), root) == before, where


@pytest.mark.parametrize("a,b", [((), ("--json",)),
                                 (("--gaps", "gaps", "--json"), ("--json", "--gaps", "gaps")),
                                 (("--floor", "3"), ("--floor", "4")),
                                 (("--floor", "34"), ("--floor3", "4"))])
def test_b2_argv_is_part_of_the_key(a, b, tmp_path):
    root = _tree(tmp_path)
    assert cache_key(a, root) != cache_key(b, root)
    assert cache_key(a, root) == cache_key(tuple(a), root)


def test_b2_an_edit_between_calls_is_recomputed_not_served_stale(tmp_path):
    root = _tree(tmp_path)
    cache = tmp_path / "cache"
    first = Counter((0, "before\n", ""))
    assert selfscan(("--json",), cache_dir=cache, root=root, compute=first) == first.value
    target = root / "pkg" / "a.py"
    st = target.stat()
    target.write_text("x = 3\n", encoding="utf-8")
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    second = Counter((0, "after\n", ""))
    assert selfscan(("--json",), cache_dir=cache, root=root, compute=second) == second.value
    assert second.calls == 1
    # and the unchanged argv on the edited tree is now a hit
    third = Counter((0, "never\n", ""))
    assert selfscan(("--json",), cache_dir=cache, root=root, compute=third) == second.value
    assert third.calls == 0


# ------------------------------------------------ behavior 3: one dir, never in the repo

def test_b3_a_cached_scan_writes_only_into_the_cache_dir(scan_tree, tmp_path):
    before = [tuple(r) for r in fingerprint(scan_tree)]
    cache = tmp_path / "cache"
    selfscan(("--gaps", "gaps", "--json"), cache_dir=cache, root=scan_tree)
    selfscan(("--gaps", "gaps", "--json"), cache_dir=cache, root=scan_tree)
    assert [tuple(r) for r in fingerprint(scan_tree)] == before, "the scanned tree changed"
    assert any(cache.iterdir()), "nothing was cached"
    outside = {p for p in tmp_path.iterdir()} - {cache}
    assert outside == set(), outside


def test_b3_the_autouse_fixture_caches_under_the_run_basetemp(tmp_path_factory, tmp_path):
    """With no cache_dir passed, entries land under getbasetemp().parent, shared run-wide."""
    root = _tree(tmp_path)
    value = (0, f"t375-autouse-{os.getpid()}-{time.time_ns()}\n", "")
    counter = Counter(value)
    assert selfscan(("--t375",), root=root, compute=counter) == value
    run_dir = tmp_path_factory.getbasetemp().parent
    hits = []
    for dirpath, _dirs, files in os.walk(run_dir):
        if "selfscan" not in dirpath:
            continue
        for name in files:
            p = pathlib.Path(dirpath, name)
            with contextlib.suppress(OSError, ValueError):
                if json.loads(p.read_text(encoding="utf-8")) == list(value):
                    hits.append(p)
    assert len(hits) == 1, hits
    # one shared directory: not inside this worker's own test tmp dir, not in the repo
    assert tmp_path not in hits[0].parents
    assert REPO_ROOT not in hits[0].parents
    if os.environ.get("PYTEST_XDIST_WORKER"):
        base = tmp_path_factory.getbasetemp()
        assert base not in hits[0].parents, "a per-worker dir is not shared across workers"
    assert selfscan(("--t375",), root=root, compute=counter) == value
    assert counter.calls == 1


def test_b3_selfscan_never_touches_the_repo_tree(tmp_path):
    before = _git_status()
    selfscan(("--t375-probe",), cache_dir=tmp_path, root=REPO_ROOT,
             compute=Counter((0, "probe\n", "")))
    assert _git_status() == before


# ------------------------------------------------ behavior 4: cross-process, once

_CHILD = textwrap.dedent("""
    import json, os, pathlib, sys, time
    sys.path.insert(0, {tests!r})
    import _selfscan
    cache, root, log, go, mode = (pathlib.Path(a) for a in sys.argv[1:6])
    mode = str(mode)
    def compute(argv, r):
        with open(log, "a") as fh:
            fh.write(f"{{os.getpid()}}\\n")
        if mode == "hang":
            time.sleep(60)
        time.sleep(1.0)
        return (3, "shared\\n", "warn\\n")
    while not go.exists():
        time.sleep(0.01)
    print(json.dumps(list(_selfscan.selfscan(("--k",), cache_dir=cache, root=root,
                                             compute=compute))))
""")


def _spawn(tmp_path, root, mode="normal"):
    script = tmp_path / "child.py"
    script.write_text(_CHILD.format(tests=str(TESTS)), encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(script), str(tmp_path / "cache"), str(root),
         str(tmp_path / "log"), str(tmp_path / "go"), mode],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_b4_two_concurrent_processes_compute_once_and_agree(tmp_path):
    root = _tree(tmp_path)
    procs = [_spawn(tmp_path, root) for _ in range(3)]
    (tmp_path / "go").write_text("", encoding="utf-8")
    outs = []
    for p in procs:
        out, err = p.communicate(timeout=90)
        assert p.returncode == 0, err
        outs.append(json.loads(out))
    assert outs == [[3, "shared\n", "warn\n"]] * 3
    log = (tmp_path / "log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1, f"computed {len(log)} times across processes: {log}"
    # a later process (fresh interpreter) is a pure hit
    late = _spawn(tmp_path, root)
    out, err = late.communicate(timeout=90)
    assert late.returncode == 0, err
    assert json.loads(out) == [3, "shared\n", "warn\n"]
    assert len((tmp_path / "log").read_text(encoding="utf-8").splitlines()) == 1


def test_b4_a_live_claim_that_never_publishes_times_out_into_a_local_compute(tmp_path):
    root = _tree(tmp_path)
    hog = _spawn(tmp_path, root, mode="hang")
    (tmp_path / "go").write_text("", encoding="utf-8")
    try:
        deadline = time.monotonic() + 30
        while not (tmp_path / "log").exists():
            assert time.monotonic() < deadline, "the hog never claimed"
            time.sleep(0.02)
        counter = Counter((0, "local\n", ""))
        t0 = time.monotonic()
        got = selfscan(("--k",), cache_dir=tmp_path / "cache", root=root,
                       compute=counter, wait_seconds=0.5)
        elapsed = time.monotonic() - t0
        assert got == counter.value
        assert counter.calls == 1
        assert 0.4 <= elapsed < 10, f"waited {elapsed:.2f}s against a 0.5s bound"
    finally:
        hog.kill()
        hog.communicate()


def test_b4_a_compute_that_raised_does_not_wedge_or_raise_for_the_next_caller(tmp_path):
    root = _tree(tmp_path)
    cache = tmp_path / "cache"

    def boom(argv, r):
        raise RuntimeError("scan blew up")

    with pytest.raises(RuntimeError):
        selfscan(("--k",), cache_dir=cache, root=root, compute=boom)
    counter = Counter((0, "recovered\n", ""))
    t0 = time.monotonic()
    got = selfscan(("--k",), cache_dir=cache, root=root, compute=counter, wait_seconds=1.0)
    assert got == counter.value
    assert time.monotonic() - t0 < 10


def test_b4_the_default_wait_bound_is_positive_and_at_most_120_seconds():
    import inspect

    default = inspect.signature(selfscan).parameters["wait_seconds"].default
    assert isinstance(default, (int, float)) and 0 < default <= 120, default


# ------------------------------------------------ behavior 5: corrupt = miss; rc cached

JUNK = ["", "{", "[0, \"a\"", "null", "{\"rc\": 0}", "[0, \"a\"]",
        "[0, \"a\", \"b\", \"c\"]", "[\"0\", \"a\", \"b\"]", "[0, 1, \"b\"]",
        "[0, \"a\", null]", "[true, \"a\", \"b\"]", "[0.0, \"a\", \"b\"]", "\u00ff\u00fe"]


@pytest.mark.parametrize("junk", JUNK, ids=[f"j{i}" for i in range(len(JUNK))])
def test_b5_a_corrupt_entry_is_recomputed_and_repaired(junk, tmp_path):
    root = _tree(tmp_path)
    cache = tmp_path / "cache"
    old = Counter((1, "old\n", ""))
    selfscan(("--k",), cache_dir=cache, root=root, compute=old)
    entries = _entries(cache, old.value)
    assert len(entries) == 1, entries
    entries[0].write_text(junk, encoding="utf-8")
    fresh = Counter((0, "fresh\n", ""))
    got = selfscan(("--k",), cache_dir=cache, root=root, compute=fresh)
    assert got == (0, "fresh\n", "")
    assert type(got[0]) is int
    assert fresh.calls == 1
    never = Counter((9, "never\n", ""))
    assert selfscan(("--k",), cache_dir=cache, root=root, compute=never) == fresh.value
    assert never.calls == 0, "the repaired entry was not republished"


@pytest.mark.parametrize("value", [(2, "", "Error: x\n"), (1, "doc\n", ""), (0, "", "")])
def test_b5_any_rc_is_cached_and_returned_exactly(value, tmp_path):
    root = _tree(tmp_path)
    counter = Counter(value)
    for _ in range(3):
        assert selfscan(("--k",), cache_dir=tmp_path / "c", root=root,
                        compute=counter) == value
    assert counter.calls == 1


def test_b5_a_real_failing_scan_is_cached_like_a_success(scan_tree, tmp_path):
    argv = ("--gaps", "missing-dir")
    first = selfscan(argv, cache_dir=tmp_path, root=scan_tree)
    assert first[0] == 2 and first[2].startswith("Error: ")
    assert _entries(tmp_path, first), "a non-zero rc was not cached"
    never = Counter((0, "never\n", ""))
    assert selfscan(argv, cache_dir=tmp_path, root=scan_tree, compute=never) == first
    assert never.calls == 0


# ------------------------------------------------ behavior 6: the six re-pointed modules

@pytest.mark.parametrize("n", SIX)
def test_b6_direct_sites_carry_a_reason_and_selfscan_users_share_the_cache(n):
    text = (TESTS / f"test_iter{n}_behavior.py").read_text(encoding="utf-8")
    directs = [ln.strip() for ln in text.splitlines() if "# direct:" in ln]
    assert directs, f"iter{n}: no `# direct:` site named (every module keeps one)"
    for ln in directs:
        assert ln.split("# direct:", 1)[1].strip(), f"iter{n}: reasonless direct: {ln}"
    if "selfscan(" in text:
        # without the autouse fixture selfscan silently degrades to a direct run
        assert "selfscan_run_cache" in text, f"iter{n} calls selfscan without the cache"


def test_b6_at_least_one_module_reads_through_the_cache():
    users = [n for n in SIX
             if "selfscan(" in (TESTS / f"test_iter{n}_behavior.py").read_text("utf-8")]
    assert len(users) >= 3, users
