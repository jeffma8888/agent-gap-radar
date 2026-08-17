"""Iteration 03 behaviors: on a git target, the scan's file walk is driven by the
tracked set instead of a filesystem glob.

Black-box. Nothing here reads the implementation source. Assertions drive the public
CLI entry point (`main`), the public `scan()`/`evaluate()` API, or `iter_files`, which
the spec names as the unit whose contract this iteration changes. Expected values are
stated literally or derived from a REFERENCE walk written from the spec's own
description of the pre-change algorithm, never copied out of the new code.

The reference walk (spec "Why"): the old `iter_files` globbed the whole tree with
`Path.glob` and only afterwards filtered against the tracked set, so on a git target
`SKIP_DIRS` was never consulted. `_reference_git_walk` below is that algorithm.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from agent_gap_radar.checks import iter_files

#: Repo root, found relative to this file so no absolute machine path appears here.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _tree(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, check=True)


def _git_repo(root: pathlib.Path, files: dict[str, str],
              untracked: dict[str, str] | None = None) -> pathlib.Path:
    """Materialise `files` and commit them; `untracked` is written but never added."""
    _tree(root, files)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "t")
    if untracked:
        _tree(root, untracked)
    return root


def _tracked(root: pathlib.Path) -> set[str]:
    out = _git(root, "ls-files").stdout.splitlines()
    return {line for line in out if line}


def _reference_git_walk(target: pathlib.Path, pattern: str) -> list[str]:
    """The PRE-CHANGE algorithm, as described by the spec: glob the tree, then keep
    only files whose resolved path is in the tracked set. `SKIP_DIRS` is deliberately
    NOT consulted -- the spec says the old code never reached it on a git target.
    """
    tracked_resolved = {(target / rel).resolve() for rel in _tracked(target)}
    hits = set()
    for p in target.glob(pattern):
        if not p.is_file():
            continue
        if p.resolve() not in tracked_resolved:
            continue
        hits.add(str(p.relative_to(target)))
    return sorted(hits)


def _rel(target: pathlib.Path, paths) -> list[str]:
    return sorted(str(pathlib.Path(p).relative_to(target)) for p in paths)


def _register_globs() -> list[str]:
    """Every glob in every check of the COMMITTED register, deduped and sorted."""
    found: set[str] = set()

    def walk(rule) -> None:
        if not isinstance(rule, dict):
            return
        for g in rule.get("globs") or []:
            found.add(g)
        for key in ("rules", "any_of", "all_of"):
            for sub in rule.get(key) or []:
                walk(sub)
        for key in ("rule", "not"):
            if rule.get(key):
                walk(rule[key])

    records = sorted((REPO_ROOT / "gaps").glob("*.json"))
    assert records, "premise: the committed register must have records"
    for f in records:
        check = json.loads(f.read_text(encoding="utf-8")).get("check")
        if not check:
            continue
        for key in ("applies_when", "present_when", "mitigated_when"):
            if check.get(key):
                walk(check[key])
    return sorted(found)


def _single_check_register(root: pathlib.Path, *, globs: list[str],
                           pattern: str) -> pathlib.Path:
    """A minimal one-record register whose only rule is a content match.

    Built by hand rather than copied from `gaps/` so the tree can be tiny and the
    verdict unambiguous: with no `mitigated_when`, a check that finds nothing earns a
    non-committal verdict, never ABSENT.
    """
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "id": "GAP-001", "title": "t", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s",
        "why_now": "w", "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/x", "date": "2026-01-02",
                      "quote": "the verbatim line"}],
        "check": {"id": "CHK-900", "rationale": "r", "manual_question": "q",
                  "present_when": {"kind": "content_matches", "globs": globs,
                                   "pattern": pattern},
                  "fixtures": {"bad": {"a.py": pattern + "\n"},
                               "good": {"a.py": "c\n"}}},
    }
    (root / "GAP-001.json").write_text(json.dumps(record), encoding="utf-8")
    return root



#: A tree written so that the register's pattern vocabulary actually matches
#: something. Anti-vacuity: a differential over patterns that match nothing on both
#: sides passes for free, so the coverage count is asserted below.
DIFFERENTIAL_FILES = {
    "AGENTS.md": "a\n",
    "CLAUDE.md": "c\n",
    "LEARNINGS.md": "l\n",
    "README.md": "r\n",
    "pyproject.toml": "[p]\n",
    "uv.lock": "lock\n",
    "package-lock.json": "{}\n",
    "notes.txt": "n\n",
    ".mcp.json": "{}\n",
    "mcp.json": "{}\n",
    "mcp.lock": "{}\n",
    "mcp_config.json": "{}\n",
    "mcp-servers.json": "{}\n",
    "mcp-servers.lock": "{}\n",
    "claude_desktop_config.json": "{}\n",
    "src/app.py": "print(1)\n",
    "src/pkg/util.py": "x = 1\n",
    "src/pkg/.mcp.json": "{}\n",
    "src/tool.mcp.json": "{}\n",
    "tests/test_app.py": "def test_a(): pass\n",
    "tests/unit/test_deep.py": "def test_b(): pass\n",
    "tests/util_test.py": "def test_c(): pass\n",
    "tests/test_eval_flow.py": "def test_d(): pass\n",
    "tests/e2e/flow.spec.ts": "it()\n",
    "tests/e2e/flow.test.ts": "it()\n",
    "evals/basic.json": "{}\n",
    "evals/deep/case.yaml": "k: v\n",
    "evals/runner.py": "run()\n",
    "eval/legacy.py": "old()\n",
    "eval/nested/deep.py": "old()\n",
    "data/my_eval.json": "{}\n",
    "data/my_eval.yaml": "k: v\n",
    "steering/rules.md": "s\n",
    "svc/main.go": "package main\n",
    "svc/lib.rs": "fn main() {}\n",
    "web/app.ts": "let a = 1\n",
    "web/app.js": "var a = 1\n",
    "web/app.spec.ts": "it()\n",
    "web/app.test.ts": "it()\n",
    "config/app.yaml": "k: v\n",
    "config/app.yml": "k: v\n",
    "config/settings.toml": "[k]\n",
    "tpl/page.jinja": "{{ x }}\n",
    "prompts/sys.prompt": "you are\n",
    ".gitignore": "state/\n",
}

#: Present in the tree, absent from the tracked set. Neither walk may return these.
DIFFERENTIAL_UNTRACKED = {
    "scratch/untracked.py": "x\n",
    "state/iter-01/probe.py": "x\n",
}


# ---------------------------------------------------------------------------
# Behavior 1 -- differential: tracked-path matching == the old glob walk
# ---------------------------------------------------------------------------

def test_tracked_walk_equals_the_old_glob_walk_for_every_register_pattern(tmp_path):
    """EB1. Per-pattern differential over EVERY glob in the committed register."""
    target = _git_repo(tmp_path / "t", DIFFERENTIAL_FILES, DIFFERENTIAL_UNTRACKED)
    patterns = _register_globs()
    assert len(patterns) >= 30, f"register pattern extraction looks broken: {patterns}"

    diffs: list[str] = []
    matched_patterns = 0
    total_hits = 0
    for pattern in patterns:
        expected = _reference_git_walk(target, pattern)
        actual = _rel(target, iter_files(target, [pattern]))
        if expected != actual:
            diffs.append(f"{pattern!r}: old={expected} new={actual}")
        if actual:
            matched_patterns += 1
            total_hits += len(actual)

    assert not diffs, "tracked-path matching diverged from the glob walk:\n" + "\n".join(diffs)
    # Anti-vacuity: the differential must have compared real, non-empty answers.
    # Measured baseline on this tree: 41 of 41 patterns match, 86 total hits. The
    # thresholds are absolute counts, not ratios, so adding a pattern the tree does
    # not cover cannot break them -- only gutting the tree can.
    assert matched_patterns >= 35, (
        f"only {matched_patterns}/{len(patterns)} patterns matched anything; "
        "the differential would pass on an empty tree"
    )
    assert total_hits >= 80, f"too few file hits to be a real differential: {total_hits}"


def test_the_differential_tree_would_expose_a_matcher_that_matches_everything(tmp_path):
    """Control for the test above: the tree contains near-misses, so a matcher that
    returned every tracked file would be caught rather than pass."""
    target = _git_repo(tmp_path / "t", DIFFERENTIAL_FILES, DIFFERENTIAL_UNTRACKED)
    tracked = _tracked(target)
    assert len(tracked) >= 40, tracked
    py_only = _rel(target, iter_files(target, ["**/*.py"]))
    assert py_only, "premise"
    assert len(py_only) < len(tracked), "a match-everything matcher would look correct"
    assert "notes.txt" not in py_only
    assert "svc/main.go" not in py_only


def test_only_tracked_files_are_returned_on_a_git_target(tmp_path):
    """The invariant behind both the speedup and the scope rule."""
    target = _git_repo(tmp_path / "t", DIFFERENTIAL_FILES, DIFFERENTIAL_UNTRACKED)
    got = _rel(target, iter_files(target, ["**/*.py"]))
    assert got, "premise: tracked python files exist"
    assert "scratch/untracked.py" not in got, got
    assert "state/iter-01/probe.py" not in got, got
    assert "src/app.py" in got, got


def test_iter_files_returns_a_sorted_deduped_list(tmp_path):
    """Byte-stable output requires a deterministic order and no double-counting."""
    target = _git_repo(tmp_path / "t", {"a.py": "x\n", "b/c.py": "y\n"})
    got = iter_files(target, ["**/*.py", "**/*.py", "b/**/*.py"])
    as_str = [str(p) for p in got]
    assert as_str == sorted(as_str), as_str
    assert len(as_str) == len(set(as_str)), as_str
    assert len(as_str) == 2, as_str


# ---------------------------------------------------------------------------
# Behavior 2 -- non-git targets keep the Path.glob + SKIP_DIRS walk
# ---------------------------------------------------------------------------

def test_non_git_target_still_walks_the_filesystem_and_skips_vendored_dirs(tmp_path):
    """EB2. No git means no tracked set, so a plain file must still be found -- and
    the skip list must still apply, which is what makes this the OLD path."""
    target = _tree(tmp_path / "t", {
        "src/a.py": "x\n",
        "node_modules/dep.py": "x\n",
        ".venv/lib/site.py": "x\n",
        "no_git_here.py": "x\n",
    })
    assert not (target / ".git").exists(), "premise: not a git repo"
    got = _rel(target, iter_files(target, ["**/*.py"]))
    assert got == ["no_git_here.py", "src/a.py"], got


def test_non_git_target_returns_files_that_no_git_index_lists(tmp_path):
    """The distinguishing property of the fallback: nothing is filtered by tracking."""
    target = _tree(tmp_path / "t", {"only_on_disk.py": "x\n"})
    assert _rel(target, iter_files(target, ["**/*.py"])) == ["only_on_disk.py"]


# ---------------------------------------------------------------------------
# Behavior 3 -- a trailing /** matches files at or below the directory
# ---------------------------------------------------------------------------

def test_trailing_double_star_matches_files_at_or_below_that_directory(tmp_path):
    """EB3. Expected set is stated literally, so this assertion does not inherit the
    running interpreter's `Path.glob("dir/**")` semantics (3.12 yields directories
    only, 3.13 yields files too)."""
    target = _git_repo(tmp_path / "t", {
        "evals/basic.json": "{}\n",
        "evals/deep/nested/case.yaml": "k: v\n",
        "evals/runner.py": "x\n",
        "eval/legacy.py": "x\n",
        "notevals/x.py": "x\n",
    })
    got = _rel(target, iter_files(target, ["evals/**"]))
    assert got == ["evals/basic.json", "evals/deep/nested/case.yaml",
                   "evals/runner.py"], got


def test_interior_double_star_matches_zero_directories(tmp_path):
    target = _git_repo(tmp_path / "t", {"top.py": "x\n", "a/b/deep.py": "x\n"})
    assert _rel(target, iter_files(target, ["**/*.py"])) == ["a/b/deep.py", "top.py"]


# ---------------------------------------------------------------------------
# Behavior 4 -- matching is case-sensitive on the tracked path
# ---------------------------------------------------------------------------

def test_matching_is_case_sensitive_on_the_tracked_path(tmp_path):
    """EB4. Same commit, same verdicts, whatever the filesystem's case folding."""
    target = _git_repo(tmp_path / "t", {"AGENTS.md": "a\n", "notes.md": "n\n"})
    assert _rel(target, iter_files(target, ["AGENTS.md"])) == ["AGENTS.md"]
    assert iter_files(target, ["agents.md"]) == []
    assert _rel(target, iter_files(target, ["notes.md"])) == ["notes.md"]
    assert iter_files(target, ["NOTES.md"]) == []


