"""Two research agents describing ONE gap must land ONE record.

The `_signature` gate only catches a candidate that copies another check's
patterns verbatim. The failure that actually happened is different and larger: a
fan-out of parallel agents, asked overlapping questions, produced seven records
for one gap (unscoped multi-tenant retrieval), each with its own wording and its
own differently-spelled detector. Every one of them passed every gate.

So this file pins the BEHAVIOURAL test that catches that case -- two checks are
the same check when each fires on the other's bad fixture and stays silent on the
other's good fixture -- and, just as importantly, pins the two ways it must NOT
overreach:

  * a genuinely different detector still lands (or the gate is a bottleneck
    wearing a quality badge);
  * a BROADER detector does not absorb a narrower one, because generality is not
    sameness. Accepting one-way hits was measured to make one broad cost check
    swallow three distinct records.

Offline, like the rest of the suite: fixtures are written to a temp dir and the
checks run against them.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

import promote  # noqa: E402


def _doc(**overrides) -> dict:
    doc = {
        "id": "GAP-900",
        "title": "A placeholder title the gate will renumber",
        "layer": "orchestration",
        "gap_type": "missing-contract",
        "status": "open",
        "problem": "p",
        "symptom": "s",
        "why_now": "w",
        "severity": 3,
        "frequency": 3,
        "tractability": 3,
        "evidence": [
            {
                "source_class": "vendor-primary",
                "title": "A page that was actually fetched",
                "locator": "https://example.com/a",
                "date": "2026-01-01",
                "quote": "one two three four five six seven",
            }
        ],
        "build_hypothesis": "b",
        "check": _check(),
    }
    doc.update(overrides)
    return doc


def _check(pattern: str = r"time\.sleep\(\s*\d",
           mitigated: str = r"jitter|random\.uniform",
           bad: dict[str, str] | None = None,
           good: dict[str, str] | None = None) -> dict:
    return {
        "id": "CHK-900",
        "rationale": "r",
        "manual_question": "q",
        "present_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": pattern},
        "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": mitigated},
        "fixtures": {
            "bad": bad or {"a.py": "import time\ntime.sleep(5)\n"},
            "good": good or {"a.py": "import random, time\ntime.sleep(5 + random.uniform(0, 1))  # jitter\n"},
        },
    }


#: Same gap, two agents. The patterns are spelled differently (so the signature
#: gate sees two distinct checks) but each detector reproduces the other's
#: verdicts on the other's own fixtures.
TENANT_A = _check(
    pattern=r"retrieve\(|search\(",
    mitigated=r"tenant_id",
    bad={"svc.py": "rows = retrieve(query)\n"},
    good={"svc.py": "rows = retrieve(query, tenant_id=caller.tenant_id)\n"},
)
TENANT_B = _check(
    pattern=r"search\(|retrieve\(",
    mitigated=r"tenant_id|principal_id",
    bad={"db.py": "hits = search(q)\n"},
    good={"db.py": "hits = search(q, tenant_id=principal.tenant_id)\n"},
)

#: Same SYMPTOM, different FIX. Both detectors fire on the other's bad tree, and
#: both ALSO fire on the other's good tree, because each recognises only its own
#: mitigation. Firing on both trees means the detector did not discriminate, so
#: neither may be called a twin -- what counts as fixed is part of a gap's identity.
SCOPE_BY_TENANT = _check(
    pattern=r"retrieve\(",
    mitigated=r"tenant_id",
    bad={"x.py": "rows = retrieve(q)\n"},
    good={"x.py": "rows = retrieve(q, tenant_id=caller.tenant_id)\n"},
)
SCOPE_BY_PRINCIPAL = _check(
    pattern=r"retrieve\(",
    mitigated=r"principal",
    bad={"y.py": "rows = retrieve(q)\n"},
    good={"y.py": "rows = retrieve(q, principal=caller.principal)\n"},
)

#: One-way only: BROAD fires on NARROW's fixtures, NARROW does not fire on BROAD's.
BROAD = _check(
    pattern=r"spend|tokens|usage",
    mitigated=r"budget",
    bad={"m.py": "spend = compute_cost(resp)\n"},
    good={"m.py": "spend = compute_cost(resp)\nbudget.charge(spend)\n"},
)
NARROW = _check(
    pattern=r"usage",
    mitigated=r"budget",
    bad={"n.py": "usage = resp.usage\n"},
    good={"n.py": "usage = resp.usage\nbudget.charge(usage)\n"},
)


def _empty_register(tmp_path: Path) -> Path:
    gaps = tmp_path / "gaps"
    gaps.mkdir(parents=True, exist_ok=True)
    return gaps


def _run(tmp_path: Path, candidates: dict[str, dict], gaps: Path | None = None) -> str:
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for name, doc in candidates.items():
        (inbox / name).write_text(json.dumps(doc), encoding="utf-8")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        promote.main(["--inbox", str(inbox),
                      "--gaps", str(gaps if gaps is not None else _empty_register(tmp_path))])
    return buf.getvalue()


def _accepted(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("ACCEPT")]


def _rejected(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith("REJECT")]


def test_a_differently_spelled_but_interchangeable_check_is_refused(tmp_path):
    """The seven-records-for-one-gap flood, as a test."""
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A),
        "b.json": _doc(title="A read carries no tenant predicate", check=TENANT_B),
    })
    assert len(_accepted(out)) == 1, f"one gap must land once:\n{out}"
    assert len(_rejected(out)) == 1, out
    assert "interchangeable" in _rejected(out)[0], _rejected(out)[0]


def test_the_refusal_names_the_record_it_duplicates(tmp_path):
    """A reason a human cannot act on is not a reason."""
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A),
        "b.json": _doc(title="A read carries no tenant predicate", check=TENANT_B),
    })
    kept = _accepted(out)[0].split("->")[1].strip().split("-")[0:2]
    twin_id = "-".join(kept)
    assert twin_id in _rejected(out)[0], (
        f"the refusal must name {twin_id}: {_rejected(out)[0]}")
    assert "Retrieval is not scoped to a tenant" in _rejected(out)[0], (
        "and quote its title, so a reviewer can judge the call without opening the file")


def test_a_genuinely_different_check_still_lands(tmp_path):
    """The other half of two-sided. A gate that refuses everything is not a gate."""
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A),
        "z.json": _doc(title="A retry has no jitter so clients synchronise", check=_check()),
    })
    assert len(_accepted(out)) == 2, f"two distinct gaps must both land:\n{out}"
    assert not _rejected(out), out


def test_a_broader_check_does_not_absorb_a_narrower_one(tmp_path):
    """One-way is SUBSUMPTION, not identity; only the symmetric case may block.

    Measured consequence of getting this wrong: accepting one-way hits let a broad
    cost check swallow three genuinely distinct records in the same pass.
    """
    fires = promote._Twins(tmp_path / "fx")
    (tmp_path / "fx").mkdir(parents=True, exist_ok=True)
    from agent_gap_radar.models import Gap
    broad = Gap.model_validate({**_doc(check=BROAD), "id": "GAP-801"})
    narrow = Gap.model_validate({**_doc(check=NARROW), "id": "GAP-802"})
    b, n = fires._tree(broad), fires._tree(narrow)
    assert fires._stands_in_for(b, n), (
        "precondition: the broad detector must fire on the narrow one's fixtures, "
        "or this test is not exercising the one-way case at all")
    assert not fires._stands_in_for(n, b), "precondition: and not the reverse"

    out = _run(tmp_path, {
        "broad.json": _doc(title="Spend is never metered at all", check=BROAD),
        "narrow.json": _doc(title="Token usage is discarded at the call site", check=NARROW),
    })
    assert len(_accepted(out)) == 2, f"subsumption must not refuse:\n{out}"


def test_a_detector_that_fires_on_the_good_fixture_too_is_not_a_twin(tmp_path):
    """The load-bearing half of the test: SILENT on the other's good fixture.

    Without it, "stands in for" degenerates into "also matches", and any check
    broad enough to fire on a mitigated tree gets counted as a duplicate of it.
    Two records agreeing on the symptom while disagreeing on what counts as the
    FIX are different gaps, and this is the case that says so.
    """
    from agent_gap_radar.models import Gap
    fires = promote._Twins(tmp_path / "fx")
    (tmp_path / "fx").mkdir(parents=True, exist_ok=True)
    x = Gap.model_validate({**_doc(check=SCOPE_BY_TENANT), "id": "GAP-811"})
    y = Gap.model_validate({**_doc(check=SCOPE_BY_PRINCIPAL), "id": "GAP-812"})
    tx, ty = fires._tree(x), fires._tree(y)
    spec_x, _, _ = tx
    _, y_bad, y_good = ty
    from agent_gap_radar.checks import Verdict, run_check
    assert run_check(spec_x, y_bad).verdict is Verdict.PRESENT, (
        "precondition: it must fire on the other's bad tree, or the test is vacuous")
    assert run_check(spec_x, y_good).verdict is Verdict.PRESENT, (
        "precondition: and ALSO on the other's good tree, which is the whole point")
    assert not fires._stands_in_for(tx, ty), "firing on both trees is not standing in"

    out = _run(tmp_path, {
        "x.json": _doc(title="A read is not scoped to the calling tenant",
                       check=SCOPE_BY_TENANT),
        "y.json": _doc(title="A read is not bound to the calling principal",
                       check=SCOPE_BY_PRINCIPAL),
    })
    assert len(_accepted(out)) == 2, (
        f"neither detector discriminated on the other's evidence:\n{out}")


def test_a_candidate_is_compared_against_the_existing_register_too(tmp_path):
    """Deduping only within a pass would let tick N+1 re-land tick N's gap."""
    gaps = _empty_register(tmp_path)
    landed = {**_doc(title="Retrieval is not scoped to a tenant", check=TENANT_A),
              "id": "GAP-401"}
    landed["check"] = {**TENANT_A, "id": "CHK-401"}
    (gaps / "GAP-401-retrieval.json").write_text(json.dumps(landed), encoding="utf-8")

    out = _run(tmp_path, {"b.json": _doc(title="A read carries no tenant predicate",
                                         check=TENANT_B)}, gaps=gaps)
    assert not _accepted(out), f"the register already covers this:\n{out}"
    assert "GAP-401" in _rejected(out)[0], _rejected(out)[0]


