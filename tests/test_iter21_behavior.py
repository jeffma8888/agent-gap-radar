"""Iteration 21 behaviors: `radar taxonomy` reaches the published `render.document()`
instead of carrying half a copy of the one-newline tail, a census counts that GUARANTEE
rather than its body, and no module imports a name it never loads.

Black-box, and the isolation contract is honored: nothing here reads the implementation
source to DERIVE an expectation, and nothing reads the engineer's or the reviewer's notes
or a diff. Behavior 1's expectation is built from the PUBLISHED vocabularies
(`taxonomy.LAYERS`, `GAP_TYPES`, `SOURCE_CLASSES`, `SOURCE_WEIGHTS`, from iteration 71
`STATUSES` with its `STATUS_GLOSSES` attribute table, and from iteration 100 the citation
partition `citable_statuses()` / `terminal_statuses()`), never from the verb's rendering code
and never from a restated literal -- the document's byte length and the vocabulary contents
are both deliberately absent from this file, so a taxonomy that legitimately grows keeps
this test green.

Behaviors 3-8 are a SOURCE CENSUS and an AST ORACLE, which the spec asks for by name.
They read `src/agent_gap_radar/**/*.py` as DATA and assert only counts and name lists;
each one is proven two-sided IN THIS RUN against planted samples, and both report their
domain size so an empty walk can never read as clean.

Two lessons from this repo's own history are encoded structurally rather than trusted:

* The census pattern needs a DOUBLED backslash and its planted samples need a SINGLE one.
  Building both from one constant makes every sample read 0 -- including known-bad -- and
  the matcher then certifies itself two-sided while blind. The samples here are raw
  strings carrying one real backslash each, and `test_census_matcher_backslash_arity`
  asserts that arity directly rather than leaving it to inspection.
* The unused-import oracle must count `ast.Name` LOADS ONLY. Crediting an `ast.Attribute`
  name as a load makes an imported `confidence` look used by any `obj.confidence` read,
  which is exactly the confounder the real file carries; `known-bad-shadowed-by-attribute`
  reproduces it so this oracle cannot pass while blind to it.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from agent_gap_radar import taxonomy
from agent_gap_radar.cli import main

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src" / "agent_gap_radar"

#: Behavior 1 -- the verb's own section headings. These are the taxonomy verb's
#: publishing choices, not vocabulary CONTENT, so pinning them is the point.
TAXONOMY_TITLE = "# Taxonomy"
LAYERS_HEADING = "## Layers"
GAP_TYPES_HEADING = "## Gap types"
SOURCES_HEADING = "## Evidence source classes (strongest first)"
STATUSES_HEADING = "## Record statuses"
CITATION_GATE_HEADING = "## Citation gate"


def _joined_with_one_newline_tail(lines):
    """`lines` as a document ending in exactly one newline.

    Written as a per-line generator on purpose: the literal join-plus-newline idiom is
    the thing behavior 4 censuses, and this file should not become a future hit for a
    census that someone later widens to cover `tests/`.
    """
    return "".join(line + "\n" for line in lines)


def _expected_side(statuses):
    """One side of the citation partition, in the verb's format.

    The FORMAT is restated here and the CONTENT is derived -- the same split iteration 71
    used for the gloss bullets. `(none)` is the documented rendering of an empty side; a
    bare separator would leave trailing whitespace on a published line.
    """
    return ", ".join(f"`{status}`" for status in statuses) if statuses else "(none)"


def _expected_taxonomy_document():
    """Behavior 1 -- derived from the published vocabularies, in the verb's order."""
    lines = [TAXONOMY_TITLE, "", LAYERS_HEADING, ""]
    lines += [f"- `{name}` -- {gloss}" for name, gloss in taxonomy.LAYERS.items()]
    lines += ["", GAP_TYPES_HEADING, ""]
    lines += [f"- `{name}` -- {gloss}" for name, gloss in taxonomy.GAP_TYPES.items()]
    lines += ["", SOURCES_HEADING, ""]
    lines += [f"- `{cls}` (weight {taxonomy.SOURCE_WEIGHTS[cls]})"
              for cls in taxonomy.SOURCE_CLASSES]
    lines += ["", STATUSES_HEADING, ""]
    # Ordered by `STATUSES`, never by the gloss mapping's own key order: the tuple is what
    # `models.py` validates a record against, so it is the thing the document owes a
    # reader. Iterating the mapping instead would let a reordered gloss table read green.
    lines += [f"- `{status}` -- {taxonomy.STATUS_GLOSSES[status]}"
              for status in taxonomy.STATUSES]
    lines += ["", CITATION_GATE_HEADING, ""]
    # Iteration 100's partition. Both sides come from the taxonomy's own DERIVATION
    # helpers rather than from a restated pair of lists, so this stays green when the
    # status vocabulary grows and reds when the verb publishes a partition the library
    # does not agree with -- which is the only failure worth pinning here.
    lines += [f"- `citable` -- {_expected_side(taxonomy.citable_statuses())}",
              f"- `terminal` -- {_expected_side(taxonomy.terminal_statuses())}"]
    return _joined_with_one_newline_tail(lines)


