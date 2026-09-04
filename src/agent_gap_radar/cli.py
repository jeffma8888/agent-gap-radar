"""radar -- command line entry point.

Conventions (shared with sibling tools): errors go to stderr prefixed with
"Error: " and exit 2; stdout carries only the document, so output is pipeable.
"Pipeable" is the reason `EXIT_BROKEN_PIPE` exists: a reader that stops reading is
the consumer's own decision, not a defect in the register, so it gets a code of
its own and a silent stderr rather than this module's error vocabulary.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import NoReturn

from . import __version__
from .diff import diff_json, diff_registers, render_diff
from .models import Gap
from .prd import render_prd
from .registry import RegistryError, gaps_dir, load_all, load_one
from .render import document, gap_brief, json_document, radar_report
from .scan import gate_verdict, render_scan, scan, scan_json, select_for_prd
from .scoring import (CONFIDENCE_FLOOR_DEFAULT, below_floor,
                      promotion_options, rank, strongest_source)
from .taxonomy import (GAP_TYPES, LAYERS, SOURCE_CLASSES, SOURCE_WEIGHTS,
                       STATUS_GLOSSES, STATUSES, citable_statuses,
                       terminal_statuses)


def _status_list(statuses: tuple[str, ...]) -> str:
    """Render one side of the citation partition as backticked names.

    `(none)` for an empty side rather than an empty string: patching `STATUSES` can
    legitimately empty either side, and a bare `-- ` would leave trailing whitespace on a
    published line, which the byte-stability bar treats as output the renderer owns.
    """
    return ", ".join(f"`{s}`" for s in statuses) if statuses else "(none)"


def _resolve(path_arg: str) -> pathlib.Path:
    """Accept either a repo root (containing gaps/) or the gaps dir itself."""
    p = pathlib.Path(path_arg).expanduser()
    candidate = gaps_dir(p)
    return candidate if candidate.is_dir() else p


#: Every exit code `main()` can return, each named so no call site spells an
#: integer. `docs/CONSUMER_CONTRACT.md` publishes exactly this set under
#: `## Exit codes`, and a test asserts the document's table EQUALS `EXIT_CODES` in
#: both directions -- so a fourth code cannot ship undocumented, and a row for a
#: code the CLI cannot produce cannot survive either.
#:
#: `1` was held unused by iteration 25 for exactly one purpose, and this is it:
#: `EXIT_GAPS_PRESENT` below. The reservation is now SPENT, not free.
EXIT_OK = 0
#: The floor-gated verdict `scan --exit-code` reports: this target exhibits at
#: least one PRESENT gap whose EVIDENCE clears the confidence floor. OPT-IN, so
#: no verb can return it unless a caller asked a verdict question -- a code that
#: appeared by default would turn every existing `scan` consumer red on the day
#: it shipped. Distinct from `EXIT_ERROR` because nothing went wrong: the tool
#: answered, and the answer is that this target has an above-floor gap.
EXIT_GAPS_PRESENT = 1
EXIT_ERROR = 2
#: The shell's own 128+SIGPIPE, so `head`, `grep -q` and `less` see the code they
#: already expect from a pipeline they closed. Chosen over `1` for that reason
#: back when `1` was still being held; see above.
EXIT_BROKEN_PIPE = 141
#: Numeric order, which is the order the published table lists them in too.
EXIT_CODES: tuple[int, ...] = (EXIT_OK, EXIT_GAPS_PRESENT, EXIT_ERROR,
                               EXIT_BROKEN_PIPE)


def _fail(msg: str) -> int:
    sys.stderr.write(f"Error: {msg}\n")
    return EXIT_ERROR


#: Marker appended to a row whose record sits below the confidence floor. A
#: SUFFIX, not a new column, so the leading `id / p= / c= / title` field order a
#: consumer already cuts on stays byte-stable.
BELOW_FLOOR_MARKER = "  [below-floor]"

#: One row of `radar list`: the scored record plus whether it is below the floor.
ListRow = tuple[Gap, float, int, bool]


def _list_rows(gaps: list[Gap], confidence_floor: int) -> list[ListRow]:
    """Every record, ranked rows first, then below-floor rows in id order.

    Deliberately ONE sequence rather than a ranked list plus a below-floor list.
    The register's single protected rule is that a below-floor record is
    displayed and never silently dropped, and handing a caller two collections is
    exactly how that drop gets re-created downstream: consuming only the first
    one looks like reading the ranking and is in fact hiding the research queue.
    Reuses `scoring.below_floor()`, so no second below-floor predicate exists.
    """
    return ([(g, pri, conf, False) for g, pri, conf in rank(gaps, confidence_floor)]
            + [(g, pri, conf, True)
               for g, pri, conf in below_floor(gaps, confidence_floor)])


def _list_text(rows: list[ListRow]) -> str:
    """Line-oriented form: one line per record, below-floor rows flagged.

    Builds the row lines and hands them to the PUBLISHED `render.document()` rather
    than appending a newline per row. The per-row append was a THIRD private
    construction of the one-newline tail this product has already collapsed twice,
    and unlike the other two it was WRONG in the vacuous case: over zero rows it
    returned the empty string, so `list` was the single verb that could exit 0
    having written no bytes at all, against a guarantee `VISION.md` publishes for
    every renderer. Routing here does not DECIDE that question -- `document([])`
    decided it long ago -- it stops this call site from answering it privately.

    Byte-identical on any non-empty register: no row can equal "" (every row opens
    with a GAP-NNN id, which the schema requires), so `document`'s trailing-blank
    normalisation has nothing to strip, and joining on one newline plus a tail is
    the same string as appending one newline per row. The list is built fresh here
    because `document` pops from the sequence it is handed.
    """
    return document([
        f"{gap.id}  p={pri:>4.1f}  c={conf}  {gap.title}"
        + (BELOW_FLOOR_MARKER if is_below else "")
        for gap, pri, conf, is_below in rows
    ])


def _needs(gap: Gap, is_below: bool, confidence_floor: int) -> list[str] | None:
    """The prescription for one record: what one further citation would have to be.

    `null` ABOVE the floor is a DECIDED answer, not an omission and not
    `promotion_options`' own reply. That function is total, so it answers an
    at-floor record with the weakest positive class -- every class already
    satisfies the floor, so the cheapest one wins -- and published verbatim that
    answer reads as "this record needs a secondary summary" about a record that
    needs nothing. `null` says the question does not apply. It is the same call
    `render._needs_cell` already makes in prose for the human table, where an
    unreachable floor says so rather than rendering an empty cell.

    The key is emitted for every record either way, so a consumer reads the
    biconditional `needs is null <=> not below_floor` off the payload instead of
    having to distinguish "absent" from "nothing needed" -- an absent key is the
    one shape a gate cannot assert on.

    A list rather than the tuple `promotion_options` returns. `json.dumps` would
    emit either as an array, so this is not a correctness fix; it makes the
    payload builder hold only JSON-native values, which is what lets the whole
    document be compared against `json.loads` of itself without a shape caveat.
    Order is untouched -- ladder order, strongest rung first -- because the
    cheapest option a reader should reach for first is the one printed first.
    """
    return list(promotion_options(gap, confidence_floor)) if is_below else None


def _list_json(rows: list[ListRow], confidence_floor: int) -> str:
    """A stable record list for a machine consumer.

    A flat array with a `below_floor` boolean, not two arrays: the text marker
    can be scraped, but a boolean can be ASSERTED by a consumer's gate, which is
    where the never-drop invariant stops being prose and becomes checkable.
    Carries `priority` and `confidence` as distinct fields and never a blended
    score, matching `scan_json` -- a composite would launder the one distinction
    the register exists to preserve.

    `strongest_source` and `needs` are appended LAST, and both are DERIVED by
    calling `scoring` rather than re-deriving anything here: this module holds no
    second copy of the ladder order or of `SOURCE_WEIGHTS`, so a published
    prescription cannot disagree with the score it is prescribing for. They close
    the same gap on the machine surface that the markdown report's below-floor
    table already closed for a human: the payload used to publish the RESULT of
    the confidence derivation (an integer) and nothing about the ladder rung
    behind it or the remedy, so `tools/promote.py` -- the one door the register is
    fed through -- could see that a record was weak and never what would clear it,
    and the only alternative was to scrape a markdown table or re-implement
    `confidence()` across a repo boundary.

    `strongest_source` is published for EVERY record and not just the tail,
    because "what is this record's confidence derived FROM" is exactly as
    answerable above the floor as below it, and it is the register's core
    invariant made readable rather than a below-floor annotation.
    """
    payload = {
        "confidence_floor": confidence_floor,
        "counts": {
            "total": len(rows),
            "ranked": sum(1 for row in rows if not row[3]),
            "below_floor": sum(1 for row in rows if row[3]),
        },
        "records": [
            {
                "gap_id": gap.id,
                "title": gap.title,
                "layer": gap.layer,
                "gap_type": gap.gap_type,
                "status": gap.status,
                "priority": pri,
                "confidence": conf,
                "below_floor": is_below,
                "strongest_source": strongest_source(gap),
                "needs": _needs(gap, is_below, confidence_floor),
            }
            for gap, pri, conf, is_below in rows
        ],
    }
    return json_document(payload)


def _unknown_layer(layer: str) -> str:
    """The refusal for a `--layer` value outside the closed vocabulary.

    The accepted values are JOINED FROM `taxonomy.LAYERS`, so `cli.py` holds no
    second copy of a vocabulary that is meant to be debated in one place, and the
    message carries no COUNT of them -- a hand-maintained size of a machine-published
    vocabulary decays silently and then misleads with authority, which is the reason
    the contract's `radar taxonomy` cell already refuses to restate one.

    Naming every accepted value rather than just refusing is what makes a typo fixable
    without a second command, and it is affordable precisely because the vocabulary is
    CLOSED: an open label set could not be printed, which is the argument for closing
    it in the first place.
    """
    return (f"unknown layer '{layer}'; the layer vocabulary is closed: "
            + ", ".join(LAYERS))


def _select_layer(gaps: list[Gap], layer: str | None) -> list[Gap]:
    """Narrow the record DOMAIN to one layer, or hand it back untouched.

    Applied to the LOADED RECORDS, before `_list_rows`, and that ordering is the whole
    design of this filter rather than an implementation detail. `rank()`/`below_floor()`
    partitions whatever domain it is handed, so filtering upstream of it keeps ONE
    below-floor predicate in the product: a filtered listing cannot arrive at a
    different answer to "is this record below the floor" than the unfiltered one.
    Filtering rendered rows -- or a JSON payload after the fact -- would put an
    omission mechanism DOWNSTREAM of the single rule this register protects, which is
    exactly how a below-floor record gets dropped by a filter that never mentions the
    floor.

    Total by construction, which is what makes the per-layer documents a PARTITION of
    the register and not a sample of it: `models.Gap` validates `layer` against
    `taxonomy.LAYERS` at load, so every loaded record falls under exactly one layer and
    concatenating one document per layer reproduces the unfiltered line multiset.
    """
    return gaps if layer is None else [gap for gap in gaps if gap.layer == layer]


class _PublishedErrorParser(argparse.ArgumentParser):
    """An `ArgumentParser` whose refusals speak the vocabulary this tool publishes.

    argparse answers a STRUCTURAL refusal -- a missing positional, an unknown verb, an
    unparseable flag value, an unrecognized option -- with `<prog>: error: <message>`
    and exit 2. That code is the one `docs/CONSUMER_CONTRACT.md` publishes as "stderr's
    last non-empty line begins `Error: `", so the default spelling makes the promise
    FALSE on the most common failure a consumer can produce: a mistyped invocation. A
    consumer implementing the published rule literally gets an empty match on that whole
    failure class, and its own error report then says nothing at all.

    Not a new rule. `build_parser()` below already argues it, refusing `choices=LAYERS`
    because argparse "would refuse a bad value with ITS vocabulary on stderr and exit 2
    -- a code this module reserves for a refusal it explains in its own published
    `Error: ` line", and routing that one check through `_fail` instead. The decision was
    applied to exactly one flag and to no structural refusal; this applies it to every
    door at once.

    Installed on the TOP-LEVEL parser only. `add_subparsers` defaults its `parser_class`
    to `type(self)`, so all eight verbs inherit the override with no per-verb edit and no
    second place to keep in sync -- and a verb added later inherits it by construction
    rather than by someone remembering.
    """

    def error(self, message: str) -> NoReturn:
        """Keep the usage block, then refuse through the one published error site.

        The usage block is printed and printed FIRST rather than dropped, which is why
        the contract promises the LAST non-empty line rather than a single line: usage is
        the only place a caller learns the arity it got wrong, and three committed tests
        read it off stderr for exactly these argv shapes. Ordering it above the message
        keeps `Error: ` last, so a consumer reads one deterministic line.

        Routed through `_fail` rather than writing its own prefixed line, so the prefix
        keeps exactly ONE construction site in this package and a later change to the
        error channel cannot reach half of it. `_fail` also supplies the code, so no
        integer is spelled here either. Raises because argparse's contract for `error()`
        is that it never returns to its caller.
        """
        self.print_usage(sys.stderr)
        raise SystemExit(_fail(message))


def build_parser() -> argparse.ArgumentParser:
    parser = _PublishedErrorParser(
        prog="radar",
        description="Evidence-first gap radar for AI agent infrastructure.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    for name, help_text in [
        ("validate", "Validate every gap record; exit 2 on any problem."),
        ("list", "One line per gap: id, priority, confidence, title."),
        ("report", "Full ranked radar report (markdown)."),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("path", nargs="?", default=".")
        if name in ("list", "report"):
            p.add_argument("--floor", type=int, default=2,
                           help="confidence floor for the ranking (default 2)")
        if name == "list":
            p.add_argument("--json", action="store_true",
                           help="emit a stable record list for a machine "
                                "consumer")
            # No `choices=LAYERS` deliberately. argparse would refuse a bad
            # value with ITS vocabulary on stderr and exit 2 -- a code this
            # module reserves for a refusal it explains in its own published
            # `Error: ` line -- and the usage block it prints would carry the
            # whole layer list into every `list` usage message. Validated in
            # `_dispatch` instead, through `_fail`, so the one published error
            # site answers for it. "layer" leads the help text because argparse
            # wraps on whitespace and the word a reader greps for must survive
            # a narrow terminal.
            p.add_argument("--layer", default=None, metavar="L",
                           help="layer to narrow the listing to; one value "
                                "from the closed taxonomy that `radar "
                                "taxonomy` publishes")

    p_show = sub.add_parser("show", help="Full brief for one gap (markdown).")
    p_show.add_argument("gap_id")
    p_show.add_argument("path", nargs="?", default=".")

    p_prd = sub.add_parser("prd", help="Emit a build-loop prd.json for one gap.")
    p_prd.add_argument("path", nargs="?", default=".")
    p_prd.add_argument("--gap", dest="gap_id", default=None,
                       help="gap id (default: the top-ranked gap)")
    p_prd.add_argument("--project", default="agent-gap-radar")

    p_scan = sub.add_parser(
        "scan", help="Apply the register's checks to a target repo or service.")
    p_scan.add_argument("target", help="path to the repository/service to inspect")
    p_scan.add_argument("--gaps", default=".",
                        help="register location (default: current dir)")
    p_scan.add_argument("--json", action="store_true",
                        help="emit a stable object for a machine consumer")
    # `--prd` and `--exit-code` are MUTUALLY EXCLUSIVE, and argparse enforces it
    # rather than a branch silently preferring one. Both are floor-gated verdict
    # surfaces with CONTRADICTORY code vocabularies: `--prd` already answers "a
    # finding cleared the floor" with 0 (it built against it) and "none did" with
    # 2, while `--exit-code` answers the first with 1. Accepting the pair would
    # make one of them lose without saying so, and the losing direction is
    # fail-open -- a gate would read 0 over a target with above-floor gaps.
    # Refusing the pair costs a consumer nothing that works today: the pair is
    # not accepted at HEAD either, because the flag did not exist.
    verdict_surface = p_scan.add_mutually_exclusive_group()
    # "confidence floor" LEADS this help text deliberately. argparse wraps
    # help on whitespace, and a phrase the docs promise a reader will find
    # is broken by a line split; leading it survives any width above ~33
    # columns instead of only the default 80.
    verdict_surface.add_argument("--prd", action="store_true",
                                 help="confidence floor gated: emit a prd.json "
                                      "for the worst PRESENT finding that clears "
                                      "the floor, instead of the report")
    verdict_surface.add_argument("--exit-code", action="store_true",
                                 help="confidence floor gated: exit 1 when this "
                                      "target has an above-floor PRESENT gap, 0 "
                                      "when it has none; same document either way")

    p_diff = sub.add_parser(
        "diff", help="Report what changed between two register states.")
    # Two REQUIRED positionals. Deliberately unlike `list`/`show`/`report`, whose
    # `nargs="?" default="."` lets a consumer copying a documented invocation read
    # whichever register sits in its own working directory -- a silent wrong answer,
    # not an error. A diff with a defaulted side is that shape twice, and it would
    # compare a register against itself and report "nothing changed".
    p_diff.add_argument("old", help="register state to compare FROM")
    p_diff.add_argument("new", help="register state to compare TO")
    # Same help wording as `scan --json` deliberately: one machine surface should not
    # read as a different KIND of thing on a neighbouring verb. Not a verdict surface
    # and not mutually exclusive with anything -- `diff` has no `--exit-code`, so
    # there is no second floor-gated code vocabulary for this flag to contradict.
    p_diff.add_argument("--json", action="store_true",
                        help="emit a stable object for a machine consumer")

    sub.add_parser("taxonomy", help="Print the fixed vocabularies.")
    return parser


def _silence_stdout() -> None:
    """Point the process's stdout descriptor at the null device. Never raises.

    A broken pipe is answered by an exit code, but the undelivered bytes are still
    sitting in `sys.stdout`'s buffer, and CPython flushes `sys.stdout` during
    interpreter shutdown -- past every handler in this module. That second flush is
    what makes an unguarded run print `Exception ignored on flushing sys.stdout`
    and exit 120: the code below has already returned by then and cannot answer for
    it. So the fix has to happen at the FILE DESCRIPTOR the buffer will be flushed
    to, not at the exception, which is why this redirects rather than closes.

    Silent on failure on purpose, in both directions. An in-process consumer or a
    test double may have replaced `sys.stdout` with an object that has no real
    descriptor -- there is then no shutdown flush that can re-raise, so the absence
    is benign rather than something to report. And a guard that raises while
    handling a broken pipe would replace a quiet 141 with a traceback, which is the
    exact failure it exists to remove.
    """
    try:
        fd = sys.stdout.fileno()
    except (AttributeError, ValueError, OSError):
        # `io.UnsupportedOperation` (a StringIO double) subclasses both ValueError
        # and OSError, so it is covered without importing `io` for the name alone.
        return
    if not isinstance(fd, int):
        # A test double is under no obligation to return an int here, and a
        # `TypeError` out of `dup2` would escape the caller's `except
        # BrokenPipeError` and replace a quiet 141 with a traceback -- the exact
        # failure this guard exists to remove. No descriptor, nothing to redirect.
        return
    try:
        with open(os.devnull, "wb") as null:
            # dup2 duplicates onto `fd`, so `fd` outlives this block pointing at the
            # null device; closing `null` closes only the source descriptor.
            os.dup2(null.fileno(), fd)
    except OSError:
        return


def main(argv: list[str] | None = None) -> int:
    """Run one verb, absorbing a reader that stopped reading.

    The FLUSH is inside the guard, and that placement is the whole fix. Writing to a
    pipe fills the text layer's buffer and returns, so a document smaller than that
    buffer never touches the pipe until interpreter shutdown -- where a broken pipe
    is past every handler and CPython answers with 120 plus a line on the stderr this
    tool promises carries only `Error: `. Flushing here moves that failure back
    inside the `try`, where it can be answered with an exit code.

    Only `BrokenPipeError` is absorbed. A wider `except OSError` would swallow a
    genuine write failure -- a full disk, a revoked descriptor -- and report the
    consumer's own early exit for it, so every other `OSError` propagates unchanged.

    `SystemExit` from argparse (`--help`, `--version`, a usage error) is deliberately
    NOT caught: callers assert on it today, and it carries its own code.
    """
    try:
        code = _dispatch(argv)
        sys.stdout.flush()
        return code
    except BrokenPipeError:
        _silence_stdout()
        return EXIT_BROKEN_PIPE


def _dispatch(argv: list[str] | None = None) -> int:
    """Parse `argv` and run the named verb. Every return value is in `EXIT_CODES`.

    Split from `main()` so the broken-pipe guard wraps ALL nine `sys.stdout.write`
    sites plus argparse's own help write at once, instead of nine copies of the same
    `try`. A guard confined to the `if __name__` block would miss the packaged
    console script entirely, which is what a consumer actually runs.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return EXIT_OK

    if args.command == "taxonomy":
        out = ["# Taxonomy", "", "## Layers", ""]
        out += [f"- `{k}` -- {v}" for k, v in LAYERS.items()]
        out += ["", "## Gap types", ""]
        out += [f"- `{k}` -- {v}" for k, v in GAP_TYPES.items()]
        out += ["", "## Evidence source classes (strongest first)", ""]
        out += [f"- `{c}` (weight {SOURCE_WEIGHTS[c]})" for c in SOURCE_CLASSES]
        # Ordered by `STATUSES`, not by the gloss mapping, so the tuple that
        # `models.py` VALIDATES against is the one thing that decides both the
        # membership and the order of what is published about it.
        out += ["", "## Record statuses", ""]
        out += [f"- `{s}` -- {STATUS_GLOSSES[s]}" for s in STATUSES]
        # The PARTITION, published because it is the only rule a citation gate can
        # implement without inventing one. Both sides are derived from `STATUSES` by the
        # taxonomy module, so this branch cannot publish a partition the library would
        # disagree with, and neither side is read from `gaps/`: a vocabulary rule must
        # hold for a status no record happens to carry yet.
        out += ["", "## Citation gate", ""]
        out += [f"- `citable` -- {_status_list(citable_statuses())}",
                f"- `terminal` -- {_status_list(terminal_statuses())}"]
        # Reach the published `render.document` rather than re-spell its tail here.
        # The one-newline rule is a published guarantee, and a second copy of it
        # holds only while the copies agree: this branch spelled the join tail
        # WITHOUT the trailing-blank normalisation, so it produced the right
        # bytes only because the taxonomy list happens to end on a bullet.
        # `document` pops trailing blanks IN PLACE; safe here because `out` is
        # never read after this write.
        sys.stdout.write(document(out))
        return EXIT_OK

    if args.command == "scan":
        directory = _resolve(args.gaps)
        try:
            gaps = load_all(directory)
        except RegistryError as exc:
            return _fail(str(exc))
        try:
            result = scan(gaps, args.target)
        except (NotADirectoryError, OSError) as exc:
            return _fail(f"cannot scan target: {exc}")
        if args.prd:
            if not result.actionable:
                return _fail("no PRESENT finding to build against; "
                             "run without --prd to see MANUAL questions")
            # Read the floor ONCE and use that same value for the decision
            # and for every message about it, so a message can never name a
            # floor other than the one actually applied.
            floor = CONFIDENCE_FLOOR_DEFAULT
            selection = select_for_prd(result, floor)
            if selection.selected is None:
                listed = ", ".join(
                    f"{f.gap.id} (confidence {f.confidence})"
                    for f in selection.passed_over)
                named = selection.passed_over[0].gap.id
                return _fail(
                    f"no PRESENT finding clears the confidence floor "
                    f"{floor}: {listed}. Strengthen the evidence, or name "
                    f"it explicitly with 'radar prd --gap {named}'.")
            # Announced, one line each, BEFORE the document: a build loop
            # reading stdout is unaffected, and a human reading stderr sees
            # what the floor cost rather than a silent substitution.
            for finding in selection.passed_over:
                sys.stderr.write(
                    f"Note: skipped {finding.gap.id} "
                    f"(priority {finding.priority:.1f}, "
                    f"confidence {finding.confidence}) -- below the "
                    f"confidence floor {floor}.\n")
            sys.stdout.write(render_prd(selection.selected.gap,
                                        project=result.target.name))
            return EXIT_OK
        # Decided BEFORE a byte is written, because a scan that verdicted NOTHING
        # is a refusal and the published `2` row promises stdout stays empty on
        # one. With the flag off `verdict` is False and the return is `EXIT_OK`,
        # so the default path keeps today's single exit code and today's bytes.
        verdict = gate_verdict(result) if args.exit_code else False
        if verdict is None:
            return _fail(
                f"scan applied 0 register records from {directory}, so "
                "--exit-code has no verdict to report; an all-zero census is "
                "vacuous, not a clean target -- check the register path")
        sys.stdout.write(scan_json(result) if args.json
                         else render_scan(result))
        return EXIT_GAPS_PRESENT if verdict else EXIT_OK

    if args.command == "diff":
        # Both sides load BEFORE anything is written, so a failure on either side
        # leaves stdout empty rather than half a document.
        try:
            old_gaps = load_all(_resolve(args.old))
            new_gaps = load_all(_resolve(args.new))
        except RegistryError as exc:
            return _fail(str(exc))
        # Compared ONCE and bound, so both surfaces answer from the same comparison
        # rather than each calling `diff_registers` down its own branch. The two
        # serializers are then provably reading one object, which is what makes
        # "the markdown default is unchanged" a statement about the SURFACE only.
        comparison = diff_registers(old_gaps, new_gaps)
        sys.stdout.write(diff_json(comparison) if args.json
                         else render_diff(comparison))
        return EXIT_OK

    # BEFORE `_resolve` and `load_all`, so an argument typo is diagnosable
    # independently of the register's health: `--layer <bogus>` over a path holding no
    # register must name the layer, not report a registry error, or the caller fixes
    # the wrong thing. Read off `args` only under the verb that declares the option
    # rather than through a `getattr` default -- a default would silently pass a
    # renamed `dest` as "no layer given", turning this whole branch dead.
    if args.command == "list" and args.layer is not None:
        if args.layer not in LAYERS:
            return _fail(_unknown_layer(args.layer))

    directory = _resolve(args.path)

    try:
        if args.command == "show":
            sys.stdout.write(gap_brief(load_one(directory, args.gap_id)))
            return EXIT_OK

        gaps = load_all(directory)

        if args.command == "validate":
            # A verdict verb cannot show the size of the domain it examined:
            # one exit code has no room to say "there was nothing to parse".
            # So certifying an EMPTY register asserts the strongest available
            # claim on no evidence at all, and an emptied register, a moved
            # one, or a path a level too high becomes indistinguishable from a
            # healthy one to the CI reading this exit code. Refuse instead --
            # the same answer `tools/check_locators.py` already gives its own
            # empty domain. Deliberately NOT pushed down into `load_all`:
            # `list`/`report` emit a DOCUMENT, which shows its own emptiness
            # where the reader can see it, so only the verdict verb needs this.
            if not gaps:
                return _fail(f"no gap records found in {directory}")
            sys.stdout.write(f"OK: {len(gaps)} gap record(s) valid.\n")
            return EXIT_OK

        if args.command == "list":
            rows = _list_rows(_select_layer(gaps, args.layer), args.floor)
            sys.stdout.write(_list_json(rows, args.floor) if args.json
                             else _list_text(rows))
            return EXIT_OK

        if args.command == "report":
            sys.stdout.write(radar_report(gaps, args.floor))
            return EXIT_OK

        if args.command == "prd":
            if args.gap_id:
                gap = load_one(directory, args.gap_id)
            else:
                ranked = rank(gaps)
                if not ranked:
                    return _fail("no gap clears the confidence floor")
                gap = ranked[0][0]
            sys.stdout.write(render_prd(gap, args.project))
            return EXIT_OK

    except RegistryError as exc:
        return _fail(str(exc))

    return _fail(f"unknown command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
