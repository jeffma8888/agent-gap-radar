"""Iteration 74 behaviors: every published statement of the `priority` rule becomes TRUE,
and the requirement is DERIVED from `scoring`'s own weight constants so a weight change
reds the documents instead of decaying quietly.

WHAT THIS PROTECTS. `priority` is a weighted sum of the three 1-5 inputs -- severity, then
frequency, then tractability, at the weights `scoring` publishes as `W_SEVERITY`,
`W_FREQUENCY` and `W_TRACTABILITY` -- normalised to 0.0-10.0. Three surfaces stated it as a
PRODUCT of the same three inputs, and a product is not the same ranking: `docs/
CONSUMER_CONTRACT.md` deliberately does NOT store the derived scores and tells a file-reading
consumer to "compute them the same way", so the false sentence in that same document was the
only published referent for "the same way".

WHY THIS IS DERIVED RATHER THAN A LITERAL SEARCH. The checker below never looks for `3/2/1`
as text it knows in advance. It reads the three constants at test time and BUILDS the
spellings it will accept, so if a future iteration reweighted the inputs, these tests would
demand the new weights in the prose rather than keep blessing the old ones -- the code
decides what the prose owes. Behavior 4 asserts that dependence directly, by scoring the
committed documents under a SUBSTITUTED triple and requiring them to fail.

WHAT IT DELIBERATELY DOES NOT PIN. No sentence, no line number and no section: any wording
that names each input with its weight (or carries the ordered weight triple) satisfies it,
so an honest rewrite cannot red a correct document. The one literal pinned is an ABSENCE --
the retired product formulation -- which no honest rewrite reintroduces.

TWO-SIDEDNESS, because a checker that never refuses is fail-open. Behavior 5 scores the
retired sentence (must name NONE of the three) and the corrected README sentence (must name
ALL three) as inline fixtures; behavior 6 scores real committed prose that was already
correct, `src/agent_gap_radar/diff.py`, and behavior 4 re-scores every one of them under a
substituted triple and under a ROTATED one, so a checker that keyed on the value set rather
than on the ordered assignment would be caught.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here reads `src/` implementation
logic, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors, and every claim is measured by driving
the public library surface (`scoring.W_*`, `scoring.priority`, `registry.load_all`), by
driving `cli.main`, or by counting substrings in a PUBLISHED document. Two file reads are
mechanical token censuses over bytes that are themselves the artifact under test -- the
`scoring` module docstring (read through `scoring.__doc__`, so the assertion is about the
docstring the interpreter sees) and `diff.py`'s committed prose -- and neither reads logic.

Landmine avoided, per the iteration-09 lesson: `gaps/` is grown by an unattended research
pass, so no live gap id and no live count or score is written down here. Record ids and the
register size are always discovered at run time.

Offline and path-clean: no network is touched (an autouse tripwire enforces it), no absolute
machine path appears -- the repo root is derived from `__file__` -- and no subprocess runs.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import socket

import pytest

from agent_gap_radar import registry, scoring
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
#: The roadmap handle the iteration-62 durability sweep repoints. Behavior 8 reads its
#: document THROUGH this name rather than inline, so naming this module in that sweep is
#: load-bearing rather than cosmetic: the sweep can drive the pin over a grown or shrunk
#: ledger of its own making, which is how the suite proves the pin survives a later ship.
ROADMAP = REPO_ROOT / "PRODUCT.md"
README = REPO_ROOT / "README.md"
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
DIFF_MODULE = REPO_ROOT / "src" / "agent_gap_radar" / "diff.py"

#: The retired formulation. Pinned as an ABSENCE only, never as a required phrasing.
RETIRED_RULE = "severity x frequency x tractability"

#: The three inputs, in the order their weights are declared.
INPUT_NAMES = ("severity", "frequency", "tractability")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite is offline, and that is enforced here rather than promised."""

    def _tripwire(*_a: object, **_k: object) -> None:
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket, "socket", _tripwire)
    monkeypatch.setattr(socket, "create_connection", _tripwire)


def live_weights() -> tuple[int, int, int]:
    """The weights READ AT TEST TIME, in `INPUT_NAMES` order. Nothing is hardcoded."""
    return (scoring.W_SEVERITY, scoring.W_FREQUENCY, scoring.W_TRACTABILITY)


_WHITESPACE = re.compile(r"\s+")


def norm(text: str) -> str:
    """Lowercase with every whitespace run collapsed, so a line break inside a sentence
    cannot hide a spelling and a two-line docstring reads like a one-line one."""
    return _WHITESPACE.sub(" ", text.lower())


