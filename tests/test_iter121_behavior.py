r"""Iteration 121 behaviors: `Gap` gains a RECORD-level locator rule -- at least one
citation's locator must be resolvable in SHAPE (`http://` or `https://` followed by
non-space) -- so the schema door enforces the same clause the ingest door
(`tools/promote.py`) already did, and `radar validate` refuses a register the ingest gate
would have refused. The FIELD-level rule (non-blank only) is deliberately unchanged.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/`, the
engineer's notes (`engineer.md`), the reviewer's notes (`reviewer.md`, `fix_review.md`),
`IMPLEMENTATION.patch`, or any diff. Every assertion either constructs a record through
the PUBLIC schema (`Gap.model_validate` / `Evidence.model_validate`), drives the PUBLIC
CLI entry point (`agent_gap_radar.cli.main`) and reads the bytes it emitted plus its exit
code, or reads a file under `tests/` -- the surfaces the isolation contract names as
readable. Every expectation comes from `pm.md`'s Expected Behaviors.

Structural notes, so this file cannot lie later:

* **SYNTHETIC-ONLY, per the spec's acceptance criterion.** Every record under test is
  built in-process or written into `tmp_path`. There is NO live scan, and NO census or
  loop over the committed `gaps/*.json` files -- a research pass that adds a record cannot
  red this module. The only live-register touch is behavior 5's requirement that the
  shipped register still certifies, and that is done by RUNNING the verbs and reading
  their bytes, never by walking the register's files. Measured cost of all live verbs
  together: under 0.3s (`validate` 0.09s, `list` 0.03s, `report` 0.03s, `prd` 0.02s,
  `taxonomy` 0.00s).
* **Every refusal test is preceded by its CONTROL.** A refusal-only probe cannot separate
  "the record-level locator rule fired" from "some other required field was missing", so
  the same record with one resolvable citation is asserted ACCEPTED first at both the
  model level (behavior 1) and the CLI level (behavior 4).
* **"Resolvable" is SHAPE ONLY and this module never dereferences a locator.** No network
  call is made or needed; a locator that is well-shaped and 404s is out of scope for this
  rule, and reading these tests must not suggest otherwise.
* **No literal live record count and no live gap id is hardcoded.** Behavior 5 derives the
  record count from `validate`'s own stdout and the `show` id from `list`'s own stdout, so
  a register that grows moves no literal here.
* **Behavior 5 says "byte-identical to before this change", which no single-revision test
  can observe.** What is checkable in this checkout is tested: the shipped register still
  exits 0 (no record is newly rejected), and every other verb is byte-stable across
  repeated runs with an unchanged exit code. Comparing bytes against another commit would
  require checking that commit out, which a test may not do. Disclosed in `tester.md`.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from pydantic import ValidationError

from agent_gap_radar.cli import main
from agent_gap_radar.models import Evidence, Gap

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
#: The register this repo ships. Read only by RUNNING a verb against it (behavior 5).
LIVE_GAPS = REPO_ROOT / "gaps"

#: Behavior 2 and 6: the spec's own resolvable literals.
RESOLVABLE = "https://example.com/a"
RESOLVABLE_PLAIN_HTTP = "http://example.com/a"

#: Behavior 1's own literal, and behavior 2's own literal for the degraded citation.
NON_RESOLVABLE = "internal wiki, page 4"
DEGRADED = "see the design doc"

#: Behavior 6 plus the shapes the spec's named authoritative rule (`https?://\S+$` in
#: `tools/promote.py`) excludes. Each is non-blank, so the FIELD-level rule admits every
#: one of them; what is under test is that a record carrying ONLY these is refused.
NOT_RESOLVABLE_SHAPES = [
    "httpx://example.com/a",        # behavior 6: a near-miss scheme
    "example.com/a",                # behavior 6: no scheme at all
    NON_RESOLVABLE,                 # behavior 1: prose
    DEGRADED,                       # behavior 2's degraded half, alone
    "10.1145/1234567",              # a bare DOI: legal FIELD value, not a lone citation
    "docs/CONSUMER_CONTRACT.md",    # a stable local artifact path, same
    "ftp://example.com/a",          # a scheme the rule does not name
    "https://",                     # the scheme with nothing after it
    "https://example.com/a b",      # a space inside: `\S+$` cannot reach the end
]

#: Behavior 3: values whose `.strip()` is empty. The field-level rule iteration 24 settled
#: must still refuse these, with its own wording.
BLANK_LOCATORS = ["", "   ", "\t", "\n", "\t\n", " \t\n "]

#: Behavior 3: the record-level message must NOT be what a blank locator reports, or the
#: field-level error iteration 24 pinned has been silently replaced.
RECORD_RULE_MARKER = "resolvable locator"
#: The field-level error iteration 24 settled, quoted from the running product's own
#: refusal (see `test_behavior3_...`), used only as a "did the wording move" tripwire.
FIELD_RULE_MARKER = "locator must not be empty"

#: Verbs whose bytes behavior 5 holds stable over the shipped register. `scan` is
#: deliberately absent: the spec forbids a live scan in this module.
STABLE_VERBS = ["validate", "list", "report", "prd"]

GAP_ID_RE = re.compile(r"GAP-\d+")
VALIDATE_OK_RE = re.compile(r"^OK: (\d+) gap record\(s\) valid\.\n$")


def _ev(**over) -> dict:
    """One schema-valid citation. Mirrors `tests/test_models.py`'s helper."""
    base = {
        "source_class": "first-party-field",
        "title": "t",
        "locator": RESOLVABLE,
        "date": "2026-01-02",
        "quote": "a verbatim excerpt",
    }
    base.update(over)
    return base


