# agent-gap-radar

Evidence-first gap radar for AI agent infrastructure: find where agents actually break, rank it honestly, then hand the top gap to a build loop.

Most "state of AI agents" content is a reading list. This is a register. Every gap in `gaps/` is a JSON record with a fixed schema, a closed taxonomy, at least one verbatim citation with a resolvable locator, and two scores that are deliberately kept apart: how much the gap matters, and how well we actually know it is real. The last command turns the top-ranked gap into a `prd.json` that an autonomous build loop consumes directly, so research changes what gets built instead of accumulating.

## Why the two scores never get blended

`priority` is severity x frequency x tractability. `confidence` is derived only from evidence quality: the strongest source class sets the ceiling, two independent classes add a point, and anything sourced solely from model output scores zero no matter how much of it there is.

Blend them and a well-cited small problem outranks a poorly-cited large one, with no way to see which input moved. So the ranking sorts on `priority` and applies a visible `confidence` floor instead. Records below the floor are printed in their own section rather than deleted, because a weakly-sourced gap is a research task, not a mistake.

That distinction is the whole reason `GAP-010` is in the register: it is a widely-repeated market statistic whose primary survey is not linked, so it scores confidence 1 and is excluded from the ranking by the tool's own rule. A credibility ladder that never excludes anything is decoration.

## Quickstart

```bash
uv sync
uv run radar validate .          # schema-check every record, exit 2 on any problem
uv run radar list .              # one line per ranked gap
uv run radar report .            # the full ranked radar (markdown)
uv run radar show GAP-003 .      # one gap in depth, with evidence and quotes
uv run radar prd .               # emit a build-loop prd.json for the top gap
uv run radar taxonomy            # the fixed vocabularies
```

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

`radar prd` emits the `prd.json` shape used by Ralph-style loops: ordered stories, `passes` flags, verifiable acceptance criteria. Two properties are enforced by tests:

The first story is always a failing reproduction of the gap, because a loop handed a specification optimises the specification. Give it a red test and the target is unambiguous.

The emitted document carries the source gap's evidence forward, so the loop building the mitigation can see the citation that justified the work.

## Current register

Ten seed records spanning observability, evaluation, orchestration, context and memory, multi-agent coordination, and lifecycle. Nine clear the confidence floor; one is retained below it as a worked example of the ladder doing its job.

The first-party records cite specific incidents in [agent-failure-modes](https://github.com/jeffma8888/agent-failure-modes), a corpus of post-mortems from running autonomous multi-agent build loops, so a reader can check the claim rather than take it on trust.

## Checking the citations

Locators are verified out of band, never in the test suite: `python3 tools/check_locators.py gaps`. The suite is offline by contract, and a test that needs the network fails on a plane and in CI without egress, which teaches a team to ignore red. All 13 locators in the current register resolved when last checked.

## Design constraints

Offline-first: no network access at runtime or in tests. One runtime dependency (pydantic v2). Deterministic output, so a report can be committed and diffed. Python 3.12+, uv-managed.

## License

MIT
