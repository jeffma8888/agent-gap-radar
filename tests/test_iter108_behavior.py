r"""Iteration 108 behaviours: `radar show` publishes each record's `Check.rationale`
verbatim as the LAST bullet of `## Detection`, and the schema refuses a rationale that
cannot render as one bullet.

WHAT THIS ITERATION CLAIMS, IN BEHAVIOURAL TERMS
`Check.rationale` is the largest authored field in the register that no surface read. This
iteration gives it exactly one publication point: a `- Rationale: <value>` bullet closing
the `## Detection` block of `radar show`, verbatim and untruncated, DISPLAYED as
`- Rationale: none recorded` when the field is empty, absent when the record has no check
at all, and guarded at LOAD time so a value that cannot be one bullet (a value holding a
line break, or a value differing from its stripped form) is refused with exit 2.

ISOLATION. This module honours the tester's isolation contract. It reads `pm.md`, this
repo's `tests/` conventions, and the PUBLISHED artifacts under `gaps/` (data, not code),
and it observes the product only by IMPORTING its public names and RUNNING its CLI. It
does not read `src/`, the engineer's or the reviewer's notes, any patch, or any diff.

WHY EACH BEHAVIOUR IS PAIRED WITH A CONTROL, AND WHICH RIVAL RULE THE PAIR KILLS

* B1's expectation is built from the JSON ON DISK, never from the model object, so a
  renderer that publishes a normalised or re-wrapped copy of the field cannot pass by
  agreeing with itself. The verbatim claim is measured where it can actually break: 118
  of the 119 live rationales are longer than 120 characters and the longest is 1206, so a
  wrap or an ellipsis at any conventional width reds `test_b1_...verbatim...`. The
  non-vacuity guard asserts the domain is the whole checked register, not a lucky subset.

* B2's "existing bullets keep their order and text" is measured DIFFERENTIALLY: the same
  published record is rendered twice into synthetic registers differing ONLY in the
  rationale value, and every line of the document except the rationale bullet itself is
  required to be byte-identical. A same-shape assertion on one render cannot distinguish
  an additive bullet from a renderer that also reflowed its neighbours; this one can.

* B3 pins the DISPLAY rule against the silent-drop rival, in both of its shapes -- the
  empty string and the absent key -- because `Out of Scope` forbids making the field
  required, so absence must render, not raise.

* B3 also pins the SPEC CONTRADICTION rather than choosing quietly. Behaviour 3 says a
  whitespace-only rationale renders `none recorded`; behaviour 6 says a value differing
  from its stripped form is refused at load. A whitespace-only value satisfies both
  antecedents, so no implementation can honour both sentences. Measured, the product
  refuses it (behaviour 6 wins, the only self-consistent reading, since a refused record
  cannot reach a renderer). `test_b3_whitespace_only_is_refused_which_contradicts_b3`
  records that verdict IN CODE so a later iteration that implements behaviour 3 literally
  reds here instead of silently reopening the guard.

* B4 uses the live checkless record as its subject and a checked record as its CONTROL in
  the same test, so "no Rationale bullet" cannot pass by being true of every record.

* B5's byte-stability is measured ACROSS PROCESSES under differing `PYTHONHASHSEED`,
  because a set-ordered or dict-ordered publication step is invisible to a same-process
  double call: string hashing is seeded per interpreter run.

* B5's "appears in no other section or verb" census is LABEL-EXACT (`- Rationale: ` at
  line start), never a word search, because the word is ordinary English: GAP-116 quotes a
  paper that says `agent rationales`, so a case-insensitive `in` census reports TWO
  occurrences on a CORRECT document. `test_b5_a_naive_word_census_would_false_positive`
  pins that trap so a later simplification to `doc.count("rationale")` reds instead of
  silently inverting the rule.

* B6 is asserted at every verb that LOADS the register, not only at `show`, because that
  is the difference between a load-time guard and a render-time one; and the accepted
  single-line value is run through the same fixture as a control, so a refusal cannot be
  credited to a broken synthetic register.

TWO DELIBERATE NON-ASSERTIONS, NAMED SO A LATER ITERATION DOES NOT "FIX" THEM
1. The exact wording of the guard's error message is NOT pinned. The quality bar fixes the
   CONTRACT (one `Error: ` line, exit 2, clean stdout) and this module asserts that;
   pinning the sentence would make a legitimate rewording red.
2. `radar diff` is not exercised. `Out of Scope` explicitly excludes it, and its inputs are
   two register states, so any assertion here would be about the diff verb's own feature.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from agent_gap_radar import cli, registry

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"

#: The published records, read as DATA. `raw` is the JSON on disk, so every expectation in
#: this module is built from the authored bytes rather than from a parsed model.
RAW_RECORDS = {
    payload["id"]: payload
    for payload in (
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(GAPS_DIR.glob("*.json"))
    )
}
CHECKED_IDS = tuple(
    sorted(gap_id for gap_id, raw in RAW_RECORDS.items() if raw.get("check") is not None)
)
CHECKLESS_IDS = tuple(
    sorted(gap_id for gap_id, raw in RAW_RECORDS.items() if raw.get("check") is None)
)

DETECTION_HEADING = "## Detection"
RATIONALE_PREFIX = "- Rationale: "
EMPTY_RATIONALE_LINE = "- Rationale: none recorded"
ERROR_PREFIX = "Error: "


def run(argv):
    """Drive the CLI in-process, returning `(exit_code, stdout, stderr)`.

    A parser refusal is surfaced as an assertion failure rather than a `SystemExit`
    escaping the test, so an argv shape this module got wrong cannot read as a product bug.
    """
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([str(token) for token in argv])
    except SystemExit as exc:  # argparse refused an argv shape
        raise AssertionError(
            f"{argv} was refused by the parser (exit {exc.code}); stderr={err.getvalue()!r}"
        ) from exc
    return code, out.getvalue(), err.getvalue()


def show(gap_id, root=REPO_ROOT):
    """`radar show <id> <root>` as a document, gated on the producer being healthy."""
    code, out, err = run(["show", gap_id, str(root)])
    assert code == 0, f"show {gap_id} exited {code}; stderr={err!r}"
    assert err == "", f"show {gap_id} wrote to stderr: {err!r}"
    return out


def detection_block(document):
    """The `## Detection` block: heading through the line before the next `## ` heading,
    with trailing blank lines removed so "last line" means the last CONTENT line."""
    lines = document.splitlines()
    assert lines.count(DETECTION_HEADING) == 1, "the block heading must occur exactly once"
    start = lines.index(DETECTION_HEADING)
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## "):
        end += 1
    block = lines[start:end]
    while block and block[-1] == "":
        block.pop()
    return block


def bullets(block):
    return [line for line in block if line.startswith("- ")]


def synthetic_register(root, rationale, source_id="GAP-020", omit=False):
    """A one-record register cloned from a PUBLISHED record, with `rationale` replaced.

    Cloning keeps this module from restating the record schema (which would be pinning the
    implementation's shape) while letting each case control exactly one field.
    """
    payload = json.loads(json.dumps(RAW_RECORDS[source_id]))
    assert payload.get("check") is not None, "the fixture source must carry a check"
    if omit:
        payload["check"].pop("rationale", None)
    else:
        payload["check"]["rationale"] = rationale
    gaps = pathlib.Path(root) / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    (gaps / f"{payload['id']}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload["id"]


# ---------------------------------------------------------------------------
# Behavior 1 -- every checked record renders `- Rationale: <value verbatim>`
# ---------------------------------------------------------------------------


def test_b1_the_domain_is_the_whole_checked_register_so_b1_is_not_vacuous():
    assert len(RAW_RECORDS) >= 120, "the live register shrank; re-derive this module's domain"
    assert len(CHECKED_IDS) == len(RAW_RECORDS) - len(CHECKLESS_IDS)
    assert len(CHECKED_IDS) >= 119, f"only {len(CHECKED_IDS)} checked records"
    assert CHECKLESS_IDS, "no checkless record on disk, so behaviour 4 would be vacuous"
    for gap_id in CHECKED_IDS:
        assert RAW_RECORDS[gap_id]["check"].get("rationale", "").strip(), (
            f"{gap_id} has an empty rationale on disk; behaviour 1's live domain assumed "
            "every checked record authors one"
        )


def test_b1_every_checked_record_publishes_its_rationale_inside_detection():
    for gap_id in CHECKED_IDS:
        expected = RATIONALE_PREFIX + RAW_RECORDS[gap_id]["check"]["rationale"]
        block = detection_block(show(gap_id))
        assert expected in block, (gap_id, block[-1] if block else block)


def test_b1_the_published_bullet_is_verbatim_and_untruncated():
    """No wrap, no reflow, no ellipsis: the bullet's tail IS the authored bytes.

    Discriminating by construction -- 118 of the live rationales exceed 120 characters and
    the longest is over 1200, so any conventional wrap or truncation reds here.
    """
    longest = 0
    for gap_id in CHECKED_IDS:
        authored = RAW_RECORDS[gap_id]["check"]["rationale"]
        longest = max(longest, len(authored))
        line = [ln for ln in detection_block(show(gap_id)) if ln.startswith(RATIONALE_PREFIX)]
        assert len(line) == 1, (gap_id, line)
        published = line[0][len(RATIONALE_PREFIX) :]
        assert published == authored, gap_id
        assert "\u2026" not in published and "..." not in published[-4:], (gap_id, published[-40:])
    assert longest > 400, f"longest live rationale is only {longest} chars; wrap test is weak"


def test_b1_the_bullet_appears_exactly_once_in_the_whole_document():
    for gap_id in CHECKED_IDS:
        document = show(gap_id)
        assert sum(1 for ln in document.splitlines() if ln.startswith(RATIONALE_PREFIX)) == 1, gap_id


# ---------------------------------------------------------------------------
# Behavior 2 -- LAST line of the block; the existing bullets keep order and text
# ---------------------------------------------------------------------------


def test_b2_the_rationale_bullet_is_the_last_line_of_the_detection_block():
    for gap_id in CHECKED_IDS:
        block = detection_block(show(gap_id))
        expected = RATIONALE_PREFIX + RAW_RECORDS[gap_id]["check"]["rationale"]
        assert block[-1] == expected, (gap_id, block[-1][:120])
        assert bullets(block)[-1] == expected, gap_id


def test_b2_the_preceding_bullets_are_the_ones_the_record_declares():
    """Order is asserted positionally: `- Check:` opens the block, `- Rules declared:`
    (when the record declares rules) precedes the rationale, and nothing follows it."""
    for gap_id in CHECKED_IDS:
        block = detection_block(show(gap_id))
        items = bullets(block)
        assert len(items) >= 3, (gap_id, items)
        assert items[0].startswith("- Check: `"), (gap_id, items[0])
        rationale_at = [i for i, ln in enumerate(items) if ln.startswith(RATIONALE_PREFIX)]
        assert rationale_at == [len(items) - 1], (gap_id, rationale_at, len(items))
        declares_rules = any(
            key in RAW_RECORDS[gap_id]["check"]
            for key in ("applies_when", "present_when", "mitigated_when")
        )
        rules_bullets = [i for i, ln in enumerate(items) if ln.startswith("- Rules declared:")]
        if declares_rules:
            assert rules_bullets and rules_bullets[0] < len(items) - 1, (gap_id, items)
        else:
            assert not rules_bullets, (gap_id, items)


def test_b2_the_bullet_is_purely_additive_every_other_byte_is_unmoved(tmp_path):
    """Differential control: two renders of ONE record differing only in the rationale.

    Every line except the rationale bullet must be byte-identical. This is what
    distinguishes an appended bullet from a renderer that also re-wrapped its neighbours;
    a shape assertion on a single render cannot tell those apart.
    """
    short = synthetic_register(tmp_path / "a", "a one-line sentinel")
    long_value = "b " * 400 + "tail"
    other = synthetic_register(tmp_path / "b", long_value.strip())
    assert short == other
    doc_a, doc_b = show(short, tmp_path / "a"), show(other, tmp_path / "b")
    lines_a, lines_b = doc_a.splitlines(), doc_b.splitlines()
    assert len(lines_a) == len(lines_b), "the rationale value changed the LINE COUNT"
    differing = [i for i, (x, y) in enumerate(zip(lines_a, lines_b)) if x != y]
    assert len(differing) == 1, [(lines_a[i][:60], lines_b[i][:60]) for i in differing]
    assert lines_a[differing[0]].startswith(RATIONALE_PREFIX)
    assert lines_b[differing[0]] == RATIONALE_PREFIX + long_value.strip()


def test_b2_the_empty_case_also_leaves_every_other_byte_unmoved(tmp_path):
    """The `none recorded` substitute is a value swap, not a different code path."""
    kept = synthetic_register(tmp_path / "kept", "a one-line sentinel")
    blank = synthetic_register(tmp_path / "blank", "")
    doc_a, doc_b = show(kept, tmp_path / "kept"), show(blank, tmp_path / "blank")
    lines_a, lines_b = doc_a.splitlines(), doc_b.splitlines()
    assert len(lines_a) == len(lines_b)
    differing = [i for i, (x, y) in enumerate(zip(lines_a, lines_b)) if x != y]
    assert len(differing) == 1, differing
    assert lines_b[differing[0]] == EMPTY_RATIONALE_LINE


# ---------------------------------------------------------------------------
# Behavior 3 -- the empty case is DISPLAYED, never omitted
# ---------------------------------------------------------------------------


def test_b3_an_empty_rationale_renders_none_recorded_as_the_last_bullet(tmp_path):
    gap_id = synthetic_register(tmp_path, "")
    block = detection_block(show(gap_id, tmp_path))
    assert block[-1] == EMPTY_RATIONALE_LINE, block[-3:]
    assert bullets(block)[-1] == EMPTY_RATIONALE_LINE


def test_b3_an_absent_rationale_key_is_displayed_too_not_an_error(tmp_path):
    """`Out of Scope` forbids making the field required, so absence must RENDER."""
    gap_id = synthetic_register(tmp_path, None, omit=True)
    code, out, err = run(["show", gap_id, str(tmp_path)])
    assert (code, err) == (0, ""), (code, err)
    assert detection_block(out)[-1] == EMPTY_RATIONALE_LINE


def test_b3_whitespace_only_is_refused_which_contradicts_b3_and_honours_b6(tmp_path):
    """PM FEEDBACK PINNED IN CODE: behaviours 3 and 6 disagree on this input.

    B3 says a whitespace-only rationale renders `none recorded`; B6 says a value differing
    from its stripped form is refused at load. Both antecedents fire, so the spec is
    unsatisfiable as written. The product refuses -- the only self-consistent reading,
    since a record refused at load never reaches a renderer. Asserted so that implementing
    B3 literally (which would reopen the guard) reds here rather than passing silently.
    """
    for index, value in enumerate((" ", "   ", "\t", "\n", " \t ")):
        root = tmp_path / f"ws{index}"
        gap_id = synthetic_register(root, value)
        code, out, err = run(["show", gap_id, str(root)])
        assert code == 2, (repr(value), code, out[:80])
        assert out == "", (repr(value), out[:80])
        assert err.startswith(ERROR_PREFIX) and len(err.splitlines()) == 1, (repr(value), err)


# ---------------------------------------------------------------------------
# Behavior 4 -- a record with NO check renders the block as today
# ---------------------------------------------------------------------------


def test_b4_the_checkless_record_publishes_no_rationale_bullet_and_a_checked_one_does():
    """Subject and control in one test, so "absent" cannot pass by being absent everywhere."""
    for gap_id in CHECKLESS_IDS:
        document = show(gap_id)
        assert RATIONALE_PREFIX not in document, gap_id
        block = detection_block(document)
        items = bullets(block)
        assert len(items) == 2, (gap_id, items)
        assert items[0].startswith("- Check: none declared"), (gap_id, items[0])
        assert not any(ln.startswith(RATIONALE_PREFIX) for ln in items), gap_id
    control = show(CHECKED_IDS[0])
    assert RATIONALE_PREFIX in control, "the control record must publish the bullet"


def test_b4_the_checkless_block_is_byte_stable_and_carries_no_placeholder():
    for gap_id in CHECKLESS_IDS:
        block = detection_block(show(gap_id))
        assert block == detection_block(show(gap_id)), gap_id
        joined = "\n".join(block)
        assert "Rationale" not in joined, (gap_id, joined[:200])
        assert "none recorded" not in joined, (gap_id, joined[:200])


# ---------------------------------------------------------------------------
# Behavior 5 -- one trailing newline, byte-stable, rc 0, clean stderr, one home
# ---------------------------------------------------------------------------


def test_b5_show_ends_in_exactly_one_newline_with_rc0_and_clean_stderr():
    for gap_id in sorted(RAW_RECORDS):
        code, out, err = run(["show", gap_id, str(REPO_ROOT)])
        assert (code, err) == (0, ""), (gap_id, code, err)
        assert out.endswith("\n") and not out.endswith("\n\n"), (gap_id, repr(out[-8:]))


def test_b5_the_document_is_byte_stable_across_processes_and_hash_seeds():
    """Two subprocesses under different `PYTHONHASHSEED` must emit identical bytes.

    A same-process double call cannot see a set-ordered publication step: string hashing is
    seeded once per interpreter run.
    """
    gap_id = CHECKED_IDS[0]
    outputs = []
    for seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-m", "agent_gap_radar.cli", "show", gap_id, str(REPO_ROOT)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        if proc.returncode != 0 and not proc.stdout:
            pytest.skip(f"module entry point unavailable: {proc.stderr.strip()[:120]}")
        outputs.append(proc.stdout)
    assert len(set(outputs)) == 1, "the document moved with PYTHONHASHSEED"
    assert outputs[0] == show(gap_id), "the subprocess and in-process documents differ"
    assert RATIONALE_PREFIX in outputs[0]


def test_b5_the_label_appears_in_exactly_one_section_of_show():
    for gap_id in CHECKED_IDS:
        document = show(gap_id)
        lines = document.splitlines()
        hits = [i for i, ln in enumerate(lines) if ln.startswith(RATIONALE_PREFIX)]
        assert len(hits) == 1, (gap_id, hits)
        start = lines.index(DETECTION_HEADING)
        end = start + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1
        assert start < hits[0] < end, (gap_id, hits, start, end)


def test_b5_a_naive_word_census_would_false_positive():
    """The trap this module's LABEL-EXACT census avoids, pinned so it cannot be simplified.

    GAP-116 quotes a paper containing `agent rationales`, so a case-insensitive word census
    reports TWO occurrences on a CORRECT document. A later rewrite to
    `doc.lower().count("rationale") == 1` reds here instead of inverting the rule quietly.
    """
    trap = [
        gap_id
        for gap_id in CHECKED_IDS
        if show(gap_id).lower().count("rationale") != 1
    ]
    assert trap, "no live record exercises the word-census trap any more; keep LABEL-EXACT anyway"
    for gap_id in trap:
        document = show(gap_id)
        assert sum(1 for ln in document.splitlines() if ln.startswith(RATIONALE_PREFIX)) == 1, gap_id


def test_b5_no_other_verb_publishes_the_rationale(tmp_path):
    root = str(REPO_ROOT)
    argvs = [
        ["validate", root],
        ["list", root],
        ["report", root],
        ["taxonomy"],
        ["prd", "--gap", CHECKED_IDS[0], root],
        ["scan", "--json", "--gaps", str(GAPS_DIR), str(tmp_path)],
        ["scan", "--gaps", str(GAPS_DIR), str(tmp_path)],
    ]
    for argv in argvs:
        code, out, err = run(argv)
        assert code == 0, (argv, code, err[:200])
        assert RATIONALE_PREFIX not in out, argv
        assert '"rationale"' not in out, (argv, "a machine payload gained the field")
        assert "rationale" not in out.lower(), (argv, "unexpected mention outside show")


# ---------------------------------------------------------------------------
# Behavior 6 -- a rationale that cannot be one bullet is REFUSED at load
# ---------------------------------------------------------------------------

#: Values that must be refused. The first group cannot be ONE line; the second differs from
#: its stripped form. `\u2028`/`\u2029` are here because `str.splitlines()` treats them as
#: breaks while `"\n" in value` does not see them at all.
REFUSED_VALUES = (
    "a\nb",
    "a\r\nb",
    "a\rb",
    "a\x0bb",
    "a\x0cb",
    "a\u2028b",
    "a\u2029b",
    "trailing newline\n",
    " leading space",
    "trailing space ",
    "\tleading tab",
    "trailing tab\t",
)

#: Every verb that LOADS the register. The guard is a LOAD guard, so all of these must
#: refuse; if only `show` refused, the guard would be living in the renderer.
LOADING_VERBS = ("validate", "list", "report")


@pytest.mark.parametrize("value", REFUSED_VALUES, ids=lambda v: repr(v))
def test_b6_a_rationale_that_cannot_be_one_bullet_is_refused_by_show(tmp_path, value):
    gap_id = synthetic_register(tmp_path, value)
    code, out, err = run(["show", gap_id, str(tmp_path)])
    assert code == 2, (repr(value), code)
    assert out == "", (repr(value), out[:120])
    assert err.startswith(ERROR_PREFIX), (repr(value), err[:120])
    assert len(err.splitlines()) == 1, (repr(value), err)
    assert err.endswith("\n") and not err.endswith("\n\n"), repr(err[-6:])


@pytest.mark.parametrize("verb", LOADING_VERBS)
def test_b6_the_refusal_is_at_load_so_every_register_reading_verb_refuses(tmp_path, verb):
    synthetic_register(tmp_path, "two\nlines")
    code, out, err = run([verb, str(tmp_path)])
    assert code == 2, (verb, code, out[:120])
    assert out == "", (verb, out[:120])
    assert err.startswith(ERROR_PREFIX) and len(err.splitlines()) == 1, (verb, err)


def test_b6_the_control_a_single_line_stripped_value_is_accepted_everywhere(tmp_path):
    """Without this, every refusal above could be credited to a broken fixture."""
    gap_id = synthetic_register(tmp_path, "one stripped line with punctuation: fine.")
    for verb in LOADING_VERBS:
        code, out, err = run([verb, str(tmp_path)])
        assert (code, err) == (0, ""), (verb, code, err[:200])
    document = show(gap_id, tmp_path)
    assert detection_block(document)[-1] == (
        RATIONALE_PREFIX + "one stripped line with punctuation: fine."
    )


def test_b6_the_guard_starts_green_on_the_live_register():
    """The acceptance criterion, asserted directly: no authored rationale trips the guard."""
    code, out, err = run(["validate", str(REPO_ROOT)])
    assert (code, err) == (0, ""), (code, err[:300])
    for gap_id in CHECKED_IDS:
        authored = RAW_RECORDS[gap_id]["check"]["rationale"]
        assert authored == authored.strip(), gap_id
        assert len(authored.splitlines()) == 1, gap_id


def test_b6_an_interior_run_of_spaces_is_NOT_a_refusal(tmp_path):
    """The guard is about the ENDS and about line breaks, not about internal whitespace."""
    value = "an  interior   double space is authored prose, not a shape defect"
    gap_id = synthetic_register(tmp_path, value)
    code, out, err = run(["show", gap_id, str(tmp_path)])
    assert (code, err) == (0, ""), (code, err[:200])
    assert detection_block(out)[-1] == RATIONALE_PREFIX + value


# ===========================================================================
# EXTENSIONS -- tester-retry round.
#
# The previous round was cut short by the stage cap; its module is KEPT above and every claim
# in it was RE-MEASURED here before anything was added. These are the holes it left. Each
# expectation below was measured against the built product BEFORE it was written down, and each
# names the rival rule it kills.
# ===========================================================================

#: Every verb the CLI advertises. Behaviour 5's claim ("`Rationale` appears in no other section
#: or verb") is only meaningful over a CLOSED set, and the previous round censused a HAND-PICKED
#: seven, leaving `diff` unasserted. This tuple is checked against `--help` below, so a ninth
#: verb landing later cannot silently escape the census.
ALL_VERBS = ("validate", "list", "report", "show", "prd", "scan", "diff", "taxonomy")

#: Every verb that LOADS a register. Measured: all six refuse a mis-shaped rationale, which is
#: what makes the guard a LOAD guard rather than a renderer check. `taxonomy` reads no register
#: and `show` is covered by its own case above.
REGISTER_READING_VERBS = ("validate", "list", "report", "prd", "scan", "diff")


def cli_help(argv):
    """`--help` output, tolerating the `SystemExit` argparse raises on a help request.

    The module's `run()` deliberately converts `SystemExit` into an assertion failure, so a
    help request needs its own driver rather than a weakening of that guard.
    """
    out, err = io.StringIO(), io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main([str(token) for token in argv])
    except SystemExit as exc:
        code = exc.code
    return code, out.getvalue(), err.getvalue()


def test_x_the_verb_census_is_closed_over_the_advertised_surface():
    """A census over a hand-written verb list is unfalsifiable once the list goes stale.

    This pins the list to what the product advertises, so a new verb forces a decision here
    instead of quietly inheriting an unmeasured exemption from behaviour 5.
    """
    code, out, err = cli_help(["--help"])
    assert code == 0, (code, err[:200])
    groups = re.findall(r"\{([a-z,]+)\}", out)
    assert groups, out[:400]
    advertised = tuple(sorted(groups[0].split(",")))
    assert advertised == tuple(sorted(ALL_VERBS)), (advertised, tuple(sorted(ALL_VERBS)))


def test_x_diff_publishes_no_rationale_in_either_shape(tmp_path):
    """The 8th verb, left unasserted by the previous round, closing the behaviour-5 census.

    `Out of Scope` forbids CHANGING `diff`, which is precisely why the census belongs here: it
    pins that diff stayed SILENT without asserting anything about what diff chooses to report.
    The two states differ in nothing but the rationale, and its value carries a sentinel word
    that appears nowhere else, so a leak of the VALUE (not just the label) also reds.
    """
    old, new = tmp_path / "old", tmp_path / "new"
    synthetic_register(old, "old zzsentinelzz value for the diff census")
    synthetic_register(new, "new zzsentinelzz value for the diff census")
    for extra in ([], ["--json"]):
        code, out, err = run(["diff", str(old), str(new)] + extra)
        assert (code, err) == (0, ""), (extra, code, err[:200])
        assert RATIONALE_PREFIX not in out, extra
        assert "rationale" not in out.lower(), (extra, "diff leaked the field label")
        assert "zzsentinelzz" not in out, (extra, "diff published a rationale VALUE")


def test_x_the_scan_census_holds_on_a_target_where_checks_actually_fire():
    """The previous round censused `scan` against an EMPTY tmp dir, where a check can only
    report absence and the document stays tiny. Pointed at this repo the scan produces a large
    document with real findings -- the only version of this census that could catch a leak.
    """
    for extra in ([], ["--json"]):
        code, out, err = run(["scan"] + extra + ["--gaps", str(GAPS_DIR), str(REPO_ROOT)])
        assert code == 0, (extra, code, err[:300])
        assert len(out) > 5000, (extra, len(out), "scan document too small to be a real census")
        assert RATIONALE_PREFIX not in out, extra
        assert '"rationale"' not in out, (extra, "a machine payload gained the field")
        assert "rationale" not in out.lower(), extra


#: Values hostile to a markdown renderer, plus a length beyond the live domain and a non-ASCII
#: run. The contract is VERBATIM, so a renderer that escapes, fences, wraps or transliterates
#: any of these reds. Written with `\u` escapes so this source file stays pure ASCII.
HOSTILE_VALUES = (
    ("backticks", "uses `importlib.reload` and `sys.modules` directly"),
    ("leading_dash", "- looks like a bullet in its own right"),
    ("markdown_punct", "a | b | c and #hash and *stars* and _under_ and 1. ordered"),
    ("links_and_html", "a [link](https://example.invalid/x) and <html> and & ampersand"),
    ("quotes", "a colon: and \"double\" and 'single' quotes"),
    ("non_ascii", "caf\u00e9 na\u00efve \u4e2d\u6587 \u2014 em dash \u00b5 micro"),
)


@pytest.mark.parametrize(
    ("label", "value"), HOSTILE_VALUES, ids=[label for label, _ in HOSTILE_VALUES]
)
def test_x_a_render_hostile_value_is_published_verbatim(tmp_path, label, value):
    """The live register authors plain prose, so it cannot discriminate a renderer that escapes.

    Measured: all six are published byte-identically, which is what "verbatim" has to mean.
    """
    gap_id = synthetic_register(tmp_path, value)
    code, out, err = run(["show", gap_id, str(tmp_path)])
    assert (code, err) == (0, ""), (label, code, err[:200])
    block = detection_block(out)
    assert block[-1] == RATIONALE_PREFIX + value, (label, block[-1][:160])
    assert out.endswith("\n") and not out.endswith("\n\n"), (label, repr(out[-8:]))


def test_x_a_value_longer_than_any_live_rationale_is_still_untruncated(tmp_path):
    """The live domain tops out near 1.2k characters, so it cannot catch a truncation at 4k.

    This puts the ceiling four times past the longest authored value and asserts the published
    LENGTH, not just a prefix match, so a silent tail-drop cannot pass.
    """
    live_max = max(len(RAW_RECORDS[gap_id]["check"]["rationale"]) for gap_id in CHECKED_IDS)
    assert live_max > 400, f"live max is only {live_max}; re-derive this ceiling"
    value = "w" * (live_max * 4)
    gap_id = synthetic_register(tmp_path, value)
    block = detection_block(show(gap_id, tmp_path))
    published = block[-1][len(RATIONALE_PREFIX) :]
    assert len(published) == len(value), (len(published), len(value), "the tail was dropped")
    assert published == value
    assert len(block) == len(detection_block(show(gap_id, tmp_path))), "render is not stable"


def test_x_an_explicit_json_null_is_refused_while_the_absent_key_renders(tmp_path):
    """THE DISCRIMINATING PAIR, asserted in one test because either half alone reads as correct.

    A naive `rationale: str | None = None` schema would accept an explicit `null` and render
    `none recorded` for BOTH shapes. Measured, the product separates them: the ABSENT key is
    accepted and displayed (behaviour 3 -- `Out of Scope` forbids making the field required),
    while an explicit `null` is REFUSED (behaviour 6 -- it cannot render as one bullet).
    """
    absent_root = tmp_path / "absent"
    absent = synthetic_register(absent_root, None, omit=True)
    code, out, err = run(["show", absent, str(absent_root)])
    assert (code, err) == (0, ""), (code, err[:200])
    assert detection_block(out)[-1] == EMPTY_RATIONALE_LINE, detection_block(out)[-3:]

    null_root = tmp_path / "null"
    explicit = synthetic_register(null_root, None)
    code, out, err = run(["show", explicit, str(null_root)])
    assert code == 2, (code, out[:160])
    assert out == "", out[:160]
    assert err.startswith(ERROR_PREFIX) and len(err.splitlines()) == 1, err


#: Non-string JSON values. None of these can be one bullet either, and pydantic's lax coercion
#: would happily publish `5` as `"5"` -- a rationale nobody authored.
NON_STRING_VALUES = (
    ("int", 5),
    ("float", 1.5),
    ("bool", True),
    ("list", ["a", "b"]),
    ("dict", {"a": 1}),
)


@pytest.mark.parametrize(
    ("label", "value"), NON_STRING_VALUES, ids=[label for label, _ in NON_STRING_VALUES]
)
def test_x_a_non_string_rationale_is_refused_with_the_error_contract(tmp_path, label, value):
    gap_id = synthetic_register(tmp_path, value)
    code, out, err = run(["show", gap_id, str(tmp_path)])
    assert code == 2, (label, code, out[:160])
    assert out == "", (label, out[:160])
    assert err.startswith(ERROR_PREFIX) and len(err.splitlines()) == 1, (label, err)
    assert err.endswith("\n") and not err.endswith("\n\n"), (label, repr(err[-6:]))


@pytest.mark.parametrize("verb", REGISTER_READING_VERBS)
def test_x_every_register_reading_verb_refuses_not_just_the_three(tmp_path, verb):
    r"""The previous round proved the guard fires at `validate`, `list` and `report`. That is
    three of the SIX verbs that load a register, and the missing three (`prd`, `scan`, `diff`)
    are exactly the ones whose refusal cannot be explained by the markdown renderer. Measured:
    all six refuse `two\nlines` with rc 2, empty stdout and one `Error: ` line.
    """
    bad_root = tmp_path / "bad"
    good_root = tmp_path / "good"
    gap_id = synthetic_register(bad_root, "two\nlines")
    synthetic_register(good_root, "one clean stripped line")
    argv = {
        "validate": [verb, str(bad_root)],
        "list": [verb, str(bad_root)],
        "report": [verb, str(bad_root)],
        "prd": ["prd", "--gap", gap_id, str(bad_root)],
        "scan": ["scan", "--gaps", str(bad_root / "gaps"), str(tmp_path / "target")],
        "diff": ["diff", str(bad_root), str(good_root)],
    }[verb]
    (tmp_path / "target").mkdir(exist_ok=True)
    code, out, err = run(argv)
    assert code == 2, (verb, code, out[:160])
    assert out == "", (verb, out[:160])
    assert err.startswith(ERROR_PREFIX) and len(err.splitlines()) == 1, (verb, err)


@pytest.mark.parametrize("verb", REGISTER_READING_VERBS)
def test_x_the_control_a_clean_register_passes_the_same_six_verbs(tmp_path, verb):
    """Without this, all six refusals above could be credited to a broken synthetic register."""
    good_root = tmp_path / "good"
    gap_id = synthetic_register(good_root, "one clean stripped line")
    (tmp_path / "target").mkdir(exist_ok=True)
    argv = {
        "validate": [verb, str(good_root)],
        "list": [verb, str(good_root)],
        "report": [verb, str(good_root)],
        "prd": ["prd", "--gap", gap_id, str(good_root)],
        "scan": ["scan", "--gaps", str(good_root / "gaps"), str(tmp_path / "target")],
        "diff": ["diff", str(good_root), str(good_root)],
    }[verb]
    code, out, err = run(argv)
    assert (code, err) == (0, ""), (verb, code, err[:300])
    assert out.endswith("\n") and not out.endswith("\n\n"), (verb, repr(out[-8:]))


def test_x_an_authored_none_recorded_is_indistinguishable_from_an_empty_one(tmp_path):
    """PM FEEDBACK PINNED IN CODE: the DISPLAY string for the empty case is itself a legal
    rationale, so the published document cannot tell "nobody wrote one" from "somebody wrote
    those two words". Measured: the two documents are byte-identical. Recorded so that a later
    iteration which distinguishes them (a marker, italics, a different sentence) reds here and
    has to make that call deliberately rather than inheriting it.
    """
    authored_root, empty_root = tmp_path / "authored", tmp_path / "empty"
    authored = synthetic_register(authored_root, "none recorded")
    empty = synthetic_register(empty_root, "")
    doc_a = show(authored, authored_root)
    doc_b = show(empty, empty_root)
    assert detection_block(doc_a)[-1] == EMPTY_RATIONALE_LINE
    assert doc_a == doc_b, "the two cases diverged; the ambiguity note above is now stale"


def test_x_detection_is_an_interior_section_so_last_line_of_block_constrains_something():
    """If `## Detection` closed the document, "the LAST line of the block" would be satisfied by
    any renderer that appended to the end of the file. Measured on all 120 live records:
    `## Evidence` follows it every time, so behaviour 2 pins an INTERIOR position.
    """
    for gap_id in sorted(RAW_RECORDS):
        lines = show(gap_id).splitlines()
        start = lines.index(DETECTION_HEADING)
        following = [ln for ln in lines[start + 1 :] if ln.startswith("## ")]
        assert following, (gap_id, "Detection is the final section; behaviour 2 is vacuous")
        assert following[0] == "## Evidence", (gap_id, following[0])


def test_x_the_subprocess_entry_point_is_live_so_the_seed_test_cannot_skip_silently():
    """`test_b5_the_document_is_byte_stable_across_processes_and_hash_seeds` carries a
    `pytest.skip` escape hatch. If the module entry point ever breaks, that hatch retires the
    ONLY cross-process byte-stability evidence in this module without a single red mark. This
    test has no hatch, so the condition behind the skip becomes observable.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "agent_gap_radar.cli", "show", CHECKED_IDS[0], str(REPO_ROOT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr.strip()[:300])
    assert proc.stdout.endswith("\n") and not proc.stdout.endswith("\n\n"), repr(proc.stdout[-8:])
    assert RATIONALE_PREFIX in proc.stdout, "the entry point ran but published no rationale"


# ===========================================================================
# EXTENSIONS -- tester-retry2 round.
#
# The two earlier rounds were BOTH cut short by the stage cap, so this round re-measured
# their headline claims (full suite: 3222 passed / 5 skipped) before adding anything. The
# holes closed below are the ones neither round reached. Every expectation here was measured
# against the built product BEFORE it was written down, and each names the rival it kills.
# ===========================================================================

#: Values whose refusal cannot be explained by a `"\n" in value` check alone; each carries a
#: break that would ESCAPE into the error line if the guard interpolated the raw value.
BREAK_BEARING_VALUES = ("a\nb", "a\r\nb", "a\rb", "a\x0bb", "a\x0cb", "a\u2028b", "a\u2029b")

#: Characters Python's `str.strip()` treats as whitespace (so a value ending in one differs
#: from its stripped form and must be REFUSED), paired with one it does NOT.
STRIPPED_BY_PYTHON = ("\u00a0", "\u3000", "\u2007", "\x1c")
NOT_STRIPPED_BY_PYTHON = ("\u200b", "\u2060")


def test_x2_the_guard_lives_in_the_loader_not_the_cli_or_the_renderer():
    """The sharpest load-vs-render discriminator available, and neither earlier round used it.

    "Six verbs refuse" is consistent with a guard sitting in a shared CLI helper. Driving the
    PUBLIC loader directly removes the CLI from the picture entirely: `registry.load_all` on a
    mis-shaped register raises `registry.RegistryError` before any renderer exists, the clean
    control returns the record with its rationale intact, and the LIVE register still loads.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp) / "bad"
        synthetic_register(bad, "line one\nline two")
        with pytest.raises(registry.RegistryError) as caught:
            registry.load_all(registry.gaps_dir(bad))
        assert "rationale" in str(caught.value), str(caught.value)[:200]

        good = pathlib.Path(tmp) / "good"
        synthetic_register(good, "one clean stripped line")
        records = registry.load_all(registry.gaps_dir(good))
        assert len(records) == 1, records
        assert records[0].check.rationale == "one clean stripped line"

    live = registry.load_all(registry.gaps_dir(REPO_ROOT))
    assert len(live) == len(RAW_RECORDS), (len(live), len(RAW_RECORDS))


def test_x2_the_refusal_is_locatable_naming_the_offending_record_file_and_the_field(tmp_path):
    """A one-line refusal over a 120-record register is only actionable if it says WHICH record.

    Neither earlier round asserted anything about the error's CONTENT, only its shape, so a
    guard degraded to `Error: invalid register` would have passed every existing case. This
    pins the two locators an operator needs (the record's file, the field name) without pinning
    the sentence around them -- the deliberate non-assertion in this module's header stands.
    """
    gap_id = synthetic_register(tmp_path, "two\nlines")
    code, out, err = run(["validate", str(tmp_path)])
    assert (code, out) == (2, ""), (code, out[:120])
    assert len(err.splitlines()) == 1, err
    assert f"{gap_id}.json" in err, err[:200]
    assert "rationale" in err, err[:200]


def test_x2_two_violating_records_still_produce_exactly_one_error_line_naming_both(tmp_path):
    """The one-`Error:`-line contract is only interesting when there is MORE than one violation.

    Every existing refusal case plants a single bad record, where "one line" is free. Measured
    with two violations of DIFFERENT kinds (a break and a trailing space): the product still
    emits exactly one line and names BOTH records in it, so neither the contract nor the
    locators are traded away as the register degrades.
    """
    synthetic_register(tmp_path, "one\nbad", source_id="GAP-020")
    synthetic_register(tmp_path, "trailing space ", source_id="GAP-021")
    code, out, err = run(["validate", str(tmp_path)])
    assert (code, out) == (2, ""), (code, out[:160])
    assert len(err.splitlines()) == 1, err
    assert err.startswith(ERROR_PREFIX) and err.endswith("\n") and not err.endswith("\n\n")
    assert "GAP-020.json" in err and "GAP-021.json" in err, err[:300]


@pytest.mark.parametrize("value", BREAK_BEARING_VALUES, ids=lambda v: repr(v))
def test_x2_the_refused_value_is_echoed_with_its_break_escaped(tmp_path, value):
    r"""THE MECHANISM behind the one-line error contract, which no existing test constrains.

    The refusal echoes the offending value so an author can find it. A guard that interpolated
    the RAW value would emit a two-line `Error: ` block for exactly the inputs it is meant to
    reject -- passing every "rc 2 / stdout empty" assertion while breaking the quality bar's
    one-line rule. Measured: no raw break character survives into stderr for any of the seven
    break shapes, and the escaped form is what keeps the line count at one.
    """
    gap_id = synthetic_register(tmp_path, value)
    code, out, err = run(["show", gap_id, str(tmp_path)])
    assert (code, out) == (2, ""), (repr(value), code, out[:120])
    assert len(err.splitlines()) == 1, (repr(value), err)
    body = err[:-1]
    for char in "\n\r\u2028\u2029\x0b\x0c":
        assert char not in body, (repr(value), f"raw {char!r} leaked into the error line")


def test_x2_the_guard_domain_is_exactly_python_str_strip_in_both_directions(tmp_path):
    """Both halves in ONE test, because either alone reads as correct.

    The guard's rule is "differs from its stripped form", so its domain is whatever Python
    calls whitespace -- not the ASCII blanks the existing cases use. Measured: a no-break space
    or an ideographic space at the ends is REFUSED (Python strips them, so the bullet would
    open or close with an invisible blank), while a zero-width space or a word joiner is
    ACCEPTED and published verbatim (Python does not strip them, and they still render as one
    bullet). A guard rewritten as `value != value.strip(" \t")` would pass the first half's
    ASCII cases and silently admit the refused ones; this pair reds.
    """
    for index, char in enumerate(STRIPPED_BY_PYTHON):
        for side, value in (("lead", char + "x"), ("trail", "x" + char)):
            root = tmp_path / f"strip{index}{side}"
            gap_id = synthetic_register(root, value)
            code, out, err = run(["show", gap_id, str(root)])
            assert code == 2, (side, repr(value), code, out[:80])
            assert out == "", (side, repr(value), out[:80])
            assert err.startswith(ERROR_PREFIX) and len(err.splitlines()) == 1, (repr(value), err)

    for index, char in enumerate(NOT_STRIPPED_BY_PYTHON):
        value = char + "kept verbatim" + char
        assert value == value.strip(), f"{char!r} is stripped after all; re-derive this control"
        root = tmp_path / f"keep{index}"
        gap_id = synthetic_register(root, value)
        code, out, err = run(["show", gap_id, str(root)])
        assert (code, err) == (0, ""), (repr(value), code, err[:200])
        assert detection_block(out)[-1] == RATIONALE_PREFIX + value, (repr(value),)


def test_x2_the_bullet_joins_the_SAME_contiguous_run_no_blank_line_opens_a_second_block():
    """`block[-1] == expected` cannot see a blank line inserted BEFORE the rationale bullet.

    Both earlier rounds measured the bullet's POSITION (last content line of the block) and its
    text, and both survive a renderer that emits `heading / blank / bullets / blank / rationale`
    -- two visual blocks, which is what iteration 29's single-contiguous-block rule exists to
    forbid. Measured on all 120 live records: after the one blank that follows the heading, the
    block's content lines are contiguous, so the new bullet is inside the existing run.
    """
    for gap_id in sorted(RAW_RECORDS):
        block = detection_block(show(gap_id))
        assert block[0] == DETECTION_HEADING, (gap_id, block[0])
        assert block[1] == "", (gap_id, "the heading is no longer followed by one blank line")
        interior = block[2:]
        assert interior, gap_id
        blanks = [index for index, line in enumerate(interior) if line == ""]
        assert not blanks, (gap_id, blanks, [ln[:40] for ln in interior])


def test_x2_the_census_holds_on_the_one_record_that_actually_carries_the_word(tmp_path):
    """The word-census trap record, run through the OTHER verbs rather than only `show`.

    `test_b5_no_other_verb_publishes_the_rationale` censuses `prd` on `CHECKED_IDS[0]`, a record
    whose text never contains the word, so its strong `word not in out.lower()` assertion is
    free there. The trap record is where a leak would hide. Measured: the trap set is exactly
    one record, and `prd` on THAT record publishes neither the label nor the word.
    """
    trap = [gap_id for gap_id in CHECKED_IDS if show(gap_id).lower().count("rationale") != 1]
    assert len(trap) == 1, trap
    for argv in (["prd", "--gap", trap[0], str(REPO_ROOT)], ["report", str(REPO_ROOT)]):
        code, out, err = run(argv)
        assert (code, err) == (0, ""), (argv, code, err[:200])
        assert RATIONALE_PREFIX not in out, argv
        assert not any(ln.startswith(RATIONALE_PREFIX) for ln in out.splitlines()), argv
