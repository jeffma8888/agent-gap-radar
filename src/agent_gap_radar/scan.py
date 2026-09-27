"""Apply the register's checks to a concrete target repository.

This is what turns the register from a reading list into an instrument: point it
at a service or an agent project and it reports which known gaps that specific
target exhibits, with file:line locations, plus the questions a human must
answer where static analysis honestly cannot decide.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from .checks import (CheckOutcome, LocationNote, UNKNOWN_MEANING, Verdict,
                     file_cache_scope, read_cache_scope, run_check)
from .models import Gap
from .registry import RegistryError, parse_record
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


def clears_floor(finding: Finding, confidence_floor: int) -> bool:
    """THE floor comparison: does this finding's EVIDENCE reach `confidence_floor`?

    One spelling for the rule every verdict surface applies. `select_for_prd` walks
    with it (so `--prd`'s selection and `--exit-code`'s verdict inherit it), and
    `new_since_baseline` filters with it, so a change to the comparison moves every
    surface together and no surface can tell a consumer a different story about one
    record than the others do. `_finding_json`'s `below_floor` is documented as this
    predicate's exact complement and keeps its own `<` deliberately: it must read a
    confidence it has ALREADY evaluated once, and passing the finding here would score
    the record a second time.
    """
    return finding.confidence >= confidence_floor


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
        if clears_floor(finding, confidence_floor):
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


@dataclass(frozen=True)
class Baseline:
    """A prior `scan --json` document, reduced to the three facts a target gate reads.

    `present` is every gap id whose baseline verdict was PRESENT, at ANY confidence:
    the baseline's `below_floor` flags and `confidence_floor` are deliberately not
    read. A finding the prior scan already displayed is CARRIED whatever the floor
    said about it then, because the question this object answers is "was it there?",
    not "did it clear a floor?" -- the floor is applied exactly once, to the CURRENT
    scan, by `new_since_baseline`, so raising the floor between two scans cannot turn
    an old finding into a "new" one. `spelling` is the path as the caller typed it,
    echoed into the document for the reason `ScanResult.requested_spelling` is: a
    resolved path makes the document reproducible only on the machine that wrote it.
    """

    spelling: str
    target_name: str
    present: frozenset[str]


class BaselineError(Exception):
    """Raised when a `--baseline` argument is not a scan document this gate can read."""


class _BaselineFinding(BaseModel):
    """The two keys of a published finding the baseline reads.

    `extra="ignore"` (never `forbid`) on both models: the payload's keys are APPENDED
    over time, and a gate holding last release's baseline must still read a document
    this release wrote. Anything less than these two keys is not a finding at all.
    """

    model_config = ConfigDict(extra="ignore")

    gap_id: str
    verdict: str


class _BaselineDocument(BaseModel):
    """As much of the shape `scan_json` publishes as `load_baseline` needs to trust."""

    model_config = ConfigDict(extra="ignore")

    target_name: str
    findings: list[_BaselineFinding]


def load_baseline(spelling: str) -> Baseline:
    """Read a prior `scan --json` document, or refuse in one of two sentences.

    Both refusals name the path AS TYPED, because that is the token the caller can fix.
    `not a file` covers a missing path and a directory alike; `not a scan document`
    covers everything a readable file can be that is not the payload `scan_json`
    writes -- not JSON, not an object, no `target_name` or `findings`, a finding
    without `gap_id` and `verdict`, or an object that repeats a key. The last goes
    through `registry.parse_record` rather than `json.loads` on purpose: Python keeps
    the LAST of two identical keys and raises nothing, so a `findings` array pasted
    twice into a committed baseline would hand this gate whichever copy came second,
    silently. pydantic's `ValidationError` and a `UnicodeDecodeError` are both
    `ValueError`s, which is why the clause names no third class.

    WHY REFUSE RATHER THAN FALL BACK TO "NO BASELINE": a gate whose baseline could not
    be read and that then reported 0 would publish a clean gate it never earned -- the
    fail-open direction `gate_verdict`'s `None` exists to stop. Refusing the OTHER way,
    to the flagless verdict, would red a build over a typo in a path, which teaches a
    consumer to drop the flag. Exit 2 with the path named is the only answer that
    sends the caller to the actual defect.
    """
    path = pathlib.Path(spelling)
    if not path.is_file():
        raise BaselineError(f"not a file: {spelling}")
    try:
        parsed = _BaselineDocument.model_validate(
            parse_record(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RegistryError) as exc:
        raise BaselineError(f"not a scan document: {spelling}") from exc
    present = frozenset(f.gap_id for f in parsed.findings
                        if f.verdict == Verdict.PRESENT.value)
    return Baseline(spelling=spelling, target_name=parsed.target_name,
                    present=present)


def new_since_baseline(result: ScanResult, confidence_floor: int,
                       baseline_present: frozenset[str]) -> tuple[str, ...]:
    """The above-floor PRESENT gap ids of `result` the baseline did not carry, ascending.

    THE non-regression predicate for a TARGET, kept beside `gate_verdict` because it
    answers the other half of the gate rule `docs/CONSUMER_CONTRACT.md` binds a consumer
    to. `gate_verdict` asks "is anything above-floor PRESENT here?" and reddens a target
    with a backlog forever, until the whole backlog is fixed or the floor is raised until
    it is vacuous; this asks "is anything above-floor PRESENT here that was NOT PRESENT
    last time?", so a team can adopt the gate today and pay the backlog down under it.
    `diff --exit-code` answers non-regression for the REGISTER and refuses a scan payload
    outright, so before this a target had no non-regression surface at all.

    The exit code is this tuple's truthiness. It returns the IDS rather than a bool
    because the document names them: a bool here plus a second walk for the names would
    be two predicates that agree only while nobody edits one of them.

    The floor is applied ONCE, to the CURRENT scan, through `clears_floor` -- the same
    comparison `select_for_prd` and the exit code already make -- and never to the
    baseline (see `Baseline.present`). Three shapes are therefore NOT new, on purpose: a
    gap PRESENT both times (carried), a gap PRESENT then and fixed now (a fix is never
    bad news), and a gap below the floor now (a research task, exactly as `gate_verdict`
    treats it). A gap ABSENT or unverdicted then and PRESENT now IS new: that is the
    regression this predicate exists to catch. Nothing here filters the DOCUMENT -- every
    finding is still displayed -- so the register's protected rule is untouched.

    Ordered by id rather than by priority so the document's list reads the same for two
    scans that happen to rank the same new gaps differently.
    """
    return tuple(sorted(
        f.gap.id for f in result.by_verdict(Verdict.PRESENT)
        if clears_floor(f, confidence_floor) and f.gap.id not in baseline_present))


def render_baseline_line(baseline: Baseline, new_ids: tuple[str, ...]) -> str:
    """The ONE line `--baseline` adds to the markdown document.

    Spelled here, beside the predicate that produced `new_ids`, so `render_scan`
    inserts a string and never re-derives a count the exit code was decided from.
    `carried` is the baseline's WHOLE PRESENT set, floor included, because that is
    the set the gate compared against; the literal `none` stands in for an empty id
    list so the line keeps one shape whatever the verdict.
    """
    return (f"Baseline: {baseline.spelling} -- carried PRESENT: "
            f"{len(baseline.present)}; new above-floor PRESENT: {len(new_ids)} "
            f"({', '.join(new_ids) or 'none'})")


#: The verdicts that ANSWER a gate's question about a target. Named positively and
#: kept beside `unanswered()` so the partition is stated once: PRESENT says the
#: signature is there, ABSENT says a mitigation was positively found, and
#: NOT_APPLICABLE says the gap cannot apply here -- three different answers, all of
#: them answers. `MANUAL` and `UNKNOWN` are the complement by construction, so a
#: sixth verdict added to `checks.Verdict` lands OUTSIDE this set and is treated as
#: unanswered until someone argues otherwise, which is the safe default for a set
#: whose members are allowed to gate a release.
AUTOMATED_VERDICTS = frozenset(
    {Verdict.PRESENT, Verdict.ABSENT, Verdict.NOT_APPLICABLE})


def unanswered(result: ScanResult) -> list[Gap]:
    """Every applied record this scan reached no automated verdict for, in scan order.

    TOTAL over the record domain, which is the whole point: a record either produced
    a finding whose verdict is in `AUTOMATED_VERDICTS`, or it is unanswered -- because
    its check ran and honestly could not decide (`MANUAL`), because the check could not
    run or its search was cut (`UNKNOWN`), or because the record declares no check at
    all and never became a `Finding` (`uncheckable`). All three are the same fact to a
    consumer asking for a verdict code: nothing was decided about this record.

    WHY a caller needs it even though `gate_verdict` is already three-valued: that
    function's `None` is derived from `records_applied == 0`, and `records_applied`
    counts BOTH halves of the partition above. Over the whole register the two rarely
    coincide, but over a domain narrowed to ONE record the denominator is 1 even when
    that record's check could not decide -- so `gate_verdict` returns `False`, and
    `False` is published as "this target has no above-floor PRESENT gap". That is a
    fail-open: the reassuring reading of an absence of information, which is the exact
    failure the `None` case was introduced to stop.

    Returns the RECORDS, not a bool and not a message: the caller names them in its own
    published `Error: ` line, so this module holds no consumer-facing wording. Empty
    list means every applied record was answered, which is the common case over a
    whole-register scan of a real target.
    """
    return ([f.gap for f in result.findings
             if f.verdict not in AUTOMATED_VERDICTS]
            + list(result.uncheckable))


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
    locators, notes = _split_locations(finding.outcome.locations)
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
        # Every element is a `path:line` locator: this is the one array a
        # gate turns into file annotations, so the prose the checks write
        # beside the locators goes to `location_notes` instead.
        "locations": locators,
        "build_hypothesis": finding.gap.build_hypothesis,
        # APPENDED on purpose: the declared consumer's traceability gate
        # asserts a cited gap "is open", and until now that clause was
        # unanswerable from this payload. Passed straight through from the
        # record -- publishing is not selecting, so nothing here filters on it.
        "status": finding.gap.status,
        # APPENDED last, after `status`, so every earlier key keeps its index.
        # The `(+N more matches)` remainder and the `(no match) searched ...`
        # witness, in the order the check wrote them: MOVED here, never dropped,
        # because a cut remainder or an absence with no matched line is part of
        # the evidence and hiding it would overstate what the search covered.
        "location_notes": notes,
    }


def _split_locations(entries: list[str]) -> tuple[list[str], list[str]]:
    """Partition a check's location list into locators and prose, order kept.

    Decided by the producer's TYPE, not by the string's shape: `checks` tags
    every prose entry it writes as a `LocationNote`, so this function never
    re-parses a string another module wrote and cannot drift from it. Both
    halves are plain `str` so the payload carries no subclass of its own.
    """
    locators = [str(e) for e in entries if not isinstance(e, LocationNote)]
    notes = [str(e) for e in entries if isinstance(e, LocationNote)]
    return locators, notes


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


def render_scan(result: ScanResult, baseline_line: str | None = None) -> str:
    """Markdown scan report.

    The one-newline tail and the table formatting are `render.document` and
    `render.table`, not copies of them: an invariant with two implementations
    holds only while the copies happen to agree.

    `baseline_line` is the string `render_baseline_line` built, or `None`, which is
    what every flagless caller passes: the document then carries exactly the bytes it
    always has. Taken as a rendered line rather than as a `Baseline` so this renderer
    holds no second copy of the gate's arithmetic.
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
    if baseline_line is not None:
        # DIRECTLY under the census pair, because it is a third count of the same
        # kind -- what the gate compared and what it found new -- and a reader who
        # takes the exit code without this line cannot tell a carried backlog from
        # a clean target.
        lines.append(baseline_line)
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
