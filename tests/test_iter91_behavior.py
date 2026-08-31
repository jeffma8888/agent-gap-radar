"""Iteration 91 behaviors: the PUBLIC REPO clause of the quality bar gets a committed,
fail-closed brake over the whole tracked file set.

Until this iteration nothing in the suite enforced "no absolute machine paths, no employer
or personal identifiers" over `git ls-files`. Enforcement was a per-iteration hand-rolled
grep, and a grep that opens no file prints the reassuring word rather than the true one.
`tools/check_public_safety.py` replaces it, and this module is the in-suite brake that runs
it FOR REAL against the live tree.

ISOLATION CONTRACT HONORED. Nothing here reads `src/` or `tools/` implementation text, the
engineer's notes, the reviewer's notes, `IMPLEMENTATION.patch`, or any diff. Expectations
come from `pm.md`'s Feature/Why/Out-of-Scope plus the roadmap rows the PM owns (`PRODUCT.md`
row 88 and the iter 91 done-ledger row), and every claim is measured by CALLING or
INTROSPECTING the public interface -- `check_public_safety.RULES`, `.rule_defects`,
`.matches`, `.findings`, `.tracked_files`, `.main` -- or by running the tool as a subprocess.
One test does read `tools/check_public_safety.py` as BYTES, never as logic: it feeds the
file's own text to `findings()`, which is the only way to assert the self-scan property.

STRUCTURAL NOTE, and it is the load-bearing one for this file:

* **THIS FILE IS INSIDE THE DOMAIN THE GATE SCANS, so it may not contain a banned token as
  a LITERAL.** That is the trap iteration 06 hit live when its self-scanning version failed
  on its own assertion line. Every positive sample is therefore COMPOSED AT CALL TIME --
  from each rule's own committed `fires_on`/`silent_on` data, or from fragments that are
  individually clean (`"ab"`, `"mail-host.net"`, the `"@"` joiner) and only become a banned
  token once concatenated in memory. No marker literal is inlined anywhere below, which is
  the same invariant the tool holds over itself. `test_b7_this_test_file_is_silent_under_the
  _gate` measures that this discipline actually held rather than trusting it.
* **The message and line formats are composed from the tool's OWN data**, never re-typed as
  a second copy: a `4` typed here would agree with `len(RULES)` only by luck.
"""

from __future__ import annotations

import io
import contextlib
import hashlib
import pathlib
import re
import subprocess
import sys

import pytest

#: Repo root found relative to this file, so no absolute machine path appears here.
REPO = pathlib.Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "check_public_safety.py"
TOOL_REL = "tools/check_public_safety.py"

sys.path.insert(0, str(REPO / "tools"))

import check_public_safety as cps  # noqa: E402


# ---------------------------------------------------------------------------
# sample composition -- nothing below is a banned token until it is joined
# ---------------------------------------------------------------------------

BY_NAME = {r.name: r for r in cps.RULES}
PATH_RULE_NAMES = ("macos-account-home", "posix-account-home", "macos-mounted-volume")
EMAIL_RULE_NAME = "email-address"


def _marker(rule_name: str) -> str:
    """The bare marker of a path rule, read from the rule's own negative sample.

    Read, never typed: a marker literal in this file would put a name character after a
    marker the moment it appeared inside a longer sample, and red the gate on this file.
    """
    return BY_NAME[rule_name].silent_on


def _addr(local: str, domain: str) -> str:
    """Compose an address at call time from two individually-clean fragments."""
    return local + "@" + domain


