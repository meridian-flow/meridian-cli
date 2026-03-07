# Spawn Observability Design

## Summary

Meridian should make spawns observable through Meridian-owned records, not by asking downstream features to parse raw harness logs. This document proposes a spawn-focused refactor that keeps raw harness artifacts for debugging, but introduces a canonical event stream that becomes the single source for status views, report extraction, and future monitoring.

This is a design-for-extension document, not a proposal to build remote/mobile features now.

This repo is still pre-release (`0.0.1`, unreleased). Backward compatibility is not a goal for this refactor; we should prefer the clean target architecture over compatibility layers, legacy output preservation, or transitional interfaces that only exist to protect old consumers.

This refactor is **child-spawn only**. It does not attempt to make the interactive primary session live-observable.

The minimum outcome for this major version is:

1. Every spawn emits a canonical append-only event stream.
2. Meridian parses each harness once, at the adapter boundary.
3. Existing spawn-facing features consume canonical records instead of re-parsing raw harness output.
4. The design leaves room for later primary-session history, remote monitoring, and message injection without forcing a second architecture rewrite.
5. Stale pre-release concepts are deleted instead of carried forward behind compatibility layers.

## Why

Today, spawn observability is split across raw artifacts and ad hoc parsing:

- Harness adapters classify stream events during execution.
- Later code in `extract/report.py` and `ops/_spawn_query.py` re-parses raw artifacts using separate heuristics.
- Different features look at different files (`output.jsonl`, `stderr.log`, `report.md`) and infer different meanings.

That creates three concrete problems:

1. **Semantic drift**. Meridian already has harness-specific knowledge in adapters, but later layers bypass it and guess again.
2. **Weak observability**. A spawn is not represented as a stable event stream Meridian owns; it is reconstructed from debug artifacts.
3. **Poor extension path**. A future monitor, service bridge, or session viewer would either duplicate parsing logic or depend on unstable CLI-native output formats.

This is the wrong boundary. Meridian should own the meaning of spawn activity.

## Goals

- Make every spawn observable through canonical Meridian records.
- Centralize harness-specific parsing in harness adapters.
- Stop feature code from scraping raw harness output directly.
- Preserve file-based authority under `.meridian/.spaces/<space-id>/`.
- Keep raw artifacts for forensics and harness debugging.
- Support future evolution toward session history, remote monitoring, and interactive primary-session control.
- Keep the child-spawn design compatible in shape and vocabulary with a possible future primary-session observability design, without taking on that scope now.

## Non-Goals

- Building a mobile app, remote service, websocket transport, or live API in this refactor.
- Solving full primary-session history and injection now.
- Making the interactive primary session live-observable.
- Building a PTY broker, wrapper CLI, or Meridian-owned interactive terminal transport for primary sessions.
- Replacing existing raw artifacts.
- Designing a generalized event warehouse or database-backed telemetry system.
- Preserving unstable pre-release output contracts for compatibility.

## Design Principles

### Meridian owns normalized meaning

Harness CLIs can change output formats. Meridian should absorb that variability at the adapter boundary and persist stable normalized records.

### Raw artifacts are debug inputs, not product APIs

`output.jsonl`, `stderr.log`, and harness-native session files remain useful, but only as low-level evidence. Product surfaces should not depend on them directly.

### Append-only files remain the authority

The canonical observability layer must follow the repo's file-first architecture. No database, no hidden in-memory-only state.

### Spawns first, sessions later

Spawns are the minimum observable unit we need now. The design should leave a clean path for primary-session observability later without expanding scope immediately.

### Primary observability is a different transport problem

Child spawns are already launched behind Meridian-controlled pipes, so Meridian can capture and normalize them directly. Interactive primary sessions currently inherit the terminal and are only tracked through start/stop metadata plus a harness session reference. Making primary sessions live-observable would require Meridian to become a PTY/terminal broker or otherwise sit inline on the interactive transport. That is a valid future direction, but it is a distinct architecture with materially larger scope.

### Delete stale concepts instead of preserving them

