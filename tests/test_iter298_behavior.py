"""Iteration 298: for an ASCII file the literal prefilter proves the WHOLE run of a `(?i)` pattern.

Behaviors from state/iter-298/pm.md. Every test here is in-process (no spawn) except
b7/b9, which spawn `radar scan` once each for byte identity and determinism, and b2, which
spawns `git ls-files` once to enumerate the tracked `src/` domain.

Black-box: the tests drive `checks.evaluate`, the two accessor seams, `cli.main` and the
committed `tools/scan_cost.py` census. Nothing here reads the implementation text.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main
from test_iter02_behavior import _record, _write_register

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"

#: A literal that no fixture file contains: an ASCII DNF built from it admits nothing.
IMPOSSIBLE = "gapradar-iter298-literal-that-cannot-occur"

#: Behavior 7's verbs, in-process on the live register (the spec's list minus `scan`, which
#: b7/b9 spawn). `taxonomy` is added because it is a renderer too.
LIVE_VERB_ARGV = (
    ["list", str(GAPS)],
    ["list", str(GAPS), "--json"],
    ["show", "GAP-001", str(GAPS)],
    ["report", str(GAPS)],
    ["prd", str(GAPS)],
    ["diff", str(GAPS), str(GAPS)],
    ["diff", "--json", str(GAPS), str(GAPS)],
    ["validate", str(GAPS)],
    ["taxonomy"],
)


def _rule(pattern: str, glob: str) -> dict:
    return {"kind": "content_matches", "pattern": pattern, "globs": [glob]}


def _check(cid: str, pattern: str) -> dict:
    """A two-sided content check whose pattern carries an in-effect `(?i)`."""
    return {
        "id": cid, "rationale": "r", "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": pattern},
        "fixtures": {"bad": {"a.py": "x = vector_store()\n"}, "good": {"a.py": "clean\n"}},
    }


@pytest.fixture()
def target(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "a.py").write_text("x = vector_store()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = vector_\u017ftore()\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("thread_\u0130d = 1\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def scan_fixture(tmp_path: pathlib.Path):
    """A register with one `(?i)` rule and a target holding an ASCII and a non-ASCII hit."""
    rec = _record("GAP-798", 5, 5, 5, ("first-party-field",))
    rec["check"] = _check("CHK-798", "(?i)vector_store")
    reg = _write_register(tmp_path, [rec])
    tgt = tmp_path / "target"
    (tgt / "app").mkdir(parents=True)
    (tgt / "app" / "ascii.py").write_text("x = vector_store()\n", encoding="utf-8")
    (tgt / "app" / "folded.py").write_text("x = vector_\u017ftore()\n", encoding="utf-8")
    (tgt / "app" / "quiet.py").write_text("y = 1\n", encoding="utf-8")
    return tgt, reg


def _scan_bytes(target, reg, capsys):
    code = main(["scan", str(target), "--gaps", str(reg)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Behavior 1 -- a PRIVATE accessor proves the whole run under an in-effect `(?i)`.
# ---------------------------------------------------------------------------

def test_b1_private_accessor_proves_the_whole_run_under_i_flag():
    assert not hasattr(checks, "required_literal_sets_ascii")
    f = checks._required_literal_sets_ascii
    assert f("(?i)vector_store") == (frozenset({"vector_store"}),)
    assert f("(?i)thread_id") == (frozenset({"thread_id"}),)
    (conj,) = f(r"(?i)git\s+push\b")
    assert {"git", "push"} <= conj
    # the folded seam still proves only fragments, so the two are distinct answers
    assert checks.required_literal_sets("(?i)vector_store") != f("(?i)vector_store")


@pytest.mark.parametrize("pattern", ["(?im)vector_store", "(?m)(?i)vector_store",
                                     "(?s)(?i)thread_id"])
def test_b1_the_i_flag_is_ignored_however_it_is_spelled_among_the_global_flags(pattern):
    """`(?m)(?i)foo` compiles; the accessor must not re-read the `i` one group down."""
    (conj,) = checks._required_literal_sets_ascii(pattern)
    assert conj == frozenset({pattern.rsplit(")", 1)[1]}), conj


def test_b1_the_accessor_is_not_part_of_the_public_surface():
    public = {n for n in vars(checks) if not n.startswith("_") and callable(getattr(checks, n))}
    assert "required_literal_sets" in public and "required_literals" in public
    assert not any(n.endswith("_ascii") for n in public), sorted(public)


# ---------------------------------------------------------------------------
# Behavior 2 -- never LOOSER, strictly TIGHTER, measured in counts over tracked `src/`.
# ---------------------------------------------------------------------------

def _register_patterns() -> list[str]:
    pats: set[str] = set()
    for path in sorted(GAPS.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'"pattern"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
            pats.add(json.loads('"' + m.group(1) + '"'))
    return sorted(pats)


def test_b2_ascii_dnf_never_looser_and_strictly_tighter_over_tracked_src():
    provable = [p for p in _register_patterns()
                if checks.required_literal_sets(p) is not None]
    assert provable
    assert all(checks._required_literal_sets_ascii(p) is not None for p in provable)
    files = subprocess.run(["git", "ls-files", "src/**/*.py", "src/*.py"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.split()
    texts = [(REPO / f).read_text(encoding="utf-8") for f in files]
    lows = [t.lower() for t in texts if t.isascii()]
    assert lows

    def sat(dnf, low):
        return any(all(lit in low for lit in conj) for conj in dnf)

    folded_admitted = ascii_admitted = 0
    for p in provable:
        folded = checks.required_literal_sets(p)
        ascii_dnf = checks._required_literal_sets_ascii(p)
        for low in lows:
            fa, aa = sat(folded, low), sat(ascii_dnf, low)
            assert not (aa and not fa), (p, "ASCII DNF admitted a file the folded one skips")
            folded_admitted += fa
            ascii_admitted += aa
    assert ascii_admitted < folded_admitted, (folded_admitted, ascii_admitted)


def test_b2_every_ascii_conjunction_structurally_implies_a_folded_conjunction():
    """Corpus-free soundness, so behavior 2 does not rest on which `src/` files exist.

    For every ASCII conjunction A there is a folded conjunction F whose every literal is a
    SUBSTRING of some literal in A: any ASCII text satisfying A therefore satisfies F, so
    the ASCII DNF can never admit a text the folded DNF skips, for ANY ASCII text. The
    tightening is real for many patterns (the two DNFs differ), never the reverse.
    """
    provable = [p for p in _register_patterns()
                if checks.required_literal_sets(p) is not None]
    assert len(provable) > 100, len(provable)
    differ = 0
    for p in provable:
        folded = checks.required_literal_sets(p)
        ascii_dnf = checks._required_literal_sets_ascii(p)
        assert ascii_dnf is not None, p
        differ += ascii_dnf != folded
        for a in ascii_dnf:
            assert a, (p, "an empty conjunction admits every text")
            assert any(all(any(fl in al for al in a) for fl in f) for f in folded), (
                p, folded, ascii_dnf, "an ASCII conjunction is not covered by a folded one")
    assert differ > 100, differ


# ---------------------------------------------------------------------------
# Behavior 3 -- no in-effect `(?i)` means the two seams agree exactly.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pattern", ["sk_live_", r"git\s+push\b", "(?m)foo|bar", r"os\.walk\("])
def test_b3_no_i_flag_means_identical_to_the_seam(pattern: str):
    assert checks._required_literal_sets_ascii(pattern) == checks.required_literal_sets(pattern)


def _has_in_effect_i(pattern: str) -> bool:
    """True when an `i` flag is in effect anywhere: global `(?i)`/`(?im)` or scoped `(?i:`."""
    return any("i" in g for g in re.findall(r"\(\?([a-z]+)[:)]", pattern))


def test_b3_every_register_pattern_without_i_agrees_across_the_seams():
    """Only patterns with NO `i` flag at all, global or scoped: the register carries 11
    scoped `(?i:...)` patterns whose `i` IS in effect inside the group, so they are not
    behavior 3's subject (behavior 2 covers their soundness)."""
    pats = _register_patterns()
    plain = [p for p in pats if not _has_in_effect_i(p)]
    scoped = [p for p in pats if _has_in_effect_i(p)
              and not any("i" in g for g in re.findall(r"\(\?([a-z]+)\)", p))]
    assert plain and scoped, (len(plain), len(scoped))
    assert not any(_has_in_effect_i(p) for p in plain)
    for p in plain:
        assert checks._required_literal_sets_ascii(p) == checks.required_literal_sets(p), p


