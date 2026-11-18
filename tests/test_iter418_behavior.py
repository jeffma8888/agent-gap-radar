"""Iteration 418 behaviors: record validation primes the scan's compile memo.

When a record is validated, each `content_matches`/`content_absent` pattern is
compiled straight into the scan's compile memo under `re.MULTILINE`, so a scan
never compiles a validated check pattern a second time under a different flag
set. The refusal surface (invalid regex, blank pattern) does not move.

Every census and every memo inspection runs in a FRESH child interpreter: the
memo is process-wide, so a warm xdist worker would answer for a cold one.
Targets and registers are tmp dirs. No commit sha, no line number, no
wall-clock ratio, no network, no absolute machine path. The before/after
comparison against the pre-change head (compile count, byte identity) is
proved by hand in the tester report, deliberately NOT as a sha-pinned test.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS = REPO / "gaps"
SRC = REPO / "src"
TIMEOUT = 60

_CLI = "import sys\nfrom agent_gap_radar.cli import main\nraise SystemExit(main(sys.argv[1:]))\n"


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), env.get("PYTHONPATH", "")])
    return env


def _child(code: str, *args: str, cwd: pathlib.Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True, cwd=cwd, env=_env(), timeout=TIMEOUT, text=True,
    )


def _radar(args: list[str], cwd: pathlib.Path = REPO):
    p = _child(_CLI, *args, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def _walk_patterns(node, out: set[str]) -> None:
    if isinstance(node, dict):
        if node.get("kind") in ("content_matches", "content_absent") and isinstance(
            node.get("pattern"), str
        ):
            out.add(node["pattern"])
        for value in node.values():
            _walk_patterns(value, out)
    elif isinstance(node, list):
        for value in node:
            _walk_patterns(value, out)


def _register_patterns() -> set[str]:
    """Every regex pattern reachable in the committed register's check rules."""
    out: set[str] = set()
    for path in sorted(GAPS.glob("GAP-*.json")):
        _walk_patterns(json.loads(path.read_text(encoding="utf-8")).get("check"), out)
    return out


@pytest.fixture
def tiny(tmp_path: pathlib.Path) -> pathlib.Path:
    """A 2-file target repo."""
    target = tmp_path / "tiny"
    target.mkdir()
    (target / "app.py").write_text(
        "import time\n\n\ndef run():\n    while True:\n        time.sleep(1)\n",
        encoding="utf-8",
    )
    (target / "README.md").write_text("# tiny\n\nA small target.\n", encoding="utf-8")
    return target


# ---- b1: compile census of a scan in a fresh child ---------------------------

_CENSUS = r"""
import contextlib, io, json, re, sys
from re import _compiler
calls = []
real = _compiler.compile
def wrapped(p, flags=0):
    calls.append((p if isinstance(p, str) else repr(p), int(flags)))
    return real(p, flags)
_compiler.compile = wrapped
from agent_gap_radar.cli import main
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = main(["scan", sys.argv[1], "--json"])
sys.stdout.write(json.dumps({"rc": rc, "calls": calls}))
"""


def test_b1_scan_census_no_pattern_compiled_under_two_flag_sets(tiny):
    p = _child(_CENSUS, str(tiny))
    assert p.returncode == 0, p.stderr
    doc = json.loads(p.stdout)
    assert doc["rc"] in (0, 1), doc["rc"]
    calls = [tuple(c) for c in doc["calls"]]
    flagsets: dict[str, set[int]] = {}
    for pat, flags in calls:
        flagsets.setdefault(pat, set()).add(flags)
    reg = _register_patterns()
    # premise: the census saw the register's patterns at all (not vacuous)
    seen = reg & set(flagsets)
    assert len(seen) >= 100, len(seen)
    dual = sorted(p for p, f in flagsets.items() if len(f) > 1)
    assert dual == [], f"{len(dual)} patterns compiled under >1 flag set, e.g. {dual[:3]}"
    # every register pattern that reached the compiler did so under MULTILINE only
    bad = sorted(p for p in seen if flagsets[p] != {int(re.MULTILINE)})
    assert bad == [], bad[:3]


def test_b1_register_pattern_compiled_at_most_once_per_scan(tiny):
    p = _child(_CENSUS, str(tiny))
    assert p.returncode == 0, p.stderr
    calls = [tuple(c) for c in json.loads(p.stdout)["calls"]]
    reg = _register_patterns()
    counts: dict[str, int] = {}
    for pat, _flags in calls:
        if pat in reg:
            counts[pat] = counts.get(pat, 0) + 1
    assert len(counts) >= 100, len(counts)
    twice = sorted(p for p, n in counts.items() if n > 1)
    assert twice == [], twice[:3]


# ---- b2 + b3 + b4: the memo after load_all, in a fresh child -----------------

