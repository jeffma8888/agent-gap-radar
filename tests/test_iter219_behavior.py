"""Iteration 219 -- a multi-glob file domain is the UNION of its per-glob domains.

Inside an open `file_cache_scope()`, `iter_files` used to memoise a whole GLOB SET
while the matching work underneath it was done per GLOB, so a glob named by twenty
rules was matched twenty times in one scan.  This iteration assembles a multi-glob
domain from per-glob domains memoised in the SAME frame under the SAME key type.
The set-level key stays the public API; the union is an internal assembly step.

ISOLATION: black-box.  No implementation source was read to write this module --
not `checks.py`, not the diff, not the engineer's or reviewer's notes.  Every
expectation comes from the spec's Expected Behaviors, from the conventions of
`tests/test_file_cache_unit.py`, or from RUNNING the product.

PROVENANCE OF THE PINNED BYTES -- behavior 1 is proved against the PRE-CHANGE
implementation, not against a re-derived expectation.  That implementation was
materialised out-of-repo with `git archive 0356b8b src | tar -x -C <tmp>` and run
from its own `PYTHONPATH` (`scan` echoes its target, so the relative form is what
is pinned).  The four REGISTER-side documents in `PRECHANGE_DOCUMENTS` were
captured with the repo root as cwd and reproduce iteration 218's independently
pinned digests byte for byte, which is what makes the capture's provenance
checkable rather than merely asserted.  The two `scan` documents in
`FROZEN_TREE_DOCUMENTS` are captured against a FROZEN COPY of the pre-change tree
rather than the live checkout, because a digest of a document rendered from the
live checkout is a function of every file this repo later tracks -- see that
constant for the measurement.

Costs, stated as COUNTS not seconds, per `tools/scan_cost.py`'s doctrine: this
module runs two full scans of a 267-file frozen COPY of this repo, extracted once
per module (behavior 1, the only end-to-end oracle available for a change whose
whole promise is that nothing moved), and ten unmemoised enumerations of this repo
(behavior 9, bounded to the widest register sets since
`tests/test_iter219_domain_union_unit.py` carries the register-wide census).
Everything else runs against a five-file `tmp_path` tree.

Offline, deterministic, no network.  The live register is only READ.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import re
import subprocess

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import _FILE_CACHE_STACK, file_cache_scope, iter_files
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO / "gaps"

#: The commit whose TREE the two `scan` pins are measured against:
#: `0356b8b7e638eb22c011d794f77fb78b74a9d6e5`, the parent of the change this
#: module tests.  Abbreviated because the docstrings and the capture recipe name
#: it that way; `git archive` resolves either spelling.
PRECHANGE_COMMIT = "0356b8b"

#: argv -> (stdout byte length, sha256) for the REGISTER-side verbs, captured from
#: the pre-change tree with the repo root as cwd.  Their only input is `gaps/`, so
#: the live checkout is a legitimate corpus for them and iteration 218 pinned the
#: same four digests independently.  All four exit 0 with EMPTY stderr and one
#: trailing newline.
PRECHANGE_DOCUMENTS: dict[tuple[str, ...], tuple[int, str]] = {
    ("report", "gaps"):
        (39022, "be4bd4e983356c8b705e3e7c026ca2bc713912c0ac89ad7fe0c1d5587be0165f"),
    ("list", "gaps"):
        (17446, "06906c37e424382884cf2890fa7b57fc101b7eca545a92dcba415cb15f7b2f88"),
    ("list", "gaps", "--json"):
        (50218, "0a6abac448d375df019b45f6af1a9770998a27d445c2d43d565903a776374468"),
    ("validate", "gaps"):
        (29, "5320bce7a70985f99078db703925a635926e4f1fff9dfe908cd5e57b6b930720"),
}

#: argv -> (stdout byte length, sha256) for the two `scan` surfaces, rendered from
#: the FROZEN tree of `PRECHANGE_COMMIT` (see `frozen_target`).
#:
#: WHY NOT THE LIVE CHECKOUT.  `scan` enumerates its target with `git ls-files`, so
#: a digest taken against this repo scanning ITSELF is a function of every file the
#: repo later tracks -- the pin rots by construction, and it rots with news about
#: the CORPUS while claiming to be news about THROUGHPUT.  Measured the day this
#: module became tracked: three lines moved, and not one of them was a rendering
#: change.  `(+77 more matches, 77 in test files)` became `78` (this module and its
#: unit twin joined the corpus), and two evidence locators slid down `checks.py`
#: (`:1250` -> `:1305`, `:971` -> `:1026`) because the iteration added 79 lines
#: ABOVE them.  The `:971` -> `:1026` slide is also the whole of the one-byte
#: length change, which is why the length assertion still passed while the digest
#: did not.
#:
#: WHAT THE FROZEN PIN IS WORTH.  Both implementations render this tree to the same
#: bytes: the pre-change `src` (materialised as above) and the post-change `src`
#: were each run over this extracted tree, and md/json came back
#: 25116 B / `7dc7c366...` and 129742 B / `36cb0e85...` from BOTH.  That is a
#: STRICTLY stronger reading of behavior 1 than the original pin could give, since
#: the original compared two implementations over two different corpora.
FROZEN_TREE_DOCUMENTS: dict[tuple[str, ...], tuple[int, str]] = {
    ("scan", ".", "--gaps", "gaps"):
        (25116, "7dc7c366b3575024ca75a37db24547b9b985128457e3b91f42a3517fdd38a966"),
    ("scan", ".", "--gaps", "gaps", "--json"):
        (129742, "36cb0e856bea0b29acc2ca3425c45d070fd1dc5aa94c8ccef8f74692bddfa838"),
}

PY = "**/*.py"
MD = "**/*.md"
TS = "**/*.ts"


@pytest.fixture()
def target(tmp_path: pathlib.Path) -> pathlib.Path:
    """A non-git tree with one file per glob plus one TEST file.

    Not a git repo, so every ask goes through the walked branch and re-reads the
    filesystem -- which is what makes "the memo was not consulted" falsifiable.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    pass\n",
                                                  encoding="utf-8")
    (tmp_path / "notes.md").write_text("# a document\n", encoding="utf-8")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "c.ts").write_text("export const c = 1;\n", encoding="utf-8")
    return tmp_path


