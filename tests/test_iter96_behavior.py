"""Iteration 96 behaviours: the SUITE fails on ANY warning, and the glob character-class
escape that names that contract as its reason gets a direct two-sided proof.

WHAT THIS ITERATION CLAIMS, IN BEHAVIOURAL TERMS
`[tool.pytest.ini_options]` carries `filterwarnings = ["error"]`, so a warning raised
anywhere in the suite is a failure rather than a line nobody reads. The product's own glob
character-class path -- a body whose FIRST character is `[`, the case the product's prose
names -- is then shown to be SILENT under that filter while the raw splice it replaced still
SCREAMS, so the brake is proven to bite on the one case it was written for rather than merely
to exist.

ISOLATION. This module honours the tester's isolation contract: it reads `pm.md`, this repo's
`tests/` conventions, `pyproject.toml` (configuration, not implementation), and the product's
own behaviour by RUNNING it. It does not read `src/`, the engineer's or the reviewer's notes,
`IMPLEMENTATION.patch`, or any diff. Behaviour 7's `src/` walk is MECHANICAL -- it counts
occurrences of one literal and never inspects what the files say -- and it carries a positive
control, so a walk that silently read nothing cannot pass as "no hits".

WHY EVERY WARNING CLAIM IS PAIRED
A warning assertion is the easiest kind to write vacuously: a call that raises nothing because
the warning was de-duplicated, or a filter that "works" because the pattern was compiled and
cached by an earlier test, both look identical to a real pass. So every arm has a partner.

* Behaviour 1 (a bare `warnings.warn` RAISES) is paired with behaviour 2, the SAME call under
  an explicit `simplefilter("default")`, which must NOT raise and must RECORD exactly one
  warning. One arm proves the filter is live; the other proves the call really warns.
* Behaviour 4 (`iter_files` is silent) is paired with behaviour 6, the raw `re` splice under
  the identical filter state, which MUST raise `FutureWarning`. Without that pair, "no
  warning" is indistinguishable from "this filter state cannot raise anything".
* Behaviour 5 makes behaviour 4 non-vacuous on the other axis: the call has to SELECT a real
  file, so a matcher that silently matched nothing would fail.
* Behaviour 6's second arm is the POSITION control: a class body of `a[` emits no warning at
  all under `simplefilter("always")`, so a control built on that body would pass at any filter
  setting and prove nothing.

TWO DELIBERATE NON-ASSERTIONS, NAMED SO A LATER ITERATION DOES NOT "FIX" THEM
1. The exact CPython warning text `at position 1` is NOT pinned. `Possible nested set` is; the
   position claim is carried by the paired `a[` control instead, because a CPython message
   tweak is not a defect in this product and must not red this suite.
2. "No file under `src/agent_gap_radar/` is modified by this iteration" is an assertion about a
   DIFF, which this station may not read and which no committed test can hold durably -- a
   later iteration is entitled to touch `src/`. Its testable half, that no warning suppression
   ships INSIDE the product, is behaviour 7; the diff half is named in `tester.md` as
   final-gate work.
"""

from __future__ import annotations

import pathlib
import re
import tomllib
import warnings

import pytest

from agent_gap_radar import checks
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"
SELF_PATH = pathlib.Path(__file__).resolve()

#: Behaviour 1/2 use one message so the two arms are provably the SAME call.
PROBE_MESSAGE = "iter96 probe"

#: Behaviour 4/5. The character-class body's FIRST character is `[`, which is the only
#: position that provokes `FutureWarning: Possible nested set` (see behaviour 6's control).
CLASS_BODY_GLOB = "[[]*.json"

#: A second, module-unique pattern. `_glob_regex` is memoised process-wide, so a pattern any
#: other test module also uses could be served from a warm cache and never compiled at all --
#: which would make behaviour 4 pass without ever exercising the escape. This one occurs
#: nowhere else in `tests/`, so its first call in any worker process is a real compile.
UNIQUE_CLASS_BODY_GLOB = "[[]iter96*.json"

#: The raw splice the product's escape exists to replace: a class body spliced into a regex
#: without escaping, so `[` + `[` + `]` reaches `re` as `[[]`.
RAW_SPLICE = "[" + "[" + "]"


