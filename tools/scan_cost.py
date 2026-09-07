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

THE LIBRARY IS OBSERVED, NEVER CHANGED. The counters are installed by rebinding three
module globals that `agent_gap_radar.checks` already publishes as substitution seams
(`evaluate`, `_read`, `required_literals`) and restored in a `finally`, so a scan that
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
directory, or a register that will not load).
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import pathlib
import sys
from collections.abc import Callable, Iterator

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from agent_gap_radar import checks, registry, render  # noqa: E402  (path set above)
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
_DECODES = "decode calls"
_DECODED_PATHS = "distinct decoded paths"
_PROOFS = "literal-set proofs"
_PROVED_SET = "proofs that proved a set"
_PROVED_NOTHING = "proofs that proved nothing"
_DOMAIN_LABELS: tuple[str, ...] = (
    _GAP_RECORDS, _EVALUATIONS, _DECODES, _DECODED_PATHS,
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
    """

    evaluation_keys: list[tuple[object, ...]] = dataclasses.field(default_factory=list)
    decode_calls: int = 0
    decoded: set[pathlib.Path] = dataclasses.field(default_factory=set)
    literal_proofs: int = 0
    literal_sets: int = 0


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
    """Install counting wrappers over the three `checks` seams, and always restore them.

    The wrappers are installed as MODULE GLOBALS of `checks`, which is this repo's settled
    substitution convention (`checks.py` names it at its own call sites): the content
    branch looks `_read` and `required_literals` up at call time, and `evaluate` recurses
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
    original_literals = checks.required_literals

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
        return original_evaluate(rule, target, exclude_tests, boolean_only=boolean_only)

    def counting_read(path: pathlib.Path) -> str | None:
        # Counts the SEAM's calls, not `_decode`'s: `_read` is memoised inside a scan's
        # `read_cache_scope`, so calls minus distinct paths is exactly what that cache
        # saved, and both numbers are published rather than blended into one.
        counters.decode_calls += 1
        counters.decoded.add(path)
        return original_read(path)

    def counting_literals(pattern: str) -> frozenset[str] | None:
        counters.literal_proofs += 1
        proved = original_literals(pattern)
        if proved is not None:
            counters.literal_sets += 1
        return proved

    checks.evaluate = counting_evaluate
    checks._read = counting_read
    checks.required_literals = counting_literals
    try:
        yield
    finally:
        checks.evaluate = original_evaluate
        checks._read = original_read
        checks.required_literals = original_literals


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
    """
    gaps = registry.load_all(gaps_dir)
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
    parser = argparse.ArgumentParser(
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
