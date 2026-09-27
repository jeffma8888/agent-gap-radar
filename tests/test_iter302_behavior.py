"""Iteration 302 behaviors: `radar taxonomy --json` publishes the four closed
vocabularies plus the citation partition as ONE stable object; flagless `radar taxonomy`
is unchanged; the research contract's hand-copied `## Closed enums` block is pinned to
that object.

Black-box, and THE ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors 1-8 and from the PUBLISHED documents (`README.md`,
`docs/CONSUMER_CONTRACT.md`, `research/CANDIDATE_CONTRACT.md`); nothing here reads the
implementation source to derive an expectation, and nothing reads the engineer's or the
reviewer's notes or a diff. Every behavioral claim is measured by RUNNING the CLI in a
real child process (`sys.executable -m agent_gap_radar.cli`) so that exit codes and the
two byte channels are observed as a consumer sees them.

Structural notes, so this file cannot lie later:

* **The flagless markdown is the oracle for the JSON, never a hand-typed value.**
  Behaviors 2-4 parse the backticked names, the `-- ` glosses and the `(weight N)`
  integers out of `radar taxonomy` stdout in the same test and compare the payload to
  THAT, so a vocabulary that legitimately grows keeps every assertion green while a
  dropped, reordered or re-glossed member reds. No count is written down: each section's
  size is read from the markdown and asserted non-empty first, so no equality is vacuous.
* **The base arm for behavior 6 is the pre-change commit's own source**, extracted with
  `git archive` under `tmp_path` and imported through `PYTHONPATH` (the shape of
  `tests/test_iter220_behavior.py`). Both arms print the module file they imported, and the
  base arm is proved to be the OLD code by refusing `--json`, so "byte-identical to the
  base" cannot be satisfied by two runs of the same tree.
* **The drift pin (behavior 7) is two-sided in this run**: the tracked document passes,
  and a `tmp_path` copy with one layer name deleted fails with a message naming the
  deleted value (the shape of `tests/test_iter28_behavior.py`'s vocabulary control).
* **Cost is bounded by construction**: every child process runs `taxonomy` (no register
  load, no `scan`), and every arm is cached in a module-scoped fixture so nothing pays
  twice.
* **No absolute machine path and no personal identifier appears here.** The repo root is
  derived from `__file__`; every extracted or mutated copy lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from _surface_contract import (STABLE_SURFACE_HEADING, contract_text, gfm_table,
                               surface_violations)

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
RESEARCH_CONTRACT = REPO_ROOT / "research" / "CANDIDATE_CONTRACT.md"

#: Behavior 6 -- the commit whose flagless `radar taxonomy` bytes this iteration must
#: reproduce; `pm.md` names it, and it is the tree that did NOT know `--json`.
PRECHANGE_COMMIT = "5e016da"

#: Behavior 1 -- the six top-level keys, in the published order.
TOP_KEYS = ["layers", "gap_types", "source_classes", "statuses", "citable", "terminal"]

#: Behavior 3 -- the two keys of each ladder object, in order.
SOURCE_KEYS = ["name", "weight"]

#: The markdown's section headings (iteration 71 pinned them as publishing choices).
LAYERS_HEADING = "## Layers"
GAP_TYPES_HEADING = "## Gap types"
SOURCES_HEADING = "## Evidence source classes (strongest first)"
STATUSES_HEADING = "## Record statuses"
CITATION_GATE_HEADING = "## Citation gate"

#: Behavior 7 -- the research contract's section and its four enum line prefixes.
CLOSED_ENUMS_HEADING = "## Closed enums"
ENUM_PREFIXES = {
    "layer": "`layer`:",
    "gap_type": "`gap_type`:",
    "source_class": "`source_class` (weight):",
    "status": "`status`:",
}

#: Behavior 8 -- the contract row's first cell after this iteration.
TAXONOMY_CELL = "`radar taxonomy [--json]`"
TAXONOMY_CELL_BEFORE = "`radar taxonomy`"

_GLOSS_BULLET = re.compile(r"^- `([^`]+)` -- (.+)$")
_WEIGHT_BULLET = re.compile(r"^- `([^`]+)` \(weight (\d+)\)$")
_BACKTICKED = re.compile(r"`([^`]+)`")


# ---------------------------------------------------------------------------
# Child-process arms (each cached once per module).
# ---------------------------------------------------------------------------

def _radar(*argv: str, env: dict[str, str] | None = None) -> tuple[int, bytes, bytes]:
    """Run `radar <argv>` in a real child process from the repo root; raw bytes back."""
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", *argv],
        capture_output=True, cwd=str(REPO_ROOT), env=env, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr


@pytest.fixture(scope="module")
def json_arm() -> tuple[int, bytes, bytes]:
    return _radar("taxonomy", "--json")


@pytest.fixture(scope="module")
def json_arm_again() -> tuple[int, bytes, bytes]:
    return _radar("taxonomy", "--json")


@pytest.fixture(scope="module")
def markdown_arm() -> tuple[int, bytes, bytes]:
    return _radar("taxonomy")


@pytest.fixture(scope="module")
def payload(json_arm) -> dict:
    rc, out, err = json_arm
    assert rc == 0 and err == b"", (rc, err)
    return json.loads(out.decode("utf-8"))


@pytest.fixture(scope="module")
def markdown(markdown_arm) -> str:
    rc, out, err = markdown_arm
    assert rc == 0 and err == b"", (rc, err)
    return out.decode("utf-8")


# ---------------------------------------------------------------------------
# Markdown parsing -- the oracle for behaviors 2-4.
# ---------------------------------------------------------------------------

def _section(document: str, heading: str) -> list[str]:
    """The non-blank lines under `heading`, up to the next `## ` heading."""
    lines = document.splitlines()
    assert heading in lines, f"{heading!r} is not a heading of the document"
    start = lines.index(heading) + 1
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            body.append(line)
    assert body, f"the section {heading!r} is empty; the oracle would be vacuous"
    return body


def _glossed(document: str, heading: str) -> list[tuple[str, str]]:
    pairs = []
    for line in _section(document, heading):
        match = _GLOSS_BULLET.match(line)
        assert match, f"{heading!r} carries a line that is not a `name` -- gloss bullet: {line!r}"
        pairs.append((match.group(1), match.group(2)))
    return pairs


def _weighted(document: str) -> list[tuple[str, int]]:
    pairs = []
    for line in _section(document, SOURCES_HEADING):
        match = _WEIGHT_BULLET.match(line)
        assert match, f"ladder line is not a `name` (weight N) bullet: {line!r}"
        pairs.append((match.group(1), int(match.group(2))))
    return pairs


def _citation_gate(document: str) -> dict[str, list[str]]:
    gate: dict[str, list[str]] = {}
    for line in _section(document, CITATION_GATE_HEADING):
        match = _GLOSS_BULLET.match(line)
        assert match, f"citation gate line is not a `name` -- ... bullet: {line!r}"
        gate[match.group(1)] = _BACKTICKED.findall(match.group(2))
    assert set(gate) == {"citable", "terminal"}, sorted(gate)
    return gate


# ---------------------------------------------------------------------------
# Behavior 1 -- exit 0, empty stderr, six ordered keys, exactly one trailing newline.
# ---------------------------------------------------------------------------

def test_b1_json_exits_zero_with_six_ordered_keys_and_one_trailing_newline(json_arm):
    rc, out, err = json_arm
    assert rc == 0, f"`radar taxonomy --json` exited {rc}; stderr {err[:300]!r}"
    assert err == b"", f"stderr must be empty on success, got {err[:300]!r}"
    assert out[-1:] == b"\n", f"stdout must end in a newline; last byte {out[-1:]!r}"
    assert out[-2:-1] != b"\n", "stdout ends in TWO newlines; the contract is exactly one"
    obj = json.loads(out.decode("utf-8"))
    assert isinstance(obj, dict), f"top level must be an object, got {type(obj).__name__}"
    assert list(obj) == TOP_KEYS, (
        f"top-level keys must be exactly {TOP_KEYS} in order, got {list(obj)}")


# ---------------------------------------------------------------------------
# Behavior 2 -- `layers` / `gap_types` are name -> gloss maps in markdown order.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key, heading", [("layers", LAYERS_HEADING),
                                          ("gap_types", GAP_TYPES_HEADING)])
def test_b2_gloss_maps_follow_the_markdown_bullets_in_order(payload, markdown, key, heading):
    expected = _glossed(markdown, heading)
    names = [name for name, _gloss in expected]
    assert len(names) == len(set(names)), f"duplicate names under {heading!r}: {names}"
    got = payload[key]
    assert isinstance(got, dict), f"{key!r} must be an object, got {type(got).__name__}"
    assert list(got) == names, (
        f"{key!r} keys must equal the markdown's {len(names)} backticked names in order; "
        f"payload {list(got)}, markdown {names}")
    for name, gloss in expected:
        assert got[name] == gloss, (
            f"{key}[{name!r}] must equal the markdown gloss {gloss!r}, got {got[name]!r}")


# ---------------------------------------------------------------------------
# Behavior 3 -- `source_classes` is a ladder-ordered list of {name, weight} objects.
# ---------------------------------------------------------------------------

def test_b3_source_classes_are_ladder_ordered_name_weight_objects(payload, markdown):
    expected = _weighted(markdown)
    got = payload["source_classes"]
    assert isinstance(got, list), f"source_classes must be a list, got {type(got).__name__}"
    assert len(got) == len(expected) > 0, (len(got), len(expected))
    for item in got:
        assert isinstance(item, dict) and list(item) == SOURCE_KEYS, (
            f"each ladder entry must be an object with keys {SOURCE_KEYS} in order, got "
            f"{item!r}")
        assert isinstance(item["name"], str), item
        assert isinstance(item["weight"], int) and not isinstance(item["weight"], bool), item
    assert [item["name"] for item in got] == [name for name, _w in expected], (
        f"ladder order must equal the markdown's: payload "
        f"{[i['name'] for i in got]}, markdown {[n for n, _ in expected]}")
    assert [(item["name"], item["weight"]) for item in got] == expected, (
        f"weights must equal the markdown's `(weight N)`: payload "
        f"{[(i['name'], i['weight']) for i in got]}, markdown {expected}")


# ---------------------------------------------------------------------------
# Behavior 4 -- `statuses` in order; `citable` + `terminal` partition it.
# ---------------------------------------------------------------------------

def test_b4_statuses_in_order_and_citable_terminal_partition_them(payload, markdown):
    expected = _glossed(markdown, STATUSES_HEADING)
    names = [name for name, _gloss in expected]
    statuses = payload["statuses"]
    assert isinstance(statuses, dict) and list(statuses) == names, (
        f"statuses must be an object keyed in markdown order {names}, got {statuses!r}")
    assert statuses == dict(expected), (statuses, dict(expected))
    citable, terminal = payload["citable"], payload["terminal"]
    for label, arr in (("citable", citable), ("terminal", terminal)):
        assert isinstance(arr, list) and all(isinstance(s, str) for s in arr), (label, arr)
        assert arr, f"{label!r} is empty, so it partitions nothing"
        assert arr == [s for s in names if s in arr], (
            f"{label!r} must preserve statuses order {names}, got {arr}")
    assert not set(citable) & set(terminal), (
        f"citable and terminal overlap: {sorted(set(citable) & set(terminal))}")
    assert set(citable) | set(terminal) == set(names), (
        f"citable + terminal must cover every status {names}; union is "
        f"{sorted(set(citable) | set(terminal))}")
    gate = _citation_gate(markdown)
    assert citable == gate["citable"], (citable, gate["citable"])
    assert terminal == gate["terminal"], (terminal, gate["terminal"])


# ---------------------------------------------------------------------------
# Behavior 5 -- byte-stable across runs; a positional is refused with exit 2.
# ---------------------------------------------------------------------------

def test_b5_two_json_runs_are_byte_identical(json_arm, json_arm_again):
    assert json_arm[0] == 0 == json_arm_again[0]
    assert json_arm[1] == json_arm_again[1], "two `radar taxonomy --json` runs differ"
    assert json_arm[1], "the document is empty"


def test_b5_positional_is_refused_with_exit_2_and_empty_stdout():
    rc, out, err = _radar("taxonomy", "--json", ".")
    assert rc == 2, f"a positional must be refused with exit 2, got {rc}"
    assert out == b"", f"stdout must be empty on refusal, got {out[:200]!r}"
    tail = err.rstrip(b"\n").splitlines()[-1] if err.strip() else b""
    assert tail == b"Error: unrecognized arguments: .", (
        f"stderr tail must be the argparse refusal prefixed 'Error: ', got {tail!r}")


# ---------------------------------------------------------------------------
# Behavior 6 -- flagless `radar taxonomy` byte-identical to the pre-change commit;
# `-h` names `--json`.
# ---------------------------------------------------------------------------

def _git(*args: str) -> bytes:
    done = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True,
                          timeout=120)
    assert done.returncode == 0, (
        f"`git {' '.join(args)}` failed: {done.stderr.decode('utf-8', 'replace')[:400]!r}")
    return done.stdout


@pytest.fixture(scope="module")
def base_src(tmp_path_factory) -> pathlib.Path:
    """`git archive PRECHANGE_COMMIT src` extracted under a tmp dir; returns `<tmp>/src`."""
    root = tmp_path_factory.mktemp("base-arm")
    archive = _git("archive", PRECHANGE_COMMIT, "src")
    extract = subprocess.run(["tar", "-x", "-C", str(root)], input=archive,
                             capture_output=True, timeout=120)
    assert extract.returncode == 0, extract.stderr.decode("utf-8", "replace")[:400]
    src = root / "src"
    assert (src / "agent_gap_radar").is_dir(), sorted(p.name for p in root.iterdir())
    return src


_ARM_SCRIPT = (
    "import sys, agent_gap_radar.cli as c; "
    "sys.stderr.write(c.__file__ + '\\n'); "
    "raise SystemExit(c.main(sys.argv[1:]) or 0)"
)


def _arm(src: pathlib.Path | None, *argv: str) -> tuple[int, bytes, str]:
    """Run `radar <argv>` importing `agent_gap_radar` from `src` (or the installed tree).

    Returns (rc, stdout bytes, the imported module's file), so a caller can PROVE which
    tree answered instead of assuming it.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if src is not None:
        env["PYTHONPATH"] = str(src)
    proc = subprocess.run([sys.executable, "-c", _ARM_SCRIPT, *argv], capture_output=True,
                          cwd=str(REPO_ROOT), env=env, timeout=120)
    where = proc.stderr.decode("utf-8", "replace").splitlines()[0]
    return proc.returncode, proc.stdout, where


def test_b6_flagless_taxonomy_is_byte_identical_to_the_prechange_commit(base_src, markdown_arm):
    base_rc, base_out, base_file = _arm(base_src, "taxonomy")
    assert base_file.startswith(str(base_src)), (
        f"the base arm imported {base_file!r}, not the extracted {PRECHANGE_COMMIT} tree")
    assert base_rc == 0 and base_out, (base_rc, base_out[:200])
    # The base arm is the OLD code: it must not know `--json`. Without this, "identical to
    # the base" could be two runs of one tree.
    refused_rc, refused_out, _ = _arm(base_src, "taxonomy", "--json")
    assert refused_rc == 2 and refused_out == b"", (
        f"the {PRECHANGE_COMMIT} tree must refuse `--json` (exit 2, empty stdout); got "
        f"{refused_rc}, {refused_out[:200]!r}")
    here_rc, here_out, here_file = _arm(None, "taxonomy")
    assert not here_file.startswith(str(base_src)), here_file
    assert here_rc == 0
    assert here_out == markdown_arm[1], "the in-repo arm disagrees with the module fixture"
    assert here_out == base_out, (
        f"flagless `radar taxonomy` changed against {PRECHANGE_COMMIT}: "
        f"{len(here_out)} B now vs {len(base_out)} B then")


def test_b6_help_names_the_json_flag():
    rc, out, err = _radar("taxonomy", "-h")
    assert rc == 0 and err == b"", (rc, err[:200])
    text = out.decode("utf-8")
    assert "--json" in text, f"`radar taxonomy -h` never names --json:\n{text}"
    assert text.splitlines()[0].startswith("usage: radar taxonomy"), text.splitlines()[0]
    assert "[--json]" in text.splitlines()[0], text.splitlines()[0]


# ---------------------------------------------------------------------------
# Behavior 7 -- the research contract's `## Closed enums` block is pinned to the payload.
# ---------------------------------------------------------------------------

def _closed_enums_section(text: str) -> str:
    lines = text.splitlines()
    assert CLOSED_ENUMS_HEADING in lines, f"{CLOSED_ENUMS_HEADING!r} is missing"
    start = lines.index(CLOSED_ENUMS_HEADING) + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    return "\n".join(lines[start:end])


def _closed_enums(text: str) -> dict[str, list]:
    """The four hand-copied enum lines, parsed: comma-separated, wrapped across lines."""
    section = _closed_enums_section(text)
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", section) if p.strip()]
    found: dict[str, list] = {}
    for key, prefix in ENUM_PREFIXES.items():
        matching = [p for p in paragraphs if p.startswith(prefix)]
        assert len(matching) == 1, (
            f"expected exactly one paragraph starting {prefix!r}, found {len(matching)}")
        body = matching[0][len(prefix):].strip()
        tokens = [t.strip() for t in body.split(",") if t.strip()]
        assert tokens, f"the {key!r} line is empty"
        if key == "source_class":
            pairs = []
            for token in tokens:
                name, _sp, weight = token.rpartition(" ")
                assert name and weight.isdigit(), f"bad source_class token {token!r}"
                pairs.append((name, int(weight)))
            found[key] = pairs
        else:
            found[key] = tokens
    return found


def _drift_report(text: str, payload: dict) -> list[str]:
    """One message per SET difference between the document's enums and the payload."""
    enums = _closed_enums(text)
    expected = {
        "layer": set(payload["layers"]),
        "gap_type": set(payload["gap_types"]),
        "source_class": {(i["name"], i["weight"]) for i in payload["source_classes"]},
        "status": set(payload["statuses"]),
    }
    report: list[str] = []
    for key, want in expected.items():
        have = set(enums[key])
        missing, extra = sorted(want - have, key=str), sorted(have - want, key=str)
        if missing:
            report.append(f"{key}: the document is missing {missing}")
        if extra:
            report.append(f"{key}: the document names unknown {extra}")
    return report


def test_b7_closed_enums_block_equals_the_payload(payload):
    text = RESEARCH_CONTRACT.read_text(encoding="utf-8")
    enums = _closed_enums(text)
    for key in ENUM_PREFIXES:
        assert enums[key], key
    assert _drift_report(text, payload) == [], _drift_report(text, payload)
    # The oracle sentence appended to the section names the verb this block is pinned to.
    section = _closed_enums_section(text)
    assert "radar taxonomy --json" in section, (
        "the `## Closed enums` section never names `radar taxonomy --json` as its oracle")


def test_b7_control_a_deleted_layer_name_is_reported_by_name(payload, tmp_path):
    text = RESEARCH_CONTRACT.read_text(encoding="utf-8")
    victim = list(payload["layers"])[1]
    section = _closed_enums_section(text)
    assert section.count(victim + ",") == 1, (victim, section.count(victim + ","))
    mutated = text.replace(section, section.replace(victim + ", ", "", 1)
                           .replace(victim + ",\n", "", 1), 1)
    assert mutated != text
    copy = tmp_path / "candidate-contract.md"
    copy.write_text(mutated, encoding="utf-8")
    report = _drift_report(copy.read_text(encoding="utf-8"), payload)
    assert report, "a document missing one layer must fail the pin"
    assert any(victim in line and line.startswith("layer:") for line in report), (
        f"the failure never names the deleted layer {victim!r}: {report}")
    assert all(line.startswith("layer:") for line in report), report


# ---------------------------------------------------------------------------
# Behavior 8 -- contract row 21 renamed and extended; the surface collector still agrees.
# ---------------------------------------------------------------------------

def _promise_of(document: str, first_cell: str) -> str:
    rows = [row for row in gfm_table(document, STABLE_SURFACE_HEADING).rows
            if row[0] == first_cell]
    assert len(rows) == 1, f"expected exactly one row with first cell {first_cell!r}, got {len(rows)}"
    return rows[0][1]


def test_b8_contract_row_names_json_and_lists_the_six_keys_in_order():
    document = contract_text()
    promise = _promise_of(document, TAXONOMY_CELL)
    before = _promise_of(_git("show", f"{PRECHANGE_COMMIT}:docs/CONSUMER_CONTRACT.md")
                         .decode("utf-8"), TAXONOMY_CELL_BEFORE)
    assert before and before in promise, (
        "the new promise cell must keep every word of the pre-change cell")
    positions = [promise.find(f"`{key}`") for key in TOP_KEYS]
    assert all(p >= 0 for p in positions), (
        f"promise cell must name all six keys; missing "
        f"{[k for k, p in zip(TOP_KEYS, positions) if p < 0]}")
    assert positions == sorted(positions), (
        f"the six keys must be listed in payload order {TOP_KEYS}: offsets {positions}")
    assert "taxonomy" in promise and "cannot disagree" in promise, promise
    assert surface_violations(document) == [], surface_violations(document)
    readme = README.read_text(encoding="utf-8")
    quickstart = [ln for ln in readme.splitlines() if ln.startswith("uv run radar taxonomy")]
    assert any(ln.startswith("uv run radar taxonomy --json") for ln in quickstart), quickstart
    flagless_at = next(i for i, ln in enumerate(quickstart)
                       if not ln.startswith("uv run radar taxonomy --json"))
    json_at = next(i for i, ln in enumerate(quickstart)
                   if ln.startswith("uv run radar taxonomy --json"))
    assert json_at == flagless_at + 1, quickstart
