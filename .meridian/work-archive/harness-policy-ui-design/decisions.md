# Decisions

## 2026-04-17

### Decision: Three-layer policy model (Run / Session / Turn)

**What**: Separate policy into `RunPolicy` (frozen at launch), `SessionPolicy` (mutable per session), and `TurnIntent` (ephemeral per turn).

**Why**: 
- Maps cleanly to harness capability scopes (run-scoped vs session-scoped vs turn-scoped)
- Enables the UI to mutate session policy without requiring a new spawn
- Keeps turn-level concerns (steer, effort override) isolated from session state
- Matches mental model of "start a run, have a session, send turns"

**Alternatives considered**:
- Single flat `SpawnParams` extended for UI use
  - Rejected: conflates immutable and mutable fields, doesn't model scope
- Two layers (Run + Turn) with no explicit Session
  - Rejected: loses the ability to express session-scoped changes like skill refresh

---

### Decision: InstructionStack with five ordered layers

**What**: Model system instructions as five layers: base (harness), agent, skill, session, turn.

**Why**:
- Makes instruction composition explicit and testable
- Separates harness-controlled (layer 1) from Meridian-controlled (layers 2-5)
- Enables different projection modes without changing the stack model
- Allows future layers (e.g., tool instructions) without restructuring

**Alternatives considered**:
- Flat string concatenation
  - Rejected: loses structure, hard to debug composition issues
- Two layers (system + user)
  - Rejected: doesn't distinguish agent from skill from session instructions

---

### Decision: Three instruction projection modes

**What**: `append_system_prompt`, `inline_prompt`, `session_context`

**Why**:
- Claude supports separate system prompt channel via `--append-system-prompt`
- OpenCode subprocess doesn't have a system prompt flag; must inline
- OpenCode HTTP may support session-level fields; worth probing
- Codex inlines; may gain append support in future

**Alternatives considered**:
- Single projection mode (always inline)
  - Rejected: loses Claude's cleaner separation of system vs user content
- Harness-specific ad-hoc projection
  - Rejected: duplicates composition logic across projectors

---

### Decision: CapabilityManifest as capability → scope mapping

**What**: Replace `HarnessCapabilities` boolean flags with `CapabilityManifest` that maps capability names to scopes (run/session/turn/unsupported) plus degradation paths.

**Why**:
- Boolean flags don't express scope
- Degradation paths enable graceful fallback without harness-specific conditionals
- UI can query the manifest to show/hide controls
- Adding capabilities doesn't require adding new boolean fields

**Alternatives considered**:
- Extend `HarnessCapabilities` with scope annotations
  - Rejected: growing boolean struct, mixes concerns
- No capability model; let projectors fail with errors
  - Rejected: poor UX, no way for UI to adapt before user attempts an action

---

### Decision: Projectors separate from adapters

**What**: `HarnessProjector` is a distinct protocol from `HarnessAdapter`. Projectors take policy objects and emit harness requests. Adapters own extraction, session detection, and other harness-specific mechanisms.

**Why**:
- Policy → request translation is logically distinct from result extraction
- Projectors are consumed by both spawn and app; adapters are spawn-specific
- Enables transport-specific projector variants (subprocess vs HTTP)
- Reduces coupling between policy layer and transport layer

**Alternatives considered**:
- Extend `HarnessAdapter.resolve_launch_spec()` to take policy objects
  - Rejected: adapter contract would grow to serve two consumers
- Embed projection in transport connections
  - Rejected: mixes concerns, duplicates projection logic

---

### Decision: OpenCode HTTP — inline instructions in first user message

**What**: For OpenCode HTTP (streaming), compose Meridian instructions inline in the first user message rather than attempting to inject via a system prompt channel.

**Why**:
- OpenCode's base prompt is provider-specific and not appendable from outside
- The HTTP session endpoint may accept `agent` but it's unclear if it accepts arbitrary system content
- Inlining is proven to work (subprocess path already does this)
- Preserves provider/model switching flexibility — Meridian doesn't assume provider prompt structure

**Alternatives considered**:
- Probe for OpenCode system field and use if available
  - Deferred: PROBE-001 will determine if this is viable
  - If viable, `session_context` mode can be added later
- Skip instructions on OpenCode streaming
  - Rejected: agents/skills wouldn't work

---

### Decision: Graceful degradation with optional strict mode

**What**: When projecting an intent that requires an unsupported capability, apply a degradation path (e.g., inline steer directive) by default. Strict mode raises `UnsupportedCapabilityError` instead.

**Why**:
- Most users want the action to proceed even if degraded
- Power users (or CI) may want strict validation to catch configuration errors
- Degradation paths are documented in the capability manifest, making behavior predictable

**Alternatives considered**:
- Always fail on unsupported capability
  - Rejected: too strict for interactive use
- Always degrade silently
  - Rejected: strict mode is valuable for testing and automation

---

### Decision: Session fork as the model for harness/model switching in UI

