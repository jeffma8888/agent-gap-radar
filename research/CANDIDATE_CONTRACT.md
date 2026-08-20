# Candidate contract — what a research pass must hand back

A research pass does not hand back prose. It hands back **candidate gap records that
carry an executable check**, because the register's whole purpose is that
`radar scan <target>` can tell a specific project which known gaps it exhibits.
A finding nobody can run against a repo is a reading list, not a radar.

Write one JSON file per candidate into the inbox directory you were given.
`tools/promote.py` is the gate. It reassigns ids, so do not try to pick a free one.

## Gates your candidate must pass (it is rejected otherwise, with a reason)

1. **Schema** — parses as `Gap`. Enums are closed; see below.
2. **Evidence** — every locator is an `http(s)://` URL you actually fetched, every
   `quote` is a verbatim excerpt of six or more words, and **at least one source is
   not `model-output`** (that class is weighted zero: a model asserting something is
   not evidence that it is true).
3. **Fixtures, two-sided** — your check must FIRE on your own `fixtures.bad` tree and
   stay SILENT on your own `fixtures.good` tree, and the firing must report a
   location. This is the gate that matters. A detector nobody proved against a
   known-bad sample reports health it never measured.
4. **Novelty** — a check whose rule signature already exists is rejected as a
   restatement. Read the existing register first.

## Honesty rules, which override completeness

- If a source class is inaccessible to you (X/Twitter and LinkedIn are usually
  login-walled or bot-blocked), **say so in your report and move on.** Never
  synthesise a plausible URL, author, date, or quote. A fabricated locator is worse
  than a missing one because it survives review.
- If you cannot find real public evidence for a gap you believe is real, submit it
  with the evidence you do have and let the confidence score come out low. The
  register displays low-confidence records rather than dropping them; that is the
  designed behaviour, so an honest weak record is welcome and a dressed-up one is not.
- Prefer three well-evidenced candidates over eight thin ones.

## Closed enums

`layer`: model-runtime, orchestration, context-memory, tool-action,
sandbox-isolation, eval-verification, observability, cost-governance,
lifecycle-deploy, multi-agent, human-interface

`gap_type`: missing-primitive, missing-contract, silent-failure, unverifiable,
wrong-default, scaling-cliff, measurement-gap, ergonomics

`source_class` (weight): incident-postmortem 5, first-party-field 5, peer-reviewed 4,
maintainer-primary 4, vendor-primary 4, practitioner-report 3, survey-aggregate 3,
secondary-summary 1, model-output 0

`status`: open, partially-addressed, addressed, retired

## Rule kinds available to a check

`content_matches` / `content_absent` (`globs`, `pattern` — Python `re`),
`file_exists` / `file_absent` (`globs`), and the combinators `any_of` / `all_of`
(each takes a non-empty `rules` list) and `not` (which takes a single `rule`
object, not a `rules` list). Nesting depth is capped at 8. An unknown kind raises
rather than returning False, because a silently-false rule is a fail-open detector.

Every kind above, in one check the loader accepts. This fence is the normative
statement of the shapes; the prose is a summary of it. The suite round-trips every
rule object in this file through the same `Gap` validation `tools/promote.py` runs,
so a shape documented here is a shape that loads.

```json
{
  "applies_when": {"kind": "file_exists", "globs": ["**/pyproject.toml"]},
  "present_when": {
    "kind": "all_of",
    "rules": [
      {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "run_stage\\("},
      {"kind": "content_absent", "globs": ["**/*.py"], "pattern": "partial_result"},
      {
        "kind": "any_of",
        "rules": [
          {"kind": "file_absent", "globs": ["**/evals/**"]},
          {"kind": "not", "rule": {"kind": "file_exists", "globs": ["**/CHECKPOINT.md"]}}
        ]
      }
    ]
  },
  "mitigated_when": {"kind": "content_matches", "globs": ["**/*.py"],
                     "pattern": "write_checkpoint\\("}
}
```

Scanning is restricted to what `git ls-files` reports, so a pattern cannot match
vendored code or gitignored scratch.

## Verdict semantics you are designing against

- `present_when` matching means the gap signature is in the target.
- `mitigated_when` matching means a mitigation was **positively identified**.
  `ABSENT` is never inferred from the mere absence of the bad pattern; absence of
  evidence is silence, not safety.
- Both matching yields `MANUAL`, not a pass: a partial mitigation is the dangerous
  case and it needs a human to look.
- **A `mitigated_when` rule is evaluated with test files EXCLUDED**, and you cannot
  turn that off. A mitigation named only by a test is not a mitigation: credited
  from test text, a thorough suite reads as healthier than untested code, which
  inverts the signal. So write `mitigated_when` to match the code that RUNS, and
  put the mitigation in a non-test path in your `fixtures.good` tree or your
  candidate will be rejected for not discriminating.
- `present_when` still sees test files. A gap signature inside a test is real.
- Locators are ranked code-first and capped, with the suppressed remainder named.
  They are evidence that the signature exists, not a list of places to fix.
- If static analysis genuinely cannot decide, omit `present_when` and ship a
  `manual_question` instead. **An honest manual check is a first-class result.**
  Do not invent a brittle regex just to look automated.

## Skeleton

```json
{
  "id": "GAP-900",
  "title": "One line, the gap not the symptom",
  "layer": "eval-verification",
  "gap_type": "unverifiable",
  "status": "open",
  "problem": "One sentence in the voice of the person hurt by it.",
  "symptom": "What an operator actually observes.",
  "why_now": "Why this is unsolved in 2026 rather than a known solved problem.",
  "existing": ["Partial approach and why it does not close the gap."],
  "severity": 4, "frequency": 4, "tractability": 3,
  "evidence": [
    {
      "source_class": "incident-postmortem",
      "title": "Exact title of the page you fetched",
      "locator": "https://...",
      "date": "2026-01-31",
      "quote": "Verbatim excerpt, never a paraphrase.",
      "note": "Why this supports the gap."
    }
  ],
  "build_hypothesis": "The smallest thing a small team could build that moves it.",
  "tags": ["short", "lowercase"],
  "check": {
    "id": "CHK-900",
    "applies_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "..."},
    "present_when": {"kind": "content_matches", "globs": ["**/*.py"], "pattern": "..."},
    "mitigated_when": {"kind": "content_matches", "globs": ["**/*"], "pattern": "..."},
    "manual_question": "The question to ask a human when static analysis cannot decide.",
    "rationale": "Why this signature indicates the gap, and what it can get wrong.",
    "fixtures": {
      "bad":  {"app/agent.py": "code exhibiting the gap\n"},
      "good": {"app/agent.py": "the same code with the mitigation\n"}
    }
  }
}
```

## Self-verify before you finish

```
cd <repo> && python3 tools/promote.py --inbox <inbox> --gaps gaps
```

Dry run by default. It prints `ACCEPT` or `REJECT` with the reason for every
candidate. **Iterate until yours says ACCEPT.** Submitting a candidate you never
ran this against is the one failure this process cannot absorb.

Every run opens with a census — `examined N candidates in <inbox>` — and closes with
`N accepted, M rejected`, an empty inbox included. Both lines are unconditional on purpose:
an unattended caller reads a missing summary as proof the tool died, so the census is what
keeps "there was nothing to do" distinguishable from a crash.

**Exit 0 on its own does not mean YOUR candidate was accepted.** The status is 0 whenever
anything was accepted OR nothing was refused, so a batch that accepted another agent's file
and rejected yours still exits 0, and so does a run that examined nothing at all. Find your
own filename on an `ACCEPT` line; that is the only signal in the output that is about you.
