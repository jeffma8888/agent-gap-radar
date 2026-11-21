"""Iteration 423 behaviors: one closed-vocabulary refusal rule in the record model.

THE ISOLATION CONTRACT IS HONORED.  Every expectation comes from ``pm.md``'s
Expected Behaviors 1-7.  No test reads the implementation's logic by eye, the
engineer's or reviewer's notes, or any diff; behavior 6 is the spec's own
STRUCTURAL clause, so it is checked by an AST walk run at test time.

Oracles:
- "same as before the refactor": the pre-refactor tree (``git archive`` of the
  parent commit when it is present, else ``HEAD``) is unpacked into a tmp dir
  and the SAME child script runs against it via PYTHONPATH; the test skips
  cleanly when ``git``/``.git`` is unavailable.
- independent: every refusal sentence is re-derived from ``radar taxonomy
  --json`` (vocabulary + order), not from the record model.

All broken records are tmp copies of a real ``gaps/`` record mutated in one
field.  Ship-hazard notes: no ``file:line`` locator, no wall-clock bound, no
optional extra.  The pre-refactor sha is an immutable ancestor (it never moves
with the ship commit) and falls back to ``HEAD`` in a shallow clone.
"""

from __future__ import annotations

import ast
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout

import pytest

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
PKG = REPO / "src" / "agent_gap_radar"
MODELS = PKG / "models.py"
PRE_REFACTOR = "f6ec0ab"  # parent of the iter-423 change; immutable ancestor

CHILD = r"""
import io, json, sys
from contextlib import redirect_stdout, redirect_stderr
import agent_gap_radar
from agent_gap_radar.cli import main
jobs = json.loads(sys.stdin.read())
out = {"__file__": agent_gap_radar.__file__}
for key, argv in jobs:
    o, e = io.StringIO(), io.StringIO()
    with redirect_stdout(o), redirect_stderr(e):
        try:
            rc = main(argv) or 0
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    out[key] = [rc, o.getvalue(), e.getvalue()]
print(json.dumps(out))
"""


def _run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            rc = main(list(argv)) or 0
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
    return rc, out.getvalue(), err.getvalue()


def _taxonomy() -> dict:
    rc, out, _ = _run("taxonomy", "--json")
    assert rc == 0
    return json.loads(out)


TAX = _taxonomy()
ALLOWED = {
    "layer": tuple(TAX["layers"]),
    "gap_type": tuple(TAX["gap_types"]),
    "status": tuple(TAX["statuses"]),
    "source_class": tuple(c["name"] for c in TAX["source_classes"]),
}


def _sentence(field: str, value: str) -> str:
    return f"unknown {field} {value!r}; allowed: {ALLOWED[field]!r}"


#: case name -> {field: bad value}; ``source_class`` mutates evidence[0].
CASES = {
    "layer": {"layer": "not-a-layer"},
    "gap_type": {"gap_type": "not-a-type"},
    "status": {"status": "not-a-status"},
    "source_class": {"source_class": "not-a-class"},
    "layer_status": {"layer": "bogus-layer", "status": "bogus-status"},
    "all_three": {"layer": "x-l", "gap_type": "x-t", "status": "x-s"},
}


