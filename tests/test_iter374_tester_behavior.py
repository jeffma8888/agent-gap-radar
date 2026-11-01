"""Iteration 374 (tester): black-box pins for `scan --json`'s `baseline` key.

Drives `main()` in-process on tmp targets and reads stdout / stderr / exit code only.
The fixture reuses iteration 305's register (GAP-801/802/804 above the floor,
GAP-803 a model-output record that sits below it), so every comparison here is
against the markdown `Baseline:` line that module already pins.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from test_iter305_behavior import GAP, REGISTER, _run, _tree

KEY_ORDER = ["target", "target_name", "confidence_floor", "layer", "records_applied",
             "counts", "uncheckable", "findings", "baseline"]
BASELINE_KEYS = ["path", "carried", "new", "scanned", "unscanned"]
LINE = re.compile(
    r"^Baseline: (?P<path>.+) -- carried PRESENT: (?P<k>\d+); "
    r"new above-floor PRESENT: (?P<m>\d+) \((?P<new>[^)]*)\); "
    r"scanned by the baseline: (?P<r>\d+) \((?P<scanned>[^)]*)\); "
    r"unscanned by the baseline: (?P<u>\d+) \((?P<unscanned>[^)]*)\)$")


@pytest.fixture(scope="module")
def bed(tmp_path_factory):
    root = tmp_path_factory.mktemp("iter374t")
    reg = root / "reg" / "gaps"
    reg.mkdir(parents=True)
    for rec in REGISTER:
        (reg / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    trees = {
        "none": _tree(root / "t_none", set()),
        "a": _tree(root / "t_a", {"A"}),
        "aw": _tree(root / "t_aw", {"A", "W"}),
        "ab": _tree(root / "t_ab", {"A", "B"}),
        "abcw": _tree(root / "t_abcw", {"A", "B", "C", "W"}),
    }
    base = root / "bases"
    base.mkdir()

    def write(name, tree, *extra, edit=None):
        rc, out, err = _run(["scan", str(trees[tree]), "--gaps", str(reg), "--json", *extra])
        assert (rc, err) == (0, ""), (name, rc, err)
        if edit is not None:
            doc = json.loads(out)
            edit(doc)
            out = json.dumps(doc, indent=2) + "\n"
        (base / name).write_text(out, encoding="utf-8")
        return name

    def flip_802_absent(doc):
        for f in doc["findings"]:
            if f["gap_id"] == GAP["B"]:
                f["verdict"] = "ABSENT"

    def drop_key(doc):
        doc.pop("baseline", None)

    names = {
        "none": write("none.json", "none"),
        "aw": write("aw.json", "aw"),
        "ab_flipped": write("ab_flipped.json", "ab", edit=flip_802_absent),
        "narrow": write("narrow.json", "a", "--gap", GAP["A"]),
        "abcw": write("abcw.json", "abcw"),
        "aw_headera": write("aw_headera.json", "aw", edit=drop_key),
    }
    return {"root": root, "reg": reg, "trees": trees, "base": base, "names": names}


@pytest.fixture
def incwd(bed, monkeypatch):
    """Run from the baselines dir so `--baseline` is spelled relative."""
    monkeypatch.chdir(bed["base"])
    return bed


def _gate(bed, tree, bname, *extra, json_=True):
    argv = ["scan", str(bed["trees"][tree]), "--gaps", str(bed["reg"]), "--exit-code",
            "--baseline", bname, *extra]
    if json_:
        argv.append("--json")
    return _run(argv)


def _ids(clause):
    return [] if clause == "none" else clause.split(", ")


def _line(doc):
    lines = [ln for ln in doc.splitlines() if ln.startswith("Baseline: ")]
    assert len(lines) == 1, lines
    m = LINE.match(lines[0])
    assert m, lines[0]
    return m


CASES = [("abcw", "none"), ("abcw", "aw"), ("abcw", "ab_flipped"), ("abcw", "narrow"),
         ("abcw", "abcw"), ("aw", "aw"), ("none", "aw"), ("ab", "narrow")]


# 1 -- null and last without --baseline; rest of the payload unchanged.
def test_t1_baseline_null_and_last(bed):
    rc, out, err = _run(["scan", str(bed["trees"]["ab"]), "--gaps", str(bed["reg"]), "--json"])
    assert (rc, err) == (0, "")
    doc = json.loads(out)
    assert list(doc) == KEY_ORDER
    assert doc["baseline"] is None
    assert '"baseline": null' in out


def test_t1_exit_code_alone_stays_and_key_null(bed):
    rc, out, err = _run(["scan", str(bed["trees"]["ab"]), "--gaps", str(bed["reg"]), "--json",
                         "--exit-code"])
    assert (rc, err) == (1, "")
    assert json.loads(out)["baseline"] is None


# 2 -- object with exactly the five keys, in order.
@pytest.mark.parametrize("tree,bkey", CASES)
def test_t2_object_key_order(incwd, tree, bkey):
    rc, out, err = _gate(incwd, tree, incwd["names"][bkey])
    assert err == ""
    doc = json.loads(out)
    assert list(doc) == KEY_ORDER
    assert isinstance(doc["baseline"], dict)
    assert list(doc["baseline"]) == BASELINE_KEYS


# 2b -- the payload minus `baseline` equals the payload without --baseline.
@pytest.mark.parametrize("tree,bkey", CASES)
def test_t2_rest_of_payload_unchanged_by_baseline(incwd, tree, bkey):
    _, out, _ = _gate(incwd, tree, incwd["names"][bkey])
    _, plain, _ = _run(["scan", str(incwd["trees"][tree]), "--gaps", str(incwd["reg"]),
                        "--json", "--exit-code"])
    a, b = json.loads(out), json.loads(plain)
    assert b.pop("baseline") is None
    a.pop("baseline")
    assert a == b


# 3 -- path verbatim, relative stays relative, no absolute path leaks.
@pytest.mark.parametrize("spelling", ["aw.json", "./aw.json", "../bases/aw.json"])
def test_t3_path_verbatim(incwd, spelling):
    rc, out, err = _gate(incwd, "abcw", spelling)
    assert err == ""
    obj = json.loads(out)["baseline"]
    assert obj["path"] == spelling
    assert str(incwd["root"]) not in json.dumps(obj)
    _, md, _ = _gate(incwd, "abcw", spelling, json_=False)
    assert _line(md).group("path") == spelling


# 4 -- carried = every PRESENT id in B at any confidence (below-floor included).
def test_t4_carried_includes_below_floor(incwd):
    b = json.loads((incwd["base"] / "aw.json").read_text(encoding="utf-8"))
    w = [f for f in b["findings"] if f["gap_id"] == GAP["W"]]
    assert w and w[0]["verdict"] == "PRESENT" and w[0]["below_floor"] is True, w
    _, out, _ = _gate(incwd, "abcw", "aw.json")
    assert json.loads(out)["baseline"]["carried"] == sorted([GAP["A"], GAP["W"]])


@pytest.mark.parametrize("tree,bkey", CASES)
def test_t4_carried_matches_baseline_document(incwd, tree, bkey):
    name = incwd["names"][bkey]
    b = json.loads((incwd["base"] / name).read_text(encoding="utf-8"))
    want = sorted(f["gap_id"] for f in b["findings"] if f["verdict"] == "PRESENT")
    _, out, _ = _gate(incwd, tree, name)
    obj = json.loads(out)["baseline"]
    assert obj["carried"] == want
    assert int(_line(_gate(incwd, tree, name, json_=False)[1]).group("k")) == len(want)


# 5 -- lists equal the markdown clauses id for id; [] never "none"; partition algebra.
@pytest.mark.parametrize("tree,bkey", CASES)
def test_t5_lists_equal_markdown_clauses(incwd, tree, bkey):
    name = incwd["names"][bkey]
    _, out, _ = _gate(incwd, tree, name)
    _, md, _ = _gate(incwd, tree, name, json_=False)
    obj, m = json.loads(out)["baseline"], _line(md)
    for key in ("new", "scanned", "unscanned"):
        assert isinstance(obj[key], list) and "none" not in obj[key]
        assert obj[key] == _ids(m.group(key)), key
        assert obj[key] == sorted(obj[key])
    assert len(obj["new"]) == int(m.group("m"))
    assert set(obj["scanned"]) | set(obj["unscanned"]) == set(obj["new"])
    assert not set(obj["scanned"]) & set(obj["unscanned"])


def test_t5_each_partition_shape_is_reached(incwd):
    """The CASES above really exercise empty, scanned-only and unscanned-only results."""
    seen = {}
    for tree, bkey in (("abcw", "abcw"), ("ab", "ab_flipped"), ("ab", "narrow")):
        _, out, _ = _gate(incwd, tree, incwd["names"][bkey])
        seen[bkey] = json.loads(out)["baseline"]
    assert seen["abcw"]["new"] == [] and seen["abcw"]["scanned"] == []
    assert seen["abcw"]["unscanned"] == []
    assert seen["ab_flipped"]["scanned"] == [GAP["B"]] and seen["ab_flipped"]["unscanned"] == []
    assert seen["ab_flipped"]["new"] == [GAP["B"]]
    assert seen["narrow"]["unscanned"] == [GAP["B"]] and seen["narrow"]["scanned"] == []


# 6 -- exit 1 iff new non-empty; equal to the markdown invocation's code.
@pytest.mark.parametrize("tree,bkey", CASES)
def test_t6_exit_code_follows_new(incwd, tree, bkey):
    name = incwd["names"][bkey]
    rc, out, _ = _gate(incwd, tree, name)
    rc_md, _, _ = _gate(incwd, tree, name, json_=False)
    assert rc == (1 if json.loads(out)["baseline"]["new"] else 0)
    assert rc == rc_md


# 7 -- raising --floor can only shrink `new`; carried constant; markdown moves identically.
@pytest.mark.parametrize("tree,bkey", [("abcw", "none"), ("abcw", "aw"), ("ab", "narrow")])
def test_t7_floor_monotone(incwd, tree, bkey):
    name = incwd["names"][bkey]
    prev_new, carried = None, None
    for n in range(0, 11):
        rc, out, err = _gate(incwd, tree, name, "--floor", str(n))
        if rc == 2:
            assert out == "" and err.startswith("Error: "), (n, err)
            continue
        obj = json.loads(out)["baseline"]
        _, md, _ = _gate(incwd, tree, name, "--floor", str(n), json_=False)
        assert obj["new"] == _ids(_line(md).group("new")), n
        if prev_new is not None:
            assert set(obj["new"]) <= set(prev_new), (n, obj["new"], prev_new)
        carried = obj["carried"] if carried is None else carried
        assert obj["carried"] == carried, n
        prev_new = obj["new"]
    assert prev_new is not None


# 8 -- markdown: only the Baseline line differs from the flagless document.
@pytest.mark.parametrize("tree,bkey", CASES)
def test_t8_markdown_only_gains_the_line(incwd, tree, bkey):
    _, md, _ = _gate(incwd, tree, incwd["names"][bkey], json_=False)
    _, plain, _ = _run(["scan", str(incwd["trees"][tree]), "--gaps", str(incwd["reg"]),
                        "--exit-code"])
    kept = [ln for ln in md.splitlines(keepends=True) if not ln.startswith("Baseline: ")]
    assert "".join(kept) == plain
    assert "{" not in _line(md).group(0) and "[" not in _line(md).group(0)


# 9 -- refusals unchanged with or without --json.
@pytest.mark.parametrize("json_", [False, True])
@pytest.mark.parametrize("kind", ["no_exit_code", "not_file", "not_scan", "mismatch"])
def test_t9_refusals(incwd, json_, kind):
    tree = str(incwd["trees"]["abcw"])
    reg = str(incwd["reg"])
    (incwd["base"] / "junk.json").write_text('{"x": 1}\n', encoding="utf-8")
    other = _tree(incwd["root"] / f"other_{kind}_{json_}", {"A"}, name="elsewhere")
    _, odoc, _ = _run(["scan", str(other), "--gaps", reg, "--json"])
    (incwd["base"] / "other.json").write_text(odoc, encoding="utf-8")
    argv = {
        "no_exit_code": ["scan", tree, "--gaps", reg, "--baseline", "aw.json"],
        "not_file": ["scan", tree, "--gaps", reg, "--exit-code", "--baseline", "missing.json"],
        "not_scan": ["scan", tree, "--gaps", reg, "--exit-code", "--baseline", "junk.json"],
        "mismatch": ["scan", tree, "--gaps", reg, "--exit-code", "--baseline", "other.json"],
    }[kind]
    if json_:
        argv.append("--json")
    try:
        rc, out, err = _run(argv)
    except SystemExit as exc:  # argparse-level refusal
        rc, out, err = exc.code, "", "Error: "
    assert rc == 2 and out == "", (kind, rc, out)
    assert err.startswith("Error: ") or "\nError: " in err or "error" in err.lower(), err


# 10 -- this version's documents round-trip as baselines, same verdict as a HEAD-era doc.
def test_t10_round_trip(incwd):
    a_null = json.loads((incwd["base"] / "aw.json").read_text(encoding="utf-8"))
    assert a_null["baseline"] is None
    head_era = json.loads((incwd["base"] / "aw_headera.json").read_text(encoding="utf-8"))
    assert "baseline" not in head_era
    rc_obj, obj_doc, err = _gate(incwd, "aw", "aw.json")
    assert err == "" and isinstance(json.loads(obj_doc)["baseline"], dict)
    (incwd["base"] / "with_obj.json").write_text(obj_doc, encoding="utf-8")
    results = []
    for name in ("aw.json", "aw_headera.json", "with_obj.json"):
        rc, out, err = _gate(incwd, "abcw", name)
        assert err == "", (name, err)
        obj = json.loads(out)["baseline"]
        obj.pop("path")
        results.append((rc, obj))
    assert results[0] == results[1] == results[2]
    assert results[0][0] == 1 and results[0][1]["new"] == [GAP["B"], GAP["C"]]


# 11 -- byte stability, exactly one trailing newline.
@pytest.mark.parametrize("json_", [False, True])
def test_t11_byte_stable_one_newline(incwd, json_):
    first = _gate(incwd, "abcw", "narrow.json", json_=json_)
    second = _gate(incwd, "abcw", "narrow.json", json_=json_)
    assert first == second
    assert first[1].endswith("\n") and not first[1].endswith("\n\n")


# 12 -- consumer contract documents the key and its nested object.
CONTRACT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "CONSUMER_CONTRACT.md"


def test_t12_contract_documents_baseline_key():
    text = CONTRACT.read_text(encoding="utf-8")
    para = text[text.index("**`scan --json` SHIPPED.**"):]
    enum = para[:para.index(". ")]
    assert "`findings`, `baseline`," in enum
    for nested in BASELINE_KEYS:
        assert f"`{nested}`" not in enum, nested
    tail = para[len(enum):]
    for nested in BASELINE_KEYS:
        assert f"`{nested}`" in tail, nested


def test_t12_surface_table_no_longer_claims_byte_identical():
    text = CONTRACT.read_text(encoding="utf-8")
    row = next(ln for ln in text.splitlines() if ln.startswith("| `radar scan <target>"))
    cell = row[row.index("`--baseline BASELINE` names"):]
    assert "payload is byte-identical to the same invocation without the flag" not in cell
    assert "`baseline` key" in cell
