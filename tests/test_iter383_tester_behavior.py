"""Iteration 383 tester behaviors: `radar report --match TEXT`.

Black-box only: every assertion drives the public CLI (`main` in-process, plus one
`python -m agent_gap_radar.cli` subprocess for `--help`). No hand-written expected
documents: the oracles are other public outputs.

- `radar list --json` under the SAME flags is the oracle for the narrowed id set,
  the header counts and the below-floor partition (swept over every floor 0..7).
- "every report section is computed over exactly the narrowed domain" is checked by
  byte-equality: `report gaps --match T` must equal `report <copy>` where `<copy>`
  holds ONLY the records `list --match T` shows. That pins evidence age, source
  concentration, tag coverage and by-layer sections without restating them.
- the committed REGISTER.md (== bare `report gaps`) pins that the flag-less bytes are
  unchanged.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
REGISTER = REPO / "REGISTER.md"

ID_ROW = re.compile(r"^\| (?:\d+ \| )?(GAP-\d{3}) \|", re.MULTILINE)
HEADER = re.compile(
    r"^Records: (\d+) \| ranked: (\d+) \| below confidence floor \((-?\d+)\): (\d+)$",
    re.MULTILINE,
)

NEEDLES = ["memory", "eval", "cost", "tool", "budget", "approval", "tenant", "retention"]


def run(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, out, err


def listing(capsys: pytest.CaptureFixture[str], *argv: object) -> dict:
    code, out, err = run(capsys, "list", GAPS, "--json", *argv)
    assert (code, err) == (0, ""), err
    return json.loads(out)


def section(doc: str, title: str) -> str:
    start = doc.index(f"\n## {title}\n")
    nxt = doc.find("\n## ", start + 1)
    return doc[start : nxt if nxt != -1 else len(doc)]


def ids_in(text: str) -> list[str]:
    return ID_ROW.findall(text)


def report_ids(doc: str) -> set[str]:
    ranked = ids_in(section(doc, "Ranked gaps"))
    below = ids_in(section(doc, "Below confidence floor"))
    assert not set(ranked) & set(below), "an id is both ranked and below floor"
    assert len(ranked) == len(set(ranked)) and len(below) == len(set(below))
    return set(ranked) | set(below)


# 1 ------------------------------------------------------------------------------
def test_b1_help_lists_match_option() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "report", "gaps", "--help"],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--match TEXT" in proc.stdout
    assert proc.stdout.endswith("\n") and not proc.stdout.endswith("\n\n")


# 2 ------------------------------------------------------------------------------
def test_b2_memory_matches_list_spec_numbers(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "report", GAPS, "--match", "memory")
    assert (code, err) == (0, "")
    want = {r["gap_id"] for r in listing(capsys, "--match", "memory")["records"]}
    assert len(want) == 24
    assert report_ids(out) == want
    assert "Records: 24 | ranked: 24 | below confidence floor (2): 0" in out.splitlines()


@pytest.mark.parametrize("needle", NEEDLES)
def test_b2_id_set_and_header_equal_list(capsys: pytest.CaptureFixture[str], needle: str) -> None:
    code, out, err = run(capsys, "report", GAPS, "--match", needle)
    assert (code, err) == (0, "")
    data = listing(capsys, "--match", needle)
    assert report_ids(out) == {r["gap_id"] for r in data["records"]}
    m = HEADER.search(out)
    assert m is not None
    c = data["counts"]
    assert tuple(int(x) for x in m.groups()) == (c["total"], c["ranked"], 2, c["below_floor"])


@pytest.mark.parametrize("needle", NEEDLES[:4])
def test_b2_every_section_is_computed_over_the_narrowed_domain(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path, needle: str
) -> None:
    """report --match T == report over a register holding only list --match T's records."""
    keep = {r["gap_id"] for r in listing(capsys, "--match", needle)["records"]}
    assert keep, needle
    sub = tmp_path / "gaps"
    sub.mkdir()
    copied = 0
    for f in sorted(GAPS.glob("GAP-*.json")):
        if f.name[:7] in keep:
            shutil.copy2(f, sub / f.name)
            copied += 1
    assert copied == len(keep)
    _, narrowed, _ = run(capsys, "report", GAPS, "--match", needle)
    code, whole_sub, err = run(capsys, "report", sub)
    assert (code, err) == (0, "")
    assert narrowed == whole_sub


