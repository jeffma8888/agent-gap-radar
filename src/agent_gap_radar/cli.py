"""radar -- command line entry point.

Conventions (shared with sibling tools): errors go to stderr prefixed with
"Error: " and exit 2; stdout carries only the document, so output is pipeable.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import __version__
from .diff import diff_registers, render_diff
from .models import Gap
from .prd import render_prd
from .registry import RegistryError, gaps_dir, load_all, load_one
from .render import gap_brief, radar_report
from .scan import render_scan, scan, scan_json, select_for_prd
from .scoring import (CONFIDENCE_FLOOR_DEFAULT, below_floor, confidence,
                      priority, rank)
from .taxonomy import GAP_TYPES, LAYERS, SOURCE_CLASSES, SOURCE_WEIGHTS


def _resolve(path_arg: str) -> pathlib.Path:
    """Accept either a repo root (containing gaps/) or the gaps dir itself."""
    p = pathlib.Path(path_arg).expanduser()
    candidate = gaps_dir(p)
    return candidate if candidate.is_dir() else p


def _fail(msg: str) -> int:
    sys.stderr.write(f"Error: {msg}\n")
    return 2


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
    """Line-oriented form: one line per record, below-floor rows flagged."""
    return "".join(
        f"{gap.id}  p={pri:>4.1f}  c={conf}  {gap.title}"
        + (BELOW_FLOOR_MARKER if is_below else "")
        + "\n"
        for gap, pri, conf, is_below in rows
    )


def _list_json(rows: list[ListRow], confidence_floor: int) -> str:
    """A stable record list for a machine consumer.

    A flat array with a `below_floor` boolean, not two arrays: the text marker
    can be scraped, but a boolean can be ASSERTED by a consumer's gate, which is
    where the never-drop invariant stops being prose and becomes checkable.
    Carries `priority` and `confidence` as distinct fields and never a blended
    score, matching `scan_json` -- a composite would launder the one distinction
    the register exists to preserve.
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
            }
            for gap, pri, conf, is_below in rows
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
    # "confidence floor" LEADS this help text deliberately. argparse wraps
    # help on whitespace, and a phrase the docs promise a reader will find
    # is broken by a line split; leading it survives any width above ~33
    # columns instead of only the default 80.
    p_scan.add_argument("--prd", action="store_true",
                        help="confidence floor gated: emit a prd.json for the "
                             "worst PRESENT finding that clears the floor, "
                             "instead of the report")

    p_diff = sub.add_parser(
        "diff", help="Report what changed between two register states.")
    # Two REQUIRED positionals. Deliberately unlike `list`/`show`/`report`, whose
    # `nargs="?" default="."` lets a consumer copying a documented invocation read
    # whichever register sits in its own working directory -- a silent wrong answer,
    # not an error. A diff with a defaulted side is that shape twice, and it would
    # compare a register against itself and report "nothing changed".
    p_diff.add_argument("old", help="register state to compare FROM")
    p_diff.add_argument("new", help="register state to compare TO")

    sub.add_parser("taxonomy", help="Print the fixed vocabularies.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "taxonomy":
        out = ["# Taxonomy", "", "## Layers", ""]
        out += [f"- `{k}` -- {v}" for k, v in LAYERS.items()]
        out += ["", "## Gap types", ""]
        out += [f"- `{k}` -- {v}" for k, v in GAP_TYPES.items()]
        out += ["", "## Evidence source classes (strongest first)", ""]
        out += [f"- `{c}` (weight {SOURCE_WEIGHTS[c]})" for c in SOURCE_CLASSES]
        sys.stdout.write("\n".join(out) + "\n")
        return 0

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
            return 0
        sys.stdout.write(scan_json(result) if args.json
                         else render_scan(result))
        return 0

    if args.command == "diff":
        # Both sides load BEFORE anything is written, so a failure on either side
        # leaves stdout empty rather than half a document.
        try:
            old_gaps = load_all(_resolve(args.old))
            new_gaps = load_all(_resolve(args.new))
        except RegistryError as exc:
            return _fail(str(exc))
        sys.stdout.write(render_diff(diff_registers(old_gaps, new_gaps)))
        return 0

    directory = _resolve(args.path)

    try:
        if args.command == "show":
            sys.stdout.write(gap_brief(load_one(directory, args.gap_id)))
            return 0

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
            return 0

        if args.command == "list":
            rows = _list_rows(gaps, args.floor)
            sys.stdout.write(_list_json(rows, args.floor) if args.json
                             else _list_text(rows))
            return 0

        if args.command == "report":
            sys.stdout.write(radar_report(gaps, args.floor))
            return 0

        if args.command == "prd":
            if args.gap_id:
                gap = load_one(directory, args.gap_id)
            else:
                ranked = rank(gaps)
                if not ranked:
                    return _fail("no gap clears the confidence floor")
                gap = ranked[0][0]
            sys.stdout.write(render_prd(gap, args.project))
            return 0

    except RegistryError as exc:
        return _fail(str(exc))

    return _fail(f"unknown command {args.command!r}")


if __name__ == "__main__":
    raise SystemExit(main())
