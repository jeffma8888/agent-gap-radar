"""The promotion gate must REFUSE. A gate that never rejects is fail-open.

These tests exist because the register is fed by unattended research agents.
The only thing standing between a plausible-looking fabrication and the
published register is this gate, so every refusal path gets a known-bad
sample and the accept path gets a known-good one.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "promote.py"

sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

import promote  # noqa: E402


def _candidate(**overrides) -> dict:
    doc = {
        "id": "GAP-900",
        "title": "A placeholder title the gate will renumber",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "status": "open",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [
            {
                "source_class": "vendor-primary",
                "title": "A page that was actually fetched",
                "locator": "https://example.com/a",
                "date": "2026-01-01",
                "quote": "one two three four five six seven",
            }
        ],
        "build_hypothesis": "b",
        "check": {
            "id": "CHK-900",
            "rationale": "r",
            "manual_question": "q",
            "present_when": {
                "kind": "content_matches",
                "globs": ["**/*.py"],
                "pattern": r"time\.sleep\(\s*\d",
            },
            "mitigated_when": {
                "kind": "content_matches",
                "globs": ["**/*.py"],
                "pattern": r"jitter|random\.uniform",
            },
            "fixtures": {
                "bad": {"a.py": "import time\ntime.sleep(5)\n"},
                "good": {
                    "a.py": "import random, time\n"
                    "time.sleep(5 + random.uniform(0, 1))  # jitter\n"
                },
            },
        },
    }
    doc.update(overrides)
    return doc


def _run(tmp_path: Path, candidates: dict[str, dict], apply: bool = False) -> str:
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name, doc in candidates.items():
        (inbox / name).write_text(json.dumps(doc), encoding="utf-8")
    argv = ["--inbox", str(inbox), "--gaps", str(REPO / "gaps")]
    if apply:
        argv += ["--apply", "--rejected", str(tmp_path / "rejected")]
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(argv)
    return buf.getvalue()


def test_sound_candidate_is_accepted(tmp_path):
    out = _run(tmp_path, {"c.json": _candidate()})
    assert "ACCEPT" in out, out


def test_gate_reassigns_ids_so_parallel_agents_cannot_collide(tmp_path):
    """Two agents both submitting GAP-900 must both land, on distinct ids."""
    out = _run(
        tmp_path,
        {
            "a.json": _candidate(title="First distinct gap"),
            "b.json": _candidate(
                title="Second distinct gap",
                check={
                    **_candidate()["check"],
                    "present_when": {
                        "kind": "content_matches",
                        "globs": ["**/*.py"],
                        "pattern": r"os\.system\(",
                    },
                    "fixtures": {
                        "bad": {"a.py": "import os\nos.system('ls')\n"},
                        "good": {"a.py": "import subprocess\nsubprocess.run(['ls'])\n"},
                    },
                },
            ),
        },
    )
    assert out.count("ACCEPT") == 2, out
    ids = {
        m.group(1)
        for line in out.splitlines()
        if (m := re.search(r"-> (GAP-\d{3})-", line))
    }
    assert len(ids) == 2, f"ids collided: {ids}\n{out}"


def test_rejects_check_that_fires_on_its_own_good_fixture(tmp_path):
    """A non-discriminating detector matches everything and measures nothing."""
    doc = _candidate(title="Matches everything")
    doc["check"]["present_when"] = {
        "kind": "content_matches",
        "globs": ["**/*.py"],
        "pattern": "import",
    }
    doc["check"]["fixtures"] = {"bad": {"a.py": "import time\n"}, "good": {"a.py": "import time\n"}}
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "does not discriminate" in out, out


def test_rejects_check_that_does_not_fire_on_its_own_bad_fixture(tmp_path):
    doc = _candidate(title="Fires on nothing")
    doc["check"]["fixtures"]["bad"] = {"a.py": "pass\n"}
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "does not fire" in out, out


def test_rejects_evidence_that_is_only_model_output(tmp_path):
    """A model asserting something is not evidence that it is true."""
    doc = _candidate(
        title="Asserted by a model",
        evidence=[
            {
                "source_class": "model-output",
                "title": "x",
                "locator": "https://example.com/b",
                "date": "2026-01-01",
                "quote": "one two three four five six",
            }
        ],
    )
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "zero-weight" in out, out


def test_rejects_non_url_locator(tmp_path):
    doc = _candidate()
    doc["evidence"][0]["locator"] = "a blog post I remember reading"
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "not a fetchable URL" in out, out


def test_rejects_quote_too_short_to_be_a_real_excerpt(tmp_path):
    doc = _candidate()
    doc["evidence"][0]["quote"] = "it broke"
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "too short" in out, out


def test_rejects_restatement_of_a_gap_already_in_the_register(tmp_path):
    """A fan-out of research agents must not flood the register with one gap."""
    existing = json.loads(
        next((REPO / "gaps").glob("GAP-007-*.json")).read_text(encoding="utf-8")
    )
    doc = _candidate(title="Restating a known gap", check=existing["check"])
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "restatement" in out, out


def test_rejects_prose_with_no_check_at_all(tmp_path):
    doc = _candidate()
    del doc["check"]
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out and "not as prose" in out, out


def test_rejects_automated_check_with_no_fixtures(tmp_path):
    doc = _candidate()
    del doc["check"]["fixtures"]
    out = _run(tmp_path, {"c.json": doc})
    assert "REJECT" in out, out


def test_rejects_unparseable_json(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "broken.json").write_text("{not json", encoding="utf-8")
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(["--inbox", str(inbox), "--gaps", str(REPO / "gaps")])
    assert "REJECT" in buf.getvalue() and "not valid JSON" in buf.getvalue()


def test_dry_run_is_the_default_and_writes_nothing(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "c.json").write_text(json.dumps(_candidate()), encoding="utf-8")
    before = {p.name for p in (REPO / "gaps").glob("*.json")}
    promote.main(["--inbox", str(inbox), "--gaps", str(REPO / "gaps")])
    after = {p.name for p in (REPO / "gaps").glob("*.json")}
    assert before == after, "dry run must not touch the register"
    assert (inbox / "c.json").exists(), "dry run must not consume the candidate"


def test_apply_writes_the_record_and_moves_rejections_with_a_reason(tmp_path):
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    for src in (REPO / "gaps").glob("*.json"):
        (gaps / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ok.json").write_text(json.dumps(_candidate()), encoding="utf-8")
    bad = _candidate(title="Fires on nothing")
    bad["check"]["fixtures"]["bad"] = {"a.py": "pass\n"}
    (inbox / "no.json").write_text(json.dumps(bad), encoding="utf-8")

    promote.main(
        [
            "--inbox", str(inbox),
            "--gaps", str(gaps),
            "--apply",
            "--rejected", str(tmp_path / "rejected"),
        ]
    )
    # Derive the expected id rather than hardcoding one: the register grows,
    # and a test pinned to GAP-011 self-destructs the day research lands it.
    expected = promote._next_id([p.name.split("-")[0] + "-" + p.name.split("-")[1]
                                 for p in (REPO / "gaps").glob("GAP-*.json")], "GAP")
    written = sorted(p.name for p in gaps.glob(expected + "-*.json"))
    assert written, f"expected {expected}, have " + str(sorted(p.name for p in gaps.glob("*.json")))
    assert not (inbox / "ok.json").exists(), "accepted candidate should be consumed"
    reason = (tmp_path / "rejected" / "no.reason.txt")
    assert reason.exists() and "does not fire" in reason.read_text(encoding="utf-8")
    assert not list(gaps.glob("*-fires-on-nothing.json")), "rejected record must not land"
    # No .tmp files may survive an apply: writes go through a temp then replace.
    assert not list(gaps.glob("*.tmp")), "atomic write left a temp file behind"


def test_promoted_record_is_loadable_by_the_registry(tmp_path):
    """An accepted candidate must be a first-class register record, not almost one."""
    from agent_gap_radar.registry import load_all

    gaps = tmp_path / "gaps"
    gaps.mkdir()
    for src in (REPO / "gaps").glob("*.json"):
        (gaps / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "ok.json").write_text(json.dumps(_candidate()), encoding="utf-8")
    promote.main(["--inbox", str(inbox), "--gaps", str(gaps), "--apply"])
    loaded = load_all(gaps)
    assert len(loaded) == len(list((REPO / "gaps").glob("*.json"))) + 1


def test_tool_runs_as_a_script(tmp_path):
    """The self-verify command in the contract must actually work."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "c.json").write_text(json.dumps(_candidate()), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--inbox", str(inbox), "--gaps", str(REPO / "gaps")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ACCEPT" in proc.stdout, proc.stdout


