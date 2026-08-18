"""Iteration 15 behaviors: `radar scan` decodes each target file at most once per scan.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every behavioral assertion
drives the public CLI entry point (`main`) or the published `scan` / `scan_json` /
`render_scan` API and observes only the document bytes, the exit code, the stderr bytes,
or a COUNT of real filesystem decodes.

Two counters, and the difference between them is the whole point of this iteration:

* `reads` counts calls to the read seam the spec names (`checks._read`) -- how many times
  the rules ASK for a file's text.
* `decodes` counts `pathlib.Path.read_text` calls under the target -- how many times the
  filesystem is actually made to produce that text. This is the STDLIB seam, chosen
  deliberately over any product-private helper so the count means the same thing on an
  implementation that memoises differently. It was validated by measurement, not by
  reading source: on the pre-change tree these two counters are EQUAL (24 and 24 on the
  fixture below), which is what makes `decodes < reads` a falsifiable claim rather than a
  restatement.

The fixture is AMPLIFIED on purpose -- four rules reach every file, so `reads` is 4x the
distinct-file count -- and behavior 2 asserts the amplification separately. Without that
guard, `decodes == distinct_files` would be equally green on a scan that read nothing at
all, which is the vacuous-census shape this suite has been bitten by before.

What this file does NOT prove, stated so a green dot cannot be mistaken for it: it cannot
show the documents are byte-identical to the documents the PREVIOUS tree produced, because
only one tree is importable from inside the suite. It pins byte-STABILITY (two scans, one
process, same bytes) and the one-newline tail; the cross-tree byte equality was measured
out of band and is reported in the iteration's tester report.

Registers and targets are built in `tmp_path`. Nothing under `gaps/` is read to make an
assertion true -- that register is grown by an unattended research pass, so a keyed
expectation over it would go red against a CORRECT register.
"""

from __future__ import annotations

import contextlib
import json
import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar import scan as scan_mod
from agent_gap_radar.checks import MAX_FILE_BYTES, Verdict, read_cache_scope, run_check
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import render_scan, scan, scan_json

#: Planted in the target tree. The fixture checks fire on exactly this token, so every
#: verdict below is a property of the fixture and never of the published register.
MARKER = "GAPRADAR_ITER15_MARKER"

#: Planted only where a MITIGATION is wanted, in non-test code.
MITIGATION = "GAPRADAR_ITER15_MITIGATION"


# ---------------------------------------------------------------------------
# Fixture builders. Local rather than imported from test_iter02_behavior because
# these records need `mitigated_when` and `applies_when` variants that the shared
# `_record` helper does not offer -- behavior 1 wants four DIFFERENT verdicts.
# ---------------------------------------------------------------------------

def _check(cid, pattern=MARKER, mitigated=None, applies=None):
    """A schema-valid check over the target's python files.

    `models.Check` requires two-sided fixtures whenever `present_when` is set, so the
    bad tree carries the pattern and the good tree does not.
    """
    chk = {
        "id": cid, "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": pattern},
        "fixtures": {"bad": {"a.py": pattern + "\n"}, "good": {"a.py": "clean\n"}},
    }
    if mitigated is not None:
        chk["mitigated_when"] = {"kind": "content_matches", "globs": ["**/*.py"],
                                 "pattern": mitigated}
    if applies is not None:
        chk["applies_when"] = {"kind": "file_exists", "globs": applies}
    return chk


def _record(gid, check):
    rec = {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}],
    }
    if check is not None:
        rec["check"] = check
    return rec


#: Four records whose verdicts are four DIFFERENT values on the target below, so the
#: byte-stability fixture is not one verdict repeated. Every one of the four rules
#: reads every python file, which is where the 4x amplification comes from.
FOUR_VERDICTS = [
    _record("GAP-700", _check("CHK-700")),                                    # PRESENT
    _record("GAP-701", _check("CHK-701", pattern="NEVER_APPEARS_ANYWHERE")),   # MANUAL
    _record("GAP-702", _check("CHK-702", pattern="NEVER_APPEARS_ANYWHERE",
                              mitigated=MITIGATION)),                         # ABSENT
    _record("GAP-703", _check("CHK-703", applies=["**/*.rs"])),                # NOT_APPLICABLE
]


def _register(root, records=FOUR_VERDICTS):
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec, sort_keys=True),
                                             encoding="utf-8")
    return d


