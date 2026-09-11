#!/usr/bin/env python3
"""Count what one real `radar scan` costs, in COUNTS -- never in seconds.

Ten roadmap rows are priced by figures a scout produced in a throwaway script that was
then deleted: an `rg -l` sweep of `src/` and `tools/` for `perf_counter`, `time.time`,
`timeit` and `profile` returns ZERO files. What that costs is not milliseconds, it is
WRONG ANSWERS THAT SURVIVE. One open row has now been priced three times in three
non-comparable units, and the newest of the three would have shipped a memo keyed on a
component the same run shows is not constant. This file is the register's own
"harder to corrupt" rule -- schema gates, determinism, duplicate detection -- turned on
the tool's OWN cost claims: re-derivable on demand, committed, and reading the live
library rather than a copy of it.

COUNTS, NOT SECONDS, and that is the design rather than a simplification. A duration is
not reproducible on another machine, or on this one under load, so a committed document
carrying one decays into a false claim while looking precise, and a test pinning it either
flakes or pins nothing. Counts are contention-immune: the same target and the same
register yield the same integers anywhere, so this document is diffable and its
determinism is a property a test can actually assert.

NOTHING IS COMMITTED BY THIS TOOL. It writes a document to stdout and never into the
repo. A committed census decays exactly like the stale figures this file exists to
replace, and it would decay silently, because nothing recomputes it.

THE LIBRARY IS OBSERVED, NEVER CHANGED. The counters are installed by rebinding four
module globals that `agent_gap_radar.checks` already reaches through a CALL-TIME global
lookup, which is this repo's settled substitution convention (`evaluate`, `_read`,
`required_literal_sets`, `iter_files`), and restored in a `finally`, so a scan that
raises cannot leave a counting wrapper installed for the rest of the process. That
`finally` is not politeness: under `pytest -n auto` a leaked wrapper would keep counting
into a dead census while every later test in that worker ran through it.

NO PATH IS EVER PUBLISHED. This repository is public, and the two things this tool holds
that could leak an absolute machine path are the target directory and the decoded file
paths -- so neither output form carries any path at all. Paths are used as CACHE KEYS and
counted; the document publishes only how MANY there were.

Usage:
    python3 tools/scan_cost.py [--target DIR] [--gaps DIR] [--json]

Exit codes: 0 the census was emitted, 2 a usage error (a --target or --gaps that is not a
directory, a register that will not load, or a register holding zero records).
"""

from __future__ import annotations

import contextlib
import dataclasses
import pathlib
import sys
from collections.abc import Callable, Iterator

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from agent_gap_radar import checks, registry, render  # noqa: E402  (path set above)
# Refusals speak the `Error: ` vocabulary this repo publishes rather than argparse's
# `<prog>: error: ...`; the class docstring carries the argument.
from agent_gap_radar.cli import PublishedErrorParser  # noqa: E402
from agent_gap_radar.models import Gap  # noqa: E402
from agent_gap_radar.registry import RegistryError  # noqa: E402
from agent_gap_radar.scan import ScanResult, scan  # noqa: E402

#: A scan: takes the loaded register and a target, returns its result. `census` takes one
#: of these as a SEAM, which is what makes the restore-on-raise promise in this module's
#: docstring provable offline -- a substituted scan that raises drives the `finally` with
#: no need to corrupt a real target.
_ScanFn = Callable[[list[Gap], pathlib.Path], ScanResult]

#: The two rule kinds whose `evaluate` branch reads files and runs regexes. They are the
#: only kinds counted, because they are the only ones that cost anything measured here;
#: the combinators (`any_of`, `all_of`, `not`) recurse into them and are counted through
#: their children, and counting a combinator too would double-count one file pass.
_CONTENT_KINDS = frozenset({"content_matches", "content_absent"})

