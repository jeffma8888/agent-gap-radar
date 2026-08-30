"""Iteration 85 behaviors: `tools/verify_quotes.py`'s `verify` resolves the module-level
`fetch` at CALL time instead of freezing it into the signature as an import-time default,
so substituting the module attribute reaches the one seamless call `main` makes -- while
the published `fetch=` keyword keeps working and still WINS over the substitution.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/` or `tools/`
implementation logic, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any
diff. Every expectation comes from `pm.md`'s Expected Behaviors, and every claim is measured
by CALLING or INTROSPECTING the public interface -- `verify_quotes.verify`,
`verify_quotes.fetch_all`, `verify_quotes.main`, `verify_quotes.page_text` -- over literal
strings, stub callables and `tmp_path` records this file controls.

Structural notes, so this file cannot lie later:

* **The suite stays OFFLINE, and that is enforced rather than promised** (behavior 7). An
  autouse fixture installs a socket tripwire for EVERY test in this module, and one test
  proves the tripwire is armed by attempting all three patched entry points. This file
  imports no network module, and every page reaching the tool comes from a stub this file
  owns. The tripwire is installed at fixture time, i.e. AFTER this module's import, which is
  the order that matters: `ssl` builds a class out of `socket.socket` at import time.
* **Behavior 1 is the one assertion iteration 72 could not make.** That file records, in its
  own docstring, that `setattr(module, "fetch", sentinel)` was a NO-OP for `verify` and that
  asserting "the sentinel was never called" therefore could not fail. Here the falsifiable
  form is asserted instead: after the substitution, the recorder receives the url, and the
  seamless `verify(records)` returns 0 with a `VERBATIM` line -- which is only reachable if
  the substituted page arrived.
* **Behavior 2 pins the property, not the fix.** A default that is `None` plus "no element of
  `__defaults__` is callable" is a shape a revert cannot satisfy, whichever spelling the
  revert chooses. Its premise (that `verify` HAS a default at all) is asserted, so the
  callable-audit cannot pass over an empty tuple.
* **Behavior 4 is asserted twice, once with a FALSY callable seam.** `fetch is None` and
  `fetch or module_fetch` agree on every truthy seam and disagree on a falsy one, so without
  the second form a later tidy-up toward the sibling's spelling would regress precedence
  silently. The falsy stub is a callable OBJECT whose `__bool__` is False.
* **Distinct urls per test.** Every test uses its own reserved-invalid url, so no result
  can be borrowed from a neighbour through the tool's per-URL page memo -- with ONE
  deliberate exception, `test_b3_a_locator_cited_twice_is_fetched_once_within_one_call`,
  which shares a url between two records INSIDE a single call in order to pin that memo.
  Measured before pinning: the memo does not outlive a call, so even that test cannot
  couple to a neighbour.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; nothing is written outside pytest's `tmp_path`; every url literal
  uses the reserved-invalid `.invalid` TLD.
"""

from __future__ import annotations

import ast
import inspect
import json
import pathlib
import socket
import sys
import types

import pytest

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
TESTS_DIR = REPO_ROOT / "tests"
THIS_FILE = pathlib.Path(__file__).resolve()
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import verify_quotes  # noqa: E402  (path is prepared immediately above)

#: A page and a quote that verify VERBATIM through the module's own normaliser.
GOOD_PAGE = verify_quotes.page_text("<p>hello world this is the page</p>")
GOOD_QUOTE = "hello world this is the page"

NETWORK_ROOTS = {"urllib", "http", "requests", "httpx", "ssl", "socketserver", "ftplib"}


class _NetworkAttempted(AssertionError):
    """Raised by the tripwire when a test tries to open a socket."""


