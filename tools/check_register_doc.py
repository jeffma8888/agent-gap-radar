#!/usr/bin/env python3
"""Refuse a committed `REGISTER.md` whose bytes no longer match what `radar report` renders.

WHY A TRACKED, GENERATED DOCUMENT EXISTS AT ALL. `VISION.md`'s definition of done is that
the register is "the reference a builder checks before starting an agent-infrastructure
project", and until this file landed that reference was 120 raw JSON records: the ranked
document existed only in the stdout of a command a reader had to install the package to
run. `VISION.md` also justifies the byte-stability bar as existing "so reports can be
committed and diffed" -- a guarantee nothing had ever consumed. `REGISTER.md` is both: the
on-ramp a repo page can show, and the one byte-exact golden that pins the renderer.

WHY THE GOLDEN NEEDS A DOOR AND NOT A CONVENTION. A generated file under version control
has exactly one failure mode: it goes stale, silently, and then it is worse than absent
because a reader trusts it. The remedy is not a rule in a README, it is a check that can
FAIL -- and whose failure message is the repair, so the reader never has to reconstruct the
command. That command is `uv run radar report . > REGISTER.md`, and it is written once in
this file, as `REGENERATE_COMMAND` below.

WHY THE COMPARISON GOES THROUGH `cli.main` AND NOT `render.radar_report`. The artifact's
contract is the stdout of the PUBLISHED invocation, floor default and all. Calling the
renderer directly would mean this door owns a second copy of the verb's argument defaults,
so a change to the default confidence floor would leave the door happily comparing the
artifact against a document no user can produce. One route, no second opinion.

WHY THE VERDICT IS A MEASUREMENT AND NOT A BOOLEAN. This product's core invariant is that a
claim is DERIVED from what was observed rather than asserted, and a drift report is no
exception: the refusal carries the committed byte count, the rendered byte count and the
offset of the first differing byte, all computed here. The offset is what makes a
same-length edit -- the one drift a length comparison waves through -- localisable in the
same single line.

Offline by construction: it renders IN PROCESS from the tracked register and opens no
socket. It writes nothing, anywhere; a door that repairs the tree it audits cannot be
trusted to report on it.

Usage:
    uv run python tools/check_register_doc.py [--file PATH]

Exit codes: 0 the committed document matches the rendered one, 2 it drifted, could not be
read, or the register itself could not be rendered -- an unchecked artifact is not a
cleared artifact.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys

# Same shim shape as `tools/promote.py` and `tools/verify_mutations.py`, and for the same
# reason: this file runs as a script, so the package is not importable without it.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

# Refusals speak the `Error: ` vocabulary this repo publishes rather than argparse's
# `<prog>: error: ...`, and they reach the ONE construction site of the prefix rather than
# grow a second one; `cli.fail`'s docstring carries the argument.
from agent_gap_radar.cli import PublishedErrorParser, fail  # noqa: E402
from agent_gap_radar.cli import main as radar  # noqa: E402

#: The tracked artifact's repo-relative name.
ARTIFACT_NAME = "REGISTER.md"

#: The ONE published recipe that produces the artifact, BUILT from its name rather than
#: spelled a second time: a rename that touched only one of the two would leave this door
#: reading one file while its refusal told the reader to write another. `README.md` carries
#: this same string, and the suite may hold the two to one answer.
REGENERATE_COMMAND = f"uv run radar report . > {ARTIFACT_NAME}"

#: The verb the artifact is the stdout of. Named so the render below and any test that
#: re-derives the document agree on the invocation without re-spelling it.
REPORT_VERB = "report"


def default_repo() -> pathlib.Path:
    """The checkout this file lives in: the parent of `tools/`, found from `__file__`.

    Derived from this file's location and never from the cwd, so the door answers the same
    question from a worker's temp directory as from the repo root -- and carries no absolute
    machine path, which a PUBLIC repo's quality bar forbids.
    """
    return pathlib.Path(__file__).resolve().parent.parent


def rendered_document(repo: pathlib.Path) -> tuple[int, str]:
    """`(exit code, stdout)` of `radar report <repo>`, with BOTH channels captured.

    stderr is captured and dropped rather than left alone: this door promises a refusal of
    exactly one line on its own stderr, and a verb that refused would otherwise contribute
    its own `Error: ` line ahead of it. The exit code is returned instead, so the caller
    can tell "the register cannot be rendered" from "the artifact is stale" -- two different
    repairs that an empty document would collapse into one misleading drift report.

    `io.StringIO` is a text layer without `reconfigure`, which `cli.main`'s encoding pin
    already documents as a supported double.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = radar([REPORT_VERB, str(repo)])
    return code, out.getvalue()


