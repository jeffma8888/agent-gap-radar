"""Iteration 257 behaviors: `radar prd --with-fixtures` inlines the reproduction sample.

Black-box, and the ISOLATION CONTRACT IS HONORED. Nothing here reads the implementation
source, the engineer's or reviewer's notes, or any diff. Shapes were established by
RUNNING the tool (`radar prd --help`, then `radar prd` with and without the flag over
hand-built registers) and by reading `pm.md`, `PRODUCT.md` row 54 and
`docs/CONSUMER_CONTRACT.md` -- published documents of the same class as the README.

`pm.md` was CHECKPOINTED: its `## Expected Behaviors` section reads `(refining)`, so the
numbered behaviors below are RECONSTRUCTED from the three things the spec did state -- its
`## Feature` sentence ("inlines the record's `check.fixtures` bad/good file CONTENTS into
the emitted PRD so the build-loop artifact is self-contained; default output stays
byte-identical"), its `## Why` (the loop runs in ANOTHER repo and today receives a glob),
and the two PUBLISHED cells that legislate the flag: `docs/CONSUMER_CONTRACT.md`'s `radar
prd` row and `PRODUCT.md` row 54. Where those documents are silent the most reasonable
reading is tested and the ambiguity is recorded in `tester.md`.

Structural notes, so this file cannot lie later:

* **Every "verbatim" claim is proved against bytes this module did not author.**
  Behaviors 1-8 drive registers built under `tmp_path`, where the expected bytes are this
  module's own constants -- two readings of one literal. Behavior 9 is the third opinion:
  it sweeps all 120 COMMITTED records, reads `check.fixtures` straight out of each record
  file, and requires the inlined object to equal it, so the promise is asserted over data
  no test authored.

* **Vacuity guards.** The additive claim of behavior 3 is meaningless unless the flag
  MOVES something, so `test_b0_*` pins that the two arms differ and that the fixture bytes
  appear only on the flagged one; and the no-op claim of behavior 7 is meaningless unless
  a no-op is distinguishable from silence, so it is asserted as BYTE equality against a
  document the same run also proves non-empty and exit 0.

* **`--help` and the contract are read for the flag's EXISTENCE only.** Arity and defaults
  are already legislated by `tests/_surface_contract.py`; this module does not restate
  them, it only pins that a caller can discover the flag from both surfaces.

* **No absolute machine path and no personal identifier appears here.** Registers live
  under pytest's `tmp_path`; the committed register is located relative to `__file__`. No
  test here scans a repository, so the module adds no scan-sized wall time -- the two
  sweeps over 120 records cost ~5s each, measured, because `prd` reads the register only.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from agent_gap_radar.cli import main
from test_iter02_behavior import _write_register

#: The committed register, located without an absolute path (convention:
#: tests/_key_enumeration.py:72).
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"
CONTRACT_PATH = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The keys the DEFAULT arm's `reproductionSample` has always carried, in emitted order,
#: and the two the flag APPENDS after them. Split on purpose: behavior 3 asserts the
#: flagged order is exactly the concatenation, so an insertion in the middle fails.
SAMPLE_KEYS_DEFAULT = ["recordGlob", "badFiles", "goodFiles"]
SAMPLE_KEYS_ADDED = ["badFixtures", "goodFixtures"]

#: Bytes chosen so "verbatim" is falsifiable: two files per side (so name-sorting has
#: something to sort), a nested relative path, a trailing newline, a blank line, a double
#: quote, a literal backslash escape and a non-ASCII character.
BAD = {
    "runner.py": 'import subprocess\n\n\ndef step(c):\n    return subprocess.run(c, timeout=600)  # "hard" cap\n',
    "a/nested.py": "MARK257 = 1\n",
}
GOOD = {
    "runner.py": "import subprocess\n\n\ndef step(c, out):\n    out.write_text('{}')  # checkpoint \\u2713 \u2713\n    return subprocess.run(c, timeout=600)\n",
    "a/nested.py": "clean = 2\n",
}

#: Inserted in DESCENDING key order, so "name-sorted" is a claim about the tool.
UNSORTED_BAD = {"z.py": "MARK257 z\n", "m.py": "MARK257 m\n", "a.py": "MARK257 a\n"}
UNSORTED_GOOD = {"z.py": "clean z\n", "m.py": "clean m\n", "a.py": "clean a\n"}

#: ASCII, escape-free substrings of the four fixture files above, used for raw-TEXT
#: containment where JSON escaping would otherwise make a literal needle wrong.
PROBES = ("def step(c):", "MARK257 = 1", "out.write_text", "clean = 2")

#: Two bad files against ONE good file: the per-side counts in the US-001 criterion must
#: be derived per side, not one number printed twice.
ASYM_BAD = {"pkg/b.py": "MARK257\n", "a.py": "MARK257\n"}
ASYM_GOOD = {"only_good.py": "clean\n"}


# ---------------------------------------------------------------------------
# Fixture builders. Registers are built in `tmp_path`; no committed record is
# edited to make an assertion true, and the committed ones are only READ.
# ---------------------------------------------------------------------------

def _record(gid="GAP-700", bad=None, good=None, kind="automated"):
    """A schema-valid record. `kind` selects the three sample-bearing shapes.

    `automated` carries a `present_when` plus two-sided fixtures; `manual` carries a
    check with only a question (no static signature, so no sample); `none` carries no
    check at all.
    """
    rec = {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 5, "frequency": 5, "tractability": 5,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/x",
                      "date": "2026-01-02", "quote": "the verbatim line"}],
    }
    if kind == "automated":
        rec["check"] = {
            "id": "CHK-" + gid.split("-")[-1], "rationale": "r", "manual_question": "q",
            "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                             "pattern": "MARK257"},
            "fixtures": {"bad": dict(BAD if bad is None else bad),
                         "good": dict(GOOD if good is None else good)},
        }
    elif kind == "manual":
        rec["check"] = {"id": "CHK-" + gid.split("-")[-1], "rationale": "r",
                        "manual_question": "q"}
    return rec


def _repo(tmp_path, records=None, name="repo"):
    root = tmp_path / name
    root.mkdir()
    _write_register(root, records if records is not None else [_record()])
    return root


def _prd(repo, capsys, *extra):
    """Run `radar prd <repo> [extra...]` and return (rc, stdout, stderr)."""
    rc = main(["prd", str(repo), *extra])
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _both_arms(repo, capsys, *extra):
    """The same invocation without and with `--with-fixtures`."""
    plain = _prd(repo, capsys, *extra)
    flagged = _prd(repo, capsys, *extra, "--with-fixtures")
    return plain, flagged


def _sample(text):
    return json.loads(text)["sourceGap"]["check"]["reproductionSample"]


def _transcription_criterion(text):
    """US-001's LAST acceptance criterion -- the one that names where the sample is."""
    story = json.loads(text)["stories"][0]
    assert story["id"] == "US-001", story["id"]
    return story["acceptanceCriteria"][-1]


