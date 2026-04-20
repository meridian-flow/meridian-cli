# Policy Architecture

## Overview

This document describes how the policy model is realized in Meridian's architecture. The design separates intent (what the user wants) from mechanism (how each harness delivers it), enabling a future UI to swap harness/provider/model dynamically without rewriting orchestration logic.

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Consumer Layer                           │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐   │
│  │    meridian spawn   │  │         Meridian App (UI)       │   │
│  │    (CLI command)    │  │     (interactive session mgmt)  │   │
│  └──────────┬──────────┘  └───────────────┬─────────────────┘   │
└─────────────┼─────────────────────────────┼─────────────────────┘
              │                             │
              ▼                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Policy Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  RunPolicy  │  │SessionPolicy│  │      TurnIntent         │  │
│  │  (frozen)   │  │  (mutable)  │  │      (ephemeral)        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                 InstructionStack                             ││
│  │  [base_system | agent | skills | session | turn]             ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Projection Layer                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │               HarnessProjector Protocol                      ││
│  │                                                              ││
│  │   project(run: RunPolicy, session: SessionPolicy,            ││
│  │           turn: TurnIntent) -> HarnessRequest                ││
│  │                                                              ││
│  │   capabilities() -> CapabilityManifest                       ││
│  │   degrade_intent(intent, capability) -> DegradedIntent | Err ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐│
│  │ ClaudeProjector │ │OpenCodeProjector│ │   CodexProjector    ││
│  │                 │ │                 │ │                     ││
│  │ → ClaudeRequest │ │→ OpenCodeRequest│ │   → CodexRequest    ││
│  └─────────────────┘ └─────────────────┘ └─────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Transport Layer                              │
│                                                                  │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐│
│  │  Subprocess     │ │  HTTP (OpenCode │ │  WebSocket (Claude  ││
│  │  Executor       │ │  serve)         │ │  streaming)         ││
│  └─────────────────┘ └─────────────────┘ └─────────────────────┘│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │               HarnessConnection Protocol                     ││
│  │   start(), stop(), send_user_message(), events()             ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Harness Runtime                             │
│                                                                  │
│         Claude Code         OpenCode           Codex             │
│         (subprocess/WS)     (HTTP/SSE)        (subprocess/WS)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Policy Types

### RunPolicy

Defined in `meridian/lib/policy/run_policy.py`:

```python
from pydantic import BaseModel, ConfigDict
from meridian.lib.core.types import ModelId
from meridian.lib.harness.ids import HarnessId

class RunPolicy(BaseModel):
    """Launch-scoped policy; immutable after spawn creation."""
    
    model_config = ConfigDict(frozen=True)
    
    harness_id: HarnessId
    model_id: ModelId | None = None
    provider_id: str | None = None
    agent_profile: str | None = None
    effort_level: str | None = None
    permission_policy: PermissionPolicy | None = None
    timeout_seconds: float | None = None
    mcp_servers: tuple[str, ...] = ()
    reference_files: tuple[str, ...] = ()
    extra_args: tuple[str, ...] = ()
```

### SessionPolicy

Defined in `meridian/lib/policy/session_policy.py`:

```python
class SessionMode(str, Enum):
    FRESH = "fresh"
    RESUME = "resume"
    FORK = "fork"

class SessionPolicy(BaseModel):
    """Session-scoped policy; mutable during session lifecycle."""
    
    session_mode: SessionMode = SessionMode.FRESH
    source_session_id: str | None = None
    instruction_stack: InstructionStack = Field(default_factory=InstructionStack)
    active_skills: tuple[str, ...] = ()
    mcp_tool_selection: tuple[str, ...] | None = None  # None = all available
```

### TurnIntent

Defined in `meridian/lib/policy/turn_intent.py`:

```python
class TurnIntent(BaseModel):
    """Turn-scoped intent; ephemeral."""
    
    model_config = ConfigDict(frozen=True)
    
    user_message: str
    injected_context: str | None = None
    steer_directive: str | None = None
    reasoning_effort_override: str | None = None
    response_constraints: ResponseConstraints | None = None
```

---

## InstructionStack

The instruction stack is the core abstraction for system prompt composition. It represents five ordered layers, each of which may be absent, opaque (harness-controlled), or explicit (Meridian-controlled).

