"""Iteration 29 behaviors: the deep view states whether a gap is DETECTABLE, and how.

`radar scan` can only return a verdict for a record that carries an automated signature.
Over the live register that is 12 of 16; the other four -- three manual-only checks and one
record with no check at all -- can never be scored, and before this iteration `radar show`
rendered them indistinguishably from the twelve. Iteration 29 adds one `## Detection`
section to the brief naming the record's check id and the DERIVED automated/manual verdict.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source (`src/`, `tools/`), the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`,
or any diff. Every verdict about rendered output is produced by CALLING `cli.main` and
reading its stdout; `gaps/*.json` is read as DATA (it is the register under test, not an
implementation), and every expectation is derived from `pm.md`'s Expected Behaviors.

Structural notes, so this file cannot lie later:

* **The expected detectability is DERIVED from the record, never copied from the output.**
  `_expected_detectability` re-implements the spec's own rule in this file -- a check that
  declares a static signature (`present_when` / `mitigated_when`) is `automated`, a check
  with only a question is `manual`, and no check at all is `none`. An expectation lifted
  out of the rendered text would agree with any renderer, including one that printed
  `automated` for all sixteen records.
* **Behavior 4's "every other section is byte-unchanged" is asserted as CONFINEMENT, not as
  a HEAD comparison.** HEAD moves the moment this iteration lands, so a suite-level
  `== git show HEAD` is either vacuous or red on every future iteration; the byte-for-byte
  comparison against the pre-iteration tree is measured once, out of band, in the tester's
  report. What is durable and asserted here: the seven `##` headings appear in a pinned
  ORDER, `## Detection` is a single contiguous block sitting immediately before
  `## Evidence`, and after that block is EXCISED the remaining text carries none of the new
  vocabulary (`CHK-`, `detectability`, `Rules declared`). A renderer that leaked the check
  id into `## Problem` reds here even though the total byte count would look plausible.
* **Behavior 2 is tested at its EDGE with a synthetic record, because no live record has
  that shape.** All three live manual-only checks declare no rules at all, so a renderer
  that decided `manual` by asking "are the rule slots empty?" instead of "is there a static
  signature?" would pass over the whole live register. `test_b2_manual_question_survives_a_
  declared_applies_when` builds the missing shape in `tmp_path` -- a manual check that also
  carries an `applies_when` -- and ASSERTS ITS OWN PREMISE first (the mutated record must
  still LOAD, else the test proves nothing about rendering).
* **The claim the section makes about `scan` is checked against `scan` itself.** Prose
  saying "so `radar scan` never applies this record" is a testable assertion, not
  decoration: behavior 5 runs `scan --json` and requires the record rendered `none` to
  appear in `uncheckable` and NOT among `findings`, and every record rendered `manual` to
  come back with verdict `MANUAL`. Only that direction is asserted -- an automated record
  can also legitimately land on `MANUAL` when nothing matches (measured: 6 MANUAL verdicts
  against 3 manual-only records), so the converse would be a false claim.
* **Every matcher used to certify an ABSENCE is proved two-sided in the same test.** The
  section reader is shown to FIND a section that exists and to return `None` for a heading
  that does not, so a reader that silently matched nothing could not report health.
* **No absolute machine path and no personal identifier appears here**: every path is
  derived from `__file__` or from pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar import cli

#: The register under test, found relative to this file so no machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: The `##` sections the brief renders, in order. `## Detection` is this iteration's addition.
EXPECTED_HEADINGS = (
    "## Problem",
    "## Symptom",
    "## Why this is still open",
    "## Existing partial solutions",
    "## Build hypothesis",
    "## Detection",
    "## Evidence",
)

DETECTION = "## Detection"

#: Vocabulary introduced by this iteration. None of it may appear outside `## Detection`.
NEW_VOCABULARY = ("CHK-", "detectability", "Rules declared")

#: The rule slots that make a check machine-evaluable. `applies_when` alone only gates
#: whether the question is relevant, so it is deliberately NOT in this set.
SIGNATURE_SLOTS = ("present_when", "mitigated_when")


def _records() -> list[dict]:
    """Every register record, read as data, ordered by id for a stable parametrisation."""
    records = [json.loads(p.read_text()) for p in sorted(GAPS_DIR.glob("*.json"))]
    assert records, f"no gap records found under {GAPS_DIR.name}/ -- fixture is empty"
    return records


def _by_id() -> dict[str, dict]:
    return {r["id"]: r for r in _records()}


RECORDS = _records()
RECORD_IDS = [r["id"] for r in RECORDS]


def _expected_detectability(record: dict) -> str:
    """The spec's own derivation: signature -> automated, question only -> manual, else none."""
    check = record.get("check")
    if check is None:
        return "none"
    if any(check.get(slot) for slot in SIGNATURE_SLOTS):
        return "automated"
    return "manual"


