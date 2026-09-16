"""Iteration 246 -- a record file that REPEATS a JSON key is REFUSED, by name and path.

`json.loads` keeps the LAST of two identical keys and raises nothing, so ~40 bytes of
appended text -- a second `"evidence"` array -- silently replaced the evidence ladder a
record's confidence is DERIVED from.  Measured at the pre-change tree by `pm.md`: the
register's ONE below-floor record climbed from confidence 1 to 5 and moved out of
`## Below confidence floor` into the ranked table, while `validate` still printed
`OK: 120 gap record(s) valid.` and `report` still printed a line 3 that looked derived.
That is the exact regression `VISION.md` names as the one that matters most -- a record
raising its own confidence -- so this module drives the published doors and asserts the
refusal, its paths, and the neighbouring behaviours the change must NOT move.

ISOLATION CONTRACT IS HONORED.  Nothing here reads `src/agent_gap_radar/*.py` as source:
no implementation module is opened for its logic, and the engineer's notes, the reviewer's
notes, `IMPLEMENTATION.patch` and every diff were left unread.  Behaviour 7 is a LEXICAL
CENSUS in the shape `tests/test_iter242_behavior.py::test_b10_...` already ships -- it
counts occurrences of one pinned phrase and never inspects what surrounds it.  Every other
expectation comes from `pm.md`'s Expected Behaviors and is measured by CALLING the public
entry point (`cli.main`), by RUNNING the packaged one in a subprocess, or by asking the
public model door (`Gap.model_validate`) for pydantic's own error list.

Structural notes, so a green dot here cannot mean less than it looks like:

* **The repeated key is produced by a JSON EMITTER, not by string surgery.**  `_raw`
  re-serialises a record and emits a chosen key twice at a chosen dotted path, so every
  fixture is verifiably valid RFC 8259 JSON (each test asserts `json.loads` accepts it)
  and the premise of behaviour 2 -- the file IS readable and IS valid JSON -- is measured
  rather than asserted.
* **The second copy is BYTE-IDENTICAL by default.**  `pm.md` behaviour 1 requires the
  refusal to fire on repetition, not on disagreement, so the default fixture repeats the
  same bytes and a separate test supplies a DIFFERING second value.
* **Behaviour 4 is never split on `"; "`.**  pydantic's own message for an unknown `layer`
  contains `"; allowed: (...)"` (measured), which `pm.md` declares as residue and puts out
  of scope, so the two-file refusal is asserted as ONE whole-string equality against
  `aaa_clause + "; " + zzz_clause`.  That pins the order, the separator and the
  byte-identity of the schema clause at once, and cannot be satisfied by a looser reading.
* **The schema clause is DERIVED, never transcribed.**  Behaviour 4 rebuilds `zzz.json`'s
  clause from `ValidationError.errors()` AND from a run of the same file ALONE, so a
  re-worded schema refusal reddens here instead of quietly re-baselining.
* **Every refusal fixture is paired with an ACCEPTANCE of the same shape.**  The honest
  twin of each mutated fixture must exit 0 with today's exact document, so a refusal is
  attributable to the repeated key rather than to an unloadable fixture.
* **The live-register claims are DERIVED equalities, not frozen counts.**  `gaps/` is grown
  by an unattended pass, so behaviour 5 derives the record count from the directory and
  asserts `ranked + below == records` with at least one record still DISPLAYED below the
  floor.  Measured this iteration: `Records: 120 | ranked: 119 | below confidence floor
  (2): 1`.
* **No absolute machine path and no personal identifier appears here**: the repo root is
  derived from `__file__`, every fixture register lives under pytest's `tmp_path`, and the
  last test in this module enforces that with assembled needles.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from pydantic import ValidationError

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The packaged entry point, driven the way `project.scripts` declares it.  Same boot
#: line as `tests/test_iter242_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: The two register-loading verbs `pm.md` bounds the out-of-process runs to.  Iteration
#: 217 already pinned that all eight verbs route `RegistryError` identically.
VERBS = ("validate", "report")

#: The refusal sentence, PINNED by `pm.md` character for character:
#:     <basename>: N duplicate JSON key(s): <path> | <path> | ...
DUP_HEAD_WORDS = "duplicate JSON key(s)"

#: The module's existing item join, reused by the pinned sentence.
ITEM_JOIN = " | "

#: The per-FILE separator.  Unchanged by this iteration (`pm.md`, Out of Scope), and never
#: split on -- only ever used to BUILD an expected whole string.
BLOCK_SEP = "; "

#: The sentence the refusal must NOT borrow: the file is readable and is valid JSON.
FORBIDDEN_SENTENCE = "unreadable/invalid JSON"

#: The schema-refusal head that must not appear when a file's repeat already refused it.
SCHEMA_HEAD_WORDS = "schema error(s)"

#: Minimal record satisfying the shipped schema (same shape as
#: `tests/test_iter242_behavior.py` and `tests/test_iter217_behavior.py`).
RECORD = {
    "id": "GAP-001", "title": "A thing is broken", "layer": "orchestration",
    "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
    "severity": 5, "frequency": 4, "tractability": 3,
    "existing": ["partial fix one"], "build_hypothesis": "build a small wrapper",
    "evidence": [{"source_class": "first-party-field", "title": "INC-1",
                  "locator": "https://example.invalid/inc1", "date": "2026-01-02",
                  "quote": "the verbatim line"}],
}

#: Behaviour 3 needs a repeat inside a nested OBJECT and inside an ARRAY ELEMENT as well
#: as at the top level, so it needs a record carrying `tags` and a `check` whose
#: `present_when` holds a `pattern` DIRECTLY (`kind == "content_matches"`, not a nested
#: `all_of`).  A hand-written check is NOT usable here: the shipped schema requires an
#: automated check to prove itself with two-sided fixtures (measured: `check: Value error,
#: CHK-001: an automated check MUST ship two-sided fixtures`), so the fixture would refuse
#: for a reason that has nothing to do with a repeated key.  Instead the base is the FIRST
#: COMMITTED record of that shape -- valid by construction, since the live register
#: validates -- discovered rather than pinned by id, so a re-shaped record does not redden
#: this behaviour, it just moves which record carries it.
def _record_with_a_nested_pattern() -> dict:
    """The first committed record with `tags` and a direct `check.present_when.pattern`."""
    for path in sorted((REPO_ROOT / "gaps").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        check = record.get("check") or {}
        if record.get("tags") and "pattern" in (check.get("present_when") or {}):
            return record
    pytest.skip("no committed record carries a direct `check.present_when.pattern`")

#: Sentinel: the repeated key's second copy is BYTE-IDENTICAL to the first.
SAME = object()


# --------------------------------------------------------------------------- helpers
def _dotted(path: tuple) -> str:
    """`('evidence', 0, 'quote')` -> `evidence.0.quote` (BARE integer indices)."""
    return ".".join(str(part) for part in path)


def _emit(node: object, repeats: dict, path: tuple = ()) -> str:
    """Serialise `node` to JSON text, emitting each key named in `repeats` TWICE.

    `repeats` maps a dotted path to the second copy's value, or to `SAME` for a
    byte-identical copy.  The duplicated paths in every fixture below are disjoint from
    each other, so no repeat is nested inside another repeat's value.
    """
    if isinstance(node, dict):
        parts = []
        for key, value in node.items():
            here = path + (key,)
            first = json.dumps(key) + ": " + _emit(value, repeats, here)
            parts.append(first)
            dotted = _dotted(here)
            if dotted in repeats:
                second = repeats[dotted]
                parts.append(first if second is SAME
                             else json.dumps(key) + ": " + json.dumps(second))
        return "{" + ", ".join(parts) + "}"
    if isinstance(node, list):
        return "[" + ", ".join(_emit(item, repeats, path + (index,))
                               for index, item in enumerate(node)) + "]"
    return json.dumps(node)


def _raw(record: dict, repeats: dict) -> str:
    """`_emit`, plus the guarantee the fixture is valid JSON with the keys repeated."""
    text = _emit(record, repeats)
    honest = _emit(record, {})
    json.loads(text)  # RFC 8259 valid: `json` accepts it and keeps the LAST copy
    for dotted in repeats:
        needle = json.dumps(dotted.rsplit(".", 1)[-1]) + ":"
        assert text.count(needle) == honest.count(needle) + 1, (
            f"fixture does not repeat {dotted!r} exactly once more than the honest twin"
        )
    return text


def _register(root: pathlib.Path, files: dict) -> pathlib.Path:
    """Build `<root>/gaps/` from `{filename: dict-or-raw-text}` and return `<root>`."""
    gaps = root / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (gaps / name).write_text(text, encoding="utf-8")
    return root


def _run(verb: str, register: pathlib.Path, capsys) -> tuple[int, str, str]:
    """Drive the public entry point in-process and capture stdout/stderr."""
    code = main([verb, str(register)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run_bytes(verb: str, register: pathlib.Path,
               env: dict | None = None) -> subprocess.CompletedProcess:
    """Drive the PACKAGED entry point, so byte claims are about real bytes.

    `env` overlays the inherited environment.  It exists so the determinism claim can
    be measured across DIFFERENT interpreter hash seeds rather than assumed: pytest-xdist
    pins `PYTHONHASHSEED` for its workers, so an inherited environment would hand every
    run the same iteration order and a set-backed collection would look stable.
    """
    child_env = None
    if env is not None:
        child_env = dict(os.environ)
        child_env.update(env)
    return subprocess.run(
        [sys.executable, "-c", BOOT, verb, str(register)],
        capture_output=True, cwd=str(REPO_ROOT), check=False, env=child_env,
    )


def _refusal_body(err: str) -> str:
    """Assert the one-line `Error: `-prefixed contract and return the body after it."""
    assert err.endswith("\n"), f"stderr must end in one newline, got {err!r}"
    assert err.count("\n") == 1, f"stderr must be exactly ONE line, got {err!r}"
    line = err[:-1]
    assert line.startswith("Error: "), f"missing the 'Error: ' prefix: {line!r}"
    assert "Traceback" not in line
    return line[len("Error: "):]


def _dup_clause(name: str, paths: list) -> str:
    """The pinned per-file clause: `<basename>: N duplicate JSON key(s): a | b`."""
    ordered = sorted(paths)
    return f"{name}: {len(ordered)} {DUP_HEAD_WORDS}: " + ITEM_JOIN.join(ordered)


def _pydantic_clause(name: str, record: dict) -> str:
    """`zzz.json`'s schema clause, rebuilt from pydantic's OWN error list."""
    with pytest.raises(ValidationError) as excinfo:
        Gap.model_validate(record)
    items = []
    for error in excinfo.value.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "<record>"
        items.append(f"{loc}: {error['msg']}")
    return f"{name}: {len(items)} {SCHEMA_HEAD_WORDS}: " + ITEM_JOIN.join(items)


def _live_record_count() -> int:
    """The committed register's size, DERIVED so behaviour 5 pins no frozen number."""
    return len(list((REPO_ROOT / "gaps").glob("*.json")))


