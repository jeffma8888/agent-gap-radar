"""The ONE hand-spelled inventory of `build_parser()`'s surface (iteration 303).

WHY THIS EXISTS
Two truths about the CLI surface are legitimate and both are kept: the published document
(`docs/CONSUMER_CONTRACT.md`, pinned cell by cell in `tests/test_iter88_behavior.py` and
proved equal to the parser in both directions by `tests/_surface_contract.py`) and one
hand-spelled expectation of what the parser registers, which is what this module holds.
Until iteration 303 that second truth was copied by hand into four modules, and every
flag the roadmap added (`--floor` in 255, `--baseline` in 300, `taxonomy --json` in 302)
paid a four-to-seven-file re-baseline whose members nobody enumerated until the final
gate -- where iteration 299 lost a green commit to a pin it had not counted. The copies
lived in `tests/test_iter111_behavior.py` (the origin, moved here verbatim),
`tests/test_iter296_behavior.py` (a per-verb flag dict plus a flag COUNT) and
`tests/test_iter77_behavior.py` (the verbs that must refuse `--json`); a fourth test read
the other three AS TEXT to check their constants. After this module, a new flag touches
this file, the document, and -- if it lands on `scan` -- the `test_iter88` cell, and no
test reads another test's source to check what it pins.

WHY THE DERIVATIONS LIVE HERE AND NOT IN `_surface_contract.py`
`long_flags()` and `verbs_without()` are read off `EXPECTED_SURFACE`, never off the live
parser: they are the EXPECTATION side of every comparison. `tests/_surface_contract.py`
is the MEASUREMENT side (`parser_surface()` introspects `build_parser()`), and keeping the
two in separate modules is what lets a test assert one against the other without either
being able to agree with itself. For the same reason this module imports nothing from
`agent_gap_radar`.

WHY THE TEXT BELOW IS A VERBATIM MOVE
The two dicts and their `#:` comments are cut from `tests/test_iter111_behavior.py` at
`8308ab4` unchanged, so `git log -p` on either file tells the full story of every flag and
the per-row comments keep naming the iteration that added each argument.
"""

from __future__ import annotations

#: Behavior 8. `build_parser()`'s surface as it stands today, per verb:
#: (sorted option strings, positional count, sorted required dests, positional dests).
#: Compared through the oracle in `tests/_surface_contract.py` rather than re-derived here.
EXPECTED_SURFACE = {
    "diff": (["--exit-code", "--json"], 2, ["new", "old"], ["old", "new"]),
    "list": (["--floor", "--json", "--layer"], 1, [], ["path"]),
    # Iteration 257 added `--with-fixtures`; the list is SORTED, so it lands last
    # here and its registration index is asserted separately below.
    # Iteration 294 added `--floor`, the same flag and default `list`/`report`/`scan`
    # carry; the list is SORTED, so it lands first.
    "prd": (["--floor", "--gap", "--project", "--with-fixtures"], 1, [], ["path"]),
    "report": (["--floor"], 1, [], ["path"]),
    # Iteration 255 added `--floor`, so `scan` now names the same flag `list` and
    # `report` do; the sorted list is the inventory, not a ranking.
    # Iteration 299 added `--baseline`, the prior-scan document `--exit-code` gates
    # against; it takes a value and defaults to None, like `--gap`.
    "scan": (["--baseline", "--exit-code", "--floor", "--gap", "--gaps", "--json",
              "--prd"], 1, ["target"], ["target"]),
    "show": ([], 2, ["gap_id"], ["gap_id", "path"]),
    # Iteration 302 added `--json`, the only flag this verb carries; a `store_true`
    # with a `False` default, so it earns no `## Defaults` row.
    "taxonomy": (["--json"], 0, [], []),
    "validate": ([], 1, [], ["path"]),
}

#: Behavior 8's second half, read off the raw actions: per verb, one row per argument as
#: (dest, sorted option strings, required, default, nargs). `"SUPPRESS"` stands for
#: `argparse.SUPPRESS`, which is the default argparse gives its own `-h`.
EXPECTED_ARGUMENTS = {
    "diff": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("old", [], True, None, None),
        ("new", [], True, None, None),
        ("json", ["--json"], False, False, 0),
        ("exit_code", ["--exit-code"], False, False, 0),
    ],
    "list": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
        ("floor", ["--floor"], False, 2, None),
        ("json", ["--json"], False, False, 0),
        ("layer", ["--layer"], False, None, None),
    ],
    "prd": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
        ("gap_id", ["--gap"], False, None, None),
        # Iteration 294: the floor the top-ranked selection applies, registered after
        # `--gap` (the escape hatch that bypasses it). Same dest, spelling and DEFAULT
        # as the `list`/`report`/`scan` rows, so a drift in one of the four fails here.
        ("floor", ["--floor"], False, 2, None),
        ("project", ["--project"], False, "agent-gap-radar", None),
        # Iteration 257: the opt-in inlined reproduction sample. `nargs=0` and a `False`
        # default, which is why `docs/CONSUMER_CONTRACT.md`'s `## Defaults` table owes it
        # no row -- `tests/_surface_contract.py` excludes both by construction.
        ("with_fixtures", ["--with-fixtures"], False, False, 0),
    ],
    "report": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
        ("floor", ["--floor"], False, 2, None),
    ],
    "scan": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("target", [], True, None, None),
        ("gaps", ["--gaps"], False, ".", None),
        # Iteration 120: the per-record domain. Same dest and same flag spelling as
        # `prd`'s row above, which is the point -- one name for one concept.
        ("gap_id", ["--gap"], False, None, None),
        ("json", ["--json"], False, False, 0),
        # Iteration 255: the floor the verdict surfaces apply, previously hard-coded
        # at all three of them. Same dest, same spelling and the SAME DEFAULT as
        # `list`/`report` above -- a row that reads `2` in three places is what makes
        # a drift in one of them a failure here rather than a silent behavior change.
        ("floor", ["--floor"], False, 2, None),
        ("prd", ["--prd"], False, False, 0),
        ("exit_code", ["--exit-code"], False, False, 0),
        # Iteration 299: the prior `scan --json` document `--exit-code` gates against.
        # Registered LAST so the rows above keep their positions; `None` default
        # like `--gap`, so it earns no `## Defaults` row.
        ("baseline", ["--baseline"], False, None, None),
    ],
    "show": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("gap_id", [], True, None, None),
        ("path", [], False, ".", "?"),
    ],
    "taxonomy": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        # Iteration 302: the same dest, spelling, default and nargs as the `--json`
        # rows of `list`, `scan` and `diff` above -- one name for one concept.
        ("json", ["--json"], False, False, 0),
    ],
    "validate": [
        ("help", ["--help", "-h"], False, "SUPPRESS", 0),
        ("path", [], False, ".", "?"),
    ],
}


def long_flags(verb: str) -> list[str]:
    """The sorted `--` options `EXPECTED_SURFACE` pins for `verb`; `KeyError` on an
    unknown verb, so a caller cannot get an empty list for a typo and pass vacuously."""
    return sorted(o for o in EXPECTED_SURFACE[verb][0] if o.startswith("--"))


def verbs_without(flag: str) -> list[str]:
    """The sorted verbs whose pinned surface lacks `flag`.

    This is the parametrize source for "no OTHER verb gained this flag" tests: when a
    verb legitimately gains the flag, the row in `EXPECTED_SURFACE` moves and the verb
    leaves this list without a second edit anywhere.
    """
    return sorted(v for v in EXPECTED_SURFACE if flag not in long_flags(v))
