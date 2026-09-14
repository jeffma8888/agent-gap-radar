"""Bridge: turn the top-ranked gap into a build-loop PRD.

This is the point of the whole project. Research that does not change what gets
built is a reading list. The emitted document is the prd.json shape consumed by
Ralph-style loops (ordered stories, `passes` flags, verifiable criteria), so the
handoff from "we found the gap" to "a loop is building against it" is one command.
"""

from __future__ import annotations

from .models import Check, Gap, detectability
from .render import json_document
from .scoring import confidence, priority

#: Where a register keeps its records, relative to the register root. The emitted
#: document carries a POINTER to that file, never the fixture bytes: a PRD enters a
#: build loop's prompt on every iteration, and this register's own GAP-005 cites a
#: monotonically growing required-reading file killing a loop on a step cap. The
#: pointer is legitimate because the on-disk record is a documented read-only
#: surface (roadmap row 45), so a loop may read it without racing a writer.
_RECORD_DIR = "gaps"

#: Closed three-value vocabulary, one deterministic sentence each. Every sentence
#: states what the REGISTER HOLDS towards a reproduction -- never a judgement about
#: the gap itself, which `priority` and `confidence` already publish as separate,
#: deliberately unblended numbers.
DETECTABILITY_DECLARATIONS: dict[str, str] = {
    "automated": (
        "The register holds a two-sided sample the suite proves discriminates, so the "
        "reproduction is a transcription rather than an invention."),
    "manual": (
        "The register holds no static signature for this gap, so the reproduction rests "
        "on the stated question and on the judgement that answers it."),
    "none": (
        "The register holds no check for this gap at all, so a reproduction must be "
        "argued from the evidence before it can be written."),
}

#: Closed TWO-value vocabulary, one deterministic sentence each, keyed on whether the
#: record's check declares a `mitigated_when` rule -- and on nothing else. That field
#: is the only rule `checks.run_check` accepts as evidence of mitigation and therefore
#: the only thing that can yield the ABSENT verdict, so it, rather than
#: `detectability`, is what decides whether closure is checkable: `Check.is_automated`
#: is satisfied by EITHER rule, so a record can be reproduction-checkable and
#: closure-unsignatured at once and the three-value vocabulary above cannot see the
#: difference. Every sentence states what the REGISTER HOLDS towards closure -- never a
#: judgement about the gap, which `priority` and `confidence` publish as separate,
#: deliberately unblended numbers that this prose may not restate.
CLOSURE_DECLARATIONS: dict[str, str] = {
    "checkable": (
        "The register holds a mitigation signature for this gap, so closure is a "
        "verdict a scan can read rather than a claim a loop makes about itself."),
    "none": (
        "The register holds no mitigation signature for this gap, so no scan verdict "
        "can decide closure and the judgement that closes it must be stated."),
}


def _slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:48]