# 3 ------------------------------------------------------------------------------
@pytest.mark.parametrize("variant", ["MEMORY", "Memory", "mEmOrY"])
def test_b3_case_folded(capsys: pytest.CaptureFixture[str], variant: str) -> None:
    _, base, _ = run(capsys, "report", GAPS, "--match", "memory")
    code, out, err = run(capsys, "report", GAPS, "--match", variant)
    assert (code, err) == (0, "")
    assert out == base


def test_b3_literal_not_regex(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "report", GAPS, "--match", "mem.ry")
    assert (code, err) == (0, "")
    assert report_ids(out) == {r["gap_id"] for r in listing(capsys, "--match", "mem.ry")["records"]}
    assert report_ids(out) != report_ids(run(capsys, "report", GAPS, "--match", "memory")[1])


# 4 ------------------------------------------------------------------------------
def test_b4_floor_6_displays_all_24_below(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "report", GAPS, "--match", "memory", "--floor", "6")
    assert (code, err) == (0, "")
    assert "Records: 24 | ranked: 0 | below confidence floor (6): 24" in out.splitlines()
    below = set(ids_in(section(out, "Below confidence floor")))
    assert below == {r["gap_id"] for r in listing(capsys, "--match", "memory")["records"]}
    assert ids_in(section(out, "Ranked gaps")) == []


@pytest.mark.parametrize("floor", range(0, 8))
def test_b4_floor_sweep_partition_equals_list(capsys: pytest.CaptureFixture[str], floor: int) -> None:
    code, out, err = run(capsys, "report", GAPS, "--match", "memory", "--floor", floor)
    assert (code, err) == (0, "")
    data = listing(capsys, "--match", "memory", "--floor", floor)
    want_below = {r["gap_id"] for r in data["records"] if r["below_floor"]}
    for r in data["records"]:
        assert r["below_floor"] == (r["confidence"] < floor)
    assert set(ids_in(section(out, "Below confidence floor"))) == want_below
    assert set(ids_in(section(out, "Ranked gaps"))) == {r["gap_id"] for r in data["records"]} - want_below


def test_b4_default_floor_below_record_stays_displayed(capsys: pytest.CaptureFixture[str]) -> None:
    """The register's sub-floor record, matched by its own title, is shown, not dropped."""
    allrec = listing(capsys)["records"]
    low = [r for r in allrec if r["below_floor"]]
    assert low, "register has no below-floor record to exercise"
    rec = low[0]
    code, out, err = run(capsys, "report", GAPS, "--match", rec["title"].upper())
    assert (code, err) == (0, "")
    assert rec["gap_id"] in ids_in(section(out, "Below confidence floor"))
    assert rec["gap_id"] not in ids_in(section(out, "Ranked gaps"))
    m = HEADER.search(out)
    assert m is not None and int(m.group(4)) >= 1


# 5 ------------------------------------------------------------------------------
def test_b5_compose_spec_numbers(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "report", GAPS, "--layer", "context-memory", "--match", "memory")
    assert (code, err) == (0, "")
    want = {r["gap_id"] for r in listing(capsys, "--layer", "context-memory", "--match", "memory")["records"]}
    assert len(want) == 15
    assert report_ids(out) == want
    assert HEADER.search(out).group(1) == "15"  # type: ignore[union-attr]


