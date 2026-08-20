"""Iteration 23 behaviors: `radar prd` declares detectability and names the register's own
reproduction sample.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation below comes from `pm.md`'s Expected Behaviors, and every shape claim was
measured by RUNNING the tool (`radar prd . --gap ...` once per detectability class, plus
`radar taxonomy` for the closed vocabularies) or by reading `tests/`, `README.md` and the
on-disk register AS DATA.

TWO SPEC DEFECTS were measured while writing this file. Both are reported as PM feedback in
`tester.md`, and each is pinned here by an assertion rather than left as prose:

* Behavior 1 names the pointer `recordFile` with the value `gaps/<GAP-ID>.json`. No such
  file exists for any record: this register stores records as `gaps/<GAP-ID>-<slug>.json`,
  a layout `tests/test_iter20_behavior.py` already pins as the documented one. A pointer
  that resolves for zero of N records is not a pointer, so this file tests the SUBSTANTIVE
  contract -- the emitted value RESOLVES to exactly one record file, per record -- and
  locates the pointer by value-shape rather than by the spec's key name. The literal
  reading is falsified by `test_spec_defect_literal_record_path_exists_for_no_record`.
* Behavior 6's acceptance criterion ("US-001 has exactly four acceptance criteria, the
  first three byte-identical to today's") is arithmetically wrong: five are emitted, and
  exactly one of them is the criterion behavior 6 describes as new, so FOUR pre-existed,
  not three. The substantive requirement -- exactly ONE criterion added, appended LAST,
  every earlier one unchanged -- is what is asserted, by building one base record twice
  with two different checks and diffing the two emitted criteria lists.

Structural notes, so this file cannot lie later:

* Every assertion that a new record landing in `gaps/` could falsify is driven from a
  SYNTHETIC record built in `tmp_path`. The live register is loaded by exactly two tests,
  both asserting a property that must hold for ANY record (its pointer resolves; the
  spec's literal path does not exist), and both guard against a vacuous domain first.
* Behaviors 4, 5, 7 and 8 are proven TWO-SIDED in this run: the value whose absence is
  asserted is present on the other side of the same pair (the manual question is emitted
  for a manual check and withheld for an automated one; the fixture FILENAMES appear in
  the document whose fixture BODIES must not).
"""

from __future__ import annotations

import fnmatch
import json
import pathlib
import re

from agent_gap_radar.cli import main
from agent_gap_radar.prd import prd_for, render_prd
from agent_gap_radar.registry import load_all, load_one
from agent_gap_radar.scoring import below_floor

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"
README = REPO_ROOT / "README.md"

#: The five top-level keys and the six `sourceGap` keys that pre-date this iteration, in
#: emitted order (measured by running `radar prd . --gap GAP-003` before writing this).
PRE_EXISTING_TOP_KEYS = ["project", "branchName", "description", "sourceGap", "userStories"]
PRE_EXISTING_SOURCE_GAP_KEYS = ["id", "layer", "gapType", "priority", "confidence", "evidence"]

#: Behavior 1 calls the record pointer `recordFile`; the shipped key is `recordGlob`. The
#: pointer is located by presence, so this file pins the value's contract and stays honest
#: about the divergence instead of encoding one side of it as the whole truth.
POINTER_KEYS = ("recordGlob", "recordFile")

MQ = ("Does the loop tell a step that was killed at its cap from a step that refused the "
      "work, or does it record both as a refusal?")

#: Fixture BODIES, which behavior 7 forbids from reaching the document. Distinctive enough
#: that a substring hit cannot be a coincidence.
SENTINEL_BAD = "ZQX_BAD_FIXTURE_BODY_SENTINEL"
SENTINEL_GOOD = "ZQX_GOOD_FIXTURE_BODY_SENTINEL"


# --------------------------------------------------------------------------- helpers


def _rule(pattern=r"time\.sleep\(", globs=("**/*.py",)):
    return {"kind": "content_matches", "globs": list(globs), "pattern": pattern}