def test_case_sensitivity_holds_for_the_registers_literal_patterns(tmp_path):
    """The register carries literal `AGENTS.md` and `CLAUDE.md` patterns, so this is
    not hypothetical: a lowercase tracked file must not satisfy them."""
    literals = [p for p in _register_globs() if p in ("AGENTS.md", "CLAUDE.md")]
    assert literals, "premise: the register still carries literal doc patterns"
    target = _git_repo(tmp_path / "t", {"agents.md": "a\n", "claude.md": "c\n"})
    assert iter_files(target, literals) == []


# ---------------------------------------------------------------------------
# Behavior 5 -- scan verdicts, locations and bytes are unchanged
# ---------------------------------------------------------------------------
#
# "Unchanged" cannot be measured against code that no longer exists, so it is
# measured against the code path this iteration did NOT touch: on a tree where every
# file is tracked and nothing is gitignored or vendored, the tracked-set walk and the
# untouched non-git walk see the same files, so the two documents must be byte-equal.
# The register used is the COMMITTED one, so all of its patterns run end to end.

#: The differential tree minus `.gitignore`, so the git and non-git walks are
#: looking at exactly the same file set by construction.
_CLEAN_FILES = {k: v for k, v in DIFFERENTIAL_FILES.items() if k != ".gitignore"}


