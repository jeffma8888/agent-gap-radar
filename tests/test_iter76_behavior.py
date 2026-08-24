"""Iteration 76 behaviors: `radar scan` walks each file domain at most once per scan.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source, the engineer's or the reviewer's notes, or a diff. Every assertion drives the
public interface the spec names (`iter_files`, `file_cache_scope`, `scan`, `render_scan`,
`scan_json`, the CLI `main`) and observes only returned file lists, document bytes, exit
codes, stderr bytes, or a COUNT of real filesystem walks.

Two counters, and the gap between them is the whole point of this iteration:

* `asks` counts calls to `checks.iter_files` -- how many times the rules ASK for a domain.
* `walks` counts `os.scandir` calls on the target ROOT -- how many times the filesystem is
  actually made to enumerate it. This is the STDLIB seam, chosen deliberately over any
  product-private helper so the count means the same thing on an implementation that
  memoises differently. It was validated by measurement, not by reading source: with the
  memo suppressed the two counters are EQUAL (9 and 9 on the fixture below), which is what
  makes `walks == distinct domains` a falsifiable claim rather than a restatement.

The fixture is AMPLIFIED on purpose -- eight rules ask 9 times over only 3 distinct
`(target, globs, exclude_tests)` triples -- and the amplification is asserted separately.
Without that guard, `walks == distinct_keys` would be equally green on a scan that walked
nothing at all, which is the vacuous-census shape this suite has been bitten by before.

Targets are built in `tmp_path`, which is NOT a git repo, so every tree here answers
through the walked branch. That is deliberate: the walked branch re-reads the filesystem on
every call, so a file added between two calls is visible unless the memo hid it, which is
what makes "the snapshot is consulted" falsifiable at all.

What this file does NOT prove, stated so a green dot cannot be mistaken for it: it cannot
show the documents are byte-identical to the documents the PREVIOUS tree produced, because
only one tree is importable from inside the suite. It pins byte-STABILITY (two scans, one
process), the one-newline tail, CLI-equals-API bytes, and -- the strongest in-suite form of
behavior 8 -- that the memoised and UN-memoised code paths emit the same bytes. The
cross-tree byte equality was measured out of band and is reported in the tester report.

Nothing under `gaps/` is read to make an assertion true -- that register is grown by an
unattended research pass, so a keyed expectation over it would go red against a CORRECT
register.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar import scan as scan_mod
from agent_gap_radar.checks import file_cache_scope, iter_files
from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import render_scan, scan, scan_json

MARKER = "GAPRADAR_ITER76_MARKER"
MITIGATION = "GAPRADAR_ITER76_MITIGATION"

PY_GLOBS = ["**/*.py"]
MD_GLOBS = ["**/*.md"]


# ---------------------------------------------------------------------------
# Fixtures. Local rather than imported from a sibling behavior file so this
# iteration's amplification (many rules, ONE glob set) is visible here.
# ---------------------------------------------------------------------------

def _check(cid, pattern=MARKER, mitigated=None, globs=None):
    globs = globs or PY_GLOBS
    chk = {
        "id": cid, "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": globs, "pattern": pattern},
        "fixtures": {"bad": {"a.py": pattern + "\n"}, "good": {"a.py": "clean\n"}},
    }
    if mitigated is not None:
        chk["mitigated_when"] = {"kind": "content_matches", "globs": globs,
                                 "pattern": mitigated}
    return chk


def _record(gid, check):
    return {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 3, "frequency": 3, "tractability": 3,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}],
        "check": check,
    }


#: Eight rules. Six ask the SAME triple, one adds the exclude_tests=True variant via
#: `mitigated_when`, one asks a different glob set -- 9 asks over 3 distinct domains.
AMPLIFIED_RECORDS = (
    [_record(f"GAP-7{i:02d}", _check(f"CHK-7{i:02d}")) for i in range(6)]
    + [_record("GAP-710", _check("CHK-710", pattern="NEVER_APPEARS_ANYWHERE",
                                 mitigated=MITIGATION)),
       _record("GAP-711", _check("CHK-711", globs=MD_GLOBS))]
)


def _register(root, records=AMPLIFIED_RECORDS):
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec, sort_keys=True),
                                             encoding="utf-8")
    return d


def _target(root):
    """A target tree of 5 modules, a test file and a markdown file, over 3 directories."""
    t = root / "target"
    (t / "app").mkdir(parents=True)
    (t / "app" / "loop.py").write_text(MARKER + "\n" + MITIGATION + "\n", encoding="utf-8")
    for i in range(4):
        (t / "app" / f"mod{i}.py").write_text(f"clean module {i}\n", encoding="utf-8")
    (t / "tests").mkdir()
    (t / "tests" / "test_x.py").write_text("clean\n", encoding="utf-8")
    (t / "notes.md").write_text("# not python\n", encoding="utf-8")
    return t


@pytest.fixture()
def amplified(tmp_path):
    """(register, target) where eight rules ask 9 times over 3 distinct domains."""
    return load_all(_register(tmp_path)), _target(tmp_path)


@pytest.fixture()
def tree(tmp_path):
    """A non-git tree: one code file, one test file, one markdown file."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    pass\n",
                                                  encoding="utf-8")
    (tmp_path / "notes.md").write_text("# not python\n", encoding="utf-8")
    return tmp_path