def _run_main(argv, list_fn=None, read_fn=None):
    """Call `main()` with the argv it would get from the shell, capturing both streams."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cps.main(list(argv), list_fn=list_fn, read_fn=read_fn)
    return code, out.getvalue(), err.getvalue()


def _one_file(text: str, name: str = "sample.txt"):
    """Seams that present exactly one in-memory file to the scan."""
    return (lambda: [name]), (lambda path: text)


# ===========================================================================
# B1  The gate runs over the `git ls-files` domain and STATES the size it
#     scanned, so a green result is legible rather than merely quiet.
#     This is the in-suite brake: it runs the real tool on the real tree.
# ===========================================================================


def _live_scan() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), str(REPO)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )


def test_b1_the_live_tracked_tree_is_clean_and_the_scan_states_its_domain_size():
    proc = _live_scan()
    n = len(cps.tracked_files(REPO))
    assert n > 0, "the brake is vacuous if the domain is empty"
    expected = (
        f"{n} tracked file(s) scanned against {len(cps.RULES)} rule(s): 0 finding(s)\n"
    )
    assert proc.stdout == expected, (
        "the live tracked tree must be clean and must SAY how many files it cleared; "
        f"got {proc.stdout!r} on stderr {proc.stderr!r}"
    )
    assert proc.stderr == ""
    assert proc.returncode == 0


def test_b1_the_stated_count_is_the_git_index_and_not_a_directory_walk():
    tracked = cps.tracked_files(REPO)
    listed = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=str(REPO)
    )
    assert listed.returncode == 0
    assert tracked == [line for line in listed.stdout.splitlines() if line]
    # a walk would have swept these; the index does not carry them
    assert not any(p.startswith(".venv/") for p in tracked)
    assert not any(p.startswith(".pytest_cache/") for p in tracked)
    assert "PRODUCT.md" in tracked
    assert "pyproject.toml" in tracked


def test_b1_the_scan_is_deterministic_across_runs():
    first, second = _live_scan(), _live_scan()
    assert first.stdout == second.stdout
    assert first.returncode == second.returncode == 0


def test_b1_every_tracked_file_is_actually_read_not_merely_counted():
    """A count is not coverage. The reader must be handed every path in the domain."""
    domain = cps.tracked_files(REPO)
    seen = []

    def recording_read(rel):
        seen.append(rel)
        return (REPO / rel).read_text(encoding="utf-8")

    code, out, err = _run_main([str(REPO)], list_fn=lambda: domain, read_fn=recording_read)
    assert code == 0, f"stdout={out!r} stderr={err!r}"
    assert seen == domain


def test_b1_one_dirty_file_anywhere_in_the_real_domain_flips_the_verdict():
    """The two-sided proof of the live brake, with ZERO writes: the same real domain and
    the same real file bytes, with a banned token composed into exactly one of them."""
    domain = cps.tracked_files(REPO)
    target = "PRODUCT.md"
    assert target in domain
    planted = _marker("macos-account-home") + "someone/notes.md"

    def read_with_one_planted(rel):
        text = (REPO / rel).read_text(encoding="utf-8")
        return text + "\n" + planted + "\n" if rel == target else text

    code, out, err = _run_main(
        [str(REPO)], list_fn=lambda: domain, read_fn=read_with_one_planted
    )
    assert code == 1, "a planted banned token in a real tracked file did not fire the gate"
    assert err == ""
    assert f"  {target}:" in out
    assert "macos-account-home" in out
    assert f"{len(domain)} tracked file(s) scanned against {len(cps.RULES)} rule(s): 1 finding(s)" in out


def test_b1_findings_are_ordered_by_path_not_by_the_order_handed_in():
    dirty = _marker("macos-account-home") + "someone/notes"
    code, out, err = _run_main(
        [str(REPO)], list_fn=lambda: ["b.txt", "a.txt"], read_fn=lambda path: dirty
    )
    assert code == 1
    body = [line for line in out.splitlines() if line.startswith("  a.") or line.startswith("  b.")]
    assert [line.split(":")[0].strip() for line in body] == ["a.txt", "b.txt"]


# ===========================================================================
# B2  FAIL CLOSED on the first way a scan can be vacuous rather than clean:
#     a domain of ZERO files exits 2, it does not report a clean tree.
# ===========================================================================


def test_b2_an_empty_domain_is_an_error_not_a_clean_scan():
    code, out, err = _run_main([str(REPO)], list_fn=lambda: [], read_fn=lambda path: "")
    assert code == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert err.endswith("\n") and not err.endswith("\n\n")


def test_b2_a_directory_outside_any_checkout_is_an_error(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout == ""
    assert proc.stderr.startswith("Error: ")


def test_b2_a_path_that_is_not_a_directory_is_an_error():
    proc = subprocess.run(
        [sys.executable, str(TOOL), str(REPO / "no-such-directory-here")],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.startswith("Error: not a directory: ")


# ===========================================================================
# B3  FAIL CLOSED on the second way: a file the scan cannot READ is not a
#     file it can CLEAR.  Both undecodable and unreadable exit 2.
# ===========================================================================


def test_b3_a_file_that_cannot_be_decoded_is_an_error():
    def cannot_decode(path):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    code, out, err = _run_main(
        [str(REPO)], list_fn=lambda: ["blob.bin"], read_fn=cannot_decode
    )
    assert code == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert "blob.bin" in err


def test_b3_a_file_that_cannot_be_read_is_an_error():
    def cannot_read(path):
        raise OSError("permission denied")

    code, out, err = _run_main(
        [str(REPO)], list_fn=lambda: ["locked.md"], read_fn=cannot_read
    )
    assert code == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert "locked.md" in err


def test_b3_control_the_same_seam_with_a_readable_clean_file_exits_zero():
    """Without this control, exit 2 above could be the seam failing, not the policy."""
    list_fn, read_fn = _one_file("a line with nothing banned in it\n")
    code, out, err = _run_main([str(REPO)], list_fn=list_fn, read_fn=read_fn)
    assert code == 0
    assert err == ""
    assert out == f"1 tracked file(s) scanned against {len(cps.RULES)} rule(s): 0 finding(s)\n"


# ===========================================================================
# B4  THREE distinct verdicts, and a finding is not an error: clean 0,
#     finding 1 with the report on stdout, error 2 with `Error: ` on stderr
#     and stdout empty.
# ===========================================================================


def test_b4_a_finding_exits_one_and_names_path_line_rule_and_matched_text():
    rule = BY_NAME["posix-account-home"]
    dirty = "clean first line\n" + _marker("posix-account-home") + "someone/thing\n"
    list_fn, read_fn = _one_file(dirty, name="doc.md")
    code, out, err = _run_main([str(REPO)], list_fn=list_fn, read_fn=read_fn)
    assert code == 1
    assert err == ""
    lines = out.splitlines()
    hit = lines[0]
    assert hit.startswith("  doc.md:2  ")
    assert rule.name in hit
    assert _marker("posix-account-home") in hit
    assert lines[1] == f"1 tracked file(s) scanned against {len(cps.RULES)} rule(s): 1 finding(s)"
    assert lines[2] == f"  {rule.name}: {rule.why}"
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_b4_the_three_verdicts_are_distinct_and_each_is_reachable():
    clean_list, clean_read = _one_file("nothing to see")
    dirty_list, dirty_read = _one_file(_marker("macos-mounted-volume") + "disk/x")
    codes = {
        "clean": _run_main([str(REPO)], list_fn=clean_list, read_fn=clean_read)[0],
        "finding": _run_main([str(REPO)], list_fn=dirty_list, read_fn=dirty_read)[0],
        "error": _run_main([str(REPO)], list_fn=lambda: [], read_fn=lambda p: "")[0],
    }
    assert codes == {"clean": 0, "finding": 1, "error": 2}


def test_b4_every_rule_can_actually_produce_a_finding_through_main():
    """A rule that cannot reach `main()` is a comment, however well it matches."""
    for rule in cps.RULES:
        list_fn, read_fn = _one_file(rule.fires_on, name="sample.txt")
        code, out, err = _run_main([str(REPO)], list_fn=list_fn, read_fn=read_fn)
        assert code == 1, f"{rule.name} produced no finding through main()"
        assert rule.name in out
        assert f"  {rule.name}: {rule.why}" in out.splitlines()


# ===========================================================================
# B5  FOUR rules, all DATA, each carrying its OWN two-sided sample -- and the
#     self-check that proves them is itself proved two-sided.
# ===========================================================================


def test_b5_the_rule_set_is_four_named_rules_and_the_names_are_unique():
    assert len(cps.RULES) == 4
    names = [r.name for r in cps.RULES]
    assert len(set(names)) == len(names)
    assert set(names) == set(PATH_RULE_NAMES) | {EMAIL_RULE_NAME}


def test_b5_the_live_rule_set_reports_no_defects():
    assert cps.rule_defects(cps.RULES) == []


def test_b5_each_rule_fires_on_its_own_positive_sample_and_is_silent_on_its_negative():
    for rule in cps.RULES:
        assert cps.matches(rule, rule.fires_on), f"{rule.name} is silent on its own positive sample"
        assert cps.matches(rule, rule.silent_on) == [], f"{rule.name} fires on its own negative sample"


def test_b5_every_rule_states_why_it_exists():
    for rule in cps.RULES:
        assert rule.why.strip(), f"{rule.name} carries no reason"
        assert rule.fires_on and rule.silent_on


def test_b5_the_self_check_is_two_sided_a_rule_that_never_fires_is_reported():
    never = cps.Rule(
        name="never-fires",
        pattern=re.compile("a-token-absent-from-its-own-sample"),
        exempt=None,
        fires_on="the positive sample",
        silent_on="the negative sample",
        why="planted",
    )
    defects = cps.rule_defects([never])
    assert defects, "rule_defects accepted a rule that cannot fire on its own sample"
    assert any("never-fires" in d for d in defects)


def test_b5_the_self_check_is_two_sided_a_rule_that_always_fires_is_reported():
    always = cps.Rule(
        name="always-fires",
        pattern=re.compile("sample"),
        exempt=None,
        fires_on="positive sample",
        silent_on="negative sample",
        why="planted",
    )
    defects = cps.rule_defects([always])
    assert defects, "rule_defects accepted a rule that fires on its own negative sample"
    assert any("always-fires" in d for d in defects)


# ===========================================================================
# B6  The path rules require at least ONE NAME CHARACTER after the marker.
#     That is not a detail: it is the mechanism that lets the scanner hold a
#     marker itself and still stay silent, which is why no exemption list and
#     no self-exclusion are needed.
# ===========================================================================


@pytest.mark.parametrize("rule_name", PATH_RULE_NAMES)
def test_b6_a_bare_marker_is_silent(rule_name):
    rule = BY_NAME[rule_name]
    assert cps.matches(rule, _marker(rule_name)) == []


@pytest.mark.parametrize("rule_name", PATH_RULE_NAMES)
@pytest.mark.parametrize("tail", ["x", "A", "7", ".", "_", "-"])
def test_b6_a_marker_followed_by_a_name_character_fires(rule_name, tail):
    rule = BY_NAME[rule_name]
    assert cps.matches(rule, _marker(rule_name) + tail) == [_marker(rule_name) + tail]


@pytest.mark.parametrize("rule_name", PATH_RULE_NAMES)
@pytest.mark.parametrize("tail", ['"', "'", " ", "/", ")", "`", "\n", ""])
def test_b6_a_marker_followed_by_a_non_name_character_stays_silent(rule_name, tail):
    rule = BY_NAME[rule_name]
    assert cps.matches(rule, _marker(rule_name) + tail) == []


def test_b6_the_marker_is_found_mid_line_and_the_line_number_is_reported():
    dirty = "one\ntwo\n" + "prefix " + _marker("macos-account-home") + "name suffix\n"
    got = cps.findings("doc.md", dirty)
    assert [(f.path, f.line, f.rule) for f in got] == [
        ("doc.md", 3, "macos-account-home")
    ]


# ===========================================================================
# B7  NO exemption list and NO self-exclusion.  The scanner is a member of the
#     domain it scans and stays silent, and so is this test file.
# ===========================================================================


def test_b7_the_gate_source_is_silent_under_its_own_rules():
    """Read as BYTES, not as logic: this is the only way to assert the self-scan."""
    text = TOOL.read_text(encoding="utf-8")
    assert cps.findings(TOOL_REL, text) == []


def test_b7_this_test_file_is_silent_under_the_gate():
    """The trap iteration 06 hit live: a self-scanning check red on its own sample."""
    rel = "tests/" + pathlib.Path(__file__).name
    text = pathlib.Path(__file__).read_text(encoding="utf-8")
    assert cps.findings(rel, text) == []


def test_b7_the_gate_is_inside_the_domain_it_scans_once_it_is_tracked():
    """Conditional ON PURPOSE: at tester time the new tool is still untracked, so a
    hard assertion here would red the suite before the commit and green after it. The
    self-scan property itself is asserted unconditionally above."""
    tracked = cps.tracked_files(REPO)
    if TOOL_REL in tracked:
        proc = _live_scan()
        assert proc.returncode == 0
        assert f"{len(tracked)} tracked file(s)" in proc.stdout
    else:
        assert TOOL.exists(), "the gate must exist even before it is committed"


def test_b7_only_the_address_rule_carries_an_exemption():
    exempting = [r.name for r in cps.RULES if r.exempt is not None]
    assert exempting == [EMAIL_RULE_NAME]


def test_b7_no_rule_exempts_a_repository_path():
    """An exemption naming a file is an allowlist wearing a rule's clothes."""
    for rule in cps.RULES:
        if rule.exempt is None:
            continue
        for tracked in ("tests/", "tools/", "gaps/", "src/", ".md", ".py", ".json"):
            assert tracked not in rule.exempt.pattern, (
                f"{rule.name} exempts a repository path, which is an allowlist"
            )