def _target(root, extra_modules=5, marker=True, mitigation=True):
    """A target tree of `extra_modules + 1` python files, all reached by every rule."""
    t = root / "target"
    (t / "app").mkdir(parents=True)
    body = ""
    if marker:
        body += MARKER + "\n"
    if mitigation:
        body += MITIGATION + "\n"
    (t / "app" / "loop.py").write_text(body or "clean\n", encoding="utf-8")
    for i in range(extra_modules):
        (t / "app" / f"mod{i}.py").write_text(f"clean module {i}\n", encoding="utf-8")
    return t


def _verdicts(result):
    return {f.gap.id: f.outcome.verdict for f in result.findings}


# ---------------------------------------------------------------------------
# Counters. `reads` = how many times the rules ask; `decodes` = how many times the
# filesystem is made to answer. Both are filtered to paths under the target so
# register loading (which also reads text) cannot inflate either number.
# ---------------------------------------------------------------------------

class _Counts:
    def __init__(self, target):
        self.target = str(target)
        self.reads: list[str] = []
        self.decodes: list[str] = []

    def _under(self, log, name=None):
        return [p for p in log
                if p.startswith(self.target) and (name is None or p.endswith(name))]

    def read_calls(self, name=None):
        return len(self._under(self.reads, name))

    def decode_calls(self, name=None):
        return len(self._under(self.decodes, name))

    def distinct_files(self):
        return len(set(self._under(self.reads)))

    def __repr__(self):
        return (f"<reads={self.read_calls()} decodes={self.decode_calls()} "
                f"distinct={self.distinct_files()}>")


def _spy(monkeypatch, target):
    counts = _Counts(target)

    real_read = checks._read

    def read_spy(path):
        counts.reads.append(str(path))
        return real_read(path)

    real_read_text = pathlib.Path.read_text

    def read_text_spy(self, *a, **k):
        counts.decodes.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(checks, "_read", read_spy)
    monkeypatch.setattr(pathlib.Path, "read_text", read_text_spy)
    return counts


@pytest.fixture()
def amplified(tmp_path):
    """(register, target) where four rules each reach six files."""
    return load_all(_register(tmp_path)), _target(tmp_path)


# ---------------------------------------------------------------------------
# Behavior 1 -- the documents are unchanged: byte-stable, one-newline tail, and the
# CLI emits exactly the bytes the API produces.
# ---------------------------------------------------------------------------

def test_b1_the_fixture_really_spans_four_verdicts(amplified):
    """Non-vacuity gate for every byte assertion below. If the fixture collapsed to
    one verdict, "the documents are unchanged" would be a claim about one code path."""
    gaps, target = amplified
    got = {gid: v.value for gid, v in _verdicts(scan(gaps, target)).items()}
    assert got == {"GAP-700": "PRESENT", "GAP-701": "MANUAL",
                   "GAP-702": "ABSENT", "GAP-703": "NOT_APPLICABLE"}, got


def test_b1_render_scan_is_byte_stable_across_two_scans(amplified):
    gaps, target = amplified
    first = render_scan(scan(gaps, target))
    second = render_scan(scan(gaps, target))
    assert first == second


def test_b1_scan_json_is_byte_stable_across_two_scans(amplified):
    gaps, target = amplified
    first = scan_json(scan(gaps, target))
    second = scan_json(scan(gaps, target))
    assert first == second


def test_b1_both_documents_end_in_exactly_one_newline(amplified):
    gaps, target = amplified
    result = scan(gaps, target)
    for name, doc in (("render_scan", render_scan(result)), ("scan_json", scan_json(result))):
        assert doc.endswith("\n"), name
        assert not doc.endswith("\n\n"), name


def test_b1_cli_stdout_is_byte_identical_to_the_api_document(tmp_path, capsys):
    """The cache sits under the CLI, so what the user sees must not have moved."""
    reg = _register(tmp_path)
    target = _target(tmp_path)
    rc = main(["scan", str(target), "--gaps", str(reg)])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    assert cap.err == ""
    assert cap.out == render_scan(scan(load_all(reg), target))


def test_b1_cli_json_stdout_is_byte_identical_to_scan_json(tmp_path, capsys):
    reg = _register(tmp_path)
    target = _target(tmp_path)
    rc = main(["scan", str(target), "--gaps", str(reg), "--json"])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    assert cap.err == ""
    assert cap.out == scan_json(scan(load_all(reg), target))
    json.loads(cap.out)


# ---------------------------------------------------------------------------
# Behavior 2 -- each file is decoded at most once per scan, and the fixture is
# amplified so the claim could fail.
# ---------------------------------------------------------------------------

