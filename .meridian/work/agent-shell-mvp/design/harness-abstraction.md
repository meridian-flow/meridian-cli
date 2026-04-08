# Harness Abstraction

> **Status update (2026-04-08, p1135).** Three corrections from
> [`findings-harness-protocols.md`](../findings-harness-protocols.md) have
> been propagated through this doc. Read the findings first if you have not.
>
> 1. **All three primary harnesses (Claude Code, Codex `app-server`,
>    OpenCode) are tier-1 design targets.** Codex `app-server` exposes a
>    stable JSON-RPC 2.0 stdio protocol per developers.openai.com/codex/app-server
>    — `thread/start`, `turn/start`, `turn/interrupt`, and `item/*`
>    notifications are production-ready. Only the WebSocket transport and
>    specific opt-in methods are flagged experimental, and we don't need
>    them. Codex is no longer "TBD"; it is V1-capable, and ordering vs.
>    OpenCode is a product decision rather than a protocol-risk decision.
> 2. **Mid-turn steering is the differentiating capability** of the
>    platform. `HarnessSender.send_user_message()` and
>    `inject_user_message()` are core methods every adapter must implement
>    from day one. The §3.2 sender protocol and §6 mid-turn control surface
>    section take this as a hard requirement.
> 3. **Capability semantics surface as a semantic enum, not a boolean.**
>    `HarnessCapabilities.mid_turn_injection` takes one of
>    `queue` (Claude), `interrupt_restart` (Codex), `http_post` (OpenCode),
>    or `none`. The UI renders different affordances per value rather than
>    showing the same disabled-or-enabled checkbox; honest semantics beat
>    fake uniformity.
>
> The §7 Claude V0 sketch and §9 Codex section have been updated. The §10
> capability negotiation section now reads against the enum. The pre-update
> language is preserved in git history if anyone needs to compare.

> The load-bearing piece. A SOLID-compliant interface that wraps a long-lived
> agent subprocess (or HTTP session) and presents one neutral surface to the
> rest of the backend. The interface is designed against three real
> implementations (Claude Code, Codex `app-server`, OpenCode), not one
> stable + two sketchy.
>
> Read [overview.md](./overview.md) first for system context. Read
> [`exploration/meridian-channel-harness-grounding.md`](../exploration/meridian-channel-harness-grounding.md)
> for what the existing single-shot adapters in `src/meridian/lib/harness/`
> already give us. Read
> [`exploration/external-protocols-research.md`](../exploration/external-protocols-research.md)
> for the Claude Code stream-json vs opencode HTTP/ACP comparison this
> abstraction has to bridge.

## 1. Problem framing

The existing harness layer (`src/meridian/lib/harness/{adapter,claude,codex,opencode}.py`)
models exactly one shape: **one prompt → one argv → one child process → one
report file**. Every field on `SpawnParams` is mapped at command-build time;
every adapter exports `extract_report`, `extract_session_id`,
`extract_usage`. The contract assumes the subprocess **terminates** before
results are read. There is no streaming consumer, no stdin after the prompt,
no mid-run control plane.

The new shell needs the opposite: **one subprocess kept alive across many
turns**, fed user messages on a live channel, emitting normalized events
continuously, accepting interrupts and tool-approval responses while a turn is
in flight, and surviving the user opening and closing the WebSocket multiple
times per session.

| Property | Existing single-shot adapters | New session adapters |
|---|---|---|
| Process lifetime | One run | Whole session |
| Input | Argv + stdin once | Many messages over time |
| Output | Read from `report.md` after exit | Async stream of normalized events |
| Mid-run control | None | Interrupt, tool approval, mid-turn inject |
| Failure model | Exit code | Liveness probe + crash recovery |
| Reuse target | Spawn ergonomics | Frontend chat session |

The existing pattern still informs us — `HarnessCapabilities`, the
`PromptPolicy` lanes (Claude uses `--append-system-prompt` for skills,
opencode uses `system` field on session create), `SessionSeed`, and
`build_command`'s strict field mapping all transfer in spirit. But the
runtime contract is different enough that **we add a new family of adapters
beside the existing ones rather than retrofit them**. The existing
single-shot adapters keep serving `meridian spawn`. The session adapters
serve `meridian shell`. They share registries-as-pattern but not the
registry instance.

### What this abstraction must solve

1. **Bidirectional streaming.** Backend speaks commands into the harness;
   harness speaks events out. Both sides asynchronous, both sides framed.
2. **Mid-turn injection.** A user message arriving while a tool is running
   should reach the model at the next safe point. Opencode does this
   trivially via `POST /session/:id/message`; Claude Code does it by writing
   another `user` NDJSON line on stdin while the previous turn is still
   streaming. The interface must accommodate both without exposing either's
   transport.
3. **Capability negotiation.** Some harnesses support tool approval gating
   natively (opencode permissions, Claude Code `control_request` /
   `can_use_tool`), some don't. The abstraction must declare capabilities
   so the frontend can render only the affordances the active adapter
   actually implements.
4. **Crash recovery.** Subprocess dies → adapter raises a typed
   `RunError` event upstream and `health()` flips to `dead`. The
   `SessionManager` decides whether to restart. Recovery is event-driven,
   not magic.
5. **Adapter swappability.** Switching from `ClaudeCodeAdapter` to
   `OpenCodeAdapter` is one line in YAML. The router, translator, gateway,
   `SessionManager`, `EventRouter`, and frontend touch zero code.

## 2. SOLID applied

| Principle | Where it lives in this design |
|---|---|
| **SRP** | `HarnessLifecycle` owns process state. `HarnessSender` owns inbound commands. `HarnessReceiver` owns outbound events. `HarnessAdapter` is the composite that bundles all three for one harness. `FrontendTranslator` is a separate module — it never imports any adapter. `EventRouter` is separate again. |
| **OCP** | Adding `OpenCodeAdapter` = one new file under `src/meridian/shell/adapters/opencode.py` plus `register("opencode", OpenCodeAdapterFactory)` in the registry. No edits to translator, router, gateway, frontend, or any existing adapter. |
| **ISP** | Three protocols, not one fat interface. The session bootstrap depends on `HarnessLifecycle`. The inbound translator depends on `HarnessSender`. `TurnOrchestrator` consumes `HarnessReceiver`. None of them sees the others' methods. A unit test that exercises sender behavior can mock just `HarnessSender`. |
| **LSP** | Every adapter satisfies the same three protocols with the same async semantics, the same normalized event union, and the same normalized command union. Capability flags express **what an adapter supports**, not **what shape its methods take** — so an `OpenCodeAdapter` is substitutable for a `ClaudeCodeAdapter` even when only one of them supports permission gating. The caller checks `adapter.capabilities.supports_tool_approval_gating` and chooses what to attempt. |
| **DIP** | `SessionManager.__init__` accepts `adapter: HarnessAdapter` (the protocol), never `ClaudeCodeAdapter` (the concrete). Construction happens in one factory module that is the only place in the backend that imports concrete adapter classes. |

The interface is **designed against opencode's HTTP/ACP shape as a peer with
Claude Code's stream-json shape**. We deliberately do **not** lift Claude
Code's content-block vocabulary or its `control_request` shapes into the
contract. Instead we name a smaller, neutral set of operations and events
that both harnesses can implement honestly. Where Claude Code or opencode
adds something the other lacks, it goes behind a capability flag, never into
the base contract.

## 2.5 Mid-turn control is the load-bearing concern

> Per `findings-harness-protocols.md`: this section moved to the front of
> the doc on purpose. Lifecycle (start / stop / health) is plumbing.
> Mid-turn steering is the differentiating capability of the platform —
> what lets a user (or a parent orchestrator) say "wait, reconsider X" to
> a running agent and have the agent absorb the correction without being
> killed and respawned. The interface is shaped around supporting this
> cleanly across all three harnesses from day one. Retrofitting it later
> means rebuilding the interface.

The contract has three load-bearing properties:

1. **`HarnessSender.inject_user_message()` is a core method.** Every adapter
   in the V0/V1 set (Claude, Codex, OpenCode) implements it. A harness that
   cannot support it is not a tier-1 adapter. No `CapabilityNotSupported`
   escape hatch is allowed at the protocol level — only at the UI affordance
   level via the `mid_turn_injection` enum.
