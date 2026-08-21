"""Iteration 30 behaviors: the WALKED enumeration branch refuses a file whose
`resolve()` leaves the target root.

`checks.iter_files` has two enumeration branches. The TRACKED branch (git target) has
refused escaping paths since iteration 03. The WALKED branch (non-git target) did not,
so a scan of a plain directory could publish an evidence locator naming a file the
scanned tree does not contain, and flip a verdict on byte-identical inputs. Iteration
30's claim is that the walked branch now applies the same containment rule.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff.
Every expectation comes from `pm.md`'s Expected Behaviors; every claim is measured by
CALLING the public `checks` interface or by RUNNING the packaged CLI entry point.

Structural notes, so this file cannot lie later:

* **Every containment assertion asserts its fixture's PREMISE first**, as the acceptance
  criteria require: that the symlink really is a symlink, and that its `resolve()` really
  does leave the target root. A containment test whose fixture does not escape passes for
  free.
* **The guard is proved to be a DECISION, not a walk that returns nothing.** Behavior 1
  asserts the escaping entry is ABSENT *and* its non-escaping sibling is PRESENT in the
  same list. `test_control_*` additionally measures that a plain `Path.glob` walk of the
  same fixture DOES surface the escaping entry, so the fixture is a known-bad sample and
  its absence from `iter_files` is attributable to the rule under test.
* **Behavior 3 is the fail-CLOSED case, and it needs an EXPLICIT fixture because the
  incidental one the spec relied on does not exist.** `pm.md` argues a guard that resolved
  only the child would "reject every file in every fixture" here, since pytest's `tmp_path`
  shares the platform temp root. Measured: the platform temp dir is indeed reached through a
  symlink, but pytest RESOLVES its basetemp, so `tmp_path` already equals its own
  `resolve()`. Such a guard would therefore have passed this whole suite in silence, which
  makes `test_b3_a_target_root_...` load-bearing rather than belt-and-braces. Both halves
  are asserted in `test_b3_premise_the_incidental_safety_net_does_not_exist`.
* **Behavior 4 asserts RESOLVED names**, not raw path strings. Whether an in-root symlink
  and its target dedupe to one entry or stay two is not settled by the spec, so the test
  asserts the property the spec does state -- nothing inside is dropped and nothing
  outside leaks -- and the ambiguity is reported to the PM rather than silently frozen.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`, every fixture lives under pytest's `tmp_path`, and the git
  identity is the RFC-2606 reserved `t@example.invalid` used by the existing suite.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import tempfile

import pytest

from agent_gap_radar import checks

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The marker that lives ONLY in the outside file, reachable only through the escaping
#: symlink. If a rendered document ever carries a PRESENT verdict for it on a walked
#: target, the scan read something the target does not contain.
MARKER_OUTSIDE = "AGR30_OUTSIDE_ONLY_MARKER"


# ---------------------------------------------------------------------------
# helpers -- same shapes as tests/test_iter03_behavior.py and iter26
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


def _git_init(root: pathlib.Path) -> pathlib.Path:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "t")
    return root


def _rel(target: pathlib.Path, paths) -> list[str]:
    return sorted(str(pathlib.Path(p).relative_to(target)) for p in paths)


def _names(paths) -> list[str]:
    """Basenames, for the cases where the returned path's PREFIX is not what is under
    test (a symlinked target root) or is not settled by the spec (dedup)."""
    return sorted(pathlib.Path(p).name for p in paths)


def _plain_glob(target: pathlib.Path, pattern: str) -> list[str]:
    """A bare `Path.glob` walk: the reference that shows the fixture's escaping entry is
    discoverable at all, so its absence from `iter_files` is a decision."""
    return sorted(str(p.relative_to(target)) for p in target.glob(pattern) if p.is_file())


def _escape_tree(root: pathlib.Path, *, dangling: bool = False) -> pathlib.Path:
    """`pkg/inside.py` (regular) beside `pkg/escape.py` (symlink out of the root).

    `root/outside/secret.py` holds the ONLY copy of `MARKER_OUTSIDE`; `root/target` is
    the thing scans are pointed at.
    """
    outside = _tree(root / "outside", {"secret.py": f"{MARKER_OUTSIDE}\n"})
    target = _tree(root / "target", {"pkg/inside.py": "def inside():\n    return 1\n"})
    dest = outside / ("missing.py" if dangling else "secret.py")
    (target / "pkg" / "escape.py").symlink_to(dest)
    return target


def _assert_escapes(target: pathlib.Path, rel: str, *, dangling: bool = False) -> None:
    """The acceptance criteria's PREMISE assertion: the entry is a symlink, and its
    resolved path really does leave the resolved root."""
    link = target / rel
    assert link.is_symlink(), f"premise: {rel} must be a symlink"
    assert link.resolve() != link, f"premise: {rel} must resolve elsewhere"
    assert not link.resolve().is_relative_to(target.resolve()), (
        f"premise: {rel} must resolve OUTSIDE the target root"
    )
    if dangling:
        assert not link.exists(), f"premise: {rel} must dangle"
    else:
        assert link.exists(), f"premise: {rel} must resolve to a real file"


def _single_check_register(root: pathlib.Path, *, globs: list[str],
                           pattern: str) -> pathlib.Path:
    """A minimal one-record register whose only rule is a content match.

    Built by hand rather than copied from `gaps/` so the tree can be tiny and the verdict
    unambiguous: with no `mitigated_when`, a check that finds nothing earns a
    non-committal verdict, never ABSENT. Same shape as `test_iter03_behavior.py`.
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


