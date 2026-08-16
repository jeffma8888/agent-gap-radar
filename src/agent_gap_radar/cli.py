"""radar -- command line entry point.

Conventions (shared with sibling tools): errors go to stderr prefixed with
"Error: " and exit 2; stdout carries only the document, so output is pipeable.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from . import __version__
from .prd import render_prd
from .registry import RegistryError, gaps_dir, load_all, load_one
from .render import gap_brief, radar_report
from .scan import render_scan, scan, scan_json
from .scoring import confidence, priority, rank
from .taxonomy import GAP_TYPES, LAYERS, SOURCE_CLASSES, SOURCE_WEIGHTS


def _resolve(path_arg: str) -> pathlib.Path:
    """Accept either a repo root (containing gaps/) or the gaps dir itself."""
    p = pathlib.Path(path_arg).expanduser()
    candidate = gaps_dir(p)
    return candidate if candidate.is_dir() else p


def _fail(msg: str) -> int:
    sys.stderr.write(f"Error: {msg}\n")
    return 2


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
    p_scan.add_argument("--prd", action="store_true",
                        help="emit a prd.json for the worst PRESENT finding instead "
                             "of the report")

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
            sys.stdout.write(render_prd(result.actionable[0].gap,
                                        project=result.target.name))
            return 0
        sys.stdout.write(scan_json(result) if args.json
                         else render_scan(result))
        return 0

    directory = _resolve(args.path)

    try:
        if args.command == "show":
            sys.stdout.write(gap_brief(load_one(directory, args.gap_id)))
            return 0

        gaps = load_all(directory)

        if args.command == "validate":
            sys.stdout.write(f"OK: {len(gaps)} gap record(s) valid.\n")
            return 0

        if args.command == "list":
            for gap, pri, conf in rank(gaps, args.floor):
                sys.stdout.write(f"{gap.id}  p={pri:>4.1f}  c={conf}  {gap.title}\n")
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