@pytest.fixture(scope="module")
def frozen_target(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """The pre-change tree, materialised out of this repo's own object store.

    Module-scoped because both `scan` pins read it and extracting 267 files twice
    would buy nothing.  Three details are load-bearing:

    * The directory is NAMED `agent-gap-radar`, because the document echoes the
      target's resolved BASE NAME (`# Gap scan: <name>`); a `tmp_path` name would
      move the pinned bytes.  The tests enter it and spell the target `.`, because
      the document echoes the caller's SPELLING too.
    * It is deliberately NOT a git repo, so `tracked_files` answers `None` and the
      WALK enumerates it.  The archive holds exactly the tracked paths of
      `PRECHANGE_COMMIT` and none of `SKIP_DIRS`, so the walk sees that same
      census -- and taking this route keeps the pin out of reach of a
      contributor's ambient git config (a global `core.excludesFile` would change
      what `git add` tracked, and with it the corpus).
    * `git archive` reads the object store, so this needs a checkout that has the
      commit, not a shallow clone.  The module already assumes a checkout (behavior
      9 enumerates `REPO`; the acceptance-criterion test stats files under it), and
      failing loudly beats a skip that would quietly retire an oracle.
    """
    root = tmp_path_factory.mktemp("frozen") / "agent-gap-radar"
    root.mkdir()
    archive = subprocess.run(
        ["git", "-C", str(REPO), "archive", PRECHANGE_COMMIT],
        capture_output=True, timeout=120)
    assert archive.returncode == 0, (
        f"`git archive {PRECHANGE_COMMIT}` failed in {REPO}; the frozen corpus "
        f"behind the `scan` pins needs that commit: "
        f"{archive.stderr.decode('utf-8', 'replace')[:400]!r}")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive.stdout,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        f"extracting the frozen corpus failed: "
        f"{extract.stderr.decode('utf-8', 'replace')[:400]!r}")
    assert (root / "src" / "agent_gap_radar" / "checks.py").is_file(), (
        "the frozen corpus has no source tree, so a scan of it would be vacuous")
    assert (root / "gaps").is_dir(), (
        "the frozen corpus has no register, so a scan of it would be vacuous")
    assert not (root / ".git").exists(), (
        "the frozen corpus became a git repo, which changes the enumeration route")
    return root


def _spy(monkeypatch) -> list[tuple[str, tuple[str, ...], bool]]:
    """Record every ACTUAL enumeration, then delegate.  Returns the growing log."""
    seen: list[tuple[str, tuple[str, ...], bool]] = []
    real = checks._enumerate_files

    def spy(target: pathlib.Path, globs: list[str],
            exclude_tests: bool) -> list[pathlib.Path]:
        seen.append((str(target), tuple(globs), exclude_tests))
        return real(target, globs, exclude_tests)

    monkeypatch.setattr(checks, "_enumerate_files", spy)
    return seen


