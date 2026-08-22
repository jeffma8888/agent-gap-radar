# agent-gap-radar

> **Layer: an instrument above the stack.** It names where in an agent stack a gap lives and ranks it by evidence class; it implements no layer itself.

Evidence-first gap radar for AI agent infrastructure: find where agents actually break, rank it honestly, then hand the top gap to a build loop.

Most "state of AI agents" content is a reading list. This is a register, and then an instrument: `radar scan` points the register at one of *your* repos and tells you which of these gaps that specific project actually has. Every gap in `gaps/` is a JSON record with a fixed schema, a closed taxonomy, at least one verbatim citation with a resolvable locator, and two scores that are deliberately kept apart: how much the gap matters, and how well we actually know it is real. The last command turns the top-ranked gap into a `prd.json` that an autonomous build loop consumes directly, so research changes what gets built instead of accumulating.

## Why the two scores never get blended

`priority` is severity x frequency x tractability. `confidence` is derived only from evidence quality: the strongest source class sets the ceiling, two citations differing in both class and source document add a point (two labels on one URL earn nothing), and anything sourced solely from model output scores zero no matter how much of it there is.

Blend them and a well-cited small problem outranks a poorly-cited large one, with no way to see which input moved. So the ranking sorts on `priority` and applies a visible `confidence` floor instead. Records below the floor are printed in their own section rather than deleted, because a weakly-sourced gap is a research task, not a mistake.

That distinction is the whole reason `GAP-010` is in the register: it is a widely-repeated market statistic whose primary survey is not linked, so it scores confidence 1 and is excluded from the ranking by the tool's own rule. A credibility ladder that never excludes anything is decoration.

## Quickstart

```bash
uv sync
uv run radar validate .          # schema-check every record; exit 2 on any problem or on zero records
uv run radar list .              # one line per record, below-floor rows flagged
uv run radar report .            # the full ranked radar (markdown)
uv run radar show GAP-003 .      # one gap in depth, with evidence and quotes
uv run radar prd .               # emit a build-loop prd.json for the top gap
uv run radar taxonomy            # the fixed vocabularies
uv run radar diff OLD NEW        # what changed between two register states (two directories you materialise)

uv run radar scan ../my-service --gaps gaps          # which gaps does THIS repo have?
uv run radar scan ../my-service --gaps gaps --json   # the same, for a CI gate
uv run radar scan ../my-service --gaps gaps --prd    # build against its worst finding that clears the floor
uv run radar scan ../my-service --gaps gaps --exit-code  # same report, but exit 1 if it has an above-floor gap (for CI)
```

## Scanning a real target

A register tells you what tends to break. A scan tells you what *your* project has. Each record can carry a `check`: a declarative rule, evaluated against a target repository, that reports one of five verdicts per gap with file:line evidence.

The rules are **data, not code**. A register that carried executable rules would be a remote-code-execution surface for anyone who pulled a shared one.

Five verdicts, never collapsed, because collapsing them is how a tool starts lying:

| Verdict | Meaning |
|---|---|
| `PRESENT` | the gap signature was found in this target |
| `ABSENT` | a mitigation was **positively identified** |
| `NOT_APPLICABLE` | the gap cannot apply here (the precondition is missing) |
| `MANUAL` | static analysis cannot honestly decide, so it asks a question instead |
| `UNKNOWN` | the check could not be run |

Three invariants make the output trustworthy rather than merely confident:

**`ABSENT` requires positive evidence of a mitigation.** The absence of a bad pattern is silence, not safety. A target where neither signature appears is reported `MANUAL`, with the question a human should answer.

**Both signatures matching yields `MANUAL`, not a pass.** A partial mitigation is the genuinely dangerous case, so it escalates to a human instead of being reported as safe.

**A mitigation named only by a test is not a mitigation.** `mitigated_when` is evaluated with test paths excluded. This was a real, proven false negative before it was a rule: a target that exhibits a gap continuously came back `ABSENT` because a test file merely *spelled* the mitigation. Credited from test text, a thorough suite reads as healthier than untested code, which inverts the signal.

Scanning is restricted to what `git ls-files` reports, so vendored dependencies and gitignored scratch cannot manufacture findings. Locators are ranked code-first and capped, with the suppressed remainder named; they are evidence that a signature exists, not a list of places to fix.

`MANUAL` is a first-class result and usually the majority verdict. A tool that answered every question would be guessing at most of them.

## How a check earns its place

Every automated check ships a **known-bad and a known-good fixture**, and a parametrized test asserts it fires on one, stays silent on the other, and reports a location. A detector nobody proved against a known-bad sample reports health it never measured, which is worse than no detector. A separate test fails if the register ever contains zero automated checks, so the suite cannot pass vacuously.