def _check_payload(gap: Gap) -> dict:
    """What the register holds towards reproducing this gap, and towards closing it.

    Emitted for every record, including one with no check: a MISSING key reads as
    "unknown" to a consumer, while an explicit `"none"` reads as "the register has
    nothing", and those are different facts. The key is always present so a loop
    never has to infer which one it got.

    Two sides, in that order: the reproduction keys say what may be transcribed to
    make the gap PRESENT, and the appended `closure` key says what the register would
    accept as ABSENT. A loop handed only the first half can go green with the gap it
    was built from still reproducing.
    """
    check = gap.check
    kind = detectability(check)
    # A GLOB, not a path, and derived ONCE for the two consumers below -- the
    # reproduction sample and the closure rule -- because both name the same record
    # file and a second derivation is a second convention waiting to drift. Records
    # are stored `gaps/<ID>-<slug>.json`, so the exact filename is not derivable from
    # a `Gap` (which does not carry its source path), and re-deriving the slug here
    # would plant a THIRD divergent copy of the writer's convention:
    # `tools/promote.py:_slug` truncates to 56 chars where `_slug` above truncates to
    # 48, so a derived name is wrong on every record today. The id-is-the-prefix
    # property this leans on is already pinned by `tests/test_iter20_behavior.py`, and
    # `registry.load_all` rejects duplicate ids, so the pattern matches exactly one
    # file.
    record_glob = f"{_RECORD_DIR}/{gap.id}-*.json"
    payload: dict = {
        "id": None if check is None else check.id,
        "detectability": kind,
        "declaration": DETECTABILITY_DECLARATIONS[kind],
        "reproductionSample": None,
    }
    if kind == "automated":
        # `Check._automated_checks_need_fixtures` refuses to LOAD an automated check
        # without fixtures, so this reads an enforced invariant. A guard here would be
        # a branch no record can reach, which is worse than none: it would look like
        # the shape is optional when the schema says it is not.
        fixtures = check.fixtures
        payload["reproductionSample"] = {
            "recordGlob": record_glob,
            "badFiles": sorted(fixtures.bad),
            "goodFiles": sorted(fixtures.good),
        }
    elif kind == "manual":
        # Carried ONLY on a manual check, where the question IS the reproduction
        # instruction. On an automated check the same string is `scan`'s
        # both-signatures escalation question -- a different job, and up to 368
        # bytes of it per record for no build value.
        payload["manualQuestion"] = check.manual_question
    # APPENDED last, on every arm: the PRESENT side above says what may be
    # transcribed, and this says what would make the gap ABSENT. Last so the
    # pre-existing key order a consumer may have pinned is undisturbed.
    payload["closure"] = _closure_payload(check, record_glob)
    return payload


def _closure_payload(check: Check | None, record_glob: str) -> dict:
    """What the register holds towards deciding this gap is CLOSED.

    Published because `mitigated_when` is the only rule `checks.run_check` accepts as
    evidence of mitigation -- evaluated with `exclude_tests=True`, so a mitigation
    named only by a test does not count -- and ABSENT is the only verdict this product
    allows to assert safety. Handing a build loop the rule's ADDRESS lets it check its
    own work against the register instead of declaring itself done, which is the
    asymmetry `VISION.md`'s done-state names.

    READ, never evaluated, and no invocation is invented: `prd` is handed a REGISTER
    path and never a TARGET path, so any command line named here would be a guess
    about a tree this function has not seen.

    Both arms carry all three keys. A MISSING key reads as "unknown" while an explicit
    null reads as "the register has nothing" -- the same distinction `_check_payload`
    makes one level up, and the reason the refusal arm nulls rather than omits.
    """
    checkable = check is not None and check.mitigated_when is not None
    return {
        # The verdict a scan must return, not one it did return: nothing here has run.
        "verdict": "ABSENT" if checkable else None,
        "rule": ({"recordGlob": record_glob, "field": "check.mitigated_when"}
                 if checkable else None),
        "declaration": CLOSURE_DECLARATIONS["checkable" if checkable else "none"],
    }


def _reproduction_criterion(check_payload: dict) -> str:
    """The one acceptance criterion story US-001 gains.

    Story 1 asks a loop to reproduce the gap. Where the register already holds a
    file tree the suite proves yields PRESENT, transcription beats invention; where
    it holds none, the honest instruction is to STATE the judgement the test rests
    on before writing it, so a later reader can see what the reproduction assumed.
    """
    sample = check_payload["reproductionSample"]
    if sample is None:
        return ("No static signature for this gap exists in the register: state the "
                "judgement the reproduction rests on before the test is written")
    record_glob = sample["recordGlob"]
    n_bad, n_good = len(sample["badFiles"]), len(sample["goodFiles"])
    return (f"Transcribe the two-sided sample named by {record_glob} "
            f"({n_bad} bad file(s) that must yield PRESENT, {n_good} good file(s) "
            "that must not) rather than inventing a reproduction")


