"""Iteration 28 behaviors: every rule shape the research contract documents must LOAD.

Iteration 28's payload is one document. `research/CANDIDATE_CONTRACT.md` is the ENTIRE
spec handed to a context-free research agent, and it published a `not` shape the loader
refuses, so an author who followed it was rejected at the first gate with a message
contradicting the document it was told to obey. The fix is a corrected clause plus the
file's first fenced example of every combinator, and the brake is a ROUND-TRIP: pull every
rule object out of the file's ` ```json ` fences and push each one through the same
`Gap` validation the ingest door runs.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source (`src/`, `tools/`), the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`,
or any diff. `research/CANDIDATE_CONTRACT.md` and `PRODUCT.md` are read as DATA -- they are
the artifacts under test, not implementations -- and every verdict about a rule shape is
produced by CALLING `models.Gap.model_validate`. Every expectation comes from `pm.md`'s
Expected Behaviors.

Structural notes, so this file cannot lie later:

* **Behavior 3 is a DERIVED EQUALITY, not a count.** The kind set extracted from the
  document's fences is asserted EQUAL to `models.RULE_KINDS`, a constant no test referenced
  before this iteration. A floor ("at least 7 kinds") would freeze today's vocabulary; the
  equality reds the document when a kind is ADDED to the loader and stays silent when a
  sentence is legitimately reworded. Iteration 16's census over this same file passed a
  "7 of 7 rule kinds" claim and was RIGHT -- every documented kind NAME does exist -- so a
  name check is structurally unable to see a wrong KEY. This file therefore asserts the
  kinds of EXTRACTED FENCE OBJECTS, never of prose names.
* **The extractor is proved two-sided before it is trusted.** A plain ` ``` ` fence must be
  IGNORED (the document carries one: the self-verify command) and a ` ```json ` fence must
  be found, so the reader cannot silently examine zero fences and report health. Behavior 2
  additionally counts opening fence LINES independently of the regex and asserts the two
  measurements EQUAL, which is the leg that reds when the extractor is blind to a fence a
  human reader can see -- `len(parsed) == len(fences)` cannot fail, since one derives from
  the other.
* **Behaviors 6-7's controls are synthetic `tmp_path` documents** in the
  `test_iter22_behavior.py:358-381` idiom, and each fixture ASSERTS ITS OWN PREMISE: the
  deficient sample is checked to really carry a `not` object keyed `rules` before its
  REJECTED verdict is believed, so a control that decayed into a copy of the good fixture
  fails loudly instead of passing while measuring nothing.
* **Behavior 1's prose matcher is deliberately NARROW and its narrowness is on purpose.**
  The spec's Out of Scope forbids pinning the CORRECTED sentence (a wording matcher reds a
  correct suite on a legitimate rewording), so only the exact false clause's ABSENCE is
  asserted, over whitespace-normalised text. That is fail-open against a reworded
  falsehood, by design: the fenced round-trip above is the normative, machine-checked
  statement, and this is a cheap regression guard against the one wording that shipped.
  A proximity matcher was rejected as fail-CLOSED -- the CORRECT clause necessarily says
  "not a `rules` list", so `not` and `rules` are adjacent in the fixed document too.
* **This module spells the false clause in its own control sample.** Behavior 1's domain is
  `research/CANDIDATE_CONTRACT.md` ONLY. If a future iteration widens that domain to
  `tests/`, this sample is the first false hit -- move it to a fixture file, never
  "fix" it silently.
* **Behavior 8's HEAD comparison is NOT asserted here.** "byte-identical to HEAD" is
  measured once, out of band, in the tester's report: HEAD moves when this iteration lands,
  which makes a suite-level version either vacuous or red on every future iteration. What
  IS durable is asserted instead -- the five verbs are deterministic across two calls, each
  document ends in exactly ONE newline, and each exit code is pinned.
* **No absolute machine path and no personal identifier appears here**; every path is
  derived from `__file__` and every fixture lives under pytest's `tmp_path`.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from pydantic import ValidationError

from agent_gap_radar import models
from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

#: The artifacts under test, found relative to this file so no machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "research" / "CANDIDATE_CONTRACT.md"
ROADMAP = REPO_ROOT / "PRODUCT.md"

#: A ` ```json ` fence at column 0. A plain ` ``` ` fence must NOT match: the document
#: carries one (the self-verify command) and it is not JSON.
JSON_FENCE_RE = re.compile(r"^```json[^\S\n]*\n(.*?)^```[^\S\n]*$", re.M | re.S)

#: Behavior 1: the false clause as `pm.md` quotes it, whitespace-normalised.
FALSE_COMBINATOR_CLAUSE = (
    "the combinators `any_of` / `all_of` / `not` (each takes `rules`)"
)

#: Behavior 6's leaf, used inside every synthetic combinator sample.
LEAF_RULE = {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "run_stage\\("}


# --------------------------------------------------------------------------- helpers


def _normalise_ws(text: str) -> str:
    """Collapse every whitespace run to one space, so a line-wrap cannot hide a clause."""
    return re.sub(r"\s+", " ", text)


def _json_fences(text: str) -> list[str]:
    """Every ` ```json ` fence body in a markdown document, in document order."""
    return JSON_FENCE_RE.findall(text)


def _parsed_fences(text: str) -> list[object]:
    """Parse every json fence. Raises `json.JSONDecodeError` naming the fence index."""
    out = []
    for i, body in enumerate(_json_fences(text)):
        try:
            out.append(json.loads(body))
        except json.JSONDecodeError as exc:  # pragma: no cover - only on a red document
            raise AssertionError(
                f"json fence #{i} does not parse: {exc}\n----\n{body}\n----"
            ) from exc
    return out


def _rule_objects(node, out=None) -> list[dict]:
    """Every object carrying a string `kind`, recursively, through dicts and lists."""
    if out is None:
        out = []
    if isinstance(node, dict):
        if isinstance(node.get("kind"), str):
            out.append(node)
        for value in node.values():
            _rule_objects(value, out)
    elif isinstance(node, list):
        for value in node:
            _rule_objects(value, out)
    return out


def _documented_rules(text: str) -> list[dict]:
    """Every rule object in every json fence of a candidate-contract document."""
    out: list[dict] = []
    for doc in _parsed_fences(text):
        _rule_objects(doc, out)
    return out


def _vocabulary_report(text: str) -> tuple[list[dict], set[str], list[str], list[str]]:
    """(rule objects, their kinds, kinds the loader accepts but the doc omits, unknown)."""
    rules = _documented_rules(text)
    kinds = {r["kind"] for r in rules}
    missing = sorted(set(models.RULE_KINDS) - kinds)
    unknown = sorted(kinds - set(models.RULE_KINDS))
    return rules, kinds, missing, unknown


def _vocabulary_failure(text: str) -> str | None:
    """The behavior-3 failure message, or None when the equality holds."""
    rules, kinds, missing, unknown = _vocabulary_report(text)
    if not rules:
        return "no rule object could be extracted from any json fence (vacuous)"
    if missing or unknown:
        return (
            f"documented kinds {sorted(kinds)} != loader kinds "
            f"{sorted(models.RULE_KINDS)}; missing kinds: {missing}; "
            f"kinds the loader does not accept: {unknown}"
        )
    return None


def _host_record(rule: dict) -> dict:
    """An otherwise-valid record whose check hangs `rule` off `present_when`.

    Synthetic on purpose: a live register record would couple this brake to whichever
    record happens to sit first in the directory, and a manual-only record has no
    `fixtures`, so injecting any `present_when` would be refused for an unrelated reason.
    """
    return {
        "id": "GAP-901",
        "title": "synthetic host for a documented rule shape",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "status": "open",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [
            {
                "source_class": "first-party-field",
                "title": "t",
                "locator": "https://example.invalid/x",
                "date": "2026-01-02",
                "quote": "a verbatim excerpt of six or more words",
            }
        ],
        "check": {
            "id": "CHK-901",
            "present_when": rule,
            "rationale": "why this signature indicates the gap",
            "fixtures": {
                "bad": {"app/agent.py": "code exhibiting the gap\n"},
                "good": {"app/agent.py": "the same code with the mitigation\n"},
            },
        },
    }


def _load_verdict(rule: dict) -> tuple[bool, str]:
    """(ACCEPTED?, detail) for one rule object, through the real loader."""
    try:
        Gap.model_validate(_host_record(rule))
    except ValidationError as exc:
        # A pydantic message is NOT on the last line -- the last line is a docs URL.
        return False, "; ".join(e["msg"] for e in exc.errors())
    return True, "accepted"


def _synthetic_contract(tmp_path: pathlib.Path, name: str, rule: dict) -> pathlib.Path:
    """A minimal candidate-contract document whose single json fence carries `rule`."""
    path = tmp_path / name
    path.write_text(
        "# Candidate contract\n\n"
        "## Rule kinds available to a check\n\n"
        "```json\n" + json.dumps({"present_when": rule}, indent=2) + "\n```\n",
        encoding="utf-8",
    )
    return path


# ------------------------------------------------------- behavior 2: fences parse


def test_extractor_is_two_sided_before_it_is_trusted():
    """Control: a plain fence is ignored, a json fence is found."""
    plain = "text\n\n```\ncd repo && python3 tools/promote.py\n```\n"
    assert _json_fences(plain) == [], "a plain fence must not be read as JSON"
    tagged = 'text\n\n```json\n{"kind": "file_exists", "globs": ["**/x"]}\n```\n'
    assert len(_json_fences(tagged)) == 1, tagged
    assert _rule_objects(json.loads(_json_fences(tagged)[0]))[0]["kind"] == "file_exists"
    assert _documented_rules(plain) == [], "a doc with no json fence yields no rules"


def test_contract_has_json_fences_and_all_of_them_parse():
    """Behavior 2: at least one ` ```json ` fence, and every one of them is JSON."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert len(text) > 500, f"contract looks empty: {len(text)} bytes"
    fences = _json_fences(text)
    assert fences, "the contract carries no ```json fence at all"
    parsed = _parsed_fences(text)  # raises AssertionError naming the fence on bad JSON
    assert len(parsed) == len(fences), f"{len(fences)} fences, {len(parsed)} parsed"
    # A SECOND, INDEPENDENT measurement of the same quantity. The line above is trivially
    # true (one list derives from the other); this one is not. Count opening fence LINES,
    # accepting indentation, and assert the regex read exactly as many -- so the brake reds
    # precisely when it is BLIND to a fence a human reader can see (an indented json block,
    # or one whose closing fence is not at column 0), instead of quietly examining a subset
    # and reporting health over it.
    opened = [ln for ln in text.splitlines() if ln.lstrip().startswith("```json")]
    assert len(opened) == len(fences), (
        f"{len(opened)} opening json fence line(s) in the document but the extractor read "
        f"{len(fences)}: a fence the reader can see is invisible to this brake"
    )


