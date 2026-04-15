# SOLID / Harness-Neutrality Review

## Overall assessment

Request changes. The design direction is mostly right, but the load-bearing abstraction is not internally consistent yet. The biggest problem is not missing detail; it is that the docs describe incompatible contracts, which would force translator special cases and router-to-adapter leaks later.

## Findings

1. `BLOCKER` The normalized event layer is not actually the canonical contract, so the translator cannot remain a rename-only boundary. Location: [harness-abstraction.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/harness-abstraction.md#L342), [frontend-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-protocol.md#L227), [event-flow.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/event-flow.md#L83). `harness-abstraction.md` says normalized events match the wire vocabulary 1:1 and the translator only wraps/renames, but the schemas disagree on core fields and lifecycle shape: normalized events omit `turnId`, `displayId`, per-tool `sequence`, and use a 3-event thinking family, while the frontend protocol requires `THINKING_TEXT_MESSAGE_*`, `DISPLAY_RESULT(displayId, resultKind, data)`, and turn/message/tool identities throughout. `event-flow.md` then adds more drift (`resultType` vs `resultKind`, `status:"ok"` vs `status:"done"`, `runId` vs `turnId`). This means the translator would have to synthesize IDs and lifecycle edges, which is exactly the abstraction leak the design says it avoids. The fix is to define one canonical normalized schema first, then make the wire docs derive from it.

2. `BLOCKER` There is no neutral interface for sending locally executed tool results back into the harness. Location: [harness-abstraction.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/harness-abstraction.md#L204), [event-flow.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/event-flow.md#L304), [overview.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/overview.md#L222). The design says the router executes `python`/interactive tools locally and then feeds a `tool_result` back so the turn can continue, but `HarnessSender` has no `submit_tool_result`-style method. The event-flow therefore drops to Claude-specific behavior (`tool_result` NDJSON on stdin), which bypasses the abstraction entirely. That breaks DIP/OCP at the most important seam: opencode cannot be added without changing router logic. The fix is to add an explicit abstract tool-completion command or a separate tool-bridge interface that every adapter implements.

3. `MAJOR` Capability negotiation is internally contradictory, so the frontend cannot trust the advertised surface. Location: [harness-abstraction.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/harness-abstraction.md#L837), [frontend-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-protocol.md#L57), [frontend-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-protocol.md#L550), [event-flow.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/event-flow.md#L527). The Claude adapter advertises `mid_turn_injection=True` and `session_persistence/resume/fork=True`, but the frontend protocol says all of those are false in Claude V0, and `event-flow.md` explicitly says `inject_user` is a no-op in V0 and restart loses session state. Those cannot all be true. If capability flags describe theoretical harness potential instead of effective product behavior, the UI gating story is dishonest. The fix is to report effective behavior only, or split “supported by protocol” from “enabled in this release”.

4. `MAJOR` Claude session/bootstrap initialization is specified in two incompatible ways. Location: [agent-loading.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/agent-loading.md#L330), [harness-abstraction.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/harness-abstraction.md#L733), [overview.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/overview.md#L127). `agent-loading.md` says Claude gets the system prompt via an initial stream-json frame and tools via init-time tool frames. `harness-abstraction.md` and `overview.md` instead say Claude reuses existing CLI lanes like `--agents` and `--append-system-prompt`, then waits for the first `user` frame. That ambiguity will push harness-specific knowledge back into the loader/adapter boundary. The fix is to choose one authoritative Claude init path and remove the competing one from the other docs.

## What I did

Reviewed and cross-checked:
- [requirements.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/requirements.md)
- [overview.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/overview.md)
- [harness-abstraction.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/harness-abstraction.md)
- [event-flow.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/event-flow.md)
- [frontend-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-protocol.md)
- [agent-loading.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/agent-loading.md)

## Key decisions implied by the review

- The canonical contract should live in the normalized layer, not in three drifting docs.
- Local tool execution needs its own abstract completion path back into the harness.
- Capability flags must describe effective behavior, not theoretical harness potential.
- Claude init/tool registration needs one authoritative path.

## Verification

I traced the same user-turn flow across the abstraction, wire protocol, event-flow, and loader docs, with the review focused on SRP/OCP/ISP/LSP/DIP and Claude-to-opencode neutrality.

## Files modified

None.

## Issues / blockers

I could not write `$MERIDIAN_WORK_DIR/reviews/solid-review.md` because the workspace is read-only. I also attempted `meridian report create --stdin`, but this Meridian build does not support `report` (`Unknown command: report`).