# ---------------------------------------------------------------------------
# Behaviors 4 and 5 -- ASCII text is PRESENT; folded non-ASCII text is still PRESENT.
# ---------------------------------------------------------------------------

def test_b4_ascii_target_reports_present_with_locator(target: pathlib.Path):
    hit = checks.evaluate(_rule("(?i)vector_store", "a.py"), target)
    assert hit.matched is True and hit.locations == ["a.py:1"]


def test_b4_both_dnfs_are_computed_once_per_rule_above_the_file_loop(target, monkeypatch):
    """Three files in the domain (one ASCII hit, one folded hit, one miss): each seam is
    consulted exactly ONCE, so neither DNF is recomputed per file."""
    sets_calls: list[str] = []
    ascii_calls: list[str] = []
    real_sets, real_ascii = checks.required_literal_sets, checks._required_literal_sets_ascii
    monkeypatch.setattr(checks, "required_literal_sets",
                        lambda p: sets_calls.append(p) or real_sets(p))
    monkeypatch.setattr(checks, "_required_literal_sets_ascii",
                        lambda p: ascii_calls.append(p) or real_ascii(p))
    hit = checks.evaluate(_rule("(?i)vector_store", "*.py"), target)
    assert hit.matched is True and hit.locations == ["a.py:1", "b.py:1"], hit.locations
    assert sets_calls == ["(?i)vector_store"], sets_calls
    assert ascii_calls == ["(?i)vector_store"], ascii_calls


