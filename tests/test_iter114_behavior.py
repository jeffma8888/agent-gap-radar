"""Iteration 114 -- the public-safety gate's domain must hold the file under review.

Black-box, and deliberately firewalled from the implementation: nothing below reads
`tools/check_public_safety.py` as source. The module is INTROSPECTED through its public
interface only -- `shippable_files`, `tracked_files`, `main`, `RULES` -- and every verdict
is taken from the tool's own two published seams (`list_fn`, `read_fn`) or from its exit
code and streams. That is the same discipline `tests/test_iter91_behavior.py` established
for this tool.

The spec's claim under test: the gate's domain was the git INDEX, so the one file class
every round adds (this very module, untracked while every stage runs) sat outside the set
the gate cleared. `shippable_files` widens the domain to the index PLUS the untracked,
non-ignored files, and the in-suite brake below runs the real gate over that wider set --
so this file is scanned while it is still untracked.

**No banned token is written as a literal here.** Every positive sample is COMPOSED at call
time from a `RULES` member's own `silent_on` marker plus one name character, so this module
is clean under the very gate it exercises. A marker typed as a literal would red the brake
in `test_b6_b7_...` on this file's own assertion lines -- which is precisely the invariant
the tool's docstring exists to hold, and the trap iteration 06 hit live.

Counts and rule names are never typed twice: `len(cps.RULES)` and `len(domain)` are read
from the tool, because a hard-coded `4` or `242` would agree with reality only by luck and
would rot on the next commit.
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

#: git identity supplied per-command so nothing reads or writes a global git config, and no
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
_SUMMARY_FRAGMENT = "tracked file(s) scanned"


# ---------------------------------------------------------------------------
# helpers -- samples composed, never typed
# ---------------------------------------------------------------------------


def _leak_sample(rule_name: str = PATH_RULE_NAME) -> str:
    """A banned token built at call time: a rule's own marker plus one name character.

    Read, never typed. The marker alone is exempt (it is the rule's `silent_on` sample);
    appending a single name character is what turns it into the thing the rule fires on.
    """
    return BY_NAME[rule_name].silent_on + "a"


def _run_main(argv, list_fn=None, read_fn=None):
    """Call `main()` with the argv it would get from the shell, capturing both streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cps.main(list(argv), list_fn=list_fn, read_fn=read_fn)
    return code, out.getvalue(), err.getvalue()


def _summary_line(stdout: str) -> str:
    """The one published summary line, located by content rather than by position.

    Found by predicate on purpose: a finding run prints findings above it and a rule legend
    below it, so `splitlines()[0]` or `[-1]` would silently read the wrong line.
    """
    lines = [line for line in stdout.splitlines() if _SUMMARY_FRAGMENT in line]
    assert len(lines) == 1, f"expected exactly one summary line, got stdout={stdout!r}"
    return lines[0]


def _summary(n_files: int, n_findings: int) -> str:
    return (
        f"{n_files} {_SUMMARY_FRAGMENT} against {len(cps.RULES)} rule(s): "
        f"{n_findings} finding(s)"
    )


def _offenders(stdout: str) -> list[str]:
    """Repo-relative paths the gate reported, for a failure message that names them."""
    return sorted({m.group("path") for m in map(_FINDING_LINE.match, stdout.splitlines()) if m})


@pytest.fixture(scope="module")
def synthetic_repo(tmp_path_factory) -> pathlib.Path:
    """ONE throwaway work tree holding all three path classes the domain must separate.

    Module-scoped and built once (`git init` + one commit is the only git write anywhere in
    this module), and it is created under the pytest tmp base -- nothing is ever written
    into the product repo.

      `committed.md` -- in the index, so both domains hold it
      `brand-new.md` -- present, untracked, NOT ignored: the class this iteration adds
      `ignored.md`   -- present, untracked, named by `.gitignore`: in neither domain
    """
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    root = tmp_path_factory.mktemp("shippable-domain")
    (root / "committed.md").write_text("clean line\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(root), *FIXTURE_IDENTITY, "commit", "-q", "-m", "fixture"],
        check=True,
        capture_output=True,
    )
    # created AFTER the commit, so the index cannot possibly hold them
    (root / "brand-new.md").write_text("clean line\n", encoding="utf-8")
    (root / "ignored.md").write_text("clean line\n", encoding="utf-8")
    return root


# ===========================================================================
# B1  `shippable_files(root)` is a module-level function returning a sorted,
#     duplicate-free list of repo-RELATIVE paths -- a set a caller can
#     subtract, not a git transcript.
# ===========================================================================


def test_b1_the_shippable_domain_is_a_sorted_deduplicated_list_of_relative_paths():
    assert callable(getattr(cps, "shippable_files", None)), (
        "shippable_files must be a module-level public function of the gate"
    )
    result = cps.shippable_files(REPO)
    assert isinstance(result, list), f"expected list[str], got {type(result).__name__}"
    assert result, "the domain is empty, so every brake built on it would be vacuous"
    assert all(isinstance(p, str) for p in result)
    assert result == sorted(set(result)), (
        "the domain must be sorted and duplicate-free: a merge-conflict path arrives once "
        "per index stage, and a caller comparing domains needs a set, not a transcript"
    )
    absolute = [p for p in result if p.startswith("/") or p.startswith("\\")]
    assert not absolute, f"paths must be repo-relative, got {absolute[:3]}"
    unresolvable = [p for p in result if not (REPO / p).exists()]
    assert not unresolvable, (
        "every returned path must resolve under the root argument; these did not: "
        f"{unresolvable[:5]}"
    )


# ===========================================================================
# B2  The domain is a SUPERSET of the index -- on the live repo, and STRICTLY
#     so on a synthetic tree that actually has an untracked file.
# B3  A gitignored path is in NEITHER domain: a file git is told never to
#     publish is not a file this gate reports.
# ===========================================================================


def test_b2_on_the_live_repo_the_domain_covers_the_whole_index():
    tracked = set(cps.tracked_files(REPO))
    shippable = set(cps.shippable_files(REPO))
    assert tracked, "the index is empty, so this comparison would prove nothing"
    dropped = sorted(tracked - shippable)
    assert not dropped, (
        "the widened domain must never LOSE an indexed path; these went missing: "
        f"{dropped[:5]}"
    )


def test_b2_b3_the_synthetic_domain_adds_the_untracked_file_and_omits_the_ignored_one(
    synthetic_repo: pathlib.Path,
):
    tracked = cps.tracked_files(synthetic_repo)
    shippable = cps.shippable_files(synthetic_repo)

    # B2, the strict half: the untracked file is the difference between the two domains.
    assert "committed.md" in tracked, f"fixture is wrong: {tracked}"
    assert "brand-new.md" not in tracked, (
        "the index must NOT hold the untracked file, or the strict-superset claim is untestable"
    )
    assert "brand-new.md" in shippable, (
        "the file class every round adds is still outside the domain the gate clears"
    )
    assert set(tracked) < set(shippable), "the superset must be STRICT on this tree"
    assert sorted(set(shippable) - set(tracked)) == ["brand-new.md"]

    # B3: the gitignored file exists on disk and appears in neither domain.
    assert (synthetic_repo / "ignored.md").exists(), (
        "control: the ignored file must really be on disk, else its absence proves nothing"
    )
    assert "ignored.md" not in tracked
    assert "ignored.md" not in shippable, (
        "a path git is told never to publish must not be reported by the publish gate"
    )


# ===========================================================================
# B4  A directory git will not treat as a work tree raises `OSError` -- the
#     class `tracked_files` already raises and `main` already converts into
#     the exit-2 refusal, so the wider domain reuses the established path.
# ===========================================================================


def test_b4_a_directory_that_is_not_a_work_tree_is_the_established_exit_2_refusal(
    synthetic_repo: pathlib.Path,
):
    outside = synthetic_repo.parent / "not-a-work-tree"
    outside.mkdir(exist_ok=True)
    assert not (outside / ".git").exists(), "control: this directory must not be a work tree"

    with pytest.raises(OSError):
        cps.shippable_files(outside)

    code, out, err = _run_main(
        ["x", str(outside)], list_fn=lambda: cps.shippable_files(outside)
    )
    assert code == 2, f"expected the exit-2 refusal, got {code} on stdout={out!r} stderr={err!r}"
    assert out == "", f"stdout must carry only the document, got {out!r}"
    lines = err.splitlines()
    assert len(lines) == 1, f"expected exactly one stderr line, got {err!r}"
    assert lines[0].startswith("Error: "), f"stderr must be prefixed 'Error: ', got {err!r}"


# ===========================================================================
# B5  The widened domain REDDENS a leak the index domain clears -- proved with
#     no git at all, through the two published seams, two-sided.
# ===========================================================================


def test_b5_the_wider_domain_reddens_a_leak_the_index_domain_would_have_cleared():
    domain = ["committed.md", "brand-new.md"]
    leak = _leak_sample()

    def read_one_dirty(rel: str) -> str:
        return leak if rel == "brand-new.md" else "clean line\n"

    code, out, err = _run_main(
        ["x", str(REPO)], list_fn=lambda: domain, read_fn=read_one_dirty
    )
    assert code == 1, f"a leak in the new file must fail the gate; got {code}, stdout={out!r}"
    assert err == "", f"a finding is the document, not an error; stderr={err!r}"
    assert _offenders(out) == ["brand-new.md"], (
        f"the finding must name the new file and only it; stdout={out!r}"
    )
    named = [line for line in out.splitlines() if _FINDING_LINE.match(line)]
    assert PATH_RULE_NAME in named[0], f"the finding must name the rule that fired: {named[0]!r}"
    assert _summary_line(out) == _summary(2, 1)

    # The control arm: identical call, clean text for both files.
    code, out, err = _run_main(
        ["x", str(REPO)], list_fn=lambda: domain, read_fn=lambda rel: "clean line\n"
    )
    assert code == 0, f"the clean arm must pass; stdout={out!r} stderr={err!r}"
    assert err == ""
    assert _offenders(out) == [], f"the clean arm must report nothing; stdout={out!r}"
    assert _summary_line(out) == _summary(2, 0)


# ===========================================================================
# B6  THE BRAKE: the real gate, over the real wider domain, on this tree.
# B7  And it is not vacuous -- that domain provably contains this very module
#     (untracked as this runs) and every path the index holds.
# ===========================================================================


def test_b6_b7_the_in_suite_brake_clears_the_domain_this_iteration_ships():
    domain = cps.shippable_files(REPO)

    # B7 first: if these fail, the green below would mean nothing.
    assert SELF_REL in domain, (
        f"the domain does not contain {SELF_REL}, so the file under review is still "
        "outside the set the gate clears -- the exact fail-open this iteration closes"
    )
    tracked = cps.tracked_files(REPO)
    assert tracked, "the index is empty, so this brake would be vacuous"
    dropped = sorted(set(tracked) - set(domain))
    assert not dropped, f"the domain must hold every indexed path; missing {dropped[:5]}"

    code, out, err = _run_main(
        ["x", str(REPO)],
        list_fn=lambda: domain,
        read_fn=lambda rel: (REPO / rel).read_text(encoding="utf-8"),
    )
    assert code == 0, (
        "the domain this iteration would publish is NOT clean under the public-safety gate. "
        f"Offending repo-relative path(s): {_offenders(out) or '(see stdout)'}. "
        "Three remedies, pick one per path: fix the file, add it to .gitignore, or delete "
        f"it. Full stdout={out!r} stderr={err!r}"
    )
    assert err == "", f"a clean scan writes nothing to stderr; got {err!r}"
    assert out == _summary(len(domain), 0) + "\n", (
        "the gate must state the domain size it cleared, in exactly the published shape; "
        f"got {out!r}"
    )


# ===========================================================================
# B8  `main`'s DEFAULT domain did not move: bite 2 was not smuggled into bite
#     1, so every committed assertion on the summary line stays true.
# ===========================================================================


def test_b8_the_default_domain_is_still_the_index_and_the_summary_line_did_not_move():
    tracked = cps.tracked_files(REPO)
    code, out, err = _run_main(["x", str(REPO)])
    assert code == 0, f"the default run must still be green; stdout={out!r} stderr={err!r}"
    assert err == ""
    assert out == _summary(len(tracked), 0) + "\n", (
        "main()'s default domain must remain the git index and its summary line must be "
        f"byte-identical to the published one; got {out!r}"
    )

    # Not vacuous: the reported count really is a function of the domain, so the equality
    # above would have moved had the default been rewired. Stated without depending on
    # whether this module is yet committed, so it holds on both sides of the ship.
    code, other, _ = _run_main(
        ["x", str(REPO)], list_fn=lambda: ["only.md"], read_fn=lambda rel: "clean line\n"
    )
    assert code == 0
    assert _summary_line(other) == _summary(1, 0), (
        "the summary count must track the substituted domain, else the default-domain "
        f"equality above proves nothing; got {other!r}"
    )
    assert len(cps.shippable_files(REPO)) >= len(tracked)
