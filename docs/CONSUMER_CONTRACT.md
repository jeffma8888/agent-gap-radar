# Consumer contract

What a build loop, CI job, or PM tool may rely on when it consumes this
register, and the two things it must never do with it. Written 2026-08-16, when
the first consumer (`agent-foundry`) was specced against it.

The consumer-side design lives with the consumer:
`agent-foundry/docs/INTEGRATION_AGENT_GAP_RADAR.md`.

## The stable surface

| Verb | Promise |
|---|---|
| `radar validate [<repo>]` | exit 0 when at least one record was examined AND every record parses and satisfies the schema; a domain holding zero records is exit 2, never a green pass |
| `radar list [<repo>] [--json] [--floor N] [--layer L]` | every record, ranked first; below-floor records are DISPLAYED, flagged, never omitted. `--layer` narrows the record DOMAIN to one layer of the closed taxonomy before the ranking is computed, so a below-floor record in that layer is still displayed and still flagged, and one document per layer concatenates to exactly the unfiltered listing -- the filter partitions the register, it does not sample it. A value outside the vocabulary `radar taxonomy` publishes is exit 2 and an `Error: ` line naming every accepted value, never an empty document, because an empty answer to a typo is indistinguishable from a layer that genuinely holds no record -- which is itself exit 0 and an empty document. `--json` publishes the same records as a stable object -- `confidence_floor`, `counts`, `records` -- where each record carries `gap_id`, `title`, `layer`, `gap_type`, `status`, `priority`, `confidence`, `below_floor`, `strongest_source`, `needs`, in that order. The last two are DERIVED from the evidence ladder and are never asserted by a record author, which makes the ladder itself machine-readable rather than only its result: `strongest_source` is the `source_class` of the record's best citation ranked by ladder RUNG and never alphabetically, published for EVERY record, so a consumer can read what the `confidence` integer was derived FROM; `needs` is the research prescription -- the cheapest source classes a single further citation could belong to that would lift the record to the floor this invocation APPLIED, in ladder order, strongest rung first, with `model-output` never offered because evidence that is exclusively model-output scores 0 and so can lift nothing. `needs` is `null` if and only if `below_floor` is false, and an array if and only if `below_floor` is true; neither key is ever omitted, so a gate asserts both halves instead of inferring one from an absence. An EMPTY array is an answer and not a missing one -- it means no single citation of any class reaches that floor -- and above the floor the question does not apply, which is what `null` says, because naming a class there would read as a prescription for a record that needs nothing |
| `radar show <ID> [<repo>]` | the full brief for one gap, markdown |
| `radar report [<repo>] [--floor N]` | the whole register as a human brief |
| `radar prd [<repo>] [--gap <ID>] [--project NAME]` | a build-loop `prd.json` whose FIRST story reproduces the gap as a failing test |
| `radar scan <target> [--gaps R] [--json] [--prd] [--exit-code]` | applies every register check to a concrete repo: PRESENT / ABSENT / NOT_APPLICABLE / MANUAL / UNKNOWN per gap, with file:line locators; `--prd` emits a prd.json for the worst PRESENT finding whose confidence clears the register floor, names each skipped below-floor finding on stderr, and exits 2 if none clears; `--exit-code` leaves the document byte-identical whenever it verdicts and moves the ANSWER into the exit status instead -- 1 when this target has at least one PRESENT finding that clears the floor, 0 when it has none, 2 when the scan applied zero records and so verdicted nothing. The two flags are mutually exclusive: both are floor-gated verdict surfaces, and they answer the same question with opposite codes |
| `radar diff <old> <new> [--json]` | what changed between two register states: records added, records removed, and per-record changes across a CLOSED set of nine fields (`status`, `layer`, `gap_type`, `severity`, `frequency`, `tractability`, `priority`, `confidence`, citation count). Free prose is never compared, so a rewording is not a change; both domain sizes are stated, so an emptied, moved or one-level-too-high side cannot read as "everything was added"; both paths are REQUIRED, so neither side can silently default to the caller's working directory; `priority` and `confidence` are reported as two separate lines and never blended. `--json` emits that same comparison as a stable object instead of the report, so the non-regression half of the gate rule below is ASSERTABLE rather than scraped: `counts.old` and `counts.new`, `added` and `removed` as `gap_id`/`title` entries in the order the report lists them, and per changed record only the fields that DIFFER, in that same closed order, carrying both sides exactly as they were compared. `priority` and `confidence` stay two distinct `field` entries there too, and no object at any depth carries a blended `score` key |
| `radar taxonomy` | the closed vocabularies -- layers, gap types, the evidence ladder with its weights, and record statuses. Sizes are deliberately not restated in this cell: a hand-maintained count of a machine-published vocabulary decays silently and then misleads with authority |

