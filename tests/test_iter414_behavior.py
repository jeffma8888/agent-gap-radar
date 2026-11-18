"""Iteration 414 behaviors: read doors refuse non-regular files.

A register record path, or a `radar prd --after FILE`, that EXISTS but is not
a regular file (FIFO, directory, character device) is refused at exit 2 with
an `Error: ` line instead of being read -- before this iteration a FIFO named
`GAP-*.json` made `validate`/`list` block forever and `--after /dev/zero`
never returned.

Black-box: every call is a child interpreter driving the public CLI entry
point (`agent_gap_radar.cli.main`) with `timeout=10`, so a regression FAILS
(TimeoutExpired) instead of hanging the suite. Registers are tmp dirs holding
copies of committed records. No commit sha, no line number, no wall-clock
ratio, no network, no absolute machine path.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
TIMEOUT = 10
NOT_REG = "unreadable/invalid JSON: not a regular file"

_DRIVER = "import sys\nfrom agent_gap_radar.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"

needs_fifo = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFOs only")


def _env(src: pathlib.Path = REPO / "src") -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(src), env.get("PYTHONPATH", "")])
    return env


def _radar(args: list[str], cwd: pathlib.Path, src: pathlib.Path = REPO / "src"):
    p = subprocess.run(
        [sys.executable, "-c", _DRIVER, *args],
        capture_output=True, cwd=cwd, env=_env(src), timeout=TIMEOUT,
    )
    return p.returncode, p.stdout.decode("utf-8"), p.stderr.decode("utf-8")


def _src(gap_id: str) -> pathlib.Path:
    (path,) = sorted(GAPS.glob(f"{gap_id}-*.json"))
    return path


@pytest.fixture
def ws(tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    src = _src("GAP-003")
    (reg / src.name).write_bytes(src.read_bytes())
    return tmp_path


def _lines(err: str) -> list[str]:
    return err.splitlines()


# ---- b1-b3: a FIFO record in the register -----------------------------------


@needs_fifo
def test_b1_validate_refuses_fifo_record(ws):
    os.mkfifo(ws / "reg" / "GAP-999-x.json")
    rc, out, err = _radar(["validate", "reg"], ws)
    assert rc == 2
    assert out == ""
    assert _lines(err) == [f"Error: GAP-999-x.json: {NOT_REG}"]


@needs_fifo
def test_b2_validate_json_reports_invalid_json_problem(ws):
    os.mkfifo(ws / "reg" / "GAP-999-x.json")
    rc, out, err = _radar(["validate", "reg", "--json"], ws)
    assert rc == 2
    doc = json.loads(out)
    assert {"kind": "invalid-json", "file": "GAP-999-x.json", "loc": None, "msg": NOT_REG} in [
        {k: e.get(k) for k in ("kind", "file", "loc", "msg")} for e in doc["errors"]
    ]
    assert doc["valid"] is False
    assert doc["records"] == 1
    assert f"Error: GAP-999-x.json: {NOT_REG}" in _lines(err)


@needs_fifo
def test_b3_list_refuses_fifo_record(ws):
    os.mkfifo(ws / "reg" / "GAP-999-x.json")
    rc, out, err = _radar(["list", "reg"], ws)
    assert rc == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert f"GAP-999-x.json: {NOT_REG}" in err


# ---- b4: a directory record; b5: a symlink is followed -----------------------


def test_b4_directory_record_refused_without_path_leak(ws):
    (ws / "reg" / "GAP-998-d.json").mkdir()
    rc, out, err = _radar(["validate", "reg"], ws)
    assert rc == 2
    assert out == ""
    assert _lines(err) == [f"Error: GAP-998-d.json: {NOT_REG}"]
    assert str(ws) not in err
    assert "Errno" not in err


def test_b5_symlink_to_regular_record_is_read(ws):
    target = ws / "elsewhere" / _src("GAP-041").name
    target.parent.mkdir()
    target.write_bytes(_src("GAP-041").read_bytes())
    link = ws / "reg" / "GAP-997-link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    rc, out, err = _radar(["validate", "reg"], ws)
    assert rc == 0, err
    assert "not a regular file" not in err
    # premise: the link IS read -- a broken target makes it fail
    target.write_text("{not json", encoding="utf-8")
    rc2, _, err2 = _radar(["validate", "reg"], ws)
    assert rc2 == 2
    assert "GAP-997-link.json" in err2 and "not a regular file" not in err2


# ---- b6-b9: prd --after with non-regular / missing files ----------------------


def _after_refusal(spelling: str, why: str = "not a regular file") -> list[str]:
    return [f"Error: --after {spelling}: cannot read the file ({why})"]


@needs_fifo
def test_b6_prd_after_fifo_refused(ws):
    os.mkfifo(ws / "done.fifo")
    rc, out, err = _radar(["prd", str(GAPS), "--after", "done.fifo"], ws)
    assert rc == 2
    assert out == ""
    assert _lines(err) == _after_refusal("done.fifo")


@pytest.mark.skipif(not os.path.exists("/dev/zero"), reason="/dev/zero absent")
def test_b7_prd_after_dev_zero_refused(ws):
    rc, out, err = _radar(["prd", str(GAPS), "--after", "/dev/zero"], ws)
    assert rc == 2
    assert out == ""
    assert _lines(err) == _after_refusal("/dev/zero")


@pytest.mark.parametrize("spelling", ["adir", "adir/", "./adir"])
def test_b8_prd_after_directory_refused(ws, spelling):
    (ws / "adir").mkdir()
    rc, out, err = _radar(["prd", str(GAPS), "--after", spelling], ws)
    assert rc == 2
    assert out == ""
    assert _lines(err) == _after_refusal(spelling)


def test_b9_prd_after_missing_path_keeps_no_such_file(ws):
    rc, out, err = _radar(["prd", str(GAPS), "--after", "missing.json"], ws)
    assert rc == 2
    assert out == ""
    assert _lines(err) == _after_refusal("missing.json", "No such file or directory")


# ---- b10: repeated --after, the non-regular FILE in any position ---------------


def _done(ws: pathlib.Path, doc: dict, name: str) -> str:
    doc = json.loads(json.dumps(doc))
    for story in doc["stories"]:
        story["passes"] = True
    (ws / name).write_text(json.dumps(doc), encoding="utf-8")
    return name


@pytest.mark.parametrize("kind", ["fifo", "dir"])
@pytest.mark.parametrize("pos", [0, 1, 2])
def test_b10_repeated_after_bad_file_in_any_position(ws, kind, pos):
    reg = ws / "reg"
    src = _src("GAP-041")
    (reg / src.name).write_bytes(src.read_bytes())
    rc, out, err = _radar(["prd", "reg"], ws)
    assert rc == 0, err
    d1 = _done(ws, json.loads(out), "d1.json")
    rc, out, err = _radar(["prd", "reg", "--after", d1], ws)
    assert rc == 0, err
    assert err.startswith("Note: ")  # premise: a valid DONE file emits a Note
    d2 = _done(ws, json.loads(out), "d2.json")
    if kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("POSIX FIFOs only")
        os.mkfifo(ws / "bad.fifo")
        bad = "bad.fifo"
    else:
        (ws / "bad.d").mkdir()
        bad = "bad.d"
    files = [d1, d2]
    files.insert(pos, bad)
    argv = ["prd", "reg"]
    for f in files:
        argv += ["--after", f]
    rc, out, err = _radar(argv, ws)
    assert rc == 2
    assert out == ""
    assert "Note:" not in err
    assert _lines(err) == _after_refusal(bad)


# ---- b11: committed register unchanged ---------------------------------------


def test_b11_committed_register_validates(tmp_path):
    rc, out, err = _radar(["validate", str(GAPS), "--json"], tmp_path)
    assert rc == 0, err
    doc = json.loads(out)
    assert doc["valid"] is True
    assert doc["records"] == len(list(GAPS.glob("GAP-*.json")))
    assert doc["records"] >= 120


def test_b11_prd_gaps_byte_identical_to_head(tmp_path):
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("no git checkout")
    p = subprocess.run(["git", "-C", str(REPO), "archive", "HEAD", "src"],
                       capture_output=True, timeout=TIMEOUT)
    if p.returncode != 0:
        pytest.skip("git archive unavailable")
    old = tmp_path / "old"
    with tarfile.open(fileobj=io.BytesIO(p.stdout)) as tf:
        tf.extractall(old, filter="data")
    rc_new, out_new, err_new = _radar(["prd", str(GAPS)], tmp_path)
    rc_old, out_old, err_old = _radar(["prd", str(GAPS)], tmp_path, src=old / "src")
    assert rc_new == rc_old == 0, (err_new, err_old)
    assert out_new == out_old
    assert out_new.endswith("\n") and not out_new.endswith("\n\n")
