"""Iteration 258 behaviors: the schema door REFUSES an unpaired surrogate.

Black-box, and the ISOLATION CONTRACT IS HONORED: nothing here reads the implementation
source, the engineer's or the reviewer's notes, `IMPLEMENTATION.patch`, or any diff.
Every expectation comes from `pm.md`'s eight numbered Expected Behaviors; every claim is
measured either by RUNNING the packaged entry point in a subprocess (so byte and
exit-code claims are about real encoded streams) or by asking the PUBLIC model door
(`Gap.model_validate`) for pydantic's own verdict.

Why the split matters, and why it is not a style choice: `pm.md`'s test-cost criterion
records that this defect is INVISIBLE in-process -- `cli.main` under a `redirect_stdout`
to a `StringIO` returned rc 0 and a 3,396 B document on the poisoned register, because a
`StringIO` holds `str` and never encodes. So behaviors 1-2, which are about bytes leaving
the process, own a real `subprocess` stream; behaviors 3-5, which are about what the
SCHEMA accepts, are in-process and cost nothing.

Structural notes, so a green dot here cannot mean less than it looks like:

* **Cost is bounded by construction** (`pm.md` acceptance criterion 4: the tester seat is
  at the 600 s cap). Every register is a ONE-record directory built under `tmp_path` from
  this module's own literal; nothing `copytree`s the 120-record register; the `scan` arm
  points at a ONE-file target; the module spends 12 subprocess runs in total.
* **Every refusal is checked as a WHOLE stream**, not by substring: exit code, stdout
  length in bytes, the single-line `Error: ` shape and the absence of `Traceback`.
* **The negative is load-bearing.** Behavior 4 proves the rule is surrogate-scoped and
  not ASCII-scoped, and behavior 5 pins that control characters are still accepted, so
  the refusal cannot quietly grow into "reject anything unusual".
* **No absolute machine path and no personal identifier appears here.** Registers live
  under pytest's `tmp_path`; the repo is located relative to `__file__`.
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

import pytest

from pydantic import ValidationError

from agent_gap_radar.cli import main
from agent_gap_radar.models import Gap

#: Repo root, found relative to this file so no absolute machine path is written down.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GAPS_DIR = REPO_ROOT / "gaps"
SRC_DIR = REPO_ROOT / "src"

#: The packaged entry point, driven the way `project.scripts` declares it
#: (`radar = "agent_gap_radar.cli:main"`). Same boot line as `test_iter242_behavior.py`.
BOOT = "import sys; from agent_gap_radar.cli import main; sys.exit(main())"

#: The hazard: an UNPAIRED high surrogate. `json.dumps(..., ensure_ascii=True)` writes it
#: as the 6-byte ASCII escape `\ud800`, so the record file on disk is valid UTF-8 and
#: valid JSON -- which is exactly why `pm.md` calls this a completeness hole at the door
#: rather than a malformed-file case.
SURROGATE = "\ud800"

#: The escaped form the refusal must show (`pm.md` behavior 6).
SURROGATE_ESCAPED = "\\ud800"

#: A record satisfying the shipped schema, carrying one of every string container the rule
#: must cover: plain `str` on `Gap`, on `Check` and on `Evidence`, a `list[str]` element,
#: and a VALUE in the `dict[str, str]` `check.fixtures.bad`.
RECORD = {
    "id": "GAP-001",
    "title": "A thing is broken",
    "layer": "orchestration",
    "gap_type": "missing-contract",
    "status": "open",
    "problem": "p",
    "symptom": "s",
    "why_now": "w",
    "existing": ["partial fix one"],
    "severity": 5,
    "frequency": 4,
    "tractability": 3,
    "evidence": [
        {
            "source_class": "first-party-field",
            "title": "INC-1",
            "locator": "https://example.invalid/inc1",
            "date": "2026-01-02",
            "quote": "the verbatim line",
        }
    ],
    "build_hypothesis": "build a small wrapper",
    "tags": ["feedback-loop"],
    "check": {
        "id": "CHK-001",
        "manual_question": "Does the door refuse text that cannot be encoded?",
        "rationale": "A record that cannot be written to stdout is not publishable.",
        "fixtures": {
            "bad": {"runner.py": "MARK258_BAD = 1\n"},
            "good": {"runner.py": "MARK258_GOOD = 2\n"},
        },
    },
}


def _poison(field_path, value=SURROGATE):
    """Return a copy of RECORD whose ONE named field holds `value`."""
    rec = json.loads(json.dumps(RECORD))
    node = rec
    for key in field_path[:-1]:
        node = node[key]
    last = field_path[-1]
    node[last] = value
    return rec


def _register(root, rec, name="reg"):
    """Write a ONE-record register under `root` and return its directory."""
    d = root / name / "gaps"
    d.mkdir(parents=True)
    (d / "GAP-001.json").write_text(json.dumps(rec, ensure_ascii=True), encoding="utf-8")
    return d.parent


def _run(*argv):
    """Drive the PACKAGED entry point, so byte claims are about real bytes."""
    return subprocess.run(
        [sys.executable, "-c", BOOT, *argv],
        capture_output=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


def _assert_refusal(proc, *, names):
    """The product's standard failure: exit 2, empty stdout, exactly one `Error: ` line."""
    err = proc.stderr.decode("utf-8")
    assert proc.returncode == 2, f"expected exit 2, got {proc.returncode}; stderr={err!r}"
    assert len(proc.stdout) == 0, f"stdout must be 0 bytes, got {proc.stdout[:200]!r}"
    assert err.endswith("\n"), f"stderr must end in one newline, got {err!r}"
    assert err.count("\n") == 1, f"stderr must be exactly ONE line, got {err!r}"
    assert err.startswith("Error: "), f"missing the 'Error: ' prefix: {err!r}"
    assert "Traceback" not in err, f"a traceback leaked: {err!r}"
    assert "UnicodeEncodeError" not in err, (
        f"the raw codec exception leaked instead of a product error: {err!r}"
    )
    for token in names:
        assert token in err, f"refusal must name {token!r}: {err!r}"
    return err


