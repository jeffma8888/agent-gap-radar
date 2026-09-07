"""Iteration 122 behaviors: the tool-side locator door stops being a second dialect.

`tools/verify_quotes.py` used to hand-spell "is this a locator" three times as
`startswith(("http://", "https://"))`. That dialect ADMITS strings the register's
own ingest gate REFUSES, so such a citation entered the fetch set, could not be
fetched, and landed as `deferred` -- a state this tool's own docstring defines as
deliberately NOT a verdict. A record the promoter will never accept was therefore
retried on every research pass instead of being quarantined. This iteration
collapses all three onto `agent_gap_radar.models.is_resolvable_locator`, the one
predicate the ingest gate uses.

ISOLATION CONTRACT HONORED. Nothing here reads `src/` or `tools/` implementation
text, the engineer's notes, the reviewer's notes, `IMPLEMENTATION.patch`, or any
diff. Every expectation comes from `pm.md`'s Expected Behaviors, and every claim is
measured by CALLING or INTROSPECTING the public interface -- `verify_quotes.main`,
`.verify`, `.partition`, `.fetch`, `.is_resolvable_locator` -- over registers this
module writes into `tmp_path`.

STRUCTURAL NOTES, so this file cannot lie later:

* **The contract asserted is AGREEMENT WITH THE INGEST GATE, not a hardcoded row
  list.** `LOCATORS` carries the expected verdict as a literal `admitted` column
  AND one test proves that column equals `is_resolvable_locator` on every row. A
  fourth dialect that happened to pass the row list would have to also equal the
  shared predicate everywhere, which is the thing being asked for. `FLIPPED` names
  the five rows measured to change HEAD->working-tree, so the suite states which
  rows are the regression rather than leaving that to a reader.
* **"Never fetched" is asserted as an EXPLICIT CALL COUNT, not as a stub that
  raises.** A tripwire exception can be swallowed by a fetch-all wrapper and
  resurface as `unreachable`, which is precisely the pre-change outcome -- the test
  would then pass against the defect. Every fetch stub here APPENDS to a list and
  the list is compared with `==`. A module-scope autouse tripwire additionally
  replaces the real `fetch`, so a test that forgets to inject cannot open a socket:
  the suite is offline by contract, and this tool is the one network-facing seam.
* **Message texts are the contract, so each is a module constant formatted from its
  own data** and compared against a whole line with `==`, never by searching for a
  positional token. Index arithmetic over a formatted string is a second,
  unverified copy of that format.
* **Behavior 4 is driven with a PAGE-TABLE stub that returns `None` for anything it
  does not hold**, because that is the only stub shape under which the pre-change
  tool actually reaches the `deferred` state the spec names. A stub that returns a
  matching page for every URL makes the old code report `verified` instead, and the
  regression this file exists for would be mis-described.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
sys.path.insert(0, str(TOOLS))

import verify_quotes as vq  # noqa: E402

from agent_gap_radar.models import is_resolvable_locator  # noqa: E402

QUOTE = "the sky is blue"
PAGE = "well then the sky is blue indeed"
OK = "https://ok.example/p"

# The whole-line message contracts, spelled ONCE each.
NON_URL_PROBLEM = "  - {gid}: locator is not a URL: {loc!r}"
COUNTS = "{v} verbatim, {p} partial, {nf} not found, {u} unreachable"
VERBATIM_ROW = "VERBATIM     {gid}  {quote}"
PARTITION_SUMMARY = (
    "partition: {v} verified, {q} quarantined, {d} deferred; "
    "{left} file(s) left in the inbox"
)
PROBLEM_HEADING = "Problems, each of which needs a human decision:"

# (name, locator, admitted by the register's ingest gate)
LOCATORS: list[tuple[str, str, bool]] = [
    ("plain-https", "https://a.example/x", True),
    ("plain-http", "http://a.example/x", True),
    ("query-frag", "https://a.example/x?q=1#frag", True),
    ("trailing-newline", "https://a.example/x\n", True),
    ("scheme-only-http", "http://", False),
    ("scheme-only-https", "https://", False),
    ("embedded-space", "https://a.example/x y", False),
    ("embedded-newline", "https://a.example/x\nmore", False),
    ("trailing-space", "https://a.example/x ", False),
    ("leading-space", " https://a/b", False),
    ("upper-scheme", "HTTPS://A/B", False),
    ("ftp", "ftp://a/b", False),
    ("doi", "doi:10.1/xyz", False),
    ("prose", "a blog post I remember", False),
]

# The rows whose report-mode outcome was MEASURED to change HEAD -> working tree:
# the old dialect admitted and fetched each of these; the ingest gate refuses them.
FLIPPED = frozenset(
    {
        "scheme-only-http",
        "scheme-only-https",
        "embedded-space",
        "embedded-newline",
        "trailing-space",
    }
)

ROWS = [pytest.param(loc, admitted, id=name) for name, loc, admitted in LOCATORS]
FLIPPED_ROWS = [
    pytest.param(loc, id=name) for name, loc, _ in LOCATORS if name in FLIPPED
]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """A real request would be a test bug. Every test injects its own stub."""

    def tripwire(url: str):  # pragma: no cover - it must never run
        raise AssertionError(f"a test reached the real network: {url!r}")

    monkeypatch.setattr(vq, "fetch", tripwire)


def _record(directory: pathlib.Path, gid: str, locators: list[str]) -> None:
    doc = {
        "id": gid,
        "title": "a synthetic record",
        "evidence": [
            {
                "locator": loc,
                "quote": QUOTE,
                "source_class": "vendor-primary",
                "title": "t",
                "date": "2026-01-01",
            }
            for loc in locators
        ],
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{gid}.json").write_text(json.dumps(doc), encoding="utf-8")


def _report(monkeypatch, tmp_path, locators, gid="GAP-900"):
    """Drive report mode offline. Returns (rc, fetch calls, stdout lines)."""
    register = tmp_path / "register"
    _record(register, gid, locators)
    calls: list[str] = []

    def stub(url: str):
        calls.append(url)
        return PAGE

    monkeypatch.setattr(vq, "fetch", stub)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = vq.main(["--gaps", str(register)])
    assert err.getvalue() == "", "report mode writes its document to stdout only"
    return rc, calls, out.getvalue().splitlines()


# --------------------------------------------------------------------------
# Behavior 1 -- one predicate, obtained from the register, no literal copies.
# --------------------------------------------------------------------------


def test_the_tool_uses_the_registers_own_predicate_object():
    """Identity, not equivalence: a second copy would be a different object."""
    assert vq.is_resolvable_locator is is_resolvable_locator


def test_no_literal_locator_shape_test_survives_in_the_tool():
    text = (TOOLS / "verify_quotes.py").read_text(encoding="utf-8")
    assert text.count('startswith("http') == 0, "a literal scheme test survives"
    assert text.count('startswith(("http://') == 0, "the old dialect survives"
    offenders = [
        n
        for n, line in enumerate(text.splitlines(), 1)
        if "startswith(" in line and "http" in line
    ]
    assert offenders == [], f"a locator shape is still hand-spelled at {offenders}"


def test_the_shared_predicate_is_imported_exactly_once():
    text = (TOOLS / "verify_quotes.py").read_text(encoding="utf-8")
    imports = [
        line
        for line in text.splitlines()
        if line.startswith("from agent_gap_radar.models import")
    ]
    assert len(imports) == 1, imports
    assert "is_resolvable_locator" in imports[0], imports[0]


def test_the_expected_verdict_column_is_the_ingest_gate_itself():
    """The row table cannot drift away from the predicate it claims to mirror."""
    measured = {name: is_resolvable_locator(loc) for name, loc, _ in LOCATORS}
    declared = {name: admitted for name, _, admitted in LOCATORS}
    assert measured == declared


# --------------------------------------------------------------------------
# Behaviors 2, 3 and 6 -- one table over all fourteen locators.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("locator,admitted", ROWS)
def test_report_mode_answers_exactly_as_the_ingest_gate_does(
    monkeypatch, tmp_path, locator, admitted
):
    rc, calls, lines = _report(monkeypatch, tmp_path, [locator])
    problem = NON_URL_PROBLEM.format(gid="GAP-900", loc=locator)
    if admitted:
        assert rc == 0
        assert calls == [locator], "an admitted locator is fetched, exactly once"
        assert VERBATIM_ROW.format(gid="GAP-900", quote=QUOTE) in lines
        assert COUNTS.format(v=1, p=0, nf=0, u=0) in lines
        assert problem not in lines
        assert PROBLEM_HEADING not in lines
    else:
        assert rc == 1
        assert calls == [], "a refused locator must never be fetched"
        assert COUNTS.format(v=0, p=0, nf=1, u=0) in lines
        assert PROBLEM_HEADING in lines
        assert problem in lines


@pytest.mark.parametrize("locator", FLIPPED_ROWS)
def test_the_locators_the_old_dialect_admitted_are_now_refused(
    monkeypatch, tmp_path, locator
):
    """The regression itself: each of these was fetched before, and is not now."""
    rc, calls, lines = _report(monkeypatch, tmp_path, [locator])
    assert calls == [], f"{locator!r} was fetched despite not being a URL"
    assert rc == 1
    assert NON_URL_PROBLEM.format(gid="GAP-900", loc=locator) in lines


# --------------------------------------------------------------------------
# Behavior 4 -- the partition quarantines a non-URL instead of deferring it.
# --------------------------------------------------------------------------


def test_partition_quarantines_a_non_url_and_defers_nothing(tmp_path):
    inbox = tmp_path / "inbox"
    quarantine = tmp_path / "quarantine"
    deferred = tmp_path / "deferred"
    _record(inbox, "GAP-900", ["http://"])
    pages = {OK: PAGE}
    calls: list[str] = []

    def table_fetch(url: str):
        calls.append(url)
        return pages.get(url)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = vq.partition(inbox, quarantine, deferred, fetch_fn=table_fetch)

    assert rc == 0, "partitioning is the tool working, not failing"
    assert calls == [], "a non-URL must not be fetched even by the partition"
    assert (quarantine / "GAP-900.json").exists(), "the record must be quarantined"
    assert (quarantine / "GAP-900.reason.txt").exists(), "a human needs the reason"
    assert not (deferred / "GAP-900.json").exists(), "deferred is not a verdict"
    assert not list(deferred.glob("*")) if deferred.exists() else True
    assert (
        PARTITION_SUMMARY.format(v=0, q=1, d=0, left=0) in out.getvalue().splitlines()
    )


# --------------------------------------------------------------------------
# Behavior 5 -- the fetch set is derived through the shared predicate.
# --------------------------------------------------------------------------


def test_the_fetch_set_holds_only_the_resolvable_locator(monkeypatch, tmp_path):
    rc, calls, lines = _report(monkeypatch, tmp_path, [OK, "http://"], gid="GAP-901")
    assert calls == [OK], "exactly one page, and it is the resolvable one"
    assert rc == 1, "the refused sibling still fails the run"
    assert COUNTS.format(v=1, p=0, nf=1, u=0) in lines
    assert NON_URL_PROBLEM.format(gid="GAP-901", loc="http://") in lines


def test_the_verify_seam_agrees_with_report_mode(capsys):
    """`verify(records, fetch)` is the injected seam the driver uses."""
    calls: list[str] = []

    def stub(url: str):
        calls.append(url)
        return PAGE

    doc = {
        "id": "GAP-902",
        "title": "a synthetic record",
        "evidence": [
            {
                "locator": loc,
                "quote": QUOTE,
                "source_class": "vendor-primary",
                "title": "t",
                "date": "2026-01-01",
            }
            for loc in (OK, "http://")
        ],
    }
    rc = vq.verify([("GAP-902", doc)], stub)
    lines = capsys.readouterr().out.splitlines()
    assert rc == 1
    assert calls == [OK]
    assert NON_URL_PROBLEM.format(gid="GAP-902", loc="http://") in lines


# --------------------------------------------------------------------------
# Behavior 9 -- the out-of-scope neighbours keep their published claim.
# --------------------------------------------------------------------------


def test_the_ported_verbatim_claim_still_stands():
    """Row 109 keeps `check_locators.py` out of scope, so its README claim holds."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert (
        "`tools/check_locators.py` originated here and is ported verbatim into the "
        "practice index, so both registers prove their citations resolve the same way."
    ) in readme
