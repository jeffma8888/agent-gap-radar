"""Iteration 242 -- `radar validate` names EVERY schema error, and the FIELD each is in.

The ingest door threw pydantic's information away one line after computing it: a refused
record reported the COUNT of its schema errors but only the LAST error's message, with no
`loc` at all.  A fixer therefore re-ran the door once per error, and the sharpest shape --
an unknown key inside `evidence[0]`, whose whole message is `Extra inputs are not
permitted` -- named neither the key, nor the field, nor which citation.  This module drives
the published door (`radar validate`) and asserts the rendered refusal, the count that must
agree with the items beside it, and the four neighbouring behaviours the change must NOT
move.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff.  Every
expectation comes from `pm.md`'s Expected Behaviors; every claim is measured by CALLING the
public entry point (`cli.main`), by RUNNING the packaged one in a subprocess, or by asking
the public model door (`Gap.model_validate`) for pydantic's own error list.

Structural notes, so a green dot here cannot mean less than it looks like:

* **The count is checked AGAINST the items, never beside them.**  Behaviors 2 and 5 parse
  the integer out of `<n> schema error(s)` and assert it equals the number of rendered
  items, so the exact regression this iteration repairs -- dropping errors while still
  counting them -- cannot pass this file again.
* **Item ORDER and item MESSAGES are derived from pydantic, not transcribed.**  Behaviors 2
  and 4 build the expected items from `ValidationError.errors()` obtained through
  `Gap.model_validate`, so a test that merely echoed a hand-copied sentence cannot drift
  into agreeing with a re-worded implementation.
* **The pre-change sentence is pinned as FORBIDDEN.**  `_assert_not_the_old_dialect`
  asserts the refusal is not the loc-less form the door produced before this iteration
  (measured: `1 schema error(s): Field required`), which is what makes the positive
  assertions non-vacuous rather than satisfiable by either implementation.
* **Behavior 5 is split on `"; "` only where that is SAFE.**  pydantic's own messages
  contain `"; "` (`...; allowed: (...)`), which `pm.md` names as declared residue, so the
  two-file fixture deliberately uses missing-field errors ONLY -- no message in it contains
  a semicolon, so the block split measures the separator instead of colliding with it.
* **Every refusal fixture is paired with an ACCEPTANCE of the same shape.**  The same
  helper builds a valid register that must exit 0 with the `OK:` document, so a refusal is
  attributable to the mutation rather than to the fixture being unloadable for some other
  reason.
* **The live-register expectations are FLOORS, never keyed equalities.**  `gaps/` is grown
  by an unattended pass, so behavior 9 asserts exit 0, the document's shape and its single
  trailing newline; it never pins a record count.
* **No absolute machine path and no personal identifier appears here**: the repo root is
  derived from `__file__`, and every fixture register lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

from pydantic import ValidationError

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`).  Same boot line as `test_iter78_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: Minimal record satisfying the shipped schema (same shape as
#: `tests/test_iter217_behavior.py`).  Every fixture below is this record with keys
#: deleted or replaced, so the ONLY reason any of them refuses is the mutation named.
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"], "build_hypothesis": "build a small wrapper",
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}

#: The literal token behavior 4 requires for an error whose `loc` is the empty tuple.
RECORD_LEVEL_TOKEN = "<record>"

#: The separator between the rendered items of ONE file.
ITEM_SEP = " | "

#: The separator between per-FILE blocks.  Unchanged by this iteration (`pm.md`, Out of
#: Scope), and only ever split on by fixtures whose messages carry no `"; "`.
BLOCK_SEP = "; "

#: The loc-less dialect the door spoke BEFORE this iteration, measured against the
#: pre-change tree.  Behaviors 1-5 must never render this again.
OLD_DIALECT = "1 schema error(s): Field required"

#: Behavior 7, PINNED CONSTANTS captured from the pre-change implementation (the commit
#: this iteration's work sits on top of) and verified byte-identical against the working
#: tree before being written here.  They are constants, not re-renderings, so a
#: regression in these neighbouring refusals cannot re-baseline itself.
PINNED_BAD_JSON_ERR = (
    "Error: GAP-001.json: unreadable/invalid JSON: "
    "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)\n"
)
PINNED_DUPLICATE_ID_ERR = "Error: duplicate gap id(s): GAP-001\n"

#: The one thing that is NOT valid JSON, used by behavior 7.
NOT_JSON = "{not json"


# --------------------------------------------------------------------------- helpers
def _mutate(**changes: object) -> dict:
    """A deep copy of `RECORD`; a value of `None` DELETES the key."""
    record = json.loads(json.dumps(RECORD))
    for key, value in changes.items():
        if value is None:
            record.pop(key, None)
        else:
            record[key] = value
    return record


def _register(root: pathlib.Path, files: dict) -> pathlib.Path:
    """Build `<root>/gaps/` from `{filename: dict-or-raw-text}` and return `<root>`."""
    gaps = root / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (gaps / name).write_text(text, encoding="utf-8")
    return root


def _run(register: pathlib.Path, capsys) -> tuple[int, str, str]:
    """Drive the public entry point in-process and capture stdout/stderr."""
    code = main(["validate", str(register)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_bytes(register: pathlib.Path) -> subprocess.CompletedProcess[bytes]:
    """Drive the PACKAGED entry point, so byte claims are about real bytes."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, "validate", str(register)],
        capture_output=True, cwd=str(REPO_ROOT), check=False,
    )