Because the codebase is unreleased, old abstractions and compatibility aliases should not survive once the new boundary is in place. A correct replacement should delete the superseded concept, not sit beside it.

## Current State

### Existing raw artifacts

Per spawn, Meridian may already write:

- `output.jsonl`
- `stderr.log`
- `tokens.json`
- `report.md`

These artifacts are useful, but they are harness-oriented, not Meridian-oriented.

### Existing normalized concepts

Meridian already has pieces of a normalized event model:

- Harness adapters expose `parse_stream_event()`.
- `StreamEvent` already has `event_type`, `category`, `text`, and `metadata`.
- Runtime execution already observes parsed events while streaming.

This is the right direction, but it stops too early. Parsed events are used transiently during execution, then later logic re-opens raw files and guesses again.

### Current primary-session boundary

Primary sessions already have limited post-session observability:

- `sessions.jsonl` tracks session lifecycle metadata and the resolved harness session ID
- `spawns.jsonl` tracks the primary launch as a spawn with `kind="primary"`
- harness-native transcripts may exist outside Meridian and can often be resumed via the stored session reference

What Meridian does **not** currently own for primary sessions:

- live stream parsing
- canonical primary-session events
- Meridian-owned transcript/message history
- per-session `output.jsonl` / `stderr.log` artifacts for the interactive run

That limitation is acceptable for this refactor. The goal here is to fix child-spawn observability where Meridian already controls the execution boundary.

### Main architectural smell

The key smell is duplicated post-hoc parsing outside adapters:

- `src/meridian/lib/extract/report.py`
- `src/meridian/lib/ops/_spawn_query.py`

These paths encode their own ideas of:

- what counts as assistant output
- which file to inspect
- how to collapse structured content into text
- what fallback behavior is acceptable

That logic should not live there.

## Proposed Architecture

Introduce a canonical spawn observability layer with three levels:

1. **Raw harness artifacts**
2. **Canonical Meridian event stream**
3. **Derived spawn views**

This architecture applies to **child spawns only** in this major-version refactor.

### Level 1: Raw harness artifacts

Keep existing artifacts unchanged:

- `output.jsonl`
- `stderr.log`
- `tokens.json`
- `report.md`

These remain useful for debugging, replay, and adapter development.

### Level 2: Canonical Meridian event stream

Add a Meridian-owned append-only file per spawn:

- `.meridian/.spaces/<space-id>/spawns/<spawn-id>/events.jsonl`

This becomes the authoritative event stream for spawn activity.

Each line is one normalized Meridian event. Adapters emit events in their harness-specific parsing code; Meridian persists them immediately during execution.

### Level 3: Derived spawn views

Feature code reads from canonical records, not raw artifacts. Derived views may include:

- last assistant message
- running status summary
- extracted report fallback
- tool activity
- sub-run activity
- final lifecycle state

These are read models over `events.jsonl`, not alternate parsers of raw logs.

## Scope Boundary

### In scope

- child spawn execution
- child spawn raw artifacts
- child spawn canonical `events.jsonl`
- child spawn report/status/query readers
- adapter parsing at the child-spawn boundary

### Out of scope

- interactive primary-session live capture
- importing harness-native primary transcripts into Meridian
- building a unified primary + child event store in this slice
- changing primary launch UX to run through a Meridian terminal proxy

### Why the primary path is not included

The child-spawn path already runs behind Meridian-owned stdout/stderr capture, so this refactor can improve semantics without changing the execution model. The primary path does not. Meridian currently launches the primary harness interactively and lets it own the terminal until exit. Closing that observability gap would require a new interactive transport boundary, not just a better parser. That is too much scope for the current problem and would blur Meridian's coordination role into a wrapper CLI/runtime shell project.

### What to focus on

The design should stay ruthless about the immediate problem:

- define the canonical child-spawn event record cleanly
- persist it during execution
- migrate spawn-facing readers to it
- delete raw-artifact heuristics once the replacement exists

Do not spend this refactor inventing abstractions for future primary-session capture beyond what is needed to avoid obvious naming or schema conflicts.

## Deletion Policy