def _gap(gid: str = "GAP-701", **over) -> dict:
    """One otherwise-valid record, so any refusal below is attributable to the locators."""
    base = {
        "id": gid,
        "title": "a synthetic record",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [_ev()],
    }
    base.update(over)
    return base


def _with_locators(*locators: str, gid: str = "GAP-701") -> dict:
    """The same record, one citation per locator, in the order given."""
    return _gap(gid, evidence=[_ev(locator=loc) for loc in locators])


def _register(root: pathlib.Path, *locators: str, gid: str = "GAP-701") -> pathlib.Path:
    """A throwaway register directory holding exactly one record. `tmp_path`-only."""
    d = root / "gaps"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{gid}.json").write_text(
        json.dumps(_with_locators(*locators, gid=gid)), encoding="utf-8"
    )
    return d


def _messages(exc: ValidationError) -> str:
    return "\n".join(d["msg"] for d in exc.errors())


# --------------------------------------------------------------- behavior 1 (+ CONTROL)

def test_behavior1_control_one_resolvable_citation_is_accepted():
    """CONTROL FIRST: the record every refusal below mutates is itself ACCEPTED."""
    gap = Gap.model_validate(_with_locators(RESOLVABLE))
    assert gap.id == "GAP-701"
    assert [e.locator for e in gap.evidence] == [RESOLVABLE]


@pytest.mark.parametrize("gid", ["GAP-701", "GAP-702"])
def test_behavior1_all_non_resolvable_locators_are_rejected(gid):
    """A record whose citations are ALL non-resolvable is refused at construction, and the
    message names THAT record's gap id (two ids, so the id cannot be a constant)."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(NON_RESOLVABLE, gid=gid))
    msg = _messages(exc.value)
    assert gid in msg, f"the refusal must name the offending record: {msg!r}"
    assert "locator" in msg, f"the refusal must name the offending clause: {msg!r}"


def test_behavior1_two_non_resolvable_citations_are_still_rejected():
    """The rule is at-least-ONE, not any-one: two degraded citations do not add up."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(NON_RESOLVABLE, DEGRADED))
    assert "locator" in _messages(exc.value)


def test_behavior1_refusal_is_stable_across_repeated_construction():
    """Deterministic output bar: the same input reports the same message every time."""
    def once() -> str:
        with pytest.raises(ValidationError) as exc:
            Gap.model_validate(_with_locators(NON_RESOLVABLE))
        return _messages(exc.value)

    assert once() == once()


# --------------------------------------------------------------------------- behavior 2

def test_behavior2_one_degraded_and_one_resolvable_is_accepted():
    """The spec's own pair: `see the design doc` + `https://example.com/a` is ADMITTED."""
    gap = Gap.model_validate(_with_locators(DEGRADED, RESOLVABLE))
    assert [e.locator for e in gap.evidence] == [DEGRADED, RESOLVABLE]


def test_behavior2_order_does_not_matter():
    """The resolvable citation may be first or last: the rule is record-level, not
    positional."""
    gap = Gap.model_validate(_with_locators(RESOLVABLE, DEGRADED))
    assert [e.locator for e in gap.evidence] == [RESOLVABLE, DEGRADED]


@pytest.mark.parametrize("degraded", NOT_RESOLVABLE_SHAPES)
def test_behavior2_every_non_resolvable_shape_survives_beside_a_resolvable_one(degraded):
    """A DOI, a local artifact path or plain prose is still a LEGAL locator; it simply may
    not be a record's ONLY citation. This is the anti-over-reach pin: it fails if the rule
    is ever tightened from 'at least one citation' to 'every citation'."""
    gap = Gap.model_validate(_with_locators(degraded, RESOLVABLE))
    assert [e.locator for e in gap.evidence] == [degraded, RESOLVABLE]


def test_behavior2_the_resolvable_citation_may_be_any_source_class():
    """The record-level rule is about locator SHAPE, never evidence WEIGHT: a zero-weight
    `model-output` citation with a resolvable locator satisfies it. (The ingest door's
    stronger non-zero-weight rule is out of scope for the schema -- spec Feature: 'the
    rule is deliberately WEAKER than the ingest door'.)"""
    gap = Gap.model_validate(_with_locators(RESOLVABLE))
    assert gap.evidence[0].source_class == "first-party-field"  # control on the helper
    weak = Gap.model_validate(
        _gap(evidence=[_ev(source_class="model-output", locator=RESOLVABLE)])
    )
    assert weak.evidence[0].source_class == "model-output"


# --------------------------------------------------------------------------- behavior 3

@pytest.mark.parametrize("blank", BLANK_LOCATORS)
def test_behavior3_blank_locator_is_still_rejected_at_the_field(blank):
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator=blank))
    assert FIELD_RULE_MARKER in _messages(exc.value), _messages(exc.value)