# ===========================================================================
# B8  The address rule exempts the RESERVED DOMAIN CLASS, not a set of files,
#     and the exemption is anchored to the whole tail so a lookalike fires.
# ===========================================================================


@pytest.mark.parametrize(
    "domain",
    [
        "example.com",
        "example.net",
        "example.org",
        "sub.example.org",
        "deep.sub.example.com",
        "thing.invalid",
        "host.test",
    ],
)
def test_b8_an_address_at_a_reserved_domain_is_silent(domain):
    rule = BY_NAME[EMAIL_RULE_NAME]
    assert cps.matches(rule, _addr("fixture", domain)) == []


@pytest.mark.parametrize(
    "domain",
    ["mail-host.net", "company-x.co.uk", "host.io", "example.com.evil.co", "invalid.co", "test.evil.co"],
)
def test_b8_an_address_at_a_real_domain_fires_even_if_it_looks_reserved(domain):
    rule = BY_NAME[EMAIL_RULE_NAME]
    composed = _addr("person", domain)
    assert cps.matches(rule, composed) == [composed]


def test_b8_the_exemption_is_a_domain_class_so_it_holds_at_any_host_depth():
    rule = BY_NAME[EMAIL_RULE_NAME]
    host = "example.org"
    for depth in range(4):
        domain = ".".join(["sub"] * depth + [host]) if depth else host
        assert cps.matches(rule, _addr("fixture", domain)) == [], domain


