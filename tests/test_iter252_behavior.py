"""Iteration 252 -- a NOT_APPLICABLE finding names the `applies_when` rule that failed.

At HEAD every one of the 62 `NOT_APPLICABLE` findings `radar scan . --json` emits
carried the byte-identical eight-word `reason` `"applies_when did not match"`, with
zero `locations`.  That is 52.1% of the document making the register's largest claim
about a target while handing the reader nothing to check it with.  This iteration
appends the AUTHORED form of the failing rule to that sentence, on the `--json`
surface only.

ISOLATION: black-box.  No implementation source was read to write this module -- not
`checks.py`, not `scan.py`, not the diff, not the engineer's or reviewer's notes.
Every expectation comes from the spec's Expected Behaviors, from the conventions of
`tests/test_iter219_behavior.py` and `tests/test_iter248_behavior.py`, or from RUNNING
the product.  The renderer's name is never mentioned here: the spec makes it a private
implementation detail, so this module drives it only through `radar scan --json`.

THE ORACLE FOR "NOTHING ELSE MOVED" IS A REAL PRE-CHANGE MEASUREMENT, NOT A
RE-DERIVED EXPECTATION.  `PRECHANGE_FIXTURE_FINDINGS` below holds the exact finding
objects HEAD's committed implementation emits for this module's own four-file fixture
target, captured by materialising HEAD's `src/` out of repo with
`git archive HEAD src | tar -x -C <tmp>` and running the SAME argv from its own
`PYTHONPATH`.  Pinning a TINY fixture rather than the repo root is deliberate: the
register scans this repo's own `src/`, so a repo-root digest is a function of the
corpus AND the code at once and moves for reasons that are not renderings
(`test_iter219_behavior.py`'s `FROZEN_TREE_DOCUMENTS` records that measurement).

Costs, as COUNTS not seconds, per `tools/scan_cost.py`'s doctrine, and inside the
PM's stated budget of "no fresh full-tree scan": this module runs 30 in-process
scans of a four-file `tmp_path` tree (four refused before any check runs, one of
them the MARKDOWN surface), and reuses ONE module-scoped repo-root `--json` scan
across behaviors 1, 2, 5 and 6.  No new full-tree render is added to the suite, and
no pin here is a function of this repo's own corpus, so nothing added in round 3
freezes the register the way a live-document digest would.

MEASURED, not assumed -- what this round established by running things, since a
report reads verified while it is only predicted.  (a) `PRECHANGE_FIXTURE_*` below
were re-derived from `git archive HEAD src` with the subprocess proved to load the
archived `__init__.py`, and matched byte for byte.  (b) HEAD's live split is
`{PRESENT 5, ABSENT 24, NOT_APPLICABLE 61, MANUAL 29, UNKNOWN 0}` over 119 findings,
not the spec's 23/62, with 61 findings sharing ONE reason.  (c) The register REFUSES
an empty `any_of`/`all_of`, a `not` carrying a `rules` list, and an unrecognised
`kind`, all with exit 2 and one `Error: ` line -- so the spec's "unknown rule kind"
and "empty combinator" renders are unreachable through the public surface, and
`REFUSED_RULES` asserts the refusal instead of a render that cannot happen.  (d) The
allowed kinds are `all_of`, `any_of`, `content_absent`, `content_matches`,
`file_absent`, `file_exists`, `not`; `file_absent` is published by
`docs/CONSUMER_CONTRACT.md` and MISSING from the spec's behavior-3 list, so a case
for it was added here.  (e) Round 3 ran the SAME black-box comparison on the real
target -- HEAD's archived `src` and the working tree's `src`, both over this repo,
same argv -- and measured: 119 findings both sides, identical id sets, identical
`counts` {PRESENT 5, ABSENT 24, NOT_APPLICABLE 61, MANUAL 29, UNKNOWN 0}, identical
top-level keys, ZERO verdicts moved, ZERO non-`reason` keys moved, ZERO reasons
moved on a non-`NOT_APPLICABLE` verdict, and 61 of 61 `NOT_APPLICABLE` reasons
changed with the distinct-reason count going 1 -> 60 (60, not 61: two records author
the same rule, which is why behavior 5 is tested as a set EQUALITY against the
authored renders and not as a count).  Document length 130047 -> 143520 B.  (f) The
MARKDOWN render of this module's fixture is byte-identical between those two
implementations, which is what `PRECHANGE_FIXTURE_MARKDOWN` pins.

Offline, deterministic, no network.  The live register is only READ.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import pathlib
import re
import subprocess

import pytest

from agent_gap_radar.cli import main

REPO = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO / "gaps"

#: The sentence HEAD emitted, byte-identical, 62 times per scan.  It stays the PREFIX.
PREFIX = "applies_when did not match: "

#: The thirteen keys `docs/CONSUMER_CONTRACT.md` publishes for a `scan --json` finding.
#: Behavior 2: nothing added, nothing removed.
FINDING_KEYS = frozenset({
    "gap_id", "title", "layer", "gap_type", "verdict", "priority", "confidence",
    "below_floor", "reason", "question", "locations", "build_hypothesis", "status",
})

#: The `scan --json` DOCUMENT's own top-level keys, measured on HEAD's implementation
#: (`git archive HEAD src`, same argv, subprocess proved to load the archived
#: `__init__.py`).  Behavior 2 forbids a new key; a renderer that published its render
#: as a sibling document key rather than inside `reason` would show up here.
DOC_KEYS = ["confidence_floor", "counts", "findings", "records_applied", "target",
            "target_name", "uncheckable"]

#: Every `reason` sentence HEAD attaches to the verdicts this iteration must NOT touch.
#: MEASURED, not enumerated from memory: `git archive HEAD src` materialised HEAD's
#: implementation out of repo and `scan . --gaps gaps --json` ran from its own
#: PYTHONPATH, giving 119 findings as `{PRESENT 5, ABSENT 24, NOT_APPLICABLE 61,
#: MANUAL 29, UNKNOWN 0}` -- 61 NOT_APPLICABLE findings sharing ONE distinct reason,
#: and these five sentences across every other verdict.  Round 1 of this stage listed
#: only three and reddened on `GAP-047 is MANUAL with reason 'ambiguous: both
#: signatures present'`, which is a HEAD sentence, not a regression.
#: Behavior 2/6: none of them grows an `applies_when` clause.
UNMOVED_REASONS = frozenset({
    "ambiguous: both signatures present",
    "check is manual by declaration",
    "gap signature found",
    "mitigation positively identified",
    "no signature and no mitigation detected",
})

#: HEAD's five verdict counts on this repo, from the same measurement.  Not asserted by
#: equality -- the live corpus is this repo, so a later file can legitimately move a
#: verdict; `UNKNOWN` is the load-bearing one and it IS asserted, because `run_check`
#: turns a raising check into `UNKNOWN`, so a renderer that threw on one register node
#: would surface here as a count moving off zero.
HEAD_REPO_COUNTS = {"PRESENT": 5, "ABSENT": 24, "NOT_APPLICABLE": 61,
                    "MANUAL": 29, "UNKNOWN": 0}


# ---------------------------------------------------------------- fixture registers

_RECORD_TEMPLATE: dict[str, object] = {
    "id": "GAP-101",
    "title": "A fixture record that exists only to carry one applies_when rule",
    "layer": "orchestration",
    "gap_type": "missing-contract",
    "status": "open",
    "problem": "A fixture problem statement.",
    "symptom": "A fixture symptom.",
    "why_now": "A fixture rationale.",
    "existing": ["A fixture existing approach."],
    "severity": 4,
    "frequency": 4,
    "tractability": 4,
    "evidence": [
        {
            "source_class": "first-party-field",
            "title": "Fixture source",
            "locator": "https://example.invalid/fixture#1",
            "date": "2026-01-01",
            "quote": "a fixture quote",
        }
    ],
    "build_hypothesis": "A fixture build hypothesis.",
    "tags": ["fixture"],
}

PY = "**/*.py"
RS = "**/*.rs"
#: A pattern no fixture file contains; six globs, so the scope note must elide two.
MISS = "ZZ_NO_FIXTURE_FILE_CONTAINS_THIS_ZZ"
SIX = [PY, "**/*.ts", "**/*.js", "**/*.tsx", "**/*.md", "**/*.toml"]
#: Six globs the `target` fixture matches NO file for, so `file_exists` over them is
#: FALSE.  Round 1 used `SIX` for the `file_exists` case and measured
#: `GAP-105 was 'MANUAL'`: the target HAS `.py`, `.md` and `.toml` files, so that rule
#: was TRUE, `applies_when` matched, and the finding never reached the text under test.
#: A negative-rule fixture has to be negative for the rule's OWN kind.
SIX_ABSENT = ["**/*.rs", "**/*.go", "**/*.java", "**/*.rb", "**/*.c", "**/*.cpp"]
#: FIVE globs, so `+N more` must suppress exactly ONE.  The boundary matters: with
#: `SIX[:4]` nothing is elided and with `SIX` two are, so a renderer that hard-coded the
#: word or mis-counted by one would still satisfy both of those cases.
FIVE = SIX[:5]
#: A pattern carrying the characters the render's own `/.../` delimiters, a space and a
#: regex metacharacter, to pin that the pattern is emitted VERBATIM -- not quoted, not
#: escaped, not `repr`'d.  The live register renders patterns like
#: `content_matches /(?i)(?:FastAPI\(|from\s+fastapi)/ in ...`, so this shape is real.
SLASHY = r"def widget/(?:never) here \d+"
#: A pattern EVERY fixture `.py` file contains, so a rule over it is TRUE.
HIT = "def widget"


def _cm(pattern: str, globs: list[str]) -> dict[str, object]:
    return {"kind": "content_matches", "globs": list(globs), "pattern": pattern}


def _ca(pattern: str, globs: list[str]) -> dict[str, object]:
    return {"kind": "content_absent", "globs": list(globs), "pattern": pattern}


def _fe(globs: list[str]) -> dict[str, object]:
    return {"kind": "file_exists", "globs": list(globs)}


def _fa(globs: list[str]) -> dict[str, object]:
    return {"kind": "file_absent", "globs": list(globs)}


#: The token whose presence means "the gap signature fired".  Held out of the scanned
#: `target` fixture so every record's own verdict is decided by `applies_when` alone.
SIG = "ZZ_SIGNATURE_TOKEN_ZZ"

#: The register REFUSES an automated check without two-sided fixtures ("bad must fire,
#: good must not"), so every record here ships one.  ONE universal pair serves every
#: rule shape under test: the `bad` tree satisfies `content_matches /MISS/`, satisfies
#: `file_exists **/*.rs`, satisfies `content_absent /HIT/` (it never spells `HIT`), and
#: carries `SIG`; the `good` tree is the same tree with `SIG` removed.  That keeps the
#: fixture pair a CONSTANT across records, so the only variable is the rule.
_BAD_FIXTURE: dict[str, str] = {
    "a.py": f"# {MISS}\n# {SIG}\ndef thing():\n    return 1\n",
    "a.rs": "// a rust file, so file_exists **/*.rs is satisfied\n",
    "a.ts": f"// {MISS}\n// {SIG}\nexport const x = 1;\n",
    "a.js": f"// {MISS}\n// {SIG}\nconst x = 1;\n",
    "a.tsx": f"// {MISS}\n// {SIG}\nexport const y = 1;\n",
    "a.md": f"# {MISS}\n{SIG}\n",
    "a.toml": f'# {MISS}\n# {SIG}\nname = "x"\n',
}
_GOOD_FIXTURE: dict[str, str] = {
    name: body.replace(f"# {SIG}\n", "").replace(f"// {SIG}\n", "")
              .replace(f"{SIG}\n", "")
    for name, body in _BAD_FIXTURE.items()
}


def _record(gap_id: str, applies_when: dict[str, object] | None) -> dict[str, object]:
    """One register record whose automated check carries `applies_when` verbatim.

    `present_when`/`mitigated_when`/`fixtures` are held FIXED across every fixture
    record so the only variable between records is the `applies_when` rule under test.
    """
    record = json.loads(json.dumps(_RECORD_TEMPLATE))
    record["id"] = gap_id
    check: dict[str, object] = {
        "id": "CHK-" + gap_id.split("-")[1],
        "present_when": _cm(SIG, [PY, "**/*.ts", "**/*.js", "**/*.tsx", "**/*.md",
                                  "**/*.toml"]),
        "mitigated_when": _cm("ZZ_MITIGATION_NEVER_PRESENT_ZZ", [PY]),
        "manual_question": "A fixture manual question ending in a question mark?",
        "rationale": "A fixture rationale for why the question is asked.",
        "fixtures": {"bad": dict(_BAD_FIXTURE), "good": dict(_GOOD_FIXTURE)},
    }
    if applies_when is not None:
        check["applies_when"] = applies_when
    record["check"] = check
    return record


def _register(tmp_path: pathlib.Path, rules: dict[str, dict[str, object] | None]) -> pathlib.Path:
    """Write a register of one record per (gap_id -> applies_when) pair."""
    gaps = tmp_path / "reg"
    gaps.mkdir(parents=True, exist_ok=True)
    for gap_id, rule in rules.items():
        (gaps / f"{gap_id}-fixture.json").write_text(
            json.dumps(_record(gap_id, rule), indent=2) + "\n", encoding="utf-8")
    return gaps


@pytest.fixture()
def target(tmp_path: pathlib.Path) -> pathlib.Path:
    """A four-file non-git tree.  Every `.py` file carries `HIT`; no `.rs` file exists."""
    t = tmp_path / "t"
    (t / "pkg").mkdir(parents=True)
    (t / "pkg" / "a.py").write_text("def widget():\n    return 1\n", encoding="utf-8")
    (t / "pkg" / "b.py").write_text("def widget_two():\n    return 2\n", encoding="utf-8")
    (t / "notes.md").write_text("# a fixture document\n", encoding="utf-8")
    (t / "pyproject.toml").write_text('[project]\nname = "fixture"\n', encoding="utf-8")
    return t


# ---------------------------------------------------------------- running the product

def _run(argv: tuple[str, ...], monkeypatch: pytest.MonkeyPatch,
         cwd: pathlib.Path | None = None) -> tuple[int, bytes, str]:
    """Run the CLI in-process from `cwd` (default the repo root), stdout as BYTES."""
    monkeypatch.chdir(cwd if cwd is not None else REPO)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue().encode("utf-8"), err.getvalue()


def _scan_json(target: pathlib.Path, gaps: pathlib.Path,
               monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """`radar scan <target> --gaps <reg> --json`, asserting the whole-document bar.

    Every call this module makes goes through here, so behavior 7's quality bar is
    asserted on ELEVEN documents rather than once.
    """
    argv = ("scan", str(target), "--gaps", str(gaps), "--json")
    code, out, err = _run(argv, monkeypatch)
    assert code == 0, f"{' '.join(argv)} exited {code}; stderr={err!r}"
    assert err == "", f"scan --json wrote to stderr: {err!r}"
    text = out.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        "the document does not end in exactly one newline")
    doc = json.loads(text)
    assert sorted(doc) == DOC_KEYS, (
        f"the document's top-level key set is {sorted(doc)}, expected {DOC_KEYS}")
    for finding in doc["findings"]:
        assert frozenset(finding) == FINDING_KEYS, (
            f"finding {finding.get('gap_id')!r} key set is {sorted(finding)}, "
            f"expected {sorted(FINDING_KEYS)}")
    return doc


def _by_id(doc: dict[str, object]) -> dict[str, dict[str, object]]:
    return {f["gap_id"]: f for f in doc["findings"]}  # type: ignore[index]


# ------------------------------------------ an INDEPENDENT reimplementation of 3 and 4

def _scope(globs: list[str]) -> str:
    """Behavior 3's scope note: authored order, first four, `, +N more` for the rest."""
    head = ", ".join(globs[:4])
    extra = len(globs) - 4
    return f"{head}, +{extra} more" if extra > 0 else head


