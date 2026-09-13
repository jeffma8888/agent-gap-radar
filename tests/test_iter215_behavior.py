"""Iteration 215 behaviors: the committed pytest configuration schedules this suite with
pytest-xdist's WORK-STEALING distributor instead of the default static `load` chunking, so
the idle-worker tail stops being paid inside every stage of every iteration.

BLACK-BOX, and the ISOLATION CONTRACT IS HONORED. Nothing here reads `src/`, `tools/`, the
engineer's notes, the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors. The two configuration claims are read
from the committed `pyproject.toml` with `tomllib` -- the spec names that file and that
parser as the surface under test -- and everything else is measured by SPAWNING pytest over
a fixture written under `tmp_path`, or by reading the running session's own `pytestconfig`.

DESIGN NOTES a later reader should not have to re-derive.

* A DEPENDENCY FLOOR IS A FLOOR, NOT A LITERAL. Behaviour 2 asks for `pytest-xdist>=3.2`
  "or higher" (3.2 is the release that introduced `worksteal`), so the pin is parsed and
  compared as a version tuple. A test that pinned the string `>=3.2` would red on a
  TIGHTER pin and would reward loosening the floor, which is backwards.

* NON-VACUITY IS MEASURED, NOT ASSERTED, in two directions. (a) Behaviour 4 is the armed
  control's negative half: the identical spawn with a nonsense strategy must FAIL, because
  behaviour 3 alone would pass over an xdist that silently ignored an unknown `--dist`
  value. (b) The summary-count parser behaviour 7 leans on is first shown to report
  `{'passed': 2, 'skipped': 1}` for a synthetic summary line and to DISCRIMINATE a
  different one, so a parser that had rotted into returning `{}` could not make the
  scheduler-parity assertion pass by matching nothing against nothing.

* EVERY SPAWNED PROBE IS HERMETIC. `-o addopts=` so the probe cannot inherit this repo's
  own config, `-p no:cacheprovider` so nothing is written outside `tmp_path`, `cwd` set to
  `tmp_path` so the probe's rootdir is the fixture directory and not this repo, and every
  `PYTEST_*` environment variable dropped so an outer xdist worker's own bookkeeping
  cannot leak in. No probe touches the network and no probe writes above `tmp_path`.

* AMBIGUITY NOTED FOR THE PM -- BEHAVIOUR 5 IS VACUOUS IN THE SHAPE THAT SHIPS, AND THE
  SPEC ALREADY HALF-KNOWS IT. Behaviour 5 is billed as "the only behaviour that proves
  what a bare `uv run pytest` gets", as `numprocesses >= 2 implies dist == "worksteal"`.
  A test body never executes in the process that owns those options: under a bare
  `uv run pytest` (which is `-n auto`) the test process reports
  `getoption("numprocesses") is None` and `getoption("dist") == "no"`, so the guard the
  spec itself prescribes in note (c) -- accept `None` as undistributed -- makes the
  implication vacuously true in exactly the configuration it was meant to prove. The
  reading tested here keeps the spec's implication verbatim AND adds the in-session claim
  that is NOT vacuous in that shape: `pytestconfig.getini("addopts")`, read in the same
  process, is the committed token list and carries `--dist worksteal`. That is what
  distinguishes a session that read the committed default from one that did not.

* BEHAVIOUR 7 IS ENCODED AS SCHEDULER PARITY OVER A FIXTURE, NOT AS A SECOND FULL SUITE.
  "The full suite's collected and pass/skip counts are unchanged from a `--dist load` run
  of the same tree" cannot be a committed assertion: it would run the whole suite twice
  inside itself, and this product's convention (iteration 123) is deterministic counts and
  never a clock. Committed here is the invariant that claim rests on -- the same file, run
  under `--dist load` and under `--dist worksteal`, collects the same tests and produces
  the same passed/skipped counts, including a skip that must survive as a skip. The
  whole-suite instance of the same comparison belongs to the run log, not to the suite.
"""

from __future__ import annotations

import os
import pathlib
import re
import shlex
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from typing import Final

