# Agent infrastructure gap radar

Records: 120 | ranked: 119 | below confidence floor (2): 1

## Ranked gaps

| Rank | ID | Priority | Confidence | Layer | Type | Title |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GAP-041 | 9.7 | 5 | observability | unverifiable | The exact context an agent was given is never persisted, so a reported failure cannot be replayed against the input that caused it |
| 2 | GAP-003 | 9.0 | 5 | orchestration | missing-contract | No checkpoint-first contract for steps running under a hard wall-clock cap |
| 3 | GAP-016 | 9.0 | 5 | tool-action | missing-primitive | An agent's action policy lives in prompt prose, so nothing can refuse a destructive tool call |
| 4 | GAP-017 | 9.0 | 5 | eval-verification | measurement-gap | An agent eval records the score but not the spend that produced it, so accuracy bought with compute is indistinguishable from a better agent |
| 5 | GAP-018 | 9.0 | 5 | context-memory | wrong-default | Memory retrieval has no relevance floor, so a top-k lookup returns k rows however far away they are and a long-lived store guarantees stale context on every turn |
| 6 | GAP-042 | 9.0 | 5 | cost-governance | missing-contract | A spend allowance does not cross the delegation boundary, so fan-out multiplies a bound the parent believed it held |
| 7 | GAP-043 | 9.0 | 5 | cost-governance | measurement-gap | Spend is never metered in flight: the provider returns token usage on every response and nothing reads it |
| 8 | GAP-044 | 9.0 | 5 | cost-governance | missing-primitive | An agent loop is bounded by an iteration count, not by cumulative spend, so the cap holds while the bill does not |
| 9 | GAP-045 | 9.0 | 5 | context-memory | wrong-default | Retrieval APIs take the tenant predicate as an optional keyword argument, so the shortest working call reads the whole shared index and nothing refuses it |
| 10 | GAP-046 | 9.0 | 5 | context-memory | missing-contract | Conversation memory is keyed by a caller-supplied thread id with nothing binding that key to the verified identity, so one request can load another tenant's context |
| 11 | GAP-047 | 9.0 | 5 | tool-action | missing-primitive | A tool credential has no channel except prompt text, so the secret becomes model context that is cached, traced and extractable |
| 12 | GAP-048 | 9.0 | 5 | context-memory | missing-contract | Retrieval runs with no identity scope, so one tenant's documents can enter another tenant's context window |
| 13 | GAP-049 | 9.0 | 5 | context-memory | missing-contract | A retrieval or memory read carries no tenant scope, so isolation depends on the embeddings happening not to match |
| 14 | GAP-050 | 9.0 | 5 | observability | measurement-gap | The fully assembled context the model consumed is never stored, so an incident is investigated against a reconstruction instead of the original |
| 15 | GAP-051 | 9.0 | 5 | human-interface | missing-contract | A human approval surface renders a summary, so the person approves something other than the bytes the tool receives |
| 16 | GAP-052 | 9.0 | 5 | tool-action | missing-contract | An egress allowlist entry is trusted for who owns the domain, not for whether that domain can carry data back to an attacker |
| 17 | GAP-053 | 9.0 | 5 | human-interface | wrong-default | The chat render surface fetches remote subresources from model output, so exfiltration needs no tool call and no tool-level egress control is on the path |
| 18 | GAP-054 | 9.0 | 5 | tool-action | missing-primitive | No single chokepoint turns a model-authored URL into a request, so a URL allowlist must be re-applied per surface and one unguarded surface reopens exfiltration |
| 19 | GAP-055 | 9.0 | 5 | model-runtime | wrong-default | The model identifier in production is a floating alias, so a provider-side weight change is an unreviewed deploy the app cannot pin or roll back |
| 20 | GAP-056 | 9.0 | 5 | tool-action | missing-primitive | No restore point is taken before an agent's irreversible command, so detecting the mistake does not let you undo it |
| 21 | GAP-057 | 9.0 | 5 | sandbox-isolation | wrong-default | An agent's execution boundary is a single opt-out flag, and nothing requires an isolation boundary once it is set |
| 22 | GAP-058 | 9.0 | 5 | sandbox-isolation | wrong-default | An agent's exec tool inherits the operator's whole ambient credential set, so its authority is never scoped to the task |
| 23 | GAP-059 | 9.0 | 5 | multi-agent | scaling-cliff | Concurrent agents fan out onto one shared provider quota with no admission control |
| 24 | GAP-006 | 8.7 | 5 | orchestration | wrong-default | A missing machine-parsed verdict defaults to the destructive answer |
| 25 | GAP-012 | 8.7 | 5 | sandbox-isolation | missing-contract | Tool authority is not reduced after an agent ingests untrusted content, so reading and exfiltrating stay in one privilege domain |
| 26 | GAP-014 | 8.7 | 5 | lifecycle-deploy | missing-contract | A machine-generated artifact that drives inference is trusted because it is first-party, so nothing validates its shape at ingestion |
| 27 | GAP-019 | 8.7 | 5 | eval-verification | measurement-gap | An eval bank executes each task once, so a flaky agent and a dependable one earn the same score and the gap only appears in production |
| 28 | GAP-020 | 8.7 | 5 | eval-verification | measurement-gap | A benchmark result row carries no environment fingerprint, so a score cannot be reproduced or compared with the one it is plotted against |
| 29 | GAP-021 | 8.7 | 5 | eval-verification | unverifiable | Task success is decided from the text the agent produced, with no assertion against the end state of the environment |
| 30 | GAP-022 | 8.7 | 5 | eval-verification | measurement-gap | An eval harness scores one attempt per task, so the number says a success exists, not that the task completes reliably |
| 31 | GAP-023 | 8.7 | 5 | eval-verification | unverifiable | Task success is graded from the agent's response and tool calls, so a wrong, missing or extra side effect scores as a pass |
| 32 | GAP-024 | 8.7 | 5 | eval-verification | measurement-gap | An eval records the agent's outcome but not the oversight the task consumed, so no score converts into a real-work claim |
| 33 | GAP-025 | 8.7 | 5 | eval-verification | measurement-gap | Agent evals record task outcome with no cost or step budget, so a benchmark score has no denominator and cannot be projected onto a real task |
| 34 | GAP-026 | 8.7 | 5 | eval-verification | unverifiable | Nothing audits whether a task's reward can be satisfied without the task being achieved |
| 35 | GAP-027 | 8.7 | 5 | eval-verification | measurement-gap | Eval task records carry no realism attribute, so a suite pass rate cannot be conditioned on how unlike real work its tasks are |
| 36 | GAP-028 | 8.7 | 5 | context-memory | missing-primitive | Standing instructions are stated once at run start and never re-asserted, so adherence decays as the transcript grows |
| 37 | GAP-029 | 8.7 | 5 | context-memory | missing-primitive | A memory write has no validity window, so retrieval returns a fact that stopped being true |
| 38 | GAP-030 | 8.7 | 5 | context-memory | silent-failure | Context compaction rewrites the run with no invariant that load-bearing constraints survived it |
| 39 | GAP-031 | 8.7 | 5 | cost-governance | missing-primitive | The only consumption bound an SDK offers on a model call limits output, so the input side, where an agent runaway actually spends, has no ceiling |
| 40 | GAP-060 | 8.7 | 5 | observability | wrong-default | Agent tracing records the raw prompt, tool arguments and tool output, and redaction is an opt-in hook |
| 41 | GAP-061 | 8.7 | 5 | context-memory | missing-contract | Agent conversation state is isolated only by a caller-supplied key, so a process-global store merges two users with nothing failing |
| 42 | GAP-062 | 8.7 | 5 | lifecycle-deploy | missing-primitive | Prompt text ships as an unversioned literal, so a bad prompt cannot be attributed or rolled back on its own |
| 43 | GAP-063 | 8.7 | 5 | eval-verification | wrong-default | One greedy sample is treated as a reproducible answer, so exact-match evals assert on a property no layer of the stack guarantees |
| 44 | GAP-064 | 8.7 | 5 | human-interface | measurement-gap | The human approve-or-deny decision is never recorded, so approval rate and override rate cannot be measured and a rubber stamp is indistinguishable from a reviewer |
| 45 | GAP-065 | 8.7 | 5 | orchestration | wrong-default | The injection screen sits on the operator's prompt while tool results re-enter the context unscreened on every later turn |
| 46 | GAP-066 | 8.7 | 5 | sandbox-isolation | missing-primitive | An installed agent CLI is ambient authority: nothing attests who invoked it, so unattended runs are granted every tool on the machine |
| 47 | GAP-067 | 8.7 | 5 | eval-verification | measurement-gap | Quality evaluations only ever run pre-deployment, so a routing or runtime change that manifests only in production has no detector |
| 48 | GAP-068 | 8.7 | 5 | eval-verification | measurement-gap | Quality evaluation runs only against fixed offline sets, so a serving-path regression is invisible until users complain |
| 49 | GAP-069 | 8.7 | 5 | sandbox-isolation | missing-primitive | An agent invoked from CI inherits the job's ambient token scope, because nothing mints a credential sized to the declared task |
| 50 | GAP-001 | 8.3 | 5 | observability | measurement-gap | Output-only feedback cannot localise an agent's failure |
| 51 | GAP-013 | 8.3 | 5 | context-memory | missing-contract | Retrieved and tool-returned content enters the model context with no provenance label a runtime can enforce |
| 52 | GAP-032 | 8.3 | 5 | eval-verification | missing-primitive | An eval bank reports a pass rate with no measured floor, so credit the grader awards for nothing is read as agent capability |
| 53 | GAP-033 | 8.3 | 5 | eval-verification | measurement-gap | The forecast an agent rollout was approved on is never recorded beside the measured effect, so systematic overestimation cannot be detected |
| 54 | GAP-034 | 8.3 | 5 | eval-verification | measurement-gap | An agent eval harness has no null-agent control, so a task passable without doing the work scores as a pass |
| 55 | GAP-035 | 8.3 | 5 | context-memory | missing-contract | Truncation treats the message history as a flat list, but a tool call and its result are one indivisible unit |
| 56 | GAP-036 | 8.3 | 5 | context-memory | measurement-gap | The guard that decides when context is reduced counts messages, while the window and the degradation it is meant to prevent are both denominated in tokens |
| 57 | GAP-037 | 8.3 | 5 | context-memory | missing-contract | Compaction rewrites the context with no preservation invariant, so load-bearing instructions are summarised away silently |
| 58 | GAP-038 | 8.3 | 5 | cost-governance | missing-primitive | A spending agent is supervised by a keep-alive policy and exposes no durable stop control, so ending a runaway means defeating the supervisor |
| 59 | GAP-039 | 8.3 | 5 | cost-governance | silent-failure | An agent's cost model assumes prompt caching that nothing verifies, so a silent cache miss bills the whole repeated context at full input price and the first signal is the invoice |
| 60 | GAP-070 | 8.3 | 5 | tool-action | wrong-default | The tenant scope of a tool call arrives as a model-filled parameter, so isolation is decided in the prompt instead of from the authenticated session |
| 61 | GAP-071 | 8.3 | 5 | context-memory | missing-primitive | Tenant scope for agent retrieval is an optional query argument, so an omitted filter silently widens the context |
| 62 | GAP-072 | 8.3 | 5 | context-memory | wrong-default | Tenant scope in a shared retrieval or cache store is a caller-supplied argument, and a read that omits it succeeds across every tenant |
| 63 | GAP-073 | 8.3 | 5 | observability | wrong-default | Agent telemetry captures prompt and tool-call content by default, and redaction is an opt-in nothing requires |
| 64 | GAP-074 | 8.3 | 5 | lifecycle-deploy | unverifiable | Prompt versioning pins the template, not the instruction text that ran, so a bad prompt cannot be attributed or reproduced |
| 65 | GAP-075 | 8.3 | 5 | model-runtime | silent-failure | The model version that actually served a response is never recorded, so a provider-side behaviour change cannot be attributed or pinned |
| 66 | GAP-076 | 8.3 | 5 | multi-agent | wrong-default | An agent's rollback is a whole-tree reset, so it deletes a concurrent agent's uncommitted work with no ownership check |
| 67 | GAP-077 | 8.3 | 5 | tool-action | missing-contract | A destructive cleanup step is not gated on verified completion of the step that was supposed to preserve the data |
| 68 | GAP-078 | 8.3 | 5 | model-runtime | missing-contract | A cached model response is not bound to the principal it was generated for, so a shared-layer mix-up delivers it to someone else |
| 69 | GAP-079 | 8.3 | 5 | eval-verification | measurement-gap | A deployed RAG system scores only the final answer, so a retrieval regression is indistinguishable from a generation regression |
| 70 | GAP-080 | 8.3 | 5 | orchestration | wrong-default | Agent retry policy has no jitter and no retry budget, so one rate limit becomes a retry storm |
| 71 | GAP-007 | 8.0 | 5 | multi-agent | missing-contract | Concurrent agents share a working tree and a git index with no coordination protocol |
| 72 | GAP-040 | 8.0 | 5 | eval-verification | measurement-gap | An eval bank records no per-task size label, so one aggregate pass rate cannot be projected onto the longer tasks real users bring |
| 73 | GAP-081 | 8.0 | 5 | eval-verification | unverifiable | Eval tasks carry no publication date, so no score can be split into the part a model could have memorised and the part it solved |
| 74 | GAP-082 | 8.0 | 5 | eval-verification | missing-primitive | An eval bank scores every task it holds with no per-task validity attestation, so a defective task is billed to the agent |
| 75 | GAP-083 | 8.0 | 5 | eval-verification | unverifiable | An eval run has open network access and keeps no egress record, so a solved task and a retrieved answer produce the same score |
| 76 | GAP-084 | 8.0 | 5 | eval-verification | missing-primitive | An eval harness has no outcome class for its own environment failing, so a tool outage is scored as agent incapability |
| 77 | GAP-085 | 8.0 | 5 | eval-verification | measurement-gap | A benchmark harness cannot tell its own infrastructure failure from an agent capability failure, so both land in one denominator |
| 78 | GAP-086 | 8.0 | 5 | eval-verification | missing-primitive | Per-task success is never audited against the task's declared difficulty, so shortcut tasks and impossible tasks stay invisible inside the aggregate |
| 79 | GAP-087 | 8.0 | 5 | context-memory | missing-contract | Compaction ships no acceptance test, so the summary that replaces the transcript is never checked for the items the run cannot proceed without |
| 80 | GAP-088 | 8.0 | 5 | context-memory | measurement-gap | Compaction is recursive over a long run and nothing counts the generations, so a context that is a summary of a summary is indistinguishable from a first-generation one |
| 81 | GAP-089 | 8.0 | 5 | context-memory | missing-contract | Context compaction is a lossy rewrite with no protected set, so a standing instruction can be summarised away |
| 82 | GAP-090 | 8.0 | 5 | context-memory | missing-primitive | Agent memory is written as an append-only claim with no validity window, so retrieval returns facts the world has already replaced |
| 83 | GAP-091 | 8.0 | 5 | context-memory | missing-contract | Compaction has no preserved-invariant contract, so a load-bearing instruction can be summarised away silently |
| 84 | GAP-092 | 8.0 | 5 | context-memory | missing-contract | History compaction has no invariant contract, so a load-bearing instruction can be summarised away mid-run |
| 85 | GAP-093 | 8.0 | 5 | context-memory | missing-primitive | A memory store records what was true, not until when, so retrieval confidently returns a superseded fact |
| 86 | GAP-094 | 8.0 | 5 | context-memory | missing-contract | Compaction discards context irreversibly, leaving no restorable handle to what it dropped |
| 87 | GAP-095 | 8.0 | 5 | context-memory | missing-contract | Context compaction has no preserved-invariant contract, so a summary can silently drop the standing instructions |
| 88 | GAP-096 | 8.0 | 5 | context-memory | missing-contract | Context compaction is irreversible by default, so a span the summariser drops leaves no handle the agent can read back |
| 89 | GAP-097 | 8.0 | 5 | context-memory | wrong-default | A stored memory carries no validity interval and never expiring is the default, so a superseded fact keeps being recalled as current |
| 90 | GAP-098 | 8.0 | 5 | cost-governance | scaling-cliff | A spend bound is scoped to one run while the driver relaunches the run forever, so nothing carries consumption across run boundaries |
| 91 | GAP-099 | 8.0 | 5 | cost-governance | silent-failure | Running out of the step budget is reported as a normal completion, so a run that was cut off is indistinguishable from one that finished |
| 92 | GAP-100 | 8.0 | 5 | cost-governance | missing-primitive | The only brake on a runaway agent counts steps, not progress, so a loop repeating one identical action spends its entire allowance and every step looks valid |
| 93 | GAP-101 | 8.0 | 5 | cost-governance | silent-failure | A streamed model call returns no token usage unless the caller opts in, so the cost meter of a streaming agent silently reads zero |
| 94 | GAP-102 | 8.0 | 5 | cost-governance | silent-failure | A model-calling retry loop has no no-progress brake, so a stuck agent keeps paying for identical calls without ever failing |
| 95 | GAP-103 | 8.0 | 5 | multi-agent | missing-contract | A parent agent fans out to subagents without dividing a budget, so the ceiling multiplies by the fan-out |
| 96 | GAP-104 | 8.0 | 5 | cost-governance | unverifiable | An agent governs its spend by the provider's own usage meter, with no independent local ledger to reconcile it against |
| 97 | GAP-105 | 8.0 | 5 | observability | missing-contract | Prompt redaction is configured per telemetry sink, so the ordinary logging path emits the same payload unredacted |
| 98 | GAP-106 | 8.0 | 5 | eval-verification | missing-contract | Production traces are promoted into an evaluation dataset with no redaction boundary at the copy, so customer data becomes a versioned test fixture that survives its own deletion |
| 99 | GAP-107 | 8.0 | 5 | lifecycle-deploy | missing-primitive | A prompt or agent-config change deploys as an all-or-nothing label flip, so there is no fraction of traffic to canary it on and the first users to meet a bad version are all of them |
| 100 | GAP-108 | 8.0 | 5 | lifecycle-deploy | missing-primitive | Rolling back a prompt or agent version does not roll back the durable state that version wrote, so the rollback restores the code path and not the behaviour |
| 101 | GAP-109 | 8.0 | 5 | lifecycle-deploy | missing-primitive | Prompt version and model version are separately deployable, so nothing names the combination that was tested |
| 102 | GAP-110 | 8.0 | 5 | model-runtime | unverifiable | A seeded request is treated as reproducible while the serving build that decides the result is never recorded |
| 103 | GAP-111 | 8.0 | 5 | observability | missing-primitive | Telemetry redaction is a global switch, so the interaction a user complained about is not retained anywhere an engineer may read or replay it |
| 104 | GAP-112 | 8.0 | 5 | observability | unverifiable | A structured-output retry loop discards the generation that failed, so the malformed output an incident is about never becomes an artifact |
| 105 | GAP-113 | 8.0 | 5 | orchestration | silent-failure | The prompt is assembled from an unordered source, so two runs of one task are not the same request and nothing records the order that ran |
| 106 | GAP-114 | 8.0 | 5 | orchestration | missing-primitive | Prompt assembly reads the ambient clock and RNG directly, so a captured model configuration still cannot reproduce the request |
| 107 | GAP-115 | 8.0 | 5 | human-interface | measurement-gap | An approval gate records the verdict and nothing about the decision, so rubber-stamping and real review produce identical telemetry |
| 108 | GAP-116 | 8.0 | 5 | human-interface | missing-contract | A parked human decision waits indefinitely with no deadline or escalation, so a review queue nobody reads is indistinguishable from an empty one |
| 109 | GAP-117 | 8.0 | 5 | human-interface | measurement-gap | A human review queue carries no age, no backlog bound, and no default action, so unread items are indistinguishable from approved ones |
| 110 | GAP-118 | 8.0 | 5 | human-interface | missing-contract | The human approval prompt renders a tool label, not the arguments, so the only enforcement point in the loop cannot see the payload it authorizes |
| 111 | GAP-119 | 8.0 | 5 | multi-agent | missing-primitive | Delegation is bounded only by prompt instructions, so no runtime component can refuse a spawn |
| 112 | GAP-120 | 8.0 | 5 | eval-verification | missing-contract | An eval suite exists but no release path can fail on it, so a behavioural regression has no veto |
| 113 | GAP-002 | 7.3 | 5 | eval-verification | measurement-gap | Static graders cannot separate a policy loophole from a genuinely better answer |
| 114 | GAP-004 | 7.3 | 5 | context-memory | unverifiable | Steering context is assumed delivered, and nothing verifies that it was |
| 115 | GAP-009 | 7.3 | 5 | lifecycle-deploy | silent-failure | Shipped is not live: a long-running agent keeps executing the code it imported at launch |
| 116 | GAP-011 | 7.3 | 5 | tool-action | missing-contract | MCP tool descriptions are authoritative prompt text with no integrity pin, so a change after approval needs no re-approval |
| 117 | GAP-015 | 7.3 | 5 | model-runtime | missing-contract | An app routes one model to several serving backends with no output-equivalence contract between them |
| 118 | GAP-008 | 7.3 | 4 | eval-verification | ergonomics | Evaluation investment has visible upfront cost and deferred benefit, so it is chronically under-provisioned |
| 119 | GAP-005 | 6.7 | 5 | context-memory | scaling-cliff | Agent memory has no retention policy, so self-correction quietly narrows to one iteration |