def first_difference(committed: bytes, rendered: bytes) -> int:
    """The offset of the first byte at which the two documents disagree.

    Defined for unequal inputs only, and total over them: when one is a prefix of the
    other the answer is the shorter length, which is where the reader should look. This is
    the measurement a length comparison cannot make -- an edit that preserves the byte
    count moves no count but still moves this offset.
    """
    for offset, (left, right) in enumerate(zip(committed, rendered)):
        if left != right:
            return offset
    return min(len(committed), len(rendered))


def _arguments(argv: list[str] | None) -> list[str]:
    """The flags to parse, tolerating a `sys.argv`-shaped call.

    `None` means NO arguments, deliberately NOT `sys.argv[1:]`: this `main` is called in
    process by the suite, where `sys.argv` carries pytest's own options and argparse would
    refuse them as unrecognized -- turning "run the door with no arguments" into a usage
    error that has nothing to do with this repo.

    A leading token is dropped only when it NAMES THIS FILE. The repo's tool mains disagree
    about the convention -- `verify_mutations.main([])` passes flags bare while
    `scan_cost.main(["scan_cost.py", ...])` is `sys.argv`-shaped, an ambiguity a test module
    had to hedge around with a constant -- so this door accepts both. The predicate is a
    basename equality rather than "does not look like a flag", so a genuinely mistyped
    positional is still refused instead of being swallowed as a program name.
    """
    tokens = list(argv or ())
    if tokens and pathlib.Path(tokens[0]).name == pathlib.Path(__file__).name:
        return tokens[1:]
    return tokens


def main(argv: list[str] | None = None) -> int:
    """Compare the committed artifact against a fresh render; say nothing when they agree.

    Silence on success is the point: this is a brake, and a brake that prints a reassuring
    paragraph every run trains its reader to stop reading. Every refusal is one line on
    stderr with the repo's published prefix, carries the path actually read, and ends in
    the regeneration command, so the message IS the repair.

    `--file` exists so the refusing side can be measured. The committed document can only
    ever demonstrate the passing side, and a brake proven in one direction is not a brake;
    pointing this at a mutated copy is what makes the red arm reachable without editing the
    tracked tree.
    """
    parser = PublishedErrorParser(
        prog=pathlib.Path(__file__).name, description=__doc__.splitlines()[0])
    parser.add_argument(
        "--file", metavar="PATH",
        help=f"the document to check instead of the tracked {ARTIFACT_NAME}")
    args = parser.parse_args(_arguments(argv))

    repo = default_repo()
    artifact = pathlib.Path(args.file) if args.file else repo / ARTIFACT_NAME
    try:
        committed = artifact.read_bytes()
    except OSError as exc:
        return fail(f"{artifact}: the generated register document could not be read "
                    f"({type(exc).__name__}) -- regenerate it with: {REGENERATE_COMMAND}")

    code, document = rendered_document(repo)
    if code != 0:
        return fail(f"{artifact}: `{REGENERATE_COMMAND}` would exit {code} on this "
                    f"register, so the committed document cannot be checked; repair the "
                    f"register first")

    rendered = document.encode("utf-8")
    if committed != rendered:
        return fail(f"{artifact} drifted from the rendered register: committed "
                    f"{len(committed)} B, rendered {len(rendered)} B, first difference at "
                    f"byte {first_difference(committed, rendered)} -- regenerate with: "
                    f"{REGENERATE_COMMAND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
