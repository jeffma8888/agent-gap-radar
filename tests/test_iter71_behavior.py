"""Iteration 71 behaviors: `radar taxonomy` publishes the FOURTH closed vocabulary
(record `status`) with a gloss each, and a DERIVED, INTROSPECTED brake asserts that every
closed vocabulary the module defines is published by that document.

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors and from the two PUBLISHED documents (`README.md`,
`docs/CONSUMER_CONTRACT.md`); nothing here reads the implementation source to DERIVE an
expectation, and nothing reads the engineer's notes, the reviewer's notes, a diff or a
patch. Every behavioral claim is measured by CALLING a public interface -- `cli.main`, the
`taxonomy` module's public attributes -- or by reading a published document as DATA.

Structural notes, so this file cannot lie later:

* **No gloss wording is restated.** Behaviors 2 and 4 render their expectation from
  `taxonomy.STATUS_GLOSSES`, so a reworded gloss stays green while a DROPPED or REORDERED
  member reds. The four section headings ARE pinned as literals: they are the verb's
  publishing choices rather than vocabulary content, and their order is the claim.
* **No byte length and no vocabulary size is restated**, so a taxonomy that legitimately
  grows keeps every assertion here green. The one exception is `len(STATUSES)`, which is
  read from the tuple at assert time, never typed.
* **Section order is derived from the rendered bullets, never assumed.** Behavior 2 slices
  the statuses section by heading offsets taken from the observed document.
* **The introspection brake reports its DOMAIN.** Behavior 5 fails when the domain is
  empty, and it is proven two-sided IN THIS RUN three ways: over the real module (zero
  unpublished members), over a planted namespace carrying an extra unpublished vocabulary
  (named, with its missing members), and over a namespace where the attribute-table
  exclusion's PRECONDITION IS MADE FALSE, which must pull the excluded mapping back into
  the domain -- an exclusion is only demonstrably load-bearing once its verdict changes.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every planted fixture is an in-memory namespace or lives under
  pytest's `tmp_path`.
"""

from __future__ import annotations

import pathlib
import re
import types
from collections.abc import Mapping

import pytest

from _surface_contract import STABLE_SURFACE_HEADING, gfm_table
from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
CONTRACT_PATH = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: Behavior 6 -- the two contract tables read through the repo's own GFM oracle. The
#: record-shape table is named EXPLICITLY because the document carries a SECOND `status`
#: row under `### Keys the declared consumer reads`, and a whole-document reader cannot
#: tell the two apart -- measured: it finds 2 and fails closed.
RECORD_SHAPE_HEADING = "### Gap record keys"

#: Behavior 1 -- the verb's section headings, in the published order. Pinned as literals
#: on purpose: these are publishing choices, not vocabulary content. The COUNT is not
#: written into a name or a docstring here -- iteration 100 appended a fifth section, and a
#: count baked into an identifier is a derived value that goes stale where it is read most.
TAXONOMY_TITLE = "# Taxonomy"
LAYERS_HEADING = "## Layers"
GAP_TYPES_HEADING = "## Gap types"
SOURCES_HEADING = "## Evidence source classes (strongest first)"
STATUSES_HEADING = "## Record statuses"
CITATION_GATE_HEADING = "## Citation gate"
EXPECTED_HEADINGS = (LAYERS_HEADING, GAP_TYPES_HEADING, SOURCES_HEADING, STATUSES_HEADING,
                     CITATION_GATE_HEADING)


def _taxonomy_stdout(capsys) -> str:
    """`radar taxonomy` stdout, with exit code and empty stderr asserted at the source.

    Every behavior below reads the document through this helper, so no test can assert on
    bytes that arrived alongside a non-zero exit or a stderr line.
    """
    assert main(["taxonomy"]) == 0, "`radar taxonomy` must exit 0"
    captured = capsys.readouterr()
    assert captured.err == "", (
        "the quality bar gives stdout the document and stderr the errors; stderr carried "
        f"{captured.err!r}")
    return captured.out


# ---------------------------------------------------------------------------
# Behavior 1 -- four sections, in order, the new one LAST.
# ---------------------------------------------------------------------------

