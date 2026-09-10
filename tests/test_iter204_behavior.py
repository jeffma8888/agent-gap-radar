"""Iteration 204 behaviors: the brief publishes the DEMOTION counterfactual per citation.

`pm.md`: the register's one protected rule is that confidence is DERIVED from evidence, and
the register published only the ADD direction of that derivation (`promotion_options`, the
report's `Needs` column). This iteration adds the LOSS direction --
`scoring.confidence_without(gap, locator)` plus exactly one derived line per citation inside
each `### N.` block of `radar show`'s `## Evidence`, so a builder can see what a single
retraction costs the record next to the citation that carries it.

BLACK-BOX, AND THE ISOLATION CONTRACT IS HONORED. Every expectation here comes from `pm.md`
(Feature / Why / Expected Behaviors) and is measured by RUNNING the product -- `cli.main`,
`scoring.confidence`, `scoring.confidence_without`, `scoring.distinct_sources`,
`registry.load_all` -- or by reading the live register, which is published data. Nothing here
was read from `src/`, from `tools/`, from the engineer's or the reviewer's notes, from
`IMPLEMENTATION.patch`, or from any diff.

STRUCTURAL CHOICES, so this file cannot lie later:

* **The domain SIZE is asserted, not printed.** `load_all` returns `[]` for a legal empty
  directory, so an all-records loop over an empty register reports every claim green while
  examining nothing. `REGISTER` is required to hold more than 100 records before any loop runs,
  and every existence claim of behavior 9 asserts its own witness COUNT.
* **Every expected number is DERIVED INDEPENDENTLY, never lifted from the output.** This file
  carries its own copy of the spec's normalisation rule (`_document_key`: drop `#fragment`,
  drop one trailing `/`, case-fold) and its own reduction (`_expected_without`: rebuild the
  record with every citation of that document dropped, then call `confidence()`). An
  expectation read out of the rendered line would agree with any renderer, including one that
  printed the record's unchanged confidence 402 times.
* **Behavior 5's floor boundary HAS NO LIVE WITNESS AND CANNOT BE GIVEN ONE.** Measured over
  all 402 lines the live register produces, the values that occur are {0, 1, 3, 4, 5} and the
  floor (2) occurs ZERO times; searched over every source class and every pair of classes,
  `confidence()` cannot return 2 at all, so no fixture can put a citation ON the floor either.
  Every live line is therefore green under both `<` and `<=`, and the only discriminator is to
  MOVE the floor: at a patched floor of 5 the lines at exactly 5 must stay BARE (this is what
  a `<=` renderer fails) while the 143 below gain the suffix, and at a patched floor of 6 all
  402 must carry it. `_patch_floor` patches the constant wherever the package exposes it and
  ASSERTS that it patched at least one binding, so a renderer that typed `2` as a literal
  cannot read as healthy.
* **Behavior 6's "same document, different spelling" half has ZERO live witnesses**: 67 records
  cite one document more than once, but no live record spells one document two ways. The
  duplicate half is therefore asserted over the live register and the SPELLING half over a
  constructed record and a constructed register, and both halves ASSERT THEIR OWN PREMISE
  FIRST -- the voided value must DIFFER from the record's own confidence, because all spellings
  also agree when none of them matches anything (they agree on `confidence(gap)`).
* **Behavior 7 is asserted as CONFINEMENT here and measured as a DIFF out of band.** A
  suite-level comparison against `git show HEAD` is vacuous the moment this iteration lands, so
  the byte-for-byte HEAD-vs-worktree diff over all 120 briefs and all other verbs is measured
  once in the tester's report; what is durable and asserted here is that the added lines are
  the ONLY carrier of the new vocabulary, that `## Evidence` keeps its pinned five-line opening
  and that the `| Confidence |` table row still reads the record's own `confidence()`.
* **Every absence claim has a two-sided control in the same test**: the line matcher is shown
  to FIND the lines in a live brief and to return none for a document without them, so a broken
  matcher cannot read as silence.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every constructed locator uses `example.invalid`, which cannot
  resolve; no live locator is written down as a literal (they are read from the register).
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import pathlib
import re
from functools import lru_cache

import pytest

from agent_gap_radar import cli, render, scoring
from agent_gap_radar.models import Gap
from agent_gap_radar.registry import load_all

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

REGISTER: list[Gap] = load_all(GAPS_DIR)
BY_ID = {gap.id: gap for gap in REGISTER}
LIVE_IDS = sorted(BY_ID)

# The domain of nearly every assertion below, asserted rather than assumed: `load_all` accepts
# an empty directory and returns `[]`, and a loop over `[]` proves nothing.
assert len(REGISTER) > 100, f"live register too small to prove anything: {len(REGISTER)}"

#: Behavior 4's line, minus the number.
LINE_PREFIX = "- Confidence without this source document: "
#: Behaviors 4 + 5: the number, and the optional floor parenthetical with its own floor value.
LINE_RE = re.compile(rf"^{re.escape(LINE_PREFIX)}(\d+)(?: \(below floor (\d+)\))?$")
#: Vocabulary this iteration introduces. It may appear nowhere but on those lines.
NEW_VOCABULARY = "Confidence without this source document"

EVIDENCE_HEADING = "## Evidence"
LOCATOR_PREFIX = "- Locator: "
SOURCE_CLASS_PREFIX = "- Source class: "
DATE_PREFIX = "- Date: "
BLOCK_RE = re.compile(r"^### (\d+)\. ")

#: A locator no live record cites, used for behavior 3's "matches nothing" leg.
ABSENT_LOCATOR = "https://example.invalid/no-such-document"


# ---------------------------------------------------------------------------
# Running the product
# ---------------------------------------------------------------------------

def _run(argv: list[str]) -> tuple[int, str, str]:
    """Run the CLI in-process. Returns (exit code, stdout, stderr). No subprocess."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


