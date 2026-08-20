"""Iteration 24 behaviors: `Evidence.locator` gains the non-blank validator its twin
`quote` already has, so a citation nobody can check can no longer pass `radar validate`.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors; every claim was measured by
CONSTRUCTING models through their public schema, RUNNING the CLI, or reading `tests/`,
`README.md` and the on-disk register AS DATA.

Structural notes, so this file cannot lie later:

* **Every refusal test is preceded by its CONTROL.** A refusal-only probe cannot tell "the
  locator was validated" from "some other required field was missing", so `_ev()` is
  asserted ACCEPTED (behavior 1) before any blank value is asserted refused, and the CLI
  refusal (behavior 6) is paired with the same record carrying a good locator.
* **The anti-over-reach cases are pinned as behavior, not prose** (behaviors 7 and 8): a
  bare DOI, a local artifact path and an unparseable string must all stay ACCEPTED, so a
  successor cannot quietly tighten this into a URL rule without a failing test here.
* **Nothing asserts a literal record count.** The register is fed by a recurring research
  pass, so behavior 2's `OK: 16 gap record(s) valid.` is checked as `OK: <n> gap record(s)
  valid.` with `n` DERIVED from the files on disk, guarded against a vacuous zero-record
  domain first. Today that n is 16 and the byte string matches exactly.
* **Behaviors 9 and 10 say "unchanged from HEAD", which no single-revision test can
  observe.** What is checkable here is the MECHANISM that makes them true -- no live
  citation carries a blank locator, so the new rule excludes no live record -- plus the
  invariants those surfaces must keep (determinism, one trailing newline, every record
  displayed). The A/B against HEAD itself was run in the tester stage and is reported in
  `tester.md`, with a positive control proving the harness sees the intended difference.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from agent_gap_radar import scoring
from agent_gap_radar.cli import main
from agent_gap_radar.models import Evidence
from agent_gap_radar.registry import load_all

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
LIVE_GAPS = REPO_ROOT / "gaps"

#: Behavior 1's control value, quoted from the spec.
GOOD_LOCATOR = "https://example.org/a"

#: Behavior 4: "the rule is exactly 'rejected when `.strip()` is empty'". The first four
#: are the spec's own list; the rest are other strings whose `.strip()` is empty, so they
#: belong to the same rule and pin it against a narrower hand-rolled whitespace set.
BLANK_LOCATORS = ["", "   ", "\t", "\n", "\t\n", "\r", " \t\n ", "\x0b", "\u00a0", "\u3000"]

#: Behaviors 7 and 8: values the field must keep ACCEPTING. The docstring of the field
#: promises "URL, DOI, or a stable local artifact path", and this iteration closes the
#: BLANK hole only.
ACCEPTED_NON_URL_LOCATORS = [
    "10.1145/1234567",              # behavior 7: a bare DOI
    "docs/CONSUMER_CONTRACT.md",    # behavior 7: a local artifact path
    "not a url at all",             # behavior 8: unparseable, still accepted
    "TODO",                         # behavior 8, same rule: shape is not this bite
]

#: One otherwise-valid record, used for the CLI tests. Mirrors `tests/test_cli.py`.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": GOOD_LOCATOR, "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}

HUMAN_SURFACES = ["report", "list", "show", "taxonomy"]


def _ev(**over) -> dict:
    base = {
        "source_class": "first-party-field",
        "title": "t",
        "locator": GOOD_LOCATOR,
        "date": "2026-01-02",
        "quote": "a verbatim excerpt",
    }
    base.update(over)
    return base


def _register(root: pathlib.Path, locator: str) -> pathlib.Path:
    """A throwaway register directory holding one record whose citation has `locator`."""
    d = root / "gaps"
    d.mkdir(parents=True)
    record = json.loads(json.dumps(RECORD))
    record["evidence"][0]["locator"] = locator
    (d / "GAP-001.json").write_text(json.dumps(record), encoding="utf-8")
    return d


def _messages(exc: ValidationError) -> list[str]:
    return [d["msg"] for d in exc.errors()]


def _surface_argv(verb: str) -> list[str]:
    if verb == "taxonomy":
        return ["taxonomy"]
    if verb == "show":
        return ["show", "GAP-003", str(LIVE_GAPS)]
    return [verb, str(LIVE_GAPS)]


# ------------------------------------------------------------------ behavior 1 (CONTROL)

def test_behavior1_good_locator_is_accepted():
    """CONTROL, and it runs before every refusal below: the probe is live."""
    ev = Evidence.model_validate(_ev())
    assert ev.locator == GOOD_LOCATOR


def test_behavior1_control_record_is_accepted_whole():
    """The same fixture the CLI tests use must load through `Gap`, or a CLI refusal below
    could be about any other field."""
    gaps = load_all(pathlib.Path(LIVE_GAPS))
    assert gaps, "vacuous domain: the live register loaded zero records"


# ------------------------------------------------------------------ behavior 2 (CONTROL)

def test_behavior2_live_register_still_certifies(capsys):
    n = len(sorted(LIVE_GAPS.glob("*.json")))
    assert n > 0, "vacuous domain: no record files under gaps/"
    assert main(["validate", str(LIVE_GAPS)]) == 0
    captured = capsys.readouterr()
    assert captured.out == f"OK: {n} gap record(s) valid.\n"
    assert captured.err == ""


def test_behavior2_stdout_ends_in_exactly_one_newline(capsys):
    main(["validate", str(LIVE_GAPS)])
    out = capsys.readouterr().out
    assert out.endswith("\n") and not out.endswith("\n\n")


# ----------------------------------------------------------- behaviors 3 and 4 (REFUSAL)

def test_behavior3_empty_locator_is_refused():
    with pytest.raises(ValidationError):
        Evidence.model_validate(_ev(locator=""))


@pytest.mark.parametrize("blank", BLANK_LOCATORS)
def test_behavior4_blank_locator_is_refused(blank):
    """The rule is exactly 'reject when `.strip()` is empty', so every string that strips
    to nothing is refused -- not just the four the spec happens to list."""
    assert blank.strip() == "", "fixture error: this value is not blank"
    with pytest.raises(ValidationError):
        Evidence.model_validate(_ev(locator=blank))


@pytest.mark.parametrize("keeps", ["a", " a ", "\ta\n", GOOD_LOCATOR])
def test_behavior4_is_not_stronger_than_strip(keeps):
    """Two-sided against the same rule: a value with ANY non-whitespace character survives,
    including one that needs stripping. This is what stops the rule creeping wider."""
    assert keeps.strip() != ""
    assert Evidence.model_validate(_ev(locator=keeps)).locator is not None


# ---------------------------------------------------------------------------- behavior 5

def test_behavior5_message_names_the_field_and_says_why():
    with pytest.raises(ValidationError) as exc:
        Evidence.model_validate(_ev(locator=""))
    msgs = _messages(exc.value)
    assert len(msgs) == 1, msgs
    msg = msgs[0]
    assert "locator" in msg
    assert "resolve" in msg or "resolved" in msg or "check" in msg, msg
    assert len(msg) > 30, f"message states no reason: {msg!r}"


def test_behavior5_wording_is_deterministic_across_every_blank():
    """One deterministic sentence, not a per-input rendering: a reader diffing two failed
    loads must not see the message change with the whitespace that caused it."""
    seen = set()
    for blank in BLANK_LOCATORS:
        with pytest.raises(ValidationError) as exc:
            Evidence.model_validate(_ev(locator=blank))
        seen.add(tuple(_messages(exc.value)))
    assert len(seen) == 1, f"message varies with the input: {sorted(seen)}"


def test_behavior5_message_is_stable_across_repeated_loads():
    def once() -> tuple[str, ...]:
        with pytest.raises(ValidationError) as exc:
            Evidence.model_validate(_ev(locator="   "))
        return tuple(_messages(exc.value))

    assert once() == once()


# ------------------------------------------------------------- behavior 6 (CLI, 2-sided)

def test_behavior6_control_good_locator_register_is_certified(tmp_path, capsys):
    """CONTROL FIRST: the identical record with a resolvable locator still exits 0."""
    d = _register(tmp_path, GOOD_LOCATOR)
    assert main(["validate", str(d)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "OK: 1 gap record(s) valid.\n"
    assert captured.err == ""


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_behavior6_blank_locator_register_exits_two(tmp_path, capsys, blank):
    d = _register(tmp_path, blank)
    assert main(["validate", str(d)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout must carry only the document: {captured.out!r}"
    assert captured.err.startswith("Error: "), captured.err
    assert captured.err.endswith("\n") and not captured.err.endswith("\n\n")


def test_behavior6_error_stream_names_the_offending_field(tmp_path, capsys):
    d = _register(tmp_path, "")
    main(["validate", str(d)])
    err = capsys.readouterr().err
    assert "locator" in err, err
    assert "GAP-001" in err, f"the message must name the record it refused: {err!r}"


# --------------------------------------------------------- behaviors 7 and 8 (over-reach)

@pytest.mark.parametrize("locator", ACCEPTED_NON_URL_LOCATORS)
def test_behaviors7and8_non_url_locators_stay_accepted(locator):
    """Pinned so a successor cannot tighten this into a URL rule without a failing test.
    Row 57 of the roadmap records why: the schema, `tools/promote.py` and
    `tools/check_locators.py` disagree about locator SHAPE, so non-blank is the only rule
    all three doors already agree on."""
    assert Evidence.model_validate(_ev(locator=locator)).locator == locator


@pytest.mark.parametrize("locator", ACCEPTED_NON_URL_LOCATORS)
def test_behaviors7and8_non_url_register_still_validates(tmp_path, capsys, locator):
    d = _register(tmp_path, locator)
    assert main(["validate", str(d)]) == 0, capsys.readouterr().err


# ---------------------------------------------------------------------------- behavior 9

def test_behavior9_no_live_citation_carries_a_blank_locator():
    """The MECHANISM behind 'no derived score moves': the new rule excludes no live record,
    so no confidence, priority or floor status can move. Anti-vacuous on both counts."""
    files = sorted(LIVE_GAPS.glob("*.json"))
    assert len(files) > 0, "vacuous domain: no record files"
    locators = [
        c["locator"]
        for f in files
        for c in json.loads(f.read_text(encoding="utf-8"))["evidence"]
    ]
    assert len(locators) > 0, "vacuous domain: no citations"
    assert [l for l in locators if not l.strip()] == []


def test_behavior9_every_live_record_still_scores():
    gaps = load_all(pathlib.Path(LIVE_GAPS))
    assert len(gaps) > 0
    for g in gaps:
        assert 0 <= scoring.confidence(g) <= 5
        assert scoring.priority(g) > 0


def test_behavior9_ranked_and_below_floor_partition_every_record():
    """The invariant `VISION.md` protects by name: below-floor records are DISPLAYED, never
    dropped. The two partitions must cover the register exactly once."""
    gaps = load_all(pathlib.Path(LIVE_GAPS))
    assert len(gaps) > 0
    ranked = [row[0].id for row in scoring.rank(gaps)]
    below = [row[0].id for row in scoring.below_floor(gaps)]
    assert sorted(ranked + below) == sorted(g.id for g in gaps)
    assert set(ranked) & set(below) == set()


#: The corroboration point is only OBSERVABLE below the ceiling. Measured this run: with
#: `("peer-reviewed", "first-party-field")` both the distinct-locator and shared-locator
#: records score 5, because the strongest class alone already weighs 5 and the point is
#: clipped. `("vendor-primary", "secondary-summary")` scores 5 vs 4, so it can see the
#: point. A probe that picks a saturating pair reports "the locator does not matter".
CORROBORATION_CLASSES = ["vendor-primary", "secondary-summary"]


def _gap_with_locators(locators: list[str]):
    from agent_gap_radar.models import Gap

    return Gap.model_validate({
        **{k: v for k, v in RECORD.items() if k != "evidence"},
        "evidence": [
            _ev(locator=loc, source_class=cls, title=f"t{i}")
            for i, (loc, cls) in enumerate(zip(locators, CORROBORATION_CLASSES))
        ],
    })


def test_behavior9_locator_remains_load_bearing_for_confidence():
    """Why this field was worth validating: `_source_key` reads the locator, so two
    citations sharing one locator are ONE source and lose the corroboration point. Measured
    two-sided with non-blank locators, which is all the schema now permits."""
    distinct = scoring.confidence(_gap_with_locators(["https://a.invalid/x",
                                                      "https://b.invalid/y"]))
    shared = scoring.confidence(_gap_with_locators(["https://a.invalid/x",
                                                    "https://a.invalid/x"]))
    assert distinct > shared, (distinct, shared)


def test_behavior9_a_blank_locator_can_no_longer_reach_the_score_at_all():
    """The closed hole, stated as behavior: the pair of records whose confidence used to
    differ by a silently-withheld corroboration point cannot both be BUILT any more, so the
    derived number can no longer be moved by a field nothing validated."""
    with pytest.raises(ValidationError):
        _gap_with_locators(["", ""])


# --------------------------------------------------------------------------- behavior 10

@pytest.mark.parametrize("verb", HUMAN_SURFACES)
def test_behavior10_human_surface_is_deterministic(capsys, verb):
    argv = _surface_argv(verb)
    assert main(list(argv)) == 0
    first = capsys.readouterr()
    assert main(list(argv)) == 0
    second = capsys.readouterr()
    assert first.out == second.out
    assert first.out != ""
    assert first.err == "" and second.err == ""


@pytest.mark.parametrize("verb", HUMAN_SURFACES)
def test_behavior10_human_surface_ends_in_exactly_one_newline(capsys, verb):
    assert main(_surface_argv(verb)) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_behavior10_list_still_displays_every_record(capsys):
    """A schema gate that quietly shrank the displayed register would break the one rule
    the product protects by name, so the never-drop property is asserted here too."""
    gaps = load_all(pathlib.Path(LIVE_GAPS))
    assert len(gaps) > 0
    assert main(["list", str(LIVE_GAPS)]) == 0
    out = capsys.readouterr().out
    missing = [g.id for g in gaps if g.id not in out]
    assert missing == [], missing


# ---------------------------------------------------- acceptance criteria on the roadmap

def test_roadmap_records_this_iteration_once():
    """The spec requires row 44 flipped to `shipped`, a new row 57 for the deferred
    three-door reconciliation, and exactly one `- iter 24` ledger bullet, all in the same
    commit as the code."""
    text = (REPO_ROOT / "PRODUCT.md").read_text(encoding="utf-8")
    rows = {
        line.split("|")[1].strip(): line
        for line in text.splitlines()
        if line.startswith("| ") and line.split("|")[1].strip().isdigit()
    }
    assert "44" in rows, "roadmap row 44 is missing"
    assert rows["44"].split("|")[3].strip() == "shipped", rows["44"]
    assert "57" in rows, "roadmap row 57 (deferred three-door reconciliation) is missing"
    assert rows["57"].split("|")[3].strip() == "open", rows["57"]
    assert len([l for l in text.splitlines() if l.startswith("- iter 24 ")]) == 1