def _run_capture(argv):
    """For the sweeps: many invocations without paying capsys per call."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def _committed_records():
    """(gap_id, record dict) for every committed record, id-sorted."""
    records = []
    for path in sorted(GAPS_DIR.glob("GAP-*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        records.append((rec["id"], rec))
    return records


# ---------------------------------------------------------------------------
# Behavior 0 -- controls. The flag must MOVE something, or every additive and
# no-op assertion below is vacuous.
# ---------------------------------------------------------------------------

def test_b0_the_two_arms_differ_and_only_the_flagged_one_carries_the_bytes(
        tmp_path, capsys):
    repo = _repo(tmp_path)
    (rc1, plain, err1), (rc2, flagged, err2) = _both_arms(repo, capsys)
    assert (rc1, err1, rc2, err2) == (0, "", 0, ""), (rc1, err1, rc2, err2)
    assert plain != flagged, "the flag changed nothing, so nothing below is tested"
    assert len(flagged) > len(plain), "an APPENDING flag cannot shrink the document"
    for probe in PROBES:
        assert probe in flagged, probe
        assert probe not in plain, f"the DEFAULT arm leaked fixture content: {probe}"


def test_b0_the_inlined_value_is_spelled_with_json_escapes_and_stays_ascii(
        tmp_path, capsys):
    """MEASURED: a quote is emitted `\\"`, U+2713 as `\\u2713`, so one raw needle is exact.

    This is the raw-TEXT half of behavior 1's verbatim promise: `json.loads` equality
    cannot tell an ASCII-safe document from one that emits the character raw, and a
    consumer reading the bytes off a pipe can.
    """
    rc, flagged, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    assert json.dumps(GOOD["runner.py"]) in flagged
    assert json.dumps(BAD["runner.py"]) in flagged
    assert flagged.isascii(), "a byte-stable document must not depend on the reader\'s codec"


def test_b0_the_default_arm_names_no_fixture_key_at_all(tmp_path, capsys):
    """The control for behavior 5: the added keys must be unreachable without the flag."""
    rc, plain, err = _prd(_repo(tmp_path), capsys)
    assert (rc, err) == (0, "")
    for key in SAMPLE_KEYS_ADDED:
        assert key not in plain, key


# ---------------------------------------------------------------------------
# Behavior 1 -- `--with-fixtures` inlines the record's `check.fixtures` CONTENTS
# as one `{relative path: content}` object per side, bytes verbatim.
# ---------------------------------------------------------------------------

def test_b1_flag_inlines_the_sample_bytes_verbatim(tmp_path, capsys):
    rc, out, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    sample = _sample(out)
    assert sample["badFixtures"] == BAD
    assert sample["goodFixtures"] == GOOD


def test_b1_each_side_is_one_flat_object_of_string_to_string(tmp_path, capsys):
    rc, out, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    sample = _sample(out)
    for key in SAMPLE_KEYS_ADDED:
        obj = sample[key]
        assert isinstance(obj, dict) and obj, (key, obj)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in obj.items()), obj


def test_b1_a_nested_relative_path_stays_the_records_own_key(tmp_path, capsys):
    """The key is the record's relative path, not a basename and not a rewritten one."""
    rc, out, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    assert "a/nested.py" in _sample(out)["badFixtures"]


