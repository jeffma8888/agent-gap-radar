#!/usr/bin/env python3
"""Refuse a network import in the tool or its maintainer scripts, over a REACHABLE vocabulary.

WHY THIS EXISTS AND WHY IT IS NOT A FIFTH COPY OF AN EXISTING CHECK. `VISION.md` puts
"Network access in the tool or its tests" out of scope and the quality bar repeats it, so the
clause is load-bearing. It was enforced by five hand-copied vocabularies in the test suite, and
the widest of them was FAIL-OPEN in a way no reader of the tuple could see: it banned
`"http.client"` while comparing against `alias.name.split(".")[0]`, i.e. against a FIRST dotted
component. A first component is never `"http.client"`, so that element could not fire, and
`import http.client`, `import http.server` and `from http.client import HTTPConnection` all
read CLEAN. Replaying that tuple through that comparison over those three lines plus
`import socket` and `import urllib.request` returns only `['socket', 'urllib.request']`.

That is the register's own core failure mode one layer up: a check reporting SAFETY with no
witness. The product's LEARNINGS already carry the operator's ruling on the same shape
(CHK-009 matched a mitigation inside a TEST file, so a target exhibiting the gap was reported
ABSENT) and the remedy there was the same as here: make the check able to FIND the thing it
claims to ban, and ship the false negative as a regression fixture. Behavior 1's assertion
that no element contains a `.` IS that fixture -- a dotted element can never equal a first
dotted component, so its presence is a silent fail-open by construction.

TWO INVARIANTS THIS FILE IS BUILT AROUND.

1. THE VOCABULARY IS REACHABLE BY CONSTRUCTION. Every element of `NETWORK_ROOTS` is a bare
   root, and detection compares roots to roots. Root-EXACT, never a prefix test: `httpcore`
   is a real offline package and a `startswith` rule would condemn it, which is the mirrored
   fail-CLOSED defect and just as expensive.

2. THE EXEMPTION IS CHECKED IN BOTH DIRECTIONS. An allowlist entry that names a file the
   domain does not hold, or a file that imports nothing this module bans, is itself a
   violation -- for exactly the reason a dead deny-list element is one. An exemption nobody
   can justify is an unaudited hole that outlives the reason it was granted.

DOMAIN, and what is deliberately outside it. `src/agent_gap_radar/*.py` plus `tools/*.py`, so
the ~2.9k lines of maintainer scripts that sat outside every existing census are covered and
this file is a member of the domain it scans. `tests/` is NOT in the domain and that is a
decision, not an oversight: several test modules import `socket` on purpose to monkeypatch it
into a tripwire, so banning it there needs a multi-entry allowlist and a separate argument.

DEPTH MATTERS MORE THAN IT LOOKS. The house style is the lazy function-body import, so a
module-level-only walk would miss the most likely way a socket arrives. The walk here is over
every node, so an import nested in a function, a class, a `try` or a conditional is seen.

Offline and self-contained by contract: standard library only, and it neither imports nor
needs the package it guards, so it still runs on a tree whose package does not import.

Usage:
    python3 tools/check_offline.py [REPO_ROOT]

Exit codes: 0 no violations, 1 at least one violation, 2 bad usage or a file that could not
be read or parsed -- an unread file is not a cleared file.
"""

from __future__ import annotations

import ast
import pathlib
import sys
from typing import NamedTuple

#: Every module root that reaches the network, as the UNION of the roots this repo's five
#: existing hand-copied vocabularies already name, sorted. Every element is a bare root with
#: NO `.` in it, and that is the invariant behavior 1 pins: detection compares against a first
#: dotted component, so a dotted element here could never fire and would be a silent
#: fail-open. Adding one is safe; adding a dotted one is the defect this file was written for.
NETWORK_ROOTS: tuple[str, ...] = (
    "ftplib",
    "http",
    "httpx",
    "requests",
    "smtplib",
    "socket",
    "socketserver",
    "ssl",
    "urllib",
)

#: The ONLY domain file allowed to reach the network, and the repo already documents why: it
#: verifies quotes against live pages, out of band, deliberately outside the suite. Held as a
#: tuple of repo-relative POSIX paths so an entry can be compared literally, and audited in
#: BOTH directions by `violations` -- see invariant 2 in the module docstring.
ALLOWLIST: tuple[str, ...] = ("tools/verify_quotes.py",)

#: The two halves of the domain, as repo-relative POSIX prefixes. Published because the
#: report's first line counts by them and a test should not re-spell them.
PACKAGE_PREFIX: str = "src/agent_gap_radar/"
SCRIPTS_PREFIX: str = "tools/"

#: The two -- and only two -- ways this check can fire. Published as data so a caller can
#: assert the set is closed rather than grep for the strings.
VIOLATION_KINDS: tuple[str, ...] = ("network-import", "dead-allowlist-entry")


