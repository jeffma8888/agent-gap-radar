"""Iteration 216 -- the ingest door's duplicate-lookalike ADVISORY must consult the
REGISTER, not only the batch a candidate happens to arrive in.

Both BLOCKING gates at that door are seeded from the committed register; the one
advisory was scoped to the batch, so in the ordinary one-candidate batch it was
vacuous by construction (a one-element list has no pairs) and a candidate that
restated a committed record produced zero lines.

Black-box, offline, deterministic: every behaviour is observed through
`tools/promote.py` (in-process `main(argv)`, plus one subprocess for the exit code)
over a `tmp_path` inbox and a `tmp_path` register, DRY RUN -- no `--apply`, so the
real `gaps/` directory is never read and never written.

Fixture rule (from the spec's fixture notes): the token rule reads `title`,
`problem` and `symptom` ONLY, so prose overlap is placed by SHARING WORDS there
while every record carries a detector nothing else can stand in for -- which keeps
the pair a text lookalike and not a twin, and keeps the candidate ACCEPTed. Every
containment this file depends on is COMPUTED with the tool's own token rule and
asserted as a precondition, never hardcoded: a fixture that drifts must fail as a
fixture, not as a product defect.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "promote.py"

sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

import promote  # noqa: E402

NOTE_PREFIX = "NOTE    advisory lookalike, nothing was refused for this: "
IN_REGISTER = "(already in the register)"
SUMMARY = "1 accepted, 0 rejected  (dry run - pass --apply to write)"

# Disjoint vocabularies. Overlap is engineered by taking a prefix of CORE into a
# register record's word list, so containment is `shared / min(len)` on purpose.
CORE = ["retrieval", "tenant", "scoping", "documents", "shared",
        "vectorstore", "operator", "dashboard", "alerts"]
P1 = ["ledger", "provenance", "quota", "rollback", "telemetry",
      "watchdog", "beacon", "manifest", "cursor", "shard"]
P2 = ["jitter", "backoff", "throttle", "sandbox", "escalation",
      "arbiter", "digest", "harness", "lineage", "checkpoint"]
P3 = ["replay", "handoff", "schema", "transcript", "budget",
      "meter", "tracer", "sampler", "emitter", "reaper"]
P4 = ["gateway", "broker", "tunnel", "affinity", "cadence",
      "quorum", "lease", "stanza", "fanout", "cutover"]
P5 = ["pruner", "sifter", "vault", "spool", "warden",
      "relay", "panel", "probe", "atlas", "wharf"]


def _reg_words(pool: list[str], shared: int) -> list[str]:
    """A 12-word register record sharing `shared` words with CORE.

    The pool words come FIRST so each record's title is its own.
    """
    return pool[: 12 - shared] + CORE[:shared]


class _Prose:
    """The three fields the token rule reads, and nothing else."""

    def __init__(self, title: str, problem: str, symptom: str) -> None:
        self.title, self.problem, self.symptom = title, problem, symptom


def _prose(words: list[str], title_words: int = 3) -> dict:
    return {
        "title": " ".join(words[:title_words]),
        "problem": " ".join(words[:6]),
        "symptom": " ".join(words[3:]),
    }


def _tokens(words: list[str]) -> set[str]:
    return promote._lookalike_tokens(_Prose(**_prose(words)))


def _ov(a: list[str], b: list[str]) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / min(len(ta), len(tb))


def _check(marker: str) -> dict:
    """A detector no other fixture's detector fires on, so nothing is a twin."""
    return {
        "id": "CHK-900",
        "rationale": "r",
        "manual_question": "q",
        "present_when": {
            "kind": "content_matches",
            "globs": ["**/*.py"],
            "pattern": marker,
        },
        "fixtures": {"bad": {"a.py": f"# {marker}\n"}, "good": {"a.py": "pass\n"}},
    }