2. **The mode is honest, not boolean.** `HarnessCapabilities.mid_turn_injection`
   is `Literal["queue", "interrupt_restart", "http_post", "none"]`. The UI
   renders different affordances per mode — Claude users see "queued for
   next turn", Codex users see "this will interrupt the current turn",
   OpenCode users see no hint at all. Lying about wire-level behavior to
   fake uniformity is the failure mode this enum exists to prevent.
3. **The CLI consumes the same primitive.** `meridian spawn inject
   <spawn_id> "message"` is a V0 CLI command. It calls
   `adapter.inject_user_message()` against the spawn's adapter, with the
   adapter picking the right wire mechanism. This is what makes
   meridian-channel's amalgamation actually amalgamate — one adapter layer,
   two consumers (CLI and UI). See `synthesis.md` Q7 for the user
   decision on routing `meridian spawn` through the shell adapter family.

The §3.2 sender protocol below, the §7 Claude V0 sketch, and the §9 Codex
V1 sketch each answer the same question for their harness: *how does this
adapter implement `inject_user_message()`, and what is the user-visible
semantic the UI needs to know about?* That's the acceptance criterion for
each adapter section being done.

## 3. Interface decomposition

All session-lived shell types live under `src/meridian/shell/`. Imports below
assume this layout:

- `src/meridian/shell/adapters/base.py` — abstract lifecycle / sender /
  receiver protocols
- `src/meridian/shell/schemas/events.py` — canonical normalized event schema
- `src/meridian/shell/schemas/commands.py` — normalized command schema
- `src/meridian/shell/session.py` — `SessionContext`, `SessionState`, and
  session bootstrap glue

The existing single-shot adapters in `src/meridian/lib/harness/` remain
untouched. This doc is about the new shell adapter family only.

```python
# src/meridian/shell/adapters/base.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Protocol, AsyncIterator, runtime_checkable

# ──────────────────────────────────────────────────────────────────────
# Capabilities — declarative, frozen, queried at startup and per call
# ──────────────────────────────────────────────────────────────────────

MidTurnInjectionMode = Literal["queue", "interrupt_restart", "http_post", "none"]

@dataclass(frozen=True)
class HarnessCapabilities:
    """What this harness does in this build. Negotiated, not assumed."""

    # Inbound
    mid_turn_injection: MidTurnInjectionMode  # semantic enum, not a boolean — see §10.2
    interrupt: bool                   # cancel current turn
    supports_tool_approval_gating: bool
    cancel_tool: bool                 # cancel a single in-flight tool call

    # Outbound
    streaming_text: bool              # token-level deltas, not whole messages
    streaming_thinking: bool          # exposes reasoning/thinking blocks
    tool_call_args_streaming: bool    # streams tool args before completion

    # Lifecycle
    supports_session_persistence: bool # state survives adapter restart
    supports_session_resume: bool      # can attach to a previously persisted id
    supports_session_fork: bool        # branch off an existing session id
    health_probe: bool                # has a non-side-effecting liveness check

    # Identity
    harness_id: str                   # "claude-code", "opencode", "codex"
    display_name: str                 # human label for the UI

    def assert_supports(self, feature: str) -> None:
        """Raise CapabilityError if `feature` is False on this adapter.

        For boolean flags only. For `mid_turn_injection`, callers branch on the
        enum value directly because the semantics differ per mode and a single
        "supported" boolean would lie about the user-visible behavior.
        """
        if not getattr(self, feature, False):
            raise CapabilityError(self.harness_id, feature)

    @property
    def supports_mid_turn_injection(self) -> bool:
        """True for any mode other than 'none'. Use the enum directly when the
        UI needs to render a mode-specific affordance."""
        return self.mid_turn_injection != "none"
```

The gateway sends a snapshot of `HarnessCapabilities` to the frontend as
`SessionInfo.capabilities` on `SESSION_HELLO` (see
[frontend-protocol.md](./frontend-protocol.md)). These flags describe
**effective V0 behavior**, not theoretical protocol headroom. If Claude Code
could support a feature later but the V0 adapter does not implement it, the
corresponding `supports_*` flag is `False` now.

### 3.1 HarnessLifecycle

```python
# src/meridian/shell/adapters/base.py (continued)

class HarnessHealth(Enum):
    STARTING = "starting"
    READY    = "ready"
    DEGRADED = "degraded"   # responsive but has shed a non-critical capability
    DEAD     = "dead"       # process gone or HTTP session 404
    UNKNOWN  = "unknown"

@dataclass(frozen=True)
class SessionHandle:
    """Stable identifier for one harness session, opaque to callers."""
    session_id: str          # adapter-internal id (Claude UUID, opencode session id)
    harness_id: str
    started_at_ms: int

@dataclass(frozen=True)
class StartParams:
    """Everything the lifecycle needs to bring up a session."""
    agent_profile_id: str
    skills: tuple[str, ...]
    system_prompt: str | None
    model: str | None
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    resume_session_id: str | None = None   # adapter-internal id, if reattaching
    fork: bool = False

@runtime_checkable
class HarnessLifecycle(Protocol):
    """Process state. One instance per session."""

    @property
    def capabilities(self) -> HarnessCapabilities: ...

    @property
    def handle(self) -> SessionHandle | None:
        """The session id, once start() has succeeded. None before/after."""
        ...

    async def start(self, params: StartParams) -> SessionHandle:
        """Bring the harness up. Idempotent if already started with same params."""
        ...

    async def stop(self, *, grace_ms: int = 2000) -> None:
        """Best-effort graceful shutdown, then kill. Always converges to DEAD."""
        ...

    async def health(self) -> HarnessHealth:
        """Non-side-effecting probe. Cheap. Called by SessionManager periodically."""
        ...
```

`SessionManager` is the only consumer that sees `HarnessLifecycle` directly.
Lifecycle returns the `SessionHandle` that the rest of the backend uses to
correlate events with the active session.

### 3.2 HarnessSender

```python
# src/meridian/shell/adapters/base.py (continued)

@dataclass(frozen=True)
class CommandAck:
    """Confirmation that a command was accepted (not executed)."""
    command_id: str
    accepted_at_ms: int
    queued: bool                    # True if held until current turn yields

@runtime_checkable
class HarnessSender(Protocol):
    """Inbound commands toward the harness. One instance per session."""

    async def send_user_message(
        self,
        content: tuple[ContentBlock, ...],
        *,
        message_id: str,
        previous_turn_id: str | None = None,
        command_id: str | None = None,
    ) -> CommandAck:
        """Standard user turn input. Always supported. `content` is a
        content-block array (text + image + file blocks) carried verbatim
        from the frontend wire shape; the adapter packages it for its
        harness's native transport."""
        ...

    async def inject_user_message(
        self,
        content: tuple[ContentBlock, ...],
        *,
        message_id: str,
        command_id: str | None = None,
    ) -> CommandAck:
        """User message while a turn is in flight. Tier-1 capability —
        every adapter implements this from V0. Semantics vary by harness:

        - Claude (`mid_turn_injection="queue"`): write `user` NDJSON to
          stdin; the harness queues it to the next turn boundary.
        - Codex (`mid_turn_injection="interrupt_restart"`): call
          `turn/interrupt` followed by `turn/start` with the new prompt.
        - OpenCode (`mid_turn_injection="http_post"`): POST the message to
          `/session/:id/prompt_async`.

        The adapter hides the wire mechanism; callers get "deliver this
        message to the running agent" semantics. The capability enum lets
        the UI render the right mode-specific affordance.
        """
        ...

    async def interrupt(
        self,
        *,
        reason: str | None = None,
        command_id: str | None = None,
    ) -> CommandAck:
        """Cancel current turn. Requires capabilities.interrupt."""
        ...

    async def approve_tool(
        self,
        request_id: str,
        *,
        command_id: str | None = None,
    ) -> CommandAck:
        """Allow a previously requested tool call. Requires approval gating."""
        ...

    async def deny_tool(
        self,
        request_id: str,
        *,
        reason: str | None = None,
        command_id: str | None = None,
    ) -> CommandAck:
        """Reject a tool call. Requires approval gating."""
        ...

    async def cancel_tool(
        self,
        tool_call_id: str,
        *,
        command_id: str | None = None,
    ) -> CommandAck:
        """Stop a single in-flight tool. Requires cancel_tool."""
        ...

    async def submit_tool_result(
        self,
        tool_call_id: str,
        result_payload: dict[str, Any],
        *,
        status: Literal["ok", "error", "cancelled", "timeout"],
        command_id: str | None = None,
    ) -> CommandAck:
        """Feed a locally executed tool result back into the harness."""
        ...
```