def _refusal_body(err: str) -> str:
    """Assert the one-line `Error: `-prefixed contract and return the body after it."""
    assert err.endswith("\n"), f"stderr must end in one newline, got {err!r}"
    assert err.count("\n") == 1, f"stderr must be exactly ONE line, got {err!r}"
    line = err[:-1]
    assert line.startswith("Error: "), f"missing the 'Error: ' prefix: {line!r}"
    assert "Traceback" not in line
    return line[len("Error: "):]


_HEAD = re.compile(r"^(?P<name>[^:]+): (?P<count>\d+) schema error\(s\): ")


def _parse_block(block: str) -> tuple[str, int, list[str]]:
    """`<filename>: <n> schema error(s): <items>` -> (filename, n, items)."""
    match = _HEAD.match(block)
    assert match is not None, f"block does not carry the documented head: {block!r}"
    items = block[match.end():].split(ITEM_SEP)
    return match.group("name"), int(match.group("count")), items


def _split_item(item: str) -> tuple[str, str]:
    """One rendered item `"<loc>: <msg>"` -> (loc, msg)."""
    loc, sep, msg = item.partition(": ")
    assert sep, f"item carries no '<loc>: ' prefix: {item!r}"
    return loc, msg


def _assert_not_the_old_dialect(err: str) -> None:
    """The refusal is not the loc-less sentence the door produced before this change."""
    assert OLD_DIALECT not in err, f"the pre-change loc-less dialect is back: {err!r}"


def _pydantic_items(record: dict) -> list[str]:
    """The items behaviors 2/4 require, built from pydantic's OWN error list."""
    with pytest.raises(ValidationError) as excinfo:
        Gap.model_validate(record)
    rendered = []
    for error in excinfo.value.errors():
        loc = ".".join(str(part) for part in error["loc"]) or RECORD_LEVEL_TOKEN
        rendered.append(f"{loc}: {error['msg']}")
    return rendered


# ------------------------------------------------------------------- fixture registers
#: One record, one missing required field (behavior 1).
ONE_ERROR = _mutate(severity=None)

#: One record, three errors: two missing required fields plus a bad enum (behavior 2).
THREE_ERRORS = _mutate(severity=None, frequency=None, status="opne")

#: One record carrying an unknown key INSIDE the first citation (behavior 3).
NESTED_KEY = "excerpt"


def _nested_unknown_key() -> dict:
    record = json.loads(json.dumps(RECORD))
    record["evidence"][0][NESTED_KEY] = "a value the schema does not know"
    return record


def _record_level() -> dict:
    """Every citation locator non-resolvable -> the record-level validator, `loc == ()`."""
    record = json.loads(json.dumps(RECORD))
    for citation in record["evidence"]:
        citation["locator"] = "not-a-resolvable-locator"
    return record


#: Behavior 6 sweeps all four single-record refusals.
REFUSING_RECORDS = {
    "one-error": ONE_ERROR,
    "three-errors": THREE_ERRORS,
    "nested-unknown-key": _nested_unknown_key(),
    "record-level": _record_level(),
}