```python
class InstructionLayer(BaseModel):
    """One layer in the instruction stack."""
    
    model_config = ConfigDict(frozen=True)
    
    source: Literal["harness", "agent", "skill", "session", "turn"]
    content: str | None = None  # None = opaque/harness-controlled
    identity: str | None = None  # e.g., agent name, skill path

class InstructionStack(BaseModel):
    """Ordered instruction layers for system prompt composition."""
    
    layers: tuple[InstructionLayer, ...] = ()
    
    def compose(self, mode: InstructionProjectionMode) -> str:
        """Compose Meridian-controlled layers into a single string."""
        ...
    
    @property
    def meridian_layers(self) -> tuple[InstructionLayer, ...]:
        """Return only Meridian-controlled layers (source != 'harness')."""
        ...
```

### Instruction Projection Modes

```python
class InstructionProjectionMode(str, Enum):
    APPEND_SYSTEM_PROMPT = "append_system_prompt"
    INLINE_PROMPT = "inline_prompt"
    SESSION_CONTEXT = "session_context"
```

**Harness mode mapping:**

| Harness   | Subprocess Mode       | Streaming Mode           |
|-----------|-----------------------|--------------------------|
| Claude    | `append_system_prompt`| `append_system_prompt`   |
| OpenCode  | `inline_prompt`       | `session_context`        |
| Codex     | `inline_prompt`       | `inline_prompt`          |

---

## CapabilityManifest

Each harness projector exposes what it can do at each scope:

```python
class CapabilityScope(str, Enum):
    RUN = "run"
    SESSION = "session"
    TURN = "turn"
    UNSUPPORTED = "unsupported"

class CapabilityManifest(BaseModel):
    """Feature availability by scope for one harness."""
    
    model_config = ConfigDict(frozen=True)
    
    harness_id: HarnessId
    transport: Literal["subprocess", "http", "websocket"]
    
    # Capability → Scope mapping
    capabilities: dict[str, CapabilityScope]
    
    # Degradation rules
    degradation_paths: dict[str, str]  # capability → fallback description
```

### Standard Capability Names

```python
CAPABILITY_MODEL_SELECTION = "model_selection"
CAPABILITY_PERMISSION_POLICY = "permission_policy"
CAPABILITY_TIMEOUT = "timeout"
CAPABILITY_MCP_SERVERS = "mcp_servers"
CAPABILITY_INSTRUCTION_APPEND = "instruction_append"
CAPABILITY_SKILL_ACTIVATION = "skill_activation"
CAPABILITY_SESSION_RESUME = "session_resume"
CAPABILITY_SESSION_FORK = "session_fork"
CAPABILITY_MCP_TOOL_SELECTION = "mcp_tool_selection"
CAPABILITY_STEER_DIRECTIVE = "steer_directive"
CAPABILITY_EFFORT_OVERRIDE = "effort_override"
CAPABILITY_RUNTIME_MODEL_SWITCH = "runtime_model_switch"
```

### Example: OpenCode HTTP Manifest

```python
OpenCodeHttpManifest = CapabilityManifest(
    harness_id=HarnessId.OPENCODE,
    transport="http",
    capabilities={
        CAPABILITY_MODEL_SELECTION: CapabilityScope.RUN,
        CAPABILITY_PERMISSION_POLICY: CapabilityScope.UNSUPPORTED,  # ignored on streaming
        CAPABILITY_TIMEOUT: CapabilityScope.RUN,
        CAPABILITY_MCP_SERVERS: CapabilityScope.RUN,
        CAPABILITY_INSTRUCTION_APPEND: CapabilityScope.SESSION,  # via session payload
        CAPABILITY_SKILL_ACTIVATION: CapabilityScope.SESSION,
        CAPABILITY_SESSION_RESUME: CapabilityScope.SESSION,
        CAPABILITY_SESSION_FORK: CapabilityScope.UNSUPPORTED,  # streaming cannot express fork
        CAPABILITY_MCP_TOOL_SELECTION: CapabilityScope.SESSION,
        CAPABILITY_STEER_DIRECTIVE: CapabilityScope.UNSUPPORTED,
        CAPABILITY_EFFORT_OVERRIDE: CapabilityScope.UNSUPPORTED,  # streaming ignores effort
        CAPABILITY_RUNTIME_MODEL_SWITCH: CapabilityScope.UNSUPPORTED,
    },
    degradation_paths={
        CAPABILITY_STEER_DIRECTIVE: "inline_in_user_message",
        CAPABILITY_EFFORT_OVERRIDE: "drop_silently",
    },
)
```

---

## HarnessProjector Protocol