def test_b2_the_fixture_is_amplified_before_anything_is_asserted(amplified, monkeypatch):
    """The non-vacuity guard. `decodes == distinct_files` is also what a scan that
    read NOTHING would report, so the amplification has to be measured too."""
    gaps, target = amplified
    counts = _spy(monkeypatch, target)
    scan(gaps, target)
    assert counts.distinct_files() == 6, counts
    assert counts.read_calls() == 24, counts
    assert counts.read_calls() >= 2 * counts.distinct_files(), counts


def test_b2_each_file_is_decoded_exactly_once_per_scan(amplified, monkeypatch):
    gaps, target = amplified
    counts = _spy(monkeypatch, target)
    scan(gaps, target)
    assert counts.decode_calls() == counts.distinct_files(), counts
    per_file = {}
    for p in counts.decodes:
        if p.startswith(str(target)):
            per_file[p] = per_file.get(p, 0) + 1
    assert set(per_file.values()) == {1}, per_file


def test_b2_the_verdicts_are_unchanged_by_the_shared_read(amplified, monkeypatch):
    """A memo that returned the wrong text would show up here first."""
    gaps, target = amplified
    _spy(monkeypatch, target)
    got = {gid: v.value for gid, v in _verdicts(scan(gaps, target)).items()}
    assert got == {"GAP-700": "PRESENT", "GAP-701": "MANUAL",
                   "GAP-702": "ABSENT", "GAP-703": "NOT_APPLICABLE"}, got


# ---------------------------------------------------------------------------
# Behavior 3 -- the cache does not survive the scan. No caller-side clear.
# ---------------------------------------------------------------------------

def test_b3_a_second_scan_in_one_process_sees_new_content(tmp_path):
    reg = load_all(_register(tmp_path))
    target = _target(tmp_path, marker=False, mitigation=False)
    assert _verdicts(scan(reg, target))["GAP-700"] is Verdict.MANUAL

    (target / "app" / "loop.py").write_text(MARKER + "\n", encoding="utf-8")
    again = _verdicts(scan(reg, target))["GAP-700"]
    assert again is Verdict.PRESENT, "the second scan answered from the first scan's cache"


def test_b3_a_second_scan_also_sees_a_marker_that_went_away(tmp_path):
    """The other direction: a stale HIT is as wrong as a stale miss."""
    reg = load_all(_register(tmp_path))
    target = _target(tmp_path, mitigation=False)
    assert _verdicts(scan(reg, target))["GAP-700"] is Verdict.PRESENT

    (target / "app" / "loop.py").write_text("cleaned up\n", encoding="utf-8")
    assert _verdicts(scan(reg, target))["GAP-700"] is Verdict.MANUAL


def test_b3_the_cli_sees_new_content_on_a_second_invocation(tmp_path, capsys):
    reg = _register(tmp_path)
    target = _target(tmp_path, marker=False, mitigation=False)
    assert main(["scan", str(target), "--gaps", str(reg), "--json"]) == 0
    first = json.loads(capsys.readouterr().out)

    (target / "app" / "loop.py").write_text(MARKER + "\n", encoding="utf-8")
    assert main(["scan", str(target), "--gaps", str(reg), "--json"]) == 0
    second = json.loads(capsys.readouterr().out)

    def verdict(payload):
        return {f["gap_id"]: f["verdict"] for f in payload["findings"]}["GAP-700"]

    assert verdict(first) == "MANUAL"
    assert verdict(second) == "PRESENT"


def test_b3_the_second_scan_decodes_again_rather_than_reusing(tmp_path, monkeypatch):
    reg = load_all(_register(tmp_path))
    target = _target(tmp_path)
    counts = _spy(monkeypatch, target)
    scan(reg, target)
    after_one = counts.decode_calls()
    scan(reg, target)
    assert counts.decode_calls() == 2 * after_one, counts


# ---------------------------------------------------------------------------
# Behavior 4 -- no caching outside a scan. `run_check` is a public entry point.
# ---------------------------------------------------------------------------

def test_b4_two_direct_run_check_calls_both_see_the_current_file(tmp_path):
    target = _target(tmp_path, marker=False, mitigation=False)
    check = _check("CHK-700")
    assert run_check(check, target).verdict is Verdict.MANUAL

    (target / "app" / "loop.py").write_text(MARKER + "\n", encoding="utf-8")
    assert run_check(check, target).verdict is Verdict.PRESENT, (
        "an out-of-scan read answered from a cache")


