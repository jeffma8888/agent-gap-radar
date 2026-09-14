"""Iteration 221 -- `radar prd` publishes the register's own definition of CLOSED.

The PRD is the one artifact that crosses out of this register into a build loop, and it
published the PRESENT side of a check (`reproductionSample`) and nothing at all from the
mitigation side.  `mitigated_when` is the ONLY rule this product accepts as evidence of
mitigation and `ABSENT` is the only verdict it lets assert safety, so a loop could go green
on all four of US-002's acceptance criteria while the gap it was built from still verdicts
PRESENT.  This iteration appends `sourceGap.check.closure` -- a READ of `mitigated_when`,
never a re-evaluation -- plus the one US-002 criterion derived from it, and REFUSES with an
explicit three-null object rather than inventing a rule for a record the register holds no
mitigation signature for.

ISOLATION: black-box.  No implementation source was read to write this module -- not
`src/`, not `git diff`, not the engineer's, reviewer's or fix-reviewer's notes.  Every
expectation comes from the spec's Expected Behaviors, from constants and conventions of
files under `tests/` (readable by contract), or from RUNNING the product.

THE PRE-CHANGE LISTS ARE PINNED AS LITERALS, NOT RE-RENDERED.  `PRECHANGE_US002` and
`UNTOUCHED_US003` were captured by rendering `radar prd` from a `git archive` of
`PRECHANGE_COMMIT` (see tester.md for the transcript), which is what makes behavior 6's
"exactly ONE more item, appended LAST" a self-proving delta rather than a count.  The
extraction is deliberately NOT repeated inside the suite: `SPEED_STORY_NEEDED.md` is
present and this module must not add a clone or a tarball to every run.

COSTS, as counts.  ONE whole-register sweep (behaviors 4, 5, 8) -- 120 in-process `prd`
calls, module-scoped so it is paid once, measured at 4.45s.  TWO one-record scans of a
one-file synthetic target (behavior 9).  Everything else renders a one- or two-record
`tmp_path` register.  No network, no live-repo scan; `gaps/` is READ and never written.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main

# Hard import, never `importorskip`: the shipped minimal schema-valid record.  Reusing it
# means a schema change reddens one constant instead of every synthetic register.
from test_iter217_behavior import RECORD

REPO = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO / "gaps"

#: The commit the pre-change literals below were rendered from.
PRECHANGE_COMMIT = "7a32d85"

# --------------------------------------------------------------- the emitted vocabulary

#: Behavior 1 / 2: the closure object's keys, in emitted order.
CLOSURE_KEYS = ("verdict", "rule", "declaration")

#: Behavior 1: the `rule` pointer's keys, in emitted order.
RULE_KEYS = ("recordGlob", "field")

#: Behavior 1: the register field the pointer names.  The product may never publish a
#: DIFFERENT field here, because this is the only rule that can yield ABSENT.
MITIGATION_FIELD = "check.mitigated_when"

#: Behavior 5: the closed two-member declaration vocabulary, verbatim.
CHECKABLE_DECLARATION = (
    "The register holds a mitigation signature for this gap, so closure is a verdict a "
    "scan can read rather than a claim a loop makes about itself."
)
REFUSAL_DECLARATION = (
    "The register holds no mitigation signature for this gap, so no scan verdict can "
    "decide closure and the judgement that closes it must be stated."
)
CLOSURE_DECLARATIONS = (CHECKABLE_DECLARATION, REFUSAL_DECLARATION)

#: Behavior 5: prose that would let a record argue about its own quality.
SELF_ASSESSMENT_TOKENS = ("confidence", "priority", "severity")

# ------------------------------------------------------- the pre-change story literals

#: US-002's acceptance criteria BEFORE this iteration, in order.  Behavior 6 is a delta
#: against this list: the emitted list must be exactly this plus ONE item at the end.
PRECHANGE_US002 = (
    "The US-001 test passes",
    "The mitigation is opt-in or dormant by default (no behaviour change on upgrade)",
    "Full test suite passes",
    "No new runtime dependency",
)

#: US-003's acceptance criteria, which behavior 7 forbids this iteration from touching.
#: Register-independent, so one literal covers every record.
UNTOUCHED_US003 = (
    "README or docs page states the gap, the symptom, and the mitigation",
    "Every claim cites a locator from the gap record",
    "Full test suite passes",
    "No new runtime dependency",
)

#: US-001's criteria minus its last (reproduction) item, which varies by check shape.
#: `RECORD["symptom"]` is interpolated into the first line by the shipped renderer.
UNTOUCHED_US001_HEAD = (
    f"A test encodes the observed symptom: {RECORD['symptom']}",
    "The test FAILS on the current code and the failure message names the gap",
    "Full test suite passes",
    "No new runtime dependency",
)

#: Tokens the closure change may not leak into the two stories it must not touch.
CLOSURE_LEAK_TOKENS = ("closure", "mitigation signature", "ABSENT", MITIGATION_FIELD)

# ------------------------------------------------------------------- synthetic registers

_PRESENT_RULE = {"kind": "content_matches", "globs": ["**/*.py"],
                 "pattern": "dangerous_call"}
_MITIGATION_RULE = {"kind": "content_matches", "globs": ["**/*.py"],
                    "pattern": "checkpoint_write"}
_FIXTURES = {"bad": {"a.py": "dangerous_call()\n"}, "good": {"b.txt": "nothing\n"}}

#: The five check shapes the spec names.  `None` is behavior 2(c): no check at all.
CHECK_SHAPES = {
    # behavior 1: both rules -- the shape 114 of the 120 live records carry.
    "both_rules": {"id": "CHK-001", "present_when": _PRESENT_RULE,
                   "mitigated_when": _MITIGATION_RULE, "fixtures": _FIXTURES},
    # behavior 3: `models.py:234` accepts either rule, and availability keys off the
    # MITIGATION one alone.  Zero instances live, so only a synthetic register proves it.
    "mitigation_only": {"id": "CHK-001", "mitigated_when": _MITIGATION_RULE,
                        "fixtures": _FIXTURES},
    # behavior 2(a): automated, present side only.
    "present_only": {"id": "CHK-001", "present_when": _PRESENT_RULE,
                     "fixtures": _FIXTURES},
    # behavior 2(b): manual -- neither rule.
    "manual": {"id": "CHK-001", "manual_question": "Ask a human this."},
    # behavior 2(c): no check.
    "no_check": None,
}

CHECKABLE_SHAPES = ("both_rules", "mitigation_only")
REFUSAL_SHAPES = ("present_only", "manual", "no_check")

SYNTHETIC_ID = RECORD["id"]
SYNTHETIC_GLOB = f"gaps/{SYNTHETIC_ID}-*.json"


def _write_register(directory: pathlib.Path, check: object) -> pathlib.Path:
    """One-record register at `directory`, carrying `check` (omitted when `None`)."""
    directory.mkdir(parents=True, exist_ok=True)
    record = dict(RECORD)
    if check is None:
        record.pop("check", None)
    else:
        record["check"] = check
    (directory / f"{SYNTHETIC_ID}.json").write_text(
        json.dumps(record), encoding="utf-8")
    return directory


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _prd(tmp_path, shape: str, capsys) -> dict:
    """The prd document for a one-record synthetic register carrying `shape`."""
    register = _write_register(tmp_path / shape / "gaps", CHECK_SHAPES[shape])
    code, out, err = _run(["prd", str(register)], capsys)
    assert (code, err) == (0, ""), (shape, code, err)
    return json.loads(out)


def _closure(document: dict) -> dict:
    return document["sourceGap"]["check"]["closure"]


# ------------------------------------------------------------- the live-register sweep

@pytest.fixture(scope="module")
def live_documents() -> dict[str, dict]:
    """`radar prd --gap <ID>` for EVERY record of the live register, paid once.

    Behaviors 4, 5 and 8 are asserted over every record, and `prd` publishes exactly one
    record per invocation, so the sweep is the only way to reach them all.  No record
    count, id set or byte digest of the live document is pinned anywhere in this module.
    """
    ids = sorted(json.loads(path.read_text(encoding="utf-8"))["id"]
                 for path in LIVE_GAPS.glob("*.json"))
    assert ids, "the live register is empty -- the sweep would assert nothing"
    documents = {}
    for gap_id in ids:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["prd", str(LIVE_GAPS), "--gap", gap_id])
        assert (code, err.getvalue()) == (0, ""), (gap_id, code, err.getvalue())
        documents[gap_id] = json.loads(out.getvalue())
    return documents


# --------------------------------------------------------------------------- behavior 1

@pytest.mark.parametrize("shape", CHECKABLE_SHAPES)
def test_b1_checkable_closure_keys_and_verdict(tmp_path, capsys, shape):
    """A record whose check declares `mitigated_when` gets the verdict a scan can read."""
    closure = _closure(_prd(tmp_path, shape, capsys))
    assert tuple(closure) == CLOSURE_KEYS, tuple(closure)
    assert closure["verdict"] == "ABSENT", closure
    assert closure["declaration"] == CHECKABLE_DECLARATION, closure["declaration"]


@pytest.mark.parametrize("shape", CHECKABLE_SHAPES)
def test_b1_checkable_rule_names_the_record_and_the_field(tmp_path, capsys, shape):
    rule = _closure(_prd(tmp_path, shape, capsys))["rule"]
    assert tuple(rule) == RULE_KEYS, tuple(rule)
    assert rule["field"] == MITIGATION_FIELD, rule
    assert rule["recordGlob"] == SYNTHETIC_GLOB, rule


def test_b1_the_two_globs_are_one_derivation_not_two(tmp_path, capsys):
    """`closure.rule` and `reproductionSample` must name the SAME file, byte for byte."""
    check = _prd(tmp_path, "both_rules", capsys)["sourceGap"]["check"]
    sample = check["reproductionSample"]
    assert sample is not None, check
    assert check["closure"]["rule"]["recordGlob"] == sample["recordGlob"], check


def test_b1_live_checkable_records_agree_on_the_glob(live_documents):
    """Same two-glob identity over every live record that carries BOTH keys."""
    compared = 0
    for gap_id, document in live_documents.items():
        check = document["sourceGap"]["check"]
        sample, closure = check["reproductionSample"], check["closure"]
        if sample is None or closure["rule"] is None:
            continue
        assert closure["rule"]["recordGlob"] == sample["recordGlob"], gap_id
        assert closure["rule"]["recordGlob"] == f"gaps/{gap_id}-*.json", gap_id
        compared += 1
    assert compared, "no live record carried both a sample and a rule -- vacuous"


# --------------------------------------------------------------------------- behavior 2

@pytest.mark.parametrize("shape", REFUSAL_SHAPES)
def test_b2_refusal_is_three_explicit_nulls_never_an_invented_rule(
        tmp_path, capsys, shape):
    """A missing key reads as 'unknown'; an explicit null says the register has nothing."""
    closure = _closure(_prd(tmp_path, shape, capsys))
    assert tuple(closure) == CLOSURE_KEYS, (shape, tuple(closure))
    for key in ("verdict", "rule", "declaration"):
        assert key in closure, (shape, key, closure)
    assert closure["verdict"] is None, (shape, closure)
    assert closure["rule"] is None, (shape, closure)
    assert closure["declaration"] == REFUSAL_DECLARATION, (shape, closure["declaration"])


@pytest.mark.parametrize("shape", REFUSAL_SHAPES)
def test_b2_refusal_never_borrows_the_checkable_verdict(tmp_path, capsys, shape):
    """The refusal arm may not smuggle ABSENT in as prose."""
    closure = _closure(_prd(tmp_path, shape, capsys))
    assert "ABSENT" not in json.dumps(closure), (shape, closure)


# --------------------------------------------------------------------------- behavior 3

def test_b3_availability_keys_off_mitigated_when_alone(tmp_path, capsys):
    """A check with `mitigated_when` and NO `present_when` takes the CHECKABLE arm.

    The negative control is `present_only`, the mirror shape: same detectability, same
    non-null `reproductionSample`, opposite arm.  So the arm cannot be keyed on
    `detectability` or on `reproductionSample` and still pass this pair.
    """
    checkable = _prd(tmp_path, "mitigation_only", capsys)["sourceGap"]["check"]
    refusing = _prd(tmp_path, "present_only", capsys)["sourceGap"]["check"]
    assert "present_when" not in CHECK_SHAPES["mitigation_only"]
    assert "mitigated_when" not in CHECK_SHAPES["present_only"]
    assert checkable["detectability"] == refusing["detectability"] == "automated"
    assert checkable["reproductionSample"] is not None
    assert refusing["reproductionSample"] is not None
    assert checkable["closure"]["verdict"] == "ABSENT", checkable
    assert refusing["closure"]["verdict"] is None, refusing


# --------------------------------------------------------------------------- behavior 4

#: The check keys that precede `closure`, in emitted order, for the two check kinds.
PRECEDING_KEYS = {
    "automated": ("id", "detectability", "declaration", "reproductionSample"),
    "manual": ("id", "detectability", "declaration", "reproductionSample",
               "manualQuestion"),
}


def test_b4_closure_is_always_present_and_always_last(live_documents):
    for gap_id, document in live_documents.items():
        keys = tuple(document["sourceGap"]["check"])
        assert "closure" in keys, (gap_id, keys)
        assert keys[-1] == "closure", (gap_id, keys)


def test_b4_nothing_ahead_of_closure_was_reordered(live_documents):
    """The preceding keys keep their shipped order for both check kinds."""
    seen = set()
    for gap_id, document in live_documents.items():
        check = document["sourceGap"]["check"]
        preceding = tuple(check)[:-1]
        expected = PRECEDING_KEYS["manual" if "manualQuestion" in preceding
                                 else "automated"]
        assert preceding == expected, (gap_id, preceding, expected)
        seen.add(preceding)
    assert seen, "the sweep produced no records -- vacuous"


@pytest.mark.parametrize("shape", sorted(CHECK_SHAPES))
def test_b4_closure_is_last_for_every_synthetic_shape(tmp_path, capsys, shape):
    """The manual arm of `PRECEDING_KEYS` is only reachable synthetically at will."""
    keys = tuple(_prd(tmp_path, shape, capsys)["sourceGap"]["check"])
    assert keys[-1] == "closure", (shape, keys)
    expected = PRECEDING_KEYS["manual" if "manualQuestion" in keys else "automated"]
    assert keys[:-1] == expected, (shape, keys)


# --------------------------------------------------------------------------- behavior 5

def test_b5_exactly_two_distinct_declarations_live(live_documents):
    distinct = {_closure(d)["declaration"] for d in live_documents.values()}
    assert len(distinct) == 2, sorted(distinct)
    assert distinct == set(CLOSURE_DECLARATIONS), sorted(distinct)


def test_b5_each_declaration_is_one_clean_line(live_documents):
    for gap_id, document in live_documents.items():
        declaration = _closure(document)["declaration"]
        assert "\n" not in declaration, (gap_id, declaration)
        assert declaration == declaration.strip(), (gap_id, repr(declaration))
        assert declaration, gap_id


def test_b5_closure_prose_never_self_assesses(live_documents):
    """Closure may not become a second way for a record to argue about its own quality."""
    for gap_id, document in live_documents.items():
        lowered = json.dumps(_closure(document)).lower()
        for token in SELF_ASSESSMENT_TOKENS:
            assert token not in lowered, (gap_id, token, lowered)


def test_b5_the_vocabulary_is_closed_over_the_synthetic_shapes(tmp_path, capsys):
    """No third sentence hides behind a shape the live register has no instance of."""
    emitted = {shape: _closure(_prd(tmp_path, shape, capsys))["declaration"]
               for shape in sorted(CHECK_SHAPES)}
    assert set(emitted.values()) == set(CLOSURE_DECLARATIONS), emitted
    for shape in CHECKABLE_SHAPES:
        assert emitted[shape] == CHECKABLE_DECLARATION, shape
    for shape in REFUSAL_SHAPES:
        assert emitted[shape] == REFUSAL_DECLARATION, shape


# --------------------------------------------------------------------------- behavior 6

@pytest.mark.parametrize("shape", sorted(CHECK_SHAPES))
def test_b6_us002_gains_exactly_one_criterion_appended_last(tmp_path, capsys, shape):
    """A delta against the pre-change list, not a bare count."""
    criteria = _prd(tmp_path, shape, capsys)["stories"][1]["acceptanceCriteria"]
    assert len(criteria) == len(PRECHANGE_US002) + 1, (shape, criteria)
    assert tuple(criteria[:-1]) == PRECHANGE_US002, (shape, criteria)
    assert criteria[-1] not in PRECHANGE_US002, (shape, criteria[-1])
    assert "\n" not in criteria[-1], (shape, criteria[-1])
    assert criteria[-1] == criteria[-1].strip(), (shape, repr(criteria[-1]))


@pytest.mark.parametrize("shape", CHECKABLE_SHAPES)
def test_b6_checkable_criterion_is_derived_from_the_closure_payload(
        tmp_path, capsys, shape):
    """One payload read twice: the criterion carries the machine block's own strings."""
    document = _prd(tmp_path, shape, capsys)
    closure = _closure(document)
    line = document["stories"][1]["acceptanceCriteria"][-1]
    assert closure["verdict"] in line, (shape, line)
    assert closure["rule"]["recordGlob"] in line, (shape, line)
    assert closure["rule"]["field"] in line, (shape, line)