## By layer

Every layer in the closed taxonomy is listed on purpose: a zero means the layer is unexamined, not that it is clean -- it is not a target to fill.

| Layer | Records |
| --- | --- |
| model-runtime | 5 |
| orchestration | 6 |
| context-memory | 28 |
| tool-action | 8 |
| sandbox-isolation | 5 |
| eval-verification | 28 |
| observability | 8 |
| cost-governance | 12 |
| lifecycle-deploy | 8 |
| multi-agent | 5 |
| human-interface | 7 |

## Evidence age

Ages are measured against 2026-08-28, the newest citation date in this register, so the same register always renders the same bytes; no clock is read.

An old citation is not a closed gap: evidence for a durable property does not weaken with age. This says where to go and CHECK, not what to delete and not what to pad with a fresher link.

| ID | Newest citation | Age (days) | Title |
| --- | --- | --- | --- |
| GAP-078 | 2023-03-24 | 1253 | A cached model response is not bound to the principal it was generated for, so a shared-layer mix-up delivers it to someone else |
| GAP-118 | 2025-05-26 | 459 | The human approval prompt renders a tool label, not the arguments, so the only enforcement point in the loop cannot see the payload it authorizes |
| GAP-081 | 2025-06-14 | 440 | Eval tasks carry no publication date, so no score can be split into the part a model could have memorised and the part it solved |
| GAP-011 | 2025-06-18 | 436 | MCP tool descriptions are authoritative prompt text with no integrity pin, so a change after approval needs no re-approval |
| GAP-051 | 2025-06-18 | 436 | A human approval surface renders a summary, so the person approves something other than the bytes the tool receives |
| GAP-021 | 2025-07-03 | 421 | Task success is decided from the text the agent produced, with no assertion against the end state of the environment |
| GAP-040 | 2025-07-03 | 421 | An eval bank records no per-task size label, so one aggregate pass rate cannot be projected onto the longer tasks real users bring |
| GAP-082 | 2025-07-03 | 421 | An eval bank scores every task it holds with no per-task validity attestation, so a defective task is billed to the agent |
| GAP-025 | 2025-07-12 | 412 | Agent evals record task outcome with no cost or step budget, so a benchmark score has no denominator and cannot be projected onto a real task |
| GAP-016 | 2025-07-23 | 401 | An agent's action policy lives in prompt prose, so nothing can refuse a destructive tool call |
| GAP-033 | 2025-07-25 | 399 | The forecast an agent rollout was approved on is never recorded beside the measured effect, so systematic overestimation cannot be detected |
| GAP-020 | 2025-08-07 | 386 | A benchmark result row carries no environment fingerprint, so a score cannot be reproduced or compared with the one it is plotted against |
| GAP-034 | 2025-08-07 | 386 | An agent eval harness has no null-agent control, so a task passable without doing the work scores as a pass |
| GAP-084 | 2025-08-07 | 386 | An eval harness has no outcome class for its own environment failing, so a tool outage is scored as agent incapability |
| GAP-086 | 2025-08-07 | 386 | Per-task success is never audited against the task's declared difficulty, so shortcut tasks and impossible tasks stay invisible inside the aggregate |
| GAP-058 | 2025-08-27 | 366 | An agent's exec tool inherits the operator's whole ambient credential set, so its authority is never scoped to the task |