def _show(capsys, gap_id: str, register: pathlib.Path | None = None) -> tuple[int, str, str]:
    """`radar show <gap_id> <register>` in process. Returns (exit code, stdout, stderr)."""
    capsys.readouterr()
    root = REPO_ROOT if register is None else register
    code = cli.main(["show", gap_id, str(root)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _section(document: str, heading: str) -> str | None:
    """The body of `heading` up to the next `## `, or None when the heading is absent.

    Proved two-sided by `test_the_section_reader_is_two_sided` before any absence claim
    in this module is believed.
    """
    lines = document.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.rstrip("\n") == heading:
            body: list[str] = []
            for follower in lines[index + 1:]:
                if follower.startswith("## "):
                    break
                body.append(follower)
            return "".join(body)
    return None


def _without_detection(document: str) -> str:
    """The brief with the whole `## Detection` block excised, heading included."""
    body = _section(document, DETECTION)
    assert body is not None, "cannot excise a section that is not there"
    block = DETECTION + "\n" + body
    assert document.count(block) == 1, "the Detection block is not a single contiguous run"
    return document.replace(block, "")


# --------------------------------------------------------------------------- the reader


def test_the_section_reader_is_two_sided(capsys):
    """The matcher every absence claim below rests on must find a real section and miss a
    fake one. Without this leg, a reader that returned None for everything would make each
    'no new vocabulary outside Detection' assertion pass while measuring nothing."""
    _, out, _ = _show(capsys, RECORD_IDS[0])
    assert _section(out, "## Problem"), "reader found nothing in a section that exists"
    assert _section(out, "## No Such Heading") is None, "reader matched a heading that is absent"


# ------------------------------------------------------- behavior 1: the check id is named


def test_b1_an_automated_record_names_its_check_id(capsys):
    """Behavior 1: `radar show GAP-006` prints a `## Detection` section naming the check id."""
    code, out, err = _show(capsys, "GAP-006")
    assert code == 0
    assert err == ""
    assert out.count("\n" + DETECTION + "\n") == 1, "expected exactly one Detection heading"
    body = _section(out, DETECTION)
    assert body is not None and body.strip(), "Detection section is missing or empty"
    assert "CHK-006" in body, f"check id not named in the section:\n{body}"


@pytest.mark.parametrize("gap_id", RECORD_IDS)
def test_b1_every_record_names_its_own_check_id_and_derived_verdict(capsys, gap_id):
    """Behavior 1, over the whole register: the section names THE RIGHT check id and the
    verdict DERIVED from the record. GAP-011 carries CHK-010, so an off-by-one that paired
    a record with its neighbour's check reds here and nowhere else."""
    record = _by_id()[gap_id]
    _, out, _ = _show(capsys, gap_id)
    body = _section(out, DETECTION)
    assert body is not None and body.strip(), f"{gap_id}: Detection section missing or empty"

    expected = _expected_detectability(record)
    assert f"`{expected}`" in body, f"{gap_id}: derived verdict {expected!r} not stated:\n{body}"
    for other in {"automated", "manual", "none"} - {expected}:
        assert f"`{other}`" not in body, f"{gap_id}: section also claims {other!r}:\n{body}"

    check = record.get("check")
    if check is None:
        assert "CHK-" not in body, f"{gap_id}: names a check id but the record has none:\n{body}"
    else:
        assert f"`{check['id']}`" in body, f"{gap_id}: {check['id']} not named:\n{body}"
        wrong = [
            other["check"]["id"]
            for other in RECORDS
            if other.get("check") and other["check"]["id"] != check["id"]
        ]
        named_wrong = [cid for cid in wrong if cid in body]
        assert not named_wrong, f"{gap_id}: names another record's check {named_wrong}"


# --------------------------------------------- behavior 2: the manual question is rendered


def test_b2_manual_only_records_print_their_manual_question(capsys):
    """Behavior 2: a manual-only record prints its manual question in the section.

    Asserted verbatim against the register field, so a paraphrase or a truncation reds.
    """
    manual = [r for r in RECORDS if _expected_detectability(r) == "manual"]
    assert manual, "no manual-only record in the register -- behavior 2 would be vacuous"
    for record in manual:
        _, out, _ = _show(capsys, record["id"])
        body = _section(out, DETECTION)
        assert body is not None, f"{record['id']}: no Detection section"
        question = record["check"]["manual_question"]
        assert question in body, (
            f"{record['id']}: manual question not rendered verbatim.\n"
            f"expected: {question!r}\nsection:\n{body}"
        )


def test_b2_an_automated_record_does_not_advertise_a_manual_question(capsys):
    """The discriminating leg of behavior 2. The section exists to separate the records
    `scan` can score from the ones it cannot; if the question were printed for every
    record, behavior 2 would pass while the section distinguished nothing.

    NOTE (PM feedback, recorded rather than assumed): printing the question for automated
    records TOO is a defensible reading of the spec, which only says a manual-only record
    must print it. This asserts the shipped reading -- automated records state their rules
    instead -- and is the one assertion in this file that a future iteration might
    legitimately have to change.
    """
    automated = [
        r
        for r in RECORDS
        if _expected_detectability(r) == "automated" and r["check"].get("manual_question")
    ]
    assert automated, "no automated record carries a manual question -- leg is vacuous"
    record = automated[0]
    _, out, _ = _show(capsys, record["id"])
    body = _section(out, DETECTION)
    assert record["check"]["manual_question"] not in body, (
        f"{record['id']} is automated yet its section prints the manual question, so the "
        "section no longer separates scorable records from unscorable ones"
    )


def test_b2_manual_question_survives_a_declared_applies_when(capsys, tmp_path):
    """Behavior 2 at its EDGE, with the shape no live record has.

    A check may carry `applies_when` (which only gates relevance) and still have no static
    signature -- it is manual. A renderer that decided 'manual' by asking whether the rule
    slots are EMPTY, rather than whether a SIGNATURE exists, would classify this record
    automated, print its rules, and silently drop the human question. 0 of 16 live records
    exercise it, so the whole live register and the full suite are blind to it.
    """
    source = next(r for r in RECORDS if _expected_detectability(r) == "manual")
    raw = json.loads(json.dumps(source))
    donor = next(r for r in RECORDS if _expected_detectability(r) == "automated")
    applies_when = donor["check"]["applies_when"]

    raw["check"]["applies_when"] = applies_when
    for slot in SIGNATURE_SLOTS:
        raw["check"].pop(slot, None)
    question = raw["check"]["manual_question"]

    register = tmp_path / "register"
    (register / "gaps").mkdir(parents=True)
    (register / "gaps" / "record.json").write_text(json.dumps(raw, indent=2) + "\n")

    # Premise first: an unloadable fixture would make every claim below vacuous.
    code, out, err = _show(capsys, raw["id"], register)
    assert code == 0, f"the fixture register did not load (exit {code}): {err}"
    assert _expected_detectability(raw) == "manual", "fixture is not the manual shape"
    assert raw["check"]["applies_when"], "fixture lost the applies_when it exists to carry"

    body = _section(out, DETECTION)
    assert body is not None, "no Detection section for the fixture record"
    assert "`manual`" in body, f"a check with only applies_when was not called manual:\n{body}"
    assert "`automated`" not in body, f"a check with no signature was called automated:\n{body}"
    assert question in body, f"the manual question was dropped:\n{body}"


# ------------------------------------------- behavior 3: no check at all is stated, not blank


def test_b3_a_record_with_no_check_states_it_explicitly(capsys):
    """Behavior 3: a record with no check prints an explicit statement, not an empty section."""
    uncheckable = [r for r in RECORDS if r.get("check") is None]
    assert uncheckable, "every record has a check -- behavior 3 would be vacuous"
    for record in uncheckable:
        _, out, _ = _show(capsys, record["id"])
        body = _section(out, DETECTION)
        assert body is not None, f"{record['id']}: no Detection section"
        prose = [line for line in body.splitlines() if line.strip()]
        assert prose, f"{record['id']}: Detection section is empty"
        assert "`none`" in body, f"{record['id']}: derived verdict not stated:\n{body}"
        assert "CHK-" not in body, f"{record['id']}: names a check that does not exist:\n{body}"
        assert "scan" in body, (
            f"{record['id']}: the section does not say what this means for scan:\n{body}"
        )


# -------------------------------------------- behavior 4: one newline, nothing else moved


@pytest.mark.parametrize("gap_id", RECORD_IDS)
def test_b4_the_brief_ends_in_exactly_one_newline_and_is_deterministic(capsys, gap_id):
    """Behavior 4: exactly one trailing newline, byte-stable across calls, stdout only."""
    code, first, err = _show(capsys, gap_id)
    assert code == 0
    assert err == "", f"{gap_id}: wrote to stderr on success: {err!r}"
    assert first.endswith("\n"), f"{gap_id}: does not end in a newline"
    assert not first.endswith("\n\n"), f"{gap_id}: ends in more than one newline"
    assert not any(
        line != line.rstrip() for line in first.splitlines()
    ), f"{gap_id}: a line carries trailing whitespace"
    _, second, _ = _show(capsys, gap_id)
    assert first == second, f"{gap_id}: two identical calls produced different bytes"


@pytest.mark.parametrize("gap_id", RECORD_IDS)
def test_b4_the_new_section_is_confined_and_the_heading_order_is_pinned(capsys, gap_id):
    """Behavior 4, durable form: the change is CONFINED to one contiguous new section.

    The byte-for-byte comparison against the pre-iteration tree is measured out of band in
    the tester's report -- HEAD moves when this lands. What survives every future iteration
    is that `## Detection` is one block sitting immediately before `## Evidence`, and that
    none of the new vocabulary leaked into any other section.
    """
    _, out, _ = _show(capsys, gap_id)
    headings = tuple(line for line in out.splitlines() if line.startswith("## "))
    assert headings == EXPECTED_HEADINGS, f"{gap_id}: heading order changed: {headings}"

    remainder = _without_detection(out)
    for token in NEW_VOCABULARY:
        assert token not in remainder, (
            f"{gap_id}: {token!r} appears outside the Detection section, so the new section "
            "is not the only thing that changed"
        )
    # Count HEADING LINES, not the substring: `### 1. ...` in `## Evidence` contains `## `,
    # so a `.count("## ")` over the whole document is a broken measurement (it reported 10
    # for a 7-heading brief) and would red a correct renderer.
    surviving = tuple(line for line in remainder.splitlines() if line.startswith("## "))
    assert surviving == tuple(h for h in EXPECTED_HEADINGS if h != DETECTION), (
        f"{gap_id}: excising Detection changed the other headings: {surviving}"
    )
    assert remainder.startswith(f"# {gap_id}: "), f"{gap_id}: title line moved"
    assert remainder.endswith("\n"), f"{gap_id}: excision left the remainder unterminated"


def test_b4_the_other_verbs_did_not_gain_the_section(capsys):
    """Behavior 4, cross-verb: `render.gap_brief` is the only renderer in scope, so the
    ranked report, the one-line list and the taxonomy must carry none of the new vocabulary.
    """
    for argv in (["report", str(REPO_ROOT)], ["list", str(REPO_ROOT)], ["taxonomy"]):
        capsys.readouterr()
        code = cli.main(argv)
        out = capsys.readouterr().out
        assert code == 0, f"{argv[0]} exited {code}"
        assert DETECTION not in out, f"{argv[0]} grew a Detection section"
        for token in ("CHK-", "detectability"):
            assert token not in out, f"{argv[0]} gained {token!r}"


# ------------------------------- behavior 5 (derived): the section's claim about scan holds


def test_b5_the_rendered_verdict_agrees_with_what_scan_actually_does(capsys):
    """The section's prose makes a checkable promise about `scan`; check it against `scan`.

    Asserted in the sound direction only: a record rendered `none` must be reported
    uncheckable and never scored, and a record rendered `manual` must come back MANUAL.
    The converse is FALSE by measurement -- an automated record whose signature simply does
    not match also lands on MANUAL -- so requiring `automated` records to be non-MANUAL
    would red a correct suite.
    """
    capsys.readouterr()
    code = cli.main(["scan", str(REPO_ROOT), "--gaps", str(REPO_ROOT), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code in (0, 1), f"scan exited {code}"

    verdicts = {f["gap_id"]: f["verdict"] for f in payload["findings"]}
    uncheckable = set(payload["uncheckable"])
    assert verdicts, "scan returned no findings -- the cross-check would be vacuous"

    for record in RECORDS:
        gap_id = record["id"]
        _, out, _ = _show(capsys, gap_id)
        body = _section(out, DETECTION)
        # Without this leg the whole test passes VACUOUSLY when no section is rendered at
        # all: an empty body takes neither branch below. Measured against the pre-iteration
        # tree, this was the one test in the file that did not red.
        assert body is not None, f"{gap_id}: no Detection section, so nothing to cross-check"
        stated = [word for word in ("`none`", "`manual`", "`automated`") if word in body]
        assert len(stated) == 1, f"{gap_id}: section states {stated} verdict word(s), want 1"
        if "`none`" in body:
            assert gap_id in uncheckable, f"{gap_id} rendered `none` but scan did not skip it"
            assert gap_id not in verdicts, f"{gap_id} rendered `none` yet scan scored it"
        elif "`manual`" in body:
            assert verdicts.get(gap_id) == "MANUAL", (
                f"{gap_id} rendered `manual` but scan returned {verdicts.get(gap_id)!r}"
            )