#: The COMPLETE evaluation key, in the order it is recorded: every argument that can
#: change what a content rule ANSWERS. `boolean_only` is a member for a reason a memo
#: author must not have to rediscover -- a `boolean_only=True` evaluation may leave its
#: file loop at the first hit, so answering a `boolean_only=False` caller from that entry
#: returns a silently TRUNCATED location list, which is the fail-open this key exists to
#: make visible rather than cheap.
_KEY_FIELDS: tuple[str, ...] = (
    "target", "kind", "pattern", "globs", "exclude_tests", "boolean_only")

#: label -> the fields DROPPED from the complete key, published in this order. Each
#: degraded row prices one candidate memo key: dropping a field can only MERGE keys, so a
#: row whose count is higher than `complete`'s is a memo that would answer one caller from
#: another caller's entry. The rows are DISPLAYED rather than filtered because the whole
#: point is to show which key is unsafe, not to hide it.
_KEYINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("complete", ()),
    ("without boolean_only", ("boolean_only",)),
    ("without exclude_tests", ("exclude_tests",)),
    ("without kind", ("kind",)),
)

#: The domain and read labels, in published order. Held ONCE because both output forms use
#: each string verbatim -- as a Markdown row label and as a JSON key -- and two spellings
#: of one label is the duplicated-invariant shape this product has already paid to fix
#: twice. A cross-form test then compares one list against itself rather than two lists
#: that agree only while someone keeps them agreeing.
_GAP_RECORDS = "gap records"
_EVALUATIONS = "content evaluations"
_DOMAIN_FILES = "files in content domains"
_DECODES = "decode calls"
_DECODED_PATHS = "distinct decoded paths"
_PROOFS = "literal-set proofs"
_PROVED_SET = "proofs that proved a set"
_PROVED_NOTHING = "proofs that proved nothing"
#: `_DOMAIN_FILES` sits between the evaluation count and the decode count because the
#: three rows are ONE funnel in that order -- evaluations, the files those evaluations were
#: handed, the reads they actually made -- and a reader who has to jump a row to compare a
#: numerator with its denominator infers the amplification instead of being shown it.
_DOMAIN_LABELS: tuple[str, ...] = (
    _GAP_RECORDS, _EVALUATIONS, _DOMAIN_FILES, _DECODES, _DECODED_PATHS,
    _PROOFS, _PROVED_SET, _PROVED_NOTHING)

#: The two columns of the keying table, also held once and also used as JSON keys.
_DISTINCT = "distinct keys"
_DUPLICATES = "duplicate calls"

#: Named in the machine form so a consumer can tell this payload from the register's own
#: documents without matching on the presence of a key.
_SCHEMA = "scan-cost-census/1"

#: Spelled as a constant so the machine form's one non-integer leaf is named in one place.
_SCHEMA_KEY = "schema"


@dataclasses.dataclass
class _Counters:
    """The raw tallies the installed seams fill. Mutable and private on purpose.

    `evaluation_keys` keeps the full key per call rather than a set, because every
    degraded keying in `_KEYINGS` is derived from the SAME recorded calls. Deriving them
    from one list is what makes `duplicate calls` comparable across rows; four independent
    sets would be four samples of four scans.

    `decoded` holds paths, which is why nothing here is ever rendered: a path is a cache
    key in this module and a leak in a public document.

    `content_domain_files` is a SUM, and `kind_stack` is the whole reason that sum can be
    ATTRIBUTED: `iter_files` is reached from the content branch and from the
    `file_exists`/`file_absent` branch, and its arguments do not say which caller asked, so
    an enumeration is credited to the innermost rule kind `evaluate` is inside -- a kind the
    evaluation wrapper already holds. A stack and not one field, because `evaluate` recurses
    through the combinators, so the kind that asked is the LAST one pushed and the frames
    above it are still open.
    """

    evaluation_keys: list[tuple[object, ...]] = dataclasses.field(default_factory=list)
    decode_calls: int = 0
    decoded: set[pathlib.Path] = dataclasses.field(default_factory=set)
    literal_proofs: int = 0
    literal_sets: int = 0
    content_domain_files: int = 0
    kind_stack: list[object] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Census:
    """One scan's counts. Every value is an `int`, and there is no duration anywhere.

    Two mappings rather than a flat one, because the keying rows are a TABLE -- one row
    per candidate memo key -- and flattening them would spell each label twice, once per
    column.
    """

    domain: dict[str, int]
    keyings: dict[str, dict[str, int]]


