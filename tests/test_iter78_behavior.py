"""Iteration 78 behaviors: the loader inspects each GLOB ELEMENT, not just the globs list.

`_validate_rule` type-checked the `globs` LIST and never its members, so a leaf rule
carrying a non-`str` element was CERTIFIED by the schema and then crashed the scan. This
file drives the one door the spec names -- `Gap.model_validate`, equivalently
`radar validate` -- and asserts the refusal, its message, its CLI surface, and the two
things the change must NOT move: the live register, and the glob shapes the fix pass
deliberately STRUCK.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors (as amended by the fix pass); every
claim is measured by CALLING the public loader or by RUNNING the packaged entry point.

Structural notes, so a green dot here cannot mean less than it looks like:

* **Every refusal is paired with an ACCEPTANCE of the same shape.** A record-level
  validator sitting beside the one under test (the two-sided-fixture rule on `check`) can
  refuse a probe record for its OWN reason, and a sibling's refusal is indistinguishable
  from ours. So each parametrized refusal has an all-`str` control built by the same
  helper: the control must LOAD, which is what makes the refusal attributable.
* **The struck limbs are pinned as ACCEPTED, not left unmentioned.** Behaviors 2, 3 and 4
  (blank, absolute, `..`) were decided against because `tests/test_iter26_behavior.py`
  depends on `""` and `/etc/**` being schema-valid. A test that only asserted refusals
  would let a later "obvious" tightening pass this file and red iteration 26's, so the
  accepted shapes are asserted here, with the reason, at the same door.
* **The deliberate asymmetry is asserted in ONE test.** A blank GLOB element loads; a
  blank PATTERN is refused. Those two live in the same function and look like an
  inconsistency, so they are measured side by side rather than in separate files.
* **The register walker is proven to FIND a planted non-`str` before its silence over the
  real register is believed.** A walker that returned no elements would satisfy "every
  live glob element is a string" for free.
* **The live-register expectations are FLOORS, never keyed equalities.** This register is
  grown by an unattended research pass, so `== 16` would go red against a CORRECT register;
  the record count in the `validate` line is derived from disk and compared to it.
* **No absolute machine path and no personal identifier appears here**: the repo root is
  derived from `__file__` and every fixture register lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from pydantic import ValidationError

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`). Same boot line as `test_iter26_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

MARKER_PRESENT = "AGR78_SIGNATURE_SEEN"
MARKER_MITIGATED = "AGR78_MITIGATION_SEEN"

#: The four leaf kinds the spec enumerates. Each one carries a `globs` list.
LEAF_KINDS = ("file_exists", "file_absent", "content_matches", "content_absent")

#: The two leaf kinds that also carry a `pattern` (behavior 8's control lives here).
CONTENT_KINDS = ("content_matches", "content_absent")

#: Behavior 1: the three non-`str` elements the spec names, all ACCEPTED at HEAD.
NON_STR_ELEMENTS = (123, None, ["a"])

#: Behaviors 2/3/4, STRUCK by the fix pass: these stay schema-VALID on purpose.
#: `""` and `/etc/**` are load-bearing for `tests/test_iter26_behavior.py`; `..` was
#: measured enumerating zero files, so refusing it would be a quality rule, not containment.
STRUCK_GLOB_ELEMENTS = ("", "   ", "\t", "/etc/**", "../x", "a/../b", "**/../y", "a//b")

#: Behavior 8: whitespace-only patterns, ACCEPTED at HEAD by a truthiness test.
BLANK_PATTERNS = ("   ", "\t", " \t ", "\n")

#: The refusal a bad regex keeps (behavior 8's "existing refusals are unchanged" half).
BAD_REGEX = "(unclosed"


def _glob_message(kind: str, element: object) -> str:
    """The message grammar behavior 1 requires: the field named, the element's `repr`."""
    return f"{kind} requires each 'globs' element to be a string, got {element!r}"


def _pattern_message(kind: str) -> str:
    """The existing `pattern` refusal idiom, which behavior 8 must reuse verbatim."""
    return f"{kind} requires a 'pattern' string"


def _leaf(kind: str, globs: list, pattern: str = MARKER_MITIGATED) -> dict:
    """One leaf rule of the given kind carrying `globs`."""
    rule: dict = {"kind": kind, "globs": globs}
    if kind in CONTENT_KINDS:
        rule["pattern"] = pattern
    return rule


