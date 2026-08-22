"""Iteration 68 behaviors: the prd payload publishes its story list under `stories`, and
the emitted top-level key set becomes a published surface guarded by a DERIVED brake.

The flagship verb's hand-off failed on the name of one key: the one declared consumer's
reader accepts a bare array or an object whose `stories` value is a list, so the old
wrapper name made a present, well-formed document read as zero stories. This iteration
renames that one key and publishes the complete emitted key set in
`docs/CONSUMER_CONTRACT.md`, with a test that DERIVES the expected set from the emitter's
own bytes so the document cannot decay away from the payload.

Black-box, and the ISOLATION CONTRACT IS HONORED. Every expectation below comes from
`pm.md`'s Expected Behaviors and from the committed `docs/CONSUMER_CONTRACT.md`; every
claim is measured by CALLING the public CLI entry point `agent_gap_radar.cli.main` and
reading observable stdout / stderr / exit code, or by reading a committed document AS
DATA. Nothing here reads the implementation source, the engineer's or the reviewer's
notes, `IMPLEMENTATION.patch`, or any diff. The only imports are the stdlib, pytest and
the CLI entry point -- behavior 5 asks for the consumer shape to be asserted offline
without importing anything outside this repo, and this module imports nothing else.

Structural notes, so this file cannot lie later:

* **The retired wrapper name is never spelled as one literal token.** `RETIRED_KEY` is
  built by concatenation, so this module cannot become a hit for a future census over
  tracked bytes for the key this iteration retires -- the trap `test_iter21_behavior.py`
  already records for censused literals.
* **Behavior 7's brake is scoped to the ENUMERATION paragraph, not to the whole section.**
  Measured on the committed document: `stories` occurs in three separate code spans in
  that section, so a whole-section set collector EQUALS the emitted key set today and
  would still equal it after `stories` was deleted from the published list -- fail-open in
  the deletion direction for exactly the key that matters. the test named
  `..._whole_section_scope_is_fail_open_which_is_why_the_brake_is_scoped` pins that
  weakness as a measured fact, so nobody widens the scope back.
* **Both directions are proved on the REAL artifact as well as in memory.** The spec asks
  for two-sided controls over in-memory documents (the `test_iter22_behavior.py` idiom,
  where each key appears exactly once); those PASS while the whole-section collector is
  blind on the committed file, which is the rules-verified / domain-unverified split.
  So the same brake is also run over MUTATED COPIES of the committed section text.
* **Key sets are compared to each other, never to a hand-copied list, wherever the spec
  says EQUAL.** Behavior 4 compares the two prd surfaces to each other; behavior 7
  compares the document to the emitter. Only behavior 1's ORDER and behavior 3's four
  sibling VALUES are pinned as literals, because an order and a byte-identity claim have
  nothing else to be derived from.
* **No absolute machine path and no personal identifier appears here.** Synthetic
  registers and targets live under pytest's `tmp_path`; the two tests that read the live
  register or the committed contract resolve them from this file's own location and guard
  against a vacuous domain first.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = REPO_ROOT / "docs" / "CONSUMER_CONTRACT.md"

#: The live record behaviors 1-3 name. Its stories are register DATA, so every assertion
#: that a new record could falsify is driven from a synthetic register instead.
LIVE_GAP = "GAP-003"

#: Behavior 1: the complete emitted top-level keys, in emitted order.
EMITTED_ORDER = ("project", "branchName", "description", "sourceGap", "stories")

#: Behavior 2: the story keys, and the ids for the live gap.
STORY_KEYS = ("id", "title", "description", "acceptanceCriteria", "priority", "passes",
              "notes")
STORY_IDS = ("US-001", "US-002", "US-003")

#: The retired wrapper name. Built by concatenation ON PURPOSE -- see the module docstring.
RETIRED_KEY = "user" + "Stories"

#: Behavior 3's byte-identity pins for the live gap, measured by running the tool. A
#: black-box test cannot observe pre-iteration bytes; these make the claim enforceable
#: from here on, and the ambiguity is reported as PM feedback in `tester.md`.
PINNED_SIBLINGS = {
    "project": "agent-gap-radar",
    "branchName": "ralph/no-checkpoint-first-contract-for-steps-running-u",
    "description": (
        "GAP-003 -- No checkpoint-first contract for steps running under a hard "
        "wall-clock cap. My agent step is killed by a timeout I did not configure, and "
        "because it was still composing its answer when it died, hours of correct work "
        "score as zero."
    ),
}

#: Planted in the synthetic target so its check fires PRESENT; a property of this file's
#: fixtures and never of the committed register.
MARKER = "GAPMARK68"


# --------------------------------------------------------------------------- helpers


def _run(argv, capsys):
    """Call the CLI and return `(code, stdout, stderr)`; argparse refusals included."""
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _check(cid, pattern=MARKER):
    """Fires PRESENT iff `pattern` appears in the target's python files."""
    return {
        "id": cid,
        "rationale": "why this check exists",
        "manual_question": "does the loop do this?",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"],
                         "pattern": pattern},
        "fixtures": {"bad": {"a.py": pattern + "\n"}, "good": {"a.py": "clean\n"}},
    }