def _render(rule: object) -> str:
    """The spec's behaviors 3-4, written from the SPEC and never from the source.

    This is the oracle behavior 5 cross-checks the product against: a second
    implementation of the same authored-rule grammar, so agreement is evidence and
    not a tautology.
    """
    if not isinstance(rule, dict):
        return f"unknown rule kind: {None!r}"
    kind = rule.get("kind")
    if kind in ("any_of", "all_of"):
        inner = ", ".join(_render(r) for r in rule.get("rules") or [])
        return f"{kind}({inner})"
    if kind == "not":
        # The register REFUSES `not` with a `rules` list ("not requires a 'rule'
        # object", exit 2), so `rule` is the only shape that can reach a render.
        return f"not({_render(rule.get('rule'))})"
    if kind == "content_matches":
        return f"content_matches /{rule.get('pattern')}/ in {_scope(list(rule.get('globs') or []))}"
    if kind == "content_absent":
        return f"content_absent /{rule.get('pattern')}/ in {_scope(list(rule.get('globs') or []))}"
    if kind == "file_exists":
        return f"file_exists {_scope(list(rule.get('globs') or []))}"
    if kind == "file_absent":
        return f"file_absent {_scope(list(rule.get('globs') or []))}"
    return f"unknown rule kind: {kind!r}"