def _copy_live_register(root: pathlib.Path) -> pathlib.Path:
    """A scratch register holding a copy of every committed record."""
    shutil.copytree(REPO_ROOT / "gaps", root / "gaps")
    return root


# ------------------------------------------------------------------------------- b1
def test_b1_a_repeated_top_level_key_is_refused_by_both_doors(tmp_path):
    """Behaviour 1 -- exit 2, ZERO stdout bytes, exactly the pinned stderr line."""
    expected = ("Error: " + _dup_clause("GAP-001.json", ["evidence"]) + "\n").encode()
    for verb in VERBS:
        root = _register(tmp_path / verb, {
            "GAP-001.json": _raw(RECORD, {"evidence": SAME}),
        })
        done = _run_bytes(verb, root)
        assert done.returncode == 2, (verb, done.returncode, done.stderr)
        assert done.stdout == b"", f"{verb} wrote to stdout: {done.stdout!r}"
        assert done.stderr == expected, f"{verb}: {done.stderr!r} != {expected!r}"


def test_b1_the_honest_twin_of_that_file_is_still_accepted(tmp_path):
    """Behaviour 1, the OTHER side: the same record without the repeat still loads."""
    root = _register(tmp_path, {"GAP-001.json": json.dumps(RECORD)})
    done = _run_bytes("validate", root)
    assert done.returncode == 0, done.stderr
    assert done.stderr == b""
    assert done.stdout == b"OK: 1 gap record(s) valid.\n", done.stdout
    done = _run_bytes("report", root)
    assert done.returncode == 0, done.stderr
    assert done.stdout.endswith(b"\n") and not done.stdout.endswith(b"\n\n")
    assert b"GAP-001" in done.stdout


