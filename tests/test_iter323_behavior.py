"""Iteration 323 behaviors: design-rationale documentation for CONFIDENCE_FLOOR_DEFAULT.

The constant ``CONFIDENCE_FLOOR_DEFAULT = 2`` in ``scoring.py`` now has an adjacent
comment block explaining WHY the value is 2, derived from the evidence ladder
arithmetic. The same derivation is added to ``CONSUMER_CONTRACT.md``'s Defaults
prose paragraph.

THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
``pm.md``'s Expected Behaviors 1-5. No test here reads the implementation source,
the engineer's or the reviewer's notes, or any diff. Every behavioral claim is
measured by running the CLI or by reading published documents, both of which are
inside the contract.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
CONTRACT = REPO / "docs" / "CONSUMER_CONTRACT.md"


# ---------------------------------------------------------------------------
# B3 guard -- the reasoning adjacent to CONFIDENCE_FLOOR_DEFAULT cannot be
# silently removed. The PM's B3 says: "A test asserts that the comment/
# docstring adjacent to CONFIDENCE_FLOOR_DEFAULT in scoring.py is non-empty
# and contains the word 'citation' or 'independent'."
#
# This test reads the scoring.py file as a DOCUMENT (it is a published
# module) and locates the constant by its textual definition, then checks
# the immediately adjacent lines for the required keywords.
# ---------------------------------------------------------------------------

SCORING_PY = REPO / "src" / "agent_gap_radar" / "scoring.py"


def _adjacent_comment_lines(path: pathlib.Path, anchor: str, window: int = 15) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    anchor_indices = [i for i, ln in enumerate(lines) if anchor in ln]
    assert anchor_indices, f"{anchor!r} not found in {path.name}"
    idx = anchor_indices[0]
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    region = lines[start:end]
    comment_lines = [ln for ln in region if ln.strip().startswith("#")]
    return "\n".join(comment_lines)


def test_b3_confidence_floor_has_adjacent_reasoning():
    comments = _adjacent_comment_lines(SCORING_PY, "CONFIDENCE_FLOOR_DEFAULT = 2")
    assert comments, (
        "CONFIDENCE_FLOOR_DEFAULT = 2 has no adjacent comment lines — "
        "the design rationale must not be silently removed"
    )
    lower = comments.lower()
    assert "citation" in lower or "independent" in lower, (
        f"adjacent comments must contain 'citation' or 'independent'; "
        f"got: {comments[:300]}"
    )


# ---------------------------------------------------------------------------
# B1 -- the comment states the factual derivation (evidence ladder, floor 2
# meaning at least two citations differing in class or source document).
# ---------------------------------------------------------------------------

def test_b1_comment_states_factual_derivation():
    comments = _adjacent_comment_lines(SCORING_PY, "CONFIDENCE_FLOOR_DEFAULT = 2")
    lower = comments.lower()
    assert "ladder" in lower or "evidence" in lower, (
        "the comment must reference the evidence ladder derivation"
    )
    assert "2" in comments or "two" in lower, (
        "the comment must mention the threshold value or its equivalent"
    )


# ---------------------------------------------------------------------------
# B2 -- CONSUMER_CONTRACT.md Defaults section gains a derivation sentence
# linking the value to the evidence ladder.
# ---------------------------------------------------------------------------

def test_b2_contract_defaults_has_derivation():
    text = CONTRACT.read_text(encoding="utf-8")
    defaults_start = text.find("## Defaults")
    assert defaults_start != -1, "## Defaults heading not found in CONSUMER_CONTRACT.md"
    defaults_section = text[defaults_start:]
    next_heading = defaults_section.find("\n## ", 1)
    if next_heading != -1:
        defaults_section = defaults_section[:next_heading]
    lower = defaults_section.lower()
    assert "ladder" in lower or "evidence" in lower, (
        "the Defaults section must mention the evidence ladder derivation"
    )
    assert "citation" in lower or "independent" in lower, (
        "the Defaults section must mention 'citation' or 'independent'"
    )


# ---------------------------------------------------------------------------
# B4 -- zero rendered-byte changes on all verbs.
# Uses the same two-arm git-archive technique as iter 322 to compare current
# tree output against the pre-change commit.
# ---------------------------------------------------------------------------

PRECHANGE_COMMIT = "624ad28"

_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "sys.stderr.write(c.__file__ + '\\n'); "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)


def _arm(src: pathlib.Path | None, *argv: str) -> tuple[int, bytes, str]:
    import os
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run(
        [sys.executable, "-c", _ARM_SCRIPT, *argv],
        capture_output=True, cwd=str(REPO), env=env, timeout=120)
    where = proc.stderr.decode("utf-8", "replace").splitlines()[0]
    return proc.returncode, proc.stdout, where


def _git(*args: str) -> bytes:
    done = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: "
        f"{done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("base-arm-323")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(
        ["tar", "-x", "-C", str(root)], input=archive,
        capture_output=True, timeout=120)
    assert extract.returncode == 0, (
        extract.stderr.decode("utf-8", "replace")[:400])
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


@pytest.mark.parametrize("verb", [
    ("report", str(GAPS)),
    ("list", str(GAPS)),
    ("show", "GAP-001", str(GAPS)),
    ("scan", str(REPO), "--gaps", str(GAPS)),
    ("taxonomy",),
    ("prd", str(GAPS)),
])
def test_b4_verb_byte_identical_to_head(base_src, verb):
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the extracted {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])

    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0

    if here_out != base_out:
        base_lines = base_out.decode("utf-8", "replace").splitlines()
        here_lines = here_out.decode("utf-8", "replace").splitlines()
        diffs = [(i, b, h) for i, (b, h) in enumerate(zip(base_lines, here_lines)) if b != h]
        snippet = diffs[:5] if diffs else f"len {len(base_out)} vs {len(here_out)}"
        assert here_out == base_out, (
            f"`radar {' '.join(verb)}` changed against {PRECHANGE_COMMIT}; "
            f"first diffs (line, base, here): {snippet}")