@pytest.mark.parametrize("shape", REFUSAL_SHAPES)
def test_b6_refusal_criterion_names_the_record_and_demands_a_judgement(
        tmp_path, capsys, shape):
    line = _prd(tmp_path, shape, capsys)["stories"][1]["acceptanceCriteria"][-1]
    assert SYNTHETIC_ID in line, (shape, line)
    assert re.search(r"no mitigation signature", line, re.I), (shape, line)
    assert re.search(r"judge?ment", line, re.I), (shape, line)
    assert "ABSENT" not in line, (shape, line)
    assert MITIGATION_FIELD not in line, (shape, line)


def test_b6_us002_carries_five_criteria_live(live_documents):
    """Shape only -- no id set and no record count is pinned."""
    for gap_id, document in live_documents.items():
        criteria = document["stories"][1]["acceptanceCriteria"]
        assert len(criteria) == len(PRECHANGE_US002) + 1, (gap_id, criteria)
        assert tuple(criteria[:-1]) == PRECHANGE_US002, (gap_id, criteria)


# --------------------------------------------------------------------------- behavior 7

@pytest.mark.parametrize("shape", ("both_rules", "manual"))
def test_b7_us001_is_untouched(tmp_path, capsys, shape):
    """Its last item is still the reproduction criterion (pinned by iteration 23)."""
    criteria = _prd(tmp_path, shape, capsys)["stories"][0]["acceptanceCriteria"]
    assert len(criteria) == 5, (shape, criteria)
    assert tuple(criteria[:-1]) == UNTOUCHED_US001_HEAD, (shape, criteria)
    if shape == "both_rules":
        assert SYNTHETIC_GLOB in criteria[-1], criteria[-1]
        assert re.search(r"transcrib", criteria[-1], re.I), criteria[-1]
    else:
        assert re.search(r"no static signature", criteria[-1], re.I), criteria[-1]