def _names(target: pathlib.Path, paths: list[pathlib.Path]) -> list[str]:
    return sorted(p.relative_to(target).as_posix() for p in paths)


def _key(target: pathlib.Path, globs: tuple[str, ...],
         exclude_tests: bool = False) -> tuple[str, tuple[str, ...], bool]:
    return (str(target), globs, exclude_tests)


def _run(argv: tuple[str, ...], monkeypatch,
         cwd: pathlib.Path | None = None) -> tuple[int, bytes, str]:
    """Run the CLI in-process from `cwd` (default the repo root), stdout as BYTES."""
    monkeypatch.chdir(cwd if cwd is not None else REPO)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue().encode("utf-8"), err.getvalue()


def _document_is_unchanged(
        argv: tuple[str, ...], monkeypatch, *,
        pins: dict[tuple[str, ...], tuple[int, str]] | None = None,
        cwd: pathlib.Path | None = None) -> None:
    """Assert one document against its pin: exit code, stderr, length, sha, newline.

    `pins`/`cwd` travel together -- a digest only means anything alongside the
    corpus it was taken from, so naming one without the other is the mistake this
    iteration fixed.
    """
    expected_len, expected_sha = (pins or PRECHANGE_DOCUMENTS)[argv]
    code, out, err = _run(argv, monkeypatch, cwd)
    assert code == 0, f"{' '.join(argv)} exited {code}; stderr={err!r}"
    assert err == "", f"{' '.join(argv)} wrote to stderr: {err!r}"
    assert len(out) == expected_len, (
        f"{' '.join(argv)} is {len(out)} B, pre-change was {expected_len} B")
    assert hashlib.sha256(out).hexdigest() == expected_sha, (
        f"{' '.join(argv)} bytes moved against the pre-change document")
    text = out.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        "the document does not end in exactly one newline")


# ------------------------------------------------------------------ behavior 1
def test_b1_scan_is_byte_identical_to_the_prechange_document(
        frozen_target, monkeypatch):
    """The end-to-end oracle: a throughput change must move ZERO published bytes.

    Scanned target is the FROZEN pre-change tree, not the live checkout, so the
    only thing this digest can report on is the rendering code.
    """
    _document_is_unchanged(("scan", ".", "--gaps", "gaps"), monkeypatch,
                           pins=FROZEN_TREE_DOCUMENTS, cwd=frozen_target)


def test_b1_scan_json_is_byte_identical_to_the_prechange_document(
        frozen_target, monkeypatch):
    """The release-gate projection of the same scan, pinned separately: it renders
    locators and per-gap verdicts the markdown brief summarises away."""
    _document_is_unchanged(("scan", ".", "--gaps", "gaps", "--json"), monkeypatch,
                           pins=FROZEN_TREE_DOCUMENTS, cwd=frozen_target)


@pytest.mark.parametrize("argv", [
    ("report", "gaps"), ("list", "gaps"), ("list", "gaps", "--json"),
    ("validate", "gaps"),
])
def test_b1_the_other_documents_are_byte_identical_too(argv, monkeypatch):
    """Acceptance criterion: the register-side verbs are collateral, not targets."""
    _document_is_unchanged(argv, monkeypatch)


# ------------------------------------------------------------------ behavior 2
def test_b2_a_multi_glob_ask_leaves_n_plus_one_keys_whose_set_entry_is_the_union(
        target, monkeypatch):
    """Three globs asked as one set: the frame holds the set key AND one key per
    glob, and the set's value is `sorted` of the union of the three."""
    seen = _spy(monkeypatch)
    globs = (PY, MD, TS)

    with file_cache_scope() as frame:
        answer = iter_files(target, list(globs))
        set_key = _key(target, globs)
        per_glob = [_key(target, (g,)) for g in globs]

        assert set(frame) == {set_key, *per_glob}, (
            f"expected {len(globs) + 1} keys (1 set + {len(globs)} per glob), got "
            f"{sorted(k[1] for k in frame)}")
        union: set[pathlib.Path] = set()
        for key in per_glob:
            union.update(frame[key])
        assert frame[set_key] == sorted(union), (
            "the set entry is not sorted(union) of its per-glob entries")
        assert answer == sorted(union)

    assert _names(target, answer) == ["notes.md", "pkg/a.py", "tests/test_a.py",
                                      "web/c.ts"]
    assert len(seen) == 3, f"3 distinct globs must cost 3 enumerations; got {len(seen)}"