def _doc(words: list[str], marker: str, *, title_words: int = 3,
         severity: int = 3, frequency: int = 3, tractability: int = 3,
         **overrides) -> dict:
    doc = {
        "id": "GAP-900",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "status": "open",
        "why_now": "w",
        "severity": severity,
        "frequency": frequency,
        "tractability": tractability,
        "evidence": [
            {
                "source_class": "vendor-primary",
                "title": "A page that was actually fetched",
                "locator": "https://example.com/a",
                "date": "2026-01-01",
                "quote": "one two three four five six seven",
            }
        ],
        "build_hypothesis": "b",
        "check": _check(marker),
    }
    doc.update(_prose(words, title_words))
    doc.update(overrides)
    return doc


def _register(tmp_path: Path, records: list[tuple[str, list[str], str]]) -> Path:
    gaps = tmp_path / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    for gid, words, marker in records:
        doc = _doc(words, marker, id=gid)
        doc["check"]["id"] = "CHK-" + gid.split("-")[1]
        (gaps / f"{gid}-fixture.json").write_text(json.dumps(doc), encoding="utf-8")
    return gaps


def _inbox(tmp_path: Path, candidates: dict[str, dict]) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name, doc in candidates.items():
        (inbox / name).write_text(json.dumps(doc), encoding="utf-8")
    return inbox


def _run(tmp_path: Path, candidates: dict[str, dict], gaps: Path | None = None):
    """(rc, stdout, stderr) from a DRY RUN over a tmp inbox and tmp register."""
    inbox = _inbox(tmp_path, candidates)
    if gaps is None:
        gaps = tmp_path / "gaps"
        gaps.mkdir(parents=True, exist_ok=True)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = promote.main(["--inbox", str(inbox), "--gaps", str(gaps)])
    return rc, out.getvalue(), err.getvalue()


def _notes(out: str) -> list[str]:
    """Advisory lines with the fixed prefix stripped, in printed order."""
    return [ln[len(NOTE_PREFIX):] for ln in out.splitlines()
            if ln.startswith(NOTE_PREFIX)]


def _ids(out: str) -> dict[str, str]:
    """Candidate file name -> the gap id it was ACCEPTed as."""
    found = {}
    for line in out.splitlines():
        m = re.match(r"ACCEPT\s+(\S+) -> (GAP-\d{3})", line)
        if m:
            found[Path(m.group(1)).name] = m.group(2)
    return found


def _parse(note: str) -> tuple[float, str, str, str]:
    """(overlap, subject id, partner id, tail) from one advisory line."""
    m = re.match(r"^(\d\.\d\d)  (GAP-\d{3}) most resembles (GAP-\d{3})\b(.*)$", note)
    assert m, f"advisory line does not carry the documented shape: {note!r}"
    return float(m.group(1)), m.group(2), m.group(3), m.group(4)


REG_HIGH = _reg_words(P1, 5)   # 5/9 against CORE
REG_MID = _reg_words(P2, 3)    # 3/9 against CORE
REG_LOW = _reg_words(P3, 2)    # 2/9 against CORE
LONG_TITLE = " ".join(CORE)    # > 56 chars, so the truncation is exercised


# ---------------------------------------------------------------------------
# 1. REGISTER PARTNER FOUND AND MARKED
# ---------------------------------------------------------------------------
def test_b1_a_committed_record_is_named_as_the_partner_and_marked(tmp_path):
    ov = _ov(CORE, REG_HIGH)
    assert ov >= promote._LOOKALIKE_AT, (
        f"precondition: the pair must be at or above the threshold, "
        f"got {ov:.3f} against {promote._LOOKALIKE_AT}")
    assert len(LONG_TITLE) > 56, (
        "precondition: the candidate title must be long enough to truncate")
    assert (len(_tokens(CORE)), len(_tokens(REG_HIGH))) == (9, 12), (
        "precondition: the token rule must still read these fixtures as 9 and 12 tokens")
    assert f"{ov:.2f}" == "0.56", (
        f"precondition: 5 shared of min(9, 12) is 0.56, computed {ov:.6f} -- the printed "
        "number is pinned to a LITERAL here so a changed token rule cannot move the "
        "expectation and the product together and stay green")
    gaps = _register(tmp_path, [("GAP-401", REG_HIGH, "reg_high")])
    rc, out, err = _run(
        tmp_path, {"c.json": _doc(CORE, "cand_core", title_words=len(CORE))}, gaps)
    assert rc == 0, err
    notes = _notes(out)
    assert len(notes) == 1, (
        f"a candidate restating a committed record must be reported exactly once:\n{out}")
    cid = _ids(out).get("c.json")
    assert cid, f"the candidate must still be ACCEPTed:\n{out}"
    assert notes[0] == (
        f"{ov:.2f}  {cid} most resembles GAP-401 (already in the register): "
        f"{LONG_TITLE[:56]!r} / {' '.join(REG_HIGH[:3])[:56]!r}"), notes[0]


