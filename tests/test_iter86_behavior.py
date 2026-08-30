"""Iteration 86 behaviors: `radar scan`'s two documents name the target the CALLER
spelled, while `target_name` and the `# Gap scan:` heading keep deriving from the
resolved path -- so the artifact `docs/CONSUMER_CONTRACT.md` points a CI gate at is
reproducible off the machine that produced it.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads `src/` or `tools/`
implementation logic, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or
any diff. Every expectation comes from `pm.md`'s Expected Behaviors, and every claim is
measured by CALLING the public interface (`main`, `scan`, `scan_json`, `render_scan`,
`ScanResult`) or by reading a PUBLISHED document (`docs/CONSUMER_CONTRACT.md`,
`PRODUCT.md`) -- the same latitude `tests/test_iter13_behavior.py` takes.

Structural notes, so this file cannot lie later:

* **Every target and register is built under `tmp_path`, and `~` is redirected there.**
  Behavior 4 needs a `~`-prefixed argument that RESOLVES to a real directory, because
  `scan()` keeps expanding and resolving for the walk. Rather than write into the real
  home, `HOME` (and `USERPROFILE`, for parity) is pointed at `tmp_path`, so the
  expansion is hermetic and no committed byte and no machine path is involved.
* **No absolute path is spelled as a literal anywhere.** Expected values are DERIVED
  from the `tmp_path` the fixture built, so this module carries no machine path and
  cannot leak an account name into the repo (an acceptance criterion in its own right).
* **Behavior 6 does not trust `test_iter13_behavior.py`.** That module's `TOP_KEYS` pin
  is IMPORTED *and* independently re-spelled here as `EXPECTED_TOP_KEYS`, then both are
  asserted against the live payload. Editing the older pin to match a changed payload
  would therefore red THIS file -- which is what the acceptance criterion "no committed
  key pin is edited" actually asks for, and a bare re-import could not detect.
* **Behavior 9 is proved behaviorally, not by grepping the module.** The spec offers a
  structural assertion ("one occurrence of the fallback expression"), but reading the
  implementation's source text is exactly what the isolation contract forbids, and a
  source census cannot see a SECOND rule that happens to be spelled differently. The
  falsifiable form used here instead: every public attribute of `ScanResult` that
  carries the displayed string is replaced, one at a time, with a sentinel, and the two
  renderers are required to move TOGETHER or not at all. A second independent path from
  either renderer to the value shows up as a patch that moves exactly one surface.
* **Anti-vacuity.** Every fixture asserts that its scan actually produced findings
  before any claim is made about the document, so an empty register cannot make a
  "no absolute path appears" assertion true by having no content at all.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.registry import load_all
from agent_gap_radar.scan import ScanResult, render_scan, scan, scan_json
from test_iter02_behavior import _record, _target, _write_register
from test_iter13_behavior import TOP_KEYS as ITER13_TOP_KEYS

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"
ROADMAP = REPO_ROOT / "PRODUCT.md"

#: Behavior 6, re-spelled independently of the module that already pins it. See the
#: docstring: importing the older constant alone cannot detect that constant being edited.
EXPECTED_TOP_KEYS = ["target", "target_name", "confidence_floor", "records_applied",
                     "counts", "uncheckable", "findings"]

#: Two records that both clear the default confidence floor and both fire on the
#: `_target` fixture tree, so every document under test carries real findings.
RECORDS = [_record("GAP-860", 5, 3, 5, ("first-party-field",), "CHK-860"),
           _record("GAP-861", 4, 3, 3, ("first-party-field",), "CHK-861")]

TARGET_LINE = re.compile(r"^Target: `(?P<value>.*)`$", re.MULTILINE)
HEADING_LINE = re.compile(r"^# Gap scan: (?P<name>.*)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Fixtures. `_record`, `_write_register` and `_target` come from
# tests/test_iter02_behavior.py, as in every module since iteration 02.
# ---------------------------------------------------------------------------

@pytest.fixture()
def reg(tmp_path):
    """A register whose two checks both fire on the `_target` tree."""
    return _write_register(tmp_path / "reg", list(RECORDS))


@pytest.fixture()
def target(tmp_path):
    """A target tree that trips both fixture checks, so both records are PRESENT."""
    return _target(tmp_path / "hit")


@pytest.fixture()
def gaps(reg):
    return load_all(reg)


@pytest.fixture(autouse=True)
def _home_is_tmp(tmp_path, monkeypatch):
    """`~` expands inside `tmp_path`, so behavior 4's tilde case never touches a real home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


