#!/usr/bin/env python3
"""Refuse to ship a public-repo leak, over every tracked file rather than one document.

This repository is PUBLIC and the quality bar it ships under says so: no absolute machine
paths, no employer or personal identifiers. Nothing committed enforced that clause. Enforcement
was per-iteration and ad-hoc -- exactly 2 of 78 test files carry banned-token literals and both
are scoped to the one or two documents their own iteration edited, so 222 tracked files were
covered by a grep hand-rolled fresh each time. In iteration 90 that grep printed the word CLEAN
having opened no file: the shell's `grep` is ripgrep, it read `-E` as `--encoding`, and the
check's or-else fallback turned the tool's own error into a pass.

The domain is `git ls-files`, this product's settled answer to "which files are ours" (the same
domain six tracked test files already drive). Most of it -- 120 of 224 files -- is register data
written by an outside research pipeline from arbitrary primary sources, which is precisely the
path an account name or an address arrives on, and none of the five refusal gates
`docs/CONSUMER_CONTRACT.md` publishes is a public-safety gate.

FAIL CLOSED, on the two ways a scan can be vacuous rather than clean. A domain of zero files
returns 2, and a file this scan cannot decode returns 2 -- an unread file is not a cleared file.
That is this product's settled position after three earlier fail-opens, where `radar validate`
over zero records and `check_locators` over zero checked locators both used to report health.

THE RULE SET IS DATA, and it needs no exemption list and no self-exclusion. Every pattern
requires at least one name character AFTER its marker, and this file never places a name character
there. Each marker is held EXACTLY ONCE -- as `_MACOS_HOME`, `_POSIX_HOME` and `_MACOS_VOLUME`,
each a bare string literal terminated by that literal's closing quote, and a quote is not a member
of `_NAME_CHAR`. `_path_rule` then composes every pattern from that variable, so no marker literal
is ever adjacent to the character class. The invariant a future editor must preserve is therefore
one sentence: NEVER INLINE A MARKER LITERAL into a pattern, a sample or a sentence, because that is
the edit which would put a name character after a marker and red this gate on its own source. So
this module is a member of the domain it scans and reports zero, and so are the two test files that
assert a bare marker is absent from a document. Iteration 06 hit the other version of this live:
its self-scanning check failed on its own assertion line and had to be narrowed to two documents.

Each rule carries its own two-sided samples and `rule_defects` asserts them, so "these rules
work" is a pure function an offline suite can call rather than a claim in this docstring. `main`
runs it as a pre-flight and refuses to scan when it is non-empty, because a scanner whose rules
are broken still prints a clean report.

TWO CANDIDATE RULES WERE REJECTED ON MEASUREMENT, recorded here so nobody re-adds them.

* A windows drive path (drive letter, colon, backslash, name character) fires 467 times across
  108 tracked files on CORRECT data: gap records are JSON, and an escaped newline inside a
  verbatim code quote reads as exactly that shape.
* An ascii-purity rule would red the 7 tracked files that legitimately carry non-ascii verbatim
  quotes -- 6 gap records and `research/CANDIDATE_CONTRACT.md`. The verbatim-quote invariant
  outranks a character-set preference.

REAL NAMES AND EMPLOYER TOKENS ARE DELIBERATELY NOT CHECKED. A word list of the names a public
repository must not contain IS the leak it claims to prevent.

Usage:
    python3 tools/check_public_safety.py [repo_root]

Exit codes: 0 every tracked file is clean, 1 at least one finding, 2 the scan cannot be trusted
(bad usage, a rule that fails its own samples, an empty domain, or a file it could not read).
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: One character of an account, host or volume name. Requiring at least one of these AFTER a
#: marker is what lets this module scan itself: every marker below is held once as a bare string
#: literal ending in a closing quote, which is not a member of this class, and the patterns
#: compose the marker from that variable instead of inlining it beside this class.
_NAME_CHAR = r"[A-Za-z0-9._-]"

#: Markers, held ONCE each so a pattern and its samples cannot drift apart. Each is a BARE
#: marker, which is exactly the shape the rules deliberately do not report.
_MACOS_HOME = "/Users/"
_POSIX_HOME = "/home/"
_MACOS_VOLUME = "/Volumes/"

#: Composed into samples at run time so no banned shape is ever a literal in this file.
_AT = "@"

#: The local part needs two characters, and the reason is measured rather than aesthetic: 20 of
#: the 22 address-shaped matches on the live tree have a ONE-character local part, and every one
#: of them is the payload of a JSON newline escape inside a verbatim code quote -- the same
#: false-positive mechanism that disqualified the windows drive rule. The cost is stated rather
#: than hidden: an address whose local part is a single character is invisible to this rule.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")

#: RFC 2606 and RFC 6761 reserved names. An address at a reserved domain cannot identify a
#: person, so exempting the DOMAIN CLASS is a rule; exempting the files that happen to contain
#: one today would be an allowlist, and an allowlist stops covering the next file.
_RESERVED_DOMAIN = re.compile(
    r"@(?:[A-Za-z0-9-]+\.)*(?:example\.(?:com|net|org)|example|invalid|localhost|test)$"
)


@dataclass(frozen=True)
class Rule:
    """One public-safety rule, and the two samples that prove it works.

    `fires_on` and `silent_on` are part of the rule rather than part of a test, because the
    rule is DATA that a caller can extend: a new entry arrives with its own proof or
    `rule_defects` refuses the whole set. `silent_on` is the discriminating negative, not a
    decorative one -- for a path rule it is the BARE marker, which is the live case two tracked
    test files contain.
    """

    name: str
    pattern: re.Pattern[str]
    exempt: re.Pattern[str] | None
    fires_on: str
    silent_on: str
    why: str


@dataclass(frozen=True)
class Finding:
    """One non-exempt occurrence, located precisely enough to fix without a second search."""

    path: str
    line: int
    rule: str
    text: str


def _path_rule(name: str, marker: str, why: str) -> Rule:
    """An absolute path root that embeds an account or volume name.

    The marker is used once for the pattern and once for each sample, so an edit cannot leave
    the pattern and its proof disagreeing. The positive sample is composed at run time; the
    negative one IS the bare marker, which is why the two tracked test files that assert a bare
    marker is absent from a document do not become findings themselves.
    """
    return Rule(
        name=name,
        pattern=re.compile(re.escape(marker) + _NAME_CHAR),
        exempt=None,
        fires_on=marker + "account",
        silent_on=marker,
        why=why,
    )


#: The rule set. Four rules: three absolute path roots that carry an account or volume name
#: across the two operating systems this product's tooling runs on, and one personal-identifier
#: rule. Order is fixed because it orders the report.
RULES: tuple[Rule, ...] = (
    _path_rule(
        "macos-account-home",
        _MACOS_HOME,
        "an absolute macOS home path names the account that produced the file",
    ),
    _path_rule(
        "posix-account-home",
        _POSIX_HOME,
        "an absolute POSIX home path names the account that produced the file",
    ),
    _path_rule(
        "macos-mounted-volume",
        _MACOS_VOLUME,
        "a mounted volume path names a machine or a drive somebody chose the name of",
    ),
    Rule(
        name="email-address",
        pattern=_EMAIL,
        exempt=_RESERVED_DOMAIN,
        fires_on="person" + _AT + "mail-host.net",
        silent_on="fixture" + _AT + "example.invalid",
        why="an address identifies a person, and a register quote is the door one arrives through",
    ),
)

#: Lists the tracked file set as repo-relative paths. `main` takes one of these as a SEAM, so
#: every verdict below is reachable from a suite with no git repository to hand.
_ListFn = Callable[[], list[str]]

#: Reads one repo-relative path as text, raising `UnicodeDecodeError` or `OSError` when it
#: cannot. The second seam, for the same reason.
_ReadFn = Callable[[str], str]


def matches(rule: Rule, text: str) -> list[str]:
    """Every non-exempt occurrence of `rule` in `text`, in the order it finds them."""
    found: list[str] = []
    for hit in rule.pattern.finditer(text):
        occurrence = hit.group(0)
        if rule.exempt is not None and rule.exempt.search(occurrence):
            continue
        found.append(occurrence)
    return found


def rule_defects(rules: Sequence[Rule]) -> list[str]:
    """Name every rule that fails its own two samples, so a broken rule set cannot report clean.

    Pure, over DATA, and microseconds long, which is what makes the two-sidedness of the rule
    set assertable by an offline suite instead of argued for in a docstring. Both halves matter
    and the SILENT half is the load-bearing one: a rule that fires on everything passes the
    positive sample, and only the negative sample separates a discriminating rule from a
    permanently-red one.
    """
    defects: list[str] = []
    for rule in rules:
        if not matches(rule, rule.fires_on):
            defects.append(f"rule {rule.name} does not fire on its own positive sample")
        if matches(rule, rule.silent_on):
            defects.append(f"rule {rule.name} fires on its own negative sample")
    return defects


def findings(path: str, text: str, rules: Sequence[Rule] | None = None) -> list[Finding]:
    """Every finding in one file's text, ordered by line and then by rule order.

    Line-oriented so a report can name a line without a second pass, which is safe here
    because no rule can span a newline.
    """
    active = RULES if rules is None else rules
    found: list[Finding] = []
    for number, line in enumerate(text.split("\n"), 1):
        for rule in active:
            for occurrence in matches(rule, line):
                found.append(Finding(path, number, rule.name, occurrence))
    return found


def tracked_files(root: pathlib.Path) -> list[str]:
    """The tracked file set, as repo-relative paths.

    `git ls-files` rather than a directory walk, for the reason `radar scan` already settled: a
    walk sees build output, virtual environments and gitignored scratch, none of which is
    published, so a walk both wastes work and invents findings in files nobody can read.
    """
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "git ls-files failed")
    return [line for line in result.stdout.split("\n") if line]


def main(
    argv: list[str], list_fn: _ListFn | None = None, read_fn: _ReadFn | None = None
) -> int:
    """Scan every tracked file, and refuse rather than report health it did not establish.

    Three refusals, all returning 2, because each one is a clean report this tool would
    otherwise have printed over work it did not do:

    * a rule that fails its own samples -- the rule set is the whole check, so a broken one
      makes every subsequent silence meaningless;
    * a domain of zero files -- the vacuous success three earlier rows in this product already
      ruled against on other surfaces;
    * a file that cannot be read or decoded -- an unread file is not a cleared file, and the
      alternative (skip it and keep going) is how a scan reports CLEAN over a hole.

    The scanned count is printed next to the finding count for the same reason `check_locators`
    prints its denominator: a reader must not have to trust that "0 findings" came from a full
    pass rather than from an empty one.

    `list_fn` and `read_fn` are SEAMS resolved at CALL time and never bound as signature
    defaults. A default argument is evaluated once at definition, so `list_fn=tracked_files`
    would capture this module's function forever and silently ignore any later substitution --
    a failure that reads as a broken repository rather than as an unusable seam.
    """
    root = pathlib.Path(argv[1] if len(argv) > 1 else ".")
    if not root.is_dir():
        sys.stderr.write(f"Error: not a directory: {root}\n")
        return 2

    defects = rule_defects(RULES)
    if defects:
        for defect in defects:
            sys.stderr.write(f"Error: {defect}\n")
        return 2

    lister = list_fn or (lambda: tracked_files(root))
    reader = read_fn or (lambda relative: (root / relative).read_text(encoding="utf-8"))

    try:
        files = lister()
    except OSError as exc:
        sys.stderr.write(f"Error: cannot list the tracked files of {root}: {exc}\n")
        return 2

    if not files:
        sys.stderr.write(
            f"Error: 0 tracked file(s) under {root} -- a scan of nothing is not a clean scan\n"
        )
        return 2

    found: list[Finding] = []
    for relative in sorted(files):
        try:
            text = reader(relative)
        except UnicodeDecodeError:
            sys.stderr.write(
                f"Error: cannot decode {relative} as utf-8 -- a file this scan cannot read is "
                f"not a file it can clear\n"
            )
            return 2
        except OSError as exc:
            sys.stderr.write(f"Error: cannot read {relative}: {exc}\n")
            return 2
        found.extend(findings(relative, text))

    for finding in found:
        print(f"  {finding.path}:{finding.line}  {finding.rule}  {finding.text}")
    print(
        f"{len(files)} tracked file(s) scanned against {len(RULES)} rule(s): "
        f"{len(found)} finding(s)"
    )
    for rule in RULES:
        if any(finding.rule == rule.name for finding in found):
            print(f"  {rule.name}: {rule.why}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