**What**: When the user switches harness or model mid-session in the UI, create a new session with `session_mode: fork` and carry conversation context.

**Why**:
- A session is tied to one harness and one model at creation time
- "Switching" is actually "forking to a new session on the new harness/model"
- Conversation context can be carried forward as injected context or summary
- This is the only feasible path — runtime harness switching is not possible

**Alternatives considered**:
- Runtime model switching within a session
  - Rejected: no harness supports this; `CAPABILITY_RUNTIME_MODEL_SWITCH` is universally unsupported
- Start a completely fresh session on switch
  - Rejected: loses conversation context, poor UX

---

### Decision: Persist RunPolicy as spawn metadata

**What**: When a spawn completes, persist `RunPolicy` alongside the spawn record. `SessionPolicy` can be reconstructed from session state.

**Why**:
- Enables "clone this spawn" without re-specifying parameters
- Enables "fork from spawn" with modified parameters
- `RunPolicy` is frozen and small; cheap to persist
- Complements existing spawn artifacts (report, usage, session ID)

**Alternatives considered**:
- Persist full `SessionPolicy` as well
  - Deferred: session state already captures most of this; unclear if explicit persistence adds value
- Don't persist policy; require re-specification on clone/fork
  - Rejected: poor UX for a common operation

---

## Open Decisions (Pending Probe Results)

### Pending: OpenCode HTTP instruction channel

**Depends on**: PROBE-001 (OpenCode system field)

If OpenCode HTTP accepts a `system` field, consider using `InstructionProjectionMode.SESSION_CONTEXT` instead of `INLINE_PROMPT`. Decision deferred until probe completes.

---

### Pending: OpenCode fork capability

**Depends on**: PROBE-002 (OpenCode fork semantics)

If OpenCode HTTP has a fork API, mark `CAPABILITY_SESSION_FORK` as supported for that transport. If not, leave as unsupported and handle fork as "new session with context."

---

### Pending: Claude instruction persistence on resume

**Depends on**: PROBE-003 (Claude resume + append-system-prompt)

Affects whether `SessionPolicy.active_skills` changes can take effect on resume. Decision on skill refresh semantics deferred until probe completes.

---

## 2026-04-19 — Design Pivot: Thin Passthrough Model

### Decision: Kill the policy abstraction layer

**What**: Abandon RunPolicy/SessionPolicy/TurnIntent, InstructionStack, HarnessProjector, and complex CapabilityManifest. Replace with thin command passthrough.

**Why**:
- Harnesses already have rich slash command interfaces (`/model`, `/compact`, `/skill-name`, etc.)
- Slash commands are just user messages — Meridian can send them directly
- Building an abstraction layer over this is unnecessary complexity
- Skills are harness-native, not Meridian-injected content

**What we're keeping**:
- HarnessConnection (still need to talk to harnesses)
- Launch-time config (model, agent, effort at spawn creation)
- AG-UI mapper (translate events for UI rendering)

**What we're killing**:
- RunPolicy / SessionPolicy / TurnIntent types
- InstructionStack (5 layers)
- HarnessProjector abstraction
- Projection modes (append_system_prompt, inline_prompt, session_context)
- Complex CapabilityManifest with scope mapping

---

### Decision: Cross-harness switching = view past + start fresh

**What**: When switching harnesses, don't try to carry conversation context. Show past session as read-only, start fresh on new harness.

**Why**:
- Session formats are harness-specific and incompatible
- Context carrying would require N×N conversion paths
- Maintenance nightmare as harnesses evolve
- Users have context in their head / on screen — don't need programmatic transfer

**Alternatives rejected**:
- Fork with context summary → still requires format translation
- Fork with full transcript → formats don't match
- Abstract session format → massive scope creep

---

### Decision: Intra-harness changes via native slash commands

**What**: Model switching, effort changes, skill activation, compact — all via harness slash commands.

**How it works**:
- User clicks "Switch to Opus" → UI sends `/model opus` to harness
- User clicks "Compact" → UI sends `/compact` to harness
- User activates skill → UI sends `/skill-name` to harness

**Why**:
- Harnesses already implement this
- No abstraction needed
- UI just needs to know what commands each harness supports

---

### Decision: Simple capability model (command list, not scope mapping)

**What**: Replace CapabilityManifest with simple `HarnessCommands` that lists supported slash commands and launch flags.

**Why**:
- Don't need scope (run/session/turn) — harness handles that
- Don't need degradation paths — if command not supported, don't show the button
- Simple list is sufficient for UI to show/hide controls

---

## Superseded Decisions

The following decisions from 2026-04-17 are superseded by this pivot:

- ~~Three-layer policy model~~ → No policy layers
- ~~InstructionStack with five layers~~ → No instruction injection
- ~~Three instruction projection modes~~ → No projection
- ~~CapabilityManifest as capability → scope mapping~~ → Simple command list
- ~~Projectors separate from adapters~~ → No projectors
- ~~Session fork for harness/model switching~~ → Fresh start for harness, slash command for model
