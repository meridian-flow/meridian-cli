# Harness Adapter Abstraction

> What this is: the target shape of the meridian-channel harness
> adapter interface after the D36/D37 refactor.
>
> What this is not: the AG-UI event schema (lives in
> [`../events/`](../events/) and ultimately in meridian-flow), or the
> per-harness translation rules (lives in [`adapters.md`](adapters.md)).

Up: [`overview.md`](overview.md).

## Three New Adapter Responsibilities

Today's `SubprocessHarness` protocol in `src/meridian/lib/harness/adapter.py`
covers command building, env setup, and post-hoc artifact extraction.
The refactor adds three orthogonal responsibilities:

1. **Emit AG-UI events on an output channel** — translate this harness's
   wire format into the canonical AG-UI event taxonomy and push events
   onto the spawn's stdout AG-UI channel **as they happen**, not after
   the run completes.
2. **Accept FIFO control frames** — read normalized control frames
   (`user_message`, `interrupt`, `cancel`) from the per-spawn control
   FIFO and dispatch them through the harness-native injection
   mechanic. The FIFO is the **single authoritative control ingress**;
   the streaming spawn does not multiplex stdin as a control channel
   (see [`mid-turn-steering.md`](mid-turn-steering.md) for the
   ownership story).
3. **Report capabilities honestly** — extend `HarnessCapabilities` so
   the consumer (CLI, frontend, dev-workflow orchestrator) can render
   the right affordance for what this harness can actually do
   mid-turn. Capabilities are reported **out-of-band via `params.json`**
   at spawn-launch time, not as an on-wire AG-UI event — meridian-flow
   owns the AG-UI taxonomy and meridian-channel does not unilaterally
   add events to it (see "Capability reporting via `params.json`"
   below).

These three responsibilities sit alongside the existing ones, not on
top of them. The existing artifact contracts (`report.md`,
`output.jsonl`, `stderr.log`, session-id extraction, `extract_usage`,
`extract_report`) keep working unchanged — that is what the existing
dogfood workflow depends on.

## Existing Surface That Stays

| Today (in `adapter.py`) | Refactor disposition |
|---|---|
| `class HarnessCapabilities(BaseModel)` | **extends** — adds `mid_turn_injection` and a few honesty flags |
| `class RunPromptPolicy(BaseModel)` | unchanged |
| `class SpawnParams(BaseModel)` | unchanged (streaming mode signaled via launch metadata, not by mutating SpawnParams) |
| `class McpConfig(BaseModel)` | unchanged |
| `class StreamEvent(BaseModel)` | unchanged — kept as the **internal** parsed-line type used by `launch/stream_capture.py`. AG-UI events are a separate model. |
| `class SpawnResult(BaseModel)` | unchanged |
| `class SubprocessHarness(Protocol)` (and `BaseSubprocessHarness`) | **extends** — adds AG-UI emission method, control-frame dispatch method, capability surface |
| `class InProcessHarness(Protocol)` | unchanged. `direct.py` keeps `supports_stream_events=False` and is **out of scope** for this refactor. |
| `class ConversationExtractingHarness(Protocol)` | unchanged |
| `class ArtifactStore(Protocol)`, `class PermissionResolver(Protocol)` | unchanged |
| `def resolve_mcp_config(...)` | unchanged |

The interface is grown, not replaced. Every existing call site
(`launch/runner.py`, `launch/process.py`, `ops/spawn/execute.py`, the
test suite) continues to work against the unchanged half of the
protocol.

## New Surface

### Event emission

AG-UI emission happens **inside the adapter**, not in a post-hoc layer.
The shared model + emitter live in a new sibling module:

```
src/meridian/lib/harness/ag_ui_events.py
```

`ag_ui_events.py` owns:

- The AG-UI event Pydantic models — one per event type from
  meridian-flow's canonical taxonomy: `RUN_STARTED`, `STEP_STARTED`,
  `THINKING_*`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `TOOL_OUTPUT`,
  `TOOL_CALL_RESULT`, `DISPLAY_RESULT`, `RUN_FINISHED`. **No
  meridian-channel-only events.** Capability discovery happens
  out-of-band via `params.json`; control errors and acks are written
  to `control.log` and surfaced through CLI exit codes (see
  [`mid-turn-steering.md`](mid-turn-steering.md)). meridian-channel
  cannot mint new event types in the AG-UI vocabulary because
  meridian-flow owns the schema (D36).