@pytest.mark.parametrize("shape", ("both_rules", "manual"))
def test_b7_us003_is_untouched(tmp_path, capsys, shape):
    criteria = _prd(tmp_path, shape, capsys)["stories"][2]["acceptanceCriteria"]
    assert tuple(criteria) == UNTOUCHED_US003, (shape, criteria)


@pytest.mark.parametrize("shape", ("both_rules", "manual"))
def test_b7_closure_did_not_leak_into_the_other_two_stories(tmp_path, capsys, shape):
    document = _prd(tmp_path, shape, capsys)
    for index in (0, 2):
        blob = json.dumps(document["stories"][index])
        for token in CLOSURE_LEAK_TOKENS:
            assert token not in blob, (shape, index, token, blob)


def test_b7_story_identity_and_order_are_untouched(tmp_path, capsys):
    stories = _prd(tmp_path, "both_rules", capsys)["stories"]
    assert [story["id"] for story in stories] == ["US-001", "US-002", "US-003"], stories


# --------------------------------------------------------------------------- behavior 8

#: An angle-bracket placeholder such as `<target>` would be a fabricated invocation.
_PLACEHOLDER = re.compile(r"<[^>\s]+>")


def _path_shaped(text: str) -> list[str]:
    """Whitespace-delimited tokens that look like a path, stripped of trailing prose."""
    return [token.strip(".,;:)(") for token in text.split()
            if "/" in token.strip(".,;:)(")]