@lru_cache(maxsize=None)
def _show(gap_id: str, root: str | None = None) -> str:
    code, out, err = _run(["show", gap_id, root or str(REPO_ROOT)])
    assert code == 0, (gap_id, code, err)
    assert err == "", err
    return out


# ---------------------------------------------------------------------------
# This file's OWN derivations -- never read out of the rendered document
# ---------------------------------------------------------------------------

def _document_key(locator: str) -> str:
    """The spec's normalisation written a SECOND, independent way, so `_doc` has a real
    two-sided control: drop `#fragment` FIRST, then drop exactly ONE trailing `/`, then
    case-fold.

    The order is the whole content of this helper. The previous version of it tested
    `locator.endswith("/")` -- False as soon as a fragment FOLLOWS the slash -- and then used
    `rstrip("/")`, which drops ALL trailing slashes; both defects were invisible because the
    control only fed it spellings no live locator has. `.../p/#s2` and `.../p//` are the two
    spellings that tell the orders apart, and `_spellings` now emits the first.
    """
    return re.sub(r"/\Z", "", re.sub(r"#.*\Z", "", locator, count=1), count=1).casefold()


def _doc(locator: str) -> str:
    """`_document_key` written the plain way, and cross-checked against it below."""
    head = locator.split("#", 1)[0]
    if head.endswith("/"):
        head = head[:-1]
    return head.casefold()


def _spellings(locator: str) -> tuple[str, ...]:
    """Spellings of ONE document the spec must treat as identical."""
    head = _doc(locator)
    return (
        locator,
        head,
        head + "/",
        head.upper(),
        head + "#section-2",
        head.upper() + "/",
        # Slash BEFORE fragment: the one spelling that separates "strip the fragment, then one
        # trailing slash" (the spec's order) from any other order. No live locator has it.
        head + "/#s2",
        head.upper() + "/#S3",
    )


def _expected_without(gap: Gap, locator: str) -> int:
    """The spec's own answer, derived by REDUCING the record and calling `confidence()`.

    Every citation whose SOURCE DOCUMENT is `locator` is dropped -- not just the citation
    whose locator string matches -- so this encodes behavior 6 ("this source retracted", never
    "this excerpt deleted") as well as behaviors 1 and 3.
    """
    target = _doc(locator)
    kept = [e for e in gap.evidence if _doc(e.locator) != target]
    if len(kept) == len(gap.evidence):
        return scoring.confidence(gap)
    return scoring.confidence(gap.model_copy(update={"evidence": kept}))


def _citation_locators(gap: Gap) -> list[str]:
    return [e.locator for e in gap.evidence]


# ---------------------------------------------------------------------------
# Reading the rendered document
# ---------------------------------------------------------------------------

def _new_lines(document: str) -> list[str]:
    """Every line of `document` carrying behavior 4's shape. Proved two-sided below."""
    return [line for line in document.splitlines() if line.startswith(LINE_PREFIX)]


def _blocks(document: str) -> list[list[str]]:
    """The body lines of each `### N.` block under `## Evidence`, in document order."""
    lines = document.splitlines()
    try:
        start = lines.index(EVIDENCE_HEADING)
    except ValueError as exc:  # pragma: no cover -- a brief without evidence is a defect
        raise AssertionError(f"{EVIDENCE_HEADING} missing from the brief") from exc
    blocks: list[list[str]] = []
    for line in lines[start + 1:]:
        if BLOCK_RE.match(line):
            blocks.append([])
        elif blocks is not None and blocks:
            blocks[-1].append(line)
    return blocks


def _section_names(document: str) -> list[str]:
    return [line for line in document.splitlines() if line.startswith("## ")]


def _evidence_section(document: str) -> str:
    lines = document.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.rstrip("\n") == EVIDENCE_HEADING)
    return "".join(lines[start:])


def _patch_floor(monkeypatch: pytest.MonkeyPatch, value: int) -> list[str]:
    """Rebind `CONFIDENCE_FLOOR_DEFAULT` everywhere the package exposes it.

    Behavior 5 says `<F>` is READ from that constant and never typed into the renderer, so the
    test moves the constant and requires the document to follow. The binding the renderer reads
    is an implementation choice this file must not know, so every module that exposes the name
    is patched and the test asserts it patched at least one.
    """
    patched = []
    for module in (scoring, render, cli):
        if hasattr(module, "CONFIDENCE_FLOOR_DEFAULT"):
            monkeypatch.setattr(module, "CONFIDENCE_FLOOR_DEFAULT", value)
            patched.append(module.__name__)
    assert patched, "CONFIDENCE_FLOOR_DEFAULT is exposed by no importable module"
    return patched


