# Policy Model Behavioral Specification

## Overview

This specification defines how Meridian expresses user and system intent as structured policy objects, independent of which harness executes the work. The policy model must support both `meridian spawn` (CLI-driven coordination) and a future Meridian UI (interactive session management with dynamic harness/model switching).

---

## EARS Notation Reference

- **[UBIQ-xxx]** — Ubiquitous requirement; always true.
- **[EVENT-xxx]** — Event-driven; when X occurs, the system shall Y.
- **[STATE-xxx]** — State-dependent; while X, the system shall Y.
- **[OPTION-xxx]** — Optional feature; where X is configured, the system shall Y.
- **[UNWANTED-xxx]** — Exception; if X occurs, the system shall Y.

---

## Policy Layers

Meridian policy is organized into three hierarchical layers:

### RunPolicy (launch-scoped)

Fixed at spawn creation; cannot change during the run.

**[UBIQ-POL-001]** The system shall express run-scoped intent through a `RunPolicy` structure containing:
- `harness_id`: which harness executes this run
- `model_id`: which model to request
- `provider_id`: optional explicit provider (may be inferred from model)
- `agent_profile`: optional agent profile name
- `effort_level`: optional reasoning effort hint
- `permission_policy`: sandbox/approval configuration
- `timeout_seconds`: optional runtime limit
- `mcp_servers`: list of MCP server references
- `reference_files`: list of file paths to include as context

**[UBIQ-POL-002]** The system shall treat all fields in `RunPolicy` as immutable after spawn creation.

**[UBIQ-POL-003]** The system shall support `RunPolicy` construction from:
- Explicit CLI flags (`-m`, `-a`, `--approval`, etc.)
- Agent profile YAML
- Project/user configuration
with precedence: CLI > profile > project > user > harness defaults.

### SessionPolicy (session-scoped)

Mutable during the session lifecycle; persists across turns.

**[UBIQ-POL-010]** The system shall express session-scoped intent through a `SessionPolicy` structure containing:
- `system_instructions`: structured instruction layers (see INSTR-xxx)
- `session_mode`: fresh | resume | fork
- `source_session_id`: when resuming or forking, the source session
- `conversation_context`: optional prior turns or summary
- `active_skills`: list of skill identifiers active for this session
- `mcp_tool_selection`: per-session tool enablement

**[UBIQ-POL-011]** When session mode is `resume`, the system shall pass the source session ID to the harness and suppress fresh prompt/instruction injection where the harness would rehydrate context.

**[UBIQ-POL-012]** When session mode is `fork`, the system shall:
- Pass the source session ID to the harness
- Signal fork intent to the harness
- Allow fresh prompt/instruction injection (fork creates a new conversation branch)

**[OPTION-POL-013]** Where the UI enables mid-session model switching, the system shall:
- Create a new harness session with session mode `fork`
- Carry forward conversation context from the source session
- Project the switch as a fresh turn on the new model

### TurnIntent (turn-scoped)

Ephemeral intent for a single user turn.

**[UBIQ-POL-020]** The system shall express turn-scoped intent through a `TurnIntent` structure containing:
- `user_message`: the primary prompt text
- `injected_context`: optional turn-specific context (reference files, tool outputs)
- `steer_directive`: optional steering instruction for this turn only
- `reasoning_effort_override`: optional per-turn effort adjustment
- `response_constraints`: optional output format or length hints

**[UBIQ-POL-021]** The system shall treat `TurnIntent` as ephemeral; it does not persist to `SessionPolicy` or affect future turns.

**[EVENT-POL-022]** When a turn intent includes a steer directive and the harness supports steering, the system shall inject the directive through the harness steering channel.

**[UNWANTED-POL-023]** If a turn intent includes a steer directive and the harness does not support steering, the system shall either:
- Compose the directive into the user message (graceful degradation)
- Return an `UnsupportedCapability` error (strict mode)
based on the configured fallback policy.

---

## System Instructions

### Instruction Layering

**[UBIQ-INSTR-001]** The system shall model system instructions as an ordered stack of layers:
1. `base_system_prompt`: harness/provider-owned base prompt (may be opaque)
2. `agent_instructions`: from agent profile system prompt
3. `skill_instructions`: from active skill content
4. `session_instructions`: session-level appended instructions
5. `turn_instructions`: turn-level injected context

**[UBIQ-INSTR-002]** The system shall treat layer 1 (base_system_prompt) as harness-controlled; Meridian does not write to it but may need to know its existence.

**[UBIQ-INSTR-003]** Layers 2–5 are Meridian-controlled and shall be composed into a single projection for harness consumption.

### Projection Modes

Different harnesses accept instructions through different channels:

**[UBIQ-INSTR-010]** The system shall support three instruction projection modes:
- `append_system_prompt`: harness accepts a separate system prompt channel (Claude `--append-system-prompt`)
- `inline_prompt`: instructions are composed into the user prompt body (OpenCode, Codex)
- `session_context`: instructions are set at session creation (OpenCode HTTP API `agent` or `system` field)

**[UBIQ-INSTR-011]** The system shall declare each harness's supported projection mode(s) in its capability manifest.

**[EVENT-INSTR-012]** When projecting instructions, the system shall select the projection mode based on:
1. Harness capability (what modes are available)
2. Session mode (resume may suppress projection)
3. Transport (subprocess vs streaming may have different channels)

### Cross-Harness Instruction Semantics

**[UBIQ-INSTR-020]** The system shall not assume identical instruction semantics across harnesses. Specifically:
- Claude's `--append-system-prompt` injects after the base system prompt
- OpenCode's base prompt is provider-specific and not directly appendable
- OpenCode session API may accept `agent` or `system` fields at session creation

**[UBIQ-INSTR-021]** For OpenCode, the system shall layer Meridian instructions by:
- Composing agent/skill content inline in the prompt or session payload
- Allowing OpenCode to apply its provider-specific base prompt independently
- Not attempting to replace or modify OpenCode's base prompt

**[OPTION-INSTR-022]** Where a harness supports turn-level instruction channels, the system shall use them for `turn_instructions` rather than inlining into the user message.

---

## Capability Advertising

### Capability Manifest

**[UBIQ-CAP-001]** Each harness adapter shall expose a `CapabilityManifest` declaring:
- `run_scoped`: features fixed at launch
- `session_scoped`: features configurable per-session
- `turn_scoped`: features configurable per-turn
- `unsupported`: features not available on this harness

**[UBIQ-CAP-002]** The capability manifest shall include at minimum:
```
run_scoped:
  - model_selection
  - permission_policy
  - timeout
  - mcp_servers

session_scoped:
  - instruction_layers
  - skill_activation
  - session_mode (resume/fork)
  - mcp_tool_selection

turn_scoped:
  - user_message
  - steer_directive (optional)
  - reasoning_effort_override (optional)
  - injected_context

unsupported: (harness-specific)
```

**[UBIQ-CAP-003]** The UI/runtime shall query the capability manifest to determine what controls to expose and what operations are valid for the current harness.

### Scope Transitions

**[EVENT-CAP-010]** When the user requests a model change in the UI:
- If model change is `session_scoped`, the system shall create a new session and fork conversation context
- If model change is `run_scoped` only, the system shall surface this as a new spawn (with fork from current session)

**[EVENT-CAP-011]** When the user requests a harness change in the UI:
- The system shall surface this as a new spawn with session mode `fork`
- Conversation context carries forward; harness-specific state does not

---

## Projector Contract

### Intent to Request Translation

**[UBIQ-PROJ-001]** The system shall define a `HarnessProjector` contract that translates:
- `(RunPolicy, SessionPolicy, TurnIntent)` → harness-native request

**[UBIQ-PROJ-002]** Each harness adapter shall implement its own projector. The projector is responsible for:
- Selecting transport (subprocess, HTTP, WebSocket)
- Mapping policy fields to harness-native parameters
- Selecting instruction projection mode
- Handling capability mismatches

**[UBIQ-PROJ-003]** Projector output shall be a typed launch spec:
- `ClaudeLaunchSpec`, `OpenCodeLaunchSpec`, `CodexLaunchSpec`, etc.
- The launch spec is what the transport layer consumes

### Unsupported Intent Handling

**[EVENT-PROJ-010]** When projecting an intent that requires an unsupported capability, the projector shall:
1. Check if a graceful degradation path exists
2. If yes, apply degradation and log a warning
3. If no, raise `UnsupportedCapability` with the specific capability name

**[OPTION-PROJ-011]** Where configured for strict mode, the projector shall always raise `UnsupportedCapability` rather than degrading gracefully.

**[UBIQ-PROJ-012]** Common degradation paths:
- Steer directive → inline in user message
- Effort override → drop if harness has no effort mapping
- Turn-level instructions → inline in user message

---

## Shared Abstractions (spawn + app)

**[UBIQ-SHARED-001]** The `RunPolicy`, `SessionPolicy`, and `TurnIntent` types shall be defined in `meridian.lib.policy` and used by both:
- `meridian spawn` command construction
- Future Meridian app session management

**[UBIQ-SHARED-002]** The projector contract shall be the same for spawn and app; only the driving layer differs:
- Spawn: single-shot policy → project → execute → finalize
- App: interactive policy → project → connect → event loop → [turn] → ...

**[UBIQ-SHARED-003]** Session state persistence shall use the same event store format for spawn-initiated and app-initiated sessions, enabling cross-surface session visibility.