def test_b4_a_direct_run_check_decodes_every_time(tmp_path, monkeypatch):
    """The default read path is uncached: one rule over one file, twice, decodes twice."""
    target = _target(tmp_path, extra_modules=0)
    counts = _spy(monkeypatch, target)
    check = _check("CHK-700")
    run_check(check, target)
    run_check(check, target)
    assert counts.decode_calls("loop.py") == 2, counts


# ---------------------------------------------------------------------------
# Behavior 5 -- a cached read returns exactly what an uncached read returns,
# INCLUDING `None`. An oversized or undecodable file is a value, not a miss.
# ---------------------------------------------------------------------------

def _none_target(root):
    """A target whose files all carry the marker but two of them cannot be read:
    one is over `MAX_FILE_BYTES`, one is not valid UTF-8."""
    t = root / "target"
    (t / "app").mkdir(parents=True)
    (t / "app" / "big.py").write_text(MARKER + "\n" + "z" * MAX_FILE_BYTES,
                                      encoding="utf-8")
    (t / "app" / "bad.py").write_bytes(b"\xff\xfe\x00 " + MARKER.encode() + b" \xff\n")
    (t / "app" / "ok.py").write_text("clean\n", encoding="utf-8")
    return t


def test_b5_an_unreadable_file_never_produces_a_finding(tmp_path):
    """Correctness half: the marker sits in both unreadable files and in neither
    case may it be reported. A None that was re-tried as a miss would still say
    this -- the count assertions below are what make the caching observable."""
    reg = load_all(_register(tmp_path))
    verdicts = _verdicts(scan(reg, _none_target(tmp_path)))
    assert verdicts["GAP-700"] is Verdict.MANUAL, verdicts
    assert verdicts["GAP-703"] is Verdict.NOT_APPLICABLE, verdicts


def test_b5_an_undecodable_file_is_decoded_once_per_scan(tmp_path, monkeypatch):
    """Four rules reach `bad.py`; its decode raises and yields None. If None read as
    "absent from the cache", the most expensive files in a repo would be re-read once
    per rule -- exactly the amplification this iteration removes."""
    reg = load_all(_register(tmp_path))
    target = _none_target(tmp_path)
    counts = _spy(monkeypatch, target)
    scan(reg, target)
    assert counts.read_calls("bad.py") == 4, counts
    assert counts.decode_calls("bad.py") == 1, counts


def test_b5_a_readable_and_an_unreadable_file_are_cached_the_same_way(tmp_path, monkeypatch):
    reg = load_all(_register(tmp_path))
    target = _none_target(tmp_path)
    counts = _spy(monkeypatch, target)
    scan(reg, target)
    assert counts.decode_calls("ok.py") == 1, counts
    assert counts.decode_calls("bad.py") == 1, counts


def test_b5_an_oversized_file_is_asked_for_repeatedly_but_never_read_twice(
        tmp_path, monkeypatch):
    """`big.py` is over the byte cap, so a decode is never even attempted -- the
    stdlib count is 0 with or without a cache. What IS observable is that the four
    rules still ask for it and still get the same answer, and that the scan as a
    whole decodes exactly one file per distinct readable file."""
    reg = load_all(_register(tmp_path))
    target = _none_target(tmp_path)
    counts = _spy(monkeypatch, target)
    verdicts = _verdicts(scan(reg, target))
    assert counts.read_calls("big.py") == 4, counts
    assert counts.decode_calls("big.py") == 0, counts
    assert counts.decode_calls() == 2, counts
    assert verdicts["GAP-700"] is Verdict.MANUAL, verdicts


# ---------------------------------------------------------------------------
# Behavior 6 -- nesting is safe. A scan run inside an already-open scope is a
# DIFFERENT scan and must not inherit or poison the enclosing snapshot.
# ---------------------------------------------------------------------------

def test_b6_a_scan_nested_in_an_open_scope_still_sees_new_content(tmp_path):
    reg = load_all(_register(tmp_path))
    target = _target(tmp_path, marker=False, mitigation=False)
    with read_cache_scope():
        assert _verdicts(scan(reg, target))["GAP-700"] is Verdict.MANUAL
        (target / "app" / "loop.py").write_text(MARKER + "\n", encoding="utf-8")
        nested = _verdicts(scan(reg, target))["GAP-700"]
    assert nested is Verdict.PRESENT, "a nested scan answered from the enclosing scope"


def test_b6_a_scan_inside_a_scope_still_decodes_each_file_once(tmp_path, monkeypatch):
    reg = load_all(_register(tmp_path))
    target = _target(tmp_path)
    counts = _spy(monkeypatch, target)
    with read_cache_scope():
        scan(reg, target)
        assert counts.decode_calls() == counts.distinct_files() == 6, counts


