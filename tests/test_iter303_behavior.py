"""Iteration 303 behaviors: `tests/_surface_inventory.py` is the ONE hand-spelled
inventory of `build_parser()`'s surface; `test_iter111` imports it, `test_iter296` b1 and
`test_iter77`'s `--json` refusers DERIVE from it, the `test_iter300` text pin is gone, and
no runtime byte moved (`src/` byte-identical to the pre-change commit).

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors 1-8; nothing here reads the implementation source to derive
an expectation (the mutation probe EDITS a copy of `cli.py` by locating the `scan`
subparser registration, it never asserts on what it read), and nothing reads the
engineer's or the reviewer's notes or a diff. Sibling TEST modules are read as text and
as AST -- that is the object under test this iteration.

Structural notes, so this file cannot lie later:

* **The pre-change literals are the oracle for behavior 1**, not a second hand copy: the
  two dicts are `ast.literal_eval`ed out of `git show <PRECHANGE>:tests/test_iter111...`
  and compared `==` to the live module, so this file adds no fifth spelling of the
  inventory.
* **Every "returns nothing" census has a control** that finds the same probe in the
  PRE-CHANGE text, so an empty census proves the deletion and not a probe that never
  matched anything. The probes are assembled from fragments and described, never
  quoted, in prose: a census that reads `tests/` as text must not find its own module.
* **Node-id claims are read statically** (top-level `def test_*` names via `ast`, plus the
  parametrize sources the ids derive from) against the same reading of the pre-change
  tree extracted with `git archive`; behavior 7 is the ONE node that spawns pytest, and
  behavior 8 is the ONE node that spawns `radar` (two verbs, two arms).
* **The mutation probe mutates a COPY of the live `src/`** under `tmp_path`, so it keeps
  asking the same question of whatever tree ships next, and it proves the mutated tree
  answered by finding the injected flag in the failure output.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every extracted or mutated copy lives under pytest's tmp dirs.
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

import _surface_inventory as inventory
from _surface_contract import parser_surface
from _surface_inventory import (EXPECTED_ARGUMENTS, EXPECTED_SURFACE, long_flags,
                                verbs_without)

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
INVENTORY_NAME = "_surface_inventory.py"

#: The commit whose `tests/` still carried the four copies and whose `src/` this
#: iteration must reproduce byte for byte; `pm.md` names it.
PRECHANGE_COMMIT = "8308ab4"

#: Behavior 1 -- the eight verbs, sorted.
VERBS = ["diff", "list", "prd", "report", "scan", "show", "taxonomy", "validate"]

#: Behavior 7 -- the four nodes that must go red when `scan` grows a flag: the two
#: inventory pins, the node derived from the inventory, and the published document.
TWO_TRUTHS_RED = {
    "tests/test_iter111_behavior.py::test_behavior_8_verb_set_and_per_verb_surface_are_unchanged",
    "tests/test_iter111_behavior.py::test_behavior_8_per_argument_required_default_and_nargs_are_unchanged",
    "tests/test_iter296_behavior.py::test_iter296_b1_the_derived_inventory_is_the_pinned_inventory",
    "tests/test_surface_contract_unit.py::test_the_shipped_document_agrees_with_the_parser",
}
PROBE_FILES = ["tests/test_iter111_behavior.py", "tests/test_iter296_behavior.py",
               "tests/test_iter77_behavior.py", "tests/test_surface_contract_unit.py"]
PROBE_SELECTION = "behavior_8 or b1_the_derived or shipped_document_agrees"

#: Behavior 6 -- the one function deleted from `test_iter300`, and the survivors.
DELETED_300 = "test_b13_the_re_pinned_modules_spell_the_published_cell_and_the_eighteen_flags"
KEPT_300_TESTS = [
    "test_b13_the_two_re_pinned_modules_import_and_their_cell_pins_agree_with_the_document",
    "test_b13_the_old_scan_cell_survives_nowhere_as_text",
    "test_b13_the_old_scan_flag_row_survives_nowhere_under_tests",
    "test_b13_the_contract_spells_the_new_scan_cell_exactly_once",
]
KEPT_300_CONSTANTS = ["OLD_CELL_TAIL", "OLD_SCAN_ROW", "_GLUE"]
KEPT_300_HELPERS = ["_texts", "_new_scan_cell"]

#: Behavior 4 -- the renamed 296 node.
RENAMED_296 = "test_iter296_b1_the_derived_inventory_is_the_pinned_inventory"

#: Census probes, assembled so this module is not its own hit. Described, not quoted:
#: the opening of a hand-spelled `scan` flag row (key, colon, bracket, quote, two
#: dashes); the 296 flag-count words; the 300 count words; the two assignment openers.
SCAN_FLAG_ROW_OPENING = '"scan": [' + '"--'
COUNT_WORDS_296 = re.compile("== 1[0-9]|" + "eight" + "een|" + "seven" + "teen|" + "six" + "teen")
COUNT_WORDS_300 = re.compile("== 18|" + "eight" + "een")
ASSIGNMENT_OPENERS = re.compile(r"^EXPECTED_SURFACE = |^EXPECTED_ARGUMENTS = ", re.M)
#: A strict prefix of two live flags, assembled so the 296 b8 prefix census, which walks
#: every module under `tests/`, does not read this module as keeping an abbreviation alive.
GA_PREFIX = "--" + "ga"


# ---------------------------------------------------------------------------
# Helpers: git, AST readings, and the pre-change tree.
# ---------------------------------------------------------------------------

def _git(*args: str) -> bytes:
    done = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True,
                          timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: {done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


def _extract(tree: str, path: str, tmp_root: pathlib.Path) -> pathlib.Path:
    """`git archive <tree> <path>` extracted under `tmp_root`; returns `<tmp_root>/<path>`."""
    archive = _git("archive", tree, path)
    done = subprocess.run(["tar", "-x", "-C", str(tmp_root)], input=archive,
                          capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[:400]
    out = tmp_root / path
    assert out.is_dir(), sorted(p.name for p in tmp_root.iterdir())
    return out


@pytest.fixture(scope="module")
def head_tests(tmp_path_factory) -> pathlib.Path:
    """`tests/` as it stood at PRECHANGE_COMMIT."""
    return _extract(PRECHANGE_COMMIT, "tests", tmp_path_factory.mktemp("head-tests"))


@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    """`src/` as it stood at PRECHANGE_COMMIT."""
    return _extract(PRECHANGE_COMMIT, "src", tmp_path_factory.mktemp("base-arm"))


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _test_names(text: str) -> set[str]:
    """Top-level `def test_*` names -- the static reading of a module's node ids."""
    return {node.name for node in ast.parse(text).body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def _assigned_names(text: str) -> set[str]:
    names: set[str] = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _literal_assignments(text: str, wanted: set[str]) -> dict[str, object]:
    """`ast.literal_eval` of every top-level `NAME = <literal>` whose NAME is wanted."""
    found: dict[str, object] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    found[target.id] = ast.literal_eval(node.value)
    return found


def _imports_from(text: str, module: str) -> set[str]:
    return {alias.name for node in ast.parse(text).body
            if isinstance(node, ast.ImportFrom) and node.module == module
            for alias in node.names}


def _imported_modules(text: str) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            mods.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def _function(text: str, name: str) -> ast.FunctionDef:
    matches = [node for node in ast.parse(text).body
               if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(matches) == 1, f"expected exactly one `def {name}`, found {len(matches)}"
    return matches[0]


def _parametrize_source(fn: ast.FunctionDef, argname: str) -> ast.expr:
    """The second argument of the `pytest.mark.parametrize(<argname>, ...)` decorator."""
    for deco in fn.decorator_list:
        if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                and deco.func.attr == "parametrize" and deco.args
                and isinstance(deco.args[0], ast.Constant) and deco.args[0].value == argname):
            return deco.args[1]
    raise AssertionError(f"`{fn.name}` has no parametrize over {argname!r}")


def _test_files(root: pathlib.Path) -> dict[str, set[str]]:
    return {p.name: _test_names(_read(p)) for p in sorted(root.glob("test_*.py"))}


# ---------------------------------------------------------------------------
# Behavior 1 -- the module exists, pins eight verbs, equals the pre-change literals.
# ---------------------------------------------------------------------------

def test_b1_the_inventory_pins_the_eight_verbs_and_equals_the_prechange_literals(head_tests):
    assert sorted(EXPECTED_SURFACE) == VERBS, sorted(EXPECTED_SURFACE)
    assert sorted(EXPECTED_ARGUMENTS) == VERBS, sorted(EXPECTED_ARGUMENTS)
    before = _literal_assignments(_read(head_tests / "test_iter111_behavior.py"),
                                  {"EXPECTED_SURFACE", "EXPECTED_ARGUMENTS"})
    assert set(before) == {"EXPECTED_SURFACE", "EXPECTED_ARGUMENTS"}, sorted(before)
    assert EXPECTED_SURFACE == before["EXPECTED_SURFACE"], (
        "EXPECTED_SURFACE moved with a change; it must be the pre-change literal verbatim")
    assert EXPECTED_ARGUMENTS == before["EXPECTED_ARGUMENTS"], (
        "EXPECTED_ARGUMENTS moved with a change; it must be the pre-change literal verbatim")
    # No third `EXPECTED_*` name, and the module is the expectation side: nothing from
    # the product is imported, so it cannot agree with the parser by construction.
    expected_names = sorted(n for n in vars(inventory) if n.startswith("EXPECTED_"))
    assert expected_names == ["EXPECTED_ARGUMENTS", "EXPECTED_SURFACE"], expected_names
    module_text = _read(TESTS / INVENTORY_NAME)
    product = sorted(m for m in _imported_modules(module_text)
                     if m == "agent_gap_radar" or m.startswith("agent_gap_radar."))
    assert product == [], f"the inventory imports the product: {product}"
    assert inventory.__doc__ and "303" in inventory.__doc__, "docstring must name iteration 303"
    assert callable(inventory.long_flags) and callable(inventory.verbs_without)
    # The inventory's PUBLIC surface is exactly the four names the spec's module shape
    # lists (`from __future__ import annotations` leaves `annotations` behind and is not
    # a name the module publishes); anything else is a fifth spelling or a new public name.
    public = sorted(n for n in vars(inventory) if not n.startswith("_") and n != "annotations")
    assert public == ["EXPECTED_ARGUMENTS", "EXPECTED_SURFACE", "long_flags", "verbs_without"], public
    assert not _test_names(_read(TESTS / INVENTORY_NAME)), "the inventory is data, not a test module"


# ---------------------------------------------------------------------------
# Behavior 2 -- `long_flags` / `verbs_without` read off the inventory; agree with parser.
# ---------------------------------------------------------------------------

def test_b2_long_flags_and_verbs_without_are_read_off_the_inventory():
    assert long_flags("scan") == ["--baseline", "--exit-code", "--floor", "--gap", "--gaps",
                                  "--json", "--prd"], long_flags("scan")
    assert long_flags("taxonomy") == ["--json"], long_flags("taxonomy")
    assert long_flags("show") == [], long_flags("show")
    with pytest.raises(KeyError):
        long_flags("nope")
    for verb in VERBS:
        flags = long_flags(verb)
        assert flags == sorted(flags) and all(f.startswith("--") for f in flags), (verb, flags)
        assert set(flags) == {o for o in EXPECTED_SURFACE[verb][0] if o.startswith("--")}, verb
    assert verbs_without("--json") == ["prd", "report", "show", "validate"], (
        verbs_without("--json"))
    assert verbs_without("--floor") == ["diff", "show", "taxonomy", "validate"], (
        verbs_without("--floor"))
    assert verbs_without("--nope") == VERBS, verbs_without("--nope")
    assert verbs_without("--help") == VERBS, "`-h/--help` is not an inventory flag"


def test_b2_the_derivations_agree_with_the_live_parser():
    live = parser_surface()
    assert sorted(live) == VERBS, sorted(live)
    measured = {v: sorted(o for o in s.options if o.startswith("--")) for v, s in live.items()}
    assert {v: long_flags(v) for v in EXPECTED_SURFACE} == measured, measured
    for flag in ("--json", "--floor", "--exit-code"):
        assert verbs_without(flag) == sorted(v for v, s in live.items() if flag not in s.options), flag


# ---------------------------------------------------------------------------
# Behavior 3 -- `test_iter111` imports the inventory; the two literals live in ONE file.
# ---------------------------------------------------------------------------

def test_b3_test_iter111_imports_the_inventory_and_keeps_its_node_ids(head_tests):
    hits = sorted((p.name, m.group(0)) for p in TESTS.glob("*.py")
                  for m in ASSIGNMENT_OPENERS.finditer(_read(p)))
    assert hits == [(INVENTORY_NAME, "EXPECTED_ARGUMENTS = "),
                    (INVENTORY_NAME, "EXPECTED_SURFACE = ")], hits
    before = _read(head_tests / "test_iter111_behavior.py")
    assert len(ASSIGNMENT_OPENERS.findall(before)) == 2, "control: the census never saw the origin"
    now = _read(TESTS / "test_iter111_behavior.py")
    assert not ({"EXPECTED_SURFACE", "EXPECTED_ARGUMENTS"} & _assigned_names(now))
    assert {"EXPECTED_ARGUMENTS", "EXPECTED_SURFACE"} <= _imports_from(now, "_surface_inventory")
    assert _test_names(now) == _test_names(before), (
        sorted(_test_names(now) ^ _test_names(before)))
    import test_iter111_behavior as t111
    assert callable(getattr(t111, "test_behavior_8_verb_set_and_per_verb_surface_are_unchanged"))
    assert callable(getattr(
        t111, "test_behavior_8_per_argument_required_default_and_nargs_are_unchanged"))
    ids = [case[0] for case in t111.HELP_CASES]
    assert [i for i in ids if i.endswith("-help") and i != "root-help"] == [
        f"{verb}-help" for verb in VERBS], ids
    assert t111.EXPECTED_SURFACE is EXPECTED_SURFACE and t111.EXPECTED_ARGUMENTS is EXPECTED_ARGUMENTS


# ---------------------------------------------------------------------------
# Behavior 4 -- `test_iter296` b1 derives from the inventory and pins no flag count.
# ---------------------------------------------------------------------------

def test_b4_test_iter296_b1_derives_from_the_inventory_and_pins_no_count(head_tests):
    now = _read(TESTS / "test_iter296_behavior.py")
    before = _read(head_tests / "test_iter296_behavior.py")
    old = {n for n in _test_names(before) if n.startswith("test_iter296_b1_the_derived")}
    assert len(old) == 1 and RENAMED_296 not in old, sorted(old)
    assert _test_names(now) == (_test_names(before) - old) | {RENAMED_296}, (
        sorted(_test_names(now) ^ _test_names(before)))
    assert not [n for n in _test_names(now) if n.endswith("_flags")], "the old id survives"
    assert COUNT_WORDS_296.findall(now) == [], COUNT_WORDS_296.findall(now)
    assert COUNT_WORDS_296.findall(before), "control: the pre-change module pinned a count"
    assert {"EXPECTED_SURFACE", "long_flags"} <= _imports_from(now, "_surface_inventory")
    body = ast.get_source_segment(now, _function(now, RENAMED_296))
    assert body and "long_flags(verb) for verb in EXPECTED_SURFACE" in body, body
    assert "assert len(PREFIX_CASES) >= 60" in now
    assert 'assert ("scan", "--gap") not in' in now
    assert f'assert ("scan", "{GA_PREFIX}") in' in now
    # The hand-spelled `scan` flag row is gone from every test, and the probe is real.
    row_hits = sorted(p.name for p in TESTS.glob("*.py") if SCAN_FLAG_ROW_OPENING in _read(p))
    assert row_hits == [], row_hits
    assert SCAN_FLAG_ROW_OPENING in before, "control: the pre-change 296 spelled the row"


# ---------------------------------------------------------------------------
# Behavior 5 -- `test_iter77` parametrizes the `--json` refusers from the inventory.
# ---------------------------------------------------------------------------

def test_b5_test_iter77_parametrizes_the_json_refusers_from_the_inventory(head_tests):
    now = _read(TESTS / "test_iter77_behavior.py")
    before = _read(head_tests / "test_iter77_behavior.py")
    assert _test_names(now) == _test_names(before), sorted(_test_names(now) ^ _test_names(before))
    assert "verbs_without" in _imports_from(now, "_surface_inventory")
    fn = _function(now, "test_no_other_verb_gained_a_json_flag")
    source = _parametrize_source(fn, "verb")
    assert (isinstance(source, ast.Call) and isinstance(source.func, ast.Name)
            and source.func.id == "verbs_without"
            and [a.value for a in source.args if isinstance(a, ast.Constant)] == ["--json"]), (
        ast.dump(source))
    head_list = ast.literal_eval(
        _parametrize_source(_function(before, "test_no_other_verb_gained_a_json_flag"), "verb"))
    assert set(head_list) == set(verbs_without("--json")) == {"prd", "report", "show", "validate"}
    assert verbs_without("--json") == ["prd", "report", "show", "validate"], "ids, in order"
    published = "test_the_verbs_that_already_published_json_still_do"
    assert (ast.literal_eval(_parametrize_source(_function(now, published), "verb"))
            == ast.literal_eval(_parametrize_source(_function(before, published), "verb"))
            == ["list", "diff", "taxonomy"])
    # The pre-change sentence, whitespace-normalized (it wrapped across two lines and
    # backticked the verb): `taxonomy` left this list in iteration 302 ...
    left_in_302 = "left this list in iteration 302"
    doc = " ".join((ast.get_docstring(fn) or "").split())
    assert left_in_302 not in doc, doc
    assert "derived" in doc.lower() and "_surface_inventory" in doc, doc
    before_doc = " ".join(
        (ast.get_docstring(_function(before, "test_no_other_verb_gained_a_json_flag")) or "").split())
    assert f"`taxonomy` {left_in_302}" in before_doc, (
        "control: the pre-change docstring carried the sentence", before_doc)


# ---------------------------------------------------------------------------
# Behavior 6 -- the `test_iter300` text pin is deleted; the whole suite moved by 3 edits.
# ---------------------------------------------------------------------------

def test_b6_test_iter300_deletes_the_text_pin_and_keeps_the_four_tests_and_helpers(head_tests):
    now = _read(TESTS / "test_iter300_behavior.py")
    before = _read(head_tests / "test_iter300_behavior.py")
    assert DELETED_300 in _test_names(before), "control: the deleted node existed"
    assert DELETED_300 not in _test_names(now)
    assert _test_names(now) == _test_names(before) - {DELETED_300}, (
        sorted(_test_names(now) ^ _test_names(before)))
    assert set(KEPT_300_TESTS) <= _test_names(now)
    assert set(KEPT_300_CONSTANTS) <= _assigned_names(now), sorted(_assigned_names(now))
    helpers = {n.name for n in ast.parse(now).body if isinstance(n, ast.FunctionDef)}
    assert set(KEPT_300_HELPERS) <= helpers, sorted(helpers)
    assert COUNT_WORDS_300.findall(now) == [], COUNT_WORDS_300.findall(now)
    assert COUNT_WORDS_300.findall(before), "control: the pre-change module pinned the count"


def test_b6_the_whole_suite_node_set_moved_by_exactly_the_three_named_edits(head_tests):
    before, now = _test_files(head_tests), _test_files(TESTS)
    me = pathlib.Path(__file__).name
    assert set(now) == set(before) | {me}, sorted(set(now) ^ set(before))
    assert now[me], "this module collects nothing"
    changed = {name: (sorted(before[name] - now[name]), sorted(now[name] - before[name]))
               for name in before if before[name] != now[name]}
    assert changed == {
        "test_iter296_behavior.py": (
            sorted(n for n in before["test_iter296_behavior.py"]
                   if n.startswith("test_iter296_b1_the_derived")), [RENAMED_296]),
        "test_iter300_behavior.py": ([DELETED_300], []),
    }, changed


# ---------------------------------------------------------------------------
# Behavior 7 -- a flag added to `scan` reds exactly the two truths, nothing hand-spelled.
# ---------------------------------------------------------------------------

def _mutate_scan_subparser(cli_py: pathlib.Path) -> None:
    """Add `--x` (store_true) to the `scan` subparser, located by its registration
    literal (`<name> = <sub>.add_parser("scan"`), never by a line number."""
    text = _read(cli_py)
    registrations = list(re.finditer(r'(\w+)\s*=\s*\w+\.add_parser\(\s*"scan"', text))
    assert len(registrations) == 1, f"expected one `scan` registration, found {len(registrations)}"
    (registration,) = registrations
    owner = registration.group(1)
    tail = text[registration.end():]
    first_argument = re.search(r"^(\s*)" + re.escape(owner) + r"\.add_argument\(", tail, re.M)
    assert first_argument, f"`{owner}` never calls add_argument after its registration"
    at = registration.end() + first_argument.start()
    injected = f'{first_argument.group(1)}{owner}.add_argument("--x", action="store_true")\n'
    cli_py.write_text(text[:at] + injected + text[at:], encoding="utf-8")


def test_b7_a_flag_added_to_the_scan_subparser_reds_exactly_the_two_truths(tmp_path):
    mutated_src = tmp_path / "src"
    shutil.copytree(REPO_ROOT / "src", mutated_src,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    cli_py = mutated_src / "agent_gap_radar" / "cli.py"
    assert cli_py.is_file(), cli_py
    _mutate_scan_subparser(cli_py)
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = str(mutated_src)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *PROBE_FILES, "-p", "no:xdist", "-o", "addopts=",
         "-k", PROBE_SELECTION, "-rA"],
        capture_output=True, cwd=str(REPO_ROOT), env=env, timeout=300)
    out = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 1, f"expected exit 1 (tests failed), got {proc.returncode}:\n{out[-1500:]}"
    failed = {ln.split()[1] for ln in out.splitlines() if ln.startswith("FAILED ")}
    passed = {ln.split()[1] for ln in out.splitlines() if ln.startswith("PASSED ")}
    assert failed == TWO_TRUTHS_RED, (sorted(failed ^ TWO_TRUTHS_RED), out[-1500:])
    assert passed and not (passed & failed), (sorted(passed), sorted(failed))
    assert len(passed | failed) >= 5, "the selection collected fewer nodes than it did at 303"
    assert "'--x'" in out, "the failure output never names the injected flag; which tree answered?"
    assert (mutated_src / "agent_gap_radar" / "cli.py").read_text(encoding="utf-8").count('"--x"') == 1