# ---------------------------------------------------------------------------
# Constructed records and registers (the live register lacks these shapes)
# ---------------------------------------------------------------------------

def _prototype_citations() -> dict[str, object]:
    """One live citation per source class, to be re-pointed at `example.invalid` locators."""
    proto: dict[str, object] = {}
    for gap in REGISTER:
        for citation in gap.evidence:
            proto.setdefault(citation.source_class, citation)
    return proto


PROTO = _prototype_citations()
assert {"peer-reviewed", "secondary-summary"} <= set(PROTO), sorted(PROTO)


def _citation(source_class: str, locator: str, title: str):
    return PROTO[source_class].model_copy(update={"locator": locator, "title": title})


def _variant_record() -> Gap:
    """One document spelled THREE ways, plus a second, weaker document.

    No live record has this shape (measured: 0 of 120), so the normalisation half of
    behaviors 2 and 6 has no live witness and is proved here.
    """
    base = REGISTER[0]
    evidence = [
        _citation("peer-reviewed", "https://example.invalid/p", "One document, plain"),
        _citation("peer-reviewed", "https://example.invalid/p/", "One document, trailing slash"),
        _citation("peer-reviewed", "https://example.invalid/P#s2", "One document, case+fragment"),
        _citation("secondary-summary", "https://example.invalid/q", "A second, weaker document"),
    ]
    return base.model_copy(update={"evidence": evidence})


def _register(root: pathlib.Path, records: list[Gap]) -> pathlib.Path:
    """Write `records` as a register under `root/gaps/` and return `root`."""
    gaps = root / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    for record in records:
        payload = json.loads(record.model_dump_json())
        (gaps / f"{record.id}.json").write_text(
            json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8"
        )
    loaded = load_all(gaps)
    assert len(loaded) == len(records), (len(loaded), len(records))
    return root


# ---------------------------------------------------------------------------
# Controls: the matchers and this file's own derivations are two-sided
# ---------------------------------------------------------------------------

def test_control_the_line_matcher_is_two_sided() -> None:
    """A matcher that found nothing would report every absence claim green."""
    live = _show(LIVE_IDS[0])
    assert _new_lines(live), "matcher found no line in a brief that must carry them"
    stripped = "\n".join(l for l in live.splitlines() if not l.startswith(LINE_PREFIX)) + "\n"
    assert _new_lines(stripped) == [], "matcher fired on a document with the lines removed"
    assert NEW_VOCABULARY not in stripped, "the vocabulary survives outside the added lines"


def test_control_this_files_two_normalisations_agree_on_every_live_locator() -> None:
    """The expectation helper is only trustworthy if its own key rule is consistent.

    Live locators alone are NOT enough: they all lack a fragment and a trailing slash, so two
    disagreeing implementations agree on every one of them. The degenerate spellings below are
    the ones that discriminate, and `_spellings` now emits a slash-before-fragment form too.
    """
    degenerate = [
        "https://example.invalid/p", "https://example.invalid/p/", "https://example.invalid/p//",
        "https://example.invalid/p#s2", "https://example.invalid/p/#s2",
        "HTTPS://EXAMPLE.INVALID/P/#S2", "", "#", "#frag", "/", "///", " ", "not a url",
    ]
    for spelling in degenerate:
        assert _document_key(spelling) == _doc(spelling), spelling
    for gap in REGISTER:
        for locator in _citation_locators(gap):
            for spelling in _spellings(locator):
                assert _document_key(spelling) == _doc(spelling), spelling


def test_control_no_evidence_combination_can_score_exactly_the_floor() -> None:
    """WHY behavior 5's boundary has to be probed by MOVING the floor instead of by a fixture.

    Measured here rather than asserted in a comment: over every combination of up to four
    cited documents drawn from every source class the register uses, `confidence()` returns a
    value in {0, 1, 3, 4, 5} and NEVER the floor (2). So no document -- live or constructed --
    can put a citation ON the floor, every rendered line is green under both `<` and `<=`, and
    the only discriminator left is `_patch_floor`. If a future scoring change makes the floor
    reachable this control goes RED, which is the signal that a real boundary fixture is now
    possible and behavior 5 should get one.
    """
    floor = scoring.CONFIDENCE_FLOOR_DEFAULT
    classes = sorted(PROTO)
    assert len(classes) >= 5, classes
    base = REGISTER[0]
    reachable: set[int] = set()
    for size in range(0, 5):
        for combo in itertools.combinations_with_replacement(classes, size):
            evidence = [
                _citation(source_class, f"https://example.invalid/d{index}", f"Doc {index}")
                for index, source_class in enumerate(combo)
            ]
            reachable.add(scoring.confidence(base.model_copy(update={"evidence": evidence})))
    assert 0 in reachable and max(reachable) >= floor, reachable
    assert floor not in reachable, (floor, sorted(reachable))