def _names(target, paths):
    return sorted(p.relative_to(target).as_posix() for p in paths)


class _Counts:
    def __init__(self) -> None:
        self.asks: list[tuple[str, tuple[str, ...], bool]] = []
        self.walks = 0

    def distinct_domains(self) -> int:
        return len(set(self.asks))

    def __repr__(self) -> str:  # shown on failure
        return (f"<asks={len(self.asks)} distinct={self.distinct_domains()} "
                f"walks={self.walks} keys={sorted(set(self.asks))}>")


def _spy(monkeypatch, target) -> _Counts:
    """Count domain ASKS and real filesystem WALKS of the target root."""
    counts = _Counts()

    real_iter = checks.iter_files

    def iter_spy(target_, globs, exclude_tests=False):
        counts.asks.append((str(target_), tuple(globs), bool(exclude_tests)))
        return real_iter(target_, globs, exclude_tests)

    root = str(pathlib.Path(target).resolve())
    real_scandir = os.scandir

    def scandir_spy(path="."):
        try:
            if str(pathlib.Path(path).resolve()) == root:
                counts.walks += 1
        except (OSError, TypeError, ValueError):
            pass
        return real_scandir(path)

    monkeypatch.setattr(checks, "iter_files", iter_spy)
    monkeypatch.setattr(os, "scandir", scandir_spy)
    return counts


@contextlib.contextmanager
def _no_memo():
    """A scope that memoises nothing -- the control for the whole iteration."""
    yield {}


def _suppress_memo(monkeypatch):
    """Patch the name the CALLER bound. `scan` imported `file_cache_scope` directly, so
    patching it on `checks` would leave the real scope in place and make the control
    vacuous -- a control that agrees with the treatment is the cheapest false pass there
    is, so the two sides are asserted to DIFFER wherever this is used."""
    monkeypatch.setattr(scan_mod, "file_cache_scope", _no_memo)


# ---------------------------------------------------------------------------
# Behavior 1 -- outside any scope, `iter_files` re-enumerates on every call.
# ---------------------------------------------------------------------------