# --------------------------------------------------------------------------
# Ranked, capped promotion. Once unattended research can produce candidates
# faster than anyone reads them, "passes the gate" is no longer a sufficient
# reason to land: a thousand mechanically-valid records is a junk drawer, and
# it makes every score already in the register unbelievable.
# --------------------------------------------------------------------------

def _fresh_register(tmp_path) -> pathlib.Path:
    gaps = tmp_path / "gaps"
    gaps.mkdir()
    for src in (REPO / "gaps").glob("*.json"):
        (gaps / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return gaps


def _distinct(title: str, pattern: str, source_class: str = "vendor-primary",
              severity: int = 3) -> dict:
    """A candidate with its own check signature so novelty never rejects it."""
    doc = _candidate(title=title, severity=severity)
    doc["evidence"][0]["source_class"] = source_class
    doc["check"]["present_when"] = {
        "kind": "content_matches", "globs": ["**/*.py"], "pattern": pattern,
    }
    doc["check"]["fixtures"] = {
        "bad": {"a.py": f"# {pattern}\n"}, "good": {"a.py": "pass\n"},
    }
    doc["check"].pop("mitigated_when", None)
    return doc


def test_limit_caps_how_many_land_in_one_pass(tmp_path):
    gaps = _fresh_register(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for i in range(5):
        (inbox / f"c{i}.json").write_text(
            json.dumps(_distinct(f"Distinct gap number {i}", f"marker_{i}")),
            encoding="utf-8")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(["--inbox", str(inbox), "--gaps", str(gaps), "--apply",
                      "--limit", "2", "--rejected", str(tmp_path / "rej")])
    out = buf.getvalue()
    assert out.count("ACCEPT") == 2, out
    assert "3 left for a later pass" in out, out
    assert len(list(inbox.glob("*.json"))) == 3, "the rest must survive untouched"


def test_stronger_evidence_is_promoted_first(tmp_path):
    """Confidence outranks a self-assigned severity, because it cannot be inflated."""
    gaps = _fresh_register(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    # Weak evidence but maximal self-reported severity.
    (inbox / "loud.json").write_text(json.dumps(_distinct(
        "Loud but weakly sourced", "marker_loud",
        source_class="secondary-summary", severity=5)), encoding="utf-8")
    # Strong evidence, modest self-reported severity.
    (inbox / "solid.json").write_text(json.dumps(_distinct(
        "Quiet but well sourced", "marker_solid",
        source_class="incident-postmortem", severity=1)), encoding="utf-8")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(["--inbox", str(inbox), "--gaps", str(gaps), "--apply",
                      "--limit", "1", "--rejected", str(tmp_path / "rej")])
    out = buf.getvalue()
    assert "solid.json" in out and "ACCEPT" in out, out
    assert (inbox / "loud.json").exists(), "the weakly-sourced one should wait"


def test_register_cap_escalates_instead_of_flooding_or_discarding(tmp_path):
    gaps = _fresh_register(tmp_path)
    existing = len(list(gaps.glob("*.json")))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for i in range(3):
        (inbox / f"c{i}.json").write_text(
            json.dumps(_distinct(f"Waiting gap {i}", f"marker_w{i}")), encoding="utf-8")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = promote.main(["--inbox", str(inbox), "--gaps", str(gaps), "--apply",
                           "--register-cap", str(existing)])
    out = buf.getvalue()
    assert rc == 0
    assert "REGISTER AT CAPACITY" in out, out
    assert "NOTHING was discarded" in out, out
    assert len(list(inbox.glob("*.json"))) == 3, "candidates must be preserved"
    assert len(list(gaps.glob("*.json"))) == existing, "register must not grow"


def test_register_cap_allows_only_the_remaining_room(tmp_path):
    gaps = _fresh_register(tmp_path)
    existing = len(list(gaps.glob("*.json")))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for i in range(4):
        (inbox / f"c{i}.json").write_text(
            json.dumps(_distinct(f"Room gap {i}", f"marker_r{i}")), encoding="utf-8")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(["--inbox", str(inbox), "--gaps", str(gaps), "--apply",
                      "--register-cap", str(existing + 2),
                      "--rejected", str(tmp_path / "rej")])
    out = buf.getvalue()
    assert out.count("ACCEPT") == 2, out
    assert len(list(gaps.glob("*.json"))) == existing + 2


def test_rank_puts_unparseable_last_but_still_reports_it(tmp_path):
    gaps = _fresh_register(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "broken.json").write_text("{not json", encoding="utf-8")
    (inbox / "ok.json").write_text(json.dumps(_distinct("Fine gap", "marker_ok")),
                                   encoding="utf-8")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(["--inbox", str(inbox), "--gaps", str(gaps)])
    out = buf.getvalue()
    assert "ACCEPT" in out and "not valid JSON" in out, out
