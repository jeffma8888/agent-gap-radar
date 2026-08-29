"""Promote researched candidate gap records into the register, but only if they earn it.

This is the quality gate that makes UNATTENDED research safe. A research agent
writes a candidate JSON into an inbox; nothing reaches the register until it has
passed every gate below. A candidate that fails is REJECTED with a written
reason, never merged with a warning.

Gates, in order:
  1. Schema      - parses as a Gap under the same model the register uses.
  2. Evidence    - at least one resolvable-looking locator, and no source class
                   that scores zero confidence as the ONLY evidence.
  3. Fixtures    - an automated check must FIRE on its own bad fixture (with a
                   reported location) and stay SILENT on its good fixture.
                   A detector nobody proved against a known-bad sample is worse
                   than no detector, because it reports health it never measured.
  4. Novelty     - refuses a candidate whose check signature already exists,
                   so a fan-out of research agents cannot flood the register
                   with restatements of one gap.
  5. Twins       - refuses a candidate whose check is INTERCHANGEABLE with one
                   already held: each fires on the other's bad fixture and stays
                   silent on the other's good one. Gate 4 only catches a copied
                   signature; parallel agents restate one gap in different words
                   with differently-spelled detectors, which is invisible to it.

Ids are ALWAYS reassigned here. Research agents run context-free and in
parallel, so they cannot coordinate numbering; letting them try guarantees
collisions. They submit a placeholder and this tool allocates.

Offline. Locator liveness is deliberately NOT checked here - that needs network,
which belongs in tools/check_locators.py, out of band.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agent_gap_radar.checks import Verdict, run_check  # noqa: E402
from agent_gap_radar.models import Gap  # noqa: E402
from agent_gap_radar.registry import load_all  # noqa: E402
from agent_gap_radar.scoring import confidence, priority  # noqa: E402
from agent_gap_radar.taxonomy import SOURCE_WEIGHTS  # noqa: E402


class Rejected(Exception):
    """A candidate failed a gate. The message is the reason, written to disk."""


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:56].rstrip("-")


def _next_id(existing: list[str], prefix: str) -> str:
    used = {int(m.group(1)) for i in existing if (m := re.fullmatch(prefix + r"-(\d{3})", i))}
    n = 1
    while n in used:
        n += 1
    return f"{prefix}-{n:03d}"


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _gate_evidence(gap: Gap) -> None:
    if not gap.evidence:
        raise Rejected("no evidence: a gap record with no source is an opinion")
    weights = {e.source_class: SOURCE_WEIGHTS.get(e.source_class, 0) for e in gap.evidence}
    if all(w == 0 for w in weights.values()):
        raise Rejected(
            "every evidence item is a zero-weight source class "
            f"({sorted(weights)}): the claim rests on nothing checkable"
        )
    for e in gap.evidence:
        if not re.match(r"https?://\S+$", e.locator):
            raise Rejected(f"locator is not a fetchable URL: {e.locator!r}")
        if len(e.quote.split()) < 6:
            raise Rejected(
                f"quote for {e.locator!r} is too short to be a real excerpt: {e.quote!r}"
            )


def _gate_fixtures(gap: Gap) -> None:
    """The anti-fail-open gate. Prove the check two-sided before trusting it."""
    check = gap.check
    if check is None:
        raise Rejected("no check: research must land as a check, not as prose")
    if check.present_when is None:
        if not check.manual_question:
            raise Rejected("a manual check needs a manual_question")
        return
    if check.fixtures is None:
        raise Rejected("an automated check must ship bad AND good fixtures")

    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad"
        good = Path(td) / "good"
        bad.mkdir()
        good.mkdir()
        _write_tree(bad, check.fixtures.bad)
        _write_tree(good, check.fixtures.good)

        spec = check.model_dump(exclude_none=True)
        out_bad = run_check(spec, bad)
        if out_bad.verdict is not Verdict.PRESENT:
            raise Rejected(
                f"check does not fire on its own bad fixture (got "
                f"{out_bad.verdict.value}; {out_bad.reason}): an unproven "
                "detector reports health it never measured"
            )
        if not out_bad.locations:
            raise Rejected(
                "check fires on the bad fixture but reports no location, "
                "so a user cannot act on the finding"
            )
        if run_check(spec, good).verdict is Verdict.PRESENT:
            raise Rejected(
                "check also fires on its own good fixture: it does not "
                "discriminate, it just matches everything"
            )


def _signature(check) -> str:
    """A stable fingerprint of what a check actually looks for."""
    return json.dumps(
        [check.applies_when, check.present_when, check.mitigated_when],
        sort_keys=True,
        separators=(",", ":"),
    )


class _Twins:
    """Behavioural duplicate detection: are two records' DETECTORS interchangeable?

    The exact `_signature` gate above only catches a candidate that copies another
    check's patterns verbatim. It cannot see the case that actually floods a
    register: several research agents, asked overlapping questions, describe ONE
    gap in different words with differently-spelled detectors.

    This gate answers the question by MEASUREMENT rather than by paraphrase. Two
    records are the same gap when each one's check fires on the other's bad
    fixture and stays SILENT on the other's good fixture -- that is, when either
    detector could stand in for the other on the other's own evidence. The
    "silent on good" half is what keeps it honest: a check broad enough to match
    anything fires on both trees and is therefore never counted as a twin.

    WHY NOT TEXT SIMILARITY, measured rather than assumed. Over 24 real
    candidates (276 pairs; 28 hand-labelled as one-gap-restated, 248 as
    distinct), every lexical signal tried had OVERLAPPING distributions, so no
    threshold separates them:

        feature      duplicates min   distinct max
        title Jaccard      0.000          0.158
        body Jaccard       0.100          0.105
        body containment   0.205          0.213
        title SequenceMatcher 0.275       0.482

    A gate built on any of those must either miss real duplicates or refuse real
    research, and tuning the number only moves which error you get. Restricting
    the comparison to records sharing a layer and gap_type does not rescue it
    either: only 13 of the 28 duplicate pairs share both, because agents file the
    same gap under different layers. So text similarity is reported as ADVISORY
    (see `_advisory_lookalikes`) and never blocks.

    On the same 248 distinct pairs the mutual-equivalence test above produced
    ZERO false positives, and collapsed the 24 candidates to 18 in rank order.

    WHY MUTUAL AND NOT ONE-WAY. A one-way hit means A's check also fires on B's
    evidence -- subsumption, not identity, and it is real information. It is NOT
    a licence to refuse: accepting one-way hits made a broad cost check absorb
    three genuinely distinct records in the same measurement. Generality is not
    sameness, so only the symmetric case blocks.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._trees: dict[str, tuple[dict, Path, Path] | None] = {}
        self._known: list[Gap] = []

    @staticmethod
    def _key(gap: Gap) -> str:
        """Identify a record by its CHECK CONTENT, never by its id.

        Ids are not identity here. This tool reassigns a candidate's id at the
        moment it is examined, and the id it hands out is the next FREE one, so a
        candidate that gets refused leaves its number unclaimed and the next
        candidate is assigned the very same number. An id-keyed cache therefore
        serves the refused record's fixtures to its successor, which then gets
        judged as though it were that record -- measured cost when this was live:
        one true duplicate started a cascade that refused 849 of 859 candidates,
        every one of them naming the same twin.
        """
        check = gap.check
        if check is None:
            return "no-check:" + gap.id
        body = json.dumps(
            check.model_dump(exclude_none=True, exclude={"id"}),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:20]

    def _tree(self, gap: Gap) -> tuple[dict, Path, Path] | None:
        """Materialise a record's fixture pair once per pass. None = not comparable."""
        key = self._key(gap)
        if key in self._trees:
            return self._trees[key]
        check = gap.check
        built: tuple[dict, Path, Path] | None = None
        if check is not None and check.present_when is not None and check.fixtures is not None:
            base = self._root / key
            bad, good = base / "bad", base / "good"
            bad.mkdir(parents=True, exist_ok=True)
            good.mkdir(parents=True, exist_ok=True)
            _write_tree(bad, check.fixtures.bad)
            _write_tree(good, check.fixtures.good)
            built = (check.model_dump(exclude_none=True), bad, good)
        self._trees[key] = built
        return built

    @staticmethod
    def _stands_in_for(
        mine: tuple[dict, Path, Path], theirs: tuple[dict, Path, Path]
    ) -> bool:
        """Does MY check reproduce THEIR check's verdicts on THEIR own fixtures?"""
        spec = mine[0]
        _, bad, good = theirs
        return (
            run_check(spec, bad).verdict is Verdict.PRESENT
            and run_check(spec, good).verdict is not Verdict.PRESENT
        )

    def remember(self, gap: Gap) -> None:
        self._known.append(gap)

    def twin_of(self, gap: Gap) -> Gap | None:
        """The first remembered record whose detector is interchangeable with this one."""
        mine = self._tree(gap)
        if mine is None:
            return None
        for other in self._known:
            theirs = self._tree(other)
            if theirs is None:
                continue
            if self._stands_in_for(mine, theirs) and self._stands_in_for(theirs, mine):
                return other
        return None


