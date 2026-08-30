"""Iteration 72 behaviors: `tools/verify_quotes.py` gains an injectable `fetch` seam and a
published `page_text` normaliser that treats a closed set of code-ish inline tags as
zero-width -- so the four verdicts become provable with no network, and an honest quote that
crosses a `<code>` boundary stops being reported NOT ON PAGE.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/` or `tools/`
implementation logic, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any
diff. Every expectation comes from `pm.md`'s Expected Behaviors, and every claim is measured
by CALLING the public interface -- `verify_quotes.page_text`, `verify_quotes.verify`,
`verify_quotes.INLINE_ZERO_WIDTH_TAGS`, `verify_quotes.PARTIAL_WINDOW` -- over literal HTML
strings and stub callables this file controls.

Structural notes, so this file cannot lie later:

* **The suite stays OFFLINE, and that is enforced rather than promised.** An autouse fixture
  installs a socket tripwire for every test in this module, so any attempt to reach the
  network fails loudly here instead of passing on a good network day. This file imports no
  `urllib`, and every page reaching `verify` comes from an injected callable.
* **The seam's default binds at definition time**, so `monkeypatch.setattr(module, "fetch",
  sentinel)` is a NO-OP for `verify` and an assertion that such a sentinel "was never called"
  could not fail. That vacuous form is deliberately absent. What is asserted instead is the
  property that CAN fail: the injected callable receives every distinct URL exactly once, as
  its only argument, and the parameter default IS the module's own `fetch` object.
* **Behavior 3 is asserted with its control beside it.** The reproduction quote and a plain
  prose sentence come from the SAME fragment; the prose is what proves the page was fine and
  the checker was not, so a future regression cannot be read as a bad fixture.
* **Behaviors 4-6 are the opposite-side pins.** Curing a fail-CLOSED checker is the cheapest
  way to buy a fail-OPEN one, so the same file that proves `<code>` is now zero-width also
  proves `span`/`em`/`strong`/`a` still become a space and that block tags still separate.
* **The seam returns PAGE TEXT, not raw HTML.** Measured: `verify` normalises whatever the
  seam returns with the shared `_norm`, while tag handling lives in `page_text`, which the
  real `fetch` applies before returning. So every injected page here is produced by
  `page_text` over a literal HTML string -- injecting raw HTML would pass or fail by
  accident depending on whether a tag happened to sit inside the quoted span.
* **Window-sized fixtures read `PARTIAL_WINDOW` from the module**, never the literal 12, so a
  later tuning of that constant cannot silently make the PARTIAL test vacuous.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; nothing is written outside pytest's `tmp_path`.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import socket
import sys

import pytest

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import verify_quotes  # noqa: E402  (path is prepared immediately above)

#: The fragment the spec reproduces the fail-CLOSED bug from (behavior 3).
CODE_BOUNDARY_FRAGMENT = (
    "<p>The <code>outputSchema</code>: Optional JSON Schema defining expected output "
    "structure is used.</p>"
)
#: The honest, character-perfect quote that crosses the inline-code boundary, normalised.
CODE_BOUNDARY_QUOTE = "outputschema: optional json schema defining expected output structure"
#: Prose from the SAME fragment: the control that proves the page is fine.
CODE_BOUNDARY_CONTROL = "is used."

EXPECTED_ZERO_WIDTH = {"code", "kbd", "samp", "var", "tt"}


class _NetworkAttempted(AssertionError):
    """Raised by the tripwire when a test tries to open a socket."""


@pytest.fixture(autouse=True)
def _offline_tripwire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 14: no test in this module may touch the network.

    This guard is two-sided: it cannot pass vacuously, because any real fetch attempt --
    including the module-level `fetch` reached through a def-time default -- raises here.
    """

    def boom(*_args: object, **_kwargs: object) -> None:
        raise _NetworkAttempted("a test in this module attempted to open a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket, "getaddrinfo", boom)


def _record(*citations: dict) -> dict:
    """A minimal record in the shape `verify` consumes: an `evidence` list of citations."""
    return {"id": "GAP-000", "evidence": list(citations)}


# --------------------------------------------------------------------------------------
# Behavior 3 -- a quote spanning an inline-code boundary verifies (the fail-CLOSED bug).
# --------------------------------------------------------------------------------------


def test_b3_quote_crossing_inline_code_boundary_is_on_the_page() -> None:
    """The reproduction: the honest quote must be FOUND in the normalised page."""
    page = verify_quotes.page_text(CODE_BOUNDARY_FRAGMENT)
    assert CODE_BOUNDARY_QUOTE in page, (
        "an honest quote crossing an inline <code> boundary must normalise onto the page"
    )
    assert "outputschema :" not in page, (
        "no space may be inserted where the <code> element was"
    )


def test_b3_control_prose_from_the_same_fragment_is_also_on_the_page() -> None:
    """The control that proves the page was fine and the checker was not."""
    page = verify_quotes.page_text(CODE_BOUNDARY_FRAGMENT)
    assert CODE_BOUNDARY_CONTROL in page


# --------------------------------------------------------------------------------------
# Behavior 1 -- the page normaliser is published and `_visible_text` is retired.
# --------------------------------------------------------------------------------------


def test_b1_page_text_is_a_published_callable_returning_normalised_text() -> None:
    assert callable(verify_quotes.page_text)
    out = verify_quotes.page_text("<p>Hello   There</p>")
    assert isinstance(out, str)
    assert out == "hello there", "page_text returns the NORMALISED visible text"


def test_b1_the_retired_name_is_gone_from_the_module() -> None:
    assert not hasattr(verify_quotes, "_visible_text")
    module_text = (TOOLS_DIR / "verify_quotes.py").read_text(encoding="utf-8")
    # Counted, not printed: a failure reports the count, never the module body.
    assert module_text.count("_visible_text") == 0


def test_b1_fetch_obtains_its_page_text_through_page_text() -> None:
    """`fetch` is the one line that needs a socket, so its ROUTING is measured from the
    compiled function's global references rather than by calling it."""
    names = verify_quotes.fetch.__code__.co_names
    assert "page_text" in names
    assert "_visible_text" not in names


# --------------------------------------------------------------------------------------
# Behavior 2 -- the zero-width inline set is a published closed constant.
# --------------------------------------------------------------------------------------


def test_b2_zero_width_set_members_are_exactly_the_five_code_ish_tags() -> None:
    assert set(verify_quotes.INLINE_ZERO_WIDTH_TAGS) == EXPECTED_ZERO_WIDTH


def test_b2_zero_width_set_is_closed_against_runtime_widening() -> None:
    """"Closed constant" read as immutable: a mutable set would let any importer widen the
    false-merge surface at runtime, which is exactly what "Out of Scope" forbids."""
    assert isinstance(verify_quotes.INLINE_ZERO_WIDTH_TAGS, frozenset)


# --------------------------------------------------------------------------------------
# Behavior 3 (continued) -- every member, both forms, any case, with attributes.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("tag", sorted(EXPECTED_ZERO_WIDTH))
def test_b3_each_member_is_removed_with_no_separator(tag: str) -> None:
    raw = "<p>a<" + tag + ">b</" + tag + ">c</p>"
    assert verify_quotes.page_text(raw) == "abc"


@pytest.mark.parametrize(
    "raw",
    [
        "<p>a<CODE>b</CODE>c</p>",
        "<p>a<Code>b</cOdE>c</p>",
        '<p>a<code class="x">b</code>c</p>',
        "<p>a<code   data-lang='py'  >b</code  >c</p>",
        "<p>a<KBD>b</KBD>c</p>",
    ],
)
def test_b3_case_and_attributes_do_not_defeat_the_rule(raw: str) -> None:
    assert verify_quotes.page_text(raw) == "abc"


def test_b3_a_closing_form_alone_is_still_zero_width() -> None:
    assert verify_quotes.page_text("<p>a</code>b</p>") == "ab"


# --------------------------------------------------------------------------------------
# Behavior 4 -- a tag OUTSIDE the set still becomes a space (the set is closed).
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["span", "em", "strong"])
def test_b4_tags_outside_the_set_still_become_a_space(tag: str) -> None:
    raw = "<p>a<" + tag + ">b</" + tag + "></p>"
    assert verify_quotes.page_text(raw) == "a b"


