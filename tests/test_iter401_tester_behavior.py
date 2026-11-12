"""Iteration 401 (tester): `radar report` `## Identical evidence sets` -- black-box, spec 1-8.

Written from the spec alone (no implementation source read). Drives the public CLI
in-process (`cli.main`) over synthetic registers built in `tmp_path` on reserved
`.example` hosts. Behavior 1's "only the section moved" clause is checked against the
pre-feature commit `f9e8357` extracted with `git archive` (skipped when that commit is
not reachable, e.g. in a shallow checkout); behavior 8's census reads the committed
register and is cross-checked by an independent normalisation over `gaps/*.json`.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import pathlib
import subprocess
import sys
import tarfile

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.taxonomy import LAYERS

REPO = pathlib.Path(__file__).resolve().parents[1]
PRE_FEATURE_SHA = "f9e8357"
HEADING = "## Identical evidence sets"
TAG = "## Tag coverage"
BELOW = "## Below confidence floor"
HEADER = "| IDs | Layers | Documents |"
CENSUS = ("Records whose cited document set exactly matches another record's: "
          "{r} of {n} | groups: {g}")
L = list(LAYERS)


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def _report(root, *extra):
    code, out, err = _run(["report", root, *extra])
    assert code == 0, (code, err)
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out[-8:])
    return out


def _rec(gid, locators, layer=None, cls="first-party-field", title=None):
    return {
        "id": gid, "title": title or f"Tester record {gid}", "layer": layer or L[0],
        "gap_type": "missing-contract", "problem": "a problem", "symptom": "a symptom",
        "why_now": "now", "severity": 4, "frequency": 4, "tractability": 4,
        "existing": ["a partial fix"], "build_hypothesis": "a small wrapper",
        "evidence": [{"source_class": cls, "title": f"S{i}", "locator": loc,
                      "date": "2026-01-02", "quote": "a verbatim line"}
                     for i, loc in enumerate(locators)],
    }


def _reg(root, records):
    d = root / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    for r in records:
        (d / f"{r['id']}.json").write_text(json.dumps(r), encoding="utf-8")
    return root


def _section(out):
    assert out.count(HEADING + "\n") == 1
    start = out.index(HEADING + "\n")
    nxt = out.index("\n## ", start + len(HEADING))
    return out[start:nxt + 1]


def _rows(section):
    return [ln for ln in section.splitlines()
            if ln.startswith("| ") and ln != HEADER and not ln.startswith("| ---")]


def _parse(row):
    return [c.strip() for c in row.strip("|").split("|")]


SPEC_FIXTURE = [
    _rec("GAP-001", ["https://a.example/p", "https://b.example/q"]),
    _rec("GAP-002", ["https://A.example/p/", "https://b.example/q#s2"]),
    _rec("GAP-003", ["https://a.example/p"]),
    _rec("GAP-004", ["https://c.example/r"]),
]


# -- behavior 1: placement and exactly-once ------------------------------------
def test_b1_heading_once_between_tag_coverage_and_below_floor(tmp_path):
    out = _report(_reg(tmp_path, SPEC_FIXTURE))
    lines = out.splitlines()
    assert lines.count(HEADING) == 1
    assert lines.index(TAG) < lines.index(HEADING) < lines.index(BELOW)
    # Nothing else sits between Tag coverage's section and ours.
    between = out[out.index(TAG):out.index(HEADING)]
    assert between.count("\n## ") == 0


def _pre_feature_report(tmp_path, register_root, extra=()):
    if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", PRE_FEATURE_SHA + "^{commit}"],
                      capture_output=True).returncode != 0:
        pytest.skip("pre-feature commit not reachable in this checkout")
    tar = tmp_path / "src.tar"
    with tar.open("wb") as fh:
        subprocess.run(["git", "-C", str(REPO), "archive", PRE_FEATURE_SHA, "src"],
                       stdout=fh, check=True)
    old = tmp_path / "old"
    with tarfile.open(tar) as tf:
        tf.extractall(old, filter="data")
    driver = ("import sys; sys.path.insert(0, sys.argv[1]);"
              "from agent_gap_radar.cli import main; sys.exit(main(sys.argv[2:]))")
    res = subprocess.run([sys.executable, "-c", driver, str(old / "src"), "report",
                          str(register_root), *extra], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    return res.stdout


@pytest.mark.parametrize("extra", [(), ("--layer", L[0]), ("--match", "zz-no-such-text")])
def test_b1_only_the_section_was_inserted_vs_pre_feature(tmp_path, extra):
    root = _reg(tmp_path / "r", SPEC_FIXTURE + [
        _rec("GAP-005", ["https://d.example/s"], cls="model-output"),  # below floor
        _rec("GAP-006", ["https://d.example/s"], layer=L[1]),
    ])
    old = _pre_feature_report(tmp_path, root, extra)
    new = _report(root, *extra)
    sec = _section(new)
    assert HEADING not in old
    assert new.replace(sec, "", 1) == old


# -- behavior 2/6: census and purpose line ---------------------------------------
def test_b2_b6_census_then_purpose_layout(tmp_path):
    sec = _section(_report(_reg(tmp_path, SPEC_FIXTURE))).split("\n")
    assert sec[0] == HEADING and sec[1] == ""
    assert sec[2] == CENSUS.format(r=2, n=4, g=1)
    assert sec[3] == ""
    purpose = sec[4]
    assert "may be one gap filed twice" in purpose
    assert "no count in this section reaches priority, confidence, the ranking or the floor" in purpose
    assert "merged" in purpose and "hidden" in purpose
    assert sec[5] == ""
    assert sec[6] == HEADER


def test_b2_census_counts_grouped_records_and_template_is_fixed_for_singular(tmp_path):
    # Exactly one group of 3: R=3, G=1 -- "groups: 1" not "group: 1".
    recs = [_rec(f"GAP-01{i}", ["https://x.example/a"]) for i in range(3)]
    recs.append(_rec("GAP-020", ["https://y.example/b"]))
    sec = _section(_report(_reg(tmp_path, recs)))
    assert CENSUS.format(r=3, n=4, g=1) in sec.splitlines()


# -- behavior 3: table rows ------------------------------------------------------
def test_b3_rows_sorted_layers_in_taxonomy_order_no_cap(tmp_path):
    recs = []
    # 12 two-record groups, to exceed any plausible display cap (10).
    for k in range(12):
        loc = f"https://g{k:02d}.example/doc"
        recs.append(_rec(f"GAP-{200 + 2 * k:03d}", [loc]))
        recs.append(_rec(f"GAP-{201 + 2 * k:03d}", [loc]))
    # A 3-record group written with layers in REVERSE taxonomy order and ids out of order.
    tri = ["https://t.example/1", "https://t.example/2", "https://t.example/3"]
    recs += [_rec("GAP-109", tri, layer=L[-1]), _rec("GAP-107", tri, layer=L[3]),
             _rec("GAP-108", list(reversed(tri)), layer=L[-1])]
    sec = _section(_report(_reg(tmp_path, recs)))
    rows = [_parse(r) for r in _rows(sec)]
    assert len(rows) == 13
    assert [r[0].split(", ")[0] for r in rows] == sorted(r[0].split(", ")[0] for r in rows)
    assert rows[0] == ["GAP-107, GAP-108, GAP-109", f"{L[3]}, {L[-1]}", "3"]
    assert rows[1] == ["GAP-200, GAP-201", L[0], "1"]
    assert CENSUS.format(r=27, n=27, g=13) in sec.splitlines()
    assert sec.endswith("\n\n") or sec.rstrip("\n").splitlines()[-1].startswith("| ")


def test_b3_table_followed_by_blank_line(tmp_path):
    out = _report(_reg(tmp_path, SPEC_FIXTURE))
    sec = _section(out)
    body = sec.rstrip("\n").splitlines()
    assert body[-1].startswith("| ")
    assert sec.endswith(body[-1] + "\n\n")  # one blank line, then the next heading


# -- behavior 4: the spec fixture --------------------------------------------------
def test_b4_spec_fixture_exact_row(tmp_path):
    sec = _section(_report(_reg(tmp_path, SPEC_FIXTURE)))
    rows = _rows(sec)
    assert len(rows) == 1
    assert _parse(rows[0]) == ["GAP-001, GAP-002", L[0], "2"]
    assert "GAP-003" not in sec and "GAP-004" not in sec


def test_b4_case_slash_fragment_variants_are_one_document(tmp_path):
    recs = [_rec("GAP-031", ["https://h.example/Doc"]),
            _rec("GAP-032", ["https://H.EXAMPLE/doc/#frag"]),
            _rec("GAP-033", ["https://h.example/doc/other"])]
    rows = [_parse(r) for r in _rows(_section(_report(_reg(tmp_path, recs))))]
    assert rows == [["GAP-031, GAP-032", L[0], "1"]]


# -- behavior 5: no group / empty list -------------------------------------------
def test_b5_no_group_renders_zero_census_and_none_found(tmp_path):
    recs = [_rec("GAP-041", ["https://a.example/1"]), _rec("GAP-042", ["https://a.example/2"]),
            _rec("GAP-043", ["https://a.example/1", "https://a.example/2"])]
    sec = _section(_report(_reg(tmp_path, recs))).split("\n")
    assert sec[2] == CENSUS.format(r=0, n=3, g=0)
    assert sec[3] == "" and "may be one gap filed twice" in sec[4] and sec[5] == ""
    assert sec[6] == "None found."
    assert HEADER not in "\n".join(sec)


def test_b5_empty_record_list_renders_only_none_found(tmp_path):
    out = _report(_reg(tmp_path, SPEC_FIXTURE), "--match", "zz-no-such-text")
    assert _section(out) == HEADING + "\n\nNone found.\n\n"


# -- scope: narrowed like the other sections, below-floor included -----------------
def test_scope_layer_narrowing_splits_a_cross_layer_group(tmp_path):
    recs = [_rec("GAP-051", ["https://s.example/x"], layer=L[0]),
            _rec("GAP-052", ["https://s.example/x"], layer=L[1]),
            _rec("GAP-053", ["https://s.example/x"], layer=L[1])]
    root = _reg(tmp_path, recs)
    full = _section(_report(root))
    assert [_parse(r) for r in _rows(full)] == [["GAP-051, GAP-052, GAP-053", f"{L[0]}, {L[1]}", "1"]]
    narrowed = _section(_report(root, "--layer", L[0]))
    assert CENSUS.format(r=0, n=1, g=0) in narrowed.splitlines()
    assert "None found." in narrowed.splitlines()
    l1 = _section(_report(root, "--layer", L[1]))
    assert [_parse(r) for r in _rows(l1)] == [["GAP-052, GAP-053", L[1], "1"]]


def test_scope_match_narrowing(tmp_path):
    recs = [_rec("GAP-061", ["https://m.example/x"], title="needle alpha"),
            _rec("GAP-062", ["https://m.example/x"], title="needle beta"),
            _rec("GAP-063", ["https://m.example/x"], title="other")]
    sec = _section(_report(_reg(tmp_path, recs), "--match", "needle"))
    assert CENSUS.format(r=2, n=2, g=1) in sec.splitlines()
    assert [_parse(r)[0] for r in _rows(sec)] == ["GAP-061, GAP-062"]


def test_scope_below_floor_record_counted_and_still_below_floor(tmp_path):
    recs = [_rec("GAP-071", ["https://f.example/x"]),
            _rec("GAP-072", ["https://f.example/x"], cls="model-output")]
    out = _report(_reg(tmp_path, recs))
    sec = _section(out)
    assert [_parse(r)[0] for r in _rows(sec)] == ["GAP-071, GAP-072"]
    assert CENSUS.format(r=2, n=2, g=1) in sec.splitlines()
    below = out[out.index(BELOW):]
    ranked = out[:out.index(TAG)]
    assert "GAP-072" in below
    assert "GAP-071" in ranked and "GAP-071" not in below


# -- behavior 7: display-only --------------------------------------------------------
def _list(root):
    code, out, err = _run(["list", root, "--json"])
    assert code == 0 and err == ""
    return {r["gap_id"]: (r["confidence"], r["priority"], r["below_floor"])
            for r in json.loads(out)["records"]}


def test_b7_group_membership_moves_no_score(tmp_path):
    together = _list(_reg(tmp_path / "all", SPEC_FIXTURE))
    for rec in SPEC_FIXTURE[:2]:
        alone = _list(_reg(tmp_path / rec["id"], [rec]))
        assert together[rec["id"]] == alone[rec["id"]]


def test_b7_report_sections_outside_ours_unchanged_by_grouping(tmp_path):
    # Same records, but GAP-002's locator moved off the shared set: no group forms.
    split = [dict(r) for r in SPEC_FIXTURE]
    split[1] = _rec("GAP-002", ["https://A.example/p/", "https://z.example/elsewhere"])
    grouped = _report(_reg(tmp_path / "g", SPEC_FIXTURE))
    ungrouped = _report(_reg(tmp_path / "u", split))
    assert grouped[grouped.index(BELOW):] == ungrouped[ungrouped.index(BELOW):]
    assert _list(tmp_path / "g")["GAP-002"][:3] == _list(tmp_path / "u")["GAP-002"][:3]


# -- behavior 8: determinism, contract, committed census -------------------------------
def test_b8_byte_identical_reruns(tmp_path):
    root = _reg(tmp_path, SPEC_FIXTURE)
    assert _report(root) == _report(root)


def _independent_census():
    sets = {}
    for p in sorted((REPO / "gaps").glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        sets[rec["id"]] = frozenset(e["locator"].split("#")[0].rstrip("/").lower()
                                    for e in rec["evidence"])
    by = {}
    for gid, s in sets.items():
        by.setdefault(s, []).append(gid)
    groups = [g for g in by.values() if len(g) >= 2]
    return len(sets), sum(map(len, groups)), len(groups)


def test_b8_committed_register_census(tmp_path):
    out = _report(REPO)
    n, r, g = _independent_census()
    assert (r, n, g) == (17, 120, 8)  # spec figure at HEAD f9e8357
    assert CENSUS.format(r=r, n=n, g=g) in _section(out).splitlines()
    assert (REPO / "REGISTER.md").read_text(encoding="utf-8") == out


def test_b8_committed_pairs_match_independent_grouping():
    out = _report(REPO)
    rows = [_parse(x)[0].split(", ") for x in _rows(_section(out))]
    sets = {}
    for p in (REPO / "gaps").glob("*.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        sets[rec["id"]] = frozenset(e["locator"].split("#")[0].rstrip("/").lower()
                                    for e in rec["evidence"])
    pairs = {tuple(sorted((a, b))) for a, b in itertools.combinations(sets, 2)
             if sets[a] == sets[b]}
    shown = {tuple(sorted(c)) for row in rows for c in itertools.combinations(row, 2)}
    assert shown == pairs and len(pairs) == 10