#: Words too common in this domain to carry any signal about WHICH gap a record
#: describes. Dropped before the advisory overlap is computed.
_LOOKALIKE_STOP = frozenset("""
a an the and or but if then than that this these those is are was were be been being
of to in on at by for with from into over under about as it its their there here so
not no nor does do did done doing have has had can could should would will shall may
might must one two any each every some all both other another same such only just also
very more most what which who whom whose when where why how because while during
before after agent agents run runs running system systems tool tools model models
call calls
""".split())
_LOOKALIKE_TOKEN = re.compile(r"[a-z][a-z0-9-]{2,}")

#: Containment at which a pair is worth a human's attention. This is the 99th
#: percentile of the DISTINCT pairs in the measurement quoted on `_Twins`, chosen
#: so the advisory is noisy rather than silent. It is deliberately NOT a rejection
#: threshold: the duplicate minimum on the same data was 0.205, so any cutoff here
#: misclassifies one side or the other.
_LOOKALIKE_AT = 0.20


def _lookalike_tokens(gap: Gap) -> set[str]:
    text = " ".join([gap.title, gap.problem, gap.symptom]).lower()
    return {t for t in _LOOKALIKE_TOKEN.findall(text) if t not in _LOOKALIKE_STOP}


def _advisory_lookalikes(gaps: list[Gap]) -> list[str]:
    """ADVISORY, never blocking: each record's CLOSEST lookalike, if it has one.

    Reported because the behavioural gate is deliberately conservative -- it
    refuses only records whose detectors are provably interchangeable, which
    leaves semantic restatements whose checks look for different code shapes. A
    line here is a question for a reviewer, not a verdict, and NOTHING in this
    tool acts on it. See `_Twins` for why it cannot be promoted to a gate.

    Two shapes were tried on the real backlog and both were worse:

      * every pair above the threshold -- 29 lines for 24 records, and an
        advisory nobody finishes reading is indistinguishable from none, the same
        way an unread quarantine queue is;
      * connected components -- 3 tidy "families", but single linkage chains
        through weak links, so a 9-member family put approval-gate logging in
        with sampling-settings recording. A grouping that merges things a reader
        can see are different gets the whole advisory dismissed.

    So each record reports only its single strongest partner, and a mutual pair
    prints once. That is bounded by the number of records, never chains, and
    answers the question a reviewer actually has: which other record do I need to
    read next to this one?
    """
    toks = {g.id: _lookalike_tokens(g) for g in gaps}
    by_id = {g.id: g for g in gaps}

    best: dict[str, tuple[float, str]] = {}
    for i, a in enumerate(gaps):
        for b in gaps[i + 1:]:
            ta, tb = toks[a.id], toks[b.id]
            if not ta or not tb:
                continue
            overlap = len(ta & tb) / min(len(ta), len(tb))
            if overlap < _LOOKALIKE_AT:
                continue
            for x, y in ((a.id, b.id), (b.id, a.id)):
                if overlap > best.get(x, (0.0, ""))[0]:
                    best[x] = (overlap, y)

    seen: set[frozenset[str]] = set()
    out: list[str] = []
    for gid, (overlap, partner) in sorted(best.items(), key=lambda kv: (-kv[1][0], kv[0])):
        pair = frozenset((gid, partner))
        if pair in seen:
            continue
        seen.add(pair)
        out.append(f"{overlap:.2f}  {gid} most resembles {partner}: "
                   f"{by_id[gid].title[:56]!r} / {by_id[partner].title[:56]!r}")
    return out