def _source_record(multi: bool) -> pathlib.Path:
    for p in sorted(GAPS.glob("GAP-*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if (len(rec["evidence"]) > 1) == multi:
            return p
    raise AssertionError("no suitable source record")


@pytest.fixture(scope="module")
def cases_root(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("iter423_cases")
    src = _source_record(multi=True)
    base = json.loads(src.read_text(encoding="utf-8"))
    for name, muts in CASES.items():
        rec = json.loads(json.dumps(base))
        for field, value in muts.items():
            if field == "source_class":
                rec["evidence"][0]["source_class"] = value
            else:
                assert rec[field] in ALLOWED[field]  # premise: base was valid
                rec[field] = value
        d = root / name
        d.mkdir()
        (d / src.name).write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    return root


def _jobs(root: pathlib.Path) -> list:
    jobs = []
    for name in CASES:
        d = str(root / name)
        jobs.append([f"{name}/md", ["validate", d]])
        jobs.append([f"{name}/json", ["validate", "--json", d]])
    jobs.append(["register/list", ["list", "--json", str(GAPS)]])
    jobs.append(["register/validate", ["validate", str(GAPS)]])
    return jobs


def _child(src_dir: pathlib.Path, jobs: list) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_dir)
    env["PYTHONHASHSEED"] = "0"
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        input=json.dumps(jobs), capture_output=True, text=True,
        cwd=str(src_dir.parent), env=env, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    # premise: the child really imported the tree we pointed it at
    assert pathlib.Path(doc["__file__"]).resolve().is_relative_to(src_dir.resolve())
    return doc


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, timeout=60)


@pytest.fixture(scope="module")
def results(cases_root, tmp_path_factory) -> dict:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("git or .git unavailable: no pre-refactor oracle")
    rev = PRE_REFACTOR
    if _git("cat-file", "-e", f"{rev}^{{commit}}").returncode != 0:
        rev = "HEAD"
        if _git("rev-parse", "--verify", "HEAD").returncode != 0:
            pytest.skip("no HEAD commit available")
    old = tmp_path_factory.mktemp("iter423_old")
    arch = _git("archive", "--format=tar", rev, "src")
    if arch.returncode != 0:
        pytest.skip(f"git archive {rev} failed")
    subprocess.run(["tar", "-x", "-C", str(old)], input=arch.stdout, check=True, timeout=60)
    jobs = _jobs(cases_root)
    return {"old": _child(old / "src", jobs), "new": _child(REPO / "src", jobs)}


def _keys(case: str) -> list[str]:
    return [f"{case}/md", f"{case}/json"]


# --- behaviors 1-3: one bad closed field, byte-identical to the oracle ------

@pytest.mark.parametrize("case", ["layer", "gap_type", "status", "source_class"])
def test_b1_b3_single_bad_field_bytes_match_pre_refactor(results, case):
    for key in _keys(case):
        assert results["new"][key] == results["old"][key], key
        assert results["new"][key][0] == 2


@pytest.mark.parametrize("case", ["layer", "gap_type", "status", "source_class"])
def test_b1_b3_refusal_sentence_derived_from_taxonomy(results, case):
    (field, value), = CASES[case].items()
    want = _sentence(field, value)
    rc, out, err = results["new"][f"{case}/md"]
    assert rc == 2 and out == ""
    assert err.startswith("Error: ") and err.endswith("\n")
    assert want in err
    assert err.count("unknown ") == 1
    rc, out, err = results["new"][f"{case}/json"]
    doc = json.loads(out)
    assert rc == 2 and doc["valid"] is False and out.endswith("}\n")
    msgs = [e["msg"] for e in doc["errors"]]
    assert len(msgs) == 1 and want in msgs[0]


def test_b1_layer_allowed_lists_every_layer_in_taxonomy_order(results):
    _, _, err = results["new"]["layer/md"]
    listed = err.split("allowed: ", 1)[1].rstrip("\n")
    assert ast.literal_eval(listed) == ALLOWED["layer"]
    assert len(ALLOWED["layer"]) >= 10  # premise: a real vocabulary


# --- behavior 4: two (and three) bad fields --------------------------------

@pytest.mark.parametrize("case", ["layer_status", "all_three"])
def test_b4_multiple_bad_fields_bytes_match_pre_refactor(results, case):
    for key in _keys(case):
        assert results["new"][key] == results["old"][key], key
        assert results["new"][key][0] == 2


@pytest.mark.parametrize("case", ["layer_status", "all_three"])
def test_b4_every_bad_field_reported_in_field_order(results, case):
    muts = CASES[case]
    rc, out, _ = results["new"][f"{case}/json"]
    errors = json.loads(out)["errors"]
    assert [e["loc"] for e in errors] == list(muts)
    for e, (field, value) in zip(errors, muts.items()):
        assert _sentence(field, value) in e["msg"]
    _, _, err = results["new"][f"{case}/md"]
    assert f"{len(muts)} schema error(s)" in err
    pos = [err.index(_sentence(f, v)) for f, v in muts.items()]
    assert pos == sorted(pos)


# --- behavior 5: the shipped register is unchanged -------------------------

@pytest.mark.parametrize("key", ["register/list", "register/validate"])
def test_b5_valid_register_unchanged(results, key):
    assert results["new"][key] == results["old"][key]
    rc, out, err = results["new"][key]
    assert rc == 0 and err == "" and out.endswith("\n") and not out.endswith("\n\n")


def test_b5_list_json_covers_every_record(results):
    _, out, _ = results["new"]["register/list"]
    doc = json.loads(out)
    n = len(list(GAPS.glob("GAP-*.json")))
    assert n >= 100 and len(doc["records"]) == n == doc["counts"]["total"]


# --- behavior 6: one refusal site; the per-field validators are gone --------

def _refusal_sites(tree: ast.AST, *, strict: bool) -> int:
    """Count ``raise ValueError(f"unknown ...")`` nodes.

    strict=True: the f-string's first part is EXACTLY the literal ``"unknown "``
    followed by an interpolated field name (the generic rule).  strict=False is
    the spec's literal wording (first literal part starts with ``"unknown "``).
    """
    n = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)):
            continue
        call = node.exc
        if not (isinstance(call.func, ast.Name) and call.func.id == "ValueError"):
            continue
        if not call.args or not isinstance(call.args[0], ast.JoinedStr):
            continue
        parts = call.args[0].values
        if not parts or not isinstance(parts[0], ast.Constant):
            continue
        first = parts[0].value
        if strict:
            if first == "unknown " and len(parts) > 1 and isinstance(parts[1], ast.FormattedValue):
                n += 1
        elif isinstance(first, str) and first.startswith("unknown "):
            n += 1
    return n


def test_b6_exactly_one_generic_unknown_field_refusal_site():
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    assert _refusal_sites(tree, strict=True) == 1
    # every refusal sentence the model emits about a closed field comes from it:
    # no f-string spells a field name literally after "unknown ".
    for field in ("layer", "gap_type", "status", "source_class"):
        lit = f"unknown {field} "
        assert lit not in MODELS.read_text(encoding="utf-8"), lit


@pytest.mark.parametrize("name", ["_known_layer", "_known_type", "_known_status"])
def test_b6_per_field_validators_gone_from_gap(name):
    assert not hasattr(Gap, name)
    assert name not in Gap.__pydantic_decorators__.field_validators
    assert name not in vars(Gap)


# --- behavior 7: module count and models.py imports -------------------------

def test_b7_still_ten_src_modules():
    mods = sorted(p.name for p in PKG.glob("*.py") if p.name != "__init__.py")
    assert len(mods) == 10, mods


def test_b7_models_imports_only_pydantic_stdlib_package():
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue  # relative: inside the package
            roots.add((node.module or "").split(".")[0])
    assert roots  # premise: the module imports something
    bad = {r for r in roots
           if r not in sys.stdlib_module_names and r not in {"pydantic", "agent_gap_radar"}}
    assert not bad, bad
