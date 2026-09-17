"""Iteration 253 -- the no-network door bans BARE roots over a domain wider than one file.

ISOLATION: black-box.  No implementation source was read to write this module -- not
`tools/check_offline.py`, not the diff, not the engineer's or reviewer's notes.  Every
expectation comes from the spec's Expected Behaviors, from the roadmap's iter-253 ledger
row, from the conventions of `tests/test_roadmap_integrity.py` (which is the CLI shape the
spec says to mirror) and from RUNNING the tool.  The tool's source is touched here only by
an AST walk and by character counts, which are measurements, never a reading.

WHY THIS MODULE EXISTS.  The repo's one static enforcement of the VISION out-of-scope
clause "Network access in the tool or its tests" banned the DOTTED element
`"http.client"` while comparing it against a FIRST dotted component, so no `http` import
could ever match it: `import http.client` read CLEAN.  `test_b1_a_dotted_element_could_
never_fire...` is that false negative kept as a regression fixture -- it replays the old
first-component comparison and the new door on the same three inputs and shows the old one
silent where the new one fires.

TWO-SIDED, per the repo's fixture doctrine: absence of a finding is evidence only when the
same function is shown to produce one.  Both violation kinds are proved RED on a scratch
copy of the domain and GREEN again with the defect removed, and every mutation asserts its
own premise, so a silently no-op edit cannot pass as a known-bad fixture.

MEASURED DISCREPANCY, and why no integer is pinned here.  The spec's behavior 4 and its
first header line say the domain is "exactly 18 entries ... 7 under `tools/`".  The tree
says **19 = 11 + 8**: the new checker is itself a member of the set it scans, so the spec
priced the pre-change tree and is off by exactly one -- the reconciliation the iter-253
ledger row in `PRODUCT.md` states.  This module therefore derives the counts from an
INDEPENDENT glob of the two directories rather than freezing 18 or 19 into an assertion:
iteration 245's mistake was a pin that is a function of this repo's own file census, which
reds a test about a checker the next time somebody adds a script.  The structural claim is
pinned instead (the domain IS those two globs in that order, and nothing from `tests/`),
and that claim is what a wrong domain breaks.

Offline, deterministic, no network: the only child processes are four runs of the tool
itself, and the real `src/` is READ, never written -- `test_b6_...` hashes the whole live
domain before and after the scratch-tree mutation to prove it.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL_REL = "tools/check_offline.py"
TOOL = REPO / TOOL_REL

sys.path.insert(0, str(REPO / "tools"))

import check_offline as co  # noqa: E402

PACKAGE_PREFIX = "src/agent_gap_radar/"
SCRIPTS_PREFIX = "tools/"

#: The spec's vocabulary, spelled out here so the assertion is against the SPEC and not
#: against whatever the module happens to hold.
SPEC_VOCABULARY = (
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

#: The defect the domain half exists to catch: a lazy function-body import, the house
#: style the spec quotes (`cli.py`'s `THE SEAM` block).
LAZY_IMPORT = "\n\ndef _late() -> None:\n    import http.client\n"

ALLOWLISTED_REL = "tools/verify_quotes.py"


# ---------------------------------------------------------------------------
# helpers -- an INDEPENDENT re-derivation of the spec's domain, never the tool's
# ---------------------------------------------------------------------------


def _expected_domain() -> tuple[str, ...]:
    """`sorted(src/agent_gap_radar/*.py)` then `sorted(tools/*.py)`, repo-relative POSIX."""
    package = sorted(p.name for p in (REPO / "src" / "agent_gap_radar").glob("*.py"))
    scripts = sorted(p.name for p in (REPO / "tools").glob("*.py"))
    return tuple([PACKAGE_PREFIX + n for n in package] + [SCRIPTS_PREFIX + n for n in scripts])


def _first_components(source: str) -> set[str]:
    """The OLD, defective comparison: the first dotted component of every import name."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def _build_scratch(root: pathlib.Path) -> pathlib.Path:
    """A copy of the domain -- and only the domain -- under `root`."""
    (root / "src" / "agent_gap_radar").mkdir(parents=True)
    (root / "tools").mkdir(parents=True)
    for rel in _expected_domain():
        shutil.copy2(REPO / rel, root / rel)
    return root