@pytest.fixture(autouse=True)
def _offline_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 7: no test in this module may touch the network.

    Two-sided: `test_b7_the_socket_tripwire_is_armed_and_would_fire` proves it fires, so a
    guard that had quietly stopped being installed could not read as compliance.
    """

    def boom(*_args: object, **_kwargs: object) -> None:
        raise _NetworkAttempted("a test in this module attempted to open a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


def _record(*citations: dict) -> dict:
    """A minimal record in the shape `verify` consumes: an `evidence` list of citations."""
    return {"id": "GAP-000", "evidence": list(citations)}


def _lines(captured: str) -> list[str]:
    return [line for line in captured.splitlines() if line.strip()]


def _verbatim(captured: str) -> list[str]:
    return [line for line in _lines(captured) if line.startswith("VERBATIM")]


class _Recorder:
    """A stub `fetch`: records every url it is handed and returns a good page."""

    def __init__(self, page: str = GOOD_PAGE) -> None:
        self.page = page
        self.urls: list[str] = []
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args: object, **kwargs: object) -> str:
        self.calls.append((args, kwargs))
        self.urls.append(args[0] if args else kwargs.get("url"))  # type: ignore[arg-type]
        return self.page


class _FalsyRecorder(_Recorder):
    """A callable that is FALSY. `fetch is None` keeps it; `fetch or fetch` discards it."""

    def __bool__(self) -> bool:
        return False


class _Boom:
    """A callable that must never be reached. Records any breach for the message."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        raise AssertionError("this callable must never be invoked, got %r" % (url,))


def _one_record_register(tmp: pathlib.Path, url: str, gap_id: str = "GAP-900") -> pathlib.Path:
    """A register directory holding exactly one `*.json` record with an https locator."""
    directory = tmp / "register"
    directory.mkdir()
    doc = {
        "id": gap_id,
        "title": "a probe record this test owns",
        "evidence": [
            {
                "locator": url,
                "quote": GOOD_QUOTE,
                "source_class": "vendor-primary",
                "title": "a probe source",
                "date": "2026-01-01",
            }
        ],
    }
    (directory / (gap_id + ".json")).write_text(json.dumps(doc), encoding="utf-8")
    return directory


# --------------------------------------------------------------------------------------
# Behavior 1 -- the DEFAULT path honours a substituted module `fetch`.
# --------------------------------------------------------------------------------------


def test_b1_the_seamless_call_reaches_a_substituted_module_fetch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """THE regression: `verify(records)` with NO seam must use the CURRENT module `fetch`.

    Before this iteration the default was bound once at definition, so this substitution
    was silently ignored and the real socket stayed wired into the only call `main` makes.
    """
    url = "https://example.invalid/b1-default-path"
    recorder = _Recorder()
    monkeypatch.setattr(verify_quotes, "fetch", recorder)

    records = [("GAP-D1", _record({"locator": url, "quote": GOOD_QUOTE}))]
    rc = verify_quotes.verify(records)
    out = capsys.readouterr().out

    assert rc == 0
    assert recorder.urls == [url], "the substituted callable must receive exactly that url"
    assert len(recorder.calls) == 1, recorder.calls
    assert all(len(args) == 1 for args, _ in recorder.calls), "the url is the only argument"
    verbatim = _verbatim(out)
    assert len(verbatim) == 1, out
    assert "GAP-D1" in verbatim[0], verbatim


