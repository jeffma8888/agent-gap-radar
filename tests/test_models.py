"""Schema validation is the register's first quality gate, so test its refusals."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from agent_gap_radar.models import Evidence, Gap


def _ev(**over) -> dict:
    base = {
        "source_class": "first-party-field",
        "title": "t",
        "locator": "https://example.invalid/x",
        "date": "2026-01-02",
        "quote": "a verbatim excerpt",
    }
    base.update(over)
    return base


def _gap(**over) -> dict:
    base = {
        "id": "GAP-001",
        "title": "t",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [_ev()],
    }
    base.update(over)
    return base


def test_minimal_gap_validates():
    gap = Gap.model_validate(_gap())
    assert gap.id == "GAP-001"
    assert gap.status == "open"


@pytest.mark.parametrize("bad_id", ["GAP-1", "gap-001", "GAP-0001", "001", ""])
def test_malformed_id_rejected(bad_id):
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(id=bad_id))


def test_unknown_layer_rejected():
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(layer="not-a-layer"))


def test_unknown_gap_type_rejected():
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(gap_type="vibes"))


def test_unknown_status_rejected():
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(status="maybe"))


def test_gap_requires_at_least_one_evidence():
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(evidence=[]))


@pytest.mark.parametrize("score", [0, 6, -1])
def test_scores_bounded_1_to_5(score):
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(severity=score))


def test_extra_fields_forbidden():
    """A typo'd field name must fail loudly, not be silently ignored."""
    with pytest.raises(ValidationError):
        Gap.model_validate(_gap(sevirity=4))


def test_evidence_rejects_unknown_source_class():
    with pytest.raises(ValidationError):
        Evidence.model_validate(_ev(source_class="a-friend-told-me"))


@pytest.mark.parametrize("bad_date", ["2026-1-2", "01-02-2026", "2026", "not a date"])
def test_evidence_requires_iso_date(bad_date):
    with pytest.raises(ValidationError):
        Evidence.model_validate(_ev(date=bad_date))


@pytest.mark.parametrize("impossible", ["2026-02-30", "2026-04-31", "2026-13-01", "2026-00-10"])
def test_evidence_rejects_a_shape_legal_but_impossible_calendar_date(impossible):
    """The `YYYY-MM-DD` SHAPE is not the whole rule, because the stored value is
    arithmetic input.

    `2026-02-30` is a plausible research-pass typo that the shape check accepts, and every
    consumer that parses a stored date raises on it -- so before this refusal existed a
    register could be `OK` to `radar validate` and still crash `radar report`, which is
    the primary human surface. Refused at the ingest door instead, where the curator who
    can fix the record is the one who hears about it.

    ARMED against the shape check it sits behind: each sample is asserted to MATCH the
    `YYYY-MM-DD` pattern first, so a green result here is evidence about the calendar
    parse and not about a shape refusal that would have fired anyway.
    """
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", impossible), (
        f"premise broken: {impossible!r} is not shape-legal, so this sample cannot show "
        f"that the calendar parse is what refuses it")
    with pytest.raises(ValidationError):
        Evidence.model_validate(_ev(date=impossible))


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_evidence_rejects_empty_quote(blank):
    """A citation with no excerpt cannot be checked by a reader."""
    with pytest.raises(ValidationError):
        Evidence.model_validate(_ev(quote=blank))