New records arrive through a gated inbox (`tools/promote.py`), because the register is fed by unattended research passes. A candidate is refused, with a written reason, unless it parses, cites at least one non-zero-weight source with a fetchable locator and a real excerpt, proves its check two-sided against its own fixtures, and is not a restatement of a check already in the register. Ids are assigned by the gate: context-free parallel agents cannot coordinate numbering, so letting them try guarantees collisions.

Quotes are then checked against the live page (`tools/verify_quotes.py`, network, out of band). A fabricated quote on a real, resolving URL is the one defect every offline signal reports as fine.

## What a gap record looks like

Records are closed-vocabulary on purpose. A gap that does not fit an existing `layer` is an argument to change the taxonomy in a pull request, not a free-text label, because free text is what turns a register into a junk drawer.

| Field group | Purpose |
|---|---|
| `layer`, `gap_type`, `status` | Where in the stack it lives, what kind of gap it is, whether it is still open |
| `problem`, `symptom`, `why_now` | The gap in the voice of the person hurt by it, what an operator observes, and why it is not already solved |
| `existing` | Partial solutions, each with the reason it falls short |
| `severity`, `frequency`, `tractability` | The three inputs to `priority`, 1-5 each |
| `evidence[]` | Source class, title, locator, date, and a verbatim quote. A citation with no excerpt is rejected by the schema |
| `build_hypothesis` | If we built one thing against this gap, what would it be |

## The evidence ladder

Source classes are ranked, and the ranking is load-bearing because confidence is computed from it rather than asserted in prose.

Strongest first: `incident-postmortem`, `first-party-field`, `peer-reviewed`, `maintainer-primary`, `vendor-primary`, `practitioner-report`, `survey-aggregate`, `secondary-summary`, `model-output`.

`model-output` carries weight zero. An LLM's opinion about the state of agent infrastructure is a hypothesis to check, never evidence, and a record whose only support is model output cannot clear any floor above zero.

## From gap to build

`radar prd` emits the `prd.json` shape used by Ralph-style loops: ordered stories, `passes` flags, verifiable acceptance criteria. Three properties are enforced by tests:

The first story is always a failing reproduction of the gap, because a loop handed a specification optimises the specification. Give it a red test and the target is unambiguous.

The emitted document carries the source gap's evidence forward, so the loop building the mitigation can see the citation that justified the work.

The payload declares whether the gap is statically detectable at all -- and where it is, it names where the register's own two-sided sample lives, as a pattern matching the gap's record file, so the reproduction story is a transcription rather than an invention. Where the register holds no signature, it says so instead of sending a loop to hunt for one.

## Current register

The register grows: unattended research passes propose records and the gate above decides which land. For the current contents run `uv run radar list .`, one line per record with below-floor rows flagged, or `uv run radar report .`, which prints the count, the ranking, and the below-floor section separately. Counts are deliberately not restated here, because a hand-maintained summary of a machine-updated source decays silently and then misleads with authority.

To review what a pass actually changed, `radar diff OLD NEW` compares two register states you materialise yourself: records added, records removed, and for records on both sides the changes in a closed set of nine fields -- `status`, `layer`, `gap_type`, the three `priority` inputs, the two derived scores, and the citation count. Free prose is never compared, so a rewording is not a change, and the two derived scores are printed as separate lines, never blended. There is deliberately no git integration: it takes two directories, so the tool has no opinion about how you produced them.

It seeded with ten records spanning observability, evaluation, orchestration, context and memory, multi-agent coordination, and lifecycle. `GAP-010` is retained *below* the confidence floor as a worked example of the ladder doing its job.

The first-party records cite specific incidents in [agent-failure-modes](https://github.com/jeffma8888/agent-failure-modes), a corpus of post-mortems from running autonomous multi-agent build loops, so a reader can check the claim rather than take it on trust.

## Checking the citations

Locators are verified out of band, never in the test suite: `python3 tools/check_locators.py gaps` for reachability, and `python3 tools/verify_quotes.py --gaps gaps` to confirm each quote is verbatim on the page it cites. The suite is offline by contract, and a test that needs the network fails on a plane and in CI without egress, which teaches a team to ignore red. Both tools read the register at run time, so neither claim needs to be restated in prose to stay true.

## Design constraints

Offline-first: no network access at runtime or in tests. One runtime dependency (pydantic v2). Deterministic output, so a report can be committed and diffed. Python 3.12+, uv-managed.

## License

MIT
