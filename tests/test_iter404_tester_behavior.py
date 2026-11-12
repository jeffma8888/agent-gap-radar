"""Iteration 404 (tester): black-box checks on the re-landed iteration-402 trim.

The engineer's `test_iter402_behavior.py` pins the premises from the inside.  This
module checks the same spec from the outside: the node ids that pytest actually
COLLECTS (behaviors 1, 2, 6), a second, independent non-span-equivalent rewrite
that must red the surviving oracle (behavior 4), the subtracted corpus measured
against an independent `git archive` of the frozen tree (behaviors 5, 7), and a
byte-stable `radar report` (behavior 8).

TIME-BOMB DISCIPLINE (what killed iteration 403): nothing here pins a moving commit
sha, compares output against a fixed tree, or names a `path:N` locator.  The only
sha literal is the historical frozen corpus `0356b8b`, which never moves.

Offline, deterministic, no network; writes land in pytest-managed temp dirs.
"""

from __future__ import annotations

import contextlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tarfile

import pytest

import test_iter245_behavior as t245
import test_iter370_behavior as t370
from agent_gap_radar import checks
from agent_gap_radar.cli import main
from test_iter370_behavior import repo_ascii_texts  # noqa: F401 -- fixture under test

REPO = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
FROZEN = "0356b8b"
REAL = checks._folded_fast_path


# --- behaviors 1, 2, 6: what pytest really collects ---------------------------