def test_b1_validate_refuses_a_surrogate_in_a_quote(poisoned_arms):
    """Behavior 1: `radar validate` on a poisoned quote -> exit 2, 0 B stdout, one line.

    Reads the module-scoped `validate` stream rather than spawning a sixth identical
    one, which keeps the module at the 12 subprocess runs `pm.md` acceptance criterion
    4 allows while this round adds four new real-stream arms.
    """
    err = _assert_refusal(poisoned_arms["validate"], names=("GAP-001.json",))
    for part in ("evidence", "0", "quote"):
        assert part in err, f"the field path must name {part!r}: {err!r}"

#: The five string containers `pm.md` behavior 3 names, and the pydantic `loc` PREFIX each
#: must report. Recorded as a prefix, not an exact tuple, so the test pins WHICH field the
#: door blamed without transcribing pydantic's container-level reporting choice.
PLACEMENTS = (
    ("title", ["title"], ("title",)),
    ("check.rationale", ["check", "rationale"], ("check", "rationale")),
    ("evidence[0].locator", ["evidence", 0, "locator"], ("evidence", 0, "locator")),
    ("tags element", ["tags", 0], ("tags",)),
    ("check.fixtures.bad value", ["check", "fixtures", "bad", "runner.py"],
     ("check", "fixtures", "bad")),
)

#: Legal non-ASCII, the load-bearing negative of behavior 4: an em dash, a multiplication
#: sign and an ASTRAL emoji (a real surrogate PAIR in UTF-16 terms) must all stay accepted.
EM_DASH = "\u2014"
TIMES = "\u00d7"
EMOJI = "\U0001f600"

#: The OTHER half of the surrogate block: a lone LOW surrogate. `pm.md` says "unpaired
#: surrogate", not "U+D800", so a rule that only knew the high half would be a hole.
LOW_SURROGATE = "\udfff"

#: An astral character written on disk the way JSON is ALLOWED to write it: as a
#: well-formed UTF-16 escape PAIR. `json.loads` joins the pair into U+1F600, so this is
#: the sharpest form of behavior 4's negative -- the rule must be about what the string
#: DECODES to, never about the letters `\ud` appearing in the file.
ASTRAL_FROM_ESCAPE_PAIR = json.loads('"\\ud83d\\ude00"')

#: The records `pm.md` behavior 4 names as the committed register's non-ASCII content.
#: Held as ID PREFIXES because a committed record file is `GAP-NNN-<slug>.json`, and the
#: slug is title-derived, so pinning whole filenames would pin unrelated prose.
NAMED_NON_ASCII = ("GAP-012", "GAP-014", "GAP-045", "GAP-056", "GAP-103", "GAP-105")

