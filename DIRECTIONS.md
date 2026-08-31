# Foundry directions

foundry directions -- agent-gap-radar
  iter-87
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- one JSON document tail, not four: the same 60-character terminator is written out four times, and the census that guards its text twin cannot see it
    - Candidate A2 -- one offline tripwire, not five divergent ones: the quality bar's most load-bearing rule is hand-copied per module and has already drifted
    - Candidate A3 -- retire `tools/check_locators.py`: its domain is now provably a subset of the quote checker's, and the repo pays an offline-seam tax twice for one question
    winner: A1
    ship: pending (not yet decided)
  iter-86
    lenses: integration-and-adoption, simplification-and-deletion
    - Candidate A1 -- `radar list --json` publishes each record's newest citation date, so the evidence-age axis reaches the one surface the declared consumer reads
    - Candidate A2 -- `radar diff --json`'s key set is published nowhere, and it is the payload the contract's own gate rule points at
    - Candidate A3 -- `radar scan --json`'s `target` is the scanning machine's absolute path, so the artifact a CI gate commits cannot be diffed against a laptop's
    - Candidate B1 -- one scan-scoped memo mechanism, two instances: `file_cache_scope` and `read_cache_scope` are the same nine lines written twice
    - Candidate B2 -- the roadmap index/archive split, smallest honest slice: 57 shipped rows' notes move out byte-for-byte, and `PRODUCT.md` halves
    - Candidate B3 -- delete the third cache lifetime: `_TRACKED_CACHE` is process-lifetime beside two scan-scoped caches, and the suite pays for it 8 times
    winner: A3
    ship: PUSHED a5c6f1b
  iter-85
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- the offline guarantee is honoured by a seam `main()` does not use, so patching `verify_quotes.fetch` is silently ineffective on the one path the tool actually runs
    - Candidate A2 -- `radar scan` can answer a second scan from the first scan's file list, in the module whose own docstring argues against exactly that (roadmap row 43)
    - Candidate A3 -- the repo has no `conftest.py`, so both of its cross-cutting test preconditions are hand-copied per module
    - Candidate B1 -- `radar diff --json` is the only machine payload with no published key set, while the contract instructs a consumer to gate on exactly that diff
    - Candidate B2 -- the below-floor prescription reaches only the human table, so a gate can scrape a marker but cannot read a field (roadmap row 21)
    - Candidate B3 -- the scan surface a CI gate consumes is machine-specific, so the same scan of the same target differs between CI and a laptop (roadmap row 34)
    winner: A1
    ship: PUSHED afc6582
  iter-84
    lenses: new-capability, hardening/DX
    - Candidate A1 -- the ranked view publishes each record's `status`, so a builder can see that the register's #3 gap says the industry has partly moved
    - Candidate A2 -- `radar list --layer L`, the filter roadmap row 16 deferred on purpose
    - Candidate A3 -- `radar report` publishes which sources several records rest on (roadmap row 56)
    - Candidate B1 -- the register's core invariant has no planted-defect proof, and the harness that would give it one is run by nothing
    - Candidate B2 -- the ingest door admits a detector shape the suite only refuses after it is committed (roadmap row 62)
    - Candidate B3 -- teach the roadmap brake to read an archive, because the file the PM reads every iteration is 2.07x its own wall
    winner: A2
    ship: PUSHED 5ea1dcb
  iter-83
    lenses: narrative-and-docs, new-capability
    - Candidate A -- retire the contract's unpaid promise: a SHIPPED verb section that advertises outstanding work it no longer has
    - Candidate B -- publish the promote gate's COMPLETE refusal set, derived from the code
    - Candidate C -- a measurement receipt in the docs must carry the register size it was measured over
    - Candidate A -- `radar report` publishes evidence AGE, so a record can be old without anyone noticing (roadmap row 10)
    - Candidate B -- a shared-source view, so 13 records resting on ONE blog post stop reading as 13 independent findings (roadmap row 56)
    - Candidate C -- ask the COMMITTED register which of its own records duplicate each other (roadmap row 11)
    winner: unknown
    ship: PUSHED e617f64
  iter-82
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A1 -- a necessary-literal prefilter in front of every content rule
    - Candidate A2 -- memoise a content rule's evaluation for the lifetime of one scan
    - Candidate A3 -- publish per-rule scan cost so the next expensive record is visible on the pass that lands it
    - Candidate B1 -- the roadmap's `Next up` pointer names a shipped row as the strongest remaining candidate
    - Candidate B2 -- roadmap row 20 is `open` for a defect that was fixed outside the loop, and nothing stops the count coming back
    - Candidate B3 -- the front door never names the two machine surfaces built for the declared consumer
    winner: B1
    ship: PUSHED 1da0c54
  iter-81
    lenses: simplification-and-deletion, performance-and-throughput (iteration 81)
    - Candidate A1 -- re-land the one-slug-rule collapse iteration 80 lost at the clean-clone gate
    - Candidate A2 -- one JSON tail, not four: `render.json_document()`
    - Candidate A3 -- delete the copied helper set: `test_iter77_behavior.py` is `test_iter11_behavior.py`'s helpers
    - Candidate B1 -- one register pattern costs 29% of every scan; anchor it and prove the document is byte-identical
    - Candidate B2 -- placeholder (rule-result memo, ~3.5% measured) -- see refinement
    - Candidate B3 -- placeholder (literal prefilter) -- see refinement
    winner: B1
    ship: PUSHED 5a51837
  iter-80
    lenses: integration-and-adoption, simplification-and-deletion
    - Candidate A1 -- the four register doors have no doc round-trip: assert every documented `tools/*.py` command against that tool's own parser (roadmap row 50)
    - Candidate A2 -- `radar diff` gained a machine payload in iter 77 and the one door that CREATES a register delta still cannot speak it
    - Candidate A3 -- three of the four tools answer `--help`; the one the README tells you to run first answers `Error: not a directory: --help`
    - Candidate B1 -- one record slug, not two: re-land the collapse iteration 75 built, approved and lost
    - Candidate B2 -- one cache-lifetime rule in `checks.py`, not three: retire `_TRACKED_CACHE` (roadmap row 43)
    - Candidate B3 -- collapse duplicate open rows 64 and 70, and do the index/archive split the foundry already did to itself
    winner: B1
    ship: REVERTED
  iter-79
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- the public-repo bar is enforced file-by-file by whichever iteration touched a doc, and the 120-record register is covered by nothing
    - Candidate A2 -- the mutation harness that proves the suite can fail is referenced by nothing in the repo, and its 20 anchors rot silently
    - Candidate A3 -- `check_locators.py` reports "0 broken" after checking zero locators, and has no seam to test it offline
    - Candidate B1 -- two of the three `--json` machine surfaces are invisible at the front door, and `--floor` is named nowhere
    - Candidate B2 -- the register's only door has an on-ramp describing a pipeline that no longer exists
    - Candidate B3 -- the machine payload a CI consumer commits is machine-local (row 34)
    winner: A3
    ship: PUSHED df23fc7
  iter-78
    lenses: new-capability, hardening/DX
    - Candidate A1 -- the newest-citation date becomes a DERIVED published fact, and the age threshold is deliberately split off
    - Candidate A2 -- `radar list --layer L`: a closed-vocabulary filter that REFUSES a typo and SPEAKS when it matches nothing
    - Candidate A3 -- a status past `open` must cite the evidence that earned it, keyed on the DOCUMENT and not on a list position
    - Candidate B1 -- do the roadmap index/archive split: `PRODUCT.md` is 94,641 chars against a 54,000-char wall, and the committed brake that would police the split does not know an archive exists
    - Candidate B2 -- `checks._TRACKED_CACHE` is process-lifetime in the one module that argues in its own comments against process-lifetime caches; a second scan in the same process answers from the first scan's file list
    - Candidate B3 -- `_validate_rule` type-checks the `globs` LIST and never looks at an element, so `""`, `"   "`, a bare newline, `"/etc/**"` and `"../../**"` are all schema-valid checks
    winner: B3
    ship: PUSHED 27d96da
  iter-77
    lenses: narrative-and-docs, new-capability
    - Candidate A1 -- the consumer contract restates a register count, is wrong on both numbers, and breaks a rule it publishes itself
    - Candidate A2 -- the contract tells a release gate to require `status == open`, which would refuse the register's top-ranked record
    - Candidate A3 -- the roadmap says `open` for something iteration 64 shipped, and nothing in the repo can detect that
    - Candidate B1 -- a status past `open` must cite the evidence that earned it, and `radar show` publishes it
    - Candidate B2 -- `radar show` publishes what each citation CONTRIBUTES to the derived confidence
    - Candidate B3 -- `radar diff --json`, so the non-regression half of the published gate rule is implementable
    winner: B3
    ship: PUSHED fe680e1
  iter-76
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A -- memoise `iter_files` for the lifetime of one scan (roadmap row 67)
    - Candidate B -- to be completed (CLI import cost paid per subprocess)
    - Candidate C -- to be completed (per-pattern regex cost)
    - Candidate A1 -- the stable-surface table marks three verbs' arguments REQUIRED that the parser makes optional
    - Candidate B1 -- the contract restates a register cardinality, and it is now wrong in both numerator and denominator
    - Candidate C1 -- the ingest door is stricter than the schema, and no consumer-facing document says so
    winner: A1
    ship: PUSHED 11752d7
  iter-75
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- Collapse the two divergent `_slug` implementations into one
    - Candidate A2 -- Archive spent measurement prose from the 49 shipped rows, not the ledger
    - Candidate A3 -- Collapse the duplicate open rows 64 and 70 into one open row
    - Candidate B1 -- memoise the per-scan file-set enumeration in the frame the read cache already owns
    - Candidate B2 -- memoise the content-rule verdict per (pattern, globs, exclude_tests, kind) within one scan
    - Candidate B3 -- pay for pydantic only on the verbs that need a register
    winner: A1
    ship: REVERTED
  iter-74
    lenses: integration-and-adoption, simplification-and-deletion
    - Candidate A1 -- both published documents state the priority formula, both state it WRONG, and the contract obliges a file-reading consumer to implement it
    - Candidate A2 -- `radar list --json` says a record is below the floor and never what would lift it (roadmap row 21)
    - Candidate A3 -- the consumer switches on members of our closed vocabularies, and the contract promises they are switchable but never that they are stable
    - Candidate B1 -- One `_slug`, not two, and the trailing dash goes with the copy
    - Candidate B2 -- Move shipped-row detail out of `PRODUCT.md` into an archive
    - Candidate B3 -- Delete the byte-identical duplicated test helpers
    winner: A1
    ship: PUSHED 761bcd1
  iter-73
    lenses: hardening/DX, integration-and-adoption
    - Candidate A -- `tools/check_locators.py` returns "all locators resolve" after checking zero of them
    - Candidate B -- the ingest door admits a content pattern the suite bans, so a research pass reds a green suite
    - Candidate C -- a derived brake that every tool is DRIVEN by a test, not merely mentioned by one
    - Candidate A1 -- `agent_gap_radar.scoring` becomes importable without pydantic, so the declared consumer stops ordering the register by a third rule (roadmap row 33)
    - Candidate C1 -- the published gate rule tells a consumer to require `status == open`, which refuses the joint-highest-priority record
    - Candidate D1 -- `radar diff` has no machine payload, so the non-regression half of our own gate rule is unimplementable
    winner: A1
    ship: PUSHED 0a611c5
  iter-72
    lenses: new-capability, hardening/DX
    - Candidate A -- the ranked report publishes each record's newest-citation date
    - Candidate B -- the report gains a shared-source section: which records rest on the same locator
    - Candidate C -- opt-in `radar prd --with-fixtures` inlines the reproduction sample bytes
    - Candidate B1 -- the tracked-set cache gets the scan lifetime this module already argues for
    - Candidate B2 -- the quote gate gets a network seam, so its verdict logic is testable offline
    - Candidate B3 -- byte-exact goldens for one renderer, over a SYNTHETIC register
    winner: B2
    ship: PUSHED 5701bb8
  iter-71
    lenses: narrative-and-docs, new-capability
    - Candidate A1 -- publish the fourth closed vocabulary: `radar taxonomy` names three of four, and the missing one is the one a consumer is told to switch on
    - Candidate A2 -- the stable-surface table has no declared bracket convention, so it marks four optional arguments as required and hides `prd`'s shipped default
    - Candidate A3 -- delete the contract's restated register cardinality, wrong twice, and the heading obligation its own body discharges
    - Candidate B1 -- `radar report` publishes the CROSS-record shared-evidence view (roadmap row 56)
    - Candidate B2 -- `radar diff --json`, so the non-regression gate the contract already prescribes has a machine surface
    - Candidate B3 -- `radar show` states a record's floor position and the prescription that would lift it, DERIVED
    winner: A1
    ship: PUSHED 4e1bd39
  iter-70
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A -- `content_absent` stops reading once its boolean is decided
    - Candidate B -- memoise ENUMERATION (`iter_files`) for the scope of one scan
    - Candidate C -- to be decided from measurement (row 63 fold-in / row 68 bounded enumeration)
    - Candidate B1 -- `UNKNOWN` means two things and every surface, including the tool's own output, publishes only one
    - Candidate B2 -- the consumer contract restates a register count, and it is now wrong on BOTH numbers
    - Candidate B3 -- the contract tells a consumer to gate on a status the register's joint-top record does not have
    winner: B1
    ship: PUSHED 6e69680
  iter-69
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- two enumeration branches, ONE matcher: delete the duplicated match loop in `checks.py`
    - Candidate A2 -- four closed-vocabulary validators are ONE general rule (`models.py`)
    - Candidate A3 -- retire `tools/check_locators.py`: one out-of-band network checker, not two
    - Candidate B1 -- memoize a content rule's verdict per (pattern, file) inside the existing read-cache scope
    - Candidate B2 -- memoize `iter_files` per (target, globs, exclude_tests) for the life of one scan
    - Candidate B3 -- stop evaluating `any_of` sub-rules whose result can no longer change a byte of output
    winner: A1
    ship: PUSHED 773afda
  iter-68
    lenses: integration-and-adoption, simplification-and-deletion
    - Candidate A1 -- `radar prd` emits a wrapper key the one declared consumer cannot parse
    - Candidate A2 -- the derived ranking is unreachable without pydantic, so the wired consumer ranks the register differently from `radar list`
    - Candidate A3 -- `registry.load_all` returns `[]` where `radar validate` exits 2, and I tripped over it in this run
    - Candidate B1 -- four closed-vocabulary validators collapse into one general rule
    - Candidate B2 -- retire the two vocabulary accessors the product itself never calls
    - Candidate B3 -- delete the restated register count in the published contract rather than updating it
    winner: A1
    ship: PUSHED 962df3b
  iter-67
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- `radar scan` publishes the operator's home directory on both surfaces, so a committed report is machine-local
    - Candidate A2 -- `tools/verify_quotes.py` certifies a vacuous domain, is the outlier of three doors, and has no tests
    - Candidate A3 -- `checks._TRACKED_CACHE` outlives the scan, in the module whose own docstring forbids that
    - Candidate B1 -- `radar prd` emits `userStories`, and the one declared consumer's reader answers `valid=False, total=0` on our bytes
    - Candidate B2 -- `radar scan` finds 2 PRESENT gaps and exits 0, while the published contract has already RESERVED exit 1 for the verdict code
    - Candidate B3 -- the below-floor prescription shipped as a human table column, so no gate can assert it
    winner: B2
    ship: PUSHED c86a51e
  iter-66
    lenses: new-capability, hardening/DX
    - Candidate A1 -- `radar sources`: a register-wide source inventory, so one document carrying three records becomes visible
    - Candidate B1 -- deterministic evidence staleness (roadmap row 10), anchored to a supplied date and never to the wall clock
    - Candidate C1 -- `radar list --layer <L>` (roadmap row 16), publishing the denominator it omits
    - Candidate B1 -- `radar list` reaches the published `document()` renderer, closing the last zero-byte verb (roadmap row 23)
    - Candidate B2 -- one `live_ids()` test helper, then a census brake scoped to its callers (roadmap row 28)
    - Candidate B3 -- the roadmap index/archive split, sized from where the bytes actually are (roadmap rows 64 and 70)
    winner: B1
    ship: PUSHED 920cb29
  iter-65
    lenses: narrative-and-docs, new-capability
    - Candidate A1 -- UNKNOWN acquired a second meaning in iteration 63 and no published document says so
    - Candidate A2 -- the contract's honesty rule requires `is open`, and the register's #2 record fails it
    - Candidate A3 -- the contract restates two counts it does not derive, both now wrong, and contradicts itself twenty lines later
    - Candidate B1 -- publish the distinct-SOURCE denominator that the corroboration rule already keys on
    - Candidate B2 -- evidence staleness, with the as-of input made explicit
    - Candidate B3 -- `radar list --layer L`, the filter row 16 deliberately deferred
    winner: B1
    ship: PUSHED fe59e55
  iter-64
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A -- memoise the file ENUMERATION for the life of a scan, and correct row 67's headline figure
    - Candidate B -- stop the content scan once its boolean is already decided (row 47, first bite only)
    - Candidate C -- a verb that needs no records still pays the full pydantic import: 100.7 ms of fixed startup, on every invocation
    - Candidate B1 -- the consumer contract restates a record count it does not derive, and it is now wrong by 60% (roadmap row 20)
    - Candidate B2 -- the README's confidence rule describes the pre-iteration-18 behaviour (roadmap row 49)
    - Candidate B3 -- iteration 63 changed what ABSENT and UNKNOWN MEAN, and no published document says so (no roadmap row yet)
    winner: B2
    ship: PUSHED c591b7e
  iter-63
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- delete `MAX_SCAN_FILES`: a cap applied after the walk it claims to bound, which silently shrinks the scan domain
    - Candidate A2 -- delete `_TRACKED_CACHE`, so `checks.py` has ONE cache lifetime instead of two (roadmap row 43)
    - Candidate A3 -- retire `tools/check_locators.py`: one out-of-band network checker, not two
    - Candidate A -- one alternation pass per file instead of one pass per pattern
    - Candidate B -- memoise the enumeration per scan, like the read cache already does
    - Candidate C -- charge the register for its own scan cost (`scan --timing`)
    winner: A1
    ship: PUSHED bee84a0
  iter-62
    lenses: integration-and-adoption, simplification-and-deletion
    - Candidate A1 -- make the derived scores reachable without pydantic, so the one real consumer can read the ranking (roadmap row 33)
    - Candidate A2 -- an opt-in, floor-gated verdict exit code for `radar scan` (roadmap row 25)
    - Candidate A3 -- the scan document names an absolute machine path, so a committed scan is not portable (roadmap row 34)
    - Candidate B1 -- delete `taxonomy.layer_names()` and `gap_type_names()`, two public aliases nothing in production calls
    - Candidate B2 -- collapse FOUR locator predicates into one shared definition (roadmap row 57)
    - Candidate B3 -- `PRODUCT.md` is 8,705 chars past the roadmap wall and the breach grows every iteration (roadmap row 64)
    winner: A1
    ship: PUSHED 98be130
  iter-61
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- three literal iteration-number pins red the next ship commit, and the product's own tool says the document is CLEAN
    - Candidate A2 -- the ingest door admits the one pattern shape the suite forbids, so a research pass can red an unrelated future iteration
    - Candidate A3 -- the public-repo safety bar is prose in 19 files and an executable check over 2
    - Candidate B1 -- `radar prd` wraps its stories in `userStories`; the one declared consumer reads `stories`, so the hand-off answers `valid=False, total=0`
    - Candidate B2 -- `radar scan` finds three above-floor PRESENT gaps and exits 0, so a CI gate learns nothing from the exit code (roadmap row 25)
    - Candidate B3 -- `status` is OPTIONAL in our schema and REQUIRED by the declared consumer, so a schema-valid record can vanish from the only surface anything consumes
    winner: A1
    ship: REVERTED
  iter-60
    lenses: new-capability, hardening/DX -- iteration 60
    - A1 -- Evidence staleness: a record publishes the age of its newest citation
    - A2 -- The report publishes distinct SOURCE DOCUMENTS, not just a citation count
    - A3 -- `radar list --layer L`, with the count it excluded stated in the output
    - Candidate B1 -- `radar list` answers a zero-record register with zero bytes, while every sibling surface answers
    - Candidate B2 -- the ingest door admits the check-pattern shape the suite brakes, so bad data detonates later as a RED suite
    - Candidate B3 -- the locator resolver reports `0 broken` and exits 0 over locators it never checked
    winner: B1
    ship: REVERTED
  iter-31
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- The roadmap-ledger brake cannot fire until the commit it judges exists, so a forgotten row destroys an iteration instead of failing a check
    - Candidate A2 -- A brake against a closed-set live-register id census (row 28), plus the measurement showing both cheap versions of it are wrong
    - Candidate A3 -- `checks._TRACKED_CACHE` is process-lifetime in the one module that argues against process-lifetime caches (row 43)
    - Candidate B1 -- `radar prd` output is `valid=False` to the declared consumer's prd reader, over one wrapper key
    - Candidate B2 -- `radar scan` exits 0 while reporting PRESENT findings, and exit 1 is already reserved for it
    - Candidate B3 -- the one wired consumer cannot reach `priority` at all, and its ordering agrees with ours only because of its layer filter
    winner: B1
    ship: PUSHED 60a0fce
  iter-30
    lenses: new-capability, hardening/DX
    - Candidate A1 -- `radar report --as-of DATE` flags a record whose newest citation is older than N months
    - Candidate A2 -- a source-independence view: publish the distinct-source count the corroboration rule already keys on
    - Candidate A3 -- `radar scan` gains an opt-in, floor-gated non-zero exit code
    - Candidate B1 -- `_iter_walked` gains the escaping-symlink containment `_iter_tracked` already has
    - Candidate B2 -- the public-repo safety bar becomes one derived brake instead of 19 prose claims
    - Candidate B3 -- a suite brake against a closed-set live-register id census
    winner: B1
    ship: REVERTED
  iter-29
    lenses: narrative-and-docs, new-capability -- iteration 29
    - Candidate A1 -- the fence iteration 28 added says the loader accepts it as a check; measured, the loader refuses it twice
    - Candidate A2 -- the contract tells a gate to require `open`, and two of the register's top four are `partially-addressed` (row 39)
    - Candidate A3 -- delete the restated register count from the machine-consumer contract (row 20)
    - Candidate B1 -- a derived review-due axis: how old is each record's newest citation, measured against the register's own clock
    - Candidate B2 -- `radar show` states whether the gap is DETECTABLE, and how
    - Candidate B3 -- publish the DISTINCT-SOURCE count wherever the citation count is already published
    winner: B2
    ship: PUSHED 813038f
  iter-28
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A1 -- memoise file selection for the duration of one scan
    - Candidate A2 -- a necessary-literal prefilter before the regex pass
    - Candidate A3 -- stop paying a 126 ms pydantic import on invocations that never touch a model
    - Candidate B1 -- the research contract documents a rule shape the loader REJECTS, so a candidate written exactly to spec dies at the door
    - Candidate B2 -- the machine-consumer contract restates a register count, is wrong by six records, and the row-30 oracle is structurally blind to it
    - Candidate B3 -- the contract's honesty rule tells a gate to require `open`, and two of the register's top four are `partially-addressed`
    winner: B1
    ship: PUSHED 2cb1c2f
  iter-27
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- One match stage: the two `iter_files` branches stop carrying two copies of the loop the function already documents as shared
    - Candidate A2 -- One record slug, not two: `prd._slug` and `promote._slug` disagree on all 16 live titles
    - Candidate A3 -- Delete `MAX_SCAN_FILES`: a bound applied after the work it claims to bound, which silently drops files from a sorted list
    - Candidate B1 -- one register pattern is 57% of the whole scan, and its leading `[\w/.-]*` is provably free
    - Candidate B2 -- resolve each (globs, exclude_tests) file list once per scan
    winner: B1
    ship: PUSHED 23f9405
  iter-26
    lenses: integration-and-adoption, simplification-and-deletion
    - Candidate A1 -- `radar list --json` carries the below-floor prescription a gate can assert
    - Candidate A2 -- `radar scan` gains the opt-in, floor-gated verdict exit code that iteration 25 pre-reserved
    - Candidate A3 -- the scan document's `target` is portable, so a scan artifact can be committed and diffed
    - Candidate B1 -- delete the second glob dialect: `_iter_walked` matches with `_glob_regex` instead of `Path.glob`
    - Candidate B2 -- delete one of the two slug dialects, so the register has one filename convention
    - Candidate B3 -- one membership rule for four closed vocabularies, and one way to name one
    winner: B1
    ship: PUSHED 7570c39
  iter-25
    lenses: hardening/DX -- iteration 25, integration-and-adoption -- iteration 25
    - Candidate A1 -- the CLI's published error contract does not survive a reader that stops reading
    - Candidate A2 -- the tracked-set cache outlives the scan it belongs to (roadmap row 43)
    - Candidate A3 -- an UNREADABLE register is reported as an EMPTY register
    - Candidate B1 -- a scan that finds three above-floor PRESENT gaps exits 0, so nothing but a JSON parser can consume it (roadmap row 25)
    - Candidate B2 -- the `prd.json` payload is the vision's whole bridge and no document lists a single one of its keys
    - Candidate B3 -- the below-floor prescription reaches the human table and not the machine payload (roadmap row 21)
    winner: A1
    ship: PUSHED 13ed4c9
  iter-24
    lenses: new-capability, hardening/DX
    - Candidate A -- `radar show` states whether the gap is DETECTABLE, and how
    - Candidate B -- evidence staleness: surface how old a record's newest citation is
    - Candidate C -- publish the DISTINCT-SOURCE count, not just the citation count
    - Candidate B1 -- `Evidence.locator` gains the validator its twin `quote` already has (row 44)
    - Candidate B2 -- the tracked-file memo moves into the scan scope that already exists (row 43)
    - Candidate B3 -- the research contract's rule-kind sentence is wrong, and the brake row 38 proposes cannot see it (row 38)
    winner: B1
    ship: PUSHED 2389ba8
  iter-23
    lenses: narrative-and-docs, new-capability
    - Candidate A1 -- the research contract documents a rule shape the schema gate REJECTS, and the gate still exits 0
    - Candidate A2 -- the front door still publishes the pre-iteration-18 confidence rule, and the consumer contract publishes the corrected one
    - Candidate A3 -- the stable-surface table marks `radar prd --gap` REQUIRED, it is optional, and the row-30 oracle is provably blind to the difference
    - Candidate B1 -- `radar prd` throws away the two-sided fixtures the register already holds, so its first story asks a build loop to invent the reproduction the register could hand it
    - Candidate B2 -- 15 of the register's 41 citations re-use a locator already cited elsewhere, and no surface names a source that three records depend on
    - Candidate B3 -- `radar list --layer L`, the product's first omission mechanism, with the omission counted out loud
    winner: B1
    ship: PUSHED 6a9e175
  iter-22
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A1 -- reject a file before the regex runs, using literals the pattern itself requires
    - Candidate B1 -- memoise the target file enumeration for the life of one scan
    - Candidate C1 -- stop paying pydantic's import on verbs that load no records
    - Candidate B1 -- README states the pre-iteration-18 corroboration rule, so the front door and the consumer contract now disagree about the one invariant VISION.md protects
    - Candidate B2 -- the stable-surface table's `<>` versus `[]` notation carries no meaning, and none of the six real defaults is published
    - Candidate B3 -- the research spec's self-verify step cannot tell "my candidate was accepted" from "the gate never saw my file"
    winner: B3
    ship: PUSHED 57c0407
  iter-21
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- the `taxonomy` verb hand-rolls the one-newline tail, and the row-32 brake is structurally blind to it
    - Candidate A2 -- one JSON tail, not three, and `sort_keys=False` is a no-op spelled three times
    - Candidate A3 -- the consumer contract re-enumerates the promote gate's refusal rules, so the document carries a second copy of a rule `tools/promote.py` owns
    - Candidate B1 -- `content_absent` stops at the first hitting file
    - Candidate B2 -- a boolean-only context stops at the first hit (`applies_when`, `not`)
    - Candidate B3 -- resolve each `(globs, exclude_tests)` file list once per scan
    winner: A1
    ship: PUSHED 7c09e77
  iter-20
    lenses: integration-and-adoption (iteration 20), simplification-and-deletion (iteration 20)
    - Candidate A1 -- the only surface a live consumer reads is the record file, and the contract never mentions it
    - Candidate A2 -- `radar scan` spends the one universal integration surface on nothing (roadmap row 25)
    - Candidate A3 -- the derived scores are unreachable without pydantic, and the consumer has now SHIPPED the workaround (roadmap row 33)
    - Candidate B1 -- two caps on "locations reported per rule": one named constant and one magic `10`
    - Candidate B2 -- `taxonomy.gap_type_names()` is a dead public accessor; its sibling is called only by tests
    - Candidate B3 -- roadmap row 20: DELETE the restated seed-record count, do not correct it
    winner: A1
    ship: PUSHED 707bdff
  iter-19
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- `Evidence.locator` has no validator, so a citation nobody can check passes `radar validate`
    - Candidate A2 -- `_TRACKED_CACHE` is process-lifetime, inside the one module that argues against process-lifetime caches
    - Candidate A3 -- bare `radar` writes 923 bytes of help to STDOUT and exits 0
    - Candidate B1 -- `radar scan` reports a clean target when the register is EMPTY, on the one verb the consumer contract points a CI gate at
    - Candidate B2 -- the below-floor promotion prescription reaches ONLY a human markdown table, so a gate must scrape prose to read it
    - Candidate B3 -- `radar scan` publishes an absolute machine path, so the same scan of the same target is not the same document on two machines
    winner: B1
    ship: PUSHED a152804
  iter-18
    lenses: new-capability, hardening/DX
    - Candidate A1 -- `radar show` never shows the check, so the register's deep view cannot say whether a record is detectable at all
    - Candidate A2 -- one source cited under two class labels earns a corroboration point, so a record can lift its own confidence without new evidence
    - Candidate A3 -- evidence staleness measured against the register's own newest citation, so the age is derived and needs no clock
    - Candidate B1 -- four live-register content premises keep the iteration-09 landmine armed, and row 28's brake as written cannot see them
    - Candidate B2 -- the quote verifier passes an unbounded fabricated tail and exits 0, and it has no test at all
    - Candidate B3 -- the suite's own PASS marker is suppressible: addopts carries `-q`, so any caller adding `-q` composes to `-qq` and the summary line vanishes while the exit code stays 0
    winner: A2
    ship: PUSHED 2ccba93
  iter-17
    lenses: narrative-and-docs, new-capability
    - Candidate A1 -- the research pass's own spec documents the `not` combinator with the wrong key, and the register disproves it
    - Candidate A2 -- the consumer contract's honesty gate says a cited gap must be "open"; the register's number-two record is `partially-addressed`
    - Candidate A3 -- roadmap row 20, sixth nomination, and the defect that is NOT the stale count
    - Candidate B1 -- `radar report` names every layer in the taxonomy, so an unexamined layer stops being invisible
    - Candidate B2 -- evidence staleness as a derived age with an explicit `--as-of`, and no wall clock
    - Candidate B3 -- overlap detection keyed on shared citations, because the roadmap's title-token mechanism is measurably dead
    winner: B1
    ship: PUSHED be89396
  iter-16
    lenses: performance-and-throughput (iter 16), narrative-and-docs (iter 16)
    - Candidate A1 -- one register pattern is 39% of all regex time, and 7.4x of it is provably free
    - Candidate A2 -- the per-scan memo covers file CONTENT but not the PATH FACTS around it
    - Candidate A3 -- the register cannot see the cost of its own patterns
    - Candidate B1 -- the consumer contract advertises a ninth verb that has no roadmap row, no owner and no code
    - Candidate B2 -- the contract's two restated register counts go, and the brake distinguishes the two kinds of restated number
    - Candidate B3 -- the pydantic-free import surface gets written down BEFORE row 33 gets a line of code
    winner: B1
    ship: PUSHED 2ddb360
  iter-15
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate B1 -- one JSON document contract, not three
    - Candidate B2 -- one way to ask whether a rule matched, and `RuleHit.__bool__` goes
    - Candidate B3 -- the confidence floor default stops being declared four times
    - Candidate B1 -- scan-scoped read cache (roadmap row 29), with its ceiling corrected to 23%
    - Candidate B2 -- memoise the (pattern, file) decision, not just the file
    - Candidate B3 -- pending suite measurement
    winner: B1
    ship: PUSHED 62ab326
  iter-14
    lenses: integration-and-adoption (iteration 14)
    - Candidate A1 -- The derived scores are unreachable without installing pydantic, so the one real consumer re-implements the ranking and inverts it
    - Candidate A2 -- `radar scan` still reports a clean target over an empty register, and it is now the LAST verb that does (roadmap row 24)
    - Candidate A3 -- Scan output embeds an absolute machine path, so the artifact a consumer commits is neither portable nor byte-stable across machines
    - Candidate B1 -- `scan.py` stops carrying private copies of `render.py` document primitives
    - Candidate B2 -- the confidence floor default stops being spelled as an unnamed `2`
    - Candidate B3 -- `tools/check_locators.py` stops carrying a second register loader
    winner: B1
    ship: PUSHED 4c5968b
  iter-13
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- Derive the confidence-floor default from the scoring constant instead of hand-copying it
    - Candidate A2 -- One renderer contract test, enumerated from the module surface, that reds the suite when a new renderer arrives uncovered
    - Candidate A3 -- Settle the vacuous edge of the one-newline contract: `radar list` over a zero-record register writes zero bytes
    - Candidate B1 -- `scan --json` publishes the confidence floor it applied, and flags each finding against it
    - Candidate B2 -- `radar diff --json`: the contract's own non-regression mechanism has no machine surface
    - Candidate B3 -- `list --json` carries the below-floor prescription a gate can assert (roadmap row 21)
    winner: B1
    ship: PUSHED dc35e78
  iter-12
    lenses: new-capability, hardening/DX
    - Candidate A1 -- `radar coverage`: name the layers the register has never examined
    - Candidate B1 -- `radar list --layer L`, the product's first omission mechanism
    - Candidate C1 -- evidence staleness, flagged against an explicit `--as-of` date
    - Candidate A2 -- the quote verifier passes an unbounded fabricated tail and exits 0
    - Candidate B2 -- `radar scan` states how many records it applied, and the count is asserted as an identity
    - Candidate C2 -- `radar list` writes zero bytes over an empty register while its own `--json` twin writes a document
    winner: A2
    ship: PUSHED 6d0ec8b
  iter-11
    lenses: narrative-and-docs, new-capability
    - Candidate A -- roadmap row 20, reframed: the contract's Promise cells are structurally unchecked
    - Candidate B -- the published surface's third axis: four measured optionality disagreements, and two tracked docs contradicting each other
    - Candidate C -- the contract never says what `radar scan`'s exit code means, and a gate author's default guess is wrong
    - Candidate A1 -- `radar diff OLD NEW`: make an unattended research pass reviewable (roadmap row 12)
    - Candidate A2 -- the two AUTOMATIC prd paths stop building against a record the register itself calls addressed
    - Candidate A3 -- evidence staleness as a third axis, computed from an explicit `--as-of` (roadmap row 10)
    winner: A1
    ship: unknown
  iter-10
    lenses: performance-and-throughput (iteration 10), narrative-and-docs (iteration 10)
    - Candidate A -- `radar scan` reads each file once per scan (roadmap row 29)
    - Candidate B -- glob resolution is recomputed per rule
    - Candidate C -- the suite re-loads and re-validates the live register per test
    - Candidate B1 -- the consumer contract's record count decays by scope, not by arithmetic (roadmap row 20)
    - Candidate B2 -- the "stable surface" table is hand-copied, and 5 of its 7 rows omit a real flag
    - Candidate B3 -- two repos agree on `radar ingest`; neither roadmap has a row for it
    winner: B2
    ship: PUSHED 108bc65
  iter-09
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- delete the live-register twin of a synthetic test that already proves the same thing
    - Candidate A2 -- one confidence-floor default, not three spellings; delete cli.py's two dead imports
    - Candidate A3 -- one document-terminator contract, not five implementations
    - Candidate B1 -- one read per file per scan: 173 MB decoded to cover a 2 MB repo
    - Candidate B2 -- the tracked set is re-projected to relative paths on every rule
    - Candidate B3 -- placeholder, being measured
    winner: A1
    ship: PUSHED 1e00bfe
  iter-08
    lenses: integration-and-adoption (iteration 08), simplification-and-deletion (iteration 08)
    - Candidate A1 -- `radar scan` states the size of the register it applied, so a zero-record domain stops reading as a clean target
    - Candidate A2 -- `radar scan --gaps` stops defaulting to the current directory, the one verb whose register and target are different paths
    - Candidate A3 -- `radar list --json` carries the below-floor prescription and the strongest source class a gate can assert
    - B1 -- delete `taxonomy.layer_names()` and `taxonomy.gap_type_names()`, which nothing has ever called
    - B2 -- collapse `rank()` and `below_floor()` into one partition, so never-dropping a record stops being a coincidence
    - B3 -- delete `RuleHit.__bool__`, the dormant second way to ask the question the fail-open boundary turns on
    winner: B2
    ship: PUSHED 04b81e0
  iter-07
    lenses: hardening/DX, integration-and-adoption
    - Candidate A1 -- `strongest_source()` derived from the ladder, killing the alphabetical `min()`
    - Candidate A2 -- `radar scan` reports the size of the register it applied
    - Candidate A3 -- the CLI contract test derives its verb list from `build_parser()`
    - Candidate B1 -- commit the derived index as a file, so a consumer needs no install to read the register honestly
    - Candidate B2 -- `radar scan` gains an opt-in, floor-gated non-zero exit code
    - Candidate B3 -- `radar taxonomy` publishes the status vocabulary, and gains `--json`
    winner: A1
    ship: PUSHED a181ae8
  iter-06
    lenses: new-capability -- iteration 06, hardening/DX (iteration 06)
    - Candidate A1 -- the report's layer table drops every layer with zero records, so "never examined" is a thing the register cannot say
    - Candidate A2 -- the `status` lifecycle field is inert, so a gap the register itself calls addressed still ranks and can still be handed to a build loop
    - Candidate A3 -- a review-due axis: records whose newest citation has aged past a threshold, kept strictly out of confidence
    - B1 -- `radar validate` must fail when it examined zero records
    - B2 -- One ladder-order helper: "Strongest source" is currently sorted alphabetically
    - B3 -- Offline two-sided tests for the quote verifier, the one guard nothing tests
    winner: B1
    ship: PUSHED dc737f9
  iter-05
    lenses: narrative-and-docs, new-capability
    - A1 -- The contract a machine consumer reads still describes a ten-record register with nine checks; it is sixteen and fifteen (roadmap #20)
    - A2 -- The published verb table omits the exact flag the same document tells a CI gate to consume
    - A3 -- The README's coverage sentence is three layers stale, and the two layers that have never had a record are the fact worth stating
    - Candidate B1 -- the below-floor queue names the exact citation that would lift each record
    - Candidate B2 -- name the layers the register has never examined
    - Candidate B3 -- flag records whose newest citation has aged past a threshold
    winner: B1
    ship: PUSHED 60b2320
  iter-04
    lenses: performance-and-throughput, narrative-and-docs
    - Candidate A -- read each file at most once per scan
    - Candidate B -- resolve each distinct globset once per scan
    - Candidate C -- being measured
    - Candidate B1 -- the consumer contract tells a release gate the register has ten records; it has sixteen
    - Candidate B2 -- PRODUCT.md lost iteration 03, and still marks a shipped row as "currently landing"
    - Candidate B3 -- three documents rest on GAP-010 scoring confidence 1, and no test defends it
    winner: B2
    ship: PUSHED b91ceef
  iter-03
    lenses: simplification-and-deletion, performance-and-throughput
    - Candidate A1 -- retire `tools/check_locators.py`: one out-of-band network checker, not two
    - Candidate A2 -- one confidence-floor default, not three spellings (and delete cli.py's two dead imports)
    - Candidate A3 -- one register fixture builder, not four; delete the pair whose bodies match
    - Candidate B1 -- scan globs 181,440 paths to read 222: drive the walk from the tracked set
    - Candidate B2 -- the same glob is re-walked 32 times in one scan; memoise per scan
    - Candidate B3 -- MAX_SCAN_FILES documents a bound the code does not enforce
    winner: B1
    ship: PUSHED f2ad079
  iter-02
    lenses: integration-and-adoption (iteration 02), simplification-and-deletion
    - Candidate A1 -- `radar scan --prd` hands a build loop a below-floor gap that `radar prd` refuses
    - Candidate A2 -- an empty or misdirected register reports health: `validate` prints OK on zero records
    - Candidate A3 -- `radar list --layer L`, the one flag the in-flight consumer contract names and the CLI does not have
    - Candidate B1 -- delete the code an AST census proves nothing calls
    - Candidate B2 -- one markdown document contract, not two, and the duplicate is the untested one
    - Candidate B3 -- one two-sided fixture proof, not two gates and three tree-builders
    winner: A1
    ship: PUSHED 4b7bba7
  iter-01
    lenses: hardening/DX -- iteration 01, integration-and-adoption (iteration 01)
    - Candidate A -- "Strongest source" is computed alphabetically, not from the evidence ladder
    - Candidate B -- the two-sided fixture proof exists three times and is reachable from none of them
    - Candidate C -- pin the renderer contract against a frozen fixture register (roadmap #8)
    - Candidate B1 -- `radar list` drops below-floor records and is missing both flags its own consumer contract publishes
    - Candidate B2 -- `radar scan` hands a CI gate no exit-code signal, so the only universal integration surface carries nothing
    - Candidate B3 -- scan output embeds an absolute machine path, so the artifact a consumer commits is not portable
    winner: B1
    ship: PUSHED c143c3b
59 scouted iterations
