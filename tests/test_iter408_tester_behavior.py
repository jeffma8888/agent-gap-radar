"""Iteration 408 tester behaviors: `scan --prd` skips terminal-status findings.

Black-box: every assertion drives the public CLI (`agent_gap_radar.cli.main`
in-process, or a child interpreter for the pre-change comparison) and reads
only stdout, stderr and the exit code. Registers are tmp dirs holding copies
of the repo's own GAP-041 and GAP-003 records; targets are tmp dirs outside
any git checkout (off-git); nothing touches the network.

"Byte-identical to HEAD" is pinned against the PRE-FEATURE commit `9488358`
-- never HEAD, which becomes the feature once committed -- extracted with
`git archive`; those nodes skip when that commit is absent (a shallow clone).
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re
import subprocess
import sys
import tarfile

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
PRE_FEATURE_SHA = "9488358"

APP = (
    "import openai\n"
    "messages = []\n"
    "def go(x):\n"
    "    messages.append(x)\n"
    "    return openai.chat.completions.create(messages=messages)\n"
)
RUNNER = "import subprocess\ndef step(cmd):\n    return subprocess.run(cmd, timeout=600)\n"


def _run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(args)
        except SystemExit as exc:  # argparse paths
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def _terminal() -> list[str]:
    rc, out, _ = _run(["taxonomy", "--json"])
    assert rc == 0
    return json.loads(out)["terminal"]


def _record(gap_id: str) -> pathlib.Path:
    (path,) = sorted(GAPS.glob(f"{gap_id}-*.json"))
    return path


def _register(root: pathlib.Path, status041: str | None, *, with041: bool = True) -> str:
    """`status041=None` keeps GAP-041's committed status (open)."""
    root.mkdir(parents=True, exist_ok=True)
    src3 = _record("GAP-003")
    (root / src3.name).write_text(src3.read_text(encoding="utf-8"), encoding="utf-8")
    if with041:
        src41 = _record("GAP-041")
        data = json.loads(src41.read_text(encoding="utf-8"))
        if status041 is not None:
            data["status"] = status041
        (root / src41.name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return root.name


def _target(root: pathlib.Path, *, runner: bool) -> str:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text(APP, encoding="utf-8")
    if runner:
        (root / "runner.py").write_text(RUNNER, encoding="utf-8")
    return root.name


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _scan(target: str, reg: str, *extra: str) -> tuple[int, str, str]:
    return _run(["scan", target, "--gaps", reg, *extra])


def _findings(target: str, reg: str) -> dict[str, dict]:
    rc, out, _ = _scan(target, reg, "--json")
    assert rc == 0
    return {f["gap_id"]: f for f in json.loads(out)["findings"]}


# ---- pre-change oracle -----------------------------------------------------


def _pre_feature_src(tmp_path: pathlib.Path) -> pathlib.Path:
    probe = subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"{PRE_FEATURE_SHA}^{{commit}}"],
        capture_output=True,
    )
    if probe.returncode != 0:
        pytest.skip(f"pre-feature commit {PRE_FEATURE_SHA} not available (shallow clone?)")
    tar_path = tmp_path / "pre.tar"
    with tar_path.open("wb") as fh:
        subprocess.run(
            ["git", "-C", str(REPO), "archive", PRE_FEATURE_SHA, "src"], stdout=fh, check=True
        )
    dest = tmp_path / "pre"
    with tarfile.open(tar_path) as tf:
        tf.extractall(dest, filter="data")
    return dest / "src"


_CHILD = (
    "import contextlib, io, json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from agent_gap_radar.cli import main\n"
    "res = []\n"
    "for argv in json.loads(sys.argv[2]):\n"
    "    out, err = io.StringIO(), io.StringIO()\n"
    "    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):\n"
    "        try:\n"
    "            rc = main(argv)\n"
    "        except SystemExit as exc:\n"
    "            rc = exc.code\n"
    "    res.append([rc, out.getvalue(), err.getvalue()])\n"
    "sys.stdout.write(json.dumps(res))\n"
)


def _head(tmp_path: pathlib.Path, argvs: list[list[str]]) -> list[tuple[int, str, str]]:
    src = _pre_feature_src(tmp_path)
    child = subprocess.run(
        [sys.executable, "-c", _CHILD, str(src), json.dumps(argvs)],
        capture_output=True, text=True, check=True, cwd=str(tmp_path),
    )
    return [tuple(r) for r in json.loads(child.stdout)]


