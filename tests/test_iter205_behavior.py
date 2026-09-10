"""Iteration 205 behaviors: the SCANNED repository no longer chooses a command we run.

`pm.md`: `checks.tracked_files()` shells out to `git ls-files`, and `git` honors the
TARGET tree's `.git/config` -- so a hostile repo carrying `core.fsmonitor = <script>`
made `radar scan` execute that script. This iteration pins the one invocation against
the target's own configuration, derives the neutralised settings from a published
constant, and states the claim's limit in the consumer contract.

BLACK-BOX, AND THE ISOLATION CONTRACT IS HONORED. Every expectation here comes from
`pm.md` (Feature / Why / Expected Behaviors) and is measured by RUNNING the product --
`radar scan` across a real process boundary, `checks.tracked_files()` as a public
helper, `tools/check_public_safety.py` and `tools/roadmap_integrity.py` as committed
brakes -- or by reading PUBLISHED prose (`docs/CONSUMER_CONTRACT.md`, `PRODUCT.md`).
Nothing here was read from `src/`, from the engineer's or the reviewer's notes, from
`IMPLEMENTATION.patch`, or from any diff.

STRUCTURAL CHOICES, so this file cannot lie later:

* **THE FIXTURE IS ARMED IN EVERY TEST THAT ASSERTS AN ABSENCE, AND IT IS ARMED LAST.**
  The assertion this module ships is that a marker file DOES NOT EXIST, and that passes
  over a fixture that stopped being hostile -- a broken `git init`, a script that lost
  its `+x` bit, a git build without fsmonitor support, a typo in the config key. So the
  product is driven FIRST and the raw-`git` control runs AFTERWARDS on the same repo in
  the same state: if the control fails to create the marker the test fails, and the
  ordering means the control cannot have primed any cache that made the product's run
  vacuous.
* **Every victim repo is built under the test's own `tmp_path`**, per-test rather than
  module-scoped, so the marker path of one test can never be the marker of another. No
  absolute machine path, home path or identifier is written down: every path is derived
  from `tmp_path` or from `__file__`.
* **No global git configuration is read or written.** Identity is passed per command
  with `-c`, and every `git config` write targets the throwaway repo.
* **`git` may be absent**: the module skips rather than passing (spec behavior 2).
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The product's own entry point, driven across a real process boundary.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: The live register `radar scan` reads.
REGISTER = REPO_ROOT / "gaps"

#: Identity passed per command, so no global git config is consulted or written.
FIXTURE_IDENTITY = (
    "-c", "user.name=fixture",
    "-c", "user.email=fixture@example.invalid",
    "-c", "commit.gpgsign=false",
)

#: The one setting the spec names by name (behavior 5).
NAMED_SETTING = "core.fsmonitor"

#: The tracked file every victim repo holds, and the only one (behavior 3).
TRACKED_NAME = "a.py"


def _git(root: pathlib.Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, timeout=180
    )


def _victim(tmp_path: pathlib.Path, *, arm: bool = True) -> tuple[pathlib.Path, pathlib.Path]:
    """A scratch git repo holding one committed file, plus the marker path.

    When `arm` is true the repo's OWN config points `core.fsmonitor` at a script whose
    only effect is to create the marker. Nothing outside `tmp_path` is touched.
    """
    if shutil.which("git") is None:
        pytest.skip("git executable not available")
    root = tmp_path / "victim"
    root.mkdir(parents=True, exist_ok=True)
    marker = tmp_path / "marker.txt"
    (root / TRACKED_NAME).write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    _git(root, "add", "-A")
    _git(root, *FIXTURE_IDENTITY, "commit", "-q", "-m", "fixture")
    if arm:
        _arm(root, marker, tmp_path)
    return root, marker


def _arm(root: pathlib.Path, marker: pathlib.Path, tmp_path: pathlib.Path) -> None:
    """Point the repo's own `core.fsmonitor` at a marker-creating script."""
    script = tmp_path / "hook.sh"
    script.write_text(
        "#!/bin/sh\n"
        f'printf run > "{marker}"\n'
        "exit 1\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    _git(root, "config", NAMED_SETTING, str(script))


def _scan(target: pathlib.Path) -> subprocess.CompletedProcess[bytes]:
    """`radar scan <target> --gaps gaps` across a real process boundary, bytes not text."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, "scan", str(target), "--gaps", str(REGISTER)],
        cwd=str(REPO_ROOT), capture_output=True, timeout=180,
    )


def _armed_control(root: pathlib.Path, marker: pathlib.Path) -> subprocess.CompletedProcess[bytes]:
    """Behavior 2. Raw `git ls-files -z`, NO `-c` override: the fixture must bite."""
    return _git(root, "ls-files", "-z")


# ===========================================================================
# B1  Hostile target, process boundary, nothing executed
# B2  ... and the fixture is armed, asserted AFTER the product ran
# ===========================================================================


def test_b1_scanning_a_hostile_repo_executes_nothing_and_b2_the_fixture_is_armed(tmp_path):
    root, marker = _victim(tmp_path)

    proc = _scan(root)

    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert proc.stderr == b"", proc.stderr.decode("utf-8", "replace")
    assert proc.stdout, "scan wrote no document"
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")
    assert not marker.exists(), (
        "the scanned repository's own core.fsmonitor script RAN: " + marker.name
    )

    # Behavior 2 -- the control, in the same test and AFTER the product's run.
    control = _armed_control(root, marker)
    assert control.stdout == TRACKED_NAME.encode() + b"\0", control.stdout
    assert marker.exists(), (
        "FIXTURE NOT ARMED: raw `git ls-files -z` did not run core.fsmonitor, so the "
        "absence asserted above proves nothing"
    )


# ===========================================================================
# B3  Safety is not bought with correctness
# ===========================================================================


def test_b3_the_pinned_invocation_still_resolves_the_tracked_set(tmp_path):
    """Behavior 3. `frozenset({<victim>/a.py})`, never `None`: a `None` here would be a
    silent fallback to the hand-maintained skip list, which WIDENS the scanned domain."""
    from agent_gap_radar import checks

    root, marker = _victim(tmp_path)

    got = checks.tracked_files(root)

    assert got is not None, "tracked_files fell back instead of resolving the tracked set"
    assert isinstance(got, frozenset), type(got).__name__
    assert {pathlib.Path(p).resolve() for p in got} == {(root / TRACKED_NAME).resolve()}, got
    assert not marker.exists(), "tracked_files executed the target's own fsmonitor script"

    control = _armed_control(root, marker)
    assert control.stdout == TRACKED_NAME.encode() + b"\0", control.stdout
    assert marker.exists(), "FIXTURE NOT ARMED: the absence asserted above proves nothing"


# ===========================================================================
# B4  An honest target is byte-identical before and after the config is armed
# ===========================================================================


def test_b4_an_honest_target_is_byte_identical_before_and_after_arming(tmp_path):
    """Behavior 4. Two fresh processes over ONE repo whose only change is the hostile
    setting: same bytes, exit 0 both times, marker never appears. So the hardening moves
    no output on any target."""
    root, marker = _victim(tmp_path, arm=False)

    before = _scan(root)
    assert before.returncode == 0, before.stderr.decode("utf-8", "replace")
    assert before.stdout, "scan wrote no document"

    _arm(root, marker, tmp_path)

    after = _scan(root)
    assert after.returncode == 0, after.stderr.decode("utf-8", "replace")
    assert after.stdout == before.stdout, "the hostile setting moved the document"
    assert after.stderr == b"" == before.stderr
    assert not marker.exists(), "the target's own fsmonitor script RAN"

    control = _armed_control(root, marker)
    assert control.stdout == TRACKED_NAME.encode() + b"\0", control.stdout
    assert marker.exists(), "FIXTURE NOT ARMED: the absence asserted above proves nothing"


# ===========================================================================
# B5  The neutralised settings are DERIVED and PUBLISHED, never hand-typed twice
# ===========================================================================


def _settings() -> tuple[str, ...]:
    from agent_gap_radar import checks

    return checks.UNTRUSTED_GIT_SETTINGS


def test_b5_the_published_constant_is_a_non_empty_tuple_of_settings():
    got = _settings()
    assert isinstance(got, tuple), type(got).__name__
    assert got, "UNTRUSTED_GIT_SETTINGS is empty, so nothing is neutralised"
    assert all(isinstance(s, str) and s for s in got), got
    assert len(set(got)) == len(got), got
    assert NAMED_SETTING in got, got


def test_b5_the_argv_carries_an_empty_override_for_every_setting_before_ls_files(monkeypatch,
                                                                                tmp_path):
    """Behavior 5. The argv `tracked_files` hands `subprocess.run` must carry `-c` and
    `<setting>=` for EVERY element, each positioned BEFORE the `ls-files` token."""
    from agent_gap_radar import checks

    root, marker = _victim(tmp_path)
    seen: list[list[str]] = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append([str(t) for t in argv])
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(checks.subprocess, "run", spy)
    checks.tracked_files(root)

    assert len(seen) == 1, seen  # one subprocess per resolution, and it is the one we read
    argv = seen[0]
    assert "ls-files" in argv, argv
    verb = argv.index("ls-files")
    for setting in _settings():
        override = f"{setting}="
        assert override in argv, (setting, argv)
        i = argv.index(override)
        assert i >= 1 and argv[i - 1] == "-c", (setting, argv)
        assert i < verb, (setting, argv)
    assert not marker.exists(), "the spied invocation executed the target's script"

    monkeypatch.setattr(checks.subprocess, "run", real)
    control = _armed_control(root, marker)
    assert control.stdout == TRACKED_NAME.encode() + b"\0", control.stdout
    assert marker.exists(), "FIXTURE NOT ARMED: the absence asserted above proves nothing"


CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: A git config key SHAPE. Lowercase after the dot, which excludes the constant's own
#: name (`checks.UNTRUSTED_GIT_SETTINGS`).
_KEY = re.compile(r"^[a-z][a-z0-9-]*\.[a-z][A-Za-z0-9-]*$")

#: ... and a git config key's last segment is never a FILE extension. This exclusion is
#: load-bearing, not defensive: the live `## radar scan` section already backticks
#: `dispatcher.py` and `watchdog.py`, which the shape above matches.
_FILE_SUFFIX = re.compile(r"\.(py|md|json|toml|txt|sh|yml|yaml|cfg|ini|lock)$")


def _scan_section() -> str:
    lines = CONTRACT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## `radar scan`"))
    end = next((i for i, line in enumerate(lines[start + 1:], start + 1)
                if line.startswith("## ")), len(lines))
    return "\n".join(lines[start:end])


def _settings_paragraph() -> str:
    """The paragraph of the `## radar scan` section that names the PUBLISHED list.

    Scoped by the constant's own name -- vocabulary the spec fixes -- rather than by any
    sentence wording, and required to be unique so a second paragraph cannot dilute it.
    """
    paras = [p for p in re.split(r"\n\s*\n", _scan_section())
             if "checks.UNTRUSTED_GIT_SETTINGS" in p]
    assert len(paras) == 1, f"expected exactly one paragraph naming the list, got {len(paras)}"
    return paras[0]


def _keys_in(text: str) -> set[str]:
    return {t for t in re.findall(r"`([^`\n]+)`", text)
            if _KEY.match(t) and not _FILE_SUFFIX.search(t)}


def test_b5_the_prose_reads_back_the_constant_in_both_directions():
    """Behavior 5. Set equality BOTH ways, so neither a setting missing from the prose
    nor a setting named in the prose but not neutralised can pass."""
    published = _keys_in(_settings_paragraph())
    assert published == set(_settings()), (published, _settings())


def test_b5_every_setting_appears_verbatim_in_the_published_paragraph():
    para = _settings_paragraph()
    for setting in _settings():
        assert f"`{setting}`" in para, setting


def test_b5_the_key_reader_is_two_sided():
    """The extractor must be shown to FIND keys and to return NONE where there are none,
    so an empty result can never read as agreement."""
    assert _keys_in(_settings_paragraph()), "extractor found nothing in the live paragraph"
    assert _keys_in("no settings here: `verdict`, `reason`, `dispatcher.py`") == set()
    assert _keys_in("armed: `core.fsmonitor`") == {NAMED_SETTING}
    # The two tokens the live section really carries must read as file names, not keys.
    assert _keys_in("`dispatcher.py` `watchdog.py`") == set()


# ===========================================================================
# B6  The claim's limit is stated, and the single call site is pinned
# ===========================================================================


def test_b6_the_contract_says_the_targets_git_configuration_is_not_trusted():
    para = _settings_paragraph().lower()
    assert re.search(r"git config\w*", para), para
    assert re.search(r"\bnot\s+trusted\b", para), para


def test_b6_the_contract_says_only_the_named_settings_are_neutralised():
    para = _settings_paragraph().lower()
    assert re.search(r"\bonly\b[^.]*\bnamed\b", para), para


def test_b6_the_contract_refuses_to_claim_the_list_is_complete():
    para = _settings_paragraph().lower()
    assert re.search(r"\bnot\b[^.]*\bcomplete\b", para), para


SRC = REPO_ROOT / "src" / "agent_gap_radar"


def _src_files() -> list[pathlib.Path]:
    files = sorted(SRC.rglob("*.py"))
    assert len(files) > 3, files  # the domain is real, so the counts below mean something
    return files


def test_b6_exactly_one_subprocess_run_call_site_exists_under_src():
    """Behavior 6. A second git invocation added later cannot skip the neutralisation
    without reading this brake."""
    sites = [(f.relative_to(REPO_ROOT).as_posix(), f.read_text(encoding="utf-8").count(
        "subprocess.run")) for f in _src_files()]
    total = sum(n for _, n in sites)
    assert total == 1, [s for s in sites if s[1]]


def test_b6_no_second_hand_typed_c_override_exists_under_src():
    """Acceptance criterion: the argv is BUILT from the constant, not typed twice."""
    literals = sum(
        len(re.findall(r"""(?<![\w-])["']-c["']""", f.read_text(encoding="utf-8")))
        for f in _src_files()
    )
    assert literals == 1, literals


# ===========================================================================
# Committed brakes, at the process boundary
# ===========================================================================


@pytest.mark.parametrize("tool", ["check_public_safety.py", "roadmap_integrity.py"])
def test_the_committed_brakes_stay_green_over_the_new_files(tool):
    proc = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / tool)],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
