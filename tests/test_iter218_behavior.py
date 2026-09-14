"""Iteration 218 -- `agent_gap_radar.scoring` declares the surface it supports.

Eighteen top-level functions were importable from the module `VISION.md` singles out
for protection; eight of them were internal census steps of two report sections with
no caller outside `render.py`.  This iteration privatises those eight and publishes
an explicit `__all__`.  Because it is a pure visibility change, its whole oracle is
that NO rendered byte moved -- and that equivalence cannot be measured after the
fact, since re-rendering a renamed tree only compares the new tree with itself.

ISOLATION: black-box.  No implementation source was read to write this module.  The
verbs are driven through `cli.main(argv)`; the surface facts are RUNTIME
introspection of the imported module's namespace (`vars`, `inspect.signature`), never
a reading of `scoring.py`.  Every constant below was MEASURED, not assumed.

PROVENANCE OF THE PINNED BYTES -- the pre-change implementation was materialised as
an opaque blob with `git archive HEAD src | tar -x -C <tmp>` at HEAD `31e5864` (the
tree before this iteration's edit), then run under its own `PYTHONPATH` with nothing
installed.  All five documents and all eight helper return values were captured from
THAT tree and are pinned here as literals; they are not re-rendered from the working
tree, so a regression that shipped in this very iteration cannot re-baseline itself.

TWO SPEC FORMS ARE PINNED AS MEASURED, NOT AS WRITTEN (see tester.md):
  * Every behaviour spells the invocation `radar report . --gaps gaps`.  There is no
    `--gaps` flag on `report`/`list`/`validate` -- the register is a POSITIONAL --
    so that literal form exits 2 with `Error: unrecognized arguments: --gaps gaps`,
    and it also passes `.`, which would point the register at the repo root.  The
    real form is `radar report gaps`.  Both are pinned: the working form for the
    equivalence, and the spec's literal form with the refusal it actually produces.
  * `radar scan` DOES take `--gaps`, but its `target` positional is echoed into the
    document, so the same scan reports 6025 B from `scan gaps` and 6063 B from an
    absolute target.  The pinned digests are the RELATIVE form, so `_run` chdirs to
    the repo root; this is a path echo, not drift, and the absolute form is pinned
    too so a future reader cannot mistake one for the other.

Offline, deterministic, no network.  The live `gaps/` register is only READ; every
written fixture lives under `tmp_path`.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import pathlib

import pytest

from agent_gap_radar import render, registry
from agent_gap_radar import scoring
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------------
# Spec behaviour 4: the surviving public function set, AS A LITERAL.  Copied from
# the spec, NOT derived from the module under test -- deriving it would make the
# assertion vacuous.
PUBLIC_FUNCTIONS = [
    "below_floor", "confidence", "confidence_without", "distinct_sources",
    "distinct_tags", "priority", "promotion_options", "rank", "strongest_source",
    "tag_coverage",
]

#: Spec behaviour 6/7: the eight names that become private.
PRIVATISED = (
    "distinct_register_sources", "shared_sources", "records_on_shared_source",
    "sole_source_records", "newest_citation_date", "register_anchor_date",
    "evidence_age_days", "aged_records",
)

#: Acceptance criterion: `__all__` is EXACTLY the 10 public functions plus the one
#: constant `render.py` imports from `scoring`.
ALL_EXPECTED = frozenset(PUBLIC_FUNCTIONS) | {"CONFIDENCE_FLOOR_DEFAULT"}

#: argv tail -> (stdout byte length, sha256) captured from the PRE-CHANGE tree at
#: HEAD `31e5864` via `git archive`.  All five exited 0 with EMPTY stderr.
PRECHANGE_DOCUMENTS: dict[tuple[str, ...], tuple[int, str]] = {
    ("report", "gaps"):
        (39022, "be4bd4e983356c8b705e3e7c026ca2bc713912c0ac89ad7fe0c1d5587be0165f"),
    ("list", "gaps"):
        (17446, "06906c37e424382884cf2890fa7b57fc101b7eca545a92dcba415cb15f7b2f88"),
    ("list", "gaps", "--json"):
        (50218, "0a6abac448d375df019b45f6af1a9770998a27d445c2d43d565903a776374468"),
    ("validate", "gaps"):
        (29, "5320bce7a70985f99078db703925a635926e4f1fff9dfe908cd5e57b6b930720"),
    ("scan", "gaps"):
        (6025, "8cf1f95984524fa39202aaa46f196a10e8b4376fa8de0c89fcce3a9b5c264a07"),
}

#: `str(inspect.signature(...))` of each of the eight, read off the PRE-CHANGE tree.
PRECHANGE_SIGNATURES = {
    "distinct_register_sources": "(gaps: 'list[Gap]') -> 'int'",
    "shared_sources": "(gaps: 'list[Gap]') -> 'list[tuple[str, list[str]]]'",
    "records_on_shared_source": "(gaps: 'list[Gap]') -> 'list[str]'",
    "sole_source_records": "(gaps: 'list[Gap]') -> 'list[Gap]'",
    "newest_citation_date": "(gap: 'Gap') -> 'str'",
    "register_anchor_date": "(gaps: 'list[Gap]') -> 'str | None'",
    "evidence_age_days": "(newest: 'str', anchor: 'str') -> 'int'",
    "aged_records": "(gaps: 'list[Gap]', threshold_days: 'int' = 365)"
                    " -> 'list[tuple[Gap, str, int]]'",
}

# --------------------------------------------------------------------------------
# A FIXED three-record register, so behaviour 7's "unchanged return value" stays a
# real oracle forever: pinning values taken from the LIVE register would go stale the
# next time a gap record is added.  Every expected value below was produced by the
# PRE-CHANGE tree on exactly this fixture.
_BASE = {
    "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"], "build_hypothesis": "build a small wrapper",
}


def _ev(locator: str, date: str, title: str, cls: str = "first-party-field") -> dict:
    return {"source_class": cls, "title": title, "locator": locator, "date": date,
            "quote": "the verbatim line"}


_A = "https://example.invalid/a"
FIXTURE_RECORDS = {
    # GAP-001 shares source A with GAP-002 and is old enough to age out.
    "GAP-001": dict(_BASE, id="GAP-001", evidence=[_ev(_A, "2024-01-02", "A")]),
    "GAP-002": dict(_BASE, id="GAP-002", evidence=[
        _ev(_A, "2026-01-02", "A"),
        _ev("https://example.invalid/b", "2026-03-04", "B", "vendor-primary")]),
    # GAP-003 carries the register's newest citation, so it sets the anchor.
    "GAP-003": dict(_BASE, id="GAP-003", evidence=[
        _ev("https://example.invalid/c", "2026-05-06", "C", "vendor-primary")]),
}

#: PRE-CHANGE outputs on FIXTURE_RECORDS, gap objects projected to `<gap ID>`.
PRECHANGE_FIXTURE_RETURNS = {
    "distinct_register_sources": 3,
    "shared_sources": [[_A, ["GAP-001", "GAP-002"]]],
    "records_on_shared_source": ["GAP-001", "GAP-002"],
    "sole_source_records": ["<gap GAP-001>", "<gap GAP-003>"],
    "register_anchor_date": "2026-05-06",
    "aged_records": [["<gap GAP-001>", "2024-01-02", 855]],
}


def _plain(obj):
    """Project Gap models to a stable token so a pydantic repr change cannot red this."""
    if hasattr(obj, "id") and hasattr(obj, "evidence"):
        return f"<gap {obj.id}>"
    if isinstance(obj, (list, tuple)):
        return [_plain(x) for x in obj]
    return obj


@pytest.fixture(scope="module")
def fixture_register(tmp_path_factory):
    directory = tmp_path_factory.mktemp("register") / "gaps"
    directory.mkdir(parents=True)
    for name, record in FIXTURE_RECORDS.items():
        (directory / f"{name}.json").write_text(json.dumps(record), encoding="utf-8")
    gaps = sorted(registry.load_all(directory), key=lambda g: g.id)
    assert [g.id for g in gaps] == ["GAP-001", "GAP-002", "GAP-003"]
    return gaps


def _private(name: str):
    """The behaviour formerly published under `name`, now under `_name`."""
    return getattr(scoring, f"_{name}")


def _run(argv, capsys, monkeypatch):
    """Run the CLI with the repo root as cwd -- `scan` echoes a relative target."""
    monkeypatch.chdir(REPO)
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out.encode("utf-8"), captured.err


# ------------------------------------------------------------------- b1, b2, b3
def test_b1_report_is_byte_identical_to_the_pre_change_document(capsys, monkeypatch):
    argv = ("report", "gaps")
    expected_len, expected_sha = PRECHANGE_DOCUMENTS[argv]
    code, out, err = _run(argv, capsys, monkeypatch)
    assert code == 0
    assert err == ""
    assert len(out) == expected_len
    assert hashlib.sha256(out).hexdigest() == expected_sha


def test_b2_report_ends_in_exactly_one_newline_and_stdout_is_only_the_document(
        capsys, monkeypatch):
    code, out, err = _run(("report", "gaps"), capsys, monkeypatch)
    assert code == 0
    text = out.decode("utf-8")
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    assert text.lstrip().startswith("#")  # a markdown document, no preamble
    assert err == ""  # nothing but the document reached stdout, nothing reached stderr


@pytest.mark.parametrize("argv", [
    ("list", "gaps"), ("list", "gaps", "--json"), ("validate", "gaps"),
    ("scan", "gaps"),
])
def test_b3_other_verbs_are_byte_identical_to_their_pre_change_output(
        argv, capsys, monkeypatch):
    expected_len, expected_sha = PRECHANGE_DOCUMENTS[argv]
    code, out, err = _run(argv, capsys, monkeypatch)
    assert code == 0  # every pinned invocation exited 0 pre-change
    assert err == ""
    assert (len(out), hashlib.sha256(out).hexdigest()) == (expected_len, expected_sha)
    assert out.endswith(b"\n") and not out.endswith(b"\n\n")


def test_b3_the_specs_literal_invocation_is_refused_for_an_unknown_flag(
        capsys, monkeypatch):
    """The spec spells `report . --gaps gaps`; `--gaps` is not a flag on this verb.

    argparse's contract is that `error()` never returns, so the refusal arrives as
    `SystemExit(2)` rather than a return code -- pinned as measured.
    """
    monkeypatch.chdir(REPO)
    with pytest.raises(SystemExit) as excinfo:
        main(["report", ".", "--gaps", "gaps"])
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip().splitlines()[-1] == (
        "Error: unrecognized arguments: --gaps gaps")


def test_b3_scan_echoes_its_target_so_an_absolute_target_is_a_different_document(
        capsys, monkeypatch):
    """Pinned so a later reader cannot mistake the path echo for a rendering drift."""
    code, out, err = _run(("scan", str(REPO / "gaps")), capsys, monkeypatch)
    assert code == 0 and err == ""
    assert len(out) != PRECHANGE_DOCUMENTS[("scan", "gaps")][0]


def test_b3_the_engineers_committed_digests_agree_with_this_modules_capture():
    """Two independent pre-change captures of the same five documents must agree.

    Imported HARD, not with `importorskip`: this is the ONLY assertion that can catch
    a golden which is secretly a post-change self-portrait, so if the fixture ever
    disappears the suite must go red rather than quietly skip the one check that
    matters.  Round 2 re-derived all five pairs a second time from an independent
    `git archive 31e5864` export; all three captures agree.
    """
    import _iter218_report_golden as fixture

    assert dict(fixture.PRECHANGE_DOCUMENTS) == PRECHANGE_DOCUMENTS


# ------------------------------------------------------------------------ b4
def test_b4_public_callable_surface_is_exactly_the_pinned_ten_names():
    found = sorted(
        n for n, v in vars(scoring).items()
        if not n.startswith("_") and callable(v)
        and getattr(v, "__module__", None) == scoring.__name__)
    assert found == sorted(PUBLIC_FUNCTIONS)  # nothing extra is published
    for name in PUBLIC_FUNCTIONS:            # and nothing pinned went missing
        assert callable(getattr(scoring, name)), name


# ------------------------------------------------------------------------ b5
def test_b5_dunder_all_is_a_duplicate_free_sequence_of_resolvable_names():
    assert hasattr(scoring, "__all__")
    names = scoring.__all__
    assert isinstance(names, (tuple, list)), type(names)
    assert all(isinstance(n, str) for n in names)
    assert len(names) == len(set(names))
    unresolved = [n for n in names if not hasattr(scoring, n)]
    assert unresolved == []


# ------------------------------------------------------------------------ b6
def test_b6_dunder_all_holds_the_ten_public_names_and_none_of_the_eight():
    names = set(scoring.__all__)
    assert set(PUBLIC_FUNCTIONS) <= names
    assert names.isdisjoint(PRIVATISED)


def test_b6_dunder_all_is_exactly_the_ten_functions_plus_the_one_shared_constant():
    assert set(scoring.__all__) == ALL_EXPECTED


# ------------------------------------------------------------------------ b7
@pytest.mark.parametrize("name", PRIVATISED)
def test_b7_each_privatised_name_is_absent_public_and_present_private(name):
    assert not hasattr(scoring, name), f"{name} is still published"
    assert callable(_private(name)), f"_{name} is missing"
    # It stayed IN scoring.py -- no logic moved into render.py.
    assert _private(name).__module__ == scoring.__name__


@pytest.mark.parametrize("name", PRIVATISED)
def test_b7_each_privatised_name_keeps_its_pre_change_signature(name):
    assert str(inspect.signature(_private(name))) == PRECHANGE_SIGNATURES[name]


@pytest.mark.parametrize("name", sorted(PRECHANGE_FIXTURE_RETURNS))
def test_b7_each_privatised_name_returns_its_pre_change_value(name, fixture_register):
    assert _plain(_private(name)(fixture_register)) == PRECHANGE_FIXTURE_RETURNS[name]


def test_b7_the_two_per_record_helpers_return_their_pre_change_values(
        fixture_register):
    newest = _private("newest_citation_date")
    assert newest(fixture_register[0]) == "2024-01-02"
    assert newest(fixture_register[1]) == "2026-03-04"
    anchor = _private("register_anchor_date")(fixture_register)
    assert _private("evidence_age_days")(newest(fixture_register[0]), anchor) == 855
    # The default threshold is still 365, so lowering it widens the aged set.
    assert _plain(_private("aged_records")(fixture_register, 1)) == [
        ["<gap GAP-001>", "2024-01-02", 855], ["<gap GAP-002>", "2026-03-04", 63]]


# ------------------------------------------------------------------------ b8
def test_b8_scoring_still_imports_with_pydantic_absent():
    """Proved the way the committed tests prove it -- the blocker is IMPORTED."""
    import importlib

    import test_iter73_behavior as it73

    with it73.pydantic_blocked():
        module = importlib.import_module("agent_gap_radar.scoring")
        assert set(module.__all__) == ALL_EXPECTED
        for name in PUBLIC_FUNCTIONS:
            assert callable(getattr(module, name)), name
        for name in PRIVATISED:
            assert not hasattr(module, name), name
            assert callable(getattr(module, f"_{name}")), name


# ------------------------------------------------------------------------ b9
def test_b9_render_imports_and_holds_no_stale_scoring_name():
    borrowed = {n: v for n, v in vars(render).items()
                if callable(v) and getattr(v, "__module__", None) == scoring.__name__}
    assert borrowed, "render borrows nothing from scoring -- the census is vacuous"
    for name, value in borrowed.items():
        assert getattr(scoring, name, None) is value, name
    # No name render borrows may be one of the OLD public spellings.
    assert set(borrowed).isdisjoint(PRIVATISED)


# ------------------------ acceptance criterion: no doc points at a dead name ----
def test_no_shipped_module_points_at_a_dead_public_scoring_name():
    dead = [f"scoring.{n}" for n in PRIVATISED]
    offenders = []
    for path in sorted((REPO / "src").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        offenders += [f"{path.name}: {token}" for token in dead if token in text]
    assert offenders == []


# ================================================================================
# ROUND 2 EXTENSIONS.  The round-1 module was left behind by a stage-cap kill; every
# pin above was RE-MEASURED in round 2 from a second, independent
# `git archive 31e5864 src | tar -x` export (all five documents, the two censuses and
# all eight signatures agreed exactly).  The tests below cover what round 1 had not
# reached: the pre-change census delta, the EFFECT of `__all__` on a star import, the
# old names as a consumer now meets them (ImportError), determinism, and render's
# namespace under the old spellings.
# ================================================================================

#: The public callable census of the PRE-CHANGE tree, pinned as a literal -- measured
#: in round 2 by running the census expression of behaviour 4 against the
#: `git archive 31e5864` export with nothing installed.  Eighteen names; the ten of
#: `PUBLIC_FUNCTIONS` plus the eight of `PRIVATISED` and nothing else.  This is what
#: makes behaviour 4 a DELTA rather than a bare snapshot: it states which names the
#: iteration removed from the published surface, without the module under test having
#: any say in the answer.
PRECHANGE_PUBLIC_FUNCTIONS = [
    "aged_records", "below_floor", "confidence", "confidence_without",
    "distinct_register_sources", "distinct_sources", "distinct_tags",
    "evidence_age_days", "newest_citation_date", "priority", "promotion_options",
    "rank", "records_on_shared_source", "register_anchor_date", "shared_sources",
    "sole_source_records", "strongest_source", "tag_coverage",
]


def test_b4_the_privatised_eight_are_exactly_the_pre_change_public_delta():
    """The two literals must partition the pre-change surface with no remainder."""
    assert len(PRECHANGE_PUBLIC_FUNCTIONS) == 18
    assert sorted(PUBLIC_FUNCTIONS) + sorted(PRIVATISED) != []  # both non-empty
    assert sorted(set(PUBLIC_FUNCTIONS) | set(PRIVATISED)) == PRECHANGE_PUBLIC_FUNCTIONS
    assert set(PUBLIC_FUNCTIONS).isdisjoint(PRIVATISED)
    # ...and today's module publishes the ten, i.e. exactly the eight went away.
    today = sorted(
        n for n, v in vars(scoring).items()
        if not n.startswith("_") and callable(v)
        and getattr(v, "__module__", None) == scoring.__name__)
    assert sorted(set(PRECHANGE_PUBLIC_FUNCTIONS) - set(PRIVATISED)) == today


def test_b5_a_star_import_publishes_exactly_the_dunder_all_surface():
    """Behaviours 5 and 6 have an EFFECT, and this is it: what `import *` hands over.

    Asserted through the interpreter rather than by reading `__all__` back, because a
    declared-but-wrong `__all__` (a name that resolves but is not the module's own, a
    stray non-public leak) is invisible to a set comparison against itself.
    """
    namespace: dict = {}
    exec("from agent_gap_radar.scoring import *", namespace)  # noqa: S102
    delivered = {n for n in namespace if not n.startswith("__")}
    assert delivered == ALL_EXPECTED
    assert delivered.isdisjoint(PRIVATISED)
    # Every delivered function belongs to scoring itself -- no re-exported third party.
    for name in delivered - {"CONFIDENCE_FLOOR_DEFAULT"}:
        assert namespace[name].__module__ == scoring.__name__, name
    # The one constant is a plain float floor, not a callable smuggled in as data.
    assert isinstance(namespace["CONFIDENCE_FLOOR_DEFAULT"], (int, float))
    assert not callable(namespace["CONFIDENCE_FLOOR_DEFAULT"])


@pytest.mark.parametrize("name", PRIVATISED)
def test_b7_the_old_public_name_is_no_longer_importable_at_all(name):
    """How a consumer meets behaviour 7: `from ... import shared_sources` now fails.

    `hasattr` is the mechanism; ImportError is the observable contract, and it is the
    form that would red loudly for any downstream reader of
    `docs/CONSUMER_CONTRACT.md` who had been depending on the wider surface.
    """
    with pytest.raises(ImportError):
        exec(f"from agent_gap_radar.scoring import {name}", {})  # noqa: S102
    # The replacement spelling imports cleanly under the same one-line form.
    private: dict = {}
    exec(f"from agent_gap_radar.scoring import _{name} as fn", private)  # noqa: S102
    assert callable(private["fn"])


def test_b1_report_is_deterministic_across_repeated_runs(capsys, monkeypatch):
    """This repo's stated convention (iteration 111) proves byte-identity as
    determinism plus cross-route, so the pinned digest is paired with a same-process
    re-run: a renderer that had picked up run-order or dict-order sensitivity in the
    rename would match the golden once and drift on the second call.
    """
    first_code, first, first_err = _run(("report", "gaps"), capsys, monkeypatch)
    second_code, second, second_err = _run(("report", "gaps"), capsys, monkeypatch)
    assert (first_code, second_code) == (0, 0)
    assert first_err == "" and second_err == ""
    assert first == second
    assert len(first) == PRECHANGE_DOCUMENTS[("report", "gaps")][0]


@pytest.mark.parametrize("name", PRIVATISED)
def test_b9_render_exposes_no_attribute_under_an_old_public_spelling(name):
    """A stale `from scoring import shared_sources` in render would raise at import
    time, but a stale REBINDING (a local alias kept for compatibility) would not --
    and it would quietly re-publish the surface this iteration retired, one module
    over.  Measured absent on the working tree, pinned so it stays absent.
    """
    assert not hasattr(render, name), f"render re-publishes the retired {name}"


def test_b9_render_borrows_the_private_spellings_for_the_report_census():
    """The positive half of behaviour 9: render did not merely stop naming the old
    helpers, it now reaches them under the new names.  Six of the eight are census
    steps render calls; the two the spec measured as having NO caller
    (`newest_citation_date`, `evidence_age_days`) are correctly absent from its
    namespace, so this asserts the six and pins the two as not-borrowed.
    """
    borrowed = {n for n, v in vars(render).items()
                if callable(v)
                and getattr(v, "__module__", None) == scoring.__name__}
    reached = {n for n in borrowed if n.startswith("_")}
    assert reached == {
        "_distinct_register_sources", "_shared_sources", "_records_on_shared_source",
        "_sole_source_records", "_register_anchor_date", "_aged_records",
    }
    for name in ("newest_citation_date", "evidence_age_days"):
        assert f"_{name}" not in borrowed  # no caller, per the spec's own census
        assert callable(_private(name))    # still reachable from scoring itself
