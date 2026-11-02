"""Iteration 380 (tester): black-box pins for `scan --exit-code` refusing on UNKNOWN.

The engineer's module drives the spec's fixtures T and P once each. This module adds
angles that do not trust any hand-written expectation:

- a FLOOR SWEEP (0..7): at every floor the `--json` document of the same scan is the
  oracle -- the gate refuses (2, empty stdout) iff that document lists an UNKNOWN
  finding with `below_floor == false`, the `Error:` line names exactly those ids and
  their count, and otherwise the exit is 0 with the very same document (behaviors 1, 4);
- target VARIANTS (unreadable file nested in a subdir, two unreadable files, a target
  holding only the unreadable file) checked against the same json-derived oracle (1);
- the refusal is identical across markdown/`--json`, across repeated runs and in a
  FRESH `python -m agent_gap_radar.cli` process (1, 2);
- readable controls with above-floor MANUAL / NOT_APPLICABLE and zero UNKNOWN exit 0,
  so MANUAL is excluded from the predicate, not merely unmentioned (6);
- a baseline written while the target was READABLE (clean) cannot certify the same
  target once a file becomes unreadable; a baseline plus a floor above every UNKNOWN
  still exits 0 (7);
- P: precedence holds in both formats with the same document either way (5);
- `--gap <UNKNOWN id> --exit-code` keeps the one-record refusal naming ONE id (8).
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CLAUSE = "reached no verdict (UNKNOWN)"
GID = re.compile(r"GAP-\d+")

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root reads a chmod 000 file, so unreadable cannot be staged",
)


def _run(capsys, *argv: object) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _last(err: str) -> str:
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, "stderr is empty"
    return lines[-1]


def _json(capsys, target: pathlib.Path, *extra: object) -> dict:
    code, out, err = _run(capsys, "scan", target, "--gaps", GAPS, "--json", *extra)
    assert code == 0 and err == "", (code, err)
    assert out.endswith("\n") and not out.endswith("\n\n")
    return json.loads(out)


def _gating_unknown(doc: dict) -> list[str]:
    return [f["gap_id"] for f in doc["findings"]
            if f["verdict"] == "UNKNOWN" and not f["below_floor"]]


def _assert_refusal(code: int, out: str, err: str, ids: list[str]) -> str:
    assert code == 2, (code, err[-300:])
    assert out == "", "stdout must carry no bytes on a refusal"
    line = _last(err)
    assert line.startswith("Error: "), line
    assert CLAUSE in line, line
    named = GID.findall(line)
    assert len(named) == len(set(named)), "an id is named twice"
    assert set(named) == set(ids), sorted(set(named) ^ set(ids))
    assert re.search(rf"(?<!\d){len(ids)}(?!\d)", line), f"count {len(ids)} missing: {line[:120]}"
    return line


class _Blocked:
    """chmod the files 000 for the body; always restore 0o644."""

    def __init__(self, *paths: pathlib.Path):
        self.paths = paths

    def __enter__(self):
        for p in self.paths:
            p.chmod(0o000)
        return self

    def __exit__(self, *exc):
        for p in self.paths:
            p.chmod(0o644)
        return False


def _make_t(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    root.mkdir(parents=True)
    (root / "a.py").write_text("import os\n")
    blocked = root / "b.py"
    blocked.write_text("x=1\n")
    return root, blocked


@pytest.fixture
def target_t(tmp_path: pathlib.Path) -> Iterator[pathlib.Path]:
    root, blocked = _make_t(tmp_path / "t")
    with _Blocked(blocked):
        yield root


# --------------------------------------------------------------------- behaviors 1, 4


@needs_non_root
@pytest.mark.parametrize("floor", range(0, 8))
def test_floor_sweep_json_is_the_oracle(capsys, target_t, floor) -> None:
    doc = _json(capsys, target_t, "--floor", floor)
    for f in doc["findings"]:  # the oracle itself obeys the one floor spelling
        assert f["below_floor"] is (f["confidence"] < floor), f
    ids = _gating_unknown(doc)
    code, out, err = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code", "--floor", floor)
    if ids:
        _assert_refusal(code, out, err, ids)
    else:
        _, plain, _ = _run(capsys, "scan", target_t, "--gaps", GAPS, "--floor", floor)
        assert (code, err) == (0, ""), (code, err)
        assert out == plain, "same document either way"


@needs_non_root
def test_floor_sweep_reaches_both_outcomes_and_a_one_id_step(capsys, target_t) -> None:
    counts = {f: len(_gating_unknown(_json(capsys, target_t, "--floor", f))) for f in range(0, 8)}
    assert any(counts.values()) and not all(counts.values()), counts
    # some floor step drops exactly one id (the confidence-4 UNKNOWN of the spec)
    steps = [counts[f] - counts[f + 1] for f in range(0, 7)]
    assert 1 in steps, counts


@needs_non_root
def test_default_floor_equals_explicit_default(capsys, target_t) -> None:
    doc = _json(capsys, target_t)
    bare = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code")
    explicit = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                    "--floor", doc["confidence_floor"])
    assert bare == explicit
    _assert_refusal(*bare, _gating_unknown(doc))


# --------------------------------------------------------------------- behaviors 1, 2


@needs_non_root
def test_markdown_json_repeat_and_fresh_process_agree(capsys, target_t) -> None:
    ids = _gating_unknown(_json(capsys, target_t))
    md = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code")
    js = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code", "--json")
    again = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code")
    line = _assert_refusal(*md, ids)
    assert js == md == again
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "scan", str(target_t),
         "--gaps", str(GAPS), "--exit-code", "--json"],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert (proc.returncode, proc.stdout) == (2, ""), proc.stderr[-300:]
    assert _last(proc.stderr) == line


@needs_non_root
@pytest.mark.parametrize("variant", ["nested", "two_blocked", "only_blocked"])
def test_target_variants(capsys, tmp_path, variant) -> None:
    root = tmp_path / variant
    root.mkdir()
    blocked: list[pathlib.Path] = []
    if variant == "nested":
        (root / "a.py").write_text("import os\n")
        (root / "pkg" / "deep").mkdir(parents=True)
        blocked.append(root / "pkg" / "deep" / "b.py")
    elif variant == "two_blocked":
        (root / "a.py").write_text("import os\n")
        blocked += [root / "b.py", root / "c.py"]
    else:
        blocked.append(root / "b.py")
    for p in blocked:
        p.write_text("x=1\n")
    with _Blocked(*blocked):
        doc = _json(capsys, root)
        ids = _gating_unknown(doc)
        assert ids, "fixture must stage an above-floor UNKNOWN"
        assert not any(f["verdict"] == "PRESENT" and not f["below_floor"] for f in doc["findings"])
        _assert_refusal(*_run(capsys, "scan", root, "--gaps", GAPS, "--exit-code"), ids)


# --------------------------------------------------------------------- behavior 6


@pytest.mark.parametrize("variant", ["t_readable", "empty_py", "plain_text"])
def test_readable_controls_with_manual_exit_zero(capsys, tmp_path, variant) -> None:
    root = tmp_path / variant
    if variant == "t_readable":
        _make_t(root)
    elif variant == "empty_py":
        root.mkdir()
        (root / "m.py").write_text("")
    else:
        root.mkdir()
        (root / "README.md").write_text("hello\n")
    doc = _json(capsys, root)
    assert _gating_unknown(doc) == [], "control must have no above-floor UNKNOWN"
    above = {f["verdict"] for f in doc["findings"] if not f["below_floor"]}
    present = "PRESENT" in above
    code, out, err = _run(capsys, "scan", root, "--gaps", GAPS, "--exit-code")
    _, plain, _ = _run(capsys, "scan", root, "--gaps", GAPS)
    assert (code, err) == (1 if present else 0, ""), (code, err)
    assert out == plain
    assert CLAUSE not in err


def test_readable_t_has_above_floor_manual(capsys, tmp_path) -> None:
    """Guards the control above: it really carries MANUAL above the floor."""
    root, _ = _make_t(tmp_path / "t")
    doc = _json(capsys, root)
    assert any(f["verdict"] == "MANUAL" and not f["below_floor"] for f in doc["findings"])
    assert _run(capsys, "scan", root, "--gaps", GAPS, "--exit-code")[0] == 0


# --------------------------------------------------------------------- behavior 7


@needs_non_root
def test_clean_baseline_cannot_certify_a_now_unreadable_target(capsys, tmp_path) -> None:
    root, blocked = _make_t(tmp_path / "t")
    code, base, err = _run(capsys, "scan", root, "--gaps", GAPS, "--json")
    assert code == 0 and err == ""
    bfile = tmp_path / "base.json"
    bfile.write_text(base)
    assert _run(capsys, "scan", root, "--gaps", GAPS, "--exit-code", "--baseline", bfile)[0] == 0
    with _Blocked(blocked):
        ids = _gating_unknown(_json(capsys, root))
        for extra in ((), ("--json",)):
            _assert_refusal(*_run(capsys, "scan", root, "--gaps", GAPS, "--exit-code",
                                  "--baseline", bfile, *extra), ids)


@needs_non_root
def test_baseline_with_floor_above_every_unknown_exits_zero(capsys, target_t, tmp_path) -> None:
    doc = _json(capsys, target_t)
    top = max(f["confidence"] for f in doc["findings"] if f["verdict"] == "UNKNOWN")
    bfile = tmp_path / "b.json"
    _, base, _ = _run(capsys, "scan", target_t, "--gaps", GAPS, "--json")
    bfile.write_text(base)
    code, out, err = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                          "--baseline", bfile, "--floor", top + 1)
    assert (code, err) == (0, ""), err[-300:]
    # `--baseline` needs `--exit-code`, so the oracle is the help's promise:
    # the plain document plus exactly one `Baseline:` line
    _, plain, _ = _run(capsys, "scan", target_t, "--gaps", GAPS, "--floor", top + 1)
    extra = [line for line in out.splitlines() if line not in plain.splitlines()]
    assert len(extra) == 1 and extra[0].startswith("Baseline:"), extra
    assert out.endswith("\n") and not out.endswith("\n\n")
    code, out, err = _run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                          "--baseline", bfile, "--floor", top)
    assert code == 2 and out == "" and CLAUSE in _last(err)


# --------------------------------------------------------------------- behavior 5


@pytest.fixture(scope="module")
def target_p(tmp_path_factory) -> Iterator[pathlib.Path]:
    root = tmp_path_factory.mktemp("p") / "p"
    shutil.copytree(REPO / "src", root, ignore=shutil.ignore_patterns("__pycache__"))
    blocked = root / "z.py"
    blocked.write_text("x=1\n")
    with _Blocked(blocked):
        yield root


@needs_non_root
def test_p_present_outranks_unknown_in_both_formats(capsys, target_p) -> None:
    doc = _json(capsys, target_p)
    assert _gating_unknown(doc), "P must carry an above-floor UNKNOWN"
    assert any(f["verdict"] == "PRESENT" and not f["below_floor"] for f in doc["findings"])
    for extra in ((), ("--json",)):
        code, out, err = _run(capsys, "scan", target_p, "--gaps", GAPS, "--exit-code", *extra)
        _, plain, _ = _run(capsys, "scan", target_p, "--gaps", GAPS, *extra)
        assert (code, err) == (1, ""), (code, err[-300:])
        assert out == plain and out.endswith("\n") and not out.endswith("\n\n")


# --------------------------------------------------------------------- behavior 8


@needs_non_root
def test_gap_narrowed_unknown_keeps_the_one_record_refusal(capsys, target_t) -> None:
    ids = _gating_unknown(_json(capsys, target_t))
    gid = ids[0]
    code, out, err = _run(capsys, "scan", target_t, "--gaps", GAPS, "--gap", gid, "--exit-code")
    assert code == 2 and out == ""
    line = _last(err)
    assert line.startswith("Error: ") and CLAUSE not in line, line
    assert GID.findall(line) == [gid], line