def _closure_criterion(check_payload: dict, gap_id: str) -> str:
    """The one acceptance criterion story US-002 gains.

    US-002 asks a loop for the smallest mitigation, and before this none of its four
    criteria mentioned the register at all -- so a loop could pass every one of them
    while the gap it was built from still verdicts PRESENT. Read out of the SAME
    closure payload the machine block carries, so the human instruction and the
    machine fact are one derivation of the register rather than two.

    Where the register holds no signature the criterion REFUSES rather than inventing
    a rule: an unfalsifiable "the gap is fixed" criterion is worse than an explicit
    demand that the judgement be written down where a later reader can weigh it.
    """
    closure = check_payload["closure"]
    rule = closure["rule"]
    if rule is None:
        return (f"The register holds no mitigation signature for {gap_id}, so no scan "
                "verdict can decide closure: state the judgement that closes it")
    # The glob is the LAST token, unpunctuated: this line is read by a build loop that
    # may well split it on whitespace, and a trailing comma would hand it a pattern
    # that matches nothing.
    return (f"Closure is read from the register rather than asserted -- the gap "
            f"verdicts {closure['verdict']} against the rule the register holds at "
            f"{rule['field']} in {rule['recordGlob']}")


def prd_for(gap: Gap, project: str = "agent-gap-radar") -> dict:
    """Build a prd.json-shaped dict for one gap.

    Story 1 is always a failing reproduction of the gap. A build loop that
    starts from a spec instead of a red test optimises the spec.
    """
    branch = f"ralph/{_slug(gap.title)}"
    criteria_tail = ["Full test suite passes", "No new runtime dependency"]
    # Built ONCE and read twice: the machine payload below and story US-001's
    # derived criterion must describe the same register, so they cannot be two
    # independent derivations that drift apart.
    check_payload = _check_payload(gap)

    stories = [
        {
            "id": "US-001",
            "title": f"Reproduce {gap.id} as a failing test",
            "description": (
                f"As a maintainer, I need an executable demonstration of {gap.id} "
                "so that any fix is measured against a real failure, not a description."),
            "acceptanceCriteria": [
                f"A test encodes the observed symptom: {gap.symptom}",
                "The test FAILS on the current code and the failure message names the gap",
                *criteria_tail,
                _reproduction_criterion(check_payload),
            ],
            "priority": 1,
            "passes": False,
            "notes": f"Gap priority {priority(gap):.1f}, confidence {confidence(gap)}.",
        },
        {
            "id": "US-002",
            "title": f"Minimal mitigation for {gap.id}",
            "description": (
                "As an operator, I want the smallest change that turns the silent "
                "failure into a visible, actionable one."),
            "acceptanceCriteria": [
                "The US-001 test passes",
                "The mitigation is opt-in or dormant by default (no behaviour change on upgrade)",
                *criteria_tail,
                _closure_criterion(check_payload, gap.id),
            ],
            "priority": 2,
            "passes": False,
            "notes": gap.build_hypothesis,
        },
        {
            "id": "US-003",
            "title": f"Document {gap.id} and its mitigation",
            "description": (
                "As a reader, I want the gap, the evidence, and the mitigation in one "
                "place so the decision is reviewable later."),
            "acceptanceCriteria": [
                "README or docs page states the gap, the symptom, and the mitigation",
                "Every claim cites a locator from the gap record",
                *criteria_tail,
            ],
            "priority": 3,
            "passes": False,
            "notes": "",
        },
    ]

    return {
        "project": project,
        "branchName": branch,
        "description": f"{gap.id} -- {gap.title}. {gap.problem}",
        "sourceGap": {
            "id": gap.id,
            "layer": gap.layer,
            "gapType": gap.gap_type,
            "priority": priority(gap),
            "confidence": confidence(gap),
            "evidence": [
                {"sourceClass": e.source_class, "locator": e.locator, "date": e.date}
                for e in gap.evidence
            ],
            "check": check_payload,
            # APPENDED last: a build loop is handed this document every
            # iteration, so a partially-addressed record must not arrive
            # looking fresh. Read from the record; selection is unchanged.
            "status": gap.status,
        },
        "stories": stories,
    }


def render_prd(gap: Gap, project: str = "agent-gap-radar") -> str:
    return json_document(prd_for(gap, project))