def test_b6_leaving_a_nested_scan_leaves_the_outer_scope_usable(tmp_path, monkeypatch):
    """The outer scope must still answer after the inner one closes, and it must
    answer with the text it snapshotted -- not with an emptied cache."""
    reg = load_all(_register(tmp_path))
    target = _target(tmp_path)
    counts = _spy(monkeypatch, target)
    loop = target / "app" / "loop.py"
    with read_cache_scope():
        assert checks._read(loop) is not None
        before = counts.decode_calls("loop.py")
        scan(reg, target)
        assert checks._read(loop) is not None
        assert counts.decode_calls("loop.py") == before + 1, counts


# ---------------------------------------------------------------------------
# Behavior 7 -- errors and exit codes are unchanged.
# ---------------------------------------------------------------------------

def test_b7_a_missing_target_still_exits_2_with_one_error_line(tmp_path, capsys):
    reg = _register(tmp_path)
    rc = main(["scan", str(tmp_path / "not-there"), "--gaps", str(reg)])
    cap = capsys.readouterr()
    assert rc == 2
    assert cap.out == ""
    lines = [ln for ln in cap.err.split("\n") if ln]
    assert len(lines) == 1, cap.err
    assert lines[0].startswith("Error: "), cap.err


def test_b7_a_missing_target_with_json_also_exits_2_with_empty_stdout(tmp_path, capsys):
    reg = _register(tmp_path)
    rc = main(["scan", str(tmp_path / "not-there"), "--gaps", str(reg), "--json"])
    cap = capsys.readouterr()
    assert rc == 2
    assert cap.out == ""
    assert cap.err.startswith("Error: ")
    assert cap.err.endswith("\n") and not cap.err.endswith("\n\n")


def test_b7_a_file_as_a_target_still_exits_2(tmp_path, capsys):
    reg = _register(tmp_path)
    afile = tmp_path / "a-file.txt"
    afile.write_text("not a directory\n", encoding="utf-8")
    rc = main(["scan", str(afile), "--gaps", str(reg)])
    cap = capsys.readouterr()
    assert rc == 2
    assert cap.out == ""
    assert cap.err.startswith("Error: ")


# ---------------------------------------------------------------------------
# Behavior 8 -- a measured, non-vacuous reduction.
# ---------------------------------------------------------------------------

def test_b8_the_decode_count_strictly_drops_below_the_ask_count(amplified, monkeypatch):
    """The reduction, stated as the inequality that goes red if the cache is removed:
    on the pre-change tree every ask was a decode, so `decodes == reads == 24`."""
    gaps, target = amplified
    counts = _spy(monkeypatch, target)
    scan(gaps, target)
    assert counts.decode_calls() < counts.read_calls(), counts
    assert counts.decode_calls() == 6 and counts.read_calls() == 24, counts


def test_b8_control_bypassing_the_scope_restores_the_amplified_count(
        amplified, monkeypatch):
    """The falsification control, in-tree: with the scan's cache scope replaced by a
    no-op, the same fixture decodes once per ask again. If a future refactor stops
    reaching the scope through this name the control cannot bypass anything, so it
    SKIPS rather than reporting a red suite against correct code -- the primary
    assertion above is what actually guards the behavior."""
    gaps, target = amplified

    @contextlib.contextmanager
    def _null():
        yield {}

    monkeypatch.setattr(scan_mod, "read_cache_scope", _null)
    monkeypatch.setattr(checks, "read_cache_scope", _null)
    counts = _spy(monkeypatch, target)
    scan(gaps, target)
    if counts.decode_calls() == counts.distinct_files():
        pytest.skip("the cache scope is not reached through `read_cache_scope`; "
                    "falsification cannot be demonstrated by patching that name")
    assert counts.decode_calls() == counts.read_calls() == 24, counts


def test_b8_the_bypassed_control_produces_the_same_documents(amplified, monkeypatch):
    """The cache is a cost change, not a behavior change: bypassing it must not move
    a single byte of either document."""
    gaps, target = amplified
    cached_md, cached_json = render_scan(scan(gaps, target)), scan_json(scan(gaps, target))

    @contextlib.contextmanager
    def _null():
        yield {}

    monkeypatch.setattr(scan_mod, "read_cache_scope", _null)
    monkeypatch.setattr(checks, "read_cache_scope", _null)
    result = scan(gaps, target)
    assert render_scan(result) == cached_md
    assert scan_json(result) == cached_json