def test_b1_repetition_refuses_even_when_the_two_values_DISAGREE(tmp_path, capsys):
    """Behaviour 1 -- the rule is repetition; a differing second copy refuses too."""
    louder = [dict(RECORD["evidence"][0], quote="a different verbatim line"),
              dict(RECORD["evidence"][0], title="INC-2")]
    root = _register(tmp_path, {"GAP-001.json": _raw(RECORD, {"evidence": louder})})
    code, out, err = _run("validate", root, capsys)
    assert code == 2 and out == ""
    assert _refusal_body(err) == _dup_clause("GAP-001.json", ["evidence"])


# ------------------------------------------------------------------------------- b2
def test_b2_the_refusal_never_reads_unreadable_or_invalid_json(tmp_path, capsys):
    """Behaviour 2 -- the duplicate-key clause is its own sentence."""
    raw = _raw(RECORD, {"evidence": SAME})
    assert json.loads(raw), "premise: the fixture IS readable and IS valid JSON"
    root = _register(tmp_path, {"GAP-001.json": raw})
    code, out, err = _run("validate", root, capsys)
    assert code == 2 and out == ""
    assert DUP_HEAD_WORDS in err, err
    assert FORBIDDEN_SENTENCE not in err, f"the wrong defect is named: {err!r}"
    assert SCHEMA_HEAD_WORDS not in err, f"a schema clause leaked in: {err!r}"