## Source concentration

Sources cited by more than one record: 61 of 167 | records resting on a shared source: 102 of 120

A shared source is not a fault -- a young field has few primary sources -- and nothing here derives a penalty: no count in this section reaches priority, confidence, the ranking or the floor, and none of them is a number to drive down. The actionable case is a record resting on ONE source, whose entire evidentiary basis a single retraction voids.

| Source | Records | IDs |
| --- | --- | --- |
| https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues | 13 | GAP-014, GAP-015, GAP-041, GAP-050, GAP-063, GAP-067, GAP-068, GAP-075, GAP-108, GAP-111, GAP-112, GAP-114, GAP-120 |
| https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | 13 | GAP-028, GAP-030, GAP-036, GAP-037, GAP-074, GAP-087, GAP-088, GAP-089, GAP-091, GAP-094, GAP-095, GAP-096, GAP-097 |
| https://arxiv.org/abs/2507.02825 | 12 | GAP-021, GAP-025, GAP-026, GAP-027, GAP-032, GAP-034, GAP-040, GAP-082, GAP-083, GAP-084, GAP-085, GAP-086 |
| https://genai.owasp.org/llmrisk/llm022025-sensitive-information-disclosure | 9 | GAP-046, GAP-047, GAP-048, GAP-049, GAP-060, GAP-061, GAP-071, GAP-072, GAP-105 |
| https://openai.com/index/march-20-chatgpt-outage | 8 | GAP-045, GAP-046, GAP-048, GAP-049, GAP-061, GAP-071, GAP-072, GAP-078 |
| https://research.trychroma.com/context-rot | 8 | GAP-018, GAP-028, GAP-030, GAP-036, GAP-089, GAP-091, GAP-092, GAP-093 |
| https://openai.com/index/expanding-on-sycophancy | 7 | GAP-055, GAP-062, GAP-074, GAP-075, GAP-107, GAP-109, GAP-120 |
| https://arxiv.org/abs/2507.09089 | 6 | GAP-020, GAP-024, GAP-025, GAP-026, GAP-033, GAP-084 |
| https://arxiv.org/abs/2407.01502 | 5 | GAP-017, GAP-019, GAP-025, GAP-034, GAP-083 |
| https://arxiv.org/abs/2410.10813 | 4 | GAP-029, GAP-090, GAP-093, GAP-097 |
| https://arxiv.org/abs/2503.14499 | 4 | GAP-019, GAP-027, GAP-033, GAP-040 |
| https://arxiv.org/abs/2505.06120 | 4 | GAP-030, GAP-037, GAP-087, GAP-089 |
| https://qdrant.tech/documentation/guides/multiple-partitions | 4 | GAP-045, GAP-049, GAP-071, GAP-072 |
| https://simonwillison.net/2025/jun/16/the-lethal-trifecta | 4 | GAP-011, GAP-012, GAP-013, GAP-065 |
| https://www.wiz.io/blog/wiz-research-uncovers-exposed-deepseek-database-leak | 4 | GAP-060, GAP-073, GAP-105, GAP-106 |
| https://arxiv.org/html/2507.02825v5 | 3 | GAP-020, GAP-084, GAP-086 |
| https://docs.langchain.com/oss/python/langgraph/persistence | 3 | GAP-046, GAP-061, GAP-108 |
| https://github.com/nrwl/nx/security/advisories/ghsa-cxm3-wv7p-598c | 3 | GAP-057, GAP-058, GAP-066 |
| https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks | 3 | GAP-011, GAP-051, GAP-118 |
| https://langfuse.com/docs/observability/features/masking | 3 | GAP-060, GAP-073, GAP-105 |
| https://langfuse.com/docs/prompt-management/features/prompt-version-control | 3 | GAP-062, GAP-107, GAP-109 |
| https://langfuse.com/docs/prompt-management/overview | 3 | GAP-062, GAP-074, GAP-109 |
| https://link.springer.com/article/10.1007/s10462-026-11571-0 | 3 | GAP-022, GAP-023, GAP-085 |
| https://nx.dev/blog/s1ngularity-postmortem | 3 | GAP-057, GAP-066, GAP-069 |
| https://openai.com/index/introducing-swe-bench-verified | 3 | GAP-081, GAP-082, GAP-085 |
| https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference | 3 | GAP-050, GAP-063, GAP-110 |
| https://arxiv.org/abs/2406.12045 | 2 | GAP-019, GAP-021 |
| https://arxiv.org/abs/2504.01382 | 2 | GAP-026, GAP-040 |
| https://arxiv.org/abs/2510.11977 | 2 | GAP-017, GAP-083 |
| https://arxiv.org/abs/2606.05405 | 2 | GAP-022, GAP-024 |
| https://arxiv.org/abs/2608.19741 | 2 | GAP-022, GAP-023 |
| https://arxiv.org/html/2503.14499v4 | 2 | GAP-027, GAP-086 |
| https://arxiv.org/html/2509.10540v1 | 2 | GAP-052, GAP-053 |
| https://arxiv.org/html/2606.05391v1 | 2 | GAP-115, GAP-116 |
| https://cognition.ai/blog/dont-build-multi-agents | 2 | GAP-076, GAP-096 |
| https://cookbook.openai.com/examples/reproducible_outputs_with_the_seed_parameter | 2 | GAP-110, GAP-113 |
| https://docs.claude.com/en/docs/claude-code/memory | 2 | GAP-092, GAP-093 |
| https://docs.langchain.com/oss/python/langchain/short-term-memory | 2 | GAP-088, GAP-092 |
| https://docs.vllm.ai/en/latest/usage/reproducibility.html | 2 | GAP-063, GAP-110 |
| https://github.blog/ai-and-ml/github-copilot/improving-token-efficiency-in-github-agentic-workflows | 2 | GAP-042, GAP-043 |
| https://github.com/anthropics/claude-code/issues/35166 | 2 | GAP-044, GAP-102 |
| https://github.com/anthropics/claude-code/issues/69578 | 2 | GAP-042, GAP-043 |
| https://github.com/jeffma8888/agent-failure-modes/blob/main/incidents/inc-0004-a-monotonically-growing-required-reading-file-silently-kills.md | 2 | GAP-004, GAP-005 |
| https://github.com/jeffma8888/agent-failure-modes/blob/main/incidents/inc-0020-a-steering-channel-counts-only-when-the-consumer-s-own-parse.md | 2 | GAP-004, GAP-005 |
| https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1913 | 2 | GAP-012, GAP-013 |
| https://github.com/nerudek/hermes-token-loop-postmortem | 2 | GAP-038, GAP-103 |
| https://github.com/run-llama/llama_index/issues/16499 | 2 | GAP-099, GAP-100 |
| https://invariantlabs.ai/blog/mcp-github-vulnerability | 2 | GAP-012, GAP-118 |
| https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/model-versions | 2 | GAP-055, GAP-109 |
| https://manus.im/blog/context-engineering-for-ai-agents-lessons-from-building-manus | 2 | GAP-094, GAP-096 |
| https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices | 2 | GAP-011, GAP-070 |
| https://openai.com/index/sycophancy-in-gpt-4o | 2 | GAP-055, GAP-068 |
| https://openai.github.io/openai-agents-python/human_in_the_loop | 2 | GAP-115, GAP-116 |
| https://raw.githubusercontent.com/jeffma8888/agent-failure-modes/main/incidents/inc-0011-concurrent-agent-brains-silently-starve-and-kill-each-other.md | 2 | GAP-059, GAP-080 |
| https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/langchain/langchain_classic/agents/agent.py | 2 | GAP-099, GAP-100 |
| https://raw.githubusercontent.com/nerudek/hermes-token-loop-postmortem/main/readme.md | 2 | GAP-031, GAP-038 |
| https://security.googleblog.com/2025/06/mitigating-prompt-injection-attacks.html | 2 | GAP-012, GAP-013 |
| https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | 2 | GAP-002, GAP-008 |
| https://www.anthropic.com/engineering/multi-agent-research-system | 2 | GAP-103, GAP-119 |
| https://www.anthropic.com/news/claude-for-chrome | 2 | GAP-012, GAP-065 |
| https://www.bleepingcomputer.com/news/security/asana-warns-mcp-ai-feature-exposed-customer-data-to-other-orgs | 2 | GAP-045, GAP-070 |