def _layers(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return sorted({r["layer"] for r in listing(capsys)["records"]})


@pytest.mark.parametrize("needle", ["memory", "eval", "cost"])
def test_b5_compose_every_layer(capsys: pytest.CaptureFixture[str], needle: str) -> None:
    layers = _layers(capsys)
    assert len(layers) >= 5
    nonempty = 0
    for layer in layers:
        code, out, err = run(capsys, "report", GAPS, "--layer", layer, "--match", needle)
        assert (code, err) == (0, ""), (layer, err)
        want = {r["gap_id"] for r in listing(capsys, "--layer", layer, "--match", needle)["records"]}
        assert report_ids(out) == want, layer
        nonempty += bool(want)
        layer_only = {r["gap_id"] for r in listing(capsys, "--layer", layer)["records"]}
        match_only = {r["gap_id"] for r in listing(capsys, "--match", needle)["records"]}
        assert want == layer_only & match_only, layer
    assert nonempty >= 1


# 6 ------------------------------------------------------------------------------
@pytest.mark.parametrize("blank", ["", "   ", "\t", " \n "])
@pytest.mark.parametrize("extra", [(), ("--layer", "context-memory"), ("--floor", "6")])
def test_b6_blank_text_refused(
    capsys: pytest.CaptureFixture[str], blank: str, extra: tuple[str, ...]
) -> None:
    try:
        code = main(["report", str(GAPS), "--match", blank, *extra])
    except SystemExit as exc:  # argparse-level refusals raise
        code = exc.code
    out, err = capsys.readouterr()
    assert code == 2
    assert out == ""
    lines = err.splitlines()
    assert len(lines) == 1 and err.endswith("\n")
    assert lines[0].startswith("Error: --match needs non-blank TEXT")


# 7 ------------------------------------------------------------------------------
@pytest.mark.parametrize("extra", [(), ("--layer", "context-memory"), ("--floor", "0")])
def test_b7_no_match_is_well_formed_empty_report(
    capsys: pytest.CaptureFixture[str], extra: tuple[str, ...]
) -> None:
    code, out, err = run(capsys, "report", GAPS, "--match", "zzqx-no-such-text", *extra)
    assert (code, err) == (0, "")
    floor = extra[1] if extra[:1] == ("--floor",) else "2"
    assert f"Records: 0 | ranked: 0 | below confidence floor ({floor}): 0" in out.splitlines()
    assert "None found." in section(out, "Ranked gaps")
    assert ids_in(out) == []
    assert "Traceback" not in out
    _, bare, _ = run(capsys, "report", GAPS)
    assert [l for l in out.splitlines() if l.startswith("## ")] == [
        l for l in bare.splitlines() if l.startswith("## ")
    ]


# 8 ------------------------------------------------------------------------------
def test_b8_bare_report_equals_committed_register(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(capsys, "report", GAPS)
    assert (code, err) == (0, "")
    assert out == REGISTER.read_text(encoding="utf-8")
    _, dot, _ = run(capsys, "report", REPO)
    assert dot == out


def test_b8_match_everything_needle_equals_bare(capsys: pytest.CaptureFixture[str]) -> None:
    """A needle every record contains ('the') narrows nothing, so bytes equal bare."""
    total = listing(capsys)["counts"]["total"]
    if listing(capsys, "--match", "the")["counts"]["total"] != total:
        pytest.fail("'the' is no longer in every record; pick another universal needle")
    _, bare, _ = run(capsys, "report", GAPS)
    _, out, _ = run(capsys, "report", GAPS, "--match", "the")
    assert out == bare


# 9 ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "argv",
    [
        (),
        ("--match", "memory"),
        ("--match", "zzqx-no-such-text"),
        ("--match", "memory", "--floor", "6"),
        ("--layer", "context-memory", "--match", "memory"),
        ("--layer", "observability", "--floor", "0"),
    ],
)
def test_b9_exactly_one_trailing_newline(capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]) -> None:
    code, out, err = run(capsys, "report", GAPS, *argv)
    assert (code, err) == (0, "")
    assert out.endswith("\n") and not out.endswith("\n\n")
    _, again, _ = run(capsys, "report", GAPS, *argv)
    assert again == out


# 10 -----------------------------------------------------------------------------
def test_b10_docs() -> None:
    contract = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    assert "`radar report [<repo>] [--floor N] [--layer L] [--match TEXT]`" in contract
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert re.search(r"radar report \. --match \S", readme)
    inv = (REPO / "tests" / "_surface_inventory.py").read_text(encoding="utf-8")
    assert "--match" in inv