def _ini_filterwarnings() -> object:
    """Behaviour 3's seam: the ini value as it is SPELLED ON DISK.

    Read with `tomllib` rather than through pytest's resolved config on purpose. Pytest merges
    a command-line `-W` into the same effective filter set, so its resolved view cannot tell a
    committed configuration from a flag somebody typed once; the file can.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]["filterwarnings"]


# ---------------------------------------------------------------------------
# Behaviour 1 -- the filter is live with no help from the caller.
# ---------------------------------------------------------------------------

def test_b1_a_bare_warning_is_an_error_under_the_declared_command():
    """No `-W` on the command line, no `filterwarnings` mark on this test: it still raises.

    The absence of a local mark is not left to a reader's eye -- the module asserts it about
    its own source text in `test_b1_the_raise_is_not_locally_engineered`.
    """
    with pytest.raises(UserWarning) as excinfo:
        warnings.warn(PROBE_MESSAGE, UserWarning)
    assert str(excinfo.value) == PROBE_MESSAGE


def test_b1_the_raise_is_not_locally_engineered():
    """Behaviour 1 must be attributable to the ini, so this module may not cheat.

    A `@pytest.mark.filterwarnings("error")` anywhere in here would make behaviour 1 pass on a
    repo whose `pyproject.toml` never gained the line. Reading this module's OWN text is the
    only way to close that hole from inside the suite.
    """
    own_text = SELF_PATH.read_text(encoding="utf-8")

    # Gate on the DECORATOR FORM, not on the bare token: this module has to discuss the mark
    # in prose to explain why it refuses to use one, so a token search would accuse its own
    # docstring. Measured -- the first draft of this assertion did exactly that.
    decorators = [
        line.strip()
        for line in own_text.splitlines()
        if line.strip().startswith("@") and "filterwarnings" in line
    ]
    assert decorators == [], f"a local filterwarnings mark would void behaviour 1: {decorators}"

    # The other cheat available from inside a test module is installing a process-wide
    # suppression at import time. The needle is assembled at runtime so that naming it here
    # cannot make this assertion fail on itself.
    for needle in ("warnings." + "filterwarnings(", "simplefilter(" + chr(34) + "ignore"):
        assert needle not in own_text, f"module-level warning suppression: {needle}"


# ---------------------------------------------------------------------------
# Behaviour 2 -- behaviour 1 is not vacuous.
# ---------------------------------------------------------------------------

def test_b2_the_same_call_is_harmless_under_an_explicit_default_filter():
    """The identical call, under `simplefilter("default")`, neither raises nor fails.

    This is what separates "the filter turned a real warning into an error" from "this call
    cannot warn" and from "this interpreter cannot raise". `record=True` supplies the positive
    half: exactly one `UserWarning` carrying the same message is observed.
    """
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("default")
        warnings.warn(PROBE_MESSAGE, UserWarning)

    assert [w.category for w in recorded] == [UserWarning]
    assert str(recorded[0].message) == PROBE_MESSAGE


# ---------------------------------------------------------------------------
# Behaviour 3 -- the configuration is what makes behaviour 1 true.
# ---------------------------------------------------------------------------

def test_b3_pyproject_pins_the_error_filter_as_its_first_element():
    value = _ini_filterwarnings()
    assert isinstance(value, list)
    assert value, "filterwarnings must not be an empty list"
    assert all(isinstance(element, str) for element in value)
    assert value[0] == "error"


def test_b3_the_neighbouring_ini_keys_are_still_present():
    """A caller cannot silently lose the filter, and the filter cannot silently cost the
    suite its existing invocation: `addopts` and `testpaths` are asserted to still exist.

    Their VALUES are deliberately not pinned here -- iteration 18 already refused one change
    to `addopts` and a later iteration may legitimately make another -- but their disappearance
    would mean the ini block was rewritten rather than extended.
    """
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    ini = data["tool"]["pytest"]["ini_options"]
    assert "addopts" in ini
    assert "testpaths" in ini
    assert isinstance(ini["addopts"], str)
    assert isinstance(ini["testpaths"], list)


# ---------------------------------------------------------------------------
# Behaviours 4 and 5 -- the product's glob character-class path is silent, and selective.
# ---------------------------------------------------------------------------

def test_b4_b5_glob_character_class_is_silent_under_an_error_filter(tmp_path):
    """`iter_files` over a glob whose class body opens with `[` raises nothing, and SELECTS.

    Behaviour 4 is the silence; behaviour 5 is the selection. Both run inside ONE
    `simplefilter("error")` state, so the silence cannot be credited to a filter that was only
    entered for the trivial half. The directory holds exactly the two files the spec names, and
    that premise is asserted rather than assumed -- a fixture that quietly grew a third file
    would turn behaviour 5's equality into a different claim.
    """
    (tmp_path / "[a].json").write_text("{}", encoding="utf-8")
    (tmp_path / "plain.json").write_text("{}", encoding="utf-8")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["[a].json", "plain.json"]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        selected = checks.iter_files(tmp_path, [CLASS_BODY_GLOB])
        everything = checks.iter_files(tmp_path, ["*.json"])

    assert isinstance(selected, list)
    assert [p.name for p in selected] == ["[a].json"]

    # The premise behind "rejects `plain.json`": both files really are in the domain, so the
    # single-element answer above is a matcher decision and not an empty directory.
    assert sorted(p.name for p in everything) == ["[a].json", "plain.json"]


def test_b4_the_escape_runs_on_a_pattern_no_other_test_can_have_cached(tmp_path):
    """The same silence on a pattern that is provably compiled rather than memoised.

    The glob->regex translation is memoised process-wide. A pattern another module also uses
    could therefore be served from a warm cache, so "no warning" would be attributable to "no
    compile happened" -- the vacuity that matters most for behaviour 4. `UNIQUE_CLASS_BODY_GLOB`
    occurs nowhere else under `tests/`, so its first call in any worker process is a real
    compile of a class body whose first character is `[`.
    """
    (tmp_path / "[iter96].json").write_text("{}", encoding="utf-8")
    (tmp_path / "iter96.json").write_text("{}", encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        selected = checks.iter_files(tmp_path, [UNIQUE_CLASS_BODY_GLOB])

    assert [p.name for p in selected] == ["[iter96].json"]


# ---------------------------------------------------------------------------
# Behaviour 6 -- the control discriminates, and it is position-sensitive.
# ---------------------------------------------------------------------------

def test_b6_the_raw_splice_still_screams_under_the_same_filter_state():
    """The paired control for behaviour 4: same filter state, unescaped body, `FutureWarning`.

    `re.purge()` first, because `re.compile` memoises by pattern: a warm cache would swallow
    the warning and this control would fail OPEN, reporting the escape as unnecessary.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        re.purge()
        with pytest.raises(FutureWarning) as excinfo:
            re.compile(RAW_SPLICE)

    assert "Possible nested set" in str(excinfo.value)


