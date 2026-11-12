"""Iteration 400 tester: black-box checks of the fresh-vs-cached determinism rewrite.

The six target nodes are driven IN-PROCESS with both scan seams replaced by spies:
`_selfscan.run_direct` (the fresh side, reached as a module attribute) and the target
module's `selfscan` name (the cached side). The spies record the argv each side was
asked for and hand back canned documents, so these arms cost no real scan at all.

That lets every Expected Behavior be exercised cheaply:
  B1  exactly one fresh call, a cached call with the IDENTICAL argv, no other scan path;
  B2  the argv is one of the four keys other modules warm;
  B3  each kept assertion is proven able to fail by feeding a document that breaks it;
  B4  a one-byte perturbation of the fresh side alone fails the node;
  B8  the `_selfscan` docstring tells the truth.
One arm (B5) runs a single real `run_direct` to pin that it is never cached.
"""

from __future__ import annotations

import importlib
import json
import subprocess

import pytest

import _selfscan

#: (module, function, call-kwargs, expects-json)
TARGETS = (
    ("test_iter298_behavior", "test_b7_b9_scan_is_deterministic_and_ends_in_one_newline", {}, False),
    ("test_iter342_behavior", "test_b10_scan_json_deterministic", {}, True),
    ("test_iter345_behavior", "test_b3_scan_determinism", {}, False),
    ("test_iter394_behavior", "test_b8_self_scan_twice_byte_identical", {}, True),
    ("test_iter28_behavior", "test_verb_is_deterministic_and_ends_in_one_newline", {"which": "scan"}, False),
    ("test_iter28_behavior", "test_verb_is_deterministic_and_ends_in_one_newline", {"which": "scan --json"}, True),
)
IDS = ["298", "342", "345", "394", "28-scan", "28-scan-json"]

WARM_MD = {(), ("--gaps", "gaps")}
WARM_JSON = {("--json",), ("--gaps", "gaps", "--json")}

GOOD_MD = "# radar scan\n\nsome body\n"
GOOD_JSON = '{"gaps": [{"id": "GAP-001"}]}\n'


def _good(argv: tuple[str, ...]) -> tuple[int, str, str]:
    return (0, GOOD_JSON if "--json" in argv else GOOD_MD, "")


