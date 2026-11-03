"""Iteration 383: ``radar report`` gains ``list``'s ``--match TEXT`` domain filter.

``radar list`` under the same flags is the oracle for every live-register id set
here: the report must be computed over exactly the records the listing shows, so a
second, hand-written matcher would be a second source of truth. The committed
``REGISTER.md`` is the bare report's byte pin, which is why the "without the flag
nothing moved" behavior compares against it rather than a hard-coded digest.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
ID = re.compile(r"^\| (?:\d+ \| )?(GAP-\d+) \|", re.MULTILINE)


def _run(capsys, argv: list[str]) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def _listed_ids(capsys, flags: list[str]) -> set[str]:
    """The id set ``radar list <flags>`` prints: the oracle for the report's domain."""
    code, out, err = _run(capsys, ["list", GAPS, *flags])
    assert (code, err) == (0, "")
    return {line.split()[0] for line in out.splitlines()}


def _section(document: str, heading: str) -> str:
    """The body of one ``## `` section, up to the next heading or the end."""
    start = document.index(f"## {heading}\n")
    end = document.find("\n## ", start + 1)
    return document[start:] if end == -1 else document[start:end]


def _report_ids(document: str) -> set[str]:
    """Every id in the ranked and below-floor tables -- the two halves of the domain."""
    ids = ID.findall(_section(document, "Ranked gaps"))
    ids += ID.findall(_section(document, "Below confidence floor"))
    assert len(ids) == len(set(ids)), "a record listed twice"
    return set(ids)


def _header(document: str) -> str:
    return next(line for line in document.splitlines() if line.startswith("Records: "))


def test_b1_help_lists_match(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["report", "--help"])
    assert exc.value.code == 0
    assert "--match TEXT" in capsys.readouterr().out


def test_b2_b3_b9_match_narrows_to_the_list_domain_case_folded(capsys):
    code, out, err = _run(capsys, ["report", GAPS, "--match", "memory"])
    assert (code, err) == (0, "")
    expected = _listed_ids(capsys, ["--match", "memory"])
    assert expected and _report_ids(out) == expected
    assert _header(out) == f"Records: {len(expected)} | ranked: {len(expected)} | below confidence floor (2): 0"
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert _run(capsys, ["report", GAPS, "--match", "MEMORY"]) == (0, out, "")


def test_b4_below_floor_matches_are_displayed_not_dropped(capsys):
    code, out, err = _run(capsys, ["report", GAPS, "--match", "memory", "--floor", "6"])
    assert (code, err) == (0, "")
    expected = _listed_ids(capsys, ["--match", "memory"])
    below = set(ID.findall(_section(out, "Below confidence floor")))
    assert below == expected
    assert _header(out) == f"Records: {len(expected)} | ranked: 0 | below confidence floor (6): {len(expected)}"


def test_b5_match_composes_with_layer(capsys):
    flags = ["--layer", "context-memory", "--match", "memory"]
    code, out, err = _run(capsys, ["report", GAPS, *flags])
    assert (code, err) == (0, "")
    expected = _listed_ids(capsys, flags)
    assert expected < _listed_ids(capsys, ["--match", "memory"])
    assert _report_ids(out) == expected
    assert _header(out).startswith(f"Records: {len(expected)} |")


@pytest.mark.parametrize("text", ["", "   "])
def test_b6_blank_text_is_exit_2(capsys, text):
    code, out, err = _run(capsys, ["report", GAPS, "--match", text])
    assert (code, out) == (2, "")
    assert err.startswith("Error: --match needs non-blank TEXT")
    assert err.endswith("\n") and err.count("\n") == 1


def test_b7_no_match_is_an_exit_0_empty_report(capsys):
    code, out, err = _run(capsys, ["report", GAPS, "--match", "zzqx-no-such-text"])
    assert (code, err) == (0, "")
    assert _header(out) == "Records: 0 | ranked: 0 | below confidence floor (2): 0"
    assert "None found." in _section(out, "Ranked gaps")
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b8_without_match_the_bare_report_is_the_committed_register(capsys):
    code, out, err = _run(capsys, ["report", GAPS])
    assert (code, err) == (0, "")
    assert out == (REPO / "REGISTER.md").read_text(encoding="utf-8")
