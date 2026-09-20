"""Iteration 265 behavior tests (black-box; spec: state/iter-265/pm.md).

Feature: ``scan --json`` publishes pure ``path:line`` locators in each finding's
``locations`` array and moves the checks' prose notes (the ``(+N more matches...)``
ranking remainder and the ``(no match) searched ...`` / ``(no files) searched ...``
diagnostics) to an APPENDED sibling key ``location_notes``. The markdown brief is
unchanged byte for byte.

ISOLATION CONTRACT HONORED: nothing here read ``src/``, the engineer's or reviewer's
notes, or a diff of any source file. Expectations come from ``pm.md`` (and the scout
measurement it cites); shapes were measured by RUNNING the tool and by reading files
under ``tests/`` and the published ``docs/CONSUMER_CONTRACT.md``.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO_ROOT / "gaps"

LOCATOR = re.compile(r"^[^\n]+:\d+$")


def _radar(*argv: str, cwd: pathlib.Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")


@pytest.fixture(scope="module")
def self_scan_json() -> dict:
    proc = _radar("scan", ".", "--gaps", "gaps", "--json")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_iter265_b1_every_locations_element_is_a_pure_locator(self_scan_json) -> None:
    """Behavior 1: no prose survives in ``locations`` on the self-scan."""
    offenders = [(f["gap_id"], loc) for f in self_scan_json["findings"]
                 for loc in f["locations"] if not LOCATOR.match(loc)]
    assert offenders == [], offenders


# --------------------------------------------------------------------------------------
# Shared shapes (measured by RUNNING the tool; pm.md names the three prose dialects)
# --------------------------------------------------------------------------------------

#: The commit immediately before this iteration's change (control arm, iter-264 recipe).
PRECHANGE_COMMIT = "a4193db"

NOTE_DIALECTS = (
    re.compile(r"^\(\+\d+ more matches(, \d+ in test files)?\)$"),
    re.compile(r"^\(no match\) searched .+ for /.+/$", re.DOTALL),
    re.compile(r"^\(no files\) searched .+$", re.DOTALL),
)

CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"


def _is_note(text: str) -> bool:
    return any(d.match(text) for d in NOTE_DIALECTS)


@pytest.fixture(scope="module")
def prechange_src(tmp_path_factory) -> pathlib.Path:
    """``git archive PRECHANGE_COMMIT src`` under a tmp dir, probed to be what is imported."""
    import io
    import tarfile

    root = tmp_path_factory.mktemp("prechange265")
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", PRECHANGE_COMMIT, "src"], capture_output=True)
    assert archive.returncode == 0, archive.stderr.decode("utf-8", "replace")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(root, filter="data")
    src = root / "src"
    probe = subprocess.run(
        [sys.executable, "-c", "import agent_gap_radar; print(agent_gap_radar.__file__)"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=_env(src))
    assert probe.returncode == 0, probe.stderr
    assert probe.stdout.strip().startswith(str(src)), probe.stdout
    return src


def _env(src: pathlib.Path) -> dict:
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    return env


def _radar_bytes(*argv: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        cwd=str(REPO_ROOT), capture_output=True, env=env)


@pytest.fixture(scope="module")
def prechange_scan_json(prechange_src) -> dict:
    proc = _radar_bytes("scan", ".", "--gaps", "gaps", "--json", env=_env(prechange_src))
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.decode("utf-8"))


# --------------------------------------------------------------------------------------
# Behavior 2 -- ``location_notes`` is an APPENDED sibling key on every finding
# --------------------------------------------------------------------------------------

def test_iter265_b2_every_finding_carries_location_notes_as_a_list_of_strings(
        self_scan_json) -> None:
    findings = self_scan_json["findings"]
    assert findings, "the self-scan produced no findings"
    for f in findings:
        assert "location_notes" in f, f["gap_id"]
        assert isinstance(f["location_notes"], list), f["gap_id"]
        assert all(isinstance(n, str) for n in f["location_notes"]), f["gap_id"]


def test_iter265_b2_location_notes_is_appended_last_and_prior_keys_keep_their_order(
        self_scan_json, prechange_scan_json) -> None:
    """Additive only: every pre-change key keeps its index; the new key is the tail."""
    for before, now in zip(prechange_scan_json["findings"], self_scan_json["findings"]):
        assert now["gap_id"] == before["gap_id"]
        assert list(now.keys()) == list(before.keys()) + ["location_notes"], list(now.keys())


def test_iter265_b2_every_note_is_one_of_the_three_prose_dialects(self_scan_json) -> None:
    notes = [(f["gap_id"], n) for f in self_scan_json["findings"] for n in f["location_notes"]]
    assert notes, "the self-scan carried no notes at all; the fixture lost its signal"
    offenders = [(g, n[:80]) for g, n in notes if not _is_note(n)]
    assert offenders == [], offenders
    assert all(not LOCATOR.match(n) for _, n in notes)


# --------------------------------------------------------------------------------------
# Behavior 3 -- the two arrays PARTITION the pre-change list, in order, nothing dropped
# --------------------------------------------------------------------------------------

def test_iter265_b3_locations_and_notes_partition_the_prechange_list_in_order(
        self_scan_json, prechange_scan_json) -> None:
    before_f = prechange_scan_json["findings"]
    now_f = self_scan_json["findings"]
    assert [f["gap_id"] for f in before_f] == [f["gap_id"] for f in now_f]
    for before, now in zip(before_f, now_f):
        old = before["locations"]
        assert [x for x in old if LOCATOR.match(x)] == now["locations"], before["gap_id"]
        assert [x for x in old if not LOCATOR.match(x)] == now["location_notes"], before["gap_id"]
        assert len(old) == len(now["locations"]) + len(now["location_notes"])


def test_iter265_b3_two_sided_the_prechange_tree_mixed_prose_into_locations(
        prechange_scan_json) -> None:
    """The control arm is proven OLD: it had no ``location_notes`` and prose in ``locations``."""
    findings = prechange_scan_json["findings"]
    assert all("location_notes" not in f for f in findings)
    prose = [x for f in findings for x in f["locations"] if not LOCATOR.match(x)]
    assert prose, "the pre-change payload had no prose in locations; the arm is not old"
    present_tails = [f["locations"][-1] for f in findings
                     if f["verdict"] == "PRESENT" and f["locations"]]
    assert present_tails and all(_is_note(t) for t in present_tails), present_tails


def test_iter265_b3_every_other_finding_key_and_the_top_level_are_unchanged(
        self_scan_json, prechange_scan_json) -> None:
    strip = {"locations", "location_notes"}
    for before, now in zip(prechange_scan_json["findings"], self_scan_json["findings"]):
        assert {k: v for k, v in before.items() if k not in strip} == \
               {k: v for k, v in now.items() if k not in strip}, before["gap_id"]
    assert {k: v for k, v in prechange_scan_json.items() if k != "findings"} == \
           {k: v for k, v in self_scan_json.items() if k != "findings"}


# --------------------------------------------------------------------------------------
# Behavior 4 -- the markdown brief is byte-identical to the pre-change tree
# --------------------------------------------------------------------------------------

def test_iter265_b4_markdown_brief_is_byte_identical_to_the_prechange_tree(
        prechange_src) -> None:
    now = _radar_bytes("scan", ".", "--gaps", "gaps")
    before = _radar_bytes("scan", ".", "--gaps", "gaps", env=_env(prechange_src))
    assert now.returncode == before.returncode == 0, (now.stderr, before.stderr)
    assert now.stdout == before.stdout, (len(before.stdout), len(now.stdout))
    assert now.stdout.endswith(b"\n") and not now.stdout.endswith(b"\n\n")


def test_iter265_b4_markdown_still_renders_the_notes_inline(self_scan_json) -> None:
    """Only the machine payload separates them; the brief keeps the prose beside locators."""
    md = _radar_bytes("scan", ".", "--gaps", "gaps").stdout.decode("utf-8")
    # The brief renders evidence for PRESENT findings only (measured on the pre-change tree too).
    notes = [n for f in self_scan_json["findings"] if f["verdict"] == "PRESENT"
             for n in f["location_notes"]]
    assert notes
    missing = [n[:60] for n in notes if n not in md]
    assert missing == [], missing


# --------------------------------------------------------------------------------------
# Behavior 5 -- payload hygiene survives: byte-stable, one newline, stdout only
# --------------------------------------------------------------------------------------

def test_iter265_b5_scan_json_is_byte_stable_and_ends_in_exactly_one_newline() -> None:
    first = _radar_bytes("scan", ".", "--gaps", "gaps", "--json")
    second = _radar_bytes("scan", ".", "--gaps", "gaps", "--json")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stderr == b""
    assert first.stdout.endswith(b"\n") and not first.stdout.endswith(b"\n\n")
    json.loads(first.stdout.decode("utf-8"))


# --------------------------------------------------------------------------------------
# Behavior 6 -- the contract publishes the shape
# --------------------------------------------------------------------------------------

def test_iter265_b6_contract_lists_location_notes_and_the_locator_shape(self_scan_json) -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "`location_notes`" in text
    assert re.search(r"Every element of `locations` is a\s+`path:line` locator", text), \
        "the contract does not state the locator shape of `locations`"
    keys = list(self_scan_json["findings"][0].keys())
    for key in keys:
        assert f"`{key}`" in text, key


# --------------------------------------------------------------------------------------
# Behaviors 7-10 (tester-retry round) -- the split holds OFF the self-scan, on planted
# targets that drive each prose dialect deliberately. The self-scan is a moving corpus;
# these fixtures are not, so a regression in the split cannot hide behind a re-baseline.
# Register triggers are read from ``gaps/*.json`` (product data), never from ``src/``.
# --------------------------------------------------------------------------------------

NO_MATCH = re.compile(r"^\(no match\) searched .+ for /.+/$", re.DOTALL)
NO_FILES = re.compile(r"^\(no files\) searched .+$", re.DOTALL)
REMAINDER = re.compile(r"^\(\+(\d+) more matches(?:, (\d+) in test files)?\)$")


def _scan_json(target: pathlib.Path) -> dict:
    proc = _radar_bytes("scan", str(target), "--gaps", "gaps", "--json")
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == b"", proc.stderr
    return json.loads(proc.stdout.decode("utf-8"))


def _finding(payload: dict, gap_id: str) -> dict:
    hits = [f for f in payload["findings"] if f["gap_id"] == gap_id]
    assert len(hits) == 1, (gap_id, len(hits))
    return hits[0]


def _brief_evidence_bullets(target: pathlib.Path, gap_id: str) -> list[str]:
    """The ``- Signature seen at`` bullets the markdown brief renders under one finding."""
    md = _radar_bytes("scan", str(target), "--gaps", "gaps").stdout.decode("utf-8")
    lines = md.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.startswith(f"### {gap_id} ")]
    assert len(heads) == 1, (gap_id, heads)
    bullets: list[str] = []
    seen_signature = False
    for ln in lines[heads[0] + 1:]:
        if ln.startswith("### "):
            break
        if ln.startswith("- Signature seen at"):
            seen_signature = True
            continue
        if seen_signature:
            if ln.startswith("  - `") and ln.endswith("`"):
                bullets.append(ln[len("  - `"):-1])
            else:
                break
    assert seen_signature, f"the brief renders no evidence list for {gap_id}"
    return bullets


def _assert_all_findings_are_split_cleanly(payload: dict) -> None:
    for f in payload["findings"]:
        assert isinstance(f["locations"], list) and isinstance(f["location_notes"], list)
        assert all(LOCATOR.match(x) for x in f["locations"]), (f["gap_id"], f["locations"])
        assert all(_is_note(n) for n in f["location_notes"]), (f["gap_id"], f["location_notes"])
        assert list(f.keys())[-1] == "location_notes", list(f.keys())


@pytest.fixture()
def review_queue_target(tmp_path: pathlib.Path) -> pathlib.Path:
    """Trips GAP-117 (a review-queue vocabulary with no age/backlog vocabulary)."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "review_queue = []\n\n\ndef park(item):\n    review_queue.append(item)\n",
        encoding="utf-8")
    (tmp_path / "README.md").write_text("# tiny\n", encoding="utf-8")
    return tmp_path


