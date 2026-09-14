"""Iteration 217 -- an unreadable register directory REFUSES instead of publishing
zero records.

`registry.load_all` enumerated with a `glob`, and `pathlib` swallows a
DIRECTORY-level `OSError`, so N unreadable records behind a mode-`0o000` directory
read as a genuinely empty register: four verbs published a zero-record document at
exit 0 and three refused for a reason that was actively false (blaming emptiness,
the evidence, or the requested id).  That violates the one rule the product names as
the rule it protects -- records are DISPLAYED, never silently dropped -- at maximum
scale, and it is the machine payload (`list --json` emitting an all-zero census at
exit 0) that a release gate cannot distinguish from health.

Black-box: every behaviour is observed through the public interface (`cli.main(argv)`
for the verbs, `registry.load_all` for the one unit fact the spec states in those
terms), asserting on the observable stdout/stderr/exit code.  Offline, deterministic,
`tmp_path` only -- the live `gaps/` directory is never read and never written.

Permission-fixture rule (from the spec's fixture notes): every blocked directory
PROBES that the mode is actually effective (one `iterdir()`; `pytest.skip` when it
succeeds, i.e. running as root or on a filesystem that ignores the mode) and RESTORES
a readable mode in teardown, so no test can leave an unremovable temp tree.

TWO SPEC DEFECTS ARE PINNED HERE AS MEASURED, NOT AS WRITTEN (see tester.md):
  * Behaviour 8 asserts `radar list <empty>` writes ZERO stdout bytes.  It writes
    exactly ONE byte, `"\n"`, at exit 0 -- the empty document's single trailing
    newline, which the quality bar REQUIRES of every renderer.  Zero bytes would
    itself be a violation, so the measured byte is the correct control and it is
    asserted as `"\n"` with a comment, never silently loosened.
  * Behaviour 2 spells the invocation `radar show <blocked> GAP-001`.  `show`'s
    positionals are `<gap_id> [<path>]`, so that literal form refuses with
    `Error: not a directory: GAP-001` and never reaches the register.  Both are
    pinned: the ordering that EXERCISES the behaviour, and the literal spec form
    with the argument-order refusal it actually produces.

The behaviour-7 equivalence bytes are PINNED CONSTANTS below (sha256 + length +,
for the two short documents, the verbatim text), captured from a run of the
PRE-CHANGE implementation at HEAD `e718714` extracted with `git archive` -- they are
not re-rendered from the working tree, so a rendering regression cannot re-baseline
itself.  Verified byte-identical between pre-change and post-change for all six
verbs before being written here.

RE-BASELINED BY ITERATION 221 for `prd` ONLY, and by SUBTRACTION rather than by
re-capture: that iteration APPENDS `sourceGap.check.closure` and one US-002
acceptance criterion, so the document legitimately GREW and the six-verb identity
above now holds for five of them verbatim and for `prd` once those two fragments are
removed.  The pinned constants stay exactly as captured at `e718714` -- the
historical witness is never re-rendered from the working tree.  See
`_without_iteration_221_appends`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from agent_gap_radar import registry
from agent_gap_radar.cli import build_parser, main

from _appended_fragment import appended_item_fragment, appended_key_fragment

REPO = pathlib.Path(__file__).resolve().parent.parent

#: Minimal record satisfying the shipped schema.  Two copies make every register in
#: this module non-empty, so any zero-record answer can only come from the block.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"], "build_hypothesis": "build a small wrapper",
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}

#: The three sentences the new refusal may never substitute itself for.  Each blames
#: the register's CONTENTS for a failure that belongs to the directory (spec b4).
FALSE_ATTRIBUTIONS = ("no gap records found", "no gap clears the confidence floor",
                      "no such gap")

#: Pre-change stdout, pinned (sha256, byte length).  Register path never appears in
#: any of these documents -- verified -- so a tmp_path fixture reproduces them exactly.
PINNED = {
    "validate": ("d6e83d9e896de68050e94f8245dd7ae2a4fb94797480ddb396bbd6f9083bbf5e", 27),
    "list": ("ec9a0774697712a4c0394c15fdac6023bc2ae3559c89b0cda21d012d74ae1a5e", 80),
    "listjson": ("93ce864da30c0073c8fbe574509721f1ebf9caa2bc61f6994e06de2318f8dd26", 742),
    "report": ("286cd5cf6fa473b79bb60e3c1b41152fa70ef2b5f3d7ab11a0fd82dead448d0c", 2716),
    "show": ("490b6d3c3bee7691e01b0b6b16d6bf4bafdcd21b8e508550233f5e663c59dc12", 952),
    "prd": ("807264bd1ed44276a5e77ea0233eb22f66bdd7617c2a8c98268c352141483b19", 2527),
}

#: The two short documents in full, so a digest mismatch is readable rather than opaque.
PINNED_VALIDATE_TEXT = "OK: 2 gap record(s) valid.\n"
PINNED_LIST_TEXT = ("GAP-001  p= 8.7  c=5  A thing is broken\n"
                    "GAP-002  p= 8.7  c=5  A thing is broken\n")

READABLE_VERBS = {
    "validate": lambda reg: ["validate", reg],
    "list": lambda reg: ["list", reg],
    "listjson": lambda reg: ["list", reg, "--json"],
    "report": lambda reg: ["report", reg],
    "show": lambda reg: ["show", "GAP-001", reg],
    "prd": lambda reg: ["prd", reg],
}


def _write_register(directory: pathlib.Path, count: int = 2) -> pathlib.Path:
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(1, count + 1):
        (directory / f"GAP-{i:03d}.json").write_text(
            json.dumps(dict(RECORD, id=f"GAP-{i:03d}")), encoding="utf-8")
    return directory


def _block(directory: pathlib.Path) -> None:
    """Set mode 0o000 and PROVE the block is effective, else skip."""
    directory.chmod(0o000)
    try:
        list(directory.iterdir())
    except OSError:
        return
    directory.chmod(0o755)
    pytest.skip("mode 0o000 does not block iterdir here (root, or a permissive fs)")


@pytest.fixture()
def blocked(tmp_path):
    """`<root>/gaps` holding two valid records, then made unreadable."""
    directory = _write_register(tmp_path / "repo" / "gaps")
    _block(directory)
    try:
        yield directory
    finally:
        directory.chmod(0o755)


@pytest.fixture()
def readable(tmp_path):
    return _write_register(tmp_path / "other" / "gaps")


def _expected(path: pathlib.Path) -> str:
    return f"Error: cannot read register directory: {path}"


def _run(argv, capsys):
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- b1
def test_b1_load_all_raises_registry_error_naming_the_path(blocked):
    """It does NOT return [], and it does NOT leak a bare OSError/PermissionError."""
    with pytest.raises(registry.RegistryError) as excinfo:
        registry.load_all(blocked)
    assert str(excinfo.value) == f"cannot read register directory: {blocked}"
    assert not isinstance(excinfo.value, OSError)


def test_b1_the_same_records_load_when_the_directory_is_readable(blocked):
    """Control for b1: the block is the ONLY reason, the records are valid."""
    blocked.chmod(0o755)
    assert [g.id for g in registry.load_all(blocked)] == ["GAP-001", "GAP-002"]


# ------------------------------------------------------------------------ b2-b4
#: Every register-reading door named by behaviour 2.  `scan` needs a target tree,
#: so it carries its own test below.
BLOCKED_INVOCATIONS = {
    "validate": lambda b, t: ["validate", b],
    "list": lambda b, t: ["list", b],
    "list --json": lambda b, t: ["list", b, "--json"],
    "report": lambda b, t: ["report", b],
    "show": lambda b, t: ["show", "GAP-001", b],
    "prd": lambda b, t: ["prd", b],
    "scan --gaps": lambda b, t: ["scan", t, "--gaps", b],
}


@pytest.fixture()
def target(tmp_path):
    tree = tmp_path / "target"
    tree.mkdir()
    (tree / "app.py").write_text("x = 1\n", encoding="utf-8")
    return tree


@pytest.mark.parametrize("name", sorted(BLOCKED_INVOCATIONS))
def test_b2_every_register_door_exits_2_with_zero_stdout(
        name, blocked, target, capsys):
    code, out, _ = _run(BLOCKED_INVOCATIONS[name](blocked, target), capsys)
    assert (code, out) == (2, ""), name


@pytest.mark.parametrize("name", sorted(BLOCKED_INVOCATIONS))
def test_b3_last_stderr_line_is_the_pinned_refusal(name, blocked, target, capsys):
    _, _, err = _run(BLOCKED_INVOCATIONS[name](blocked, target), capsys)
    assert err.strip().splitlines()[-1] == _expected(blocked), name


@pytest.mark.parametrize("name", sorted(BLOCKED_INVOCATIONS))
def test_b4_stderr_never_blames_emptiness_evidence_or_the_id(
        name, blocked, target, capsys):
    _, _, err = _run(BLOCKED_INVOCATIONS[name](blocked, target), capsys)
    assert not any(f in err for f in FALSE_ATTRIBUTIONS), (name, err)


def test_b2_spec_literal_show_argument_order_refuses_on_the_argument_shape(
        blocked, capsys):
    """The spec spells `show <blocked> GAP-001`; positionals are `<gap_id> [<path>]`.

    Pinned as MEASURED: that literal form never reaches the register, so it is the
    argument-order refusal (iteration 206's committed vocabulary working), not this
    iteration's guard.  The ordering that exercises the behaviour is covered above.
    """
    code, out, err = _run(["show", blocked, "GAP-001"], capsys)
    assert (code, out) == (2, "")
    assert err.strip().splitlines()[-1] == "Error: not a directory: GAP-001"


# --------------------------------------------------------------------------- b5
@pytest.mark.parametrize("blocked_side", ["old", "new"])
def test_b5_diff_refuses_from_either_side_naming_the_blocked_one(
        blocked, readable, capsys, blocked_side):
    """Neither ordering may read as "everything added" or "everything removed"."""
    argv = (["diff", blocked, readable] if blocked_side == "old"
            else ["diff", readable, blocked])
    code, out, err = _run(argv, capsys)
    assert (code, out) == (2, ""), blocked_side
    assert err.strip().splitlines()[-1] == _expected(blocked), blocked_side
    assert not any(f in err for f in FALSE_ATTRIBUTIONS)


def test_b5_diff_of_two_readable_registers_still_succeeds(readable, tmp_path, capsys):
    """Control for b5: the refusal is the block, not the verb."""
    other = _write_register(tmp_path / "third" / "gaps")
    code, out, _ = _run(["diff", readable, other], capsys)
    assert code == 0
    assert out.endswith("\n") and not out.endswith("\n\n")


# --------------------------------------------------------------------------- b6
def test_b6_a_repo_root_whose_gaps_subdir_is_blocked_names_the_subdir(
        blocked, capsys):
    """Path resolution still happens; the message names `<root>/gaps`, not the arg."""
    root = blocked.parent
    code, out, err = _run(["list", root], capsys)
    assert (code, out) == (2, "")
    assert err.strip().splitlines()[-1] == _expected(root / "gaps")
    assert err.strip().splitlines()[-1] != _expected(root)


# --------------------------------------------------------------------------- b7
def _without_iteration_221_appends(name: str, out: str) -> str:
    """`out` with iteration 221's two APPENDED `prd` fragments removed; other verbs as-is.

    RE-BASELINED BY ITERATION 221 on the terms iteration 92 set (see
    `test_iter68_behavior.test_b3_the_payload_is_byte_identical_to_the_pre_rename_document`):
    the iteration APPENDS `sourceGap.check.closure` and one US-002 acceptance criterion, so
    the document legitimately GREW and the behaviour it ships cannot be delivered without
    those bytes.  The honest update keeps the historical witness -- `PINNED["prd"]` remains
    the PRE-CHANGE sha256 and length captured at `e718714`, untouched -- and accounts for
    the growth as a MEASURED term, instead of re-capturing the digest from the working
    tree, which is the one move that would let a rendering regression re-baseline itself.

    Both fragments are DERIVED from the emitted document rather than pinned as fresh
    literals, because which arm the closure declaration takes is chosen by register DATA
    (whether the record carries a `check.mitigated_when` rule -- this module's `RECORD`
    carries no `check` at all, so it exercises the REFUSAL arm).  Nothing the pin refuses
    is surrendered: only these two fragments' own lengths may vary, each is asserted to
    occur EXACTLY once before it is removed -- a fragment reconstructed with the wrong
    indent, separators or value occurs ZERO times and reds -- and a third new key or a byte
    moved anywhere else still reds the digest below.  Removing exactly 244 + 141 bytes here
    reproduces the pinned 2527 and its sha256, which is simultaneously the proof that zero
    bytes moved OUTSIDE the appended region.
    """
    if name != "prd":
        return out
    doc = json.loads(out)
    story = doc["stories"][1]
    assert story["id"] == "US-002", (
        f'premise: iteration 221 appended its criterion to US-002, which is `stories[1]`; '
        f'found {story["id"]!r}')
    check = doc["sourceGap"]["check"]
    assert "closure" in check, (
        "premise: iteration 221 APPENDED `sourceGap.check.closure`. With the key gone the "
        "subtraction below is void, so the pin would compare the wrong two documents.")
    fragments = (
        ("closure", appended_key_fragment("closure", check, 6)),
        ("criterion", appended_item_fragment(story["acceptanceCriteria"][-1], 8)),
    )
    for label, fragment in fragments:
        assert out.count(fragment) == 1, (
            f"premise: iteration 221's appended {label} occurs exactly once in the emitted "
            f"bytes, so removing it recovers the pre-change document; found "
            f"{out.count(fragment)} for {fragment!r}")
        out = out.replace(fragment, "", 1)
    return out


@pytest.mark.parametrize("name", sorted(READABLE_VERBS))
def test_b7_readable_register_stdout_is_byte_identical_to_pre_change(
        name, readable, capsys):
    """Pinned pre-change bytes: zero rendered bytes may move on a readable register.

    Five verbs are compared verbatim; `prd` is compared with iteration 221's two APPENDED
    fragments subtracted, which is the same claim about every byte it did not append.
    """
    expected_sha, expected_len = PINNED[name]
    code, out, err = _run(READABLE_VERBS[name](readable), capsys)
    assert (code, err) == (0, ""), name
    pinned = _without_iteration_221_appends(name, out)
    assert len(pinned.encode("utf-8")) == expected_len, (name, out)
    assert hashlib.sha256(pinned.encode("utf-8")).hexdigest() == expected_sha, (name, out)


def test_b7_the_two_short_documents_match_verbatim(readable, capsys):
    """A digest mismatch above should be readable, so pin these in full too."""
    assert _run(["validate", readable], capsys)[1] == PINNED_VALIDATE_TEXT
    assert _run(["list", readable], capsys)[1] == PINNED_LIST_TEXT


@pytest.mark.parametrize("name", sorted(READABLE_VERBS))
def test_b7_every_document_ends_in_exactly_one_newline(name, readable, capsys):
    out = _run(READABLE_VERBS[name](readable), capsys)[1]
    assert out.endswith("\n"), name
    assert not out.endswith("\n\n"), name


# --------------------------------------------------------------------------- b8
def test_b8_a_genuinely_empty_readable_directory_is_untouched(tmp_path, capsys):
    """The new refusal is NOT reachable from a directory that is merely empty.

    MEASURED CORRECTION to the spec: behaviour 8 asserts ZERO stdout bytes for
    `list <empty>`; it emits exactly ONE, the empty document's required trailing
    newline.  The quality bar makes that byte mandatory, so it is pinned as `"\\n"`.
    """
    empty = tmp_path / "empty"
    empty.mkdir()

    code, out, err = _run(["list", empty], capsys)
    assert (code, err) == (0, "")
    assert out == "\n"

    code, out, err = _run(["validate", empty], capsys)
    assert (code, out) == (2, "")
    assert err.strip().splitlines()[-1] == f"Error: no gap records found in {empty}"
    assert "cannot read register directory" not in err


# --------------------------------------------------------------------------- b9
def test_b9_a_missing_path_keeps_the_missing_path_wording(tmp_path, capsys):
    missing = tmp_path / "does-not-exist"
    code, out, err = _run(["list", missing], capsys)
    assert (code, out) == (2, "")
    assert err.strip().splitlines()[-1] == f"Error: not a directory: {missing}"
    assert "cannot read register directory" not in err


# -------------------------------------------------------------------------- b10
def test_b10_per_file_unreadability_keeps_todays_per_file_text(tmp_path, capsys):
    """This iteration WIDENS the refusal and narrows nothing."""
    directory = _write_register(tmp_path / "perfile" / "gaps")
    records = sorted(directory.glob("*.json"))
    for path in records:
        path.chmod(0o000)
    try:
        records[0].read_text(encoding="utf-8")
    except OSError:
        pass
    else:
        for path in records:
            path.chmod(0o644)
        pytest.skip("mode 0o000 does not block read here (root, or a permissive fs)")
    try:
        code, out, err = _run(["validate", directory], capsys)
        assert (code, out) == (2, "")
        last = err.strip().splitlines()[-1]
        assert last.startswith("Error: ")
        assert "unreadable/invalid JSON" in last
        assert "GAP-001.json" in last and "GAP-002.json" in last
        assert "cannot read register directory" not in err
    finally:
        for path in records:
            path.chmod(0o644)


# -------------------------------------------------------------------------- b11
def test_b11_the_cli_surface_gained_no_verb_and_no_flag():
    """No `--allow-unreadable` escape hatch, no new verb."""
    text = build_parser().format_help()
    assert "allow-unreadable" not in text
    assert "unreadable" not in text
    #: The verb slate as published by `--help`, pinned so a new verb must be a
    #: deliberate edit here rather than a silent surface addition.
    verbs = {line.split()[0] for line in text.splitlines()
             if line.startswith("    ") and line.strip() and not line.startswith("     ")}
    assert verbs, text
    assert not any(v.startswith("unread") for v in verbs), verbs


def test_b11_the_consumer_contract_document_needs_no_edit():
    """The refusal is invisible to the stable-surface table: no document byte moved."""
    contract = REPO / "docs" / "CONSUMER_CONTRACT.md"
    text = contract.read_text(encoding="utf-8")
    assert "cannot read register directory" not in text
    assert "allow-unreadable" not in text