In every invocation above, `[x]` means the CLI accepts the run WITHOUT `x` and
`<x>` means it refuses without it. The brackets are that argument's ARITY as
`build_parser()` reports it -- `action.required` for an option, `nargs` for a
positional -- and never advice: a cell that wants to discourage omitting an
optional argument says so in its Promise instead, because the bracketing is
asserted against the parser and a nudge spelled as arity reads to a machine
consumer as a demand the tool does not make.

Guarantees a consumer may build on: offline always (no network at runtime or in
tests); deterministic, byte-stable output; stdout carries only the document,
errors go to stderr prefixed `Error: ` with exit 2; the taxonomy is closed, so a
consumer may switch on a layer or gap-type string. That `Error: ` promise covers
a refusal the tool can explain in words, which is not the only way a run ends
non-zero -- the complete set is published under `## Exit codes` immediately below,
and a test asserts that table lists exactly the codes the CLI can return.

## Exit codes

| Code | When | What a consumer should do |
|---|---|---|
| `0` | the verb produced its document | read stdout |
| `1` | OPT-IN, `scan --exit-code` only: the tool answered, and this target exhibits at least one PRESENT gap whose evidence clears the confidence floor. stdout carries the same document as the same invocation without the flag, and stderr is empty -- nothing went wrong | fail the gate, then read the `## Actionable now` section of stdout (or `--json`'s `findings`) for which gaps and where |
| `2` | the tool refuses and says why: stderr's LAST non-empty line begins `Error: `, and stdout stays empty rather than half a document. Deliberately not promised as a SINGLE line: a structural refusal -- a missing positional, an unknown verb, an unparseable flag value, an unrecognized option -- prints the `usage:` block ABOVE that line, because usage is the only place a caller learns the arity it got wrong. The prefixed line is always the last one, and argparse's own `<prog>: error: ...` spelling never reaches stderr, so one deterministic line answers every exit-2 door | read stderr's LAST non-empty line -- it names the register, the path, the record or the argument at fault |
| `141` | the READER went away: stdout's pipe was closed, or the reader exited before the document finished. stderr is EMPTY and stdout is truncated, because nothing was wrong with the register | treat it as the consumer's own early exit, never as a defect here. It is the shell's 128+SIGPIPE, so head, grep -q and less see the code they already expect |

Every code `radar` can return is above, and nothing else. That table is the
contract and not a summary of one: a test reads it and asserts its backticked
integers EQUAL `cli.EXIT_CODES`, in BOTH directions, so a code the CLI gained but
the document omits fails, and so does a row for a code the CLI cannot produce. It
sits immediately under its heading on purpose -- the reader that checks it fails
closed on a table it cannot find, and prose between the two is enough to hide it.

Exit 1 was held unused and unlisted for one named purpose, and that purpose has
now arrived: it is the floor-gated verdict code of `scan --exit-code` (roadmap
row 25), which is why the row above describes a gate result rather than a
failure. Two properties of that code are worth stating plainly, because a gate is
built on them. It is OPT-IN, so no invocation that works today can start
returning it -- `scan` without the flag still exits 0 whatever it finds. And it
is FLOOR-GATED, so a record whose only evidence is model output can never turn a
build red: below-floor PRESENT findings still appear in the document, and they
report 0. The floor rule has one implementation, shared with `--prd`, so the two
cannot disagree about one target.

**A departing reader is never reported as this tool's error.** On 141 stderr
carries no `Error: ` line, no `BrokenPipeError` and no traceback. Getting that
right needed the guard to FLUSH stdout itself: a document smaller than the pipe
buffer sits in the text layer until interpreter shutdown, where a broken pipe is
past every handler and CPython answers with 120 plus an `Exception ignored on
flushing sys.stdout` line -- on the stderr this document promises carries only
`Error: `. The 141 path also points the process's stdout descriptor at the null
device, so that shutdown flush cannot re-raise.

## The record file surface

The register is files in git, and that is the feature -- so reading a record file
directly is a supported use of this project, not a bypass of the verbs above. It
is also what the one declared consumer actually does: `agent-foundry` reads
`<register>/gaps/*.json` as plain local JSON, with no subprocess, no `uv` on the
PATH and no import of this package, and it consumes none of the verbs, none of the
JSON payloads and no exit code. Until this section existed, every byte-stability
promise this document made was made about surfaces nothing consumed, and nothing
at all covered the surface that IS consumed.

**The guarantee, bounded exactly.** One record is one JSON object, stored at
`<register>/gaps/<ID>-<slug>.json`; the id is the file name's PREFIX, so a
consumer discovers records by globbing `gaps/*.json` -- which is what the declared
consumer does -- rather than by constructing a path from an id. The key NAMES
listed below are not renamed and not removed without a Done-ledger row in
`PRODUCT.md`. New fields MAY be added at any time, and that is safe for a consumer
reading by key -- so what is frozen here is the documented subset's NAMES, not the
schema's growth. The two derived scores are deliberately NOT stored: `priority`
and `confidence` are computed from the stored integers and from the evidence
ladder, so a consumer that wants them either computes them the same way or reads
them from a verb, and the unblended invariant below binds the file exactly as it
binds the CLI.

**The shape is closed.** Both models are declared `extra="forbid"`, so a record
carrying a key this section does not list fails `radar validate` instead of
reaching a reader. A consumer may therefore treat an unrecognised key as a defect
in the register rather than as data it has to tolerate.

### Gap record keys

| Key | Required | Type | What it holds |
|---|---|---|---|
| `id` | yes | string | `GAP-000`-shaped identity, unique in the register, and the PREFIX of the record's file name |
| `title` | yes | string | one line, the gap named as a reader would refer to it |
| `layer` | yes | string | where in an agent stack the gap lives; a closed vocabulary, so a consumer may switch on it |
| `gap_type` | yes | string | what kind of gap it is; a closed vocabulary, so a consumer may switch on it |
| `status` | no | string | a closed vocabulary, published in full by `radar taxonomy`; absent means `open` |
| `problem` | yes | string | one sentence, in the voice of the person hurt by it |
| `symptom` | yes | string | what an operator actually observes |
| `why_now` | yes | string | why this is a gap today rather than a solved problem |
| `existing` | no | list of strings | partial solutions and why each falls short; absent means none recorded |
| `severity` | yes | integer | 1 to 5, the damage when the gap bites |
| `frequency` | yes | integer | 1 to 5, how often it bites a real team |
| `tractability` | yes | integer | 1 to 5, whether a small team can move it |
| `evidence` | yes | list of objects | at least one citation, each shaped by the next table |
| `build_hypothesis` | no | string | the one thing worth building against this gap; absent means none proposed |
| `tags` | no | list of strings | free labels, NOT a closed vocabulary; never switch on one |
| `check` | no | object | how to detect the gap in a target repository; absent means the gap is not checkable today |

`severity`, `frequency` and `tractability` are the whole input to `priority`, and
`priority` itself is not stored anywhere in the file.

### Evidence item keys

| Key | Required | Type | What it holds |
|---|---|---|---|
| `source_class` | yes | string | the evidence-ladder rung; a closed vocabulary, and the ceiling input to `confidence` |
| `title` | yes | string | the source as a reader would cite it |
| `locator` | yes | string | a URL, a DOI, or a stable local artifact path |
| `date` | yes | string | ISO `YYYY-MM-DD`, when the source was published |
| `quote` | yes | string | a verbatim excerpt, never a paraphrase |
| `note` | no | string | why this source supports the gap; absent means no gloss |

A consumer deriving `confidence` for itself reads `source_class` for the ceiling
AND `locator` for independence: the corroboration point requires two citations
differing in BOTH class and source document, so two labels on one URL earn
nothing. A record whose only rung is `model-output` carries confidence 0 by
construction, which is the rule the next section binds machine consumers to.

### Keys the declared consumer reads

| Key | Model | How the declared consumer reads it |
|---|---|---|
| `id` | Gap | required; a record missing it is skipped and counted as unreadable |
| `status` | Gap | required; the consumer selects on it |
| `layer` | Gap | required |
| `severity` | Gap | required |
| `frequency` | Gap | required |
| `tractability` | Gap | required |
| `title` | Gap | read with a default, so a rename arrives as an EMPTY STRING rather than an error |
| `gap_type` | Gap | read with a default, so a rename arrives as an EMPTY STRING rather than an error |
| `evidence` | Gap | read with a default, then iterated to reach each item's rung |
| `source_class` | Evidence | read with a default per evidence item, and it fails the same silent way |

**Frozen text: this table must not be edited to make a rename go green.** It
mirrors code in another repository, which no test here can read, so it is the one
part of this section not derived from our own schema. That is exactly its job: a
rename that updates the two tables above in step still reds HERE, because a key
named here that no longer exists in the schema is a cross-repo break, and the
notice arrives before the consumer starts rendering blanks. The reverse direction
-- asserting that our tables cover every key the consumer reads -- cannot be
checked from this repository at all, and stating that limit is more honest than
implying coverage: that half is a review obligation on whoever renames a
documented key.

### Deriving the scores without installing pydantic

A consumer reading `gaps/*.json` directly, as the declared consumer does, has the
stored integers and the evidence ladder but not `priority` and `confidence` --
which are deliberately not stored. It does not have to reinvent them. Three
modules of this package import with **pydantic absent**, so a reader with nothing
installed can `import agent_gap_radar.scoring` and call the same functions the
CLI calls, rather than writing a third ordering rule for the same register that
no test on either side of the repo boundary can see drift.

| Module | Imports with pydantic absent | Why |
|---|---|---|
| `agent_gap_radar.taxonomy` | yes | the closed vocabularies and their weights are plain tuples and mappings |
| `agent_gap_radar.checks` | yes | rules are DATA; the matcher is stdlib `re` over text |
| `agent_gap_radar.scoring` | yes | the two derived scores, and the below-floor prescription |
| `agent_gap_radar.models` | no | the schema IS pydantic -- validating a record is what the dependency is FOR |
| `agent_gap_radar.registry` | no | it validates every record through `models` before returning it |
| `agent_gap_radar.render` | no | downstream of a validated record |
| `agent_gap_radar.prd` | no | downstream of a validated record |
| `agent_gap_radar.scan` | no | downstream of a validated record |
| `agent_gap_radar.diff` | no | downstream of a validated record |
| `agent_gap_radar.cli` | no | the entry point loads the register, so it validates |

**This table is DERIVED, not hand-maintained.** A test installs an import blocker
for `pydantic` in-process -- with a positive control asserting `import pydantic`
really does raise first, because an absence measured by an unproven matcher is not
evidence -- imports all ten modules behind it, and asserts the set that succeeds
EQUALS the set this table marks `yes`, in both directions. So a module that later
grows a runtime pydantic import reds the suite instead of leaving this document
quietly wrong, and a module that becomes pydantic-free without being published
here reds it too.

**The record shape `scoring` requires.** It is duck-typed, and that is the
guarantee: it reads attributes, never a class. An object is scoreable when it
carries

| Attribute | On | Read by |
|---|---|---|
| `id` | the record | the tie-break in `rank` and the sort in `below_floor` |
| `severity`, `frequency`, `tractability` | the record | `priority` |
| `evidence` | the record | `confidence`, `distinct_sources`, `strongest_source`, `promotion_options` |
| `source_class` | each evidence item | the ceiling and the corroboration pair |
| `locator` | each evidence item, OPTIONALLY | source identity for the corroboration pair |

`locator` is the only optional one, and omitting it is not free: an item without
it reads as the EMPTY source key, which is a DISTINCT key rather than a neutral
one, so a record that omits one locator while another citation carries one EARNS
the corroboration point that the truth -- both citations naming the same
document -- withholds. Measured on synthetic records, strongest class weight 4:
two citations of different classes on ONE document score 4 with
`distinct_sources` 1; the same pair with the second `locator` omitted scores 5
with `distinct_sources` 2. Omitting it is safe only when EVERY item omits it,
which makes the keys coincide again. So supply the locator whenever the record
has one -- `Evidence` rejects a blank one, so every citation in `gaps/` carries
it, and this can only bite a hand-built object. A `types.SimpleNamespace` per
record and per citation is enough -- measured over the live register, the five
functions and both views answer identically to the pydantic-backed `Gap`
objects. Nothing here is a second public record shape: it is the shape the file
surface above already documents, read one attribute at a time.

## The invariant a consumer must not launder

`priority` and `confidence` are deliberately UNBLENDED. `priority` is a
weighted sum of severity x3, frequency x2 and tractability x1, normalised to
0.0-10.0 - how much it would matter to fix.
`confidence` is derived ONLY from the evidence ladder - how much we should
believe the gap is real. A single composite number would hide exactly the
distinction the register exists to preserve, so no consumer should compute one.

Two consequences that bind machine consumers specifically:

- **A record whose only evidence class is `model-output` carries confidence 0
  by construction.** It may inform a discussion. It may never justify shipping
  anything, and it may never block anything.
- **Below-floor records are shown, not dropped.** A consumer that filters them
  out silently reproduces the failure the ladder was built to prevent. Render
  them with their floor status attached (GAP-010 exists in the seed register
  specifically to keep this path exercised).

## `radar scan` - the verb a gate consumes (SHIPPED), and what it still owes

`scan` is what turns the register from a reading list into an instrument, and it
is what a release gate should consume. It is already implemented: nearly every
record carries a check, and each returns PRESENT, ABSENT, NOT_APPLICABLE,
MANUAL or UNKNOWN rather than a bare pass/fail. The exact count is
deliberately not restated here -- `radar scan` prints `Register records
applied` and `Gaps with no check yet` on every run, and a hand-maintained
restatement of a number the research pipeline changes decays silently and then
misleads with authority. MANUAL is a first-class verdict - where static
analysis cannot honestly decide, the tool asks a question instead of guessing,
which is the behaviour a consumer should trust it for.

**First real target, 2026-08-16: `agent-foundry`** (a 200+-iteration autonomous
loop whose defects are independently documented, so its ground truth was known
before the scan ran). Result: 2 PRESENT, 1 ABSENT, 1 NOT_APPLICABLE, 5 MANUAL,
0 UNKNOWN. GAP-006 PRESENT was a true positive on that repo's single worst known
live defect - a missing verdict token parsed as a revert, which had already
destroyed a fully-verified iteration.

Two defects that same run exposed, both of which must be fixed before any
consumer lets a check BLOCK a release. **Both were fixed the same day; the
diagnosis below is kept verbatim because the reasoning is the durable part.**

1. **CHK-009 fail-open (a proven false negative).** GAP-009 was reported ABSENT
   with a "positively identified mitigation" citing a TEST file. The target
   exhibits GAP-009 continuously and ships a dedicated verb to measure it. The
   `mitigated_when` pattern (`importlib.reload|self_restart|--restart|os.execv`)
   matched test text that merely mentions reloading. **Fix: exclude test globs
   from every `mitigated_when`.** A mitigation must be found in code that runs,
   never in a test that names it - otherwise thorough test suites read as
   healthier than untested code, which inverts the signal.
   **FIXED structurally, not per-check:** `mitigated_when` is now always
   evaluated with test paths excluded, and the flag propagates through every
   nested combinator, so a future research candidate cannot reintroduce it. The
   real target re-scanned from 2 PRESENT / 1 ABSENT to 3 PRESENT / 0 ABSENT.
   Regression test: a tree whose only mention of the mitigation is in a test
   must not report ABSENT, plus a positive control so the exclusion did not
   simply break detection, plus word-boundary cases (`latest`, `protest`,
   `manifest` are not test paths).
2. **Locator noise on lexical checks.** CHK-006's verdict was right while 12 of
   its 13 locators were test files that merely spell `PUSHED|REVERTED|verdict`.
   Report the locators as evidence-of-signature, not as a fix list, until a
   check can rank them.
   **FIXED:** locators are now ranked code-first at the point the cap is applied
   (ranking after the cap would have been cosmetic), the heading reads
   "Signature seen at (evidence, ranked code first)", and the suppressed
   remainder is named rather than silently cut. On the real target GAP-003 now
   leads with `dispatcher.py` and `watchdog.py` instead of eighteen test files.

**`scan --json` SHIPPED.** A gate gets a stable object: `target`, `target_name`,
`confidence_floor`, `records_applied`, `counts` keyed by verdict, `uncheckable`,
`findings`, and per finding `gap_id`, `title`, `layer`, `gap_type`, `verdict`,
`priority`, `confidence`, `below_floor`, `reason`, `question`, `locations`,
`build_hypothesis`, `status`. `status` is the record's own stored value, passed
through unchanged, so the traceability clause's citable-status test is answerable
payload instead of requiring a second read of the register; publishing it selects
nothing, and a below-floor or non-`open` record is still DISPLAYED, never dropped.
`priority` and `confidence` stay separate fields and no
blended `score` key exists, so the invariant survives serialisation; a test
asserts that. `confidence_floor` is the floor the scan APPLIED and `below_floor`
is derived from the `confidence` printed beside it, so a gate asserts the
never-drop rule from the payload instead of hard-coding the threshold on its own
side of the boundary. `records_applied` is how many register records the scan
reached -- `findings` plus `uncheckable` -- so a gate can tell an all-zero
`counts` over a real register from one over a register that never loaded, which
are otherwise the same payload and the wrong reading is the reassuring one.
`target` ECHOES the target the caller named, verbatim -- no expansion, no
resolution, no trailing-slash normalisation -- so `radar scan .` publishes `.`
and not the scanning machine's resolved root: the artifact a gate commits and
diffs is reproducible off the machine that produced it, and carries no account
name. `target_name` is the portable identity to key on -- the resolved
directory's base name, unaffected by how the invocation spelled the path -- so
the payload still says WHAT was scanned.
Every key the tool emits must appear in this list: the drift this paragraph
already suffered was omission, so the list is the contract and not a summary of
it. Output is byte-stable across runs of one INVOCATION; two spellings of one
directory agree key-for-key except in `target`.

## The prd payload -- the five top-level keys, published

Both prd surfaces -- the prd verb, and the scan verb run with its prd flag -- emit ONE
JSON object, and these are the complete top-level keys it carries, in emitted order:
`project`, `branchName`, `description`, `sourceGap`, `stories`.

`stories` carries the ordered story array a build loop iterates and writes back to as
each story's pass flag flips. It is spelled that way because the one declared consumer's
reader accepts a bare array or an object whose `stories` value is a list, and that
ecosystem's own prd producer emits the same shape. Measured against live emitted bytes,
the earlier wrapper name made that reader answer zero stories and made the consuming
dispatcher render a present file as unparseable -- so the hand-off this product exists
to complete failed on the name of one key and nothing else.

The payload carries exactly ONE copy of the story list, under exactly one name, and no
compatibility alias is emitted. A prd document is a file the consuming loop WRITES BACK
to as each pass flag flips, so two copies of one list can diverge in the consumer's own
hand and a reader may then count the stale one: a silent wrong answer of exactly the
class this register exists to name, which is worse than a rename a consumer can see.

This list is the contract and not a summary of it. A test DERIVES the expected set from
the emitter's own bytes and compares it to the key names backticked in this section, in
both directions, so a key added to the payload reds the suite until this document names
it, and a key named here that the tool does not emit reds it too. That same comparison
runs against both prd surfaces, which are asserted EQUAL to each other, so a later
rename cannot fix one surface and leave the other behind.

### The sourceGap object -- the eight inner keys, published

`sourceGap` carries, in emitted order, `id`, `layer`, `gapType`, `priority`,
`confidence`, `evidence`, `check`, `status`. `status` is read from the register
record and published verbatim: the prd is the document that enters a build
loop's prompt, so a `partially-addressed` record must not arrive there looking
fresh. It is published, not acted on -- the prd verb selects the same record
whatever the status says.

## `radar ingest` - the reverse direction (NOT PLANNED)

**Decided in iteration 16: not planned, and not built.** When that decision was
taken there was no parser entry, no roadmap row and no code, and this document
was the only tracked file that named the verb - so a consumer could plan against
a verb that was never going to arrive. The roadmap row added alongside this
edit records the decision; it does not re-promise the verb. The design note below is KEPT rather than deleted, because its
argument is the invariant `VISION.md` names as the one this register exists to
protect.

The idea. A running agent loop is the best available source of
`first-party-field` evidence: its own stage kills, reverts and role lessons are
primary records of gaps in the very stack this register describes, so a verb
could read such a corpus and propose DRAFT records.

The discipline that would have to come with it: a drafted record enters BELOW
the confidence floor and stays displayed-but-not-ranked until a human promotes
it with a citation. The ladder is the product. A record appended without a
citation would make every score in the register unbelievable, which costs more
than the record adds.

Why no verb is needed. That job is already done, OUTSIDE the byte-stable CLI, by
`tools/promote.py` reading candidates written against
`research/CANDIDATE_CONTRACT.md`. That gate enforces this section's own value
more strictly than the section proposed: it REFUSES a candidate whose evidence
is entirely zero-weight source classes, whose locator is not a fetchable URL,
whose quote runs under six words, or whose check was never proven to fire on its
own bad fixture and stay silent on its good one - instead of admitting an
unciteable record below the floor and trusting that a human comes back for it.
It stays out of `radar` deliberately: promotion WRITES to the register and runs
a candidate's fixtures in a temporary directory, and neither belongs behind a
verb sold to consumers as read-only and byte-stable.

## What a consumer must never do

- **Never gate on "gaps closed" throughput, and never score a team on it.** A
  loop optimising against that metric will farm whatever the register makes
  cheapest to claim, and the register decays into a scoreboard. Gate on honesty
  (a cited gap really exists, carries a citable status, and is above the floor)
  and on non-regression (the diff did not reintroduce a known gap).
- **Never gate a citation on `status` being `open` alone.** The citable set is
  `taxonomy.citable_statuses()`, published by `radar taxonomy` under its
  `## Citation gate` heading; today it is `open` and `partially-addressed`. It is
  DERIVED from `taxonomy.STATUSES` by removing `taxonomy.TERMINAL_STATUSES`, the
  statuses that assert the work is already finished, so a status the register grows
  later stays citable until someone decides otherwise instead of dropping out of the
  build pipeline unannounced. Gating on `open` alone refuses a TRUTHFUL citation of a
  `partially-addressed` record, and one of the register's top three records by
  priority is exactly that. Read the partition from the vocabulary, never from the
  statuses that happen to be present in `gaps/` -- a rule has to hold for a status no
  record carries yet.
- **Never treat a missing gap citation as a defect.** "No register gap fits
  this work" is a legitimate, common answer; forcing a citation manufactures
  false ones.