def _scan_doc(target: pathlib.Path, capsys, extra=()) -> tuple[int, str, str]:
    from agent_gap_radar.cli import main
    rc = main(["scan", str(target), "--gaps", str(REPO_ROOT / "gaps"), *extra])
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def test_scan_of_a_git_target_matches_the_untouched_non_git_path_byte_for_byte(
        tmp_path, capsys):
    """EB5. Same basename in different parents, so only the absolute path differs."""
    git_target = _git_repo(tmp_path / "A" / "t", _CLEAN_FILES)
    plain_target = _tree(tmp_path / "B" / "t", _CLEAN_FILES)
    assert not (plain_target / ".git").exists(), "premise"

    rc_git, out_git, err_git = _scan_doc(git_target, capsys)
    rc_plain, out_plain, err_plain = _scan_doc(plain_target, capsys)

    assert (rc_git, rc_plain) == (0, 0)
    assert (err_git, err_plain) == ("", "")
    normalised_git = out_git.replace(str(git_target), "TARGET")
    normalised_plain = out_plain.replace(str(plain_target), "TARGET")
    assert normalised_git == normalised_plain, (
        "the tracked-set walk and the filesystem walk disagree on a tree where "
        "every file is tracked"
    )
    assert "PRESENT" in out_git, "anti-vacuity: the document must be a real report"


