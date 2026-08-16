"""The anti-fail-open harness.

Every automated check in the register is run against its own declared fixtures:
the bad tree MUST produce PRESENT, and the good tree MUST NOT. A detector that
has never been shown to discriminate is worse than no detector, because it
reports health. These tests are what make such a check unmergeable.
"""

from __future__ import annotations

import pathlib

import pytest

from agent_gap_radar.checks import Verdict, evaluate, is_test_path, run_check
from agent_gap_radar.registry import load_all

REPO_GAPS = pathlib.Path(__file__).resolve().parent.parent / "gaps"


def _materialise(tmp_path: pathlib.Path, tree: dict[str, str]) -> pathlib.Path:
    root = tmp_path / "target"
    for rel, content in tree.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _checked_gaps():
    return [g for g in load_all(REPO_GAPS)
            if g.check is not None and g.check.fixtures is not None]


def test_register_has_at_least_one_automated_check():
    """Guards against this whole harness silently testing nothing."""
    assert _checked_gaps(), "no automated checks found; harness would be vacuous"


@pytest.mark.parametrize("gap", _checked_gaps(), ids=lambda g: g.id)
def test_bad_fixture_fires(gap, tmp_path):
    target = _materialise(tmp_path, gap.check.fixtures.bad)
    outcome = run_check(gap.check.model_dump(exclude_none=True), target)
    assert outcome.verdict is Verdict.PRESENT, (
        f"{gap.check.id} did NOT fire on its own known-bad fixture "
        f"(got {outcome.verdict.value}: {outcome.reason}). A detector that "
        f"cannot fire is fail-open.")
    assert outcome.locations, f"{gap.check.id} fired but reported no location"


@pytest.mark.parametrize("gap", _checked_gaps(), ids=lambda g: g.id)
def test_good_fixture_does_not_fire(gap, tmp_path):
    target = _materialise(tmp_path, gap.check.fixtures.good)
    outcome = run_check(gap.check.model_dump(exclude_none=True), target)
    assert outcome.verdict is not Verdict.PRESENT, (
        f"{gap.check.id} fired on its known-GOOD fixture at "
        f"{outcome.locations} -- false positive.")


# --- evaluator semantics ---------------------------------------------------

def test_absence_of_pattern_never_yields_absent(tmp_path):
    """The core invariant: not finding the bad pattern is not evidence of safety."""
    target = _materialise(tmp_path, {"a.py": "print('nothing interesting')\n"})
    check = {
        "id": "CHK-999",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": "dangerous_call"},
        "manual_question": "Does this project handle X?",
    }
    outcome = run_check(check, target)
    assert outcome.verdict is Verdict.MANUAL
    assert outcome.verdict is not Verdict.ABSENT
    assert "X" in outcome.question


def test_absent_requires_positive_mitigation(tmp_path):
    target = _materialise(tmp_path, {"a.py": "checkpoint_write(out)\n"})
    check = {
        "id": "CHK-998",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": "dangerous_call"},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": "checkpoint_write"},
    }
    assert run_check(check, target).verdict is Verdict.ABSENT


def test_both_signatures_escalates_to_manual(tmp_path):
    """A partial mitigation is the dangerous case, so it must not read as safe."""
    target = _materialise(tmp_path, {"a.py": "dangerous_call()\ncheckpoint_write(o)\n"})
    check = {
        "id": "CHK-997",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": "dangerous_call"},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                           "pattern": "checkpoint_write"},
    }
    outcome = run_check(check, target)
    assert outcome.verdict is Verdict.MANUAL
    assert "mitigation" in outcome.question.lower()


def test_not_applicable_short_circuits(tmp_path):
    target = _materialise(tmp_path, {"readme.md": "a static site\n"})
    check = {
        "id": "CHK-996",
        "applies_when": {"kind": "file_exists", "globs": ["**/*.py"]},
        "present_when": {"kind": "content_matches", "globs": ["**/*.md"],
                         "pattern": "site"},
        "fixtures": {"bad": {"x.py": "y"}, "good": {"x.py": "z"}},
    }
    assert run_check(check, target).verdict is Verdict.NOT_APPLICABLE


def test_unknown_rule_kind_raises_rather_than_passing():
    """Silently returning False for an unknown kind would be fail-open."""
    with pytest.raises(ValueError, match="unknown rule kind"):
        evaluate({"kind": "vibes_check", "globs": ["*"]}, pathlib.Path("."))


