"""Iteration 427 behaviors: ``radar scan`` skips radar's OWN scan documents.

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-10, the README/contract and from running the CLI; no test
was written from the implementation source, the engineer's or reviewer's notes,
or any diff.

Ship hazards: no sha, no ``git show HEAD`` baseline and no file:line locator of a
ship-rewritten file (H1) -- "default bytes unchanged" is pinned as an INVARIANCE
(the document of the target holding scan documents, minus its one disclosure
line / key, equals the clean target's document byte for byte) plus a FIXED
flagless key list.  No wall-clock bound (H2), no extras (H3).

All fixtures are built ONCE at module scope and every CLI call runs in a few
child interpreters that take a JSON job list on stdin (``main()`` per job).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"

CHILD = r"""
import contextlib, io, json, os, sys
from agent_gap_radar.cli import main
jobs = json.loads(sys.stdin.read())
res = []
for args in jobs:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(args)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    res.append([rc or 0, out.getvalue(), err.getvalue()])
sys.stdout.write(json.dumps(res))
"""

BENCH = "# benchmark harness\n\nscore = 0\n"
README_T = "# demo\n"
SHA_PROSE = "the image is pinned at repo@sha256:0123abcd and a lockfile hash\n"

FLAGLESS_KEYS = [
    "target", "target_name", "confidence_floor", "layer", "records_applied",
    "counts", "uncheckable", "findings", "baseline",
]
SEVEN = ["target", "target_name", "confidence_floor", "records_applied",
         "counts", "findings", "baseline"]
DOCS = ["radar-baseline.json", "radar-scan.md"]
MD_LINE = ("Radar documents: `radar-baseline.json`, `radar-scan.md` -- 2 target "
           "file(s) not scanned (radar's own scan output)")

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")


def _batch(jobs: list[list[str]]) -> list[tuple[int, str, str]]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONHASHSEED"] = "0"
    proc = subprocess.run(
        [sys.executable, "-c", CHILD], input=json.dumps(jobs), cwd=REPO, env=env,
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stderr
    return [tuple(r) for r in json.loads(proc.stdout)]


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, env=GIT_ENV, check=True, capture_output=True)


def _write(root: pathlib.Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _git_target(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    root.mkdir(parents=True)
    _write(root, files)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _commit_all(root: pathlib.Path, msg: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)


def _json_doc(missing: str | None = None) -> str:
    d = {"target": "x", "target_name": "x", "confidence_floor": 3,
         "records_applied": 1, "counts": {}, "findings": [], "baseline": None}
    if missing:
        d.pop(missing)
    d["note"] = SHA_PROSE
    return json.dumps(d, indent=2) + "\n"


NEGATIVES = {
    "md_third_line": ("notes/x.md", "# Gap scan: x\n\nSomething else\n" + SHA_PROSE),
    "invalid_json": ("notes/bad.json", '{"records_applied": 1, "note": "' + SHA_PROSE.strip() + '"\n'),
    **{f"json_no_{k}": ("notes/x.json", _json_doc(k)) for k in SEVEN},
}
POSITIVES = {
    "min_md": ("notes/x.md", "# Gap scan: x\n\nTarget: `y`\n" + SHA_PROSE),
    "min_json": ("notes/x.json", _json_doc()),
}


def _scan(t: pathlib.Path, *extra: str) -> list[str]:
    return ["scan", str(t), *extra]


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git unavailable")
    base = tmp_path_factory.mktemp("iter427")
    t = _git_target(base / "T", {"app/bench.py": BENCH, "README.md": README_T})
    pre = _batch([
        _scan(t, "--gap", "GAP-020", "--exit-code"),   # 0 S0
        _scan(t, "--json"),                            # 1
        _scan(t),                                      # 2
    ])
    # step 2: the README's gate recipe, run inside the target
    _write(t, {"radar-baseline.json": pre[1][1], "radar-scan.md": pre[2][1]})
    _commit_all(t, "baseline")
    outside = base / "outside-baseline.json"
    outside.write_text(pre[1][1], encoding="utf-8")
    # a baseline that did not carry GAP-020: the gate must then go red
    mod = json.loads(pre[1][1])
    for f in mod["findings"]:
        if f["gap_id"] == "GAP-020":
            f["verdict"], f["locations"] = "NOT_APPLICABLE", []
    mod["counts"]["PRESENT"] -= 1
    mod["counts"]["NOT_APPLICABLE"] += 1
    nogap = base / "no-gap020-baseline.json"
    nogap.write_text(json.dumps(mod, indent=2) + "\n", encoding="utf-8")
    # 9: a plain directory copy (no .git)
    plain = base / "plain"
    shutil.copytree(t, plain, ignore=shutil.ignore_patterns(".git"))
    # 5: the baseline committed under a neutral name
    renamed = _git_target(base / "R", {"app/bench.py": BENCH, "README.md": README_T,
                                       "notes/ci.out": pre[1][1]})
    shapes = {}
    for name, (rel, body) in {**NEGATIVES, **POSITIVES}.items():
        shapes[name] = _git_target(base / f"S-{name}", {"app/bench.py": BENCH,
                                                        "README.md": README_T, rel: body})
    jobs = {
        "s1": _scan(t, "--gap", "GAP-020", "--exit-code"),
        "s1_md": _scan(t, "--gap", "GAP-020"),
        "s1_json": _scan(t, "--gap", "GAP-020", "--json"),
        "json": _scan(t, "--json"),
        "md": _scan(t),
        "excl_json": _scan(t, "--json", "--exclude", "radar-scan.md"),
        "excl_md": _scan(t, "--exclude", "radar-scan.md"),
        "gate_inside": _scan(t, "--exit-code", "--baseline", str(t / "radar-baseline.json")),
        "gate_outside": _scan(t, "--exit-code", "--baseline", str(outside)),
        "gate_nogap": _scan(t, "--exit-code", "--baseline", str(nogap)),
        "plain_json": _scan(plain, "--json"),
        "renamed_json": _scan(renamed, "--json"),
        "renamed_md": _scan(renamed),
        "self_json": _scan(REPO, "--json"),
        "self_md": _scan(REPO),
    }
    for name, st in shapes.items():
        jobs[f"shape_{name}"] = _scan(st, "--json", "--gap", "GAP-020")
    names = list(jobs)
    res = dict(zip(names, _batch([jobs[n] for n in names])))
    # 8: a baseline document that itself CARRIES radar_documents is accepted
    carrying = base / "carrying-baseline.json"
    carrying.write_text(res["json"][1], encoding="utf-8")
    (res["gate_carrying"],) = _batch([_scan(t, "--exit-code", "--baseline", str(carrying))])
    return {"t": t, "pre": pre, "res": res, "outside": outside, "carrying": carrying}


def _ok(r: tuple[int, str, str], rc: int = 0) -> str:
    assert r[0] == rc, r
    assert r[1].endswith("\n") and not r[1].endswith("\n\n"), repr(r[1][-20:])
    return r[1]


def _f(doc: dict, gap: str) -> dict:
    (f,) = [f for f in doc["findings"] if f["gap_id"] == gap]
    return f


def _no_doc_locator(doc: dict, names=("radar-baseline.json", "radar-scan.md")) -> None:
    for f in doc["findings"]:
        for loc in f["locations"]:
            assert not any(loc.startswith(n) for n in names), (f["gap_id"], loc)


# -- 1: the measured fail-open is closed (regression fixture) --
def test_b1_s0_is_red_before_the_baseline_is_committed(world):
    assert world["pre"][0][0] == 1, world["pre"][0]


def test_b1_gate_stays_red_after_committing_the_recipe_output(world):
    assert world["res"]["s1"][0] == 1, world["res"]["s1"]


def test_b1_json_gap020_present_at_bench_and_no_document_locator(world):
    r = world["res"]
    d = json.loads(_ok(r["s1_json"]))
    f = _f(d, "GAP-020")
    assert f["verdict"] == "PRESENT"
    assert f["locations"] and all(l.startswith("app/bench.py") for l in f["locations"])
    full = json.loads(_ok(r["json"]))
    _no_doc_locator(full)
    assert full["counts"]["ABSENT"] == json.loads(world["pre"][1][1])["counts"]["ABSENT"]


def test_b1_markdown_gap020_in_present_section_no_document_evidence(world):
    md = _ok(world["res"]["s1_md"])
    present = md[md.index("## Actionable now (PRESENT"):md.index("## Needs a human answer")]
    assert "### GAP-020 " in present
    assert "`app/bench.py:3`" in present
    absent = md[md.index("## Positively mitigated (ABSENT)"):]
    assert "GAP-020" not in absent
    assert "radar-baseline.json:" not in md and "radar-scan.md:" not in md


# -- 2: verdicts equal the clean target --
def test_b2_counts_and_verdict_list_equal_the_clean_target(world):
    before = json.loads(world["pre"][1][1])
    after = json.loads(_ok(world["res"]["json"]))
    assert after["counts"] == before["counts"]
    pairs = lambda d: [(f["gap_id"], f["verdict"]) for f in d["findings"]]
    assert pairs(after) == pairs(before)


# -- 3: markdown disclosure --
def test_b3_markdown_line_directly_after_target(world):
    lines = _ok(world["res"]["md"]).split("\n")
    i = next(i for i, l in enumerate(lines) if l.startswith("Target: "))
    assert lines[i + 1] == MD_LINE
    assert lines.count(MD_LINE) == 1


# -- 4: JSON disclosure --
def test_b4_json_key_value_and_position(world):
    d = json.loads(_ok(world["res"]["json"]))
    assert d["radar_documents"] == DOCS
    assert list(d) == FLAGLESS_KEYS[:4] + ["radar_documents"] + FLAGLESS_KEYS[4:]


# -- 5: recognised by shape, not by name --
def test_b5_renamed_baseline_is_still_listed_and_skipped(world):
    r = world["res"]
    d = json.loads(_ok(r["renamed_json"]))
    assert d["radar_documents"] == ["notes/ci.out"]
    _no_doc_locator(d, ("notes/ci.out",))
    assert _f(d, "GAP-020")["verdict"] == "PRESENT"
    assert ("Radar documents: `notes/ci.out` -- 1 target file(s) not scanned "
            "(radar's own scan output)") in _ok(r["renamed_md"]).split("\n")


@pytest.mark.parametrize("name", sorted(POSITIVES))
def test_b5_minimal_shapes_are_recognised(world, name):
    d = json.loads(_ok(world["res"][f"shape_{name}"]))
    assert d["radar_documents"] == [POSITIVES[name][0]]
    assert _f(d, "GAP-020")["verdict"] == "PRESENT"


@pytest.mark.parametrize("name", sorted(NEGATIVES))
def test_b5_near_shapes_are_not_recognised_and_still_scanned(world, name):
    rel = NEGATIVES[name][0]
    d = json.loads(_ok(world["res"][f"shape_{name}"]))
    assert "radar_documents" not in d
    assert list(d) == FLAGLESS_KEYS
    f = _f(d, "GAP-020")
    # the near-shape file is read like any other: its prose still mitigates
    assert f["verdict"] == "ABSENT", f
    assert any(l.startswith(rel) for l in f["locations"]), f["locations"]


# -- 6: default bytes unchanged --
def test_b6_clean_target_has_fixed_keys_and_no_line(world):
    pre = world["pre"]
    assert list(json.loads(pre[1][1])) == FLAGLESS_KEYS
    assert "Radar documents:" not in pre[2][1]


def test_b6_disclosure_is_the_only_difference_from_the_clean_target(world):
    r, pre = world["res"], world["pre"]
    md = _ok(r["md"])
    assert "\n".join(l for l in md.split("\n") if l != MD_LINE) == pre[2][1]
    d = json.loads(_ok(r["json"]))
    d.pop("radar_documents")
    clean = json.loads(pre[1][1])
    assert d == clean
    assert list(d) == list(clean)


def test_b6_self_scan_carries_no_disclosure(world):
    r = world["res"]
    d = json.loads(r["self_json"][1])
    assert r["self_json"][0] in (0, 1), r["self_json"][2]
    assert "radar_documents" not in d
    assert [k for k in d if k in FLAGLESS_KEYS] == FLAGLESS_KEYS
    assert "Radar documents:" not in r["self_md"][1]


# -- 7: --exclude interplay --
def test_b7_excluded_document_counted_once_under_exclude_only(world):
    d = json.loads(_ok(world["res"]["excl_json"]))
    assert d["radar_documents"] == ["radar-baseline.json"]
    assert d["exclude"]["files"] == 1
    keys = list(d)
    assert keys.index("layer") < keys.index("exclude") < keys.index("radar_documents")
    assert keys[keys.index("radar_documents") + 1] == "records_applied"


def test_b7_markdown_radar_line_follows_excluded_line(world):
    lines = _ok(world["res"]["excl_md"]).split("\n")
    i = next(i for i, l in enumerate(lines) if l.startswith("Target: "))
    assert lines[i + 1].startswith("Excluded: `radar-scan.md` -- 1 target file(s)")
    assert lines[i + 2] == ("Radar documents: `radar-baseline.json` -- 1 target file(s) "
                            "not scanned (radar's own scan output)")


# -- 8: the gate recipe works on itself --
def _baseline_line(out: str, path: pathlib.Path) -> str:
    (line,) = [l for l in out.split("\n") if l.startswith("Baseline: ")]
    prefix = f"Baseline: {path} -- "
    assert line.startswith(prefix), line
    return line[len(prefix):]


def test_b8_inside_baseline_carries_gap020_and_matches_outside_copy(world):
    r, t = world["res"], world["t"]
    inside = _baseline_line(_ok(r["gate_inside"], 0), t / "radar-baseline.json")
    outside = _baseline_line(_ok(r["gate_outside"], 0), world["outside"])
    assert inside.startswith("carried PRESENT: 2; new above-floor PRESENT: 0 (none); ")
    assert inside == outside


def test_b8_gate_is_red_iff_a_new_above_floor_present_exists(world):
    out = world["res"]["gate_nogap"]
    assert out[0] == 1, out
    assert "new above-floor PRESENT: 1 (GAP-020)" in out[1]


def test_b8_baseline_carrying_radar_documents_is_accepted(world):
    assert "radar_documents" in json.loads(world["carrying"].read_text(encoding="utf-8"))
    r = world["res"]["gate_carrying"]
    assert r[0] == 0 and r[2] == "", r
    assert "new above-floor PRESENT: 0 (none)" in r[1]


# -- 9: non-git target --
def test_b9_plain_copy_lists_the_same_documents_and_counts(world):
    d = json.loads(_ok(world["res"]["plain_json"]))
    assert d["radar_documents"] == DOCS
    assert d["counts"] == json.loads(world["pre"][1][1])["counts"]
    _no_doc_locator(d)


# -- 10: contract --
def _scan_row() -> str:
    rows = [l for l in CONTRACT.read_text(encoding="utf-8").split("\n")
            if l.startswith("| `radar scan ")]
    assert len(rows) == 1, len(rows)
    return rows[0]


def test_b10_contract_states_recognition_rule_and_disclosure():
    row = _scan_row()
    for needle in ("# Gap scan: ", "Target: ", "applies_when", "present_when",
                   "mitigated_when", "radar_documents", "Radar documents:",
                   "radar's own scan output", "by SHAPE"):
        assert needle in row, needle
    for k in SEVEN:
        assert f"`{k}`" in row, k
    low = row.lower()
    assert "absent when no" in low
    assert "no rule" in low
