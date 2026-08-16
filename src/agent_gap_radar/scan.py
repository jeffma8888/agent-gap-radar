"""Apply the register's checks to a concrete target repository.

This is what turns the register from a reading list into an instrument: point it
at a service or an agent project and it reports which known gaps that specific
target exhibits, with file:line locations, plus the questions a human must
answer where static analysis honestly cannot decide.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from .checks import CheckOutcome, Verdict, run_check
from .models import Gap
from .scoring import confidence, priority


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

    def by_verdict(self, verdict: Verdict) -> list[Finding]:
        return [f for f in self.findings if f.verdict is verdict]

    @property
    def actionable(self) -> list[Finding]:
        """PRESENT findings, worst first. This is the work queue."""
        rows = self.by_verdict(Verdict.PRESENT)
        rows.sort(key=lambda f: (-f.priority, f.gap.id))
        return rows


def scan(gaps: list[Gap], target: pathlib.Path | str) -> ScanResult:
    target = pathlib.Path(target).expanduser().resolve()
    if not target.is_dir():
        raise NotADirectoryError(str(target))

    findings: list[Finding] = []
    uncheckable: list[Gap] = []

    for gap in sorted(gaps, key=lambda g: g.id):
        if gap.check is None:
            uncheckable.append(gap)
            continue
        outcome = run_check(gap.check.model_dump(exclude_none=True), target)
        findings.append(Finding(gap=gap, outcome=outcome))

    return ScanResult(target=target, findings=findings, uncheckable=uncheckable)


def render_scan(result: ScanResult) -> str:
    """Markdown scan report. Ends in exactly one newline."""
    lines = [f"# Gap scan: {result.target.name}", "",
             f"Target: `{result.target}`", ""]

    counts = {v: len(result.by_verdict(v)) for v in Verdict}
    lines += ["| Verdict | Count | Meaning |", "| --- | --- | --- |"]
    meaning = {
        Verdict.PRESENT: "gap signature found in this target",
        Verdict.ABSENT: "a mitigation was positively identified",
        Verdict.MANUAL: "static analysis cannot decide; a human must answer",
        Verdict.NOT_APPLICABLE: "this gap cannot apply to this target",
        Verdict.UNKNOWN: "the check could not be run",
    }
    for v in Verdict:
        lines.append(f"| {v.value} | {counts[v]} | {meaning[v]} |")
    lines += ["", f"Gaps with no check yet: {len(result.uncheckable)}", ""]

    lines += ["## Actionable now (PRESENT, worst first)", ""]
    if result.actionable:
        for f in result.actionable:
            lines += [f"### {f.gap.id} -- {f.gap.title}", "",
                      f"- Priority {f.priority:.1f}, evidence confidence {f.confidence}",
                      f"- Layer: `{f.gap.layer}` | type: `{f.gap.gap_type}`",
                      f"- Why this matters: {f.gap.problem}"]
            if f.outcome.locations:
                lines.append("- Found at:")
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
        lines += ["## Could not run (UNKNOWN)", ""]
        lines += [f"- **{f.gap.id}** {f.outcome.reason}" for f in unknown]
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"