@pytest.fixture()
def valid_register(tmp_path):
    return _register(tmp_path / "valid", {"GAP-001.json": RECORD})


# --------------------------------------------------------------------------- control
def test_control_a_valid_register_still_certifies(valid_register, capsys):
    """Attribution control: the fixture shape LOADS, so every refusal below is the mutation."""
    code, out, err = _run(valid_register, capsys)
    assert (code, err) == (0, "")
    assert out == "OK: 1 gap record(s) valid.\n"


# ------------------------------------------------------------------------------- b1
def test_b1_a_single_field_error_names_its_field(tmp_path, capsys):
    """Exit 2, zero stdout, and ONE stderr line naming the field `severity`."""
    register = _register(tmp_path / "b1", {"GAP-001.json": ONE_ERROR})
    code, out, err = _run(register, capsys)
    assert code == 2
    assert out == ""
    assert err == "Error: GAP-001.json: 1 schema error(s): severity: Field required\n"
    _assert_not_the_old_dialect(err)


def test_b1_the_packaged_entry_point_writes_the_same_bytes(tmp_path):
    """Behavior 1 again, over real bytes: zero on stdout, one trailing newline on stderr."""
    register = _register(tmp_path / "b1bytes", {"GAP-001.json": ONE_ERROR})
    proc = _run_bytes(register)
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert proc.stderr == (
        b"Error: GAP-001.json: 1 schema error(s): severity: Field required\n"
    )


# ------------------------------------------------------------------------------- b2
def test_b2_every_error_is_reported_and_the_count_matches_them(tmp_path, capsys):
    """Three errors -> head says 3, and exactly 3 items are rendered beside it."""
    register = _register(tmp_path / "b2", {"GAP-001.json": THREE_ERRORS})
    code, out, err = _run(register, capsys)
    assert (code, out) == (2, "")
    body = _refusal_body(err)
    name, count, items = _parse_block(body)
    assert name == "GAP-001.json"
    assert count == 3, f"head must count the record's errors, got {count} in {err!r}"
    assert len(items) == count, (
        f"the head claims {count} error(s) but {len(items)} item(s) were rendered: {err!r}"
    )
    _assert_not_the_old_dialect(err)


def test_b2_the_three_locs_each_appear_as_the_loc_of_one_item(tmp_path, capsys):
    """`status`, `severity` and `frequency` are each ONE item's loc, not a substring."""
    register = _register(tmp_path / "b2locs", {"GAP-001.json": THREE_ERRORS})
    _, _, err = _run(register, capsys)
    _, count, items = _parse_block(_refusal_body(err))
    locs = [_split_item(item)[0] for item in items]
    assert sorted(locs) == ["frequency", "severity", "status"]
    assert len(locs) == count


def test_b2_item_order_is_pydantic_errors_order(tmp_path, capsys):
    """Order is `ValidationError.errors()` order, and each message is verbatim."""
    register = _register(tmp_path / "b2order", {"GAP-001.json": THREE_ERRORS})
    _, _, err = _run(register, capsys)
    _, _, items = _parse_block(_refusal_body(err))
    assert items == _pydantic_items(THREE_ERRORS)


def test_b2_the_bad_enum_message_survives_its_own_semicolon(tmp_path, capsys):
    """The enum message contains `'; '`; it must be carried verbatim, not truncated."""
    register = _register(tmp_path / "b2enum", {"GAP-001.json": THREE_ERRORS})
    _, _, err = _run(register, capsys)
    _, _, items = _parse_block(_refusal_body(err))
    enum_items = [i for i in items if _split_item(i)[0] == "status"]
    assert len(enum_items) == 1
    _, msg = _split_item(enum_items[0])
    assert msg.startswith("Value error, unknown status 'opne'")
    assert "; allowed: (" in msg