def _record(rule: dict, gid: str = "GAP-001") -> dict:
    """A schema-valid register record whose `mitigated_when` carries the rule under test.

    Every other field is filled the way `tests/test_iter26_behavior.py` fills a fixture
    record, so the record-level validators (closed vocabularies, the two-sided `fixtures`
    rule on `check`) are all satisfied and cannot supply the refusal we are attributing to
    the glob-element rule.
    """
    return {
        "id": gid,
        "title": "Fixture gap for the element-level glob rule",
        "layer": "lifecycle-deploy",
        "gap_type": "silent-failure",
        "status": "open",
        "problem": "A synthetic record that carries one glob list through the loader.",
        "symptom": "Nothing real; this record exists only to exercise schema refusal.",
        "why_now": "The schema type-checked the globs list and never its elements.",
        "existing": ["Nothing; this is a fixture and claims no prior art."],
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [{
            "source_class": "first-party-field",
            "title": "Fixture citation for a fixture record",
            "locator": "https://example.invalid/fixture/notes.md",
            "date": "2026-08-20",
            "quote": "A glob that can never match is not checkable.",
        }],
        "build_hypothesis": "Validate each glob element at the ingest door.",
        "tags": ["fixture"],
        "check": {
            "id": "CHK-001",
            "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                             "pattern": MARKER_PRESENT},
            "mitigated_when": rule,
            "manual_question": "Does the loader inspect each glob element?",
            "rationale": "Fixture check; its only job is to carry a glob list.",
            "fixtures": {
                "bad": {"pkg/a.py": MARKER_PRESENT + "\n"},
                "good": {"pkg/a.py": MARKER_MITIGATED + "\n"},
            },
        },
    }


#: pydantic prefixes a validator-raised `ValueError` with this, and the CLI renders the
#: prefixed form (`Error: ... 1 schema error(s): Value error, <message>`), so it is asserted
#: rather than tolerated: it is the evidence the refusal travelled as a `ValueError`.
VALUE_ERROR_PREFIX = "Value error, "


def _refusal(rule: dict) -> str:
    """Load a record carrying `rule`; return the one schema message it is refused with.

    Fails the test if the record LOADS, and fails it if more than one error is reported --
    a probe that trips two validators cannot attribute the refusal to either. The
    `Value error, ` prefix is asserted and then stripped, so the returned string is the
    message the validator itself wrote.
    """
    with pytest.raises(ValidationError) as excinfo:
        Gap.model_validate(_record(rule))
    errors = excinfo.value.errors()
    assert len(errors) == 1, f"expected exactly one schema error, got {len(errors)}: {errors}"
    msg = errors[0]["msg"]
    assert msg.startswith(VALUE_ERROR_PREFIX), (
        f"the refusal did not travel as a ValueError: {msg!r}")
    return msg[len(VALUE_ERROR_PREFIX):]


def _loads(rule: dict) -> Gap:
    """Load a record carrying `rule`, asserting it is ACCEPTED. The anti-vacuity control."""
    try:
        return Gap.model_validate(_record(rule))
    except ValidationError as exc:  # pragma: no cover -- only on a regression
        pytest.fail(f"a record the loader must accept was refused:\n{exc}")


def _register(tmp_path: pathlib.Path, rule: dict) -> pathlib.Path:
    """A one-record register directory on disk, for the CLI surface of behavior 7."""
    root = tmp_path / "register"
    (root / "gaps").mkdir(parents=True, exist_ok=True)
    (root / "gaps" / "GAP-001-fixture.json").write_text(
        json.dumps(_record(rule), indent=2) + "\n", encoding="utf-8")
    return root