def _rank(paths: list[Path]) -> list[tuple[Path, Gap | None]]:
    """Best-first work queue: CONFIDENCE before priority, deliberately.

    `priority` is built from severity, frequency and tractability, which a
    research agent assigns to its OWN record. `confidence` is derived from the
    EVIDENCE CLASS, which is far harder to inflate: you cannot upgrade a blog
    post into a peer-reviewed paper by claiming it is one. So when the pipeline
    must choose which of many valid candidates to land, it prefers the records
    whose backing is strongest over the ones that describe themselves as most
    urgent.

    A file that does not parse sorts LAST but keeps its place in the queue, so it
    is still reported by the normal refusal path rather than silently dropped.
    """
    scored: list[tuple[Path, Gap | None]] = []
    for path in paths:
        try:
            scored.append(
                (path, Gap.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            )
        except Exception:
            scored.append((path, None))
    scored.sort(key=lambda t: (
        -(confidence(t[1]) if t[1] is not None else -1),
        -(priority(t[1]) if t[1] is not None else -1),
        t[0].name,
    ))
    return scored


def promote(inbox: Path, gaps_dir: Path, rejected: Path, apply: bool,
            limit: int = 0, register_cap: int = 0) -> int:
    with tempfile.TemporaryDirectory() as fixture_root:
        return _promote(inbox, gaps_dir, rejected, apply, limit, register_cap,
                        _Twins(Path(fixture_root)))


def _promote(inbox: Path, gaps_dir: Path, rejected: Path, apply: bool,
             limit: int, register_cap: int, twins: _Twins) -> int:
    existing = load_all(gaps_dir)
    gap_ids = [g.id for g in existing]
    chk_ids = [g.check.id for g in existing if g.check]
    seen_sigs = {_signature(g.check): g.id for g in existing if g.check}
    for known in existing:
        twins.remember(known)

    candidates = sorted(inbox.glob("*.json"))
    # Publish the denominator on EVERY run, the vacuous one included. This gate runs
    # unattended, and its caller reads a MISSING summary line as proof the tool itself
    # died -- so an early return over an empty inbox made a healthy no-op look like a
    # crash. The empty case now FALLS THROUGH to the one summary emitter at the bottom
    # instead of getting a second copy of it, so the two can never drift apart.
    print(f"examined {len(candidates)} candidates in {inbox}")

    # Typed, and split across two lines rather than one tuple unpack: the compact form
    # spells the summary line's own format substring, which would leave a source census
    # for "exactly one summary emitter" unable to tell an accumulator from an emitter.
    accepted: list[tuple[Path, Gap]] = []
    refused: list[tuple[Path, str]] = []

    # A register is only useful while it stays CURATED. Once research can produce
    # candidates faster than anyone reads them, "passes the gate" stops being a
    # sufficient reason to land: a thousand mechanically-valid records is a junk
    # drawer, and it makes every score already in the register unbelievable. So
    # automatic growth has a ceiling, and reaching it ESCALATES rather than either
    # flooding the register or discarding the research.
    if register_cap and len(existing) >= register_cap:
        print(f"REGISTER AT CAPACITY: {len(existing)} records, cap {register_cap}. "
              f"{len(candidates)} candidate(s) waiting; NOTHING was discarded.")
        print("A human decides what the register carries from here. Strongest "
              "waiting candidates by evidence class:")
        for cpath, cgap in _rank(candidates)[:5]:
            if cgap is None:
                print(f"  (unparseable)  {cpath.name}")
            else:
                print(f"  c{confidence(cgap)} p{priority(cgap):>4}  {cpath.name}")
        return 0

    room = (register_cap - len(existing)) if register_cap else len(candidates)
    budget = max(0, min(limit or len(candidates), room, len(candidates)))
    for path, _prescored in _rank(candidates):
        if len(accepted) >= budget:
            break
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            refused.append((path, f"not valid JSON: {exc}"))
            continue
        try:
            new_gap_id = _next_id(gap_ids, "GAP")
            new_chk_id = _next_id(chk_ids, "CHK")
            raw["id"] = new_gap_id
            if isinstance(raw.get("check"), dict):
                raw["check"]["id"] = new_chk_id
            gap = Gap.model_validate(raw)
            _gate_evidence(gap)
            _gate_fixtures(gap)
            sig = _signature(gap.check)
            if sig in seen_sigs:
                raise Rejected(
                    f"check signature is identical to {seen_sigs[sig]}: this is a "
                    "restatement of a gap already in the register"
                )
            if (twin := twins.twin_of(gap)) is not None:
                raise Rejected(
                    f"check is interchangeable with {twin.id} ({twin.title!r}): each "
                    "fires on the other's bad fixture and stays silent on the other's "
                    "good one, so this is the same gap already covered"
                )
        except Rejected as exc:
            refused.append((path, str(exc)))
            continue
        except Exception as exc:  # pydantic and anything else, same treatment
            refused.append((path, f"{type(exc).__name__}: {exc}"))
            continue

        gap_ids.append(new_gap_id)
        chk_ids.append(new_chk_id)
        seen_sigs[sig] = new_gap_id
        twins.remember(gap)
        accepted.append((path, gap))

    for path, gap in accepted:
        dest = gaps_dir / f"{gap.id}-{_slug(gap.title)}.json"
        print(f"ACCEPT  {path.name} -> {dest.name}")
        if apply:
            body = json.dumps(
                gap.model_dump(exclude_none=True), indent=2, ensure_ascii=False
            )
            tmp = dest.with_suffix(".json.tmp")
            tmp.write_text(body + "\n", encoding="utf-8")
            tmp.replace(dest)
            path.unlink()

    for path, reason in refused:
        print(f"REJECT  {path.name}: {reason}")
        if apply:
            rejected.mkdir(parents=True, exist_ok=True)
            (rejected / (path.stem + ".reason.txt")).write_text(
                f"{path.name}\n\n{reason}\n", encoding="utf-8"
            )
            path.replace(rejected / path.name)

    for line in _advisory_lookalikes([g for _, g in accepted]):
        print(f"NOTE    advisory lookalike, nothing was refused for this: {line}")

    untouched = len(candidates) - len(accepted) - len(refused)
    print(
        f"\n{len(accepted)} accepted, {len(refused)} rejected"
        + (f", {untouched} left for a later pass" if untouched > 0 else "")
        + ("" if apply else "  (dry run - pass --apply to write)")
    )
    return 0 if accepted or not refused else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inbox", type=Path, required=True)
    ap.add_argument("--gaps", type=Path, default=Path("gaps"))
    ap.add_argument("--rejected", type=Path)
    ap.add_argument("--apply", action="store_true", help="Write. Default is a dry run.")
    ap.add_argument("--limit", type=int, default=0,
                    help="accept at most N candidates this pass (0 = no limit)")
    ap.add_argument("--register-cap", type=int, default=0,
                    help="refuse to grow the register beyond N records (0 = off)")
    args = ap.parse_args(argv)
    rejected = args.rejected or args.inbox.parent / "rejected"
    try:
        return promote(args.inbox, args.gaps, rejected, args.apply,
                       limit=args.limit,
                       register_cap=args.register_cap)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