`ContentBlock` is a tagged union of `{type:"text", text:str}`,
`{type:"image", source:{path, mime}}`, and `{type:"file", source:{path, mime}}`
— matching the frontend wire shape in `frontend-protocol.md` §5.1 exactly.
The normalized `UserMessage` carries this array verbatim; the translator is
rename-only (see `event-flow.md` §2) and does not repackage it. Each adapter
then packages the content-block array into its harness's native transport:
Claude Code emits NDJSON `user` messages with the same block shape, Codex
`app-server` maps blocks to JSON-RPC `turn/start` args, OpenCode serializes
to its HTTP `parts` array. Attachments are thus **part of** the content-block
array, not a parallel carrier — one type survives the full path from browser
to harness.

`command_id` is caller-supplied so the backend can correlate `CommandAck`
and downstream events back to a specific UI action. Adapters must never
generate it themselves.

**`inject_user_message` and `send_user_message` are intentionally separate
methods.** They model the same intent (user wants to say something) but they
have **different acceptance semantics**: `send_user_message` is valid only
when no turn is in flight (or queues until idle, depending on the adapter);
`inject_user_message` is valid only when a turn **is** in flight. Conflating them
into one method forces the caller to decide what state the harness is in,
and that state is exactly what the adapter knows and the caller does not.
Splitting them is ISP applied to verbs.

### 3.3 HarnessReceiver

```python
# src/meridian/shell/adapters/base.py (continued)

@runtime_checkable
class HarnessReceiver(Protocol):
    """Outbound events from the harness. One instance per session."""

    def events(self) -> AsyncIterator[NormalizedEvent]:
        """Async iterator of normalized events.

        Hot iterator — starts emitting as soon as the harness produces output.
        Caller drives the loop. Iterator terminates when the session reaches
        a terminal state (RUN_FINISHED with no further turns, or RUN_ERROR
        on fatal failure, or after stop()).
        """
        ...
```

There is intentionally **only one method**. The receiver is a pure pull-side
iterator — adapters internally wire stdout / SSE to a `asyncio.Queue` and
yield from it. This is the smallest possible interface that satisfies the
streaming requirement, and it's why the receiver is its own protocol: the
event router depends on `HarnessReceiver` and nothing else, and a fake
receiver for tests is one async generator.

### 3.4 HarnessAdapter — composite

```python
# src/meridian/shell/adapters/base.py (continued)

@runtime_checkable
class HarnessAdapter(HarnessLifecycle, HarnessSender, HarnessReceiver, Protocol):
    """The composite each concrete adapter implements.

    Note: callers should depend on the narrowest sub-protocol they need
    (DIP applied through ISP). The composite exists so factories can hand
    out one object that satisfies all three roles for one session.
    """
    ...
```

`HarnessAdapter` is a structural composite, not an inheritance chain. A
concrete adapter implements all three protocols on one class. Tests depend
on the slimmest one they need.

## 4. Normalized events

The receiver yields events from this union. This is the **canonical normalized
schema** for the shell. Every other design doc derives from it. The
translator may rename fields for the frontend wire contract and wrap them in
the WS envelope, but it does not synthesize missing IDs, invent lifecycle
edges, or reconstruct semantics that were not already present here.

```python
# src/meridian/shell/schemas/events.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

# Common envelope ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class EventMeta:
    session_id: str
    seq: int                     # monotonic per session
    received_at_ms: int          # adapter-side wallclock

# Run lifecycle ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunStarted:
    meta: EventMeta
    turn_id: str
    message_id: str
    triggered_by_command_id: str | None   # echo of caller's command_id, if any

@dataclass(frozen=True)
class RunFinished:
    meta: EventMeta
    turn_id: str
    usage: TokenUsage | None
    stop_reason: Literal["end_turn", "max_tokens", "interrupted", "error"]

@dataclass(frozen=True)
class RunError:
    meta: EventMeta
    turn_id: str | None
    code: str                    # "harness_dead", "transport_lost", "malformed_event", ...
    message: str
    recoverable: bool

# Text content ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TextMessageStart:
    meta: EventMeta
    message_id: str
    role: Literal["assistant"]

@dataclass(frozen=True)
class TextMessageContent:
    meta: EventMeta
    message_id: str
    delta: str

@dataclass(frozen=True)
class TextMessageEnd:
    meta: EventMeta
    message_id: str

# Thinking / reasoning ─────────────────────────────────────────────────

@dataclass(frozen=True)
class ThinkingStart:
    meta: EventMeta
    message_id: str

@dataclass(frozen=True)
class ThinkingContent:
    meta: EventMeta
    message_id: str
    delta: str

@dataclass(frozen=True)
class ThinkingEnd:
    meta: EventMeta
    message_id: str

# Tool calls ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolCallStart:
    meta: EventMeta
    tool_call_id: str
    tool_name: str
    message_id: str | None

@dataclass(frozen=True)
class ToolCallArgs:
    """Either a streamed delta of args JSON, or the complete args dict.

    Adapters that stream args set `delta` and leave `args_complete` None.
    Adapters that don't set `args_complete` once and never set `delta`.
    """
    meta: EventMeta
    tool_call_id: str
    delta: str | None
    args_complete: dict[str, Any] | None

@dataclass(frozen=True)
class ToolCallEnd:
    """Tool call structure finalized. Execution may or may not have started."""
    meta: EventMeta
    tool_call_id: str

@dataclass(frozen=True)
class ToolOutput:
    """Streaming stdout/stderr from a tool while it executes.

    Mirrors biomedical-mvp's TOOL_OUTPUT — incremental progress text the
    UI shows under the tool call card.
    """
    meta: EventMeta
    tool_call_id: str
    stream: Literal["stdout", "stderr"]
    chunk: str
    sequence: int

@dataclass(frozen=True)
class ToolCallResult:
    """Final tool result going back into the model. Carries display payload too."""
    meta: EventMeta
    tool_call_id: str
    message_id: str | None
    status: Literal["done", "error", "cancelled", "timeout"]
    result_summary: str | None      # short text the model receives
    error: str | None

@dataclass(frozen=True)
class DisplayResult:
    """Rich display payload referenced by the activity stream.

    Mirrors biomedical-mvp's DISPLAY_RESULT — points the frontend at a
    structured result file (.meridian/result.json + sidecar binaries) that
    the activity stream renders inline (plot, mesh, table, image).
    """
    meta: EventMeta
    tool_call_id: str
    message_id: str | None
    display_id: str
    result_kind: str               # "plotly", "mesh", "image", "table", ...
    data: dict[str, Any]

# Permission / approval ────────────────────────────────────────────────

@dataclass(frozen=True)
class PermissionRequested:
    """Harness wants user approval for a tool call. Capability-gated."""
    meta: EventMeta
    request_id: str
    tool_call_id: str
    tool_name: str
    args_preview: dict[str, Any]
    timeout_ms: int | None         # adapter's view of how long it will wait

# Session ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionPersisted:
    """Adapter has flushed session state to durable storage. Capability-gated."""
    meta: EventMeta
    persisted_session_id: str

# Sentinel ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HarnessHeartbeat:
    """Liveness signal during long quiet periods so the gateway knows the
    pipe isn't dead. Adapter-driven, not transport-driven."""
    meta: EventMeta

NormalizedEvent = (
    RunStarted | RunFinished | RunError
    | TextMessageStart | TextMessageContent | TextMessageEnd
    | ThinkingStart | ThinkingContent | ThinkingEnd
    | ToolCallStart | ToolCallArgs | ToolCallEnd
    | ToolOutput | ToolCallResult | DisplayResult
    | PermissionRequested
    | SessionPersisted
    | HarnessHeartbeat
)
```