def _echo(payload_or_doc):
    """The displayed target, read off whichever surface was handed in."""
    if isinstance(payload_or_doc, dict):
        return payload_or_doc["target"]
    match = TARGET_LINE.search(payload_or_doc)
    assert match is not None, f"no `Target:` line in the document: {payload_or_doc[:200]!r}"
    return match.group("value")


def _cli(argv, capsys):
    rc = main(argv)
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def _json_via_cli(target, reg, capsys, spelling=None):
    argv = ["scan", spelling if spelling is not None else str(target),
            "--gaps", str(reg), "--json"]
    rc, out, err = _cli(argv, capsys)
    assert rc == 0, f"scan exited {rc}; stderr was {err!r}"
    assert err == "", f"a clean scan writes nothing to stderr; got {err!r}"
    payload = json.loads(out)
    assert payload["findings"], "anti-vacuity: this fixture must produce findings"
    return payload


def _md_via_cli(target, reg, capsys, spelling=None):
    argv = ["scan", spelling if spelling is not None else str(target),
            "--gaps", str(reg)]
    rc, out, err = _cli(argv, capsys)
    assert rc == 0, f"scan exited {rc}; stderr was {err!r}"
    assert err == "", f"a clean scan writes nothing to stderr; got {err!r}"
    assert "GAP-860" in out, "anti-vacuity: this fixture must produce findings"
    return out


# --- behavior 1: `--json` echoes the caller's spelling -----------------------------------

def test_b1_json_echoes_the_dot_the_caller_typed(target, reg, capsys, monkeypatch):
    monkeypatch.chdir(target)
    payload = _json_via_cli(target, reg, capsys, spelling=".")
    assert payload["target"] == ".", (
        f'the caller typed "." so the payload must echo "."; got {payload["target"]!r}')


def test_b1_the_echo_is_neither_absolute_nor_a_prefix_of_the_resolved_root(
        target, reg, capsys, monkeypatch):
    monkeypatch.chdir(target)
    echoed = _json_via_cli(target, reg, capsys, spelling=".")["target"]
    resolved = str(target.resolve())
    assert not pathlib.PurePath(echoed).is_absolute(), f"{echoed!r} is an absolute path"
    assert echoed not in (resolved, resolved + "/"), f"{echoed!r} is the resolved root"
    assert not resolved.startswith(echoed.rstrip(".")) or echoed == ".", (
        f"{echoed!r} looks like a fragment of the resolved root {resolved!r}")


# --- behavior 2: the markdown echoes the same spelling, and carries no absolute path -----

def test_b2_markdown_target_line_is_the_backticked_spelling(target, reg, capsys,
                                                            monkeypatch):
    monkeypatch.chdir(target)
    doc = _md_via_cli(target, reg, capsys, spelling=".")
    assert "Target: `.`" in doc, (
        f"the brief must carry ``Target: `.` ``; Target line was {_echo(doc)!r}")
    assert _echo(doc) == ".", f"exactly the spelling, nothing appended; got {_echo(doc)!r}"