def test_unknown_rule_kind_surfaces_as_unknown_verdict(tmp_path):
    target = _materialise(tmp_path, {"a.py": "x\n"})
    outcome = run_check({"id": "CHK-995",
                         "present_when": {"kind": "nope", "globs": ["*"]}}, target)
    assert outcome.verdict is Verdict.UNKNOWN


def test_empty_all_of_is_rejected_not_vacuously_true(tmp_path):
    target = _materialise(tmp_path, {"a.py": "x\n"})
    with pytest.raises(ValueError, match="vacuously true"):
        evaluate({"kind": "all_of", "rules": []}, target)


def test_locations_include_line_numbers(tmp_path):
    target = _materialise(tmp_path, {"a.py": "line1\nline2\nBADMARK\n"})
    hit = evaluate({"kind": "content_matches", "globs": ["**/*.py"],
                    "pattern": "BADMARK"}, target)
    assert hit.matched
    assert hit.locations == ["a.py:3"]


def test_vendored_dirs_are_skipped(tmp_path):
    target = _materialise(tmp_path, {
        "node_modules/pkg/a.py": "BADMARK\n",
        ".venv/lib/b.py": "BADMARK\n",
        "src/c.py": "clean\n",
    })
    hit = evaluate({"kind": "content_matches", "globs": ["**/*.py"],
                    "pattern": "BADMARK"}, target)
    assert not hit.matched, f"scanned vendored code: {hit.locations}"


# --- scope: judge what the project ships, not its scratch -------------------

def _git_init(root: pathlib.Path) -> None:
    import subprocess
    for cmd in (["git", "init", "-q"],
                ["git", "config", "user.email", "t@example.invalid"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=root, capture_output=True, check=True)


def test_gitignored_files_are_not_scanned(tmp_path):
    """A loop's gitignored per-iteration scratch is not the project's code."""
    import subprocess
    root = _materialise(tmp_path, {
        ".gitignore": "state/\n",
        "src/clean.py": "print('fine')\n",
        "state/iter-01/probe.py": "BADMARK\n",
    })
    _git_init(root)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, check=True)

    from agent_gap_radar.checks import _TRACKED_CACHE
    _TRACKED_CACHE.clear()
    hit = evaluate({"kind": "content_matches", "globs": ["**/*.py"],
                    "pattern": "BADMARK"}, root)
    _TRACKED_CACHE.clear()
    assert not hit.matched, f"scanned gitignored scratch: {hit.locations}"


def test_tracked_files_are_scanned(tmp_path):
    """Positive control: the same harness must still find real tracked code."""
    import subprocess
    root = _materialise(tmp_path, {"src/real.py": "BADMARK\n"})
    _git_init(root)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, check=True)

    from agent_gap_radar.checks import _TRACKED_CACHE
    _TRACKED_CACHE.clear()
    hit = evaluate({"kind": "content_matches", "globs": ["**/*.py"],
                    "pattern": "BADMARK"}, root)
    _TRACKED_CACHE.clear()
    assert hit.matched and hit.locations == ["src/real.py:1"]


def test_non_git_target_falls_back_to_skip_list(tmp_path):
    root = _materialise(tmp_path, {"src/a.py": "BADMARK\n",
                                   "node_modules/x.py": "BADMARK\n"})
    from agent_gap_radar.checks import _TRACKED_CACHE
    _TRACKED_CACHE.clear()
    hit = evaluate({"kind": "content_matches", "globs": ["**/*.py"],
                    "pattern": "BADMARK"}, root)
    _TRACKED_CACHE.clear()
    assert hit.matched
    assert hit.locations == ["src/a.py:1"], hit.locations


# --------------------------------------------------------------------------
# A mitigation named only by a test is not a mitigation.
#
# Regression for a PROVEN false negative found by scanning a real target:
# GAP-009 came back ABSENT ("mitigation positively identified") citing a TEST
# file that merely spelled `importlib.reload`, while the target exhibited that
# gap continuously and shipped a dedicated verb to measure it. Credited from
# test text, a thorough suite reads as HEALTHIER than untested code, which
# inverts the signal this tool exists to produce.
# --------------------------------------------------------------------------