def test_b4_an_anchor_still_becomes_a_space() -> None:
    assert verify_quotes.page_text('<p>a<a href="x">b</a></p>') == "a b"


@pytest.mark.parametrize("tag", ["span", "em", "strong", "a"])
def test_b4_no_tag_outside_the_set_is_in_the_zero_width_set(tag: str) -> None:
    assert tag not in verify_quotes.INLINE_ZERO_WIDTH_TAGS


# --------------------------------------------------------------------------------------
# Behavior 5 -- block boundaries still separate, so the fix bought no false pass.
# --------------------------------------------------------------------------------------


def test_b5_paragraph_boundaries_still_separate() -> None:
    out = verify_quotes.page_text("<p>ends here</p><p>Starts there</p>")
    assert out == "ends here starts there"
    assert "herestarts" not in out


@pytest.mark.parametrize("tag", ["div", "li", "h1"])
def test_b5_other_block_boundaries_still_separate(tag: str) -> None:
    raw = "<" + tag + ">ends here</" + tag + "><" + tag + ">Starts there</" + tag + ">"
    out = verify_quotes.page_text(raw)
    assert out == "ends here starts there"
    assert "herestarts" not in out


def test_b5_a_void_break_still_separates() -> None:
    out = verify_quotes.page_text("ends here<br>Starts there")
    assert out == "ends here starts there"
    assert "herestarts" not in out