def _note(gap_id: str, priority: float, status: str) -> str:
    return (
        f"Note: skipped {gap_id} (priority {priority:.1f}, status {status}) "
        "-- a terminal status; the work is already done."
    )


# ---- fixture premise -------------------------------------------------------


def test_premise_terminal_statuses_are_the_published_partition():
    assert set(_terminal()) == {"addressed", "retired"}


def test_premise_fixture_both_gaps_present_and_head_builds_gap041(ws):
    reg = _register(ws / "reg", "addressed")
    t = _target(ws / "t", runner=True)
    f = _findings(t, reg)
    assert f["GAP-041"]["verdict"] == "PRESENT" and f["GAP-041"]["status"] == "addressed"
    assert f["GAP-003"]["verdict"] == "PRESENT" and f["GAP-003"]["status"] == "open"
    assert f["GAP-041"]["priority"] > f["GAP-003"]["priority"]
    assert f["GAP-041"]["confidence"] == 5 and f["GAP-003"]["confidence"] == 5
    # At the pre-change commit this exact fixture dispatched a build at GAP-041.
    ((rc, out, _),) = _head(ws, [["scan", t, "--gaps", reg, "--prd"]])
    assert rc == 0
    assert json.loads(out)["description"].startswith("GAP-041")


# ---- Behavior 1 + 2 --------------------------------------------------------


@pytest.mark.parametrize("status", ["addressed", "retired"])
def test_b1_terminal_top_finding_is_skipped(ws, status):
    assert status in _terminal()
    reg = _register(ws / "reg", status)
    t = _target(ws / "t", runner=True)
    rc, out, _ = _scan(t, reg, "--prd")
    assert rc == 0
    doc = json.loads(out)
    assert doc["description"].startswith("GAP-003")
    assert "GAP-041" not in out
    assert out.endswith("}\n") and not out.endswith("\n\n")


def test_b1_prd_is_byte_identical_to_head_without_the_terminal_record(ws):
    reg = _register(ws / "reg", "addressed")
    _register(ws / "reg_no041", None, with041=False)
    t = _target(ws / "t", runner=True)
    rc, out, _ = _scan(t, reg, "--prd")
    ((h_rc, h_out, _),) = _head(ws, [["scan", t, "--gaps", "reg_no041", "--prd"]])
    assert h_rc == 0 and h_out
    assert (rc, out) == (h_rc, h_out)


@pytest.mark.parametrize("status", ["addressed", "retired"])
def test_b2_skip_note_is_the_exact_line_and_only_stderr(ws, status):
    reg = _register(ws / "reg", status)
    t = _target(ws / "t", runner=True)
    p = _findings(t, reg)["GAP-041"]["priority"]
    rc, _, err = _scan(t, reg, "--prd")
    assert rc == 0
    assert err == _note("GAP-041", p, status) + "\n"


# ---- Behavior 3 ------------------------------------------------------------


@pytest.mark.parametrize("status", ["addressed", "retired"])
def test_b3_only_terminal_present_is_refused(ws, status):
    reg = _register(ws / "reg", status)
    t = _target(ws / "t", runner=False)
    f = _findings(t, reg)
    assert f["GAP-041"]["verdict"] == "PRESENT"
    assert f["GAP-003"]["verdict"] != "PRESENT"
    rc, out, err = _scan(t, reg, "--prd")
    assert rc == 2
    assert out == ""
    errors = [ln for ln in err.splitlines() if ln.startswith("Error: ")]
    assert len(errors) == 1, err
    (line,) = errors
    assert "GAP-041" in line and status in line and "terminal status" in line
    assert "radar prd --gap" not in err
    assert err.endswith("\n") and not err.endswith("\n\n")


# ---- Behavior 4 ------------------------------------------------------------


def test_b4_below_floor_refusal_names_only_citable_findings(ws):
    reg = _register(ws / "reg", "addressed")
    t = _target(ws / "t", runner=True)
    rc, out, err = _scan(t, reg, "--prd", "--floor", "6")
    assert rc == 2
    assert out == ""
    lines = err.splitlines()
    errors = [ln for ln in lines if ln.startswith("Error: ")]
    assert len(errors) == 1, err
    (line,) = errors
    assert line.startswith("Error: no PRESENT finding clears the confidence floor")
    assert "GAP-003" in line
    assert "radar prd --gap GAP-003" in line
    # The terminal id is never suggested as a build target anywhere.
    assert "radar prd --gap GAP-041" not in err
    # It is still accounted for: by the behavior-2 Note line or in the Error line.
    p = _findings(t, reg)["GAP-041"]["priority"]
    note = _note("GAP-041", p, "addressed")
    assert note in lines or "GAP-041" in line
    if note in lines:
        # A Note line names it, so the refusal's citable listing must not.
        assert "GAP-041" not in line
        assert lines.index(note) < lines.index(line)