# ---------------------------------------------------------------------------
# Behavior 1 -- confidence_without reaches the score only through confidence()
# ---------------------------------------------------------------------------

def test_b1_confidence_without_returns_an_int_for_every_live_citation() -> None:
    total = 0
    for gap in REGISTER:
        for locator in _citation_locators(gap):
            value = scoring.confidence_without(gap, locator)
            assert isinstance(value, int) and not isinstance(value, bool), (gap.id, value)
            assert 0 <= value <= scoring.confidence(gap), (gap.id, locator, value)
            total += 1
    assert total == sum(len(g.evidence) for g in REGISTER) > 100, total


def test_b1_the_value_equals_an_independent_reduction_over_the_whole_register() -> None:
    """Derived, not lifted: rebuild the record without that document and call `confidence()`."""
    checked = 0
    for gap in REGISTER:
        for locator in _citation_locators(gap):
            assert scoring.confidence_without(gap, locator) == _expected_without(gap, locator), (
                gap.id, locator
            )
            checked += 1
    assert checked == 402 or checked > 100, checked


def test_b1_patching_confidence_is_observable_in_the_result(monkeypatch) -> None:
    """The seam: the answer must come from `confidence()` on a REDUCED stand-in.

    The stub returns a value that encodes the size of the evidence tuple it was handed, so a
    re-derivation of the arithmetic fails (it never sees the stub) and so does a call that
    passes the WHOLE record (the size would not shrink).
    """
    gap = next(g for g in REGISTER if len(g.evidence) >= 2)
    locator = gap.evidence[0].locator
    dropped = sum(1 for e in gap.evidence if _doc(e.locator) == _doc(locator))
    assert dropped >= 1, gap.id
    real = scoring.confidence_without(gap, locator)

    monkeypatch.setattr(scoring, "confidence", lambda g: 1000 + len(g.evidence))
    patched = scoring.confidence_without(gap, locator)
    assert patched == 1000 + len(gap.evidence) - dropped, (gap.id, patched, dropped)
    assert patched != real, "the stub is indistinguishable from the real score"


def test_b1_the_call_is_pure_and_repeatable() -> None:
    """`pure` in the acceptance criteria: the record it is handed must come back untouched, and
    a second call must answer the same. A probe that mutated the record in place would corrupt
    every later reader in the process, and the corruption would show up as an unrelated test."""
    for gap in REGISTER[:20]:
        before = tuple((e.locator, e.source_class, e.quote) for e in gap.evidence)
        confidence_before = scoring.confidence(gap)
        first = [scoring.confidence_without(gap, loc) for loc in _citation_locators(gap)]
        second = [scoring.confidence_without(gap, loc) for loc in _citation_locators(gap)]
        assert first == second, gap.id
        after = tuple((e.locator, e.source_class, e.quote) for e in gap.evidence)
        assert after == before, gap.id
        assert scoring.confidence(gap) == confidence_before, gap.id


# ---------------------------------------------------------------------------
# Behavior 2 -- source identity is the DOCUMENT, under one shared normalisation
# ---------------------------------------------------------------------------

def test_b2_every_spelling_of_one_document_returns_the_SAME_CHANGED_value() -> None:
    """The premise is asserted first: all spellings also agree when NONE of them matches."""
    record = _variant_record()
    unchanged = scoring.confidence(record)
    canonical = "https://example.invalid/p"
    voided = scoring.confidence_without(record, canonical)
    assert voided != unchanged, ("premise failed: voiding changes nothing", voided, unchanged)
    for spelling in _spellings(canonical):
        assert scoring.confidence_without(record, spelling) == voided, spelling


def test_b2_the_scorers_own_source_key_collapses_the_same_spellings() -> None:
    """`_source_key` and `confidence_without` must key on ONE rule, so both must collapse the
    three spellings of `/p` to one document: the record has 4 citations and 2 documents."""
    record = _variant_record()
    assert len(record.evidence) == 4
    assert scoring.distinct_sources(record) == 2, scoring.distinct_sources(record)
    assert len({scoring._source_key(e) for e in record.evidence}) == 2


def test_b2_respelling_every_live_locator_moves_neither_surface() -> None:
    """Over the live register: a record whose locators are re-spelled (case, trailing slash,
    fragment) must score the same and count the same distinct sources -- and
    `confidence_without` must answer the same for every spelling of the same document."""
    for gap in REGISTER:
        respelled = gap.model_copy(update={
            "evidence": [
                e.model_copy(update={"locator": _doc(e.locator).upper() + "/#s9"})
                for e in gap.evidence
            ]
        })
        assert scoring.confidence(respelled) == scoring.confidence(gap), gap.id
        assert scoring.distinct_sources(respelled) == scoring.distinct_sources(gap), gap.id
        for locator in _citation_locators(gap):
            base = scoring.confidence_without(gap, locator)
            for spelling in _spellings(locator):
                assert scoring.confidence_without(gap, spelling) == base, (gap.id, spelling)