def test_b6_the_control_is_position_sensitive():
    """A class body of `a[` emits NOTHING, so it cannot serve as this iteration's control.

    Recorded rather than asserted-absent-by-raising: `simplefilter("always")` defeats every
    de-duplication registry, so an empty record list means the interpreter genuinely had
    nothing to say about `[a[]`.
    """
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        re.purge()
        re.compile("[a[]")

    assert [w.category.__name__ for w in recorded] == []

    # And the same probe DOES see the first-position body, so the empty list above is a real
    # absence rather than a recorder that observes nothing.
    with warnings.catch_warnings(record=True) as recorded_first:
        warnings.simplefilter("always")
        re.purge()
        re.compile(RAW_SPLICE)

    assert [w.category for w in recorded_first] == [FutureWarning]


# ---------------------------------------------------------------------------
# Behaviour 7 -- this is a suite brake, not a runtime silencer.
# ---------------------------------------------------------------------------

def test_b7_no_warning_control_ships_inside_the_product():
    """`filterwarnings` occurs ZERO times under `src/agent_gap_radar/`.

    Mechanical: the walk counts one literal and a positive control, and never uses what the
    files say for anything else. The control is what stops "no hits" from meaning "no files
    were read" -- the failure shape that let a mitigation-by-test pass as a mitigation once
    already in this product's own register.
    """
    scanned: list[str] = []
    hits: list[str] = []
    control_hits: list[str] = []

    for path in sorted(SRC_DIR.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        scanned.append(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        if "filterwarnings" in text:
            hits.append(rel)
        if "iter_files" in text:
            control_hits.append(rel)

    assert scanned, "the src walk read nothing, so its verdict is not evidence"
    assert control_hits, (
        "positive control failed: the public name `iter_files` was not found anywhere under "
        f"src, so this reader is not seeing product source ({len(scanned)} file(s) scanned)"
    )
    assert hits == [], f"warning control shipped inside the product: {hits}"


# ---------------------------------------------------------------------------
# Behaviour 8 -- the published surface contract still holds.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["validate", str(REPO_ROOT)], id="validate"),
        pytest.param(["report", str(REPO_ROOT)], id="report"),
        pytest.param(["list", str(REPO_ROOT)], id="list"),
        pytest.param(["taxonomy"], id="taxonomy"),
    ],
)
def test_b8_surface_verbs_exit_zero_with_a_clean_stderr(argv, capsys):
    """Exit 0, stdout ending in exactly one newline, and EXACTLY zero bytes on stderr.

    Driven in-process, the way this repo's CLI tests already drive it, which is what makes it
    a real check of the filter too: a warning raised while loading the live register would now
    fail this test instead of printing a line onto the stream the contract reserves for
    `Error: `.
    """
    assert main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.endswith("\n")
    assert not captured.out.endswith("\n\n")