def test_taxonomy_publishes_exactly_the_expected_sections_in_order(capsys):
    """Behavior 1: exit 0, empty stderr, exactly the `##` headings of `EXPECTED_HEADINGS`
    in that order, with the LAST one last in the document.

    Both claims are read from `EXPECTED_HEADINGS` rather than restated, so appending a
    section is a ONE-LINE change to that tuple and no assertion or name carries a count
    that a later section would falsify."""
    out = _taxonomy_stdout(capsys)
    headings = tuple(line for line in out.splitlines() if line.startswith("## "))
    assert headings == EXPECTED_HEADINGS, (
        f"`radar taxonomy` publishes {len(headings)} `##` section(s) {headings}, expected "
        f"exactly {len(EXPECTED_HEADINGS)} in the order {EXPECTED_HEADINGS}")
    assert headings[-1] == EXPECTED_HEADINGS[-1], (
        f"{EXPECTED_HEADINGS[-1]!r} must be the LAST section of the document; the document "
        f"ends on {headings[-1]!r}")
    assert out.splitlines()[0] == TAXONOMY_TITLE, (
        f"the document must open with {TAXONOMY_TITLE!r}; it opens with "
        f"{out.splitlines()[0]!r}")


def test_taxonomy_takes_no_positional_argument_and_reads_no_register(capsys, tmp_path,
                                                                    monkeypatch):
    """Behavior 1 and the acceptance criterion 'takes no new argument and reads no
    register', measured rather than inspected: the same bytes must come back from a
    working directory that holds NO register at all. A verb that silently read `.` would
    differ here, or fail."""
    first = _taxonomy_stdout(capsys)
    empty = tmp_path / "no-register-here"
    empty.mkdir()
    monkeypatch.chdir(empty)
    assert not any(empty.iterdir()), "the fixture directory must be empty"
    second = _taxonomy_stdout(capsys)
    assert second == first, (
        "`radar taxonomy` output changed when run from a directory with no register, so "
        "the verb is reading a register it should not read")


def test_taxonomy_rejects_a_positional_argument(capsys):
    """Behavior 1, the other side: the verb accepts no positional, so handing it one is
    an error rather than a silently ignored token. `SystemExit(2)` is argparse's own
    refusal; a verb that accepted the token would return 0 and print the document."""
    with pytest.raises(SystemExit) as raised:
        main(["taxonomy", "."])
    assert raised.value.code == 2, (
        f"argparse must refuse an unexpected positional with exit 2, got "
        f"{raised.value.code!r}")


# ---------------------------------------------------------------------------
# Behavior 2 -- one bullet per status, in `STATUSES` order, gloss derived.
# ---------------------------------------------------------------------------

def _statuses_section(out: str) -> list[str]:
    """The non-blank lines of the statuses section, sliced by OBSERVED offsets.

    Bounded at the NEXT `## ` heading rather than at end-of-document. Until iteration 100
    the statuses section was last, so running to the end was equivalent and the difference
    was unobservable; once a section follows it, an unbounded slice silently annexes that
    section's bullets and behavior 2's one-bullet-per-status claim reads the wrong lines.
    """
    at = out.index(STATUSES_HEADING)
    body = out[at + len(STATUSES_HEADING):]
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            break
        if line.strip():
            lines.append(line)
    return lines


def _lines_after(out: str, heading: str) -> list[str]:
    """Every non-blank line following `heading`, to end-of-document.

    Deliberately UNBOUNDED, because the reader it models -- `test_iter08`'s ladder parser
    -- is unbounded: it splits on the ladder heading and keeps every later matching line.
    Kept separate from `_statuses_section` so one helper is not asked to be both bounded
    and unbounded, which is how the annexation above went unnoticed.
    """
    at = out.index(heading)
    return [line for line in out[at + len(heading):].splitlines() if line.strip()]


def test_statuses_section_holds_one_derived_bullet_per_status(capsys):
    """Behavior 2: exactly one bullet per member of `taxonomy.STATUSES`, in that tuple's
    order, each `` - `<status>` -- <gloss> `` with the gloss DERIVED from the module.

    Ordered by `STATUSES`, never by `STATUS_GLOSSES`: the tuple is what a record is
    validated against, so it is what the document owes a reader. While the two agree,
    iterating the mapping instead would render identical bytes and no test could tell
    them apart -- so the expectation is built from the tuple and INDEXES the mapping,
    which also turns a missing gloss into a loud KeyError.
    """
    out = _taxonomy_stdout(capsys)
    expected = [f"- `{status}` -- {taxonomy.STATUS_GLOSSES[status]}"
                for status in taxonomy.STATUSES]
    observed = _statuses_section(out)
    assert observed == expected, (
        f"the `{STATUSES_HEADING}` section carries {len(observed)} line(s) that do not "
        f"match the {len(expected)} bullet(s) derived from `taxonomy.STATUSES`:\n"
        f"observed: {observed}\nexpected: {expected}")