# ------------------------------------- behaviors 3+5: derived vocabulary equality


def test_documented_kinds_equal_the_loader_vocabulary():
    """Behaviors 3 and 5: the extracted kind set EQUALS `models.RULE_KINDS`, non-vacuously."""
    text = CONTRACT.read_text(encoding="utf-8")
    rules, kinds, missing, unknown = _vocabulary_report(text)
    # Behavior 5 first, so a vacuous extraction names its own cause.
    assert rules, (
        "zero rule objects extracted from the contract's json fences -- the vocabulary "
        "equality would pass vacuously, so this fails instead"
    )
    assert kinds == set(models.RULE_KINDS), _vocabulary_failure(text)
    assert not missing and not unknown, _vocabulary_failure(text)


def test_vocabulary_reader_names_the_missing_kinds(tmp_path):
    """Behavior 7, control: a one-kind document FAILS the equality, by name."""
    doc = _synthetic_contract(tmp_path, "one-kind.md", LEAF_RULE)
    text = doc.read_text(encoding="utf-8")
    rules, kinds, missing, unknown = _vocabulary_report(text)
    # The fixture asserts its own premise: it really does exemplify exactly one kind.
    assert kinds == {"content_matches"}, kinds
    assert len(rules) == 1, rules
    message = _vocabulary_failure(text)
    assert message is not None, "a one-kind document must fail the equality"
    for kind in set(models.RULE_KINDS) - {"content_matches"}:
        assert kind in message, f"failure message never names missing kind {kind}: {message}"
    assert unknown == [], unknown
    assert sorted(missing) == sorted(set(models.RULE_KINDS) - {"content_matches"})