def test_b5_non_ascii_folds_keep_the_folded_dnf_and_report_present(target: pathlib.Path):
    assert re.search("(?i)vector_store", "vector_\u017ftore")
    assert re.search("(?i)thread_id", "thread_\u0130d")
    hit = checks.evaluate(_rule("(?i)vector_store", "b.py"), target)
    assert hit.matched is True and hit.locations == ["b.py:1"]
    hit = checks.evaluate(_rule("(?i)thread_id", "c.py"), target)
    assert hit.matched is True and hit.locations == ["c.py:1"]


def test_b5_the_fixtures_are_really_non_ascii_and_the_ascii_dnf_would_skip_them():
    """The control: without the per-file gate, the ASCII DNF WOULD skip these files."""
    for text, pattern in (("x = vector_\u017ftore()\n", "(?i)vector_store"),
                          ("thread_\u0130d = 1\n", "(?i)thread_id")):
        assert not text.isascii()
        (conj,) = checks._required_literal_sets_ascii(pattern)
        assert not all(lit in text.lower() for lit in conj), (pattern, conj)


# ---------------------------------------------------------------------------
# Behavior 6 -- mutation pins: the non-ASCII arm never consults the ASCII DNF; the
# seam-None convention still renders identical bytes.
# ---------------------------------------------------------------------------

def test_b6_mutation_ascii_arm_consulted_only_for_ascii_text(target, monkeypatch):
    monkeypatch.setattr(checks, "_required_literal_sets_ascii",
                        lambda pattern: (frozenset({IMPOSSIBLE}),))
    # fires-on-bad: the ASCII file is skipped by the stand-in
    assert checks.evaluate(_rule("(?i)vector_store", "a.py"), target).matched is False
    # silent-on-good: the non-ASCII file never consults the ASCII arm
    hit = checks.evaluate(_rule("(?i)vector_store", "b.py"), target)
    assert hit.matched is True and hit.locations == ["b.py:1"]
    hit = checks.evaluate(_rule("(?i)thread_id", "c.py"), target)
    assert hit.matched is True and hit.locations == ["c.py:1"]


def test_b6_a_swapped_arm_would_have_been_caught(target, monkeypatch):
    """The spec's stand-in verbatim: `(frozenset({"vector_store"}),)` for every pattern.

    Under a swapped arm (ASCII DNF consulted for non-ASCII text) `b.py` would be skipped,
    because `"vector_store" not in "x = vector_\u017ftore()"`.
    """
    monkeypatch.setattr(checks, "_required_literal_sets_ascii",
                        lambda pattern: (frozenset({"vector_store"}),))
    hit = checks.evaluate(_rule("(?i)vector_store", "b.py"), target)
    assert hit.matched is True and hit.locations == ["b.py:1"]


