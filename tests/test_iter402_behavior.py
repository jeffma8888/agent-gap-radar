"""Iteration 402: retire a duplicated span oracle and de-duplicate a live corpus.

WHY THIS MODULE EXISTS.  Two suite-time cuts are only honest if the proof they
remove is really proved elsewhere, so this module pins the premises:

* `test_iter364_behavior::test_b9_span_equality_over_frozen_corpus` was deleted
  because `test_iter245_behavior::test_b3_folded_arm_span_lists_equal_raw_arm_span_lists`
  proves the same statement: the same classifier, the same register patterns and the
  same `FROZEN_COMMIT` corpus.  Behavior 3 below holds 364's rewrite and corpus pin
  equal to 245's, so if they ever diverge the retirement turns red instead of silently
  losing coverage.
* `test_iter370_behavior`'s live corpus now drops every text that is byte-identical
  to a frozen-corpus text, because 245 b3 already proves those.  Behaviors 5 and 7
  check that this is a SUBTRACTION and not an emptying.
* Behavior 4 checks that the surviving oracle still discriminates: a rewrite that is
  not span-equivalent makes 245 b3 raise.

Costs, as COUNTS: no scan.  The guard runs no regex over a corpus.  Behavior 4 runs
chunk 0 over a corpus of three in-memory texts, twice.  Two `git archive`
extractions of the frozen tree are made: one for this module's independent frozen
set and one inside 370's imported fixture.  Offline, deterministic, no network;
writes land in pytest-managed temporary directories.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import test_iter245_behavior as t245
import test_iter364_behavior as t364
import test_iter370_behavior as t370
from agent_gap_radar import checks
from test_iter370_behavior import repo_ascii_texts  # noqa: F401 -- the fixture under test

REPO = pathlib.Path(__file__).resolve().parents[1]

#: The real classifier, captured at import so the broken arm can wrap it.
REAL = checks._folded_fast_path


# --- behavior 3: the retired oracle was the surviving one, restated -----------

def test_b3_364_rewrite_is_the_245_rewrite_for_every_register_pattern():
    patterns = t245._register_patterns()
    assert patterns, "the register yields no patterns"
    assert t364._register_patterns is t245._register_patterns
    diverged = [p for p in patterns if t364.f(p) != checks._folded_fast_path(p)]
    assert diverged == [], diverged[:3]


def test_b3_both_modules_pin_the_same_frozen_corpus():
    assert t364.FROZEN_COMMIT == t245.FROZEN_COMMIT == "0356b8b"


def test_b1_the_duplicate_oracle_is_gone_and_the_survivor_remains():
    assert not hasattr(t364, "test_b9_span_equality_over_frozen_corpus")
    assert callable(t364.test_b9_named_span_pairs)
    assert callable(t245.test_b3_folded_arm_span_lists_equal_raw_arm_span_lists)


# --- behavior 4: the surviving oracle still discriminates ----------------------

def _broken(pattern: str) -> str | None:
    """Accept exactly what the real classifier accepts, but demand a trailing NUL.

    The body is kept, so the rewrite is close to the real one.  It is still not
    span-equivalent: it can never match a text that contains no NUL.
    """
    rewritten = REAL(pattern)
    if rewritten is None:
        return None
    head = re.match(r"\(\?[a-zA-Z]+\)", rewritten)
    flags = head.group(0) if head else ""
    return f"{flags}(?:{rewritten[len(flags):]})\\x00"


def _tiny_corpus() -> list[tuple[str, str]]:
    """Three in-memory ASCII texts built from chunk 0's own sources.

    They are derived from the register, so register growth that reshuffles chunk 0
    cannot leave them matching nothing.  The upper-case and mixed-case copies are
    what make the fold actually do work.
    """
    joined = "\n".join(t245._accepted_patterns()[0::t245.CHUNKS])
    return [("joined", joined), ("upper", joined.upper()), ("title", joined.title())]


def test_b4_tiny_corpus_is_matched_by_chunk_zero():
    corpus = _tiny_corpus()
    assert all(text.isascii() for _, text in corpus)
    hits = sum(1 for p in t245._accepted_patterns()[0::t245.CHUNKS]
               for _, text in corpus if re.search(p, text, re.MULTILINE))
    assert hits > 0, "the tiny corpus matches no chunk-0 pattern; behavior 4 is vacuous"


def test_b4_real_classifier_passes_the_surviving_oracle():
    t245.test_b3_folded_arm_span_lists_equal_raw_arm_span_lists(0, _tiny_corpus())


def test_b4_broken_rewrite_reds_the_surviving_oracle(monkeypatch):
    monkeypatch.setattr(checks, "_folded_fast_path", _broken)
    with pytest.raises(AssertionError, match="span divergence"):
        t245.test_b3_folded_arm_span_lists_equal_raw_arm_span_lists(0, _tiny_corpus())


# --- behaviors 5 and 7: 370's corpus is subtracted, not emptied ---------------

def _ascii_walk(root: pathlib.Path, tops: tuple[str, ...]) -> list[tuple[str, str]]:
    """An independent restatement of the HEAD-style walk, so a bug in 370's helper
    cannot vouch for itself."""
    out = []
    for top in tops:
        for path in sorted((root / top).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if text.isascii():
                out.append((str(path.relative_to(root)), text))
    return out


@pytest.fixture(scope="module")
def frozen_texts(tmp_path_factory) -> frozenset[str]:
    root = t245._extract(t245.FROZEN_COMMIT,
                         tmp_path_factory.mktemp("frozen402") / t245.FROZEN_DIR_NAME)
    texts = frozenset(text for _, text in _ascii_walk(root, ("",)))
    assert len(texts) > 100, len(texts)
    return texts


def _live_part(fixture: list[tuple[str, str]]) -> list[tuple[str, str]]:
    synthetic = t370.SYNTHETIC_TEXTS
    assert fixture[len(fixture) - len(synthetic):] == synthetic, (
        "SYNTHETIC_TEXTS are no longer appended in full at the tail")
    return fixture[:len(fixture) - len(synthetic)]


def test_b5_no_live_text_equals_a_frozen_text(repo_ascii_texts, frozen_texts):
    live = _live_part(repo_ascii_texts)
    assert len(live) > 100, len(live)
    assert [name for name, text in live if text in frozen_texts] == []


def test_b7_live_corpus_is_a_nonempty_strict_subset_of_the_head_walk(repo_ascii_texts):
    live = set(_live_part(repo_ascii_texts))
    walk = set(_ascii_walk(REPO, ("src", "tests")))
    assert live, "the live corpus was emptied"
    assert live < walk, sorted(n for n, _ in live - walk)[:3]


def test_b7_only_frozen_identical_files_were_dropped(repo_ascii_texts, frozen_texts):
    live = set(_live_part(repo_ascii_texts))
    dropped = [(n, t) for n, t in _ascii_walk(REPO, ("src", "tests")) if (n, t) not in live]
    assert dropped, "nothing was subtracted"
    # Covers `src/` and `tests/` alike: no file leaves unless 245 b3 proves its text.
    assert [n for n, t in dropped if t not in frozen_texts] == []


def test_no_absolute_machine_path_in_this_module():
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    for needle in ("/" + "Users" + "/", "/" + "home" + "/", "C" + ":\\"):
        assert needle not in source, needle