def _validate_cli(register: pathlib.Path) -> subprocess.CompletedProcess[bytes]:
    """`radar validate <register>` across a real process boundary, bytes not text."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, "validate", str(register)],
        cwd=str(REPO_ROOT), capture_output=True, timeout=180)


# --- behavior 1: a non-`str` glob element is refused, in every leaf kind ------


@pytest.mark.parametrize("kind", LEAF_KINDS)
@pytest.mark.parametrize("element", NON_STR_ELEMENTS, ids=["int", "none", "list"])
def test_b1_non_str_glob_element_is_refused_in_every_leaf_kind(kind, element):
    """Behavior 1. All twelve combinations are ACCEPTED at HEAD; all must now be refused."""
    msg = _refusal(_leaf(kind, ["**/*.py", element]))
    assert msg == _glob_message(kind, element), (
        f"{kind} with element {element!r} was refused with an unexpected message: {msg!r}")


@pytest.mark.parametrize("kind", LEAF_KINDS)
@pytest.mark.parametrize("element", NON_STR_ELEMENTS, ids=["int", "none", "list"])
def test_b1_message_names_the_field_and_the_rejected_element_repr(kind, element):
    """Behavior 1's message contract, asserted by part so a reword still names both."""
    msg = _refusal(_leaf(kind, [element]))
    assert "globs" in msg, f"the message does not name the field: {msg!r}"
    assert repr(element) in msg, f"the message does not carry repr({element!r}): {msg!r}"
    assert msg.startswith(f"{kind} requires"), (
        f"the message does not follow the existing idiom of this function: {msg!r}")


@pytest.mark.parametrize("kind", LEAF_KINDS)
def test_b1_control_an_all_str_globs_list_still_loads(kind):
    """ANTI-VACUITY. Without this, every refusal above could come from a sibling validator."""
    _loads(_leaf(kind, ["**/*.py", "pkg/*.py", "evals/**"]))


def test_b1_one_shared_rule_gives_all_four_kinds_the_same_verdict():
    """Acceptance criterion: ONE element rule, so the four leaf kinds cannot disagree."""
    verdicts = {kind: _refusal(_leaf(kind, [123])) for kind in LEAF_KINDS}
    tails = {msg.split("requires", 1)[1] for msg in verdicts.values()}
    assert len(tails) == 1, (
        f"the four leaf kinds disagree about the same bad element: {verdicts}")


# --- behavior 5: the refusal reaches nested rules -----------------------------


def _nested(kind: str, inner: dict) -> dict:
    """A combinator wrapping `inner`, in the register's own syntax (`rules` / `rule`)."""
    return {"kind": kind, "rule": inner} if kind == "not" else {"kind": kind, "rules": [inner]}


@pytest.mark.parametrize("combinator", ["any_of", "all_of", "not"])
@pytest.mark.parametrize("element", NON_STR_ELEMENTS, ids=["int", "none", "list"])
def test_b5_a_bad_glob_nested_in_a_combinator_is_refused_identically(combinator, element):
    """Behavior 5. The message is the LEAF's message: recursion must not rewrap it."""
    inner = _leaf("file_exists", [element])
    msg = _refusal(_nested(combinator, inner))
    assert msg == _glob_message("file_exists", element), (
        f"{combinator} reported a different message than the bare leaf: {msg!r}")


@pytest.mark.parametrize("combinator", ["any_of", "all_of", "not"])
def test_b5_control_a_combinator_over_good_globs_still_loads(combinator):
    """ANTI-VACUITY for behavior 5: the combinator shapes themselves must still load."""
    _loads(_nested(combinator, _leaf("content_matches", ["**/*.py"])))


def test_b5_refusal_survives_two_levels_of_nesting():
    """Behavior 5 at depth: `any_of` over `not` over a leaf. Recursion is not one level deep."""
    deep = {"kind": "any_of", "rules": [{"kind": "not", "rule": _leaf("file_absent", [None])}]}
    assert _refusal(deep) == _glob_message("file_absent", None)


def test_b5_refusal_reaches_a_sibling_rule_position():
    """A combinator whose FIRST member is fine and whose SECOND is bad still refuses.

    Reasonable-reading extension of behavior 5: a recursion that stopped at the first
    member would pass every test above. Noted as PM feedback, not as spec text.
    """
    rule = {"kind": "all_of", "rules": [_leaf("file_exists", ["**/*.py"]),
                                        _leaf("file_exists", [123])]}
    assert _refusal(rule) == _glob_message("file_exists", 123)


@pytest.mark.parametrize("slot", ["applies_when", "present_when", "mitigated_when"])
def test_b5_every_rule_slot_goes_through_the_same_door(slot):
    """Reasonable-reading extension: the spec calls `_validate_rule` "the one door".

    A rule slot that skipped element validation would leave the same crash reachable, so
    all three slots are driven. Flagged as an ambiguity note in the report.
    """
    record = _record(_leaf("content_matches", ["**/*.py"]))
    record["check"][slot] = _leaf("file_exists", [123])
    with pytest.raises(ValidationError) as excinfo:
        Gap.model_validate(record)
    assert _glob_message("file_exists", 123) in str(excinfo.value)