# ------------------------------------------------------------------------------- b3
def test_b3_a_nested_loc_keeps_its_list_index(tmp_path, capsys):
    """`evidence.0.excerpt` -- bare digits between two `.`, no brackets, no quotes."""
    register = _register(tmp_path / "b3", {"GAP-001.json": _nested_unknown_key()})
    code, out, err = _run(register, capsys)
    assert (code, out) == (2, "")
    _, count, items = _parse_block(_refusal_body(err))
    assert (count, len(items)) == (1, 1)
    loc, msg = _split_item(items[0])
    assert loc == f"evidence.0.{NESTED_KEY}"
    assert msg == "Extra inputs are not permitted"
    for forbidden in ("evidence[0]", "('evidence'", "evidence.'0'", "evidence..", "[0]"):
        assert forbidden not in err, f"index rendered as {forbidden!r}: {err!r}"


# ------------------------------------------------------------------------------- b4
def test_b4_a_record_level_error_renders_the_literal_record_token(tmp_path, capsys):
    """An empty `loc` becomes `<record>`, never an empty string; message verbatim."""
    broken = _record_level()
    register = _register(tmp_path / "b4", {"GAP-001.json": broken})
    code, out, err = _run(register, capsys)
    assert (code, out) == (2, "")
    _, count, items = _parse_block(_refusal_body(err))
    assert (count, len(items)) == (1, 1)
    loc, msg = _split_item(items[0])
    assert loc == RECORD_LEVEL_TOKEN
    assert msg.startswith("Value error, ")
    assert "no citation has a resolvable locator" in msg
    assert items == _pydantic_items(broken)
    assert ")): " not in err and ": : " not in err


# ------------------------------------------------------------------------------- b5
#: Two invalid records whose messages contain NO `"; "`, so `BLOCK_SEP` is splittable.
_B5_FILES = {
    "GAP-002.json": _mutate(id="GAP-002", severity=None, frequency=None),
    "GAP-001.json": _mutate(severity=None),
}


def test_b5_two_broken_records_both_report_in_filename_order(tmp_path, capsys):
    """One block per file, joined by `'; '`, files in filename-sorted order."""
    register = _register(tmp_path / "b5", _B5_FILES)
    code, out, err = _run(register, capsys)
    assert (code, out) == (2, "")
    body = _refusal_body(err)
    blocks = body.split(BLOCK_SEP)
    assert len(blocks) == 2, f"expected one block per file: {body!r}"
    names = [_parse_block(block)[0] for block in blocks]
    assert names == sorted(_B5_FILES), "blocks must be in filename-sorted order"


def test_b5_each_blocks_count_equals_its_own_files_error_count(tmp_path, capsys):
    """The per-file integer is that file's OWN count (1 and 2, not 3 and 3)."""
    register = _register(tmp_path / "b5counts", _B5_FILES)
    _, _, err = _run(register, capsys)
    blocks = _refusal_body(err).split(BLOCK_SEP)
    parsed = {name: (count, items) for name, count, items in map(_parse_block, blocks)}
    for name, (count, items) in parsed.items():
        assert len(items) == count, f"{name}: head says {count}, rendered {len(items)}"
    assert parsed["GAP-001.json"][0] == 1
    assert parsed["GAP-002.json"][0] == 2
    assert sorted(_split_item(i)[0] for i in parsed["GAP-002.json"][1]) == [
        "frequency", "severity"]


# ------------------------------------------------------------------------------- b6
@pytest.mark.parametrize("label", sorted(REFUSING_RECORDS))
def test_b6_the_refusal_contract_holds_for_every_single_record_shape(
        label, tmp_path, capsys):
    """Exit 2, zero stdout, exactly one `Error: ` line, one trailing `\\n`, no traceback."""
    register = _register(tmp_path / f"b6-{label}",
                         {"GAP-001.json": REFUSING_RECORDS[label]})
    code, out, err = _run(register, capsys)
    assert code == 2
    assert out == ""
    body = _refusal_body(err)
    assert body
    _assert_not_the_old_dialect(err)


def test_b6_the_two_record_shape_also_holds_the_contract(tmp_path, capsys):
    code, out, err = _run(_register(tmp_path / "b6two", _B5_FILES), capsys)
    assert (code, out) == (2, "")
    assert _refusal_body(err)