def _strings(payload: object) -> list[str]:
    """Every string VALUE inside a JSON-ish payload, at any depth.

    The scan is over values rather than over `json.dumps`, because the dump's own
    punctuation would decorate the very tokens this behaviour has to compare verbatim.
    """
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, dict):
        return [text for value in payload.values() for text in _strings(value)]
    if isinstance(payload, list):
        return [text for item in payload for text in _strings(item)]
    return []


def test_b8_closure_invents_no_invocation(live_documents):
    scanned = 0
    for gap_id, document in live_documents.items():
        for text in _strings(_closure(document)):
            assert "://" not in text, (gap_id, text)
            assert not _PLACEHOLDER.search(text), (gap_id, text)
            for token in _path_shaped(text):
                assert not token.startswith("/"), (gap_id, token)
                assert token == f"gaps/{gap_id}-*.json", (gap_id, token)
            scanned += 1
    assert scanned, "no closure string was scanned -- vacuous"


def test_b8_the_new_criterion_invents_no_invocation(live_documents):
    """The delta guard is load-bearing: without it this passes on a document whose last
    US-002 item is still the pre-change `No new runtime dependency`, i.e. it would assert
    a negative about a criterion this iteration never added.  Measured: the un-guarded
    form PASSES against `PRECHANGE_COMMIT`.
    """
    for gap_id, document in live_documents.items():
        criteria = document["stories"][1]["acceptanceCriteria"]
        assert len(criteria) == len(PRECHANGE_US002) + 1, (gap_id, criteria)
        line = criteria[-1]
        assert line not in PRECHANGE_US002, (gap_id, line)
        assert "://" not in line, (gap_id, line)
        assert not _PLACEHOLDER.search(line), (gap_id, line)
        for token in _path_shaped(line):
            assert not token.startswith("/"), (gap_id, token)
            assert token == f"gaps/{gap_id}-*.json", (gap_id, token)