def spellings(name: str, weight: int) -> tuple[str, ...]:
    """The accepted ways to name one input WITH its weight, built from the weight."""
    return (f"{name} x{weight}", f"{name} (x{weight})", f"{name} *{weight}")


def weight_triple(weights: tuple[int, int, int]) -> str:
    """The ordered triple spelling, which names all three inputs at once."""
    return "/".join(str(w) for w in weights)


def unnamed_inputs(text: str, weights: tuple[int, int, int]) -> tuple[str, ...]:
    """Which of the three inputs `text` fails to name at `weights`, in declaration order.

    An empty result means the text states the weighted rule; a non-empty one names what is
    missing, which is what makes the failure message useful.
    """
    haystack = norm(text)
    if weight_triple(weights) in haystack:
        return ()
    return tuple(
        name
        for name, weight in zip(INPUT_NAMES, weights, strict=True)
        if not any(s in haystack for s in spellings(name, weight))
    )


# --- Inline fixtures for the two-sided control (behavior 5) -------------------------------
#: Known-BAD: the sentence this iteration retires. Must name none of the three inputs.
FIXTURE_RETIRED = "Priority is severity x frequency x tractability."
#: Known-GOOD: the shape the corrected README sentence takes. Must name all three.
FIXTURE_CORRECTED = (
    "`priority` is a weighted sum of the three 1-5 inputs -- severity x3, frequency x2, "
    "tractability x1 -- normalised to 0.0-10.0."
)


def substituted(weights: tuple[int, int, int]) -> tuple[int, int, int]:
    """A triple that differs from `weights` in every position, used to prove derivation."""
    return tuple(w + 1 for w in weights)  # type: ignore[return-value]


def rotated(weights: tuple[int, int, int]) -> tuple[int, int, int]:
    """The same VALUE SET in a different order: catches a checker keyed on values only."""
    return (weights[2], weights[1], weights[0])