# ---------------------------------------------------------------------------
# 2. NON-VACUITY, BOTH SIDES
# ---------------------------------------------------------------------------
def test_b2_the_same_lone_candidate_is_silent_on_an_empty_register(tmp_path):
    """One-sided: an empty register must produce nothing."""
    cand = {"c.json": _doc(CORE, "cand_core", title_words=len(CORE))}
    rc, out, _ = _run(tmp_path / "empty", cand)
    assert rc == 0
    assert _ids(out).get("c.json"), out
    assert _notes(out) == [], (
        f"nothing to resemble, so nothing may be reported:\n{out}")


def test_b2_the_same_lone_candidate_speaks_once_when_the_record_exists(tmp_path):
    """The other side: the ONLY difference is one file in the register."""
    cand = {"c.json": _doc(CORE, "cand_core", title_words=len(CORE))}
    gaps = _register(tmp_path, [("GAP-401", REG_HIGH, "reg_high")])
    rc, out, _ = _run(tmp_path / "seeded", cand, gaps)
    assert rc == 0
    assert len(_notes(out)) == 1, out


# ---------------------------------------------------------------------------
# 3. BOUNDED BY THE BATCH, NOT THE REGISTER
# ---------------------------------------------------------------------------
def test_b3_one_line_per_record_naming_the_strongest_register_partner(tmp_path):
    hi, mid, lo = _ov(CORE, REG_HIGH), _ov(CORE, REG_MID), _ov(CORE, REG_LOW)
    assert hi > mid > lo >= promote._LOOKALIKE_AT, (
        "precondition: three DIFFERENT containments, all at or above the threshold, "
        f"got {hi:.3f} {mid:.3f} {lo:.3f} against {promote._LOOKALIKE_AT}")
    gaps = _register(tmp_path, [
        ("GAP-401", REG_HIGH, "reg_high"),
        ("GAP-402", REG_MID, "reg_mid"),
        ("GAP-403", REG_LOW, "reg_low"),
    ])
    rc, out, err = _run(tmp_path, {"c.json": _doc(CORE, "cand_core")}, gaps)
    assert rc == 0, err
    notes = _notes(out)
    assert len(notes) == 1, (
        f"three partners are still ONE record, so still one line:\n{out}")
    overlap, subject, partner, _tail = _parse(notes[0])
    assert subject == _ids(out)["c.json"], notes[0]
    assert partner == "GAP-401", (
        f"the STRONGEST register partner is GAP-401 at {hi:.2f}, "
        f"not GAP-402 at {mid:.2f} or GAP-403 at {lo:.2f}: {notes[0]}")
    assert overlap == float(f"{hi:.2f}"), notes[0]


