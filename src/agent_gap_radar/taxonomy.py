"""Fixed vocabularies for the gap register.

These are deliberately closed enumerations. A gap record that does not fit an
existing layer is a signal to debate the taxonomy in a PR, not to invent a
free-text label -- free text is what turns a register into a junk drawer.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Where in the agent stack a gap lives.
# ---------------------------------------------------------------------------
LAYERS: dict[str, str] = {
    "model-runtime": "Inference/serving: latency, caps, determinism, token budgets.",
    "orchestration": "Loop control: stage sequencing, retries, verdicts, resume.",
    "context-memory": "What the agent knows: steering, digests, retention, retrieval.",
    "tool-action": "Tool/plugin contracts, action schemas, side-effect declaration.",
    "sandbox-isolation": "Execution boundaries, permissioning, blast-radius control.",
    "eval-verification": "Deciding whether the work is correct: graders, oracles, gates.",
    "observability": "Seeing inside a run: traces, intermediate state, attribution.",
    "cost-governance": "Spend attribution, budgets, quota contention, throttling.",
    "lifecycle-deploy": "Promotion, rollback, versioning of agents and their prompts.",
    "multi-agent": "Coordination: shared state, concurrency, handoff, role isolation.",
    "human-interface": "Escalation, review queues, approval gates, trust calibration.",
}

# ---------------------------------------------------------------------------
# What KIND of gap it is. A gap is not always "no tool exists".
# ---------------------------------------------------------------------------
GAP_TYPES: dict[str, str] = {
    "missing-primitive": "No component provides this at all.",
    "missing-contract": "Components exist but agree on no interface/protocol.",
    "silent-failure": "The failure mode exists and emits no signal.",
    "unverifiable": "A claim is made that nothing checks (delivery, coverage, success).",
    "wrong-default": "A safe behaviour is available but is not the default.",
    "scaling-cliff": "Works at small N, degrades non-obviously as N grows.",
    "measurement-gap": "The thing that matters is not measured; a proxy is measured.",
    "ergonomics": "Solvable today, but the cost keeps teams from doing it.",
}

# ---------------------------------------------------------------------------
# Evidence credibility ladder. Ordered: index 0 is strongest.
# This ordering is load-bearing -- confidence is DERIVED from it, so a record
# cannot inflate its own confidence with prose.
# ---------------------------------------------------------------------------
SOURCE_CLASSES: tuple[str, ...] = (
    "incident-postmortem",   # a specific failure that happened, with root cause
    "first-party-field",     # reproducible first-hand operation, with measurements
    "peer-reviewed",         # academic paper, accepted venue
    "maintainer-primary",    # issue/RFC/doc by the people who own the component
    "vendor-primary",        # vendor engineering post about their own system
    "practitioner-report",   # named practitioner writing up their own experience
    "survey-aggregate",      # survey/report over many respondents
    "secondary-summary",     # blog summarising someone else's primary source
    "model-output",          # produced by an LLM; NEVER sufficient on its own
)

SOURCE_WEIGHTS: dict[str, int] = {
    "incident-postmortem": 5,
    "first-party-field": 5,
    "peer-reviewed": 4,
    "maintainer-primary": 4,
    "vendor-primary": 4,
    "practitioner-report": 3,
    "survey-aggregate": 3,
    "secondary-summary": 1,
    "model-output": 0,
}

STATUSES: tuple[str, ...] = ("open", "partially-addressed", "addressed", "retired")

#: One line per status, keyed and ORDERED like `STATUSES` -- the rendered section is
#: derived from that tuple, so a key missing here would render a KeyError rather than a
#: quietly glossless bullet. `status` is the one closed vocabulary a machine consumer is
#: told in writing to select on, and until this iteration `radar taxonomy` published the
#: other three and omitted it, so reading the register's own documentation could not
#: recover `addressed` or `retired` -- exactly the two values that mean a gap has stopped
#: being actionable, which is what a release gate needs to know.
STATUS_GLOSSES: dict[str, str] = {
    "open": "Live and actionable: nothing published is known to handle it.",
    "partially-addressed": "A mitigation exists for part of it; the gap still bites.",
    "addressed": "A published fix covers it; kept for provenance, not for building.",
    "retired": "No longer a real gap, or superseded by another record.",
}


def layer_names() -> tuple[str, ...]:
    return tuple(LAYERS)


def gap_type_names() -> tuple[str, ...]:
    return tuple(GAP_TYPES)
