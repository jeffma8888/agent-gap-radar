"""Iteration 374: `radar scan --json` carries the `--baseline` gate's partition as `baseline`.

Black-box over the public CLI: every assertion drives `main()` and reads stdout, stderr
and the exit code. The fixture (gaps A/B/C above the floor, W below it) is the one
iteration 305 built, so the markdown `Baseline:` line these tests compare against is a
line that module already pins.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from test_iter305_behavior import REGISTER, _run, _tree

KEY_ORDER = ["target", "target_name", "confidence_floor", "layer", "records_applied",
             "counts", "uncheckable", "findings", "baseline"]
BASELINE_KEYS = ["path", "carried", "new", "scanned", "unscanned"]


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    root = tmp_path_factory.mktemp("iter374")
    reg = root / "reg" / "gaps"
    reg.mkdir(parents=True)
    for rec in REGISTER:
        (reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    trees = {label: _tree(root / f"tree_{label}", present)
             for label, present in {"a": {"A"}, "ab": {"A", "B"}, "aw": {"A", "W"},
                                    "abcw": {"A", "B", "C", "W"}}.items()}
    old_reg = root / "old_reg" / "gaps"
    old_reg.mkdir(parents=True)
    for rec in REGISTER[:1] + REGISTER[3:]:
        (old_reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")

    def write_baseline(label: str, name: str, gaps: pathlib.Path = reg) -> str:
        rc, out, err = _run(["scan", str(trees[label]), "--gaps", str(gaps), "--json"])
        assert (rc, err) == (0, ""), (label, rc, err)
        (root / name).write_text(out, encoding="utf-8")
        return name  # a RELATIVE spelling: tests chdir into `root`

    return {"root": root, "reg": str(reg), "trees": trees,
            "b_aw": write_baseline("aw", "b-aw.json"),
            "b_a_partial": write_baseline("a", "b-a-partial.json", old_reg)}


@pytest.fixture
def scan(bed, monkeypatch):
    monkeypatch.chdir(bed["root"])

    def run(label: str, *extra: str):
        return _run(["scan", str(bed["trees"][label]), "--gaps", bed["reg"], *extra])
    return run


def _line(markdown: str) -> str:
    (line,) = [ln for ln in markdown.splitlines() if ln.startswith("Baseline: ")]
    return line


def _clause_ids(line: str, clause: str) -> list[str]:
    m = re.search(re.escape(clause) + r": (\d+) \(([^)]*)\)", line)
    assert m, (clause, line)
    ids = [] if m.group(2) == "none" else m.group(2).split(", ")
    assert len(ids) == int(m.group(1)), line
    return ids


def test_b1_no_baseline_key_is_null_and_last(scan):
    rc, out, err = scan("abcw", "--json")
    payload = json.loads(out)
    assert list(payload) == KEY_ORDER
    assert payload["baseline"] is None
    assert (rc, err) == (0, "")


@pytest.mark.parametrize("label", ["a", "ab", "abcw"])
def test_b2_to_b6_object_matches_markdown_line_and_exit(scan, bed, label):
    gate = ["--exit-code", "--baseline", bed["b_aw"]]
    rc, out, err = scan(label, "--json", *gate)
    md_rc, md_out, md_err = scan(label, *gate)
    obj = json.loads(out)["baseline"]
    assert list(obj) == BASELINE_KEYS
    assert obj["path"] == bed["b_aw"] == "b-aw.json"
    assert obj["carried"] == ["GAP-801", "GAP-803"]  # GAP-803 is below the floor
    line = _line(md_out)
    assert obj["new"] == _clause_ids(line, "new above-floor PRESENT")
    assert obj["scanned"] == _clause_ids(line, "scanned by the baseline")
    assert obj["unscanned"] == _clause_ids(line, "unscanned by the baseline")
    for key in ("carried", "new", "scanned", "unscanned"):
        assert obj[key] == sorted(obj[key])
    assert set(obj["scanned"]) | set(obj["unscanned"]) == set(obj["new"])
    assert not set(obj["scanned"]) & set(obj["unscanned"])
    assert rc == md_rc == (1 if obj["new"] else 0)
    assert err == md_err == ""


def test_b5_unscanned_ids_land_in_unscanned(scan, bed):
    rc, out, _ = scan("abcw", "--json", "--exit-code", "--baseline", bed["b_a_partial"])
    obj = json.loads(out)["baseline"]
    assert obj["new"] == ["GAP-802", "GAP-804"]
    assert (obj["scanned"], obj["unscanned"]) == ([], ["GAP-802", "GAP-804"])
    assert rc == 1


def test_b7_floor_only_shrinks_new(scan, bed):
    news, carried = [], []
    # "6" left the sweep in iter 384: beside `--exit-code` it is now refused.
    for floor in ("0", "2", "5"):
        _, out, _ = scan("abcw", "--json", "--exit-code", "--baseline", bed["b_aw"],
                         "--floor", floor)
        _, md, _ = scan("abcw", "--exit-code", "--baseline", bed["b_aw"], "--floor", floor)
        obj = json.loads(out)["baseline"]
        assert obj["new"] == _clause_ids(_line(md), "new above-floor PRESENT")
        news.append(set(obj["new"]))
        carried.append(obj["carried"])
    assert all(later <= earlier for earlier, later in zip(news, news[1:]))
    assert all(c == carried[0] for c in carried)
    rc, out, err = scan("abcw", "--json", "--exit-code", "--baseline", bed["b_aw"],
                        "--floor", "6")
    assert (rc, out) == (2, "") and "exceeds the highest confidence the evidence ladder can derive (5)" in err


def test_b8_markdown_has_no_json_artifacts(scan, bed):
    _, plain, _ = scan("abcw")
    _, gated, _ = scan("abcw", "--exit-code", "--baseline", bed["b_aw"])
    assert '"baseline"' not in plain + gated
    assert [ln for ln in gated.splitlines() if not ln.startswith("Baseline: ")] \
        == plain.splitlines()


@pytest.mark.parametrize("json_flag", [(), ("--json",)])
def test_b9_refusals_unchanged(scan, bed, json_flag):
    other = bed["root"] / "other"
    if not other.exists():
        _tree(other, {"A"}, name="elsewhere")
        rc, out, _ = _run(["scan", str(other / "elsewhere"), "--gaps", bed["reg"], "--json"])
        (bed["root"] / "b-other.json").write_text(out, encoding="utf-8")
        (bed["root"] / "not-scan.json").write_text("{}\n", encoding="utf-8")
    for extra in (["--baseline", bed["b_aw"]],
                  ["--exit-code", "--baseline", "no-such-file.json"],
                  ["--exit-code", "--baseline", "not-scan.json"],
                  ["--exit-code", "--baseline", "b-other.json"]):
        rc, out, err = scan("ab", *json_flag, *extra)
        assert (rc, out) == (2, ""), extra
        assert err.startswith("Error: "), (extra, err)


def test_b10_new_documents_round_trip_as_baselines(scan, bed):
    for spelling, carry in (("rt-null.json", []), ("rt-obj.json", ["--exit-code", "--baseline",
                                                                     bed["b_aw"]])):
        _, out, _ = scan("aw", "--json", *carry)
        (bed["root"] / spelling).write_text(out, encoding="utf-8")
        rc, gated, err = scan("abcw", "--json", "--exit-code", "--baseline", spelling)
        _, ref, _ = scan("abcw", "--json", "--exit-code", "--baseline", bed["b_aw"])
        assert (rc, err) == (1, "")
        got, want = json.loads(gated)["baseline"], json.loads(ref)["baseline"]
        assert {**got, "path": None} == {**want, "path": None}


def test_b11_byte_stable_single_newline(scan, bed):
    runs = [scan("abcw", "--json", "--exit-code", "--baseline", bed["b_aw"])[1]
            for _ in range(2)]
    assert runs[0] == runs[1]
    assert runs[0].endswith("}\n") and not runs[0].endswith("\n\n")


def test_b12_contract_documents_baseline_key():
    text = (pathlib.Path(__file__).resolve().parents[1] / "docs" /
            "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    for key in BASELINE_KEYS:
        assert f"`{key}`" in text
    assert "`baseline`" in text