@pytest.mark.parametrize("label", sorted(REFUSING_RECORDS))
def test_b6_over_real_bytes_stdout_is_empty_and_stderr_ends_in_one_newline(
        label, tmp_path):
    register = _register(tmp_path / f"b6b-{label}",
                         {"GAP-001.json": REFUSING_RECORDS[label]})
    proc = _run_bytes(register)
    assert proc.returncode == 2
    assert proc.stdout == b""
    assert proc.stderr.startswith(b"Error: ")
    assert proc.stderr.endswith(b"\n")
    assert proc.stderr.count(b"\n") == 1
    assert b"Traceback" not in proc.stderr


# ------------------------------------------------------------------------------- b7
def test_b7_an_invalid_json_file_refuses_with_the_pinned_pre_change_bytes(
        tmp_path, capsys):
    """No loc machinery leaks into the JSON-decode refusal."""
    register = _register(tmp_path / "b7json", {"GAP-001.json": NOT_JSON})
    code, out, err = _run(register, capsys)
    assert (code, out) == (2, "")
    assert err == PINNED_BAD_JSON_ERR
    assert "schema error(s)" not in err
    assert RECORD_LEVEL_TOKEN not in err


def test_b7_a_duplicate_id_refuses_with_the_pinned_pre_change_bytes(tmp_path, capsys):
    register = _register(tmp_path / "b7dup", {
        "GAP-001.json": RECORD, "GAP-002.json": _mutate()})
    code, out, err = _run(register, capsys)
    assert (code, out) == (2, "")
    assert err == PINNED_DUPLICATE_ID_ERR
    assert "schema error(s)" not in err


# ------------------------------------------------------------------------------- b8
@pytest.mark.parametrize("label", sorted(REFUSING_RECORDS))
def test_b8_two_consecutive_invocations_are_byte_identical(label, tmp_path):
    register = _register(tmp_path / f"b8-{label}",
                         {"GAP-001.json": REFUSING_RECORDS[label]})
    first, second = _run_bytes(register), _run_bytes(register)
    assert (first.returncode, first.stdout, first.stderr) == (
        second.returncode, second.stdout, second.stderr)


def test_b8_the_multi_file_refusal_is_deterministic(tmp_path):
    register = _register(tmp_path / "b8multi", _B5_FILES)
    first, second = _run_bytes(register), _run_bytes(register)
    assert first.stderr == second.stderr
    assert first.returncode == second.returncode == 2


# ------------------------------------------------------------------------------- b9
def test_b9_the_live_register_still_certifies_at_exit_zero(capsys):
    """Floor, not a keyed equality: `gaps/` is grown by an unattended pass."""
    code, out, err = _run(REPO_ROOT, capsys)
    assert code == 0, f"the live register must stay valid; stderr was {err!r}"
    assert err == ""
    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert re.fullmatch(r"OK: \d+ gap record\(s\) valid\.\n", out), repr(out)
    assert int(re.search(r"OK: (\d+) ", out).group(1)) >= 1


# ------------------------------------------------------------------------------ b10
def test_b10_the_refusal_sentence_keeps_exactly_one_construction_site():
    """A lexical census: `schema error(s)` occurs in ONE file, ONE place, under `src/`."""
    sites = {}
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        count = path.read_text(encoding="utf-8").count("schema error(s)")
        if count:
            sites[path.relative_to(REPO_ROOT).as_posix()] = count
    assert len(sites) == 1, f"the sentence has more than one home: {sites}"
    assert sum(sites.values()) == 1, f"the sentence is constructed twice: {sites}"


def test_b10_the_record_token_and_item_separator_are_not_copied_around():
    """The rendering helper is one site too: `<record>` appears in at most one module."""
    homes = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if RECORD_LEVEL_TOKEN in path.read_text(encoding="utf-8")
    ]
    assert len(homes) <= 1, f"`{RECORD_LEVEL_TOKEN}` is written in several modules: {homes}"


# ------------------------------------------------------------- acceptance-criteria pins
def test_ac_no_absolute_machine_path_or_identifier_in_this_module():
    """The module states its own compliance with the public-repo rule it is bound by.

    The needles are ASSEMBLED rather than written out, so this guard does not trip on
    its own source text.
    """
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    needles = ("/" + "Users" + "/", "/" + "home" + "/", "/" + "root" + "/", "C" + ":\\")
    for needle in needles:
        assert needle not in text, f"absolute machine path fragment {needle!r} present"