def test_every_status_is_named_exactly_once_in_the_document(capsys):
    """Behavior 2 as coverage: no member may be silently dropped, and none may be
    published twice (two bullets for one status is a document that contradicts itself)."""
    out = _taxonomy_stdout(capsys)
    for status in taxonomy.STATUSES:
        bullet = f"- `{status}` -- {taxonomy.STATUS_GLOSSES[status]}"
        assert out.count(bullet) == 1, (
            f"status {status!r} is published {out.count(bullet)} time(s) with its gloss, "
            "expected exactly 1")


# ---------------------------------------------------------------------------
# Behavior 3 -- the shape of `STATUS_GLOSSES`, with no wording pinned.
# ---------------------------------------------------------------------------

def test_status_glosses_key_sequence_equals_statuses():
    """Behavior 3: same members AND same order, so the mapping cannot drift from the
    tuple that validates records."""
    assert isinstance(taxonomy.STATUS_GLOSSES, Mapping), (
        f"`STATUS_GLOSSES` must be a Mapping, it is {type(taxonomy.STATUS_GLOSSES)}")
    assert tuple(taxonomy.STATUS_GLOSSES) == tuple(taxonomy.STATUSES), (
        f"`STATUS_GLOSSES` keys {tuple(taxonomy.STATUS_GLOSSES)} are not "
        f"`STATUSES` {tuple(taxonomy.STATUSES)} in the same order")


def test_every_status_gloss_is_a_non_empty_single_line_string():
    """Behavior 3: a non-empty string with no newline. A newline inside a gloss would
    break the one-bullet-per-member rendering without any other test noticing."""
    for status, gloss in taxonomy.STATUS_GLOSSES.items():
        assert isinstance(gloss, str) and gloss.strip(), (
            f"the gloss for {status!r} must be a non-empty string, it is {gloss!r}")
        assert "\n" not in gloss, (
            f"the gloss for {status!r} carries a newline, which would split its bullet")


# ---------------------------------------------------------------------------
# Behavior 4 -- the whole document, byte for byte, from the four vocabularies.
# ---------------------------------------------------------------------------

def _partition_side(statuses) -> str:
    """One side of the citation partition, in the verb's format.

    The FORMAT is restated; the CONTENT is derived -- the same split every other section
    body in this file uses.
    """
    return ", ".join(f"`{status}`" for status in statuses) if statuses else "(none)"


def _expected_document() -> str:
    """The document derived from the PUBLISHED vocabularies, in the verb's order.

    An independent derivation, not a copy of the renderer: the section bodies are built
    from `taxonomy` here, and no byte length and no vocabulary size is written down.
    """
    lines = [TAXONOMY_TITLE, "", LAYERS_HEADING, ""]
    lines += [f"- `{name}` -- {gloss}" for name, gloss in taxonomy.LAYERS.items()]
    lines += ["", GAP_TYPES_HEADING, ""]
    lines += [f"- `{name}` -- {gloss}" for name, gloss in taxonomy.GAP_TYPES.items()]
    lines += ["", SOURCES_HEADING, ""]
    lines += [f"- `{cls}` (weight {taxonomy.SOURCE_WEIGHTS[cls]})"
              for cls in taxonomy.SOURCE_CLASSES]
    lines += ["", STATUSES_HEADING, ""]
    lines += [f"- `{status}` -- {taxonomy.STATUS_GLOSSES[status]}"
              for status in taxonomy.STATUSES]
    lines += ["", CITATION_GATE_HEADING, ""]
    # Iteration 100's citation partition. Derived through the taxonomy's own helpers, so a
    # status added to `STATUSES` moves the expectation with the document instead of reding
    # a correct verb; `(none)` is the published rendering of an empty side.
    lines += [f"- `citable` -- {_partition_side(taxonomy.citable_statuses())}",
              f"- `terminal` -- {_partition_side(taxonomy.terminal_statuses())}"]
    return "".join(line + "\n" for line in lines)


def test_taxonomy_stdout_equals_the_published_vocabularies(capsys):
    """Behavior 4: byte-for-byte equality with the derived document."""
    out = _taxonomy_stdout(capsys)
    expected = _expected_document()
    assert out == expected, (
        f"`radar taxonomy` stdout ({len(out.encode())} bytes) does not equal the document "
        f"derived from the published vocabularies ({len(expected.encode())} bytes)")