- A small `AgUiEmitter` interface that adapters call into:
  `emit(event: AgUiEvent)`. The concrete emitter writes JSONL to the
  spawn's AG-UI sink (stdout in `--ag-ui-stream` mode, a per-spawn
  artifact file in non-streaming mode for replay).
- **No per-tool render config model.** Per-tool render config is
  frontend-resident in meridian-flow's `toolDisplayConfigs` dictionary
  (see [`adapters.md`](adapters.md)); meridian-channel's wire format
  carries only `{toolName, toolCallId}` on `TOOL_CALL_START` and the
  reducer looks up the config by tool name. The adapters do not ship a
  per-tool config table.

> **Sprawl risk note (deferred to implementation).** If `ag_ui_events.py`
> grows past ~300 LoC or accumulates more than three responsibilities
> (types, emitter wiring, display-result synthesis helpers), split it
> into `ag_ui_types.py` (Pydantic models only) plus
> `ag_ui_emitter.py` (sink + serialization). Keep the design as one
> module for now — revisit during the implementation pass once the real
> shape is visible.

> **Reference, do not duplicate.** `ag_ui_events.py` defines a Python
> type model that **mirrors** the AG-UI taxonomy from
> [`meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md).
> When that taxonomy gains a field, the Python model gains a field. The
> taxonomy itself is **not** redefined here.

The adapter's responsibility is translation, not invention. Each
adapter reads its harness's wire frames and calls
`emitter.emit(...)` with the corresponding AG-UI event. The
translation rules per harness live in
[`../events/harness-translation.md`](../events/harness-translation.md)
(written by Architect B).

The new method on `SubprocessHarness` is roughly:

```python
async def stream_ag_ui_events(
    self,
    *,
    raw_lines: AsyncIterator[str],   # already framed by stream_capture
    spawn_id: SpawnId,
) -> AsyncIterator[AgUiEvent]:
    """Translate harness wire frames into AG-UI events.

    Yields AG-UI events as the harness produces them. The runner
    (`launch/runner.py`) consumes the iterator and forwards events to
    the configured sink (stdout JSONL in `--ag-ui-stream` mode, a
    sibling artifact file otherwise). Lifecycle / finalization /
    `SpawnResult` derivation stays where it is today — this method does
    not own those concerns.

    Adapters override; the base class is a no-op for backward compat.
    """
```

The architectural commitment is "translation runs **inside the
adapter**, returning an async iterator of typed events. The runner owns
sink wiring and finalization; the adapter owns translation only." This
keeps `stream_ag_ui_events` a pure raw-wire → AG-UI events boundary and
preserves the existing `launch/runner.py` ownership of `SpawnResult`,
`report.md`, exit codes, and the artifact contract. The
`launch/stream_capture.py` bridge already has a generic event-observer
callback hook (per the touchpoints map); that hook is where the
per-line stream is teed into the adapter's translator.

### FIFO control surface

The control frame model lives in a second new sibling module:

```
src/meridian/lib/harness/control_channel.py
```

`control_channel.py` owns:

- The `ControlFrame` Pydantic model and its three concrete subtypes
  (`UserMessageFrame`, `InterruptFrame`, `CancelFrame`). Field shapes
  and the `version` field are pinned in
  [`mid-turn-steering.md`](mid-turn-steering.md).
- A `ControlFrameParser` that validates a JSONL line and yields a
  typed frame, raising on schema violations.
- A `ControlDispatcher` interface adapters implement: a single
  `dispatch(frame: ControlFrame) -> None` (or async equivalent) that
  is called when a new frame arrives. The dispatcher owns the
  harness-native translation: stream-json frame written to the
  **harness's** stdin for Claude, `turn/interrupt` + `turn/start` for
  Codex, HTTP POST for OpenCode.

The **FIFO reader** (the actual `os.open(fifo_path, O_NONBLOCK |
O_RDONLY)` plumbing and the read loop that yields raw lines) lives in
the launch layer, alongside the existing subprocess plumbing — see
`lib/launch/control_fifo.py` (new) or as an extension to the streaming
launch branch in `lib/launch/process.py`. **Position**: FIFO opening
and tailing is launch-process plumbing, not adapter concern;
`harness/control_channel.py` stays pure types + parser. This mirrors
the outbound side, where `lib/launch/stream_capture.py` is the
plumbing bridge while the AG-UI types live in `harness/ag_ui_events.py`.

The shared piece is the **frame format and validation** — the same
JSONL shape on the wire, the same parser, the same version field. The
adapter-specific piece is the dispatcher implementation. This split is
deliberate per the touchpoints map: the three harnesses have different
runtime semantics for the same control frame, so the dispatch cannot
sit in `common.py`, but the parse-and-validate path absolutely should
be shared.

### Capability surface

`HarnessCapabilities` (in `adapter.py` today) gains a small set of
honesty fields. **The new fields use a flat shape with no `supports_`
prefix**, because they describe semantic capabilities, not boolean
gates. The existing legacy `supports_*` fields stay as-is for backward
compat with non-refactored code paths but are NOT broadcast on the
wire and are NOT part of the streaming-spawn capability bundle. The
new fields are the canonical streaming-mode capability surface:

```python
class HarnessCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    # ... existing legacy fields stay (used by non-streaming code paths) ...
    supports_stream_events: bool = True
    supports_stdin_prompt: bool = False
    supports_session_resume: bool = False
    supports_session_fork: bool = False
    supports_native_skills: bool = False
    supports_native_agents: bool = False
    supports_programmatic_tools: bool = False
    supports_primary_launch: bool = False
    reference_input_mode: Literal["inline", "paths"] = "paths"

    # NEW — D37 / findings-harness-protocols.md.
    # Flat shape, no `supports_` prefix. This is the canonical
    # streaming-mode capability surface, identical across every
    # surface (params.json, the in-process Python class, and any
    # downstream consumer that reads it).
    mid_turn_injection: Literal[
        "queue",             # Claude — write user frame, harness queues for next boundary
        "interrupt_restart", # Codex — call interrupt then start a new turn with the new prompt
        "http_post",         # OpenCode — POST to live session message endpoint
        "none",              # adapter does not implement injection in this build
    ] = "none"
    runtime_model_switch: bool = False
    runtime_permission_switch: bool = False
    structured_reasoning_stream: bool = False
    cost_tracking: bool = True
```

`mid_turn_injection` is a **semantic enum** because the wire-level
behavior is honestly different across the three harnesses, and the UI
needs to render the difference. Per the
[findings doc](../../findings-harness-protocols.md): a Claude user sees
"message queued for next turn"; a Codex user sees "this will interrupt
the current turn"; an OpenCode user sees a normal send button. **Don't
lie about wire-level behavior to fake uniformity.**

There is no `supports_interrupt` or `supports_cancel` field. Cancel
semantics are handled at the lifecycle layer (every adapter must tear
down its harness subprocess on a `CancelFrame` — that is a contract,
not a capability). Interrupt semantics fold into the `mid_turn_injection`
enum: a `queue` adapter cannot interrupt cleanly, an `interrupt_restart`
adapter is the interrupt primitive, an `http_post` adapter routes
interrupt through whatever the session API exposes (or rejects the
frame with a control-log entry — see
[`mid-turn-steering.md`](mid-turn-steering.md)).

`cost_tracking` and `structured_reasoning_stream` are honesty flags
called out by the findings doc — Codex's companion-style adapter
doesn't surface per-token usage or `item/reasoning/delta` streaming
today, so the adapter declares that and the consumer renders
accordingly.

### Capability reporting via `params.json`

Capabilities are written to the per-spawn `params.json` artifact at
spawn-launch time, not as an on-wire AG-UI event. `params.json` is
already a load-bearing per-spawn artifact (per
[`../refactor-touchpoints.md`](../refactor-touchpoints.md)): every
existing dry-run / `spawn show` / debugging surface reads it. Adding a
`capabilities` block to it is a low-cost extension that does not
require meridian-flow to bless a new event type.

The capability bundle in `params.json` looks like:

```json
{
  "spawn_id": "...",
  "agent": "...",
  "harness": "claude",
  "control_protocol_version": "0.1",
  "capabilities": {
    "mid_turn_injection": "queue",
    "runtime_model_switch": false,
    "runtime_permission_switch": false,
    "structured_reasoning_stream": true,
    "cost_tracking": true
  }
}
```

Any consumer that needs to know what mid-turn semantics this spawn
exposes — the Go backend rendering an affordance, the dev-workflow
orchestrator deciding whether to show "queued for next turn" — reads
`params.json` once at spawn-attach time. The live AG-UI event stream
stays pure: it carries only events from meridian-flow's canonical
taxonomy.

> **Future migration.** If meridian-flow later blesses a canonical
> `CAPABILITY` event in its AG-UI taxonomy, meridian-channel can start
> emitting it on the wire as the first event after `RUN_STARTED`. The
> event payload would be the same `capabilities` object that lives in
> `params.json` today. Until that conversation has happened, the bundle
> lives in `params.json` only — meridian-channel does not unilaterally
> mint new events in the AG-UI vocabulary (D36).

## What Does Not Change

- **`InProcessHarness` and `direct.py`** stay exactly as they are.
  The in-process Anthropic Messages API adapter does not participate
  in subprocess streaming; its `supports_stream_events=False` flag is
  a useful sentinel and stays. If we ever want streaming AG-UI from
  `direct.py`, that is a separate work item with very different
  trade-offs (no subprocess, no wire format to translate, native
  Python event objects). Reviewers should not flag direct.py as a
  gap — it is an explicit non-goal here.
- **`StreamEvent`** stays as the internal parsed-line type used by
  `launch/stream_capture.py`. The pre-existing parsing pipeline is
  load-bearing for `output.jsonl`, `report.md` extraction, and the
  fallback chain in `launch/extract.py` and `launch/report.py`. AG-UI
  events are a **second** event family the same line stream
  produces, not a replacement for `StreamEvent`.
- **`SpawnResult`** stays as the post-hoc summary returned at the end
  of a non-streaming spawn. Streaming spawns still emit a
  `RUN_FINISHED` event and write the same `report.md`/`output.jsonl`
  artifacts; `SpawnResult` is the in-process tail of that for
  callers that ran a non-streaming `meridian spawn create`.
- **`SpawnParams`** stays. Streaming-mode invocation lives in
  `launch_types.py` (a streaming launch flavor) so the prepared-plan
  and dry-run paths in `ops/spawn/prepare.py` and `ops/spawn/models.py`
  do not have to learn a new prompt-assembly shape.
- **`registry.py`** stays unless typing forces a small registration
  update for the new capability.

## Extension Points That Are Out Of Scope

- **A second `HarnessAdapter` family** for interactive vs batch tools.
  Not needed; the streaming-mode launch flavor handles the difference.
- **Approval gating** as a new method. Approvals stay in the existing
  permissions resolver path. The findings doc notes Codex's
  `item/*/requestApproval` requests; for V0 the Codex adapter
  auto-accepts (matching companion's posture) and surfaces approval
  events on the AG-UI stream as `TOOL_CALL_START` with metadata. Real
  approval gating is a follow-up.
- **Runtime model switching as an `inject_model` control frame.** Not
  in V0 — none of the three harnesses support it natively (per
  findings), and faking it would mean restarting the harness, which
  is what `cancel` + new spawn already does.

## Source File Map

| File | Status | Why |
|---|---|---|
| `harness/adapter.py` | extends | New methods on `SubprocessHarness`, new fields on `HarnessCapabilities`, new defaults on `BaseSubprocessHarness` |
| `harness/ag_ui_events.py` | **new** | AG-UI event model + emitter interface + per-tool config model |
| `harness/control_channel.py` | **new** | Control frame model + reader + dispatcher interface |
| `harness/launch_types.py` | extends | Streaming-mode launch flavor metadata |
| `harness/common.py` | extends carefully | Shared parse helpers grow; **do not** become the dumping ground for adapter-specific translation |
| `harness/transcript.py` | unchanged | Stays text-only; AG-UI is wire-format, not transcript |
| `harness/direct.py` | **unchanged** | In-process; out of scope |
| `harness/registry.py` | unchanged or trivial | Typing update only if needed |

For consumers (`launch/`, `lib/state/`, `lib/ops/spawn/`, `cli/`), see
[`../refactor-touchpoints.md`](../refactor-touchpoints.md). The
abstraction grows where the abstraction lives; the consumers grow
where the streaming-mode launch and `meridian spawn inject` plumbing
needs them.