def test_b8_the_register_path_never_reaches_the_document(tmp_path, capsys):
    """A tmp_path register is the control an absolute path would show up in."""
    register = _write_register(tmp_path / "leak" / "gaps", CHECK_SHAPES["both_rules"])
    code, out, err = _run(["prd", str(register)], capsys)
    assert (code, err) == (0, ""), (code, err)
    assert str(tmp_path) not in out, out
    assert str(REPO) not in out, out


# --------------------------------------------------------------------------- behavior 9

@pytest.fixture()
def present_target(tmp_path) -> pathlib.Path:
    """A one-file tree the `both_rules` check verdicts PRESENT against.

    `present_when` matches `dangerous_call` and `mitigated_when` matches
    `checkpoint_write`; only the first is here, so the mitigation cannot fire.
    """
    tree = tmp_path / "target"
    tree.mkdir(parents=True)
    (tree / "app.py").write_text("def step():\n    dangerous_call()\n", encoding="utf-8")
    return tree


def test_b9_the_target_really_verdicts_present(tmp_path, capsys, present_target):
    """Control: without this, behavior 9 could compare two documents about nothing."""
    register = _write_register(tmp_path / "b9" / "gaps", CHECK_SHAPES["both_rules"])
    code, out, err = _run(
        ["scan", str(present_target), "--gaps", str(register), "--json"], capsys)
    assert (code, err) == (0, ""), (code, err)
    assert "PRESENT" in out, out