def _automated_check(cid="CHK-900", bad=None, good=None, manual_question=MQ):
    """A check with a `present_when` rule -- automated by the register's own predicate."""
    return {
        "id": cid,
        "rationale": "why this check exists",
        "manual_question": manual_question,
        "present_when": _rule(),
        "fixtures": {
            "bad": bad if bad is not None else {"a.py": "import time\ntime.sleep(5)\n"},
            "good": good if good is not None else {"a.py": "pass\n"},
        },
    }


def _mitigated_only_check(cid="CHK-902", manual_question=MQ):
    """Automated on the OTHER limb of the predicate: a `mitigated_when` and no `present_when`."""
    return {
        "id": cid,
        "rationale": "r",
        "manual_question": manual_question,
        "mitigated_when": _rule(pattern="jitter"),
        "fixtures": {"bad": {"a.py": "pass\n"}, "good": {"a.py": "backoff with jitter\n"}},
    }


def _manual_check(cid="CHK-901", manual_question=MQ):
    """Manual by declaration: neither rule, so nothing static can be keyed on."""
    return {"id": cid, "rationale": "r", "manual_question": manual_question}


def _record(gid="GAP-900", check=None, **over):
    rec = {
        "id": gid,
        "title": f"a synthetic record for {gid}",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "problem": "p",
        "symptom": "the symptom text",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "build_hypothesis": "b",
        "evidence": [
            {"source_class": "incident-postmortem", "title": "a post-mortem",
             "locator": "https://example.invalid/inc1", "date": "2026-01-02",
             "quote": "the verbatim line that was actually read"},
            {"source_class": "incident-postmortem", "title": "a second post-mortem",
             "locator": "https://example.invalid/inc2", "date": "2026-02-03",
             "quote": "a second verbatim line that was actually read"},
        ],
    }
    if check is not None:
        rec["check"] = check
    rec.update(over)
    return rec


def _register(root, *records):
    """Write records into a `gaps/` dir, named the way this register names them."""
    d = pathlib.Path(root) / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    for rec in records:
        (d / f"{rec['id']}-a-synthetic-record.json").write_text(
            json.dumps(rec), encoding="utf-8")
    return d


def _gap(root, record):
    return load_one(_register(root, record), record["id"])


def _check_payload(gap):
    return prd_for(gap)["sourceGap"]["check"]


def _pointer(sample):
    present = [k for k in POINTER_KEYS if k in sample]
    assert len(present) == 1, f"expected exactly one record pointer key, got {sorted(sample)}"
    return sample[present[0]]


def _us001(gap):
    first = prd_for(gap)["userStories"][0]
    assert first["id"] == "US-001", first["id"]
    return first


# ------------------------------------------------------- behavior 1: automated record


def test_b1_automated_record_emits_the_stated_check_object(tmp_path):
    chk = _check_payload(_gap(tmp_path, _record(check=_automated_check(cid="CHK-900"))))
    assert chk["id"] == "CHK-900", chk
    assert chk["detectability"] == "automated", chk
    assert isinstance(chk["reproductionSample"], dict), chk


def test_b1_fixture_side_lists_are_sorted_relative_paths(tmp_path):
    bad = {"z.py": "import time\ntime.sleep(1)\n",
           "a.py": "import time\ntime.sleep(2)\n",
           "src/m.py": "import time\ntime.sleep(3)\n"}
    good = {"q.py": "pass\n", "b.py": "pass\n"}
    sample = _check_payload(
        _gap(tmp_path, _record(check=_automated_check(bad=bad, good=good))))["reproductionSample"]
    assert list(bad) != sorted(bad), "input order was already sorted; this test would be vacuous"
    assert sample["badFiles"] == sorted(bad), sample["badFiles"]
    assert sample["goodFiles"] == sorted(good), sample["goodFiles"]


