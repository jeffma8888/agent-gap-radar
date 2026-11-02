"""Iteration 380 behaviors: a whole-register `scan --exit-code` refuses on UNKNOWN.

`gate_verdict` reads only PRESENT, so a scan whose checks could not read the files
they needed used to exit `0` -- "no above-floor PRESENT gap" -- on a target where
almost nothing was answered. The contract says a gate must never treat UNKNOWN as a
pass, so now an above-floor UNKNOWN makes `--exit-code` exit 2 with an `Error:`
line naming the ids, unless a known above-floor PRESENT (1) already decided it.

Fixture T: `a.py` + an unreadable `b.py`. Fixture P: a copy of `src/` plus an
unreadable `z.py` (it has PRESENT findings AND UNKNOWN ones). Every chmod node skips
under root (root reads anything) and restores the mode in a fixture teardown.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
from collections.abc import Iterator

import pytest
from _selfscan import selfscan, selfscan_run_cache  # noqa: F401  (autouse fixture)

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT_DOC = REPO / "docs" / "CONSUMER_CONTRACT.md"
CLAUSE = "reached no verdict (UNKNOWN)"

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root reads a chmod 000 file, so unreadable cannot be staged",
)


def run(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    """`(exit code, stdout, stderr)` of one in-process CLI call."""
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def last_line(err: str) -> str:
    """stderr's last non-empty line -- the one the contract promises begins `Error: `."""
    return [line for line in err.splitlines() if line.strip()][-1]


def unknown_ids(document: str, floor_clears: int | None = None) -> list[str]:
    """Ids of above-floor UNKNOWN findings in `findings` order, read from `--json`."""
    findings = json.loads(document)["findings"]
    return [f["gap_id"] for f in findings if f["verdict"] == "UNKNOWN"
            and (not f["below_floor"] if floor_clears is None
                 else f["confidence"] >= floor_clears)]


@pytest.fixture
def target_t(tmp_path: pathlib.Path) -> Iterator[pathlib.Path]:
    """Fixture T: one readable and one chmod-000 python file."""
    root = tmp_path / "t"
    root.mkdir()
    (root / "a.py").write_text("import os\n")
    blocked = root / "b.py"
    blocked.write_text("x=1\n")
    blocked.chmod(0)
    try:
        yield root
    finally:
        blocked.chmod(0o644)


@pytest.fixture(scope="module")
def target_p(tmp_path_factory: pytest.TempPathFactory) -> Iterator[pathlib.Path]:
    """Fixture P: the repo's `src/` plus one chmod-000 file -- PRESENT and UNKNOWN."""
    root = tmp_path_factory.mktemp("p") / "p"
    shutil.copytree(REPO / "src", root, ignore=shutil.ignore_patterns("__pycache__"))
    blocked = root / "z.py"
    blocked.write_text("x=1\n")
    blocked.chmod(0)
    try:
        yield root
    finally:
        blocked.chmod(0o644)


@needs_non_root
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["markdown", "json"])
def test_b1_b2_whole_register_unknown_refuses(capsys, target_t, extra) -> None:
    _, doc, _ = run(capsys, "scan", target_t, "--gaps", GAPS, "--json")
    expected = unknown_ids(doc)
    assert expected, "fixture T must produce above-floor UNKNOWN findings"
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code", *extra)
    assert (code, out) == (2, "")
    line = last_line(err)
    assert line.startswith("Error: ")
    assert CLAUSE in line
    # Named in SCAN order (register id order), the order `unanswered` uses too;
    # `--json`'s `findings` array is ranked, so compare as the sorted id set.
    assert ", ".join(sorted(expected)) in line
    assert f"{len(expected)} finding(s)" in line


@needs_non_root
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["markdown", "json"])
def test_b3_documents_unchanged_without_exit_code(capsys, target_t, extra) -> None:
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, *extra)
    assert (code, err) == (0, "")
    assert out.endswith("\n") and not out.endswith("\n\n")
    # --floor 6 clears no UNKNOWN, so --exit-code verdicts and must not alter the bytes.
    gated = run(capsys, "scan", target_t, "--gaps", GAPS, *extra, "--exit-code",
                "--floor", "6")
    plain_at_6 = run(capsys, "scan", target_t, "--gaps", GAPS, *extra, "--floor", "6")
    assert gated[1] == plain_at_6[1]