This refactor should explicitly remove stale codepaths, not just add a better one.

### Delete once canonical events exist

- raw assistant-message extraction in `src/meridian/lib/extract/report.py`
- raw running-message extraction in `src/meridian/lib/ops/_spawn_query.py`
- fallback-to-last-raw-line report behavior
- any spawn feature path that reads `stderr.log` or `output.jsonl` as a product input instead of debug evidence

### Delete compatibility-only spawn surfaces

Pre-release compatibility aliases and dual-shape outputs should not survive this refactor. In particular, compatibility-only fields in spawn wait/show models should be removed instead of re-supported by the new design.

### Keep only as debug artifacts

- `output.jsonl`
- `stderr.log`
- `tokens.json`

These stay on disk, but they are no longer part of the semantic read path for spawn-facing features.

## Consistency With Primary Paths

Even though primary launch and child spawn execution are separate paths today, they should stay internally consistent where that does not force shared execution machinery.

Good consistency targets:

- reuse the same status vocabulary where meanings match (`running`, `succeeded`, `failed`)
- prefer the same lifecycle naming style across child events and primary metadata
- keep per-spawn/per-session directory layout and path helpers conceptually aligned
- avoid harness-specific semantics leaking into one path but not the other when Meridian can define a shared concept cleanly

Bad consistency targets:

- forcing primary launch to pretend it has child-style stream artifacts when it does not
- introducing fake shared abstractions that hide the real transport differences
- blocking child-spawn cleanup work until primary can match it exactly

## Canonical Event Model

The schema should be small, explicit, and stable. It does not need to preserve every raw harness field.

Recommended fields:

```json
{
  "ts": "2026-03-06T18:12:01Z",
  "space_id": "s1",
  "spawn_id": "p12",
  "harness": "codex",
  "event_id": "e41",
  "event_type": "message.delta",
  "category": "assistant",
  "role": "assistant",
  "text": "Implemented parser normalization",
  "status": "in_progress",
  "tool_name": null,
  "subspawn_id": null,
  "raw_ref": {
    "stream": "stdout",
    "artifact": "output.jsonl",
    "line": 42
  }
}
```

### Required fields

- `ts`
- `space_id`
- `spawn_id`
- `harness`
- `event_id`
- `event_type`
- `category`

### Optional fields

- `role`
- `text`
- `status`
- `tool_name`
- `tool_args_summary`
- `exit_code`
- `error`
- `subspawn_id`
- `raw_ref`
- `metadata`

### Canonical categories

Use a limited category set:

- `assistant`
- `thinking`
- `tool_use`
- `subrun`
- `lifecycle`
- `error`
- `progress`

These categories should be Meridian-owned, even if harness-specific event types differ.

### Canonical event types

Use explicit normalized event types where useful:

- `lifecycle.started`
- `lifecycle.completed`
- `lifecycle.failed`
- `message.delta`
- `message.completed`
- `thinking.delta`
- `tool.started`
- `tool.completed`
- `subrun.started`
- `subrun.completed`
- `warning`
- `error`

Meridian does not need to normalize every raw harness event into a perfect taxonomy on day one. It only needs enough event types to make spawns observable and support stable consumers.

## Adapter Responsibilities

Harness adapters should become the only place that understands harness-native output structure.

### Adapter contract changes

Today, adapters expose `parse_stream_event(line) -> StreamEvent | None`.

That is close, but not sufficient as the long-term boundary. The contract should evolve toward:

- decode one raw stdout/stderr line into one or more canonical Meridian events
- indicate when an event contributes assistant-visible message text
- expose enough structure to assemble reports and live status safely

Two viable paths:

### Option A: Evolve `StreamEvent`

Keep the current execution flow, but strengthen `StreamEvent` into the canonical persisted event shape.

Pros:

- Smaller refactor
- Reuses existing adapter entrypoints
- Minimal churn in execution pipeline

Cons:

- Risks overloading one struct for runtime, persistence, and display concerns

### Option B: Add a distinct persisted event type

Keep `StreamEvent` for in-process parsing and map it to a persisted `SpawnEventRecord`.

