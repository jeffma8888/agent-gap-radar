"""Iteration 385: a citation locator with edge whitespace is refused, and "resolvable" is a
whole-string match.

Why this matters: corroboration (the confidence point for two citations from different
source documents) keys on the locator string. Before this iteration, `U` and `U + " "`
cited under two source classes read as two documents, so ONE document plus a stray editor
keystroke earned a corroboration point. Separately, `https?://\\S+$` under `re.match`
admitted a trailing newline. Both doors now agree: the field refuses edge whitespace and
the shared pattern (in `models.py` and its stdlib copy in `tools/check_locators.py`) ends
in `\\Z`.

Offline, in-process, and every path is derived from this file's location.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys

import pytest
from pydantic import ValidationError

from agent_gap_radar import models
from agent_gap_radar.cli import main
from agent_gap_radar.models import Evidence, Gap, is_resolvable_locator
from agent_gap_radar.scoring import confidence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import check_locators  # noqa: E402  (path is prepared immediately above)

U = "https://example.org/post"
EDGE_PHRASE = "must not begin or end with whitespace"
EMPTY_PHRASE = "locator must not be empty"
PADDED = [U + " ", " " + U, U + "\t", U + "\n", "\n" + U]
OK_RE = re.compile(r"^OK: (\d+) gap record\(s\) valid\.\n$")


def _ev(**over: object) -> dict:
    """One schema-valid citation; overrides replace single keys."""
    base = {
        "source_class": "practitioner-report",
        "title": "t",
        "locator": U,
        "date": "2026-01-02",
        "quote": "a verbatim excerpt",
    }
    base.update(over)
    return base


def _gap(evidence: list[dict]) -> dict:
    """One otherwise-valid record, so any refusal is attributable to its citations."""
    return {
        "id": "GAP-701",
        "title": "a synthetic record",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": evidence,
    }


def _messages(exc: ValidationError) -> str:
    return "\n".join(e["msg"] for e in exc.errors())


# ---------------------------------------------------------------------------- behavior 1

def test_control_the_unpadded_locator_validates():
    assert Evidence.model_validate(_ev()).locator == U


@pytest.mark.parametrize("locator", PADDED, ids=repr)
def test_behavior1_edge_whitespace_is_refused_with_the_repr(locator):
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator=locator))
    msg = _messages(exc.value)
    assert EDGE_PHRASE in msg, msg
    assert repr(locator) in msg, msg
    assert "\n" not in msg, "a newline must appear escaped, never as a raw line break"


# ---------------------------------------------------------------------------- behavior 2

@pytest.mark.parametrize("locator", ["ISBN 978 0 00 000000 0", "docs/field notes.md"])
def test_behavior2_inner_whitespace_is_not_refused(locator):
    assert Evidence.model_validate(_ev(locator=locator)).locator == locator


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"], ids=repr)
def test_behavior2_blank_refusal_keeps_its_message(blank):
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator=blank))
    msg = _messages(exc.value)
    assert EMPTY_PHRASE in msg and EDGE_PHRASE not in msg, msg


# ---------------------------------------------------------------------------- behavior 3

def test_behavior3_a_padded_copy_cannot_corroborate():
    padded = _gap([_ev(), _ev(source_class="secondary-summary", locator=U + " ")])
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(padded)
    assert EDGE_PHRASE in _messages(exc.value)


def test_behavior3_the_same_document_twice_earns_no_point():
    single = Gap.model_validate(_gap([_ev()]))
    twice = Gap.model_validate(_gap([_ev(), _ev(source_class="secondary-summary")]))
    assert confidence(twice) == confidence(single)


# ---------------------------------------------------------------------------- behavior 4

RESOLVABILITY = [
    ("https://example.com/a\n", False),
    ("https://example.com/a\n\n", False),
    ("https://example.com/a ", False),
    ("https://example.com/a", True),
    ("http://example.com/a#frag", True),
]


@pytest.mark.parametrize("locator,expected", RESOLVABILITY, ids=repr)
def test_behavior4_both_predicates_give_the_same_whole_string_answer(locator, expected):
    assert is_resolvable_locator(locator) is expected
    assert check_locators.is_resolvable_locator(locator) is expected


def test_behavior4_both_patterns_end_in_backslash_z():
    patterns = [models.RESOLVABLE_LOCATOR_RE.pattern,
                check_locators._RESOLVABLE_LOCATOR_RE.pattern]
    assert patterns[0] == patterns[1]
    for pattern in patterns:
        assert pattern.endswith(r"\Z") and not pattern.endswith("$"), pattern


# ---------------------------------------------------------------------------- behavior 5

def test_behavior5_validate_names_the_padded_record(tmp_path, capsys):
    copy_dir = tmp_path / "gaps"
    shutil.copytree(LIVE_GAPS, copy_dir)
    target = sorted(copy_dir.glob("*.json"))[0]
    record = json.loads(target.read_text(encoding="utf-8"))
    record["evidence"][0]["locator"] += "\n"
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    assert main(["validate", str(copy_dir)]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    lines = [ln for ln in err.splitlines() if ln.startswith("Error: ")]
    assert lines, err
    assert any(target.name in ln and EDGE_PHRASE in ln for ln in lines), err


def test_behavior5_the_shipped_register_still_validates(capsys):
    count = len(list(LIVE_GAPS.glob("*.json")))
    assert count > 0
    assert main(["validate", str(LIVE_GAPS)]) == 0
    out, err = capsys.readouterr()
    assert err == ""
    match = OK_RE.match(out)
    assert match and int(match.group(1)) == count, out


# ---------------------------------------------------------------------------- behavior 6

@pytest.mark.parametrize("argv", [["list"], ["report"], ["list", "--json"]])
def test_behavior6_rendered_surfaces_are_byte_stable(argv, capsys):
    outputs = []
    for _ in range(2):
        assert main([*argv, str(LIVE_GAPS)]) == 0
        out, err = capsys.readouterr()
        assert err == ""
        outputs.append(out)
    assert outputs[0] == outputs[1]
    assert outputs[0].endswith("\n") and not outputs[0].endswith("\n\n")


def test_behavior6_bare_report_still_matches_the_committed_register(capsys):
    """REGISTER.md is the committed render of `report gaps`, so equality shows this
    iteration re-rendered nothing."""
    assert main(["report", str(LIVE_GAPS)]) == 0
    assert capsys.readouterr().out == (REPO_ROOT / "REGISTER.md").read_text(encoding="utf-8")


def test_behavior6_no_live_locator_carries_edge_whitespace():
    for path in sorted(LIVE_GAPS.glob("*.json")):
        for ev in json.loads(path.read_text(encoding="utf-8"))["evidence"]:
            assert ev["locator"] == ev["locator"].strip(), path.name


# ---------------------------------------------------------------------------- behavior 7

def test_behavior7_contract_locator_row_states_the_rule():
    text = (REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| `locator` | yes | string |")]
    assert len(rows) == 1, rows
    assert "no leading or trailing whitespace" in rows[0]
    assert "trailing newline is not resolvable" in rows[0]



# ------------------------------------------------------------ tester additions (black-box)

UNICODE_EDGES = [U + "\xa0", "\u2028" + U, U + "\r", U + "\r\n", "\x0b" + U, U + "\x0c"]


@pytest.mark.parametrize("locator", UNICODE_EDGES, ids=repr)
def test_tester_behavior1_every_strip_whitespace_edge_is_refused(locator):
    """The rule is `v != v.strip()`, so the oracle is str.strip() itself, not a list of
    three ASCII characters."""
    assert locator != locator.strip()
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator=locator))
    msg = _messages(exc.value)
    assert EDGE_PHRASE in msg and repr(locator) in msg, msg


@pytest.mark.parametrize("locator", ["docs/field notes.md", "doi:10.1000/x y", U],
                         ids=repr)
def test_tester_behavior2_kept_locators_are_stored_verbatim(locator):
    """Refuse, never normalise: an accepted locator is the exact input string."""
    ev = Evidence.model_validate(_ev(locator=locator))
    assert ev.locator == locator and ev.locator == ev.locator.strip()


@pytest.mark.parametrize("padded", PADDED, ids=repr)
def test_tester_behavior3_every_padded_twin_is_refused_on_the_record(padded):
    record = _gap([_ev(), _ev(source_class="secondary-summary", locator=padded)])
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(record)
    msg = _messages(exc.value)
    assert EDGE_PHRASE in msg and repr(padded) in msg, msg


def test_tester_behavior3_a_genuinely_different_document_still_corroborates():
    """Control for the 'no point' oracle: the ladder still rewards two distinct
    documents, so the equality above is not a ladder that never moves."""
    single = Gap.model_validate(_gap([_ev()]))
    other = Gap.model_validate(
        _gap([_ev(), _ev(source_class="secondary-summary", locator=U + "/other")]))
    assert confidence(other) > confidence(single)


SWEEP = [
    "https://example.com/a", "http://example.com/a#frag", "https://example.com/a\n",
    "https://example.com/a\n\n", "https://example.com/a ", "https://example.com/a\t",
    "https://example.com/a\r", " https://example.com/a", "https://", "https://x",
    "https://x y", "ftp://example.com/a", "docs/a.md", "", "HTTPS://example.com/a",
]


@pytest.mark.parametrize("locator", SWEEP, ids=repr)
def test_tester_behavior4_the_two_doors_never_disagree(locator):
    assert is_resolvable_locator(locator) is check_locators.is_resolvable_locator(locator)


@pytest.mark.parametrize("locator", SWEEP, ids=repr)
def test_tester_behavior4_resolvable_implies_no_whitespace_anywhere(locator):
    if is_resolvable_locator(locator):
        assert not any(ch.isspace() for ch in locator), repr(locator)


def test_tester_behavior4_pattern_is_exactly_the_spec_pattern():
    assert models.RESOLVABLE_LOCATOR_RE.pattern == r"https?://\S+\Z"
    assert check_locators._RESOLVABLE_LOCATOR_RE.pattern == r"https?://\S+\Z"


@pytest.mark.parametrize("suffix", ["\n", " ", "\t"], ids=repr)
def test_tester_behavior5_subprocess_door_one_error_line(tmp_path, suffix):
    """Drive the real console entry in a child process: exit 2, empty stdout, and an
    `Error: ` line naming the padded record's file -- no traceback."""
    import os
    import subprocess

    copy_dir = tmp_path / "gaps"
    shutil.copytree(LIVE_GAPS, copy_dir)
    target = sorted(copy_dir.glob("*.json"))[-1]
    record = json.loads(target.read_text(encoding="utf-8"))
    record["evidence"][0]["locator"] += suffix
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; from agent_gap_radar.cli import main; sys.exit(main())",
         "validate", str(copy_dir)],
        capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120,
    )
    assert proc.returncode == 2, proc.stderr
    assert proc.stdout == ""
    assert "Traceback" not in proc.stderr
    lines = [ln for ln in proc.stderr.splitlines() if ln.startswith("Error: ")]
    assert any(target.name in ln and EDGE_PHRASE in ln for ln in lines), proc.stderr
    untouched = sorted(copy_dir.glob("*.json"))[0].name
    assert not any(untouched in ln for ln in lines), proc.stderr