import pytest

REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT: Final[pathlib.Path] = REPO_ROOT / "pyproject.toml"

WORKSTEAL: Final[str] = "worksteal"
XDIST_FLOOR: Final[tuple[int, int]] = (3, 2)
PYTEST_FLOOR: Final[tuple[int, int]] = (8, 0)
EXPECTED_DEV_PACKAGES: Final[frozenset[str]] = frozenset({"pytest", "pytest-xdist"})
EXPECTED_RUNTIME_DEPENDENCIES: Final[tuple[str, ...]] = ("pydantic>=2",)

SPAWN_TIMEOUT: Final[int] = 300

TWO_PASSING_TESTS: Final[str] = (
    "def test_alpha() -> None:\n"
    "    assert True\n"
    "\n"
    "\n"
    "def test_beta() -> None:\n"
    "    assert True\n"
)

TWO_PASSING_ONE_SKIPPED: Final[str] = (
    "import pytest\n"
    "\n"
    "\n"
    "def test_alpha() -> None:\n"
    "    assert True\n"
    "\n"
    "\n"
    "def test_beta() -> None:\n"
    "    assert True\n"
    "\n"
    "\n"
    '@pytest.mark.skip(reason="fixture keeps a skip in the count")\n'
    "def test_gamma() -> None:\n"
    '    raise AssertionError("this body must never run")\n'
)

_OUTCOME_COUNT: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<count>\d+)\s+(?P<outcome>passed|failed|skipped|error|errors|xfailed|xpassed)\b"
)
_REQUIREMENT: Final[re.Pattern[str]] = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*>=\s*(?P<version>\d+(?:\.\d+)*)$"
)


def _pyproject() -> Mapping[str, object]:
    """The committed project configuration, parsed with `tomllib`."""
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _ini_options() -> Mapping[str, object]:
    data = _pyproject()
    tool = data["tool"]
    assert isinstance(tool, Mapping)
    pytest_table = tool["pytest"]
    assert isinstance(pytest_table, Mapping)
    ini = pytest_table["ini_options"]
    assert isinstance(ini, Mapping)
    return ini


def _as_tokens(addopts: object) -> list[str]:
    """`addopts` as pytest itself reads it: a shell-split string or an explicit list."""
    if isinstance(addopts, str):
        return shlex.split(addopts)
    assert isinstance(addopts, Sequence), f"addopts is neither str nor list: {addopts!r}"
    return [str(token) for token in addopts]


def _carries(tokens: Sequence[str], flag: str, value: str) -> bool:
    """True when `tokens` sets `flag` to `value`, in either accepted spelling."""
    if f"{flag}={value}" in tokens:
        return True
    return any(
        token == flag and index + 1 < len(tokens) and tokens[index + 1] == value
        for index, token in enumerate(tokens)
    )


def _floor(requirement: str) -> tuple[str, tuple[int, ...]]:
    match = _REQUIREMENT.match(requirement.strip())
    assert match is not None, f"dependency pin is not a simple `name>=version`: {requirement!r}"
    version = tuple(int(part) for part in match.group("version").split("."))
    return match.group("name").lower(), version


def _counts(stdout: str) -> dict[str, int]:
    """Every `<n> <outcome>` pair pytest reported, keyed by outcome."""
    found: dict[str, int] = {}
    for match in _OUTCOME_COUNT.finditer(stdout):
        outcome = match.group("outcome").rstrip("s") if match.group("outcome") == "errors" else match.group("outcome")
        found[outcome] = int(match.group("count"))
    return found


def _hermetic_env() -> dict[str, str]:
    """The ambient environment with every `PYTEST_*` variable dropped."""
    return {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}


def _spawn(fixture: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run pytest in a child process over `fixture` alone, hermetically."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *args,
            str(fixture),
        ],
        capture_output=True,
        text=True,
        cwd=str(fixture.parent),
        env=_hermetic_env(),
        timeout=SPAWN_TIMEOUT,
    )