def test_b2_a_genuinely_unparseable_file_still_says_unreadable(tmp_path, capsys):
    """Behaviour 2, the OTHER side: the neighbouring sentence still exists, unmoved."""
    root = _register(tmp_path, {"GAP-001.json": "{not json"})
    code, out, err = _run("validate", root, capsys)
    assert code == 2 and out == ""
    assert FORBIDDEN_SENTENCE in err, err
    assert DUP_HEAD_WORDS not in err, f"the new clause fires on the wrong input: {err!r}"


# ------------------------------------------------------------------------------- b3
def test_b3_nested_and_multiple_repeats_are_all_named_in_one_clause(tmp_path, capsys):
    """Behaviour 3 -- three repeats, one clause, bare indices, sorted, ` | `-joined."""
    paths = ["evidence.0.quote", "check.present_when.pattern", "tags"]
    record = _record_with_a_nested_pattern()
    raw = _raw(record, {path: SAME for path in paths})
    root = _register(tmp_path, {"GAP-001.json": raw})
    code, out, err = _run("validate", root, capsys)
    assert code == 2, err
    assert out == ""
    body = _refusal_body(err)
    assert body == _dup_clause("GAP-001.json", paths), body
    # The head COUNT is checked against the items it stands beside, so a clause that
    # dropped a path while still counting it cannot pass this file.
    head = re.match(r"GAP-001\.json: (\d+) " + re.escape(DUP_HEAD_WORDS) + ": ", body)
    assert head is not None, body
    items = body[head.end():].split(ITEM_JOIN)
    assert int(head.group(1)) == len(items) == 3, body
    # The SORT claim is non-vacuous: file order puts `evidence.0.quote` before `tags`
    # before `check.present_when.pattern`, and sorted order is the reverse of that.
    assert items == sorted(items) != ["evidence.0.quote", "tags",
                                      "check.present_when.pattern"]
    assert "evidence[0]" not in body, "indices must be BARE, as `_dotted_loc` renders"


def test_b3_the_honest_check_bearing_twin_is_accepted(tmp_path, capsys):
    """Behaviour 3, the OTHER side: the same record with no repeat validates."""
    record = _record_with_a_nested_pattern()
    root = _register(tmp_path, {"GAP-001.json": json.dumps(record)})
    code, out, err = _run("validate", root, capsys)
    assert code == 0, err
    assert err == ""
    assert out == "OK: 1 gap record(s) valid.\n", out


# ------------------------------------------------------------------------------- b4
_BAD_LAYER = dict(RECORD, id="GAP-002", layer="no-such-layer")