def test_a_refusal_does_not_contaminate_the_next_candidate(tmp_path):
    """Regression. Ids are handed out as "next free", so a REFUSED candidate leaves
    its number unclaimed and the next candidate is assigned the same one. When the
    fixture cache was keyed by id, that served the refused record's fixtures to its
    successor, which was then judged as though it WERE that record.

    Measured cost while it was live: one true duplicate cascaded into 849 refusals
    out of 859 candidates, every one of them naming the same twin. A cache key is
    not usually a correctness concern; here it decides which evidence a record is
    judged on, which makes it one.
    """
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A),
        "b.json": _doc(title="A read carries no tenant predicate", check=TENANT_B),
        "z.json": _doc(title="A retry has no jitter so clients synchronise", check=_check()),
    })
    assert len(_rejected(out)) == 1, f"only the true duplicate may be refused:\n{out}"
    assert len(_accepted(out)) == 2, (
        f"the record AFTER a refusal must be judged on its own fixtures:\n{out}")
    assert "jitter" in out, "and it is the unrelated one that has to survive"


def test_a_manual_only_candidate_is_not_refused_as_a_twin(tmp_path):
    """A manual check has no fixtures, so it cannot be MEASURED against another.

    Unmeasurable must mean "not compared", never "assumed duplicate" -- the whole
    point of this gate is that it only refuses what it has evidence for.
    """
    manual = {"id": "CHK-900", "rationale": "r",
              "manual_question": "Does your retrieval carry a tenant predicate?"}
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A),
        "m.json": _doc(title="Retrieval is not scoped to a tenant either", check=manual),
    })
    assert len(_accepted(out)) == 2, f"a manual record must not be guessed away:\n{out}"