# ---- Behavior 5 ------------------------------------------------------------


def test_b5_exit_code_gate_still_counts_an_only_terminal_finding(ws):
    reg = _register(ws / "reg", "addressed")
    t = _target(ws / "t", runner=False)
    rc, out, err = _scan(t, reg, "--exit-code")
    assert rc == 1
    assert err == ""
    ((h_rc, h_out, h_err),) = _head(ws, [["scan", t, "--gaps", reg, "--exit-code"]])
    assert (rc, out, err) == (h_rc, h_out, h_err)


# ---- Behavior 6 + 7 --------------------------------------------------------


@pytest.mark.parametrize("runner", [True, False], ids=["both", "only041"])
def test_b6_scan_documents_byte_identical_to_head(ws, runner):
    reg = _register(ws / "reg", "addressed")
    t = _target(ws / "t", runner=runner)
    argvs = [
        ["scan", t, "--gaps", reg],
        ["scan", t, "--gaps", reg, "--json"],
        ["scan", t, "--gaps", reg, "--exit-code"],
        ["scan", t, "--gaps", reg, "--json", "--floor", "6"],
    ]
    new = [_run(a) for a in argvs]
    assert new == _head(ws, argvs)
    # Selection rule, not display filter: the terminal record is still shown.
    assert "GAP-041" in new[0][1]
    assert _findings(t, reg)["GAP-041"]["status"] == "addressed"
    for _, out, _ in new:
        assert out.endswith("\n") and not out.endswith("\n\n")


@pytest.mark.parametrize("runner", [True, False], ids=["both", "only041"])
def test_b7_register_without_terminal_records_unchanged_on_prd(ws, runner):
    reg = _register(ws / "reg", None)
    t = _target(ws / "t", runner=runner)
    assert _findings(t, reg)["GAP-041"]["status"] not in _terminal()
    argvs = [
        ["scan", t, "--gaps", reg, "--prd"],
        ["scan", t, "--gaps", reg, "--prd", "--floor", "6"],
        ["scan", t, "--gaps", reg, "--prd", "--floor", "1"],
    ]
    new = [_run(a) for a in argvs]
    assert new == _head(ws, argvs)
    assert new[0][0] == 0 and json.loads(new[0][1])["description"].startswith("GAP-041")


# ---- Behavior 8 ------------------------------------------------------------


def _literal_count(text: str) -> int:
    return len(re.findall(r"""["'](?:addressed|retired)["']""", text))


def test_b8_scan_py_adds_no_status_literal(tmp_path):
    src = _pre_feature_src(tmp_path)
    rel = pathlib.Path("agent_gap_radar") / "scan.py"
    before = (src / rel).read_text(encoding="utf-8")
    now = (REPO / "src" / rel).read_text(encoding="utf-8")
    assert _literal_count(now) <= _literal_count(before)


def test_b8_literal_counter_sees_a_spelled_status():
    assert _literal_count('if s in ("addressed", \'retired\'):') == 2
    assert _literal_count("terminal_statuses()") == 0


# ---- Behavior 9 ------------------------------------------------------------


def _contract() -> str:
    return (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")


def test_b9_selection_door_paragraph_names_scan_prd():
    text = re.sub(r"\s+", " ", _contract())
    m = re.search(r"It is published verbatim AND acted on, at the SELECTION doors? only -- (.{0,200})", text)
    assert m, "selection-door paragraph not found"
    assert "`radar scan --prd`" in m.group(1) or "`scan --prd`" in m.group(1)
    assert "--exit-code" in m.group(1)


def test_b9_contract_says_scan_prd_skips_terminal_and_gate_still_counts():
    text = re.sub(r"\s+", " ", _contract())
    assert re.search(r"`--prd`[^|]{0,600}skips, at selection, every finding whose gap carries a terminal status", text) \
        or re.search(r"scan --prd`? skips[^.]{0,200}terminal", text), "no skip statement"
    assert re.search(r"`--exit-code` still counts terminal findings", text)
