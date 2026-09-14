"""The union identity the memo now RELIES on, asserted over the committed register.

`checks.iter_files` refuses to sort or dedupe its set-level key because normalising it
would ASSERT that a domain is the union of its globs and that order and repetition
cannot change the answer -- and its docstring says that if the assertion were ever
false "the failure would be silent". Iteration 219 stopped arguing that invariant in
prose and started RELYING on it: a multi-glob domain is now ASSEMBLED as the union of
its per-glob domains. This module is the citation both `_memoised_domain` and
`iter_files` name, and it is what makes the reliance falsifiable.

THE ORACLE IS THE OLD CODE PATH, NOT A RE-DERIVED EXPECTATION. Every expectation here
is a direct, unmemoised `_enumerate_files(target, whole_set, exclude_tests)` -- exactly
what `iter_files` returned before this change -- computed OUTSIDE any scope so no frame
can answer it. A test that rebuilt the expectation by unioning per-glob calls itself
would agree with the new assembly by construction and could not see the defect it
exists to catch.

THE DOMAIN IS THE WHOLE REGISTER, NOT A SAMPLE. Every `globs` list under `check.*` in
`gaps/*.json` is collected, at every nesting depth (`present_when.globs`,
`...rules[].globs`, `...rules[].rule.rules[].globs`), and every distinct set is asked
under BOTH `exclude_tests` values. Measured today against this repo as its own target:
528 glob-list mentions, 100 distinct sets (97 multi-glob, largest 22 globs), 200 cases,
0 mismatches. Register-derived sizes are asserted as FLOORS with a re-derive message,
the repo's convention for a live-register domain; the arithmetic identities between
those sizes are asserted EXACTLY, because they are properties of the code, not of the
register's current contents.

WHY EACH ASSERTION HAS A CONTROL
* Equality alone can pass vacuously: an empty domain equals an empty domain, and a set
  whose files all come from one glob equals that glob's own domain. So the identity test
  also requires that most cases are non-empty and that many cases have a union STRICTLY
  larger than EVERY one of its per-glob domains (measured: 92), i.e. the union step is
  doing work that no single glob could account for.
* The assembly is checked at the FRAME, not only at the return value: for a multi-glob
  case the set entry must equal `sorted` of the union of the per-glob entries that sit
  beside it. A correct answer produced by quietly enumerating the whole set anyway would
  pass a return-value comparison and red here.
* The prize is asserted as a COUNT, never as seconds (`tools/scan_cost.py`'s doctrine),
  and the counted calls must every one carry a SINGLE-element `globs` argument -- the
  observable difference between per-glob matching and per-set matching.

`tmp_path` is deliberately NOT used: the invariant being relied on is about the globs the
REGISTER actually holds against a real tree, and a synthetic tree would answer most of
those globs with an empty list, which is the one answer that cannot discriminate.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from agent_gap_radar import checks
from agent_gap_radar.checks import _FILE_CACHE_STACK, file_cache_scope, iter_files

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: Measured 2026-09 on the 120-record register with this repo as target. Floors, not
#: equalities: the register grows, and a shrinking one should say so loudly rather than
#: silently narrowing this module's domain.
MIN_MENTIONS = 500
MIN_DISTINCT_SETS = 90
MIN_MULTI_GLOB_SETS = 85
MIN_NON_EMPTY_CASES = 150
MIN_STRICTLY_UNIONED_CASES = 60


def _glob_lists(node: object, found: list[tuple[str, ...]]) -> None:
    """Every `globs` list anywhere under a `check` payload, at any nesting depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            if (key == "globs" and isinstance(value, list)
                    and all(isinstance(item, str) for item in value)):
                found.append(tuple(value))
            else:
                _glob_lists(value, found)
    elif isinstance(node, list):
        for item in node:
            _glob_lists(item, found)