_MEMO = r"""
import json, pathlib, re, sys
from agent_gap_radar import checks, registry
pats = json.loads(sys.stdin.read())
before = [p for p in pats if (p, re.MULTILINE) in checks._COMPILE_CACHE]
seam_calls = []
real_seam = checks._cached_compile
def counting(pattern, flags=0):
    seam_calls.append(pattern)
    return real_seam(pattern, flags)
checks._cached_compile = counting
gaps = registry.load_all(pathlib.Path("gaps"))
checks._cached_compile = real_seam
missing, notpat, noml = [], [], []
stored = {}
for p in pats:
    v = checks._COMPILE_CACHE.get((p, re.MULTILINE))
    if v is None:
        missing.append(p); continue
    if not isinstance(v, re.Pattern):
        notpat.append(p); continue
    if not (v.flags & re.MULTILINE):
        noml.append(p)
    stored[p] = v
same = [p for p, v in stored.items() if checks._cached_compile(p, re.MULTILINE) is v]
sys.stdout.write(json.dumps({
    "records": len(gaps), "before": before, "seam_calls": len(seam_calls),
    "missing": missing, "notpat": notpat, "noml": noml,
    "stored": len(stored), "same": len(same),
}))
"""


@pytest.fixture(scope="module")
def memo_doc() -> dict:
    pats = sorted(_register_patterns())
    p = subprocess.run(
        [sys.executable, "-c", _MEMO], input=json.dumps(pats), capture_output=True,
        cwd=REPO, env=_env(), timeout=TIMEOUT, text=True,
    )
    assert p.returncode == 0, p.stderr
    doc = json.loads(p.stdout)
    doc["n"] = len(pats)
    return doc


def test_b2_premise_memo_cold_before_load_and_register_nonempty(memo_doc):
    assert memo_doc["records"] >= 1
    assert memo_doc["n"] >= 100
    assert memo_doc["before"] == []


def test_b2_load_all_primes_every_reachable_pattern_under_multiline(memo_doc):
    assert memo_doc["missing"] == []
    assert memo_doc["notpat"] == []
    assert memo_doc["noml"] == []
    assert memo_doc["stored"] == memo_doc["n"]


def test_b2_nested_rule_patterns_are_primed():
    """Patterns only reachable under all_of/any_of/not are in the walked set and primed."""
    nested: set[str] = set()
    for path in sorted(GAPS.glob("GAP-*.json")):
        check = json.loads(path.read_text(encoding="utf-8")).get("check") or {}
        for value in check.values():
            if isinstance(value, dict) and value.get("kind") in ("all_of", "any_of", "not"):
                _walk_patterns(value, nested)
    assert nested, "premise: the register has nested content rules"
    code = (
        "import json, pathlib, re, sys\n"
        "from agent_gap_radar import checks, registry\n"
        "registry.load_all(pathlib.Path('gaps'))\n"
        "pats = json.loads(sys.stdin.read())\n"
        "print(json.dumps([p for p in pats if (p, re.MULTILINE) not in checks._COMPILE_CACHE]))\n"
    )
    p = subprocess.run(
        [sys.executable, "-c", code], input=json.dumps(sorted(nested)), capture_output=True,
        cwd=REPO, env=_env(), timeout=TIMEOUT, text=True,
    )
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == []


def test_b3_load_all_makes_zero_seam_calls(memo_doc):
    # the zero is not vacuous: b2 shows the memo was primed by the same load
    assert memo_doc["stored"] >= 100
    assert memo_doc["seam_calls"] == 0


def test_b3_seam_still_counts_scan_regex_compiles(tiny):
    code = (
        "import contextlib, io, json, pathlib, sys\n"
        "from agent_gap_radar import checks\n"
        "from agent_gap_radar.cli import main\n"
        "n = []\n"
        "real = checks._cached_compile\n"
        "def counting(pattern, flags=0):\n"
        "    n.append(pattern)\n"
        "    return real(pattern, flags)\n"
        "checks._cached_compile = counting\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    rc = main(['scan', sys.argv[1], '--json'])\n"
        "print(json.dumps({'rc': rc, 'n': len(n)}))\n"
    )
    p = _child(code, str(tiny))
    assert p.returncode == 0, p.stderr
    doc = json.loads(p.stdout)
    assert doc["rc"] in (0, 1)
    assert doc["n"] > 0


def test_b4_scan_reuses_the_validated_pattern_object(memo_doc):
    assert memo_doc["same"] == memo_doc["stored"] == memo_doc["n"]