# ---------------------------------------------------------------------------
# 4. REGISTER RECORDS ARE NEVER SUBJECTS
# ---------------------------------------------------------------------------
def test_b4_a_pair_that_is_entirely_inside_the_register_is_not_reported(tmp_path):
    """The advisory is about what is ARRIVING. Reporting the register against
    itself would print 75 lines on every single-candidate run."""
    ra = P4[:6] + P5[:6]
    rb = P4[:6] + P1[:6]
    cand_words = CORE[:7] + [P5[0], P1[0]]
    assert _ov(ra, rb) >= promote._LOOKALIKE_AT, (
        f"precondition: the two committed records must be lookalikes, got {_ov(ra, rb):.3f}")
    for other in (ra, rb):
        got = _ov(cand_words, other)
        assert 0 < got < promote._LOOKALIKE_AT, (
            "precondition: the candidate needs a NON-ZERO overlap under the threshold "
            f"(zero would pass even with the threshold at zero), got {got:.3f}")
    gaps = _register(tmp_path, [("GAP-401", ra, "reg_a"), ("GAP-402", rb, "reg_b")])
    rc, out, err = _run(tmp_path, {"c.json": _doc(cand_words, "cand_quiet")}, gaps)
    assert rc == 0, err
    assert _ids(out).get("c.json"), out
    assert _notes(out) == [], (
        f"neither committed record may be the SUBJECT of an advisory line:\n{out}")


# ---------------------------------------------------------------------------
# 5. AN IN-BATCH PARTNER KEEPS THE ITERATION-215 SPELLING
# ---------------------------------------------------------------------------
def test_b5_an_in_batch_partner_carries_no_marker_and_the_old_format(tmp_path):
    a_words, b_words = CORE, P2[:8] + CORE[:4]
    ov = _ov(a_words, b_words)
    assert ov >= promote._LOOKALIKE_AT, f"precondition: got {ov:.3f}"
    rc, out, err = _run(tmp_path, {
        "a.json": _doc(a_words, "cand_a"),
        "b.json": _doc(b_words, "cand_b"),
    })
    assert rc == 0, err
    notes = _notes(out)
    assert len(notes) == 1, f"a mutual pair prints once, not twice:\n{out}"
    assert IN_REGISTER not in notes[0], (
        f"neither partner is in the register, so the marker must be absent: {notes[0]}")
    overlap, subject, partner, _tail = _parse(notes[0])
    titles = {_ids(out)["a.json"]: " ".join(a_words[:3]),
              _ids(out)["b.json"]: " ".join(b_words[:3])}
    assert {subject, partner} == set(titles), notes[0]
    assert notes[0] == (f"{ov:.2f}  {subject} most resembles {partner}: "
                        f"{titles[subject][:56]!r} / {titles[partner][:56]!r}"), notes[0]


# ---------------------------------------------------------------------------
# 6. ADVISORY, NEVER BLOCKING
# ---------------------------------------------------------------------------
def test_b6_the_register_aware_advisory_refuses_nothing(tmp_path):
    gaps1 = _register(tmp_path / "one", [("GAP-401", REG_HIGH, "reg_high")])
    gaps3 = _register(tmp_path / "three", [
        ("GAP-401", REG_HIGH, "reg_high"),
        ("GAP-402", REG_MID, "reg_mid"),
        ("GAP-403", REG_LOW, "reg_low"),
    ])
    for label, gaps in (("behaviour 1", gaps1), ("behaviour 3", gaps3)):
        rc, out, err = _run(tmp_path / label.replace(" ", "_"),
                            {"c.json": _doc(CORE, "cand_core")}, gaps)
        assert rc == 0, f"{label}: rc={rc} err={err!r}"
        assert _ids(out).get("c.json"), f"{label}: no ACCEPT line:\n{out}"
        assert [ln for ln in out.splitlines() if ln.startswith("ACCEPT")], out
        assert not [ln for ln in out.splitlines() if ln.startswith("REJECT")], (
            f"{label}: an advisory may never refuse:\n{out}")
        assert SUMMARY in out.splitlines(), (
            f"{label}: the summary line must be untouched:\n{out}")
        assert not [ln for ln in err.splitlines() if ln.startswith("Error: ")], err


