"""Iteration 220 -- the re-land: a committed digest may not be a function of the
scanning repo's own GROWING corpus.

Iteration 219 pinned two `scan .` documents rendered from the LIVE checkout.  Its
own two new test modules joined `git ls-files` the instant they were committed, so
the pins were GREEN in the working tree (the modules untracked) and RED inside a
clean clone (the modules tracked), and a tree that was green in front of the final
gate was reverted.  This iteration re-points those two pins at a FROZEN corpus --
the tree of `PRECHANGE_COMMIT`, materialised out of this repo's own object store --
so tracked-file growth can never redden them again.

ISOLATION: black-box.  No implementation source was read to write this module --
not `src/`, not `git diff`, not the engineer's, reviewer's or fix-reviewer's notes.
Every expectation comes from the spec's Expected Behaviors, from the constants and
conventions of `tests/test_iter219_behavior.py` (a test file, readable by contract),
or from RUNNING the product.

WHY A CLONE.  The condition that killed iteration 219 -- "tracked, not untracked" --
is the one condition the working tree cannot reproduce, because this iteration's own
modules are untracked here until the final gate commits them.  So behavior 1 builds
the same kind of full local clone the pre-ship gate builds, commits into it a file
this repo does not track (`GROWTH_PROBE`), and renders the pinned document THERE.
That clone is also where `git archive PRECHANGE_COMMIT` has to keep resolving.

Costs, stated as COUNTS per `tools/scan_cost.py`'s doctrine: this module runs
exactly TWO whole-register scans, each in a module-scoped fixture so it is paid
once -- one of the frozen 267-file corpus (behavior 1, out of process, from the
clone's own `src`) and one of the live checkout (behavior 3, the negative control
that proves the pin is no longer anchored to a corpus that grows).  The remaining
tests are `git` plumbing and set arithmetic.

Offline, deterministic, no network.  The product repo is only READ; every write
lands in `tmp_path`.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

import pytest

from agent_gap_radar.cli import main

# Hard import, never `importorskip`: these constants ARE the iteration's
# deliverable, so their absence must fail the suite rather than skip it.
from test_iter219_behavior import (
    FROZEN_TREE_DOCUMENTS,
    PRECHANGE_COMMIT,
    PRECHANGE_DOCUMENTS,
)

REPO = pathlib.Path(__file__).resolve().parents[1]

MD_ARGV = ("scan", ".", "--gaps", "gaps")
JSON_ARGV = ("scan", ".", "--gaps", "gaps", "--json")

#: The document echoes its target's resolved BASE NAME, so the frozen tree has to
#: be extracted into a directory spelled exactly this way or the bytes move.
FROZEN_DIR_NAME = "agent-gap-radar"

#: A file this repo does NOT track, committed inside the clone so that the clone's
#: corpus is strictly larger than the one iteration 219 pinned against.
GROWTH_PROBE = "tests/test_zz_iter220_growth_probe.py"
GROWTH_PROBE_BODY = (
    '"""Iteration 220 growth probe -- exists only inside a test\'s clone."""\n'
    "\n"
    "\n"
    "def test_growth_probe():\n"
    "    pass\n"
)

#: The files that reddened iteration 219's pins.  They are tracked TODAY and they
#: are outside the frozen corpus, which is what makes the fix a DELTA rather than a
#: snapshot: the corpus is fixed at a commit that predates every one of them.
ITER219_MODULES = (
    "tests/test_iter219_behavior.py",
    "tests/test_iter219_domain_union_unit.py",
)
THIS_MODULE = "tests/test_iter220_behavior.py"

#: `git ls-tree -r --name-only PRECHANGE_COMMIT | wc -l` == 267, MEASURED.  A
#: literal, not a re-derivation: it is the census the two pins were captured over,
#: and pinning it is what lets the growth assertions below be self-proving.
FROZEN_CENSUS_SIZE = 267

