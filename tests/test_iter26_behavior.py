"""Iteration 26 behaviors: a non-git target answers a register glob exactly like a git one.

`checks.iter_files` has two enumeration branches -- what git tracks, and what a directory
walk finds. Iteration 26's claim is that the branches differ in ENUMERATION only: both
resolve a register-supplied glob with the product's own matcher, so a pattern that is
schema-valid but hostile to `pathlib.Path.glob` (`/etc/**`, `""`, `[a-\\]`) can no longer
crash the walked branch, fabricate a verdict on it, or make one commit scan to two answers.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors; every claim is measured by RUNNING the
packaged entry point or by CALLING the public `checks` interface.

Structural notes, so this file cannot lie later:

* **Every glob probe is A/B across the two branches, and the premise is asserted BOTH
  WAYS.** `checks.tracked_files()` must return `None` for the plain directory and a
  non-`None` list for the committed one. An A/B whose two sides run the same branch cannot
  tell a fix from a no-op, and `checks._TRACKED_CACHE` is keyed on the resolved path for the
  life of the process, so the two sides are two DIFFERENT directories holding the same bytes
  rather than one path that gains and loses `.git`.
* **"Matches nothing" is proved to be a DECISION, not the branch's only answer.**
  `test_walked_branch_discriminates_...` drives the identical target and record twice,
  changing only the glob list, and gets two different verdicts. Without that control every
  assertion below would pass on a walked branch that returned no files at all.
* **Behavior 4's expectation is written out literally.** The file names are typed as
  constants, never computed from `Path.glob`, so the test cannot inherit the interpreter
  semantics whose divergence across 3.12/3.13 is the reason the matcher exists.
* **Behavior 5 gets its OWN tree**, because the spec names exactly four files for it
  (`.venv/lib/x.py`, `node_modules/z.py`, `pkg/a.py`, `tests/test_a.py`) and the shared tree
  holds extra `.py` files that would make a literal expectation wrong. Per the spec, `.git`
  is deliberately NOT used as the skipped-directory sample: creating `.git` is what selects
  the other branch, so that fixture would silently test the tracked path.
* **No absolute machine path and no personal identifier appears here**; the repo root is
  derived from `__file__` and every fixture lives under pytest's `tmp_path_factory`.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from agent_gap_radar import checks

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`). Same boot line as `test_iter25_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: Content markers. `present_when` looks for the first; `mitigated_when` looks for the
#: second, which lives in exactly one file so a glob either reaches it or does not.
MARKER_PRESENT = "AGR26_SIGNATURE_SEEN"
MARKER_MITIGATED = "AGR26_MITIGATION_SEEN"
MARKER_NEVER = "AGR26_MARKER_THAT_IS_NOWHERE"

#: The shared tree, materialised twice: once as a plain directory (walked branch) and once
#: as a directory with `git init` plus a real commit of the same bytes (tracked branch).
TREE: dict[str, str] = {
    "evals/basic.json": '{"cases": 1}\n',
    "evals/deep/x.py": "def deep():\n    return 1\n",
    "pkg/a.py": f"def a():\n    return {MARKER_PRESENT!r}\n",
    "pkg/mit.py": f"def mitigated():\n    return {MARKER_MITIGATED!r}\n",
    "tests/test_a.py": "def test_a():\n    assert True\n",
}

#: Behavior 4, typed out rather than computed. A trailing `/**` means "everything at or
#: below here", so it reaches the nested file as well as the shallow one.
EVALS_GLOB_EXPECTED = ("evals/basic.json", "evals/deep/x.py")

#: Behavior 4's live-matcher control: every `.py` file in the shared tree, typed out.
PY_GLOB_EXPECTED = ("evals/deep/x.py", "pkg/a.py", "pkg/mit.py", "tests/test_a.py")

#: Behavior 5's tree -- exactly the four files the spec names, and no others.
SKIP_TREE: dict[str, str] = {
    ".venv/lib/x.py": "def vendored():\n    return 1\n",
    "node_modules/z.py": "def vendored():\n    return 2\n",
    "pkg/a.py": "def a():\n    return 3\n",
    "tests/test_a.py": "def test_a():\n    assert True\n",
}
SKIP_TREE_PY_EXPECTED = ("pkg/a.py", "tests/test_a.py")
SKIP_TREE_PY_EXCLUDING_TESTS_EXPECTED = ("pkg/a.py",)

#: The three schema-valid patterns that `pathlib.Path.glob` refuses or mishandles.
ABSOLUTE_GLOB = "/etc/**"
EMPTY_GLOB = ""
MALFORMED_GLOB = "[a-\\]"

#: Behavior 3: the interpreter-internal text a fabricated verdict rendered into the
#: document. Quoted from `pm.md`'s measurement log.
FABRICATED_VERDICT_TEXT = "Unacceptable pattern"

#: Behavior 6 and behavior 1: stderr must be EMPTY, so these are the strings whose absence
#: is worth naming individually when the byte-equality assertion fails.
FORBIDDEN_STDERR = ("Traceback", "NotImplementedError", "FutureWarning", "re.error")


def _materialise(root: pathlib.Path, tree: dict[str, str]) -> pathlib.Path:
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _git_commit(root: pathlib.Path) -> None:
    """`git init` plus a real commit, because `tracked_files` returns None for an empty repo.

    Identity is supplied per-command so nothing reads or writes a global git config, and no
    credential or authentication command is ever run.
    """
    env_args = ["-c", "user.email=fixture@example.invalid", "-c", "user.name=fixture"]
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), *env_args, "commit", "-q", "-m", "fixture"],
                   check=True, capture_output=True)


@pytest.fixture(scope="module")
def walked_target(tmp_path_factory) -> pathlib.Path:
    """The shared tree as a plain directory: no `.git`, so the walked branch is selected."""
    return _materialise(tmp_path_factory.mktemp("walked") / "target", TREE)


@pytest.fixture(scope="module")
def git_target(tmp_path_factory) -> pathlib.Path:
    """The same bytes, committed: `git ls-files` succeeds, so the tracked branch is used."""
    root = _materialise(tmp_path_factory.mktemp("tracked") / "target", TREE)
    _git_commit(root)
    return root


@pytest.fixture(scope="module")
def skip_dirs_target(tmp_path_factory) -> pathlib.Path:
    """Behavior 5's four-file tree, plain so the walked branch is selected."""
    return _materialise(tmp_path_factory.mktemp("skips") / "target", SKIP_TREE)