# ---------------------------------------------------------------------------
# Behavior 3 -- totality, no raises
# ---------------------------------------------------------------------------

def test_b3_a_locator_matching_no_citation_returns_the_records_own_confidence() -> None:
    for gap in REGISTER:
        assert scoring.confidence_without(gap, ABSENT_LOCATOR) == scoring.confidence(gap), gap.id


def test_b3_voiding_the_only_cited_document_returns_zero() -> None:
    sole = [g for g in REGISTER if len({_doc(e.locator) for e in g.evidence}) == 1]
    assert len(sole) > 0, "no live sole-source record to witness the zero leg"
    for gap in sole:
        assert scoring.confidence_without(gap, gap.evidence[0].locator) == 0, gap.id
    # And the same, constructed, so the leg survives a register that loses its witnesses.
    single = REGISTER[0].model_copy(update={
        "evidence": [_citation("peer-reviewed", "https://example.invalid/only", "Only source")]
    })
    assert scoring.confidence_without(single, "https://example.invalid/only") == 0


def test_b3_an_empty_evidence_tuple_returns_zero() -> None:
    empty = REGISTER[0].model_copy(update={"evidence": []})
    assert scoring.confidence(empty) == 0, "premise: an unevidenced record scores 0"
    assert scoring.confidence_without(empty, ABSENT_LOCATOR) == 0
    assert scoring.confidence_without(empty, REGISTER[0].evidence[0].locator) == 0


@pytest.mark.parametrize("locator", ["", "#", "/", "///", "#frag", " ", "not a url"])
def test_b3_no_raises_on_degenerate_locators(locator: str) -> None:
    for gap in REGISTER[:5]:
        value = scoring.confidence_without(gap, locator)
        assert isinstance(value, int) and 0 <= value <= 5, (gap.id, locator, value)


# ---------------------------------------------------------------------------
# Behavior 4 -- exactly one added line per citation, in a pinned position
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gap_id", LIVE_IDS)
def test_b4_one_line_per_citation_with_the_derived_number(gap_id: str) -> None:
    gap = BY_ID[gap_id]
    document = _show(gap_id)
    lines = _new_lines(document)
    assert len(lines) == len(gap.evidence), (gap_id, len(lines), len(gap.evidence))
    numbers = []
    for line in lines:
        match = LINE_RE.match(line)
        assert match, (gap_id, repr(line))
        numbers.append(int(match.group(1)))
    assert numbers == [_expected_without(gap, e.locator) for e in gap.evidence], (gap_id, numbers)


@pytest.mark.parametrize("gap_id", LIVE_IDS)
def test_b4_the_line_sits_immediately_after_the_blocks_locator_line(gap_id: str) -> None:
    """Pinned order inside each `### N.` block: Source class, Date, Locator, then this line."""
    gap = BY_ID[gap_id]
    blocks = _blocks(_show(gap_id))
    assert len(blocks) == len(gap.evidence), (gap_id, len(blocks))
    for index, (block, citation) in enumerate(zip(blocks, gap.evidence), start=1):
        bullets = [l for l in block if l.startswith("- ")]
        assert bullets[0].startswith(SOURCE_CLASS_PREFIX), (gap_id, index, bullets[:4])
        assert bullets[1].startswith(DATE_PREFIX), (gap_id, index, bullets[:4])
        assert bullets[2] == f"{LOCATOR_PREFIX}{citation.locator}", (gap_id, index, bullets[2])
        assert bullets[3].startswith(LINE_PREFIX), (gap_id, index, bullets[3])
        assert len([l for l in block if l.startswith(LINE_PREFIX)]) == 1, (gap_id, index)
        locator_at = block.index(bullets[2])
        assert block[locator_at + 1] == bullets[3], (gap_id, index, block[locator_at:locator_at + 2])


# ---------------------------------------------------------------------------
# Behavior 5 -- the floor parenthetical, and the floor it reads
# ---------------------------------------------------------------------------

def test_b5_the_suffix_tracks_the_floor_over_every_live_line() -> None:
    floor = scoring.CONFIDENCE_FLOOR_DEFAULT
    seen_below = seen_at_or_above = 0
    for gap_id in LIVE_IDS:
        for line in _new_lines(_show(gap_id)):
            match = LINE_RE.match(line)
            assert match, (gap_id, repr(line))
            value, stated = int(match.group(1)), match.group(2)
            if value < floor:
                assert stated is not None, (gap_id, line, floor)
                assert int(stated) == floor, (gap_id, line, floor)
                assert line.endswith(f": {value} (below floor {floor})"), (gap_id, line)
                seen_below += 1
            else:
                assert stated is None, (gap_id, line, floor)
                assert line == f"{LINE_PREFIX}{value}", (gap_id, line)
                seen_at_or_above += 1
    assert seen_below > 0 and seen_at_or_above > 0, (seen_below, seen_at_or_above)