def test_b1_record_pointer_names_the_gap_and_matches_exactly_one_record_file(tmp_path):
    rec = _record(check=_automated_check())
    d = _register(tmp_path, rec)
    pointer = _pointer(_check_payload(load_one(d, rec["id"]))["reproductionSample"])
    assert pointer.startswith("gaps/"), pointer
    assert rec["id"] in pointer, pointer
    names = [p.name for p in d.iterdir() if p.is_file()]
    matched = fnmatch.filter(names, pointer.split("/", 1)[1])
    assert matched == [f"{rec['id']}-a-synthetic-record.json"], (pointer, names, matched)


def test_b1_pointer_resolves_to_one_file_for_every_automated_record_in_the_live_register():
    """Holds for ANY record, so the live register is a legitimate domain here."""
    automated = [g for g in load_all(LIVE_GAPS)
                 if _check_payload(g)["detectability"] == "automated"]
    assert automated, "no automated records found; this check would be vacuous"
    for gap in automated:
        pointer = _pointer(_check_payload(gap)["reproductionSample"])
        hits = sorted(REPO_ROOT.glob(pointer))
        assert len(hits) == 1, f"{gap.id}: pointer {pointer!r} resolved to {len(hits)} file(s)"


def test_spec_defect_literal_record_path_exists_for_no_record():
    """Behavior 1's literal `gaps/<GAP-ID>.json` is unimplementable: it exists nowhere."""
    gaps = load_all(LIVE_GAPS)
    assert gaps, "empty register; this check would be vacuous"
    assert [g.id for g in gaps if (LIVE_GAPS / f"{g.id}.json").exists()] == []


# ---------------------------------------------------- behavior 2: manual-only record


def test_b2_manual_only_record_declares_manual_and_carries_the_question_verbatim(tmp_path):
    chk = _check_payload(_gap(tmp_path, _record(check=_manual_check(cid="CHK-901"))))
    assert chk["id"] == "CHK-901", chk
    assert chk["detectability"] == "manual", chk
    assert chk["reproductionSample"] is None, chk
    assert chk["manualQuestion"] == MQ, chk["manualQuestion"]


# -------------------------------------------------------- behavior 3: no check at all


def test_b3_record_without_a_check_carries_an_explicit_none_never_an_omission(tmp_path):
    sg = prd_for(_gap(tmp_path, _record(check=None)))["sourceGap"]
    assert "check" in sg, sorted(sg)
    chk = sg["check"]
    assert chk["id"] is None, chk
    assert chk["detectability"] == "none", chk
    assert chk["reproductionSample"] is None, chk


# ------------------------------------- behavior 4: manualQuestion only where it repros


def test_b4_manual_question_is_withheld_from_an_automated_check_and_kept_on_a_manual_one(tmp_path):
    """Two-sided: the SAME question string is on both records; only one document carries it."""
    auto = _check_payload(_gap(tmp_path / "a", _record(check=_automated_check())))
    manual = _check_payload(_gap(tmp_path / "m", _record(check=_manual_check())))
    assert "manualQuestion" not in auto, sorted(auto)
    assert manual["manualQuestion"] == MQ
    assert MQ not in json.dumps(auto), auto


def test_b4_a_mitigated_only_check_is_automated_too(tmp_path):
    """The predicate is `present_when OR mitigated_when`; this pins the second limb."""
    chk = _check_payload(_gap(tmp_path, _record(check=_mitigated_only_check())))
    assert chk["detectability"] == "automated", chk
    assert "manualQuestion" not in chk, sorted(chk)
    assert isinstance(chk["reproductionSample"], dict), chk


# --------------------------------------------- behavior 5: neutral closed-vocab declaration


def test_b5_declaration_is_one_deterministic_sentence_per_detectability_class(tmp_path):
    seen = {}
    for name, chk in (("automated", _automated_check()),
                      ("manual", _manual_check()),
                      ("none", None)):
        payload = _check_payload(_gap(tmp_path / name, _record(check=chk)))
        text = payload["declaration"]
        assert isinstance(text, str) and text.strip(), (name, text)
        assert text.endswith("."), (name, text)
        assert ". " not in text, f"{name}: declaration is more than one sentence: {text!r}"
        seen[payload["detectability"]] = text
    assert sorted(seen) == ["automated", "manual", "none"], sorted(seen)
    assert len(set(seen.values())) == 3, seen