def test_b9_scan_prd_and_prd_emit_the_same_check_bytes(tmp_path, capsys, present_target):
    """One emitter, both surfaces -- key ORDER included, so this is a byte comparison."""
    register = _write_register(tmp_path / "b9" / "gaps", CHECK_SHAPES["both_rules"])

    code, out, err = _run(["prd", str(register)], capsys)
    assert (code, err) == (0, ""), (code, err)
    from_prd = json.loads(out)["sourceGap"]["check"]

    code, out, err = _run(
        ["scan", str(present_target), "--gaps", str(register), "--prd"], capsys)
    assert (code, err) == (0, ""), (code, err)
    from_scan = json.loads(out)["sourceGap"]["check"]

    assert json.dumps(from_scan, indent=2) == json.dumps(from_prd, indent=2)
    assert from_scan["closure"]["verdict"] == "ABSENT", from_scan


# -------------------------------------------------------------------------- behavior 10

TOP_LEVEL_KEYS = ("project", "branchName", "description", "sourceGap", "stories")
SOURCE_GAP_KEYS = ("id", "layer", "gapType", "priority", "confidence", "evidence",
                   "check", "status")


def test_b10_live_prd_exits_zero_with_a_silent_stderr(capsys):
    code, out, err = _run(["prd", str(LIVE_GAPS)], capsys)
    assert (code, err) == (0, ""), (code, err)
    assert out, "the document is empty"


def test_b10_live_prd_is_byte_identical_across_two_runs(capsys):
    first = _run(["prd", str(LIVE_GAPS)], capsys)[1]
    second = _run(["prd", str(LIVE_GAPS)], capsys)[1]
    assert first == second, "the document is not deterministic"


def test_b10_the_document_ends_in_exactly_one_newline(capsys):
    out = _run(["prd", str(LIVE_GAPS)], capsys)[1]
    assert out.endswith("\n"), repr(out[-20:])
    assert not out.endswith("\n\n"), repr(out[-20:])


def test_b10_the_published_key_sets_are_unchanged(live_documents):
    """The appended key is nested inside `check`, so neither published set moves."""
    for gap_id, document in live_documents.items():
        assert tuple(document) == TOP_LEVEL_KEYS, (gap_id, tuple(document))
        assert tuple(document["sourceGap"]) == SOURCE_GAP_KEYS, (
            gap_id, tuple(document["sourceGap"]))


def test_b10_a_missing_register_keeps_the_error_vocabulary(tmp_path, capsys):
    code, out, err = _run(["prd", str(tmp_path / "absent")], capsys)
    assert code == 2, (code, out, err)
    assert out == "", out
    assert err.startswith("Error: "), err
    assert err.endswith("\n") and not err.endswith("\n\n"), repr(err)
# =====================================================================================
# EXTENSION -- retry round.  Every test below was added because the ANTI-VACUITY pass
# (this module run against `PRECHANGE_COMMIT`'s own `src`, selected by `sys.path` alone)
# showed the checkpoint round left one pin a pre-change implementation could already
# satisfy, and left three claims of the spec asserted only synthetically.
# =====================================================================================


def _prd_for_check(directory: pathlib.Path, check: object, capsys) -> dict:
    """The prd document for a one-record register carrying an ARBITRARY check payload.

    `_prd` can only reach the five named shapes; behaviors 1 and 8 need checks that differ
    from each other in the mitigation rule's CONTENT while holding its presence fixed.
    """
    register = _write_register(directory / "gaps", check)
    code, out, err = _run(["prd", str(register)], capsys)
    assert (code, err) == (0, ""), (code, err)
    return json.loads(out)