def test_b5_moving_the_floor_moves_the_annotation_and_its_stated_value(monkeypatch) -> None:
    """The boundary discriminator. No live line sits ON the floor, so `<` and `<=` agree on
    every live document; at a floor of 5 the lines AT 5 must stay bare, which is exactly what
    a `<=` renderer gets wrong, and the stated floor must be the patched 5, not a literal 2."""
    _show.cache_clear()
    try:
        _patch_floor(monkeypatch, 5)
        bare = suffixed = 0
        for gap_id in LIVE_IDS:
            for line in _new_lines(_show(gap_id)):
                match = LINE_RE.match(line)
                assert match, (gap_id, repr(line))
                value, stated = int(match.group(1)), match.group(2)
                if value < 5:
                    assert stated == "5", (gap_id, line)
                    suffixed += 1
                else:
                    assert value == 5 and stated is None, (gap_id, line)
                    bare += 1
        assert bare > 0 and suffixed > 0, (bare, suffixed)
    finally:
        _show.cache_clear()


def test_b5_a_floor_above_every_value_annotates_every_line(monkeypatch) -> None:
    _show.cache_clear()
    try:
        _patch_floor(monkeypatch, 6)
        lines = [line for gap_id in LIVE_IDS for line in _new_lines(_show(gap_id))]
        assert len(lines) > 100, len(lines)
        for line in lines:
            match = LINE_RE.match(line)
            assert match and match.group(2) == "6", repr(line)
    finally:
        _show.cache_clear()


# ---------------------------------------------------------------------------
# Behavior 6 -- one document retracted, not one excerpt deleted
# ---------------------------------------------------------------------------

def test_b6_live_duplicate_citations_of_one_document_report_one_shared_number() -> None:
    witnesses = 0
    for gap_id in LIVE_IDS:
        gap = BY_ID[gap_id]
        keys = [_doc(e.locator) for e in gap.evidence]
        duplicated = {k for k in keys if keys.count(k) >= 2}
        if not duplicated:
            continue
        witnesses += 1
        lines = _new_lines(_show(gap_id))
        for key in duplicated:
            positions = [i for i, k in enumerate(keys) if k == key]
            reported = {lines[i] for i in positions}
            assert len(reported) == 1, (gap_id, key, reported)
            kept = [e for e in gap.evidence if _doc(e.locator) != key]
            expected = 0 if not kept else scoring.confidence(
                gap.model_copy(update={"evidence": kept})
            )
            assert LINE_RE.match(next(iter(reported))).group(1) == str(expected), (
                gap_id, key, reported, expected
            )
    assert witnesses > 10, f"too few live duplicate-document records to prove behavior 6: {witnesses}"


def test_b6_the_brief_reports_one_number_for_three_spellings_of_one_document(tmp_path) -> None:
    """Rendered end to end on a constructed register, because the live one has no such record."""
    record = _variant_record()
    root = _register(tmp_path, [record])
    document = _show(record.id, str(root))
    lines = _new_lines(document)
    assert len(lines) == 4, lines
    variant_lines, other_line = lines[:3], lines[3]
    assert len(set(variant_lines)) == 1, variant_lines
    weaker_only = record.model_copy(update={"evidence": [record.evidence[3]]})
    expected = scoring.confidence(weaker_only)
    assert expected != scoring.confidence(record), "premise: voiding /p must change the score"
    floor = scoring.CONFIDENCE_FLOOR_DEFAULT
    suffix = f" (below floor {floor})" if expected < floor else ""
    assert variant_lines[0] == f"{LINE_PREFIX}{expected}{suffix}", variant_lines[0]
    strong_only = record.model_copy(update={"evidence": list(record.evidence[:3])})
    other_expected = scoring.confidence(strong_only)
    other_suffix = f" (below floor {floor})" if other_expected < floor else ""
    assert other_line == f"{LINE_PREFIX}{other_expected}{other_suffix}", other_line


# ---------------------------------------------------------------------------
# Behavior 7 -- nothing else in the brief moves
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gap_id", LIVE_IDS)
def test_b7_the_added_lines_are_the_only_carrier_of_the_new_vocabulary(gap_id: str) -> None:
    document = _show(gap_id)
    gap = BY_ID[gap_id]
    assert document.count(NEW_VOCABULARY) == len(gap.evidence), gap_id
    evidence = _evidence_section(document)
    assert evidence.count(NEW_VOCABULARY) == len(gap.evidence), gap_id
    outside = document.replace(evidence, "")
    assert NEW_VOCABULARY not in outside, gap_id
    assert "confidence_without" not in document, gap_id


@pytest.mark.parametrize("gap_id", LIVE_IDS)
def test_b7_the_evidence_opening_and_the_confidence_row_are_unmoved(gap_id: str) -> None:
    """The pinned opening (heading, blank, count line, blank, `### 1.`) and the table row."""
    gap = BY_ID[gap_id]
    lines = _show(gap_id).splitlines()
    start = lines.index(EVIDENCE_HEADING)
    assert lines[start + 1] == "", lines[start:start + 5]
    assert lines[start + 2].startswith(f"{len(gap.evidence)} citation"), lines[start + 2]
    assert "distinct source document" in lines[start + 2], lines[start + 2]
    assert lines[start + 3] == "", lines[start:start + 5]
    assert lines[start + 4].startswith("### 1. "), lines[start:start + 5]
    row = [l for l in lines if l.startswith("| Confidence |")]
    assert row == [f"| Confidence | {scoring.confidence(gap)} |"], (gap_id, row)