# ---------------------------------------------------------------------------
# Behavior 8 -- no runtime byte moved: two `--json` verbs byte-identical to the base src.
# ---------------------------------------------------------------------------

_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "sys.stderr.write(c.__file__ + '\\n'); "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)


def _arm(src: pathlib.Path | None, *argv: str) -> tuple[int, bytes, str]:
    """Run `radar <argv>` importing `agent_gap_radar` from `src` (or the installed tree);
    returns (rc, stdout bytes, the imported module file) so the answering tree is PROVED."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run([sys.executable, "-c", _ARM_SCRIPT, *argv], capture_output=True,
                          cwd=str(REPO_ROOT), env=env, timeout=120)
    where = proc.stderr.decode("utf-8", "replace").splitlines()[0]
    return proc.returncode, proc.stdout, where


def test_b8_taxonomy_json_and_list_json_are_byte_identical_to_the_prechange_src(base_src):
    for argv in (["taxonomy", "--json"], ["list", ".", "--json"]):
        base_rc, base_out, base_file = _arm(base_src, *argv)
        assert base_file.startswith(str(base_src)), (argv, base_file)
        here_rc, here_out, here_file = _arm(None, *argv)
        assert not here_file.startswith(str(base_src)), (argv, here_file)
        assert base_rc == 0 == here_rc, (argv, base_rc, here_rc)
        assert here_out and here_out[-1:] == b"\n" and here_out[-2:-1] != b"\n", argv
        assert here_out == base_out, (
            f"`radar {' '.join(argv)}` changed against {PRECHANGE_COMMIT}: "
            f"{len(here_out)} B now vs {len(base_out)} B then")