def test_lookalike_prose_is_reported_as_advisory_and_refuses_nothing(tmp_path):
    """Text similarity was measured NOT to separate duplicates from distinct records,
    so it reports and never blocks. This pins that it stays advisory."""
    shared = {"problem": "a tenant reads another tenant's documents from a shared store",
              "symptom": "an operator sees documents from a tenant that never uploaded them"}
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A, **shared),
        "z.json": _doc(title="A retry has no jitter so clients synchronise",
                       check=_check(), **shared),
    })
    assert len(_accepted(out)) == 2, out
    assert not _rejected(out), "an advisory must never refuse anything"
    notes = [ln for ln in out.splitlines() if ln.startswith("NOTE")]
    assert notes, f"near-identical prose should be surfaced for a human:\n{out}"
    assert "advisory" in notes[0] and "nothing was refused" in notes[0], notes[0]
    assert "most resembles" in notes[0], (
        f"name the one record a reviewer should read next to it: {notes[0]}")
    assert len(notes) == 1, f"a mutual pair prints once, not twice:\n{out}"


def test_the_advisory_is_bounded_by_records_not_by_pairs(tmp_path):
    """An advisory that grows as n-squared is one nobody finishes reading.

    Five mutually-similar records make ten pairs. Reporting every pair produced 29
    lines for 24 real records, which is why each record reports only its single
    closest partner instead.
    """
    shared = {"problem": "a tenant reads another tenant's documents from a shared store",
              "symptom": "an operator sees documents from a tenant that never uploaded them"}
    out = _run(tmp_path, {
        "a.json": _doc(title="Retrieval is not scoped to a tenant", check=TENANT_A, **shared),
        "b.json": _doc(title="A read is not bound to the calling principal",
                       check=SCOPE_BY_PRINCIPAL, **shared),
        "c.json": _doc(title="Spend is never metered anywhere", check=BROAD, **shared),
        "d.json": _doc(title="Token usage is dropped at the call site", check=NARROW, **shared),
        "e.json": _doc(title="A retry has no jitter so clients synchronise",
                       check=_check(), **shared),
    })
    accepted = _accepted(out)
    assert len(accepted) == 5, f"none of these five is a twin of another:\n{out}"
    notes = [ln for ln in out.splitlines() if ln.startswith("NOTE")]
    assert notes, "five near-identical records must not pass unremarked"
    assert len(notes) <= len(accepted), (
        f"{len(notes)} advisory lines for {len(accepted)} records is pairwise growth:\n{out}")
    assert all("most resembles" in ln for ln in notes), notes