# --- behaviors 2/3/4: STRUCK, so the accepted shapes are pinned ---------------


@pytest.mark.parametrize("element", STRUCK_GLOB_ELEMENTS)
@pytest.mark.parametrize("kind", LEAF_KINDS)
def test_struck_glob_shapes_remain_schema_valid(kind, element):
    """Behaviors 2, 3 and 4 were DECIDED AGAINST, and this is the guard for that decision.

    `""` and `/etc/**` are asserted schema-valid by five committed tests in
    `tests/test_iter26_behavior.py` (they are that file's dead-glob control), and a `..`
    glob was measured enumerating zero files, so none of these is a containment hole. If a
    later round "finishes the job" by refusing them, this file goes red first and names the
    reason, instead of iteration 26's suite going red without one.
    """
    _loads(_leaf(kind, [element]))


def test_the_blank_glob_and_blank_pattern_asymmetry_is_deliberate():
    """One blank string is accepted and the other refused; both are measured side by side.

    A future round that "unified" the two would silently either red iteration 26's dead-glob
    control (refusing the glob) or reopen the accepted-vacuous-pattern hole (accepting the
    pattern), so the asymmetry is asserted in a single function with its reason attached.
    """
    _loads(_leaf("content_matches", [""], pattern=MARKER_MITIGATED))
    assert _refusal(_leaf("content_matches", ["**/*.py"], pattern="   ")) == \
        _pattern_message("content_matches")


# --- behavior 8: the two-sided `pattern` control in the same function --------


@pytest.mark.parametrize("pattern", BLANK_PATTERNS, ids=["spaces", "tab", "mixed", "newline"])
@pytest.mark.parametrize("kind", CONTENT_KINDS)
def test_b8_a_whitespace_only_pattern_is_now_refused(kind, pattern):
    """Behavior 8's red side: a truthiness test ACCEPTS these at HEAD; a strip test refuses."""
    assert _refusal(_leaf(kind, ["**/*.py"], pattern=pattern)) == _pattern_message(kind)


@pytest.mark.parametrize("kind", CONTENT_KINDS)
def test_b8_the_empty_pattern_keeps_its_existing_refusal_and_message(kind):
    """Behavior 8: `pattern=""` was already refused, with this message. Unchanged."""
    assert _refusal(_leaf(kind, ["**/*.py"], pattern="")) == _pattern_message(kind)


@pytest.mark.parametrize("kind", CONTENT_KINDS)
def test_b8_a_non_str_pattern_keeps_its_existing_refusal(kind):
    """The `pattern` slot's own type refusal is untouched by the strip rule."""
    assert _refusal(_leaf(kind, ["**/*.py"], pattern=123)) == _pattern_message(kind)


@pytest.mark.parametrize("kind", CONTENT_KINDS)
def test_b8_an_uncompilable_pattern_keeps_its_distinct_regex_refusal(kind):
    """Behavior 8: `"(unclosed"` must still be refused AS A REGEX, not as a blank string.

    Two different defects must not collapse onto one message, so this asserts the regex
    refusal is present AND that it is not the blank-pattern message.
    """
    msg = _refusal(_leaf(kind, ["**/*.py"], pattern=BAD_REGEX))
    assert "invalid regex" in msg, f"the regex refusal lost its own wording: {msg!r}"
    assert BAD_REGEX in msg, f"the message does not carry the offending pattern: {msg!r}"
    assert msg != _pattern_message(kind), (
        "an uncompilable pattern collapsed onto the blank-pattern message")


@pytest.mark.parametrize("kind", CONTENT_KINDS)
def test_b8_control_a_real_pattern_still_loads(kind):
    """ANTI-VACUITY for behavior 8: patterns with content, including leading whitespace."""
    _loads(_leaf(kind, ["**/*.py"], pattern=MARKER_MITIGATED))
    _loads(_leaf(kind, ["**/*.py"], pattern="  " + MARKER_MITIGATED))


# --- behavior 6: every live record still loads, and the rule refuses none of it


def _live_record_paths() -> list[pathlib.Path]:
    return sorted((REPO_ROOT / "gaps").glob("*.json"))