def test_b1_outside_a_scope_a_new_file_is_seen(tree):
    """`iter_files` is a public entry point, so a caller outside a scan has to see the
    tree as it is NOW."""
    before = _names(tree, iter_files(tree, PY_GLOBS))
    (tree / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    after = _names(tree, iter_files(tree, PY_GLOBS))

    assert before == ["pkg/a.py", "tests/test_a.py"]
    assert after == ["pkg/a.py", "pkg/b.py", "tests/test_a.py"], (
        "an out-of-scope enumeration answered from a cache")


def test_b1_outside_a_scope_every_call_really_walks(tree, monkeypatch):
    counts = _spy(monkeypatch, tree)
    iter_files(tree, PY_GLOBS)
    iter_files(tree, PY_GLOBS)
    assert counts.walks == 2, counts


# ---------------------------------------------------------------------------
# Behavior 2 -- inside the scope, an identical triple answers from the snapshot.
# ---------------------------------------------------------------------------

def test_b2_inside_a_scope_a_file_added_mid_scope_is_not_seen(tree):
    with file_cache_scope():
        first = _names(tree, iter_files(tree, PY_GLOBS))
        (tree / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
        second = _names(tree, iter_files(tree, PY_GLOBS))

    assert first == ["pkg/a.py", "tests/test_a.py"]
    assert second == first, "the snapshot was not consulted: a mid-scope file appeared"


def test_b2_inside_a_scope_one_domain_walks_exactly_once(tree, monkeypatch):
    # Driven through `checks.iter_files` rather than the name imported at the top of this
    # module: the ask counter patches the module attribute, and a spy installed on the
    # module is not consulted by a caller that bound the function at import time. Same
    # public function either way -- but a control that cannot see the calls it is counting
    # reports zero asks and reads as a clean pass.
    counts = _spy(monkeypatch, tree)
    with file_cache_scope():
        a = _names(tree, checks.iter_files(tree, PY_GLOBS))
        b = _names(tree, checks.iter_files(tree, PY_GLOBS))
        c = _names(tree, checks.iter_files(tree, PY_GLOBS))

    assert a == b == c == ["pkg/a.py", "tests/test_a.py"]
    assert len(counts.asks) == 3, counts
    assert counts.walks == 1, counts


# ---------------------------------------------------------------------------
# Behavior 3 -- leaving the scope forgets everything.
# ---------------------------------------------------------------------------

def test_b3_leaving_the_scope_forgets_the_snapshot(tree):
    """The scope IS the invalidation -- there is no mtime or directory-hash check to be
    subtly wrong, so this is the only thing standing between a later scan and a stale
    file list."""
    with file_cache_scope():
        assert _names(tree, iter_files(tree, PY_GLOBS)) == ["pkg/a.py", "tests/test_a.py"]
    (tree / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")

    assert _names(tree, iter_files(tree, PY_GLOBS)) == [
        "pkg/a.py", "pkg/b.py", "tests/test_a.py"
    ], "a call after the scope answered from the closed snapshot"

    with file_cache_scope():
        assert _names(tree, iter_files(tree, PY_GLOBS)) == [
            "pkg/a.py", "pkg/b.py", "tests/test_a.py"
        ], "a later scope answered from an earlier one"


# ---------------------------------------------------------------------------
# Behavior 4 -- distinct triples do not collide.
# ---------------------------------------------------------------------------

def test_b4_two_glob_sets_get_their_own_answers(tree, monkeypatch):
    counts = _spy(monkeypatch, tree)
    with file_cache_scope():
        py = _names(tree, iter_files(tree, PY_GLOBS))
        md = _names(tree, iter_files(tree, MD_GLOBS))
        assert _names(tree, iter_files(tree, PY_GLOBS)) == py

    assert py == ["pkg/a.py", "tests/test_a.py"]
    assert md == ["notes.md"], "one glob set was answered with another's file list"
    assert counts.walks == 2, counts


def test_b4_the_two_exclude_tests_answers_do_not_share_an_entry(tree, monkeypatch):
    """The fail-open this key exists to prevent: a globs-only key would hand the
    narrowed domain to a rule that asked for the wide one, so a gap signature living
    in a test file would become invisible."""
    counts = _spy(monkeypatch, tree)
    with file_cache_scope():
        wide = _names(tree, iter_files(tree, PY_GLOBS))
        narrow = _names(tree, iter_files(tree, PY_GLOBS, exclude_tests=True))
        assert _names(tree, iter_files(tree, PY_GLOBS)) == wide
        assert _names(tree, iter_files(tree, PY_GLOBS, exclude_tests=True)) == narrow

    assert wide == ["pkg/a.py", "tests/test_a.py"]
    assert narrow == ["pkg/a.py"], "exclude_tests did not narrow the domain"
    assert counts.walks == 2, counts


# ---------------------------------------------------------------------------
# Behavior 5 -- the returned list is never shared.
# ---------------------------------------------------------------------------

def test_b5_mutating_one_result_does_not_change_a_later_identical_call(tree):
    """A caller that sorted or truncated the result in place would silently narrow
    every later rule asking the same question."""
    with file_cache_scope():
        first = iter_files(tree, PY_GLOBS)
        first.clear()
        first.append(tree / "fabricated.py")
        second = iter_files(tree, PY_GLOBS)

        assert second is not first
        assert _names(tree, second) == ["pkg/a.py", "tests/test_a.py"], (
            "mutating one result corrupted the snapshot")


# ---------------------------------------------------------------------------
# Behavior 6 -- nesting.
# ---------------------------------------------------------------------------

def test_b6_an_inner_scope_is_its_own_snapshot_and_the_outer_survives(tree, monkeypatch):
    """An inner scan is a DIFFERENT scan: it takes its own snapshot, and leaving it must
    leave the enclosing snapshot intact rather than emptying it."""
    counts = _spy(monkeypatch, tree)
    with file_cache_scope():
        outer_view = _names(tree, iter_files(tree, PY_GLOBS))
        (tree / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")

        with file_cache_scope():
            inner_view = _names(tree, iter_files(tree, PY_GLOBS))
            assert inner_view == ["pkg/a.py", "pkg/b.py", "tests/test_a.py"], (
                "the inner scope inherited the outer snapshot")

        assert _names(tree, iter_files(tree, PY_GLOBS)) == outer_view, (
            "leaving the inner scope emptied or replaced the outer snapshot")

    assert outer_view == ["pkg/a.py", "tests/test_a.py"]
    assert counts.walks == 2, counts


# ---------------------------------------------------------------------------
# Behavior 7 -- an exception inside the scope still pops the frame.
# ---------------------------------------------------------------------------

def test_b7_an_exception_inside_the_scope_does_not_leak_the_snapshot(tree):
    """A leaked frame would silently become a process-lifetime cache for the next scan
    -- the one failure mode this design exists to avoid. Asserted BLACK-BOX: after the
    exception a newly added file must be visible again."""
    with pytest.raises(RuntimeError, match="mid-scan failure"):
        with file_cache_scope():
            assert _names(tree, iter_files(tree, PY_GLOBS)) == ["pkg/a.py",
                                                                "tests/test_a.py"]
            raise RuntimeError("mid-scan failure")

    (tree / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    assert _names(tree, iter_files(tree, PY_GLOBS)) == [
        "pkg/a.py", "pkg/b.py", "tests/test_a.py"
    ], "a frame survived an exception and answered a later call"


# ---------------------------------------------------------------------------
# Behavior 8 -- the feature: one walk per domain per scan, and the bytes do not move.
# ---------------------------------------------------------------------------

def test_b8_the_fixture_is_amplified_before_anything_is_asserted(amplified, monkeypatch):
    """Non-vacuity guard. `walks == distinct_domains` is also what a scan that walked
    NOTHING would report, so the amplification has to be measured too."""
    gaps, target = amplified
    counts = _spy(monkeypatch, target)
    scan(gaps, target)

    assert len(counts.asks) == 9, counts
    assert counts.distinct_domains() == 3, counts
    assert len(counts.asks) >= 3 * counts.distinct_domains(), counts


def test_b8_each_domain_is_walked_at_most_once_per_scan(amplified, monkeypatch):
    """The feature. 9 asks over 3 domains must produce 3 walks, not 9."""
    gaps, target = amplified
    counts = _spy(monkeypatch, target)
    scan(gaps, target)

    assert counts.walks == counts.distinct_domains(), counts
    assert counts.walks == 3, counts


def test_b8_the_memo_off_control_really_walks_once_per_ask(amplified, monkeypatch):
    """Proves the control is NON-VACUOUS: with the scope suppressed the two counters
    are equal, which is what makes the assertion above falsifiable."""
    gaps, target = amplified
    _suppress_memo(monkeypatch)
    counts = _spy(monkeypatch, target)
    scan(gaps, target)

    assert counts.walks == len(counts.asks) == 9, counts


def test_b8_memoised_and_unmemoised_scans_emit_identical_bytes(amplified, monkeypatch):
    """The strongest in-suite form of "output must stay byte-identical": the memo is a
    pure optimisation, so the two code paths must agree on every byte of both
    documents. A memo that returned a stale or mis-keyed list fails HERE."""
    gaps, target = amplified
    memoised_md = render_scan(scan(gaps, target))
    memoised_json = scan_json(scan(gaps, target))

    _suppress_memo(monkeypatch)
    plain_md = render_scan(scan(gaps, target))
    plain_json = scan_json(scan(gaps, target))

    assert memoised_md == plain_md
    assert memoised_json == plain_json


def test_b8_the_fixture_spans_three_verdicts(amplified):
    """Non-vacuity for the byte assertions: the documents are not one verdict repeated."""
    gaps, target = amplified
    got = sorted({f.outcome.verdict.value for f in scan(gaps, target).findings})
    assert got == ["ABSENT", "MANUAL", "PRESENT"], got


def test_b8_render_scan_is_byte_stable_across_two_scans(amplified):
    gaps, target = amplified
    assert render_scan(scan(gaps, target)) == render_scan(scan(gaps, target))


def test_b8_scan_json_is_byte_stable_across_two_scans(amplified):
    gaps, target = amplified
    assert scan_json(scan(gaps, target)) == scan_json(scan(gaps, target))


def test_b8_both_documents_end_in_exactly_one_newline(amplified):
    gaps, target = amplified
    result = scan(gaps, target)
    for name, doc in (("render_scan", render_scan(result)),
                      ("scan_json", scan_json(result))):
        assert doc.endswith("\n"), name
        assert not doc.endswith("\n\n"), name


def test_b8_cli_stdout_is_byte_identical_to_the_api_document(tmp_path, capsys):
    """The memo sits under the CLI, so what the user sees must not have moved."""
    reg = _register(tmp_path)
    target = _target(tmp_path)
    rc = main(["scan", str(target), "--gaps", str(reg)])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    assert cap.err == ""
    assert cap.out == render_scan(scan(load_all(reg), target))


def test_b8_cli_json_stdout_is_byte_identical_to_scan_json(tmp_path, capsys):
    reg = _register(tmp_path)
    target = _target(tmp_path)
    rc = main(["scan", str(target), "--gaps", str(reg), "--json"])
    cap = capsys.readouterr()
    assert rc == 0, cap.err
    assert cap.err == ""
    assert cap.out == scan_json(scan(load_all(reg), target))
    json.loads(cap.out)