def _scan(target: pathlib.Path, register: pathlib.Path, capsys,
          *, as_json: bool = False) -> str:
    """Drive the public CLI the way `project.scripts` declares it, and assert the
    quality bar's stream contract: stdout carries only the document."""
    from agent_gap_radar.cli import main
    argv = ["scan", str(target), "--gaps", str(register)]
    if as_json:
        argv.append("--json")
    rc = main(argv)
    cap = capsys.readouterr()
    assert (rc, cap.err) == (0, ""), f"rc={rc} stderr={cap.err!r}"
    assert cap.out.endswith("\n") and not cap.out.endswith("\n\n"), (
        "renderer must end in exactly one newline"
    )
    return cap.out


# ---------------------------------------------------------------------------
# Behavior 1 -- the walked branch drops an escaping symlink, keeps its sibling
# ---------------------------------------------------------------------------

def test_b1_walked_branch_drops_escaping_symlink_and_keeps_its_sibling(tmp_path):
    target = _escape_tree(tmp_path)
    _assert_escapes(target, "pkg/escape.py")
    assert checks.tracked_files(target) is None, (
        "premise: this fixture must select the WALKED branch, not the tracked one"
    )

    got = _rel(target, checks.iter_files(target, ["**/*.py"]))

    assert got == ["pkg/inside.py"], (
        "the walked branch handed the scanner a path resolving outside the target"
    )


def test_b1_control_a_plain_walk_does_surface_the_escaping_entry(tmp_path):
    """Anti-vacuity: without this, behavior 1 would also pass on a walk that returned
    nothing, or on a fixture whose symlink no glob ever reached."""
    target = _escape_tree(tmp_path)
    _assert_escapes(target, "pkg/escape.py")

    assert _plain_glob(target, "**/*.py") == ["pkg/escape.py", "pkg/inside.py"], (
        "premise: a bare glob walk must see BOTH entries, or behavior 1 proves nothing"
    )


# ---------------------------------------------------------------------------
# Behavior 2 -- one commit, one answer: git and non-git agree, and no leaked locator
# ---------------------------------------------------------------------------