# ------------------------------------------- behavior 1/2: the LIVE arm, against DATA

def _declares_mitigation(path: pathlib.Path) -> tuple[str, bool]:
    """`(id, does the record file itself declare a non-null mitigated_when)`."""
    record = json.loads(path.read_text(encoding="utf-8"))
    check = record.get("check")
    return record["id"], bool(check) and check.get("mitigated_when") is not None


def test_b1_the_live_arm_is_decided_by_the_register_s_own_mitigated_when(live_documents):
    """The register FILES are the ground truth the emitted arm is checked against.

    Every other arm assertion in this module is synthetic, where the shapes were built by
    this module and so cannot catch an arm keyed on something merely CORRELATED with
    `mitigated_when` in those five hand-made records.  Here the expectation is read out of
    `gaps/*.json` -- data, not implementation -- record by record.  Nothing is pinned: the
    id set, the counts and the split all come from the register as it stands.
    """
    declared = dict(_declares_mitigation(path) for path in LIVE_GAPS.glob("*.json"))
    assert set(declared) == set(live_documents), (
        sorted(set(declared) ^ set(live_documents)))
    checkable = refusing = 0
    for gap_id, document in live_documents.items():
        closure = _closure(document)
        if declared[gap_id]:
            assert closure["verdict"] == "ABSENT", (gap_id, closure)
            assert closure["rule"] == {"recordGlob": f"gaps/{gap_id}-*.json",
                                       "field": MITIGATION_FIELD}, (gap_id, closure)
            assert closure["declaration"] == CHECKABLE_DECLARATION, gap_id
            checkable += 1
        else:
            assert closure["verdict"] is None, (gap_id, closure)
            assert closure["rule"] is None, (gap_id, closure)
            assert closure["declaration"] == REFUSAL_DECLARATION, gap_id
            refusing += 1
    assert checkable, "no live record declares a mitigation -- the checkable arm is vacuous"
    assert refusing, "no live record refuses -- the refusal arm is vacuous here"


# ---------------------------- behavior 1 + acceptance: READ, never RE-EVALUATED

#: Mitigation rules that differ in kind, globs and body.  Shapes 2 and 3 are transcribed
#: from live records (`file_exists`, `any_of`), so the register is known to accept them.
_ALT_MITIGATIONS = (
    {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "checkpoint_write"},
    {"kind": "file_exists", "globs": ["evals/**", "**/zzz_no_such_dir/**"]},
    {"kind": "any_of", "rules": [
        {"kind": "content_matches", "globs": ["**/*.md"], "pattern": "alpha|beta"},
        {"kind": "content_matches", "globs": ["docs/**"], "pattern": "gamma"},
    ]},
)


def _with_mitigation(rule: object) -> dict:
    return {"id": "CHK-001", "present_when": _PRESENT_RULE, "mitigated_when": rule,
            "fixtures": _FIXTURES}


@pytest.mark.parametrize("index", range(1, len(_ALT_MITIGATIONS)))
def test_b1_closure_is_keyed_on_the_rule_s_presence_not_its_content(
        tmp_path, capsys, index):
    """`mitigated_when` is READ, never re-evaluated -- so its BODY cannot move the output.

    Two registers identical but for the mitigation rule (a different kind, different
    globs, a body that matches nothing anywhere) must emit a byte-identical closure
    object.  A closure that evaluated the rule, or echoed any part of it, would differ.
    """
    baseline = _closure(_prd_for_check(
        tmp_path / "base", _with_mitigation(_ALT_MITIGATIONS[0]), capsys))
    variant = _closure(_prd_for_check(
        tmp_path / f"alt{index}", _with_mitigation(_ALT_MITIGATIONS[index]), capsys))
    assert baseline["verdict"] == "ABSENT", baseline
    assert json.dumps(variant, indent=2) == json.dumps(baseline, indent=2), (
        index, variant, baseline)


# ------------------------------- behavior 8: a POINTER is published, never the rule body

_SENTINEL_PATTERN = "ZZQQ_MITIGATION_SENTINEL_QQZZ"
_SENTINEL_DIR = "zzqq_sentinel_dir"