def test_iter265_b7_planted_target_keeps_the_locator_and_moves_the_no_match_witness(
        review_queue_target) -> None:
    """One real hit + one absence witness: the hit stays a locator, the witness is a note."""
    payload = _scan_json(review_queue_target)
    _assert_all_findings_are_split_cleanly(payload)
    f = _finding(payload, "GAP-117")
    assert f["verdict"] == "PRESENT", f["reason"]
    assert f["locations"] == ["src/app.py:1"], f["locations"]
    assert len(f["location_notes"]) == 1 and NO_MATCH.match(f["location_notes"][0]), \
        f["location_notes"]
    # Findings with nothing to show carry EMPTY lists, not null and not a missing key.
    quiet = [g for g in payload["findings"] if g["verdict"] == "NOT_APPLICABLE"]
    assert quiet and all(g["locations"] == [] and g["location_notes"] == [] for g in quiet)


def test_iter265_b7_brief_renders_locators_then_notes_as_one_list(review_queue_target) -> None:
    """The markdown keeps the pre-change reading: locators and notes, one list, in order."""
    payload = _scan_json(review_queue_target)
    f = _finding(payload, "GAP-117")
    bullets = _brief_evidence_bullets(review_queue_target, "GAP-117")
    assert bullets == f["locations"] + f["location_notes"], bullets