### 4.1 Why these specific events

- **`RUN_STARTED` / `RUN_FINISHED` / `RUN_ERROR`** are the boundaries of one
  agent turn. `turn_id` is the canonical runtime identity. The frontend's
  `turnId` is a thin rename of the same concept.
- **`TEXT_MESSAGE_*`** matches Claude's `content_block_delta` for text and
  opencode's `text` parts. The split into start/content/end lets the
  frontend reducer treat content as additive without re-parsing the whole
  message on every delta.
- **`THINKING_*`** is its own family because both harnesses surface reasoning
  blocks separately and the UI renders them differently (collapsible
  "thinking" pane). The frontend's `THINKING_TEXT_MESSAGE_*` family is a thin
  rename/wrap of this one.
- **`TOOL_CALL_*` plus `TOOL_OUTPUT` plus `DISPLAY_RESULT`** is the minimal
  lifecycle the router/orchestrator stack needs. `display_id` is canonical
  here because one tool call may emit multiple display updates.
- **`PERMISSION_REQUESTED`** is its own event, not folded into
  `ToolCallStart`. A harness without approval gating simply never emits it.
- **`SESSION_PERSISTED`** is a side-channel notification — opencode emits
  it when SQLite is flushed; Claude Code emits one when it writes its
  session JSON. The frontend doesn't render it; the `SessionManager` uses
  it for resume bookkeeping.
- **`HarnessHeartbeat`** exists because real harnesses go quiet for many
  seconds during slow tool calls. The gateway needs an "I'm alive" signal
  it can forward to the WebSocket layer for keepalive logic.

### 4.2 Translator headroom

`FrontendTranslator` maps `NormalizedEvent → wire event` with **rename-only**
discipline in V0 — no semantic translation, no ID synthesis, no lifecycle
reconstruction. The reason the layer exists at all:

1. **Wire vocabulary may evolve.** When the frontend protocol grows a new
   event type (e.g. `WORK_ITEM_ATTACHED`), the translator absorbs it without
   touching adapters.
2. **Cross-harness reconciliation.** Opencode emits `reasoning` parts that
   look like text but should land as `THINKING_*` on the wire. Without the
   translator, every adapter would need to know wire-side conventions.
3. **Field shape drift.** Wire envelopes have `subId`, `seq`, `epoch` from
   the frontend-v2 contract. Normalized events have `EventMeta`. The
   translator lifts `meta` into the envelope and renames `turn_id` →
   `turnId`, `tool_call_id` → `toolCallId`, `result_kind` → `resultKind`.

The translator never reorders, never coalesces, never drops, never adds
events the adapter didn't emit. Anything more complex than rename + envelope
wrap belongs in the adapter, not the translator. (Decision logged in
[decisions.md](../decisions.md) once written.)

## 5. Normalized commands

The sender accepts commands from this union. Commands are **inbound**
counterparts to the outbound events.

```python
# src/meridian/shell/schemas/commands.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class UserMessage:
    message_id: str
    content: tuple[ContentBlock, ...]        # text + image + file blocks
    previous_turn_id: str | None = None
    command_id: str | None = None

@dataclass(frozen=True)
class MidTurnInject:
    message_id: str
    content: tuple[ContentBlock, ...]
    command_id: str | None = None

@dataclass(frozen=True)
class Interrupt:
    reason: str | None = None
    command_id: str | None = None

@dataclass(frozen=True)
class ApproveTool:
    request_id: str
    command_id: str | None = None

@dataclass(frozen=True)
class DenyTool:
    request_id: str
    reason: str | None = None
    command_id: str | None = None

@dataclass(frozen=True)
class CancelTool:
    tool_call_id: str
    command_id: str | None = None

@dataclass(frozen=True)
class SubmitToolResult:
    tool_call_id: str
    result_payload: dict[str, Any]
    status: Literal["ok", "error", "cancelled", "timeout"]
    command_id: str | None = None

NormalizedCommand = (
    UserMessage | MidTurnInject | Interrupt
    | ApproveTool | DenyTool | CancelTool | SubmitToolResult
)
```

The sender protocol exposes one method per command type rather than a
single `send(cmd: NormalizedCommand)` because:

- Distinct method signatures make capability gating explicit at the call
  site (`adapter.approve_tool(...)` is the only place to look for approval).
- IDE autocomplete and pyright type checking work better with named
  methods.
- Ad-hoc unioning at the protocol layer makes it harder for translators to
  forward only the commands they understand.

The dataclass union exists so the gateway can deserialize WebSocket
envelopes into typed commands and pattern-match on them in the translator
before invoking the right sender method.

## 6. Adapter registration and DI

```python
# src/meridian/shell/adapters/__init__.py
from __future__ import annotations
from typing import Callable, Mapping

AdapterFactory = Callable[[StartParams], HarnessAdapter]

class HarnessRegistry:
    """The single point in the backend that knows concrete adapter classes."""

    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, harness_id: str, factory: AdapterFactory) -> None:
        if harness_id in self._factories:
            raise ValueError(f"harness {harness_id!r} already registered")
        self._factories[harness_id] = factory

    def create(self, harness_id: str, params: StartParams) -> HarnessAdapter:
        if harness_id not in self._factories:
            raise UnknownHarnessError(harness_id)
        return self._factories[harness_id](params)

    def known(self) -> Mapping[str, AdapterFactory]:
        return dict(self._factories)


def build_default_registry() -> HarnessRegistry:
    """The one place that imports concrete adapters."""
    from meridian.shell.adapters.claude_code import ClaudeCodeAdapter
    # from meridian.shell.adapters.opencode import OpenCodeAdapter   # V1

    reg = HarnessRegistry()
    reg.register("claude-code", lambda p: ClaudeCodeAdapter.from_params(p))
    # reg.register("opencode", lambda p: OpenCodeAdapter.from_params(p))
    return reg
```

FastAPI wires this once at app startup:

```python
# src/meridian/shell/session.py (sketch)
from fastapi import FastAPI, Depends
from meridian.shell.adapters import HarnessRegistry, build_default_registry

def get_registry() -> HarnessRegistry:
    return app.state.harness_registry

app = FastAPI()

@app.on_event("startup")
async def _startup() -> None:
    app.state.harness_registry = build_default_registry()

# SessionContext builds the adapter once per process/work item. EventRouter,
# TurnOrchestrator, and ToolExecutionCoordinator depend on the abstract
# HarnessAdapter only, never on ClaudeCodeAdapter.
```

Config in YAML names the adapter:

```yaml
# .meridian/shell.yaml
harness:
  id: claude-code              # or "opencode" in V1
  model: claude-sonnet-4-5
  agent_profile: data-analyst
  skills:
    - biomedical-mvp/segmentation
    - biomedical-mvp/figure-rendering
```

CLI override:

```bash
meridian shell start --harness opencode --agent data-analyst
```

The override flows through the same precedence the rest of meridian-channel
already uses (CLI > env > YAML > defaults). The registry doesn't care; it
only sees `harness_id` at the moment a session is created.

**Why a registry instead of entry points / plugins?** Three adapters total
(V0: 1, V1: 2, deferred: 1) does not justify packaging extension points. A
flat in-process registry is the smallest abstraction that still satisfies
OCP. If a future harness ships outside this repo, registering at startup
moves to a config-driven import — the registry shape doesn't change.

## 7. ClaudeCodeAdapter — V0 sketch

The concrete shape of the V0 adapter, in enough detail that an implementer
doesn't have to re-derive the protocol from companion's source.

### 7.1 Process model

One long-lived child:

```
claude --input-format stream-json
       --output-format stream-json
       --verbose
       -p ""
       --model <model>
       [--append-system-prompt <system-prompt>]
       [--mcp-config <tool-config.json>]
       [--permission-mode <mode>]    # capability-gated, see §7.4
```

Notes:

- `-p ""` is required; Claude Code waits for the first `user` NDJSON line on
  stdin before doing anything (per companion's reverse engineering).
- `--input-format stream-json --output-format stream-json --verbose` is the
  documented headless triplet plus the verbosity that makes stream events
  actually appear.
- The agent profile body and skills are composed once into the session system
  prompt. Claude receives that string via `--append-system-prompt`.
- Tool definitions are materialized into an MCP config file and passed via
  `--mcp-config`. There is no competing init-time tool registration path in
  V0.
- `CLAUDECODE` is set in the child env to match the existing single-shot
  adapter's behavior; everything else inherits from the configured cwd.
- `--sdk-url ws://...` is **not** used in V0. The companion approach
  routes via WebSocket because it bridges to a browser; we already have a
  Python process attached to stdin/stdout, so the simpler stdio protocol is
  enough. We document this so V1 implementers don't second-guess it.

### 7.2 Inbound — sender → stdin

Each `HarnessSender` method writes one NDJSON line on stdin, except tool
definitions which are passed at process start through `--mcp-config`:

| Method | Wire |
|---|---|
| `send_user_message(text)` | `{"type":"user","message":{"role":"user","content":[{"type":"text","text":text}]}}` |
| `inject_user_message(text)` | Writes a `{"type":"user",...}` NDJSON line to stdin. Claude Code's stream-json input queues the message and delivers it at the next turn boundary — this is the `queue` mode in `HarnessCapabilities.mid_turn_injection`. Tier-1 V0 per `findings-harness-protocols.md`. |
| `interrupt()` | `{"type":"control_request","request_id":<uuid>,"request":{"subtype":"interrupt"}}` |
| `approve_tool(req_id)` | Raises `CapabilityNotSupported` in V0. |
| `deny_tool(req_id, reason)` | Raises `CapabilityNotSupported` in V0. |
| `cancel_tool(...)` | **Not supported.** Capability flag `cancel_tool=False`. |
| `submit_tool_result(tool_call_id, result_payload, status)` | Writes the Claude-native `tool_result` frame on stdin. This is the only supported way the local execution path resumes a Claude turn. |

Stdin writes are protected by an `asyncio.Lock` so concurrent
`send_user_message` + `interrupt` can't interleave bytes. `command_id` is
stored in a small map keyed by the run-id Claude assigns, so the receiver
can echo it on the corresponding `RunStarted`.

### 7.3 Outbound — stdout → receiver

The adapter spawns one reader task that loops over stdout NDJSON lines and
pushes normalized events into an `asyncio.Queue` that backs `events()`:

```python
async def _reader(self) -> None:
    assert self._proc and self._proc.stdout
    seq = 0
    async for line in self._proc.stdout:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            await self._emit(RunError(
                meta=self._meta(seq), turn_id=None,
                code="malformed_event", message=line[:200].decode(errors="replace"),
                recoverable=True,
            ))
            seq += 1
            continue
        for ev in self._translate_one(obj, seq):
            await self._emit(ev)
            seq += 1
```

`_translate_one` is where the Claude-specific dialect is contained. The
mapping is small:

| Claude stream-json | Normalized event(s) |
|---|---|
| first assistant `message_start` after a user command | `RunStarted` |
| `message_start` | `TextMessageStart` (assistant role) |
| `content_block_start` (text) | (no-op; covered by `TextMessageStart`) |
| `content_block_delta` (text) | `TextMessageContent` |
| `content_block_stop` (text) | `TextMessageEnd` |
| `content_block_start` (thinking) | `ThinkingStart` |
| `content_block_delta` (thinking) | `ThinkingContent` |
| `content_block_stop` (thinking) | `ThinkingEnd` |
| `content_block_start` (tool_use) | `ToolCallStart` |
| `content_block_delta` (tool_use input_json) | `ToolCallArgs(delta=...)` |
| `content_block_stop` (tool_use) | `ToolCallEnd` |
| `tool_result` acknowledgement / assistant continuation | no-op at adapter layer; the local execution path already emitted `ToolCallResult` before calling `submit_tool_result()` |
| `result` | `RunFinished` |
| `control_request` `can_use_tool` | `PermissionRequested` (V1 only; V0 adapter rejects approval gating) |
| anything else | dropped, logged at debug |

Tool execution events (`ToolOutput`, `DisplayResult`, `ToolCallResult`) **do
not come from Claude**. They come from `ToolExecutionCoordinator`, which runs
the local tool and then calls `HarnessSender.submit_tool_result()`. This keeps
Claude-specific stdin frames out of the router/orchestrator layer.

### 7.4 Capability declaration

```python
ClaudeCodeAdapter.capabilities = HarnessCapabilities(
    mid_turn_injection      = "queue",  # stream-json `user` NDJSON queues to next turn boundary
    interrupt               = True,    # control_request subtype interrupt
    supports_tool_approval_gating = False,
    cancel_tool             = False,
    streaming_text          = True,
    streaming_thinking      = True,
    tool_call_args_streaming= True,
    supports_session_persistence = False,
    supports_session_resume = False,
    supports_session_fork   = False,
    health_probe            = True,    # poll proc.returncode
    harness_id              = "claude-code",
    display_name            = "Claude Code",
)
```

### 7.5 Capability honesty in V0

Claude's protocol has more headroom than the V0 product exposes for a few
features, but the adapter reports only what is actually implemented:

1. `mid_turn_injection="queue"`. **Tier-1 V0 capability** per
   `findings-harness-protocols.md`. The adapter writes additional `user`
   NDJSON frames to stdin while a turn is in flight; Claude Code queues
   them and delivers at the next turn boundary. The composer stays enabled
   mid-turn and the UI shows a "queued for next turn" hint.
2. `supports_tool_approval_gating=False`. Claude runs with
   `--permission-mode bypassPermissions` in V0.
3. `supports_session_persistence=False`, `supports_session_resume=False`, and
   `supports_session_fork=False`. V0 is single-process and drop-on-restart,
   regardless of any Claude-internal session artifacts. **However**, the
   adapter still **captures Claude's internal session id** from the first
   `system.init` NDJSON frame and persists it on `SessionState`. This is
   zero-cost in V0 (just a field write) and unblocks V1's `claude --resume
   <id>` story without requiring an adapter rewrite. The capability flag
   stays false until V1 actually wires the resume path.

The abstract methods stay in the interface from day one. Unsupported V0
methods raise `CapabilityNotSupported`, which keeps the interface stable while
keeping the frontend honest.

### 7.6 Lifecycle mechanics

```python
async def start(self, params: StartParams) -> SessionHandle:
    cmd = self._build_command(params)
    self._proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **params.env, "CLAUDECODE": "1"},
        cwd=params.cwd,
    )
    self._reader_task = asyncio.create_task(self._reader())
    self._stderr_task = asyncio.create_task(self._stderr_drain())
    # Wait until the first assistant event yields the concrete session handle.
    self._handle = await self._await_handle(timeout_s=10)
    return self._handle

async def stop(self, *, grace_ms: int = 2000) -> None:
    if not self._proc:
        return
    try:
        self._proc.stdin.close()
        await asyncio.wait_for(self._proc.wait(), timeout=grace_ms / 1000)
    except asyncio.TimeoutError:
        self._proc.terminate()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            self._proc.kill()
    finally:
        self._reader_task.cancel()
        self._stderr_task.cancel()
        self._proc = None

async def health(self) -> HarnessHealth:
    if self._proc is None:
        return HarnessHealth.DEAD
    rc = self._proc.returncode
    if rc is None:
        return HarnessHealth.READY if self._handle else HarnessHealth.STARTING
    return HarnessHealth.DEAD
```

The reader task is the **only** consumer of stdout. The sender does **not**
read for replies — replies come back as events. This keeps SRP intact and
avoids the classic deadlock where two coroutines both try to read from the
same pipe.

## 8. OpenCodeAdapter — V1 sketch

Shorter because it isn't shipping in V0, but enough to prove the
abstraction is genuinely neutral.

### 8.1 Process / transport model

OpenCode runs as `opencode serve` — a separate HTTP server. The adapter
**does not own the process** in V1; it expects the user's `opencode serve`
to be reachable at a configured URL (or the adapter can launch one as a
subprocess and shut it down on `stop()`, decided in V1). The interesting
mapping is the protocol, not the process.

### 8.2 Lifecycle → HTTP

```python
async def start(self, params: StartParams) -> SessionHandle:
    if params.resume_session_id:
        # GET /session/:id verifies the session still exists
        await self._http.get(f"/session/{params.resume_session_id}").raise_for_status()
        sid = params.resume_session_id
    else:
        body = {
            "system": params.system_prompt,
            "agent": params.agent_profile_id,
            "model": params.model,
        }
        resp = await self._http.post("/session", json=body)
        sid = resp.json()["id"]
    self._sid = sid
    self._sse_task = asyncio.create_task(self._sse_reader())
    return SessionHandle(sid, "opencode", _now_ms())