Records resting on exactly one distinct source (a single retraction voids the whole evidentiary basis of each): GAP-006, GAP-008, GAP-009, GAP-010, GAP-015, GAP-059, GAP-067, GAP-069, GAP-078

## Tag coverage

Distinct tag values: 275 | listed below (2 or more records): 100 | of those, spanning more than one layer: 55 | occurring on exactly one record and omitted: 175

Tags are free labels and not a closed vocabulary, and nothing here derives a penalty: no count in this section reaches priority, confidence, the ranking or the floor. A tag carried by exactly one record is omitted from the table -- one record sits in one layer, so such a tag can carry no cross-layer information -- and its count is published in the census above rather than dropped. Two spellings of one theme render as two rows: that is a curation task this section makes visible, never a rewrite it performs.

| Tag | Records | Layers |
| --- | --- | --- |
| evals | 16 | eval-verification |
| long-horizon | 13 | context-memory |
| compaction | 10 | context-memory |
| cost | 10 | cost-governance, eval-verification, multi-agent |
| retrieval | 10 | context-memory, eval-verification |
| memory | 9 | context-memory, lifecycle-deploy |
| reproducibility | 9 | eval-verification, lifecycle-deploy, model-runtime, observability, orchestration |
| multi-tenant | 8 | context-memory, model-runtime, tool-action |
| isolation | 7 | context-memory, model-runtime |
| benchmark-gap | 6 | eval-verification |
| blast-radius | 6 | multi-agent, sandbox-isolation, tool-action |
| context-window | 6 | context-memory |
| rollback | 6 | lifecycle-deploy, model-runtime, multi-agent |
| benchmark | 5 | eval-verification |
| budget | 5 | cost-governance, multi-agent |
| context-bleed | 5 | context-memory |
| exfiltration | 5 | human-interface, sandbox-isolation, tool-action |
| measurement | 5 | eval-verification, human-interface |
| provenance | 5 | context-memory, eval-verification, model-runtime |
| staleness | 5 | context-memory, lifecycle-deploy |
| unattended | 5 | cost-governance, sandbox-isolation |
| attribution | 4 | eval-verification, lifecycle-deploy, model-runtime |
| benchmarks | 4 | eval-verification |
| canary | 4 | eval-verification, lifecycle-deploy, model-runtime |
| context | 4 | context-memory, lifecycle-deploy, observability |
| data-leak | 4 | context-memory, tool-action |
| egress | 4 | eval-verification, human-interface, tool-action |
| eval | 4 | eval-verification |
| observability | 4 | cost-governance, observability |
| rag | 4 | context-memory, eval-verification |
| runaway | 4 | cost-governance |
| secrets | 4 | observability, tool-action |
| silent-failure | 4 | context-memory, cost-governance |
| tokens | 4 | context-memory, cost-governance, eval-verification |
| approval | 3 | human-interface |
| benchmark-validity | 3 | eval-verification |
| cost-governance | 3 | cost-governance |
| credentials | 3 | sandbox-isolation, tool-action |
| cross-tenant | 3 | context-memory, tool-action |
| delegation | 3 | cost-governance, multi-agent |
| determinism | 3 | model-runtime, orchestration |
| fan-out | 3 | cost-governance, multi-agent |
| harness | 3 | eval-verification, orchestration |
| injection | 3 | human-interface, tool-action |
| instruction-drift | 3 | context-memory |
| irreversible | 3 | context-memory, tool-action |
| loop | 3 | cost-governance |
| mcp | 3 | human-interface, tool-action |
| pii | 3 | eval-verification, observability |
| postmortem | 3 | eval-verification, model-runtime |
| postmortem-2025 | 3 | lifecycle-deploy, model-runtime, tool-action |
| privacy | 3 | context-memory, observability |
| prompt-assembly | 3 | orchestration, tool-action |
| prompt-injection | 3 | context-memory, orchestration, sandbox-isolation |
| redaction | 3 | observability |
| reliability | 3 | eval-verification |
| replay | 3 | observability, orchestration |
| retry | 3 | cost-governance, observability, orchestration |
| reward-design | 3 | eval-verification |
| supply-chain | 3 | sandbox-isolation, tool-action |
| telemetry | 3 | context-memory, human-interface, observability |
| adoption | 2 | eval-verification |
| ambient-authority | 2 | sandbox-isolation |
| authorization | 2 | context-memory, tool-action |
| concurrency | 2 | multi-agent |
| contamination | 2 | eval-verification |
| context-engineering | 2 | context-memory |
| context-memory | 2 | context-memory |
| drift | 2 | eval-verification, model-runtime |
| grader | 2 | eval-verification |
| hitl | 2 | human-interface |
| human-in-the-loop | 2 | human-interface |
| human-oversight | 2 | human-interface |
| indirect-injection | 2 | orchestration, tool-action |
| invariant | 2 | context-memory, cost-governance |
| least-privilege | 2 | sandbox-isolation |
| measurement-gap | 2 | human-interface |
| metering | 2 | cost-governance |
| multi-agent | 2 | cost-governance, multi-agent |
| ordering | 2 | orchestration, tool-action |
| outcome-validity | 2 | eval-verification |
| pass-hat-k | 2 | eval-verification |
| production | 2 | eval-verification |
| prompt | 2 | lifecycle-deploy |
| quota | 2 | cost-governance |
| rate-limit | 2 | multi-agent, orchestration |
| regression | 2 | eval-verification |
| retention | 2 | context-memory, eval-verification |
| review-queue | 2 | human-interface |
| runaway-loop | 2 | cost-governance |
| sandbox | 2 | sandbox-isolation |
| serving | 2 | eval-verification, model-runtime |
| state | 2 | eval-verification, lifecycle-deploy |
| supersession | 2 | context-memory |
| task-validity | 2 | eval-verification |
| traces | 2 | eval-verification, observability |
| trust-calibration | 2 | human-interface |
| variance | 2 | eval-verification |
| versioning | 2 | lifecycle-deploy |
| wrong-default | 2 | cost-governance, observability |

## Below confidence floor

Kept visible on purpose: a weakly-sourced gap is a research task, not a deletion.

| ID | Priority | Confidence | Title | Strongest source | Needs |
| --- | --- | --- | --- | --- | --- |
| GAP-010 | 5.3 | 1 | Pilot-to-production conversion for enterprise agents is reported as very low, but the measurement is unaudited | secondary-summary | weight >= 3: practitioner-report, survey-aggregate |