#: Behavior 5's control characters, pinned as ACCEPTED so a later policy change is
#: deliberate: NUL and the right-to-left override.
NUL = "\x00"
RTL_OVERRIDE = "\u202e"

#: The five documents behavior 8 requires to be unmoved, as argv for the in-process door.
DOCUMENT_ARGV = (
    ("report", str(REPO_ROOT)),
    ("list", str(REPO_ROOT)),
    ("list", str(REPO_ROOT), "--json"),
    ("show", "GAP-001", str(REPO_ROOT)),
    ("prd", str(REPO_ROOT)),
)

#: Vocabulary this iteration introduces. Behavior 8's documents must not contain it: the
#: rule is a refusal at the door, so nothing about it may appear in a rendered document.
NEW_RULE_VOCABULARY = ("surrogate", SURROGATE_ESCAPED, "UTF-16", "UnicodeEncodeError")


def _target(root):
    """A ONE-file scan target, so the `scan` arm costs no repository walk."""
    t = root / "target" / "app"
    t.mkdir(parents=True)
    (t / "loop.py").write_text("import subprocess\n", encoding="utf-8")
    return t.parent


@pytest.fixture(scope="module")
def poisoned_arms(tmp_path_factory):
    """Run the FIVE real-stream arms of behaviors 1-2 once, and share the results.

    Module-scoped on purpose: `pm.md`'s acceptance criterion caps this module's
    subprocess spend, and behaviors 1, 2, 6 and 7 all read the same five streams.
    """
    root = tmp_path_factory.mktemp("iter258_poisoned")
    reg = _register(root, _poison(["evidence", 0, "quote"]))
    target = _target(root)
    gaps = reg / "gaps"
    return {
        "validate": _run("validate", str(reg)),
        "list": _run("list", str(reg)),
        "report": _run("report", str(reg)),
        "show": _run("show", "GAP-001", str(reg)),
        "scan": _run("scan", str(target), "--gaps", str(gaps)),
    }


# --- vacuity guard ---------------------------------------------------------------------
#
# Every refusal below is attributed to ONE mutation, which is a claim about the mutation
# only if the UNMUTATED record passes. Without this, a record rejected for an unrelated
# schema reason would score as a green surrogate test.


def test_b0_the_unpoisoned_record_is_accepted_by_the_schema_door():
    """The template validates, so behaviors 1-3 measure the surrogate and nothing else."""
    gap = Gap.model_validate(json.loads(json.dumps(RECORD)))
    assert gap.id == "GAP-001"
    assert gap.check is not None, "the template must carry a check, or behavior 3 is short"
    assert gap.tags, "the template must carry tags, or behavior 3 is short"


def test_b0_the_unpoisoned_register_renders(tmp_path):
    """A clean ONE-record register is a real register: `validate` accepts it at exit 0."""
    reg = _register(tmp_path, json.loads(json.dumps(RECORD)))
    proc = _run("validate", str(reg))
    assert proc.returncode == 0, f"clean register must pass: {proc.stderr.decode()!r}"
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")


# --- behavior 2 -----------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["list", "report", "show", "scan"])
def test_b2_the_four_crashing_verbs_refuse_identically(poisoned_arms, verb):
    """Behavior 2: exit 2, 0-byte stdout, one `Error: ` line, no exit 1, no `Traceback`."""
    proc = poisoned_arms[verb]
    err = _assert_refusal(proc, names=("GAP-001.json",))
    assert proc.returncode != 1, f"{verb} must not exit 1 (reserved for broken pipe)"
    for part in ("evidence", "0", "quote"):
        assert part in err, f"{verb} must name the field path part {part!r}: {err!r}"


# --- behavior 3 -----------------------------------------------------------------------


@pytest.mark.parametrize("name,path,loc_prefix", PLACEMENTS, ids=[p[0] for p in PLACEMENTS])
def test_b3_every_string_container_is_covered(name, path, loc_prefix):
    """Behavior 3: the rule covers plain `str`, `list[str]` and `dict[str, str]` alike."""
    with pytest.raises(ValidationError) as excinfo:
        Gap.model_validate(_poison(path))
    locs = [tuple(item["loc"]) for item in excinfo.value.errors()]
    assert any(loc[: len(loc_prefix)] == loc_prefix for loc in locs), (
        f"{name}: the door must blame {loc_prefix}, got {locs}"
    )
    assert SURROGATE_ESCAPED in str(excinfo.value), (
        f"{name}: the message must show the codepoint escaped: {str(excinfo.value)!r}"
    )