def test_b6_the_exit_code_and_stderr_are_untouched_as_a_script(tmp_path):
    """The in-process route cannot see the process exit code."""
    gaps = _register(tmp_path, [("GAP-401", REG_HIGH, "reg_high")])
    inbox = _inbox(tmp_path, {"c.json": _doc(CORE, "cand_core")})
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--inbox", str(inbox), "--gaps", str(gaps)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert len(_notes(proc.stdout)) == 1, proc.stdout
    assert IN_REGISTER in proc.stdout, proc.stdout
    assert SUMMARY in proc.stdout.splitlines(), proc.stdout
    assert not [ln for ln in proc.stderr.splitlines() if ln.startswith("Error: ")], proc.stderr


# ---------------------------------------------------------------------------
# 7. DETERMINISM AND ORDER
# ---------------------------------------------------------------------------
def test_b7_two_runs_over_one_inbox_and_register_are_byte_identical(tmp_path):
    gaps = _register(tmp_path, [
        ("GAP-401", REG_HIGH, "reg_high"),
        ("GAP-402", REG_MID, "reg_mid"),
    ])
    cands = {"c.json": _doc(CORE, "cand_core"),
             "d.json": _doc(P2[:9], "cand_p2")}
    _rc1, first, _e1 = _run(tmp_path, cands, gaps)
    _rc2, second, _e2 = _run(tmp_path, cands, gaps)
    assert first == second, "stdout is not byte-stable across two identical runs"


def test_b7_advisory_lines_sort_by_descending_containment(tmp_path):
    """Non-vacuous by construction: the WEAKER pair holds the LOWER subject id and
    the earlier file name, so descending containment is the only rule that puts the
    strong pair first."""
    strong_words, weak_words = CORE, P2[:9]
    strong_partner, weak_partner = _reg_words(P1, 5), _reg_words(P3, 0) + P2[:2]
    strong = _ov(strong_words, strong_partner)
    weak = _ov(weak_words, weak_partner)
    assert strong > weak >= promote._LOOKALIKE_AT, (
        f"precondition: two DIFFERENT containments above the threshold, "
        f"got {strong:.3f} and {weak:.3f}")
    assert _ov(strong_words, weak_words) < promote._LOOKALIKE_AT, (
        "precondition: the two candidates must not be each other's partner")
    gaps = _register(tmp_path, [("GAP-401", strong_partner, "reg_strong"),
                                ("GAP-402", weak_partner, "reg_weak")])
    rc, out, err = _run(tmp_path, {
        # a_* sorts first by file name and carries the higher priority, so it is
        # ranked first and handed the LOWER id -- and it is the WEAK pair.
        "a_weak.json": _doc(weak_words, "cand_weak", severity=5, frequency=5,
                            tractability=5),
        "z_strong.json": _doc(strong_words, "cand_strong", severity=1, frequency=1,
                              tractability=1),
    }, gaps)
    assert rc == 0, err
    ids = _ids(out)
    assert len(ids) == 2, out
    notes = _notes(out)
    assert len(notes) == 2, f"one line per accepted record:\n{out}"
    assert ids["z_strong.json"] > ids["a_weak.json"], (
        f"precondition: the strong pair must hold the HIGHER id, got {ids}")
    assert [_parse(n)[1] for n in notes] == [ids["z_strong.json"], ids["a_weak.json"]], (
        f"lines must run strongest first:\n" + "\n".join(notes))
    assert [_parse(n)[0] for n in notes] == [float(f"{strong:.2f}"), float(f"{weak:.2f}")], notes