def test_taxonomy_ends_in_exactly_one_newline(capsys):
    """Behavior 4's tail, observed on the bytes -- the product-wide renderer guarantee."""
    out = _taxonomy_stdout(capsys)
    assert out.endswith("\n"), "the document must end in a newline"
    assert not out.endswith("\n\n"), (
        "the document must end in EXACTLY one newline; it ends in a blank line")
    assert out.rstrip("\n") + "\n" == out, "more than one trailing newline survived"


# ---------------------------------------------------------------------------
# Behavior 5 -- the introspected, two-sided coverage brake.
# ---------------------------------------------------------------------------

#: The container types a vocabulary may be. `str` and `bytes` are excluded EXPLICITLY, so
#: a future `VERSION = "1.0"` is never read as a vocabulary of characters.
_CONTAINER_TYPES = (Mapping, tuple, list, set, frozenset)


def _candidate_vocabularies(module) -> dict[str, object]:
    """Public UPPER-CASE attributes of `module` whose value is a container."""
    found = {}
    for name in dir(module):
        if name.startswith("_") or not name.isupper():
            continue
        value = getattr(module, name)
        if isinstance(value, (str, bytes)):
            continue
        if isinstance(value, _CONTAINER_TYPES):
            found[name] = value
    return found


def _members(value) -> frozenset:
    """A Mapping's members are its KEYS; a sequence's members are its ELEMENTS."""
    return frozenset(value.keys() if isinstance(value, Mapping) else value)


def vocabulary_domain(module) -> dict[str, frozenset]:
    """{name: members} for every closed vocabulary `module` defines.

    An ATTRIBUTE TABLE is excluded: a Mapping is dropped iff some OTHER candidate that is
    NOT a Mapping carries an equal member set. The test is MEASURED member-set identity,
    never a name match -- that is what excludes `SOURCE_WEIGHTS` against `SOURCE_CLASSES`
    and `STATUS_GLOSSES` against `STATUSES`, and it is the only reason those two are not
    audited as vocabularies of their own. While their keys agree, a name match would
    render and read identically, so the rule is written the way its evidence is.
    """
    candidates = _candidate_vocabularies(module)
    sequence_members = [_members(value) for value in candidates.values()
                        if not isinstance(value, Mapping)]
    domain = {}
    for name, value in candidates.items():
        members = _members(value)
        if isinstance(value, Mapping) and any(members == other
                                              for other in sequence_members):
            continue
        domain[name] = members
    return domain


def unpublished_members(module, document: str) -> dict[str, list]:
    """{vocabulary: sorted members absent from `document` as a backticked token}."""
    missing = {}
    for name, members in vocabulary_domain(module).items():
        absent = sorted(m for m in members if f"`{m}`" not in document)
        if absent:
            missing[name] = absent
    return missing


def test_vocabulary_domain_is_non_empty_and_names_itself():
    """Behavior 5: the brake REPORTS its domain size and fails at zero, so an empty
    introspection can never read as clean."""
    domain = vocabulary_domain(taxonomy)
    assert len(domain) >= 4, (
        f"the introspected vocabulary domain collapsed to {len(domain)} "
        f"vocabular(y/ies) {sorted(domain)}; a small domain reads as health it never "
        "measured")
    assert all(members for members in domain.values()), (
        f"a vocabulary in the domain is EMPTY, so it can never report a gap: "
        f"{ {name: len(m) for name, m in domain.items()} }")


def test_every_defined_vocabulary_is_published_by_the_verb(capsys):
    """Behavior 5, the live side: zero unpublished members over a non-zero, NAMED
    domain. This is the brake that would have caught `STATUSES` being enforced at
    validation time while no surface published its value space."""
    out = _taxonomy_stdout(capsys)
    domain = vocabulary_domain(taxonomy)
    missing = unpublished_members(taxonomy, out)
    assert missing == {}, (
        f"{len(missing)} of {len(domain)} introspected vocabular(y/ies) {sorted(domain)} "
        f"have members `radar taxonomy` never publishes: {missing}")


