# Architecture Overview

## Purpose

This document provides a high-level view of the policy architecture for Meridian's cross-harness UI support. For detailed type definitions and flow diagrams, see `policy-architecture.md`.

---

## Design Goals

1. **Harness-agnostic intent**: Express user intent once; project it to any harness.
2. **Consistent semantics**: Same policy types for `meridian spawn` and Meridian app.
3. **Extensible to new harnesses**: Adding a harness = new projector + capability manifest.
4. **Clear capability boundaries**: UI knows what's possible before user attempts it.
5. **Graceful degradation**: Handle unsupported features without hard failure.

---

## Key Abstractions

### Policy Layer (`meridian/lib/policy/`)

| Type | Scope | Mutability | Purpose |
|------|-------|------------|---------|
| `RunPolicy` | Launch | Frozen | Harness, model, permissions, timeout |
| `SessionPolicy` | Session | Mutable | Instructions, skills, session mode |
| `TurnIntent` | Turn | Ephemeral | User message, steer, context |
| `InstructionStack` | Session | Mutable | Five-layer instruction composition |

### Projection Layer (`meridian/lib/harness/projectors/`)

| Component | Purpose |
|-----------|---------|
| `HarnessProjector` | Protocol: policy → harness request |
| `ClaudeProjector` | Claude-specific projection |
| `OpenCodeProjector` | OpenCode projection (subprocess + HTTP variants) |
| `CodexProjector` | Codex-specific projection |
| `CapabilityManifest` | Per-harness capability advertising |

### Transport Layer (existing `meridian/lib/harness/connections/`)

Unchanged. Projectors emit harness requests; connections execute them.

---

## Instruction Composition

The instruction stack is the core mechanism for cross-harness system prompt handling.

### Stack Structure

```
Layer 5: Turn instructions (ephemeral, per-turn context)
Layer 4: Session instructions (session-level additions)
Layer 3: Skill instructions (from active skills)
Layer 2: Agent instructions (from agent profile)
Layer 1: Base system prompt (harness-owned, opaque)
```

### Projection by Harness

| Harness | Transport | Mode | Layers Projected |
|---------|-----------|------|------------------|
| Claude | subprocess | `append_system_prompt` | 2-5 via `--append-system-prompt` |
| Claude | websocket | `append_system_prompt` | 2-5 via streaming protocol |
| OpenCode | subprocess | `inline_prompt` | 2-5 inline in prompt body |
| OpenCode | HTTP | `inline_prompt` or `session_context` | 2-5 inline or via session payload |
| Codex | subprocess | `inline_prompt` | 2-5 inline in prompt body |
| Codex | websocket | `inline_prompt` | 2-5 inline in prompt body |

---

## Capability Model

Each harness projector exposes a `CapabilityManifest`:

```yaml
harness_id: opencode
transport: http

capabilities:
  model_selection: run
  permission_policy: unsupported
  timeout: run
  mcp_servers: run
  instruction_append: session
  skill_activation: session
  session_resume: session
  session_fork: unsupported
  mcp_tool_selection: session
  steer_directive: unsupported
  effort_override: unsupported
  runtime_model_switch: unsupported

degradation_paths:
  steer_directive: inline_in_user_message
  effort_override: drop_silently
```

### Scope Definitions

- **run**: Fixed at spawn creation; cannot change during execution
- **session**: Configurable per-session; persists across turns
- **turn**: Configurable per-turn; does not persist
- **unsupported**: Not available; check `degradation_paths` for fallback

---

## Session Mode Semantics

| Mode | Instruction Injection | Conversation History |
|------|----------------------|----------------------|
| `fresh` | Full stack (layers 2-5) | Empty |
| `resume` | Suppressed (harness rehydrates) | From source session |
| `fork` | Context-delta only | From source session + new branch |

### Resume Behavior

On resume, the harness reloads the original session including its instruction context. Meridian does not re-inject instructions — doing so would duplicate or conflict with the original.

### Fork Behavior

Fork creates a new conversation branch. If agent/skills have changed since the source session, Meridian injects a context update. Otherwise, only the new prompt is sent.

---

## Cross-Harness Switching

When the user switches harness or model in the UI:

1. Current session is considered the "source session"
2. New session is created with `session_mode: fork`
3. Conversation context is carried forward (last N turns or summary)
4. New harness projector generates the request

This is the only feasible path — no harness supports runtime harness switching.

---

## Integration Points

### For `meridian spawn`

1. Construct `RunPolicy` from CLI flags, profile, config
2. Construct `SessionPolicy` from session flags and skills
3. Construct `TurnIntent` from prompt and context files
4. Select projector based on harness ID
5. Project to harness request
6. Execute via existing subprocess/streaming path

### For Meridian App

1. Construct `RunPolicy` at session start
2. Maintain `SessionPolicy` as mutable state
3. Construct `TurnIntent` per user input
4. Query `CapabilityManifest` to enable/disable UI controls
5. Project and send via connection
6. Handle events from connection

---

## Module Layout

```
meridian/lib/
├── policy/
│   ├── __init__.py
│   ├── run_policy.py
│   ├── session_policy.py
│   ├── turn_intent.py
│   ├── instruction_stack.py
│   └── capability_manifest.py
├── harness/
│   ├── projectors/
│   │   ├── __init__.py
│   │   ├── base.py           # HarnessProjector protocol
│   │   ├── claude.py
│   │   ├── opencode_subprocess.py
│   │   ├── opencode_http.py
│   │   └── codex.py
│   └── ... (existing adapter/connection code)
```

---

## Documents in This Package

| Document | Purpose |
|----------|---------|
| `spec/overview.md` | Specification summary |
| `spec/policy-model.md` | EARS behavioral requirements |
| `architecture/overview.md` | This document |
| `architecture/policy-architecture.md` | Detailed types and flows |
| `refactors.md` | Structural changes needed |
| `feasibility.md` | Probes and validated assumptions |
| `../decisions.md` | Design decision log |