def test_b2_git_and_non_git_targets_report_the_same_present_count(tmp_path, capsys):
    """Two targets, byte-identical content, differing ONLY by `git init`. The register's
    single automated record matches text held exclusively in the outside file.

    Two DIFFERENT directories rather than one path that gains `.git`, because
    `checks._TRACKED_CACHE` is keyed on the resolved path for the life of the process.
    """
    walked = _escape_tree(tmp_path / "walked")
    tracked = _git_init(_escape_tree(tmp_path / "tracked"))
    register = _single_check_register(tmp_path / "gaps", globs=["**/*.py"],
                                      pattern=MARKER_OUTSIDE)

    for label, t in (("walked", walked), ("tracked", tracked)):
        _assert_escapes(t, "pkg/escape.py")
        assert (t / "pkg" / "inside.py").read_bytes() == \
            (walked / "pkg" / "inside.py").read_bytes(), f"{label}: content must match"
    assert checks.tracked_files(walked) is None, "premise: walked branch"
    assert checks.tracked_files(tracked) is not None, "premise: tracked branch"

    docs = {}
    counts = {}
    for label, t in (("walked", walked), ("tracked", tracked)):
        docs[label] = _scan(t, register, capsys)
        payload = json.loads(_scan(t, register, capsys, as_json=True))
        counts[label] = sum(1 for f in payload["findings"]
                            if f["verdict"] == "PRESENT")

    assert counts["walked"] == counts["tracked"], (
        f"one commit scanned to two answers: {counts}"
    )
    for label, doc in docs.items():
        assert "escape.py" not in doc, (
            f"{label}: the rendered document names a file resolving outside the target"
        )
    assert MARKER_OUTSIDE not in docs["walked"], (
        "the walked scan quoted content held only outside the target"
    )


def test_b2_control_the_same_check_does_fire_on_an_in_target_file(tmp_path, capsys):
    """Two-sided control for behavior 2: a check that never matched anything would make
    the equal-count assertion pass for free."""
    target = _tree(tmp_path / "t", {"pkg/inside.py": f"{MARKER_OUTSIDE}\n"})
    register = _single_check_register(tmp_path / "gaps", globs=["**/*.py"],
                                     pattern=MARKER_OUTSIDE)
    assert checks.tracked_files(target) is None, "premise: walked branch"

    payload = json.loads(_scan(target, register, capsys, as_json=True))
    present = [f for f in payload["findings"] if f["verdict"] == "PRESENT"]

    assert len(present) == 1, (
        f"the walked branch cannot see an in-target match either: {payload['findings']}"
    )


# ---------------------------------------------------------------------------
# Behavior 3 -- the fail-CLOSED case: a symlinked target ROOT must still be walked
# ---------------------------------------------------------------------------

def test_b3_a_target_root_reached_through_a_symlink_still_yields_its_files(tmp_path):
    """The guard must resolve BOTH sides. Comparing an unresolved root against a resolved
    child rejects every file under a symlinked root -- which is every pytest fixture on
    this machine."""
    real = _tree(tmp_path / "real_root", {"pkg/inside.py": "def inside():\n    return 1\n"})
    link_root = tmp_path / "link_root"
    link_root.symlink_to(real, target_is_directory=True)

    assert link_root.is_symlink(), "premise: the target root must be a symlink"
    assert link_root.resolve() != link_root, "premise: the root must resolve elsewhere"
    assert checks.tracked_files(link_root) is None, "premise: walked branch"

    got = checks.iter_files(link_root, ["**/*.py"])

    assert _names(got) == ["inside.py"], (
        "a guard comparing an unresolved root against a resolved child reds every fixture"
    )


def test_b3_premise_the_incidental_safety_net_does_not_exist(tmp_path):
    """CORRECTS `pm.md`'s behavior-3 rationale. Measured, not inferred.

    The spec argues the fail-CLOSED guard would be caught for free, because "pytest's
    `tmp_path` is rooted in that same place" as `tempfile.mkdtemp()`, "so a guard
    comparing an unresolved root against a resolved child rejects every file in every
    fixture". Half of that is right and the conclusion is wrong. The platform's own
    temp dir IS unresolved, but pytest RESOLVES its basetemp before handing it out, so
    `tmp_path` already equals its own `resolve()`.

    A guard that resolved only the child would therefore have passed this entire suite
    silently. `test_b3_a_target_root_reached_through_a_symlink_still_yields_its_files`
    is the ONLY thing covering the fail-closed case, which makes it load-bearing rather
    than belt-and-braces.
    """
    platform_tmp = pathlib.Path(tempfile.gettempdir())
    assert platform_tmp != platform_tmp.resolve(), (
        "the spec's measurement: the platform temp dir is reached through a symlink"
    )
    assert tmp_path == tmp_path.resolve(), (
        "the spec's inference, refuted: pytest hands out an ALREADY-RESOLVED tmp_path, "
        "so no fixture here incidentally exercises a symlinked root"
    )