def test_scan_of_a_git_target_is_deterministic_and_ends_in_one_newline(
        tmp_path, capsys):
    target = _git_repo(tmp_path / "t", _CLEAN_FILES)
    _, first, _ = _scan_doc(target, capsys)
    _, second, _ = _scan_doc(target, capsys)
    assert first == second, "repeated scans of one commit must be byte-stable"
    assert first.endswith("\n") and not first.endswith("\n\n")


def test_scan_json_of_a_git_target_carries_both_scores_unblended(tmp_path, capsys):
    """The register's core invariant, re-checked on the path this iteration changed."""
    target = _git_repo(tmp_path / "t", _CLEAN_FILES)
    rc, out, err = _scan_doc(target, capsys, ["--json"])
    assert (rc, err) == (0, "")
    doc = json.loads(out)
    assert doc["findings"], "anti-vacuity: the scan must have produced findings"
    for finding in doc["findings"]:
        assert "priority" in finding and "confidence" in finding, finding
        assert "score" not in finding, f"blended score leaked: {finding}"


# ---------------------------------------------------------------------------
# Input classes the register's own patterns can reach
# ---------------------------------------------------------------------------

def test_every_committed_register_pattern_is_evaluable_without_raising(tmp_path):
    """A pattern the matcher cannot compile must not escape as a traceback: stdout
    carries only the document, and errors are `Error: ` on stderr with exit 2."""
    target = _git_repo(tmp_path / "t", {"a.py": "x\n"})
    broken = []
    for pattern in _register_globs():
        try:
            iter_files(target, [pattern])
        except Exception as exc:  # noqa: BLE001 - the point is that nothing escapes
            broken.append(f"{pattern!r}: {type(exc).__name__}: {exc}")
    assert not broken, "register patterns that raise:\n" + "\n".join(broken)