def test_b5_the_vocabulary_is_closed_over_the_whole_live_register():
    """Holds for ANY record: declaration is a function of detectability and nothing else."""
    by_class = {}
    for gap in load_all(LIVE_GAPS):
        chk = _check_payload(gap)
        by_class.setdefault(chk["detectability"], set()).add(chk["declaration"])
    assert by_class, "empty register; this check would be vacuous"
    for name, texts in by_class.items():
        assert len(texts) == 1, f"{name} has {len(texts)} declarations, so it is not closed"
    assert len(by_class) <= 3, sorted(by_class)


def test_b5_declaration_is_a_declaration_not_a_judgement_about_importance(tmp_path):
    """Opposite priority inputs, identical declaration."""
    weak = _gap(tmp_path / "w", _record(gid="GAP-901", check=_automated_check(),
                                        severity=1, frequency=1, tractability=1))
    strong = _gap(tmp_path / "s", _record(gid="GAP-902", check=_automated_check(),
                                          severity=5, frequency=5, tractability=5))
    assert prd_for(weak)["sourceGap"]["priority"] != prd_for(strong)["sourceGap"]["priority"]
    assert _check_payload(weak)["declaration"] == _check_payload(strong)["declaration"]


# ------------------------------------------------ behavior 6: US-001 gains one criterion


def test_b6_exactly_one_criterion_is_added_and_it_is_the_last_one(tmp_path):
    """One base record, two checks: the lists may differ in the LAST position only."""
    base = _record(gid="GAP-903")
    auto = _us001(_gap(tmp_path / "a", {**base, "check": _automated_check()}))
    manual = _us001(_gap(tmp_path / "m", {**base, "check": _manual_check()}))
    a, m = auto["acceptanceCriteria"], manual["acceptanceCriteria"]
    assert len(a) == len(m), (len(a), len(m))
    assert a[:-1] == m[:-1], "a criterion other than the last one varies with detectability"
    assert a[-1] != m[-1], a[-1]
    assert auto["title"] == manual["title"], "US-001's title must not vary (out of scope)"


def test_b6_us001_carries_five_criteria_four_of_which_pre_existed(tmp_path):
    """Spec arithmetic defect: the criterion asks for FOUR total / THREE pre-existing."""
    crit = _us001(_gap(tmp_path, _record(check=_automated_check())))["acceptanceCriteria"]
    assert len(crit) == 5, crit


def test_b6_automated_criterion_names_the_pointer_and_both_side_counts(tmp_path):
    bad = {"a.py": "import time\ntime.sleep(1)\n", "b.py": "import time\ntime.sleep(2)\n"}
    good = {"c.py": "pass\n", "d.py": "pass\n", "e.py": "pass\n"}
    gap = _gap(tmp_path, _record(check=_automated_check(bad=bad, good=good)))
    line = _us001(gap)["acceptanceCriteria"][-1]
    pointer = _pointer(_check_payload(gap)["reproductionSample"])
    assert pointer in line, line
    assert re.search(r"2\s+bad", line), line
    assert re.search(r"3\s+good", line), line
    assert re.search(r"transcrib", line, re.I), line


def test_b6_undetectable_criterion_states_no_signature_and_demands_the_judgement(tmp_path):
    for name, chk in (("manual", _manual_check()), ("none", None)):
        line = _us001(_gap(tmp_path / name, _record(check=chk)))["acceptanceCriteria"][-1]
        assert re.search(r"no static signature", line, re.I), (name, line)
        assert re.search(r"judge?ment", line, re.I), (name, line)
        assert "gaps/" not in line, (name, line)


