"""Iteration 424 behaviors: an unreadable ``scan --baseline`` names the real defect.

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-8; no test was written from the implementation source,
the engineer's or reviewer's notes, or any diff.  "Byte-identical to HEAD" is
encoded as FIXED LITERAL sentences (ship hazard H1: no ``git show HEAD``
baseline, no sha, no file:line locator).  No wall-clock bound, no extras.

The CLI is driven in a CHILD interpreter so rc, stdout and stderr are observed
end to end and a crash (traceback, rc 1) cannot hide.
"""

from __future__ import annotations

import errno
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"
LONG = "a" * 300 + ".json"
CHILD = (
    "import sys\n"
    "from agent_gap_radar.cli import main\n"
    "rc = main(sys.argv[1:])\n"
    "sys.exit(rc or 0)\n"
)
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


def _run(args: list[str], cwd: pathlib.Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _clean_refusal(rc: int, out: str, err: str) -> None:
    assert rc == 2, (rc, out, err)
    assert out == "", out
    assert err.startswith("Error: "), err
    assert err.endswith("\n") and err.count("\n") == 1, repr(err)
    assert "Traceback" not in err, err
    assert "Errno" not in err, err


@pytest.fixture
def work(tmp_path):
    """cwd with a small target tree ``tgt`` and a valid baseline ``B.json``."""
    shutil.copytree(REPO / "docs", tmp_path / "tgt")
    rc, out, err = _run(["scan", "--json", "--gaps", str(GAPS), "tgt"], tmp_path)
    assert rc == 0, err
    assert '"findings"' in out and '"target_name"' in out, out[:200]
    (tmp_path / "B.json").write_text(out, encoding="utf-8")
    return tmp_path


def _gate(cwd: pathlib.Path, baseline: str, *extra: str) -> tuple[int, str, str]:
    return _run(
        ["scan", "--gaps", str(GAPS), "tgt", "--exit-code", "--baseline", baseline, *extra],
        cwd,
    )


def _prd_after(cwd: pathlib.Path, after: str) -> tuple[int, str, str]:
    return _run(["prd", str(REPO), "--after", after], cwd)


def _unreadable(cwd: pathlib.Path) -> str:
    x = cwd / "locked.json"
    x.write_bytes((cwd / "B.json").read_bytes())
    x.chmod(0)
    return "locked.json"


# ---------------------------------------------------------------- behavior 1


@pytest.mark.skipif(IS_ROOT, reason="root ignores mode 000")
def test_b1_permission_denied_baseline_is_cannot_read(work):
    x = _unreadable(work)
    try:
        rc, out, err = _gate(work, x)
    finally:
        (work / x).chmod(0o600)
    _clean_refusal(rc, out, err)
    assert err == f"Error: cannot read the file (Permission denied): {x}\n", err
    assert "not a scan document" not in err, err


# ---------------------------------------------------------------- behavior 2


def test_b2_overlong_baseline_name_is_cannot_read_with_strerror(work):
    rc, out, err = _gate(work, LONG)
    _clean_refusal(rc, out, err)
    assert err.startswith("Error: cannot read the file ("), err
    assert err.endswith("): " + LONG + "\n"), err
    reason = err[len("Error: cannot read the file (") : -len("): " + LONG + "\n")]
    assert reason == os.strerror(errno.ENAMETOOLONG), reason
    assert "not a scan document" not in err, err


# ---------------------------------------------------------------- behavior 3


def _not_a_file_cases(cwd: pathlib.Path) -> list[str]:
    (cwd / "adir").mkdir()
    (cwd / "loop.json").symlink_to("loop.json")
    names = ["missing.json", "adir", "loop.json"]
    if hasattr(os, "mkfifo"):
        os.mkfifo(cwd / "fifo.json")
        names.append("fifo.json")
    return names


def test_b3_not_a_file_cases_unchanged(work):
    for x in _not_a_file_cases(work):
        rc, out, err = _gate(work, x)
        _clean_refusal(rc, out, err)
        assert err == f"Error: not a file: {x}\n", (x, err)


# ---------------------------------------------------------------- behavior 4


def _not_a_scan_document_cases(cwd: pathlib.Path) -> list[str]:
    import json

    (cwd / "empty.json").write_text("", encoding="utf-8")
    (cwd / "list.json").write_text("[]\n", encoding="utf-8")
    doc = json.loads((cwd / "B.json").read_text(encoding="utf-8"))
    doc.pop("findings")
    (cwd / "nofind.json").write_text(json.dumps(doc), encoding="utf-8")
    text = (cwd / "B.json").read_text(encoding="utf-8")
    assert text.startswith("{")
    (cwd / "dup.json").write_text('{"target_name": "tgt",' + text[1:], encoding="utf-8")
    return ["empty.json", "list.json", "nofind.json", "dup.json"]


def test_b4_not_a_scan_document_cases_unchanged(work):
    for x in _not_a_scan_document_cases(work):
        rc, out, err = _gate(work, x)
        _clean_refusal(rc, out, err)
        assert err == f"Error: not a scan document: {x}\n", (x, err)


# ---------------------------------------------------------------- behavior 5


def test_b5_readable_baseline_still_gates(work):
    rc0, plain, err0 = _run(["scan", "--gaps", str(GAPS), "tgt", "--exit-code"], work)
    rc, out, err = _gate(work, "B.json")
    assert (rc, err) == (rc0, err0) == (0, ""), (rc, err, rc0, err0)
    added = [ln for ln in out.splitlines() if ln not in plain.splitlines()]
    assert len(added) == 1 and added[0].startswith("Baseline: B.json -- carried PRESENT: "), added
    lines = out.splitlines()
    i = lines.index(added[0])
    assert lines[i - 1].startswith("Gaps with no check yet: "), lines[i - 1]
    assert lines[:i] + lines[i + 1 :] == plain.splitlines()
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b5_target_mismatch_still_refused(work):
    rc, out, err = _gate(work, "B.json", "--name", "other")
    _clean_refusal(rc, out, err)
    assert err.startswith("Error: baseline target mismatch: "), err


def test_b5_zero_records_refusal_fires_before_baseline_read(work):
    x = _unreadable(work) if not IS_ROOT else "missing.json"
    try:
        rc, out, err = _gate(work, x, "--match", "zzqq-no-record-matches-this")
    finally:
        if (work / x).exists():
            (work / x).chmod(0o600)
    _clean_refusal(rc, out, err)
    assert err.startswith("Error: scan applied 0 register records"), err
    assert "cannot read the file" not in err and "not a file" not in err, err


# ---------------------------------------------------------------- behavior 6


def test_b6_prd_after_sentences_unchanged(work):
    _not_a_file_cases(work)
    (work / "empty.json").write_text("", encoding="utf-8")
    (work / "list.json").write_text("[]\n", encoding="utf-8")
    exact = {
        "missing.json": "cannot read the file (No such file or directory)",
        "adir": "cannot read the file (not a regular file)",
        LONG: f"cannot read the file ({os.strerror(errno.ENAMETOOLONG)})",
        "list.json": "the top level is not a JSON object",
    }
    if hasattr(os, "mkfifo"):
        exact["fifo.json"] = "cannot read the file (not a regular file)"
    if not IS_ROOT:
        exact[_unreadable(work)] = "cannot read the file (Permission denied)"
    try:
        for x, tail in exact.items():
            rc, out, err = _prd_after(work, x)
            _clean_refusal(rc, out, err)
            assert err == f"Error: --after {x}: {tail}\n", (x, err)
        rc, out, err = _prd_after(work, "empty.json")
        _clean_refusal(rc, out, err)
        assert err.startswith("Error: --after empty.json: not valid JSON ("), err
    finally:
        if (work / "locked.json").exists():
            (work / "locked.json").chmod(0o600)


# ---------------------------------------------------------------- behavior 7


def _stable_prefix(err: str, lead: str) -> str:
    assert err.startswith(lead), (lead, err)
    body = err[len(lead) :].rstrip("\n")
    cuts = [i for i in (body.find("("), body.find(": ")) if i >= 0]
    return (body[: min(cuts)] if cuts else body).strip()


def _contract_row(verb: str) -> str:
    rows = [
        ln
        for ln in CONTRACT.read_text(encoding="utf-8").splitlines()
        if ln.startswith(f"| `radar {verb} ")
    ]
    assert len(rows) == 1, (verb, len(rows))
    return rows[0]


def _live_scan_prefixes(work: pathlib.Path) -> set[str]:
    xs = [LONG, *_not_a_file_cases(work), *_not_a_scan_document_cases(work)]
    if not IS_ROOT:
        xs.append(_unreadable(work))
    found = set()
    try:
        for x in xs:
            rc, out, err = _gate(work, x)
            _clean_refusal(rc, out, err)
            found.add(_stable_prefix(err, "Error: "))
    finally:
        if (work / "locked.json").exists():
            (work / "locked.json").chmod(0o600)
    rc, out, err = _gate(work, "B.json", "--name", "other")
    _clean_refusal(rc, out, err)
    found.add(_stable_prefix(err, "Error: "))
    return found


def _live_prd_prefixes(work: pathlib.Path) -> set[str]:
    xs = [LONG, *_not_a_file_cases(work)]
    (work / "empty.json").write_text("", encoding="utf-8")
    (work / "list.json").write_text("[]\n", encoding="utf-8")
    xs += ["empty.json", "list.json"]
    if not IS_ROOT:
        xs.append(_unreadable(work))
    found = set()
    try:
        for x in xs:
            rc, out, err = _prd_after(work, x)
            _clean_refusal(rc, out, err)
            found.add(_stable_prefix(err, f"Error: --after {x}: "))
    finally:
        if (work / "locked.json").exists():
            (work / "locked.json").chmod(0o600)
    return found


def test_b7_scan_contract_cell_names_every_live_baseline_sentence(work):
    found = _live_scan_prefixes(work)
    # Anti-vacuity: the live derivation sees the four sentences the spec lists.
    assert {
        "not a file",
        "cannot read the file",
        "not a scan document",
        "baseline target mismatch",
    } <= found, found
    row = _contract_row("scan")
    missing = sorted(p for p in found if p not in row)
    assert missing == [], missing


def test_b7_prd_contract_cell_names_every_live_after_sentence(work):
    found = _live_prd_prefixes(work)
    assert {
        "cannot read the file",
        "not valid JSON",
        "the top level is not a JSON object",
    } <= found, found
    row = _contract_row("prd")
    missing = sorted(p for p in found if p not in row)
    assert missing == [], missing


# ---------------------------------------------------------------- behavior 8


def test_b8_scan_cell_maps_cause_to_sentence():
    row = _contract_row("scan")
    cannot = "`Error: cannot read the file (<reason>): <path>`"
    notdoc = "`Error: not a scan document: <path>`"
    assert row.count(cannot) == 1, row.count(cannot)
    assert row.count(notdoc) == 1, row.count(notdoc)
    i, j = row.index(cannot), row.index(notdoc)
    assert i < j
    before_cannot = row[max(0, i - 300) : i].lower()
    assert "permission" in before_cannot, before_cannot
    assert "over-long name" in before_cannot or "overlong name" in before_cannot
    notdoc_clause = row[i + len(cannot) : j]
    low = notdoc_clause.lower()
    assert "only" in notdoc_clause.lower(), notdoc_clause
    for needle in ("not json", "not an object", "target_name", "findings", "repeated key"):
        assert needle in low, (needle, notdoc_clause)
    # The OS-refusal causes are not attributed to "not a scan document".
    assert "permission" not in low and "over-long" not in low, notdoc_clause