Pros:

- Cleaner separation between runtime parsing and on-disk schema
- Easier schema evolution

Cons:

- Slightly larger refactor

Recommendation: **Option B**. The extra type boundary is worth it because observability files are becoming a durable surface, not just an internal callback payload.

## On-Disk Layout

For this phase, add one canonical file:

```text
.meridian/.spaces/<space-id>/spawns/<spawn-id>/
  events.jsonl
  output.jsonl
  stderr.log
  tokens.json
  report.md
  params.json
```

`params.json` is included because a self-contained spawn directory is more debuggable and more future-proof than scattering execution context across unrelated files.

### Why only `events.jsonl` now

It is enough to support the current need: spawn observability.

We should defer `messages.jsonl` and session-level canonical files until there is a concrete primary-session design slice. The canonical event stream should be designed so those later files can be derived from it.

## Write Path

### During spawn execution

`src/meridian/lib/exec/spawn.py` already captures stdout/stderr and optionally parses stdout lines through the adapter.

Refactor the write path so that:

1. Raw stdout/stderr are still written to raw artifacts.
2. Adapter-decoded canonical events are appended to `events.jsonl` immediately.
3. Lifecycle events are also written by Meridian itself, not inferred later.

That means Meridian should emit canonical records for:

- process start
- parsed assistant/tool/thinking/subrun events
- timeouts
- cancellations
- final completion/failure

### Persistence rules

- `events.jsonl` is append-only.
- Writes should use the same tmp+rename or append discipline used elsewhere in `.meridian/.spaces`.
- If per-line append is used directly, the helper must define newline and flush behavior clearly.
- The raw artifacts and canonical event stream do not need to be written atomically as one unit; they serve different roles.

## Read Path

Once `events.jsonl` exists, spawn-facing features should move to it.

### `spawn show`

Should derive from canonical events:

- current status
- last assistant message
- recent tool activity
- sub-run summary
- failure details

It should not inspect raw harness stdout/stderr directly except for debug-only output.

### Report extraction

Report extraction should prefer:

1. explicit `report.md`
2. canonical assistant message events

It should not guess from the last non-empty raw line in `output.jsonl`. That behavior should be deleted, not preserved as a fallback.

### Running status

Running-spawn status should derive from recent canonical events, not a special parser over `stderr.log`.

## Report Policy

This refactor does not require changing the high-level report policy, but it should simplify fallback behavior.

Recommended rule order:

1. If `report.md` exists and is non-empty, use it.
2. Otherwise, derive fallback report content from canonical assistant message events.
3. If no assistant content exists, `report` is absent.

This removes the need for ad hoc raw-log heuristics in report extraction.

## Migration Strategy

This should be done in slices, not one large rewrite. But because Meridian is unreleased, the slices do not need to preserve old behavior between steps beyond what is necessary to keep the codebase working during development. We should remove incorrect or redundant paths rather than carrying them forward behind compatibility shims.

### Slice 1: Canonical spawn event writer

- Define `SpawnEventRecord`
- Add `events.jsonl`
- Persist lifecycle and parsed adapter events during spawn execution
- Do not preserve old parser abstractions longer than necessary to land the writer cleanly

### Slice 2: Shared read helpers over canonical events

- Add helpers to read last assistant message, latest lifecycle state, and recent event summaries from `events.jsonl`
- Remove existing raw parsing paths instead of introducing long-lived transitional fallback layers

### Slice 3: Move spawn features to canonical records

- Switch `spawn show`
- Switch running status
- Switch report fallback extraction
- Remove duplicated assistant-parsing heuristics from raw artifact readers
- Delete superseded helper functions and dead model fields in the same slice

### Slice 4: Tighten adapter contracts

- Expand adapter decoding where needed for Codex, Claude, and OpenCode
- Add fixture-based tests for each harness output shape Meridian supports
- Delete adapter-facing abstractions that only existed to support the old heuristic readers

### Slice 5: Optional later work

- add `messages.jsonl`
- add canonical primary-session records
- add history import/injection abstractions
- add service-facing or streaming readers