def test_b4_two_bad_files_compose_with_the_unchanged_separator(tmp_path, capsys):
    """Behaviour 4 -- one refusal, `aaa.json` first, joined by today's `; `.

    Asserted as ONE whole-string equality, never by splitting on `"; "`: pydantic's own
    message for an unknown `layer` CONTAINS `"; allowed: (...)"`, which `pm.md` declares
    as residue and puts out of scope, so a split would collide with the separator.
    """
    alone = _register(tmp_path / "alone", {"zzz.json": json.dumps(_BAD_LAYER)})
    code, out, err = _run("validate", alone, capsys)
    assert code == 2 and out == ""
    zzz_clause = _refusal_body(err)
    # The clause is DERIVED from pydantic, not transcribed, so a re-worded schema
    # refusal reddens here rather than re-baselining silently.
    assert zzz_clause == _pydantic_clause("zzz.json", _BAD_LAYER), zzz_clause

    both = _register(tmp_path / "both", {
        "aaa.json": _raw(RECORD, {"evidence": SAME}),
        "zzz.json": json.dumps(_BAD_LAYER),
    })
    code, out, err = _run("validate", both, capsys)
    assert code == 2 and out == ""
    expected = _dup_clause("aaa.json", ["evidence"]) + BLOCK_SEP + zzz_clause
    assert _refusal_body(err) == expected, _refusal_body(err)


def test_b4_a_file_that_repeats_a_key_and_fails_the_schema_reports_only_the_repeat(
    tmp_path, capsys,
):
    """Behaviour 4 -- the parse yields no record to validate, so no schema clause."""
    forged = dict(RECORD, layer="no-such-layer")
    root = _register(tmp_path, {"GAP-001.json": _raw(forged, {"evidence": SAME})})
    code, out, err = _run("validate", root, capsys)
    assert code == 2 and out == ""
    assert _refusal_body(err) == _dup_clause("GAP-001.json", ["evidence"])
    assert SCHEMA_HEAD_WORDS not in err, err


def test_b4_two_honest_files_are_still_accepted_together(tmp_path, capsys):
    """Behaviour 4, the OTHER side: the same two filenames, unmutated, load."""
    root = _register(tmp_path, {
        "aaa.json": json.dumps(RECORD),
        "zzz.json": json.dumps(dict(RECORD, id="GAP-002")),
    })
    code, out, err = _run("validate", root, capsys)
    assert code == 0, err
    assert err == "" and out == "OK: 2 gap record(s) valid.\n"


# ------------------------------------------------------------------------------- b5
def test_b5_the_committed_register_still_validates_untouched(capsys):
    """Behaviour 5 -- exit 0, one line, and a count DERIVED from the directory."""
    code, out, err = _run("validate", REPO_ROOT, capsys)
    assert code == 0, err
    assert err == ""
    assert out == f"OK: {_live_record_count()} gap record(s) valid.\n", out


def test_b5_the_report_census_line_still_displays_the_below_floor_record(capsys):
    """Behaviour 5 -- `ranked + below == records`, with at least one still DISPLAYED.

    Measured this iteration: `Records: 120 | ranked: 119 | below confidence floor (2): 1`.
    Asserted as a derived identity rather than as those three frozen integers, because
    `gaps/` is grown by an unattended pass and a legitimate new record must not redden a
    test that is about the census being HONEST.
    """
    code, out, err = _run("report", REPO_ROOT, capsys)
    assert code == 0, err
    assert err == ""
    line = out.split("\n")[2]
    match = re.fullmatch(
        r"Records: (\d+) \| ranked: (\d+) \| below confidence floor \((\d+)\): (\d+)",
        line,
    )
    assert match is not None, repr(line)
    records, ranked, _floor, below = (int(group) for group in match.groups())
    assert records == _live_record_count(), line
    assert ranked + below == records, line
    assert below >= 1, f"the below-floor record stopped being displayed: {line}"
    assert "## Below confidence floor" in out, "the below-floor section vanished"