def test_b7_a_containment_tie_breaks_on_ascending_subject_id(tmp_path):
    """Both pairs sit at the SAME containment, and the lower id belongs to the file
    that sorts LAST by name, so an id tie-break is distinguishable from file order."""
    first_words, second_words = CORE, P2[:9]
    pa, pb = _reg_words(P1, 2), _reg_words(P3, 0) + P2[:2]
    ova, ovb = _ov(first_words, pa), _ov(second_words, pb)
    assert ova == ovb >= promote._LOOKALIKE_AT, (
        f"precondition: the two containments must TIE, got {ova:.3f} and {ovb:.3f}")
    gaps = _register(tmp_path, [("GAP-401", pa, "reg_pa"), ("GAP-402", pb, "reg_pb")])
    rc, out, err = _run(tmp_path, {
        "a_late.json": _doc(first_words, "cand_first", severity=1, frequency=1,
                            tractability=1),
        "z_early.json": _doc(second_words, "cand_second", severity=5, frequency=5,
                             tractability=5),
    }, gaps)
    assert rc == 0, err
    ids = _ids(out)
    notes = _notes(out)
    assert len(notes) == 2, f"one line per accepted record:\n{out}"
    assert ids["z_early.json"] < ids["a_late.json"], (
        f"precondition: the LAST file by name must hold the lower id, got {ids}")
    subjects = [_parse(n)[1] for n in notes]
    assert subjects == sorted(subjects), (
        "a tie must break on ASCENDING subject id:\n" + "\n".join(notes))
    assert subjects == [ids["z_early.json"], ids["a_late.json"]], (
        "\n".join(notes) + f"\n{ids}")


# ---------------------------------------------------------------------------
# 8. ONE THRESHOLD, ONE TOKEN RULE, READ AT CALL TIME
# ---------------------------------------------------------------------------
def test_b8_the_register_path_reads_the_one_threshold_at_call_time(tmp_path, monkeypatch):
    ov = _ov(CORE, REG_HIGH)
    gaps = _register(tmp_path, [("GAP-401", REG_HIGH, "reg_high")])
    cand = {"c.json": _doc(CORE, "cand_core")}

    monkeypatch.setattr(promote, "_LOOKALIKE_AT", ov + 0.05)
    _rc, above, _err = _run(tmp_path / "above", cand, gaps)
    assert _notes(above) == [], (
        f"raising the one threshold above {ov:.3f} must silence the register path:\n{above}")

    monkeypatch.setattr(promote, "_LOOKALIKE_AT", ov - 0.05)
    _rc, below, _err = _run(tmp_path / "below", cand, gaps)
    assert len(_notes(below)) == 1, (
        f"lowering it must restore the same line, so there is no second copy of the "
        f"threshold:\n{below}")
    assert IN_REGISTER in below, below


# ---------------------------------------------------------------------------
# 1 + 3 + 5 CROSSED: the corpus is the UNION, and the strongest wins in BOTH
# directions.  Acceptance criterion 1 says the search runs across (the rest of
# the batch) UNION (every record in the register); a register-ONLY search and a
# batch-ONLY search each pass every single-source behaviour above, so the only
# assertion that separates them puts a partner on BOTH sides at once and asks
# which one is named.
# ---------------------------------------------------------------------------
BATCH_HIGH = _reg_words(P4, 5)   # 5/9 against CORE -> 0.56, a BATCH candidate
BATCH_LOW = _reg_words(P5, 2)    # 2/9 against CORE -> 0.22, a BATCH candidate


def test_union_a_stronger_batch_partner_beats_a_weaker_register_partner(tmp_path):
    """CORE's best is in the BATCH (0.56); the register holds a weaker one (0.22)."""
    strong, weak = _ov(CORE, BATCH_HIGH), _ov(CORE, REG_LOW)
    assert strong > weak >= promote._LOOKALIKE_AT, (
        f"precondition: batch {strong:.3f} must beat register {weak:.3f}, both at or "
        f"above {promote._LOOKALIKE_AT}")
    assert _ov(BATCH_HIGH, REG_LOW) < promote._LOOKALIKE_AT, (
        "precondition: the two non-subjects must not see each other")
    gaps = _register(tmp_path, [("GAP-401", REG_LOW, "reg_low")])
    rc, out, err = _run(tmp_path, {
        "c.json": _doc(CORE, "cand_core"),
        "d.json": _doc(BATCH_HIGH, "cand_batch_high"),
    }, gaps)
    assert rc == 0, err
    ids = _ids(out)
    assert len(ids) == 2, f"both candidates must be ACCEPTed:\n{out}"
    notes = _notes(out)
    assert len(notes) == 1, (
        f"a mutually-closest batch pair is reported once, and the weaker register "
        f"record must not add a second line:\n{out}")
    ov, subject, partner, tail = _parse(notes[0])
    assert ov == round(strong, 2), notes[0]
    assert {subject, partner} == {ids["c.json"], ids["d.json"]}, notes[0]
    assert IN_REGISTER not in notes[0], (
        f"the named partner is in the batch, so it must carry no register marker: "
        f"{notes[0]!r}")