def test_b1_the_substituted_page_is_what_decided_the_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Anti-vacuity for behavior 1: the substituted page must be able to change the verdict.

    Same seamless call, same record, a stub returning a page that does NOT hold the quote:
    the outcome inverts. A `VERBATIM` result therefore proves the stub's page was consumed,
    rather than merely proving the stub was constructed.
    """
    url = "https://example.invalid/b1-unrelated-page"
    unrelated = verify_quotes.page_text("<p>a wholly unrelated sentence of prose</p>")
    monkeypatch.setattr(verify_quotes, "fetch", _Recorder(page=unrelated))

    records = [("GAP-D2", _record({"locator": url, "quote": GOOD_QUOTE}))]
    rc = verify_quotes.verify(records)
    out = capsys.readouterr().out

    assert rc == 1, "an absent quote must fail, so the stub's page really was consulted"
    assert _verbatim(out) == [], out
    assert "NOT ON PAGE" in out, out


def test_b1_the_retired_shape_is_provably_unreachable_by_substitution() -> None:
    """Two-sided control for behavior 1: the retired shape CANNOT pass the test above.

    Built entirely from synthetic objects this test owns, so no product source is read and
    no product file is mutated. It demonstrates the MECHANISM behavior 1 pins: a default
    evaluated once at definition captures whichever callable existed then, so replacing the
    module attribute afterwards can never reach it, while a call-time indirection can -- and
    an explicit argument still beats both. Without this control, a green behavior-1 test
    would be evidence only that the stub was constructed.
    """
    module = types.ModuleType("synthetic_seam_carrier")
    module.fetch = lambda url: "original"  # type: ignore[attr-defined]

    def retired(url: str, fetch=module.fetch) -> str:  # the retired shape, on purpose
        return fetch(url)

    def _resolve_now(url: str) -> str:
        return module.fetch(url)  # type: ignore[attr-defined]

    def shipped(url: str, fetch=None) -> str:
        return (_resolve_now if fetch is None else fetch)(url)

    module.fetch = lambda url: "substituted"  # type: ignore[attr-defined]

    assert retired("u") == "original", "the retired shape ignores a later substitution"
    assert shipped("u") == "substituted", "call-time resolution honours it"
    assert shipped("u", lambda _u: "explicit") == "explicit", "an explicit seam still wins"


def test_b1_the_resolution_happens_per_call_not_once_at_first_use(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Call-time resolution must be re-read on EVERY call, not memoised at the first one.

    A fix that resolved the module attribute once -- into a module-level slot, or into a
    default on a private helper -- would satisfy the single-substitution test above and still
    be frozen from the second call onwards, which is the same fail-open one rung further in.
    Two substitutions in sequence separate the two readings; each uses its own url so no
    per-URL page memo can serve the second answer out of the first.
    """
    first, second = _Recorder(), _Recorder()
    url_one = "https://example.invalid/b1-first-substitution"
    url_two = "https://example.invalid/b1-second-substitution"

    monkeypatch.setattr(verify_quotes, "fetch", first)
    rc_one = verify_quotes.verify([("GAP-S1", _record({"locator": url_one, "quote": GOOD_QUOTE}))])
    monkeypatch.setattr(verify_quotes, "fetch", second)
    rc_two = verify_quotes.verify([("GAP-S2", _record({"locator": url_two, "quote": GOOD_QUOTE}))])
    out = capsys.readouterr().out

    assert (rc_one, rc_two) == (0, 0)
    assert first.urls == [url_one], first.urls
    assert second.urls == [url_two], (
        "the SECOND substitution must be honoured too: %r" % (second.urls,)
    )
    assert first.urls != second.urls, "the two calls must be distinguishable"
    assert len(_verbatim(out)) == 2, out


# --------------------------------------------------------------------------------------
# Behavior 2 -- the import-time binding is gone, as a property that cannot come back.
# --------------------------------------------------------------------------------------


def test_b2_the_seam_parameter_defaults_to_none() -> None:
    params = inspect.signature(verify_quotes.verify).parameters
    assert params["fetch"].default is None
    assert params["fetch"].default is not verify_quotes.fetch


def test_b2_no_default_of_verify_is_callable() -> None:
    """The shape a revert cannot satisfy, whichever spelling it picks."""
    defaults = verify_quotes.verify.__defaults__ or ()
    kwdefaults = verify_quotes.verify.__kwdefaults__ or {}
    # Premise first: an empty tuple would make the audit below vacuous.
    assert len(defaults) + len(kwdefaults) >= 1, "verify must still HAVE a defaulted parameter"
    culprits = [d for d in defaults if callable(d)]
    culprits += [v for v in kwdefaults.values() if callable(v)]
    assert culprits == [], "no default may capture a callable at definition time: %r" % (culprits,)


def test_b2_the_callable_default_audit_fires_on_a_planted_sample() -> None:
    """Anti-vacuity: the same predicate must red on a function that HAS the defect."""

    def planted(records: object, fetch: object = verify_quotes.fetch) -> None:  # pragma: no cover
        return None

    defaults = planted.__defaults__ or ()
    assert [d for d in defaults if callable(d)], "the audit must fire on a planted defect"


def test_b2_the_seam_docstring_states_the_call_time_contract_and_its_precedence_rule() -> None:
    """The published contract lives in `verify.__doc__`, so read it through the interface.

    Beyond the eight behaviors: this is the spec's docstring acceptance criterion, asserted
    POSITIVELY only. A negative check -- "the doc must not say the default is the module
    function" -- would falsely accuse a correct doc, because a doc that EXPLAINS the retired
    shape legitimately quotes it; measured, the shipped text names the old spelling while
    saying it is NOT what the parameter defaults to. So the tolerant positive form is the
    only one that cannot manufacture a false red.
    """
    doc = inspect.getdoc(verify_quotes.verify) or ""
    assert doc, "verify must carry a docstring"
    low = doc.lower()
    assert "none" in low, doc
    assert ("call time" in low) or ("call-time" in low), doc
    assert any(w in low for w in ("wins", "takes precedence", "overrides")), doc