def test_a_tracked_file_inside_a_vendored_dir_still_matches_the_old_walk(tmp_path):
    """The one input class where consulting `SKIP_DIRS` on a git target would be a
    behavior CHANGE rather than the fix: git is the authority on scope, so a file the
    project chose to track is in scope even under a vendored-looking name."""
    target = tmp_path / "t"
    target.mkdir(parents=True)
    _tree(target, {"src/a.py": "x\n", "node_modules/dep.py": "x\n",
                   ".venv/lib/site.py": "x\n"})
    _git(target, "init", "-q")
    _git(target, "config", "user.email", "t@example.invalid")
    _git(target, "config", "user.name", "t")
    _git(target, "add", "-A", "-f")  # -f: beat any global ignore file
    _git(target, "commit", "-q", "-m", "t")
    assert _tracked(target) == {"src/a.py", "node_modules/dep.py",
                                ".venv/lib/site.py"}, "premise: all three tracked"
    assert _rel(target, iter_files(target, ["**/*.py"])) == \
        _reference_git_walk(target, "**/*.py")


def test_regex_special_characters_in_a_tracked_path_match_the_old_walk(tmp_path):
    """Glob metacharacters and regex metacharacters are not the same alphabet."""
    names = {"a+b.py": "x\n", "c(d).py": "x\n", "e[f].py": "x\n", "g.h$i.py": "x\n"}
    target = _git_repo(tmp_path / "t", names)
    assert _rel(target, iter_files(target, ["**/*.py"])) == \
        _reference_git_walk(target, "**/*.py")
    assert _rel(target, iter_files(target, ["a+b.py"])) == ["a+b.py"], \
        "a literal `+` in a pattern must not be read as a regex quantifier"
    assert iter_files(target, ["ab.py"]) == [], "control: `+` is not a quantifier"


def test_a_malformed_glob_in_a_register_check_does_not_crash_the_cli(
        tmp_path, capsys):
    """A register is data, so a bad pattern is an input, not a bug in the tool: it may
    not escape as a traceback and it may never be credited as a mitigation (ABSENT).

    This pins only the two safety-relevant halves. Which non-committal verdict a
    malformed pattern earns (MANUAL vs UNKNOWN) is left to the PM -- see tester.md.
    """
    from agent_gap_radar.cli import main
    register = _single_check_register(tmp_path / "gaps", globs=["[]]"],
                                      pattern="MARKER")
    target = _git_repo(tmp_path / "t", {"a.py": "MARKER\n"})

    rc = main(["scan", str(target), "--gaps", str(register), "--json"])
    cap = capsys.readouterr()
    assert "Traceback" not in cap.err, cap.err
    if rc == 2:
        assert cap.out == "", "a refusal must leave stdout empty"
        assert cap.err.startswith("Error: "), cap.err
    else:
        assert rc == 0, rc
        verdict = json.loads(cap.out)["findings"][0]["verdict"]
        assert verdict != "ABSENT", (
            "a pattern the matcher could not evaluate was credited as a mitigation"
        )