def test_b7_every_quote_line_survives_untouched() -> None:
    """A renderer that rebuilt the block could drop or requote evidence; the quotes are data."""
    for gap_id in LIVE_IDS:
        document = _show(gap_id)
        for citation in BY_ID[gap_id].evidence:
            assert f"> {citation.quote}" in document, (gap_id, citation.locator)


# ---------------------------------------------------------------------------
# Behavior 8 -- the new number enters no other verb, no score, no ordering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["report"], ["list"], ["list", "--json"], ["prd", "--gap", LIVE_IDS[0]], ["prd"],
])
def test_b8_no_other_verb_learns_the_new_vocabulary(argv: list[str]) -> None:
    assert NEW_VOCABULARY in _show(LIVE_IDS[0]), "control: the detector must find it in show"
    code, out, err = _run([*argv, str(REPO_ROOT)])
    assert code == 0, (argv, code, err)
    assert err == "", err
    assert NEW_VOCABULARY not in out, argv
    assert "below floor" not in out, argv
    assert out.endswith("\n") and not out.endswith("\n\n"), argv


def test_b8_list_json_carries_no_new_key() -> None:
    """The payload gains NO key. `below_floor` is deliberately NOT in the forbidden set: it is
    a pre-existing key of this payload (measured -- `list --json` is byte-identical to HEAD),
    so forbidding it would red a correct repo. What is forbidden is the vocabulary THIS
    iteration introduces, and any key naming the counterfactual at all."""
    code, out, _ = _run(["list", "--json", str(REPO_ROOT)])
    assert code == 0
    payload = json.loads(out)
    blob = json.dumps(payload)
    for token in ("confidence_without", "without_source", "without this source", NEW_VOCABULARY):
        assert token not in blob, token
    keys = set(payload) | {k for record in payload["records"] for k in record}
    assert keys, "control: the payload exposes keys the check can read"
    assert not [k for k in keys if "without" in k], sorted(keys)


@pytest.mark.parametrize("gap_id", LIVE_IDS)
def test_b8_show_still_ends_in_exactly_one_newline(gap_id: str) -> None:
    document = _show(gap_id)
    assert document.endswith("\n") and not document.endswith("\n\n"), gap_id


def test_b8_the_new_number_enters_no_ordering(monkeypatch) -> None:
    """`list` order and `priority` must be blind to the counterfactual: patching
    `confidence_without` to a constant may not move either."""
    before = _run(["list", str(REPO_ROOT)])[1]
    priorities = [scoring.priority(g) for g in REGISTER]
    monkeypatch.setattr(scoring, "confidence_without", lambda gap, locator: 0)
    assert _run(["list", str(REPO_ROOT)])[1] == before
    assert [scoring.priority(g) for g in REGISTER] == priorities


# ---------------------------------------------------------------------------
# Behavior 9 -- anti-vacuity, asserted against the LIVE register
# ---------------------------------------------------------------------------

def test_b9_a_live_citation_is_worth_a_point_to_its_record() -> None:
    droppers = [
        (gap.id, locator)
        for gap in REGISTER
        for locator in _citation_locators(gap)
        if scoring.confidence_without(gap, locator) < scoring.confidence(gap)
    ]
    assert len(droppers) > 0, "no live citation moves its record's confidence: line is vacuous"


def test_b9_both_floor_branches_are_witnessed_live() -> None:
    floor = scoring.CONFIDENCE_FLOOR_DEFAULT
    crossers = []
    holders = 0
    for gap in REGISTER:
        confidence = scoring.confidence(gap)
        for locator in _citation_locators(gap):
            value = scoring.confidence_without(gap, locator)
            if confidence >= floor > value:
                crossers.append((gap.id, confidence, value))
            elif value >= floor:
                holders += 1
    assert len(crossers) > 0, "no live record crosses the floor: the suffix branch is unwitnessed"
    assert holders > 0, "no live line sits at or above the floor: the bare branch is unwitnessed"


def test_b9_a_live_record_cites_one_document_twice_with_one_shared_number() -> None:
    shared = 0
    for gap in REGISTER:
        keys = [_doc(e.locator) for e in gap.evidence]
        for key in {k for k in keys if keys.count(k) >= 2}:
            values = {
                scoring.confidence_without(gap, e.locator)
                for e in gap.evidence
                if _doc(e.locator) == key
            }
            assert len(values) == 1, (gap.id, key, values)
            shared += 1
    assert shared > 0, "no live record cites one document twice: behavior 6 is unwitnessed"


# ---------------------------------------------------------------------------
# Extensions (tester round 3): the shared normalisation on a RENDERED surface,
# byte-stability of the brief, and the below-floor record the invariant protects
# ---------------------------------------------------------------------------

