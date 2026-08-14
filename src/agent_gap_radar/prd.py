"""Bridge: turn the top-ranked gap into a build-loop PRD.

This is the point of the whole project. Research that does not change what gets
built is a reading list. The emitted document is the prd.json shape consumed by
Ralph-style loops (ordered stories, `passes` flags, verifiable criteria), so the
handoff from "we found the gap" to "a loop is building against it" is one command.
"""

from __future__ import annotations

import json

from .models import Gap
from .scoring import confidence, priority


def _slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:48]


def prd_for(gap: Gap, project: str = "agent-gap-radar") -> dict:
    """Build a prd.json-shaped dict for one gap.

    Story 1 is always a failing reproduction of the gap. A build loop that
    starts from a spec instead of a red test optimises the spec.
    """
    branch = f"ralph/{_slug(gap.title)}"
    criteria_tail = ["Full test suite passes", "No new runtime dependency"]

    stories = [
        {
            "id": "US-001",
            "title": f"Reproduce {gap.id} as a failing test",
            "description": (
                f"As a maintainer, I need an executable demonstration of {gap.id} "
                "so that any fix is measured against a real failure, not a description."),
            "acceptanceCriteria": [
                f"A test encodes the observed symptom: {gap.symptom}",
                "The test FAILS on the current code and the failure message names the gap",
                *criteria_tail,
            ],
            "priority": 1,
            "passes": False,
            "notes": f"Gap priority {priority(gap):.1f}, confidence {confidence(gap)}.",
        },
        {
            "id": "US-002",
            "title": f"Minimal mitigation for {gap.id}",
            "description": (
                "As an operator, I want the smallest change that turns the silent "
                "failure into a visible, actionable one."),
            "acceptanceCriteria": [
                "The US-001 test passes",
                "The mitigation is opt-in or dormant by default (no behaviour change on upgrade)",
                *criteria_tail,
            ],
            "priority": 2,
            "passes": False,
            "notes": gap.build_hypothesis,
        },
        {
            "id": "US-003",
            "title": f"Document {gap.id} and its mitigation",
            "description": (
                "As a reader, I want the gap, the evidence, and the mitigation in one "
                "place so the decision is reviewable later."),
            "acceptanceCriteria": [
                "README or docs page states the gap, the symptom, and the mitigation",
                "Every claim cites a locator from the gap record",
                *criteria_tail,
            ],
            "priority": 3,
            "passes": False,
            "notes": "",
        },
    ]

    return {
        "project": project,
        "branchName": branch,
        "description": f"{gap.id} -- {gap.title}. {gap.problem}",
        "sourceGap": {
            "id": gap.id,
            "layer": gap.layer,
            "gapType": gap.gap_type,
            "priority": priority(gap),
            "confidence": confidence(gap),
            "evidence": [
                {"sourceClass": e.source_class, "locator": e.locator, "date": e.date}
                for e in gap.evidence
            ],
        },
        "userStories": stories,
    }


def render_prd(gap: Gap, project: str = "agent-gap-radar") -> str:
    return json.dumps(prd_for(gap, project), indent=2, sort_keys=False) + "\n"