def test_b4_identity_survives_a_real_scan(tiny):
    code = (
        "import contextlib, io, json, pathlib, re, sys\n"
        "from agent_gap_radar import checks, registry\n"
        "from agent_gap_radar.cli import main\n"
        "registry.load_all(pathlib.Path('gaps'))\n"
        "snap = {k: v for k, v in checks._COMPILE_CACHE.items() if k[1] == re.MULTILINE}\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    rc = main(['scan', sys.argv[1], '--json'])\n"
        "moved = [k[0] for k, v in snap.items() if checks._COMPILE_CACHE.get(k) is not v]\n"
        "print(json.dumps({'rc': rc, 'snap': len(snap), 'moved': moved}))\n"
    )
    p = _child(code, str(tiny))
    assert p.returncode == 0, p.stderr
    doc = json.loads(p.stdout)
    assert doc["rc"] in (0, 1)
    assert doc["snap"] >= 100
    assert doc["moved"] == []


# ---- b5: refusal surface unchanged -------------------------------------------


def _reg_with_pattern(tmp_path: pathlib.Path, pattern: str) -> pathlib.Path:
    (src,) = sorted(GAPS.glob("GAP-009-*.json"))
    doc = json.loads(src.read_text(encoding="utf-8"))
    assert doc["check"]["mitigated_when"]["kind"] == "content_matches"
    doc["check"]["mitigated_when"]["pattern"] = pattern
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / src.name).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return reg


def _re_error(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as exc:
        return str(exc)
    raise AssertionError(f"premise: {pattern!r} should not compile")


@pytest.mark.parametrize("pattern", ["(", "a{2,1}", "(?i)x(?m)", "[z-a]"])
def test_b5_invalid_regex_still_refused_with_same_text(tmp_path, pattern):
    reg = _reg_with_pattern(tmp_path, pattern)
    rc, out, err = _radar(["validate", str(reg)], cwd=tmp_path)
    assert rc == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert f"invalid regex '{pattern}': {_re_error(pattern)}" in err
    assert str(tmp_path) not in err


@pytest.mark.parametrize("pattern", ["", "   "])
def test_b5_blank_pattern_still_refused(tmp_path, pattern):
    reg = _reg_with_pattern(tmp_path, pattern)
    rc, out, err = _radar(["validate", str(reg)], cwd=tmp_path)
    assert rc == 2
    assert out == ""
    assert err.startswith("Error: ")
    assert "content_matches requires a 'pattern' string" in err


def test_b5_failed_compile_leaves_nothing_in_memo(tmp_path):
    reg = _reg_with_pattern(tmp_path, "(")
    code = (
        "import json, pathlib, re, sys\n"
        "from agent_gap_radar import checks, registry\n"
        "try:\n"
        "    registry.load_all(pathlib.Path(sys.argv[1]))\n"
        "    raised = False\n"
        "except Exception:\n"
        "    raised = True\n"
        "print(json.dumps({'raised': raised,\n"
        "    'bad': [list(map(str, k)) for k in checks._COMPILE_CACHE if k[0] == '(']}))\n"
    )
    p = _child(code, str(reg))
    assert p.returncode == 0, p.stderr
    doc = json.loads(p.stdout)
    assert doc["raised"] is True
    assert doc["bad"] == []


# ---- b6: deterministic, one trailing newline (byte identity vs head: report) --


@pytest.mark.parametrize("verb", [["validate"], ["list", "gaps"], ["report"], ["scan", "TINY", "--json"]])
def test_b6_outputs_deterministic_and_end_in_one_newline(tiny, verb):
    args = [str(tiny) if a == "TINY" else a for a in verb]
    first = _radar(args)
    second = _radar(args)
    assert first[0] in (0, 1), first[2]
    assert first == second
    assert first[1].endswith("\n") and not first[1].endswith("\n\n")


# ---- b7: import contract ------------------------------------------------------


def test_b7_importing_models_does_not_import_checks():
    code = (
        "import sys\n"
        "import agent_gap_radar.models\n"
        "print('agent_gap_radar.checks' in sys.modules)\n"
    )
    p = _child(code)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == "False"


_BLOCKED = r"""
import importlib, json, pkgutil, sys
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("pydantic", "pydantic_core"):
            raise ImportError("blocked " + name)
        return None
sys.meta_path.insert(0, Block())
try:
    import pydantic
    control = False
except ImportError:
    control = True
import agent_gap_radar
names = sorted(m.name for m in pkgutil.iter_modules(agent_gap_radar.__path__))
ok = []
for n in names:
    for k in [k for k in sys.modules if k.startswith("agent_gap_radar.")]:
        del sys.modules[k]
    try:
        importlib.import_module("agent_gap_radar." + n)
        ok.append(n)
    except ImportError:
        pass
print(json.dumps({"control": control, "names": names, "ok": ok}))
"""


def test_b7_pydantic_free_set_unchanged_and_no_new_module():
    p = _child(_BLOCKED)
    assert p.returncode == 0, p.stderr
    doc = json.loads(p.stdout)
    assert doc["control"] is True
    assert len(doc["names"]) == 10, doc["names"]
    assert set(doc["ok"]) == {"taxonomy", "checks", "scoring", "cli"}