def _record(globs: list[str], present_pattern: str = MARKER_PRESENT) -> dict:
    """One schema-valid register record whose `mitigated_when` carries the globs under test.

    `present_when` fires on the shared tree by default, so the fixed verdict for a
    match-nothing glob list is PRESENT and for a reaching glob list is MANUAL -- two
    distinguishable answers from one target.
    """
    return {
        "id": "GAP-001",
        "title": "Fixture gap for the walked enumeration branch",
        "layer": "lifecycle-deploy",
        "gap_type": "silent-failure",
        "status": "open",
        "problem": "A synthetic record that drives one check against one fixture tree.",
        "symptom": "Nothing real; this record exists only to exercise glob matching.",
        "why_now": "The walked branch had never been driven by a register glob in a test.",
        "existing": ["Nothing; this is a fixture and claims no prior art."],
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [{
            "source_class": "first-party-field",
            "title": "Fixture citation for a fixture record",
            "locator": "https://example.invalid/fixture/notes.md",
            "date": "2026-08-20",
            "quote": "A scan of one commit must return one answer.",
        }],
        "build_hypothesis": "Resolve register globs with one matcher on both branches.",
        "tags": ["fixture"],
        "check": {
            "id": "CHK-001",
            "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                             "pattern": present_pattern},
            "mitigated_when": {"kind": "content_matches", "globs": globs,
                               "pattern": MARKER_MITIGATED},
            "manual_question": "Do both enumeration branches resolve this glob the same way?",
            "rationale": "Fixture check; its only job is to carry a glob list.",
            "fixtures": {
                "bad": {"pkg/a.py": MARKER_PRESENT + "\n"},
                "good": {"pkg/a.py": MARKER_MITIGATED + "\n"},
            },
        },
    }


def _register(tmp_path: pathlib.Path, globs: list[str],
              present_pattern: str = MARKER_PRESENT) -> pathlib.Path:
    root = tmp_path / "register"
    (root / "gaps").mkdir(parents=True, exist_ok=True)
    (root / "gaps" / "GAP-001-fixture.json").write_text(
        json.dumps(_record(globs, present_pattern), indent=2) + "\n", encoding="utf-8")
    return root


