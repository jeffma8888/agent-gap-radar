# Roadmap

Owned by the planning role. One item per iteration, smallest useful increment first. Ship order is dependency order.

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Gap schema, closed taxonomy, evidence ladder | shipped | `models.py`, `taxonomy.py` |
| 2 | Registry loader with duplicate + schema gates | shipped | `registry.py` |
| 3 | Two-axis scoring, no blending, visible floor | shipped | `scoring.py` |
| 4 | Ranked report + per-gap brief renderers | shipped | `render.py` |
| 5 | Build-loop PRD emitter | shipped | `prd.py`, red-test-first stories |
| 6 | CLI: validate, list, report, show, prd, taxonomy | shipped | `cli.py` |
| 7 | Seed records with resolvable citations | shipped | `gaps/`. Counts are not restated here: run `radar report .` |
| 8 | Byte-exact golden report fixtures | open | Pin renderer output against committed goldens |
| 9 | `radar promote` to list below-floor records with the exact missing source class | open | Turns the floor into a research queue |
| 10 | Evidence staleness: flag records whose newest citation is older than N months | open | A gap can be closed by the industry without anyone noticing |
| 11 | Cross-record duplicate detection on normalised title tokens | open | Prevent two records describing one gap |
| 12 | `radar diff` between two register states | open | Show what a research pass actually changed |
| 13 | Layer coverage report: which layers have no records and are therefore unexamined | open | Absence of records is not absence of gaps |
| 14 | `radar list` displays below-floor records, flagged; adds `--json` | iter 01 | `list` dropped them, breaking the one rule VISION.md protects by name |
| 15 | "Strongest source" must come from the ladder rung, not the alphabet | open | `render.py` uses `min(..., key=source_class)`; wrong on GAP-013/016 above the default floor |
| 16 | `radar list --layer L` filter | open | Deliberately split from #14: a filter is an omission mechanism and needs the never-drop semantics settled first |

Numbers are stable identifiers, not an ordering -- rows are appended, never renumbered, because committed docs and prior specs cite them. Ship order is the line below.

**Next up:** 15 (a shipped wrong output), then 8, then 9.

## Non-goals for this roadmap

No web fetching inside the tool. No LLM calls. No dashboard. No database. The register is files in git, and that is the feature.

## Done ledger

One row per shipped iteration, landed in that iteration's own ship commit. Deferring a record is how history gets permanently lost.

- iter 01 `radar list` stops dropping below-floor records and gains `--json`; three false doc rows made true