def _record(gid, check_id="CHK-680", pattern=MARKER):
    """A schema-valid record whose evidence clears the confidence floor."""
    return {
        "id": gid, "title": f"title of {gid}", "layer": "orchestration",
        "gap_type": "missing-contract", "problem": "p", "symptom": "s", "why_now": "w",
        "severity": 5, "frequency": 3, "tractability": 5,
        "evidence": [{"source_class": "first-party-field", "title": "t",
                      "locator": "https://example.invalid/0",
                      "date": "2026-01-02", "quote": "the verbatim line"}],
        "check": _check(check_id, pattern),
    }


def _write_register(root, records):
    d = root / "gaps"
    d.mkdir(parents=True)
    for rec in records:
        (d / f"{rec['id']}.json").write_text(json.dumps(rec), encoding="utf-8")
    return root


def _target(root, body=MARKER):
    t = root / "target"
    (t / "app").mkdir(parents=True)
    (t / "app" / "loop.py").write_text(body + "\n", encoding="utf-8")
    return t


def _live_prd(capsys, gap=LIVE_GAP):
    """`radar prd . --gap <gap>` over the committed register: code, stdout, stderr."""
    return _run(["prd", str(REPO_ROOT), "--gap", gap], capsys)


def _doc(out):
    """Parse an emitted document, failing loudly rather than raising bare."""
    assert out, "the tool emitted no document at all"
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:  # pragma: no cover - a red suite explains itself
        raise AssertionError(f"emitted document is not JSON: {exc}\n{out[:400]}") from exc


# --------------------------------------------------------------------------- section reader


def _sections(text):
    """`[(heading, body)]` for every `##`-or-deeper heading, in document order."""
    heads = [(m.start(), m.end(), m.group(0))
             for m in re.finditer(r"(?m)^#{2,}[ \t]+.*$", text)]
    out = []
    for i, (start, end, heading) in enumerate(heads):
        stop = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        out.append((heading, text[end:stop]))
    return out


#: The section anchor. A hand-written anchor for the SECTION is unavoidable -- something
#: must say WHICH section is the contract -- but no key name appears in it, so the brake
#: below cannot be satisfied by the way this file locates the prose.
SECTION_ANCHOR = "prd payload"


def _prd_section(text):
    """The heading and body of the published-key-set section, or fail loudly."""
    hits = [(h, b) for h, b in _sections(text) if SECTION_ANCHOR in h.lower()]
    assert len(hits) == 1, (
        f"expected exactly one section whose heading names {SECTION_ANCHOR!r}, "
        f"found {len(hits)}: {[h for h, _ in hits]}")
    return hits[0]


def _code_spans(chunk):
    """Every inline code span in `chunk`."""
    return re.findall(r"`([^`\n]+)`", chunk)