class _Bed:
    """Spies on both seams of one target module; `fresh`/`cached` shape the replies."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, modname: str) -> None:
        self.mod = importlib.import_module(modname)
        self.fresh_calls: list[tuple[str, ...]] = []
        self.cached_calls: list[tuple[str, ...]] = []
        self.fresh = _good
        self.cached = _good

        def run_direct(argv, *a, **k):
            self.fresh_calls.append(tuple(argv))
            return self.fresh(tuple(argv))

        def selfscan(argv=(), *a, **k):
            self.cached_calls.append(tuple(argv))
            return self.cached(tuple(argv))

        def forbidden(*a, **k):
            raise AssertionError(f"forbidden extra scan path called with {a!r}")

        monkeypatch.setattr(self.mod._selfscan, "run_direct", run_direct)
        monkeypatch.setattr(self.mod, "selfscan", selfscan)
        monkeypatch.setattr(subprocess, "run", forbidden)
        for name in ("main", "_cli", "_run", "_scan"):
            if hasattr(self.mod, name):
                monkeypatch.setattr(self.mod, name, forbidden)

    def call(self, fn: str, kwargs: dict) -> None:
        func = getattr(self.mod, fn)
        if "which" in kwargs:
            name, argv = next(v for v in self.mod.VERBS if v[0] == kwargs["which"])
            func(name, argv, None)
        else:
            func()


@pytest.mark.parametrize("modname,fn,kwargs,is_json", TARGETS, ids=IDS)
def test_b1_b2_one_fresh_one_cached_on_a_warm_key(monkeypatch, modname, fn, kwargs, is_json):
    bed = _Bed(monkeypatch, modname)
    bed.call(fn, kwargs)  # green on good canned documents, with no forbidden path hit
    assert len(bed.fresh_calls) == 1, bed.fresh_calls
    argv = bed.fresh_calls[0]
    assert argv in bed.cached_calls, (argv, bed.cached_calls)
    assert argv in (WARM_JSON if is_json else WARM_MD), argv


@pytest.mark.parametrize("modname,fn,kwargs,is_json", TARGETS, ids=IDS)
def test_b2_module_imports_the_autouse_cache_fixture(modname, fn, kwargs, is_json):
    mod = importlib.import_module(modname)
    assert getattr(mod, "selfscan_run_cache", None) is _selfscan.selfscan_run_cache


def test_b2_each_target_key_is_warmed_by_a_non_target_module(monkeypatch):
    """A cold key would compute both sides inside the node and save nothing."""
    import pathlib
    import re
    used: set[tuple[str, ...]] = set()
    for modname, fn, kwargs, _ in TARGETS:
        with monkeypatch.context() as mp:
            bed = _Bed(mp, modname)
            bed.call(fn, kwargs)
            used |= set(bed.fresh_calls)
    tests = pathlib.Path(__file__).resolve().parent
    skip = {f"{t[0]}.py" for t in TARGETS} | {pathlib.Path(__file__).name, "test_iter400_behavior.py"}
    spellings: set[str] = set()
    for path in tests.glob("test_*.py"):
        if path.name not in skip:
            text = path.read_text(encoding="utf-8")
            spellings |= set(re.findall(r"selfscan\((\([^)]*\))", text))
            if re.search(r"selfscan\(\)", text):
                spellings.add("()")
    norm = {re.sub(r"\s+", "", s).replace("'", '"') for s in spellings}
    assert used, "spies recorded no fresh argv"
    for key in used:
        lit = re.sub(r"\s+", "", repr(key)).replace("'", '"')
        assert lit in norm, f"target key {key!r} is warmed by no other module; seen {sorted(norm)}"


# B3 -- each kept assertion can fail. Each perturbation is applied to BOTH sides so that
# only the named invariant (not fresh==cached) is what breaks.
BREAKS = {
    "rc-nonzero": lambda argv: (1, _good(argv)[1], ""),
    "two-newlines": lambda argv: (0, _good(argv)[1] + "\n", ""),
    "no-newline": lambda argv: (0, _good(argv)[1].rstrip("\n"), ""),
    "blank": lambda argv: (0, "\n", ""),
}


@pytest.mark.parametrize("brk", sorted(BREAKS))
@pytest.mark.parametrize("modname,fn,kwargs,is_json", TARGETS, ids=IDS)
def test_b3_kept_invariant_can_fail(monkeypatch, modname, fn, kwargs, is_json, brk):
    bed = _Bed(monkeypatch, modname)
    bad = BREAKS[brk]
    # 298 reads its --json half only from the cache; break the side its md half asserts on.
    bed.fresh = bed.cached = (lambda argv: bad(argv) if ("--json" in argv) == is_json else _good(argv))
    with pytest.raises((AssertionError, json.JSONDecodeError)):
        bed.call(fn, kwargs)


@pytest.mark.parametrize("modname,fn,kwargs,is_json", TARGETS, ids=IDS)
def test_b3_fresh_stderr_must_be_empty(monkeypatch, modname, fn, kwargs, is_json):
    bed = _Bed(monkeypatch, modname)
    bed.fresh = lambda argv: (0, _good(argv)[1], "warning\n")
    with pytest.raises(AssertionError):
        bed.call(fn, kwargs)


@pytest.mark.parametrize("modname,fn,kwargs,is_json",
                         [t for t in TARGETS if t[3]], ids=[i for i, t in zip(IDS, TARGETS) if t[3]])
def test_b3_json_node_requires_a_non_empty_object(monkeypatch, modname, fn, kwargs, is_json):
    bed = _Bed(monkeypatch, modname)
    bed.fresh = bed.cached = lambda argv: (0, "{}\n", "") if "--json" in argv else _good(argv)
    with pytest.raises(AssertionError):
        bed.call(fn, kwargs)


@pytest.mark.parametrize("modname,fn,kwargs,is_json", TARGETS, ids=IDS)
def test_b4_one_byte_on_the_fresh_side_only_fails_the_node(monkeypatch, modname, fn, kwargs, is_json):
    bed = _Bed(monkeypatch, modname)
    bed.fresh = lambda argv: (0, _good(argv)[1] + "x", "")
    with pytest.raises(AssertionError):
        bed.call(fn, kwargs)


def test_b4_cached_side_is_unaffected_by_patching_run_direct(monkeypatch):
    """`selfscan`'s compute default is bound at def time, so patching the module
    attribute `run_direct` cannot also perturb the cached side."""
    import inspect
    default = inspect.signature(_selfscan.selfscan).parameters["compute"].default
    real = _selfscan.run_direct
    monkeypatch.setattr(_selfscan, "run_direct", lambda *a, **k: (9, "x", "x"))
    assert default is real and default is not _selfscan.run_direct


def test_b5_run_direct_is_never_served_from_the_cache():
    before = _selfscan.compute_count
    rc, out, err = _selfscan.run_direct(("--gaps", "gaps", "--json"))
    assert _selfscan.compute_count == before + 1
    assert rc == 0 and err == "" and json.loads(out)


def test_b8_selfscan_docstring_tells_the_truth():
    doc = _selfscan.__doc__ or ""
    assert "keep calling the CLI directly" not in doc
    assert "run_direct" in doc and "selfscan" in doc
    low = doc.lower()
    assert "count" in low and "monkeypatch" in low and "call the cli directly" in low
    assert "one side fresh" in low