# ------------------------------------------------------------------ behavior 3
def test_b3_two_overlapping_sets_cost_one_enumeration_per_distinct_glob(
        target, monkeypatch):
    """The prize as a COUNT: `[a,b]` then `[b,c]` is 4 glob mentions and 3 walks,
    and every walk carries a SINGLE glob -- the observable difference between
    per-glob and per-set matching."""
    seen = _spy(monkeypatch)

    with file_cache_scope() as frame:
        first = iter_files(target, [PY, MD])
        second = iter_files(target, [MD, TS])

    assert len(seen) == 3, (
        f"expected 3 enumerations for the 3 distinct globs, got {len(seen)}: "
        f"{[globs for _, globs, _ in seen]}")
    assert all(len(globs) == 1 for _, globs, _ in seen), (
        f"an enumeration carried a multi-glob argument: {[g for _, g, _ in seen]}")
    assert sorted(globs[0] for _, globs, _ in seen) == sorted([PY, MD, TS])
    assert len({(globs, excl) for _, globs, excl in seen}) == 3, "a glob walked twice"
    assert _names(target, first) == ["notes.md", "pkg/a.py", "tests/test_a.py"]
    assert _names(target, second) == ["notes.md", "web/c.ts"]
    assert set(frame) == {
        _key(target, (PY, MD)), _key(target, (MD, TS)),
        _key(target, (PY,)), _key(target, (MD,)), _key(target, (TS,)),
    }, "the two set keys plus one key per distinct glob"


# ------------------------------------------------------------------ behavior 4
def test_b4_the_single_glob_base_case_is_unchanged(target, monkeypatch):
    """What protects the 8 pins in `tests/test_file_cache_unit.py`: a one-glob ask
    is ONE enumeration and ONE key, because the set key IS its own per-glob key."""
    seen = _spy(monkeypatch)

    with file_cache_scope() as frame:
        first = iter_files(target, [PY])
        assert set(frame) == {_key(target, (PY,))}, (
            f"a single-glob ask left {len(frame)} keys: {sorted(k[1] for k in frame)}")
        assert len(seen) == 1
        second = iter_files(target, [PY])
        assert set(frame) == {_key(target, (PY,))}, "the repeat ask added a key"
        assert len(seen) == 1, "the repeat ask re-enumerated"

    assert _names(target, first) == _names(target, second) == ["pkg/a.py",
                                                              "tests/test_a.py"]


# ------------------------------------------------------------------ behavior 5
def test_b5_exclude_tests_still_separates_at_the_per_glob_level(target, monkeypatch):
    """The fail-open the key exists to prevent, now one level deeper: the SAME glob
    under both `exclude_tests` values must be two per-glob entries, two answers."""
    seen = _spy(monkeypatch)

    with file_cache_scope() as frame:
        wide = iter_files(target, [PY, MD])
        narrow = iter_files(target, [PY, MD], exclude_tests=True)

        wide_py = frame[_key(target, (PY,), False)]
        narrow_py = frame[_key(target, (PY,), True)]
        assert _names(target, wide_py) == ["pkg/a.py", "tests/test_a.py"]
        assert _names(target, narrow_py) == ["pkg/a.py"], (
            "exclude_tests did not narrow the per-glob domain")
        assert len(frame) == 6, (
            "expected 2 set keys and 4 per-glob keys (2 globs x 2 exclude_tests), "
            f"got {sorted((k[1], k[2]) for k in frame)}")

    assert _names(target, wide) == ["notes.md", "pkg/a.py", "tests/test_a.py"]
    assert _names(target, narrow) == ["notes.md", "pkg/a.py"]
    assert len(seen) == 4, (
        f"2 globs x 2 exclude_tests = 4 enumerations; got {len(seen)}")


# ------------------------------------------------------------------ behavior 6
def test_b6_every_handed_out_list_is_fresh_for_both_key_kinds(target, monkeypatch):
    """A caller that sorts or truncates its result in place must not be able to
    narrow any later domain -- including a domain assembled LATER out of the
    per-glob entry it corrupted, which is the new failure mode."""
    seen = _spy(monkeypatch)
    fabricated = target / "fabricated.py"

    with file_cache_scope() as frame:
        pair = iter_files(target, [PY, MD])
        single = iter_files(target, [PY])
        assert pair is not frame[_key(target, (PY, MD))], (
            "the cached set list itself was handed to a caller")
        assert single is not frame[_key(target, (PY,))], (
            "the cached per-glob list itself was handed to a caller")
        assert single is not pair

        pair.clear()
        pair.append(fabricated)
        single.clear()
        single.append(fabricated)

        # A brand-new set that must ASSEMBLE from the per-glob entry just mutated.
        later = iter_files(target, [PY, TS])
        assert _names(target, later) == ["pkg/a.py", "tests/test_a.py", "web/c.ts"], (
            "mutating a per-glob answer corrupted a later union")
        assert _names(target, iter_files(target, [PY])) == ["pkg/a.py",
                                                           "tests/test_a.py"]
        assert _names(target, iter_files(target, [PY, MD])) == [
            "notes.md", "pkg/a.py", "tests/test_a.py"], (
            "mutating a set answer corrupted the snapshot")
        assert all(fabricated not in value for value in frame.values()), (
            "a fabricated path reached the frame")

    assert len(seen) == 3, f"3 distinct globs, 3 walks; got {len(seen)}"