# ---------------------------------------------------------------------------
# Scope: a tracked symlink is a tracked PATH, not a licence to read outside
# ---------------------------------------------------------------------------
#
# AMBIGUITY, reported to the PM: EB1 says the git walk returns "exactly the same
# sorted list it returns today", and for THIS input class it deliberately returns
# LESS. The pre-change walk followed a tracked symlink out of the target, so content
# the target does not contain could manufacture a finding. The safer reading is the
# one tested here -- EB1's "unchanged" governs ordinary tracked files, and leaving the
# scan target is a scope violation whatever the old walk did. Measured, not assumed:
# old walk -> ['link.py', 'real.py'], new walk -> ['real.py'].


def _symlink_repo(root: pathlib.Path, *, dangling: bool) -> pathlib.Path:
    """A git target holding one ordinary file and one TRACKED symlink whose target
    lies outside the target dir. Relative link, so no machine path is embedded."""
    outside = root / "outside"
    outside.mkdir(parents=True)
    if not dangling:
        (outside / "secret.py").write_text("OUTSIDE_MARKER\n", encoding="utf-8")
    target = root / "t"
    target.mkdir(parents=True)
    (target / "real.py").write_text("inside\n", encoding="utf-8")
    (target / "link.py").symlink_to(pathlib.Path("..") / "outside" / "secret.py")
    _git(target, "init", "-q")
    _git(target, "config", "user.email", "t@example.invalid")
    _git(target, "config", "user.name", "t")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "t")
    if not (target / "link.py").is_symlink() or "link.py" not in _tracked(target):
        pytest.skip("filesystem or git did not preserve the symlink")
    return target


def test_a_tracked_symlink_leaving_the_target_is_not_read_by_a_scan(tmp_path, capsys):
    """Scope invariant: a scan may only read files inside the target it was pointed
    at. The marker exists ONLY outside, reachable only through the tracked symlink."""
    target = _symlink_repo(tmp_path / "case", dangling=False)
    register = _single_check_register(tmp_path / "gaps", globs=["**/*.py"],
                                      pattern="OUTSIDE_MARKER")

    assert _rel(target, iter_files(target, ["**/*.py"])) == ["real.py"], \
        "the walk handed the scanner a path that resolves outside the target"

    from agent_gap_radar.cli import main
    rc = main(["scan", str(target), "--gaps", str(register), "--json"])
    cap = capsys.readouterr()
    assert (rc, cap.err) == (0, ""), cap.err
    assert json.loads(cap.out)["findings"][0]["verdict"] != "PRESENT", (
        "a finding was manufactured from content outside the scan target"
    )


def test_the_same_check_does_fire_on_an_in_target_file(tmp_path, capsys):
    """Two-sided control for the test above: without this, a check that never
    matches anything would make the scope assertion pass for free."""
    target = _git_repo(tmp_path / "t", {"real.py": "OUTSIDE_MARKER\n"})
    register = _single_check_register(tmp_path / "gaps", globs=["**/*.py"],
                                      pattern="OUTSIDE_MARKER")
    from agent_gap_radar.cli import main
    rc = main(["scan", str(target), "--gaps", str(register), "--json"])
    cap = capsys.readouterr()
    assert (rc, cap.err) == (0, ""), cap.err
    assert json.loads(cap.out)["findings"][0]["verdict"] == "PRESENT", cap.out


def test_a_dangling_tracked_symlink_neither_crashes_nor_changes_the_walk(
        tmp_path, capsys):
    """A tracked path whose file does not exist is a normal state of a checkout, so
    it must be skipped quietly -- stdout carries only the document."""
    target = _symlink_repo(tmp_path / "case", dangling=True)
    assert _rel(target, iter_files(target, ["**/*.py"])) == \
        _reference_git_walk(target, "**/*.py") == ["real.py"]

    from agent_gap_radar.cli import main
    rc = main(["scan", str(target), "--gaps", str(REPO_ROOT / "gaps")])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    assert "Traceback" not in cap.err, cap.err
    assert cap.out.endswith("\n") and not cap.out.endswith("\n\n")