def _stand_in(**overrides) -> types.SimpleNamespace:
    """A namespace carrying the module's real vocabularies plus any overrides."""
    base = {name: getattr(taxonomy, name)
            for name in dir(taxonomy)
            if not name.startswith("_") and name.isupper()}
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_brake_names_a_planted_unpublished_vocabulary(capsys):
    """Behavior 5, the known-bad side: a stand-in namespace that adds one vocabulary the
    document never names must be REPORTED, with the vocabulary named and its missing
    members listed. Without this, the live pass above is health it never measured."""
    out = _taxonomy_stdout(capsys)
    planted = _stand_in(PHASES=("alpha-unpublished", "beta-unpublished"))
    domain = vocabulary_domain(planted)
    assert "PHASES" in domain, (
        f"the planted vocabulary never entered the domain {sorted(domain)}, so this "
        "known-bad sample proves nothing")
    missing = unpublished_members(planted, out)
    assert missing == {"PHASES": ["alpha-unpublished", "beta-unpublished"]}, (
        f"the brake did not name the planted unpublished vocabulary; it reported "
        f"{missing}")


def test_brake_fires_on_the_actual_pre_change_document(capsys):
    """Behavior 5's known-bad side over the REAL defect rather than a synthetic one.

    `test_brake_names_a_planted_unpublished_vocabulary` proves the brake fires on an
    INVENTED vocabulary; it does not prove it fires on the one that was actually missing.
    This reconstructs the pre-change document by stripping the trailing statuses section
    from the OBSERVED bytes, then asserts the brake names `STATUSES` with every member
    listed -- i.e. that it would have failed on the document this product published while
    `STATUSES` was enforced at validation time and disclosed nowhere. Without this, the
    brake is proven only against a sample chosen to be caught.

    No byte length is written down: the reconstruction is a SLICE of the observed
    document, and the only size claim is that it is strictly shorter.
    """
    out = _taxonomy_stdout(capsys)
    at = out.index(STATUSES_HEADING)
    pre_change = out[:at].rstrip("\n") + "\n"
    assert STATUSES_HEADING not in pre_change, (
        "the reconstruction must not still carry the statuses heading")
    assert CITATION_GATE_HEADING not in pre_change, (
        "the reconstruction slices at the statuses heading, so every LATER section must be "
        "gone too; a surviving citation-gate section would publish the status names and "
        "the brake would report nothing, passing this test for the wrong reason")
    assert len(pre_change) < len(out), (
        "the reconstruction must be strictly shorter than the published document")

    missing = unpublished_members(taxonomy, pre_change)
    # BOTH status vocabularies live in the sections this reconstruction removes, so both
    # must be named. Iteration 100 added `TERMINAL_STATUSES`, whose members are published
    # only by the citation-gate section -- and pinning `STATUSES` alone would have let a
    # second entirely unpublished vocabulary sit in the report unnoticed, which is the
    # failure this brake exists to catch. Every member list is derived, never restated.
    assert missing == {"STATUSES": sorted(taxonomy.STATUSES),
                       "TERMINAL_STATUSES": sorted(taxonomy.TERMINAL_STATUSES)}, (
        "over the pre-change document the brake must name every status vocabulary and "
        f"every member it failed to publish; it reported {missing}")

    assert unpublished_members(taxonomy, out) == {}, (
        "the same brake, same run, must report zero unpublished members over the LIVE "
        "document -- both sides or neither is evidence")


def test_attribute_table_exclusion_is_load_bearing_not_a_name_match():
    """Behavior 5's exclusion rule, proven by making its PRECONDITION FALSE.

    `STATUS_GLOSSES` is excluded ONLY because a non-Mapping candidate (`STATUSES`) has an
    equal member set. Re-key it in a scratch namespace and it MUST enter the domain -- if
    it stays out, the rule is really matching on the NAME and would keep a genuinely
    unpublished mapping invisible. Same for `SOURCE_WEIGHTS` against `SOURCE_CLASSES`.
    """
    live = vocabulary_domain(taxonomy)
    assert "STATUS_GLOSSES" not in live and "SOURCE_WEIGHTS" not in live, (
        f"both attribute tables must be excluded while their twins agree: {sorted(live)}")

    rekeyed = _stand_in(STATUS_GLOSSES={"drifted-key": "gloss"})
    domain = vocabulary_domain(rekeyed)
    assert "STATUS_GLOSSES" in domain, (
        "a Mapping whose member set NO LONGER equals any non-Mapping candidate's must "
        f"enter the domain; it did not: {sorted(domain)}")
    assert domain["STATUS_GLOSSES"] == frozenset({"drifted-key"}), (
        "a Mapping's members must be its KEYS")

    rekeyed_weights = _stand_in(SOURCE_WEIGHTS={"drifted-class": 1})
    assert "SOURCE_WEIGHTS" in vocabulary_domain(rekeyed_weights), (
        "the same rule must apply to `SOURCE_WEIGHTS`, by measurement not by name")


