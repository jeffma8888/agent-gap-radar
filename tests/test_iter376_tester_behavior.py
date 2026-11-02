"""Iteration 376 (tester): black-box pins for the per-(path, literal) prefilter memo.

The engineer's module drives the live repo. This one drives a SMALL temp target (a copy of
the repo's `src/` and `tools/` scanned against the repo's own register), which reaches real
PRESENT/ABSENT verdicts in about a second. The angles it adds:

- the memo is keyed by PATH as well as literal: in one scope a file without the literal
  must not make another file that has it look absent (a fail-open false negative), in
  either enumeration order;
- the memo does not outlive one `cli.main` call: a target rewritten between two in-process
  scans (both directions) prints exactly what a FRESH process prints for the new tree;
- byte identity memo on/off and the "at most once per pair" census on the temp target,
  including case-folded / non-ASCII text that reaches the ASCII refinement site;
- the hit stack is empty after an erroring scan.

No wall-clock assertion anywhere: the counting seam is the brake.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import shutil
import subprocess
import sys
from collections import Counter

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
BLANK = "# intentionally blank\n"
FOLD_FILE = (
    "# STRASSE straße İstanbul ΣΊΣΥΦΟΣ\n"
    "IMPORTLIB.RELOAD(module)  # Upper-cased on purpose\n"
    "def Run(): return 'CHECKPOINT' + 'Ünïcödé'\n"
)


class _CountingStr(str):
    path: pathlib.Path
    tally: Counter

    def __contains__(self, literal: object) -> bool:
        self.tally[(self.path, literal)] += 1
        return str.__contains__(self, literal)


def _run(argv: list[str], *, memo: bool = True, tally: Counter | None = None) -> tuple[int, str, str]:
    real_folded = checks._folded

    def counting(path, text):
        folded = _CountingStr(real_folded(path, text))
        folded.path = path
        folded.tally = tally
        return folded

    out, err = io.StringIO(), io.StringIO()
    with pytest.MonkeyPatch.context() as mp:
        if not memo:
            mp.setattr(checks, "_literal_hits", lambda path: None)
        if tally is not None:
            mp.setattr(checks, "_folded", counting)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _fresh(argv: list[str]) -> tuple[int, str]:
    """Oracle: a brand-new process, so no in-process state can carry over."""
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        capture_output=True, text=True, encoding="utf-8", cwd=REPO, timeout=120,
    )
    return proc.returncode, proc.stdout


def _make_target(root: pathlib.Path) -> pathlib.Path:
    target = root / "target"
    target.mkdir()
    for name in ("src", "tools"):
        shutil.copytree(REPO / name, target / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (target / "src" / "fold_probe.py").write_text(FOLD_FILE, encoding="utf-8")
    return target


def _snapshot(target: pathlib.Path) -> dict[pathlib.Path, bytes]:
    return {p: p.read_bytes() for p in sorted(target.rglob("*")) if p.is_file()}


def _blank(target: pathlib.Path) -> None:
    for p in sorted(target.rglob("*")):
        if p.is_file():
            p.write_text(BLANK, encoding="utf-8")


def _restore(snap: dict[pathlib.Path, bytes]) -> None:
    for p, data in snap.items():
        p.write_bytes(data)


def _argv(target: pathlib.Path, *extra: str) -> list[str]:
    return ["scan", str(target), "--gaps", str(REPO), *extra]


@pytest.fixture(scope="module")
def tmp_target(tmp_path_factory) -> pathlib.Path:
    return _make_target(tmp_path_factory.mktemp("iter376t"))


@pytest.fixture(scope="module")
def runs(tmp_target) -> dict[str, object]:
    on_tally: Counter = Counter()
    off_tally: Counter = Counter()
    return {
        "text_on": _run(_argv(tmp_target), tally=on_tally),
        "text_off": _run(_argv(tmp_target), memo=False, tally=off_tally),
        "json_on": _run(_argv(tmp_target, "--json")),
        "json_off": _run(_argv(tmp_target, "--json"), memo=False),
        "on_tally": on_tally,
        "off_tally": off_tally,
    }


# --- 1/2: byte identity on a temp target that reaches real verdicts -------------------


def test_t1_text_identical_on_off_and_non_vacuous(runs) -> None:
    code_on, out_on, _ = runs["text_on"]
    code_off, out_off, _ = runs["text_off"]
    assert out_on.encode() == out_off.encode()
    assert code_on == code_off
    assert "PRESENT" in out_on and "ABSENT" in out_on, "target reached no real verdict"
    assert out_on.endswith("\n") and not out_on.endswith("\n\n")


def test_t2_json_identical_on_off_and_fresh_process(runs, tmp_target) -> None:
    code_on, out_on, _ = runs["json_on"]
    code_off, out_off, _ = runs["json_off"]
    assert out_on.encode() == out_off.encode()
    assert code_on == code_off
    assert '"PRESENT"' in out_on
    assert _fresh(_argv(tmp_target, "--json")) == (code_on, out_on)


# --- 3/4: census on the temp target ----------------------------------------------------


def test_t3_at_most_once_per_pair_including_fold_probe(runs, tmp_target) -> None:
    tally: Counter = runs["on_tally"]
    assert tally
    assert {pair: n for pair, n in tally.items() if n > 1} == {}
    probe = (tmp_target / "src" / "fold_probe.py").resolve()
    assert any(pathlib.Path(p).resolve() == probe for p, _ in tally), \
        "the case-fold probe file was never prefiltered"


def test_t4_memo_off_repeats_and_drops_no_question(runs) -> None:
    on_tally: Counter = runs["on_tally"]
    off_tally: Counter = runs["off_tally"]
    assert max(off_tally.values()) >= 2
    assert sum(on_tally.values()) < sum(off_tally.values())
    assert set(on_tally) == set(off_tally)
    assert all(on_tally[pair] == 1 for pair in off_tally)


# --- 5: scope lifetime around an erroring scan -----------------------------------------


def test_t5_stack_empty_after_erroring_scan(tmp_path) -> None:
    assert checks._LITERAL_HIT_STACK == []
    code, out, err = _run(["scan", str(tmp_path / "does-not-exist"), "--gaps", str(REPO)])
    assert code == 2 and out == "" and err.startswith("Error: ")
    assert checks._LITERAL_HIT_STACK == []
    code, out, err = _run(["scan", str(tmp_path), "--gaps", str(REPO), "--gap", "GAP-99999"])
    assert code == 2 and err.startswith("Error: ")
    assert checks._LITERAL_HIT_STACK == []


# --- 6/7: no carry-over across scans, both directions, at the CLI ----------------------


@pytest.mark.parametrize("flag", [(), ("--json",)], ids=["text", "json"])
def test_t7_cli_full_then_blank_matches_fresh_process(tmp_path, flag) -> None:
    target = _make_target(tmp_path)
    _, full_out, _ = _run(_argv(target, *flag))
    _blank(target)
    code, blank_out, _ = _run(_argv(target, *flag))
    assert blank_out != full_out, "rewriting the tree moved nothing: vacuous"
    assert (code, blank_out) == _fresh(_argv(target, *flag))


@pytest.mark.parametrize("flag", [(), ("--json",)], ids=["text", "json"])
def test_t7_cli_blank_then_full_matches_fresh_process(tmp_path, flag) -> None:
    """The fail-open direction: a carried `False` would skip files that now match."""
    target = _make_target(tmp_path)
    snap = _snapshot(target)
    _blank(target)
    _, blank_out, _ = _run(_argv(target, *flag))
    _restore(snap)
    code, full_out, _ = _run(_argv(target, *flag))
    assert full_out != blank_out, "rewriting the tree moved nothing: vacuous"
    assert (code, full_out) == _fresh(_argv(target, *flag))


# --- per-path keying inside ONE scope --------------------------------------------------


def _rule() -> dict:
    return {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "dangerous_call"}


@pytest.mark.parametrize("absent_name,present_name",
                         [("a_safe.py", "z_hit.py"), ("z_safe.py", "a_hit.py")])
def test_memo_keyed_by_path_within_one_scope(tmp_path, absent_name, present_name) -> None:
    (tmp_path / absent_name).write_text("safe_call()\n", encoding="utf-8")
    (tmp_path / present_name).write_text("dangerous_call()\n", encoding="utf-8")
    with checks.read_cache_scope():
        assert checks.evaluate(_rule(), tmp_path).matched is True
        assert checks.evaluate(_rule(), tmp_path).matched is True
        a = checks._literal_hits(tmp_path / absent_name)
        b = checks._literal_hits(tmp_path / present_name)
        assert a is not None and b is not None and a is not b
    assert checks._LITERAL_HIT_STACK == []


def test_absent_only_tree_stays_unmatched_in_one_scope(tmp_path) -> None:
    (tmp_path / "a.py").write_text("safe_call()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("other_call()\n", encoding="utf-8")
    with checks.read_cache_scope():
        assert checks.evaluate(_rule(), tmp_path).matched is False
        assert checks.evaluate(_rule(), tmp_path).matched is False


# --- 8: memo answers equal direct answers, across many literals -----------------------


def test_t8_contains_agrees_with_in_for_a_literal_table() -> None:
    folded = "def run(): dangerous_call()  # straße\n"
    table = ["dangerous_call", "run", "", "straße", "absent_one", "DANGEROUS_CALL", "\n"]
    with checks.read_cache_scope():
        hits = checks._literal_hits(pathlib.Path("virtual.py"))
        for literal in table:
            for _ in range(3):
                assert checks._contains(folded, literal, hits) is (literal in folded)
            assert hits[literal] is (literal in folded)
    for literal in table:
        assert checks._contains(folded, literal, None) is (literal in folded)
