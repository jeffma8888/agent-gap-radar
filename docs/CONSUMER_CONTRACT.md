# Consumer contract

What a build loop, CI job, or PM tool may rely on when it consumes this
register, and the two things it must never do with it. Written 2026-08-16, when
the first consumer (`agent-foundry`) was specced against it.

The consumer-side design lives with the consumer:
`agent-foundry/docs/INTEGRATION_AGENT_GAP_RADAR.md`.

## The stable surface

| Verb | Promise |
|---|---|
| `radar validate <repo>` | exit 0 when at least one record was examined AND every record parses and satisfies the schema; a domain holding zero records is exit 2, never a green pass |
| `radar list [<repo>] [--json] [--floor N]` | every record, ranked first; below-floor records are DISPLAYED, flagged, never omitted |
| `radar show <ID> [<repo>]` | the full brief for one gap, markdown |
| `radar report <repo> [--floor N]` | the whole register as a human brief |
| `radar prd <repo> --gap <ID> [--project NAME]` | a build-loop `prd.json` whose FIRST story reproduces the gap as a failing test |
| `radar scan <target> [--gaps R] [--json] [--prd]` | applies every register check to a concrete repo: PRESENT / ABSENT / NOT_APPLICABLE / MANUAL / UNKNOWN per gap, with file:line locators; `--prd` emits a prd.json for the worst PRESENT finding whose confidence clears the register floor, names each skipped below-floor finding on stderr, and exits 2 if none clears |
| `radar diff <old> <new>` | what changed between two register states: records added, records removed, and per-record changes across a CLOSED set of nine fields (`status`, `layer`, `gap_type`, `severity`, `frequency`, `tractability`, `priority`, `confidence`, citation count). Free prose is never compared, so a rewording is not a change; both domain sizes are stated, so an emptied, moved or one-level-too-high side cannot read as "everything was added"; both paths are REQUIRED, so neither side can silently default to the caller's working directory; `priority` and `confidence` are reported as two separate lines and never blended |
| `radar taxonomy` | the closed vocabularies (11 layers, 8 gap types, 9 evidence classes) |

Guarantees a consumer may build on: offline always (no network at runtime or in
tests); deterministic, byte-stable output; stdout carries only the document,
errors go to stderr prefixed `Error: ` with exit 2; the taxonomy is closed, so a
consumer may switch on a layer or gap-type string.

## The invariant a consumer must not launder

`priority` and `confidence` are deliberately UNBLENDED. `priority` is
severity x frequency x tractability - how much it would matter to fix.
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
is what a release gate should consume. It is already implemented: nine of the ten
seed records carry a check, and each returns PRESENT, ABSENT, NOT_APPLICABLE,
MANUAL or UNKNOWN rather than a bare pass/fail. MANUAL is a first-class verdict -
where static analysis cannot honestly decide, the tool asks a question instead of
guessing, which is the behaviour a consumer should trust it for.

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
`confidence_floor`, `counts` keyed by verdict, `uncheckable`, `findings`, and per
finding `gap_id`, `title`, `layer`, `gap_type`, `verdict`, `priority`,
`confidence`, `below_floor`, `reason`, `question`, `locations`,
`build_hypothesis`. `priority` and `confidence` stay separate fields and no
blended `score` key exists, so the invariant survives serialisation; a test
asserts that. `confidence_floor` is the floor the scan APPLIED and `below_floor`
is derived from the `confidence` printed beside it, so a gate asserts the
never-drop rule from the payload instead of hard-coding the threshold on its own
side of the boundary. Every key the tool emits must appear in this list: the
drift this paragraph already suffered was omission, so the list is the contract
and not a summary of it. Output is byte-stable across runs.

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
  (a cited gap really exists, is open, and is above the floor) and on
  non-regression (the diff did not reintroduce a known gap).
- **Never treat a missing gap citation as a defect.** "No register gap fits
  this work" is a legitimate, common answer; forcing a citation manufactures
  false ones.