def test_a_string_attribute_is_never_read_as_a_vocabulary():
    """Behavior 5: `str` and `bytes` are excluded explicitly, so a future
    `VERSION = "1.0"` is not audited as a vocabulary of characters."""
    planted = _stand_in(VERSION="1.0", DIGEST=b"abc")
    domain = vocabulary_domain(planted)
    assert "VERSION" not in domain and "DIGEST" not in domain, (
        f"a str/bytes attribute entered the vocabulary domain: {sorted(domain)}")


def test_private_and_lower_case_attributes_are_not_candidates():
    """Behavior 5's candidate rule, both halves: a leading underscore and a non-upper
    name are both out, so a module-private helper table is not audited."""
    namespace = types.SimpleNamespace(
        REAL=("published-token",), _PRIVATE=("hidden",), helper=("lower",))
    domain = vocabulary_domain(namespace)
    assert sorted(domain) == ["REAL"], (
        f"only public UPPER-CASE containers are candidates; domain was {sorted(domain)}")


def test_brake_over_an_empty_namespace_reports_zero_rather_than_clean():
    """Behavior 5: an empty introspection must be VISIBLE as zero, which is what
    `test_vocabulary_domain_is_non_empty_and_names_itself` then refuses."""
    assert vocabulary_domain(types.SimpleNamespace()) == {}
    assert unpublished_members(types.SimpleNamespace(), "") == {}, (
        "an empty domain reports no missing members -- which is exactly why the domain "
        "size is asserted separately rather than inferred from an empty report")


def test_the_document_expectation_is_falsifiable(capsys):
    """MUTATION CHECK for behaviors 2 and 4, so their green means something.

    A byte-equality assertion is only evidence if an actually-wrong document would fail
    it. Three planted mutations of the OBSERVED bytes are compared against the derived
    expectation here -- a dropped status, a reordered pair, and a reworded gloss -- and
    the first two must differ while the third must ALSO differ, because behavior 2 derives
    the gloss from the module and the mutation moves only the rendered copy.

    Nothing under `src/` is touched: the mutation is applied to the captured string.
    """
    out = _taxonomy_stdout(capsys)
    expected = _expected_document()
    assert out == expected, "premise: the live document matches before any mutation"

    first, last = taxonomy.STATUSES[0], taxonomy.STATUSES[-1]
    dropped = out.replace(
        f"- `{last}` -- {taxonomy.STATUS_GLOSSES[last]}\n", "")
    assert dropped != expected, (
        "dropping the last status bullet did not change the document, so behavior 4 "
        "cannot detect a dropped member")

    reworded = out.replace(taxonomy.STATUS_GLOSSES[first], "a different gloss entirely")
    assert reworded != out and reworded != expected, (
        "rewording a rendered gloss did not change the document, so behavior 2 is not "
        "actually comparing the rendered text against the module's gloss")

    # The reorder mutation must isolate ORDER: swap two bullets in place and leave every
    # other byte alone. Slicing at the heading and REBUILDING the tail cannot do that once
    # a section follows -- the unbounded tail annexed `## Citation gate` and both partition
    # bullets (7 lines, not 4) and the rebuild dropped the blank line before that heading,
    # so `reordered != expected` was satisfied by the reconstruction damage and passed with
    # NO swap applied. Measured on the pre-fix worktree: unswapped != expected was True.
    # `_statuses_section` is bounded at the next `## `, and a targeted `replace` mutates
    # only the swapped pair.
    bullets = _statuses_section(out)
    if len(bullets) >= 2:
        pair = bullets[0] + "\n" + bullets[1] + "\n"
        reordered = out.replace(pair, bullets[1] + "\n" + bullets[0] + "\n", 1)
        assert reordered != out, (
            "premise: the swap must actually change the captured document, or the "
            "assertion below passes on a no-op replace")
        assert reordered != expected, (
            "swapping two status bullets did not change the document, so the ORDER "
            "claim in behavior 2 is unenforced")


# ---------------------------------------------------------------------------
# The new section's interaction with the EXISTING ladder reader -- measured, not assumed.
# ---------------------------------------------------------------------------

#: The row shape `test_iter08_behavior._observed_ladder()` parses out of this same
#: document: a hyphen bullet, a backticked lowercase-and-hyphen token, a parenthesised
#: integer weight. Restated here as the SHAPE under test, never as a count.
LADDER_ROW_SHAPE = re.compile(r"^-\s+`([a-z-]+)`\s+\(weight (\d+)\)")