# ---------------------------------------------------------------------------
# Behavior 4 -- a symlink resolving INSIDE the root is kept
# ---------------------------------------------------------------------------

def test_b4_a_symlink_resolving_inside_the_root_is_kept(tmp_path):
    target = _tree(tmp_path / "t", {
        "pkg/inside.py": "def inside():\n    return 1\n",
        "data/held.py": "def held():\n    return 2\n",
    })
    (target / "pkg" / "alias.py").symlink_to(target / "data" / "held.py")

    link = target / "pkg" / "alias.py"
    assert link.is_symlink(), "premise: alias.py must be a symlink"
    assert link.resolve() != link, "premise: alias.py must resolve elsewhere"
    assert link.resolve().is_relative_to(target.resolve()), (
        "premise: alias.py must resolve INSIDE the target root"
    )
    assert checks.tracked_files(target) is None, "premise: walked branch"

    got = checks.iter_files(target, ["**/*.py"])

    # Asserted on RESOLVED names: whether an in-root symlink and its target dedupe to one
    # entry is not settled by the spec, but "nothing inside is dropped and nothing outside
    # leaks" is exactly what behavior 4 claims.
    assert sorted({pathlib.Path(p).resolve().name for p in got}) == \
        ["held.py", "inside.py"], f"an in-root symlink changed the answer: {got}"


# ---------------------------------------------------------------------------
# Behavior 5 -- a dangling symlink is skipped quietly
# ---------------------------------------------------------------------------

def test_b5_a_dangling_symlink_is_skipped_and_raises_nothing(tmp_path, capsys):
    target = _escape_tree(tmp_path, dangling=True)
    _assert_escapes(target, "pkg/escape.py", dangling=True)
    assert checks.tracked_files(target) is None, "premise: walked branch"

    assert _rel(target, checks.iter_files(target, ["**/*.py"])) == ["pkg/inside.py"]

    register = _single_check_register(tmp_path / "gaps", globs=["**/*.py"],
                                     pattern=MARKER_OUTSIDE)
    doc = _scan(target, register, capsys)
    assert "Traceback" not in doc


# ---------------------------------------------------------------------------
# Behavior 6 -- this repo is a git target, so every published locator is tracked
# ---------------------------------------------------------------------------

#: A backtick-quoted `path:line` locator, as `radar scan` renders evidence. Excludes URLs
#: (a citation locator) by requiring no `//` and no whitespace.
_LOCATOR = re.compile(r"`([^`\s]+\.[A-Za-z0-9_]+):(\d+)`")


def test_b6_scanning_this_repo_publishes_only_tracked_locators(tmp_path, capsys):
    """This repository is a git target, so `_iter_tracked` answers and iteration 30's
    change cannot reach it. Asserted as a PROPERTY rather than as byte-equality with a
    pre-change baseline: once the diff is applied that baseline no longer exists, so
    byte-equality is not black-box testable while this is, on either branch.
    """
    assert checks.tracked_files(REPO_ROOT) is not None, (
        "premise: the repo under test must be a git target"
    )
    tracked = {line for line in
               _git(REPO_ROOT, "ls-files").stdout.splitlines() if line}
    assert tracked, "premise: git ls-files must name files"

    doc = _scan(REPO_ROOT, REPO_ROOT / "gaps", capsys)

    locators = {m.group(1) for m in _LOCATOR.finditer(doc)}
    assert locators, "anti-vacuity: the scan of this repo must publish some locator"

    untracked = sorted(p for p in locators if p not in tracked)
    assert untracked == [], f"published locators name files git does not track: {untracked}"