@needs_non_root
def test_b4_floor_rule(capsys, target_t) -> None:
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                         "--floor", "6")
    assert code == 0 and out and err == ""
    _, doc, _ = run(capsys, "scan", target_t, "--gaps", GAPS, "--json")
    lines = {}
    for floor in (4, 5):
        code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                             "--floor", floor)
        assert (code, out) == (2, "")
        ids = unknown_ids(doc, floor_clears=floor)
        assert f"{len(ids)} finding(s)" in last_line(err)
        named = last_line(err).split("(UNKNOWN): ", 1)[1].split("; ", 1)[0].split(", ")
        assert named == sorted(ids)
        lines[floor] = named
    assert len(lines[5]) == len(lines[4]) - 1


@needs_non_root
def test_b5_present_outranks_unknown(capsys, target_p) -> None:
    _, doc, _ = run(capsys, "scan", target_p, "--gaps", GAPS, "--json")
    assert unknown_ids(doc), "fixture P must carry above-floor UNKNOWN too"
    code, out, err = run(capsys, "scan", target_p, "--gaps", GAPS, "--exit-code")
    assert (code, err) == (1, "")
    assert out == run(capsys, "scan", target_p, "--gaps", GAPS)[1]


def test_b6_readable_control(capsys, tmp_path) -> None:
    (tmp_path / "a.py").write_text("import os\n")
    (tmp_path / "b.py").write_text("x=1\n")
    code, _, err = run(capsys, "scan", tmp_path, "--gaps", GAPS, "--exit-code")
    assert (code, err) == (0, "")


def test_b6_self_scan_keeps_exit_and_bytes() -> None:
    code, out, err = selfscan(("--gaps", "gaps", "--exit-code"))
    assert (code, err) == (1, "")
    assert out == selfscan(("--gaps", "gaps"))[1]


@needs_non_root
def test_b7_baseline_cannot_certify_unknown_on_t(capsys, target_t, tmp_path) -> None:
    _, doc, _ = run(capsys, "scan", target_t, "--gaps", GAPS, "--json")
    baseline = tmp_path / "b.json"
    baseline.write_text(doc)
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                         "--baseline", baseline)
    assert (code, out) == (2, "")
    assert last_line(err).startswith("Error: ") and CLAUSE in last_line(err)


@needs_non_root
def test_b7_baseline_carrying_every_present_on_p(capsys, target_p, tmp_path) -> None:
    _, doc, _ = run(capsys, "scan", target_p, "--gaps", GAPS, "--json")
    baseline = tmp_path / "p.json"
    baseline.write_text(doc)
    code, out, err = run(capsys, "scan", target_p, "--gaps", GAPS, "--exit-code",
                         "--baseline", baseline)
    assert (code, out) == (2, "")
    assert CLAUSE in last_line(err)


@needs_non_root
def test_b7_baseline_refusals_fire_first(capsys, target_t, tmp_path) -> None:
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"target_name": "elsewhere", "findings": []}))
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                         "--baseline", other)
    assert (code, out) == (2, "")
    assert last_line(err).startswith("Error: baseline target mismatch")
    junk = tmp_path / "junk.json"
    junk.write_text("not json")
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--exit-code",
                         "--baseline", junk)
    assert (code, out) == (2, "")
    assert last_line(err).startswith("Error: not a scan document")


@needs_non_root
def test_b8_existing_refusals_keep_their_text(capsys, target_t) -> None:
    _, doc, _ = run(capsys, "scan", target_t, "--gaps", GAPS, "--json")
    one = unknown_ids(doc)[0]
    code, out, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--gap", one,
                         "--exit-code")
    assert (code, out) == (2, "")
    assert last_line(err).startswith(f"Error: scan reached no automated verdict for {one}")
    assert CLAUSE not in err
    code, _, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--layer", "nope",
                       "--exit-code")
    assert code == 2 and CLAUSE not in err
    code, _, err = run(capsys, "scan", target_t, "--gaps", GAPS, "--baseline", "x.json")
    assert code == 2 and CLAUSE not in err and "--exit-code" in last_line(err)


def test_b9_contract_names_the_refusal() -> None:
    text = CONTRACT_DOC.read_text()
    scan_row = next(line for line in text.splitlines() if line.startswith("| `radar scan "))
    assert "0 when it has none" in scan_row
    assert "`MANUAL` and no-check records do not trigger it" in scan_row
    exit2_row = next(line for line in text.splitlines() if line.startswith("| `2` |"))
    assert CLAUSE in exit2_row