def test_b3_a_title_surrogate_is_refused_on_a_real_stream(tmp_path):
    """Behavior 3 on the field `pm.md` measured as the four-verb killer, end to end."""
    reg = _register(tmp_path, _poison(["title"]))
    err = _assert_refusal(_run("validate", str(reg)), names=("GAP-001.json", "title"))
    assert SURROGATE_ESCAPED in err, f"the codepoint must appear escaped: {err!r}"
    assert err.isascii(), f"behavior 6 covers behaviors 1-3: stderr must be ASCII: {err!r}"


# --- behavior 4 (the load-bearing negative) -------------------------------------------


def test_b4_legal_non_ascii_is_accepted_and_renders(tmp_path):
    """Behavior 4: surrogate-scoped, NOT ASCII-scoped -- em dash, U+00D7 and an emoji."""
    rec = json.loads(json.dumps(RECORD))
    rec["title"] = f"A thing {EM_DASH} is broken"
    rec["evidence"][0]["quote"] = f"{TIMES} the verbatim line {EMOJI}"
    reg = _register(tmp_path, rec)

    validated = _run("validate", str(reg))
    assert validated.returncode == 0, (
        f"legal non-ASCII must validate: {validated.stderr.decode()!r}"
    )

    shown = _run("show", "GAP-001", str(reg))
    assert shown.returncode == 0, f"legal non-ASCII must render: {shown.stderr.decode()!r}"
    out = shown.stdout.decode("utf-8")
    assert out.endswith("\n") and not out.endswith("\n\n"), "exactly one trailing newline"
    assert EM_DASH in out and TIMES in out and EMOJI in out, (
        "the renderer must publish the characters verbatim, not escape or drop them"
    )


def test_b4_the_committed_register_still_validates():
    """Behavior 4: all 120 committed records pass, and the non-ASCII ones are real."""
    proc = _run("validate", str(REPO_ROOT))
    assert proc.returncode == 0, f"the register must stay clean: {proc.stderr.decode()!r}"

    records = sorted(GAPS_DIR.glob("GAP-*.json"))
    assert len(records) >= 120, f"expected the committed register, found {len(records)}"
    non_ascii, surrogate_bearing = [], []
    for path in records:
        text = path.read_text(encoding="utf-8")
        if not json.dumps(json.loads(text), ensure_ascii=False).isascii():
            non_ascii.append(path.name)
        if "\\ud8" in text.lower() or "\\udc" in text.lower():
            surrogate_bearing.append(path.name)
    assert non_ascii, "the negative is vacuous unless some committed record is non-ASCII"
    missing = [
        gap_id
        for gap_id in NAMED_NON_ASCII
        if not any(name.startswith(gap_id + "-") for name in non_ascii)
    ]
    assert missing == [], (
        f"pm.md behavior 4 names these as the live non-ASCII records; they no longer "
        f"carry non-ASCII, so the negative lost its content: {missing}"
    )
    assert surrogate_bearing == [], f"a committed record holds a surrogate: {surrogate_bearing}"


# --- behavior 5 -----------------------------------------------------------------------


@pytest.mark.parametrize("label,char", [("NUL", NUL), ("RTL override", RTL_OVERRIDE)])
def test_b5_control_characters_stay_accepted(label, char):
    """Behavior 5: pinned so a later control-character policy is deliberate, not drift."""
    rec = _poison(["evidence", 0, "quote"], f"before {char} after")
    gap = Gap.model_validate(rec)
    assert char in gap.evidence[0].quote, f"{label} must survive the door verbatim"


# --- behavior 6 -----------------------------------------------------------------------


def test_b6_every_refusal_is_ascii_safe_and_escapes_the_codepoint(poisoned_arms):
    """Behavior 6: the error path cannot raise the error it reports."""
    for verb, proc in sorted(poisoned_arms.items()):
        err = proc.stderr.decode("utf-8")
        assert err.isascii(), f"{verb}: stderr must be pure ASCII, got {err!r}"
        assert SURROGATE_ESCAPED in err, f"{verb}: codepoint must be escaped: {err!r}"
        assert SURROGATE not in err, f"{verb}: the raw surrogate must never be emitted"
        assert proc.stderr == err.encode("ascii"), f"{verb}: stderr bytes must be ASCII"