def test_iter265_b8_a_finding_whose_only_witness_is_a_note_has_empty_locations(
        tmp_path: pathlib.Path) -> None:
    """Contract clause: empty ``locations`` and a non-empty ``location_notes``, never a
    fabricated line. GAP-004 applies on a steering file and is PRESENT when no test names it."""
    (tmp_path / "AGENTS.md").write_text("# steering\n\nBe careful.\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    payload = _scan_json(tmp_path)
    _assert_all_findings_are_split_cleanly(payload)
    f = _finding(payload, "GAP-004")
    assert f["verdict"] == "PRESENT", f["reason"]
    assert f["locations"] == [], f["locations"]
    assert len(f["location_notes"]) == 1 and NO_MATCH.match(f["location_notes"][0]), \
        f["location_notes"]
    # The brief still shows that witness as the finding's evidence (moved, not dropped).
    assert _brief_evidence_bullets(tmp_path, "GAP-004") == f["location_notes"]


def test_iter265_b9_the_no_files_dialect_lands_in_location_notes(tmp_path: pathlib.Path) -> None:
    """GAP-008: an LLM client import with no evals tree -> ``(no files) searched ...``."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "llm.py").write_text(
        "import openai\n\n\ndef ask(q):\n    return openai.chat(q)\n", encoding="utf-8")
    payload = _scan_json(tmp_path)
    _assert_all_findings_are_split_cleanly(payload)
    f = _finding(payload, "GAP-008")
    assert f["verdict"] == "PRESENT", f["reason"]
    assert f["locations"] == ["src/llm.py:1"], f["locations"]
    assert len(f["location_notes"]) == 1 and NO_FILES.match(f["location_notes"][0]), \
        f["location_notes"]
    assert _brief_evidence_bullets(tmp_path, "GAP-008") == f["locations"] + f["location_notes"]


def test_iter265_b10_the_capped_remainder_is_a_note_and_conserves_the_match_count(
        tmp_path: pathlib.Path) -> None:
    """More hits than the per-rule cap: the shown locators stay pure, the ``(+N more
    matches, M in test files)`` remainder is a note that precedes the absence witness, and
    shown + N equals the number of planted hits, so nothing was dropped."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    planted_src, planted_tests = 12, 2
    for i in range(1, planted_src + 1):
        (tmp_path / "src" / f"m{i}.py").write_text("review_queue = []\n", encoding="utf-8")
    for name in ("test_q.py", "test_r.py"):
        (tmp_path / "tests" / name).write_text("review_queue = []\n", encoding="utf-8")
    payload = _scan_json(tmp_path)
    _assert_all_findings_are_split_cleanly(payload)
    f = _finding(payload, "GAP-117")
    assert f["verdict"] == "PRESENT", f["reason"]
    shown = f["locations"]
    assert shown and len(shown) < planted_src + planted_tests, shown
    assert all(LOCATOR.match(x) for x in shown), shown
    assert len(f["location_notes"]) == 2, f["location_notes"]
    remainder, witness = f["location_notes"]
    m = REMAINDER.match(remainder)
    assert m, remainder
    assert len(shown) + int(m.group(1)) == planted_src + planted_tests, (shown, remainder)
    assert m.group(2) == str(planted_tests), remainder
    assert NO_MATCH.match(witness), witness
    assert _brief_evidence_bullets(tmp_path, "GAP-117") == shown + f["location_notes"]


# --------------------------------------------------------------------------------------
# Behavior 11 (tester-retry2 round) -- a pure locator is only worth publishing if a
# consumer can turn it into a file annotation without guessing: relative POSIX path
# under the target, a real file, a 1-based line inside that file. This is the
# register's "resolvable locator" invariant applied to the machine surface, and it is
# what separates ``locations`` from the prose ``location_notes`` now carries.
# --------------------------------------------------------------------------------------

def test_iter265_b11_every_published_locator_resolves_inside_the_target(self_scan_json) -> None:
    """Each ``path:line`` in ``locations`` names an existing file relative to the scanned
    target and a line index within that file's length; no absolute machine paths."""
    target = pathlib.Path(self_scan_json["target"])
    if not target.is_absolute():
        target = REPO_ROOT / target
    checked = 0
    for f in self_scan_json["findings"]:
        for loc in f["locations"]:
            path, _, line = loc.rpartition(":")
            assert path and line.isdigit(), (f["gap_id"], loc)
            assert not pathlib.PurePosixPath(path).is_absolute(), (f["gap_id"], loc)
            assert "\\" not in path, (f["gap_id"], loc)
            file = target / path
            assert file.is_file(), (f["gap_id"], loc, "no such file under the target")
            n_lines = len(file.read_bytes().splitlines())
            assert 1 <= int(line) <= n_lines, (f["gap_id"], loc, f"{n_lines} lines")
            checked += 1
    # Two-sided: the invariant was exercised on a corpus that actually publishes locators.
    assert checked >= 100, checked


def test_iter265_b11_notes_never_masquerade_as_locators_and_locators_never_as_notes(
        self_scan_json) -> None:
    """The split is a partition: no element satisfies both shapes, and every element
    satisfies exactly one, so a consumer's classification is total and unambiguous."""
    for f in self_scan_json["findings"]:
        for loc in f["locations"]:
            assert LOCATOR.match(loc) and not _is_note(loc), (f["gap_id"], loc)
        for note in f["location_notes"]:
            assert _is_note(note) and not LOCATOR.match(note), (f["gap_id"], note)
