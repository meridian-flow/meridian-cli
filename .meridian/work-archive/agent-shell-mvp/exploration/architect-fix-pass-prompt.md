# Architect fix pass: resolve review findings on agent-shell-mvp design tree

## Context

The `agent-shell-mvp` design tree was rewritten by two architects (A on overview+harness, B on events) and then reviewed by three independent reviewers:

- **p1163** (gpt-5.4, design alignment)
- **p1164** (opus, external contract fidelity — this one was sharpest)
- **p1165** (gpt-5.2, refactor / structural)

All three converged on the same substantive findings. Your job is to resolve them in a **single focused editing pass** across the affected docs. This is NOT a rewrite — the structural core is sound (AG-UI translation at the adapter boundary, sibling modules `ag_ui_events.py` / `control_channel.py`, additive artifact model, FIFO-based injection). The fix pass corrects schema drift, unifies contradictory claims, and fills missing edge-case coverage.

## What you must read first

1. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 — basis decisions
2. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — harness authority
3. `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md` — 37-file impact map
4. **The canonical meridian-flow contract** (you MUST read these — the blockers all come from drift against them):
   - `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md`
   - `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md` — **especially §"Per-Tool Display Config" at lines ~104–130**; this is where `ToolDisplayConfig` is actually defined
   - `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md`