def _scan(target: pathlib.Path, register: pathlib.Path,
          *extra: str) -> subprocess.CompletedProcess[bytes]:
    """`radar scan <target> --gaps <register>` through the packaged entry point."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, "scan", str(target), "--gaps", str(register), *extra],
        cwd=str(REPO_ROOT), capture_output=True, timeout=180)


def _verdict(target: pathlib.Path, register: pathlib.Path) -> str:
    """The per-gap verdict `radar scan` reports, read off the stable `--json` object."""
    proc = _scan(target, register, "--json")
    assert proc.returncode == 0, (
        f"scan --json exited {proc.returncode}; stderr={proc.stderr.decode()!r}")
    findings = json.loads(proc.stdout.decode("utf-8"))["findings"]
    assert len(findings) == 1, f"expected one finding, got {len(findings)}"
    return findings[0]["verdict"]


def _rel(target: pathlib.Path, paths: list[pathlib.Path]) -> tuple[str, ...]:
    """Absolute results as target-relative POSIX strings, in the order returned."""
    return tuple(p.relative_to(target).as_posix() for p in paths)


def _assert_clean_stderr(proc: subprocess.CompletedProcess[bytes], what: str) -> None:
    text = proc.stderr.decode("utf-8", "replace")
    for token in FORBIDDEN_STDERR:
        assert token not in text, f"{what}: stderr leaked {token!r}:\n{text}"
    assert proc.stderr == b"", f"{what}: stderr not empty:\n{text}"


# --- the premise, asserted both ways ---------------------------------------
# An A/B whose two sides run the SAME enumeration branch cannot tell a fix from a no-op,
# so the branch selection is itself a test rather than an assumption.

def test_plain_directory_selects_the_walked_branch(walked_target):
    assert checks.tracked_files(walked_target) is None, (
        "the plain fixture directory reports tracked files, so every 'walked branch' "
        "assertion in this file would actually be exercising the tracked branch")


def test_committed_directory_selects_the_tracked_branch(git_target):
    tracked = checks.tracked_files(git_target)
    assert tracked is not None, (
        "the committed fixture reports no tracked files, so the git side of every A/B "
        "below would fall back to the walked branch and the A/B would be vacuous")
    assert tracked, "tracked file list is empty"


def test_both_fixtures_hold_the_same_bytes(walked_target, git_target):
    """The A/B varies the BRANCH only; if the bytes differ the comparison proves nothing."""
    for rel in TREE:
        assert (walked_target / rel).read_bytes() == (git_target / rel).read_bytes(), rel


# --- anti-vacuity control: "matches nothing" is a decision, not the only answer ---

def test_walked_branch_discriminates_between_a_reaching_and_a_dead_glob(
        walked_target, tmp_path):
    """Same target, same record, two glob lists, two verdicts.

    Without this control every match-nothing assertion below would also pass on a walked
    branch that enumerated no files at all.
    """
    reaching = _register(tmp_path / "reaching", ["pkg/**"], present_pattern=MARKER_NEVER)
    dead = _register(tmp_path / "dead", [ABSOLUTE_GLOB], present_pattern=MARKER_NEVER)
    reaching_verdict = _verdict(walked_target, reaching)
    dead_verdict = _verdict(walked_target, dead)
    assert reaching_verdict == "ABSENT", (
        f"a glob that reaches {MARKER_MITIGATED} in pkg/mit.py did not find it on the "
        f"walked branch (verdict {reaching_verdict}); the matcher is not live there")
    assert dead_verdict != reaching_verdict, (
        "an absolute glob and a reaching glob produced the SAME verdict "
        f"({dead_verdict}), so this file cannot distinguish matching from not matching")


# --- Behavior 1: the crash is gone ----------------------------------------

def test_b1_absolute_glob_on_a_non_git_target_produces_a_document_not_a_traceback(
        walked_target, tmp_path):
    register = _register(tmp_path, [ABSOLUTE_GLOB])
    proc = _scan(walked_target, register)
    _assert_clean_stderr(proc, "behavior 1")
    assert proc.returncode == 0, (
        f"exit {proc.returncode} for a schema-valid register carrying {ABSOLUTE_GLOB!r}; "
        f"stderr={proc.stderr.decode()!r}")
    assert proc.stdout, "exit 0 but zero bytes of document on stdout"
    assert proc.stdout.endswith(b"\n"), "document does not end in a newline"
    assert not proc.stdout.endswith(b"\n\n"), "document ends in more than one newline"
    assert proc.stdout.startswith(b"# Gap scan:"), (
        f"stdout is not a scan document: {proc.stdout[:80]!r}")


# --- Behavior 2: an absolute glob answers the same on both branches --------

def test_b2_absolute_glob_gives_one_verdict_on_both_branches(
        walked_target, git_target, tmp_path):
    register = _register(tmp_path, [ABSOLUTE_GLOB])
    walked_proc = _scan(walked_target, register, "--json")
    git_proc = _scan(git_target, register, "--json")
    _assert_clean_stderr(walked_proc, "behavior 2 (walked)")
    _assert_clean_stderr(git_proc, "behavior 2 (tracked)")
    walked_verdict = _verdict(walked_target, register)
    git_verdict = _verdict(git_target, register)
    assert walked_verdict == git_verdict, (
        f"same register, same bytes, two verdicts: walked={walked_verdict} "
        f"tracked={git_verdict} for glob {ABSOLUTE_GLOB!r}")


# --- Behavior 3: an empty-string glob answers the same on both branches ----

def test_b3_empty_glob_gives_one_verdict_on_both_branches(
        walked_target, git_target, tmp_path):
    register = _register(tmp_path, [EMPTY_GLOB, "evals/**"])
    walked_verdict = _verdict(walked_target, register)
    git_verdict = _verdict(git_target, register)
    assert walked_verdict == git_verdict, (
        f"same register, same bytes, two verdicts: walked={walked_verdict} "
        f"tracked={git_verdict} for glob list [{EMPTY_GLOB!r}, 'evals/**']")


def test_b3_empty_glob_does_not_fabricate_a_verdict_in_the_document(
        walked_target, tmp_path):
    register = _register(tmp_path, [EMPTY_GLOB, "evals/**"])
    proc = _scan(walked_target, register)
    _assert_clean_stderr(proc, "behavior 3")
    assert proc.returncode == 0, f"exit {proc.returncode}"
    text = proc.stdout.decode("utf-8")
    assert text.count(FABRICATED_VERDICT_TEXT) == 0, (
        f"{FABRICATED_VERDICT_TEXT!r} appears {text.count(FABRICATED_VERDICT_TEXT)} "
        "time(s) in a document that is meant to be committed and diffed")
    assert "PosixPath(" not in text, "an interpreter-internal repr reached the document"


# --- Behavior 4: a trailing /** means everything at or below here ----------

def test_b4_trailing_doublestar_reaches_nested_files_on_the_walked_branch(walked_target):
    got = _rel(walked_target, checks.iter_files(walked_target, ["evals/**"]))
    assert got == EVALS_GLOB_EXPECTED, (
        f"'evals/**' returned {got}, expected {EVALS_GLOB_EXPECTED} -- the expectation is "
        "typed out literally, so a mismatch means the matcher, not the interpreter, moved")


def test_b4_control_a_plain_recursive_glob_is_live_not_vacuous(walked_target):
    """The control for the test above: the matcher returns files, and the right ones."""
    got = _rel(walked_target, checks.iter_files(walked_target, ["**/*.py"]))
    assert got == PY_GLOB_EXPECTED, f"'**/*.py' returned {got}, expected {PY_GLOB_EXPECTED}"


def test_b4_results_are_sorted(walked_target):
    for globs in (["evals/**"], ["**/*.py"]):
        got = _rel(walked_target, checks.iter_files(walked_target, globs))
        assert list(got) == sorted(got), f"{globs} returned unsorted paths: {got}"


def test_b4_both_branches_enumerate_the_same_paths_for_the_same_glob(
        walked_target, git_target):
    """Behavior 4 restated as the A/B the acceptance criteria actually promise."""
    for globs in (["evals/**"], ["**/*.py"]):
        walked = _rel(walked_target, checks.iter_files(walked_target, globs))
        tracked = _rel(git_target, checks.iter_files(git_target, globs))
        assert walked == tracked, f"{globs}: walked={walked} tracked={tracked}"


# --- Behavior 5: SKIP_DIRS and exclude_tests survive the swap --------------

def test_b5_skip_dirs_still_pruned_on_the_walked_branch(skip_dirs_target):
    got = _rel(skip_dirs_target, checks.iter_files(skip_dirs_target, ["**/*.py"]))
    assert got == SKIP_TREE_PY_EXPECTED, (
        f"'**/*.py' returned {got}, expected {SKIP_TREE_PY_EXPECTED}")
    for skipped in (".venv/lib/x.py", "node_modules/z.py"):
        assert skipped not in got, f"{skipped} was not pruned"


def test_b5_exclude_tests_still_drops_test_paths_on_the_walked_branch(skip_dirs_target):
    got = _rel(skip_dirs_target,
               checks.iter_files(skip_dirs_target, ["**/*.py"], exclude_tests=True))
    assert got == SKIP_TREE_PY_EXCLUDING_TESTS_EXPECTED, (
        f"exclude_tests=True returned {got}, "
        f"expected {SKIP_TREE_PY_EXCLUDING_TESTS_EXPECTED}")


def test_b5_control_the_skipped_dirs_really_exist_on_disk(skip_dirs_target):
    """Otherwise the pruning assertion above would pass on an empty fixture."""
    for rel in SKIP_TREE:
        assert (skip_dirs_target / rel).is_file(), f"{rel} was never created"


# --- Behavior 6: a malformed glob matches nothing, quietly ----------------

def test_b6_malformed_glob_is_quiet_and_agrees_across_branches(
        walked_target, git_target, tmp_path):
    register = _register(tmp_path, [MALFORMED_GLOB])
    walked_proc = _scan(walked_target, register)
    _assert_clean_stderr(walked_proc, "behavior 6 (walked)")
    assert walked_proc.returncode == 0, (
        f"exit {walked_proc.returncode} for glob {MALFORMED_GLOB!r}; "
        f"stderr={walked_proc.stderr.decode()!r}")
    assert walked_proc.stdout.startswith(b"# Gap scan:"), "no document on stdout"
    walked_verdict = _verdict(walked_target, register)
    git_verdict = _verdict(git_target, register)
    assert walked_verdict == git_verdict, (
        f"malformed glob {MALFORMED_GLOB!r}: walked={walked_verdict} "
        f"tracked={git_verdict}")


def test_b6_malformed_glob_matches_nothing_rather_than_raising(walked_target):
    """`iter_files` is the surface the CLI sits on, so assert the quiet answer directly."""
    assert checks.iter_files(walked_target, [MALFORMED_GLOB]) == []


# --- the published surface is unchanged (acceptance criterion) -------------

def test_scan_stdout_is_byte_stable_across_two_runs(walked_target, tmp_path):
    """Byte-stability is the mechanism that would break first if enumeration went unordered."""
    register = _register(tmp_path, ["evals/**"])
    first = _scan(walked_target, register)
    second = _scan(walked_target, register)
    assert first.returncode == 0 and second.returncode == 0
    assert first.stdout == second.stdout, "two runs of one scan produced different bytes"


def test_scan_on_this_repo_still_succeeds_and_ends_in_one_newline():
    """The live register against a real git target: the tracked branch is untouched."""
    proc = _scan(REPO_ROOT, REPO_ROOT)
    _assert_clean_stderr(proc, "live register on this repo")
    assert proc.returncode == 0, f"exit {proc.returncode}"
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")


# --- do the fixtures still have teeth? ------------------------------------
# Behaviors 1-3 are only meaningful while `/etc/**` and `""` are genuinely hostile to the
# matcher the spec names as the old one (`pathlib.Path.glob`). Both are asserted here as
# MEASURED facts about the running interpreter, so if a future CPython stops raising, this
# test fails and says the fixture needs a new hostile pattern -- rather than behaviors 1-3
# quietly becoming a probe of nothing.

def test_fixture_teeth_absolute_and_empty_globs_still_break_pathlib(walked_target):
    with pytest.raises(NotImplementedError):
        list(walked_target.glob(ABSOLUTE_GLOB))
    with pytest.raises(ValueError):
        list(walked_target.glob(EMPTY_GLOB))


def test_fixture_teeth_note_malformed_glob_is_not_a_pathlib_crash(walked_target):
    """Honest scope for behavior 6 on this interpreter.

    `[a-\\]` does NOT raise from `Path.glob` on the interpreter this suite runs; it returns
    an empty list. So behavior 6 is a REGRESSION GUARD on the product's own `re.error`
    fallback, not a reproduction of a crash observable here. Recorded as a test so a reader
    cannot mistake it for a demonstrated defect.
    """
    assert list(walked_target.glob(MALFORMED_GLOB)) == []