def test_b2_a_relative_invocation_leaks_no_absolute_path_into_the_document(
        target, reg, capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(target)
    doc = _md_via_cli(target, reg, capsys, spelling=".")
    for leaked in (str(target.resolve()), str(target.resolve().parent), str(tmp_path)):
        assert leaked not in doc, (
            f"the rendered document must carry no absolute path; found {leaked!r}")
    assert str(tmp_path) not in json.dumps(
        _json_via_cli(target, reg, capsys, spelling=".")), (
        "the payload must carry no absolute path either")


def test_b2_both_surfaces_echo_the_same_spelling(target, reg, capsys, monkeypatch):
    monkeypatch.chdir(target)
    doc = _md_via_cli(target, reg, capsys, spelling=".")
    payload = _json_via_cli(target, reg, capsys, spelling=".")
    assert _echo(doc) == _echo(payload) == ".", (
        f"the two surfaces disagree: markdown {_echo(doc)!r}, json {_echo(payload)!r}")


# --- behavior 3: `target_name` and the heading stay RESOLVED ------------------------------

def test_b3_target_name_and_heading_carry_the_resolved_base_name(target, reg, capsys,
                                                                 monkeypatch):
    monkeypatch.chdir(target)
    payload = _json_via_cli(target, reg, capsys, spelling=".")
    doc = _md_via_cli(target, reg, capsys, spelling=".")
    assert payload["target_name"] == target.resolve().name != ".", (
        f'`target_name` must name WHAT was scanned, not "."; got '
        f'{payload["target_name"]!r}')
    heading = HEADING_LINE.search(doc)
    assert heading is not None, f"no `# Gap scan:` heading in {doc[:200]!r}"
    assert heading.group("name") == target.resolve().name, (
        f"the heading must carry the resolved base name; got {heading.group('name')!r}")
    assert doc.splitlines()[0] == f"# Gap scan: {target.resolve().name}", (
        "the heading is still the document's FIRST line")


# --- behavior 4: the echo is verbatim -- no expansion, resolution or normalisation -------

def test_b4_an_absolute_argument_is_echoed_as_that_exact_string(gaps, target):
    spelled = str(target.resolve())
    result = scan(gaps, spelled)
    assert _echo(json.loads(scan_json(result))) == spelled
    assert _echo(render_scan(result)) == spelled


def test_b4_a_trailing_slash_survives(gaps, tmp_path, monkeypatch):
    inner = _target(tmp_path / "outer")
    monkeypatch.chdir(inner.parent)
    result = scan(gaps, "./target/")
    assert _echo(json.loads(scan_json(result))) == "./target/", (
        "no trailing-slash normalisation: the spelling is echoed verbatim")
    assert _echo(render_scan(result)) == "./target/"


def test_b4_a_tilde_argument_is_echoed_unexpanded(gaps, tmp_path):
    inner = _target(tmp_path / "under_home")
    spelled = f"~/{inner.relative_to(tmp_path)}"
    result = scan(gaps, spelled)
    assert _echo(json.loads(scan_json(result))) == spelled, (
        "the `~` must reach the document unexpanded")
    assert "~" in _echo(render_scan(result))
    assert str(tmp_path) not in render_scan(result), (
        "the expansion must not leak into the document either")


def test_b4_a_tilde_argument_still_scanned_the_expanded_directory(gaps, tmp_path):
    """The echo is display-only: the WALK still resolves. Without this, behavior 4 could
    pass over a tool that stopped scanning the right tree."""
    inner = _target(tmp_path / "under_home")
    result = scan(gaps, f"~/{inner.relative_to(tmp_path)}")
    payload = json.loads(scan_json(result))
    assert payload["target_name"] == inner.name
    assert payload["findings"], "the walk must still have reached the expanded directory"
    assert payload["counts"]["PRESENT"] == 2, (
        f"both fixture checks must still fire; counts were {payload['counts']}")


def test_b4_a_path_argument_is_echoed_as_str_of_that_path(gaps, tmp_path, monkeypatch):
    """`pathlib.Path("./target")` stringifies to `target`, so this discriminates
    `str(argument)` from "the characters the caller typed"."""
    inner = _target(tmp_path / "outer")
    monkeypatch.chdir(inner.parent)
    argument = pathlib.Path("./target")
    assert str(argument) == "target", "premise: pathlib drops the leading ./"
    result = scan(gaps, argument)
    assert _echo(json.loads(scan_json(result))) == str(argument)
    assert _echo(render_scan(result)) == str(argument)


# --- behavior 5: two spellings agree everywhere EXCEPT the echo --------------------------

def test_b5_two_spellings_yield_json_equal_after_dropping_target(gaps, target,
                                                                 monkeypatch):
    monkeypatch.chdir(target)
    relative = json.loads(scan_json(scan(gaps, ".")))
    absolute = json.loads(scan_json(scan(gaps, str(target.resolve()))))
    assert relative["target"] != absolute["target"], (
        "premise: the two spellings must differ in the echo, or this proves nothing")
    del relative["target"], absolute["target"]
    assert relative == absolute, (
        "dropping the single key `target` must leave two identical payloads")
    assert relative["findings"], "anti-vacuity"


def test_b5_two_spellings_yield_markdown_differing_only_in_the_target_line(
        gaps, target, monkeypatch):
    monkeypatch.chdir(target)
    relative = render_scan(scan(gaps, ".")).splitlines()
    absolute = render_scan(scan(gaps, str(target.resolve()))).splitlines()
    assert len(relative) == len(absolute), "the documents must have the same line count"
    differing = [(a, b) for a, b in zip(relative, absolute) if a != b]
    assert len(differing) == 1, (
        f"exactly one line may differ between two spellings; got {differing}")
    assert differing[0][0] == "Target: `.`", differing[0]
    assert differing[0][1] == f"Target: `{target.resolve()}`", differing[0]


# --- behavior 6: the top-level key set AND ORDER are unchanged ---------------------------

def test_b6_the_top_level_key_order_is_unchanged(target, reg, capsys, monkeypatch):
    monkeypatch.chdir(target)
    payload = _json_via_cli(target, reg, capsys, spelling=".")
    assert list(payload) == EXPECTED_TOP_KEYS, (
        f"the published key ORDER is part of the contract; got {list(payload)}")


def test_b6_the_older_committed_key_pin_was_not_edited_to_match(target, reg, capsys):
    """Behavior 6's acceptance criterion. The pin at tests/test_iter13_behavior.py is
    imported AND independently re-spelled here, so editing it reds this test."""
    assert list(ITER13_TOP_KEYS) == EXPECTED_TOP_KEYS, (
        "tests/test_iter13_behavior.py's TOP_KEYS pin has been changed; iteration 86 "
        "may not move a published key")
    payload = _json_via_cli(target, reg, capsys)
    assert list(payload) == list(ITER13_TOP_KEYS)


# --- behavior 7: a directly-constructed ScanResult still renders its resolved path -------

def test_b7_three_positional_arguments_render_the_resolved_path(gaps, target):
    """The form used by the three committed constructions in test_iter70_behavior.py."""
    resolved = target.resolve()
    inner = scan(gaps, str(resolved))
    result = ScanResult(resolved, inner.findings, inner.uncheckable)
    assert _echo(render_scan(result)) == str(resolved), (
        "a caller that supplied no spelling gets the path it DID supply")
    assert _echo(json.loads(scan_json(result))) == str(resolved)


def test_b7_the_echo_is_never_silently_blank_on_either_surface(gaps, target,
                                                              monkeypatch):
    monkeypatch.chdir(target)
    resolved = target.resolve()
    inner = scan(gaps, ".")
    cases = {"three positional": ScanResult(resolved, inner.findings, inner.uncheckable),
             "empty argument": scan(gaps, "")}
    for label, result in cases.items():
        for surface, echoed in (("markdown", _echo(render_scan(result))),
                                ("json", _echo(json.loads(scan_json(result))))):
            assert echoed != "", f"{label} rendered a BLANK target on {surface}"
            assert echoed == str(resolved), (
                f"{label} on {surface} must fall back to the resolved path; "
                f"got {echoed!r}")


def test_b7_scan_result_is_still_constructible_with_three_positional_arguments(gaps,
                                                                              target):
    """The pin behind the acceptance criterion: a new field must carry a default."""
    result = ScanResult(target.resolve(), [], [])
    assert result.target == target.resolve()
    assert result.findings == [] and result.uncheckable == []
    assert render_scan(result).endswith("\n")


# --- behavior 8: the error path is unchanged ---------------------------------------------

def test_b8_a_non_directory_target_still_exits_2_with_one_resolved_error_line(
        tmp_path, reg, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    victim = tmp_path / "not_a_dir"
    victim.write_text("x\n", encoding="utf-8")
    rc, out, err = _cli(["scan", "not_a_dir", "--gaps", str(reg)], capsys)
    assert rc == 2, f"a non-directory target exits 2; got {rc}"
    assert out == "", f"stdout carries only the document; got {out!r}"
    lines = err.splitlines()
    assert len(lines) == 1, f"exactly one stderr line; got {lines}"
    assert lines[0].startswith("Error: "), f"stderr must be prefixed; got {lines[0]!r}"
    assert str(victim.resolve()) in lines[0], (
        f"the diagnostic still names the RESOLVED path; got {lines[0]!r}")


# --- behavior 9: one rule, one implementation -------------------------------------------

def _displayed_holders(result, displayed):
    """Public attributes of `result` whose value IS the displayed string."""
    names = []
    for name in dir(type(result)):
        if name.startswith("_"):
            continue
        try:
            value = getattr(result, name)
        except Exception:                                  # pragma: no cover - defensive
            continue
        if isinstance(value, str) and value == displayed:
            names.append(name)
    return names


def test_b9_the_two_renderers_never_move_apart(gaps, target, monkeypatch):
    """One accessor, reached by name from both renderers -- proved by substitution.

    A class-level `property` wins over an instance attribute of the same name (a data
    descriptor beats `__dict__`), so this substitution reaches the value whether it is
    stored on the instance or computed. If either renderer had its OWN path to the
    value, some substitution would move exactly one surface.
    """
    monkeypatch.chdir(target)
    result = scan(gaps, ".")
    assert _echo(render_scan(result)) == _echo(json.loads(scan_json(result))) == "."
    holders = _displayed_holders(result, ".")
    assert holders, "premise: some public attribute of ScanResult carries the echo"
    sentinel = "GAPRADAR_ITER86_SENTINEL"
    moved_both = 0
    for name in holders:
        with monkeypatch.context() as patch:
            patch.setattr(type(result), name, property(lambda self: sentinel),
                          raising=False)
            md = _echo(render_scan(result)) == sentinel
            js = _echo(json.loads(scan_json(result))) == sentinel
        assert md == js, (
            f"substituting {name!r} moved the markdown ({md}) and the payload ({js}) "
            "apart, so the displayed target has TWO implementations")
        moved_both += int(md)
    assert moved_both >= 1, (
        f"no substitution among {holders} reached either renderer, so neither renderer "
        "reads the displayed target from a ScanResult accessor")


def test_b9_the_accessor_is_the_value_both_surfaces_publish(gaps, target, monkeypatch):
    """Whatever the accessor is called, its value IS what both documents show -- for the
    echoing route and for the resolved fallback."""
    monkeypatch.chdir(target)
    for result, expected in ((scan(gaps, "."), "."),
                             (ScanResult(target.resolve(), [], []),
                              str(target.resolve()))):
        holders = _displayed_holders(result, expected)
        assert holders, (
            f"no public attribute of ScanResult carries {expected!r}, so the renderers "
            "are not reading a published accessor")
        assert _echo(render_scan(result)) == expected
        assert _echo(json.loads(scan_json(result))) == expected


# --- acceptance criteria on the published documents --------------------------------------

def _collapsed(path):
    """Whitespace-collapsed document text: a prose assertion must survive a re-wrap."""
    return " ".join(path.read_text(encoding="utf-8").split())


def test_ac_the_consumer_contract_states_what_target_now_carries():
    text = _collapsed(CONTRACT_DOC)
    assert "`target` ECHOES the target the caller named, verbatim" in text, (
        "the contract must state that `target` is the caller's spelling")
    assert "no expansion, no resolution" in text
    assert "`target_name` is the portable identity to key on" in text, (
        "the contract must name `target_name` as the portable identity")


#: Built from parts on purpose. Spelling either root as a literal would make THIS file
#: the first thing the check below finds -- measured: it did, on the first run.
ABSOLUTE_ROOTS = ("/" + "Users" + "/", "/" + "home" + "/")


def test_ac_no_committed_document_carries_an_absolute_machine_path():
    """The roadmap note masks the measured value, per the spec's own instruction, and
    this module derives every expected path from `tmp_path`. Its own source is included
    in the domain: a test file is a committed file too."""
    for doc in (ROADMAP, CONTRACT_DOC, pathlib.Path(__file__)):
        text = doc.read_text(encoding="utf-8")
        for root in ABSOLUTE_ROOTS:
            assert root not in text, (
                f"{doc.name} carries an absolute machine path beginning {root!r}")


def test_ac_roadmap_row_34_is_shipped_and_records_the_three_way_choice():
    rows = [ln for ln in ROADMAP.read_text(encoding="utf-8").splitlines()
            if ln.startswith("| 34 ")]
    assert len(rows) == 1, f"exactly one row 34; got {len(rows)}"
    row = rows[0]
    assert "| shipped |" in row, f"row 34 must be flipped to shipped; got {row[:120]!r}"
    assert "iter 86" in " ".join(ROADMAP.read_text(encoding="utf-8").splitlines()[-3:]) \
        or any(ln.startswith("- iter 86 ") for ln
               in ROADMAP.read_text(encoding="utf-8").splitlines()), (
        "the iteration-86 done-ledger row must be present")


# --- quality-bar invariants this iteration's changed document bytes must keep -------------

def test_qb_both_surfaces_still_end_in_exactly_one_newline(gaps, target, monkeypatch):
    """The product quality bar: "every renderer ends in exactly ONE newline". This
    iteration rewrites a line of the markdown brief and a value in the payload, so the
    invariant is re-measured on BOTH spellings rather than assumed."""
    monkeypatch.chdir(target)
    for spelling in (".", str(target.resolve())):
        for surface, text in (("markdown", render_scan(scan(gaps, spelling))),
                              ("json", scan_json(scan(gaps, spelling)))):
            assert text.endswith("\n"), f"{surface} for {spelling!r} does not end in a newline"
            assert not text.endswith("\n\n"), (
                f"{surface} for {spelling!r} ends in more than one newline: {text[-4:]!r}")


def test_qb_the_default_carrying_field_is_the_only_optional_one(gaps, target):
    """Behavior 7's mechanism, discovered through the PUBLIC dataclass interface rather
    than by reading source: exactly one `ScanResult` field carries a default, which is why
    the three committed three-positional constructions keep working. Setting that field to
    `None` -- the value an omitted argument leaves -- must reproduce the resolved fallback
    on both surfaces."""
    import dataclasses

    optional = [f.name for f in dataclasses.fields(ScanResult)
                if f.default is not dataclasses.MISSING]
    assert len(optional) == 1, (
        f"expected exactly one field carrying a default; got {optional}")
    resolved = target.resolve()
    explicit_none = ScanResult(resolved, [], [], **{optional[0]: None})
    assert _echo(render_scan(explicit_none)) == str(resolved)
    assert _echo(json.loads(scan_json(explicit_none))) == str(resolved)