# ------------------------------------------------------------------------------- b6
def _forge_self_raised_confidence(register_root: pathlib.Path) -> str:
    """Append a second `"evidence"` array to the below-floor record; return its name."""
    gaps = register_root / "gaps"
    target = next(iter(sorted(gaps.glob("GAP-010-*.json"))))
    donor = next(iter(sorted(gaps.glob("GAP-011-*.json"))))
    stolen = json.dumps(json.loads(donor.read_text(encoding="utf-8"))["evidence"])
    text = target.read_text(encoding="utf-8").rstrip()
    assert text.endswith("}"), "premise: the record file is one JSON object"
    target.write_text(text[:-1].rstrip().rstrip(",") + ', "evidence": ' + stolen + "}",
                      encoding="utf-8")
    reloaded = json.loads(target.read_text(encoding="utf-8"))
    assert reloaded["evidence"] == json.loads(stolen), (
        "premise: `json` keeps the LAST copy, which is the escalation itself"
    )
    return target.name


def test_b6_the_escalation_this_closes_is_refused_end_to_end(tmp_path):
    """Behaviour 6 -- the forged register refuses at both doors, with zero stdout."""
    root = _copy_live_register(tmp_path / "forged")
    name = _forge_self_raised_confidence(root)
    expected = ("Error: " + _dup_clause(name, ["evidence"]) + "\n").encode()
    for verb in VERBS:
        done = _run_bytes(verb, root)
        assert done.returncode == 2, (verb, done.returncode, done.stderr)
        assert done.stdout == b"", f"{verb} published the forged register: {done.stdout[:200]!r}"
        assert done.stderr == expected, f"{verb}: {done.stderr!r} != {expected!r}"


def test_b6_the_same_scratch_register_unforged_is_accepted_unchanged(tmp_path):
    """Behaviour 6, the OTHER side: the copy WITHOUT the append is the honest baseline.

    This is what makes the refusal above attributable to the ~40 appended bytes rather
    than to the copy itself, and it pins the state the escalation used to destroy: the
    record stays BELOW the floor.
    """
    root = _copy_live_register(tmp_path / "honest")
    done = _run_bytes("validate", root)
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode() == f"OK: {_live_record_count()} gap record(s) valid.\n"
    done = _run_bytes("report", root)
    assert done.returncode == 0, done.stderr
    out = done.stdout.decode()
    below = out.split("## Below confidence floor", 1)
    assert len(below) == 2, "the below-floor section vanished from the scratch register"
    assert "GAP-010" in below[1], "the below-floor record is no longer displayed there"
    # The RANKED TABLE only -- the id legitimately also appears in `## Tag coverage`,
    # which is a census of every record and not a confidence claim.
    ranked = out.split("## Ranked gaps", 1)[1].split("\n## ", 1)[0]
    assert "GAP-010" not in ranked, "the below-floor record climbed into the ranked table"


# ------------------------------------------------------------------------------- b7
def test_b7_the_refusal_sentence_keeps_exactly_one_construction_site():
    """Behaviour 7 -- a LEXICAL census: the pinned words live in ONE file, ONE place."""
    sites = {}
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        count = path.read_text(encoding="utf-8").count(DUP_HEAD_WORDS)
        if count:
            sites[path.relative_to(REPO_ROOT).as_posix()] = count
    assert len(sites) == 1, f"the sentence has more than one home: {sites}"
    assert sum(sites.values()) == 1, f"the sentence is constructed twice: {sites}"


def test_b7_the_strict_parse_helper_is_installed_at_one_site_only():
    """Behaviour 7 -- the strict hook itself is spelled in at most one module."""
    needle = "object_" + "pairs_hook"
    homes = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
        if needle in path.read_text(encoding="utf-8")
    ]
    assert len(homes) <= 1, f"the strict hook is installed in several modules: {homes}"


# ------------------------------------------------------------- acceptance-criteria pins
def test_ac_no_absolute_machine_path_or_identifier_in_this_module():
    """The PUBLIC-REPO rule, enforced with ASSEMBLED needles so it cannot trip on itself."""
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    for needle in ("/" + "Users" + "/", "/" + "home" + "/", "C:" + "\\\\"):
        assert needle not in text, f"absolute machine path in this module: {needle!r}"