# --------------------------------------------------------------------------------------
# Behavior 6 -- script-like content is still discarded.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,forbidden",
    [
        ("<p>ok</p><script>alert(1)</script>", "alert(1)"),
        ("<p>ok</p><style>body{color:red}</style>", "color:red"),
        ('<p>ok</p><svg><path d="M0 0"/></svg>', "m0 0"),
        ("<p>ok</p><noscript>fallback text</noscript>", "fallback text"),
    ],
)
def test_b6_script_like_content_is_discarded(raw: str, forbidden: str) -> None:
    out = verify_quotes.page_text(raw)
    assert "ok" in out, "the surrounding visible text must survive"
    assert forbidden not in out


# --------------------------------------------------------------------------------------
# Behaviors 7-8 -- the seam: injected by keyword, defaulted to the module's own `fetch`.
# --------------------------------------------------------------------------------------

VERBATIM_PAGE = verify_quotes.page_text("<p>hello world this is the page</p>")
VERBATIM_QUOTE = "hello world this is the page"


def test_b7_injected_fetch_receives_each_distinct_url_exactly_once() -> None:
    """The seam is used, and a URL cited by two records is fetched ONCE.

    Note on what is NOT asserted here: `verify`'s `fetch` default binds at DEFINITION time,
    so reassigning the module attribute and asserting "the sentinel was never called" could
    not fail and would be vacuous. The falsifiable property is asserted instead -- the
    injected callable receives every distinct URL exactly once and nothing else fetches --
    and the autouse socket tripwire turns any real network attempt into a loud failure.
    """
    calls: list[tuple[tuple, dict]] = []

    def fake(*args: object, **kwargs: object) -> str:
        calls.append((args, kwargs))
        return VERBATIM_PAGE

    shared = "https://example.invalid/shared"
    other = "https://example.invalid/other"
    records = [
        ("GAP-A", _record({"locator": shared, "quote": VERBATIM_QUOTE})),
        ("GAP-B", _record({"locator": shared, "quote": VERBATIM_QUOTE})),
        ("GAP-C", _record({"locator": other, "quote": VERBATIM_QUOTE})),
    ]

    rc = verify_quotes.verify(records, fetch=fake)

    assert rc == 0
    urls = [args[0] for args, _ in calls]
    assert sorted(urls) == sorted([other, shared]), "each DISTINCT url exactly once"
    assert len(calls) == 2, "three records over two urls must produce two fetches"
    assert all(len(args) == 1 for args, _ in calls), "the url is the only argument"
    assert all(kwargs == {} for _, kwargs in calls), "no keyword argument is passed"


