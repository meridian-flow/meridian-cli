# Research: Codex idle semantics and one-shot finalization

Date: 2026-04-15

## Question
When integrating with Codex app-server over a persistent WS/session channel, how should an orchestrator decide that a one-shot delegated run is "finished" (vs merely idle and waiting for next user input)?

## Executive summary
Short answer: treat **turn lifecycle** as authoritative for one-shot tasks, not socket lifecycle.

For Codex app-server, the websocket/session is intentionally persistent. "Done" for one-shot orchestration is when:
1. You observe `turn/completed` for the specific `turnId` you started, and
2. The thread transitions to `idle` (or no further events for that turn) and there are no unresolved tool-action gates.

Do **not** wait for transport close.

## Findings

### 1) Is this a known pain point?
Yes. There are repeated user reports of Codex appearing hung/stuck in issue trackers, especially where completion semantics are unclear or output stalls.

Examples:
- openai/codex issue #6279: "hangs with no response"  
  https://github.com/openai/codex/issues/6279
- Additional "stuck/hanging" complaints are common in openai/codex issues list (symptom: agent appears active/incomplete even when no visible forward progress).

Inference: even when some incidents are regressions, the UX pattern confirms lifecycle ambiguity is a real integration/operator pain point.

### 2) What does Codex itself do?

#### Codex CLI has explicit one-shot path
Codex docs expose non-interactive/CLI execution patterns (`codex exec`) for one-off runs, instead of relying on session close.
- CLI docs: https://developers.openai.com/codex/cli
- CLI reference: https://developers.openai.com/codex/cli/reference

#### App-server is event/lifecycle based, not auto-close based
From OpenAI app-server docs:
- "Finish the turn: The server emits `turn/completed` with final status..."
- Event stream includes `item/started`, `item/completed`, deltas, errors, and turn completion.

Source: https://developers.openai.com/codex/app-server

Implication: the protocol’s completion boundary is **turn completion event**, not websocket termination.

### 3) How other frameworks define "done"

#### OpenAI Agents SDK (successor pattern from Swarm)
Runner loop ends when model emits final output and no more tool calls/handoffs; `run()` returns a result object.
- https://openai.github.io/openai-agents-js/guides/running-agents
- Key rule: final output + no tool calls => return.

#### OpenAI Swarm (historical but explicit)
Swarm documents run loop and explicit return condition:
- "If no new function calls, return"
- `max_turns` caps loops.
- https://github.com/openai/swarm

#### Microsoft AutoGen
AutoGen makes termination an explicit pluggable policy (`MaxMessageTermination`, `TextMentionTermination`, AND/OR composition).
- https://microsoft.github.io/autogen/dev/_modules/autogen_agentchat/base/_termination.html

#### LangGraph
LangGraph treats completion as graph-level control-flow completion (`END`) or interruption waiting for resume.
- Streams end when graph run finishes.
- Interrupts pause indefinitely until resumed (not "done").
- https://langchain-ai.lang.chat/langgraph/cloud/how-tos/streaming/
- https://7x.mintlify.app/oss/javascript/langgraph/interrupts

#### Anthropic Managed Agents (important comparable event model)
Anthropic explicitly models session idleness with a **stop reason**. `session.status_idle` can mean `requires_action` or `end_turn`.
- https://platform.claude.com/docs/en/managed-agents/events-and-streaming
- Their sample loop breaks on `end_turn` and continues on `requires_action`.

This is the clearest public precedent for separating:
- transport/session alive,
- turn paused for external action,
- turn complete.

### 4) Emerging best practice
Across systems, robust orchestrators use a **declared run contract**:

1. **Run scope**: per-turn/per-invocation ID (not connection).
2. **Terminal states**: `completed`, `failed`, `interrupted`, `cancelled`, `max_turns`, `timeout`.
3. **Paused states**: explicit `requires_action` (tool approval/tool result/human input).
4. **Watchdog**: idle timeout for "no events" only as failure/recovery path, not success signal.
5. **Result latch**: finalize exactly once on terminal state for the tracked run-id.

This pattern appears in Agents SDK, AutoGen, LangGraph, and Anthropic event docs.

## Recommendation for Meridian

Use a **Turn-Bound Finalization Contract** for Codex harness integration.

### Proposed contract
For a one-shot delegated run, Meridian should track `threadId + turnId` and finalize when:
1. `turn/completed` received for that `turnId`, and
2. Final turn status in terminal set `{completed, failed, interrupted, cancelled}`.

Then mark spawn finalized immediately; do not wait for WS close.

### Guardrails
- If thread goes idle **without** `turn/completed` for tracked turn within grace window, classify `incomplete/unknown` and trigger recovery probe.
- If idle stop reason indicates action required (tool confirmation/result), mark `blocked_requires_action`, not done.
- Add absolute wall-clock timeout and heartbeat/no-event timeout.
- Persist event cursor + seen terminal event id to make finalize idempotent across restarts.

### Why this is best for a small orchestrator
Pros:
- Simple state machine; low implementation complexity.
- Matches upstream Codex event semantics.
- Avoids hangs caused by waiting on persistent connection close.
- Crash recovery is straightforward (replay events until terminal).

Cons:
- Requires careful handling of rare ordering/race cases.
- Needs explicit blocked-vs-complete distinction when tools/human gates exist.

Net: best tradeoff for Meridian’s architecture (thin coordinator, crash-only, file-authoritative state).

## Suggested state machine (minimal)
- `running`
- `blocked_requires_action`
- `terminal_completed`
- `terminal_failed`
- `terminal_interrupted`
- `terminal_cancelled`
- `terminal_timeout`
- `terminal_unknown` (recovery fallback)

Transitions driven by app-server events; transport disconnect only affects observability/reconnect, not semantic completion.

## Sources
- Codex app-server docs: https://developers.openai.com/codex/app-server
- Codex CLI docs: https://developers.openai.com/codex/cli
- Codex CLI reference: https://developers.openai.com/codex/cli/reference
- Codex issue example (hang symptom): https://github.com/openai/codex/issues/6279
- OpenAI Swarm README (run loop): https://github.com/openai/swarm
- OpenAI Agents SDK (runner loop/final output): https://openai.github.io/openai-agents-js/guides/running-agents
- AutoGen termination conditions: https://microsoft.github.io/autogen/dev/_modules/autogen_agentchat/base/_termination.html
- LangGraph streaming and END semantics: https://langchain-ai.lang.chat/langgraph/cloud/how-tos/streaming/
- LangGraph interrupts: https://7x.mintlify.app/oss/javascript/langgraph/interrupts
- Anthropic Managed Agents events (`session.status_idle`, `end_turn`, `requires_action`): https://platform.claude.com/docs/en/managed-agents/events-and-streaming

## Notes on quote snippets used
- Codex app-server docs: "Finish the turn: The server emits `turn/completed`..."
- Swarm README: "If no new function calls, return"
- Anthropic docs sample loop: break on `end_turn`; continue workflow on `requires_action`