def test_union_a_stronger_register_partner_beats_a_weaker_batch_partner(tmp_path):
    """The mirror: CORE's best is COMMITTED (0.56), its batch partner is 0.22."""
    strong, weak = _ov(CORE, REG_HIGH), _ov(CORE, BATCH_LOW)
    assert strong > weak >= promote._LOOKALIKE_AT, (
        f"precondition: register {strong:.3f} must beat batch {weak:.3f}, both at or "
        f"above {promote._LOOKALIKE_AT}")
    assert _ov(BATCH_LOW, REG_HIGH) < promote._LOOKALIKE_AT, (
        "precondition: the two non-subjects must not see each other")
    gaps = _register(tmp_path, [("GAP-401", REG_HIGH, "reg_high")])
    rc, out, err = _run(tmp_path, {
        "c.json": _doc(CORE, "cand_core"),
        "d.json": _doc(BATCH_LOW, "cand_batch_low"),
    }, gaps)
    assert rc == 0, err
    ids = _ids(out)
    assert len(ids) == 2, f"both candidates must be ACCEPTed:\n{out}"
    notes = _notes(out)
    parsed = [_parse(n) for n in notes]
    by_subject = {p[1]: p for p in parsed}
    assert len(by_subject) == len(parsed), (
        f"at most ONE advisory line per accepted record:\n{out}")
    core = by_subject.get(ids["c.json"])
    assert core, f"the subject whose best partner is committed must be reported:\n{out}"
    assert (core[0], core[2]) == (round(strong, 2), "GAP-401"), notes
    assert IN_REGISTER in f"{core[0]:.2f}  {core[1]} most resembles {core[2]}{core[3]}", (
        f"a committed partner must carry the marker: {notes}")
    assert sum(IN_REGISTER in n for n in notes) == 1, (
        f"only the committed partner carries the marker:\n{out}")
    assert [p[0] for p in parsed] == sorted((p[0] for p in parsed), reverse=True), (
        f"lines must stay in descending containment order:\n{out}")


# ---------------------------------------------------------------------------
# 9. NOTHING ELSE MOVED
#
#    A pre-commit process check, so it is pinned to this iteration's baseline
#    commit and RETIRES ITSELF once the tree moves past it -- a permanently
#    live `git status` assertion would fail every future iteration whose
#    engineer legitimately edits `src/`.
# ---------------------------------------------------------------------------
BASELINE_SHA = "734a21e"          # iteration 215's ship commit = iter 216's pre-change tree
PROTECTED = ("src", "gaps", "docs", "README.md")
TOUCHABLE = ("tools/", "tests/", "PRODUCT.md")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=True).stdout


def test_b9_no_protected_path_moved_while_this_iteration_is_in_flight():
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    head = _git("rev-parse", f"--short={len(BASELINE_SHA)}", "HEAD").strip()
    if head != BASELINE_SHA:
        pytest.skip(
            f"behaviour 9 is a PRE-COMMIT check against baseline {BASELINE_SHA}; "
            f"HEAD is now {head}, so the comparison no longer describes this change")
    dirty = _git("status", "--porcelain", "--", *PROTECTED)
    assert dirty == "", (
        f"iteration 216 changes zero bytes under {', '.join(PROTECTED)}; git reports:\n"
        f"{dirty}")
    changed = sorted(ln[3:].strip().strip('"') for ln in _git("status", "--porcelain").splitlines())
    stray = [p for p in changed if not p.startswith(TOUCHABLE)]
    assert stray == [], (
        f"only {', '.join(TOUCHABLE)} may move this iteration; also touched: {stray}")