## Cleanup Opportunities

This refactor can pay down a few adjacent inconsistencies without expanding into primary-session transport work:

- standardize category naming (`subrun` vs `sub-run`, `tool_use` vs `tool-use`) so persisted records and terminal-only labels do not drift
- centralize spawn event read/write helpers instead of leaving parsing logic split across query and extract modules
- keep `spawn_store` and `session_store` conventions aligned where practical (append-only JSONL, lifecycle naming, helper shape)
- remove child-spawn-only heuristics from shared-looking modules so the primary path is not implicitly coupled to raw artifact scraping behavior it does not use

These cleanups are worth doing because they reduce semantic drift. They are not a reason to broaden scope into interactive primary capture.

## Testing Strategy

This refactor only helps if parser correctness becomes explicit and testable.

### Adapter fixtures

Each harness should have fixtures representing real output shapes Meridian relies on:

- Claude stream-json output
- Codex JSON output, including delta events
- OpenCode JSON output

Tests should assert normalized canonical events, not only final display strings.

### Persistence tests

Add tests that verify:

- `events.jsonl` is written for successful runs
- lifecycle events appear even when assistant text does not
- failure/timeout/cancellation states are represented canonically
- report fallback uses canonical assistant events, not arbitrary raw line fallback

### Backward-safety tests

Ensure existing raw artifacts still exist and remain useful for debugging. This is an additive observability layer for low-level evidence, but it is allowed to be a breaking change for any pre-release consumer currently scraping raw artifacts as a product interface.

## Risks

### Over-normalizing too early

If the schema tries to capture every harness nuance now, the first implementation will become bloated. The initial schema should focus on observability, not exhaustiveness.

### Leaving heuristics in place forever

Because the project is unreleased, transitional fallbacks should be treated as a last resort. The goal is to eliminate raw-artifact scraping from normal feature code, not to preserve it behind a second codepath.

### Half-migrated architecture

The main failure mode is landing canonical events while still leaving normal feature code on the raw-artifact path. That would create two semantic systems and guarantee drift. Each feature migrated to canonical records should delete the old path in the same slice.

### Scope creep into primary transport

Another failure mode is using this child-spawn refactor as a pretext to partially wrap the interactive primary session. A half-proxied primary path would add complexity without delivering a coherent observability model. If primary observability becomes important, it should be designed as its own transport/project slice.

### Confusing runtime and persisted models

If the same model is used for in-memory callbacks, text formatting, and on-disk persistence, schema drift will reappear in a different form. Keep the persisted record type explicit.

## Open Questions

1. Should `events.jsonl` include raw metadata blobs, or only curated fields plus a `raw_ref` pointer?
2. Do we want `message.delta` events only, or both deltas and assembled `message.completed` records in phase 1?
3. Should Meridian persist canonical events for stderr-derived failures and warnings even when the harness emits no structured stdout?
4. Do we want a separate `messages.jsonl` for spawns in this major version, or should that wait until primary-session design work begins?
5. Which naming should become canonical for shared concepts that appear in both child and primary metadata (for example `subrun` vs `sub-run`)?

## Recommendations

### Decision 1

Adopt canonical spawn `events.jsonl` in this major version.

### Decision 2

Move assistant/report/status extraction to canonical event readers, not raw artifact parsers.

### Decision 3

Keep phase 1 scoped to spawns. Do not fold primary-session history and injection into this refactor.

### Decision 4

Treat future monitoring support as an architecture constraint, not a current feature. The system should be designed so a later service can watch Meridian-owned canonical files instead of reverse-engineering harness-native output.

### Decision 5

Adopt an aggressive deletion rule for this refactor: once a canonical replacement exists, delete the old heuristic parser, compatibility alias, and duplicate read path immediately.

## Expected Outcome

If this design is followed, Meridian will gain:

- a clean observability surface for spawns
- adapter-owned harness parsing
- less duplicated parsing logic
- a safer path for future session viewing and monitoring

Most importantly, it avoids locking the project into raw-log heuristics as a de facto public interface.