# ================================================== added by the SECOND tester round
# The first round was cut short by the per-stage cap with its full-suite run still
# PENDING.  Nothing in the tree had changed since, so this round KEPT that module and
# spent its budget on the places where an implementation that satisfies every test above
# could still be wrong:
#
#   * behaviour 3's bare-index claim was only ever exercised at index 0, which a walk
#     that hard-coded the FIRST element of every array would satisfy;
#   * behaviour 3's word "deterministically" was unpinned ACROSS PROCESSES, where a
#     set-backed collection of paths varies with the interpreter's hash seed;
#   * nothing asked what a key repeated THREE times reports, so the head count and the
#     rendered items could disagree on exactly the input that has more copies than paths;
#   * behaviour 4's `"; "` composition was measured for dup + schema but never for TWO
#     duplicate clauses, so filename order was never pinned between two NEW clauses;
#   * acceptance criterion 2 says the refusal reaches EVERY register-loading verb, and
#     only two of the six were driven.
#
# Each addition is paired with an acceptance side wherever it introduces a new fixture
# shape, for the same reason as above: a refusal must be attributable to the repeated
# key and not to a fixture that was never loadable.

#: A record with TWO citations, so a repeat can sit at a NON-ZERO array index.  Measured
#: loadable before it was used as a mutation base (`validate` exits 0 on the honest twin
#: below), so a refusal here is the repeat and not the second citation.
RECORD_TWO_CITATIONS = dict(RECORD, evidence=[
    RECORD["evidence"][0],
    {"source_class": "first-party-field", "title": "INC-2",
     "locator": "https://example.invalid/inc2", "date": "2026-01-03",
     "quote": "the second verbatim line"},
])


def _raw_with_extra_top_level_copies(record: dict, key: str, copies: int) -> str:
    """Valid JSON text whose top-level `key` appears `1 + copies` times.

    `_emit` deliberately emits at most ONE extra copy per path, which is the shape every
    behaviour above needs.  A THIRD copy needs its own emitter, so this appends whole
    `"key": value` members to the object's text and then MEASURES the result: the text
    parses, and the key really is spelled the expected number of times.
    """
    honest = json.dumps(record)
    assert honest.endswith("}")
    extra = "".join(f', {json.dumps(key)}: {json.dumps(record[key])}'
                    for _ in range(copies))
    text = honest[:-1] + extra + "}"
    json.loads(text)  # RFC 8259 valid, and `json` keeps the LAST copy
    assert text.count(json.dumps(key) + ":") == 1 + copies, text
    return text


# --------------------------------------------------------------------------- b3, more
def test_b3_a_repeat_at_a_NON_ZERO_array_index_renders_THAT_index(tmp_path, capsys):
    """Behaviour 3 -- a bare index is the ELEMENT's index, not always `0`."""
    assert len(RECORD_TWO_CITATIONS["evidence"]) == 2, "premise: two citations"
    raw = _raw(RECORD_TWO_CITATIONS, {"evidence.1.quote": SAME})
    root = _register(tmp_path, {"GAP-001.json": raw})
    code, out, err = _run("validate", root, capsys)
    assert code == 2, err
    assert out == ""
    body = _refusal_body(err)
    assert body == _dup_clause("GAP-001.json", ["evidence.1.quote"]), body
    assert "evidence.0.quote" not in body, f"the wrong element is named: {body!r}"


def test_b3_the_two_citation_record_without_the_repeat_is_accepted(tmp_path, capsys):
    """The honest twin of the non-zero-index fixture."""
    root = _register(tmp_path, {"GAP-001.json": json.dumps(RECORD_TWO_CITATIONS)})
    code, out, err = _run("validate", root, capsys)
    assert code == 0, err
    assert err == ""
    assert out == "OK: 1 gap record(s) valid.\n", out