# ------------------------------------------------------------------ behavior 7
def test_b7_a_later_scope_re_enumerates_from_the_tree(target, monkeypatch):
    """The scope IS the invalidation, and it must invalidate the per-glob entries
    too -- otherwise the union would be assembled from a previous scan's snapshot."""
    seen = _spy(monkeypatch)

    with file_cache_scope():
        assert _names(target, iter_files(target, [PY, MD])) == [
            "notes.md", "pkg/a.py", "tests/test_a.py"]
    (target / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    with file_cache_scope() as second:
        assert _names(target, iter_files(target, [PY, MD])) == [
            "notes.md", "pkg/a.py", "pkg/b.py", "tests/test_a.py"], (
            "a later scope answered from an earlier scope's per-glob entry")
        assert set(second) == {_key(target, (PY, MD)), _key(target, (PY,)),
                               _key(target, (MD,))}

    assert len(seen) == 4, f"two scopes x two globs; got {len(seen)}"
    assert _FILE_CACHE_STACK == [], "a frame survived its scope"


def test_b7_outside_a_scope_nothing_is_memoised(target, monkeypatch):
    """No frame, no memo: the tree is re-read on every call, and the ask is walked
    as the set it was asked as -- splitting it would buy nothing and cost N walks."""
    seen = _spy(monkeypatch)

    before = iter_files(target, [PY, MD])
    (target / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    after = iter_files(target, [PY, MD])

    assert _names(target, before) == ["notes.md", "pkg/a.py", "tests/test_a.py"]
    assert _names(target, after) == ["notes.md", "pkg/a.py", "pkg/b.py",
                                     "tests/test_a.py"], (
        "an out-of-scope enumeration answered from a cache")
    assert len(seen) == 2, (
        f"expected one enumeration per out-of-scope call, got {len(seen)}: "
        f"{[globs for _, globs, _ in seen]}")
    assert [globs for _, globs, _ in seen] == [(PY, MD), (PY, MD)], (
        "an out-of-scope ask was split per glob, so it paid the split with no memo")


# ------------------------------------------------------------------ behavior 8
def test_b8_order_and_duplicates_change_neither_the_answer_nor_the_walk_count(
        target, monkeypatch):
    """The key stays AS ASKED -- three spellings are three set keys -- but the
    answers are equal and the third spelling costs no new walk."""
    seen = _spy(monkeypatch)

    with file_cache_scope() as frame:
        ab = iter_files(target, [PY, MD])
        ba = iter_files(target, [MD, PY])
        aab = iter_files(target, [PY, PY, MD])
        assert len(seen) == 2, (
            f"3 spellings of 2 globs must cost 2 walks; got {len(seen)}")
        assert set(frame) == {
            _key(target, (PY, MD)), _key(target, (MD, PY)), _key(target, (PY, PY, MD)),
            _key(target, (PY,)), _key(target, (MD,)),
        }, "the un-normalised set key was sorted or deduped"

    assert ab == ba == aab, "order or repetition changed the domain"
    assert _names(target, ab) == ["notes.md", "pkg/a.py", "tests/test_a.py"]
    assert len(ab) == len(set(ab)), "the union handed back a duplicated path"


# ------------------------------------------------------------------ behavior 9
def _register_glob_sets() -> list[tuple[str, ...]]:
    """Every `globs` list under `check.*` in the committed register, at any depth."""
    found: list[tuple[str, ...]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if (key == "globs" and isinstance(value, list)
                        and all(isinstance(item, str) for item in value)):
                    found.append(tuple(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path in sorted(GAPS_DIR.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")).get("check") or {})
    return sorted(set(found))


#: Measured 2026-09 on the committed 120-record register with this repo as target:
#: 100 distinct sets, widest 22 globs.  The 8 widest span 16 cases, of which 10 are
#: non-empty and 10 have a union STRICTLY larger than EVERY one of their per-glob
#: domains -- the controls that stop the equality below passing between empty lists.
#: Floors, not equalities: a shrinking register should say so loudly.
MIN_REGISTER_SETS = 90
MIN_WIDEST_SET = 10
WIDEST = 8
MIN_NON_EMPTY_CASES = 8
MIN_STRICT_CASES = 8


def test_b9_the_widest_committed_glob_sets_union_to_a_direct_enumeration():
    """Union identity on the register's real globs against the PRE-CHANGE code path:
    one direct, unmemoised whole-set enumeration, computed before any scope opens, so
    no frame can answer the oracle and no re-derivation of the new rule is involved.
    Bounded to the 8 widest sets -- `tests/test_iter219_domain_union_unit.py` carries
    the register-wide census; this is an independent spot check with its own oracle
    and its own controls.  Measured cost: 0.49s of enumeration."""
    sets = _register_glob_sets()
    assert len(sets) >= MIN_REGISTER_SETS, (
        f"only {len(sets)} distinct glob sets under check.*; the walk stopped seeing "
        "the register's nesting, or the register shrank -- re-derive this floor")
    widest = sorted(sets, key=lambda globs: (-len(globs), globs))[:WIDEST]
    assert len(widest[0]) >= MIN_WIDEST_SET, (
        f"widest committed set is {len(widest[0])} globs: the assembly is untested "
        "at width")

    assert _FILE_CACHE_STACK == [], "a leaked frame would answer the oracle"
    cases = [(globs, excl) for globs in widest for excl in (False, True)]
    direct = {case: checks._enumerate_files(REPO, list(case[0]), case[1])
              for case in cases}
    widest_per_glob = {
        (globs, glob, excl): checks._enumerate_files(REPO, [glob], excl)
        for globs, excl in cases for glob in globs
    }

    with file_cache_scope():
        assembled = {case: iter_files(REPO, list(case[0]), case[1]) for case in cases}

    mismatched = [case for case in cases if assembled[case] != direct[case]]
    assert mismatched == [], (
        f"{len(mismatched)} of {len(cases)} widest register sets do not equal their "
        f"per-glob union; first: {mismatched[:1]}")

    # Controls against a vacuous pass: empty lists are equal to each other, and a
    # union that is just one glob's domain proves nothing about the union step.
    non_empty = [case for case in cases if direct[case]]
    assert len(non_empty) >= MIN_NON_EMPTY_CASES, (
        f"only {len(non_empty)} of {len(cases)} widest cases have any files: equality "
        "here would be an agreement between empty lists")
    strict = [
        (globs, excl) for globs, excl in non_empty
        if all(len(direct[(globs, excl)]) > len(widest_per_glob[(globs, glob, excl)])
               for glob in globs)
    ]
    assert len(strict) >= MIN_STRICT_CASES, (
        f"only {len(strict)} cases are strictly larger than EVERY one of their "
        "per-glob domains, so the union step is not measurably doing anything")


# ----------------------------------------------------------------- behavior 10
def test_b10_the_per_glob_recursion_never_goes_through_the_module_global(
        target, monkeypatch):
    """`tools/scan_cost.py` counts scan cost by wrapping the module-global
    `checks.iter_files`.  If the per-glob step recursed through that NAME, one ask
    would be counted N+1 times and the committed census would move.  One ask must
    still be exactly one counted call."""
    counted: list[tuple[tuple[str, ...], bool]] = []
    real_iter_files = checks.iter_files

    def wrapper(target: pathlib.Path, globs: list[str],
                exclude_tests: bool = False) -> list[pathlib.Path]:
        counted.append((tuple(globs), exclude_tests))
        return real_iter_files(target, globs, exclude_tests)

    monkeypatch.setattr(checks, "iter_files", wrapper)
    walks = _spy(monkeypatch)

    with file_cache_scope():
        answer = checks.iter_files(target, [PY, MD, TS])

    assert counted == [((PY, MD, TS), False)], (
        f"the census wrapper saw {len(counted)} calls for one ask: {counted}")
    assert len(walks) == 3, "the per-glob step did not happen at all"
    assert _names(target, answer) == ["notes.md", "pkg/a.py", "tests/test_a.py",
                                      "web/c.ts"]


def test_the_stack_is_empty_between_tests():
    """A frame left open by any test in this module would make every later
    enumeration in this process answer from it."""
    assert _FILE_CACHE_STACK == []


# ==========================================================================
# ROUND 2 EXTENSIONS -- the previous round was cut short by the stage cap and
# left the module above behind.  Everything below is new: five behavior pins
# that the round-1 set does not reach, plus the acceptance criterion that the
# rewritten docstring must name a locator that RESOLVES.
# ==========================================================================


# ------------------------------------------------ behavior 2 (empty domains)
def test_b2_a_glob_that_matches_NOTHING_is_still_memoised(target, monkeypatch):
    """The truthiness trap.  A per-glob domain can legitimately be EMPTY, and an
    assembly that tests `if frame.get(key)` instead of `if key in frame` would
    re-walk that glob for every set that mentions it -- silently undoing the whole
    prize for exactly the globs (`**/*.rs`, `**/*.go`) the register aims at trees
    that do not have them.  Two sets sharing one empty glob must cost 3 walks."""
    seen = _spy(monkeypatch)
    absent = "**/*.rs"

    with file_cache_scope() as frame:
        first = iter_files(target, [PY, absent])
        assert len(seen) == 2, f"2 globs, 2 walks; got {[g for _, g, _ in seen]}"
        empty_key = _key(target, (absent,))
        assert empty_key in frame, (
            "a glob that matched nothing was not memoised at all, so every later set "
            "mentioning it re-walks the tree")
        assert frame[empty_key] == [], "the empty per-glob domain is not empty"

        second = iter_files(target, [MD, absent])
        assert len(seen) == 3, (
            "the empty per-glob domain was re-enumerated, so emptiness is being read "
            f"as absence: walks were {[g for _, g, _ in seen]}")

    assert _names(target, first) == ["pkg/a.py", "tests/test_a.py"]
    assert _names(target, second) == ["notes.md"]


# --------------------------------------------- behavior 3 (the other direction)
def test_b3_per_glob_asks_first_then_the_set_costs_NO_new_enumeration(
        target, monkeypatch):
    """Round 1 pins set-then-set.  This is the reverse and the shape a real scan
    hits constantly: single-glob rules run, then a wide rule asks for a set whose
    every glob is already memoised.  That set must be assembled from the frame with
    ZERO new walks, and each ask must still hand back its own list object."""
    seen = _spy(monkeypatch)

    with file_cache_scope():
        py = iter_files(target, [PY])
        md = iter_files(target, [MD])
        assert len(seen) == 2

        pair = iter_files(target, [PY, MD])
        assert len(seen) == 2, (
            "a set whose globs were ALREADY memoised individually re-walked the tree: "
            f"{[g for _, g, _ in seen]}")
        assert pair == sorted(set(py) | set(md)), (
            "the set assembled from existing per-glob entries is not their union")

        again = iter_files(target, [PY, MD])
        assert again == pair, "the repeat set ask changed the domain"
        assert again is not pair, "two asks handed back the SAME list object"
        assert len(seen) == 2


# ------------------------------------------- behavior 8 (overlap, not repetition)
def test_b8_two_DIFFERENT_globs_matching_the_same_file_dedupe_in_the_union(
        target, monkeypatch):
    """Round 1's duplicate case repeats ONE glob, which a `set` key would collapse
    on its own.  Two DISTINCT globs whose domains overlap is the case only the
    union step can get wrong (concatenation would double a path, and the ordering
    of a concatenated list is not `sorted`).  Oracle: one direct, unmemoised
    whole-set enumeration -- the pre-change code path, not a re-derived rule."""
    narrow = "pkg/*.py"
    assert _FILE_CACHE_STACK == [], "a leaked frame would answer the oracle"
    direct = checks._enumerate_files(target, [PY, narrow], False)
    narrow_only = checks._enumerate_files(target, [narrow], False)

    # Controls: if the narrow glob matched nothing, or matched everything the wide
    # one does, this case could not discriminate a dedupe from a concatenation.
    assert narrow_only, f"{narrow!r} matched nothing, so the overlap is not real"
    assert 0 < len(narrow_only) < len(direct), (
        f"{narrow!r} is not a strict subset of the pair's domain: "
        f"{len(narrow_only)} vs {len(direct)}")

    seen = _spy(monkeypatch)
    with file_cache_scope() as frame:
        assembled = iter_files(target, [PY, narrow])
        assert frame[_key(target, (PY, narrow))] == sorted(
            set(frame[_key(target, (PY,))]) | set(frame[_key(target, (narrow,))]))

    assert len(assembled) == len(set(assembled)), (
        f"an overlapping path was handed back twice: {_names(target, assembled)}")
    assert assembled == direct, (
        "the assembled overlap does not equal the whole-set enumeration it replaced")
    assert assembled == sorted(assembled), "the union is not in sorted order"
    assert len(seen) == 2, f"2 distinct globs, 2 walks; got {len(seen)}"


# ------------------------------------------------ behavior 7 (two targets, one scope)
def test_b7_the_memo_keys_on_the_TARGET_so_two_trees_never_share_a_domain(
        target, tmp_path_factory, monkeypatch):
    """`radar scan` takes a target, and one process can hold a frame while more than
    one tree is asked about.  If the per-glob entry keyed on the glob alone, the
    second tree would be answered with the first tree's files -- a silent
    cross-target fail-open that no single-target test can see."""
    other = tmp_path_factory.mktemp("other_tree")
    (other / "lib").mkdir()
    (other / "lib" / "z.py").write_text("def z():\n    return 3\n",
                                        encoding="utf-8")
    (other / "readme.md").write_text("# other\n", encoding="utf-8")

    seen = _spy(monkeypatch)
    with file_cache_scope() as frame:
        here = iter_files(target, [PY, MD])
        there = iter_files(other, [PY, MD])
        assert set(frame) == {
            _key(target, (PY, MD)), _key(target, (PY,)), _key(target, (MD,)),
            _key(other, (PY, MD)), _key(other, (PY,)), _key(other, (MD,)),
        }, "the frame does not hold one key set per target"

    assert _names(target, here) == ["notes.md", "pkg/a.py", "tests/test_a.py"]
    assert _names(other, there) == ["lib/z.py", "readme.md"], (
        "the second tree was answered out of the first tree's per-glob entry")
    assert set(here).isdisjoint(there), "two unrelated trees share a path"
    assert len(seen) == 4, (
        f"2 targets x 2 globs = 4 walks; got {len(seen)}: {[g for _, g, _ in seen]}")


# ------------------------------------------------ behavior 6 (no poisoned entry)
def test_b6_a_FAILED_enumeration_does_not_poison_the_set_key(target, monkeypatch):
    """The new failure mode of an assembled domain: the set key is written from N
    per-glob steps, so a step that RAISES halfway must leave nothing behind that a
    later ask could be answered from.  A frame that recorded a partial (or empty)
    set entry would hand a truncated domain to every later rule in the same scan --
    exactly the silent narrowing `exclude_tests` keys exist to prevent."""
    real = checks._enumerate_files
    attempted: list[tuple[str, ...]] = []

    def flaky(target_: pathlib.Path, globs: list[str],
              exclude_tests: bool) -> list[pathlib.Path]:
        attempted.append(tuple(globs))
        if tuple(globs) == (MD,):
            raise OSError("simulated tree-read failure")
        return real(target_, globs, exclude_tests)

    monkeypatch.setattr(checks, "_enumerate_files", flaky)
    with file_cache_scope() as frame:
        with pytest.raises(OSError):
            iter_files(target, [PY, MD])
        assert (MD,) in attempted, "the failing glob was never reached"

        monkeypatch.setattr(checks, "_enumerate_files", real)
        recovered = iter_files(target, [PY, MD])
        assert _names(target, recovered) == [
            "notes.md", "pkg/a.py", "tests/test_a.py"], (
            "after a failed assembly a later ask was answered from a partial entry")
        assert frame[_key(target, (PY, MD))] == recovered

    assert _FILE_CACHE_STACK == [], "the failed ask left a frame open"


# ------------------------------ acceptance criterion 3 (the locator must resolve)
def test_ac3_the_rewritten_docstring_names_a_TEST_THAT_RESOLVES():
    """Read through the PUBLIC `iter_files.__doc__`, not by reading the source file
    (the convention of `test_iter79_behavior.py` and `test_iter207_behavior.py`).

    The spec requires the un-normalised-key paragraph to be REWRITTEN rather than
    deleted, and to NAME the test that carries the union identity.  This product's
    core invariant is that a claim needs a RESOLVABLE locator, so a docstring that
    cites a test module which does not exist is the same defect the register itself
    would reject -- and it is invisible to every other test in the suite."""
    doc = iter_files.__doc__ or ""
    assert doc.strip(), "iter_files.__doc__ is empty, so this assertion is vacuous"
    flat = " ".join(doc.split())

    named = re.findall(r"tests/[\w./-]+\.py", flat)
    assert named, (
        "the docstring names no test file, so the union the assembly now RELIES on "
        f"has no locator: {flat[:300]!r}")
    missing = [name for name in named if not (REPO / name).is_file()]
    assert missing == [], (
        f"the docstring cites test module(s) that do not exist: {missing}")

    lowered = flat.lower()
    for fragment in ("union", "key"):
        assert fragment in lowered, (
            f"the rewritten paragraph never mentions {fragment!r}: {flat[:300]!r}")
