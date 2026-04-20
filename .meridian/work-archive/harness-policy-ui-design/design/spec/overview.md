# Behavioral Specification Overview

## Scope

This specification defines the harness-agnostic policy model for Meridian, enabling:
- Dynamic harness/provider/model switching in a future UI
- Consistent semantics for `meridian spawn` and Meridian app
- Extensibility to new harnesses without changing the policy layer

## Documents

| Document | Purpose |
|----------|---------|
| `policy-model.md` | EARS statements defining required system behavior |

## Core Concepts

### Three Policy Layers

1. **RunPolicy** — Frozen at spawn creation. Harness, model, permissions, timeout.
2. **SessionPolicy** — Mutable during session. Instructions, skills, session mode.
3. **TurnIntent** — Ephemeral per turn. User message, steer directive, injected context.

### Instruction Stack

Five ordered layers for system prompt composition:
1. Base system prompt (harness-owned, opaque)
2. Agent instructions
3. Skill instructions
4. Session instructions
5. Turn instructions

Layers 2-5 are Meridian-controlled and projected via harness-appropriate channels.

### Projection Modes

How instructions reach the model:
- `append_system_prompt` — Separate system prompt channel (Claude)
- `inline_prompt` — Composed into user message (OpenCode subprocess, Codex)
- `session_context` — Set at session creation (OpenCode HTTP)

### Capability Manifest

Per-harness declaration of:
- What features are available
- At what scope (run/session/turn)
- What degradation paths exist for unsupported features

## Key Requirements Summary

| ID | Summary |
|----|---------|
| UBIQ-POL-001 | RunPolicy structure definition |
| UBIQ-POL-010 | SessionPolicy structure definition |
| UBIQ-POL-020 | TurnIntent structure definition |
| UBIQ-INSTR-001 | Instruction stack layer model |
| UBIQ-INSTR-010 | Three instruction projection modes |
| UBIQ-CAP-001 | CapabilityManifest structure |
| UBIQ-PROJ-001 | HarnessProjector contract |
| UBIQ-SHARED-001 | Shared types for spawn and app |

## Cross-References

- Architecture: `../architecture/policy-architecture.md`
- Refactor agenda: `../refactors.md`
- Feasibility: `../feasibility.md`
