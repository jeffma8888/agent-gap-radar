"""Iteration 365 behaviors: the search-cap paragraph records the decode-skip decision.

Row 114's decision (iteration 342, "count and disclose") is published in
``docs/CONSUMER_CONTRACT.md``'s search-cap paragraph: files the evaluator
skips are COUNTED in ``skipped_files`` but not WEIGHED, so an ``ABSENT`` with a
non-zero tally is a narrower claim. The decided behavior is pinned in-process.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-5. No test here reads the implementation
source, the engineer's or the reviewer's notes, or any diff. Behaviors are
measured by reading the published contract and by calling the public
``run_check`` API (already used by existing tests under ``tests/``).

Spec ambiguity, recorded: EB2/EB3 mandate the literals ``non-UTF-8`` and
``skipped_files > 0``, but the committed iteration-203 figure brake forbids
any digit in this paragraph other than the file cap, and EB4 requires that
brake to pass unchanged. The two criteria cannot both hold, so the shipped
digit-free equivalents (``not decodable as text``, ``non-zero``) are pinned
here and the brake wins.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

from agent_gap_radar.checks import Verdict, run_check

REPO = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO / "docs" / "CONSUMER_CONTRACT.md"
ANCHOR = "**The search cap and the one verdict it can change.**"
MAX_FILE_BYTES = 512 * 1024

# The paragraph as it stood before this iteration, ending at its old last
# sentence. EB4: every one of these sentences survives byte-for-byte and the
# new text is appended AFTER the last one.
PRIOR_PARAGRAPH = """\
**The search cap and the one verdict it can change.** A content rule reads at
most 4000 files per evaluation (`MAX_SCAN_FILES`), and that bound is per rule on
one record, not per scan and not per target: a rule whose domain is larger
answers over the head of it. Exactly one verdict transition can follow from that
cut: ABSENT -> UNKNOWN, and it is the only place the cut is WEIGHED. It fires
where the gap signature was not found over a domain the cap cut AND a mitigation
was found -- the case that would otherwise read ABSENT -- because ABSENT is the
only one of the five verdicts that claims safety, and a claim is only as wide as
the search behind it. PRESENT, MANUAL and NOT_APPLICABLE are decided WITHOUT
consulting the cut, so where a rule's own positive is an ABSENCE
(`content_absent`, `not`) a cut head can read PRESENT where a full read would
not: the cap can over-report a gap silently, and only ABSENT is protected. The
mitigation's locators are dropped along with that verdict, on purpose: printed
beside a verdict that no longer claims safety they read as evidence of safety.
An UNKNOWN reached this way says the search was incomplete over this target;
it never says "no gap here". A gate must treat it as un-answered -- the same
as an UNKNOWN whose check never executed -- and never as a pass; the finding's
`reason` is where the cut is named, since no payload key separates the two
causes yet."""
PRIOR_LAST_SENTENCE = "no payload key separates the two\ncauses yet."


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _paragraph() -> str:
    """The contract block that begins at ANCHOR and runs to the next blank line."""
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    start = text.index(ANCHOR)
    end = text.find("\n\n", start)
    return text[start:] if end == -1 else text[start:end]


def _flat(text: str) -> str:
    """Collapse line wrapping so phrases split across lines still match."""
    return re.sub(r"\s+", " ", text).strip()


def _appended() -> str:
    """Only the text this iteration added after the prior last sentence."""
    para = _paragraph()
    assert para.startswith(PRIOR_PARAGRAPH)
    return _flat(para[len(PRIOR_PARAGRAPH):])


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;])\s+(?=[A-Z`])", _flat(text)) if s]


def _check_dict() -> dict:
    return {
        "id": "CHK-365",
        "rationale": "r",
        "manual_question": "q?",
        "present_when": {
            "kind": "content_matches",
            "globs": ["code/*.py"],
            "pattern": "SIGNATURE_X",
        },
        "mitigated_when": {
            "kind": "content_matches",
            "globs": ["guard/*.py"],
            "pattern": "MITIGATION_Y",
        },
    }


def _fixture(root: pathlib.Path, *, big_bytes: int) -> pathlib.Path:
    target = root / "target"
    (target / "code").mkdir(parents=True)
    (target / "guard").mkdir()
    head = "SIGNATURE_X = 1\n"
    pad_lines = max(0, big_bytes - len(head)) // 32 + 1
    body = head + ("# " + "p" * 29 + "\n") * pad_lines
    if big_bytes <= 1024:
        body = head
    (target / "code" / "big.py").write_text(body, encoding="utf-8")
    (target / "code" / "small.py").write_text("VALUE = 2\n", encoding="utf-8")
    (target / "guard" / "g.py").write_text("MITIGATION_Y = 1\n", encoding="utf-8")
    # git-initialised, local only: no remote, no network.
    subprocess.run(["git", "init", "-q", str(target)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(target), "add", "-A"], check=True,
                   capture_output=True)
    return target


# ---------------------------------------------------------------------------
# EB1 -- the paragraph names the disclosing key
# ---------------------------------------------------------------------------

def test_eb1_paragraph_names_skipped_files_key() -> None:
    para = _paragraph()
    assert para.startswith(ANCHOR)
    assert "skipped_files" in para
    # The key is named in the APPENDED text, not only somewhere else.
    assert "skipped_files" in _appended()


def test_eb1_paragraph_is_sliced_at_first_blank_line() -> None:
    para = _paragraph()
    assert "\n\n" not in para
    assert para.count(ANCHOR) == 1


# ---------------------------------------------------------------------------
# EB2 -- COUNTED, not WEIGHED, applied to decode skips, three causes named
# ---------------------------------------------------------------------------

def test_eb2_counted_not_weighed_phrase_present() -> None:
    assert "COUNTED, not WEIGHED" in _flat(_paragraph())


@pytest.mark.parametrize("cause", ["oversized", "not decodable as text", "unreadable"])
def test_eb2_names_each_skip_cause(cause: str) -> None:
    assert cause in _appended(), cause


def test_eb2_phrase_applies_to_skipped_files_with_all_causes() -> None:
    appended = _appended()
    i = appended.index("COUNTED, not WEIGHED")
    # The three causes follow the phrase within the same sentence span.
    tail = appended[i:i + 300]
    for cause in ("oversized", "not decodable as text", "unreadable"):
        assert cause in tail, (cause, tail)
    assert "skip" in tail


# ---------------------------------------------------------------------------
# EB3 -- ABSENT with a non-zero tally is a narrower claim; not downgraded
# ---------------------------------------------------------------------------

def test_eb3_absent_with_nonzero_tally_sentence() -> None:
    hits = [s for s in _sentences(_appended())
            if "ABSENT" in s and "skipped_files" in s and "non-zero" in s]
    assert len(hits) == 1, hits
    sentence = hits[0]
    assert "fewer files than the domain held" in sentence
    assert "must check that key itself" in sentence


def test_eb3_not_downgraded_sentence_gives_noisy_gate_reason() -> None:
    hits = [s for s in _sentences(_appended()) if "not downgraded" in s]
    assert len(hits) == 1, hits
    sentence = hits[0]
    assert "UNKNOWN" in sentence
    assert "noisy" in sentence
    assert re.search(r"vendor", sentence), sentence


def test_eb3_new_text_carries_no_digit() -> None:
    # The iteration-203 brake allows only the file-cap figure in this
    # paragraph; the appended text must therefore be digit-free.
    assert re.search(r"\d", _appended()) is None, _appended()


# ---------------------------------------------------------------------------
# EB4 -- prior sentences intact byte-for-byte, new text appended after them
# ---------------------------------------------------------------------------

def test_eb4_prior_paragraph_is_a_byte_prefix() -> None:
    para = _paragraph()
    assert para.startswith(PRIOR_PARAGRAPH)
    assert len(para) > len(PRIOR_PARAGRAPH)


def test_eb4_new_text_follows_prior_last_sentence() -> None:
    para = _paragraph()
    cut = para.index(PRIOR_LAST_SENTENCE) + len(PRIOR_LAST_SENTENCE)
    assert para.count(PRIOR_LAST_SENTENCE) == 1
    after = para[cut:]
    assert after.startswith(" ") or after.startswith("\n")
    assert "COUNTED, not WEIGHED" in after
    assert "COUNTED, not WEIGHED" not in para[:cut]


def test_eb4_paragraph_ends_on_full_stop() -> None:
    assert _paragraph().rstrip().endswith(".")


# ---------------------------------------------------------------------------
# EB5 -- the decided behavior: decode skip is counted, verdict not moved
# ---------------------------------------------------------------------------

def test_eb5_oversized_signature_file_reads_absent_with_one_skip(tmp_path) -> None:
    target = _fixture(tmp_path, big_bytes=MAX_FILE_BYTES + 4096)
    assert (target / "code" / "big.py").stat().st_size > MAX_FILE_BYTES
    assert (target / "code" / "big.py").read_text(encoding="utf-8").startswith(
        "SIGNATURE_X = 1\n")
    outcome = run_check(_check_dict(), target)
    assert outcome.verdict is Verdict.ABSENT, outcome.verdict
    assert outcome.skipped_files == 1, outcome.skipped_files
    assert list(outcome.locations) == ["guard/g.py:1"], outcome.locations


def test_eb5_control_small_signature_file_reads_manual_with_no_skip(tmp_path) -> None:
    target = _fixture(tmp_path, big_bytes=100)
    assert (target / "code" / "big.py").stat().st_size < 1024
    outcome = run_check(_check_dict(), target)
    assert outcome.verdict is Verdict.MANUAL, outcome.verdict
    assert outcome.skipped_files == 0, outcome.skipped_files


def test_eb5_arms_differ_only_by_the_skip(tmp_path) -> None:
    big = run_check(_check_dict(), _fixture(tmp_path / "a", big_bytes=MAX_FILE_BYTES + 1))
    small = run_check(_check_dict(), _fixture(tmp_path / "b", big_bytes=100))
    assert (big.verdict, big.skipped_files) == (Verdict.ABSENT, 1)
    assert (small.verdict, small.skipped_files) == (Verdict.MANUAL, 0)
    assert big.verdict is not small.verdict


def test_eb5_outcome_is_deterministic(tmp_path) -> None:
    target = _fixture(tmp_path, big_bytes=MAX_FILE_BYTES + 4096)
    first = run_check(_check_dict(), target)
    second = run_check(_check_dict(), target)
    assert (first.verdict, first.skipped_files, list(first.locations)) == (
        second.verdict, second.skipped_files, list(second.locations))