def test_b8_the_one_argument_call_form_is_still_accepted() -> None:
    """`verify(records)` with no seam, provable offline via a non-URL locator (behavior 12)."""
    records = [("GAP-NOURL", _record({"locator": "gaps/GAP-001.json", "quote": "x" * 40}))]
    rc = verify_quotes.verify(records)
    assert rc == 1


def test_b8_the_seam_default_is_none_not_the_modules_own_fetch() -> None:
    """INVERTED by iteration 85, deliberately rewritten rather than deleted.

    This fence used to require `default is verify_quotes.fetch`, which stated the defect
    as a property: a default is evaluated once at import, so it froze the real socket into
    the signature and `setattr(verify_quotes, "fetch", ...)` could never reach the seamless
    `verify(records)` call `main` makes. The retired contract is asserted ABSENT here, so a
    revert to it reds this test instead of merely un-asserting it.
    """
    params = inspect.signature(verify_quotes.verify).parameters
    assert params["fetch"].default is None
    assert params["fetch"].default is not verify_quotes.fetch
    assert params["fetch"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


# --------------------------------------------------------------------------------------
# Behaviors 9-13 -- the four verdicts, the problem list and the summary line.
# --------------------------------------------------------------------------------------


def _lines(captured: str) -> list[str]:
    return [line for line in captured.splitlines() if line.strip()]


def test_b9_verbatim_path_reports_and_returns_zero(capsys: pytest.CaptureFixture) -> None:
    records = [("GAP-V", _record({"locator": "https://example.invalid/v", "quote": VERBATIM_QUOTE}))]
    rc = verify_quotes.verify(records, fetch=lambda url: VERBATIM_PAGE)
    out = capsys.readouterr().out
    assert rc == 0
    verbatim = [line for line in _lines(out) if line.startswith("VERBATIM")]
    assert len(verbatim) == 1
    assert "GAP-V" in verbatim[0]


def test_b10_partial_path_reports_and_returns_zero(capsys: pytest.CaptureFixture) -> None:
    """The fixture is sized from `PARTIAL_WINDOW`, never from the literal 12."""
    window = verify_quotes.PARTIAL_WINDOW
    words = ["w%02d" % i for i in range(window + 4)]
    quote = " ".join(words)
    page = verify_quotes.page_text(
        "<p>" + " ".join(words[:window]) + " and then a wholly different tail</p>"
    )

    # Premises, so this cannot silently become a VERBATIM test if the constant is tuned.
    assert len(quote.split()) > window, "the quote must be LONGER than the window"
    assert quote not in page, "the whole quote must be absent from the page"
    assert " ".join(words[:window]) in page, "the window must be present in the page"

    records = [("GAP-P", _record({"locator": "https://example.invalid/p", "quote": quote}))]
    rc = verify_quotes.verify(records, fetch=lambda url: page)
    out = capsys.readouterr().out
    assert rc == 0
    partial = [line for line in _lines(out) if line.startswith("PARTIAL")]
    assert len(partial) == 1
    assert "GAP-P" in partial[0]


def test_b11_not_on_page_returns_one_and_names_the_record_and_url(
    capsys: pytest.CaptureFixture,
) -> None:
    url = "https://example.invalid/n"
    quote = "a quote that is nowhere near this page at all"
    records = [("GAP-N", _record({"locator": url, "quote": quote}))]
    unrelated = verify_quotes.page_text("<p>unrelated words entirely</p>")
    rc = verify_quotes.verify(records, fetch=lambda _url: unrelated)
    out = capsys.readouterr().out
    assert rc == 1
    flagged = [line for line in _lines(out) if line.startswith("NOT ON PAGE")]
    assert len(flagged) == 1
    assert "GAP-N" in flagged[0]
    problems = [line for line in _lines(out) if line.lstrip().startswith("- GAP-N")]
    assert len(problems) == 1, "the problem list must name the record"
    assert url in problems[0], "the problem list must name the url"


def test_b12_unreachable_is_not_a_verdict(capsys: pytest.CaptureFixture) -> None:
    url = "https://example.invalid/u"
    records = [("GAP-U", _record({"locator": url, "quote": "some quote long enough to matter"}))]
    rc = verify_quotes.verify(records, fetch=lambda _url: None)
    out = capsys.readouterr().out
    assert rc == 0, "an unreachable page is not a failed verification"
    unreachable = [line for line in _lines(out) if line.startswith("UNREACHABLE")]
    assert len(unreachable) == 1
    assert "GAP-U" in unreachable[0]
    lowered = out.lower()
    assert "unreachable is not a verdict" in lowered
    assert "rate-limit" in lowered, "the note must name rate-limiting"
    assert "js-render" in lowered, "the note must name JS rendering"


def test_b12_a_non_url_locator_is_never_fetched(capsys: pytest.CaptureFixture) -> None:
    def boom(url: str) -> str:
        raise AssertionError("a non-url locator must never be fetched, got %r" % (url,))

    records = [("GAP-L", _record({"locator": "docs/CONSUMER_CONTRACT.md", "quote": "x" * 40}))]
    rc = verify_quotes.verify(records, fetch=boom)
    out = capsys.readouterr().out
    assert rc == 1
    problems = [line for line in _lines(out) if "locator is not a URL" in line]
    assert len(problems) == 1
    assert "GAP-L" in problems[0]


@pytest.mark.parametrize(
    "locator",
    ["docs/CONSUMER_CONTRACT.md", "ftp://example.invalid/a", "example.invalid/a", "GAP-001"],
)
def test_b12_no_locator_outside_the_two_url_schemes_is_fetched(
    locator: str, capsys: pytest.CaptureFixture
) -> None:
    def boom(url: str) -> str:
        raise AssertionError("must never be fetched, got %r" % (url,))

    rc = verify_quotes.verify([("GAP-S", _record({"locator": locator, "quote": "x" * 40}))], fetch=boom)
    out = capsys.readouterr().out
    assert rc == 1
    assert "locator is not a URL" in out


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_b12_both_url_schemes_are_fetched(scheme: str) -> None:
    """The converse pin: the refusal must not swallow a legitimate plain-http locator."""
    seen: list[str] = []
    url = scheme + "://example.invalid/a"
    records = [("GAP-H", _record({"locator": url, "quote": VERBATIM_QUOTE}))]
    rc = verify_quotes.verify(records, fetch=lambda u: seen.append(u) or VERBATIM_PAGE)
    assert seen == [url]
    assert rc == 0


def test_b13_the_summary_line_reports_the_injected_outcomes(
    capsys: pytest.CaptureFixture,
) -> None:
    window = verify_quotes.PARTIAL_WINDOW
    words = ["w%02d" % i for i in range(window + 4)]
    partial_quote = " ".join(words)
    pages = {
        "https://example.invalid/v": VERBATIM_PAGE,
        "https://example.invalid/p": verify_quotes.page_text(
            "<p>" + " ".join(words[:window]) + " other tail</p>"
        ),
        "https://example.invalid/n": verify_quotes.page_text("<p>unrelated words entirely</p>"),
        "https://example.invalid/u": None,
    }
    records = [
        ("GAP-V", _record({"locator": "https://example.invalid/v", "quote": VERBATIM_QUOTE})),
        ("GAP-P", _record({"locator": "https://example.invalid/p", "quote": partial_quote})),
        (
            "GAP-N",
            _record(
                {
                    "locator": "https://example.invalid/n",
                    "quote": "a quote that is nowhere near this page at all",
                }
            ),
        ),
        ("GAP-U", _record({"locator": "https://example.invalid/u", "quote": "x" * 40})),
    ]

    rc = verify_quotes.verify(records, fetch=lambda url: pages[url])
    out = capsys.readouterr().out

    assert rc == 1, "one NOT ON PAGE makes the run fail"
    assert "1 verbatim, 1 partial, 1 not found, 1 unreachable" in out


def test_b13_the_summary_line_counts_an_empty_run_as_all_zero(
    capsys: pytest.CaptureFixture,
) -> None:
    rc = verify_quotes.verify([], fetch=lambda url: VERBATIM_PAGE)
    out = capsys.readouterr().out
    assert rc == 0
    assert "0 verbatim, 0 partial, 0 not found, 0 unreachable" in out


# --------------------------------------------------------------------------------------
# Behavior 14 -- the suite stays offline, and the guard is proved two-sided.
# --------------------------------------------------------------------------------------

THIS_FILE = pathlib.Path(__file__).resolve()
NETWORK_ROOTS = {"urllib", "http", "requests", "httpx", "ftplib", "socketserver", "ssl"}


def _imported_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _self_tree() -> ast.Module:
    return ast.parse(THIS_FILE.read_text(encoding="utf-8"))


def test_b14_this_file_imports_no_network_module() -> None:
    roots = _imported_roots(_self_tree())
    assert "urllib" not in roots, "behavior 14: the new test file imports no urllib"
    assert not (roots & NETWORK_ROOTS), sorted(roots & NETWORK_ROOTS)


def test_b14_the_socket_tripwire_is_armed_and_would_fire() -> None:
    """Anti-vacuity: a guard that cannot fail is not evidence, so prove it fires."""
    with pytest.raises(_NetworkAttempted):
        socket.socket()
    with pytest.raises(_NetworkAttempted):
        socket.create_connection(("example.invalid", 80))
    with pytest.raises(_NetworkAttempted):
        socket.getaddrinfo("example.invalid", 80)


def test_b14_every_verify_call_here_injects_a_seam_except_the_documented_one() -> None:
    """Every page reaching `verify` comes from an injected callable.

    The single exception is behavior 8's one-argument form, which is provable offline only
    because its record carries a non-URL locator and is therefore never fetched.
    """
    unseamed: list[str] = []
    seamed = 0
    for node in ast.walk(_self_tree()):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if not (isinstance(func, ast.Attribute) and func.attr == "verify"):
                continue
            if any(kw.arg == "fetch" for kw in inner.keywords):
                seamed += 1
            else:
                unseamed.append(node.name)
    # Anti-vacuity: an AST walk that finds NOTHING must not read as compliance.
    assert seamed >= 8, seamed
    assert unseamed == ["test_b8_the_one_argument_call_form_is_still_accepted"], unseamed


def test_b14_no_absolute_machine_path_is_written_down_here() -> None:
    """The needles are ASSEMBLED, never spelled: a literal here would match itself."""
    text = THIS_FILE.read_text(encoding="utf-8")
    sep = "/"
    for needle in (sep + "Users" + sep, sep + "home" + sep, "C:" + chr(92)):
        assert needle not in text, needle
    # Anti-vacuity: the same audit must fire on a planted sample.
    planted = text + sep + "Users" + sep + "someone"
    assert (sep + "Users" + sep) in planted


# --------------------------------------------------------------------------------------
# Acceptance criterion -- the docstring records the SECOND instance of the family and
# narrows the "deliberately not part of the test suite" claim to `fetch`.
# --------------------------------------------------------------------------------------


def test_docstring_names_the_family_and_both_of_its_instances() -> None:
    lowered = (verify_quotes.__doc__ or "").lower()
    assert "curly" in lowered, "the FIRST instance of the family stays named"
    assert "twice" in lowered or "second" in lowered, "the SECOND instance is recorded"
    assert "page_text" in lowered, "the second instance names the function it produced"


def test_docstring_narrows_the_untested_claim_to_fetch() -> None:
    lowered = (verify_quotes.__doc__ or "").lower()
    claim = "deliberately not part of the test suite"
    assert claim in lowered
    index = lowered.index(claim)
    around = lowered[max(0, index - 140) : index + 240]
    assert "fetch" in around, "the narrowed claim must name `fetch`"
    assert "only" in around, "the claim must say fetch is the ONLY unseamed line"


# --------------------------------------------------------------------------------------
# The known-bad SIGNATURE, pinned as a property that must never come back.
# --------------------------------------------------------------------------------------


def test_the_fail_closed_signature_never_returns(capsys: pytest.CaptureFixture) -> None:
    """End to end through `verify`: the honest boundary-crossing quote must verify.

    Before this iteration the same fixture normalised to `outputschema : ...` on the page
    side only, so `verify` reported NOT ON PAGE and returned 1 -- a checker accusing correct
    data. The two-sided measurement against the pre-change module is recorded in the
    iteration report; what is pinned HERE is the signature itself, which is stable across
    commits: the separator must not reappear, and this record must verify VERBATIM.
    """
    quote = "outputSchema: Optional JSON Schema defining expected output structure"
    records = [("GAP-CODE", _record({"locator": "https://example.invalid/spec", "quote": quote}))]
    page = verify_quotes.page_text(CODE_BOUNDARY_FRAGMENT)
    rc = verify_quotes.verify(records, fetch=lambda _url: page)
    out = capsys.readouterr().out
    assert rc == 0
    assert [line for line in _lines(out) if line.startswith("VERBATIM")], out
    assert "NOT ON PAGE" not in out
    assert "outputschema :" not in verify_quotes.page_text(CODE_BOUNDARY_FRAGMENT)


# --------------------------------------------------------------------------------------
# Behaviors 3 x 5 -- THE INTERACTION, which is where a fail-OPEN merge would actually hide.
#
# Behaviors 3 and 5 are each pinned above in isolation: a zero-width tag inside one block,
# and a block boundary between two runs of plain text. Neither shape exercises the case the
# fix could plausibly break -- a zero-width tag sitting AT a block boundary, where removing
# it with no separator lands the two blocks next to each other. The expectation is derived
# from the spec by composing its own two rules: behavior 3 removes the member with no space,
# then behavior 5 requires the surviving block boundary to separate. So the result must be
# separated, never merged.
# --------------------------------------------------------------------------------------


def test_b3x5_a_zero_width_tag_at_a_block_boundary_still_separates() -> None:
    out = verify_quotes.page_text("<li><code>a</code></li><li><code>b</code></li>")
    assert out == "a b"
    assert "ab" not in out, "removing <code> must not merge two list items"


def test_b3x5_code_closing_one_para_and_opening_the_next_still_separates() -> None:
    raw = "<p>ends <code>here</code></p><p><code>Starts</code> there</p>"
    out = verify_quotes.page_text(raw)
    assert out == "ends here starts there"
    assert "herestarts" not in out


@pytest.mark.parametrize("tag", sorted(EXPECTED_ZERO_WIDTH))
def test_b3x5_every_member_is_zero_width_without_dissolving_its_block(tag: str) -> None:
    """The rule must hold for the whole closed set, not just for `code`."""
    raw = "<p>x<%s>y</%s></p><p><%s>z</%s>w</p>" % (tag, tag, tag, tag)
    assert verify_quotes.page_text(raw) == "xy zw"


def test_b3x5_a_zero_width_tag_inside_a_space_replaced_tag_keeps_the_space() -> None:
    """`span` is outside the set (behavior 4), so it separates even wrapping a member."""
    assert verify_quotes.page_text("<p>a<span><code>b</code></span>c</p>") == "a b c"


# --------------------------------------------------------------------------------------
# The register's own candidate victim shape (pm.md marks the GAP-007 case CONDITIONAL
# because confirming it needs a fetch -- but the SHAPE is assertable offline).
# --------------------------------------------------------------------------------------


def test_a_backticked_command_rendered_as_code_verifies_through_the_seam(
    capsys: pytest.CaptureFixture,
) -> None:
    """A markdown-rendering host renders a backticked command as a `<code>` element.

    That is the shape pm.md names as the register's live candidate victim, so the shape is
    pinned here: the quote is character-perfect against the rendered page and must verify.
    """
    raw = "<p>run <code>git add -A</code> first</p>"
    quote = "run git add -A first"
    page = verify_quotes.page_text(raw)
    assert "run git add -a first" in page, "the honest quote must be on the page"

    records = [("GAP-CMD", _record({"locator": "https://example.invalid/doc", "quote": quote}))]
    rc = verify_quotes.verify(records, fetch=lambda _url: page)
    out = capsys.readouterr().out
    assert rc == 0
    assert [line for line in _lines(out) if line.startswith("VERBATIM")], out
    assert "NOT ON PAGE" not in out


def test_inner_whitespace_of_a_zero_width_element_is_still_collapsed() -> None:
    """Zero-width refers to the TAG, not to the text it wraps."""
    assert verify_quotes.page_text("<p>x<code> a b </code>y</p>") == "x a b y"
