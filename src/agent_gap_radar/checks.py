"""Declarative, offline rule evaluation for gap checks.

Design constraints that are not negotiable:

* Rules are DATA, not code. A gap record is JSON in git; letting it carry
  executable code would make the register a remote-execution surface.
* A rule that matches must report WHERE. A finding with no location is not
  actionable, and an unactionable finding trains people to ignore the tool.
* Absence of a bad pattern is NEVER evidence of safety. That is the fail-open
  detector, and it is worse than no detector at all, because it reports health.
  Only positive evidence of a mitigation may produce ABSENT.
"""

from __future__ import annotations

import enum
import pathlib
import re
import subprocess
from dataclasses import dataclass, field

MAX_FILE_BYTES = 512 * 1024
SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".mypy_cache", ".ruff_cache", ".tox", "target",
})


class Verdict(str, enum.Enum):
    """Deliberately five-valued. Collapsing these is how tools start lying."""

    PRESENT = "PRESENT"                # the gap's signature was found
    ABSENT = "ABSENT"                  # a mitigation was POSITIVELY found
    NOT_APPLICABLE = "NOT_APPLICABLE"  # the gap cannot apply to this target
    MANUAL = "MANUAL"                  # undecidable statically; ask the question
    UNKNOWN = "UNKNOWN"                # the check could not be run


@dataclass
class RuleHit:
    matched: bool
    locations: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.matched


@dataclass
class CheckOutcome:
    verdict: Verdict
    locations: list[str] = field(default_factory=list)
    question: str = ""
    reason: str = ""


_TRACKED_CACHE: dict[pathlib.Path, frozenset[pathlib.Path] | None] = {}


def tracked_files(target: pathlib.Path) -> frozenset[pathlib.Path] | None:
    """The files the target actually SHIPS, via `git ls-files`, or None.

    Judging a project by its gitignored scratch is judging the wrong artifact.
    A loop's per-iteration state, a virtualenv and a build dir are not the
    project's code, and findings located inside them are noise that trains a
    reader to distrust the tool. `git ls-files` is the authoritative answer to
    "what is this project", so it is preferred over any hand-maintained skip
    list; the skip list remains the fallback for a non-git target.

    Local subprocess only - this keeps the offline contract (no network).
    """
    key = target.resolve()
    if key in _TRACKED_CACHE:
        return _TRACKED_CACHE[key]
    result: frozenset[pathlib.Path] | None = None
    try:
        proc = subprocess.run(
            ["git", "-C", str(key), "ls-files", "-z"],
            capture_output=True, timeout=30)
        if proc.returncode == 0:
            names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
            result = frozenset((key / n) for n in names)
            if not result:
                result = None  # empty repo: fall back rather than match nothing
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        result = None
    _TRACKED_CACHE[key] = result
    return result


def iter_files(target: pathlib.Path, globs: list[str]) -> list[pathlib.Path]:
    """Resolve globs under target, restricted to what the project ships."""
    tracked = tracked_files(target)
    seen: set[pathlib.Path] = set()
    for pattern in globs:
        for path in target.glob(pattern):
            if not path.is_file():
                continue
            if tracked is not None:
                if path.resolve() not in tracked:
                    continue
            elif any(part in SKIP_DIRS for part in path.relative_to(target).parts):
                continue
            seen.add(path)
    return sorted(seen)