@pytest.fixture(scope="module")
def collected() -> list[str]:
    """Node ids of the three touched oracle modules, collected in a child pytest
    with addopts cleared (the repo's `-q` addopts would print only file counts)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "-o", "addopts=", "tests/test_iter364_behavior.py",
         "tests/test_iter245_behavior.py", "tests/test_iter370_behavior.py"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    nodes = [ln.strip() for ln in proc.stdout.splitlines() if "::" in ln]
    assert len(nodes) > 50, proc.stdout[-2000:]
    return nodes


def _named(nodes: list[str], module: str, test: str) -> list[str]:
    return [n for n in nodes if n.startswith(f"tests/{module}::{test}")]


def test_b1_retired_frozen_corpus_node_is_not_collected(collected):
    assert _named(collected, "test_iter364_behavior.py",
                  "test_b9_span_equality_over_frozen_corpus") == []
    assert not any("test_b9_span_equality_over_frozen_corpus" in n for n in collected)


def test_b1_named_span_pairs_nodes_survive(collected):
    pairs = _named(collected, "test_iter364_behavior.py", "test_b9_named_span_pairs[")
    assert len(pairs) >= 1, pairs


def test_b2_245_b3_collects_exactly_chunks_0_to_7(collected):
    name = "test_b3_folded_arm_span_lists_equal_raw_arm_span_lists"
    got = sorted(_named(collected, "test_iter245_behavior.py", name + "["))
    want = sorted(f"tests/test_iter245_behavior.py::{name}[{k}]" for k in range(8))
    assert got == want, got


def test_b6_370_b7_collects_exactly_chunks_0_to_7_and_the_vacuity_guard(collected):
    name = "test_b7_live_register_span_differential"
    got = sorted(_named(collected, "test_iter370_behavior.py", name + "["))
    want = sorted(f"tests/test_iter370_behavior.py::{name}[{k}]" for k in range(8))
    assert got == want, got
    assert _named(collected, "test_iter370_behavior.py",
                  "test_b7_differential_is_not_vacuous") == [
        "tests/test_iter370_behavior.py::test_b7_differential_is_not_vacuous"]


# --- behavior 3: the 402 module is a guard, not a scan -------------------------

def test_b3_402_module_runs_no_scan_and_pins_the_frozen_corpus():
    source = (TESTS / "test_iter402_behavior.py").read_text(encoding="utf-8")
    assert "agent_gap_radar.cli" not in source
    assert "subprocess" not in source
    assert "t364.f(p) != checks._folded_fast_path(p)" in source
    assert '== "0356b8b"' in source


# --- behavior 4: a second broken rewrite reds the surviving oracle ------------

def _start_anchored(pattern: str) -> str | None:
    """The real rewrite, pinned to the start of the text with `\\A`.  The body is
    kept, so every match it reports is a real one -- but every mid-text match is
    lost, a POSITION fault (iteration 402's guard uses a CONTENT fault).

    Note: merely stripping the inline-flag group is NOT a fault, because the
    folded arm is matched against `text.lower()`; that mutation survives 245 b3.
    """
    rewritten = REAL(pattern)
    if rewritten is None:
        return None
    head = re.match(r"\(\?[a-zA-Z]+\)", rewritten)
    flags = head.group(0) if head else ""
    return f"{flags}\\A(?:{rewritten[len(flags):]})"


def _corpus() -> list[tuple[str, str]]:
    joined = "\n".join(t245._accepted_patterns()[0::t245.CHUNKS])
    return [("lower", joined.lower()), ("upper", joined.upper())]


def test_b4_start_anchored_rewrite_is_caught(monkeypatch):
    monkeypatch.setattr(checks, "_folded_fast_path", _start_anchored)
    with pytest.raises(AssertionError, match="span divergence"):
        t245.test_b3_folded_arm_span_lists_equal_raw_arm_span_lists(0, _corpus())


def test_b4_real_rewrite_passes_the_same_corpus():
    assert checks._folded_fast_path is REAL
    t245.test_b3_folded_arm_span_lists_equal_raw_arm_span_lists(0, _corpus())


# --- behaviors 5, 7: subtraction measured against an independent archive -------

@pytest.fixture(scope="module")
def frozen_archive_texts(tmp_path_factory) -> frozenset[str]:
    probe = subprocess.run(["git", "cat-file", "-e", f"{FROZEN}^{{commit}}"],
                           cwd=REPO, capture_output=True)
    if probe.returncode != 0:
        pytest.skip("frozen corpus commit not present (shallow clone)")
    dest = tmp_path_factory.mktemp("frozen404")
    tar_path = dest / "frozen.tar"
    with tar_path.open("wb") as fh:
        subprocess.run(["git", "archive", "--format=tar", FROZEN], cwd=REPO,
                       stdout=fh, check=True)
    texts = set()
    with tarfile.open(tar_path) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            raw = tar.extractfile(member).read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if text.isascii():
                texts.add(text)
    assert len(texts) > 100, len(texts)
    return frozenset(texts)


def _split(fixture):
    n = len(t370.SYNTHETIC_TEXTS)
    return fixture[:len(fixture) - n], fixture[len(fixture) - n:]


def test_b5_synthetics_appended_in_full_and_corpus_is_large(repo_ascii_texts):
    live, tail = _split(repo_ascii_texts)
    assert tail == t370.SYNTHETIC_TEXTS
    assert len(repo_ascii_texts) > 100
    assert len(live) > 0


def test_b5_no_live_text_is_a_frozen_archive_text(repo_ascii_texts, frozen_archive_texts):
    live, _ = _split(repo_ascii_texts)
    assert [name for name, text in live if text in frozen_archive_texts] == []


def test_b7_live_texts_are_real_repo_files_under_src_or_tests(repo_ascii_texts):
    live, _ = _split(repo_ascii_texts)
    assert live
    for name, text in live:
        top = pathlib.PurePath(name).parts[0]
        assert top in ("src", "tests"), name
        assert (REPO / name).read_text(encoding="utf-8") == text, name


def test_b7_a_live_unique_file_is_kept(repo_ascii_texts, frozen_archive_texts):
    """This very module did not exist in the frozen tree, so it must be kept."""
    live, _ = _split(repo_ascii_texts)
    me = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert me not in frozen_archive_texts
    assert me in {text for _, text in live}


# --- behavior 8: radar report stays a byte-stable document ---------------------

def _report() -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(["report", str(REPO / "gaps")])
        except SystemExit as exc:
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def test_b8_report_is_byte_stable_and_ends_in_one_newline():
    first, second = _report(), _report()
    assert first == second
    rc, out, err = first
    assert rc == 0 and err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert "Records:" in out


# --- acceptance: no time bombs, no machine paths -------------------------------

_SHA = re.compile(r"""["'`]([0-9a-f]{7,40})["'`]""")
_LOCATOR = re.compile(r"(?:DIRECTIONS|PRODUCT)\.md:\d")


@pytest.mark.parametrize("module", ["test_iter402_behavior.py", "test_iter404_tester_behavior.py"])
def test_no_moving_sha_or_rewritten_file_locator(module: str):
    source = (TESTS / module).read_text(encoding="utf-8")
    shas = {s for s in _SHA.findall(source) if re.search(r"\d", s) and re.search(r"[a-f]", s)}
    assert shas <= {FROZEN}, sorted(shas)
    assert _LOCATOR.findall(source) == []


@pytest.mark.parametrize("module", ["test_iter402_behavior.py", "test_iter404_tester_behavior.py"])
def test_no_absolute_machine_path(module: str):
    source = (TESTS / module).read_text(encoding="utf-8")
    for needle in ("/" + "Users" + "/", "/" + "home" + "/", "C" + ":\\"):
        assert needle not in source, needle
