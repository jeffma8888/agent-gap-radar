# Vision (fixed intent)

`agent-gap-radar` is an evidence-first register of gaps in AI agent infrastructure, and a bridge from that register into an autonomous build loop.

## The intent, stated once

Find where AI agents actually break in production. Record each gap as a checkable artifact rather than an opinion. Rank the register honestly, keeping "how much this matters" separate from "how well we know it". Then convert the top gap into a build-loop PRD so the research changes what gets built.

## In scope

Curating and validating gap records. Improving the taxonomy when a real gap does not fit it. Strengthening the evidence on existing records, especially promoting below-floor records by finding primary sources. Rendering the register (ranked report, per-gap brief). Emitting build-loop PRDs. Tooling that makes the register harder to corrupt: schema gates, determinism, duplicate detection.

## Out of scope

Becoming an agent framework. Calling model APIs at runtime. Network access in the tool or its tests. Scraping. Storing anyone's telemetry. Publishing opinions without a locator and a verbatim quote.

## Quality bar

Offline-first: no network at runtime or in tests. Runtime dependencies: pydantic v2 only. Deterministic, byte-stable output so reports can be committed and diffed. Every renderer's output ends in exactly one newline. Errors go to stderr prefixed `Error: ` with exit code 2; stdout carries only the document.

## The rule that protects the register

A record's confidence is DERIVED from its evidence, never asserted. Any change that lets a record raise its own confidence through prose, or that silently drops below-floor records instead of displaying them, is a regression regardless of how much cleaner the output looks.

## What "done" would look like

The register is the reference a builder checks before starting an agent-infrastructure project, and at least one gap in it has been closed by a loop that started from `radar prd`.