class Violation(NamedTuple):
    """One finding: a repo-relative path, one of `VIOLATION_KINDS`, and the roots involved.

    Exactly three fields, in the order the spec names them, so a finding can be compared
    against a plain tuple in a test and still carry a human-readable line. `roots` is always
    sorted, and it is empty for a dead allowlist entry because there is nothing to name.
    """

    path: str
    kind: str
    roots: tuple[str, ...]

    @property
    def message(self) -> str:
        """One line, derived from the fields alone so the report cannot drift from the data.

        A dead allowlist entry has two causes -- the path is absent from the domain, or it is
        present and imports nothing banned -- and they collapse into ONE sentence on purpose:
        both mean the same thing about the exemption, which is that nothing justifies it.
        """
        if self.kind == "network-import":
            return f"{self.path} imports {', '.join(self.roots)}"
        return f"{self.path} is allowlisted but imports no network root, so the exemption is dead"


def network_roots_in(source: str) -> tuple[str, ...]:
    """The sorted, distinct `NETWORK_ROOTS` members `source` imports, at any nesting depth.

    Raises `SyntaxError` rather than returning `()` on source it cannot parse: an empty tuple
    is this module's word for CLEAN, and handing that word to an unreadable file is the
    fail-open shape the whole file exists to remove.

    Both import forms are covered because they are two spellings of one act:
    `import http.client` and `from http.client import HTTPConnection` reach the same socket.
    A relative `from . import x` carries no module name and is skipped -- it cannot name a
    third-party root. Only the FIRST dotted component is compared, and it is compared for
    EQUALITY, so `httpcore` is clean while `http.server` is not.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [] if node.module is None else [node.module]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root in NETWORK_ROOTS:
                found.add(root)
    return tuple(sorted(found))


def default_repo() -> pathlib.Path:
    """The checkout this file lives in: the parent of `tools/`, found from `__file__`.

    Derived, never written down. An absolute machine path in a PUBLIC repo is a quality-bar
    violation, and it would also make the tool unusable in any other checkout.
    """
    return pathlib.Path(__file__).resolve().parent.parent


def domain_files(repo: pathlib.Path) -> tuple[str, ...]:
    """Repo-relative POSIX paths of every file in the domain: the package, then the scripts.

    Two sorted halves rather than one sorted whole, so the report can count by prefix without
    re-globbing. `tests/` is absent by construction -- see the module docstring. Non-files are
    skipped so a directory named `x.py` cannot enter a domain of readable sources.
    """
    halves = (repo / PACKAGE_PREFIX, repo / SCRIPTS_PREFIX)
    return tuple(
        path.relative_to(repo).as_posix()
        for half in halves
        for path in sorted(half.glob("*.py"))
        if path.is_file()
    )


def violations(repo: pathlib.Path) -> tuple[Violation, ...]:
    """Every finding in `repo`, network imports in domain order then dead allowlist entries.

    Deterministic by construction: both passes walk an already-sorted sequence, so the tuple
    is byte-stable across runs. Propagates `SyntaxError` and `OSError` from the read/parse of
    a domain file, because a domain this function could not measure must not report clean.
    """
    domain = domain_files(repo)
    roots_by_path = {
        path: network_roots_in((repo / path).read_text(encoding="utf-8")) for path in domain
    }
    found = [
        Violation(path, "network-import", roots)
        for path, roots in roots_by_path.items()
        if roots and path not in ALLOWLIST
    ]
    found += [
        Violation(path, "dead-allowlist-entry", ())
        for path in ALLOWLIST
        if not roots_by_path.get(path)
    ]
    return tuple(found)


def report_lines(repo: pathlib.Path, findings: tuple[Violation, ...]) -> list[str]:
    """The document, header first, so `main` stays a sequence of writes and one exit code.

    Every count is DERIVED from the glob rather than written down. A hard-coded total is a
    second copy of the domain that decays the moment a file is added -- and this file's own
    arrival changes it, so a literal here would have been wrong on the commit that shipped it.
    """
    domain = domain_files(repo)
    package = [path for path in domain if path.startswith(PACKAGE_PREFIX)]
    scripts = [path for path in domain if path.startswith(SCRIPTS_PREFIX)]
    lines = [
        f"  domain: {len(domain)} file(s) -- {len(package)} under {PACKAGE_PREFIX}, "
        f"{len(scripts)} under {SCRIPTS_PREFIX}",
        f"  allowlisted: {len(ALLOWLIST)} file(s) -- {', '.join(ALLOWLIST)}",
        f"  vocabulary: {', '.join(NETWORK_ROOTS)}",
    ]
    lines += [f"  VIOLATION  {found.kind}  {found.message}" for found in findings]
    lines += ["", f"{len(findings)} violation(s)"]
    return lines


def main(argv: list[str]) -> int:
    """`python3 tools/check_offline.py [REPO_ROOT]`, mirroring `tools/roadmap_integrity.py`.

    Refusals go to stderr with the repo's published `Error: ` prefix and exit 2; stdout
    carries only the document. Exit 2 also covers a domain file that cannot be read or
    parsed, which is fail-CLOSED on the one case a checker must never call clean.
    """
    repo = pathlib.Path(argv[1]) if len(argv) > 1 else default_repo()
    if not repo.is_dir():
        sys.stderr.write(f"Error: not a directory: {repo}\n")
        return 2
    try:
        findings = violations(repo)
    except (OSError, SyntaxError) as exc:
        sys.stderr.write(f"Error: a domain file could not be read: {type(exc).__name__}: {exc}\n")
        return 2
    sys.stdout.write("\n".join(report_lines(repo, findings)) + "\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