@contextlib.contextmanager
def _observing(counters: _Counters) -> Iterator[None]:
    """Install counting wrappers over the four `checks` seams, and always restore them.

    The wrappers are installed as MODULE GLOBALS of `checks`, which is this repo's settled
    substitution convention (`checks.py` names it at its own call sites): the content
    branch looks `_read` and `required_literal_sets` up at call time, and `evaluate`
    recurses
    through its own global, so a combinator's children are counted too without this module
    knowing anything about the recursion.

    Restoration is in a `finally` and is the reason this is a context manager rather than
    two helper calls. A scan raises on an unknown rule kind, an invalid pattern and a
    vacuous `all_of` -- all three are deliberate refusals in `checks.py`, so a raising scan
    is the NORMAL case for a target this tool is pointed at, not an exotic one. Leaving a
    wrapper installed after one would make every later call in the process count into a
    census nobody reads, and under `pytest -n auto` those later calls belong to other
    tests.
    """
    original_evaluate = checks.evaluate
    original_read = checks._read
    original_literals = checks.required_literal_sets
    original_iter_files = checks.iter_files

    def counting_evaluate(rule: dict, target: pathlib.Path,
                          exclude_tests: bool = False, *,
                          boolean_only: bool = False) -> checks.RuleHit:
        kind = rule.get("kind")
        if kind in _CONTENT_KINDS:
            # Recorded BEFORE delegating, so a rule that raises inside the branch is still
            # counted as a call that was made. The globs list is frozen to a tuple because
            # a key has to be hashable, and it is read here rather than mutated.
            counters.evaluation_keys.append((
                target, kind, rule.get("pattern"), tuple(rule.get("globs") or ()),
                exclude_tests, boolean_only))
        # The kind stays on the stack for the whole delegation, so an enumeration made
        # inside this branch is credited to it, and it is popped in a `finally` for the same
        # reason the seams are restored in one: a rule that raises must not leave its kind
        # on the stack, crediting the NEXT rule's enumeration to a branch that is over.
        counters.kind_stack.append(kind)
        try:
            return original_evaluate(rule, target, exclude_tests, boolean_only=boolean_only)
        finally:
            counters.kind_stack.pop()

    def counting_read(path: pathlib.Path) -> str | None:
        # Counts the SEAM's calls, not `_decode`'s: `_read` is memoised inside a scan's
        # `read_cache_scope`, so calls minus distinct paths is exactly what that cache
        # saved, and both numbers are published rather than blended into one.
        counters.decode_calls += 1
        counters.decoded.add(path)
        return original_read(path)

    def counting_iter_files(target: pathlib.Path, globs: list[str],
                            exclude_tests: bool = False) -> list[pathlib.Path]:
        files = original_iter_files(target, globs, exclude_tests)
        if counters.kind_stack and counters.kind_stack[-1] in _CONTENT_KINDS:
            # The list a content rule's read/regex loop is HANDED, summed over the
            # evaluations that asked for one. Counted here rather than derived from the
            # register, because a domain is a fact about the TARGET tree -- two rules
            # carrying the same globs enumerate the same files, and a static walk of the
            # records would price that domain once instead of once per evaluation.
            counters.content_domain_files += len(files)
        return files

    def counting_literals(pattern: str) -> tuple[frozenset[str], ...] | None:
        counters.literal_proofs += 1
        proved = original_literals(pattern)
        if proved is not None:
            counters.literal_sets += 1
        return proved

    checks.evaluate = counting_evaluate
    checks._read = counting_read
    checks.required_literal_sets = counting_literals
    checks.iter_files = counting_iter_files
    try:
        yield
    finally:
        checks.evaluate = original_evaluate
        checks._read = original_read
        checks.required_literal_sets = original_literals
        checks.iter_files = original_iter_files


