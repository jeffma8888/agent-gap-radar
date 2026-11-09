"""Iteration 389 -- ``radar scan <target> --match TEXT`` narrows the scanned DOMAIN.

Every node runs over a three-record ``tmp_path`` register and a one-file target, so
nothing here scans the live register and the module stays well under a second:

- GAP-901: above the floor, prose contains ``memory``, PRESENT on the target.
- GAP-902: below the floor (a single model-output citation), prose contains
  ``Memory`` in another layer, PRESENT on the target -- the record the core invariant
  says must be DISPLAYED, never dropped, by a filter that never mentions the floor.
- GAP-903: above the floor, prose contains only ``quokka``, ABSENT on the target.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar.cli import build_parser, main

R1, R2, R3 = "GAP-901", "GAP-902", "GAP-903"
NEEDLE, OTHER = "memory", "quokka"
LAYER_R1 = "orchestration"
BLANK_ERROR = ("Error: --match needs non-blank TEXT; omit the flag to scan "
               "every record")
REPO = pathlib.Path(__file__).resolve().parents[1]


def _record(gid: str, title: str, layer: str, source_class: str, sig: str) -> dict:
    """A schema-valid record whose check is PRESENT iff `sig` is in a target .py file."""
    return {
        "id": gid, "title": title, "layer": layer, "gap_type": "missing-contract",
        "problem": "p", "symptom": "s", "why_now": "w", "existing": ["none"],
        "build_hypothesis": "b", "tags": ["plain"],
        "severity": 4, "frequency": 4, "tractability": 4,
        "evidence": [{"source_class": source_class, "title": "t",
                      "locator": "https://example.invalid/x", "date": "2026-01-02",
                      "quote": "the verbatim line"}],
        "check": {
            "id": "CHK" + gid[3:], "rationale": "r", "manual_question": "q",
            "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                             "pattern": sig},
            "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                               "pattern": "FIX" + sig},
            "fixtures": {"bad": {"a.py": sig + "\n"}, "good": {"a.py": "FIX" + sig + "\n"}},
        },
    }


@pytest.fixture
def world(tmp_path: pathlib.Path) -> tuple[str, str]:
    """(target, register) as strings, ready for argv."""
    gaps = tmp_path / "reg" / "gaps"
    gaps.mkdir(parents=True)
    for rec in (_record(R1, f"{NEEDLE} one", LAYER_R1, "first-party-field", "SIG_ONE"),
                _record(R2, "Memory two", "cost-governance", "model-output", "SIG_TWO"),
                _record(R3, f"{OTHER} three", LAYER_R1, "first-party-field", "SIG_THREE")):
        (gaps / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.py").write_text("SIG_ONE\nSIG_TWO\nFIXSIG_THREE\n", encoding="utf-8")
    return str(target), str(tmp_path / "reg")


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _scan(world: tuple[str, str], *flags: str) -> tuple[int, str, str]:
    target, register = world
    return _run("scan", target, "--gaps", register, *flags)


def _applied(markdown: str) -> int:
    (line,) = [ln for ln in markdown.splitlines() if ln.startswith("Register records applied:")]
    return int(line.split(":")[1])


def _ids(doc: dict) -> set[str]:
    return {f["gap_id"] for f in doc["findings"]} | set(doc["uncheckable"])


def test_b1_match_narrows_the_markdown_domain(world):
    code, out, err = _scan(world, "--match", NEEDLE)
    assert (code, err) == (0, "")
    assert _applied(out) == 2
    assert f"### {R1} " in out and f"### {R2} " in out and R3 not in out


@pytest.mark.parametrize("text", [NEEDLE, OTHER, "PLAIN", "one"])
def test_b2_case_folded_and_the_same_set_list_match_selects(world, text):
    assert _scan(world, "--match", text.upper()) == _scan(world, "--match", text.lower())
    code, out, _ = _scan(world, "--json", "--match", text)
    listed = json.loads(_run("list", world[1], "--json", "--match", text)[1])
    assert code == 0
    assert _ids(json.loads(out)) == {r["gap_id"] for r in listed["records"]}


def test_b3_a_matching_below_floor_record_is_displayed_and_flagged(world):
    doc = json.loads(_scan(world, "--json", "--match", NEEDLE)[1])
    (r2,) = [f for f in doc["findings"] if f["gap_id"] == R2]
    assert r2["below_floor"] is True


def test_b4_match_key_sits_after_layer_only_when_given(world):
    keys = list(json.loads(_scan(world, "--json", "--match", NEEDLE)[1]))
    assert keys[keys.index("layer") + 1] == "match"
    _, bare, _ = _scan(world, "--json")
    assert "match" not in json.loads(bare)
    # A needle every record carries (the `plain` tag) applies the whole domain, so the
    # flagged document is the bare one plus exactly the echoed key line.
    _, flagged, _ = _scan(world, "--json", "--match", "Plain")
    assert flagged.replace('  "match": "Plain",\n', "", 1) == bare


@pytest.mark.parametrize("text", ["", "   "])
def test_b5_blank_text_is_refused_before_any_directory_is_read(tmp_path, text):
    missing = str(tmp_path / "nowhere")
    code, out, err = _run("scan", missing, "--gaps", missing, "--match", text)
    assert (code, out) == (2, "")
    assert err.splitlines() == [BLANK_ERROR]


def test_b6_a_match_nothing_contains_applies_zero_and_gates_as_a_refusal(world):
    code, out, err = _scan(world, "--match", "zzqqxx")
    assert (code, err) == (0, "") and _applied(out) == 0
    code, out, err = _scan(world, "--match", "zzqqxx", "--exit-code")
    assert (code, out) == (2, "") and err.startswith("Error: scan applied 0 register records")


@pytest.mark.parametrize("flags, applied", [
    (["--layer", LAYER_R1, "--match", NEEDLE], 1),
    (["--match", NEEDLE, "--layer", LAYER_R1], 1),
    (["--gap", R3, "--match", NEEDLE], 0),
    (["--gap", R1, "--match", NEEDLE], 1),
])
def test_b7_match_composes_as_an_and_with_gap_and_layer(world, flags, applied):
    code, out, err = _scan(world, *flags)
    assert (code, err) == (0, "")
    assert _applied(out) == applied


@pytest.mark.parametrize("text, expected", [(NEEDLE, 1), (OTHER, 0)])
def test_b8_exit_code_over_a_matched_domain(world, text, expected):
    code, out, err = _scan(world, "--exit-code", "--match", text)
    assert (code, err) == (expected, "")
    assert out == _scan(world, "--match", text)[1]


def test_b9_a_match_narrowed_baseline_never_certifies_a_full_scan(world, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(_scan(world, "--json", "--match", OTHER)[1], encoding="utf-8")
    code, out, err = _scan(world, "--exit-code", "--baseline", str(baseline))
    assert (code, err) == (1, "")
    (line,) = [ln for ln in out.splitlines() if ln.startswith("Baseline:")]
    assert f"scanned by the baseline: 0 (none); unscanned by the baseline: 1 ({R1})" in line


def test_b10_help_and_contract_row_publish_the_flag():
    (scan_parser,) = [a.choices["scan"] for a in build_parser()._actions
                      if hasattr(a, "choices") and isinstance(a.choices, dict)
                      and "scan" in a.choices]
    help_text = " ".join(scan_parser.format_help().split())  # argparse wraps by width
    assert "--match TEXT" in help_text and "`list --match`" in help_text
    contract = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    (row,) = [ln for ln in contract.splitlines() if ln.startswith("| `radar scan <target>")]
    assert "[--gap <ID>] [--match TEXT] [--json]" in row
    assert BLANK_ERROR.removeprefix("Error: ") in row


@pytest.mark.parametrize("flags", [["--match", NEEDLE], ["--json", "--match", NEEDLE],
                                   ["--exit-code", "--match", NEEDLE]])
def test_b11_one_trailing_newline_and_byte_stable(world, flags):
    first, second = _scan(world, *flags), _scan(world, *flags)
    assert first == second
    assert first[1].endswith("\n") and not first[1].endswith("\n\n")


# ---- tester nodes (black-box, iter 389) -------------------------------------------


@pytest.mark.parametrize("text", ["\t\n", "\xa0", "\u2028", " \r\n\x0b "])
def test_tester_unicode_blank_is_refused_like_list(world, text):
    assert text.strip() == ""  # the oracle: blank means nothing survives str.strip()
    for flags in ([], ["--json"], ["--exit-code"]):
        code, out, err = _scan(world, *flags, "--match", text)
        assert (code, out) == (2, "")
        assert err.splitlines() == [BLANK_ERROR]
    assert _run("list", world[1], "--match", text)[0] == 2  # same refusal family


def test_tester_match_echo_is_the_text_as_typed(world):
    doc = json.loads(_scan(world, "--json", "--match", "MeMoRy")[1])
    assert doc["match"] == "MeMoRy"
    assert doc["records_applied"] == 2


@pytest.mark.parametrize("text", ["cost-governance", "missing-contract", "verbatim",
                                  "GAP-902", "two", "example.invalid", "SIG_ONE", "q"])
def test_tester_scan_domain_equals_list_domain_for_more_texts(world, text):
    code, out, err = _scan(world, "--json", "--match", text)
    lcode, lout, _ = _run("list", world[1], "--json", "--match", text)
    assert (code, err, lcode) == (0, "", 0)
    doc, listed = json.loads(out), json.loads(lout)
    assert _ids(doc) == {r["gap_id"] for r in listed["records"]}
    assert doc["records_applied"] == len(listed["records"])


def test_tester_narrowing_never_changes_a_selected_record(world):
    full = {f["gap_id"]: f for f in json.loads(_scan(world, "--json")[1])["findings"]}
    narrowed = json.loads(_scan(world, "--json", "--match", NEEDLE)[1])
    assert {f["gap_id"] for f in narrowed["findings"]} == {R1, R2}
    for f in narrowed["findings"]:
        assert f == full[f["gap_id"]]
    assert narrowed["counts"]["PRESENT"] == 2
    _, md_full, _ = _scan(world)
    _, md_narrow, _ = _scan(world, "--match", NEEDLE)

    def section(md: str, gid: str) -> str:
        start = md.index(f"### {gid} ")
        end = md.find("\n#", start + 1)
        return md[start:end]
    assert section(md_narrow, R2) == section(md_full, R2)
    assert "evidence confidence 0" in section(md_narrow, R2)


def test_tester_zero_match_json_is_an_empty_but_echoed_document(world):
    code, out, err = _scan(world, "--json", "--match", "zzqqxx")
    assert (code, err) == (0, "")
    doc = json.loads(out)
    assert (doc["match"], doc["records_applied"], doc["findings"], doc["uncheckable"]) == (
        "zzqqxx", 0, [], [])
    assert set(doc["counts"].values()) == {0}
    assert out.endswith("}\n") and not out.endswith("\n\n")


def test_tester_a_covering_match_baseline_does_certify_the_full_scan(world, tmp_path):
    # Positive control for b9: a narrowed baseline that DID scan R1 lets the full
    # --exit-code scan pass, so b9's exit 1 is about coverage, not a baseline that
    # can never certify anything.
    baseline = tmp_path / "covering.json"
    baseline.write_text(_scan(world, "--json", "--match", NEEDLE)[1], encoding="utf-8")
    code, out, err = _scan(world, "--exit-code", "--baseline", str(baseline))
    assert (code, err) == (0, "")
    (line,) = [ln for ln in out.splitlines() if ln.startswith("Baseline:")]
    assert "unscanned by the baseline: 0 (none)" in line