def test_behavior3_blank_locator_error_is_attributed_to_the_locator_field():
    """The field-level refusal is still reported against `locator`, not against the record
    -- i.e. the new rule was ADDED beside it, not put in its place."""
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator=""))
    locs = [d["loc"] for d in exc.value.errors()]
    assert ("locator",) in locs, locs


def test_behavior3_blank_locator_error_wording_is_unchanged():
    """The blank-locator message must not have been replaced by the new record-level one.
    Both markers are asserted so a merge of the two messages fails here."""
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator="   "))
    msg = _messages(exc.value)
    assert FIELD_RULE_MARKER in msg, msg
    assert RECORD_RULE_MARKER not in msg, (
        f"the field-level error must keep its own wording, not the record rule's: {msg!r}"
    )


def test_behavior3_a_record_whose_only_citation_is_blank_reports_the_field_error():
    """Composed door: the blank case is still diagnosed as a blank locator even though the
    record also has no resolvable citation."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(""))
    assert FIELD_RULE_MARKER in _messages(exc.value)


def test_behavior3_non_blank_non_resolvable_is_a_legal_field_value():
    """The two rules are at different levels: the FIELD still accepts every shape iteration
    24 settled on."""
    for loc in NOT_RESOLVABLE_SHAPES:
        assert Evidence.model_validate(_ev(locator=loc)).locator == loc


# --------------------------------------------------------------- behavior 4 (+ CONTROL)

def test_behavior4_control_resolvable_register_certifies(tmp_path, capsys):
    """CONTROL FIRST: the identical register with a resolvable citation still exits 0."""
    d = _register(tmp_path, RESOLVABLE)
    assert main(["validate", str(d)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "OK: 1 gap record(s) valid.\n"
    assert captured.err == ""


def test_behavior4_non_resolvable_register_exits_two(tmp_path, capsys):
    d = _register(tmp_path, NON_RESOLVABLE)
    assert main(["validate", str(d)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout must carry only the document: {captured.out!r}"
    assert captured.err.startswith("Error: "), captured.err
    assert captured.err.count("\n") == 1, f"exactly one stderr line: {captured.err!r}"
    assert captured.err.endswith("\n") and not captured.err.endswith("\n\n")


@pytest.mark.parametrize("gid", ["GAP-701", "GAP-702"])
def test_behavior4_error_line_names_the_offending_record(tmp_path, capsys, gid):
    d = _register(tmp_path, NON_RESOLVABLE, gid=gid)
    assert main(["validate", str(d)]) == 2
    err = capsys.readouterr().err
    assert gid in err, f"the refusal must name the record it refused: {err!r}"
    assert "locator" in err, err


def test_behavior4_mixed_register_certifies(tmp_path, capsys):
    """Behavior 2 at the CLI: the degraded-plus-resolvable record validates."""
    d = _register(tmp_path, DEGRADED, RESOLVABLE)
    assert main(["validate", str(d)]) == 0, capsys.readouterr().err
    assert capsys.readouterr().out == "OK: 1 gap record(s) valid.\n"


# --------------------------------------------------------------------------- behavior 5

def test_behavior5_shipped_register_still_certifies(capsys):
    """No record is newly rejected. The count is DERIVED from the tool's own line, and
    guarded against a vacuous zero-record register."""
    assert main(["validate", str(LIVE_GAPS)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    m = VALIDATE_OK_RE.match(captured.out)
    assert m, f"unexpected certification line: {captured.out!r}"
    assert int(m.group(1)) >= 1, "control: the shipped register must not be empty"


@pytest.mark.parametrize("verb", STABLE_VERBS)
def test_behavior5_every_other_verb_is_byte_stable_over_the_shipped_register(verb, capsys):
    """The reachable half of 'byte-identical': same input, same bytes, same code, twice.
    (Comparing against another commit would require checking it out -- see the module
    docstring's disclosure.)"""
    first_code = main([verb, str(LIVE_GAPS)])
    first = capsys.readouterr()
    second_code = main([verb, str(LIVE_GAPS)])
    second = capsys.readouterr()
    assert (first_code, first.out, first.err) == (second_code, second.out, second.err)
    assert first_code == 0, first.err
    assert first.err == ""
    assert first.out.endswith("\n") and not first.out.endswith("\n\n")


def test_behavior5_show_over_the_shipped_register_is_unaffected(capsys):
    """`show` needs an id, so it is DERIVED from `list`'s own output rather than pinned."""
    assert main(["list", str(LIVE_GAPS)]) == 0
    ids = GAP_ID_RE.findall(capsys.readouterr().out)
    assert ids, "control: `list` must name at least one record"
    gid = sorted(set(ids))[0]
    assert main(["show", gid, str(LIVE_GAPS)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert gid in captured.out
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


def test_behavior5_taxonomy_is_unaffected(capsys):
    """The one verb that reads no register at all: still clean, still one trailing newline."""
    assert main(["taxonomy"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


# --------------------------------------------------------------------------- behavior 6

@pytest.mark.parametrize("locator", [RESOLVABLE_PLAIN_HTTP, RESOLVABLE])
def test_behavior6_both_http_and_https_are_resolvable(locator):
    gap = Gap.model_validate(_with_locators(locator))
    assert [e.locator for e in gap.evidence] == [locator]


@pytest.mark.parametrize("locator", ["httpx://example.com/a", "example.com/a"])
def test_behavior6_near_miss_and_schemeless_are_not_resolvable(locator):
    """The spec's own two counter-examples: a record carrying only such a locator is
    refused per behavior 1."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(locator))
    assert "locator" in _messages(exc.value)


@pytest.mark.parametrize("locator", NOT_RESOLVABLE_SHAPES)
def test_behavior6_a_record_with_only_non_resolvable_locators_is_refused(locator):
    """Every shape the authoritative rule excludes, driven through behavior 1's door."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(locator))
    msg = _messages(exc.value)
    assert "GAP-701" in msg and "locator" in msg, msg


@pytest.mark.parametrize("locator", ["HTTPS://EXAMPLE.COM/a", "Http://example.com/a"])
def test_behavior6_the_scheme_check_is_case_sensitive(locator):
    r"""AMBIGUITY, tested on the most reasonable reading and reported in `tester.md`:
    behavior 6 names `http`/`https` in lower case and the Feature section names
    `tools/promote.py`'s `https?://\S+$` AUTHORITATIVE for this rule. That pattern is
    case-sensitive, so an upper-case scheme is NOT resolvable and the register's two doors
    stay in agreement -- which is the point of the iteration. If a successor decides an
    upper-case scheme should be admitted, both doors must move together and this pin is the
    place that says so."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(locator))
    assert "locator" in _messages(exc.value)


def test_behavior6_no_locator_is_ever_dereferenced():
    """Offline bar: 'resolvable' is SHAPE only. A well-shaped locator on a host that
    cannot exist is ACCEPTED -- if the rule ever dereferenced, this test would need a
    network and would hang or fail offline."""
    gap = Gap.model_validate(_with_locators("https://nonexistent.invalid/never-fetched"))
    assert gap.evidence[0].locator == "https://nonexistent.invalid/never-fetched"


# =====================================================================================
# EXTENSION (tester-retry round). The round above was cut by the stage cap after it had
# covered every behavior at the model level plus behavior 4/5 through the in-process CLI.
# What it had NOT reached, and what follows, is: (a) behavior 4 across EVERY verb that
# must load the register, not `validate` alone -- if the record-level rule lived in
# `validate` instead of at the load door, `list`/`report`/`show`/`prd` would happily
# render a record whose citations nobody can resolve; (b) the same refusal out of a REAL
# process, so the exit code is proved outside `capsys`; (c) the boundary shapes of
# "resolvable" that behavior 6 names but did not enumerate; (d) the record-level
# ATTRIBUTION acceptance criterion 1 implies (`loc == ()`), and the older
# empty-evidence error it must not mask.
# =====================================================================================

import subprocess  # noqa: E402  -- spawned only for the real-process refusal below
import sys  # noqa: E402

#: Every verb that must LOAD the register before it can emit a document. `prd` takes the
#: register as its only positional and selects the top-ranked record with `--gap`
#: (`radar prd --help`), so the path-only form is correct; `show` names its record
#: positionally. `scan` is deliberately absent: the spec forbids a live scan here.
LOADING_VERBS = [
    ["validate"],
    ["list"],
    ["list", "--json"],
    ["report"],
    ["show"],
    ["prd"],
]

#: Behavior 6, the "starts with the scheme" half of `https?://\\S+$`. Every one of these
#: CONTAINS a resolvable locator or a near-scheme, which is exactly why they are the
#: interesting refusals: a rule written with `re.search` instead of an anchored match
#: would admit all four.
SCHEME_MUST_LEAD = [
    " https://example.com/a",
    "\thttps://example.com/a",
    "see https://example.com/a",
    "https:/example.com/a",
]

#: Behavior 6, the "no space after the scheme" half. `\\S+$` cannot reach the end of a
#: string once whitespace intervenes -- including a non-breaking space, which is
#: whitespace to the rule even though it looks like part of a URL.
NO_SPACE_AFTER_SCHEME = [
    "https://example.com/a ",
    "https://example.com/a\tmore",
    "https://example.com/a b",
    "https://\u00a0x",
]

#: The message the running product emits for the record-level refusal, quoted from its own
#: stderr (see `tester2.md`). Used as a wording tripwire only.
RECORD_RULE_SENTENCE = "no citation has a resolvable locator"


def _argv(verb: list[str], register: pathlib.Path, gid: str = "GAP-701") -> list[str]:
    """One verb's argv over `register`. `show` needs its record id positionally."""
    if verb[0] == "show":
        return ["show", gid, str(register), *verb[1:]]
    return [*verb, str(register)]


def _vid(verb: list[str]) -> str:
    return "-".join(verb).replace("--", "")


# ------------------------------------------------ behavior 4, extended (+ CONTROL FIRST)

@pytest.mark.parametrize("verb", LOADING_VERBS, ids=[_vid(v) for v in LOADING_VERBS])
def test_behavior4x_control_every_loading_verb_accepts_a_resolvable_register(
    verb, tmp_path, capsys
):
    """CONTROL FIRST for the refusal matrix below: with one resolvable citation, every one
    of these verbs succeeds over the SAME one-record register, so a refusal underneath is
    attributable to the locator and not to a verb that cannot run on a tiny register."""
    d = _register(tmp_path, RESOLVABLE)
    assert main(_argv(verb, d)) == 0, capsys.readouterr().err
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


@pytest.mark.parametrize("verb", LOADING_VERBS, ids=[_vid(v) for v in LOADING_VERBS])
def test_behavior4x_every_loading_verb_refuses_the_unresolvable_record(
    verb, tmp_path, capsys
):
    """The rule lives at the LOAD door, not inside `validate`. If it did not, these verbs
    would render a record whose every citation is unresolvable -- the precise corruption
    behavior 4 exists to stop, since `validate` is the only verb a CI gate runs."""
    d = _register(tmp_path, NON_RESOLVABLE)
    assert main(_argv(verb, d)) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout must carry only the document: {captured.out!r}"
    assert captured.err.startswith("Error: "), captured.err
    assert captured.err.count("\n") == 1, f"exactly one stderr line: {captured.err!r}"
    assert "GAP-701" in captured.err, captured.err
    assert "locator" in captured.err, captured.err


def test_behavior4x_a_resolvable_record_does_not_rescue_its_neighbour(tmp_path, capsys):
    """Fail-closed and precisely attributed: a register holding one good and one bad record
    exits 2, and the error names ONLY the offender. A rule that reported the whole register
    (or that passed because SOME record was fine) would fail here."""
    d = tmp_path / "gaps"
    d.mkdir()
    (d / "GAP-800.json").write_text(
        json.dumps(_with_locators(RESOLVABLE, gid="GAP-800")), encoding="utf-8"
    )
    (d / "GAP-801.json").write_text(
        json.dumps(_with_locators(NON_RESOLVABLE, gid="GAP-801")), encoding="utf-8"
    )
    assert main(["validate", str(d)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "GAP-801" in captured.err, captured.err
    assert "GAP-800" not in captured.err, (
        f"the sound record must not be implicated: {captured.err!r}"
    )


def test_behavior4x_two_offenders_are_both_named_on_one_stderr_line(tmp_path, capsys):
    """Behavior 4 says a SINGLE `Error: ` line. Two offending records must therefore be
    joined onto that one line, not emitted as two lines -- and neither may be dropped."""
    d = tmp_path / "gaps"
    d.mkdir()
    (d / "GAP-801.json").write_text(
        json.dumps(_with_locators(NON_RESOLVABLE, gid="GAP-801")), encoding="utf-8"
    )
    (d / "GAP-802.json").write_text(
        json.dumps(_with_locators("example.com/a", gid="GAP-802")), encoding="utf-8"
    )
    assert main(["validate", str(d)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1, captured.err
    assert captured.err.startswith("Error: ")
    assert "GAP-801" in captured.err and "GAP-802" in captured.err, captured.err


def test_behavior4x_a_json_consumer_gets_all_or_nothing(tmp_path, capsys):
    """`list --json` feeds a machine. On refusal it must emit NO partial document, so a
    consumer's `json.loads` never sees half an array."""
    good = _register(tmp_path / "ok", RESOLVABLE)
    assert main(["list", "--json", str(good)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload, "control: the good register must produce a non-empty payload"

    bad = _register(tmp_path / "bad", NON_RESOLVABLE)
    assert main(["list", "--json", str(bad)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"no partial JSON may reach stdout: {captured.out!r}"
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)


def test_behavior4x_the_refusal_is_byte_stable_across_repeated_runs(tmp_path, capsys):
    """Deterministic-output bar at the CLI: same register, same bytes, same code, twice."""
    d = _register(tmp_path, NON_RESOLVABLE)
    first_code = main(["validate", str(d)])
    first = capsys.readouterr()
    second_code = main(["validate", str(d)])
    second = capsys.readouterr()
    assert (first_code, first.out, first.err) == (second_code, second.out, second.err)
    assert first_code == 2


def test_behavior4x_a_real_process_exits_two(tmp_path):
    """The one spawned process in this module. `capsys` cannot prove a process EXIT CODE:
    an entry point that returned 2 and then exited 0 would pass every test above. Spawned
    on a `tmp_path` register, so it is still synthetic-only and costs one interpreter
    start; no network, no live scan. Convention copied from
    `tests/test_iter109_behavior.py`'s spawn helper."""
    d = _register(tmp_path, NON_RESOLVABLE)
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "validate", str(d)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert proc.stdout == b"", proc.stdout
    err = proc.stderr.decode()
    assert err.startswith("Error: "), err
    assert err.count("\n") == 1, err
    assert "GAP-701" in err and "locator" in err, err


def test_behavior4x_a_real_process_still_certifies_a_resolvable_register(tmp_path):
    """CONTROL for the spawn above, so the exit code 2 is the rule's and not the spawn's."""
    d = _register(tmp_path, RESOLVABLE)
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "validate", str(d)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == b"OK: 1 gap record(s) valid.\n", proc.stdout
    assert proc.stderr == b""


# ---------------------------------------------------------------- behavior 1, extended

def test_behavior1x_the_refusal_is_attributed_to_the_record_not_to_a_field():
    """Acceptance criterion 1 makes this a RECORD-level validator, which is observable
    without reading `src/`: pydantic reports a record-level failure at `loc == ()`, while a
    field validator reports at `('evidence', 0, 'locator')`. This is the black-box witness
    that the rule was not implemented as a second field-level check."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(NON_RESOLVABLE))
    errors = exc.value.errors()
    assert len(errors) == 1, errors
    assert errors[0]["loc"] == (), errors[0]["loc"]
    assert RECORD_RULE_SENTENCE in errors[0]["msg"], errors[0]["msg"]


def test_behavior1x_the_new_rule_does_not_mask_the_empty_evidence_error():
    """A record with NO citations at all was already refused before this iteration. That
    older diagnosis must survive: a validator that ran first and reported 'no resolvable
    locator' would tell a contributor to fix the wrong thing."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_gap(evidence=[]))
    msg = _messages(exc.value)
    assert "at least 1 item" in msg, msg
    assert RECORD_RULE_MARKER not in msg, (
        f"the empty-evidence case must keep its own diagnosis: {msg!r}"
    )


def test_behavior2x_a_resolvable_citation_anywhere_in_the_ladder_satisfies_the_rule():
    """At-least-one is positional-free even in the middle of a three-citation ladder."""
    gap = Gap.model_validate(
        _with_locators(NON_RESOLVABLE, RESOLVABLE_PLAIN_HTTP, DEGRADED)
    )
    assert [e.locator for e in gap.evidence] == [
        NON_RESOLVABLE, RESOLVABLE_PLAIN_HTTP, DEGRADED
    ]


# ---------------------------------------------------------------- behavior 6, extended

@pytest.mark.parametrize("locator", ["https://a", "http://a"])
def test_behavior6x_the_scheme_plus_one_non_space_character_is_enough(locator):
    r"""The authoritative rule is `https?://\S+$`: one non-space character after the
    scheme is the floor. This is the SHAPE-only boundary -- `https://a` is not a reachable
    host, and the rule deliberately does not care (see Out of Scope: no dereferencing)."""
    gap = Gap.model_validate(_with_locators(locator))
    assert gap.evidence[0].locator == locator


@pytest.mark.parametrize("locator", SCHEME_MUST_LEAD)
def test_behavior6x_the_scheme_must_lead_the_locator(locator):
    """Each of these CONTAINS `https:` yet none of them IS a resolvable locator: the rule
    is anchored at the start, so a locator that merely mentions a URL inside prose does not
    satisfy a record's one-resolvable-citation promise."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(locator))
    assert RECORD_RULE_SENTENCE in _messages(exc.value), _messages(exc.value)


@pytest.mark.parametrize("locator", NO_SPACE_AFTER_SCHEME)
def test_behavior6x_whitespace_after_the_scheme_is_not_resolvable(locator):
    r"""`\S+$` must reach the end of the string, so any whitespace after the scheme --
    including a NON-BREAKING space, which reads as part of a URL but is whitespace to the
    rule -- leaves the locator unresolvable."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(locator))
    assert RECORD_RULE_SENTENCE in _messages(exc.value), _messages(exc.value)


def test_behavior6x_a_trailing_newline_is_admitted_by_the_authoritative_rule():
    r"""AMBIGUITY, pinned on the reading the spec mandates and reported in `tester2.md`.
    The Feature section names `tools/promote.py`'s `https?://\S+$` AUTHORITATIVE for the
    record-level promise, and in Python `$` also matches immediately before a trailing
    newline -- so `"https://example.com/a\n"` is resolvable at BOTH doors while
    `"https://example.com/a "` is resolvable at NEITHER. That asymmetry is inherited, not
    invented here, and the whole point of the iteration is that the two doors agree. This
    test exists so that a successor who tightens the rule to a full match has to move both
    doors together and read this note first.
    """
    gap = Gap.model_validate(_with_locators("https://example.com/a\n"))
    assert gap.evidence[0].locator == "https://example.com/a\n"


# ---------------------------------------------------------------- behavior 5, extended

def test_behavior5x_list_json_over_the_shipped_register_parses_and_is_byte_stable(capsys):
    """The machine-facing verb: still exit 0 over the shipped register, still parseable,
    still byte-identical run to run. The record count is DERIVED from the payload."""
    assert main(["list", "--json", str(LIVE_GAPS)]) == 0
    first = capsys.readouterr()
    assert first.err == ""
    payload = json.loads(first.out)
    assert len(payload) >= 1, "control: the shipped register must not be empty"
    assert main(["list", "--json", str(LIVE_GAPS)]) == 0
    assert capsys.readouterr().out == first.out
    assert first.out.endswith("\n") and not first.out.endswith("\n\n")


def test_behavior5x_below_floor_records_are_still_displayed(capsys):
    """THE CORE INVARIANT, unmoved: below-floor records are DISPLAYED, never dropped. A
    locator rule that rejected records would shrink this listing, so the count at floor 0
    is compared with the count at the default floor -- both derived from the tool."""
    assert main(["list", str(LIVE_GAPS)]) == 0
    default_lines = capsys.readouterr().out.splitlines()
    assert main(["list", "--floor", "0", str(LIVE_GAPS)]) == 0
    floor_zero_lines = capsys.readouterr().out.splitlines()
    assert default_lines, "control: the default listing must not be empty"
    assert len(floor_zero_lines) >= len(default_lines), (
        len(floor_zero_lines), len(default_lines)
    )


# =====================================================================================
# EXTENSION 2 (tester-retry2 round). The two rounds above were each cut by the stage cap.
# Between them they covered every behavior at the model level and behavior 4/5 across the
# verbs listed in `LOADING_VERBS`. Auditing that list against the product's OWN verb table
# (`radar --help` reports validate/list/report/show/prd/scan/diff/taxonomy) leaves TWO
# register-loading verbs with no coverage at all:
#
#   * `diff old new` -- loads TWO registers. Behavior 4's promise is a property of the LOAD
#     door, so a verb with two doors is where a rule wired into one call site leaks. Nothing
#     above would notice if `diff` rendered an unresolvable record.
#   * `scan target --gaps R` -- loads a register too. The spec forbids a LIVE scan (a scan of
#     this repo against the shipped register, ~10.4s), and this does not do one: the target
#     is a one-file `tmp_path` tree and the register is a one-record `tmp_path` register.
#     Measured at 0.003s per call, so the acceptance criterion's cost intent is honored while
#     the last loading verb stops being a blind spot.
#
# Behavior 5's "every OTHER verb" is likewise completed here: `diff` was the one verb over
# the shipped register that no test in this module touched.
# =====================================================================================

#: Behavior 4 for `diff`: which side of the comparison carries the offending register. Both
#: are tested because a rule applied to only one argument passes half of them.
DIFF_SIDES = ["old", "new"]

#: Behavior 6, the "anchored AND terminal" half, which the shapes above do not reach. Every
#: one of these CONTAINS a fully resolvable URL, and each is still refused -- so together
#: they pin that the rule is neither `re.search` nor multiline.
EMBEDDED_URL_SHAPES = [
    "https://example.com/a\nnot-a-url",   # a URL first, then more text on a second line
    "not-a-url\nhttps://example.com/a",   # a URL last: the scheme must LEAD the locator
    "https://example.com/a\n\n",          # TWO trailing newlines: `$` admits only one
]


def _diff_argv(side: str, bad: pathlib.Path, good: pathlib.Path) -> list[str]:
    """`diff old new` with the offending register on `side`."""
    return ["diff", str(bad), str(good)] if side == "old" else ["diff", str(good), str(bad)]


# ------------------------------------------------- behavior 4, `diff` (+ CONTROL FIRST)

def test_behavior4y_control_diff_accepts_two_resolvable_registers(tmp_path, capsys):
    """CONTROL FIRST for the `diff` refusals below. A self-diff of one sound register also
    doubles as a determinism control: comparing a register with itself must report no
    change, so a refusal underneath is the locator rule and not `diff` mishandling a
    one-record register."""
    d = _register(tmp_path, RESOLVABLE)
    assert main(["diff", str(d), str(d)]) == 0, capsys.readouterr().err
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")
    assert "GAP-701" not in captured.out, (
        f"a register compared with itself must report no change: {captured.out!r}"
    )


@pytest.mark.parametrize("side", DIFF_SIDES)
def test_behavior4y_diff_refuses_an_unresolvable_record_on_either_side(
    side, tmp_path, capsys
):
    """`diff` is the only verb with TWO load doors, so it is where a rule wired into one
    call site instead of into the schema would leak. Both argument positions must refuse,
    with behavior 4's exact output contract: exit 2, empty stdout, ONE `Error: ` line naming
    the offending record."""
    bad = _register(tmp_path / "bad", NON_RESOLVABLE)
    good = _register(tmp_path / "good", RESOLVABLE)
    assert main(_diff_argv(side, bad, good)) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout must carry only the document: {captured.out!r}"
    assert captured.err.startswith("Error: "), captured.err
    assert captured.err.count("\n") == 1, f"exactly one stderr line: {captured.err!r}"
    assert "GAP-701" in captured.err, captured.err
    assert "locator" in captured.err, captured.err


def test_behavior4y_diff_json_emits_no_partial_document_on_refusal(tmp_path, capsys):
    """`diff --json` feeds a machine, like `list --json`. Its refusal must also be
    all-or-nothing, with the CONTROL proving the good pair does produce a payload."""
    good = _register(tmp_path / "good", RESOLVABLE)
    assert main(["diff", "--json", str(good), str(good)]) == 0
    assert json.loads(capsys.readouterr().out), "control: a payload must be produced"

    bad = _register(tmp_path / "bad", NON_RESOLVABLE)
    assert main(["diff", "--json", str(good), str(bad)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"no partial JSON may reach stdout: {captured.out!r}"
    assert captured.err.startswith("Error: ") and captured.err.count("\n") == 1


# ------------------------------------------------- behavior 4, `scan` (+ CONTROL FIRST)

def _tiny_target(root: pathlib.Path) -> pathlib.Path:
    """A one-file synthetic target tree. NOT this repo -- see the section header on why
    this is not the live scan the spec forbids."""
    t = root / "target"
    t.mkdir(parents=True, exist_ok=True)
    (t / "app.py").write_text("print('hello')\n", encoding="utf-8")
    return t


def test_behavior4z_control_scan_accepts_a_resolvable_register(tmp_path, capsys):
    """CONTROL FIRST: the synthetic target scans clean against a sound one-record register,
    so the refusal below is attributable to the locator rule and not to the tiny target."""
    target = _tiny_target(tmp_path)
    good = _register(tmp_path / "good", RESOLVABLE)
    assert main(["scan", str(target), "--gaps", str(good)]) == 0, capsys.readouterr().err
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_behavior4z_scan_refuses_a_register_holding_an_unresolvable_record(
    extra, tmp_path, capsys
):
    """The last register-loading verb. `scan` is the verb a release gate points at a target,
    so a register it will silently accept is the same corruption behavior 4 stops at
    `validate` -- in both the markdown and the `--json` form."""
    target = _tiny_target(tmp_path)
    bad = _register(tmp_path / "bad", NON_RESOLVABLE)
    assert main(["scan", str(target), "--gaps", str(bad), *extra]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout must carry only the document: {captured.out!r}"
    assert captured.err.startswith("Error: "), captured.err
    assert captured.err.count("\n") == 1, f"exactly one stderr line: {captured.err!r}"
    assert "GAP-701" in captured.err and "locator" in captured.err, captured.err


# ------------------------------------------------------------- behavior 6, anchoring

@pytest.mark.parametrize("locator", EMBEDDED_URL_SHAPES)
def test_behavior6y_a_locator_that_merely_contains_a_url_is_not_resolvable(locator):
    r"""Every one of these CONTAINS `https://example.com/a` in full, and every one is still
    refused. Together they pin the two properties `https?://\S+$` has that a looser rule
    would lose: it is ANCHORED at the start (so `re.search` is wrong) and `\S+` cannot cross
    a newline while `$` admits at most ONE trailing newline (so `re.MULTILINE` is wrong).
    A rule written either looser way would admit all three and this module would be the only
    thing standing between the register and a citation nobody can check."""
    with pytest.raises(ValidationError) as exc:
        Gap.model_validate(_with_locators(locator))
    errors = exc.value.errors()
    assert len(errors) == 1, errors
    assert errors[0]["loc"] == (), errors[0]["loc"]
    assert RECORD_RULE_SENTENCE in errors[0]["msg"], errors[0]["msg"]


def test_behavior6y_a_fragment_or_query_after_the_host_is_still_resolvable():
    """The counterpart control: the rule is `scheme + non-space`, so ordinary URL furniture
    (a fragment, a query) stays resolvable. Without this, the refusals above could equally
    be explained by a rule that rejects anything but a bare path."""
    for locator in ["https://example.com/a#frag", "https://example.com/a?q=1&r=2"]:
        gap = Gap.model_validate(_with_locators(locator))
        assert gap.evidence[0].locator == locator


# ------------------------------------------------------- behavior 5, `diff` over live

def test_behavior5y_diff_over_the_shipped_register_certifies(capsys):
    """Behavior 5 says EVERY OTHER verb over the shipped register is unaffected, and `diff`
    was the one verb no test in this module ran. A self-diff is used so the assertion needs
    no second register state and no literal record count."""
    assert main(["diff", str(LIVE_GAPS), str(LIVE_GAPS)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n") and not captured.out.endswith("\n\n")


def test_behavior5y_diff_json_over_the_shipped_register_is_byte_stable(capsys):
    """The machine-facing half, run twice: same input, same bytes, same exit code. `--json`
    is the cheap form (measured 0.069s against 0.268s for the markdown), which is why the
    two-run byte check uses it."""
    assert main(["diff", "--json", str(LIVE_GAPS), str(LIVE_GAPS)]) == 0
    first = capsys.readouterr()
    assert first.err == ""
    assert json.loads(first.out) is not None
    assert main(["diff", "--json", str(LIVE_GAPS), str(LIVE_GAPS)]) == 0
    second = capsys.readouterr()
    assert second.out == first.out and second.err == ""
    assert first.out.endswith("\n") and not first.out.endswith("\n\n")


# --------------------------------------------------------- behavior 3, wording tripwire

def test_behavior3y_the_two_rules_report_different_diagnoses():
    """Behavior 3's real risk is not that the blank-locator error disappears but that the
    NEW rule swallows it, leaving one message for two different mistakes. Asserted as a
    pair, in one test, so the distinction cannot rot one side at a time: a blank locator
    reports the FIELD error at the field's own `loc` and never the record sentence; an
    unresolvable-but-non-blank locator reports the record sentence at `loc == ()` and never
    the field error."""
    with pytest.raises(ValidationError) as blank_exc:
        Gap.model_validate(_with_locators(""))
    blank = blank_exc.value.errors()
    assert any(e["loc"][-1] == "locator" for e in blank), blank
    blank_msgs = "\n".join(e["msg"] for e in blank)
    assert FIELD_RULE_MARKER in blank_msgs, blank_msgs
    assert RECORD_RULE_SENTENCE not in blank_msgs, blank_msgs

    with pytest.raises(ValidationError) as unresolvable_exc:
        Gap.model_validate(_with_locators(NON_RESOLVABLE))
    unresolvable = unresolvable_exc.value.errors()
    assert [e["loc"] for e in unresolvable] == [()], unresolvable
    unresolvable_msgs = "\n".join(e["msg"] for e in unresolvable)
    assert RECORD_RULE_SENTENCE in unresolvable_msgs, unresolvable_msgs
    assert FIELD_RULE_MARKER not in unresolvable_msgs, unresolvable_msgs