# --------------------------------------------------------------------------------------
# Behavior 3 -- the published keyword is unchanged, by name, kind and position.
# --------------------------------------------------------------------------------------


def test_b3_the_seam_is_still_the_positional_or_keyword_parameter_named_fetch() -> None:
    params = inspect.signature(verify_quotes.verify).parameters
    assert "fetch" in params, "the published keyword is NOT renamed: %r" % (list(params),)
    assert params["fetch"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert list(params).index("fetch") == 1, "the seam stays the second parameter"


def test_b3_the_keyword_form_routes_every_page_through_the_seam(
    capsys: pytest.CaptureFixture,
) -> None:
    url = "https://example.invalid/b3-keyword"
    recorder = _Recorder()
    records = [("GAP-KW", _record({"locator": url, "quote": GOOD_QUOTE}))]

    rc = verify_quotes.verify(records, fetch=recorder)
    out = capsys.readouterr().out

    assert rc == 0
    assert recorder.urls == [url]
    assert len(_verbatim(out)) == 1, out


def test_b3_the_positional_form_routes_every_page_through_the_seam(
    capsys: pytest.CaptureFixture,
) -> None:
    url = "https://example.invalid/b3-positional"
    recorder = _Recorder()
    records = [("GAP-POS", _record({"locator": url, "quote": GOOD_QUOTE}))]

    rc = verify_quotes.verify(records, recorder)
    out = capsys.readouterr().out

    assert rc == 0
    assert recorder.urls == [url]
    assert len(_verbatim(out)) == 1, out


def test_b3_every_page_of_a_multi_citation_record_routes_through_the_seam(
    capsys: pytest.CaptureFixture,
) -> None:
    """Behavior 3 says EVERY page, so drive a record carrying TWO citations, not one.

    A seam consulted only for the first citation would pass every single-citation fixture in
    this file while leaving the rest of a real record on the network.
    """
    first = "https://example.invalid/b3-citation-one"
    second = "https://example.invalid/b3-citation-two"
    recorder = _Recorder()
    records = [
        (
            "GAP-MULTI",
            _record(
                {"locator": first, "quote": GOOD_QUOTE},
                {"locator": second, "quote": GOOD_QUOTE},
            ),
        )
    ]

    rc = verify_quotes.verify(records, fetch=recorder)
    out = capsys.readouterr().out

    assert rc == 0
    assert recorder.urls == [first, second], recorder.urls
    assert len(_verbatim(out)) == 2, out


def test_b3_a_locator_cited_twice_is_fetched_once_within_one_call(
    capsys: pytest.CaptureFixture,
) -> None:
    """The seam makes the per-URL memo observable, so pin it -- but only WITHIN one call.

    Measured before pinning: a second, separate `verify` call over the same url fetches
    again, so the memo does not outlive a call. Asserting it ACROSS calls would couple this
    test to its neighbours and to execution order under `-n auto`; inside one call it is
    deterministic. Both records still get their own verdict line, so de-duplicating the
    fetch must not de-duplicate the report.
    """
    shared = "https://example.invalid/b3-shared-locator"
    recorder = _Recorder()
    records = [
        ("GAP-SH1", _record({"locator": shared, "quote": GOOD_QUOTE})),
        ("GAP-SH2", _record({"locator": shared, "quote": GOOD_QUOTE})),
    ]

    rc = verify_quotes.verify(records, fetch=recorder)
    out = capsys.readouterr().out

    assert rc == 0
    assert recorder.urls == [shared], (
        "one fetch for a locator cited twice: %r" % (recorder.urls,)
    )
    verbatim = _verbatim(out)
    assert len(verbatim) == 2, out
    assert {line.split()[1] for line in verbatim} == {"GAP-SH1", "GAP-SH2"}, verbatim


# --------------------------------------------------------------------------------------
# Behavior 4 -- an explicit seam BEATS a substituted module attribute.
# --------------------------------------------------------------------------------------


def test_b4_an_explicit_seam_wins_over_a_substituted_module_attribute(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    url = "https://example.invalid/b4-precedence"
    never = _Boom()
    monkeypatch.setattr(verify_quotes, "fetch", never)
    good = _Recorder()

    records = [("GAP-EXP", _record({"locator": url, "quote": GOOD_QUOTE}))]
    rc = verify_quotes.verify(records, fetch=good)
    out = capsys.readouterr().out

    assert rc == 0
    assert never.urls == [], "the module attribute must never be reached: %r" % (never.urls,)
    assert good.urls == [url]
    verbatim = _verbatim(out)
    assert len(verbatim) == 1, out
    assert "GAP-EXP" in verbatim[0]


def test_b4_a_falsy_callable_seam_still_wins(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Precedence is decided by `is None`, not by truthiness.

    `fetch or module_fetch` agrees with `fetch is None` on every TRUTHY seam, so a fixture
    whose stub is truthy cannot separate the two. This one is a callable object whose
    `__bool__` is False: under the truthiness form it would be discarded and the module
    attribute (a callable that raises) would run instead.
    """
    url = "https://example.invalid/b4-falsy-seam"
    falsy = _FalsyRecorder()
    assert callable(falsy) and not falsy, "the premise: the seam is callable AND falsy"
    never = _Boom()
    monkeypatch.setattr(verify_quotes, "fetch", never)

    records = [("GAP-FALSY", _record({"locator": url, "quote": GOOD_QUOTE}))]
    rc = verify_quotes.verify(records, fetch=falsy)
    out = capsys.readouterr().out

    assert rc == 0
    assert falsy.urls == [url], "a falsy callable seam must still receive the page request"
    assert never.urls == [], "truthiness must not decide precedence"
    assert len(_verbatim(out)) == 1, out


# --------------------------------------------------------------------------------------
# Behavior 5 -- sibling parity, pinned in ONE test.
# --------------------------------------------------------------------------------------


def test_b5_one_substitution_reaches_both_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single `setattr` must reach `fetch_all` AND `verify`.

    Pinned in one function on purpose: re-introducing an import-time default in EITHER of
    the two seams reds this test, so the parity cannot decay one half at a time.
    """
    url = "https://example.invalid/b5-parity"
    recorder = _Recorder()
    monkeypatch.setattr(verify_quotes, "fetch", recorder)

    pages = verify_quotes.fetch_all([url])
    assert pages == {url: GOOD_PAGE}, pages
    assert recorder.urls == [url], "the sibling seam resolves at call time"

    rc = verify_quotes.verify([("GAP-PAR", _record({"locator": url, "quote": GOOD_QUOTE}))])

    assert rc == 0
    assert recorder.urls == [url, url], (
        "both seams must route through the ONE substituted callable: %r" % (recorder.urls,)
    )


# --------------------------------------------------------------------------------------
# Behavior 6 -- the PRODUCTION path is substitutable end to end.
# --------------------------------------------------------------------------------------


def test_b6_main_reaches_a_substituted_module_fetch(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`main` calls `verify(records)` with no seam, so this is the path that mattered."""
    url = "https://example.invalid/b6-production"
    recorder = _Recorder()
    monkeypatch.setattr(verify_quotes, "fetch", recorder)
    register = _one_record_register(tmp_path, url, gap_id="GAP-901")
    assert len(list(register.glob("*.json"))) == 1, "the fixture holds exactly one record"

    rc = verify_quotes.main(["--gaps", str(register)])
    out = capsys.readouterr().out

    assert rc == 0
    assert recorder.urls == [url], "the substitution must reach the seamless call main makes"
    verbatim = _verbatim(out)
    assert len(verbatim) == 1, out
    assert "GAP-901" in verbatim[0], verbatim


def test_b6_main_is_not_short_circuiting_the_page(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Anti-vacuity for behavior 6: the substituted page decides `main`'s exit code too."""
    url = "https://example.invalid/b6-unrelated"
    unrelated = verify_quotes.page_text("<p>nothing here resembles the cited quote</p>")
    monkeypatch.setattr(verify_quotes, "fetch", _Recorder(page=unrelated))
    register = _one_record_register(tmp_path, url, gap_id="GAP-902")

    rc = verify_quotes.main(["--gaps", str(register)])
    out = capsys.readouterr().out

    assert rc == 1, "the stub's page must be what the verdict rests on"
    assert "NOT ON PAGE" in out, out


# --------------------------------------------------------------------------------------
# Behavior 7 -- this module cannot pass while doing I/O.
# --------------------------------------------------------------------------------------


def _self_tree() -> ast.Module:
    return ast.parse(THIS_FILE.read_text(encoding="utf-8"))


def test_b7_the_socket_tripwire_is_armed_and_would_fire() -> None:
    """Anti-vacuity: a guard that cannot fail is not evidence, so prove it fires."""
    with pytest.raises(_NetworkAttempted):
        socket.socket()
    with pytest.raises(_NetworkAttempted):
        socket.create_connection(("example.invalid", 80))
    with pytest.raises(_NetworkAttempted):
        socket.getaddrinfo("example.invalid", 80)


def test_b7_the_tripwire_fixture_is_autouse_and_patches_all_three_entry_points() -> None:
    """The tripwire's INSTALLATION is audited, not just its firing.

    A fixture that stopped being autouse, or that lost one of the three patches, would leave
    the rest of this module's assertions unguarded while every test still passed.
    """
    names: list[str] = []
    autouse = False
    for node in ast.walk(_self_tree()):
        if not isinstance(node, ast.FunctionDef) or node.name != "_offline_tripwire":
            continue
        for deco in node.decorator_list:
            source = ast.dump(deco)
            if "autouse" in source:
                autouse = True
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                if inner.func.attr == "setattr" and len(inner.args) >= 2:
                    literal = inner.args[1]
                    if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                        names.append(literal.value)
    assert autouse, "the tripwire fixture must be autouse"
    assert sorted(names) == ["create_connection", "getaddrinfo", "socket"], names


def test_b7_this_file_imports_no_network_module() -> None:
    roots: set[str] = set()
    for node in ast.walk(_self_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    assert not (roots & NETWORK_ROOTS), sorted(roots & NETWORK_ROOTS)


def test_b7_no_absolute_machine_path_is_written_down_here() -> None:
    """The needles are ASSEMBLED, never spelled: a literal here would match itself."""
    text = THIS_FILE.read_text(encoding="utf-8")
    sep = "/"
    for needle in (sep + "Users" + sep, sep + "home" + sep, "C:" + chr(92)):
        assert needle not in text, needle
    planted = text + sep + "Users" + sep + "someone"
    assert (sep + "Users" + sep) in planted, "the audit must fire on a planted sample"


# --------------------------------------------------------------------------------------
# Behavior 8 -- iteration 72's fences: exactly ONE is inverted, the rest hold unedited.
# --------------------------------------------------------------------------------------

ITER72 = TESTS_DIR / "test_iter72_behavior.py"

#: The contract this iteration retires. Named here, matched against FUNCTION DEFS in the
#: other file, so this mention cannot satisfy its own absence check.
RETIRED_FENCE = "test_b8_the_seam_default_is_the_modules_own_fetch"

HELD_FENCES = (
    "test_b8_the_one_argument_call_form_is_still_accepted",
    "test_b14_every_verify_call_here_injects_a_seam_except_the_documented_one",
    "test_the_fail_closed_signature_never_returns",
    "test_docstring_names_the_family_and_both_of_its_instances",
    "test_docstring_narrows_the_untested_claim_to_fetch",
)


def _iter72_functions() -> dict[str, ast.FunctionDef]:
    tree = ast.parse(ITER72.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def test_b8_the_retired_fence_name_is_gone_from_iteration_72() -> None:
    functions = _iter72_functions()
    assert functions, "the fence audit must not pass over an unparsed file"
    assert RETIRED_FENCE not in functions, (
        "the fence must be RENAMED, since its old name describes the retired contract"
    )


def test_b8_the_inverted_fence_survives_rewritten_rather_than_deleted() -> None:
    """A deleted fence is indistinguishable from a forgotten one, so require its successor."""
    functions = _iter72_functions()
    successors = [name for name in functions if "seam_default" in name]
    assert len(successors) == 1, successors
    body = ast.get_source_segment(ITER72.read_text(encoding="utf-8"), functions[successors[0]])
    assert body is not None
    assert "is None" in body, "the successor must assert the NEW contract"


@pytest.mark.parametrize("name", HELD_FENCES)
def test_b8_the_other_fences_are_still_present(name: str) -> None:
    assert name in _iter72_functions(), name


def test_b8_no_test_of_this_iteration_was_added_to_iteration_72() -> None:
    """Acceptance criterion: the new coverage lands HERE, not in the pinned census file."""
    assert not [name for name in _iter72_functions() if "iter85" in name or "b85" in name]
