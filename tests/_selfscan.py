"""One live `radar scan .` per tree state per suite run, shared across xdist workers.

Why: the same deterministic repo-root self-scan was recomputed by many modules and,
because a module-scoped fixture is per WORKER, again on every worker -- measured at
iter 375 as 60 in-process self-scans and ~600 worker-seconds per suite run. The tool's
byte-stability invariant makes the document a pure function of (argv, tree), so it is
safe to compute it once and hand the bytes to every plain reader.

Why the key carries a tree fingerprint and not just argv: a test that edits or touches
any file under the repo must never be served the pre-edit document. `(path, size,
mtime_ns)` changes on every write, so a stale hit is impossible by construction.

Why claim files and `os.replace`: workers are separate processes. `O_CREAT|O_EXCL`
elects exactly one computer per key; `os.replace` publishes atomically so a reader
never sees half a file. A waiter whose computer died (or is slow past the bound)
computes locally instead of raising, because a cache must never fail a test.

Sites that COUNT, MONKEYPATCH or compare a scan against itself for determinism keep
calling the CLI directly -- a cache hit would make them observe nothing.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import time
from collections.abc import Callable, Iterator, Sequence

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Directory NAMES never fingerprinted: VCS data, the venv and caches the run itself writes.
EXCLUDED_DIRS = frozenset({".git", ".venv", "__pycache__", ".pytest_cache"})

#: Upper bound on how long a waiter trusts someone else's claim (behavior 4: <= 120 s).
WAIT_SECONDS = 120.0
POLL_SECONDS = 0.05

Result = tuple[int, str, str]

#: Number of real computations in THIS process -- the test seam for "computed once".
compute_count = 0

_cache_dir: pathlib.Path | None = None


def configure(cache_dir: pathlib.Path | None) -> None:
    """Set the run-wide default cache directory (the conftest does this once per worker)."""
    global _cache_dir
    _cache_dir = cache_dir


@pytest.fixture(scope="module", autouse=True)
def selfscan_run_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Point `selfscan` at ONE directory shared by every xdist worker of this run.

    Imported into a module, this autouse fixture configures the cache before any of the
    module's own fixtures run. Under xdist each worker's basetemp is `<run>/popen-gwN`,
    so the parent is the run directory; without xdist the basetemp itself is the run
    directory (its parent is shared with EARLIER runs, whose dead claims would stall).
    """
    base = tmp_path_factory.getbasetemp()
    configure((base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base) / "selfscan")
    yield


def fingerprint(root: pathlib.Path) -> list[tuple[str, int, int]]:
    """Sorted `(relative posix path, size, mtime_ns)` of every file under `root`."""
    rows: list[tuple[str, int, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for name in filenames:
            path = pathlib.Path(dirpath, name)
            try:
                st = path.stat()
            except FileNotFoundError:
                continue
            rows.append((path.relative_to(root).as_posix(), st.st_size, st.st_mtime_ns))
    return sorted(rows)


def cache_key(argv: Sequence[str], root: pathlib.Path = REPO_ROOT) -> str:
    """sha256 over the argv tuple and the tree fingerprint (behavior 2)."""
    payload = json.dumps({"argv": list(argv), "tree": fingerprint(root)})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_direct(argv: Sequence[str], root: pathlib.Path = REPO_ROOT) -> Result:
    """The uncached value: in-process `main(["scan", ".", *argv])` with cwd = `root`."""
    global compute_count
    from agent_gap_radar.cli import main

    compute_count += 1
    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(root), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        try:
            code = main(["scan", ".", *argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return int(code or 0), out.getvalue(), err.getvalue()


def _load(path: pathlib.Path) -> Result | None:
    """A published entry, or None when absent, corrupt or the wrong shape (behavior 5)."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(value, list) and len(value) == 3 and type(value[0]) is int
            and isinstance(value[1], str) and isinstance(value[2], str)):
        return value[0], value[1], value[2]
    return None


def _publish(path: pathlib.Path, value: Result) -> None:
    """Write-to-temp then `os.replace`, so no reader ever sees a partial entry."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(list(value)), encoding="utf-8")
    os.replace(tmp, path)


def _claim(path: pathlib.Path) -> bool:
    """True when this process won the right to compute the key."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    os.write(fd, str(os.getpid()).encode("ascii"))
    os.close(fd)
    return True


def _claimer_alive(claim: pathlib.Path) -> bool:
    """False when the claim names a pid that no longer exists (a killed earlier worker)."""
    try:
        pid = int(claim.read_text(encoding="ascii") or "0")
    except (OSError, ValueError):
        return True  # claim written but pid not yet flushed: assume alive
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def selfscan(argv: Sequence[str] = (), *, cache_dir: pathlib.Path | None = None,
             root: pathlib.Path = REPO_ROOT,
             compute: Callable[[Sequence[str], pathlib.Path], Result] = run_direct,
             wait_seconds: float = WAIT_SECONDS) -> Result:
    """`(rc, stdout, stderr)` of `radar scan . *argv` at `root`, computed once per key.

    With no cache directory configured or passed, this is exactly `compute(argv, root)`.
    """
    argv = tuple(argv)
    directory = cache_dir if cache_dir is not None else _cache_dir
    if directory is None:
        return compute(argv, root)
    directory.mkdir(parents=True, exist_ok=True)
    key = cache_key(argv, root)
    entry, claim = directory / f"{key}.json", directory / f"{key}.claim"
    hit = _load(entry)
    if hit is not None:
        return hit
    if _claim(claim) or not _wait_for(entry, claim, wait_seconds):
        value = compute(argv, root)
        _publish(entry, value)
        return value
    hit = _load(entry)
    return hit if hit is not None else _recompute(entry, argv, root, compute)


def _wait_for(entry: pathlib.Path, claim: pathlib.Path, wait_seconds: float) -> bool:
    """Poll for another process's result; False on timeout or a dead claimer."""
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if entry.exists():
            return True
        if not _claimer_alive(claim):
            return False
        time.sleep(POLL_SECONDS)
    return False


def _recompute(entry: pathlib.Path, argv: tuple[str, ...], root: pathlib.Path,
               compute: Callable[[Sequence[str], pathlib.Path], Result]) -> Result:
    """A published entry that does not parse is a miss: compute and overwrite it."""
    value = compute(argv, root)
    _publish(entry, value)
    return value
