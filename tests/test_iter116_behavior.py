"""Iteration 116 -- the release gate now DEFAULTS to the domain it is gating.

Black-box, and deliberately firewalled from the implementation: nothing below reads
`tools/check_public_safety.py` as source, the engineer's notes, or any diff. The module is
driven only through its published interface -- `main`, `tracked_files`, `shippable_files`,
`RULES` -- plus the two published seams (`list_fn`, `read_fn`), exit codes and streams.
That is the discipline `tests/test_iter91_behavior.py` established for this tool and
`tests/test_iter114_behavior.py` continued.

The spec's claim under test, in one sentence: iteration 114 built `shippable_files()` (index
plus untracked, minus gitignored) but deliberately left `main()`'s default at the git INDEX,
so the shipped command line certified a tree clean while a leaky UNTRACKED file sat outside
the set it scanned -- and the one file class this loop always adds, the iteration's own new
`tests/test_iterNN_behavior.py`, is untracked while every stage runs. Bite 2 rewires the
default, and it must carry a coupled fix: `git ls-files` QUOTES a non-ASCII path
(`core.quotePath` defaults to true), so a widened default enumerated the old way hands back
a name that resolves to no file and turns a clean pass into an exit-2 refusal.

**No banned token appears as a literal here.** Every positive sample is COMPOSED at call
time from a `RULES` member's own `silent_on` marker plus one name character, so this module
is clean under the very gate it exercises -- and it has to be, because it is itself inside
the domain the gate now scans by default (behavior 6 asserts exactly that).

**Every temp work tree is created under the pytest tmp base and is MODULE-SCOPED**, because
the spec's own cost note says these 9 behaviors may not afford a `git init` per test. Three
fixtures, each built once: a domain tree, an accented tree, and an empty tree (`git init`
only, no commit). The product repo is never mutated; no global git config is read or
written (identity is passed per command with `-c`), and no network or credential command is
ever run.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO = pathlib.Path(__file__).resolve().parents[1]
SELF_REL = "tests/" + pathlib.Path(__file__).name

sys.path.insert(0, str(REPO / "tools"))

import check_public_safety as cps  # noqa: E402

BY_NAME = {r.name: r for r in cps.RULES}
PATH_RULE_NAME = "macos-account-home"
EMAIL_RULE_NAME = "email-address"

#: The noun this iteration publishes, and the noun it retires. Neither is spelled anywhere
#: else in this module, so a future rename has exactly one place to break.
NEW_NOUN = "shippable file(s)"
OLD_NOUN = "tracked file(s)"

#: git identity supplied per command so nothing reads or writes a global git config, and no
#: credential or authentication command is ever run. The address is the email rule's own
#: negative sample, read from the rule rather than typed.
FIXTURE_IDENTITY = (
    "-c",
    "user.email=" + BY_NAME[EMAIL_RULE_NAME].silent_on,
    "-c",
    "user.name=fixture",
)

#: `  <path>:<line>  <rule>  <excerpt>` -- the shape the gate prints per finding.
_FINDING_LINE = re.compile(r"^\s+(?P<path>\S+):(?P<line>\d+)\s")

#: A name whose bytes git would C-quote: `chr(0xe9)` is one accented character, never typed
#: as a literal escape, and `caf` + it is the canonical example the spec names.
ACCENT = chr(0xE9)
ACCENTED_COMMITTED = "caf" + ACCENT + "-committed.md"
ACCENTED_NEWBORN = "caf" + ACCENT + "-newborn.md"

#: The escape a C-quoted UTF-8 accented byte would show as. Built from its parts so this
#: module never types the escape it forbids in the tool's output.
QUOTE_ESCAPE = "\\" + "303"


# ---------------------------------------------------------------------------
# helpers -- samples composed, never typed
# ---------------------------------------------------------------------------


def _leak_sample(rule_name: str = PATH_RULE_NAME) -> str:
    """A banned token built at call time: a rule's own marker plus one name character.

    The marker alone is exempt (it is the rule's `silent_on` sample); appending a single
    name character is what turns it into the thing the rule fires on. Composed, never
    typed, so this file stays clean under the gate that now scans it by default.
    """
    return BY_NAME[rule_name].silent_on + "a\n"


def _run_main(argv, list_fn=None, read_fn=None):
    """Call `main()` with the argv it would get from the shell, capturing both streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cps.main(list(argv), list_fn=list_fn, read_fn=read_fn)
    return code, out.getvalue(), err.getvalue()


def _summary(n_files: int, n_findings: int) -> str:
    """The exact published summary line the spec pins, terminated by ONE newline."""
    return (
        f"{n_files} {NEW_NOUN} scanned against {len(cps.RULES)} rule(s): "
        f"{n_findings} finding(s)\n"
    )


def _summary_line(stdout: str) -> str:
    """The one summary line, located by content rather than by position.

    Found by predicate on purpose: a finding run prints findings above it and a rule legend
    below it, so `splitlines()[0]` or `[-1]` would silently read the wrong line.
    """
    lines = [line for line in stdout.splitlines() if NEW_NOUN + " scanned" in line]
    assert len(lines) == 1, f"expected exactly one summary line, got stdout={stdout!r}"
    return lines[0] + "\n"


def _offenders(stdout: str) -> list[str]:
    """Repo-relative paths the gate reported, for a failure message that names them."""
    return sorted({m.group("path") for m in map(_FINDING_LINE.match, stdout.splitlines()) if m})


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def _init(tmp_path_factory, slug: str) -> pathlib.Path:
    """A fresh work tree with `core.quotePath` PINNED ON.

    Pinned deliberately: the coupled defect this bite fixes only exists while git quotes
    non-ASCII paths, and that is git's default -- but a developer whose global config sets
    `core.quotePath=false` would make behaviors 4 and 5 vacuous on their machine. Setting it
    locally makes the hazard present for everyone, and it is a WRITE to a throwaway repo's
    own config, never to a global one.
    """
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    root = tmp_path_factory.mktemp(slug)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    _git(root, "config", "core.quotePath", "true")
    return root


def _commit(root: pathlib.Path) -> None:
    _git(root, "add", "-A")
    _git(root, *FIXTURE_IDENTITY, "commit", "-q", "-m", "fixture")


@pytest.fixture(scope="module")
def domain_repo(tmp_path_factory) -> pathlib.Path:
    """ONE tree holding all three path classes the default domain must separate.

      `committed.md`     -- in the index, so both domains hold it
      `.gitignore`       -- in the index, naming `scratch/`
      `newborn.md`       -- present, untracked, NOT ignored: the class bite 2 adds.
                            Its CONTENT is rewritten by each test that uses it, so the
                            leaky and clean arms are order-independent.
      `scratch/leak.md`  -- untracked AND ignored, and permanently LEAKY: the control that
                            makes behavior 2's exit 0 mean something.
    """
    root = _init(tmp_path_factory, "gate-domain")
    (root / "committed.md").write_text("clean line\n", encoding="utf-8")
    (root / ".gitignore").write_text("scratch/\n", encoding="utf-8")
    _commit(root)
    # created AFTER the commit, so the index cannot possibly hold either of them
    (root / "newborn.md").write_text("clean line\n", encoding="utf-8")
    (root / "scratch").mkdir()
    (root / "scratch" / "leak.md").write_text(_leak_sample(), encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def accented_repo(tmp_path_factory) -> pathlib.Path:
    """ONE tree whose committed set AND untracked set each hold a non-ASCII name."""
    root = _init(tmp_path_factory, "gate-accented")
    (root / ACCENTED_COMMITTED).write_text("clean line\n", encoding="utf-8")
    (root / "plain.md").write_text("clean line\n", encoding="utf-8")
    _commit(root)
    (root / ACCENTED_NEWBORN).write_text("clean line\n", encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def empty_repo(tmp_path_factory) -> pathlib.Path:
    """`git init` and nothing else: no commits, no files. One subprocess, no commit."""
    return _init(tmp_path_factory, "gate-empty")


def _non_ignored_count(root: pathlib.Path) -> int:
    """Every file under `root` that git does not ignore, counted WITHOUT the tool."""
    listed = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return len([p for p in listed.stdout.split("\0") if p])


# ===========================================================================
# B1  The default domain covers the untracked file: no seams, real git, and the
#     leak lives in a file the OLD default (the index) could not see.
# ===========================================================================


def test_b1_the_default_domain_covers_the_untracked_file(domain_repo: pathlib.Path):
    (domain_repo / "newborn.md").write_text(_leak_sample(), encoding="utf-8")

    # Control: the file really is outside the index, so the index-only default provably
    # could not have reported it. Without this, a green below would prove nothing.
    assert "newborn.md" not in cps.tracked_files(domain_repo), (
        "fixture is wrong: the leaky file must be UNTRACKED for this claim to bite"
    )

    code, out, err = _run_main(["x", str(domain_repo)])
    assert code == 1, (
        "the DEFAULT invocation must fail on a leak in an untracked file -- at the "
        f"pre-bite default this returned 0 with no offender. Got {code}, stdout={out!r} "
        f"stderr={err!r}"
    )
    assert err == "", f"a finding is the document, not an error; stderr={err!r}"
    assert "newborn.md" in _offenders(out), (
        f"stdout must name the untracked offender; offenders={_offenders(out)} stdout={out!r}"
    )
    named = [line for line in out.splitlines() if _FINDING_LINE.match(line)]
    assert any(PATH_RULE_NAME in line for line in named), (
        f"the finding must name the rule that fired; finding lines={named!r}"
    )


# ===========================================================================
# B2  ...and the default domain still OMITS the gitignored set -- proved with a
#     leaky ignored file present, so exit 0 is a real exclusion, not luck.
# ===========================================================================


def test_b2_the_default_domain_still_omits_the_gitignored_set(domain_repo: pathlib.Path):
    (domain_repo / "newborn.md").write_text("clean line\n", encoding="utf-8")

    # Control: the ignored file is on disk AND leaky, so if it were scanned this would red.
    leaky = domain_repo / "scratch" / "leak.md"
    assert leaky.exists(), "control: the ignored leak must really be on disk"
    assert leaky.read_text(encoding="utf-8") == _leak_sample(), (
        "control: the ignored file must hold content a committed rule fires on"
    )

    code, out, err = _run_main(["x", str(domain_repo)])
    assert code == 0, (
        "a gitignored leak must not fail the publish gate: git is told never to publish it. "
        f"Got {code}, offenders={_offenders(out)}, stdout={out!r} stderr={err!r}"
    )
    assert err == ""
    assert _offenders(out) == [], f"no offender may be named; stdout={out!r}"
    assert out == _summary(_non_ignored_count(domain_repo), 0), (
        "the summary count must equal the number of NON-IGNORED files, counted "
        f"independently of the tool; got {out!r}"
    )


# ===========================================================================
# B3  The default domain IS the shippable domain -- on the product repo, and
#     NON-VACUOUSLY on a tree where the two domains differ in size.
# ===========================================================================


def test_b3_the_default_count_on_the_product_repo_is_the_shippable_count():
    shippable = cps.shippable_files(REPO)
    code, out, err = _run_main(["x", str(REPO)])
    assert code == 0, f"the product tree must be clean; stdout={out!r} stderr={err!r}"
    assert _summary_line(out) == _summary(len(shippable), 0), (
        "main()'s default summary count must equal len(shippable_files(REPO)); got "
        f"{out!r} against a domain of {len(shippable)}"
    )


def test_b3_and_it_is_not_vacuous_the_count_exceeds_the_index(domain_repo: pathlib.Path):
    """The half the product repo cannot carry.

    On a clean product tree the index and the shippable set are EQUAL, so the assertion
    above is satisfied by an index-only default and proves nothing about the flip. This
    fixture has a real untracked file, so its default count SEPARATES the two readings.
    """
    (domain_repo / "newborn.md").write_text("clean line\n", encoding="utf-8")
    index = cps.tracked_files(domain_repo)
    shippable = cps.shippable_files(domain_repo)
    assert len(shippable) > len(index), f"fixture is wrong: {index!r} vs {shippable!r}"

    code, out, err = _run_main(["x", str(domain_repo)])
    assert code == 0, f"the fixture tree is clean here; stdout={out!r} stderr={err!r}"
    assert out == _summary(len(shippable), 0), (
        f"the default run must report the WIDER count {len(shippable)}; an index-only "
        f"default would have said {len(index)}. Got {out!r}"
    )


# ===========================================================================
# B4  Both listers return paths that EXIST -- with the git-quoting hazard proved
#     present on the fixture, so the claim is not an accident of the alphabet.
# ===========================================================================


def test_b4_the_quoting_hazard_is_really_present_on_the_accented_fixture(
    accented_repo: pathlib.Path,
):
    """The control for B4/B5: the OLD spelling of the git call really does hand back a name
    that names no file. Without this, `-z` could be absent and B4 would still pass."""
    raw = _git(accented_repo, "ls-files").stdout.splitlines()
    quoted = [p for p in raw if p.startswith('"')]
    assert quoted, (
        "control failed: `git ls-files` did not quote the accented path, so this fixture "
        f"cannot exercise the coupled defect. Got {raw!r}"
    )
    assert not (accented_repo / quoted[0]).exists(), (
        f"control failed: the quoted spelling {quoted[0]!r} unexpectedly names a real file"
    )


@pytest.mark.parametrize("lister", ["tracked_files", "shippable_files"])
def test_b4_both_listers_return_paths_that_exist(
    lister: str, accented_repo: pathlib.Path
):
    fn = getattr(cps, lister)
    for label, root in (("product repo", REPO), ("accented fixture", accented_repo)):
        result = fn(root)
        assert result, f"{lister}({label}) is empty, so this claim would be vacuous"
        missing = [p for p in result if not (root / p).exists()]
        assert not missing, (
            f"{lister} on the {label} returned path(s) that name no file: {missing[:5]}. "
            "A gate whose enumeration cannot round-trip through Path.read_text is not a gate"
        )
        malformed = [
            p for p in result if p.startswith('"') or p.endswith('"') or "\\" in p
        ]
        assert not malformed, (
            f"{lister} on the {label} returned git-QUOTED element(s) {malformed[:5]}; the "
            "two domains must agree on one raw path alphabet"
        )
    # the accented names are really in the domains, so the loop above was not empty of them
    if lister == "tracked_files":
        assert ACCENTED_COMMITTED in fn(accented_repo)
    else:
        assert {ACCENTED_COMMITTED, ACCENTED_NEWBORN} <= set(fn(accented_repo)), (
            f"the shippable domain must hold both accented names; got {fn(accented_repo)!r}"
        )


# ===========================================================================
# B5  A non-ASCII path is SCANNED, not refused -- two-sided, and exit 2 never
#     occurs in either arm.
# ===========================================================================


def test_b5_a_non_ascii_path_is_scanned_not_refused(accented_repo: pathlib.Path):
    newborn = accented_repo / ACCENTED_NEWBORN

    # Clean arm: the accented files are scanned and counted.
    newborn.write_text("clean line\n", encoding="utf-8")
    code, out, err = _run_main(["x", str(accented_repo)])
    assert code == 0, (
        "an accented filename must be SCANNED, not refused -- the pre-bite widening "
        f"returned exit 2 here. Got {code}, stdout={out!r} stderr={err!r}"
    )
    assert err == ""
    assert out == _summary(_non_ignored_count(accented_repo), 0), (
        f"the count must include both accented paths; got {out!r}"
    )

    # Leaky arm: the offender is named RAW.
    newborn.write_text(_leak_sample(), encoding="utf-8")
    code, out, err = _run_main(["x", str(accented_repo)])
    assert code != 2, f"exit 2 must not occur in either arm; stderr={err!r}"
    assert code == 1, f"a leak in the accented file must fail the gate; stdout={out!r}"
    assert err == ""
    assert ACCENTED_NEWBORN in _offenders(out), (
        f"the accented offender must be named raw; offenders={_offenders(out)!r}"
    )
    assert QUOTE_ESCAPE not in out, (
        f"no C-quote escape may appear anywhere in stdout; got {out!r}"
    )

    newborn.write_text("clean line\n", encoding="utf-8")


# ===========================================================================
# B6  The published summary line moves its noun WITH its count, from one
#     builder -- and the retired noun survives on none of the three surfaces.
# ===========================================================================


def test_b6_the_default_run_publishes_exactly_the_new_summary_line():
    shippable = cps.shippable_files(REPO)
    assert SELF_REL in shippable, (
        f"the domain does not contain {SELF_REL}, so the gate the loop runs still cannot "
        "see the file under review -- the exact fail-open this bite closes"
    )
    code, out, err = _run_main(["x", str(REPO)])
    assert code == 0, (
        "the DEFAULT invocation (no seams) must clear the tree this iteration would "
        f"publish, including its own untracked test file. Offenders={_offenders(out)}, "
        f"stdout={out!r} stderr={err!r}"
    )
    assert err == "", f"a clean scan writes nothing to stderr; got {err!r}"
    assert out == _summary(len(shippable), 0), (
        f"stdout must be exactly the one published summary line; got {out!r}"
    )
    assert out.endswith("\n") and not out.endswith("\n\n"), (
        f"the renderer must end in exactly ONE newline; got {out!r}"
    )


def test_b6_the_retired_noun_appears_on_none_of_the_three_surfaces(
    domain_repo: pathlib.Path, empty_repo: pathlib.Path
):
    def boom():
        raise OSError("cannot list")

    surfaces = {
        "summary line": _run_main(["x", str(domain_repo)]),
        "empty-domain refusal": _run_main(["x", str(empty_repo)]),
        "list-failure refusal": _run_main(["x", str(REPO)], list_fn=boom),
    }
    for label, (code, out, err) in surfaces.items():
        assert OLD_NOUN not in out, f"{label}: retired noun on stdout {out!r}"
        assert OLD_NOUN not in err, f"{label}: retired noun on stderr {err!r}"
    # not vacuous: each surface really was reached, and each really says the NEW noun
    assert NEW_NOUN in surfaces["summary line"][1]
    assert surfaces["empty-domain refusal"][0] == 2
    assert NEW_NOUN in surfaces["empty-domain refusal"][2], (
        f"the empty-domain refusal must use the new noun; got {surfaces['empty-domain refusal'][2]!r}"
    )
    assert surfaces["list-failure refusal"][0] == 2
    assert NEW_NOUN in surfaces["list-failure refusal"][2], (
        f"the list-failure refusal must use the new noun; got {surfaces['list-failure refusal'][2]!r}"
    )


# ===========================================================================
# B7  The empty-domain refusal keeps exit 2, in the new noun, byte for byte.
# ===========================================================================


def test_b7_the_empty_domain_refusal_keeps_exit_2_in_the_new_noun(
    empty_repo: pathlib.Path
):
    assert cps.shippable_files(empty_repo) == [], (
        f"fixture is wrong: the empty repo has a domain {cps.shippable_files(empty_repo)!r}"
    )
    code, out, err = _run_main(["x", str(empty_repo)])
    assert code == 2, f"a scan of nothing must refuse with exit 2; got {code}, err={err!r}"
    assert out == "", f"stdout must carry only the document; got {out!r}"
    assert err == (
        f"Error: 0 {NEW_NOUN} under {empty_repo} -- a scan of nothing is not a clean scan\n"
    ), f"the refusal must be byte-exact in the new noun; got {err!r}"


# ===========================================================================
# B8  Two established refusals/seams are NOT reversed.
# ===========================================================================


def test_b8a_the_seams_still_win_over_the_new_default():
    code, out, err = _run_main(
        ["x", str(REPO)], list_fn=lambda: ["only.md"], read_fn=lambda rel: "clean line\n"
    )
    assert code == 0, f"a seam-passing caller must be unaffected; stderr={err!r}"
    assert err == ""
    assert out == _summary(1, 0), (
        "the substituted 1-file domain must still report 1: the seams win over the "
        f"default, and the count tracks the domain actually scanned. Got {out!r}"
    )


def test_b8b_a_directory_that_is_not_a_work_tree_is_still_the_exit_2_refusal(
    tmp_path: pathlib.Path
):
    outside = tmp_path / "not-a-work-tree"
    outside.mkdir()
    (outside / "a.md").write_text("clean line\n", encoding="utf-8")
    assert not (outside / ".git").exists(), "control: this must not be a work tree"

    code, out, err = _run_main(["x", str(outside)])
    assert code == 2, (
        f"the DEFAULT invocation must keep the exit-2 refusal here; got {code}, out={out!r}"
    )
    assert out == "", f"stdout must carry only the document; got {out!r}"
    lines = [line for line in err.splitlines() if line.strip()]
    assert lines, f"an exit-2 refusal must write to stderr; got {err!r}"
    assert lines[-1].startswith("Error: "), (
        f"the last non-empty stderr line must be prefixed 'Error: '; got {err!r}"
    )


# ===========================================================================
# B9  `tracked_files` still means the INDEX -- so `tests/_document_index.py`'s
#     committed-only domain did not silently widen with `main`'s.
# ===========================================================================


def test_b9_tracked_files_still_means_the_index():
    listed = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    oracle = {p for p in listed.split("\0") if p}
    assert oracle, "control: the product repo's index must not be empty"
    assert set(cps.tracked_files(REPO)) == oracle, (
        "tracked_files must still be exactly the git index. Extra: "
        f"{sorted(set(cps.tracked_files(REPO)) - oracle)[:5]}, missing: "
        f"{sorted(oracle - set(cps.tracked_files(REPO)))[:5]}"
    )
    # and it is NOT the same function as the widened one on a tree where they differ
    assert set(cps.tracked_files(REPO)) <= set(cps.shippable_files(REPO))
