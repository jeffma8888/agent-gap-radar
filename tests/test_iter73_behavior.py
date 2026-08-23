"""Iteration 73 behaviors: `agent_gap_radar.scoring` becomes importable and callable with
pydantic ABSENT, so the register's one declared consumer can order records by OUR derived
scores instead of inventing a third ordering rule -- and `docs/CONSUMER_CONTRACT.md`
publishes which modules are reachable that way, DERIVED from the same probe these tests run.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/` implementation
logic, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors, and every claim is measured by
IMPORTING and CALLING the public library surface (`scoring.priority`, `.confidence`,
`.distinct_sources`, `.strongest_source`, `.promotion_options`, `.rank`, `.below_floor`),
by driving `cli.main`, or by parsing a published document. One assertion is a mechanical
TOKEN CENSUS over `scoring.py` (acceptance criterion "no pydantic-only API call"); it
counts four substrings and reads no logic.

Structural notes, so this file cannot lie later:

* **The absence is measured by a matcher PROVEN to bite.** `pydantic_blocked()` installs a
  `sys.meta_path` finder and, before yielding, asserts `import pydantic` raises
  `ModuleNotFoundError`. If the blocker ever stopped biting, every "imports without
  pydantic" test in this file would FAIL rather than pass vacuously -- behavior 1 exists
  precisely because an absence measured by an unproven matcher is not evidence.
* **It is two-sided in the other direction too.** Behavior 3 asserts `models` still refuses
  under the SAME blocker, so a green behavior 2 cannot come from a blocker that missed the
  package, and `_fresh` asserts the module object obtained under the blocker is NOT the
  cached one, so no result here can come from a module imported earlier with pydantic
  present.
* **No live gap id appears in any assertion**, and that is ENFORCED: a test greps this very
  file for the `GAP-0NN` shape and fails if one appears. Every fixture id is `GAP-9NN`.
  Reason: `gaps/` is grown by an unattended research pass, and a test that pinned a live
  record's value would red a CORRECT register days from now (the iteration-09 landmine).
* **The byte-identity acceptance criterion is asserted as PROPERTIES, not as the spec's
  predicted byte counts.** Those counts (`list` 1889 B, `report` 3444 B, ...) are functions
  of the live register, so pinning them here would be the same landmine. What is pinned is
  what survives a research pass: exit 0, empty stderr, exactly one trailing newline, and
  byte-stability across repeated invocation.
* **The suite stays OFFLINE and that is enforced, not promised.** An autouse fixture arms a
  socket tripwire for every test in this module.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import pathlib
import re
import socket
import sys
import types

import pytest

from agent_gap_radar import scoring as live_scoring
from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "src" / "agent_gap_radar"
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The ten importable modules of the package, `__init__` excluded (it imports nothing).
PACKAGE_MODULES = tuple(
    sorted(p.stem for p in PKG_DIR.glob("*.py") if p.stem != "__init__"))

#: Top-level roots the blocker refuses.
BLOCKED_ROOTS = ("pydantic", "pydantic_core")

#: The five scoring functions the spec names in behavior 4.
SCORERS = ("priority", "confidence", "distinct_sources", "strongest_source",
           "promotion_options")

#: Two distinct source documents, and one probe locator the fixtures never reuse.
DOC_A = "https://example.invalid/a"
DOC_B = "https://example.invalid/b"
PROBE_DOC = "https://example.invalid/probe-not-used-by-any-fixture"


class _NetworkAttempted(AssertionError):
    """Raised by the tripwire when a test tries to open a socket."""


@pytest.fixture(autouse=True)
def _offline_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test in this module may touch the network."""

    def boom(*_args: object, **_kwargs: object) -> None:
        raise _NetworkAttempted("a test in this module attempted to open a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


# ---------------------------------------------------------------------------
# the import blocker
# ---------------------------------------------------------------------------


class _Blocker:
    """A `sys.meta_path` finder that makes a set of top-level roots unimportable."""

    def __init__(self, roots: tuple[str, ...]) -> None:
        self._roots = frozenset(roots)

    def find_spec(self, fullname: str, path: object = None, target: object = None):
        if fullname.split(".")[0] in self._roots:
            raise ModuleNotFoundError(
                f"{fullname!r} is blocked in-process by this test", name=fullname)
        return None


@contextlib.contextmanager
def pydantic_blocked():
    """Make pydantic unimportable IN-PROCESS, with the positive control asserted first.

    Purges pydantic and every already-imported `agent_gap_radar` module so a cached
    module cannot answer for a fresh one, then restores `sys.modules` and
    `sys.meta_path` exactly, so no other test in this worker can observe the blocker.
    """
    saved_modules = dict(sys.modules)
    saved_meta = list(sys.meta_path)
    for name in list(sys.modules):
        root = name.split(".")[0]
        if root in BLOCKED_ROOTS or name == "agent_gap_radar" or name.startswith(
                "agent_gap_radar."):
            del sys.modules[name]
    sys.meta_path.insert(0, _Blocker(BLOCKED_ROOTS))
    try:
        # Behavior 1: the matcher is proven to bite BEFORE anything is concluded from it.
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("pydantic")
        assert "pydantic" not in sys.modules, "a purged pydantic reappeared in sys.modules"
        yield
    finally:
        sys.meta_path[:] = saved_meta
        for name in list(sys.modules):
            if name not in saved_modules:
                del sys.modules[name]
        sys.modules.update(saved_modules)


def _import_verdicts() -> dict[str, bool]:
    """module name -> did it import with pydantic absent. THE derivation behavior 8 needs."""
    verdicts: dict[str, bool] = {}
    with pydantic_blocked():
        for name in PACKAGE_MODULES:
            try:
                importlib.import_module(f"agent_gap_radar.{name}")
            except ModuleNotFoundError:
                verdicts[name] = False
            else:
                verdicts[name] = True
            # Drop it again so each module is measured on its own, not through a sibling
            # that happened to import it first.
            for cached in list(sys.modules):
                if cached == "agent_gap_radar" or cached.startswith("agent_gap_radar."):
                    del sys.modules[cached]
    return verdicts


# ---------------------------------------------------------------------------
# the ladder, OBSERVED from the published vocabulary rather than imported
# ---------------------------------------------------------------------------


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


_LADDER_LINE = re.compile(r"^- `([a-z-]+)` \(weight (\d+)\)$")


def _observed_ladder() -> dict[str, int]:
    code, out, err = _run(["taxonomy"])
    assert code == 0, (code, err)
    section = out.split("## Evidence source classes", 1)
    assert len(section) == 2, "the taxonomy verb published no evidence-ladder heading"
    weights: dict[str, int] = {}
    for line in section[1].splitlines():
        if line.startswith("## ") and weights:
            break
        match = _LADDER_LINE.match(line.strip())
        if match:
            weights[match.group(1)] = int(match.group(2))
    assert weights, "the taxonomy verb published no evidence ladder"
    return weights


LADDER = _observed_ladder()
LADDER_ORDER = tuple(LADDER)
REAL_CLASSES = tuple(c for c in LADDER_ORDER if LADDER[c] > 0)
ZERO_CLASSES = tuple(c for c in LADDER_ORDER if LADDER[c] == 0)
CEILING = max(LADDER.values())
WEAKEST_REAL = REAL_CLASSES[-1]
#: The corroboration fixtures need a ceiling class BELOW the cap, or the single
#: corroboration point is invisible against it and the one-document and two-document
#: shapes become indistinguishable -- measured: both scored 5 with the top rung.
BASE_REAL = next(c for c in REAL_CLASSES if LADDER[c] < CEILING)
#: A weaker real class, so BASE_REAL stays the ceiling and only the point moves.
OTHER_REAL = next(c for c in REAL_CLASSES if 0 < LADDER[c] < LADDER[BASE_REAL])
FLOORS = (2, 3, 4, 5)


# ---------------------------------------------------------------------------
# the synthetic set -- built twice, once pydantic-backed and once duck-typed
# ---------------------------------------------------------------------------


def _gap(cites, gid: str, sev: int = 3, freq: int = 3, tract: int = 3) -> Gap:
    """A schema-valid pydantic record whose citations are (source_class, locator) pairs."""
    record = Gap.model_validate({
        "id": gid, "title": f"t{gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": sev, "frequency": freq, "tractability": tract,
        "evidence": [{"source_class": c, "title": "t", "locator": loc,
                      "date": "2026-01-02", "quote": "q"} for c, loc in cites] or [
            {"source_class": REAL_CLASSES[0], "title": "t", "locator": DOC_A,
             "date": "2026-01-02", "quote": "q"}],
    })
    if not cites:  # min_length=1 on the schema, so the empty case is reached by copy
        record = record.model_copy(update={"evidence": []})
    return record


def _duck(cites, gid: str, sev: int = 3, freq: int = 3, tract: int = 3):
    """The same record as a plain object: no pydantic, no `model_copy`, no class."""
    return types.SimpleNamespace(
        id=gid, severity=sev, frequency=freq, tractability=tract,
        evidence=[types.SimpleNamespace(source_class=c, locator=loc) for c, loc in cites])


#: name -> (gid, sev, freq, tract, citations). Covers every shape behavior 4 names.
SHAPES: tuple[tuple[str, str, int, int, int, tuple[tuple[str, str], ...]], ...] = (
    ("no-evidence-at-all", "GAP-900", 3, 3, 3, ()),
    ("model-output-only", "GAP-901", 4, 4, 4,
     tuple((ZERO_CLASSES[0], doc) for doc in (DOC_A, DOC_B))),
    ("two-classes-one-document", "GAP-902", 5, 5, 5,
     ((BASE_REAL, DOC_A), (OTHER_REAL, DOC_A))),
    ("two-classes-two-documents", "GAP-903", 2, 4, 3,
     ((BASE_REAL, DOC_A), (OTHER_REAL, DOC_B))),
    ("below-floor-with-options", "GAP-904", 5, 5, 5, ((WEAKEST_REAL, DOC_A),)),
)


def _pydantic_set() -> list[Gap]:
    return [_gap(cites, gid, sev, freq, tract)
            for _name, gid, sev, freq, tract, cites in SHAPES]


def _duck_set() -> list[types.SimpleNamespace]:
    return [_duck(cites, gid, sev, freq, tract)
            for _name, gid, sev, freq, tract, cites in SHAPES]


def _call(module, func: str, record):
    return getattr(module, func)(record)


# ---------------------------------------------------------------------------
# behavior 1 -- the blocker is proven capable of biting
# ---------------------------------------------------------------------------


def test_behavior_1_the_blocker_bites_and_only_inside_the_block():
    """Two-sided: pydantic imports normally, and refuses under the blocker."""
    assert importlib.import_module("pydantic") is not None
    with pydantic_blocked():  # the control is asserted inside the context manager itself
        with pytest.raises(ModuleNotFoundError) as raised:
            importlib.import_module("pydantic")
        assert raised.value.name == "pydantic"
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("pydantic.fields")
    assert importlib.import_module("pydantic") is not None, "the blocker was not removed"


def test_behavior_1_the_blocker_leaves_no_trace_for_other_tests():
    before_meta, before_modules = list(sys.meta_path), dict(sys.modules)
    with pydantic_blocked():
        importlib.import_module("agent_gap_radar.scoring")
    assert list(sys.meta_path) == before_meta
    assert set(sys.modules) == set(before_modules)
    assert sys.modules["agent_gap_radar.scoring"] is before_modules[
        "agent_gap_radar.scoring"]


# ---------------------------------------------------------------------------
# behavior 2 -- scoring imports with pydantic absent
# ---------------------------------------------------------------------------


def test_behavior_2_scoring_imports_with_pydantic_absent():
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        assert module is not live_scoring, "a cached module answered for a fresh import"
        assert "pydantic" not in sys.modules
        for func in SCORERS + ("rank", "below_floor"):
            assert callable(getattr(module, func)), func


def test_behavior_2_the_package_itself_imports_with_pydantic_absent():
    """Stated because if `__init__` pulled the schema in, the approach could not work."""
    with pydantic_blocked():
        assert importlib.import_module("agent_gap_radar") is not None


# ---------------------------------------------------------------------------
# behavior 3 -- models still says it needs pydantic (the two-sided companion)
# ---------------------------------------------------------------------------


def test_behavior_3_models_still_refuses_under_the_same_blocker():
    with pydantic_blocked():
        with pytest.raises(ModuleNotFoundError) as raised:
            importlib.import_module("agent_gap_radar.models")
        assert raised.value.name in {"pydantic", "pydantic_core"}, raised.value.name


def test_acceptance_the_pydantic_free_module_set_is_exactly_three():
    verdicts = _import_verdicts()
    assert set(verdicts) == set(PACKAGE_MODULES)
    assert len(PACKAGE_MODULES) == 10, PACKAGE_MODULES
    free = {name for name, ok in verdicts.items() if ok}
    assert free == {"taxonomy", "checks", "scoring"}, verdicts


# ---------------------------------------------------------------------------
# behavior 4 -- every scorer agrees across the two paths
# ---------------------------------------------------------------------------


def test_behavior_4_the_synthetic_set_is_not_vacuous():
    """Each shape must actually exercise the property it is named for."""
    by_name = {name: gap for (name, *_), gap in zip(SHAPES, _pydantic_set())}
    assert len(by_name) == 5
    assert by_name["no-evidence-at-all"].evidence == []
    assert live_scoring.confidence(by_name["model-output-only"]) == 0
    one_doc = by_name["two-classes-one-document"]
    two_doc = by_name["two-classes-two-documents"]
    assert live_scoring.distinct_sources(one_doc) == 1, "the fixture is not one document"
    assert live_scoring.distinct_sources(two_doc) == 2, "the fixture is not two documents"
    assert LADDER[BASE_REAL] < CEILING, "a capped ceiling would hide the point"
    assert live_scoring.confidence(one_doc) == LADDER[BASE_REAL]
    assert live_scoring.confidence(two_doc) == LADDER[BASE_REAL] + 1, \
        "the corroboration pair fixtures must differ, or behavior 4 proves nothing"
    weak = by_name["below-floor-with-options"]
    assert live_scoring.confidence(weak) < 2, "the below-floor fixture is not below floor"
    assert live_scoring.promotion_options(weak, 2), "the below-floor fixture has no options"


@pytest.mark.parametrize("func", SCORERS)
def test_behavior_4_scorers_agree_across_the_two_paths(func):
    expected = [_call(live_scoring, func, gap) for gap in _pydantic_set()]
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        observed = [_call(module, func, rec) for rec in _duck_set()]
    assert observed == expected, [
        (name, e, o) for (name, *_), e, o in zip(SHAPES, expected, observed) if e != o]


@pytest.mark.parametrize("floor", FLOORS)
def test_behavior_4_promotion_options_agrees_at_every_floor(floor):
    expected = [live_scoring.promotion_options(gap, floor) for gap in _pydantic_set()]
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        observed = [module.promotion_options(rec, floor) for rec in _duck_set()]
    assert observed == expected


# ---------------------------------------------------------------------------
# behavior 5 -- promotion_options survives a record with no model_copy
# ---------------------------------------------------------------------------


def test_behavior_5_promotion_options_needs_no_model_copy():
    """The specific regression behavior 4 would otherwise let pass silently."""
    duck = _duck(((WEAKEST_REAL, DOC_A),), "GAP-905", 5, 5, 5)
    assert not hasattr(duck, "model_copy"), "the fixture must lack the pydantic-only API"
    for floor in FLOORS:
        options = live_scoring.promotion_options(duck, floor)
        assert isinstance(options, tuple), (floor, type(options))
        assert all(isinstance(o, str) for o in options), options
    assert live_scoring.promotion_options(duck, 2), \
        "a below-floor record must still be told how to earn promotion"


def test_behavior_5_holds_under_the_blocker_too():
    duck = _duck(((WEAKEST_REAL, DOC_A),), "GAP-906", 5, 5, 5)
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        assert module.promotion_options(duck, 2) == live_scoring.promotion_options(duck, 2)


class _ModelCopyTouched(AssertionError):
    """Raised when a scorer reads `model_copy` off the record it was handed."""


class _DetonateOnModelCopy:
    """Forwards every attribute to a real record, but DETONATES on `model_copy`.

    Why this exists: a `SimpleNamespace` fixture proves nothing about the PYDANTIC path,
    where `model_copy` genuinely exists -- so the absence of an `AttributeError` there is
    not evidence that the probe was swapped. This proxy turns behavior 7's claim into a
    positive one on both record shapes.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        if name == "model_copy":
            raise _ModelCopyTouched("a scorer read `model_copy` off the record")
        return getattr(self._inner, name)


def test_the_detonating_proxy_really_detonates():
    """The control. Without it, every test below could pass because nothing fired."""
    proxy = _DetonateOnModelCopy(_gap(((WEAKEST_REAL, DOC_A),), "GAP-908", 5, 5, 5))
    with pytest.raises(_ModelCopyTouched):
        proxy.model_copy  # noqa: B018  (attribute ACCESS is the tripwire)
    assert proxy.id == "GAP-908", "the proxy must still forward the real attributes"


@pytest.mark.parametrize("floor", FLOORS)
def test_behavior_5_no_scorer_reads_model_copy_off_a_real_record(floor):
    """The pydantic path is checked too, because there the attribute EXISTS."""
    for _name, gid, sev, freq, tract, cites in SHAPES:
        record = _gap(cites, gid, sev, freq, tract)
        proxy = _DetonateOnModelCopy(record)
        assert live_scoring.promotion_options(proxy, floor) == \
            live_scoring.promotion_options(record, floor), (gid, floor)
        for func in SCORERS:
            assert _call(live_scoring, func, proxy) == _call(live_scoring, func, record), (
                gid, func)


def test_behavior_5_every_scorer_is_total_on_a_class_free_record():
    """No scorer may need a class: an AttributeError here is the same defect, elsewhere."""
    for _name, gid, sev, freq, tract, cites in SHAPES:
        duck = _duck(cites, gid, sev, freq, tract)
        for func in SCORERS:
            _call(live_scoring, func, duck)  # must not raise


# ---------------------------------------------------------------------------
# behavior 6 -- both views agree, and they partition the register
# ---------------------------------------------------------------------------


def _ids(view) -> list[str]:
    return [record.id for record, *_rest in view]


def test_behavior_6_rank_and_below_floor_agree_across_the_two_paths():
    expected_rank = _ids(live_scoring.rank(_pydantic_set()))
    expected_below = _ids(live_scoring.below_floor(_pydantic_set()))
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        ducks = _duck_set()
        observed_rank = _ids(module.rank(ducks))
        observed_below = _ids(module.below_floor(ducks))
    assert observed_rank == expected_rank
    assert observed_below == expected_below
    assert observed_rank and observed_below, \
        "a fixture set that fills only one view cannot prove the partition"


def test_behavior_6_every_record_appears_in_exactly_one_view():
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        ducks = _duck_set()
        ranked, below = _ids(module.rank(ducks)), _ids(module.below_floor(ducks))
    assert set(ranked).isdisjoint(below), sorted(set(ranked) & set(below))
    assert sorted(ranked + below) == sorted(rec.id for rec in _duck_set())


# ---------------------------------------------------------------------------
# behavior 7 -- the probe swap is behavior-neutral on the pydantic path
# ---------------------------------------------------------------------------


def _reaches(gap, klass: str, floor: int) -> bool:
    """Would ONE more citation of `klass`, at a source the record does not cite, lift it?

    The oracle is written here from the spec's rule and calls only `confidence`, which
    this iteration does not touch -- so it is an independent statement of what a
    prescription MEANS, not a re-reading of the prescription's own code.
    """
    cites = tuple((e.source_class, e.locator) for e in gap.evidence)
    probe = _gap(cites + ((klass, PROBE_DOC),), gid="GAP-909",
                 sev=gap.severity, freq=gap.frequency, tract=gap.tractability)
    return live_scoring.confidence(probe) >= floor


def test_behavior_7_every_prescription_is_honest_and_the_empty_one_is_complete():
    checked = 0
    for gap in _pydantic_set():
        for floor in FLOORS:
            options = live_scoring.promotion_options(gap, floor)
            for klass in options:
                assert _reaches(gap, klass, floor), (gap.id, floor, klass)
            if not options:
                assert not [c for c in REAL_CLASSES if _reaches(gap, c, floor)], (
                    gap.id, floor, "an empty prescription hid a class that reaches")
            checked += 1
    assert checked == len(SHAPES) * len(FLOORS) == 20


def test_behavior_7_the_prescription_is_the_cheapest_rung_in_ladder_order():
    for gap in _pydantic_set():
        for floor in FLOORS:
            options = live_scoring.promotion_options(gap, floor)
            if not options:
                continue
            reaching = [c for c in REAL_CLASSES if _reaches(gap, c, floor)]
            cheapest = min(LADDER[c] for c in reaching)
            assert {LADDER[o] for o in options} == {cheapest}, (gap.id, floor, options)
            assert set(options) == {c for c in reaching if LADDER[c] == cheapest}
            rungs = [LADDER_ORDER.index(o) for o in options]
            assert rungs == sorted(rungs), (gap.id, floor, options)
            assert not set(options) & set(ZERO_CLASSES), options


def test_behavior_7_real_gap_objects_score_the_same_through_the_blocked_module():
    """The swapped probe line is exercised on a real `Gap`, not only on a stand-in."""
    records = _pydantic_set()
    expected = {floor: [live_scoring.promotion_options(g, floor) for g in records]
                for floor in FLOORS}
    with pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        observed = {floor: [module.promotion_options(g, floor) for g in records]
                    for floor in FLOORS}
    assert observed == expected
    assert any(any(v) for v in expected.values()), "no prescription was non-empty"


def test_behavior_7_promotion_options_is_deterministic_on_both_shapes():
    duck = _duck(((WEAKEST_REAL, DOC_A),), "GAP-907", 5, 5, 5)
    gap = _gap(((WEAKEST_REAL, DOC_A),), "GAP-907", 5, 5, 5)
    assert len({live_scoring.promotion_options(duck, 2) for _ in range(30)}) == 1
    assert live_scoring.promotion_options(duck, 2) == live_scoring.promotion_options(gap, 2)


# ---------------------------------------------------------------------------
# behavior 8 -- the contract publishes the module set, DERIVED from the probe
# ---------------------------------------------------------------------------

_ROW = re.compile(r"^\|\s*`agent_gap_radar\.([a-z_]+)`\s*\|\s*(yes|no)\s*\|")


def _contract_section(path: pathlib.Path | None = None) -> str:
    text = (path or CONTRACT).read_text(encoding="utf-8")
    parts = text.split("### Deriving the scores without installing pydantic", 1)
    assert len(parts) == 2, "the contract publishes no pydantic-free subsection"
    tail = parts[1]
    end = tail.find("\n## ")
    return tail if end == -1 else tail[:end]


def _published_table(section: str) -> dict[str, bool]:
    return {m.group(1): m.group(2) == "yes"
            for m in (_ROW.match(line) for line in section.splitlines()) if m}


def test_behavior_8_the_contract_table_equals_the_measured_import_set():
    section = _contract_section()
    published = _published_table(section)
    measured = _import_verdicts()
    assert set(published) == set(measured), (
        sorted(set(published) ^ set(measured)),
        "the table must name every module, in both directions")
    assert published == measured, {
        name: (published[name], measured[name])
        for name in measured if published.get(name) is not measured[name]}
    assert sum(published.values()) == 3, published


def test_behavior_8_the_comparison_detects_a_table_that_lies(tmp_path):
    """Anti-vacuity control for the test above.

    A parser that silently matched nothing, or a comparison that only checked one
    direction, would keep passing while the published table went wrong. So the same
    parser and the same comparison are pointed at a MUTATED copy of the document, one
    verdict flipped, and are required to disagree with the measurement.
    """
    measured = _import_verdicts()
    truthful = _published_table(_contract_section())
    assert truthful == measured, "the control needs a truthful starting point"

    original = CONTRACT.read_text(encoding="utf-8")
    victim = next(name for name, ok in measured.items() if ok)
    row = f"| `agent_gap_radar.{victim}` | yes |"
    assert original.count(row) == 1, (victim, original.count(row))
    mutated = tmp_path / "CONTRACT_with_one_lie.md"
    mutated.write_text(
        original.replace(row, f"| `agent_gap_radar.{victim}` | no |"), encoding="utf-8")

    lying = _published_table(_contract_section(mutated))
    assert set(lying) == set(measured), "the mutation must not break the parser itself"
    assert lying != measured, "the comparison cannot see a flipped verdict"
    assert lying[victim] is False and measured[victim] is True


def test_behavior_8_the_contract_names_the_duck_typed_protocol():
    section = _contract_section()
    for attribute in ("id", "severity", "frequency", "tractability", "evidence",
                      "source_class", "locator"):
        assert f"`{attribute}`" in section, attribute
    assert "duck" in section.lower(), "the section does not say the shape is duck-typed"
    assert "OPTIONAL" in section or "optional" in section, \
        "the section does not mark `locator` optional"


# ---------------------------------------------------------------------------
# acceptance criteria that are mechanically checkable black-box
# ---------------------------------------------------------------------------


def test_acceptance_scoring_holds_no_pydantic_only_api_call():
    """A token CENSUS, not a reading: four substring counts over one file."""
    text = (PKG_DIR / "scoring.py").read_text(encoding="utf-8")
    census = {token: text.count(token)
              for token in ("model_copy", "model_validate", "model_dump", "BaseModel")}
    assert census == {"model_copy": 0, "model_validate": 0, "model_dump": 0,
                      "BaseModel": 0}, census


def test_acceptance_no_live_gap_id_appears_in_this_file():
    """Self-enforcing: the iteration-09 landmine cannot be reintroduced here silently."""
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    live_shaped = sorted(set(re.findall(r"GAP-0\d\d", text)))
    assert live_shaped == [], live_shaped
    fixtures = sorted(set(re.findall(r"GAP-\d\d\d", text)))
    assert fixtures and all(f.startswith("GAP-9") for f in fixtures), fixtures


@pytest.mark.parametrize("verb", ["validate", "list", "report", "prd", "taxonomy"])
def test_acceptance_every_argument_free_verb_is_clean_and_byte_stable(verb):
    """Byte-identity asserted as properties; the spec's predicted counts are register-
    derived, so pinning them here would red a correct register after a research pass."""
    first = _run([verb])
    second = _run([verb])
    code, out, err = first
    assert code == 0, (verb, code, err)
    assert err == "", (verb, err)
    assert out.endswith("\n") and not out.endswith("\n\n"), verb
    assert first == second, verb