def _code_idents(chunk):
    """The DISTINCT code spans that are a single bare identifier -- i.e. key names."""
    return {s for s in _code_spans(chunk) if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", s)}


def _paragraphs(chunk):
    return [p for p in re.split(r"\n[ \t]*\n", chunk) if p.strip()]


def _published_keys(section_body):
    """Behavior 7's collector: the key names published by the ENUMERATION paragraph.

    Derived, with no hand-copied key list: of the section's paragraphs, the one carrying
    the most distinct identifier code spans IS the enumeration -- a published list of N
    keys names more of them in one place than any sentence discussing one of them.
    """
    paras = _paragraphs(section_body)
    assert paras, "the section has no paragraphs"
    best, best_n = None, -1
    for p in paras:
        n = len(_code_idents(p))
        if n > best_n:
            best, best_n = p, n
    return _code_idents(best), best


def _all_key_names(node, acc=None):
    """Every key name anywhere in a parsed document, at any depth."""
    acc = set() if acc is None else acc
    if isinstance(node, dict):
        for k, v in node.items():
            acc.add(k)
            _all_key_names(v, acc)
    elif isinstance(node, list):
        for v in node:
            _all_key_names(v, acc)
    return acc


# ---------------------------------------------------------------------------
# Behavior 1 -- the emitted top-level keys, in order, and the retired name is gone.
# ---------------------------------------------------------------------------

def test_b1_top_level_keys_are_exactly_the_five_in_emitted_order(capsys):
    code, out, err = _live_prd(capsys)
    assert (code, err) == (0, ""), f"code={code} stderr={err!r}"
    assert tuple(_doc(out).keys()) == EMITTED_ORDER


def test_b1_the_retired_wrapper_name_occurs_nowhere_in_the_document(capsys):
    _, out, _ = _live_prd(capsys)
    assert RETIRED_KEY not in out, (
        f"the retired wrapper name still occurs in the emitted bytes: "
        f"{out[max(0, out.find(RETIRED_KEY) - 60):out.find(RETIRED_KEY) + 60]!r}")
    # Two-sided: the assertion above is only meaningful if this matcher CAN fire.
    assert RETIRED_KEY in json.dumps({RETIRED_KEY: []}), "the absence matcher is dead"


def test_b1_holds_over_a_synthetic_register_too(tmp_path, capsys):
    """A register-data change must not be able to hide the key set."""
    reg = _write_register(tmp_path / "reg", [_record("GAP-680")])
    code, out, err = _run(["prd", str(reg), "--gap", "GAP-680"], capsys)
    assert (code, err) == (0, ""), f"code={code} stderr={err!r}"
    assert tuple(_doc(out).keys()) == EMITTED_ORDER
    assert RETIRED_KEY not in out


# ---------------------------------------------------------------------------
# Behavior 2 -- the `stories` value is the ordered story array, unchanged.
# ---------------------------------------------------------------------------

def test_b2_stories_is_the_ordered_story_array_with_every_pass_flag_false(capsys):
    _, out, _ = _live_prd(capsys)
    stories = _doc(out)["stories"]
    assert isinstance(stories, list), f"stories is {type(stories).__name__}, not a list"
    assert [s["id"] for s in stories] == list(STORY_IDS)
    for s in stories:
        assert tuple(s.keys()) == STORY_KEYS, f"{s.get('id')}: {tuple(s.keys())}"
        assert s["passes"] is False, f"{s['id']}: passes is {s['passes']!r}"


def test_b2_the_pass_flags_are_json_false_in_the_bytes(capsys):
    """`false`, not the string `"false"` and not `0` -- the consumer reads JSON booleans."""
    _, out, _ = _live_prd(capsys)
    doc = _doc(out)
    assert out.count('"passes": false') == len(doc["stories"]), out
    assert '"passes": true' not in out
    assert '"passes": "false"' not in out


# ---------------------------------------------------------------------------
# Behavior 3 -- nothing else about the payload moves.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(PINNED_SIBLINGS))
def test_b3_the_sibling_values_are_byte_identical_to_their_pins(capsys, key):
    _, out, _ = _live_prd(capsys)
    assert _doc(out)[key] == PINNED_SIBLINGS[key]


def test_b3_source_gap_still_carries_the_record_it_was_asked_for(capsys):
    _, out, _ = _live_prd(capsys)
    source = _doc(out)["sourceGap"]
    assert isinstance(source, dict) and source["id"] == LIVE_GAP


def test_b3_the_document_ends_in_exactly_one_newline_with_exit_0_and_no_stderr(capsys):
    code, out, err = _live_prd(capsys)
    assert code == 0
    assert err == ""
    assert out.endswith("\n") and not out.endswith("\n\n")


# ---------------------------------------------------------------------------
# Behavior 4 -- the two prd surfaces carry the SAME top-level key set.
# ---------------------------------------------------------------------------

def test_b4_scan_prd_emits_the_same_top_level_key_set_as_prd(tmp_path, capsys):
    """Synthetic register and target, so the equality cannot depend on live data."""
    reg = _write_register(tmp_path / "reg", [_record("GAP-681")])
    hit = _target(tmp_path / "hit")
    code_p, out_p, err_p = _run(["prd", str(reg), "--gap", "GAP-681"], capsys)
    assert (code_p, err_p) == (0, ""), f"prd: code={code_p} stderr={err_p!r}"
    code_s, out_s, err_s = _run(["scan", str(hit), "--gaps", str(reg), "--prd"], capsys)
    assert (code_s, err_s) == (0, ""), f"scan --prd: code={code_s} stderr={err_s!r}"
    keys_p, keys_s = set(_doc(out_p)), set(_doc(out_s))
    assert keys_p == keys_s, f"prd {sorted(keys_p)} != scan --prd {sorted(keys_s)}"
    # Named, so the equality above cannot be satisfied by two identically-wrong surfaces.
    assert keys_s == set(EMITTED_ORDER)
    assert RETIRED_KEY not in out_s
    assert out_s.endswith("\n") and not out_s.endswith("\n\n")


def test_b4_holds_on_the_live_surfaces_too(capsys):
    _, out_p, _ = _live_prd(capsys)
    code_s, out_s, err_s = _run(["scan", str(REPO_ROOT), "--prd"], capsys)
    assert (code_s, err_s) == (0, ""), f"scan --prd: code={code_s} stderr={err_s!r}"
    assert set(_doc(out_s)) == set(_doc(out_p))


# ---------------------------------------------------------------------------
# Behavior 5 -- the document satisfies the shape the declared consumer parses.
# ---------------------------------------------------------------------------

def test_b5_the_document_satisfies_the_consumer_shape_offline(capsys):
    """The consumer's reader: an object whose `stories` value is a list of story objects."""
    _, out, _ = _live_prd(capsys)
    doc = _doc(out)
    assert isinstance(doc, dict)
    stories = doc["stories"]
    assert isinstance(stories, list) and stories, "the story list is empty"
    assert all(isinstance(s, dict) for s in stories)
    assert sum(1 for s in stories if s.get("passes")) == 0, "a story is already passing"
    assert [s["id"] for s in stories] == list(STORY_IDS)


# ---------------------------------------------------------------------------
# Behaviors 1, 2, 3 and 5 -- proved TWO-SIDED against the PRE-ITERATION payload shape.
#
# A black-box stage cannot re-run the old emitter, so the old shape is reconstructed from
# the CURRENT emitted document by renaming the one wrapper key back. Everything else about
# the document is therefore identical by construction, which is what makes the control
# fair: if these assertions still passed on that document, they would be testing nothing
# this iteration changed.
# ---------------------------------------------------------------------------

#: The pre-iteration document's size in bytes, as MEASURED AND RECORDED BY `pm.md` for this
#: same invocation ("Measured this iteration against the real reader, on live bytes (3693
#: B)"). It is the one historical witness a black-box stage has, and it turns behavior 3
#: into a single number: a rename of this one key and nothing else must shrink the document
#: by exactly `len(retired) - len(new)` bytes.
PRE_ITERATION_BYTES = 3693


def _old_shape(doc):
    """The same document with the story list back under the retired wrapper name."""
    return {(RETIRED_KEY if k == "stories" else k): v for k, v in doc.items()}


def _consumer_reads(doc):
    """The declared consumer's reader, reimplemented offline: `(valid, ids_of_pending)`.

    Accepts a bare array, or an object whose `stories` value is a list. Nothing outside
    this repo is imported; this is the semantics `pm.md` measured against the real reader.
    """
    stories = doc if isinstance(doc, list) else None
    if stories is None and isinstance(doc, dict):
        candidate = doc.get("stories")
        if isinstance(candidate, list):
            stories = candidate
    if stories is None or not all(isinstance(s, dict) for s in stories):
        return False, ()
    return True, tuple(s.get("id") for s in stories if not s.get("passes"))


def test_control_the_pre_iteration_shape_fails_behavior_1(capsys):
    _, out, _ = _live_prd(capsys)
    old = _old_shape(_doc(out))
    assert tuple(old.keys()) != EMITTED_ORDER, "behavior 1's order check is vacuous"
    assert RETIRED_KEY in json.dumps(old), "the absence matcher of behavior 1 is dead"


def test_control_the_pre_iteration_shape_fails_behavior_2_and_5(capsys):
    _, out, _ = _live_prd(capsys)
    old = _old_shape(_doc(out))
    assert "stories" not in old, "premise: the control really moved the story list"
    with pytest.raises(KeyError):
        old["stories"]


def test_control_the_consumer_reader_answers_differently_on_the_two_shapes(capsys):
    """The whole point of the iteration, asserted offline on both shapes.

    `pm.md` measured the real reader returning `valid=False, total=0` before and
    `valid=True, total=3, pending=('US-001','US-002','US-003')` after. This reimplements
    those semantics and asserts both sides, so the iteration's claim is falsifiable here.
    """
    _, out, _ = _live_prd(capsys)
    doc = _doc(out)
    valid_new, pending_new = _consumer_reads(doc)
    assert (valid_new, pending_new) == (True, STORY_IDS), (valid_new, pending_new)
    valid_old, pending_old = _consumer_reads(_old_shape(doc))
    assert (valid_old, pending_old) == (False, ()), (
        "control: the reader must NOT have accepted the retired shape, or the rename "
        "changed nothing that matters")


def test_b3_the_document_is_exactly_the_rename_shorter_than_the_recorded_pre_bytes(capsys):
    """Behavior 3 as ONE number: a 4-byte shrink is only consistent with the one literal.

    Stronger than a field-by-field diff, which proves only the fields it lists: this
    covers keys and values nobody thought to check. If a future iteration legitimately
    changes the payload's SIZE, this pin is the thing to update -- deliberately, and with
    the new size measured, not deleted.
    """
    _, out, _ = _live_prd(capsys)
    delta = len(RETIRED_KEY) - len("stories")
    assert delta == 4, "premise: the rename removes exactly four bytes"
    assert len(out) == PRE_ITERATION_BYTES - delta, (
        f"emitted {len(out)} bytes; expected {PRE_ITERATION_BYTES - delta} "
        f"(the pre-iteration {PRE_ITERATION_BYTES} recorded in the spec, less the rename). "
        "Either another byte moved with the rename, or the register data changed.")


# ---------------------------------------------------------------------------
# Behavior 6 -- the contract publishes the key set, names no key the payload lacks,
# and its heading spells no verb inside a code span.
# ---------------------------------------------------------------------------

def _contract_text():
    text = CONTRACT.read_text(encoding="utf-8")
    assert len(text) > 500, f"contract looks empty: {len(text)} bytes"
    return text


def test_b6_the_section_names_every_emitted_key_in_a_code_span(capsys):
    _, out, _ = _live_prd(capsys)
    emitted = set(_doc(out))
    _, body = _prd_section(_contract_text())
    missing = emitted - _code_idents(body)
    assert not missing, f"the contract section never backticks: {sorted(missing)}"


def test_b6_the_section_names_no_identifier_the_payload_does_not_carry(capsys):
    """Derived from the payload at every depth, so `passes` may legitimately be named."""
    _, out, _ = _live_prd(capsys)
    carried = _all_key_names(_doc(out))
    _, body = _prd_section(_contract_text())
    stray = _code_idents(body) - carried
    assert not stray, f"the section names keys the payload does not carry: {sorted(stray)}"
    assert RETIRED_KEY not in _code_idents(body)


def test_b6_the_section_heading_spells_no_verb_inside_a_code_span():
    heading, _ = _prd_section(_contract_text())
    for span in _code_spans(heading):
        assert not re.search(r"\bradar\s+\w+", span), (
            f"the heading names a verb in a code span, which arms the iteration-16 "
            f"verb-heading brake: {span!r}")


# ---------------------------------------------------------------------------
# Behavior 7 -- the brake DERIVES the expected set from the emitter's own bytes.
# ---------------------------------------------------------------------------

def test_b7_published_key_set_equals_the_set_the_emitter_emits(capsys):
    _, out, _ = _live_prd(capsys)
    emitted = set(_doc(out))
    _, body = _prd_section(_contract_text())
    published, para = _published_keys(body)
    assert published == emitted, (
        f"published {sorted(published)} != emitted {sorted(emitted)}\n"
        f"enumeration paragraph:\n{para}")


#: Behavior 7's in-memory controls, in the `tests/test_iter22_behavior.py:358` idiom: a
#: planted document per direction, read through the SAME collector the real assertion uses.
#: Each key appears exactly once here, which is precisely why they cannot see the
#: whole-section fail-open the committed file exhibits -- hence the mutation tests below.
_SUFFICIENT_SECTION = (
    "## The prd payload -- the keys, published\n"
    "\n"
    "One JSON object, and these are the complete top-level keys, in emitted order:\n"
    "`project`, `branchName`, `description`, `sourceGap`, `stories`.\n"
    "\n"
    "This list is the contract and not a summary of it.\n"
)
_MISSING_ONE = _SUFFICIENT_SECTION.replace(", `sourceGap`", "")
_EXTRA_ONE = _SUFFICIENT_SECTION.replace("`stories`.", "`stories`, `notAnEmittedKey`.")


def _published_from_whole_doc(text):
    _, body = _prd_section(text)
    return _published_keys(body)[0]


def test_b7_the_collector_is_two_sided_over_in_memory_documents():
    assert _published_from_whole_doc(_SUFFICIENT_SECTION) == set(EMITTED_ORDER)
    assert _published_from_whole_doc(_MISSING_ONE) != set(EMITTED_ORDER), (
        "a section missing one key must FAIL the brake")
    assert _published_from_whole_doc(_EXTRA_ONE) != set(EMITTED_ORDER), (
        "a section naming a key the emitter does not emit must FAIL the brake")


def test_b7_the_collector_is_two_sided_over_the_committed_artifact(capsys):
    """The controls above are built where each key appears once; the real file is not."""
    _, out, _ = _live_prd(capsys)
    emitted = set(_doc(out))
    text = _contract_text()
    heading, body = _prd_section(text)
    published, para = _published_keys(body)
    assert published == emitted

    # Deletion direction, on the real prose: drop one key from the enumeration paragraph.
    for key in sorted(emitted):
        wounded = text.replace(para, para.replace(f"`{key}`", key, 1), 1)
        assert wounded != text, f"could not plant the deletion for {key}"
        assert _published_from_whole_doc(wounded) != emitted, (
            f"un-backticking `{key}` in the published list did NOT red the brake")

    # Addition direction, on the real prose.
    grown = text.replace(para, para.replace("`stories`", "`stories`, `notAnEmittedKey`", 1), 1)
    assert grown != text
    assert _published_from_whole_doc(grown) != emitted


def test_b7_whole_section_scope_is_fail_open_which_is_why_the_brake_is_scoped(capsys):
    """Pinned as a FACT: a whole-section collector cannot see `stories` deleted.

    On the committed document `stories` appears in more than one code span in this
    section, so a set collected over the whole section equals the emitted set even after
    the published list stops naming it. That is why `_published_keys` is scoped to the
    enumeration paragraph. If this test ever fails because the prose changed, the brake
    is still correct -- but do not widen its scope on the strength of the coincidence.
    """
    _, out, _ = _live_prd(capsys)
    emitted = set(_doc(out))
    text = _contract_text()
    _, body = _prd_section(text)
    assert _code_idents(body) == emitted, "premise: the section names exactly the key set"
    assert len([s for s in _code_spans(body) if s == "stories"]) > 1, (
        "premise: `stories` is discussed elsewhere in the section")

    _, para = _published_keys(body)
    wounded_body = body.replace(para, para.replace("`stories`", "stories", 1), 1)
    assert _published_keys(wounded_body)[0] != emitted, "the scoped brake must catch it"
    assert _code_idents(wounded_body) == emitted, (
        "a whole-section collector was expected to be blind to this deletion")


# ---------------------------------------------------------------------------
# Behavior 8 -- the error path is unchanged.
# ---------------------------------------------------------------------------

def test_b8_an_unknown_gap_still_exits_2_with_a_prefixed_error_and_no_stdout(capsys):
    code, out, err = _live_prd(capsys, gap="GAP-999")
    assert code == 2, f"code={code}"
    assert out == "", f"stdout must be empty on the error path: {out[:200]!r}"
    assert err.startswith("Error: "), f"stderr must be prefixed: {err!r}"
    assert err.endswith("\n")