# ------------------------------------------------- behavior 7: a pointer, not a payload


def test_b7_no_fixture_file_content_reaches_the_document(tmp_path):
    bad = {"a.py": f"import time  # {SENTINEL_BAD}\ntime.sleep(1)\n"}
    good = {"b.py": f"pass  # {SENTINEL_GOOD}\n"}
    doc = render_prd(_gap(tmp_path, _record(check=_automated_check(bad=bad, good=good))))
    assert SENTINEL_BAD not in doc
    assert SENTINEL_GOOD not in doc
    assert "a.py" in doc and "b.py" in doc, "the fixture FILENAMES are the pointer and must appear"


# ------------------------------------------- behavior 8: everything else is unchanged


def test_b8_document_parses_ends_in_one_newline_and_is_byte_stable(tmp_path):
    gap = _gap(tmp_path, _record(check=_automated_check()))
    first, second = render_prd(gap), render_prd(gap)
    assert first == second, "two renders of one record differ"
    assert first.endswith("\n") and not first.endswith("\n\n")
    assert list(json.loads(first)) == PRE_EXISTING_TOP_KEYS, list(json.loads(first))


def test_b8_pre_existing_source_gap_keys_keep_their_values_and_check_is_appended(tmp_path):
    rec = _record(check=_automated_check())
    sg = prd_for(_gap(tmp_path, rec))["sourceGap"]
    assert list(sg) == PRE_EXISTING_SOURCE_GAP_KEYS + ["check"], list(sg)
    assert sg["id"] == rec["id"]
    assert sg["layer"] == rec["layer"]
    assert sg["gapType"] == rec["gap_type"]
    assert isinstance(sg["priority"], (int, float)) and isinstance(sg["confidence"], (int, float))
    assert len(sg["evidence"]) == len(rec["evidence"]), sg["evidence"]
    blob = json.dumps(sg["evidence"])
    for item in rec["evidence"]:
        assert item["locator"] in blob, item["locator"]


def test_b8_the_change_is_purely_additive(tmp_path):
    """Strip the new key and the new criterion: the two documents must be equal."""
    base = _record(gid="GAP-904")
    without = prd_for(_gap(tmp_path / "w", base))
    with_check = prd_for(_gap(tmp_path / "c", {**base, "check": _automated_check()}))
    for doc in (without, with_check):
        doc["sourceGap"].pop("check")
        doc["userStories"][0]["acceptanceCriteria"].pop()
    assert without == with_check


# --------------------------------------------------------- behavior 9: both doors agree


def test_b9_scan_prd_and_prd_emit_the_same_check_object(tmp_path, capsys):
    rec = _record(gid="GAP-905", check=_automated_check())
    d = _register(tmp_path, rec)
    gap = load_one(d, rec["id"])
    assert below_floor([gap]) == [], "record must clear the floor or `scan --prd` emits nothing"
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.py").write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

    assert main(["prd", str(tmp_path), "--gap", rec["id"]]) == 0
    door_prd = json.loads(capsys.readouterr().out)
    assert main(["scan", str(target), "--gaps", str(tmp_path), "--prd"]) == 0
    door_scan = json.loads(capsys.readouterr().out)

    assert door_scan["sourceGap"]["id"] == rec["id"], door_scan["sourceGap"]["id"]
    assert door_prd["sourceGap"]["check"]["detectability"] == "automated"
    assert door_scan["sourceGap"]["check"] == door_prd["sourceGap"]["check"]


# ------------------------------------------------- behavior 10: the front door says it


def test_b10_readme_from_gap_to_build_states_the_third_property():
    text = README.read_text(encoding="utf-8")
    start = text.index("## From gap to build")
    end = text.index("\n## ", start + 1)
    section = text[start:end]
    assert re.search(r"three properties", section, re.I), section
    assert re.search(r"detectab", section, re.I), section
    assert re.search(r"two-sided sample", section, re.I), section
    assert re.search(r"record file|pattern", section, re.I), section