def _fixture(tmp_path: pathlib.Path, body: str = TWO_PASSING_TESTS) -> pathlib.Path:
    target = tmp_path / "test_fixture_probe.py"
    target.write_text(body, encoding="utf-8")
    return target


# ---------------------------------------------------------------- behaviour 1


def test_b1_the_committed_addopts_carries_the_work_stealing_strategy() -> None:
    """1. `addopts` sets `--dist worksteal` and still sets `-n auto` and `-q`."""
    tokens = _as_tokens(_ini_options()["addopts"])
    assert _carries(tokens, "--dist", WORKSTEAL), (
        f"pyproject.toml addopts does not schedule {WORKSTEAL!r}: {tokens!r}"
    )
    assert _carries(tokens, "-n", "auto"), f"addopts lost `-n auto`: {tokens!r}"
    assert "-q" in tokens or "--quiet" in tokens, f"addopts lost `-q`: {tokens!r}"


def test_b1_the_neighbouring_ini_options_are_untouched() -> None:
    """1. `filterwarnings` is still exactly `["error"]`, `testpaths` exactly `["tests"]`."""
    ini = _ini_options()
    assert ini["filterwarnings"] == ["error"], f"filterwarnings moved: {ini['filterwarnings']!r}"
    assert ini["testpaths"] == ["tests"], f"testpaths moved: {ini['testpaths']!r}"


# ---------------------------------------------------------------- behaviour 2


def test_b2_the_dev_group_guarantees_the_option_exists() -> None:
    """2. Exactly two dev pins: `pytest>=8.0`-or-higher and `pytest-xdist>=3.2`-or-higher."""
    data = _pyproject()
    groups = data["dependency-groups"]
    assert isinstance(groups, Mapping)
    dev = groups["dev"]
    assert isinstance(dev, Sequence) and not isinstance(dev, str)
    assert len(dev) == 2, f"dev group must hold exactly two entries, found {list(dev)!r}"

    floors = dict(_floor(str(entry)) for entry in dev)
    assert set(floors) == set(EXPECTED_DEV_PACKAGES), f"dev packages moved: {sorted(floors)}"
    assert floors["pytest-xdist"] >= XDIST_FLOOR, (
        f"pytest-xdist floor {floors['pytest-xdist']} is below the release that introduced "
        f"{WORKSTEAL!r} ({XDIST_FLOOR})"
    )
    assert floors["pytest"] >= PYTEST_FLOOR, f"pytest floor dropped below {PYTEST_FLOOR}"


def test_b2_no_runtime_dependency_was_added() -> None:
    """2. `[project] dependencies` is still exactly `["pydantic>=2"]`."""
    project = _pyproject()["project"]
    assert isinstance(project, Mapping)
    assert tuple(project["dependencies"]) == EXPECTED_RUNTIME_DEPENDENCIES, (
        f"runtime dependencies moved: {project['dependencies']!r}"
    )


def test_b2_the_installed_xdist_actually_satisfies_the_floor() -> None:
    """2. The pin is a promise about the RESOLVED environment, so read it there too."""
    xdist = pytest.importorskip("xdist")
    resolved = tuple(
        int(part) for part in str(xdist.__version__).split(".")[:2] if part.isdigit()
    )
    assert resolved >= XDIST_FLOOR, f"resolved pytest-xdist {xdist.__version__} predates {WORKSTEAL!r}"


# ---------------------------------------------------------------- behaviour 3


def test_b3_armed_control_positive_half(tmp_path: pathlib.Path) -> None:
    """3. A hermetic `--dist worksteal -n 2` spawn exits 0 and reports `2 passed`."""
    done = _spawn(_fixture(tmp_path), "--dist", WORKSTEAL, "-n", "2")
    assert done.returncode == 0, f"worksteal spawn failed: {done.returncode}\n{done.stdout}\n{done.stderr}"
    assert "2 passed" in done.stdout, f"worksteal spawn did not report `2 passed`:\n{done.stdout}"


# ---------------------------------------------------------------- behaviour 4