_MITIGATION_CHECK = {
    "id": "CHK-999",
    "rationale": "r",
    "manual_question": "q",
    "present_when": {
        "kind": "content_matches",
        "globs": ["**/*.py"],
        "pattern": r"while True",
    },
    "mitigated_when": {
        "kind": "content_matches",
        "globs": ["**/*.py"],
        "pattern": r"importlib\.reload",
    },
}


def _tree(root, files):
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def test_mitigation_found_only_in_a_test_is_not_credited(tmp_path):
    """The exact false negative that shipped. Must NOT report ABSENT."""
    _tree(tmp_path, {
        "app/loop.py": "def main():\n    while True:\n        step()\n",
        "tests/test_loop.py": "import importlib\n# we should importlib.reload here one day\n",
    })
    out = run_check(_MITIGATION_CHECK, tmp_path)
    assert out.verdict is not Verdict.ABSENT, (
        f"a mitigation named only by a test was credited: {out.locations}"
    )
    assert out.verdict is Verdict.PRESENT, out


def test_mitigation_in_real_code_is_still_credited(tmp_path):
    """The positive control. Excluding tests must not break real detection."""
    _tree(tmp_path, {
        "app/loop.py": (
            "import importlib\nimport app.mod\n\n"
            "def main():\n    while True:\n        importlib.reload(app.mod)\n"
        ),
    })
    out = run_check(_MITIGATION_CHECK, tmp_path)
    assert out.verdict is Verdict.MANUAL, out
    assert "ambiguous" in out.reason, out


def test_mitigation_only_in_code_yields_absent(tmp_path):
    _tree(tmp_path, {
        "app/reloader.py": "import importlib\nimportlib.reload(x)\n",
    })
    out = run_check(_MITIGATION_CHECK, tmp_path)
    assert out.verdict is Verdict.ABSENT, out


@pytest.mark.parametrize("rel", [
    "tests/test_x.py", "test/x.py", "spec/x.rb", "__tests__/x.js",
    "src/test_helpers.py", "src/thing_test.go", "src/a.spec.ts",
    "conftest.py", "fixtures/sample.py",
])
def test_test_paths_are_recognised(tmp_path, rel):
    assert is_test_path(tmp_path, tmp_path / rel), rel


@pytest.mark.parametrize("rel", [
    "src/app.py", "src/latest.py", "protest/x.py", "src/contest.py",
    "src/attestation.py", "lib/manifest.py",
])
def test_ordinary_code_is_not_mistaken_for_a_test(tmp_path, rel):
    """A substring match would eat `latest`, `protest`, `manifest`."""
    assert not is_test_path(tmp_path, tmp_path / rel), rel


def test_present_when_still_sees_test_files(tmp_path):
    """Only MITIGATIONS exclude tests. A gap signature in a test is real."""
    _tree(tmp_path, {"tests/test_loop.py": "def t():\n    while True:\n        pass\n"})
    out = run_check(
        {"id": "CHK-998", "rationale": "r", "manual_question": "q",
         "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                          "pattern": r"while True"}},
        tmp_path,
    )
    assert out.verdict is Verdict.PRESENT, out


# --------------------------------------------------------------------------
# Locator ranking. A verdict can be right while its evidence list is useless:
# on a repo with a large suite, test-file matches crowd out every line of code
# that actually runs. Ranking is honest only if the reader sees what was cut.
# --------------------------------------------------------------------------

def test_locations_put_real_code_before_tests(tmp_path):
    files = {f"tests/test_{i}.py": "import subprocess\n" for i in range(12)}
    files["app/runner.py"] = "import subprocess\n"
    _tree(tmp_path, files)
    hit = evaluate(
        {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "import subprocess"},
        tmp_path,
    )
    assert hit.matched
    assert hit.locations[0].startswith("app/runner.py"), hit.locations


def test_suppressed_locations_are_reported_not_silently_cut(tmp_path):
    _tree(tmp_path, {f"tests/test_{i}.py": "import subprocess\n" for i in range(15)})
    hit = evaluate(
        {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "import subprocess"},
        tmp_path,
    )
    tail = hit.locations[-1]
    assert tail.startswith("(+5 more"), hit.locations
    assert "in test files" in tail, tail


def test_no_suppression_note_when_everything_fits(tmp_path):
    _tree(tmp_path, {"app/a.py": "import subprocess\n"})
    hit = evaluate(
        {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "import subprocess"},
        tmp_path,
    )
    assert hit.locations == ["app/a.py:1"], hit.locations