```

### 8.3 Sender → HTTP endpoints

| Method | Endpoint |
|---|---|
| `send_user_message(text)` | `POST /session/:id/message` with `parts=[{type:"text",text}]` |
| `inject_user_message(text)` | `POST /session/:id/prompt_async` with the same body — opencode's documented mid-turn channel |
| `interrupt()` | `POST /session/:id/abort` |
| `approve_tool(req_id)` | `POST /session/:id/permission` `{request_id, behavior:"allow"}` |
| `deny_tool(req_id)` | `POST /session/:id/permission` `{request_id, behavior:"deny"}` |
| `cancel_tool(...)` | Not supported in opencode HTTP API (cancel happens via abort). Capability `cancel_tool=False`. |
| `submit_tool_result(tool_call_id, result_payload, status)` | `POST /session/:id/tool_result` with the normalized result payload. |

Notice: **the same `HarnessSender` interface, the same normalized command
union, totally different transport.** This is the LSP commitment paying off
on the V1 timeline.

### 8.4 Receiver → SSE

```python
async def _sse_reader(self) -> None:
    seq = 0
    async with self._http.stream("GET", "/global/event") as r:
        async for chunk in r.aiter_lines():
            if not chunk.startswith("data:"):
                continue
            payload = json.loads(chunk[5:].strip())
            for ev in self._translate_one(payload, seq):
                await self._emit(ev)
                seq += 1
```

OpenCode's `/global/event` SSE delivers events for **all** sessions on the
server; the adapter filters by `session_id == self._sid`. This is one of
the few opencode-specific quirks worth flagging — it leaks server-wide
state into a per-session adapter, and the filter must be tight.

**Scaling note (V0 only).** With one OpenCode session per shell process the
per-adapter SSE subscription is fine. When/if a single shell hosts multiple
concurrent OpenCode sessions (V1+), the per-session subscription pattern
becomes O(N²) — every adapter holds a SSE stream of all sessions and
discards N-1 of them. The V1+ fix is to **hoist `/global/event` into a
process-singleton** and fan out by `session_id` to per-session queues.
Out of scope for V0; flagged here so the V1 reviewer doesn't need to
re-derive it.

### 8.5 Capability declaration

```python
OpenCodeAdapter.capabilities = HarnessCapabilities(
    mid_turn_injection      = "http_post",  # POST /session/:id/prompt_async
    interrupt               = True,    # /abort
    supports_tool_approval_gating = True,    # native permission endpoint
    cancel_tool             = False,
    streaming_text          = True,
    streaming_thinking      = True,    # via "reasoning" parts
    tool_call_args_streaming= False,   # parts arrive complete in current docs
    supports_session_persistence = True,    # SQLite-backed
    supports_session_resume = True,
    supports_session_fork   = True,    # POST /session/:id/fork
    health_probe            = True,    # GET /session/:id
    harness_id              = "opencode",
    display_name            = "OpenCode",
)
```

The cleaner shape of opencode's protocol — explicit endpoints for every
operation, declarative permission model — is **why** the abstraction is
designed against it. Every method on `HarnessSender` has a clean opencode
mapping; every event in the union has a clean opencode source. Claude Code
fits, but it fits because the abstraction was built for the cleaner case.

## 9. CodexAppServerAdapter — V1 sketch (tier-1)

**Status update (p1135):** Codex `app-server` is a stable, documented
JSON-RPC 2.0 transport per developers.openai.com/codex/app-server. The
core protocol (`initialize`, `thread/start`, `thread/resume`, `turn/start`,
`turn/interrupt`, `item/*` notifications) is production-ready over stdio.
Only the WebSocket transport and specific opt-in methods are flagged
experimental, and we don't need them. Earlier framing of codex as
"reverse-engineered / TBD / deferred" is corrected here.

Companion's `web/server/codex-adapter.ts` and `web/CODEX_MAPPING.md` are an
MIT-licensed reference implementation with 28 unit tests and a full
JSON-RPC ↔ internal-event translation table. **Reference, not dependency.**
We pattern-match the translation and write our own adapter in Python
against our normalized event protocol.

### 9.1 Process / transport model

One long-lived child:

```
codex app-server --transport stdio
```

The adapter speaks JSON-RPC 2.0 framed messages over the child's stdin
and stdout. JSON-RPC requests carry an `id`; notifications do not. Replies
correlate by `id`.

### 9.2 Lifecycle → JSON-RPC

```python
async def start(self, params: StartParams) -> SessionHandle:
    self._proc = await asyncio.create_subprocess_exec(
        "codex", "app-server", "--transport", "stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **params.env},
        cwd=params.cwd,
    )
    self._reader_task = asyncio.create_task(self._reader())
    await self._call("initialize", {"clientInfo": {"name": "meridian-shell"}})
    await self._notify("initialized", {})
    if params.resume_session_id:
        result = await self._call("thread/resume", {"threadId": params.resume_session_id})
    else:
        result = await self._call("thread/start", {
            "model": params.model,
            "cwd": params.cwd,
            "approvalPolicy": "manual",      # gated by capability
            "sandbox": "workspace_write",
        })
    self._handle = SessionHandle(result["threadId"], "codex", _now_ms())
    return self._handle
```

### 9.3 Sender → JSON-RPC methods

| Method | JSON-RPC call |
|---|---|
| `send_user_message(text)` | `turn/start` with `{threadId, prompt:{type:"text",text}}` |
| `inject_user_message(text)` | `turn/interrupt` then `turn/start` with the new prompt — this is the `interrupt_restart` mode in `HarnessCapabilities.mid_turn_injection`. User-visible behavior is "current turn cancelled, new turn begins"; the UI surfaces this as a "this will interrupt the current turn" hint. |
| `interrupt()` | `turn/interrupt` with `{threadId}` |
| `approve_tool(req_id)` | Reply to the in-flight `item/*/requestApproval` request with `{decision:"approve"}` |
| `deny_tool(req_id)` | Reply to the in-flight `item/*/requestApproval` request with `{decision:"deny"}` |
| `cancel_tool(...)` | Not supported. Capability `cancel_tool=False`. |
| `submit_tool_result(tool_call_id, result_payload, status)` | Shell-owned tools (`python` kernel, interactive PyVista viewers, etc.) are registered with the codex thread as **MCP tools** at `thread/start` time, mirroring the `--mcp-config` path that ClaudeCodeAdapter uses. The codex `item/mcpToolCall` notification is the inbound side; the adapter responds to the in-flight MCP tool request with the normalized result payload via the same JSON-RPC reply channel. This keeps the shell-owned tool contract identical across all three adapters: `ToolExecutionCoordinator` runs the tool and calls `submit_tool_result()`, the adapter picks the wire mechanism (Claude `tool_result` stdin frame, codex MCP reply, opencode `POST /tool_result`). Codex-internal commands (`item/commandExecution`, `item/fileChange`) that the model invokes outside our MCP surface flow back to codex without round-tripping through us — those are not shell-owned tools and never reach `ToolExecutionCoordinator`. |

### 9.4 Receiver → JSON-RPC notifications

The adapter consumes server-sent JSON-RPC notifications from stdout:

| codex notification | Normalized event(s) |
|---|---|
| `turn/started` | `RunStarted` |
| `turn/completed` (stop=`end_turn`) | `RunFinished` |
| `turn/completed` (stop=`error`) | `RunError` |
| `item/agentMessage/start` | `TextMessageStart` |
| `item/agentMessage/delta` | `TextMessageContent` |
| `item/agentMessage/end` | `TextMessageEnd` |
| `item/reasoning` | `ThinkingStart` + `ThinkingContent` + `ThinkingEnd` (companion's adapter only handles bulk reasoning today; streaming `item/reasoning/delta` is a small follow-up) |
| `item/commandExecution`, `item/fileChange`, `item/mcpToolCall` | `ToolCallStart` + `ToolCallEnd` + `ToolCallResult` |
| `item/*/requestApproval` | `PermissionRequested` |
| `item/contextCompaction` | dropped at adapter, logged at debug (UI doesn't render this in V0/V1) |

### 9.5 Capability declaration

```python
CodexAppServerAdapter.capabilities = HarnessCapabilities(
    mid_turn_injection      = "interrupt_restart",  # turn/interrupt + turn/start
    interrupt               = True,    # turn/interrupt
    supports_tool_approval_gating = True,    # native item/*/requestApproval
    cancel_tool             = False,
    streaming_text          = True,
    streaming_thinking      = False,   # bulk reasoning only in companion's adapter; future enhancement
    tool_call_args_streaming= False,
    supports_session_persistence = True,    # threads are server-side
    supports_session_resume = True,    # thread/resume
    supports_session_fork   = False,   # not in core protocol
    health_probe            = True,
    harness_id              = "codex",
    display_name            = "Codex",
)
```

### 9.5.1 The shell-owned tool bridge (the load-bearing part)

The biomedical workflow depends on a **persistent Python kernel that
survives across turns** (4 GB DICOM volumes do not get re-loaded per cell).
Codex `app-server` runs its own command/file execution out of the box, but
the shell needs Codex's invocation of `python` (and the interactive
viewers) to land in our `ToolExecutionCoordinator` so the persistent kernel
and `result_helper` capture flow stay intact.

**The bridge is MCP.** At `thread/start` time, the adapter registers the
shell-owned tools (`python`, `bash`, `pick_points_on_mesh`,
`pick_box_on_volume`, etc.) as MCP tools advertised to the codex thread.
When Codex invokes one of these, it surfaces as an `item/mcpToolCall`
notification, the adapter routes it through the normalized `ToolCallStart` /
`ToolCallEnd` events, `ToolExecutionCoordinator` runs the tool against the
persistent kernel, and the result returns via `submit_tool_result()` →
the adapter's MCP reply on the same JSON-RPC channel.

This is the same shape as ClaudeCodeAdapter's `--mcp-config` path: shell
tools live behind one MCP surface that every adapter can register. Codex's
own command/file execution (`item/commandExecution`, `item/fileChange`)
remains for things the model calls **outside** our MCP surface — those are
not shell-owned tools and never reach `ToolExecutionCoordinator`.

**Why this matters for the V1 swap claim.** The "adding a new adapter is
one file" promise only holds if the new harness honors this MCP bridge.
Codex `app-server` does (it has first-class MCP support). A hypothetical
future harness that does not expose an MCP-equivalent registration surface
cannot serve as a tier-1 adapter for the biomedical use case without
inventing a substitute bridge — that would be a much bigger lift than one
new adapter file. The interface stays neutral; the bridge requirement is
documented honestly here so future adapter authors know what they're
signing up for.

### 9.6 Known gaps from companion's integration (acceptable for V1)

These match `findings-harness-protocols.md` §"Corrected Harness Picture":

- No runtime model switching — set once at `thread/start`
- No runtime permission/sandbox switching — set once at `thread/start`
- Token usage / cost tracking not yet extracted from `turn/completed`
  (small follow-up)
- Streaming reasoning is bulk-only — `item/reasoning/delta` not handled
- MCP/webSearch approval requests auto-accepted unless gated explicitly

### 9.7 Implementation order vs OpenCodeAdapter

Codex and OpenCode are **both V1-capable**. Order is a product decision —
whichever validation customer or use case shows up first. The interface in
this doc accommodates both, and the registry takes a `codex` and an
`opencode` factory in V1 regardless of order.

## 10. Capability negotiation

### 10.1 Backend-side

`SessionManager` reads `adapter.capabilities` once after `start()` and
caches it on the session record. Routes that want to send a capability-
gated command call `caps.assert_supports("interrupt")` and translate the
resulting `CapabilityError` into a structured wire error. Adapters
themselves are **also** allowed to raise `CapabilityError` from their
sender methods so that misconfigured callers fail loudly.

### 10.2 Frontend-side

On WebSocket connect, the gateway sends `SESSION_HELLO` with a
`SessionInfo.capabilities` snapshot. The frontend stores it in the session
store and queries it before rendering capability-bound UI. Mid-turn
injection branches on the **enum value** rather than a boolean, because
the user-visible behavior is genuinely different per mode:

```ts
// frontend
const caps = useSession((s) => s.capabilities);
{caps.supports_tool_approval_gating && <ApproveDenyButtons />}
{caps.interrupt && <InterruptButton />}

