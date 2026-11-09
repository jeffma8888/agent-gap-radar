"""Iteration 391: a dependency lockfile reached by a WILDCARD glob is never mitigation evidence.

Why this matters: ABSENT is the only verdict that claims a target is safe. A one-line
`package-lock.json` naming a package `sandbox` used to flip the GAP-016 reproduction
sample from PRESENT (rc 1) to ABSENT (rc 0) -- a lockfile is generated dependency data,
it does not run, and a package's NAME is not a gate. The same file is also never read by a
`content_absent` rule (there it could only suppress a signature, so dropping it is
fail-closed). A glob whose last segment names the file literally (GAP-011's
`**/package-lock.json`) keeps it.

Black-box: drives `agent_gap_radar.cli.main` in-process and the public
`checks.evaluate` / `checks.file_cache_scope` seam named by the spec. Fixtures are tmp
dirs; the bad reproduction samples come from the committed register records, the extra
files are literal strings below. Offline; every path is derived from this file's location.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

LOCKFILE_SANDBOX = '{"packages":{"node_modules/sandbox":{"version":"1.0.0"}}}\n'


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _bad_fixture(gap: str) -> dict[str, str]:
    (path,) = sorted(LIVE_GAPS.glob(f"{gap}-*.json"))
    return json.loads(path.read_text(encoding="utf-8"))["check"]["fixtures"]["bad"]


def _target(root: pathlib.Path, gap: str, extra: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True)
    for rel, text in {**_bad_fixture(gap), **extra}.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    return root


def _scan_json(target: pathlib.Path, gap: str) -> dict:
    code, out, err = _run("scan", str(target), "--gaps", str(LIVE_GAPS), "--gap", gap, "--json")
    assert code == 0, err
    assert err == ""
    doc = json.loads(out)
    (finding,) = [f for f in doc["findings"] if f["gap_id"] == gap]
    return finding


def _gate(target: pathlib.Path, gap: str) -> int:
    code, out, err = _run("scan", str(target), "--gaps", str(LIVE_GAPS), "--gap", gap, "--exit-code")
    assert err == "", err
    assert out.endswith("\n") and not out.endswith("\n\n")
    return code


def _names(finding: dict) -> str:
    return json.dumps(finding["locations"])


# ---- Behaviours 1-2: the regression fixture --------------------------------------------


def test_b1_control_bad_fixture_without_lockfile_is_present_rc1(tmp_path):
    target = _target(tmp_path / "svc", "GAP-016", {})
    assert _gate(target, "GAP-016") == 1
    assert _scan_json(target, "GAP-016")["verdict"] == "PRESENT"


def test_b1_lockfile_naming_sandbox_keeps_gap016_present_rc1(tmp_path):
    target = _target(tmp_path / "svc", "GAP-016", {"package-lock.json": LOCKFILE_SANDBOX})
    assert _gate(target, "GAP-016") == 1
    code, out, _ = _run("scan", str(target), "--gaps", str(LIVE_GAPS), "--gap", "GAP-016")
    assert code == 0
    assert "| PRESENT | 1 |" in out
    assert "| ABSENT | 0 |" in out


def test_b2_json_verdict_present_and_no_location_names_the_lockfile(tmp_path):
    target = _target(tmp_path / "svc", "GAP-016", {"package-lock.json": LOCKFILE_SANDBOX})
    finding = _scan_json(target, "GAP-016")
    assert finding["verdict"] == "PRESENT"
    assert finding["locations"], "a PRESENT verdict still cites where the signature is"
    assert "package-lock.json" not in _names(finding)


# ---- Behaviour 3: every listed spelling, case-insensitive -------------------------------


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("npm-shrinkwrap.json", LOCKFILE_SANDBOX),
        ("pnpm-lock.yaml", "name: sandbox\n"),
        ("Package-Lock.json", LOCKFILE_SANDBOX),
        ("Pnpm-Lock.yaml", "name: sandbox\n"),
        ("sub/dir/package-lock.json", LOCKFILE_SANDBOX),
    ],
)
def test_b3_other_lockfiles_and_case_variants_stay_present_rc1(tmp_path, name, text):
    target = _target(tmp_path / "svc", "GAP-016", {name: text})
    assert _gate(target, "GAP-016") == 1
    finding = _scan_json(target, "GAP-016")
    assert finding["verdict"] == "PRESENT"
    assert pathlib.PurePosixPath(name).name not in _names(finding)


# ---- Behaviour 4: a non-lockfile JSON is still mitigation evidence ----------------------


def test_b4_control_policy_json_still_mitigates(tmp_path):
    target = _target(tmp_path / "svc", "GAP-016", {"config/policy.json": '{"mode":"sandbox"}\n'})
    assert _gate(target, "GAP-016") == 0
    finding = _scan_json(target, "GAP-016")
    assert finding["verdict"] == "ABSENT"
    assert "config/policy.json" in _names(finding)


def test_b4_a_near_miss_name_is_not_a_lockfile(tmp_path):
    # Only the exact basenames are lockfiles: `package-lock.json.txt`-style or prefixed
    # names are ordinary JSON and still count (the rule is about generated lockfiles).
    target = _target(tmp_path / "svc", "GAP-016", {"my-package-lock.json": '{"mode":"sandbox"}\n'})
    finding = _scan_json(target, "GAP-016")
    assert finding["verdict"] == "ABSENT"
    assert "my-package-lock.json" in _names(finding)


# ---- Behaviour 5: GAP-011 literal carve-out ---------------------------------------------


def test_b5_gap011_literal_glob_verdict_unchanged_with_and_without_lockfile(tmp_path):
    plain = _scan_json(_target(tmp_path / "plain", "GAP-011", {}), "GAP-011")
    locked = _scan_json(_target(tmp_path / "locked", "GAP-011", {"package-lock.json": "{}\n"}), "GAP-011")
    # Measured at HEAD f8c1b5f on the same two dirs (byte-identical --json there):
    # the bare sample is PRESENT, and the literally-named lockfile still moves it to
    # MANUAL -- which proves `**/package-lock.json` still SEES the file on the
    # mitigation path. Were the lockfile dropped, `locked` would read PRESENT too.
    assert plain["verdict"] == "PRESENT"
    assert locked["verdict"] == "MANUAL"


# ---- Behaviours 6-8: the checks.evaluate seam -------------------------------------------

SIG_JSON = {"kind": "content_matches", "globs": ["**/*.json"], "pattern": "sandbox"}
ABSENT_JSON = {"kind": "content_absent", "globs": ["**/*.json"], "pattern": "sandbox"}
EXISTS_LITERAL = {"kind": "file_exists", "globs": ["**/package-lock.json"]}
EXISTS_WILD = {"kind": "file_exists", "globs": ["**/*.json"]}

# (rule, exclude_tests, expected matched) -- the spec's Behaviour 6/7 table.
SEAM_TABLE = [
    (SIG_JSON, True, False),
    (SIG_JSON, False, True),
    (ABSENT_JSON, True, True),
    (ABSENT_JSON, False, True),
    (EXISTS_LITERAL, True, True),
    (EXISTS_WILD, True, False),
    ({"kind": "any_of", "rules": [SIG_JSON]}, True, False),
    ({"kind": "all_of", "rules": [SIG_JSON]}, True, False),
    ({"kind": "any_of", "rules": [SIG_JSON]}, False, True),
    ({"kind": "all_of", "rules": [SIG_JSON]}, False, True),
]


@pytest.fixture
def lock_only(tmp_path):
    target = tmp_path / "t"
    target.mkdir()
    (target / "package-lock.json").write_text("sandbox\n", encoding="utf-8")
    return target


@pytest.mark.parametrize(("rule", "exclude_tests", "expected"), SEAM_TABLE)
def test_b6_b7_evaluate_table(lock_only, rule, exclude_tests, expected):
    assert checks.evaluate(rule, lock_only, exclude_tests=exclude_tests).matched is expected


def test_b6_literal_glob_beside_wildcard_glob_keeps_the_file(lock_only):
    # Judged per glob: another glob in the same rule names the file literally.
    rule = {"kind": "file_exists", "globs": ["**/*.json", "**/package-lock.json"]}
    assert checks.evaluate(rule, lock_only, exclude_tests=True).matched is True


def test_b6_non_lockfile_json_is_seen_on_the_mitigation_path(tmp_path):
    target = tmp_path / "t"
    target.mkdir()
    (target / "policy.json").write_text("sandbox\n", encoding="utf-8")
    assert checks.evaluate(SIG_JSON, target, exclude_tests=True).matched is True
    assert checks.evaluate(ABSENT_JSON, target, exclude_tests=False).matched is False


def test_b8_memo_cannot_leak_a_filtered_domain(lock_only):
    rules = [SIG_JSON, ABSENT_JSON, EXISTS_LITERAL, EXISTS_WILD]
    unscoped = {
        (i, flag): checks.evaluate(rule, lock_only, exclude_tests=flag).matched
        for i, rule in enumerate(rules)
        for flag in (False, True)
    }
    with checks.file_cache_scope():
        for flag in (False, True, False):
            for i, rule in enumerate(rules):
                got = checks.evaluate(rule, lock_only, exclude_tests=flag).matched
                assert got is unscoped[(i, flag)], (i, flag)
    assert unscoped[(0, False)] is True and unscoped[(0, True)] is False


# ---- Behaviour 10: the contract sentence ------------------------------------------------


def test_b10_contract_sentence_follows_the_inverts_paragraph():
    text = CONTRACT.read_text(encoding="utf-8")
    anchor = "which inverts the signal."
    assert anchor in text
    tail = text.split(anchor, 1)[1]
    following = tail.strip().split("\n\n", 1)[0]
    assert "package-lock.json" in following
    assert "uv.lock" in following
    assert "content_absent" in following
    assert "literal" in following.lower()