def _read(path: pathlib.Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _scope_note(globs: list[str], pattern: str | None = None) -> str:
    """Describe an ABSENCE in actionable terms: what was searched, and for what.

    An absent pattern has no file:line, so returning an empty location list makes
    the finding unactionable. Naming the searched scope lets a reader disagree
    with the check instead of merely distrusting it.
    """
    scope = ", ".join(globs[:4])
    if pattern:
        return f"(no match) searched {scope} for /{pattern}/"
    return f"(no files) searched {scope}"


def evaluate(rule: dict, target: pathlib.Path) -> RuleHit:
    """Evaluate one rule against a target directory.

    An unknown rule kind raises: silently returning False would be the
    fail-open failure this module exists to prevent.
    """
    kind = rule.get("kind")

    if kind == "any_of":
        locations: list[str] = []
        matched = False
        for sub in rule.get("rules", []):
            hit = evaluate(sub, target)
            if hit.matched:
                matched = True
                locations.extend(hit.locations)
        return RuleHit(matched, locations)

    if kind == "all_of":
        subs = rule.get("rules", [])
        if not subs:
            raise ValueError("all_of with no sub-rules is vacuously true; forbidden")
        locations = []
        for sub in subs:
            hit = evaluate(sub, target)
            if not hit.matched:
                return RuleHit(False, [])
            locations.extend(hit.locations)
        return RuleHit(True, locations)

    if kind == "not":
        inner = rule.get("rule")
        if inner is None:
            raise ValueError("not requires a 'rule'")
        return RuleHit(not evaluate(inner, target).matched, [])

    if kind in ("file_exists", "file_absent"):
        files = iter_files(target, rule["globs"])
        found = bool(files)
        if kind == "file_exists":
            return RuleHit(found, [str(p.relative_to(target)) for p in files[:10]])
        # An absence has no line to point at, but it does have a searched scope.
        # Naming that scope is what makes the finding actionable.
        return RuleHit(not found, [_scope_note(rule["globs"])] if not found else [])

    if kind in ("content_matches", "content_absent"):
        try:
            regex = re.compile(rule["pattern"], re.MULTILINE)
        except re.error as exc:
            raise ValueError(f"invalid pattern {rule.get('pattern')!r}: {exc}") from exc
        locations = []
        for path in iter_files(target, rule["globs"]):
            text = _read(path)
            if text is None:
                continue
            for m in regex.finditer(text):
                line_no = text[:m.start()].count("\n") + 1
                locations.append(f"{path.relative_to(target)}:{line_no}")
                break
        found = bool(locations)
        if kind == "content_matches":
            return RuleHit(found, locations[:10])
        return RuleHit(not found,
                       [_scope_note(rule["globs"], rule["pattern"])] if not found else [])

    raise ValueError(f"unknown rule kind: {kind!r}")


def run_check(check: dict, target: pathlib.Path) -> CheckOutcome:
    """Decide one check against a target. Fail-CLOSED by construction.

    Order matters. `mitigated_when` is not allowed to override a positive
    `present_when` hit: a target exhibiting BOTH signatures is the genuinely
    dangerous case (a partial mitigation), so it escalates to MANUAL rather
    than being reported as safe.
    """
    applies = check.get("applies_when")
    if applies is not None:
        try:
            if not evaluate(applies, target):
                return CheckOutcome(Verdict.NOT_APPLICABLE,
                                    reason="applies_when did not match")
        except ValueError as exc:
            return CheckOutcome(Verdict.UNKNOWN, reason=f"applies_when: {exc}")

    question = check.get("manual_question", "")
    present_rule = check.get("present_when")
    mitigated_rule = check.get("mitigated_when")

    if present_rule is None and mitigated_rule is None:
        return CheckOutcome(Verdict.MANUAL, question=question,
                            reason="check is manual by declaration")

    try:
        present = evaluate(present_rule, target) if present_rule else RuleHit(False)
        mitigated = evaluate(mitigated_rule, target) if mitigated_rule else RuleHit(False)
    except ValueError as exc:
        return CheckOutcome(Verdict.UNKNOWN, reason=str(exc))

    if present.matched and mitigated.matched:
        return CheckOutcome(
            Verdict.MANUAL, locations=present.locations + mitigated.locations,
            question=question or
            "Both the gap signature and a mitigation were found. Confirm the "
            "mitigation actually covers the code path where the signature appears.",
            reason="ambiguous: both signatures present")

    if present.matched:
        return CheckOutcome(Verdict.PRESENT, locations=present.locations,
                            reason="gap signature found")

    if mitigated.matched:
        return CheckOutcome(Verdict.ABSENT, locations=mitigated.locations,
                            reason="mitigation positively identified")

    # Nothing found either way. This is NOT absence of the gap.
    return CheckOutcome(
        Verdict.MANUAL, question=question or
        "Neither the gap signature nor a mitigation was detected. Absence of a "
        "pattern is not evidence of safety - confirm by hand.",
        reason="no signature and no mitigation detected")