def test_b1_non_ascii_and_escapes_survive_the_round_trip(tmp_path, capsys):
    rc, out, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    body = _sample(out)["goodFixtures"]["runner.py"]
    assert body == GOOD["runner.py"]
    assert "\u2713" in body and "\\u2713" in body, "one is literal, one is escaped text"
    assert "\r" not in out, "byte-stable output must not gain a carriage return"


def test_b1_a_record_with_no_sample_gains_no_fixture_key(tmp_path, capsys):
    """`reproductionSample` is `null` for a manual check, so there is nothing to inline."""
    repo = _repo(tmp_path, [_record("GAP-701", kind="manual")])
    rc, out, err = _prd(repo, capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    assert _sample(out) is None
    for key in SAMPLE_KEYS_ADDED:
        assert key not in out, key


# ---------------------------------------------------------------------------
# Behavior 2 -- the inlined keys are NAME-SORTED, and they are exactly the file
# list the default arm already published.
# ---------------------------------------------------------------------------

def test_b2_keys_are_name_sorted_whatever_order_the_record_holds(tmp_path, capsys):
    repo = _repo(tmp_path, [_record("GAP-710", UNSORTED_BAD, UNSORTED_GOOD)])
    rc, out, err = _prd(repo, capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    sample = _sample(out)
    assert list(UNSORTED_BAD) != sorted(UNSORTED_BAD), "the fixture is not a control"
    assert list(sample["badFixtures"]) == sorted(UNSORTED_BAD)
    assert list(sample["goodFixtures"]) == sorted(UNSORTED_GOOD)


def test_b2_the_inlined_keys_equal_the_published_file_lists(tmp_path, capsys):
    """`badFiles` was already name-sorted (iteration 23), so the two agree in ORDER too."""
    repo = _repo(tmp_path, [_record("GAP-711", UNSORTED_BAD, UNSORTED_GOOD)])
    rc, out, err = _prd(repo, capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    sample = _sample(out)
    assert list(sample["badFixtures"]) == sample["badFiles"]
    assert list(sample["goodFixtures"]) == sample["goodFiles"]


def test_b2_sides_are_kept_apart_when_their_file_sets_differ(tmp_path, capsys):
    repo = _repo(tmp_path, [_record("GAP-712", ASYM_BAD, ASYM_GOOD)])
    rc, out, err = _prd(repo, capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    sample = _sample(out)
    assert sample["badFixtures"] == ASYM_BAD
    assert sample["goodFixtures"] == ASYM_GOOD
    assert set(sample["badFixtures"]) & set(sample["goodFixtures"]) == set()


# ---------------------------------------------------------------------------
# Behavior 3 -- the flag APPENDS. The two keys land after the ones the default
# arm already carried, and nothing else in the document moves except US-001's
# transcription criterion (behavior 4).
# ---------------------------------------------------------------------------

def test_b3_added_keys_land_after_the_existing_ones(tmp_path, capsys):
    repo = _repo(tmp_path)
    (_, plain, _), (_, flagged, _) = _both_arms(repo, capsys)
    assert list(_sample(plain)) == SAMPLE_KEYS_DEFAULT
    assert list(_sample(flagged)) == SAMPLE_KEYS_DEFAULT + SAMPLE_KEYS_ADDED


def test_b3_the_existing_sample_entries_are_untouched(tmp_path, capsys):
    repo = _repo(tmp_path)
    (_, plain, _), (_, flagged, _) = _both_arms(repo, capsys)
    before, after = _sample(plain), _sample(flagged)
    assert {k: after[k] for k in SAMPLE_KEYS_DEFAULT} == before
    assert after["recordGlob"] == "gaps/GAP-700-*.json", after["recordGlob"]


def test_b3_nothing_else_in_the_document_moves(tmp_path, capsys):
    """Surgery test: undo the two documented additions, and the arms must be EQUAL.

    Key ORDER is compared level by level (a `json.loads` dict preserves the emitted
    order), so a re-ordered payload fails even though it would compare equal as data.
    """
    repo = _repo(tmp_path)
    (_, plain, _), (_, flagged, _) = _both_arms(repo, capsys)
    want, got = json.loads(plain), json.loads(flagged)
    assert list(want) == list(got)
    assert list(want["sourceGap"]) == list(got["sourceGap"])
    assert list(want["sourceGap"]["check"]) == list(got["sourceGap"]["check"])
    assert [list(s) for s in want["stories"]] == [list(s) for s in got["stories"]]
    # undo addition 1: the two inlined objects
    for key in SAMPLE_KEYS_ADDED:
        del got["sourceGap"]["check"]["reproductionSample"][key]
    # undo addition 2: the derived transcription criterion
    got["stories"][0]["acceptanceCriteria"][-1] = \
        want["stories"][0]["acceptanceCriteria"][-1]
    assert got == want, "the flag moved something it does not document"


def test_b3_every_other_acceptance_criterion_is_identical(tmp_path, capsys):
    repo = _repo(tmp_path)
    (_, plain, _), (_, flagged, _) = _both_arms(repo, capsys)
    a = json.loads(plain)["stories"][0]["acceptanceCriteria"]
    b = json.loads(flagged)["stories"][0]["acceptanceCriteria"]
    assert len(a) == len(b) and a[:-1] == b[:-1]
    assert a[-1] != b[-1], "the derived criterion did not move (see behavior 4)"


# ---------------------------------------------------------------------------
# Behavior 4 -- the US-001 transcription instruction is DERIVED from the payload:
# the glob on the default arm, the inlined key path on the flagged one, so a loop
# is never sent to another repo for bytes it was handed.
# ---------------------------------------------------------------------------

KEY_PATH = "sourceGap.check.reproductionSample.badFixtures and .goodFixtures"


def test_b4_default_arm_names_the_record_glob(tmp_path, capsys):
    rc, plain, err = _prd(_repo(tmp_path), capsys)
    assert (rc, err) == (0, "")
    line = _transcription_criterion(plain)
    assert "gaps/GAP-700-*.json" in line, line
    assert "badFixtures" not in line, line


def test_b4_flagged_arm_names_the_inlined_key_path_and_not_the_glob(tmp_path, capsys):
    rc, flagged, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    line = _transcription_criterion(flagged)
    assert KEY_PATH in line, line
    assert "gaps/GAP-700-*.json" not in line, (
        "the loop is still sent to another repo for bytes it was handed: " + line)


def test_b4_the_named_key_path_resolves_in_the_document_it_describes(tmp_path, capsys):
    """The instruction is only true if the path it names is actually reachable."""
    rc, flagged, err = _prd(_repo(tmp_path), capsys, "--with-fixtures")
    assert (rc, err) == (0, "")
    doc = json.loads(flagged)
    node = doc
    for step in ("sourceGap", "check", "reproductionSample", "badFixtures"):
        assert step in node, (step, list(node))
        node = node[step]
    assert node == BAD


def test_b4_per_side_counts_are_derived_per_side_on_both_arms(tmp_path, capsys):
    repo = _repo(tmp_path, [_record("GAP-712", ASYM_BAD, ASYM_GOOD)])
    (_, plain, _), (_, flagged, _) = _both_arms(repo, capsys)
    for text in (plain, flagged):
        line = _transcription_criterion(text)
        assert "2 bad file(s)" in line, line
        assert "1 good file(s)" in line, line


def test_b4_the_no_sample_arms_share_one_criterion(tmp_path, capsys):
    """With no sample there is nothing to point at, so the flag may not reword it."""
    repo = _repo(tmp_path, [_record("GAP-713", kind="none")])
    (_, plain, _), (_, flagged, _) = _both_arms(repo, capsys)
    assert _transcription_criterion(plain) == _transcription_criterion(flagged)
    assert "badFixtures" not in _transcription_criterion(flagged)


# ---------------------------------------------------------------------------
# Behavior 5 -- the default arm is unchanged, and both arms keep the published
# output contract: exit 0, stdout only, exactly one trailing newline, empty
# stderr, byte-stable across runs.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [(), ("--with-fixtures",)])
def test_b5_arm_is_byte_stable_across_runs(tmp_path, capsys, extra):
    repo = _repo(tmp_path)
    rc1, first, err1 = _prd(repo, capsys, *extra)
    rc2, second, err2 = _prd(repo, capsys, *extra)
    assert (rc1, rc2, err1, err2) == (0, 0, "", "")
    assert first == second


@pytest.mark.parametrize("extra", [(), ("--with-fixtures",)])
def test_b5_arm_ends_in_exactly_one_newline_and_carries_only_the_document(
        tmp_path, capsys, extra):
    rc, out, err = _prd(_repo(tmp_path), capsys, *extra)
    assert (rc, err) == (0, "")
    assert out.endswith("}\n") and not out.endswith("\n\n")
    assert "Error: " not in out and "Note:" not in out
    json.loads(out)


@pytest.mark.parametrize("extra", [(), ("--with-fixtures",)])
def test_b5_arm_composes_with_project_and_gap(tmp_path, capsys, extra):
    repo = _repo(tmp_path, [_record("GAP-720"), _record("GAP-721")])
    rc, out, err = _prd(repo, capsys, "--gap", "GAP-721", "--project", "other-repo",
                        *extra)
    assert (rc, err) == (0, "")
    doc = json.loads(out)
    assert doc["project"] == "other-repo"
    assert doc["sourceGap"]["id"] == "GAP-721"


def test_b5_the_flag_takes_no_value(tmp_path, capsys):
    repo = _repo(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["prd", str(repo), "--with-fixtures=1"])
    assert exc.value.code == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert cap.err.splitlines()[-1].startswith("Error: ")


# ---------------------------------------------------------------------------
# Behavior 6 -- `radar scan --prd` deliberately has no such flag: it emits the
# default arm, and the two surfaces stay byte-comparable.
# ---------------------------------------------------------------------------

def _target(root):
    t = root / "target"
    (t / "app").mkdir(parents=True)
    (t / "app" / "loop.py").write_text("MARK257\n", encoding="utf-8")
    return t


def test_b6_scan_prd_refuses_the_flag(tmp_path, capsys):
    repo = _repo(tmp_path)
    target = _target(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["scan", str(target), "--gaps", str(repo), "--prd", "--with-fixtures"])
    assert exc.value.code == 2
    cap = capsys.readouterr()
    assert cap.out == "", "a refusal may not emit half a document"
    last = [ln for ln in cap.err.splitlines() if ln.strip()][-1]
    assert last.startswith("Error: "), cap.err
    assert "--with-fixtures" in last, last
    assert cap.err.startswith("usage: "), "a structural refusal prints usage above it"


def test_b6_scan_prd_emits_the_default_arm(tmp_path, capsys):
    repo = _repo(tmp_path)
    target = _target(tmp_path)
    rc = main(["scan", str(target), "--gaps", str(repo), "--prd"])
    scanned = capsys.readouterr().out
    assert rc == 0
    sample = _sample(scanned)
    assert list(sample) == SAMPLE_KEYS_DEFAULT, sample
    assert "badFixtures" not in scanned


def test_b6_the_two_surfaces_stay_byte_comparable_on_the_check_object(tmp_path, capsys):
    repo = _repo(tmp_path)
    target = _target(tmp_path)
    assert main(["scan", str(target), "--gaps", str(repo), "--prd"]) == 0
    scanned = capsys.readouterr().out
    _, plain, _ = _prd(repo, capsys)
    assert json.dumps(json.loads(scanned)["sourceGap"]["check"]) == \
        json.dumps(json.loads(plain)["sourceGap"]["check"])


# ---------------------------------------------------------------------------
# Behavior 7 -- a record the register holds no sample for is unaffected: the flag
# is ACCEPTED and the document is BYTE-identical to the default arm.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["manual", "none"])
def test_b7_no_sample_means_the_flag_is_a_byte_level_no_op(tmp_path, capsys, kind):
    repo = _repo(tmp_path, [_record("GAP-730", kind=kind)])
    (rc1, plain, err1), (rc2, flagged, err2) = _both_arms(repo, capsys)
    assert (rc1, rc2, err1, err2) == (0, 0, "", "")
    assert plain, "a no-op claim over an empty document proves nothing"
    assert flagged == plain
    assert _sample(plain) is None


# ---------------------------------------------------------------------------
# Behavior 8 -- the flag is discoverable from both published surfaces.
# ---------------------------------------------------------------------------

def test_b8_prd_help_documents_the_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["prd", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--with-fixtures" in out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b8_the_consumer_contract_publishes_the_flag_on_the_prd_row(capsys):
    rows = [ln for ln in CONTRACT_PATH.read_text(encoding="utf-8").splitlines()
            if ln.startswith("| `radar prd")]
    assert len(rows) == 1, rows
    assert "[--with-fixtures]" in rows[0], rows[0]


# ---------------------------------------------------------------------------
# Behavior 9 -- the third opinion: over the COMMITTED register, the inlined
# object equals the bytes the record file holds, for every record.
# ---------------------------------------------------------------------------

def test_b9_committed_register_is_a_real_sweep():
    """Guard: the two sweeps below are vacuous if the register is empty or sampleless."""
    records = _committed_records()
    assert len(records) >= 100, len(records)
    with_fixtures = [g for g, r in records if r.get("check", {}).get("fixtures")]
    assert len(with_fixtures) >= 100, len(with_fixtures)
    assert len(with_fixtures) < len(records), (
        "no sampleless record left, so the no-op half of the sweep is untested")


def test_b9_every_committed_records_bytes_are_inlined_exactly(capsys):
    capsys.readouterr()
    for gap_id, rec in _committed_records():
        rc, out, err = _run_capture(
            ["prd", str(REPO_ROOT), "--gap", gap_id, "--with-fixtures"])
        assert (rc, err) == (0, ""), (gap_id, rc, err)
        sample = _sample(out)
        fixtures = rec.get("check", {}).get("fixtures")
        if not fixtures:
            assert "badFixtures" not in out, gap_id
            continue
        assert sample["badFixtures"] == fixtures["bad"], gap_id
        assert sample["goodFixtures"] == fixtures["good"], gap_id
        assert list(sample["badFixtures"]) == sorted(fixtures["bad"]), gap_id
        assert list(sample["goodFixtures"]) == sorted(fixtures["good"]), gap_id
        assert sample["badFixtures"] and sample["goodFixtures"], gap_id


def test_b9_no_committed_record_leaks_fixture_bytes_on_the_default_arm(capsys):
    capsys.readouterr()
    for gap_id, _rec in _committed_records():
        rc, out, err = _run_capture(["prd", str(REPO_ROOT), "--gap", gap_id])
        assert (rc, err) == (0, ""), (gap_id, rc, err)
        assert list(_sample(out) or SAMPLE_KEYS_DEFAULT) == SAMPLE_KEYS_DEFAULT or \
            _sample(out) is None, gap_id
        for key in SAMPLE_KEYS_ADDED:
            assert key not in out, (gap_id, key)


# ---------------------------------------------------------------------------
# Behavior 10 -- the flag opens no door: it moves no REFUSAL and its own
# spelling on the command line cannot change the bytes. An opt-in flag that
# reworded (or skipped) a selection refusal would be a second selection rule.
# ---------------------------------------------------------------------------

def test_b10_flag_position_and_repetition_do_not_change_the_bytes(tmp_path, capsys):
    """`store_true` is order- and count-insensitive, so the document must be too."""
    repo = _repo(tmp_path)
    rc1, tail, err1 = _prd(repo, capsys, "--with-fixtures")
    rc2 = main(["prd", "--with-fixtures", str(repo)])
    lead = capsys.readouterr()
    rc3, twice, err3 = _prd(repo, capsys, "--with-fixtures", "--with-fixtures")
    assert (rc1, rc2, rc3) == (0, 0, 0), (rc1, rc2, rc3)
    assert (err1, lead.err, err3) == ("", "", "")
    assert lead.out == tail, "the flag's POSITION changed the document"
    assert twice == tail, "repeating the flag changed the document"


def test_b10_a_terminal_only_register_is_refused_identically_on_both_arms(
        tmp_path, capsys):
    """The flag may not build against a record whose status says the work is done."""
    retired = {**_record("GAP-740"), "status": "retired"}
    repo = _repo(tmp_path, [retired])
    (rc1, out1, err1), (rc2, out2, err2) = _both_arms(repo, capsys)
    assert (rc1, rc2) == (2, 2), (rc1, err1, rc2, err2)
    assert (out1, out2) == ("", ""), "a refusal may not emit half a document"
    assert err1.startswith("Error: ") and err1.endswith("\n"), repr(err1)
    assert err2 == err1, "the flag reworded a refusal it does not own"
    assert "badFixtures" not in err2, err2


def test_b10_an_unknown_gap_id_is_refused_identically_on_both_arms(tmp_path, capsys):
    repo = _repo(tmp_path)
    (rc1, out1, err1), (rc2, out2, err2) = _both_arms(
        repo, capsys, "--gap", "GAP-999")
    assert (rc1, rc2) == (2, 2), (rc1, err1, rc2, err2)
    assert (out1, out2) == ("", ""), "a refusal may not emit half a document"
    assert err1.startswith("Error: ") and "GAP-999" in err1, repr(err1)
    assert err2 == err1, "the flag reworded a refusal it does not own"