def _document(path: pathlib.Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"{path.name} is empty, so nothing below would be measured"
    return text


# --- Behavior 1 --------------------------------------------------------------------------


def test_readme_states_the_weighted_rule_and_not_the_product() -> None:
    text = _document(README)
    assert RETIRED_RULE not in text
    assert RETIRED_RULE not in norm(text)
    assert unnamed_inputs(text, live_weights()) == ()


# --- Behavior 2 --------------------------------------------------------------------------


def test_consumer_contract_states_the_weighted_rule_and_not_the_product() -> None:
    text = _document(CONTRACT)
    assert RETIRED_RULE not in text
    assert RETIRED_RULE not in norm(text)
    assert unnamed_inputs(text, live_weights()) == ()


# --- Behavior 3 --------------------------------------------------------------------------


def test_scoring_module_docstring_states_the_weighted_rule() -> None:
    doc = scoring.__doc__ or ""
    assert doc.strip(), "scoring.__doc__ is empty, so the assertion below would be vacuous"
    assert RETIRED_RULE not in doc
    assert RETIRED_RULE not in norm(doc)
    assert unnamed_inputs(doc, live_weights()) == ()


# --- Behavior 4: the requirement is DERIVED from the constants ---------------------------


def test_accepted_spellings_are_built_from_the_weight_argument() -> None:
    """The checker's vocabulary changes with the weights it is given."""
    assert spellings("severity", 3) != spellings("severity", 4)
    assert "severity x3" in spellings("severity", 3)
    assert "severity x4" in spellings("severity", 4)
    assert weight_triple((3, 2, 1)) != weight_triple((1, 2, 3))


@pytest.mark.parametrize("source", ["readme", "contract", "docstring", "diff"])
def test_committed_text_fails_under_a_substituted_weight_triple(source: str) -> None:
    """Substitute a different triple and every corrected document must FAIL, which is what
    makes these tests a brake on the weights rather than a `3/2/1` literal search."""
    texts = {
        "readme": _document(README),
        "contract": _document(CONTRACT),
        "docstring": scoring.__doc__ or "",
        "diff": _document(DIFF_MODULE),
    }
    text = texts[source]
    live = live_weights()
    assert unnamed_inputs(text, live) == ()
    assert unnamed_inputs(text, substituted(live)) != ()


@pytest.mark.parametrize("source", ["readme", "contract", "docstring", "diff"])
def test_committed_text_fails_under_the_same_weights_in_a_different_order(
    source: str,
) -> None:
    """Same value set, wrong assignment: a checker that accepted any arrangement of the
    three numbers would pass here, so this is what pins the ORDER."""
    texts = {
        "readme": _document(README),
        "contract": _document(CONTRACT),
        "docstring": scoring.__doc__ or "",
        "diff": _document(DIFF_MODULE),
    }
    live = live_weights()
    assert rotated(live) != live, "rotation is a no-op at these weights; pick another probe"
    assert unnamed_inputs(texts[source], rotated(live)) != ()


# --- Behavior 5: two-sided, inline fixtures ----------------------------------------------


def test_checker_refuses_the_retired_sentence_and_accepts_the_corrected_one() -> None:
    live = live_weights()
    refused = unnamed_inputs(FIXTURE_RETIRED, live)
    accepted = unnamed_inputs(FIXTURE_CORRECTED, live)
    assert refused == INPUT_NAMES, "the retired sentence must name NONE of the three inputs"
    assert accepted == (), "the corrected sentence must name ALL three inputs"
    assert refused != accepted, "a checker that treats both alike proves nothing"


# --- Behavior 6: positive control on prose already committed ------------------------------


def test_diff_module_prose_already_satisfies_the_checker() -> None:
    """`diff.py` stated the rule correctly all along, so the requirement is satisfiable by
    text nobody wrote for this brake."""
    text = _document(DIFF_MODULE)
    assert RETIRED_RULE not in text
    assert unnamed_inputs(text, live_weights()) == ()


# --- Behavior 7: no behavior change ------------------------------------------------------


def test_priority_is_the_weighted_sum_for_every_live_record() -> None:
    """Recomputed independently from the published constants, for every record on disk."""
    records = registry.load_all(registry.gaps_dir(REPO_ROOT))
    assert records, "no records loaded, so this test would be vacuous"
    ws, wf, wt = live_weights()
    ceiling = 5 * (ws + wf + wt)
    for gap in records:
        weighted = ws * gap.severity + wf * gap.frequency + wt * gap.tractability
        assert scoring.priority(gap) == round(10.0 * weighted / ceiling, 1)


def _run(argv: list[str]) -> str:
    """Drive the CLI and GATE ON THE PRODUCER: a failed command's usage text is not output,
    and comparing two error pages for equality is a fail-open proof."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
    except SystemExit as exc:  # argparse refused an argv shape it does not know
        raise AssertionError(
            f"{argv} was refused by the parser (exit {exc.code}); "
            f"stderr={err.getvalue()!r}"
        ) from exc
    text = out.getvalue()
    assert code == 0, f"{argv} exited {code}; stderr={err.getvalue()!r}"
    assert err.getvalue() == "", f"{argv} wrote to stderr: {err.getvalue()!r}"
    assert len(text) > 200, f"{argv} produced only {len(text)} bytes"
    return text


def _verbs() -> list[list[str]]:
    records = registry.load_all(registry.gaps_dir(REPO_ROOT))
    assert records
    root = str(REPO_ROOT)
    return [
        ["list", root],
        ["report", root],
        ["show", records[0].id, root],
        ["taxonomy"],
    ]


def test_documents_are_byte_stable_and_end_in_exactly_one_newline() -> None:
    for argv in _verbs():
        first = _run(argv)
        assert first == _run(argv), f"{argv} is not byte-stable across invocations"
        assert first.endswith("\n") and not first.endswith("\n\n"), argv


# --- Behavior 8: the roadmap row and the ledger row --------------------------------------


def test_roadmap_carries_a_shipped_row_and_a_ledger_row_for_this_iteration() -> None:
    lines = _document(ROADMAP).splitlines()
    rows = [ln for ln in lines if ln.startswith("| ") and "| shipped |" in ln]
    assert any("Iteration 74" in ln for ln in rows), "no shipped row dated to iteration 74"
    assert any(ln.startswith("- iter 74 ") for ln in lines), "no `- iter 74` ledger row"


# --- Acceptance criterion 1 as a census, so a fourth surface cannot appear later ----------


def test_the_retired_rule_occurs_nowhere_under_src_readme_or_docs() -> None:
    domain = [README, *sorted((REPO_ROOT / "src").rglob("*.py")), *sorted((REPO_ROOT / "docs").rglob("*.md"))]
    assert len(domain) >= 10, f"census domain collapsed to {len(domain)} files"
    offenders = {
        p.relative_to(REPO_ROOT).as_posix(): p.read_text(encoding="utf-8").count(RETIRED_RULE)
        for p in domain
        if RETIRED_RULE in p.read_text(encoding="utf-8")
    }
    assert offenders == {}