def _live_domain_digest() -> str:
    """One digest over every live domain file, path and bytes, so a write cannot hide."""
    digest = hashlib.sha256()
    for rel in _expected_domain():
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update((REPO / rel).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _strip_network_imports(path: pathlib.Path) -> int:
    """Delete every import line that names a vocabulary root.  Returns lines removed."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [
        line
        for line in lines
        if not (line.lstrip().startswith(("import ", "from ")) and co.network_roots_in(line.strip()))
    ]
    path.write_text("".join(kept), encoding="utf-8")
    return len(lines) - len(kept)


def _run(args: list[str], cwd: pathlib.Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the tool itself, no shell, no network
        [sys.executable, str(TOOL), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _last_nonempty(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines, f"no non-empty line in {text!r}"
    return lines[-1]


# ---------------------------------------------------------------------------
# behaviour 1 -- the vocabulary is reachable BY CONSTRUCTION
# ---------------------------------------------------------------------------


def test_b1_the_vocabulary_is_the_spec_tuple_of_bare_roots_in_order() -> None:
    """Behaviour 1: a `tuple[str, ...]`, the spec's nine roots, in the spec's order."""
    assert isinstance(co.NETWORK_ROOTS, tuple), f"not a tuple: {type(co.NETWORK_ROOTS)!r}"
    assert all(isinstance(root, str) for root in co.NETWORK_ROOTS)
    assert co.NETWORK_ROOTS == SPEC_VOCABULARY


def test_b1_no_vocabulary_element_contains_a_dot() -> None:
    """Behaviour 1: a dotted element can never equal a first dotted component."""
    dotted = [root for root in co.NETWORK_ROOTS if "." in root]
    assert dotted == [], f"dotted element(s) can never fire: {dotted}"


@pytest.mark.parametrize("root", SPEC_VOCABULARY)
def test_b1_every_vocabulary_element_can_actually_fire(root: str) -> None:
    """Behaviour 1: reachability is per-element, bare AND under a submodule."""
    assert co.network_roots_in(f"import {root}") == (root,)
    assert co.network_roots_in(f"import {root}.sub") == (root,)
    assert co.network_roots_in(f"from {root}.sub import thing") == (root,)


def test_b1_a_dotted_element_could_never_fire_which_is_the_regression_fixture() -> None:
    """Behaviour 1, the false negative kept as a fixture: old door silent, new door red.

    The banned element was `"http.client"` compared against `alias.name.split(".")[0]`.
    On the same three inputs the old comparison never sees `http.client` and always sees
    the bare root, so the old ban was unreachable while the new one fires.
    """
    doors = (
        "import http.client",
        "import http.server",
        "from http.client import HTTPConnection",
    )
    for source in doors:
        firsts = _first_components(source)
        assert "http.client" not in firsts, f"premise broken for {source!r}: {sorted(firsts)}"
        assert "http" in firsts, f"premise broken for {source!r}: {sorted(firsts)}"
        assert "http.client" not in co.NETWORK_ROOTS
        assert co.network_roots_in(source) == ("http",), f"new door missed {source!r}"


# ---------------------------------------------------------------------------
# behaviour 2 -- detection is root-EXACT at any nesting depth
# ---------------------------------------------------------------------------

SPEC_CASES = (
    ("import http.client", ("http",)),
    ("import http.server", ("http",)),
    ("from http.client import HTTPConnection", ("http",)),
    ("def f():\n    import http.client\n", ("http",)),
    ("class C:\n    def m(self):\n        from urllib import request\n", ("urllib",)),
    ("import socket, ssl", ("socket", "ssl")),
    ("import urllib.request as u", ("urllib",)),
    ("import httpcore", ()),
    ("import json\nimport pathlib\n", ()),
)


@pytest.mark.parametrize(("source", "expected"), SPEC_CASES)
def test_b2_the_spec_input_table_holds_exactly(source: str, expected: tuple[str, ...]) -> None:
    """Behaviour 2: the spec's nine inputs return the spec's nine values, exactly."""
    assert co.network_roots_in(source) == expected


def test_b2_the_result_is_sorted_and_distinct() -> None:
    """Behaviour 2: 'sorted distinct members' -- a repeat collapses, order is not source order."""
    source = "import ssl\nimport socket\nimport ssl\nfrom urllib import parse\n"
    assert co.network_roots_in(source) == ("socket", "ssl", "urllib")


def test_b2_root_exactness_cuts_both_ways() -> None:
    """Behaviour 2: a longer name that merely STARTS with a root is not a hit; a submodule is."""
    assert co.network_roots_in("import httpcore") == ()
    assert co.network_roots_in("import socketio") == ()
    assert co.network_roots_in("from httpcore import x") == ()
    assert co.network_roots_in("import httpx.foo") == ("httpx",)
    assert co.network_roots_in("from socketserver import TCPServer") == ("socketserver",)


def test_b2_depth_beyond_the_specs_two_levels_is_still_seen() -> None:
    """Behaviour 2: 'any nesting depth' -- a try body inside a with inside a method."""
    source = (
        "class C:\n"
        "    def m(self) -> None:\n"
        "        with open('x') as fh:\n"
        "            try:\n"
        "                import http.client\n"
        "            except ImportError:\n"
        "                from requests import Session\n"
    )
    assert co.network_roots_in(source) == ("http", "requests")


def test_b2_an_import_only_named_in_prose_is_not_an_import() -> None:
    """Behaviour 2: the door reads the AST, so a mention cannot make a file dirty."""
    source = '"""This module deliberately avoids import socket and urllib.request."""\nX = "import ssl"\n'
    assert co.network_roots_in(source) == ()


# ---------------------------------------------------------------------------
# behaviour 3 -- an unparseable source REFUSES
# ---------------------------------------------------------------------------


def test_b3_an_unparseable_source_raises_instead_of_reading_clean() -> None:
    """Behaviour 3: `SyntaxError`, never `()` -- a broken file must not read as offline."""
    with pytest.raises(SyntaxError):
        co.network_roots_in("def (")


# ---------------------------------------------------------------------------
# behaviour 4 -- the domain is the tool plus the maintainer scripts, never tests/
# ---------------------------------------------------------------------------


def test_b4_the_domain_is_the_two_globs_in_the_spec_order() -> None:
    """Behaviour 4: package files sorted, then scripts sorted, repo-relative POSIX."""
    assert co.domain_files(REPO) == _expected_domain()


def test_b4_the_domain_split_is_the_measured_census_not_a_frozen_integer() -> None:
    """Behaviour 4: the counts are a FUNCTION of the two directories.

    The spec says 18 / 11 / 7; the tree says 19 / 11 / 8 because the checker is a member
    of the set it scans.  Derived, so a future script does not red this module.
    """
    domain = co.domain_files(REPO)
    package = [rel for rel in domain if rel.startswith(PACKAGE_PREFIX)]
    scripts = [rel for rel in domain if rel.startswith(SCRIPTS_PREFIX)]
    assert len(package) == len(list((REPO / "src" / "agent_gap_radar").glob("*.py")))
    assert len(scripts) == len(list((REPO / "tools").glob("*.py")))
    assert len(package) + len(scripts) == len(domain)
    assert package == sorted(package)
    assert scripts == sorted(scripts)


def test_b4_no_domain_entry_comes_from_tests_and_every_entry_is_relative() -> None:
    """Behaviour 4: `tests/` is out of scope, and no entry is an absolute machine path."""
    domain = co.domain_files(REPO)
    assert [rel for rel in domain if rel.startswith("tests/")] == []
    for rel in domain:
        assert not rel.startswith("/"), f"absolute path in domain: {rel!r}"
        assert "\\" not in rel, f"non-POSIX separator: {rel!r}"
        assert (REPO / rel).is_file(), f"domain names a non-file: {rel!r}"


def test_b4_the_checker_scans_itself() -> None:
    """Behaviour 4: `tools/check_offline.py` is one of the domain files."""
    assert TOOL_REL in co.domain_files(REPO)


# ---------------------------------------------------------------------------
# behaviour 5 -- one exemption, two kinds, and the live tree clean
# ---------------------------------------------------------------------------


def test_b5_the_allowlist_is_exactly_one_named_file() -> None:
    """Behaviour 5: one exemption, spelled repo-relative."""
    assert co.ALLOWLIST == (ALLOWLISTED_REL,)


def test_b5_the_live_tree_is_clean_which_is_the_brake_this_iteration_ships() -> None:
    """Behaviour 5: `violations(REPO) == ()`.

    This is the acceptance criterion's brake: a future lazy `import http.client` anywhere
    under `src/agent_gap_radar/` or `tools/` reds `uv run pytest` here.
    """
    assert co.violations(REPO) == ()


def test_b5_a_violation_record_exposes_path_kind_and_sorted_roots(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviour 5: the record shape, proved on a record the checker actually produced."""
    assert set(co.VIOLATION_KINDS) == {"network-import", "dead-allowlist-entry"}
    scratch = _build_scratch(tmp_path / "tree")
    target = scratch / "src" / "agent_gap_radar" / "render.py"
    target.write_text(target.read_text(encoding="utf-8") + LAZY_IMPORT, encoding="utf-8")
    (record,) = co.violations(scratch)
    assert record.path == "src/agent_gap_radar/render.py"
    assert record.kind in co.VIOLATION_KINDS
    assert isinstance(record.roots, tuple)
    assert list(record.roots) == sorted(record.roots)


# ---------------------------------------------------------------------------
# behaviour 6 -- network-import proved TWO-SIDED on a scratch tree
# ---------------------------------------------------------------------------


def test_b6_a_lazy_network_import_is_red_and_its_removal_is_green(tmp_path: pathlib.Path) -> None:
    """Behaviour 6: red with the defect, green without, on a copy of the real domain."""
    before = _live_domain_digest()
    scratch = _build_scratch(tmp_path / "tree")
    assert co.violations(scratch) == (), "premise broken: the scratch copy is not clean"

    target = scratch / "src" / "agent_gap_radar" / "render.py"
    pristine = target.read_text(encoding="utf-8")
    target.write_text(pristine + LAZY_IMPORT, encoding="utf-8")
    assert target.read_text(encoding="utf-8") != pristine, "premise broken: mutation was a no-op"

    found = co.violations(scratch)
    assert len(found) == 1, f"expected exactly one record, got {found!r}"
    (record,) = found
    assert record.kind == "network-import"
    assert record.path == "src/agent_gap_radar/render.py"
    assert record.roots == ("http",)

    target.write_text(pristine, encoding="utf-8")
    assert co.violations(scratch) == ()

    assert _live_domain_digest() == before, "the real domain was written to"


# ---------------------------------------------------------------------------
# behaviour 7 -- dead-allowlist-entry proved RED on a scratch tree
# ---------------------------------------------------------------------------


def test_b7_an_exemption_that_no_longer_needs_it_is_a_violation(tmp_path: pathlib.Path) -> None:
    """Behaviour 7: a dead allowlist entry fails for the same reason a dead ban does."""
    scratch = _build_scratch(tmp_path / "tree")
    exempt = scratch / ALLOWLISTED_REL
    removed = _strip_network_imports(exempt)
    assert removed == 3, f"premise: the exempt script's three network imports, removed {removed}"
    assert co.network_roots_in(exempt.read_text(encoding="utf-8")) == ()

    found = co.violations(scratch)
    assert len(found) == 1, f"expected exactly one record, got {found!r}"
    (record,) = found
    assert record.kind == "dead-allowlist-entry"
    assert record.path == ALLOWLISTED_REL
    assert record.roots == ()


def test_b7_an_exemption_absent_from_the_domain_is_the_same_violation(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviour 7, the other half of 'absent from the domain, or imports no member'."""
    scratch = _build_scratch(tmp_path / "tree")
    (scratch / ALLOWLISTED_REL).unlink()
    found = co.violations(scratch)
    assert len(found) == 1, f"expected exactly one record, got {found!r}"
    (record,) = found
    assert record.kind == "dead-allowlist-entry"
    assert record.path == ALLOWLISTED_REL
    assert record.roots == ()


# ---------------------------------------------------------------------------
# behaviour 8 -- the CLI contract
# ---------------------------------------------------------------------------


def test_b8_a_clean_run_exits_zero_with_the_specs_header_and_one_newline() -> None:
    """Behaviour 8: exit 0, empty stderr, one trailing newline, the three header lines."""
    domain = co.domain_files(REPO)
    package = [rel for rel in domain if rel.startswith(PACKAGE_PREFIX)]
    scripts = [rel for rel in domain if rel.startswith(SCRIPTS_PREFIX)]

    first = _run([])
    assert first.returncode == 0, f"stderr={first.stderr!r}"
    assert first.stderr == ""
    assert first.stdout.endswith("\n")
    assert not first.stdout.endswith("\n\n")

    lines = first.stdout.splitlines()
    assert lines[0] == (
        f"  domain: {len(domain)} file(s) -- {len(package)} under {PACKAGE_PREFIX}, "
        f"{len(scripts)} under {SCRIPTS_PREFIX}"
    )
    assert lines[1] == f"  allowlisted: {len(co.ALLOWLIST)} file(s) -- {ALLOWLISTED_REL}"
    assert lines[2] == "  vocabulary: " + ", ".join(SPEC_VOCABULARY)
    assert _last_nonempty(first.stdout) == "0 violation(s)"


def test_b8_two_consecutive_clean_runs_are_byte_identical() -> None:
    """Behaviour 8: deterministic output, the quality bar's byte-stability rule."""
    first = _run([])
    second = _run([])
    assert first.stdout == second.stdout
    assert first.returncode == second.returncode == 0


def test_b8_a_violating_tree_exits_one_and_names_the_file_and_root(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviour 8: exit 1, the VIOLATION line verbatim, and the count last."""
    scratch = _build_scratch(tmp_path / "tree")
    target = scratch / "src" / "agent_gap_radar" / "render.py"
    target.write_text(target.read_text(encoding="utf-8") + LAZY_IMPORT, encoding="utf-8")

    result = _run([str(scratch)])
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert (
        "  VIOLATION  network-import  src/agent_gap_radar/render.py imports http"
        in result.stdout.splitlines()
    )
    assert _last_nonempty(result.stdout) == "1 violation(s)"
    assert result.stdout.endswith("\n")
    assert not result.stdout.endswith("\n\n")


def test_b8_a_repo_root_that_is_not_a_directory_exits_two_on_stderr_alone() -> None:
    """Behaviour 8: bad usage -- exit 2, stdout empty, one `Error: ` line on stderr."""
    result = _run(["PRODUCT.md"])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout == ""
    assert result.stderr.startswith("Error: ")
    assert result.stderr.endswith("\n")
    assert result.stderr.count("\n") == 1


def test_b8_the_default_repo_root_is_the_parent_of_tools() -> None:
    """Behaviour 8: `argv[1]` is optional and defaults to the parent of `tools/`."""
    assert pathlib.Path(co.default_repo()).resolve() == REPO


# ---------------------------------------------------------------------------
# behaviour 9 -- the new tool is itself offline and self-contained
# ---------------------------------------------------------------------------


def _tool_import_roots() -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(TOOL.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_b9_the_tool_imports_only_the_standard_library() -> None:
    """Behaviour 9: no new dependency can enter through the checker."""
    roots = _tool_import_roots() - {"__future__"}
    outside = sorted(root for root in roots if root not in sys.stdlib_module_names)
    assert outside == [], f"non-stdlib import(s): {outside}"


def test_b9_the_tool_imports_no_vocabulary_root_and_no_shell_or_product_module() -> None:
    """Behaviour 9: the door does not walk through itself, and shells out to nothing."""
    roots = _tool_import_roots()
    assert roots & set(co.NETWORK_ROOTS) == set()
    assert "subprocess" not in roots
    assert "agent_gap_radar" not in roots


def test_b9_the_tool_carries_no_absolute_machine_path() -> None:
    """Behaviour 9, the PUBLIC REPO rule: the repo root is found from `__file__`."""
    text = TOOL.read_text(encoding="utf-8")
    assert "/Users/" not in text
    assert "/home/" not in text


# ---------------------------------------------------------------------------
# EXTENSION (tester-retry round of this same iteration).  The first round of this
# stage was cut short by the per-stage cap with the nine behaviours covered but
# four spec claims never exercised:
#   * behaviour 1's "the UNION of the roots the repo's five existing copies already
#     name" -- an arithmetic claim about committed files, asserted by nobody;
#   * behaviour 5's "checked in BOTH directions" -- only the DEAD direction was
#     proved; that the exemption actually SUPPRESSES a live import was not;
#   * behaviours 5-8 with MORE THAN ONE violation, i.e. the plural count line and
#     the record order that byte-stable stdout depends on;
#   * behaviour 2 on a RELATIVE import, an input the spec's nine-case table omits.
# ---------------------------------------------------------------------------

#: The five hand-copied vocabularies the spec says `NETWORK_ROOTS` is the union of,
#: quoted VERBATIM from the committed modules so this claim carries its own locator --
#: the register's own citation rule, applied to a test.  `tests/` is inside the
#: isolation contract, so these are quotations, not a reading of the implementation.
EXISTING_DOORS: tuple[tuple[str, str], ...] = (
    (
        "tests/test_iter207_behavior.py",
        '    forbidden = ("socket", "urllib", "http.client", "requests", "httpx", "ftplib")',
    ),
    (
        "tests/test_iter206_behavior.py",
        '    forbidden = {"socket", "urllib", "http", "requests", "httpx", "ssl", "ftplib", "smtplib"}',
    ),
    (
        "tests/test_iter72_behavior.py",
        'NETWORK_ROOTS = {"urllib", "http", "requests", "httpx", "ftplib", "socketserver", "ssl"}',
    ),
    (
        "tests/test_iter85_behavior.py",
        'NETWORK_ROOTS = {"urllib", "http", "requests", "httpx", "ssl", "socketserver", "ftplib"}',
    ),
    (
        "tests/test_iter87_behavior.py",
        '    banned = {"socket", "http.client", "urllib.request", "ssl", "requests", "httpx"}',
    ),
)


def test_b1_the_vocabulary_is_exactly_the_union_of_the_five_committed_doors() -> None:
    """Behaviour 1: the vocabulary is DERIVED from the repo, not invented here.

    Two-sided by construction: each citation must still appear verbatim in its file, so
    a door that was reworded cannot silently drop out of the union and shrink the claim.
    """
    union: set[str] = set()
    for rel, quote in EXISTING_DOORS:
        text = (REPO / rel).read_text(encoding="utf-8")
        assert quote in text, f"stale citation -- not found in {rel}: {quote!r}"
        union |= {name.split(".")[0] for name in re.findall(r'"([A-Za-z0-9_.]+)"', quote)}
    assert tuple(sorted(union)) == co.NETWORK_ROOTS, (
        "the vocabulary is no longer the union of the five committed doors: "
        f"union={tuple(sorted(union))} tool={co.NETWORK_ROOTS}"
    )


def test_b2_a_relative_import_cannot_fire_because_no_domain_module_is_named_for_a_root() -> None:
    """Behaviour 2, the one input the spec's table omits, kept as a TRIPWIRE.

    `from . import http` is `()` under every reading (a bare relative import carries no
    module name).  `from .http import x` is the OPEN case: it names an intra-package
    sibling, not the stdlib root, and all five committed doors above would read it as
    `http` too, so the new door is CONSISTENT with the repo rather than a regression --
    but the reading is only harmless while no domain module is NAMED for a vocabulary
    root.  Measured today: the domain's 33 relative imports name only `checks`, `diff`,
    `models`, `prd`, `registry`, `render`, `scan`, `scoring`, `taxonomy` -- zero
    collisions.  Adding `src/agent_gap_radar/http.py` would make the reading
    load-bearing, and this test reds THEN, which is when the ambiguity needs deciding.
    """
    assert co.network_roots_in("from . import http") == ()
    stems = {rel.rsplit("/", 1)[-1].removesuffix(".py") for rel in co.domain_files(REPO)}
    collisions = sorted(stems & set(co.NETWORK_ROOTS))
    assert collisions == [], (
        "a domain module named for a vocabulary root makes the relative-import reading "
        f"load-bearing -- decide it before shipping: {collisions}"
    )


def test_b3_every_unparseable_shape_refuses_rather_than_reading_clean() -> None:
    """Behaviour 3: refusal is a property of unparseability, not of one magic string."""
    for broken in ("def (", "import (", "class:\n", "from import x", "def f(:\n    pass\n"):
        with pytest.raises(SyntaxError):
            co.network_roots_in(broken)


def test_b5_the_exemption_suppresses_a_live_import_rather_than_finding_none(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviour 5, the direction the first round left unproved.

    A clean tree proves nothing about an allowlist unless the allowlisted file really
    does import a banned root: otherwise the exemption could be dead code and the tree
    would look identical.  So assert the premise, then the suppression.
    """
    scratch = _build_scratch(tmp_path / "tree")
    exempt_roots = co.network_roots_in((scratch / ALLOWLISTED_REL).read_text(encoding="utf-8"))
    assert exempt_roots != (), "premise broken: the exempt script imports no vocabulary root"
    assert set(exempt_roots) <= set(co.NETWORK_ROOTS)
    assert co.violations(scratch) == (), (
        f"the allowlist failed to suppress {exempt_roots} in {ALLOWLISTED_REL}"
    )


def test_b5_both_kinds_fire_together_and_the_record_order_is_deterministic(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviours 5-7 with TWO violations: both kinds coexist and repeat identically.

    Determinism is asserted, ordering policy is not: byte-stable stdout requires only
    that two calls agree, and the spec fixes no sort key.
    """
    scratch = _build_scratch(tmp_path / "tree")
    target = scratch / "src" / "agent_gap_radar" / "render.py"
    target.write_text(target.read_text(encoding="utf-8") + LAZY_IMPORT, encoding="utf-8")
    removed = _strip_network_imports(scratch / ALLOWLISTED_REL)
    assert removed == 3, f"premise: three network imports to remove, removed {removed}"

    found = co.violations(scratch)
    assert len(found) == 2, f"expected both kinds, got {found!r}"
    assert {(record.kind, record.path, record.roots) for record in found} == {
        ("network-import", "src/agent_gap_radar/render.py", ("http",)),
        ("dead-allowlist-entry", ALLOWLISTED_REL, ()),
    }
    assert co.violations(scratch) == found, "two calls disagreed, so stdout cannot be byte-stable"


def test_b8_two_violations_report_the_plural_count_and_keep_stderr_empty(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviour 8: a FINDING is the document on stdout, never an error on stderr.

    The quality bar reserves stderr and exit 2 for errors; a violation is the tool
    working, so exit 1 with an empty stderr and the count last.
    """
    scratch = _build_scratch(tmp_path / "tree")
    target = scratch / "src" / "agent_gap_radar" / "render.py"
    target.write_text(target.read_text(encoding="utf-8") + LAZY_IMPORT, encoding="utf-8")
    assert _strip_network_imports(scratch / ALLOWLISTED_REL) == 3

    result = _run([str(scratch)])
    assert result.returncode == 1, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    assert not result.stdout.endswith("\n\n")
    assert _last_nonempty(result.stdout) == "2 violation(s)"
    reported = [line for line in result.stdout.splitlines() if "VIOLATION" in line]
    assert len(reported) == 2, reported
    assert any(
        "network-import" in line and "src/agent_gap_radar/render.py" in line for line in reported
    ), reported
    assert any(
        "dead-allowlist-entry" in line and ALLOWLISTED_REL in line for line in reported
    ), reported


def test_b8_a_repo_root_that_does_not_exist_is_the_same_usage_error(
    tmp_path: pathlib.Path,
) -> None:
    """Behaviour 8: 'not a directory' covers absent as well as not-a-directory."""
    result = _run([str(tmp_path / "no-such-tree")])
    assert result.returncode == 2, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout == ""
    assert result.stderr.startswith("Error: ")
    assert result.stderr.endswith("\n")
    assert result.stderr.count("\n") == 1


def test_b8_the_clean_report_names_no_absolute_machine_path() -> None:
    """Behaviour 9's PUBLIC REPO rule, applied to the OUTPUT and not only the source."""
    stdout = _run([]).stdout
    assert "/Users/" not in stdout
    assert "/home/" not in stdout
    assert str(REPO) not in stdout
