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
| 9 | Below-floor rows name the cheapest source class that would lift them to the floor | shipped | `scoring.promotion_options` + a derived `Needs` column; no verb, so `tools/promote.py` keeps the word |
| 10 | Evidence staleness: flag records whose newest citation is older than N months | open | A gap can be closed by the industry without anyone noticing |
| 11 | Cross-record duplicate detection on normalised title tokens | open | Prevent two records describing one gap |
| 12 | `radar diff` between two register states | open | Show what a research pass actually changed |
| 13 | Layer coverage report: which layers have no records and are therefore unexamined | open | Absence of records is not absence of gaps |
| 14 | `radar list` displays below-floor records, flagged; adds `--json` | shipped | `list` dropped them, breaking the one rule VISION.md protects by name |
| 15 | "Strongest source" must come from the ladder rung, not the alphabet | open | `render.py` uses `min(..., key=source_class)`; measured wrong for GAP-013 (prints maintainer-primary, ladder says peer-reviewed) and GAP-016 (prints the weight-1 secondary-summary, ladder says vendor-primary); both reachable at `--floor 6` |
| 16 | `radar list --layer L` filter | open | Deliberately split from #14: a filter is an omission mechanism and needs the never-drop semantics settled first |
| 17 | `radar scan --prd` honours the confidence floor its twin `radar prd` already enforces | shipped | The report displays below-floor findings; the PRD selection must not BUILD against one |
| 18 | `radar scan` drives its file walk from the tracked set instead of globbing the tree | shipped | 12x faster on a 230-file target; `checks.py` |
| 19 | Roadmap-ledger integrity: retire the ambiguous `iter NN` status, brake on a shipped iteration with no ledger row | shipped | The loss of iter 03 was invisible while the status column carried three vocabularies |
| 20 | `docs/CONSUMER_CONTRACT.md` restates a record count it does not derive, and is wrong by 60% | open | The document a machine consumer reads breaks the restated-count rule `README.md` publishes |
| 21 | `radar list --json` carries the below-floor prescription a gate can assert | open | Split from #9, which landed the human table first; a marker can be scraped, a field can be asserted |
| 22 | `radar validate` must fail when it examined zero records | shipped | Exit 0 over an empty domain made the `iff` published at `docs/CONSUMER_CONTRACT.md` false; `tools/check_locators.py` already refused the identical case and `radar prd` already exits 2 |
| 23 | `radar list` over a zero-record register writes zero bytes, not one newline | open | Measured in iter 06: exit 0, 0 bytes. The vacuous edge of the one-newline contract -- decide whether an empty document is a newline or nothing |

Status values are exactly `open` or `shipped` -- there is no third value. A row is flipped to `shipped` in the same commit that lands it, together with that iteration's Done-ledger row; the iteration that shipped a row is recorded in the ledger, never in this column.

Numbers are stable identifiers, not an ordering -- rows are appended, never renumbered, because committed docs and prior specs cite them. Ship order is the line below.

**Next up:** 15 (a shipped wrong output, and the column immediately left of the one iter 05 added), then 20 (a wrong count in the document a machine consumer reads), then 8. Then 16, whose never-drop dependency #14 has cleared, then 21, then 23.

## Non-goals for this roadmap

No web fetching inside the tool. No LLM calls. No dashboard. No database. The register is files in git, and that is the feature.

## Done ledger

One row per shipped iteration, landed in that iteration's own ship commit. Deferring a record is how history gets permanently lost.

- iter 01 `radar list` stops dropping below-floor records and gains `--json`; three false doc rows made true
- iter 02 `radar scan --prd` no longer builds against a below-floor finding; skips announced, exit 2 when none clears
- iter 03 `scan` walks the tracked set instead of globbing the tree, 12x faster; row recorded late, in iter 04
- iter 04 retires the ambiguous `iter NN` status; the suite now fails when a shipped iteration has no ledger row
- iter 05 below-floor rows name the cheapest citation class that lifts them, derived from `confidence()`
- iter 06 `radar validate` fails closed on a domain holding zero records; the contract's false `iff` made true