def test_taxonomy_document_equals_the_published_vocabularies(capsys):
    """Behavior 1: exit 0, and stdout IS the derived document, byte for byte."""
    assert main(["taxonomy"]) == 0
    captured = capsys.readouterr()
    expected = _expected_taxonomy_document()
    assert captured.out == expected, (
        f"`radar taxonomy` stdout ({len(captured.out.encode())} bytes) does not equal the "
        f"document derived from the published vocabularies ({len(expected.encode())} bytes)")
    assert captured.err == "", (
        "the quality bar gives stdout the document and stderr the errors; stderr carried "
        f"{captured.err!r}")


def test_taxonomy_covers_every_published_vocabulary_entry(capsys):
    """Behavior 1, restated as coverage: no entry may be silently dropped, and the
    five sections stay in the order the verb publishes them."""
    assert main(["taxonomy"]) == 0
    out = capsys.readouterr().out
    for name in list(taxonomy.LAYERS) + list(taxonomy.GAP_TYPES):
        assert f"- `{name}` --" in out, f"vocabulary entry {name!r} is missing from the verb"
    for cls in taxonomy.SOURCE_CLASSES:
        assert f"- `{cls}` (weight {taxonomy.SOURCE_WEIGHTS[cls]})" in out, (
            f"source class {cls!r} is missing or carries the wrong weight")
    for status in taxonomy.STATUSES:
        assert f"- `{status}` -- {taxonomy.STATUS_GLOSSES[status]}" in out, (
            f"record status {status!r} is missing or carries the wrong gloss")
    for status in taxonomy.citable_statuses() + taxonomy.terminal_statuses():
        assert f"`{status}`" in out, (
            f"status {status!r} is in the partition but absent from the published document")
    positions = [out.index(h) for h in
                 (TAXONOMY_TITLE, LAYERS_HEADING, GAP_TYPES_HEADING, SOURCES_HEADING,
                  STATUSES_HEADING, CITATION_GATE_HEADING)]
    assert positions == sorted(positions), f"section order changed: offsets {positions}"