def test_b8_the_committed_negative_sample_is_at_a_reserved_domain():
    """The rule's own silent sample must be silent BECAUSE of the exemption, so that
    the exemption is what this rule is two-sided about."""
    rule = BY_NAME[EMAIL_RULE_NAME]
    assert rule.exempt is not None
    assert rule.pattern.search(rule.silent_on) is not None, (
        "the negative sample must be a real address, or the exemption is never exercised"
    )
    assert cps.matches(rule, rule.silent_on) == []


# ===========================================================================
# B9  The two rules REJECTED on measurement stay rejected, and the reason is
#     enforced rather than remembered: a windows-drive rule fired 467 times on
#     correct data, and an ascii-purity rule would red the tracked files that
#     legitimately carry non-ascii verbatim quotes.
# ===========================================================================


def test_b9_no_rule_fires_on_a_windows_drive_path():
    windows = "C:" + _marker("macos-account-home").replace("/", "\\") + "account\\notes.md"
    assert cps.findings("doc.md", windows) == []


def test_b9_no_rule_fires_on_an_escaped_newline_inside_a_json_quote():
    """The measured shape that made the rejected rule fire 467 times: drive letter,
    backslash, name character -- which is what `\\n` inside a JSON string looks like."""
    quoted = '{"quote": "first line\\nsecond line", "id": "GAP-001"}'
    assert cps.findings("gaps/GAP-001.json", quoted) == []


