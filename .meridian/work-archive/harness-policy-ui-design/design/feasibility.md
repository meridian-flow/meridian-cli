# Feasibility Notes

## Summary

The policy model design is feasible given the existing harness adapter architecture. The main risk areas are:

1. OpenCode HTTP instruction projection — the streaming path has different capabilities than subprocess
2. Session context transfer between harnesses — no existing mechanism for this
3. Capability manifest completeness — harnesses may have undocumented capabilities or limitations

---

## Validated Assumptions

### VA-001: Claude supports append-system-prompt

**Status**: Verified

**Evidence**: `project_claude.py` already uses `--append-system-prompt`. Live smoke tests confirm behavior.

**Implication**: Claude projector can use `InstructionProjectionMode.APPEND_SYSTEM_PROMPT` for instruction layers 2-5.

---

### VA-002: OpenCode subprocess accepts inline instructions

**Status**: Verified

**Evidence**: Current `project_opencode_subprocess.py` composes instructions inline in prompt. Live spawns work.

**Implication**: OpenCode subprocess projector can use `InstructionProjectionMode.INLINE_PROMPT`.

---

### VA-003: OpenCode streaming ignores effort override

**Status**: Verified

**Evidence**: `project_opencode_streaming.py` explicitly logs this:
```python
logger.debug(
    "OpenCode streaming does not support effort override; ignoring effort=%s",
    normalized_effort,
)
```

**Implication**: `CapabilityManifest` for OpenCode HTTP should mark `CAPABILITY_EFFORT_OVERRIDE` as `UNSUPPORTED` with degradation path `drop_silently`.

---

### VA-004: OpenCode streaming ignores permission resolver

**Status**: Verified

**Evidence**: `_consume_streaming_lifecycle_fields()` logs:
```python
logger.debug(
    "OpenCode streaming ignores permission resolver overrides; "
    "opencode serve has no launch-time permission mapping"
)
```

**Implication**: `CAPABILITY_PERMISSION_POLICY` is `UNSUPPORTED` for OpenCode HTTP transport.

---

### VA-005: OpenCode HTTP session creation accepts model/agent

**Status**: Verified

**Evidence**: `project_opencode_spec_to_session_payload()` emits:
```python
if spec.model is not None:
    payload["model"] = spec.model
    payload["modelID"] = spec.model

if spec.agent_name:
    payload["agent"] = spec.agent_name
```

**Implication**: OpenCode HTTP projector can set model and agent at session creation time.

---

## Probes Required

### PROBE-001: OpenCode HTTP session payload — `system` field

**Question**: Does OpenCode HTTP `/session` endpoint accept a `system` field for custom system prompt content?

**Why it matters**: If yes, the OpenCode HTTP projector could use `InstructionProjectionMode.SESSION_CONTEXT` to inject Meridian instructions at session creation, avoiding inline composition.

**Probe design**:
1. Start `opencode serve`
2. POST to `/session` with `{"model": "...", "system": "Custom instruction"}`
3. Send a message and observe if the custom system prompt affects behavior
4. Check if the session endpoint returns a schema or error indicating accepted fields

**Fallback if no**: Continue using inline composition in the first user message.

---

### PROBE-002: OpenCode HTTP fork semantics