def test_b4_armed_control_negative_half(tmp_path: pathlib.Path) -> None:
    """4. The identical spawn with a nonsense strategy must FAIL -- the control can fail."""
    done = _spawn(_fixture(tmp_path), "--dist", "no-such-strategy", "-n", "2")
    assert done.returncode != 0, (
        "an unknown --dist value was accepted, so behaviour 3 proves nothing:\n"
        f"{done.stdout}\n{done.stderr}"
    )
    assert "2 passed" not in done.stdout, f"an unknown --dist value still ran the tests:\n{done.stdout}"


# ---------------------------------------------------------------- behaviour 5


def test_b5_the_running_session_uses_the_committed_strategy(pytestconfig: pytest.Config) -> None:
    """5. The spec's implication, verbatim, plus the in-session claim that is not vacuous."""
    numprocesses = pytestconfig.getoption("numprocesses", default=None)
    dist = pytestconfig.getoption("dist", default=None)
    distributed = isinstance(numprocesses, int) and not isinstance(numprocesses, bool) and numprocesses >= 2
    if distributed:
        assert dist == WORKSTEAL, (
            f"a session with {numprocesses} workers is scheduling {dist!r}, not {WORKSTEAL!r}"
        )

    ini_addopts = list(pytestconfig.getini("addopts"))
    if ini_addopts:
        assert _carries(ini_addopts, "--dist", WORKSTEAL), (
            "the running session read an addopts that does not schedule "
            f"{WORKSTEAL!r}: {ini_addopts!r}"
        )


# ---------------------------------------------------------------- behaviour 6


def test_b6_the_committed_tool_shape_still_runs(tmp_path: pathlib.Path) -> None:
    """6. `-p xdist -n 0 --dist worksteal` -- what `tools/verify_mutations.py` spawns."""
    done = _spawn(_fixture(tmp_path), "-p", "xdist", "-n", "0", "--dist", WORKSTEAL)
    assert done.returncode == 0, (
        "`-n 0 --dist worksteal` broke the one committed tool shape that passes its own "
        f"-n: exit {done.returncode}\n{done.stdout}\n{done.stderr}"
    )
    assert "2 passed" in done.stdout, f"`-n 0 --dist worksteal` did not report `2 passed`:\n{done.stdout}"


# ---------------------------------------------------------------- behaviour 7


def test_b7_control_the_summary_parser_reports_and_discriminates() -> None:
    """7. The parser behaviour 7 leans on must report a real line and tell two apart."""
    assert _counts("2 passed, 1 skipped in 0.42s") == {"passed": 2, "skipped": 1}
    assert _counts("3 passed in 0.42s") != _counts("2 passed, 1 skipped in 0.42s")
    assert _counts("no tests ran in 0.01s") == {}


def test_b7_the_scheduler_changes_no_outcome(tmp_path: pathlib.Path) -> None:
    """7. Same tree, `--dist load` vs `--dist worksteal`: same collection, same counts."""
    fixture = _fixture(tmp_path, TWO_PASSING_ONE_SKIPPED)

    collected = {
        strategy: _spawn(fixture, "--dist", strategy, "-n", "2", "--collect-only").stdout
        for strategy in ("load", WORKSTEAL)
    }
    assert _counts(collected["load"]) == _counts(collected[WORKSTEAL]), (
        f"collection differs by scheduler:\n{collected['load']}\n---\n{collected[WORKSTEAL]}"
    )

    runs = {
        strategy: _spawn(fixture, "--dist", strategy, "-n", "2")
        for strategy in ("load", WORKSTEAL)
    }
    for strategy, done in runs.items():
        assert done.returncode == 0, f"--dist {strategy} failed: {done.stdout}\n{done.stderr}"
    assert _counts(runs["load"].stdout) == {"passed": 2, "skipped": 1}, (
        f"the fixture itself moved under --dist load:\n{runs['load'].stdout}"
    )
    assert _counts(runs[WORKSTEAL].stdout) == _counts(runs["load"].stdout), (
        "pass/skip counts moved with the scheduler:\n"
        f"{runs['load'].stdout}\n---\n{runs[WORKSTEAL].stdout}"
    )