def test_no_trailing_section_line_matches_the_ladder_row_shape(capsys):
    """`_observed_ladder()` splits on `## Evidence source classes` and keeps EVERY later
    line that matches the ladder row shape, so any section appended AFTER the ladder is
    inside its domain. A status bullet carries a gloss and no weight, and a citation-gate
    bullet carries a comma-joined name list and no weight, so neither may match -- and that
    must be measured here rather than left to whichever test happens to notice an extra
    rung appearing.

    The domain is every line after the ladder's OWN rungs, to end-of-document, which is
    what the reader being modelled actually scans. It was `_statuses_section` until
    iteration 100 appended a section BEYOND the statuses -- exactly the case the docstring
    already claimed to cover, and the one a bounded slice would have stopped covering.
    """
    out = _taxonomy_stdout(capsys)
    trailing = _lines_after(out, SOURCES_HEADING)[len(taxonomy.SOURCE_CLASSES):]
    assert trailing, (
        "the domain after the evidence ladder is EMPTY, so this assertion measures nothing; "
        "it must cover every line the ladder reader would keep")
    for line in trailing:
        assert not LADDER_ROW_SHAPE.match(line.strip()), (
            f"a line published after the evidence ladder parses as a ladder rung: {line!r}; "
            "the evidence-ladder reader would report an extra source class")


def test_ladder_row_shape_is_two_sided():
    """The shape above must actually FIRE on a real rung, or the assertion that it does
    not fire on a status bullet is health it never measured."""
    assert LADDER_ROW_SHAPE.match("- `secondary-summary` (weight 1)"), (
        "the ladder row shape does not match a real rung, so it can prove nothing")
    assert not LADDER_ROW_SHAPE.match("- `open` -- Live and actionable: nothing."), (
        "the ladder row shape matches a gloss bullet, so it is the wrong shape")


def test_evidence_ladder_still_publishes_every_source_class(capsys):
    """The ladder section itself is untouched by the new section: one rung per member of
    `SOURCE_CLASSES`, in that order, each carrying the weight `SOURCE_WEIGHTS` gives it.
    Derived from the module, so no count is written down."""
    out = _taxonomy_stdout(capsys)
    after = out.split(SOURCES_HEADING, 1)[1]
    observed = tuple((m.group(1), int(m.group(2)))
                     for m in (LADDER_ROW_SHAPE.match(line.strip())
                               for line in after.splitlines())
                     if m)
    expected = tuple((cls, taxonomy.SOURCE_WEIGHTS[cls])
                     for cls in taxonomy.SOURCE_CLASSES)
    assert observed == expected, (
        f"the evidence ladder parses as {len(observed)} rung(s) {observed}, expected the "
        f"{len(expected)} derived from `SOURCE_CLASSES`: {expected}")


# ---------------------------------------------------------------------------
# Behavior 6 -- the two published documents stop misdescribing `status`.
# ---------------------------------------------------------------------------

def _table_rows(document: str) -> list[list[str]]:
    """Every GFM table row of `document` as stripped cells, separator rows dropped.

    Read across the whole document on purpose: behavior 6 identifies each row by the
    CONTENT of its first cell, so a heading-anchored reader would add a second thing that
    can drift. Separator rows are dropped by shape, not by position.
    """
    rows = []
    for line in document.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= set("-: ") and cell for cell in cells):
            continue
        rows.append(cells)
    return rows


def _one_row(document: str, predicate, what: str) -> list[str]:
    """The single row whose first cell satisfies `predicate`; fails closed on 0 or 2+."""
    found = [row for row in _table_rows(document) if predicate(row[0])]
    assert len(found) == 1, (
        f"expected exactly 1 table row whose first cell {what}, found {len(found)}: "
        f"{[row[0] for row in found]}")
    return found[0]


def _contract_row(heading: str, first_cell: str) -> tuple[str, ...]:
    """The single row of the table under `heading` whose first cell is `first_cell`.

    Read through `_surface_contract.gfm_table`, the repo's own oracle, rather than a
    second GFM reader: it fails closed on a duplicated heading and on a ragged row, so
    "the document says X" cannot quietly become "the document says something, one column
    over".
    """
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    table = gfm_table(contract, heading)
    found = [row for row in table.rows if row[0] == first_cell]
    assert len(found) == 1, (
        f"expected exactly 1 row under {heading!r} whose first cell is {first_cell!r}, "
        f"found {len(found)}: {[row[0] for row in found]}")
    return found[0]


