"""Apply the register's checks to a concrete target repository.

This is what turns the register from a reading list into an instrument: point it
at a service or an agent project and it reports which known gaps that specific
target exhibits, with file:line locations, plus the questions a human must
answer where static analysis honestly cannot decide.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from .checks import (CheckOutcome, UNKNOWN_MEANING, Verdict, file_cache_scope,
                     read_cache_scope, run_check)
from .models import Gap
from .render import document, json_document, table
from .scoring import CONFIDENCE_FLOOR_DEFAULT, confidence, priority

#: What an all-zero verdict census means when the register itself was empty.
#: Deliberately names NO path: `scan()` receives a list of gaps and never learns
#: where they came from, so a claimed register path would be a guess.
EMPTY_REGISTER_NOTE = (
    "**No records were applied, so this scan verdicted nothing.** An all-zero "
    "census is vacuous here, not a clean target: check the register path.")


@dataclass
class Finding:
    gap: Gap
    outcome: CheckOutcome

    @property
    def verdict(self) -> Verdict:
        return self.outcome.verdict

    @property
    def priority(self) -> float:
        return priority(self.gap)

    @property
    def confidence(self) -> int:
        return confidence(self.gap)


@dataclass
class ScanResult:
    target: pathlib.Path
    findings: list[Finding]
    uncheckable: list[Gap]
    #: How the caller spelled the target, verbatim -- or `None` when a caller
    #: constructed the result directly and named no spelling. Carried BESIDE the
    #: resolved `target` and never instead of it: the file walk, `target_name`
    #: and the document heading all keep reading the resolved path, so the
    #: document still states WHAT was scanned. Defaulted because committed
    #: callers pass the first three fields positionally.
    requested_spelling: str | None = None

    @property
    def displayed_target(self) -> str:
        """The target as both DOCUMENTS name it: the caller's spelling, when there was one.

        The SINGLE accessor for that value. `scan_json`'s `target` and
        `render_scan`'s `Target:` line are the same claim about one scan, and this
        repo has paid four times (roadmap rows 26, 32, 46, 72) for an invariant
        that had two implementations -- two copies of the fallback below would hold
        only while they happened to agree.

        WHY the spelling and not the resolved path: `docs/CONSUMER_CONTRACT.md`
        points a CI gate at `scan --json` as an artifact to COMMIT and DIFF, and a
        resolved root makes that artifact reproducible only on the machine that
        produced it -- so the same committed invocation (`radar scan .`) reports a
        change that did not happen, and exports an account name nobody asked the
        tool to invent. The portable identity is already published beside it:
        `target_name` stays the resolved base name, so this removes an invented
        value rather than information.

        The echo is VERBATIM -- no expansion, no resolution, no trailing-slash
        normalisation -- because a normalised spelling is a value the caller never
        typed, and relativising against the cwd can emit `../..` chains or fail
        outright across volumes. The property bought is therefore byte-equality
        per INVOCATION, not per target: two spellings of one directory still
        differ here, and in nothing else.

        Falls back to the resolved path when there is no spelling to echo, so a
        directly-constructed result names the path it was given rather than
        rendering a blank field.
        """
        return (str(self.target) if self.requested_spelling is None
                else self.requested_spelling)

    def by_verdict(self, verdict: Verdict) -> list[Finding]:
        return [f for f in self.findings if f.verdict is verdict]

    @property
    def records_applied(self) -> int:
        """How many register records this scan actually reached.

        DERIVED from the two collections that partition the register -- every gap
        either got its check run (a `Finding`) or had no check to run
        (`uncheckable`) -- so it cannot disagree with them the way a counter
        incremented at the call site could, and neither renderer needs a second
        source for the number.

        This is the denominator the rest of both documents is relative to. An
        all-zero verdict census over an emptied or misdirected register is
        otherwise indistinguishable from a target that exhibits none of the
        register's gaps, and the indistinguishable reading is the REASSURING one,
        on the exact payload `docs/CONSUMER_CONTRACT.md` points a CI gate at.
        """
        return len(self.findings) + len(self.uncheckable)

    @property
    def actionable(self) -> list[Finding]:
        """PRESENT findings, worst first. This is the work queue."""
        rows = self.by_verdict(Verdict.PRESENT)
        rows.sort(key=lambda f: (-f.priority, f.gap.id))
        return rows


@dataclass
class PrdSelection:
    """Which PRESENT finding `--prd` may build against, and what the floor cost.

    `passed_over` is an audit trail, not a leftover. The register's one protected
    rule is that a below-floor record is DISPLAYED rather than silently dropped;
    a selection that quietly stepped past one would re-create that drop on the
    single surface deciding what actually gets built. Empty when the floor
    changed nothing, which is the common case.
    """

    selected: Finding | None
    passed_over: list[Finding]


def select_for_prd(result: ScanResult,
                   confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT
                   ) -> PrdSelection:
    """The worst PRESENT finding whose EVIDENCE clears `confidence_floor`.

    Walks `actionable` in its own `(-priority, id)` order, so the floor changes
    WHICH finding is built against and never what the scan found or reported.

    `passed_over` collects only the below-floor findings ranked AHEAD of the
    selection: one ranked below it cost nothing, so naming it would be noise.
    When nothing clears the floor the walk runs off the end and collects every
    PRESENT finding, which is exactly the list a refusal has to name -- one
    loop, both outcomes, no second predicate to drift.

    A displayed record is not an actionable one: `radar prd` already refuses to
    auto-select below the floor, and this is the same automatic path. An
    explicitly named `radar prd --gap X` still bypasses it, because a human
    named it.
    """
    passed_over: list[Finding] = []
    for finding in result.actionable:
        if finding.confidence >= confidence_floor:
            return PrdSelection(selected=finding, passed_over=passed_over)
        passed_over.append(finding)
    return PrdSelection(selected=None, passed_over=passed_over)


def gate_verdict(result: ScanResult,
                 confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT) -> bool | None:
    """Does this target exhibit a PRESENT gap whose EVIDENCE clears the floor?

    THREE-valued on purpose, because "no" has two meanings a gate must not be
    handed as one. `None` says the scan applied ZERO register records, so there is
    no verdict to report at all: an all-zero verdict census over an emptied,
    moved, or one-level-too-high register is otherwise indistinguishable from a
    target that exhibits none of the register's gaps, and the indistinguishable
    reading is the REASSURING one. `radar validate` already refuses that exact
    input rather than certifying it, and a caller asking for a verdict code is
    asking the same kind of question, so it gets the same answer.

    DERIVED from `select_for_prd`, never from a second floor comparison. That walk
    already answers "is there a PRESENT finding at or above the floor" -- its
    `selected` is precisely that finding -- so reusing it means the exit code and
    `--prd` cannot tell a consumer two different stories about one target, and the
    floor rule keeps exactly one spelling. A below-floor PRESENT finding therefore
    reports False here for the same reason `--prd` refuses to build against it: it
    is a research task, not a verdict. It is still DISPLAYED, because this
    function changes no document -- only the code the process exits with.
    """
    if result.records_applied == 0:
        return None
    return select_for_prd(result, confidence_floor).selected is not None


def _finding_json(finding: Finding, confidence_floor: int) -> dict[str, object]:
    """One finding as a stable object, with its floor status derived in place.

    `confidence()` is evaluated exactly ONCE, into `conf`, and both the published
    `confidence` and `below_floor` read that same local. Reading the property
    twice would score the record twice and leave the consumer's only cross-check
    -- the printed confidence against the published floor -- resting on two
    evaluations agreeing rather than on one value. `below_floor` is the exact
    complement of the `>=` that `select_for_prd` applies, so the two surfaces
    cannot tell a caller different stories about the same record.
    """
    conf = finding.confidence
    return {
        "gap_id": finding.gap.id,
        "title": finding.gap.title,
        "layer": finding.gap.layer,
        "gap_type": finding.gap.gap_type,
        "verdict": finding.verdict.value,
        "priority": finding.priority,
        "confidence": conf,
        "below_floor": conf < confidence_floor,
        "reason": finding.outcome.reason,
        "question": finding.outcome.question,
        # Lexical evidence of the signature, ranked code-first. NOT a
        # fix list: a regex match is not a proof of the defect's site.
        "locations": list(finding.outcome.locations),
        "build_hypothesis": finding.gap.build_hypothesis,
    }


def scan_json(result: ScanResult,
              confidence_floor: int = CONFIDENCE_FLOOR_DEFAULT) -> str:
    """A stable object for machine consumers (a CI gate, a build loop).

    Separate from the markdown brief on purpose: a gate that regex-scrapes prose
    breaks the first time a heading is reworded. Emits `priority` and
    `confidence` as distinct fields and never a blended score, so a consumer
    cannot accidentally launder a low-confidence record into a high-priority one.

    Publishes the floor it APPLIED, and flags every finding against it. Without
    the floor on this surface a consumer has to hard-code the threshold across a
    repo boundary -- where no test in this repo can ever see it drift -- to obey
    the two rules the contract binds it to: a record whose only evidence is
    model-output may never block anything, and a below-floor finding must carry
    its floor status. Publishing both makes the register's one protected rule
    (below-floor records are DISPLAYED, never dropped) assertable on the surface
    a gate actually reads, rather than only in the prose that describes it.

    The floor changes no verdict and drops no finding: it is reported, never
    applied as a filter. `counts` stays a pure verdict census for the same
    reason -- a stray non-verdict key would break a consumer iterating it.

    `records_applied` sits BESIDE that census rather than inside it, for the same
    reason: it is the denominator, not a verdict. Summing `counts` and
    `uncheckable` already yields the number, and leaving a consumer to re-derive
    it across the repo boundary -- where no test here can see the arithmetic drift
    -- is precisely how a register that never loaded reads as a clean target.
    """
    payload = {
        "target": result.displayed_target,
        "target_name": result.target.name,
        "confidence_floor": confidence_floor,
        "records_applied": result.records_applied,
        "counts": {v.value: len(result.by_verdict(v)) for v in Verdict},
        "uncheckable": [g.id for g in result.uncheckable],
        "findings": [
            _finding_json(f, confidence_floor)
            for f in sorted(result.findings,
                            key=lambda f: (f.verdict.value, -f.priority, f.gap.id))
        ],
    }
    return json_document(payload)


def scan(gaps: list[Gap], target: pathlib.Path | str) -> ScanResult:
    # Captured BEFORE resolution, because resolution destroys it: this is the one
    # value in the result the tool did not compute, and echoing it is what makes a
    # committed invocation's document reproducible off this machine. An empty
    # argument spells no target at all, so it takes `displayed_target`'s
    # resolved-path fallback instead of emitting a blank field.
    requested = str(target) or None
    target = pathlib.Path(target).expanduser().resolve()
    if not target.is_dir():
        raise NotADirectoryError(str(target))

    findings: list[Finding] = []
    uncheckable: list[Gap] = []

    # One read snapshot and one enumeration snapshot per scan. Every gap's rules
    # reach the target through these scopes, so a file reached by several rules is
    # decoded once, a domain asked for by several rules is walked once, and every
    # rule in THIS scan sees the same bytes and the same file list; both scopes
    # close before the result is returned, so no later scan can be answered from
    # either. Entered together because a scan that held one and not the other
    # would answer two rules from one snapshot and one stale walk.
    with read_cache_scope(), file_cache_scope():
        for gap in sorted(gaps, key=lambda g: g.id):
            if gap.check is None:
                uncheckable.append(gap)
                continue
            outcome = run_check(gap.check.model_dump(exclude_none=True), target)
            findings.append(Finding(gap=gap, outcome=outcome))

    return ScanResult(target=target, findings=findings,
                      uncheckable=uncheckable,
                      requested_spelling=requested)


def render_scan(result: ScanResult) -> str:
    """Markdown scan report.

    The one-newline tail and the table formatting are `render.document` and
    `render.table`, not copies of them: an invariant with two implementations
    holds only while the copies happen to agree.
    """
    # The heading names the RESOLVED base name (what was scanned) while the
    # Target line echoes the caller's spelling (what they asked for); both read
    # one accessor each, so neither can drift into the other's job.
    lines = [f"# Gap scan: {result.target.name}", "",
             f"Target: `{result.displayed_target}`", ""]

    counts = {v: len(result.by_verdict(v)) for v in Verdict}
    meaning = {
        Verdict.PRESENT: "gap signature found in this target",
        Verdict.ABSENT: "a mitigation was positively identified",
        Verdict.MANUAL: "static analysis cannot decide; a human must answer",
        Verdict.NOT_APPLICABLE: "this gap cannot apply to this target",
        Verdict.UNKNOWN: UNKNOWN_MEANING,
    }
    # Rows follow `Verdict` declaration order -- PRESENT, ABSENT,
    # NOT_APPLICABLE, MANUAL, UNKNOWN -- which is what the committed bytes
    # carry; `meaning` is keyed by member so a reordering cannot silently
    # pair a count with the wrong sentence.
    lines += table(["Verdict", "Count", "Meaning"],
                   [[v.value, str(counts[v]), meaning[v]] for v in Verdict])
    # The count LEADS the pair because it is the denominator: `Gaps with no check
    # yet` is a share of it, and a reader who takes the second number without the
    # first cannot tell a scan of nothing from a scan that found nothing.
    lines += ["", f"Register records applied: {result.records_applied}",
              f"Gaps with no check yet: {len(result.uncheckable)}"]
    if result.records_applied == 0:
        lines.append(EMPTY_REGISTER_NOTE)
    lines.append("")

    lines += ["## Actionable now (PRESENT, worst first)", ""]
    if result.actionable:
        for f in result.actionable:
            lines += [f"### {f.gap.id} -- {f.gap.title}", "",
                      f"- Priority {f.priority:.1f}, evidence confidence {f.confidence}",
                      f"- Layer: `{f.gap.layer}` | type: `{f.gap.gap_type}`",
                      f"- Why this matters: {f.gap.problem}"]
            if f.outcome.locations:
                # "Signature seen at", not "fix here": these are lexical
                # matches evidencing the pattern, ranked code-first. Calling
                # them a fix list would overstate what a regex established.
                lines.append("- Signature seen at (evidence, ranked code first):")
                lines += [f"  - `{loc}`" for loc in f.outcome.locations]
            if f.gap.build_hypothesis:
                lines.append(f"- Suggested fix: {f.gap.build_hypothesis}")
            lines.append("")
    else:
        lines += ["None found.", ""]

    lines += ["## Needs a human answer (MANUAL)", "",
              "These are not passes. Static analysis cannot settle them, so the "
              "tool asks instead of guessing.", ""]
    manual = sorted(result.by_verdict(Verdict.MANUAL),
                    key=lambda f: (-f.priority, f.gap.id))
    if manual:
        for f in manual:
            lines += [f"- **{f.gap.id}** ({f.priority:.1f}) {f.gap.title}",
                      f"  - {f.outcome.question or 'Confirm by hand.'}"]
            if f.outcome.locations:
                lines.append(f"  - context: `{f.outcome.locations[0]}`")
        lines.append("")
    else:
        lines += ["None found.", ""]

    mitigated = result.by_verdict(Verdict.ABSENT)
    lines += ["## Positively mitigated (ABSENT)", ""]
    if mitigated:
        lines += [f"- **{f.gap.id}** {f.gap.title} (evidence: "
                  f"`{f.outcome.locations[0] if f.outcome.locations else 'n/a'}`)"
                  for f in sorted(mitigated, key=lambda f: f.gap.id)]
    else:
        lines.append("None found.")
    lines.append("")

    unknown = result.by_verdict(Verdict.UNKNOWN)
    if unknown:
        # Derived from the member, not spelled: a heading naming a CAUSE was
        # false for half the findings under it, and a hand-typed value drifts
        # from the enum the moment either is edited.
        lines += [f"## No verdict ({Verdict.UNKNOWN.value})", ""]
        lines += [f"- **{f.gap.id}** {f.outcome.reason}" for f in unknown]
        lines.append("")

    return document(lines)