**Question**: Can OpenCode HTTP API express fork semantics (create new session from existing session's history)?

**Why it matters**: The current streaming path cannot express `continue_fork`. If OpenCode has a fork API, we can support session forking in the UI.

**Evidence from requirements.md**:
> Whether streaming fork should move to the documented OpenCode fork API instead of session-create semantics.

**Probe design**:
1. Review OpenCode API documentation for fork endpoints
2. Test candidate endpoints: `POST /session/{id}/fork`, `POST /sessions/{id}/fork`
3. If no fork endpoint, test creating a session with `parentSessionId` or similar field

**Fallback if no**: `CAPABILITY_SESSION_FORK` is `UNSUPPORTED` for OpenCode HTTP; UI must handle fork as "new session with context summary."

---

### PROBE-003: Claude resume behavior with append-system-prompt

**Question**: On `--resume`, does Claude apply `--append-system-prompt` again, or does it skip instruction injection?

**Why it matters**: If Claude re-applies, skill updates on resume will take effect. If it skips, skills are fixed to the original session's state.

**Probe design**:
1. Start a Claude session with `--append-system-prompt "MARKER-A"`
2. Resume the session with `--append-system-prompt "MARKER-B"`
3. Ask the model what system instructions it sees
4. Verify whether MARKER-A, MARKER-B, or both are present

**Impact on design**: If Claude re-applies, `SessionPolicy.active_skills` can change on resume. If not, the policy layer should warn that skill changes won't take effect on resume.

---

### PROBE-004: OpenCode MCP tool selection at session level

**Question**: Can OpenCode HTTP session creation restrict which MCP tools are available?

**Why it matters**: `SessionPolicy.mcp_tool_selection` needs a projection path for OpenCode HTTP.

**Evidence from current code**:
```python
projected_mcp_tools = [entry.strip() for entry in spec.mcp_tools if entry.strip()]
if projected_mcp_tools:
    payload["mcp"] = {"servers": projected_mcp_tools}
```

This suggests MCP servers can be specified, but it's unclear if this restricts to a subset or declares all servers.

**Probe design**:
1. Configure multiple MCP servers in OpenCode config
2. Create session with `"mcp": {"servers": ["subset"]}`
3. Verify only the specified servers' tools are available

---

### PROBE-005: OpenCode streaming session state persistence

**Question**: Does an OpenCode HTTP session's state persist if the `opencode serve` process restarts?

**Why it matters**: For a Meridian app, if the user closes and reopens, can they resume the same session? Or must the session be recreated?

**Probe design**:
1. Start `opencode serve`, create session, send messages
2. Kill the serve process
3. Restart `opencode serve`
4. Attempt to resume the same session by ID
5. Observe if history is preserved

**Impact on design**: If sessions don't persist, the app must track conversation state externally or always start fresh sessions.

---

## Open Questions

### OQ-001: Conversation context format for cross-harness fork

When forking from OpenCode to Claude (or vice versa), what format should conversation context take?

**Options**:
1. Full transcript (may exceed context limits)
2. Summary generated by prior model (adds latency)
3. Last N turns (arbitrary cutoff)
4. System-level context injection (e.g., "You are continuing a conversation...")

**Recommendation**: Start with option 4 (system-level context injection) with option 3 (last N turns) as supplementary. Full transcript is a future enhancement if needed.

---

### OQ-002: Capability manifest discovery vs declaration

Should capability manifests be:
1. **Declared statically** in code (current direction)
2. **Discovered dynamically** by probing the harness at runtime

**Tradeoff**: Static is simpler and predictable. Dynamic adapts to harness updates but adds latency and complexity.

**Recommendation**: Static declaration. Harness capability changes are infrequent and should be handled by updating the adapter code, not by runtime discovery.

---

### OQ-003: Policy persistence across sessions

Should `RunPolicy` and `SessionPolicy` be persisted as spawn artifacts?

**Current state**: `SpawnParams` are logged but not structured for re-use.

**Proposal**: Persist `RunPolicy` as spawn metadata. `SessionPolicy` evolves during the session; persist the final state at session end.

**Benefit**: Enables "clone this spawn" or "fork from this spawn" without re-specifying all parameters.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| OpenCode HTTP lacks instruction channel | Medium | Medium | Fall back to inline composition (already works) |
| Cross-harness context transfer loses fidelity | High | Medium | Start with minimal context; iterate based on user feedback |
| Capability manifest misses edge cases | Medium | Low | Add capabilities incrementally as gaps are discovered |
| Claude resume re-applies instructions | Low | Low | Test and document behavior; design doesn't depend on specific outcome |
| OpenCode fork API doesn't exist | High | Medium | Mark fork as unsupported on HTTP; subprocess path still works |

---

## Recommended Probe Priority

1. **PROBE-002** (OpenCode fork semantics) — highest uncertainty, gates capability manifest accuracy
2. **PROBE-001** (OpenCode system field) — affects instruction projection mode decision
3. **PROBE-003** (Claude resume + append) — affects skill refresh behavior
4. **PROBE-004** (MCP tool selection) — lower priority, graceful degradation is acceptable
5. **PROBE-005** (session persistence) — lower priority, affects app UX but not spawn