def test_b6_seam_none_disables_both_prefilters(target, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(checks, "required_literal_sets", lambda pattern: None)
    monkeypatch.setattr(checks, "_required_literal_sets_ascii",
                        lambda pattern: calls.append(pattern) or (frozenset({IMPOSSIBLE}),))
    hit = checks.evaluate(_rule("(?i)vector_store", "a.py"), target)
    assert hit.matched is True and hit.locations == ["a.py:1"]
    assert calls == ["(?i)vector_store"], "computed once per rule, above the file loop"


def test_b6_seam_none_renders_the_scan_byte_identical(scan_fixture, capsys, monkeypatch):
    target, reg = scan_fixture
    base_code, base_out, base_err = _scan_bytes(target, reg, capsys)
    assert base_code == 0, base_err
    assert "| PRESENT | 1 |" in base_out, base_out
    monkeypatch.setattr(checks, "required_literal_sets", lambda pattern: None)
    monkeypatch.setattr(checks, "_required_literal_sets_ascii", lambda pattern: None)
    code, out, err = _scan_bytes(target, reg, capsys)
    assert (code, out, err) == (base_code, base_out, base_err), "the prefilter changed the document"


def test_b6_the_byte_comparison_can_see_an_unsound_ascii_arm(scan_fixture, capsys, monkeypatch):
    """Control: an unsound ASCII DNF skips the ASCII hit; the folded file still fires."""
    target, reg = scan_fixture
    _c, base_out, _e = _scan_bytes(target, reg, capsys)
    monkeypatch.setattr(checks, "_required_literal_sets_ascii",
                        lambda pattern: (frozenset({IMPOSSIBLE}),))
    _c2, unsound_out, _e2 = _scan_bytes(target, reg, capsys)
    assert unsound_out != base_out, "the comparison cannot detect a moved locator"
    assert "app/folded.py:1" in unsound_out and "app/ascii.py:1" not in unsound_out, unsound_out


# ---------------------------------------------------------------------------
# Behavior 7 -- renderers are byte-identical to the pre-change semantics.
# ---------------------------------------------------------------------------

def test_b7_scan_is_byte_identical_to_the_single_folded_arm_of_c22994d(
        scan_fixture, capsys, monkeypatch):
    """At c22994d every file took the folded DNF. Making the ASCII arm return exactly the
    folded answer reproduces that semantics; the document must not move by a byte."""
    target, reg = scan_fixture
    base = _scan_bytes(target, reg, capsys)
    folded = checks.required_literal_sets
    monkeypatch.setattr(checks, "_required_literal_sets_ascii", lambda pattern: folded(pattern))
    assert _scan_bytes(target, reg, capsys) == base


@pytest.mark.parametrize("argv", LIVE_VERB_ARGV, ids=lambda a: "-".join(a[:1] + a[2:]))
def test_b7_every_other_verb_is_deterministic_and_ends_in_one_newline(argv, capsys):
    outs = []
    for _ in range(2):
        code = main(list(argv))
        captured = capsys.readouterr()
        assert code == 0, captured.err
        assert captured.err == ""
        outs.append(captured.out)
    assert outs[0] == outs[1]
    assert outs[0].endswith("\n") and not outs[0].endswith("\n\n")


def test_b7_version_is_unchanged_in_shape(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert re.fullmatch(r"\d+\.\d+\.\d+\n", out), out


# ---------------------------------------------------------------------------
# Behavior 8 -- `tools/scan_cost.py` counters are unchanged: the new accessor never
# re-enters the two counted seams, and `required_literal_sets` runs once per rule.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cost_tool():
    sys.path.insert(0, str(REPO / "tools"))
    import scan_cost  # noqa: PLC0415

    return scan_cost


def test_b8_accessor_never_reenters_the_counted_seams(monkeypatch):
    calls: list[tuple[str, str]] = []
    real_sets, real_lits = checks.required_literal_sets, checks.required_literals
    monkeypatch.setattr(checks, "required_literal_sets",
                        lambda p: calls.append(("sets", p)) or real_sets(p))
    monkeypatch.setattr(checks, "required_literals",
                        lambda p: calls.append(("lits", p)) or real_lits(p))
    for p in _register_patterns() + ["(?i)vector_store", "(?i)thread_id"]:
        checks._required_literal_sets_ascii(p)
    assert calls == [], calls


def test_b8_census_counts_one_literal_set_proof_per_rule_not_per_file(cost_tool, scan_fixture):
    target, reg = scan_fixture
    census = cost_tool.census(target, reg)
    payload = json.loads(cost_tool.render_json(census))
    assert payload["literal-set proofs"] == 1, payload
    assert payload["files in content domains"] == 3, payload


def test_b8_census_is_byte_identical_to_the_single_folded_arm(cost_tool, scan_fixture, monkeypatch):
    target, reg = scan_fixture
    base_json = cost_tool.render_json(cost_tool.census(target, reg))
    base_md = cost_tool.render_markdown(cost_tool.census(target, reg))
    folded = checks.required_literal_sets  # the UNWRAPPED seam, so the census cannot count it
    monkeypatch.setattr(checks, "_required_literal_sets_ascii", lambda pattern: folded(pattern))
    assert cost_tool.render_json(cost_tool.census(target, reg)) == base_json
    assert cost_tool.render_markdown(cost_tool.census(target, reg)) == base_md


# ---------------------------------------------------------------------------
# Behaviors 7 and 9 -- the live self-scan, at a real process boundary.
# ---------------------------------------------------------------------------

def _scan(*args: str) -> subprocess.CompletedProcess[bytes]:
    code = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"
    return subprocess.run([sys.executable, "-c", code, "scan", str(REPO),
                           "--gaps", str(GAPS), *args], cwd=REPO, capture_output=True)


def test_b7_b9_scan_is_deterministic_and_ends_in_one_newline():
    first, second = _scan(), _scan()
    assert first.returncode == 0 and first.stderr == b""
    assert first.stdout == second.stdout
    assert first.stdout.endswith(b"\n") and not first.stdout.endswith(b"\n\n")
    js = _scan("--json")
    assert js.returncode == 0 and json.loads(js.stdout) is not None
    assert js.stdout.endswith(b"\n") and not js.stdout.endswith(b"\n\n")