```python
class HarnessRequest(Protocol):
    """Base protocol for harness-native request types."""
    pass

class HarnessProjector(Protocol[RequestT]):
    """Contract for translating policy intent to harness-native requests."""
    
    def capabilities(self) -> CapabilityManifest: ...
    
    def project(
        self,
        run: RunPolicy,
        session: SessionPolicy,
        turn: TurnIntent,
    ) -> RequestT: ...
    
    def degrade_intent(
        self,
        intent: str,
        capability: str,
    ) -> str | None:
        """Return degraded intent or None if degradation not possible."""
        ...
```

### Claude Projector

```python
class ClaudeRequest(BaseModel):
    """Claude-specific projected request."""
    
    command: list[str]  # full CLI command
    env_overrides: dict[str, str]
    prompt: str
    stdin_content: str | None

class ClaudeProjector(HarnessProjector[ClaudeRequest]):
    """Projects policy to Claude CLI invocation."""
    
    def project(self, run, session, turn):
        # Instruction composition uses append_system_prompt mode
        instructions = session.instruction_stack.compose(
            InstructionProjectionMode.APPEND_SYSTEM_PROMPT
        )
        
        # Build command with --append-system-prompt flag
        command = [...]
        if instructions:
            command.extend(["--append-system-prompt", instructions])
        
        return ClaudeRequest(command=command, ...)
```

### OpenCode Projector

```python
class OpenCodeSubprocessRequest(BaseModel):
    """OpenCode subprocess projected request."""
    
    command: list[str]
    env_overrides: dict[str, str]
    prompt: str

class OpenCodeHttpRequest(BaseModel):
    """OpenCode HTTP/SSE projected request."""
    
    serve_command: list[str]  # opencode serve command
    session_payload: dict[str, object]  # POST /session body
    message_payload: dict[str, object]  # POST /session/{id}/message body

class OpenCodeProjector(HarnessProjector[OpenCodeSubprocessRequest | OpenCodeHttpRequest]):
    """Projects policy to OpenCode invocation."""
    
    def __init__(self, transport: Literal["subprocess", "http"]):
        self._transport = transport
    
    def project(self, run, session, turn):
        if self._transport == "http":
            return self._project_http(run, session, turn)
        return self._project_subprocess(run, session, turn)
    
    def _project_http(self, run, session, turn):
        # Instructions go into session_payload, not command line
        instructions = session.instruction_stack.compose(
            InstructionProjectionMode.SESSION_CONTEXT
        )
        
        session_payload = {
            "model": run.model_id,
            "agent": run.agent_profile,
            # OpenCode accepts agent/system field at session creation
        }
        
        # Compose instructions into prompt for inline mode
        # OpenCode HTTP doesn't have a separate instruction channel
        composed_prompt = self._compose_inline(instructions, turn.user_message)
        
        message_payload = {
            "parts": [{"type": "text", "text": composed_prompt}],
        }
        
        return OpenCodeHttpRequest(
            serve_command=[...],
            session_payload=session_payload,
            message_payload=message_payload,
        )
```

---

## Instruction Composition for OpenCode

OpenCode's architecture means Meridian cannot directly append to the provider's base prompt. Instead:

### Fresh Session (spawn or app)

```
┌──────────────────────────────────────────────────────────────┐
│              OpenCode Provider Base Prompt                   │
│         (applied by OpenCode, opaque to Meridian)            │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼ (applied by provider/model)
┌──────────────────────────────────────────────────────────────┐
│                   User Message Turn 1                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ # Agent Instructions (optional)                        │  │
│  │ [Meridian agent profile body]                          │  │
│  │                                                        │  │
│  │ # Skills                                               │  │
│  │ [Loaded skill content]                                 │  │
│  │                                                        │  │
│  │ # Task                                                 │  │
│  │ [Actual user prompt]                                   │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Resume Session

On resume, OpenCode rehydrates the conversation history. Meridian should not re-inject instructions:

```
┌──────────────────────────────────────────────────────────────┐
│              OpenCode Provider Base Prompt                   │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│               [Restored Conversation History]                │
│  Turn 1: [original message with instructions]                │
│  Turn 2: [assistant response]                                │
│  ...                                                         │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                   New User Message                           │
│  [New prompt text only - no re-injection]                    │
└──────────────────────────────────────────────────────────────┘
```

### Fork Session

Fork creates a new branch. New instructions can be injected if the fork changes agent/skill context:

```
┌──────────────────────────────────────────────────────────────┐
│              OpenCode Provider Base Prompt                   │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│               [Forked Conversation Context]                  │
│  Turn 1–N: [conversation up to fork point]                   │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│                   Fork Turn (new branch)                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ # Context Update (if agent/skills changed)             │  │
│  │ [New agent/skill instructions if different]            │  │
│  │                                                        │  │
│  │ # Fork Prompt                                          │  │
│  │ [User prompt for the fork branch]                      │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Unsupported Intent Handling