def test_taxonomy_ends_in_exactly_one_newline(capsys):
    """Behavior 2 -- the published guarantee, observed on the bytes."""
    assert main(["taxonomy"]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n"), "renderer output must end in a newline"
    assert not out.endswith("\n\n"), (
        "renderer output must end in EXACTLY one newline; it ends in a blank line")
    assert out.rstrip("\n") + "\n" == out, "more than one trailing newline survived"


#: Behavior 4 -- the ARGUMENT-AGNOSTIC idiom: a newline-literal `.join(...)` whose
#: argument carries no parentheses, immediately followed by `+` and a newline literal,
#: either quote style. The doubled backslash matches a LITERAL backslash-n inside a
#: string literal; a single backslash here would be a fail-CLOSED matcher that reports
#: the idiom in every healthy file.
JOIN_TAIL_IDIOM = re.compile(
    r'''(?:"\\n"|'\\n')\.join\([^()]*\)\s*\+\s*(?:"\\n"|'\\n')''')

#: Known-bad: the half-copy this iteration removes. Must be seen exactly once.
PLANTED_BAD = r'''sys.stdout.write("\n".join(out) + "\n")'''

#: The same idiom in single quotes -- the pattern is quote-agnostic by spec.
PLANTED_BAD_SINGLE_QUOTED = r'''sys.stdout.write('\n'.join(out) + '\n')'''

#: Known-good: the convention this iteration installs. Must be seen zero times.
PLANTED_GOOD = r'''sys.stdout.write(document(out))'''

#: Near-miss: a newline join with NO one-newline tail. Zero, or a hit could be scored
#: on the join alone and every ordinary line-joining renderer would read as a copy.
PLANTED_NEAR_MISS_NO_TAIL = r'''sys.stdout.write("\n".join(out))'''

#: Near-miss: a one-newline tail on a DIFFERENT separator. Zero.
PLANTED_NEAR_MISS_OTHER_SEPARATOR = r'''sys.stdout.write(", ".join(out) + "\n")'''

#: Near-miss: a TWO-newline tail. Zero -- it is not the guarantee under census.
PLANTED_NEAR_MISS_TWO_NEWLINES = r'''sys.stdout.write("\n".join(out) + "\n\n")'''

#: DOCUMENTED BLIND SPOT, asserted so it is a known limit rather than a surprise: the
#: spec scopes the idiom to an argument with no parentheses, so a join over a CALL is
#: invisible to this census. Zero here means "out of scope", never "clean".
PLANTED_OUT_OF_SCOPE_CALL_ARGUMENT = r'''sys.stdout.write("\n".join(f(out)) + "\n")'''


def _census_in(root):
    """(files scanned, {filename: hits}) over `root/**/*.py`, `__pycache__` excluded."""
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    hits = {}
    for path in files:
        found = len(JOIN_TAIL_IDIOM.findall(path.read_text(encoding="utf-8")))
        if found:
            hits[path.name] = found
    return files, hits


def _census():
    """The live census: `src/agent_gap_radar/**/*.py`."""
    return _census_in(SRC_DIR)


def test_join_tail_guarantee_has_exactly_one_implementation():
    """Behavior 4. Measured before this iteration: 2, `{'cli.py': 1, 'render.py': 1}`."""
    files, hits = _census()
    total = sum(hits.values())
    assert total == 1, (
        f"the argument-agnostic one-newline join tail occurs {total} time(s) across "
        f"{len(files)} file(s) under src/agent_gap_radar/, expected exactly 1: {hits}")
    assert list(hits) == ["render.py"], (
        f"the single implementation must live in render.py; found it in {list(hits)} "
        f"across {len(files)} file(s) scanned")


def test_cli_carries_no_inline_one_newline_tail():
    """Behavior 3 -- stated as its own assertion so a failure names the file."""
    files, hits = _census()
    assert hits.get("cli.py", 0) == 0, (
        f"cli.py still carries {hits.get('cli.py')} inline one-newline tail(s); the "
        f"taxonomy branch must reach render.document() instead ({len(files)} file(s) "
        f"scanned, all hits: {hits})")


def test_census_domain_is_non_empty_and_reported():
    """Behavior 6 -- an empty walk must never read as clean."""
    files, _ = _census()
    assert len(files) >= 8, (
        f"census domain collapsed to {len(files)} file(s) under {SRC_DIR.name}/; a small "
        "domain reads as health it never measured")
    assert all(path.suffix == ".py" for path in files)
    assert not any("__pycache__" in path.parts for path in files)


@pytest.mark.parametrize(
    "sample,expected",
    [(PLANTED_BAD, 1),
     (PLANTED_BAD_SINGLE_QUOTED, 1),
     (PLANTED_GOOD, 0),
     (PLANTED_NEAR_MISS_NO_TAIL, 0),
     (PLANTED_NEAR_MISS_OTHER_SEPARATOR, 0),
     (PLANTED_NEAR_MISS_TWO_NEWLINES, 0),
     (PLANTED_OUT_OF_SCOPE_CALL_ARGUMENT, 0)],
    ids=["known-bad", "known-bad-single-quoted", "known-good", "near-miss-no-tail",
         "near-miss-other-separator", "near-miss-two-newlines",
         "out-of-scope-call-argument"])
def test_census_matcher_is_two_sided(sample, expected):
    """Behavior 5 -- the exact counts the spec names, proven in this run."""
    assert len(JOIN_TAIL_IDIOM.findall(sample)) == expected, (
        f"census matcher scored {len(JOIN_TAIL_IDIOM.findall(sample))} on {sample!r}, "
        f"expected {expected}")


def test_census_matcher_backslash_arity():
    """Behavior 5's failure mode, asserted rather than inspected: one real backslash per
    newline literal in a sample, doubled only inside the pattern. Two backslashes in a
    sample makes every count 0 and the matcher certifies itself two-sided while blind."""
    assert PLANTED_BAD.count("\\") == 2, (
        "known-bad must carry exactly one real backslash per newline literal (two total)")
    assert PLANTED_NEAR_MISS_NO_TAIL.count("\\") == 1
    assert JOIN_TAIL_IDIOM.pattern.count("\\\\") == 4, (
        "the pattern needs a DOUBLED backslash in each of its four newline-literal "
        "alternatives to match a literal backslash-n in source text")


def _planted_tree(root, copies):
    """A synthetic src-shaped tree of 9 modules, `copies` of which carry the idiom."""
    root.mkdir(parents=True)
    for index in range(9):
        body = PLANTED_BAD if index < copies else PLANTED_GOOD
        (root / f"mod{index}.py").write_text(body + "\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "mod0.py").write_text(PLANTED_BAD + "\n", encoding="utf-8")
    return root


def test_census_walk_is_two_sided_over_a_whole_tree(tmp_path):
    """Behaviors 4-6 for the DOMAIN WALK, not just the regex: the census must fire on a
    planted second copy, or behavior 4 passing over `src/` is health it never measured."""
    files, hits = _census_in(_planted_tree(tmp_path / "one", copies=1))
    assert len(files) == 9 and sum(hits.values()) == 1 and list(hits) == ["mod0.py"]

    files, hits = _census_in(_planted_tree(tmp_path / "two", copies=2))
    assert len(files) == 9, "`__pycache__` leaked into the domain"
    assert sum(hits.values()) == 2, (
        "a second copy of the idiom did NOT raise the census count; behavior 4 would "
        f"pass with the duplicate still present: {hits}")

    files, hits = _census_in(_planted_tree(tmp_path / "none", copies=0))
    assert len(files) == 9 and hits == {}


# --------------------------------------------------------------------------------------
# Behaviors 7 and 8 -- the unused-import oracle.
# --------------------------------------------------------------------------------------

def _names_in_quoted_annotation(text):
    """Name loads inside a QUOTED annotation. An unparseable annotation string is
    SKIPPED rather than raised on: a brake that dies on odd-but-legal source is a
    fail-closed brake."""
    try:
        parsed = ast.parse(text, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}


def _annotation_string(node):
    """The string body of a quoted annotation on `node`, or None."""
    candidate = None
    if isinstance(node, ast.arg):
        candidate = node.annotation
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        candidate = node.returns
    elif isinstance(node, ast.AnnAssign):
        candidate = node.annotation
    if isinstance(candidate, ast.Constant) and isinstance(candidate.value, str):
        return candidate.value
    return None


def unused_imports(source):
    """Imported local names that are never loaded, sorted.

    Imported names honour `asname` and skip `import *` (a star import binds names this
    oracle cannot see, so it must never be reported). Subtracted: `ast.Name` LOADS ONLY
    -- an attribute access on an imported module is already a Name load of the module,
    so also crediting `ast.Attribute` names is pure over-credit and blinds the oracle to
    an imported `confidence` shadowed by an `obj.confidence` read -- plus `__all__`
    string entries (a re-export is a use) and `annotations` (the `__future__` import is
    a compiler directive, never a load).
    """
    tree = ast.parse(source)
    imported, loaded, exported, annotation_strings = [], set(), set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported.append(alias.asname or alias.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded.add(node.id)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Name) and target.id == "__all__"
                        and isinstance(node.value, (ast.List, ast.Tuple))):
                    exported |= {element.value for element in node.value.elts
                                 if isinstance(element, ast.Constant)
                                 and isinstance(element.value, str)}
        text = _annotation_string(node)
        if text is not None:
            annotation_strings.append(text)
    for text in annotation_strings:
        loaded |= _names_in_quoted_annotation(text)
    return sorted({name for name in imported
                   if name not in loaded and name not in exported
                   and name != "annotations"})


def _modules():
    return sorted(p for p in SRC_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_module_imports_a_name_it_never_loads():
    """Behavior 7. Measured before this iteration: cli.py -> ['confidence', 'priority'],
    every other module -> []."""
    modules = _modules()
    offenders = {path.name: names for path in modules
                 if (names := unused_imports(path.read_text(encoding="utf-8")))}
    assert offenders == {}, (
        f"{len(offenders)} of {len(modules)} module(s) under src/agent_gap_radar/ import "
        f"a name they never load: {offenders}")


def test_unused_import_oracle_domain_is_non_empty_and_reported():
    """Behavior 6, applied to the oracle's own domain -- 11 modules today."""
    modules = _modules()
    assert len(modules) >= 8, (
        f"unused-import oracle walked only {len(modules)} module(s); a collapsed domain "
        "reports clean without measuring anything")


#: Behavior 8 -- known-bad samples the oracle MUST flag.
UNUSED_FROM_IMPORT = "from .scoring import confidence\n\n\ndef f():\n    return 1\n"
UNUSED_ALIASED_IMPORT = "import json as j\n\n\ndef f():\n    return 1\n"
#: The confounder the real file carries: the imported name also appears as an ATTRIBUTE
#: read. An oracle that credits `ast.Attribute` names reports this CLEAN.
UNUSED_SHADOWED_BY_ATTRIBUTE = (
    "from .scoring import confidence\n\n\ndef f(gap):\n    return gap.confidence\n")

#: Behavior 8 -- known-good samples the oracle MUST stay silent on.
REEXPORTED_VIA_DUNDER_ALL = "from .models import Gap\n\n__all__ = ['Gap']\n"
ANNOTATION_ONLY_IMPORT = "import pathlib\n\n\ndef f(p: pathlib.Path):\n    return p\n"
QUOTED_FORWARD_REFERENCE = "from .models import Gap\n\n\ndef f(g: 'Gap'):\n    return g\n"
QUOTED_RETURN_ANNOTATION = "from .models import Gap\n\n\ndef f(x) -> 'Gap':\n    return x\n"
QUOTED_ANNASSIGN = "from .models import Gap\n\ng: 'Gap' = None\n"
STAR_IMPORT = "from .models import *\n\n\ndef f():\n    return 1\n"
FUTURE_ANNOTATIONS = "from __future__ import annotations\n\n\ndef f():\n    return 1\n"


@pytest.mark.parametrize(
    "sample,expected",
    [(UNUSED_FROM_IMPORT, ["confidence"]),
     (UNUSED_ALIASED_IMPORT, ["j"]),
     (UNUSED_SHADOWED_BY_ATTRIBUTE, ["confidence"]),
     (REEXPORTED_VIA_DUNDER_ALL, []),
     (ANNOTATION_ONLY_IMPORT, []),
     (QUOTED_FORWARD_REFERENCE, []),
     (QUOTED_RETURN_ANNOTATION, []),
     (QUOTED_ANNASSIGN, []),
     (STAR_IMPORT, []),
     (FUTURE_ANNOTATIONS, [])],
    ids=["known-bad-unused-from-import", "known-bad-aliased-import",
         "known-bad-shadowed-by-attribute", "known-good-dunder-all-reexport",
         "known-good-annotation-only-import", "known-good-quoted-forward-reference",
         "known-good-quoted-return-annotation", "known-good-quoted-annassign",
         "known-good-star-import-skipped", "known-good-future-annotations"])
def test_unused_import_oracle_is_two_sided(sample, expected):
    """Behavior 8 -- both directions, on shapes this repo does not currently contain."""
    assert unused_imports(sample) == expected, (
        f"oracle returned {unused_imports(sample)}, expected {expected}")


def test_unused_import_oracle_survives_an_unparseable_annotation():
    """Behavior 8 -- an annotation string that is not valid Python is SKIPPED, so the
    oracle degrades to 'not credited as a load' instead of raising."""
    sample = "from .models import Gap\n\n\ndef f(g: 'Gap[[['):\n    return g\n"
    assert unused_imports(sample) == ["Gap"], (
        "an unparseable quoted annotation must be skipped, not raised on")


def test_taxonomy_is_deterministic_across_repeated_invocations(capsys):
    """Behaviors 1-3 as a STATEFULNESS probe, and the reason it earns its place: the spec
    records that the substituted renderer MUTATES the list it is handed (it pops trailing
    blanks in place). That is harmless only while the list is rebuilt per call, so a
    second invocation returning different bytes is the observable signature of the risk.
    The quality bar's word is `deterministic`, so this is a published property, not a
    guess."""
    assert main(["taxonomy"]) == 0
    first = capsys.readouterr().out
    assert main(["taxonomy"]) == 0
    second = capsys.readouterr().out
    assert first == second, (
        "`radar taxonomy` is not byte-stable across two calls in one process: the "
        f"second run produced {len(second.encode())} bytes against {len(first.encode())}")
    assert second.endswith("\n") and not second.endswith("\n\n"), (
        "the one-newline tail did not survive a repeated invocation")
