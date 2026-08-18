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
| 15 | "Strongest source" must come from the ladder rung, not the alphabet | shipped | `scoring.strongest_source`, keyed on the `SOURCE_CLASSES` index so equal weights resolve by rung. The alphabetical `min()` was wrong for GAP-013 and GAP-016 at `--floor 6`, and worse at the DEFAULT floor: `confidence() < 2` restricts every below-floor row to `{secondary-summary, model-output}`, the one pair that mis-sorts, so the table could name `model-output` as a record's best evidence |
| 16 | `radar list --layer L` filter | open | Deliberately split from #14: a filter is an omission mechanism and needs the never-drop semantics settled first |
| 17 | `radar scan --prd` honours the confidence floor its twin `radar prd` already enforces | shipped | The report displays below-floor findings; the PRD selection must not BUILD against one |
| 18 | `radar scan` drives its file walk from the tracked set instead of globbing the tree | shipped | 12x faster on a 230-file target; `checks.py` |
| 19 | Roadmap-ledger integrity: retire the ambiguous `iter NN` status, brake on a shipped iteration with no ledger row | shipped | The loss of iter 03 was invisible while the status column carried three vocabularies |
| 20 | `docs/CONSUMER_CONTRACT.md` restates a record count it does not derive, and is wrong by 60% | open | The document a machine consumer reads breaks the restated-count rule `README.md` publishes |
| 21 | `radar list --json` carries the below-floor prescription a gate can assert | open | Split from #9, which landed the human table first; a marker can be scraped, a field can be asserted |
| 22 | `radar validate` must fail when it examined zero records | shipped | Exit 0 over an empty domain made the `iff` published at `docs/CONSUMER_CONTRACT.md` false; `tools/check_locators.py` already refused the identical case and `radar prd` already exits 2 |
| 23 | `radar list` over a zero-record register writes zero bytes, not one newline | open | Measured in iter 06: exit 0, 0 bytes. The vacuous edge of the one-newline contract -- decide whether an empty document is a newline or nothing |
| 24 | `radar scan` states how many records it applied | open | A scan over a zero-record register exits 0 and prints all-zero counts and "None found." in every section, so a moved, emptied or one-level-too-high register reads as a clean target. The fail-open iter 06 closed in `validate`, still live in the verb `docs/CONSUMER_CONTRACT.md` points a CI gate at. NOT an exit-2 (that would reverse iter 06's deliberate call) -- a positive count a gate can assert |
| 25 | `radar scan` gains an opt-in, floor-gated non-zero exit code | open | Raised by independent scouts in iter 01 and again in iter 07: a scan finding 3 PRESENT gaps exits 0, so a gate must parse JSON to learn anything. Must stay opt-in with today's bytes unchanged, must gate on the confidence floor (a `model-output` record may never block a build), keep exit 2 for errors, and must never become a "gaps closed" score |
| 26 | `rank()` and `below_floor()` collapse into one single-pass partition, so never-dropping a record stops being a coincidence | shipped | The two filters were exact complements by inspection and by nothing else, while `VISION.md` names that rule as the one it protects and iter 01 shipped the fix for an actual instance of it in `radar list`. Output bytes unchanged; `cli.py:54` already carried a comment warning that a second below-floor predicate is how this breaks. The behavioral proxy for the dedup is a call count: `confidence()` is evaluated exactly once per record per call, where each half previously scored every record and then re-scored its survivors (measured 31 and 17 calls over 16 records) |
| 27 | Two live-register id censuses become oracles derived from `confidence()`, and the rendered report's SECTION membership is asserted for the first time | shipped | `test_iter05_behavior.py` pinned `sorted(cells) == ["GAP-008", "GAP-010"]`, and the recurring research pass falsified it by writing a 17th record: the suite went RED over a CORRECT register, which is how a loop comes to revert something unrelated. Iteration 08 proved every id appears exactly once in `radar report`; nothing proved it appears in the RIGHT section, so a below-floor record rendered into the ranked table would still have passed. Zero-line `src/` diff; `gaps/` untouched, because the records are another writer's in-flight data |
| 28 | A suite brake against re-introducing a closed-set id census over the live register | open | Row 27 removed the two that existed; nothing stops the next one, and the landmine only detonates days later when a research pass lands. Must not fire on the synthetic `tmp_path` fixtures, which name ids legitimately |
| 29 | `radar scan` reads each file at most once per scan | open | Measured in iter 09: `checks._read` runs once per (rule, file) pair, so one file is decoded up to 54 times -- 7,856 reads over 227 distinct files, 173.1 MB decoded to cover a 2 MB target, 5.9 s wall on agent-foundry. The one cost that scales as records x target size, and the register is grown by a schedule (16 -> 33 records in days). Declined as iter 04's Candidate A, when no figure was attached. The cache must be scan-scoped, never process-lifetime, or a scan answers from a stale file |
| 30 | The consumer contract's stable-surface table is DERIVED from `build_parser()` instead of hand-copied | shipped | 5 of 7 rows named less than the CLI accepts: `report` omitted `--floor`, `prd` omitted `--project`, `scan` omitted `--json` (the exact object `docs/CONSUMER_CONTRACT.md` points a CI gate at), and `list` + `show` omitted their register-path positional, whose `nargs="?" default="."` makes a copied invocation read whatever register is in the consumer's cwd -- a silent wrong answer, not an error. Zero flags were invented, so the live drift was one-directional OMISSION and a one-sided "every documented flag exists" check would have passed the table unchanged |

Status values are exactly `open` or `shipped` -- there is no third value. A row is flipped to `shipped` in the same commit that lands it, together with that iteration's Done-ledger row; the iteration that shipped a row is recorded in the ledger, never in this column.

Numbers are stable identifiers, not an ordering -- rows are appended, never renumbered, because committed docs and prior specs cite them. Ship order is the line below.

**Next up:** 29 -- measured this iteration on three real targets, small, and the only cost on the board that grows as records x target size while the register is grown by a schedule; `radar scan` is also the verb `docs/CONSUMER_CONTRACT.md` points a CI gate at, so the waste is per-commit for every consumer. Then 24, a scan over a moved, emptied or one-level-too-high register reporting all-zero counts and reading as a clean target, which is also the precondition for 25. Then 20, long unclaimed (the count of iterations it has waited is deliberately not restated here -- it decays) and which no rotated lens will ever claim (it is docs drift, and every lens rules it out) -- a planning role should take it directly instead of waiting for a slate to nominate it. Then 8 (goldens had to land after 15, which has cleared), then 16, whose never-drop dependency #14 has cleared and whose omission semantics row 26 made checkable, then 21, then 23, then 25 behind 24, and 28 the next time a simplification lens comes round.

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
- iter 07 "Strongest source" comes from the ladder rung; alphabetical min() could print `model-output` as best evidence
- iter 08 `rank()` + `below_floor()` become one single-pass partition; never-drop is asserted, not coincidental
- iter 09 two live-register id censuses become `confidence()` oracles; the report's SECTION membership is now asserted
- iter 10 the contract's stable-surface table becomes a parser-derived assertion; 5 rows named less than the CLI accepts
