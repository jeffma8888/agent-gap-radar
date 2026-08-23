"""Iteration 62 behaviors: the ledger bound comes from the LEDGER, not from a literal.

Iterations 32-60 shipped nothing because four assertions bound `PRODUCT.md`'s Done ledger
to a literal iteration number -- a row COUNT equality, two CONTIGUITY claims and a
real-`git log` subset-of-a-literal-range -- so every ship commit made its own clean clone
RED. This iteration replaces those four with a floor, a historical PREFIX and the product's
own one-directional judge. The behavior under test is therefore a property OF THE SUITE, and
the surface this file drives is the public one: the committed test functions themselves,
invoked over documents this file controls.

Iteration 61 landed exactly this payload and was reverted anyway, by ONE assertion in this
very file that was true only BEFORE its own ship commit existed -- `after != real`, "git
already reports this iteration as shipped". Iteration 62 re-lands the payload with that
assertion gone, and with this module INSIDE the durability sweep's discovered domain rather
than exempted from it, because whatever a gate exempts is the one place it can never look.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/`, `tools/`
source, the engineer's or reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Every
expectation comes from `pm.md`'s Expected Behaviors. Every claim is measured by CALLING a
public interface -- `tools/roadmap_integrity`, or a committed test function under `tests/`,
which the isolation contract names as readable -- over the committed `PRODUCT.md` or over a
fixture derived from it under pytest's `tmp_path`.

Structural notes, so this file cannot lie later:

* **This file must not reintroduce the defect it is testing.** No assertion here compares a
  ledger row count or a ledger value list to a literal iteration number as an EQUALITY or a
  MAXIMUM. The historical run 1..31 appears only as an ordered PREFIX and as a FLOOR, both of
  which are invariant under any later iteration appending rows.
* **The durability claim is measured, not argued.** `test_eb3_...` grows the live ledger by
  two sparse future rows and re-invokes every zero-argument committed test function whose OWN
  SOURCE reads ledger text or the real git ship list -- keyed on INPUT SOURCE, which is the
  sweep discipline iteration 60 died for skipping -- and requires all of them to stay green.
* **Every mutated fixture asserts its own premise**, so a no-op `replace` cannot turn a
  known-bad document into a copy of the good one.
* **This module is not exempt from its own sweep.** It is named in `LEDGER_READING_MODULES`
  and the coverage guard discovers it from the filesystem with NO identity-based exclusion, so
  its own zero-argument ledger-reading tests are re-invoked over the grown sparse document.
* **No assertion here is true only before this iteration's ship commit exists.** Anti-vacuity
  arms key on a value that can never enter this document's git history -- one greater than the
  maximum of the real ship list and the ledger values -- so shipping cannot falsify one.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every fixture is written under pytest's `tmp_path`.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib
import re
import sys
import types

import pytest

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROADMAP = REPO_ROOT / "PRODUCT.md"
TESTS_DIR = REPO_ROOT / "tests"

#: This file is BOTH the sweeper and one of the swept modules: iteration 61 exempted itself
#: from the coverage guard and was reverted by a pin inside this very file. Derived from
#: `__file__`, never written down as a literal, so a rename needs no edit here.
SELF_MODULE = pathlib.Path(__file__).stem

sys.path.insert(0, str(REPO_ROOT / "tools"))

import roadmap_integrity as ri  # noqa: E402

import test_iter12_behavior as it12  # noqa: E402
import test_iter31_behavior as it31  # noqa: E402

#: The ledger's historical run: the contiguous prefix already recorded when the four pins
#: were retired. A FLOOR and a PREFIX, never a ceiling -- later iterations append rows, and
#: an iteration that ships nothing appends none, so the ledger may be LONGER and SPARSE.
HISTORICAL_RUN: tuple[int, ...] = tuple(range(1, 32))

#: This iteration. The ledger's first NON-CONTIGUOUS value is 61, and this row makes a second
#: one, which is the whole point: a ledger that is sparse cannot be pinned to a literal count.
THIS_ITER = 62

#: Modules whose committed tests read ledger text or the real git ship list, and which
#: therefore have to survive a later iteration's ship commit. IMPORTED HERE, not merely
#: named, so the durability sweep below cannot go vacuous when this file is run alone.
LEDGER_READING_MODULES = (
    "test_iter04_behavior",
    "test_iter12_behavior",
    "test_iter20_behavior",
    "test_iter24_behavior",
    "test_iter28_behavior",
    "test_iter31_behavior",
    "test_iter74_behavior",
    "test_roadmap_integrity",
    SELF_MODULE,
)

for _module_name in LEDGER_READING_MODULES:
    if _module_name != SELF_MODULE:
        # This module is mid-import; `sys.modules` already holds it, and re-importing a
        # partially initialised module is a trap worth not setting.
        importlib.import_module(_module_name)

#: What "reads ledger text or real git" means, keyed on INPUT SOURCE rather than on file
#: neighbourhood -- the sweep iteration 60 skipped.
LEDGER_INPUT_TOKENS = ("ledger", "shipped_iterations_from_git", "unrecorded_ships")


def _live() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _mutate(text: str, old: str, new: str) -> str:
    """Replace `old` once, asserting it was there and that the result differs."""
    assert old in text, f"fixture premise broken: {old!r} is not in the live document"
    mutated = text.replace(old, new, 1)
    assert mutated != text, "fixture premise broken: the mutation was a no-op"
    return mutated


def _ledger_values(text: str) -> list[int]:
    return [value for _, value in ri.ledger_iterations(text)]


def _ledger_line(text: str, iteration: int) -> str:
    pattern = re.compile(rf"^- iter {iteration:02d}\b.*$", re.MULTILINE)
    matches = pattern.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one ledger row for {iteration:02d}, found {len(matches)}"
    )
    return matches[0]


def _as_roadmap(tmp_path: pathlib.Path, text: str, name: str) -> pathlib.Path:
    path = tmp_path / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _point_at(monkeypatch: pytest.MonkeyPatch, path: pathlib.Path) -> None:
    """Repoint every ledger-reading module's roadmap handle at `path`.

    The committed tests read their document through a module-level `ROADMAP`, so this is the
    seam that lets a black-box caller drive them over a document it controls.
    """
    for name in LEDGER_READING_MODULES:
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "ROADMAP"):
            monkeypatch.setattr(module, "ROADMAP", path)


def _future_rows(text: str, count: int = 2) -> list[int]:
    """Iteration numbers strictly ABOVE the live ledger maximum.

    DERIVED, never written down: iteration 61 hard-coded 62 and 63 here, and the row for 62
    then landed in the live document, so the fixture would have duplicated an existing row.
    """
    ceiling = max(_ledger_values(text))
    return [ceiling + n for n in range(1, count + 1)]


def _grown(text: str) -> str:
    """The live ledger plus two SPARSE future rows -- what a later ship commit produces."""
    last = _ledger_line(text, max(_ledger_values(text)))
    rows = "".join(f"\n- iter {value:02d} a later row" for value in _future_rows(text))
    return _mutate(text, last, f"{last}{rows}")


def _ledger_reading_tests(module_names: tuple[str, ...]) -> list[tuple[str, str]]:
    """Zero-argument committed test functions whose OWN SOURCE reads ledger text or the real
    git ship list. Selection is keyed on INPUT SOURCE, not on file neighbourhood."""
    targets: list[tuple[str, str]] = []
    for module_name in module_names:
        module = sys.modules.get(module_name)
        assert module is not None, f"{module_name} was never imported: selection is vacuous"
        for name, func in sorted(vars(module).items()):
            if not name.startswith("test_") or not isinstance(func, types.FunctionType):
                continue
            if inspect.signature(func).parameters:
                continue  # needs a fixture this direct caller cannot supply
            if any(token in inspect.getsource(func) for token in LEDGER_INPUT_TOKENS):
                targets.append((module_name, name))
    return targets


def _sweep(
    monkeypatch: pytest.MonkeyPatch,
    path: pathlib.Path,
    document: str,
    module_names: tuple[str, ...],
    ships: list[int] | None = None,
    exclude: tuple[tuple[str, str], ...] = (),
) -> list[str]:
    """Point every named module at `path`/`document` and invoke its ledger-reading tests,
    returning one line per FAILURE. A skip is an outcome, not a failure.

    TWO seams are repointed, because one is not enough: a module-level `ROADMAP` handle read
    per call, AND any module-level STRING snapshot of the document taken at import time --
    `test_iter04_behavior.REAL` is such a snapshot, and patching only `ROADMAP` would leave
    its twelve ledger tests reading the committed file, so the sweep would report green
    without having examined them. `ships`, when given, also repoints the git probe, which is
    what makes a full clean-clone simulation possible before any commit exists.
    """
    for module_name in module_names:
        module = sys.modules[module_name]
        if hasattr(module, "ROADMAP"):
            monkeypatch.setattr(module, "ROADMAP", path)
        if isinstance(getattr(module, "REAL", None), str):
            monkeypatch.setattr(module, "REAL", document)
    if ships is not None:
        monkeypatch.setattr(
            ri, "shipped_iterations_from_git",
            lambda _root: types.SimpleNamespace(iterations=list(ships), skip_reason=None),
        )

    failures: list[str] = []
    for module_name, name in _ledger_reading_tests(module_names):
        if (module_name, name) in exclude:
            continue
        func = getattr(sys.modules[module_name], name)
        try:
            func()
        except AssertionError as exc:
            failures.append(f"{module_name}::{name} -- {exc}")
        except Exception as exc:  # noqa: BLE001 -- a skip is an outcome, not a red pin
            if type(exc).__name__ not in {"Skipped", "OutcomeException"}:
                failures.append(f"{module_name}::{name} -- {type(exc).__name__}: {exc}")
    return failures


def _module_with_a_contiguity_pin(name: str, path: pathlib.Path) -> types.ModuleType:
    """A synthetic ledger-reading module carrying exactly the retired defect: an assertion
    that the ledger is GAPLESS. Arms `_sweep`, which is otherwise a check that has never
    been shown to fire."""
    module = types.ModuleType(name)
    module.ROADMAP = path

    def test_the_ledger_is_contiguous() -> None:
        values = [
            value
            for _, value in ri.ledger_iterations(module.ROADMAP.read_text(encoding="utf-8"))
        ]
        assert values == list(range(1, len(values) + 1)), f"ledger has gaps: {values}"

    module.test_the_ledger_is_contiguous = test_the_ledger_is_contiguous
    return module


def _real_ships() -> list[int]:
    ships = ri.shipped_iterations_from_git(REPO_ROOT)
    if ships.iterations is None:
        pytest.skip(f"cannot ask git: {ships.skip_reason}")
    return list(ships.iterations)


# ---------------------------------------------------------------------------
# Behavior 1 -- the committed document is a NON-CONTIGUOUS ledger and the product's
# own judges accept it
# ---------------------------------------------------------------------------

def test_eb1_the_committed_ledger_is_sparse_and_the_products_judges_accept_it() -> None:
    """Behavior 1's premise, stated growth-safely.

    `uv run pytest` exiting 0 over this document is the stage's own suite result; what this
    test pins is the property that makes that result meaningful -- the ledger really is
    non-contiguous, so a suite that passes over it cannot be asserting contiguity anywhere.
    """
    text = _live()
    values = _ledger_values(text)
    assert values, "anti-vacuity: no ledger rows parsed, so every assertion below is empty"

    assert values[: len(HISTORICAL_RUN)] == list(HISTORICAL_RUN), (
        f"the historical run is not the ledger's ordered prefix: "
        f"{values[: len(HISTORICAL_RUN)]}"
    )
    assert THIS_ITER in values, f"the ledger has no row for iteration {THIS_ITER}: {values}"
    assert len(values) > len(HISTORICAL_RUN), "the ledger did not grow past the historical run"
    assert values != list(range(1, len(values) + 1)), (
        "premise broken: this ledger is contiguous, so it cannot witness the sparse case"
    )
    assert ri.ledger_sequence_violations(text) == [], (
        "; ".join(v.message for v in ri.ledger_sequence_violations(text))
    )


# ---------------------------------------------------------------------------
# Behavior 2 -- ledger size is a FLOOR that can only grow, never an equality
# ---------------------------------------------------------------------------

def test_eb2_the_size_claim_fires_when_a_historical_row_is_deleted(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 2, FAIL side. Deleting any one historical row must red the size claim."""
    text = _live()
    victim = HISTORICAL_RUN[len(HISTORICAL_RUN) // 2]
    shrunk = _mutate(text, _ledger_line(text, victim) + "\n", "")
    assert len(_ledger_values(shrunk)) == len(_ledger_values(text)) - 1, (
        "fixture premise broken: exactly one ledger row must have been removed"
    )

    _point_at(monkeypatch, _as_roadmap(tmp_path, shrunk, "shrunk"))
    with pytest.raises(AssertionError) as excinfo:
        it31.test_b8_ledger_keeps_the_historical_run_as_an_ordered_prefix_over_a_growing_floor()
    assert str(victim) in str(excinfo.value), (
        f"the failure does not name the lost iteration {victim}: {excinfo.value}"
    )


def test_eb2_the_size_claim_admits_a_further_higher_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 2, PASS side -- the case the retired row-count EQUALITY rejected.

    This is the exact shape of a later iteration's ship commit, which is what reverted a
    green iteration from its own clean clone.
    """
    text = _live()
    later = max(_ledger_values(text)) + 1
    grown = _mutate(
        text, _ledger_line(text, max(_ledger_values(text))),
        f"{_ledger_line(text, max(_ledger_values(text)))}\n- iter {later:02d} a later row",
    )
    assert len(_ledger_values(grown)) == len(_ledger_values(text)) + 1

    _point_at(monkeypatch, _as_roadmap(tmp_path, grown, "grown"))
    it31.test_b8_ledger_keeps_the_historical_run_as_an_ordered_prefix_over_a_growing_floor()


# ---------------------------------------------------------------------------
# Behavior 3 -- the historical run is asserted as a PREFIX, and contiguity over the
# WHOLE ledger is asserted nowhere
# ---------------------------------------------------------------------------

def test_eb3_the_prefix_claim_fires_when_two_historical_rows_are_transposed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 3, FAIL side. Order within the historical run is still a rule."""
    text = _live()
    first, second = HISTORICAL_RUN[6], HISTORICAL_RUN[7]
    line_a = _ledger_line(text, first)
    line_b = _ledger_line(text, second)
    swapped = _mutate(text, f"{line_a}\n{line_b}", f"{line_b}\n{line_a}")
    values = _ledger_values(swapped)
    assert values.index(second) < values.index(first), (
        "fixture premise broken: the two historical rows were not transposed"
    )

    _point_at(monkeypatch, _as_roadmap(tmp_path, swapped, "swapped"))
    with pytest.raises(AssertionError):
        it31.test_b8_ledger_keeps_the_historical_run_as_an_ordered_prefix_over_a_growing_floor()


def test_eb3_no_ledger_reading_test_reds_over_a_sparse_grown_ledger(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 3, the DURABILITY claim: contiguity over the whole ledger is gone.

    Simulates the one event the four retired pins could not survive -- a later iteration
    appending rows, sparsely -- and re-invokes every zero-argument committed test function
    whose OWN SOURCE reads ledger text or the real git ship list. Selection is keyed on
    INPUT SOURCE rather than on which file a pin happened to live in, because iteration 60
    relaxed two pins, cleared a file by neighbourhood, and was killed by a third pin in it.
    """
    text = _live()
    grown = _grown(text)
    expected_rows = _future_rows(text)
    assert _ledger_values(grown)[-2:] == expected_rows, (
        f"fixture premise broken: no rows appended, expected {expected_rows}"
    )
    assert ri.ledger_sequence_violations(grown) == [], (
        "fixture premise broken: the grown ledger must satisfy the product's own judge"
    )

    targets = _ledger_reading_tests(LEDGER_READING_MODULES)
    assert len(targets) >= 20, f"selection is too thin to be a sweep: {len(targets)}"
    assert len({module for module, _ in targets}) >= 4, (
        f"the sweep reaches too few modules to be a sweep: {sorted(set(targets))}"
    )

    path = _as_roadmap(tmp_path, grown, "grown_sparse")
    failures = _sweep(monkeypatch, path, grown, LEDGER_READING_MODULES)
    assert failures == [], (
        "a later iteration's sparse ledger still reds the suite:\n" + "\n".join(failures)
    )


def test_eb3_the_durability_sweep_fires_on_a_module_that_pins_contiguity(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two-sided control for the durability claim.

    `_sweep(...) == []` is evidence only if the sweep is able to REPORT the retired defect.
    A synthetic ledger-reading module asserting the ledger is gapless is registered, and the
    sweep must name it over the same sparse document the claim above passes on -- so the
    green verdict there is a property of the suite, not of a sweep that inspects nothing.
    """
    name = "_iter62_synthetic_contiguity_pin"
    path = _as_roadmap(tmp_path, _grown(_live()), "grown_sparse")
    monkeypatch.setitem(sys.modules, name, _module_with_a_contiguity_pin(name, path))

    assert _ledger_reading_tests((name,)) == [(name, "test_the_ledger_is_contiguous")], (
        "the selector did not see the synthetic pin, so the sweep is untested"
    )
    failures = _sweep(monkeypatch, path, _grown(_live()), (name,))
    assert len(failures) == 1, f"the sweep did not report the contiguity pin: {failures}"
    assert "ledger has gaps" in failures[0], failures[0]


def _modules_with_ledger_reading_tests(test_dir: pathlib.Path) -> dict[str, tuple[str, ...]]:
    """Every test module under `test_dir` defining a zero-argument `test_*` whose OWN SOURCE
    reads ledger text or the real git ship list.

    Derived from source with `ast`, so it needs no import and -- the point -- it cannot
    inherit the omission it exists to detect. `_ledger_reading_tests` above selects from a
    HAND-WRITTEN tuple; this selects from the filesystem, so the two can be compared.
    """
    found: dict[str, tuple[str, ...]] = {}
    for path in sorted(test_dir.glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        names = tuple(
            node.name
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("test_")
            and not node.args.args
            and not node.args.kwonlyargs
            and any(
                token in (ast.get_source_segment(source, node) or "")
                for token in LEDGER_INPUT_TOKENS
            )
        )
        if names:
            found[path.stem] = names
    return found


def test_eb3_the_durability_sweep_reaches_every_ledger_reading_module_in_the_suite() -> None:
    """Behavior 3's COVERAGE premise, which the sweep itself cannot supply.

    `_sweep(...) == []` is only evidence about the modules `LEDGER_READING_MODULES` names,
    and that tuple is HAND-WRITTEN -- a derived value that drifts the moment a later
    iteration adds a ledger-reading test elsewhere. Iteration 60 relaxed two pins, cleared a
    file by NEIGHBOURHOOD, and was killed by a third pin in a file its sweep never opened.
    So the sweep's DOMAIN is measured against the suite on disk, not trusted.

    The declared tuple may be a strict SUPERSET (naming a module whose ledger-reading tests
    all take fixtures is harmless); what must never happen is a module the sweep skips.
    """
    discovered = _modules_with_ledger_reading_tests(TESTS_DIR)
    assert len(discovered) >= 5, (
        f"anti-vacuity: discovery is too thin to be a sweep of the suite: {sorted(discovered)}"
    )
    unswept = sorted(set(discovered) - set(LEDGER_READING_MODULES))
    assert unswept == [], (
        "these modules define zero-argument ledger-reading tests that the durability sweep "
        f"never invokes, so their pins are unmeasured: {unswept}"
    )


def test_eb3_the_coverage_guard_fires_when_a_ledger_reading_module_is_left_unswept() -> None:
    """Two-sided control for the coverage guard.

    An empty `unswept` is evidence only if a real omission would be NAMED. Drop one genuinely
    ledger-reading module from the declared tuple and the comparison must report exactly it.
    """
    discovered = _modules_with_ledger_reading_tests(TESTS_DIR)
    assert discovered, "premise broken: nothing was discovered, so the control is vacuous"

    dropped = sorted(discovered)[0]
    assert dropped in LEDGER_READING_MODULES, (
        f"premise broken: {dropped} is already unswept, so the guard should be RED"
    )
    thinned = tuple(name for name in LEDGER_READING_MODULES if name != dropped)
    assert len(thinned) == len(LEDGER_READING_MODULES) - 1, "premise broken: nothing removed"

    assert sorted(set(discovered) - set(thinned)) == [dropped], (
        f"the coverage guard failed to name the module removed from the sweep: {dropped}"
    )


def test_eb3_and_eb4_a_full_clean_clone_of_this_iterations_ship_commit_stays_green(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The decisive simulation, covering BOTH inputs at once -- behaviors 3 and 4 together.

    A clean clone of a later ship commit differs from the working tree in two ways: the ledger
    has grown SPARSELY, and real `git log` now reports iterations the retired pins had never
    heard of. The working tree cannot supply the second half -- which is exactly why
    `test_iter31_behavior:244` was green pre-commit and reverted iterations 30 and 60 -- so it
    is supplied here by repointing the git probe.

    One target is EXCLUDED with a stated reason, and its presence in the selection is asserted
    so the exclusion cannot go stale: `test_eb3_check_agrees_with_an_independent_git_extraction`
    compares the probe against its OWN independent extraction, so a patched probe makes
    disagreement certain. That is a property of this harness, not of the product.
    """
    excluded = ("test_iter04_behavior", "test_eb3_check_agrees_with_an_independent_git_extraction")
    targets = _ledger_reading_tests(LEDGER_READING_MODULES)
    assert excluded in targets, (
        f"the documented exclusion is no longer in the selection: {excluded}"
    )

    grown = _grown(_live())
    later = _future_rows(_live())
    ships = sorted({*_real_ships(), THIS_ITER, *later})
    assert THIS_ITER in ships and later[-1] in ships, (
        f"premise: git must report the new ships {[THIS_ITER, *later]}"
    )

    failures = _sweep(
        monkeypatch, _as_roadmap(tmp_path, grown, "clean_clone"), grown,
        LEDGER_READING_MODULES, ships=ships, exclude=(excluded,),
    )
    assert failures == [], (
        "a clean clone of a later ship commit still reds the suite:\n" + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Behaviors 4 and 5 -- the git-keyed cross-check is DERIVED, gives the same verdict on
# both sides of a ship commit, still SKIPs, and can still fail
# ---------------------------------------------------------------------------

def test_eb4_the_git_cross_check_verdict_is_identical_once_this_iteration_has_shipped(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 4. The retired form subtracted the real ship set from a literal range, so it
    was green by construction pre-commit and red from every later clean clone. The derived
    form must return the SAME verdict when git reports this iteration as shipped.
    """
    real = _real_ships()
    text = _live()
    assert ri.unrecorded_ships(text, real) == [], "premise: the live pairing is clean today"

    after = sorted({*real, THIS_ITER})
    # ANTI-VACUITY, and deliberately NOT `after != real`: that arm is true only until this
    # iteration's own ship commit exists, so it reverted iteration 61 from a clean clone of
    # the very commit that landed it. Key it instead on a number git can never report, and
    # assert the SENSITIVITY of the check rather than a property of the ship set -- silence
    # below is then evidence, because the same call is proved able to speak.
    unshippable = max([*real, *_ledger_values(text)]) + 1
    assert ri.unrecorded_ships(text, [*real, unshippable]) == [unshippable], (
        f"anti-vacuity: the cross-check cannot even name iteration {unshippable:02d}, "
        "which has no ledger row, so its silence over the real ship set proves nothing"
    )
    assert ri.unrecorded_ships(text, after) == [], (
        f"the derived cross-check changes verdict once iteration {THIS_ITER} has shipped: "
        f"{ri.unrecorded_ship_messages(ri.unrecorded_ships(text, after))}"
    )

    monkeypatch.setattr(
        ri, "shipped_iterations_from_git",
        lambda _root: types.SimpleNamespace(iterations=after, skip_reason=None),
    )
    it31.test_b9_every_iteration_git_calls_shipped_has_exactly_one_ledger_row()


def test_eb4_the_git_cross_check_still_skips_when_git_cannot_be_asked(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 4. The offline path is a SKIP with a stated reason, never a pass."""
    monkeypatch.setattr(
        ri, "shipped_iterations_from_git",
        lambda _root: types.SimpleNamespace(iterations=None, skip_reason="not a git target"),
    )
    with pytest.raises(BaseException) as excinfo:
        it31.test_b9_every_iteration_git_calls_shipped_has_exactly_one_ledger_row()
    assert type(excinfo.value).__name__ == "Skipped", (
        f"expected a pytest skip, got {type(excinfo.value).__name__}: {excinfo.value}"
    )
    assert "not a git target" in str(excinfo.value)


def test_eb5_the_git_cross_check_names_a_shipped_iteration_that_has_no_ledger_row() -> None:
    """Behavior 5. The derived check is proved able to fail over THIS document, so its
    silence in behavior 4 is evidence rather than a reader that returns nothing."""
    real = _real_ships()
    text = _live()
    synthetic = max([*real, *_ledger_values(text)]) + 1
    assert ri.unrecorded_ships(text, [synthetic]) == [synthetic], (
        f"premise: iteration {synthetic:02d} must have no ledger row"
    )
    assert ri.unrecorded_ships(text, [*real, synthetic]) == [synthetic]
    assert f"{synthetic:02d}" in ri.unrecorded_ship_messages([synthetic])[0]

    it31.test_b9_the_real_git_cross_check_can_fail_over_this_very_document()


# ---------------------------------------------------------------------------
# Behavior 6 -- the iteration-12 ledger-number claim accepts a sparse ledger and still
# fires on a duplicate
# ---------------------------------------------------------------------------

def test_eb6_the_iter12_number_claim_accepts_the_live_sparse_ledger() -> None:
    """Behavior 6, PASS side. This is the fourth pin -- the one iteration 60 missed."""
    it12.test_b8_ledger_numbers_are_two_digit_unique_and_strictly_ascending()


def test_eb6_the_iter12_number_claim_fires_on_a_duplicated_ledger_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavior 6, FAIL side. Uniqueness and ascent are still rules over the whole ledger."""
    text = _live()
    victim = HISTORICAL_RUN[4]
    line = _ledger_line(text, victim)
    doubled = _mutate(text, line, f"{line}\n{line}")
    assert _ledger_values(doubled).count(victim) == 2, (
        "fixture premise broken: the row was not duplicated"
    )

    _point_at(monkeypatch, _as_roadmap(tmp_path, doubled, "doubled"))
    with pytest.raises(AssertionError):
        it12.test_b8_ledger_numbers_are_two_digit_unique_and_strictly_ascending()


# ---------------------------------------------------------------------------
# Behavior 7 -- both of the product's own judges are asserted directly over the live
# document and are silent
# ---------------------------------------------------------------------------

def test_eb7_both_product_judges_are_silent_over_the_live_document() -> None:
    """Behavior 7. The tools ACCEPT the document; only the retired pins rejected it, which
    is the finding this iteration rests on."""
    text = _live()
    assert ri.ledger_iterations(text), "anti-vacuity: no ledger rows parsed"

    sequence = ri.ledger_sequence_violations(text)
    assert sequence == [], "; ".join(v.message for v in sequence)

    missing = ri.unrecorded_ships(text, _real_ships())
    assert missing == [], "; ".join(ri.unrecorded_ship_messages(missing))


# ---------------------------------------------------------------------------
# Behavior 8 -- the `_mutate` discipline survives in both relaxed files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", [it12, it31], ids=["iter12", "iter31"])
def test_eb8_each_relaxed_files_mutator_asserts_its_own_premise(module) -> None:
    """Behavior 8. A control fixture built with a no-op `replace`, or keyed on a string the
    live document does not hold, is vacuous -- so both mutators must refuse both cases.
    """
    text = _live()
    sample = _ledger_line(text, HISTORICAL_RUN[0])

    with pytest.raises(AssertionError):
        module._mutate(text, "a string the live document does not hold", "x")
    with pytest.raises(AssertionError):
        module._mutate(text, sample, sample)

    changed = module._mutate(text, sample, sample + " (mutated)")
    assert changed != text, "the mutator must still perform a real replacement"


# ---------------------------------------------------------------------------
# Iteration 62 spec behaviors 6 and 7 -- the sweep's DOMAIN includes this module, and the
# sweep over the REAL declared domain is proved able to FIRE.
#
# The `eb<N>` numbers above are iteration 61's spec. Iteration 62's spec adds two behaviors
# the preserved payload does not assert directly: (6) the discovered domain includes the
# current iteration's own test module and the declared tuple names it -- iteration 61
# EXEMPTED itself and was reverted by a pin inside the exempted file; and (7) the sweep,
# pointed at a document with a historical ledger row deleted, reports FAILURES rather than
# silence, measured over the REAL committed modules and not a synthetic stand-in.
# ---------------------------------------------------------------------------

def test_spec62_eb6_the_sweep_domain_contains_this_iterations_own_test_module() -> None:
    """Iteration 62, behavior 6. No identity-based self-exclusion survives.

    `test_eb3_the_durability_sweep_reaches_every_ledger_reading_module_in_the_suite` asserts
    `discovered - declared == []`, which is silent when a module is in NEITHER set -- exactly
    the state iteration 61 shipped. So the membership of this module is asserted positively,
    on both sides: the filesystem discovery must FIND it, and the hand-written tuple the sweep
    actually iterates must NAME it.
    """
    discovered = _modules_with_ledger_reading_tests(TESTS_DIR)
    assert discovered, "anti-vacuity: discovery found nothing, so membership proves nothing"
    assert SELF_MODULE in discovered, (
        "the discovery does not see this module's own zero-argument ledger-reading tests, "
        f"so the sweep can never measure them: {sorted(discovered)}"
    )
    assert SELF_MODULE in LEDGER_READING_MODULES, (
        "the declared sweep tuple does not name this module, so its own pins are unswept -- "
        "the exemption that reverted iteration 61"
    )

    own = [name for module, name in _ledger_reading_tests(LEDGER_READING_MODULES)
           if module == SELF_MODULE]
    assert own, (
        "the selector reaches none of this module's tests, so naming it in the tuple is "
        "cosmetic rather than load-bearing"
    )


def test_spec62_eb7_the_sweep_over_the_real_modules_fires_on_a_deleted_historical_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Iteration 62, behavior 7, FAIL side over the REAL domain.

    The existing two-sided control registers a SYNTHETIC module carrying the retired defect,
    which proves the sweep's plumbing invokes something -- never that the suite's real pins
    still speak. Here the same sweep, over the same declared tuple of committed modules, is
    pointed at the live document with one historical ledger row deleted: it must report
    failures, name more than one module, and name THIS module -- which is what makes removing
    the self-exemption load-bearing rather than cosmetic.
    """
    text = _live()
    victim = HISTORICAL_RUN[len(HISTORICAL_RUN) // 2]
    shrunk = _mutate(text, _ledger_line(text, victim) + "\n", "")
    assert len(_ledger_values(shrunk)) == len(_ledger_values(text)) - 1, (
        "fixture premise broken: exactly one ledger row must have been removed"
    )

    path = _as_roadmap(tmp_path, shrunk, "row_deleted")
    failures = _sweep(monkeypatch, path, shrunk, LEDGER_READING_MODULES)
    assert len(failures) >= 3, (
        "the durability sweep is silent over a document missing ledger row "
        f"{victim:02d}, so its green verdict elsewhere is not evidence: {failures}"
    )

    named = {line.split("::")[0] for line in failures}
    assert len(named) >= 2, f"only one module spoke, so the sweep is barely two-sided: {named}"
    assert SELF_MODULE in named, (
        "this module's own ledger-reading tests did not fire over a broken ledger, so its "
        f"place in the sweep is cosmetic: {sorted(named)}"
    )