# ------------------------------------- behavior 4: every documented rule LOADS


def test_every_documented_rule_object_loads():
    """Behavior 4: each extracted rule is ACCEPTED as a check's `present_when`."""
    text = CONTRACT.read_text(encoding="utf-8")
    rules = _documented_rules(text)
    assert rules, "no rule object extracted -- see behavior 5"
    verdicts = [(r.get("kind"), *_load_verdict(r)) for r in rules]
    refused = [(k, d) for k, ok, d in verdicts if not ok]
    census = f"examined {len(rules)} rule object(s) across {len(_json_fences(text))} fence(s)"
    print(f"[behavior 4] {census}: {len(rules) - len(refused)} accepted, {len(refused)} refused")
    assert not refused, f"{census}; the loader REFUSES documented shapes: {refused}"
    # The census must participate in the VERDICT, not only in the failure text: this repo
    # runs pytest with -q, so the stdout of a PASSING test is dropped and a print alone
    # reports nothing on a green run. The floor is DERIVED, never pinned at todays 12 --
    # one rule object carries exactly one kind, so exemplifying every kind the loader
    # accepts needs at least that many objects.
    assert len(rules) >= len(models.RULE_KINDS), (
        f"{census}: fewer rule objects than the loader has kinds "
        f"({len(models.RULE_KINDS)}), so the vocabulary equality cannot hold non-vacuously"
    )