### Graceful Degradation Table

| Intent | If Unsupported | Degradation Path |
|--------|----------------|------------------|
| `steer_directive` | Inline in user message | Compose as `[Steering: ...]` prefix |
| `effort_override` | Drop | Log warning, proceed without |
| `session_fork` | New fresh session | Create new session, carry context manually |
| `permission_policy` | Drop | Log warning, rely on harness defaults |
| `mcp_tool_selection` | Ignore | All MCP tools remain available |
| `runtime_model_switch` | Fork to new session | Create fork with new model |

### Strict Mode

When `MERIDIAN_STRICT_CAPABILITIES=1`:
- No degradation; all unsupported intents raise `UnsupportedCapabilityError`
- UI should disable controls for unsupported capabilities

---

## Integration with Existing Code

### Migration Path

The new policy layer sits between the consumer layer and the existing projection layer:

1. **Phase 1**: Define policy types in `meridian/lib/policy/`
2. **Phase 2**: Implement projectors that consume policy and emit existing launch specs
3. **Phase 3**: Refactor `meridian spawn` to construct policy objects
4. **Phase 4**: Add capability manifest to harness bundles
5. **Phase 5**: Meridian app consumes policy layer directly

### Relationship to Existing Types

| New Type | Replaces/Wraps | Location |
|----------|----------------|----------|
| `RunPolicy` | Subset of `SpawnParams` | `meridian/lib/policy/` |
| `SessionPolicy` | New (session_mode fields from SpawnParams) | `meridian/lib/policy/` |
| `TurnIntent` | `prompt` from SpawnParams | `meridian/lib/policy/` |
| `HarnessProjector` | `HarnessAdapter.resolve_launch_spec()` | `meridian/lib/harness/projectors/` |
| `CapabilityManifest` | Extends `HarnessCapabilities` | `meridian/lib/harness/capabilities/` |

`SpawnParams` remains as the transport layer's input; projectors output to existing `*LaunchSpec` types.

---

## Event Flow Examples

### Spawn Flow (Single Turn)

```
CLI: meridian spawn -a reviewer -m claude-sonnet "Review this PR"
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Construct RunPolicy                                            │
│    harness_id: claude, model_id: claude-sonnet, agent: reviewer │
│  Construct SessionPolicy                                        │
│    session_mode: fresh, instruction_stack: [agent, skills]      │
│  Construct TurnIntent                                           │
│    user_message: "Review this PR"                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ClaudeProjector.project(run, session, turn)                    │
│    → ClaudeRequest(command=[...], ...)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Subprocess executor: run command, capture output               │
└─────────────────────────────────────────────────────────────────┘
```

### App Flow (Multi-Turn with Model Switch)

```
App: User opens session with OpenCode + Gemini
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  RunPolicy: harness=opencode, model=gemini-2.5-pro              │
│  SessionPolicy: mode=fresh, instructions=[agent, skills]        │
│  TurnIntent: "Explain this codebase"                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  OpenCodeProjector.project() → OpenCodeHttpRequest              │
│  OpenCodeConnection.start() → session_id                        │
│  send_user_message() → stream events                            │
└─────────────────────────────────────────────────────────────────┘
                              │
User: Switches model to claude-sonnet in UI
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  UI queries capability: runtime_model_switch → UNSUPPORTED      │
│  Degradation: fork to new session                               │
│                                                                 │
│  New RunPolicy: harness=claude, model=claude-sonnet             │
│  SessionPolicy: mode=fork, source_session_id=<opencode-sid>     │
│  TurnIntent: (continuation prompt or user's next message)       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ClaudeProjector.project() with conversation context            │
│  New Claude session with forked context                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Open Design Questions

1. **Session context transfer on harness switch**: When forking from OpenCode to Claude, how much conversation history should be carried? Full transcript? Summary? Last N turns?

2. **Skill refresh on session resume**: Should skills be re-injected on resume even if the harness rehydrates context? (Currently: no for OpenCode, yes for Claude if using append-system-prompt)

3. **Capability manifest versioning**: How should the manifest evolve as harnesses gain features? Should capabilities have version constraints?

4. **Provider-specific instruction slots**: OpenCode HTTP may expose `agent` or `system` fields. Should the projector attempt to use these or always inline?