def _walk_globs(rule: object) -> list[object]:
    """Every element of every `globs` list at any depth of a rule tree, in document order."""
    found: list[object] = []
    if isinstance(rule, dict):
        globs = rule.get("globs")
        if isinstance(globs, list):
            found.extend(globs)
        for key in ("rules", "rule"):
            child = rule.get(key)
            if isinstance(child, list):
                for member in child:
                    found.extend(_walk_globs(member))
            elif child is not None:
                found.extend(_walk_globs(child))
    return found


def test_the_glob_walker_finds_a_planted_element_at_every_depth():
    """POSITIVE CONTROL for the walker below. A walker returning [] would pass for free."""
    planted = {
        "kind": "all_of",
        "rules": [
            _leaf("file_exists", ["top"]),
            {"kind": "any_of", "rules": [_leaf("file_exists", ["nested"])]},
            {"kind": "not", "rule": _leaf("file_exists", ["negated", 123])},
        ],
    }
    assert _walk_globs(planted) == ["top", "nested", "negated", 123]


def test_b6_every_live_register_record_still_loads():
    """Behavior 6. The one assertion that would catch an over-broad rule on real data."""
    paths = _live_record_paths()
    assert len(paths) >= 16, f"expected at least 16 live records, found {len(paths)}"
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        try:
            Gap.model_validate(record)
        except ValidationError as exc:  # pragma: no cover -- only on a regression
            pytest.fail(f"live record {path.name} no longer loads:\n{exc}")


def test_b6_the_rule_refuses_no_glob_the_live_register_carries():
    """Acceptance criterion, re-measured here instead of trusted from the spec text.

    The spec measured 171 glob occurrences over 41 distinct patterns and 0 refusals, and
    those two counts reproduce here EXACTLY. Its "across 15 of 16 records" is the count of
    records carrying a `check` (15); of those, 12 carry globs, because three checks are
    manual-only with all three rule slots null. Both are asserted, separately and named,
    so the discrepancy cannot be re-discovered as a defect later.

    Every count is a FLOOR, never a keyed equality: this register is grown by an unattended
    research pass, so `== 171` would red against a CORRECT register.
    """
    occurrences: list[object] = []
    records_with_globs = 0
    records_with_a_check = 0
    for path in _live_record_paths():
        record = json.loads(path.read_text(encoding="utf-8"))
        check = record.get("check") or {}
        if check:
            records_with_a_check += 1
        found: list[object] = []
        for slot in ("applies_when", "present_when", "mitigated_when"):
            found.extend(_walk_globs(check.get(slot)))
        if found:
            records_with_globs += 1
        occurrences.extend(found)

    non_str = [g for g in occurrences if not isinstance(g, str)]
    assert non_str == [], f"the live register carries glob elements this rule refuses: {non_str}"
    assert len(occurrences) >= 171, f"expected >=171 glob occurrences, found {len(occurrences)}"
    assert len(set(occurrences)) >= 41, (
        f"expected >=41 distinct glob patterns, found {len(set(occurrences))}")
    assert records_with_a_check >= 15, (
        f"expected >=15 records carrying a check, found {records_with_a_check}")
    assert records_with_globs >= 12, (
        f"expected >=12 records carrying globs, found {records_with_globs}")


def test_b6_radar_validate_on_the_live_register_stays_green(capsys):
    """Behavior 6's CLI half: exit 0, the OK line, empty stderr.

    The record count is DERIVED from disk rather than pinned, so a grown register does not
    red this. The byte length of the line is asserted against the same derived count, which
    is what "stdout bytes unchanged" means for a register that legitimately grows.
    """
    assert main(["validate", str(REPO_ROOT)]) == 0
    captured = capsys.readouterr()
    expected = f"OK: {len(_live_record_paths())} gap record(s) valid.\n"
    assert captured.out == expected, f"stdout moved: {captured.out!r} != {expected!r}"
    assert captured.err == "", f"validate wrote to stderr: {captured.err!r}"


# --- behavior 7: the refusal's CLI surface -----------------------------------