def test_b9_no_rule_fires_on_non_ascii_text():
    for ch in ("\u00e9", "\u2014", "\u201c", "\u4e2d", "\u00a0"):
        assert cps.findings("doc.md", "a verbatim quote with " + ch + " in it") == []


def test_b9_the_tracked_tree_really_does_carry_non_ascii_and_is_still_green():
    """Without this, the ascii-purity rejection is a claim rather than a constraint."""
    carriers = []
    for rel in cps.tracked_files(REPO):
        path = REPO / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(ord(ch) > 127 for ch in text):
            carriers.append(rel)
    assert carriers, "no tracked file carries non-ascii, so the rejection is untested"
    proc = _live_scan()
    assert proc.returncode == 0


# ===========================================================================
# B10  Output discipline from the quality bar: stdout carries only the
#      document, errors go to stderr prefixed `Error: ` with exit 2, and every
#      stream ends in exactly ONE newline.
# ===========================================================================


def test_b10_a_clean_run_writes_one_line_to_stdout_and_nothing_to_stderr():
    proc = _live_scan()
    assert proc.stderr == ""
    assert proc.stdout.count("\n") == 1
    assert proc.stdout.endswith("\n") and not proc.stdout.endswith("\n\n")


def test_b10_an_error_writes_nothing_to_stdout_and_one_prefixed_line_to_stderr(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(TOOL), str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.startswith("Error: ")
    assert proc.stderr.endswith("\n") and not proc.stderr.endswith("\n\n")
    assert proc.stderr.count("\n") == 1


def test_b10_a_finding_report_ends_in_exactly_one_newline():
    list_fn, read_fn = _one_file(_marker("macos-account-home") + "someone/x")
    code, out, err = _run_main([str(REPO)], list_fn=list_fn, read_fn=read_fn)
    assert code == 1
    assert out.endswith("\n") and not out.endswith("\n\n")
    assert err == ""


# ===========================================================================
# B11  The verdict is reachable OFFLINE through the call-time seams, and the
#      seams BITE: a substituted lister and reader must be the ones consulted.
# ===========================================================================


def test_b11_the_reader_seam_is_the_one_consulted():
    seen = []

    def recording_read(path):
        seen.append(path)
        return "clean line"

    code, out, err = _run_main(
        [str(REPO)], list_fn=lambda: ["one.md", "two.md"], read_fn=recording_read
    )
    assert code == 0
    assert seen == ["one.md", "two.md"], (
        "main() did not consult the substituted reader, so the seam is decorative"
    )


def test_b11_the_lister_seam_is_the_one_consulted():
    code, out, err = _run_main(
        [str(REPO)], list_fn=lambda: ["only.md"], read_fn=lambda path: "clean"
    )
    assert code == 0
    assert out.startswith("1 tracked file(s) scanned"), (
        "main() reported a domain size the substituted lister did not produce"
    )


def test_b11_a_custom_rule_set_is_honored_by_findings():
    """`findings` takes the rules as data, so a caller can prove a verdict offline."""
    only_email = [BY_NAME[EMAIL_RULE_NAME]]
    dirty_path = _marker("macos-account-home") + "someone/x"
    assert cps.findings("doc.md", dirty_path) != []
    assert cps.findings("doc.md", dirty_path, rules=only_email) == []
    assert cps.findings("doc.md", BY_NAME[EMAIL_RULE_NAME].fires_on, rules=only_email) != []


def test_b11_the_scan_touches_no_network_and_needs_no_runtime_dependency():
    """Offline-first: the gate must run under a bare interpreter with no site packages."""
    proc = subprocess.run(
        [sys.executable, "-S", "-c",
         "import sys, pathlib; sys.path.insert(0, 'tools'); "
         "import check_public_safety as m; "
         "print(len(m.RULES)); print(m.rule_defects(m.RULES))"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["4", "[]"]


# ===========================================================================
# B12  The verdict this iteration SHIPS is the verdict over the domain that
#      exists AFTER the commit, which is a superset of today's index: at
#      tester time both new files are still untracked, so the live run above
#      clears a domain that excludes the very files under review.
# ===========================================================================


def _post_commit_domain() -> list[str]:
    """Today's index plus whatever of this iteration's two files it does not yet hold.

    Idempotent on purpose: before the commit this adds two paths, after the commit it
    adds none, so the same assertion holds on both sides of the ship.
    """
    tracked = cps.tracked_files(REPO)
    shipping = [TOOL_REL, "tests/" + pathlib.Path(__file__).name]
    return sorted(tracked + [rel for rel in shipping if rel not in tracked])


def test_b12_the_domain_this_iteration_ships_is_clean_including_its_own_two_files():
    domain = _post_commit_domain()
    for rel in (TOOL_REL, "tests/" + pathlib.Path(__file__).name):
        assert rel in domain
    code, out, err = _run_main(
        [str(REPO)],
        list_fn=lambda: domain,
        read_fn=lambda rel: (REPO / rel).read_text(encoding="utf-8"),
    )
    assert code == 0, f"the post-commit domain is not clean: stdout={out!r} stderr={err!r}"
    assert err == ""
    assert out == (
        f"{len(domain)} tracked file(s) scanned against {len(cps.RULES)} rule(s): 0 finding(s)\n"
    )


def test_b12_the_shipping_domain_is_a_superset_of_the_live_one():
    """Guards the guard: if this ever equals the live domain BEFORE the commit, the test
    above has quietly stopped covering the new files."""
    live = cps.tracked_files(REPO)
    domain = _post_commit_domain()
    assert set(live) <= set(domain)
    assert len(domain) - len(live) == sum(
        1 for rel in (TOOL_REL, "tests/" + pathlib.Path(__file__).name) if rel not in live
    )


# ===========================================================================
# B13  The domain root is the ARGUMENT, not the process cwd -- a gate invoked
#      from a subdirectory must still clear the whole tree -- and a bare
#      invocation falls back to the cwd rather than to nothing.
# ===========================================================================


def _tracked_count(cwd: pathlib.Path) -> int:
    listed = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=str(cwd)
    )
    assert listed.returncode == 0
    return len([line for line in listed.stdout.splitlines() if line])


def test_b13_invoked_from_a_subdirectory_the_root_argument_still_scans_the_whole_tree():
    whole = _tracked_count(REPO)
    proc = subprocess.run(
        [sys.executable, str(TOOL), str(REPO)],
        capture_output=True,
        text=True,
        cwd=str(REPO / "tests"),
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout.startswith(f"{whole} tracked file(s) scanned")


def test_b13_a_subtree_root_narrows_the_domain_to_that_subtree():
    """The control for the test above: if the root argument were ignored, these two
    invocations would report the SAME count and neither test would mean anything."""
    whole = _tracked_count(REPO)
    subtree = _tracked_count(REPO / "tests")
    assert 0 < subtree < whole, "tests/ must be a strict non-empty subset for this control"
    proc = subprocess.run(
        [sys.executable, str(TOOL), str(REPO / "tests")],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout.startswith(f"{subtree} tracked file(s) scanned")


def test_b13_a_bare_invocation_scans_the_cwd_domain():
    whole = _tracked_count(REPO)
    proc = subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, text=True, cwd=str(REPO)
    )
    assert proc.returncode == 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.stdout.startswith(f"{whole} tracked file(s) scanned")


# ===========================================================================
# B14  The address exemption is LOAD-BEARING on real data, not decorative:
#      remove it and the live tracked tree goes RED.  Without this the green
#      run is compatible with the tree simply holding no address at all.
# ===========================================================================


def _unexempted(rule):
    return cps.Rule(
        name=rule.name,
        pattern=rule.pattern,
        exempt=None,
        fires_on=rule.fires_on,
        silent_on=rule.silent_on,
        why=rule.why,
    )


def _scan_tree(rules):
    hits = []
    for rel in cps.tracked_files(REPO):
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        hits.extend(cps.findings(rel, text, rules=rules))
    return hits


def test_b14_dropping_the_exemption_reds_the_live_tree():
    live = BY_NAME[EMAIL_RULE_NAME]
    without = _scan_tree([_unexempted(live)])
    assert without, (
        "the live tree holds no address at all, so the exemption is untested by real data "
        "and the green scan proves nothing about it"
    )
    assert {f.rule for f in without} == {EMAIL_RULE_NAME}


def test_b14_with_the_exemption_the_same_occurrences_are_silent():
    live = BY_NAME[EMAIL_RULE_NAME]
    assert _scan_tree([live]) == [], "the exemption does not cover the live occurrences"


def test_b14_the_live_occurrences_sit_in_test_fixtures_not_in_register_data():
    """Where they are matters: a real address in a gap record would be a leak the
    exemption must NOT be widened to cover."""
    without = _scan_tree([_unexempted(BY_NAME[EMAIL_RULE_NAME])])
    assert without
    for finding in without:
        assert finding.path.startswith("tests/"), (
            f"an address-shaped token sits outside tests/: {finding.path}"
        )


def test_b14_a_live_scan_writes_nothing_to_the_files_it_reads():
    """A gate that edits the tree it audits is worse than no gate."""
    watched = [TOOL, pathlib.Path(__file__)]
    before = [(p, hashlib.sha256(p.read_bytes()).hexdigest()) for p in watched]
    proc = _live_scan()
    assert proc.returncode == 0
    after = [(p, hashlib.sha256(p.read_bytes()).hexdigest()) for p in watched]
    assert before == after