# ------------------------------------------------------------------- the live register

@pytest.fixture(scope="module")
def repo_scan() -> dict[str, object]:
    """ONE repo-root `radar scan . --json`, shared by behaviors 5 and 6.

    Out of process so a module-scoped fixture needs no `monkeypatch` (which is
    function-scoped) and so the cwd change cannot leak into another test.
    """
    proc = subprocess.run(
        ["python", "-m", "agent_gap_radar.cli", "scan", ".", "--gaps", "gaps", "--json"],
        cwd=REPO, capture_output=True, check=False)
    assert proc.returncode == 0, (
        f"repo-root scan --json exited {proc.returncode}; stderr={proc.stderr!r}")
    assert proc.stderr == b"", f"repo-root scan --json wrote to stderr: {proc.stderr!r}"
    text = proc.stdout.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    return json.loads(text)


def _live_applies_when() -> dict[str, object]:
    """gap_id -> the record's authored `applies_when`, read from the register as DATA."""
    out: dict[str, object] = {}
    for path in sorted(GAPS_DIR.glob("GAP-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        rule = (record.get("check") or {}).get("applies_when")
        if rule is not None:
            out[record["id"]] = rule
    return out


# =============================================================== Expected Behavior 1

def test_b1_a_not_applicable_reason_names_the_rule_that_failed(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 1: verdict unchanged, reason = PREFIX + the authored render.

    `locations` stays empty and `question` stays empty -- the rule did not match, so
    there is no matched line to cite, and inventing one beside a non-match is the
    opposite of this iteration's point.
    """
    rule = _cm(MISS, [PY])
    gaps = _register(tmp_path, {"GAP-101": rule})
    doc = _scan_json(target, gaps, monkeypatch)
    finding = _by_id(doc)["GAP-101"]
    assert finding["verdict"] == "NOT_APPLICABLE", (
        f"a non-matching applies_when must stay NOT_APPLICABLE, got {finding['verdict']!r}")
    assert finding["reason"] == PREFIX + f"content_matches /{MISS}/ in {PY}", (
        f"reason was {finding['reason']!r}")
    assert finding["locations"] == [], f"locations was {finding['locations']!r}"
    assert finding["question"] == "", f"question was {finding['question']!r}"


# =============================================================== Expected Behavior 2

def test_b2_no_key_moved_and_no_other_verdict_grew_an_applies_when_clause(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 2: the key set is the published thirteen and no verdict value moved.

    The armed half is `GAP-107`, whose `applies_when` MATCHES this target: its verdict
    must be one of the three that mean the check actually ran, and its `reason` must be
    one of HEAD's three unmoved sentences -- byte-identical, not merely similar.
    """
    gaps = _register(tmp_path, {
        "GAP-101": _cm(MISS, [PY]),
        "GAP-107": _cm(HIT, [PY]),
    })
    doc = _scan_json(target, gaps, monkeypatch)  # asserts FINDING_KEYS on every finding
    findings = _by_id(doc)
    assert set(findings) == {"GAP-101", "GAP-107"}
    assert doc["counts"]["NOT_APPLICABLE"] == 1, f"counts were {doc['counts']!r}"
    for gap_id, finding in findings.items():
        if finding["verdict"] == "NOT_APPLICABLE":
            continue
        assert finding["reason"] in UNMOVED_REASONS, (
            f"{gap_id}'s verdict {finding['verdict']!r} carries reason "
            f"{finding['reason']!r}, which is not one of HEAD's three")


def test_b2_the_prechange_implementation_agrees_on_every_finding_but_the_reason(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 2, against a REAL pre-change measurement (`PRECHANGE_FIXTURE_FINDINGS`).

    Every key of every finding is compared to what HEAD's committed implementation
    emitted for this exact target and register.  `reason` is the ONLY key allowed to
    differ, and only on a `NOT_APPLICABLE` finding.
    """
    gaps = _register(tmp_path, PRECHANGE_FIXTURE_RULES)
    doc = _scan_json(target, gaps, monkeypatch)
    got = _by_id(doc)
    assert sorted(got) == sorted(PRECHANGE_FIXTURE_FINDINGS), (
        "the set of findings moved against the pre-change implementation")
    for gap_id, before in PRECHANGE_FIXTURE_FINDINGS.items():
        after = got[gap_id]
        for key in sorted(FINDING_KEYS):
            if key == "reason":
                continue
            assert after[key] == before[key], (
                f"{gap_id}.{key} moved: pre-change {before[key]!r}, now {after[key]!r}")
        if before["verdict"] != "NOT_APPLICABLE":
            assert after["reason"] == before["reason"], (
                f"{gap_id} is {before['verdict']} and its reason moved: "
                f"{before['reason']!r} -> {after['reason']!r}")
    assert doc["counts"] == PRECHANGE_FIXTURE_COUNTS, (
        f"counts moved: pre-change {PRECHANGE_FIXTURE_COUNTS!r}, now {doc['counts']!r}")


# ============================================================= Expected Behaviors 3, 4

#: One case per row of behaviors 3 and 4: (gap_id, applies_when, expected render).
#: Every rule here is FALSE against the `target` fixture, so each one reaches the
#: NOT_APPLICABLE text through the product's own public surface.
RULE_CASES: list[tuple[str, dict[str, object], str]] = [
    # -- behavior 3, leaves
    ("GAP-101", _cm(MISS, [PY]), f"content_matches /{MISS}/ in {PY}"),
    ("GAP-102", _cm(MISS, SIX),
     f"content_matches /{MISS}/ in {PY}, **/*.ts, **/*.js, **/*.tsx, +2 more"),
    ("GAP-103", _cm(MISS, SIX[:4]),
     f"content_matches /{MISS}/ in {PY}, **/*.ts, **/*.js, **/*.tsx"),
    ("GAP-104", _fe([RS]), f"file_exists {RS}"),
    ("GAP-105", _fe(SIX_ABSENT),
     "file_exists **/*.rs, **/*.go, **/*.java, **/*.rb, +2 more"),
    ("GAP-106", _ca(HIT, [PY]), f"content_absent /{HIT}/ in {PY}"),
    ("GAP-109", _cm(MISS, FIVE),
     f"content_matches /{MISS}/ in {PY}, **/*.ts, **/*.js, **/*.tsx, +1 more"),
    ("GAP-110", _cm(SLASHY, [PY]), f"content_matches /{SLASHY}/ in {PY}"),
    # `file_absent` is a kind the register ALLOWS and the consumer contract publishes,
    # though the spec's behavior-3 list omits it; over a target that HAS `.py` files
    # the rule is false, so it reaches the text under test.
    ("GAP-108", _fa([PY]), f"file_absent {PY}"),
    # -- behavior 4, combinators, sub-rules in AUTHORED order
    ("GAP-111", {"kind": "all_of", "rules": [_cm(MISS, [PY]), _fe([RS])]},
     f"all_of(content_matches /{MISS}/ in {PY}, file_exists {RS})"),
    ("GAP-112", {"kind": "any_of", "rules": [_cm(MISS, [PY]), _fe([RS])]},
     f"any_of(content_matches /{MISS}/ in {PY}, file_exists {RS})"),
    ("GAP-116", {"kind": "not", "rule": _cm(HIT, [PY])},
     f"not(content_matches /{HIT}/ in {PY})"),
    ("GAP-114", {"kind": "any_of", "rules": [
        {"kind": "all_of", "rules": [_cm(MISS, [PY]), _fe([RS])]}, _fe([RS])]},
     f"any_of(all_of(content_matches /{MISS}/ in {PY}, file_exists {RS}), "
     f"file_exists {RS})"),
    # `not` as an ARM of a combinator, and a combinator INSIDE a `not`: the recursion
    # has to descend through both, and only the nested forms can catch a renderer that
    # special-cased `not` at the top level.
    ("GAP-113", {"kind": "all_of", "rules": [{"kind": "not", "rule": _cm(HIT, [PY])},
                                             _cm(MISS, [PY])]},
     f"all_of(not(content_matches /{HIT}/ in {PY}), content_matches /{MISS}/ in {PY})"),
    ("GAP-117", {"kind": "not", "rule": {"kind": "any_of", "rules": [
        _cm(HIT, [PY]), _fe(["**/*.go"])]}},
     f"not(any_of(content_matches /{HIT}/ in {PY}, file_exists **/*.go))"),
]


@pytest.mark.parametrize(("gap_id", "rule", "expected"), RULE_CASES,
                         ids=[c[0] + ":" + c[1]["kind"] for c in RULE_CASES])  # type: ignore[index]
def test_b3_b4_each_rule_shape_renders_exactly_as_the_spec_states(
        gap_id: str, rule: dict[str, object], expected: str,
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behaviors 3 and 4: one scan per rule shape, asserting the WHOLE reason string.

    Parametrised one-record-per-scan rather than one scan over all of them, because a
    render that leaked another record's rule into this one would otherwise pass.
    """
    gaps = _register(tmp_path, {gap_id: rule})
    doc = _scan_json(target, gaps, monkeypatch)
    finding = _by_id(doc)[gap_id]
    assert finding["verdict"] == "NOT_APPLICABLE", (
        f"{gap_id} was {finding['verdict']!r}; this rule is false against the fixture")
    assert finding["reason"] == PREFIX + expected, f"reason was {finding['reason']!r}"
    assert finding["reason"] == PREFIX + _render(rule), (
        "the product and this module's independent renderer disagree")


def test_b4_a_partly_true_all_of_still_renders_as_authored(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 4's last sentence: no sub-render may claim a per-leaf result.

    `GAP-115`'s first arm MATCHES the target and its second does not, so a renderer
    that annotated arms would have to say something false about the first one.
    """
    rule = {"kind": "all_of", "rules": [_cm(HIT, [PY]), _fe([RS])]}
    gaps = _register(tmp_path, {"GAP-115": rule})
    doc = _scan_json(target, gaps, monkeypatch)
    reason = _by_id(doc)["GAP-115"]["reason"]
    assert reason == PREFIX + f"all_of(content_matches /{HIT}/ in {PY}, file_exists {RS})", (
        f"reason was {reason!r}")
    for claim in ("(no match)", "(matched)", "no match)", "-> False", "=False"):
        assert claim not in reason, f"the render asserts a per-leaf result {claim!r}"


#: Rule nodes the register REFUSES outright, each measured in this round through
#: `radar scan --json` (exit 2, empty stdout, one `Error: ` line on stderr).  They
#: matter to behaviors 3 and 4 as the REASON their totality clauses are unreachable
#: from the public surface: an empty `any_of`/`all_of` and an unrecognised `kind` never
#: reach a render, because record validation rejects the file before any check runs.
REFUSED_RULES: list[tuple[str, dict[str, object], str]] = [
    ("empty-any_of", {"kind": "any_of", "rules": []}, "any_of"),
    ("empty-all_of", {"kind": "all_of", "rules": []}, "all_of"),
    ("not-with-a-rules-list", {"kind": "not", "rules": [_cm(MISS, [PY])]}, "not"),
    ("unrecognised-kind", {"kind": "frobnicate", "pattern": MISS, "globs": [PY]},
     "frobnicate"),
]


@pytest.mark.parametrize(("name", "rule", "token"), REFUSED_RULES,
                         ids=[c[0] for c in REFUSED_RULES])
def test_b3_b4_a_malformed_rule_is_refused_cleanly_and_never_rendered(
        name: str, rule: dict[str, object], token: str,
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behaviors 3/4 totality + the quality bar for every failure path.

    The spec says a rule dict whose `kind` is unrecognised "RAISES NOTHING, so the
    renderer is total", and that the path is unreachable from `run_check`.  Measured
    here: it is unreachable EARLIER than the spec says -- record validation refuses
    the register file, so the scan never verdicts at all.  What must hold on that path
    is the product's own bar: exit 2, `Error: ` on stderr, and stdout carrying nothing.
    """
    gaps = _register(tmp_path, {"GAP-101": rule})
    argv = ("scan", str(target), "--gaps", str(gaps), "--json")
    code, out, err = _run(argv, monkeypatch)
    assert code == 2, f"{name}: exited {code}, expected 2; stderr={err!r}"
    assert out == b"", f"{name}: stdout was not empty on a refusal: {out[:200]!r}"
    assert err.startswith("Error: "), f"{name}: stderr does not start with the prefix: {err!r}"
    assert err.endswith("\n") and err.count("\n") == 1, (
        f"{name}: the refusal is not exactly one line: {err!r}")
    assert token in err, f"{name}: the refusal does not name {token!r}: {err!r}"
    assert PREFIX not in err, (
        f"{name}: a refused rule reached the NOT_APPLICABLE text: {err!r}")


# =============================================================== Expected Behavior 5

def test_b5_the_defect_is_closed_on_the_real_target(repo_scan: dict[str, object]) -> None:
    """Behavior 5: every live NOT_APPLICABLE reason names its rule, and they differ.

    Distinct-reason count was exactly 1 over 62 findings at HEAD.  The check that this
    is not merely "more than one" is the second assertion: the number of distinct
    reasons EQUALS the number of distinct authored renders among the records that
    reached the verdict, computed here from `gaps/` by this module's own renderer.
    """
    na = [f for f in repo_scan["findings"] if f["verdict"] == "NOT_APPLICABLE"]
    assert na, "the repo-root scan produced no NOT_APPLICABLE findings to measure"
    for finding in na:
        reason = finding["reason"]
        assert reason.startswith(PREFIX), f"{finding['gap_id']}'s reason is {reason!r}"
        assert len(reason) > len(PREFIX), (
            f"{finding['gap_id']}'s reason is the bare prefix and names no rule")
    distinct = {f["reason"] for f in na}
    assert len(distinct) > 1, (
        f"all {len(na)} NOT_APPLICABLE reasons are still identical: {distinct!r}")
    authored = _live_applies_when()
    expected = {PREFIX + _render(authored[f["gap_id"]]) for f in na}
    assert distinct == expected, (
        "the distinct reasons are not the distinct authored renders; "
        f"only in product: {sorted(distinct - expected)!r}; "
        f"only in the register: {sorted(expected - distinct)!r}")


def test_b5_every_live_reason_is_the_render_of_that_records_own_rule(
        repo_scan: dict[str, object]) -> None:
    """Behavior 5, per RECORD rather than per SET.

    `test_b5_the_defect_is_closed_on_the_real_target` compares the SET of distinct
    reasons with the SET of distinct authored renders, which a renderer that attached
    record B's rule to record A's finding would still satisfy exactly.  This pins each
    finding to ITS OWN record's `applies_when`, read from `gaps/` as data.
    """
    authored = _live_applies_when()
    mismatched: list[tuple[str, str, str]] = []
    ruleless: list[str] = []
    for finding in repo_scan["findings"]:
        if finding["verdict"] != "NOT_APPLICABLE":
            continue
        rule = authored.get(finding["gap_id"])
        if rule is None:
            ruleless.append(finding["gap_id"])
            continue
        want = PREFIX + _render(rule)
        if finding["reason"] != want:
            mismatched.append((finding["gap_id"], want, finding["reason"]))
    assert ruleless == [], (
        f"records verdicted NOT_APPLICABLE with no authored applies_when: {ruleless!r}")
    assert mismatched == [], (
        "a NOT_APPLICABLE reason does not render its own record's rule: "
        + "; ".join(f"{g}: want {w!r}, got {r!r}" for g, w, r in mismatched[:5]))


def test_b2_the_live_scan_verdicts_every_record_and_none_became_unknown(
        repo_scan: dict[str, object]) -> None:
    """Behavior 2 on the real target: no verdict moved into `UNKNOWN`.

    `run_check` converts a raising check into `UNKNOWN`, so a renderer that threw on
    one of the 116 authored `applies_when` nodes would show up here as a count off
    zero -- and HEAD's measurement (see `HEAD_REPO_COUNTS`) is exactly zero.  The
    other four counts are deliberately NOT pinned by equality: the live target is this
    repo, whose corpus legitimately grows.
    """
    counts = repo_scan["counts"]
    assert sorted(counts) == sorted(HEAD_REPO_COUNTS), (
        f"the verdict vocabulary moved: {sorted(counts)!r}")
    assert counts["UNKNOWN"] == 0, (
        f"{counts['UNKNOWN']} finding(s) became UNKNOWN, which is what a raising "
        "renderer looks like from outside")
    assert sum(counts.values()) == len(repo_scan["findings"]), (
        f"counts {counts!r} do not sum to {len(repo_scan['findings'])} findings")
    assert counts["NOT_APPLICABLE"] > 0, "no NOT_APPLICABLE finding to measure"


# =============================================================== Expected Behavior 6

def test_b6_a_matching_rule_never_reaches_this_text(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 6, armed control on a fixture whose rule is TRUE."""
    gaps = _register(tmp_path, {"GAP-107": _cm(HIT, [PY])})
    doc = _scan_json(target, gaps, monkeypatch)
    finding = _by_id(doc)["GAP-107"]
    assert finding["verdict"] != "NOT_APPLICABLE", (
        "a target that satisfies applies_when must not be told the gap cannot apply")
    assert "applies_when" not in finding["reason"], (
        f"a matching rule reached the NOT_APPLICABLE text: {finding['reason']!r}")


def test_b6_no_live_finding_outside_the_verdict_mentions_applies_when(
        repo_scan: dict[str, object]) -> None:
    """Behavior 6 on the real target: the clause is confined to ONE verdict."""
    leaked = [(f["gap_id"], f["verdict"], f["reason"]) for f in repo_scan["findings"]
              if f["verdict"] != "NOT_APPLICABLE" and "applies_when" in f["reason"]]
    assert leaked == [], f"findings outside NOT_APPLICABLE mention applies_when: {leaked!r}"
    for f in repo_scan["findings"]:
        if f["verdict"] != "NOT_APPLICABLE":
            assert f["reason"] in UNMOVED_REASONS, (
                f"{f['gap_id']} is {f['verdict']} with reason {f['reason']!r}")


# =============================================================== Expected Behavior 7

def test_b7_two_consecutive_runs_are_byte_identical(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 7: determinism, one trailing newline, stdout only, empty stderr."""
    gaps = _register(tmp_path, dict(PRECHANGE_FIXTURE_RULES))
    argv = ("scan", str(target), "--gaps", str(gaps), "--json")
    first = _run(argv, monkeypatch)
    second = _run(argv, monkeypatch)
    assert first[0] == second[0] == 0
    assert first[2] == second[2] == ""
    assert first[1] == second[1], "two consecutive scan --json runs differ"
    text = first[1].decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_b7_the_render_is_a_function_of_the_rule_dict_alone(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 7's second sentence: not the target path, not the cwd, not the env.

    Two DIFFERENT target trees with different names, scanned from two different cwds,
    must produce the identical reason for the identical rule.
    """
    rule = {"kind": "all_of", "rules": [_cm(MISS, SIX), _fe([RS])]}
    gaps = _register(tmp_path, {"GAP-101": rule})
    reasons = []
    for name, cwd in (("alpha", REPO), ("a-much-longer-tree-name", tmp_path)):
        t = tmp_path / name
        (t / "pkg").mkdir(parents=True)
        (t / "pkg" / "a.py").write_text("def widget():\n    return 1\n", encoding="utf-8")
        code, out, err = _run(
            ("scan", str(t), "--gaps", str(gaps), "--json"), monkeypatch, cwd)
        assert code == 0 and err == ""
        reasons.append(_by_id(json.loads(out.decode("utf-8")))["GAP-101"]["reason"])
    assert reasons[0] == reasons[1], f"the render moved with the target/cwd: {reasons!r}"
    assert reasons[0] == PREFIX + _render(rule)


# ============================================================ Expected Behaviors 8, 9

#: Behavior 8: the markdown pin `test_iter219_behavior.py` commits, quoted here so a
#: re-baseline of it is visible from THIS module too.  Behavior 9 names the `--json`
#: pin as the ONE that may move, and its HEAD value, so a second silent re-baseline is
#: a red test rather than an invisible one.
MARKDOWN_PIN = (25116, "7dc7c366b3575024ca75a37db24547b9b985128457e3b91f42a3517fdd38a966")
JSON_PIN_AT_HEAD = (129742, "36cb0e856bea0b29acc2ca3425c45d070fd1dc5aa94c8ccef8f74692bddfa838")


def _committed_scan_pins() -> dict[tuple[str, ...], tuple[object, ...]]:
    """`FROZEN_TREE_DOCUMENTS` read out of `test_iter219_behavior.py` as a LITERAL.

    Parsed with `ast`, not imported: round 1 of this stage used
    `__import__("tests.test_iter219_behavior")` and measured
    `ModuleNotFoundError: No module named 'tests'` -- this project's `tests/` is a
    rootdir directory, not a package.  Parsing is also the stricter oracle: it reads
    the bytes the repo COMMITS, with none of that module's imports or fixtures running.
    """
    source = (REPO / "tests" / "test_iter219_behavior.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        target_names = []
        if isinstance(node, ast.AnnAssign):
            target_names = [getattr(node.target, "id", "")]
        elif isinstance(node, ast.Assign):
            target_names = [getattr(t, "id", "") for t in node.targets]
        if "FROZEN_TREE_DOCUMENTS" in target_names and node.value is not None:
            literal = ast.literal_eval(node.value)
            return {tuple(k): tuple(v) for k, v in literal.items()}
    raise AssertionError(
        "FROZEN_TREE_DOCUMENTS is no longer a module-level literal in "
        "tests/test_iter219_behavior.py, so behaviors 8 and 9 have no oracle")


def test_b8_b9_exactly_one_committed_scan_pin_moved_and_it_is_the_json_one() -> None:
    """Behaviors 8 and 9, read off the committed pin constants, not off whole files.

    Deliberately NOT a whole-file digest of `test_iter219_behavior.py`: iteration 245's
    `pins are unedited` brake was written from one iteration's diff and froze that
    surface forever.  This asserts only the two propositions the spec makes -- the
    markdown pin is unchanged, and the `--json` pin grew past its HEAD value -- so a
    later iteration that legitimately moves the JSON bytes again is not blocked by it.
    """
    pins = _committed_scan_pins()
    assert pins[("scan", ".", "--gaps", "gaps")] == MARKDOWN_PIN, (
        "the markdown pin moved; behavior 8 requires that surface be byte-identical")
    length, digest = pins[("scan", ".", "--gaps", "gaps", "--json")]
    assert (length, digest) != JSON_PIN_AT_HEAD, (
        "the --json pin was not re-baselined, so the new reason text never reached it")
    assert length > JSON_PIN_AT_HEAD[0], (
        f"the --json document is {length} B, not strictly greater than "
        f"{JSON_PIN_AT_HEAD[0]} B; naming 61 rules can only make it longer")
    assert re.fullmatch(r"[0-9a-f]{64}", digest), f"digest {digest!r} is not a sha256"


def test_b9_the_old_sentence_is_spelled_at_exactly_one_site() -> None:
    """Behavior 9's tail: the sentence has ONE spelling site and no test/doc pins it.

    Measured over the repo as text, so a copy of the sentence pasted into a second
    module or a golden reds this immediately.
    """
    proc = subprocess.run(["git", "grep", "-c", "applies_when did not match", "--",
                           "src", "tests", "docs", "gaps"],
                          cwd=REPO, capture_output=True, text=True, check=False)
    hits = {}
    for line in proc.stdout.splitlines():
        path, _, count = line.rpartition(":")
        hits[path] = int(count)
    assert hits.get("src/agent_gap_radar/checks.py") == 1, (
        f"the sentence is spelled {hits.get('src/agent_gap_radar/checks.py')!r} times "
        f"in checks.py; the spec requires exactly one site. All hits: {hits!r}")
    assert hits.get("docs/CONSUMER_CONTRACT.md", 0) >= 1, (
        "the consumer contract does not spell the sentence at all, so behavior 10 "
        f"cannot be documenting this reason. All hits: {hits!r}")
    assert set(hits) <= {"src/agent_gap_radar/checks.py",
                         "docs/CONSUMER_CONTRACT.md",
                         "tests/test_iter252_behavior.py"}, (
        f"the sentence leaked into a golden, another test module or a record: "
        f"{sorted(hits)!r}")


# =============================================================== Expected Behavior 10

def test_b10_the_consumer_contract_documents_the_new_reason() -> None:
    """Behavior 10: the contract states it, and its published key list is unchanged."""
    text = (REPO / "docs" / "CONSUMER_CONTRACT.md").read_text(encoding="utf-8")
    assert "applies_when" in text, "the contract never mentions applies_when"
    lowered = text.lower()
    assert "not_applicable" in lowered
    for key in sorted(FINDING_KEYS):
        assert key in text, f"the contract stopped publishing the {key!r} key"
    for absent in ("applies_when_render", "rule_render", "applies_when_rule"):
        assert absent not in text, (
            f"the contract publishes a NEW key {absent!r}; behavior 2 forbids one")


# ---- pre-change measurement, captured from HEAD's src; see the module docstring ----
PRECHANGE_FIXTURE_RULES: dict[str, dict[str, object] | None] = {
    "GAP-101": _cm(MISS, [PY]),
    "GAP-104": _fe([RS]),
    "GAP-107": _cm(HIT, [PY]),
    "GAP-111": {"kind": "all_of", "rules": [_cm(MISS, [PY]), _fe([RS])]},
}
#: HEAD's MARKDOWN render of this module's own fixture target and register -- the
#: surface behavior 8 freezes -- captured the same way as the findings below and with
#: the one `Target: ` line normalised, because it carries the tmp_path.  Byte length AND
#: digest, so a re-baseline cannot hide in a same-length edit.  MEASURED: HEAD's src and
#: the working tree's src both emit these exact bytes, so behavior 8 holds on a frozen
#: tree this module owns, independently of `test_iter219_behavior.py`'s repo-root pin.
PRECHANGE_FIXTURE_MARKDOWN = (
    839, "f0848538eb409a82e1012f951de061a67b045d4c7f7c5b395b60d3a8f135aa45")

PRECHANGE_FIXTURE_COUNTS: dict[str, int] = {
    "PRESENT": 0,
    "ABSENT": 0,
    "NOT_APPLICABLE": 3,
    "MANUAL": 1,
    "UNKNOWN": 0
}
PRECHANGE_FIXTURE_FINDINGS: dict[str, dict[str, object]] = {
    "GAP-101": {
        "below_floor": False,
        "build_hypothesis": "A fixture build hypothesis.",
        "confidence": 5,
        "gap_id": "GAP-101",
        "gap_type": "missing-contract",
        "layer": "orchestration",
        "locations": [],
        "priority": 8.0,
        "question": "",
        "reason": "applies_when did not match",
        "status": "open",
        "title": "A fixture record that exists only to carry one applies_when rule",
        "verdict": "NOT_APPLICABLE"
    },
    "GAP-104": {
        "below_floor": False,
        "build_hypothesis": "A fixture build hypothesis.",
        "confidence": 5,
        "gap_id": "GAP-104",
        "gap_type": "missing-contract",
        "layer": "orchestration",
        "locations": [],
        "priority": 8.0,
        "question": "",
        "reason": "applies_when did not match",
        "status": "open",
        "title": "A fixture record that exists only to carry one applies_when rule",
        "verdict": "NOT_APPLICABLE"
    },
    "GAP-107": {
        "below_floor": False,
        "build_hypothesis": "A fixture build hypothesis.",
        "confidence": 5,
        "gap_id": "GAP-107",
        "gap_type": "missing-contract",
        "layer": "orchestration",
        "locations": [],
        "priority": 8.0,
        "question": "A fixture manual question ending in a question mark?",
        "reason": "no signature and no mitigation detected",
        "status": "open",
        "title": "A fixture record that exists only to carry one applies_when rule",
        "verdict": "MANUAL"
    },
    "GAP-111": {
        "below_floor": False,
        "build_hypothesis": "A fixture build hypothesis.",
        "confidence": 5,
        "gap_id": "GAP-111",
        "gap_type": "missing-contract",
        "layer": "orchestration",
        "locations": [],
        "priority": 8.0,
        "question": "",
        "reason": "applies_when did not match",
        "status": "open",
        "title": "A fixture record that exists only to carry one applies_when rule",
        "verdict": "NOT_APPLICABLE"
    }
}


# ============================================ Expected Behaviors 1, 5, 8 -- extensions

def test_b1_a_record_with_no_applies_when_never_carries_the_clause(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 1's precondition, negated: no rule means no clause and no verdict.

    Behavior 1 is conditioned on a record whose check HAS an `applies_when` that does
    not match.  116 of the register's 120 records carry one, so the four that do not are
    the boundary: such a record must never be told the gap cannot apply, and its reason
    must not grow the clause either.  A renderer wired at the wrong site -- say onto
    every finding, or onto a missing rule as `None` -- fails exactly here.
    """
    gaps = _register(tmp_path, {"GAP-101": None})
    doc = _scan_json(target, gaps, monkeypatch)
    finding = _by_id(doc)["GAP-101"]
    assert finding["verdict"] != "NOT_APPLICABLE", (
        "a record with no applies_when cannot be NOT_APPLICABLE: nothing failed to match")
    assert "applies_when" not in finding["reason"], (
        f"a ruleless record grew the clause: {finding['reason']!r}")
    assert finding["reason"] in UNMOVED_REASONS, (
        f"reason was {finding['reason']!r}, not one of HEAD's five sentences")
    assert doc["counts"]["NOT_APPLICABLE"] == 0, f"counts were {doc['counts']!r}"


def _normalised_markdown(out: bytes) -> bytes:
    """The markdown with its one absolute-path line replaced by a token.

    `Target: ` echoes the scanned path, which is a `tmp_path` here, so the raw bytes
    cannot be pinned.  Everything else in the document is a function of the register and
    the tree, both of which this module fixes.
    """
    text = out.decode("utf-8")
    return re.sub(r"^Target: `.*`$", "Target: `<TARGET>`", text, flags=re.M).encode("utf-8")


def test_b8_the_markdown_surface_is_byte_identical_to_the_prechange_render(
        target: pathlib.Path, tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior 8, measured DIRECTLY rather than through the repo-root pin.

    `test_b8_b9_...` reads the committed pin constant, which proves only that nobody
    edited it.  This runs the markdown surface itself over a tree and register this
    module owns and compares it byte for byte with what HEAD's implementation emitted
    for the same inputs (`PRECHANGE_FIXTURE_MARKDOWN`).  The register here contains
    three records whose `applies_when` fails, so if the new clause had leaked onto the
    human surface -- the thing the spec's `## Out of Scope` forbids -- these bytes move.
    """
    gaps = _register(tmp_path, PRECHANGE_FIXTURE_RULES)
    argv = ("scan", str(target), "--gaps", str(gaps))
    code, out, err = _run(argv, monkeypatch)
    assert code == 0, f"markdown scan exited {code}; stderr={err!r}"
    assert err == "", f"markdown scan wrote to stderr: {err!r}"
    text = out.decode("utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n"), (
        "the markdown document does not end in exactly one newline")
    assert PREFIX not in text, (
        "the NOT_APPLICABLE clause reached the MARKDOWN surface, which behavior 8 "
        "freezes and the spec's Out of Scope forbids")
    norm = _normalised_markdown(out)
    got = (len(norm), hashlib.sha256(norm).hexdigest())
    assert got == PRECHANGE_FIXTURE_MARKDOWN, (
        f"the markdown render moved: pre-change {PRECHANGE_FIXTURE_MARKDOWN}, now {got}")


def test_b1_b5_every_live_not_applicable_finding_is_one_clean_witness_line(
        repo_scan: dict[str, object]) -> None:
    """Behaviors 1 and 5 on the REAL target, on the parts only a live scan can show.

    Behavior 1's `locations == []` / `question == ""` clauses were asserted on fixtures
    only; here they are asserted on all 61 live NOT_APPLICABLE findings -- inventing a
    location beside a non-match is what the spec's Out of Scope rules out.  The rest is
    the quality bar for a machine surface a gate reads: one line, no tab, no doubled or
    edge whitespace, ASCII, and no absolute machine path from the scanning host (this is
    a PUBLIC repo, and the rules are authored globs, never resolved paths).
    """
    na = [f for f in repo_scan["findings"] if f["verdict"] == "NOT_APPLICABLE"]
    assert na, "the repo-root scan produced no NOT_APPLICABLE findings to measure"
    dirty: list[tuple[str, str]] = []
    for finding in na:
        reason = finding["reason"]
        gap_id = finding["gap_id"]
        assert finding["locations"] == [], (
            f"{gap_id} is NOT_APPLICABLE and cites {finding['locations']!r}: the rule "
            "did not match, so there is no matched line to cite")
        assert finding["question"] == "", f"{gap_id} carries question {finding['question']!r}"
        if ("\n" in reason or "\t" in reason or "  " in reason
                or reason != reason.strip() or not reason.isascii()):
            dirty.append((gap_id, reason))
        assert "/Users/" not in reason and "/home/" not in reason, (
            f"{gap_id}'s reason carries an absolute host path: {reason!r}")
    assert dirty == [], (
        "NOT_APPLICABLE reasons are not single clean ASCII lines: "
        + "; ".join(f"{g}: {r!r}" for g, r in dirty[:3]))
