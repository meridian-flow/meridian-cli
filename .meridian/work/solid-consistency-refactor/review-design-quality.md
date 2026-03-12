# Design Review: SOLID & Consistency Refactor

I compared the proposed 12-phase refactor against the current implementation in:

- `src/meridian/lib/harness/adapter.py`
- `src/meridian/lib/harness/direct.py`
- `src/meridian/lib/harness/registry.py`
- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/state/session_store.py`
- `src/meridian/lib/core/spawn_lifecycle.py`
- `src/meridian/lib/ops/runtime.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/extract.py`
- `src/meridian/lib/launch/env.py`
- `src/meridian/lib/launch/session_ids.py`
- `src/meridian/lib/state/reaper.py`
- `src/meridian/cli/main.py`

The design is strongest in Phases 2, 4, 5, 8, 9, 10, and 12. The main design risks are Phase 7, Phase 11, and the proposed placement/scope of `SessionScope`.

## Findings

### 1. Phase 7 only partially fixes ISP/LSP

The current problem is real: `HarnessAdapter` is too broad, and `DirectAdapter` clearly proves it by implementing fake subprocess-oriented methods. Splitting the protocol is the right direction.

The proposed split is still not clean enough:

- `StreamParsingHarness` mixes two different responsibilities:
  - streaming concerns: `parse_stream_event`
  - artifact/finalization concerns: `extract_usage`, `extract_report`, `extract_session_id`
- Those extraction methods are used by finalization and session-observation code, not by stream parsing. Current consumers in `launch/extract.py`, `launch/report.py`, and `launch/session_ids.py` do not conceptually need a "stream parsing" interface.
- `SessionAwareHarness` also mixes distinct concerns:
  - session seeding/detection
  - launch content filtering, which is really prompt/launch policy

This means the design still groups methods by where they happen to live today, not by stable reasons to change.

Recommendation:

- Split along behavior boundaries instead:
  - `SubprocessLaunchHarness`
  - `ArtifactExtractingHarness`
  - `PrimarySessionDetectingHarness`
  - `LaunchContentHarness`
  - `InProcessHarness`
- Keep `HarnessIdentity` and capability metadata if needed for UX, but do not make the booleans compete with the protocols as the source of truth.

Result: `DirectAdapter` can then implement only `InProcessHarness`, and subprocess adapters can implement the smaller interfaces they actually support.

### 2. Phase 11 overstates how much a new spawn state becomes "one edit"

Centralizing transition rules is a good idea. The current code still spreads status checks across `spawn_store.py`, `reaper.py`, `api.py`, and CLI filtering. That is worth improving.

The proposed state-machine story is too strong:

- Adding a new state still requires changing `SpawnStatus` in `core/domain.py`.
- CLI presets and validation in `cli/spawn.py` still need explicit policy updates.
- Reaper behavior in `state/reaper.py` still depends on state semantics, not just transition legality.
- Output shaping and stats code still need to decide where the new state belongs.

So this refactor localizes transition validation, but it does not make state expansion open/closed in the strong sense claimed by the doc.

There is also a correctness issue in the proposed integration:

- `validate_transition(record.status, "running")` must happen under the same lock as the append.
- If validation happens on a previously-read record outside the append lock, it is advisory only and races with concurrent writers.

Recommendation:

- Keep Phase 11 focused on:
  - one authoritative transition table
  - one authoritative active/terminal classification
  - validation inside the locked store mutation path
- Do not try to eliminate every string comparison via wrapper predicates. That is mostly churn and does not remove the need for explicit policy tables in CLI and reaper code.

### 3. `SessionScope` is useful, but it is placed too low and owns too much policy

There is real duplication today between `ops/spawn/execute.py` and `launch/process.py`:

- `start_session`
- auto-create work item
- `stop_session`
- materialization cleanup nearby in both paths

Extracting shared lifecycle code is reasonable. The problem is the proposed location and responsibility boundary.

Why it is too broad in `state/session_scope.py`:

- It imports `work_store` and auto-creates work items.
- That is workflow policy, not state-storage mechanism.
- The project philosophy explicitly separates mechanism from policy. Putting auto-work creation in the state layer cuts against that.

Why the module becomes muddled:

- The same phase also proposes `cleanup_materialized_resources(...)` in the same module.
- Materialized harness resources are not a session-store concern.

My read is:

- `SessionScope` is not too narrow.
- It is slightly too broad if it owns both session lifetime and "ensure there is a work item".
- It definitely lives in the wrong layer if it sits under `state/`.

Recommendation:

- Keep `session_store` primitive.
- Move the orchestration helper to `launch/` or `ops/`.
- Split responsibilities:
  - `session_scope(...)` for start/stop lifetime only
  - `ensure_session_work_item(...)` as a separate policy helper
  - materialization cleanup stays near harness materialization helpers, not in session scope

### 4. Phase 8 reduces duplication but does not fully solve OCP for new CLI groups

`register_cli_group()` is a good cleanup. The repeated registration loops are real duplication today.

But for the specific question "how easy is it to add a new CLI command group?":

- The answer is still: add a module, add a sub-app, and edit `cli/main.py`.
- The design improves adding commands inside an existing group much more than adding an entirely new group.

That is acceptable if centralized CLI composition is intentional. It is not truly open/closed for group addition.

Recommendation:

- Either describe Phase 8 honestly as boilerplate removal for existing groups, or
- go one step further and make group registration manifest-driven from `cli/main.py` as well

### 5. Phase 1 and Phase 4 conflict on `resolve_state_root()`

Phase 1 says to delete `resolve_state_root()` from `ops/runtime.py` as dead code.
Phase 4 then proposes `resolve_state_root()` in `ops/runtime.py` as the shared abstraction for duplicated helpers.

This is a design inconsistency, not a code bug, but it matters because it suggests the boundary is not fully settled.

Recommendation:

- Decide first whether `ops/runtime.py` is the home for repo/state resolution helpers.
- If yes, keep the helper and standardize on it.
- If no, remove it and use `resolve_state_paths()` directly.
- Do not delete and then reintroduce the same abstraction in adjacent phases.

## Evaluation By Topic

### Single Responsibility

`event_store` is the right granularity if it stays narrow:

- append under lock
- crash-tolerant read
- parser callback dispatch

That has one stable reason to change: JSONL event-store mechanics.

It should not absorb:

- domain event folding
- ID generation
- session lifetime locks
- store-specific queries

`SessionScope` is the opposite case:

- start/stop lifetime is one responsibility
- auto-work creation is another
- materialization cleanup is a third

Keep the first, split the rest.

### Open/Closed

Adding a new harness type:

- Better than today if Phase 7 is refined as above.
- Not fully solved if extraction/session methods remain bundled in the wrong interfaces.

Adding a new spawn state:

- Better validation story.
- Still not "one edit"; state semantics will continue to affect CLI, reconciliation, and output policy.

Adding a new CLI command group:

- Still requires editing `cli/main.py` under the current proposal.

Adding a new JSONL event store:

- This is where the design is strongest.
- Phase 2 cleanly supports extend-with-data rather than copy-paste another store.

### Liskov Substitution

`DirectAdapter` can implement only `InProcessHarness` without breaking the design only if every call site is retargeted to the narrow interface it actually needs.

Today that is not true:

- finalization helpers expect extraction methods
- env builders expect subprocess-launch behavior
- session observers expect detection methods
- registry lookups still return one broad adapter type

So LSP is achievable, but only if the migration is thorough. The protocols themselves need to reflect actual substitutability, not just current module boundaries.

### Interface Segregation

Good intent, imperfect split:

- `SubprocessHarness`: good
- `InProcessHarness`: good
- `StreamParsingHarness`: too broad/misnamed
- `SessionAwareHarness`: still broad and somewhat vague

The cleanest split is by launch, extraction, and session-detection concerns.

### Dependency Inversion

Phase 2 is a good DIP move:

- the shared reader depends on a `parse_event` callback rather than concrete event types

Phase 7 also moves in the right direction if the interfaces are tightened.

The main DIP regression risk is `SessionScope` in `state/` depending on `work_store`, which would make the lower-level state layer depend on higher-level workflow policy.

### Naming

Mostly good, with a few exceptions:

- `StreamParsingHarness` is misleading if it also owns artifact extraction.
- `SessionAwareHarness` is vague for an interface that also filters launch content.
- `JSONLEventStore` is a good conceptual name, but the design example actually shows a functional module (`append_event`, `read_events`, `lock_file`) rather than a store object.

Given the current codebase style, a functional module name like `jsonl_events.py` or `event_store.py` is fine. Just do not describe it as a class-based store if that is not the real design.

### Simplicity

Phases 2, 4, 5, 8, 9, 10, and 12 are mostly straightforward and worthwhile.

Phase 11 is the most likely to over-engineer:

- `SpawnTransition` enum
- `_ALLOWED_TRANSITIONS`
- many small predicate helpers
- mass replacement of direct status comparisons

That is probably more machinery than needed for five states.

A simpler version would be:

- keep `SpawnStatus`
- add one transition table
- add one active/terminal classification
- validate transitions inside store mutations
- keep explicit policy tables where UI/reaper behavior genuinely differs

## Bottom Line

The refactor direction is good, and the design correctly identifies the highest-value consistency problems in the current codebase:

- duplicated JSONL store mechanics
- duplicated session lifecycle orchestration
- monolithic harness adapter surface
- duplicated CLI registration

I would approve the plan with three changes before implementation:

1. Redesign Phase 7 around launch/extraction/session-detection interfaces instead of the current `StreamParsingHarness` and `SessionAwareHarness` grouping.
2. Narrow and relocate `SessionScope` so the state layer stays mechanism-only.
3. Scale back Phase 11 to a locked transition table plus shared status classification, rather than trying to route all status reasoning through wrappers.

With those changes, the refactor should age well. Without them, it will still improve the codebase, but it risks replacing obvious duplication with subtler abstraction drift.