def test_b8_the_mitigation_rule_s_own_body_never_reaches_the_document(tmp_path, capsys):
    """The closure names WHERE the rule lives, so it may not carry the rule itself.

    A published rule body would be the fabricated-invocation failure in its subtlest
    form: a glob or regex from the register read by a loop as something to run.  The
    sentinels are strings no other part of this product can produce.
    """
    check = _with_mitigation({"kind": "content_matches",
                              "globs": [f"**/{_SENTINEL_DIR}/*.py"],
                              "pattern": _SENTINEL_PATTERN})
    document = _prd_for_check(tmp_path / "sentinel", check, capsys)
    assert _closure(document)["verdict"] == "ABSENT", document
    blob = json.dumps(document)
    assert _SENTINEL_PATTERN not in blob, blob
    assert _SENTINEL_DIR not in blob, blob
    assert "content_matches" not in blob, blob
    # The only thing the document may say about the rule is WHERE it lives, and it must
    # say exactly that twice -- once in the machine block, once in the US-002 criterion.
    # That count IS the acceptance criterion "built ONCE and read twice", measured.
    assert blob.count("mitigated_when") == blob.count(MITIGATION_FIELD), blob
    assert blob.count(MITIGATION_FIELD) == 2, blob.count(MITIGATION_FIELD)


@pytest.mark.parametrize("shape", REFUSAL_SHAPES)
def test_b2_the_refusal_publishes_no_pointer_at_all(tmp_path, capsys, shape):
    """An explicit null is the whole payload: no glob, no field name, no half-pointer."""
    blob = json.dumps(_closure(_prd(tmp_path, shape, capsys)))
    assert MITIGATION_FIELD not in blob, (shape, blob)
    assert "recordGlob" not in blob, (shape, blob)
    assert SYNTHETIC_GLOB not in blob, (shape, blob)


# ------------------------------------ behavior 6: one payload read twice, over the LIVE

#: Verdicts this product has but the closure of a register-only read may never assert.
_OTHER_VERDICTS = ("PRESENT", "PARTIAL", "UNKNOWN", "MITIGATED")


def test_b6_the_live_criterion_and_the_machine_block_never_disagree(live_documents):
    """Over every live record, not just the five synthetic shapes.

    A second derivation would show up here as an arm mismatch on any record whose two
    code paths read the check differently, which is exactly what "built ONCE and read
    twice" is supposed to make impossible.
    """
    checkable = refusing = 0
    for gap_id, document in live_documents.items():
        closure = _closure(document)
        line = document["stories"][1]["acceptanceCriteria"][-1]
        if closure["verdict"] is None:
            assert gap_id in line, (gap_id, line)
            assert "ABSENT" not in line, (gap_id, line)
            assert MITIGATION_FIELD not in line, (gap_id, line)
            refusing += 1
        else:
            assert closure["verdict"] in line, (gap_id, line)
            assert closure["rule"]["recordGlob"] in line, (gap_id, line)
            assert closure["rule"]["field"] in line, (gap_id, line)
            checkable += 1
        for token in _OTHER_VERDICTS:
            assert token not in line, (gap_id, token, line)
            assert token not in json.dumps(closure), (gap_id, token, closure)
    assert checkable and refusing, (checkable, refusing)


# --------------------------------------- behavior 9: the refusal arm crosses too

def test_b9_scan_prd_and_prd_agree_on_the_refusal_arm_too(tmp_path, capsys,
                                                          present_target):
    """The checkable arm crossing both surfaces does not prove the refusal arm does."""
    register = _write_register(tmp_path / "b9refusal" / "gaps",
                               CHECK_SHAPES["present_only"])

    code, out, err = _run(["prd", str(register)], capsys)
    assert (code, err) == (0, ""), (code, err)
    from_prd = json.loads(out)["sourceGap"]["check"]

    code, out, err = _run(
        ["scan", str(present_target), "--gaps", str(register), "--prd"], capsys)
    assert (code, err) == (0, ""), (code, err)
    from_scan = json.loads(out)["sourceGap"]["check"]

    assert json.dumps(from_scan, indent=2) == json.dumps(from_prd, indent=2)
    assert from_scan["closure"] == {"verdict": None, "rule": None,
                                    "declaration": REFUSAL_DECLARATION}, from_scan


# ------------------------------------- behavior 10: stability on the appended arm too

@pytest.mark.parametrize("shape", sorted(CHECK_SHAPES))
def test_b10_every_shape_is_deterministic_and_ends_in_one_newline(tmp_path, capsys,
                                                                  shape):
    """Behavior 10 was asserted only over the live register, where four of the five
    shapes have no instance -- `mitigation_only` has none at all.
    """
    register = _write_register(tmp_path / shape / "gaps", CHECK_SHAPES[shape])
    first = _run(["prd", str(register)], capsys)
    second = _run(["prd", str(register)], capsys)
    assert first == second, shape
    code, out, err = first
    assert (code, err) == (0, ""), (shape, code, err)
    assert out.endswith("\n"), (shape, repr(out[-20:]))
    assert not out.endswith("\n\n"), (shape, repr(out[-20:]))