def test_prose_below_the_threshold_produces_no_advisory_noise(tmp_path):
    """A detector that fires on everything trains its reader to ignore it.

    The two records here overlap on 2 of 12 tokens, so their similarity is NON-ZERO
    but under the threshold. That precondition is asserted rather than assumed: a
    pair with literally zero overlap would be excluded by the "strictly better than
    nothing" comparison whatever the threshold is, which makes it useless as a
    control -- it would pass even with the threshold set to zero.
    """
    a_prose = {"problem": "a tenant reads another tenant's documents from a shared retrieval store",
               "symptom": "an operator sees documents from a tenant that never uploaded them"}
    b_prose = {"problem": "every client retries on the same schedule so load arrives as a spike",
               "symptom": "an operator sees a sawtooth of traffic instead of a smooth recovery"}
    a_title = "Retrieval is not scoped to a tenant"
    b_title = "A retry storm has no jitter so clients synchronise"

    class _Prose:
        def __init__(self, title, problem, symptom):
            self.title, self.problem, self.symptom = title, problem, symptom

    ta = promote._lookalike_tokens(_Prose(a_title, **a_prose))
    tb = promote._lookalike_tokens(_Prose(b_title, **b_prose))
    overlap = len(ta & tb) / min(len(ta), len(tb))
    assert 0 < overlap < promote._LOOKALIKE_AT, (
        f"precondition: this control needs a non-zero overlap under the threshold, "
        f"got {overlap:.3f} against {promote._LOOKALIKE_AT}")

    out = _run(tmp_path, {
        "a.json": _doc(title=a_title, check=TENANT_A, **a_prose),
        "z.json": _doc(title=b_title, check=_check(), **b_prose),
    })
    assert len(_accepted(out)) == 2, out
    assert not [ln for ln in out.splitlines() if ln.startswith("NOTE")], out


def test_the_advisory_names_the_STRONGEST_partner_not_just_any_partner(tmp_path):
    """"most resembles" is a claim about ranking, so it has to be true.

    Three records: A resembles B strongly (0.77) and C weakly (0.23), both above the
    threshold. A's line must name B. Reporting whichever partner happened to be
    compared last would still print one line per record and still look correct, which
    is exactly why the count alone is not enough to pin this down.
    """
    class _Prose:
        def __init__(self, title, problem, symptom):
            self.title, self.problem, self.symptom = title, problem, symptom

    a = dict(title="Retrieval is not scoped to a tenant",
             problem="a tenant reads another tenant's documents from a shared vector store",
             symptom="an operator sees documents from a tenant that never uploaded them")
    b = dict(title="A memory read is not scoped to a tenant",
             problem="a tenant reads another tenant's documents from a shared memory store",
             symptom="an operator sees documents from a tenant that never wrote them")
    c = dict(title="An approval gate records no decision",
             problem="an auditor cannot tell a real review from a rubber stamp on a shared queue",
             symptom="an operator sees an approved run with no record of who approved it")

    tok = {k: promote._lookalike_tokens(_Prose(**v)) for k, v in (("a", a), ("b", b), ("c", c))}

    def ov(x, y):
        return len(tok[x] & tok[y]) / min(len(tok[x]), len(tok[y]))

    assert ov("a", "b") > ov("a", "c") >= promote._LOOKALIKE_AT, (
        "precondition: A must resemble B more than C, with BOTH above the threshold, "
        f"got a~b={ov('a', 'b'):.2f} a~c={ov('a', 'c'):.2f}")

    out = _run(tmp_path, {
        "a.json": _doc(check=TENANT_A, **a),
        "b.json": _doc(check=SCOPE_BY_PRINCIPAL, **b),
        "c.json": _doc(check=_check(), **c),
    })
    assert len(_accepted(out)) == 3, out
    notes = [ln for ln in out.splitlines() if ln.startswith("NOTE")]
    assert any("GAP-001 most resembles GAP-002" in ln for ln in notes), (
        f"A's closest record is B, not whichever was compared last:\n" + "\n".join(notes))
    assert not any("GAP-001 most resembles GAP-003" in ln for ln in notes), notes