# ----------------------------- behavior 6: two-sided control on the `not` shape


def test_not_with_a_rules_list_is_reported_rejected(tmp_path):
    """Behavior 6, deficient half: the shape the document used to publish is REFUSED."""
    doc = _synthetic_contract(tmp_path, "deficient.md", {"kind": "not", "rules": [LEAF_RULE]})
    rules = _documented_rules(doc.read_text(encoding="utf-8"))
    # Premise of the fixture, asserted rather than assumed: it carries a `not` keyed `rules`.
    tops = [r for r in rules if r["kind"] == "not"]
    assert len(tops) == 1, rules
    assert "rules" in tops[0] and "rule" not in tops[0], tops[0]
    ok, detail = _load_verdict(tops[0])
    assert not ok, "the documented-but-wrong `not`+`rules` shape must be REJECTED"
    assert "rule" in detail, detail


def test_not_with_a_single_rule_object_is_reported_accepted(tmp_path):
    """Behavior 6, sufficient half: the corrected shape is ACCEPTED."""
    doc = _synthetic_contract(tmp_path, "sufficient.md", {"kind": "not", "rule": LEAF_RULE})
    rules = _documented_rules(doc.read_text(encoding="utf-8"))
    tops = [r for r in rules if r["kind"] == "not"]
    assert len(tops) == 1, rules
    assert "rule" in tops[0] and "rules" not in tops[0], tops[0]
    ok, detail = _load_verdict(tops[0])
    assert ok, f"the corrected `not`+`rule` shape must be ACCEPTED, got: {detail}"


def test_combinator_key_discipline_is_not_symmetric():
    """Behavior 6, extended: `any_of` refuses `rule`, so the keys are not interchangeable."""
    ok, _ = _load_verdict({"kind": "any_of", "rules": [LEAF_RULE]})
    assert ok, "`any_of` with a `rules` list must load"
    ok, detail = _load_verdict({"kind": "any_of", "rule": LEAF_RULE})
    assert not ok, "`any_of` with a single `rule` must be refused"
    assert "rules" in detail, detail


# ------------------------------------------------- behavior 1: the false clause