5. The three review reports (read them, don't just trust this brief):
   - `.meridian/spawns/p1163/report.md`
   - `.meridian/spawns/p1164/report.md`
   - `.meridian/spawns/p1165/report.md`
6. The current state of the design tree:
   - `$MERIDIAN_WORK_DIR/design/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/{overview,abstraction,adapters,mid-turn-steering}.md`
   - `$MERIDIAN_WORK_DIR/design/events/{overview,flow,harness-translation}.md`

## Blockers you must resolve

### B1 — Remove `CAPABILITY` / `CONTROL_RECEIVED` / `CONTROL_ERROR` from the on-wire AG-UI event stream

**Problem**: The design invents these as AG-UI events. They are NOT in meridian-flow's canonical taxonomy. D36 says meridian-flow owns the schema; we reference, not fork.

**Resolution**: Do not emit them as AG-UI events. Carry the information out-of-band:

- **Capability bundle**: write to the existing `params.json` under `.meridian/spawns/<id>/` at spawn-launch time (touchpoints map confirms `params.json` is already a load-bearing per-spawn artifact). The frontend or any consumer can read it once at session start — it does not belong in the live event stream. Propose an optional future migration: "if meridian-flow later blesses a canonical `CAPABILITY` event, meridian-channel can start emitting it on the wire; until then, it lives in `params.json`."
- **Control error**: write a structured line to the existing `stderr.log` (or a new `.meridian/spawns/<id>/control.log` sibling if you think that's cleaner — pick one and be consistent). Do NOT emit a `CONTROL_ERROR` AG-UI event. The injecting CLI process (`meridian spawn inject`) gets synchronous feedback from its write to the FIFO; async notification to the streaming consumer happens by reading `control.log` / `stderr.log`.
- **Control ack**: remove `CONTROL_RECEIVED` entirely. The CLI writer has synchronous confirmation (FIFO write succeeded or failed); the streaming consumer does not need an event for every received control frame. If visibility is important, add a control-log line.

Apply this to:
- `events/flow.md` — remove CAPABILITY/CONTROL_* from the event sequence table and the "Capability Event Placement" section. Explicitly state the out-of-band carriers.
- `events/harness-translation.md` — remove these rows from mapping tables.
- `harness/abstraction.md` — the `HarnessCapabilities` Python type stays (it's an in-process value), but the wire emission is out-of-band via `params.json` at launch time. Rename any section like "AG-UI capability event" to "Capability reporting via `params.json`".
- `harness/mid-turn-steering.md` — replace async `CONTROL_ERROR` with control-log writes + synchronous CLI return codes. Update the error-reporting resolution for D37 Q3 accordingly.

### B2 — Strip per-tool config from `TOOL_CALL_START` payload

**Problem**: The design invents a `config: {input, stdout, stderr}` field on `TOOL_CALL_START`. Two problems:
1. meridian-flow's canonical `ToolDisplayConfig` uses different field names and types: `{inputCollapsed: boolean, stdoutCollapsed: boolean, stderrMode: "collapsed" | "hidden-popup" | "inline", producesResults: boolean, label?: string, icon?: React.ComponentType}`. Read `component-architecture.md` lines 89–130 for the exact shape.
2. More fundamentally, meridian-flow does NOT carry this config on the wire at all. It's a frontend-resident `toolDisplayConfigs: Record<string, ToolDisplayConfig>` lookup table keyed by `toolName`. The wire format carries `{toolCallId, toolName}` and (in tool_call_args) the arguments. The config is resolved by the reducer via dict lookup.

**Resolution**: Remove the `config` field from `TOOL_CALL_START` entirely. Replace the "Per-Tool Behavior Config Attachment" section in `events/flow.md` with a one-paragraph note: "Per-tool render config is frontend-resident in meridian-flow's `toolDisplayConfigs` dictionary, keyed by `toolName`. meridian-channel's wire format carries only `{toolCallId, toolName}` on `TOOL_CALL_START`; the reducer looks up the config. See `component-architecture.md` §'Per-Tool Display Config'."

Then replace the "per-tool render config" tables in `harness/adapters.md` and the matching tables in `events/harness-translation.md` with a **coordination checklist** section:

> "meridian-flow's `toolDisplayConfigs` must contain entries for the following tools that meridian-channel's adapters expose. Where a tool is not yet in `toolDisplayConfigs`, opening a meridian-flow PR to add the entry is a prerequisite for the local-deployment path to work cleanly."

List the tools per harness (Claude's `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob`, `Task`, `WebFetch`, `WebSearch`, `TodoWrite`; Codex's tool set; OpenCode's tool set). You don't have to invent config values for each — that's meridian-flow's call. Just enumerate "these tools exist, their entries need to be added."

### B3 — Pick one authoritative control ingress: FIFO only

**Problem**: The current design simultaneously describes "stdin JSONL control" and "per-spawn FIFO control" as control inputs, which implies multiplexed concurrent channels without a defined ordering rule. This is a correctness hazard.

**Resolution**: **FIFO is the single authoritative control ingress.** Stdin is not a control channel at all in streaming mode — the streaming spawn closes its stdin after startup (or uses it only for one-shot initial prompt, not for control frames). `meridian spawn inject` always writes to `.meridian/spawns/<id>/control.fifo`. Dev-workflow orchestrators that used to write to stdin in the proposed design switch to writing to the FIFO via the `meridian spawn inject` CLI or by opening the FIFO directly.

Update:
- `overview.md` — "stdin control protocol" → "FIFO-based control protocol". The stdin control wording in "three deliverables" is misleading; fix it.
- `harness/mid-turn-steering.md` — rewrite the "Stdin Ownership Question" section. The new answer to D37 Q1 is: **FIFO is the single ingress; the streaming spawn does not use stdin as a control channel**. Explain the tradeoff you're rejecting (stdin convenience for quick testing) and why FIFO wins (works from any process, decouples from PTY-vs-pipe launch distinction, makes injection race-free per spawn).
- `harness/abstraction.md` — the `control_channel.py` reader reads from the FIFO, not from stdin. Update accordingly.
- Consider whether `harness/control_channel.py` should even live in `harness/` or in `launch/` — if it's a FIFO reader, it's closer to launch plumbing than to adapter concern. Take a position and note it.

### C1 — Unify capability shape across all docs (drop `supports_` prefix)

**Problem**: Four different shapes for the capability object across `events/flow.md`, `harness/mid-turn-steering.md`, `harness/abstraction.md`, `events/harness-translation.md`.

**Resolution**: Single shape, flat, no `supports_` prefix. The fields are:

```python
@dataclass
class HarnessCapabilities:
    mid_turn_injection: Literal["queue", "interrupt_restart", "http_post", "none"]
    runtime_model_switch: bool
    runtime_permission_switch: bool
    structured_reasoning_stream: bool
    cost_tracking: bool
```

Propagate this exact shape across:
- `harness/abstraction.md` (the Python class)
- `events/harness-translation.md` (the dataclass)
- `harness/mid-turn-steering.md` (any prose that references field names)
- `events/flow.md` — since CAPABILITY is no longer on-wire, this becomes "the `capabilities` field inside `params.json`". Use the same field names.

### C2 — Resolve internal contradictions

- **Codex structured reasoning**: `adapters.md` says "false in V0", `harness-translation.md` says "true/planned". Pick **"false in V0, future upgrade"** based on `findings-harness-protocols.md` (companion's adapter does not yet stream `item/reasoning/delta`). Apply consistently.
- **Claude `supports_interrupt`**: `mid-turn-steering.md` line ~149 hard-codes `true` but line ~386 says Claude V0 should be `false`. Apply **false** (Claude queues, it does not interrupt) per findings-harness-protocols.md. There's no `supports_interrupt` field in the unified capability shape above — it's `mid_turn_injection: "queue"` for Claude, which is the honest surface. Remove any remaining `supports_interrupt` references.

### C3 — Add an explicit "Failure modes and edge cases" section to `harness/mid-turn-steering.md`

The design is required by /dev-principles to enumerate failure modes and edge cases explicitly. Add a section covering:

- **Harness subprocess dies mid-stream**: the AG-UI consumer sees the stream terminate abruptly (TCP-level close), `report.md` extraction still runs on the partial `output.jsonl`, `reaper.py` marks the spawn as crashed. FIFO writers get `EPIPE` on further writes and the CLI returns a failure exit code.
- **AG-UI consumer disconnects but harness keeps running**: the spawn continues. AG-UI events buffer briefly in the writer (or drop once buffer full — decide which and state it), control frames still work via FIFO, `report.md` still finalizes at natural turn end. Reconnection by a new consumer is NOT in scope for V0 — they can read `output.jsonl` and `report.md` after the fact.
- **Two `meridian spawn inject` commands race against the same spawn**: FIFO writes are atomic up to `PIPE_BUF` (4096 bytes on Linux) for JSONL frames. Frames larger than that can interleave; the design should specify a max frame size < `PIPE_BUF` and document that the CLI rejects larger frames. Ordering between two racing injectors is first-come-first-served by the kernel; there's no priority mechanism.
- **Control frame arrives during `--from` / `--fork`**: `--from` continues an existing spawn; if the existing spawn is in streaming mode, its FIFO is still the authoritative ingress and control frames route normally. `--fork` creates a new spawn; the new spawn gets a new FIFO. Mid-turn control frames that arrive after the parent has been forked go to the parent's FIFO, not the child's. Document this cleanly.
- **FIFO does not exist yet when CLI tries to inject**: the CLI checks `.meridian/spawns/<id>/control.fifo` exists and fails with a clear error if not (spawn is not in streaming mode, or spawn has already exited and cleaned up its FIFO).
- **FIFO exists but no reader**: write to the FIFO blocks (POSIX semantics). The CLI writer should `O_NONBLOCK` open and fail fast with "spawn not accepting control frames" if no reader is present. Document this as the CLI's failure mode.

### C4 — Fix relative `..` path counts in upper-level docs

`design/overview.md` and `design/harness/*.md` currently use **5** `..` segments to reach meridian-flow. Actual distance from those files to `meridian-flow/.meridian/work/biomedical-mvp/design/` is **6** segments (5 from the `events/` subdir, 5 from the `harness/` subdir — wait, verify this). Check each link by clicking it in a markdown previewer or `ls` each resolved path manually. Correct all broken links.

Use this as a sanity check:
```bash
# from design/harness/abstraction.md:
ls ../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md
```

### C5 — Rename the new streaming CLI flag

`cli/spawn.py` line 211 already has a hidden `--stream` flag: "Stream raw harness output to terminal (debug only)." Reusing `--stream` for the AG-UI streaming mode will confuse anyone inspecting the CLI and risks regressing smoke expectations.

**Resolution**: Use `--ag-ui-stream` as the new flag name. Document in `overview.md` that the existing hidden `--stream` debug flag can optionally be renamed to `--raw-stream` in a separate refactor, but that's not part of this work item. Note the collision explicitly so implementers don't collapse both into one path.

### C6 — Ground or remove the Codex `item/*/start|delta|end` subdivision

`events/harness-translation.md` uses notation like `item/agentMessage/start`, `item/agentMessage/delta`, `item/agentMessage/end` but `findings-harness-protocols.md` only documents the item types, not the `/start|delta|end` subdivision. Either:

- (a) Add a one-line citation to `findings-harness-protocols.md` or companion's `CODEX_MAPPING.md` documenting where the subdivision comes from, then the references are anchored; OR
- (b) If there's no citation, reframe the notation as "Codex fires per-item notifications; the adapter detects turn boundaries by matching `item/*` types and lifecycle states; the exact wire sub-path convention is adapter-detected, not a Codex protocol feature."

Pick (a) if you can find a source, (b) if you can't. Do not leave the current ungrounded notation.

## Concerns NOT in scope for this fix pass

- **`ag_ui_events.py` responsibility sprawl** (P1165 Concern 1): valid concern but it's a structural judgment that can be revisited once actual code is being written. Leave the current design as-is; add a brief note in `harness/abstraction.md` that "if `ag_ui_events.py` grows past ~300 LoC or more than three responsibilities, split into `ag_ui_types.py` + `ag_ui_emitter.py` — revisit during implementation."
- **`codex.py` size growth risk** (P1165 Concern 2): same — note in `harness/adapters.md` Codex section that "if codex.py grows past ~800 LoC during implementation, split out `codex_rpc.py` / `codex_translate.py` siblings." Don't pre-split in the design.
- **Streaming translation API return shape** (P1165 Concern 3): a minor API tweak — change the method signature in `harness/abstraction.md` from `stream_ag_ui_events(...) -> SpawnResult` to `stream_ag_ui_events(...) -> Iterator[AgUiEvent]` and let the existing runner path own `SpawnResult` construction. Small fix, do it.

## Deliverables

Edit these files in place. Do NOT rewrite from scratch — make targeted edits:

- `$MERIDIAN_WORK_DIR/design/overview.md` — B3, C5 (flag rename)
- `$MERIDIAN_WORK_DIR/design/harness/overview.md` — propagation of B1/B2/B3 if mentioned
- `$MERIDIAN_WORK_DIR/design/harness/abstraction.md` — B1 (CAPABILITY), B3, C1, and P1165 Concern 3 (method signature fix)
- `$MERIDIAN_WORK_DIR/design/harness/adapters.md` — B2 (tool config), C2 (Codex reasoning), fix `..` paths, inline note about codex.py growth
- `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md` — B1 (CONTROL_*), B3 (FIFO only), C1 (capability shape), C2 (claude supports_interrupt), C3 (failure modes), C5 (flag rename), fix `..` paths
- `$MERIDIAN_WORK_DIR/design/events/overview.md` — fix `..` paths if any
- `$MERIDIAN_WORK_DIR/design/events/flow.md` — B1 (CAPABILITY placement), B2 (TOOL_CALL_START config)
- `$MERIDIAN_WORK_DIR/design/events/harness-translation.md` — B1 (remove CAPABILITY/CONTROL_* rows), B2 (tool tables), C1 (capability shape), C2 (Codex reasoning), C6 (item/*/start|delta|end grounding)

## Principles

1. **Make targeted edits, not rewrites.** The structural core is approved. Fix the specific issues, leave the rest intact.
2. **Reference, don't duplicate.** meridian-flow owns the canonical schema. When you edit, double-check you're linking not restating.
3. **Every claim traces back to a decision.** D34–D40 remain the basis. If a fix changes a D37 open-question resolution, say so explicitly.
4. **Be honest about what's meridian-channel's vs meridian-flow's.** If a thing is meridian-channel's concern (like the mid_turn_injection enum, which describes how our adapter talks to three different harnesses), own it. If it's meridian-flow's (like ToolDisplayConfig), reference it.

## Report format

When done, report:
- Files changed (line counts)
- Each blocker/concern addressed and the concrete change you made
- Any finding you could not resolve and why
- Any new contradictions you discovered while editing (you may find more drift when you re-read)
- Any concerns the reviewers raised that you intentionally deferred (with reasoning)