def test_contract_status_row_points_at_the_verb_that_publishes_the_values():
    """Behavior 6(a): the `status` key row of the contract's record-shape table names
    `radar taxonomy`, so a consumer told to select on the field is told where its value
    space is published.

    Scoped to `### Gap record keys` deliberately. The document publishes a SECOND
    `status` row under `### Keys the declared consumer reads`, so an unscoped reader finds
    two and cannot say which one the behavior is about -- measured in this run by
    `test_status_appears_in_two_contract_tables`, which pins that as a known fact rather
    than leaving it as a surprise.
    """
    row = _contract_row(RECORD_SHAPE_HEADING, "`status`")
    assert "radar taxonomy" in " | ".join(row), (
        "the contract's record-shape `status` row must name `radar taxonomy`, the verb "
        f"that publishes its closed value space; the row reads {row!r}")


def test_status_appears_in_two_contract_tables():
    """Behavior 6(a)'s scope, asserted so it is a known limit rather than a surprise.

    The contract names `status` in TWO tables. Only the record-shape row is in scope for
    behavior 6(a); the consumer-keys row is recorded here as PM feedback -- it is the row
    that tells a consumer to select on the field, and it still carries no pointer to the
    published value space.
    """
    document = CONTRACT_PATH.read_text(encoding="utf-8")
    rows = [row for row in _table_rows(document) if row[0] == "`status`"]
    assert len(rows) == 2, (
        f"expected the contract to carry `status` in 2 tables, found {len(rows)}: {rows}")
    consumer_row = _contract_row("### Keys the declared consumer reads", "`status`")
    assert consumer_row != rows[0], (
        "the two `status` rows must be distinct rows of distinct tables")


def test_readme_status_row_no_longer_describes_a_boolean():
    """Behavior 6(b): the README field-group row naming `layer`, `gap_type` and `status`
    does not contain the word `whether` -- the reading that is false for the records
    already carrying `partially-addressed`."""
    readme = README_PATH.read_text(encoding="utf-8")

    def names_the_three(cell: str) -> bool:
        return all(token in cell for token in ("`layer`", "`gap_type`", "`status`"))

    row = _one_row(readme, names_the_three,
                   "names `layer`, `gap_type` and `status`")
    assert "whether" not in " | ".join(row), (
        "the README field-group row still glosses `status` with `whether`, which reads "
        f"boolean; the row reads {row!r}")


def test_stable_surface_taxonomy_row_restates_no_count():
    """Behavior 6(c): the stable-surface row for `radar taxonomy` carries NO digit, so
    the cell cannot decay when a vocabulary grows -- the rule `README.md` already
    publishes for its own register section, applied to the one cell this change would
    otherwise falsify."""
    row = _contract_row(STABLE_SURFACE_HEADING, "`radar taxonomy`")
    text = " | ".join(row)
    digits = sorted({ch for ch in text if ch.isdigit()})
    assert digits == [], (
        f"the stable-surface `radar taxonomy` row restates digit(s) {digits}, which decay "
        f"as the vocabularies grow; the row reads {row!r}")


def test_row_reader_is_two_sided_over_a_planted_document():
    """Behavior 6's reader, proven both ways in this run: it must FIND a planted row and
    it must fail closed when the row is absent or duplicated. A reader that silently
    returns nothing would let all three assertions above pass over a document that had
    lost the row entirely."""
    good = "| A | B |\n|---|---|\n| `status` | says radar taxonomy |\n"
    assert _one_row(good, lambda cell: cell == "`status`", "x")[1] == (
        "says radar taxonomy")

    with pytest.raises(AssertionError):
        _one_row("| A | B |\n|---|---|\n| `other` | x |\n",
                 lambda cell: cell == "`status`", "is '`status`'")

    doubled = ("| A | B |\n|---|---|\n| `status` | one |\n| `status` | two |\n")
    with pytest.raises(AssertionError):
        _one_row(doubled, lambda cell: cell == "`status`", "is '`status`'")


def test_row_reader_drops_separator_rows_only():
    """Behavior 6's reader must not mistake a data row for a separator. `---` alone is a
    separator; a cell of prose that merely CONTAINS a hyphen is data."""
    document = "| A | B |\n|:---|---:|\n| - a hyphen bullet | b -- c |\n"
    rows = _table_rows(document)
    assert rows == [["A", "B"], ["- a hyphen bullet", "b -- c"]], (
        f"separator handling is wrong: {rows}")
