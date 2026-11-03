"""Iteration 384: `scan --exit-code` refuses a `--floor` above the ladder's ceiling.

`scoring.confidence` is derived on 0..CONFIDENCE_MAX, so a floor above it is cleared by
no finding and `--exit-code` would answer `0` for every target -- an off switch spelled
as a number. Beside `--exit-code` (and only there) such a floor is now exit 2 with an
empty stdout, decided before any directory is read. Every other surface keeps accepting
any floor, and a floor of CONFIDENCE_MAX or less verdicts exactly as before.
"""

from __future__ import annotations

import pathlib

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scoring import CONFIDENCE_MAX, confidence
from test_iter02_behavior import _record, _target, _write_register

REPO = pathlib.Path(__file__).resolve().parents[1]
LIVE = REPO / "gaps"
PHRASE = "exceeds the highest confidence the evidence ladder can derive"

#: One PRESENT finding at confidence 5 (a first-party-field citation): the strongest a
#: record can be, so `--floor 5` must still turn the gate red.
TOP = _record("GAP-841", 4, 4, 4, ("first-party-field",), "CHK-841")


def _refusal(floor: int) -> str:
    """The exact last stderr line behavior 1 names, built from the constant."""
    return (f"Error: --floor {floor} {PHRASE} ({CONFIDENCE_MAX}), so --exit-code could "
            f"never fail; use a floor of {CONFIDENCE_MAX} or less")


def _run(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _last(err: str) -> str:
    return [line for line in err.splitlines() if line.strip()][-1]


@pytest.fixture(scope="module")
def bed(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pathlib.Path]:
    root = tmp_path_factory.mktemp("iter384")
    return {"reg": _write_register(root / "reg", [TOP]),
            "hit": _target(root / "hit"),
            "clean": _target(root / "clean", body="clean")}


def _assert_refused(result: tuple[int, str, str], floor: int) -> None:
    code, out, err = result
    assert (code, out) == (2, ""), (code, err[-300:])
    assert _last(err) == _refusal(floor)


# --- behavior 1 ------------------------------------------------------------

@pytest.mark.parametrize("floor", [6, 7, 99])
@pytest.mark.parametrize("target", ["hit", "clean"])
def test_b1_unclearable_floor_is_refused(capsys, bed, floor, target) -> None:
    _assert_refused(_run(capsys, "scan", bed[target], "--gaps", bed["reg"],
                         "--exit-code", "--floor", floor), floor)


# --- behavior 2 ------------------------------------------------------------

def test_b2_refused_before_any_directory_is_read(capsys, bed, tmp_path) -> None:
    missing = tmp_path / "nope"
    _assert_refused(_run(capsys, "scan", bed["hit"], "--gaps", missing,
                         "--exit-code", "--floor", 7), 7)
    _assert_refused(_run(capsys, "scan", missing, "--gaps", bed["reg"],
                         "--exit-code", "--floor", 7), 7)


# --- behavior 3 ------------------------------------------------------------

@pytest.mark.parametrize("extra", [("--gap", "GAP-841"), ("--layer", "orchestration"),
                                   ("--json",), ("--baseline", "BASELINE")],
                         ids=["gap", "layer", "json", "baseline"])
def test_b3_composes_with_every_exit_code_modifier(capsys, bed, tmp_path, extra) -> None:
    extra = tuple(str(tmp_path / "b.json") if e == "BASELINE" else e for e in extra)
    _assert_refused(_run(capsys, "scan", bed["hit"], "--gaps", bed["reg"],
                         "--exit-code", *extra, "--floor", 6), 6)


# --- behavior 4 ------------------------------------------------------------

@pytest.mark.parametrize("floor", [5, 2, 0, -1])
def test_b4_clearable_floors_verdict_as_before(capsys, bed, floor) -> None:
    _, doc, _ = _run(capsys, "scan", bed["hit"], "--gaps", bed["reg"], "--floor", floor)
    assert _run(capsys, "scan", bed["hit"], "--gaps", bed["reg"], "--exit-code",
                "--floor", floor) == (1, doc, "")
    _, clean, _ = _run(capsys, "scan", bed["clean"], "--gaps", bed["reg"], "--floor", floor)
    assert _run(capsys, "scan", bed["clean"], "--gaps", bed["reg"], "--exit-code",
                "--floor", floor) == (0, clean, "")


# --- behavior 5 ------------------------------------------------------------

@pytest.mark.parametrize("argv", [("scan", "HIT", "--floor", "6"),
                                  ("scan", "HIT", "--json", "--floor", "6"),
                                  ("list", "REG", "--floor", "99"),
                                  ("report", "REG", "--floor", "99")],
                         ids=["scan", "scan-json", "list", "report"])
def test_b5_floors_without_exit_code_are_accepted(capsys, bed, argv) -> None:
    sub = {"HIT": str(bed["hit"]), "REG": str(bed["reg"])}
    argv = [sub.get(a, a) for a in argv]
    if argv[0] == "scan":
        argv += ["--gaps", str(bed["reg"])]
    code, out, err = _run(capsys, *argv)
    assert (code, err) == (0, "") and out.endswith("\n") and not out.endswith("\n\n")
    assert PHRASE not in out


def test_b5_prd_keeps_its_own_refusal(capsys, bed) -> None:
    code, out, err = _run(capsys, "scan", bed["hit"], "--gaps", bed["reg"], "--prd",
                          "--floor", 6)
    assert (code, out) == (2, "")
    assert _last(err).startswith("Error: no PRESENT finding clears the confidence floor 6")
    assert PHRASE not in err


# --- behavior 6 ------------------------------------------------------------

def test_b6_baseline_without_exit_code_keeps_its_refusal(capsys, bed, tmp_path) -> None:
    code, out, err = _run(capsys, "scan", bed["hit"], "--gaps", bed["reg"], "--baseline",
                          tmp_path / "b.json", "--floor", 9)
    assert (code, out) == (2, "")
    assert _last(err).startswith("Error: --baseline requires --exit-code")
    assert PHRASE not in err


# --- behavior 7 ------------------------------------------------------------

def test_b7_the_ceiling_is_the_constant_the_ladder_obeys() -> None:
    assert CONFIDENCE_MAX == 5
    assert max(confidence(g) for g in load_all(LIVE)) <= CONFIDENCE_MAX


def test_b7_the_refusal_reads_the_constant(capsys, bed, monkeypatch) -> None:
    """Raising the ceiling moves the refusal with it: there is no second literal."""
    monkeypatch.setattr("agent_gap_radar.scoring.CONFIDENCE_MAX", 6)
    code, _, err = _run(capsys, "scan", bed["hit"], "--gaps", bed["reg"], "--exit-code",
                        "--floor", 6)
    assert code == 0 and err == ""
    code, _, err = _run(capsys, "scan", bed["hit"], "--gaps", bed["reg"], "--exit-code",
                        "--floor", 7)
    assert code == 2 and _last(err).endswith("(6), so --exit-code could never fail; "
                                             "use a floor of 6 or less")


# --- behavior 8 ------------------------------------------------------------

def test_b8_contract_states_the_refusal_in_both_rows() -> None:
    rows = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8").splitlines()
    scan_row = [r for r in rows if r.startswith("| `radar scan <target>")]
    exit_two = [r for r in rows if r.startswith("| `2` |")]
    assert len(scan_row) == 1 and len(exit_two) == 1
    assert PHRASE in scan_row[0] and PHRASE in exit_two[0]