def test_false_combinator_clause_matcher_is_two_sided():
    """Behavior 1, control: the matcher fires on the shipped falsehood, not on the fix."""
    # The FIRST sample is the wrap the falsehood actually shipped with, copied from the
    # pre-fix revision of the document rather than retyped; the SECOND wraps at a different
    # point, which is what proves the whitespace normalisation and not luck is doing the
    # work. A matcher that only saw one wrap would be one reflow away from fail-open.
    shipped_falsehood = (
        "`file_exists` / `file_absent` (`globs`), and the combinators `any_of` / `all_of` /\n"
        "`not` (each takes `rules`). Nesting depth is capped at 8. An unknown kind raises\n"
    )
    other_wrap = (
        "`file_exists` / `file_absent` (`globs`), and the combinators `any_of` /\n"
        "`all_of` / `not` (each takes `rules`). Nesting depth is capped at 8.\n"
    )
    for sample in (shipped_falsehood, other_wrap):
        assert FALSE_COMBINATOR_CLAUSE in _normalise_ws(sample), (
            "the matcher cannot see the clause it exists to forbid at this line wrap:\n"
            + sample
        )
    corrected = (
        "the combinators `any_of` / `all_of`\n(each takes a non-empty `rules` list) and "
        "`not` (which takes a single `rule`\nobject, not a `rules` list).\n"
    )
    assert FALSE_COMBINATOR_CLAUSE not in _normalise_ws(corrected), (
        "the matcher fires on the CORRECTED clause -- it would red a green document"
    )


def test_false_combinator_clause_is_gone():
    """Behavior 1: the clause claiming all three combinators take `rules` is absent."""
    text = _normalise_ws(CONTRACT.read_text(encoding="utf-8"))
    assert FALSE_COMBINATOR_CLAUSE not in text, (
        "the research contract again publishes a `not` shape the loader refuses: "
        f"{FALSE_COMBINATOR_CLAUSE!r}"
    )


# --------------------------------------- behavior 8: determinism and exit codes


VERBS = (
    ("validate", ["validate", str(REPO_ROOT)]),
    ("list", ["list", str(REPO_ROOT)]),
    ("report", ["report", str(REPO_ROOT)]),
    ("scan", ["scan", str(REPO_ROOT)]),
    ("scan --json", ["scan", str(REPO_ROOT), "--json"]),
)


@pytest.mark.parametrize("name,argv", VERBS, ids=[v[0] for v in VERBS])
def test_verb_is_deterministic_and_ends_in_one_newline(name, argv, capsys):
    """Behavior 8, the durable half: same bytes twice, exit 0, exactly one trailing newline."""
    first_code = main(list(argv))
    first = capsys.readouterr()
    second_code = main(list(argv))
    second = capsys.readouterr()
    assert first_code == 0, f"{name} exited {first_code}; stderr={first.err!r}"
    assert second_code == first_code, f"{name}: {first_code} then {second_code}"
    assert first.err == "", f"{name} wrote to stderr: {first.err!r}"
    assert first.out == second.out, f"{name} is not byte-stable across two runs"
    assert first.out.endswith("\n"), f"{name} does not end in a newline"
    assert not first.out.endswith("\n\n"), f"{name} ends in more than one newline"
    # Anti-vacuity WITHOUT pinning today's byte count: a verb printing nothing would be
    # trivially "deterministic", but a floor pinned at the current size reds on any
    # legitimate register growth. Non-blank is the floor; the json verb must also parse.
    assert first.out.strip(), f"{name} produced only whitespace"
    if "--json" in argv:
        payload = json.loads(first.out)
        assert payload, f"{name} emitted an empty JSON document"


# --------------------------------------------------- behavior 9: roadmap ledger


def test_roadmap_records_this_iteration():
    """Behavior 9: row 38 reads `shipped` and the Done ledger carries an `- iter 28 ` row."""
    text = ROADMAP.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| 38 |")]
    assert len(rows) == 1, f"expected exactly one roadmap row 38, found {len(rows)}"
    cells = [c.strip() for c in rows[0].split("|")]
    assert "shipped" in cells, f"row 38 is not shipped: {cells[3][:80]!r}"
    ledger = [ln for ln in text.splitlines() if ln.startswith("- iter 28 ")]
    assert len(ledger) == 1, f"expected one `- iter 28 ` ledger row, found {len(ledger)}"