def _all_spellings_of_one_document(document: str) -> tuple[str, ...]:
    """Eight spellings the spec's normalisation must collapse to ONE document.

    Wider than `_spellings`: this one carries NO second document, so voiding the single
    document under ANY spelling must take the record to 0. A `confidence_without` that
    matched on the raw locator string would answer the record's unchanged confidence for
    seven of the eight, and `distinct_sources` would read 8 instead of 1.
    """
    head = _doc(document)
    return (
        head,
        head + "/",
        head + "//",
        head.upper(),
        head + "#s2",
        head.upper() + "/",
        head + "/#s3",
        head.upper() + "/#S4",
    )


def test_b2_eight_spellings_of_one_document_are_one_source_on_both_surfaces(tmp_path) -> None:
    """Behavior 2, joint constraint: `distinct_sources`, `_source_key`, `confidence()` and
    `confidence_without` must ALL read one document here, and the brief must render 8 identical
    lines. Both halves of the spec's "in both places by construction" claim are checked against
    the SAME spellings, including the slash-before-fragment form no live locator has.
    """
    spellings = _all_spellings_of_one_document("https://example.invalid/one")
    assert len(set(spellings)) == 8, spellings
    record = REGISTER[0].model_copy(update={
        "evidence": [
            _citation("peer-reviewed", spelling, f"One document, spelling {index}")
            for index, spelling in enumerate(spellings)
        ]
    })
    # The scorer's own key rule, and the count the brief publishes.
    assert scoring.distinct_sources(record) == 1, scoring.distinct_sources(record)
    assert len({scoring._source_key(e) for e in record.evidence}) == 1
    # Independence is counted by document, so 8 citations of one document score what 1 does.
    single = record.model_copy(update={"evidence": [record.evidence[0]]})
    assert scoring.confidence(record) == scoring.confidence(single), (
        scoring.confidence(record), scoring.confidence(single)
    )
    # Premise first: the document is worth something, so a wrong key cannot pass by voiding zero.
    assert scoring.confidence(record) > 0, "premise: the sole document must be worth a point"
    for spelling in spellings:
        assert scoring.confidence_without(record, spelling) == 0, spelling

    # Rendered end to end: 8 identical lines, all below the floor, all stating it.
    document = _show(record.id, str(_register(tmp_path, [record])))
    lines = _new_lines(document)
    floor = scoring.CONFIDENCE_FLOOR_DEFAULT
    assert lines == [f"{LINE_PREFIX}0 (below floor {floor})"] * 8, lines


@pytest.mark.parametrize("gap_id", LIVE_IDS)
def test_b2_the_rendered_denominator_uses_the_same_normalisation(gap_id: str) -> None:
    """The `## Evidence` count line already publishes "citations across distinct source
    documents". That denominator and the new line must key on ONE rule, so it is checked
    against THIS file's independent normalisation as well as against `distinct_sources`.
    """
    gap = BY_ID[gap_id]
    documents = {_doc(e.locator) for e in gap.evidence}
    lines = _show(gap_id).splitlines()
    count_line = lines[lines.index(EVIDENCE_HEADING) + 2]
    match = re.match(r"^(\d+) citations? across (\d+) distinct source documents?\b", count_line)
    assert match, (gap_id, count_line)
    assert int(match.group(1)) == len(gap.evidence), (gap_id, count_line)
    assert int(match.group(2)) == len(documents), (gap_id, count_line, sorted(documents))
    assert scoring.distinct_sources(gap) == len(documents), gap_id


def test_b7_every_brief_is_byte_stable_across_repeated_renders() -> None:
    """The quality bar is byte-stable output, and the new value is derived per citation. A
    derivation that iterated a set (of source keys, of documents) could reorder or re-value
    between renders; `_show` is memoised, so this renders each brief a SECOND time by hand.
    """
    checked = 0
    for gap_id in LIVE_IDS:
        first = _show(gap_id)
        code, second, err = _run(["show", gap_id, str(REPO_ROOT)])
        assert code == 0 and err == "", (gap_id, code, err)
        assert second == first, gap_id
        checked += 1
    assert checked > 100, checked


def test_b9_a_record_already_below_the_floor_still_publishes_every_line() -> None:
    """The register's protected invariant is that below-floor records are DISPLAYED, never
    dropped, so the weakest records are exactly the ones whose counterfactual must still be
    there. This also reconciles behavior 9's two counts: a line can be below the floor without
    CROSSING it, because its record was already below.
    """
    floor = scoring.CONFIDENCE_FLOOR_DEFAULT
    weak = [gap for gap in REGISTER if scoring.confidence(gap) < floor]
    assert weak, "no live record sits below the floor: this leg is unwitnessed"
    for gap in weak:
        lines = _new_lines(_show(gap.id))
        assert len(lines) == len(gap.evidence), (gap.id, len(lines))
        for line in lines:
            match = LINE_RE.match(line)
            assert match, (gap.id, repr(line))
            value = int(match.group(1))
            assert value <= scoring.confidence(gap) < floor, (gap.id, line)
            assert match.group(2) == str(floor), (gap.id, line)