def _census() -> tuple[list[tuple[str, ...]], list[tuple[str, ...]]]:
    """`(every mention, distinct sets sorted)` read from the JSON on disk as DATA."""
    mentions: list[tuple[str, ...]] = []
    for path in sorted(GAPS_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        _glob_lists(payload.get("check") or {}, mentions)
    return mentions, sorted(set(mentions))


MENTIONS, GLOB_SETS = _census()
CASES = tuple((globs, exclude_tests)
              for globs in GLOB_SETS for exclude_tests in (False, True))


class _Measured:
    """One pass over every case: the unmemoised oracle, then the memoised assembly."""

    def __init__(self) -> None:
        assert _FILE_CACHE_STACK == [], "a leaked frame would answer the oracle"
        # The oracle FIRST and outside any scope: this is the pre-change code path.
        self.direct = {
            case: checks._enumerate_files(REPO_ROOT, list(case[0]), case[1])
            for case in CASES
        }
        self.calls: list[tuple[tuple[str, ...], bool]] = []
        real = checks._enumerate_files

        def spy(target: pathlib.Path, globs: list[str],
                exclude_tests: bool) -> list[pathlib.Path]:
            self.calls.append((tuple(globs), exclude_tests))
            return real(target, globs, exclude_tests)

        checks._enumerate_files = spy  # type: ignore[assignment]
        try:
            # ONE scope for every case, which is the production shape: a scan holds one
            # frame and many rules ask it, so a glob shared by two sets is matched once.
            with file_cache_scope() as frame:
                self.assembled = {
                    case: iter_files(REPO_ROOT, list(case[0]), case[1])
                    for case in CASES
                }
                self.frame = {key: list(value) for key, value in frame.items()}
        finally:
            checks._enumerate_files = real  # type: ignore[assignment]


@pytest.fixture(scope="module")
def measured() -> _Measured:
    """Computed once per module: the pass costs ~1.5s, and three tests read it."""
    return _Measured()


def test_the_census_covers_the_whole_register_and_is_not_a_sample():
    """The domain guard. Every later assertion is only as strong as this census, so a
    walk that silently stopped matching the register's nesting must red HERE."""
    assert len(MENTIONS) >= MIN_MENTIONS, (
        f"only {len(MENTIONS)} glob-list mentions found under check.*; the walk stopped "
        "seeing the register's nesting, or the register shrank -- re-derive this module")
    assert len(GLOB_SETS) >= MIN_DISTINCT_SETS, (
        f"only {len(GLOB_SETS)} distinct glob sets; re-derive this module's floors")
    multi = [globs for globs in GLOB_SETS if len(globs) > 1]
    assert len(multi) >= MIN_MULTI_GLOB_SETS, (
        f"only {len(multi)} multi-glob sets: the union path is barely exercised")
    assert max(len(globs) for globs in GLOB_SETS) >= 10, (
        "no large glob set left in the register; the assembly is untested at width")
    assert len(CASES) == 2 * len(GLOB_SETS), "each set must be asked under both values"


def test_every_committed_glob_set_unions_to_a_direct_enumeration(measured):
    """THE invariant `iter_files` now relies on, over every set the register holds and
    both `exclude_tests` values, against the unmemoised whole-set enumeration."""
    mismatched = [case for case in CASES
                  if measured.assembled[case] != measured.direct[case]]
    assert mismatched == [], (
        f"{len(mismatched)} of {len(CASES)} committed glob sets do not equal their "
        f"per-glob union; first: {mismatched[:2]}")

    # Controls against a vacuous pass.
    non_empty = [case for case in CASES if measured.direct[case]]
    assert len(non_empty) >= MIN_NON_EMPTY_CASES, (
        f"only {len(non_empty)} of {len(CASES)} cases have any files: equality here "
        "would be an agreement between empty lists")
    strict = [
        case for case in CASES
        if len(case[0]) > 1 and measured.direct[case] and all(
            len(measured.direct[case]) > len(measured.direct[((glob,), case[1])])
            for glob in case[0] if ((glob,), case[1]) in measured.direct)
    ]
    assert len(strict) >= MIN_STRICTLY_UNIONED_CASES, (
        f"only {len(strict)} cases are strictly larger than EVERY one of their "
        "per-glob domains, so the union step is not measurably doing anything")


def test_the_frame_shows_the_union_being_assembled_from_its_per_glob_entries(measured):
    """Not just the right answer, the right MECHANISM: a set entry equals `sorted` of the
    union of the per-glob entries sitting beside it in the same frame. An implementation
    that quietly enumerated the whole set anyway would pass the test above and red here."""
    checked = 0
    for globs, exclude_tests in CASES:
        set_key = (str(REPO_ROOT), globs, exclude_tests)
        assert set_key in measured.frame, f"no frame entry for {set_key}"
        if len(globs) <= 1:
            continue
        union: set[pathlib.Path] = set()
        for glob in globs:
            per_glob_key = (str(REPO_ROOT), (glob,), exclude_tests)
            assert per_glob_key in measured.frame, (
                f"{glob!r} was never memoised on its own, so the set was not assembled "
                "per glob")
            union.update(measured.frame[per_glob_key])
        assert measured.frame[set_key] == sorted(union), (
            f"the frame's entry for {globs} is not the union of its per-glob entries")
        checked += 1
    assert checked >= MIN_MULTI_GLOB_SETS, f"only {checked} multi-glob cases checked"


def test_each_glob_is_matched_once_per_scope_and_only_ever_alone(measured):
    """The prize, stated as a COUNT and never as seconds. Every enumeration inside the
    scope carries a SINGLE glob, and one enumeration happens per distinct
    `(one glob, exclude_tests)` pair no matter how many sets mention it."""
    assert all(len(globs) == 1 for globs, _ in measured.calls), (
        "an enumeration ran with a multi-glob argument, so a set was matched as a set: "
        f"{[globs for globs, _ in measured.calls if len(globs) != 1][:3]}")
    distinct_pairs = {(globs[0], exclude_tests) for globs, exclude_tests in measured.calls}
    assert len(measured.calls) == len(distinct_pairs), (
        f"{len(measured.calls)} enumerations for {len(distinct_pairs)} distinct "
        "(glob, exclude_tests) pairs: one was matched twice in one scope")

    per_glob_asks = 2 * sum(len(globs) for globs in GLOB_SETS)
    assert len(measured.calls) < per_glob_asks / 2, (
        f"{per_glob_asks} per-glob asks resolved to {len(measured.calls)} enumerations: "
        "the redundancy this iteration removes is no longer measurable")

    # The frame gains per-glob entries and loses none: set keys + per-glob keys, minus
    # the single-glob cases where the set key IS its own per-glob key.
    single_glob_cases = sum(1 for globs, _ in CASES if len(globs) == 1)
    assert len(measured.frame) == len(CASES) + len(distinct_pairs) - single_glob_cases, (
        f"frame holds {len(measured.frame)} keys; expected {len(CASES)} set keys plus "
        f"{len(distinct_pairs)} per-glob keys minus {single_glob_cases} shared")