def test_b7_a_refused_record_exits_2_with_error_on_stderr_and_no_stdout(tmp_path):
    """Behavior 7, in process bytes: `Error: ` on stderr, exit 2, ZERO stdout bytes."""
    proc = _validate_cli(_register(tmp_path, _leaf("content_matches", ["**/*.py", 123])))
    assert proc.returncode == 2, (
        f"expected exit 2, got {proc.returncode}; stderr={proc.stderr.decode()!r}")
    assert proc.stdout == b"", f"stdout must carry only the document: {proc.stdout!r}"
    err = proc.stderr.decode("utf-8")
    assert err.startswith("Error: "), f"stderr is not prefixed as the bar requires: {err!r}"
    assert _glob_message("content_matches", 123) in err, (
        f"the CLI hid the schema message: {err!r}")
    assert "Traceback" not in err, f"a traceback reached stderr: {err!r}"


def test_b7_control_the_same_register_with_good_globs_exits_0(tmp_path):
    """ANTI-VACUITY for behavior 7: the fixture register itself must be loadable."""
    proc = _validate_cli(_register(tmp_path, _leaf("content_matches", ["**/*.py"])))
    assert proc.returncode == 0, (
        f"the control register did not load: {proc.stderr.decode()!r}")
    assert proc.stdout == b"OK: 1 gap record(s) valid.\n", f"stdout moved: {proc.stdout!r}"
    assert proc.stderr == b"", f"stderr not empty: {proc.stderr!r}"


def _scan_cli(target: pathlib.Path,
              register: pathlib.Path) -> subprocess.CompletedProcess[bytes]:
    """`radar scan <target> --gaps <register>` across a real process boundary."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, "scan", str(target), "--gaps", str(register)],
        cwd=str(REPO_ROOT), capture_output=True, timeout=180)


def _target(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal scannable target: one Python file carrying the present-side marker."""
    root = tmp_path / "target"
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "a.py").write_text(f"x = {MARKER_PRESENT!r}\n", encoding="utf-8")
    return root


def test_the_crash_the_refusal_exists_to_prevent_is_now_unreachable(tmp_path):
    """The harm named in the spec's Why, driven end to end rather than argued.

    At HEAD the pair was: `validate` exit 0 (the record is CERTIFIED), then `scan` exit 1
    with a traceback and ZERO document bytes -- the one outcome the CLI contract forbids,
    and unreachable from the matcher because the crash precedes the regex. A load-time
    refusal must convert that into the ordinary schema refusal on BOTH verbs.

    Nothing here asserts anything about scan-time matching: the register never reaches the
    matcher, which is exactly the claim.
    """
    register = _register(tmp_path, _leaf("content_matches", ["**/*.py", 123]))
    proc = _scan_cli(_target(tmp_path), register)
    assert proc.returncode == 2, (
        f"expected the schema refusal's exit 2, got {proc.returncode}; "
        f"stderr={proc.stderr.decode()!r}")
    assert proc.stdout == b"", f"a refused scan must emit no document: {proc.stdout!r}"
    err = proc.stderr.decode("utf-8")
    assert err.startswith("Error: "), f"stderr is not prefixed as the bar requires: {err!r}"
    assert "Traceback" not in err, f"the crash is still reachable: {err!r}"
    assert "AttributeError" not in err, f"the crash is still reachable: {err!r}"
    assert _glob_message("content_matches", 123) in err, f"the CLI hid the reason: {err!r}"


def test_control_the_same_scan_over_a_good_register_still_produces_a_document(tmp_path):
    """ANTI-VACUITY: the fixture target and register must be scannable, or the test above
    would pass against a scan that refused everything."""
    register = _register(tmp_path, _leaf("content_matches", ["**/*.py"]))
    proc = _scan_cli(_target(tmp_path), register)
    assert proc.returncode == 0, f"the control scan failed: {proc.stderr.decode()!r}"
    assert proc.stdout.startswith(b"# Gap scan:"), f"no document on stdout: {proc.stdout[:80]!r}"
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n"), (
        "the renderer must end in exactly ONE newline")
    assert proc.stderr == b"", f"stderr not empty: {proc.stderr!r}"


def test_b7_the_refusal_is_a_value_error_not_a_crash(tmp_path):
    """Behavior 7's mechanism: refusal travels as a `ValueError`, the `pattern=""` path.

    `pydantic.ValidationError` IS a `ValueError`, which is what routes this to `Error: ` /
    exit 2 rather than to a traceback with zero document bytes.
    """
    with pytest.raises(ValueError):
        Gap.model_validate(_record(_leaf("file_exists", [123])))