def _tally(gap_records: int, counters: _Counters) -> Census:
    """Turn raw tallies into the published counts, deriving rather than re-counting.

    `proofs that proved nothing` is a SUBTRACTION and not a second tally. The two arms of
    the extractor's `is not None` test partition its calls, so counting both arms
    separately would be two numbers that add up only while both increments stay correct --
    the duplicated-invariant shape again. Same argument for `duplicate calls`, which is
    the call count minus that row's distinct keys by construction: a reader never has to
    trust that two counters agree.
    """
    evaluations = len(counters.evaluation_keys)
    domain = {
        _GAP_RECORDS: gap_records,
        _EVALUATIONS: evaluations,
        _DOMAIN_FILES: counters.content_domain_files,
        _DECODES: counters.decode_calls,
        _DECODED_PATHS: len(counters.decoded),
        _PROOFS: counters.literal_proofs,
        _PROVED_SET: counters.literal_sets,
        _PROVED_NOTHING: counters.literal_proofs - counters.literal_sets,
    }

    keyings: dict[str, dict[str, int]] = {}
    for label, dropped in _KEYINGS:
        unknown = tuple(field for field in dropped if field not in _KEY_FIELDS)
        if unknown:
            # A typo in `_KEYINGS` would otherwise render as a row identical to `complete`
            # -- a keying that silently drops nothing, reported as one that drops a field,
            # which is a false safety claim about a memo key.
            raise ValueError(f"keying {label!r} drops unknown key field(s): {unknown}")
        kept = tuple(i for i, field in enumerate(_KEY_FIELDS) if field not in dropped)
        distinct = len({tuple(key[i] for i in kept) for key in counters.evaluation_keys})
        keyings[label] = {_DISTINCT: distinct, _DUPLICATES: evaluations - distinct}

    return Census(domain=domain, keyings=keyings)


def census(target: pathlib.Path | str, gaps_dir: pathlib.Path | str,
           scan_fn: _ScanFn | None = None) -> Census:
    """Count one real scan of `target` against the register in `gaps_dir`.

    `scan_fn` is a SEAM resolved at CALL time and never bound as a signature default: a
    default argument is evaluated once at definition, so `scan_fn=scan` would capture this
    module's import forever and silently ignore any later substitution of it -- a failure
    that reads as an unmoving census rather than as an unusable seam.

    Raises whatever the register loader or the scan raises. Refusing to swallow is the
    point: a census over a register that half-loaded, or over a scan that died in the
    middle, is a smaller set of counts printed with the same authority as a complete one.

    A register holding ZERO records is refused by the same argument, one step further in,
    and the refusal is HERE rather than in `main` so that every caller of the library gets
    it. An empty register yields a census whose every count is `0` at exit 0, and each
    property this document publishes then holds VACUOUSLY -- `duplicate calls` is `0 - 0`
    under all four keyings, and the complete key "dominates" every degraded one by tying
    with it -- so an all-zero census is indistinguishable from a scan that genuinely had no
    work to do, while carrying the authority of a real measurement. It is also the shape a
    reader hits by accident: `--gaps` resolves under `--target`, so pointing it at a tree
    whose records live elsewhere loads nothing at all. The message names no path, because
    this repository is public and a register argument is an absolute path in most hands.
    """
    gaps = registry.load_all(gaps_dir)
    if not gaps:
        raise ValueError("no gap records in the register: a census over zero records "
                         "counts zero of everything, which reads as a clean scan")
    counters = _Counters()
    fn = scan_fn or scan
    with _observing(counters):
        fn(gaps, pathlib.Path(target))
    return _tally(len(gaps), counters)