// mid-turn composer affordance — mode-aware, not boolean
switch (caps.mid_turn_injection) {
  case "queue":             // Claude — composer enabled, hint "queued for next turn"
  case "http_post":         // OpenCode — composer enabled, no hint
  case "interrupt_restart": // Codex — composer enabled, hint "this will interrupt the current turn"
  case "none":              // fallback — composer disabled mid-turn
}
```

If the user issues a command the active adapter doesn't support, the
backend responds with a `RUN_ERROR` whose `code` is `capability_unsupported`
and the frontend shows a toast. The session keeps running; nothing crashes.

### 10.3 Hot-swap of adapter

Out of scope for V0. Switching harness mid-session would require a
session-state translation layer between two adapters, and that's a V2+
problem at the earliest. The interface does not preclude it: a future
`SessionManager` could `stop()` adapter A and `start(resume_session_id=...)`
adapter B if both supported the same persisted format. Today they don't.

## 11. Edge cases and failure modes

The interface only earns its keep if it survives reality. Each of the
failure modes below has a concrete handling rule, not "TODO".

### 11.1 Subprocess dies unexpectedly (crash, OOM, kill)

- The reader task notices `proc.stdout` EOF.
- It emits `RunError(code="harness_dead", message=<last stderr line>, recoverable=False)`.
- It calls `self._mark_dead()` so `health()` returns `DEAD`.
- The receiver iterator yields the `RunError` and then terminates (the queue
  is closed). Downstream consumers see `StopAsyncIteration`.
- `SessionManager` sees `DEAD` on its next health probe, marks the session
  as crashed, and notifies the gateway. The frontend shows a "session
  crashed" banner with a "restart" button. Restart = `start()` a fresh
  adapter; resume only if `supports_session_persistence` is True and the prior
  session id is known.

### 11.2 Harness hangs (no output for N seconds)

- The adapter emits `HarnessHeartbeat` on a 5s timer if it hasn't emitted
  any other event. **Heartbeats do not consume `seq` in the gateway's
  reconnect buffer** — the gateway compresses runs of heartbeats and the
  frontend reducer treats `HarnessHeartbeat` as silent (no state mutation,
  just a "still alive" tick). This keeps the 30s reconnect window from
  filling with heartbeat noise on long-running tool calls. The gateway
  forwards a heartbeat to the WebSocket so the connection stays warm and
  the user sees an "agent is thinking" indicator.
- If silence exceeds a configurable threshold (default 120s), `health()`
  flips to `DEGRADED` and the gateway sends a soft warning. We do **not**
  auto-kill — biomedical analysis legitimately takes minutes for some tool
  calls. The user can `interrupt()` from the UI.
- If the user is also gone (no active WebSocket), `SessionManager` may
  decide to `stop()` the adapter after a longer timeout. That policy lives
  in `SessionManager`, not in the adapter.

### 11.3 Stdin/stdout desync (partial NDJSON line, SSE reconnect mid-event)

- Stdin: writes are line-buffered with explicit `\n` and locked. A partial
  line cannot be written.
- Stdout: `_reader` reads with `readline()`, which is by definition
  line-framed. A partial line means EOF, which is handled as §11.1.
- SSE (opencode): `httpx` SSE client handles reconnect transparently. If a
  reconnect drops in the middle of an event, opencode's protocol re-sends
  from the last delivered seq. The adapter trusts the seq and emits a
  `RunError(code="transport_lost", recoverable=True)` if it sees a gap.

### 11.4 User interrupt during tool execution

- Frontend dispatches `Interrupt`.
- Sender writes `control_request` (Claude) or `POST /abort` (opencode).
- Local execution layer also receives a cancel signal via its own channel
  (see [local-execution.md](./local-execution.md)) — the in-flight Python
  cell is aborted via the persistent kernel's interrupt mechanism.
- The adapter eventually sees a `RunFinished(stop_reason="interrupted")`.
- The frontend updates the activity stream to show the cancelled state.

The abstraction's job here is to **deliver the interrupt**, not to
coordinate with local execution. Coordination is `SessionManager`'s job and
is documented in [event-flow.md](./event-flow.md).

### 11.5 User disconnects WebSocket mid-turn

- The session **does not stop**. The adapter keeps running. Events keep
  piling into its outbound queue.
- The queue has a configurable bounded size (default 10_000 events). If it
  fills, oldest events are dropped and a `RunError(code="event_overflow",
  recoverable=True)` is emitted; the next reconnect sees the error and
  knows it has missed events. (V0 acceptable; V1 may add per-event
  persistence.)
- On reconnect, the frontend re-subscribes and the gateway flushes the
  queue from the position the client last acked.

### 11.6 Server restart mid-turn

- V0 explicitly **does not persist mid-turn state**. The session is lost.
  On next start, the user begins a new session. The frontend shows a
  "previous session ended unexpectedly" banner.
- V1 with `supports_session_persistence=True` adapters can do better: on restart,
  `SessionManager` reads the persisted session list and presents
  resume-able sessions; a resume calls `start(resume_session_id=...)`.
- We document this honestly so V0 users (Dad) aren't surprised.

### 11.7 Malformed event from harness

- The `_reader` `try/except json.JSONDecodeError` handles parse failures.
- The adapter emits `RunError(code="malformed_event", recoverable=True)`
  and continues consuming the stream. One bad line does not kill the
  session.
- If five consecutive lines are malformed, the adapter flips to `DEGRADED`
  and emits a fatal `RunError(code="harness_corrupt", recoverable=False)`.
  The threshold is configurable.

### 11.8 Tool approval timeout

- Adapter that supports `supports_tool_approval_gating` includes `timeout_ms` on the
  `PermissionRequested` event so the frontend can render a countdown.
- If the user does nothing, the **adapter** is responsible for the timeout
  policy — it sends an automatic deny on its underlying transport. The
  default is 5 minutes; configurable.
- The denied tool flows through normally as
  `ToolCallResult(status="error", error="approval_timeout")`.

### 11.9 Concurrent commands during a turn

- Sender methods are async; multiple coroutines may call them. The adapter
  serializes writes via an internal lock.
- Ordering: `interrupt` is processed before any queued `send_user_message`
  in the same batch. `inject_user_message` is processed in arrival order.
- The adapter never reorders events on the receive side.

### 11.10 Resume after a fork

- `start(resume_session_id=X, fork=True)` creates a new branch off X.
- The new `SessionHandle.session_id` is the **forked** id, not X.
- Events on the new session are independent of X.
- Whether forks are visible across sessions is opencode's / Claude Code's
  problem; the abstraction just exposes the flag.

## 12. What this doc deliberately does NOT cover

To keep one concept per doc:

- **Tool execution** — how the agent's `python` and `bash` tools actually
  run, how the persistent kernel works, how `result.json` is captured.
  See [local-execution.md](./local-execution.md) and
  [interactive-tool-protocol.md](./interactive-tool-protocol.md).
- **Frontend wire format** — envelope shape, wire event names, binary
  framing for meshes, work item subscription model. See
  [frontend-protocol.md](./frontend-protocol.md).
- **Event routing** — how `EventRouter`, `TurnOrchestrator`, and
  `ToolExecutionCoordinator` cooperate, how outbound events fan out, and how
  the translator does its rename pass. See [event-flow.md](./event-flow.md).
- **Agent profile loading** — how `.agents/` is read, how
  `data-analyst` becomes the `agent_profile_id` field on `StartParams`,
  how skills get inlined into Claude's `--append-system-prompt`. See
  [agent-loading.md](./agent-loading.md).
- **FastAPI WebSocket layer** — gateway concerns, subscription multiplexing,
  REST endpoints. See [frontend-protocol.md](./frontend-protocol.md) and
  the gateway section of the overview.
- **Session manager policy** — restart policy, idle timeout, persistence,
  multi-session limits. The adapter is the mechanism; the manager is the
  policy. See `event-flow.md` once it lands; `SessionManager` is named
  there but its policy doc is TBD.

The boundary discipline is the point: this doc is the contract for one
seam, and only one seam. Everything that crosses that seam is named and
typed; everything that doesn't is somebody else's doc.

## 13. Open questions (for review)

- **Should `inject_user_message` and `send_user_message` collapse into one
  method?** Argument for: simpler surface. Argument against (current
  position): different acceptance semantics, capability gating, and the
  opencode endpoint is literally a different URL. Keep them split unless a
  reviewer makes a strong case.
- **Should `DisplayResult` carry the payload inline or always reference a
  file?** Current position: always reference. Aligns with biomedical-mvp
  result_helper, keeps WebSocket frames small, lets binary mesh data ride
  the existing binary frame channel. Inline-payload variant deferred until
  a use case demands it.
- **Should the adapter own its subprocess for opencode, or assume an
  external `opencode serve`?** Current position: V1 decides; either is
  compatible with the interface. Lean toward "adapter owns it, opt out via
  config" so single-user laptop installs work without extra setup.
- **Should `HarnessHeartbeat` be a normalized event or a separate channel?**
  Current position: normalized event. Heartbeats need to ride the same
  ordering as everything else so the gateway can use them as keepalive
  markers without a second pipe. The cost is one trivial event type.
- **Should we support `cancel_tool` at all in V0?** Neither Claude Code nor
  opencode supports it cleanly today. Codex `app-server` does not expose
  per-tool cancel either — only `turn/interrupt`. We can drop the method
  entirely if it's never used; keeping it documents the design intent in
  case a future harness exposes it.

- **Should `meridian spawn` route through this same `HarnessAdapter`?**
  *(Added by p1135.)* Today `meridian spawn` shells out via the
  single-shot adapters in `src/meridian/lib/harness/`. If the spawn
  lifecycle migrates onto the session-lived adapter family in
  `src/meridian/shell/adapters/`, every spawn in the dev-orchestration
  tree gains a mid-turn control channel for free — `meridian spawn inject
  <spawn_id> "reconsider X"` becomes harness-agnostic, and dev
  orchestrators can steer their children using the same primitive the UI
  uses. **Strong recommendation per `findings-harness-protocols.md`: yes.**
  See `synthesis.md` Q7 for the user decision.

## 14. Verification checklist

This abstraction is "right" if all of the following hold:

- [ ] Adding `OpenCodeAdapter` requires changes to **only** one new file
      under `src/meridian/shell/adapters/` and one line in `build_default_registry`.
- [ ] `FrontendTranslator`, `EventRouter`, `SessionManager`, the FastAPI
      gateway, and the frontend require **zero** changes to ship V1.
- [ ] A `FakeHarnessAdapter` exists in `tests/harness/` that implements all
      three protocols and is used in at least the gateway-level tests.
      This guards OCP from silent rot before V1.
- [ ] No file outside `src/meridian/shell/adapters/` imports any concrete adapter
      class. (`grep -r "from meridian.shell.adapters.claude_code" src/meridian/shell/`
      should match exactly one place: `registry.py`.)
- [ ] No event in the union has a Claude-specific name. ("content_block",
      "stream_event", "system/init" never appear.)
- [ ] No method on `HarnessSender` has a Claude-specific argument. No
      `permission_mode` enum, no `--sdk-url`, no `request_id` shape that
      assumes a UUID format.
- [ ] Capability flags accurately reflect each adapter's honest behavior.
      `supports_tool_approval_gating=False` for ClaudeCodeAdapter in V0 is a feature, not a
      bug — lying here is what causes silent capability rot.
- [ ] The receiver iterator terminates cleanly on `stop()`, `RunFinished`
      with no follow-up turn, and `RunError(recoverable=False)`. None of
      these leak background tasks.

If any of these fail, the abstraction is wrong and needs revision before
implementation lands. This is the most load-bearing doc in the design;
the verification gate is intentionally strict.