#: The `(+N more matches, M in test files)` pairs of the FROZEN markdown brief, in
#: document order, MEASURED against the frozen tree.  Frozen bytes, so a frozen
#: literal; the live counts are deliberately NOT pinned because they move every
#: time the repo grows a test file -- which is the whole point.
FROZEN_MATCH_COUNTS = ((30, 30), (12, 12), (22, 22), (77, 77))

_MATCHES = re.compile(r"\(\+(\d+) more matches, (\d+) in test files\)")

#: Rendering the frozen corpus out of process: `sys.path` selects the tree whose
#: implementation runs, argv[2] is where the document lands, and the exit code is
#: the only thing on the child's real stdout.
_RENDER_CHILD = """
import contextlib, io, pathlib, sys

sys.path.insert(0, sys.argv[1])
from agent_gap_radar.cli import main

buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    code = main(sys.argv[3:])
pathlib.Path(sys.argv[2]).write_bytes(buffer.getvalue().encode("utf-8"))
sys.stderr.write(f"IMPL {main.__module__} {sys.modules[main.__module__].__file__}\\n")
sys.stdout.write(str(code))
"""


def _git(*args: str, cwd: pathlib.Path) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          timeout=300)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed in {cwd.name}: {done.stderr[:400]!r}")
    return done.stdout


def _tracked(repo: pathlib.Path) -> set[str]:
    return {line for line in _git("ls-files", cwd=repo).splitlines() if line}


def _match_counts(document: str) -> tuple[tuple[int, int], ...]:
    return tuple((int(a), int(b)) for a, b in _MATCHES.findall(document))


def _extract_frozen(source_repo: pathlib.Path,
                    parent: pathlib.Path) -> pathlib.Path:
    """`git archive PRECHANGE_COMMIT` from `source_repo`, extracted under `parent`."""
    root = parent / FROZEN_DIR_NAME
    root.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(source_repo), "archive", PRECHANGE_COMMIT],
        capture_output=True, timeout=300)
    assert archive.returncode == 0, (
        f"`git archive {PRECHANGE_COMMIT}` failed in {source_repo.name}: "
        f"{archive.stderr.decode('utf-8', 'replace')[:400]!r}")
    extract = subprocess.run(["tar", "-x", "-C", str(root)], input=archive.stdout,
                             capture_output=True, timeout=300)
    assert extract.returncode == 0, (
        f"extracting the frozen corpus failed: "
        f"{extract.stderr.decode('utf-8', 'replace')[:400]!r}")
    assert not (root / ".git").exists(), (
        "the frozen corpus became a git repo, which changes the enumeration route")
    return root


def _render_out_of_process(tree: pathlib.Path, impl_src: pathlib.Path,
                           argv: tuple[str, ...],
                           out_name: str) -> tuple[int, bytes, str]:
    """Render `argv` with `tree` as cwd and `impl_src` as the implementation.

    Out of process because the implementation is selected by `sys.path`, and the
    child echoes the file it actually imported so provenance is MEASURED rather
    than assumed.  Returns `(exit code, stdout bytes, stderr)`.
    """
    document = tree.parent / out_name
    done = subprocess.run(
        [sys.executable, "-c", _RENDER_CHILD, str(impl_src), str(document), *argv],
        cwd=tree, capture_output=True, text=True, timeout=900)
    assert done.returncode == 0, (
        f"rendering {' '.join(argv)} in {tree.name} crashed: {done.stderr[-600:]!r}")
    return int(done.stdout), document.read_bytes(), done.stderr


def _impl_file(stderr: str) -> str:
    """The path of the `cli` module the child actually imported."""
    match = re.search(r"^IMPL (\S+) (\S+)$", stderr, re.MULTILINE)
    assert match, f"the child did not report its implementation: {stderr!r}"
    assert match.group(1) == "agent_gap_radar.cli", (
        f"an unexpected module rendered the document: {match.group(1)!r}")
    return match.group(2)


