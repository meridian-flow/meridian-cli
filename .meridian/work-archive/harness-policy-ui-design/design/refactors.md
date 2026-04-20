# Refactor Agenda

This document lists structural rearrangements that should be sequenced early when they unlock safe parallel implementation of the policy model.

---

## REF-001: Extract policy types from SpawnParams

**Current state**: `SpawnParams` conflates run-scoped, session-scoped, and turn-scoped fields in a single flat struct.

**Target state**: Three distinct types (`RunPolicy`, `SessionPolicy`, `TurnIntent`) defined in `meridian/lib/policy/`, with `SpawnParams` remaining as a transport-layer struct that projectors produce.

**Why this unlocks parallelism**: New policy-layer work can proceed without touching the existing launch/transport path. Projectors can be implemented incrementally per-harness.

**Sequencing**: This should be the first refactor. No behavioral changes, only type extraction and mapping.

---

## REF-002: Split HarnessCapabilities into CapabilityManifest

**Current state**: `HarnessCapabilities` is a flat struct of boolean feature flags. It doesn't express:
- Scope (run vs session vs turn)
- Degradation paths
- Transport-specific variations

**Target state**: `CapabilityManifest` replaces `HarnessCapabilities` with a richer structure:
- `capabilities: dict[str, CapabilityScope]`
- `degradation_paths: dict[str, str]`
- Transport identifier

**Why this unlocks parallelism**: UI work can query capabilities without knowing harness internals. Projectors can implement degradation independently.

**Sequencing**: After REF-001. Can proceed in parallel with REF-003.

---

## REF-003: Introduce HarnessProjector protocol

**Current state**: `HarnessAdapter.resolve_launch_spec()` takes `SpawnParams` and produces a harness-specific launch spec. The adapter owns both capability knowledge and projection logic.

**Target state**: `HarnessProjector` is a separate protocol that:
- Takes `(RunPolicy, SessionPolicy, TurnIntent)`
- Produces `HarnessRequest` (existing `*LaunchSpec` types)
- Exposes `capabilities() -> CapabilityManifest`
- Implements `degrade_intent()` for graceful fallback

**Why this unlocks parallelism**: The projection contract is stable; individual harness projectors can be implemented independently.

**Sequencing**: After REF-001. Can proceed in parallel with REF-002.

---

## REF-004: Extract InstructionStack composition logic

**Current state**: Instruction composition is scattered:
- Claude: `--append-system-prompt` handling in `project_claude.py`
- OpenCode: inline composition in `project_opencode_streaming.py`
- Codex: inline composition in `project_codex.py`

**Target state**: `InstructionStack.compose(mode: InstructionProjectionMode) -> str` centralizes composition. Each projector selects the mode; the stack composes the output.

**Why this unlocks parallelism**: Instruction composition changes (e.g., adding new layers, changing format) don't touch projector code.

**Sequencing**: Can proceed in parallel with REF-002/REF-003 after REF-001 defines the types.

---

## REF-005: Consolidate session mode handling

**Current state**: Session resume/fork logic is handled differently per adapter:
- `continue_harness_session_id` and `continue_fork` fields in `SpawnParams`
- `seed_session()` and `filter_launch_content()` adapter methods
- Streaming path has different capabilities than subprocess path

**Target state**: `SessionPolicy.session_mode` enum (`fresh | resume | fork`) with `source_session_id`. Projectors interpret the mode; adapters don't decide session semantics.

**Why this unlocks parallelism**: Session mode logic is policy, not mechanism. Moving it to policy layer lets the UI control session mode without harness-specific code.

**Sequencing**: After REF-001 and REF-003. This is the integration point.

---

## REF-006: Transport-specific projector variants

**Current state**: OpenCode has separate subprocess and HTTP paths with different capabilities. The adapter chooses transport internally.

**Target state**: Explicit transport variants:
- `OpenCodeSubprocessProjector`
- `OpenCodeHttpProjector`

Each declares its own `CapabilityManifest`. The launch layer or app selects the appropriate projector based on context.

**Why this unlocks parallelism**: HTTP projector can evolve independently of subprocess projector. Capability differences are explicit rather than buried in conditionals.

**Sequencing**: After REF-003. Can proceed in parallel with OpenCode parity work.

---

## Refactor Dependency Graph

```
REF-001 (extract policy types)
   │
   ├──────────────────────────────────┐
   │                                  │
   ▼                                  ▼
REF-002 (CapabilityManifest)      REF-003 (HarnessProjector)
   │                                  │
   └──────────────┬───────────────────┘
                  │
                  ▼
            REF-004 (InstructionStack)
                  │
                  ▼
            REF-005 (session mode)
                  │
                  ▼
            REF-006 (transport variants)
```

---

## Estimated Effort

| Refactor | Size | Risk | Dependencies |
|----------|------|------|--------------|
| REF-001 | M | Low | None |
| REF-002 | S | Low | REF-001 |
| REF-003 | M | Medium | REF-001 |
| REF-004 | S | Low | REF-001 |
| REF-005 | M | Medium | REF-001, REF-003 |
| REF-006 | M | Medium | REF-003 |

M = Medium (1-2 days), S = Small (< 1 day)

---

## Non-Refactor Prerequisites

- Probe OpenCode HTTP API for session creation payload schema (feasibility item)
- Confirm OpenCode streaming accepts `agent` or `system` fields (feasibility item)
- Validate Claude `--append-system-prompt` behavior on resume (assumption to verify)