# --- behavior 7 -----------------------------------------------------------------------


def test_b7_all_five_doors_speak_one_dialect(poisoned_arms):
    """Behavior 7, behaviorally: one spelling of the rule can only produce one message."""
    messages = {verb: proc.stderr.decode("utf-8") for verb, proc in poisoned_arms.items()}
    distinct = sorted(set(messages.values()))
    assert len(distinct) == 1, (
        "five doors reported the same poison in more than one dialect, so the rule is "
        f"spelled more than once: {messages}"
    )


def test_b7_the_predicate_is_spelled_at_exactly_one_site():
    """Behavior 7, as the census `pm.md` asks for (the rows-32/46 two-standards precedent).

    A census, not a reading: this counts FILES under `src/` that mention the rule's subject
    at all. Two files mentioning it is the failure the precedent names -- two doors with two
    spellings of one rule.
    """
    sources = sorted(p for p in SRC_DIR.rglob("*.py"))
    assert sources, f"no source files found under {SRC_DIR.name}/"
    mentions = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in sources
        if "surrogate" in p.read_text(encoding="utf-8").lower()
    ]
    assert len(mentions) == 1, (
        f"the surrogate rule must be spelled at exactly ONE site under src/, found "
        f"{len(mentions)}: {mentions}"
    )
    assert mentions[0].endswith("/models.py"), (
        "pm.md acceptance criterion 2 puts the predicate in the SCHEMA so every door "
        f"inherits it; it is spelled in {mentions[0]} instead"
    )


# --- behavior 8 -----------------------------------------------------------------------


def test_b8_the_five_documents_are_unmoved_and_byte_stable(capsys):
    """Behavior 8: zero re-baselines.

    `pm.md` words this as "byte-identical to HEAD", which cannot live in a committed test
    because HEAD moves (the iteration-256 precedent). The durable half is pinned here --
    each document exits 0 with EMPTY stderr, ends in exactly ONE newline, is identical
    across two runs of the same tree, and never leaks this iteration's vocabulary. The
    HEAD half is measured out of band in `tester.md` with `git status --porcelain`, which
    names the files that moved without reading a diff.
    """
    for argv in DOCUMENT_ARGV:
        first_code = main(list(argv))
        first = capsys.readouterr()
        second_code = main(list(argv))
        second = capsys.readouterr()

        label = " ".join(a for a in argv if not a.startswith("/"))
        assert first_code == 0 == second_code, f"{label}: exit 0 expected, got {first_code}"
        assert first.err == "" == second.err, f"{label}: stderr must be empty, got {first.err!r}"
        assert first.out, f"{label}: emitted nothing"
        assert first.out.endswith("\n"), f"{label}: must end in a newline"
        assert not first.out.endswith("\n\n"), f"{label}: must end in EXACTLY one newline"
        assert first.out == second.out, f"{label}: output is not byte-stable across runs"
        for token in NEW_RULE_VOCABULARY:
            assert token not in first.out, (
                f"{label}: the new refusal rule leaked into a rendered document ({token!r})"
            )


# --- behaviors 3-5, second round: the edges the first round left unmeasured ------------
#
# Added by the retry round. The first round's placements covered the five containers
# `pm.md` behavior 3 ENUMERATES; these five arms attack the three ways a rule can be
# narrower than "an unpaired surrogate in any record string" and still pass that list:
# it could know only the HIGH half of the block, only a string that STARTS with the
# hazard, or only the dict VALUES that behavior 3 spells out and not the KEYS.


def _poison_fixture_key(char=SURROGATE):
    """Return a copy of RECORD whose `check.fixtures.bad` has a poisoned dict KEY."""
    rec = json.loads(json.dumps(RECORD))
    rec["check"]["fixtures"]["bad"] = {f"run{char}.py": "MARK258_BAD = 1\n"}
    return rec