@pytest.fixture(scope="module")
def grown_clone(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """A full local clone of this repo that TRACKS a file this repo does not.

    Full history and no `--depth`, which is what the pre-ship gate does, because
    `git archive PRECHANGE_COMMIT` reads the object store.  The working-tree copies
    of this iteration's two test modules AND of `src/` are laid over the clone's
    checkout so the clone is the world as it will exist AFTER the ship, and
    `GROWTH_PROBE` is committed on top so the corpus is strictly larger than
    iteration 219's unconditionally -- before the ship and after it.

    `src/` is part of that overlay and was NOT when this fixture was written, which
    made the oracle incoherent for any iteration that moves both a pin and the code
    behind it: `git clone` copies HEAD, so the render ran the COMMITTED
    implementation while `FROZEN_TREE_DOCUMENTS` was read from the WORKING TREE.
    Iteration 252 hit exactly that -- HEAD's 129742 B measured against the working
    tree's re-baselined pin -- and the failure was a property of the fixture, not of
    the change.  A pin and the implementation that renders it must come from the
    same tree; "the world as it will exist AFTER the ship" includes `src/`.
    """
    clone = tmp_path_factory.mktemp("grown") / "clone"
    done = subprocess.run(["git", "clone", "--quiet", str(REPO), str(clone)],
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, f"cloning the repo failed: {done.stderr[:400]!r}"

    for name in (*ITER219_MODULES, THIS_MODULE):
        source = REPO / name
        if source.is_file():
            shutil.copyfile(source, clone / name)
    shutil.rmtree(clone / "src")
    shutil.copytree(REPO / "src", clone / "src",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (clone / GROWTH_PROBE).write_text(GROWTH_PROBE_BODY, encoding="utf-8")

    _git("add", "-A", cwd=clone)
    _git("-c", "user.name=radar tests", "-c", "user.email=tests@example.invalid",
         "commit", "--quiet", "-m", "test: a tracked file the pins must survive",
         cwd=clone)
    return clone


@pytest.fixture(scope="module")
def frozen_tree(grown_clone, tmp_path_factory) -> pathlib.Path:
    """The frozen corpus, extracted ONCE from the CLONE's own object store.

    Extracted from the clone rather than from this checkout on purpose: that is the
    reachability the pre-ship gate depends on, and both `scan` surfaces read the
    same 267 files, so paying for the archive twice would buy nothing.
    """
    return _extract_frozen(grown_clone, tmp_path_factory.mktemp("frozen"))


@pytest.fixture(scope="module")
def frozen_document(grown_clone, frozen_tree) -> tuple[int, bytes, str]:
    """`scan . --gaps gaps` over the frozen corpus, rendered INSIDE the clone.

    Module-scoped: one whole-register scan, paid once.  Returns
    `(exit code, stdout bytes, stderr)`.
    """
    return _render_out_of_process(frozen_tree, grown_clone / "src", MD_ARGV,
                                  "document.md.bytes")


@pytest.fixture(scope="module")
def frozen_json_document(grown_clone, frozen_tree) -> tuple[int, bytes, str]:
    """The `--json` twin of the same frozen render -- the OTHER pin that died.

    Both of iteration 219's failures were `scan .` pins, so verifying only the
    markdown brief would leave half the fix unmeasured.  Module-scoped: one whole-
    register scan, paid once.
    """
    return _render_out_of_process(frozen_tree, grown_clone / "src", JSON_ARGV,
                                  "document.json.bytes")


@pytest.fixture(scope="module")
def clone_live_document(grown_clone) -> tuple[int, bytes, str]:
    """`scan .` over the CLONE ITSELF: the OLD, live-corpus style of pin.

    The counterfactual.  This is the render iteration 219 committed a digest for,
    and inside a clone that tracks more files it does not come back the same --
    which is why the pin had to move to a frozen corpus.  Module-scoped: one
    whole-register scan, paid once.
    """
    return _render_out_of_process(grown_clone, grown_clone / "src", MD_ARGV,
                                  "clone-live.md.bytes")


@pytest.fixture(scope="module")
def tracked_pin_run(
        grown_clone) -> tuple[subprocess.CompletedProcess, str, pathlib.Path]:
    """Expected Behavior 1 in its LITERAL form: `pytest tests/test_iter219_\
behavior.py` inside the clone, where that module is TRACKED.

    Scoped to `-k b1_scan` (exactly the two tests that reddened, no more), run with
    `-n0` so the outer suite's `-n auto` cannot nest, and with the clone's own `src`
    on `PYTHONPATH` so the code under test is the clone's -- verified, not assumed,
    by importing the package in the same environment and reporting `__file__`.
    """
    env = {**os.environ,
           "PYTHONPATH": str(grown_clone / "src"),
           "PYTHONDONTWRITEBYTECODE": "1"}
    for leak in ("PYTEST_ADDOPTS", "PYTEST_CURRENT_TEST", "PYTEST_XDIST_WORKER",
                 "PYTEST_XDIST_WORKER_COUNT", "PYTEST_XDIST_TESTRUNUID"):
        env.pop(leak, None)
    which = subprocess.run(
        [sys.executable, "-c", "import agent_gap_radar as m; print(m.__file__)"],
        cwd=grown_clone, capture_output=True, text=True, timeout=300, env=env)
    assert which.returncode == 0, (
        f"the clone's package does not import: {which.stderr[-400:]!r}")
    report = grown_clone.parent / "tracked-pins.xml"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_iter219_behavior.py",
         "-k", "b1_scan", "-n0", "-p", "no:cacheprovider", "--no-header",
         f"--junit-xml={report}"],
        cwd=grown_clone, capture_output=True, text=True, timeout=1800, env=env)
    return done, which.stdout.strip(), report


@pytest.fixture(scope="module")
def live_document() -> tuple[int, bytes, str]:
    """The same argv rendered from the LIVE checkout -- the negative control.

    Module-scoped: one whole-register scan, paid once.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.chdir(REPO), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = main(list(MD_ARGV))
    return code, out.getvalue().encode("utf-8"), err.getvalue()


# ------------------------------------------------------------------ behavior 1
def test_b1_the_pinned_document_renders_in_a_clone_that_tracks_more_files(
        frozen_document):
    """The condition iteration 219 died on, reproduced and passed.

    The clone tracks `GROWTH_PROBE` plus this iteration's own modules, i.e. strictly
    more files than the corpus the pins were captured over -- and the pinned bytes
    come back unmoved, because the corpus they name is frozen at a commit.
    """
    expected_len, expected_sha = FROZEN_TREE_DOCUMENTS[MD_ARGV]
    code, out, err = frozen_document
    assert code == 0, f"the frozen scan exited {code}"
    assert len(out) == expected_len, (
        f"the frozen corpus rendered {len(out)} B in a clone that tracks more "
        f"files; the pin says {expected_len} B")
    assert hashlib.sha256(out).hexdigest() == expected_sha, (
        "the frozen document's bytes moved inside a clone -- the pin is still a "
        "function of what the repo tracks")
    text = out.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        "the document does not end in exactly one newline")
    assert "IMPL agent_gap_radar.cli" in err, (
        f"the clone's own implementation did not render it: {err!r}")


def test_b1_the_frozen_commit_still_resolves_inside_a_fresh_clone(grown_clone):
    """`git archive` reads the object store, so a gate that clones must still find
    `PRECHANGE_COMMIT` -- a full clone does, and the fixture fails LOUDLY if not."""
    kind = _git("cat-file", "-t", PRECHANGE_COMMIT, cwd=grown_clone).strip()
    assert kind == "commit", (
        f"{PRECHANGE_COMMIT} is a {kind!r} in a fresh clone, so the frozen corpus "
        f"is unreachable there")


def test_b1_the_frozen_archive_is_a_constant_of_the_commit_not_of_the_checkout(
        grown_clone):
    """Same commit, two different checkouts, byte-identical archive: the corpus
    cannot drift with the tree that happens to hold it."""
    here = subprocess.run(["git", "-C", str(REPO), "archive", PRECHANGE_COMMIT],
                          capture_output=True, timeout=300)
    there = subprocess.run(["git", "-C", str(grown_clone), "archive",
                            PRECHANGE_COMMIT], capture_output=True, timeout=300)
    assert here.returncode == 0 and there.returncode == 0
    assert hashlib.sha256(here.stdout).hexdigest() == \
        hashlib.sha256(there.stdout).hexdigest(), (
        "the frozen archive differs between this checkout and a clone of it")
    assert _tracked(grown_clone) != _tracked(REPO), (
        "the clone tracks the same files as this repo, so it proves nothing about "
        "growth")


def test_b1_pytest_passes_on_the_iter219_module_when_it_is_tracked(
        tracked_pin_run, grown_clone):
    """Expected Behavior 1, measured verbatim instead of modelled.

    The two `scan` pins are executed BY PYTEST, from a checkout where
    `tests/test_iter219_behavior.py` and its unit twin are tracked files -- the
    exact world in which the pre-ship gate answered BROKEN one iteration ago.
    """
    done, impl_file, report = tracked_pin_run
    assert impl_file.startswith(str(grown_clone) + os.sep), (
        f"the nested run imported {impl_file!r}, which is not the clone's own "
        f"implementation, so it measured the wrong tree")
    tracked = _tracked(grown_clone)
    for name in ITER219_MODULES:
        assert name in tracked, (
            f"{name} is untracked in the clone, so this run does not reproduce the "
            f"condition that reddened the pins")
    assert done.returncode == 0, (
        "`pytest tests/test_iter219_behavior.py -k b1_scan` FAILED in a clone that "
        f"tracks the module:\n{done.stdout[-2000:]}\n{done.stderr[-800:]}")
    suite = ElementTree.parse(report).getroot().find("testsuite")
    assert suite is not None, f"the nested run wrote no junit report: {report}"
    tally = {key: int(suite.attrib[key])
             for key in ("tests", "failures", "errors", "skipped")}
    assert tally == {"tests": 2, "failures": 0, "errors": 0, "skipped": 0}, (
        f"the two `scan` pins did not both RUN and pass in the tracked clone: "
        f"{tally}\n{done.stdout[-1200:]}")
    names = sorted(case.attrib["name"] for case in suite.iter("testcase"))
    assert names == [
        "test_b1_scan_is_byte_identical_to_the_prechange_document",
        "test_b1_scan_json_is_byte_identical_to_the_prechange_document",
    ], f"the nested run executed the wrong tests: {names}"


def test_b1_the_json_twin_renders_the_pinned_bytes_in_a_grown_clone(
        frozen_json_document, grown_clone):
    """The second pin that died, verified on the same terms as the first: exit 0,
    the pinned length and digest, one trailing newline, and parseable JSON."""
    expected_len, expected_sha = FROZEN_TREE_DOCUMENTS[JSON_ARGV]
    code, out, err = frozen_json_document
    assert code == 0, f"the frozen `--json` scan exited {code}"
    assert len(out) == expected_len, (
        f"the frozen `--json` document is {len(out)} B in a clone that tracks more "
        f"files; the pin says {expected_len} B")
    assert hashlib.sha256(out).hexdigest() == expected_sha, (
        "the frozen `--json` bytes moved inside a clone -- the release-gate "
        "projection is still a function of what the repo tracks")
    text = out.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        "the `--json` document does not end in exactly one newline")
    json.loads(text)
    assert _impl_file(err).startswith(str(grown_clone) + os.sep)


def test_b1_the_implementation_that_rendered_each_pin_lives_in_the_clone(
        frozen_document, frozen_json_document, grown_clone):
    """Provenance, by `__file__` rather than by module name: a pin rendered by this
    checkout's `src` would say nothing about what a clean clone does."""
    clone_src = str(grown_clone / "src") + os.sep
    for label, (_, _, err) in (("markdown", frozen_document),
                               ("json", frozen_json_document)):
        where = _impl_file(err)
        assert where.startswith(clone_src), (
            f"the {label} pin was rendered by {where!r}, not by the clone's src")
        assert not where.startswith(str(REPO) + os.sep), (
            f"the {label} pin was rendered by the live checkout: {where!r}")


# ------------------------------------------------------------------ behavior 2
def test_b2_the_frozen_corpus_is_exactly_the_commits_tree(grown_clone,
                                                          tmp_path_factory):
    """267 files, the commit's own census, and no `.git` -- so the enumeration is a
    WALK of a fixed file set rather than a `git ls-files` of a growing one."""
    census = {line for line in
              _git("ls-tree", "-r", "--name-only", PRECHANGE_COMMIT,
                   cwd=REPO).splitlines() if line}
    assert len(census) == FROZEN_CENSUS_SIZE, (
        f"the frozen commit tracks {len(census)} files, not {FROZEN_CENSUS_SIZE}")

    frozen = _extract_frozen(grown_clone, tmp_path_factory.mktemp("census"))
    extracted = {p.relative_to(frozen).as_posix()
                 for p in frozen.rglob("*") if p.is_file()}
    assert extracted == census, (
        "the extracted corpus is not the commit's tree; "
        f"missing={sorted(census - extracted)[:5]} extra="
        f"{sorted(extracted - census)[:5]}")


def test_b2_every_file_that_reddened_the_old_pin_is_outside_the_frozen_corpus():
    """The fix as a DELTA: the modules whose tracking broke iteration 219 are
    tracked TODAY and absent from the corpus the pins now name."""
    census = {line for line in
              _git("ls-tree", "-r", "--name-only", PRECHANGE_COMMIT,
                   cwd=REPO).splitlines() if line}
    tracked_today = _tracked(REPO)

    for name in ITER219_MODULES:
        assert name in tracked_today, (
            f"{name} is not tracked, so this repo is not the world the pin has to "
            f"survive")
        assert name not in census, (
            f"{name} is inside the frozen corpus, so the pin is not frozen before "
            f"the growth that reddened it")
    assert (REPO / THIS_MODULE).is_file()
    assert THIS_MODULE not in census, (
        "this iteration's own module is inside the frozen corpus, which is "
        "chronologically impossible -- the pin names the wrong commit")
    assert len(tracked_today) > FROZEN_CENSUS_SIZE, (
        f"the repo tracks {len(tracked_today)} files, not more than the frozen "
        f"{FROZEN_CENSUS_SIZE}, so nothing here demonstrates growth")


# ------------------------------------------------------------------ behavior 3
def test_b3_the_live_checkout_no_longer_renders_the_pinned_bytes(live_document,
                                                                frozen_document):
    """The negative control.  If the pin still measured the live checkout, these
    two documents would be equal -- and the pin would redden on the next commit."""
    expected_len, expected_sha = FROZEN_TREE_DOCUMENTS[MD_ARGV]
    live_code, live_out, live_err = live_document
    assert live_code == 0 and live_err == "", (
        f"the live scan exited {live_code}; stderr={live_err!r}")
    assert hashlib.sha256(live_out).hexdigest() != expected_sha, (
        "the live checkout renders the pinned bytes, so the pin is indistinguishable"
        " from the live-corpus pin this iteration replaced")

    frozen_out = frozen_document[1]
    assert hashlib.sha256(frozen_out).hexdigest() == expected_sha
    live_counts = _match_counts(live_out.decode("utf-8"))
    frozen_counts = _match_counts(frozen_out.decode("utf-8"))
    assert frozen_counts == FROZEN_MATCH_COUNTS, (
        f"the frozen brief's match counts moved: {frozen_counts}")
    assert live_counts != frozen_counts, (
        "the live and frozen briefs report the same match counts, so the corpus "
        "has not in fact grown and this control is vacuous")
    assert sum(sum(pair) for pair in live_counts) > \
        sum(sum(pair) for pair in frozen_counts), (
        f"the live corpus is not larger than the frozen one: {live_counts} vs "
        f"{frozen_counts}")


def test_b3_a_live_corpus_render_in_the_same_clone_does_not_reproduce_the_pin(
        clone_live_document, frozen_document):
    """The counterfactual that names iteration 219's death.

    ONE clone, TWO corpora, the SAME implementation: scanning the clone itself (the
    old style of pin) does not reproduce the committed digest, while scanning the
    frozen tree does.  So the pin's stability comes from the corpus being frozen,
    not from the clone happening to be quiet.
    """
    expected_len, expected_sha = FROZEN_TREE_DOCUMENTS[MD_ARGV]
    live_code, live_out, _ = clone_live_document
    assert live_code == 0, f"the clone's live scan exited {live_code}"
    assert hashlib.sha256(live_out).hexdigest() != expected_sha, (
        "a live-corpus render inside a grown clone reproduced the pin, which would "
        "make this whole iteration unnecessary")

    frozen_out = frozen_document[1]
    assert len(frozen_out) == expected_len
    assert hashlib.sha256(frozen_out).hexdigest() == expected_sha

    live_counts = _match_counts(live_out.decode("utf-8"))
    frozen_counts = _match_counts(frozen_out.decode("utf-8"))
    assert frozen_counts == FROZEN_MATCH_COUNTS, (
        f"the frozen brief's match counts moved: {frozen_counts}")
    assert live_counts != frozen_counts, (
        f"the clone's live corpus reports the frozen match counts {frozen_counts}, "
        f"so it did not in fact grow")
    assert sum(sum(pair) for pair in live_counts) > \
        sum(sum(pair) for pair in frozen_counts), (
        f"the clone's corpus is not larger than the frozen one: {live_counts} vs "
        f"{frozen_counts}")


# --------------------------------------------------------- acceptance criteria
def test_ac_no_scan_pin_names_the_live_checkout_as_its_corpus():
    """A digest only means something alongside the corpus it was taken from, so the
    two dictionaries must stay separated by exactly that: `scan` pins are frozen,
    register-side pins read the live `gaps/`."""
    assert set(FROZEN_TREE_DOCUMENTS) == {MD_ARGV, JSON_ARGV}, (
        f"the frozen pins are {sorted(FROZEN_TREE_DOCUMENTS)}, not the two `scan` "
        f"surfaces")
    assert set(PRECHANGE_DOCUMENTS) == {
        ("report", "gaps"), ("list", "gaps"), ("list", "gaps", "--json"),
        ("validate", "gaps"),
    }, f"the live-corpus pins changed shape: {sorted(PRECHANGE_DOCUMENTS)}"
    assert not [argv for argv in PRECHANGE_DOCUMENTS if argv[0] == "scan"], (
        "a `scan` pin is back in the live-corpus dictionary")
    assert not set(FROZEN_TREE_DOCUMENTS) & set(PRECHANGE_DOCUMENTS)
    assert FROZEN_TREE_DOCUMENTS[MD_ARGV] != FROZEN_TREE_DOCUMENTS[JSON_ARGV], (
        "the two frozen pins carry the same length and digest, so one of them is a "
        "copy rather than a measurement")
    for argv, (length, sha) in FROZEN_TREE_DOCUMENTS.items():
        assert length > 0 and re.fullmatch(r"[0-9a-f]{64}", sha), (
            f"{argv} carries a malformed pin: {(length, sha)!r}")


def test_ac_the_frozen_commit_is_the_parent_of_the_change_under_pin():
    """`PRECHANGE_COMMIT` must be an ANCESTOR of HEAD and must predate the modules
    that reddened the pins -- otherwise "pre-change" is just a label."""
    assert _git("cat-file", "-t", PRECHANGE_COMMIT, cwd=REPO).strip() == "commit"
    merge_base = _git("merge-base", PRECHANGE_COMMIT, "HEAD", cwd=REPO).strip()
    resolved = _git("rev-parse", PRECHANGE_COMMIT, cwd=REPO).strip()
    assert merge_base == resolved, (
        f"{PRECHANGE_COMMIT} is not an ancestor of HEAD, so it cannot be the "
        f"pre-change tree")
