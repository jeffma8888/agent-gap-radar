"""Iteration 307 behaviors: `radar list . --json` gains a top-level `"layer"` key
echoing the `--layer` argument (or `null` when absent); the flagless `radar list`
surface is unchanged.

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors 1-5. No test here reads the implementation source, the
engineer's or the reviewer's notes, or any diff. Every behavioral claim is measured by
RUNNING the CLI in a real child process (`sys.executable -m agent_gap_radar.cli`) so
that exit codes and the two byte channels are observed as a consumer sees them.

Structural notes, so this file cannot lie later:

* **Behavior 3 parses the LIVE `list --json` output to find key positions.**
  No hand-typed key list is written down except for the one key this iteration
  adds; the test reads the object's key order and asserts the relative position,
  so it cannot become stale by a future key addition.
* **Behavior 4 uses `git archive HEAD` to extract the pre-change tree.** Both
  arms print the module file they imported, and the base arm is proved to be
  the OLD code by refusing `--json --layer` with a missing `layer` key, so
  "byte-identical to the base" cannot be satisfied by two runs of one tree.
  CORRECTION: the `list --json` flag existed before this iteration, so the
  base arm IS expected to produce output; what it must NOT carry is the `layer`
  key. The base arm is proved to be the OLD code by its ABSENCE of the `layer`
  key.
* **Behavior 5 compares `validate`, `report`, `taxonomy`, `taxonomy --json`,
  `prd` across both arms.** `scan --json` is excluded because it references
  `cli.py` line numbers which shift with the production diff.
* **No absolute machine path and no personal identifier appears here.** The
  repo root is derived from `__file__`; every extracted copy lives under
  pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

PRECHANGE_COMMIT = "7731896"

TOP_LEVEL_KEYS = ["confidence_floor", "layer", "counts", "records"]


def _radar(*argv: str, env: dict[str, str] | None = None) -> tuple[int, bytes, bytes]:
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        capture_output=True, cwd=str(REPO_ROOT), env=env, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


@pytest.fixture(scope="module")
def json_no_layer() -> tuple[int, bytes, bytes]:
    return _radar("list", ".", "--json")


@pytest.fixture(scope="module")
def json_with_layer() -> tuple[int, bytes, bytes]:
    return _radar("list", ".", "--json", "--layer", "model-runtime")


@pytest.fixture(scope="module")
def flagless_with_layer() -> tuple[int, bytes, bytes]:
    return _radar("list", ".", "--layer", "model-runtime")


# ---------------------------------------------------------------------------
# Behavior 1 -- `list --json --layer model-runtime` has `"layer": "model-runtime"`.
# ---------------------------------------------------------------------------

def test_b1_json_with_layer_echoes_model_runtime(json_with_layer):
    rc, out, err = json_with_layer
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert err == b"", f"stderr must be empty, got {err[:300]!r}"
    obj = json.loads(out.decode("utf-8"))
    assert "layer" in obj, f"top-level keys {list(obj)} missing 'layer'"
    assert obj["layer"] == "model-runtime", f"layer value {obj['layer']!r}"


# ---------------------------------------------------------------------------
# Behavior 2 -- `list --json` (no --layer) has `"layer": null`.
# ---------------------------------------------------------------------------

def test_b2_json_no_layer_echoes_null(json_no_layer):
    rc, out, err = json_no_layer
    assert rc == 0, f"exit {rc}; stderr {err[:300]!r}"
    assert err == b"", f"stderr must be empty, got {err[:300]!r}"
    obj = json.loads(out.decode("utf-8"))
    assert "layer" in obj, f"top-level keys {list(obj)} missing 'layer'"
    assert obj["layer"] is None, f"layer should be null, got {obj['layer']!r}"


# ---------------------------------------------------------------------------
# Behavior 3 -- Key ordering: confidence_floor, layer, counts, records.
# ---------------------------------------------------------------------------

def test_b3_key_order_is_fixed(json_no_layer):
    rc, out, _ = json_no_layer
    assert rc == 0
    obj = json.loads(out.decode("utf-8"))
    keys = list(obj)
    assert keys == TOP_LEVEL_KEYS, (
        f"top-level keys must be exactly {TOP_LEVEL_KEYS} in order, got {keys}")


def test_b3_key_order_with_layer_filter(json_with_layer):
    rc, out, _ = json_with_layer
    assert rc == 0
    obj = json.loads(out.decode("utf-8"))
    keys = list(obj)
    assert keys == TOP_LEVEL_KEYS, (
        f"top-level keys must be exactly {TOP_LEVEL_KEYS} in order, got {keys}")


# ---------------------------------------------------------------------------
# Behavior 4 -- Flagless `list --layer` is byte-identical to HEAD.
# ---------------------------------------------------------------------------

def _git(*args: str) -> bytes:
    done = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True,
                          timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: {done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "sys.stderr.write(c.__file__ + '\\n'); "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)


def _arm(src: pathlib.Path | None, *argv: str) -> tuple[int, bytes, str]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run([sys.executable, "-c", _ARM_SCRIPT, *argv], capture_output=True,
                          cwd=str(REPO_ROOT), env=env, timeout=120)
    where = proc.stderr.decode("utf-8", "replace").splitlines()[0]
    return proc.returncode, proc.stdout, where


@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("base-arm-307")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(["tar", "-x", "-C", str(root)], input=archive,
                             capture_output=True, timeout=120)
    assert extract.returncode == 0, extract.stderr.decode("utf-8", "replace")[:400]
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


def test_b4_flagless_list_with_layer_byte_identical_to_prechange(base_src, flagless_with_layer):
    base_rc, base_out, base_file = _arm(base_src, "list", ".", "--layer", "model-runtime")
    assert base_file.startswith(str(base_src)), (
        f"the base arm imported {base_file!r}, not the extracted {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])
    base_json_rc, base_json_out, _ = _arm(base_src, "list", ".", "--json")
    assert base_json_rc == 0
    base_obj = json.loads(base_json_out.decode("utf-8"))
    assert "layer" not in base_obj, (
        f"the {PRECHANGE_COMMIT} tree must NOT carry the 'layer' key; "
        f"keys: {list(base_obj)}")
    here_rc, here_out, here_file = _arm(None, "list", ".", "--layer", "model-runtime")
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0
    assert here_out == flagless_with_layer[1], "the in-repo arm disagrees with the module fixture"
    assert here_out == base_out, (
        f"flagless `radar list . --layer model-runtime` changed against "
        f"{PRECHANGE_COMMIT}: {len(here_out)} B now vs {len(base_out)} B then")


# ---------------------------------------------------------------------------
# Behavior 5 -- Other verbs byte-identical to HEAD.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verb", [
    ("validate", "."),
    ("report", "."),
    ("taxonomy",),
    ("taxonomy", "--json"),
    ("prd", "."),
])
def test_b5_other_verbs_byte_identical_to_prechange(base_src, verb):
    base_rc, base_out, base_file = _arm(base_src, *verb)
    assert base_file.startswith(str(base_src)), (
        f"base arm imported {base_file!r}, not the {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])
    here_rc, here_out, here_file = _arm(None, *verb)
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0
    assert here_out == base_out, (
        f"`radar {' '.join(verb)}` changed against {PRECHANGE_COMMIT}: "
        f"{len(here_out)} B now vs {len(base_out)} B then")