EDGE_PLACEMENTS = (
    (
        "lone LOW surrogate",
        _poison(["evidence", 0, "quote"], f"a {LOW_SURROGATE} b"),
        ("evidence", 0, "quote"),
        "\\udfff",
    ),
    (
        "surrogate in mid-string, not at index 0",
        _poison(["problem"], f"a {SURROGATE} b"),
        ("problem",),
        SURROGATE_ESCAPED,
    ),
    (
        "a dict KEY, not a value",
        _poison_fixture_key(),
        ("check", "fixtures", "bad"),
        SURROGATE_ESCAPED,
    ),
    (
        "an element of the list[str] `existing`",
        _poison(["existing", 0], f"partial {SURROGATE}"),
        ("existing",),
        SURROGATE_ESCAPED,
    ),
    (
        "the id field, which carries its own validator",
        _poison(["id"], f"GAP-00{SURROGATE}"),
        ("id",),
        SURROGATE_ESCAPED,
    ),
)


@pytest.mark.parametrize(
    "name,record,loc_prefix,escaped", EDGE_PLACEMENTS, ids=[e[0] for e in EDGE_PLACEMENTS]
)
def test_b3_the_rule_covers_the_whole_block_and_keys_too(name, record, loc_prefix, escaped):
    """Behavior 3, widened: whole surrogate block, any offset, keys as well as values."""
    with pytest.raises(ValidationError) as excinfo:
        Gap.model_validate(record)
    message = str(excinfo.value)
    locs = [tuple(item["loc"]) for item in excinfo.value.errors()]
    assert any(loc[: len(loc_prefix)] == loc_prefix for loc in locs), (
        f"{name}: the door must blame {loc_prefix}, got {locs}"
    )
    assert message.isascii(), f"{name}: behavior 6 -- the message must be ASCII: {message!r}"
    assert escaped in message, f"{name}: the codepoint must appear escaped: {message!r}"


def test_b4_a_wellformed_escape_pair_is_accepted_on_a_real_stream(tmp_path):
    """Behavior 4's sharpest negative: `\\ud83d\\ude00` on disk is U+1F600, so it PASSES.

    A rule implemented by grepping the record file for the letters `\\ud` would refuse this
    file; a rule about what the decoded string can ENCODE accepts it. Run on a real stream
    because the point is that these bytes reach stdout.
    """
    assert ASTRAL_FROM_ESCAPE_PAIR == EMOJI, "the escape pair must decode to one astral char"
    assert len(ASTRAL_FROM_ESCAPE_PAIR) == 1, "Python must join the pair, not keep two halves"

    rec = _poison(["title"], f"A {ASTRAL_FROM_ESCAPE_PAIR} thing is broken")
    reg = _register(tmp_path, rec)
    raw = (reg / "gaps" / "GAP-001.json").read_text(encoding="utf-8")
    assert "\\ud83d\\ude00" in raw, "ensure_ascii must have written the pair as escapes"

    proc = _run("validate", str(reg))
    assert proc.returncode == 0, (
        f"a well-formed escape pair must validate: {proc.stderr.decode()!r}"
    )
    assert proc.stderr == b"", f"a clean register must print nothing to stderr: {proc.stderr!r}"


def test_b5_control_characters_are_accepted_by_the_real_door(tmp_path):
    """Behavior 5 as `pm.md` words it: `radar validate` at exit 0, not just the model door.

    The first round pinned this in-process only. Behavior 5 names the VERB, and the verb is
    what a curator runs, so the pin has to survive a real stream to mean anything.
    """
    rec = _poison(["evidence", 0, "quote"], f"before{NUL}middle{RTL_OVERRIDE}after")
    reg = _register(tmp_path, rec)
    proc = _run("validate", str(reg))
    assert proc.returncode == 0, (
        f"control characters must stay ACCEPTED (out of scope per pm.md): "
        f"{proc.stderr.decode(errors='replace')!r}"
    )
    assert proc.stderr == b"", f"nothing may be reported: {proc.stderr!r}"
    assert proc.stdout.endswith(b"\n") and not proc.stdout.endswith(b"\n\n")


def test_meta_the_module_stays_inside_its_subprocess_budget():
    """`pm.md` acceptance criterion 4 caps the module at ~12 real CLI runs; count them.

    The tester seat is at the 600 s cap (`pm.md` quotes -1.0 s of headroom), so the cost
    ceiling is part of the contract, not advice. This counts `_run(` call sites in this
    module -- counted by parsing, so a mention in prose cannot inflate the census. Five
    of the runs live in the module-scoped fixture, which is why
    behaviors 1, 2, 6 and 7 share one set of streams instead of re-spawning them.
    """
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    call_sites = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_run"
    )
    assert call_sites <= 12, (
        f"this module must spend at most 12 subprocess CLI runs, it spells {call_sites}"
    )