def test_b3_a_key_repeated_THREE_times_keeps_head_count_and_items_in_step(
    tmp_path, capsys,
):
    """Behaviour 3 -- more COPIES than PATHS, and the head must still count the items.

    `pm.md` pins the head as "the number of paths listed" and says nothing about whether
    a key spelled three times is ONE repeated path or TWO, so this asserts only what the
    spec actually fixes: the file refuses, the head equals the rendered item count, and
    the repeated key is named.  The open reading is recorded in `tester2.md` for the PM.
    """
    raw = _raw_with_extra_top_level_copies(RECORD, "evidence", 2)
    root = _register(tmp_path, {"GAP-001.json": raw})
    code, out, err = _run("validate", root, capsys)
    assert code == 2, err
    assert out == ""
    body = _refusal_body(err)
    head = re.match(r"GAP-001\.json: (\d+) " + re.escape(DUP_HEAD_WORDS) + ": ", body)
    assert head is not None, body
    items = body[head.end():].split(ITEM_JOIN)
    assert int(head.group(1)) == len(items), body
    assert all(item == "evidence" for item in items), body
    assert FORBIDDEN_SENTENCE not in err and SCHEMA_HEAD_WORDS not in err, err


def test_b3_the_refusal_is_BYTE_IDENTICAL_under_three_different_hash_seeds(tmp_path):
    """Behaviour 3 -- "deterministically", measured across PROCESSES, not assumed.

    The quality bar requires byte-stable output.  A collection of repeated paths backed
    by a `set` renders in an order that depends on the interpreter's string hash seed, so
    the same register can emit two different refusals in two runs.  Three fresh
    interpreters with three explicit seeds must produce ONE stderr, byte for byte.
    """
    paths = ["evidence.0.quote", "check.present_when.pattern", "tags"]
    record = _record_with_a_nested_pattern()
    root = _register(tmp_path, {"GAP-001.json": _raw(record, {p: SAME for p in paths})})
    expected = ("Error: " + _dup_clause("GAP-001.json", paths) + "\n").encode()
    seen = {}
    for seed in ("0", "1", "2"):
        done = _run_bytes("validate", root, env={"PYTHONHASHSEED": seed})
        assert done.returncode == 2, (seed, done.stderr)
        assert done.stdout == b"", (seed, done.stdout)
        seen[seed] = done.stderr
    assert len(set(seen.values())) == 1, f"the refusal is seed-dependent: {seen}"
    assert seen["0"] == expected, seen["0"]


# --------------------------------------------------------------------------- b4, more
def test_b4_two_files_that_BOTH_repeat_a_key_compose_in_filename_order(tmp_path, capsys):
    """Behaviour 4 -- two NEW clauses, `aaa.json` first, joined by today's `; `.

    Safe to assert as a whole string with no derivation: neither duplicate-key clause
    contains `"; "`, so this pins the separator AND the order without touching the
    pydantic-message collision that `pm.md` puts out of scope.
    """
    root = _register(tmp_path, {
        "aaa.json": _raw(RECORD, {"evidence": SAME}),
        "zzz.json": _raw(dict(RECORD, id="GAP-002"), {"title": SAME}),
    })
    code, out, err = _run("validate", root, capsys)
    assert code == 2, err
    assert out == ""
    expected = (_dup_clause("aaa.json", ["evidence"]) + BLOCK_SEP
                + _dup_clause("zzz.json", ["title"]))
    assert _refusal_body(err) == expected, _refusal_body(err)
    assert SCHEMA_HEAD_WORDS not in err and FORBIDDEN_SENTENCE not in err, err


# ---------------------------------------------------- acceptance criterion 2, a 3rd verb
def test_ac2_a_third_register_loading_verb_routes_the_refusal_identically(
    tmp_path, capsys,
):
    """`list` loads the register too, and must refuse with the SAME bytes.

    `pm.md` bounds the out-of-process runs to `validate` and `report`; this drives the
    third door IN-PROCESS, which costs nothing, because acceptance criterion 2 claims the
    failure arrives at EVERY caller on the existing `problems` path.
    """
    root = _register(tmp_path, {"GAP-001.json": _raw(RECORD, {"evidence": SAME})})
    code, out, err = _run("list", root, capsys)
    assert code == 2, err
    assert out == "", f"list wrote to stdout: {out!r}"
    assert _refusal_body(err) == _dup_clause("GAP-001.json", ["evidence"])


def test_ac2_that_third_verb_still_lists_the_honest_twin(tmp_path, capsys):
    """The acceptance side of the third door: one line, one trailing newline, exit 0."""
    root = _register(tmp_path, {"GAP-001.json": json.dumps(RECORD)})
    code, out, err = _run("list", root, capsys)
    assert code == 0, err
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n"), repr(out)
    assert "GAP-001" in out, out