def render_markdown(result: Census) -> str:
    """The human document: two tables, no prose restating any number in them.

    Reaches `render.table` and `render.document` rather than formatting pipes here,
    because the one-newline tail is a PUBLISHED guarantee of this package and a second
    implementation of it in a tool is a second thing to keep true.
    """
    lines = [
        "# scan cost census", "",
        "Counts from one scan of one target against one register. No value below is a "
        "duration: a duration is not reproducible on another machine, so a committed one "
        "decays while still looking precise.", "",
        "The domain row is the total its content read loops were HANDED, so it bounds the "
        "decode row beneath it, and the difference between the two is what the first-hit "
        "exit and the file cap never reached -- NOT what the decode memo saved. A memo hit "
        "is a call that was still made, so the memo's saving is the decode row read "
        "against the distinct-path row.", "",
    ]
    lines += render.table(
        ["fact", "count"],
        [[label, str(result.domain[label])] for label in _DOMAIN_LABELS])
    lines += [
        "", "## Evaluation keying", "",
        "One row per candidate memo key over the same recorded calls. The right-hand "
        "column is the upper bound on what a memo keyed that way could skip -- and any "
        "row that beats the first one buys that saving by answering one caller from "
        "another caller's entry, under different flags.", "",
    ]
    lines += render.table(
        ["keying", _DISTINCT, _DUPLICATES],
        [[label, str(result.keyings[label][_DISTINCT]),
          str(result.keyings[label][_DUPLICATES])] for label, _ in _KEYINGS])
    return render.document(lines)


def _in_sorted_key_order(obj: object) -> object:
    """Rebuild every mapping with its keys INSERTED in sorted order, recursively.

    `render.json_document` pins `sort_keys=False` deliberately, so that every register
    payload publishes its keys in the order its author wrote them. This document wants the
    opposite -- sorted keys, so a diff of two censuses cannot show a field moving -- and
    the way to get it without a second `json.dumps` in this repo is to hand that renderer
    a dict whose insertion order IS sorted order.
    """
    if isinstance(obj, dict):
        return {key: _in_sorted_key_order(obj[key]) for key in sorted(obj)}
    return obj


def render_json(result: Census) -> str:
    """The machine document: one object, sorted keys, every leaf an `int` or a `str`.

    No leaf is a float, and that is a contract rather than a coincidence of this data: a
    float is how a duration would arrive, and a consumer that can assert the absence of
    one never has to read the labels to know it is not being handed a timing.
    """
    payload: dict[str, object] = {_SCHEMA_KEY: _SCHEMA, "keyings": result.keyings}
    payload.update(result.domain)
    return render.json_document(_in_sorted_key_order(payload))


def main(argv: list[str]) -> int:
    """Emit the census, or refuse with one line on stderr and exit 2.

    Both directories are checked HERE, before any work, in the same sentence shape the
    other tools in this directory use. The scan and the loader would each raise on a bad
    path, but their messages carry a resolved path and an exception's noun; a consumer
    matching `Error: ` deserves one line whichever argument was wrong.

    `--gaps` defaults to `gaps` UNDER THE TARGET rather than under the working directory.
    A cwd-relative default would make one command line produce different censuses
    depending on where it ran, which would turn the determinism promise above into a claim
    about the shell.
    """
    parser = PublishedErrorParser(
        prog="scan_cost.py",
        description="Count what one radar scan costs, in counts and never in seconds.")
    parser.add_argument("--target", default=".",
                        help="directory to scan (default: the working directory)")
    parser.add_argument("--gaps", default=None,
                        help="register directory (default: 'gaps' under --target)")
    parser.add_argument("--json", action="store_true",
                        help="emit the machine form: one JSON object, keys sorted")
    args = parser.parse_args(argv[1:])

    target = pathlib.Path(args.target)
    if not target.is_dir():
        sys.stderr.write(f"Error: not a directory: {target}\n")
        return 2

    gaps_dir = pathlib.Path(args.gaps) if args.gaps else registry.gaps_dir(target)
    if not gaps_dir.is_dir():
        sys.stderr.write(f"Error: not a directory: {gaps_dir}\n")
        return 2

    try:
        result = census(target, gaps_dir)
    except (RegistryError, OSError, ValueError) as exc:
        # One line, one prefix, exit 2 -- the same refusal shape as the two checks above,
        # so a caller never has to tell a bad argument apart from a bad register by the
        # SHAPE of the failure. A traceback on stdout would also break the promise that
        # stdout carries only the document.
        sys.stderr.write(f"Error: {exc}\n")
        return 2

    sys.stdout.write(render_json(result) if args.json else render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
