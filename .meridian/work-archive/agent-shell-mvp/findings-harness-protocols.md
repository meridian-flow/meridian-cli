# Findings: Harness Protocol Status (mid-conversation update)

**Status**: Design input — correction to assumptions that may be baked into early design docs.
**Source**: Dev-orchestrator conversation (c1046), 2026-04-08, after live research into companion + OpenAI dev docs.
**Audience**: design-orchestrator convergence pass (p1125) and any downstream reviewers touching `harness-abstraction.md`.

## TL;DR

**All three primary harnesses (Claude Code, Codex, OpenCode) expose a stable, programmatic, mid-turn-capable control surface.** The `HarnessAdapter` interface should be designed against three real implementations, not one stable + two sketchy. Earlier framing that treated codex as "experimental / deferred / unknown" is wrong and should be corrected wherever it appears in the design docs.

## What Changed vs Earlier Requirements

Earlier discussion and possibly early drafts of `harness-abstraction.md` may carry the assumption that:

- Claude Code is the only harness with a stable programmatic mid-turn channel.
- Codex headless (`codex exec`) is single-shot and has no mid-turn injection.
- OpenCode is the easiest and should be V1 while codex is V2 or deferred entirely.

This is no longer accurate. Corrected picture below.

## Corrected Harness Picture

### Claude Code

- **Transport**: `--input-format stream-json --output-format stream-json`, NDJSON over stdin/stdout.
- **Status**: Stable, documented.
- **Mid-turn semantics**: User messages written to stdin queue and deliver at the next turn boundary. No interrupt needed for the common case.
- **Risk**: Low. Anthropic has no incentive to pull this — it's the integration path.

### Codex (`codex app-server`)

- **Transport**: JSON-RPC 2.0 over stdio (default) or WebSocket (experimental).
- **Status**: **Stable for the core protocol we need.** Per developers.openai.com/codex/app-server:
  - "Core JSON-RPC protocol: stable, production-ready"
  - "Thread/turn lifecycle: stable"
  - "stdio transport: stable"
  - WebSocket transport is the part flagged experimental, and specific opt-in methods are gated behind an `experimentalApi` capability. **Neither affects our adapter** — we need stdio + the stable core methods only.
- **Relevant methods**:
  - `initialize` / `initialized` — handshake
  - `thread/start` — begin session with `{model, cwd, approvalPolicy, sandbox}`
  - `thread/resume` — resume an existing thread
  - `turn/start` — begin a new turn with a prompt
  - `turn/interrupt` — **this is the mid-turn control primitive**
  - `item/*` notifications — streaming output (agentMessage, commandExecution, fileChange, reasoning, webSearch, mcpToolCall, contextCompaction)
  - `item/*/requestApproval` requests — tool approvals (server responds with decision)
- **Mid-turn semantics**: Interrupt + re-start. Not quite as graceful as Claude's queue-to-next-boundary, but user-visible behavior is close enough and it's a real, stable capability.
- **Reference implementation**: `web/server/codex-adapter.ts` in [The-Vibe-Company/companion](https://github.com/The-Vibe-Company/companion). MIT-licensed, 28 unit tests, documents the full message translation in `web/CODEX_MAPPING.md`. **Use as reference, not a dependency.** Pattern-match the JSON-RPC ↔ internal event translation; write our own adapter in Python against our own event protocol.
- **Known gaps from companion's integration** (all acceptable for V0/V1):
  - No runtime model switching — set at `thread/start`
  - No runtime permission mode switching — set at `thread/start`
  - Token usage / cost tracking not extracted from `turn/completed` yet (easy to add)
  - Streaming reasoning is bulk-only — `item/reasoning/delta` not handled in companion's adapter
  - MCP/webSearch approval requests auto-accepted

### OpenCode

- **Transport**: HTTP session API exposed by `opencode serve` (also ACP NDJSON over stdin for some flows).
- **Status**: Stable — it's the product surface for external drivers. Designed modular specifically to support this use case.
- **Mid-turn semantics**: POST a new user message to the session endpoint. Cleanest of the three.
- **Risk**: Lowest protocol risk — changing this would break opencode's own external integration story.

## Implications for the Design

### 1. `harness-abstraction.md` should treat all three as tier-1 design targets

The interface has to work against all three. Don't design a Claude-only interface and retrofit codex/opencode later — that's how abstractions get warped into the shape of the first implementation.

The interface I'd sketch (for design-orchestrator to refine):

```python
class HarnessAdapter(Protocol):
    # Lifecycle
    async def launch(self, config: LaunchConfig) -> SpawnHandle: ...
    async def resume(self, handle: SpawnHandle) -> None: ...
    async def terminate(self, handle: SpawnHandle) -> None: ...

    # Turn control
    async def start_turn(self, handle: SpawnHandle, prompt: str) -> TurnId: ...
    async def interrupt_turn(self, handle: SpawnHandle, turn_id: TurnId) -> None: ...

    # Mid-turn input — the key capability
    async def send_user_message(self, handle: SpawnHandle, text: str) -> None:
        """
        Deliver a user message to a running spawn.

        Semantics vary by harness:
        - Claude: queues to next turn boundary
        - Codex: interrupts current turn and starts a new one
        - OpenCode: POSTs to session endpoint

        The adapter hides the wire mechanism. Callers get "deliver this message"
        semantics; the adapter picks the best approximation for its harness.
        """

    # Capability introspection
    def capabilities(self) -> HarnessCapabilities: ...

    # Event stream (notifications from harness → us)
    def events(self, handle: SpawnHandle) -> AsyncIterator[HarnessEvent]: ...

    # Approval responses (for tool-use gating)
    async def respond_to_approval(self, handle: SpawnHandle, req_id: str, decision: Decision) -> None: ...
```

`HarnessCapabilities` is where the semantic differences surface honestly:

```python
@dataclass
class HarnessCapabilities:
    mid_turn_injection: Literal["queue", "interrupt_restart", "http_post", "none"]
    runtime_model_switch: bool
    runtime_permission_switch: bool
    structured_reasoning_stream: bool
    cost_tracking: bool
```

The UI can then decide, per harness, whether to gray out the input box mid-turn, whether to show a model switcher, etc. The abstraction unifies *capability*; the metadata surfaces *semantics*.

### 2. Implementation order is now a product decision, not a protocol decision

Earlier framing: "Claude V0 because it's the only stable thing." Corrected framing: "Claude V0 because that's the harness our initial validation customer already uses, and the stream-json surface is the most mature." Codex and OpenCode are both viable V1 targets; pick based on which customer/use case shows up first, not based on protocol risk.

Suggested order for the design to document:

- **V0**: Claude Code. Ship Yao Lab validation on this.
- **V1**: Either codex or opencode — design supports both, we pick when we know who's next.
- **V2**: The remaining one.

### 3. The `meridian spawn` → sub-orchestrator injection insight still holds, and now generalizes

The earlier conversation noted: if `meridian spawn` launches Claude harness spawns with stream-json stdin kept open, every Claude spawn in the tree has a mid-turn injection channel — enabling primary-orchestrator → sub-orchestrator message injection.

With the corrected picture, this generalizes: **if meridian spawn routes through the HarnessAdapter layer instead of shelling out raw, every spawn in the tree — Claude, codex, or opencode — has a mid-turn control channel**. The `meridian spawn inject <spawn_id> "message"` CLI command becomes harness-agnostic. It just calls `adapter.send_user_message(handle, text)` and the adapter figures out whether that's a stdin write, a `turn/interrupt` + `turn/start`, or an HTTP POST.

This is a strong argument for routing meridian-channel's own spawn mechanism through the same HarnessAdapter abstraction the frontend shell uses. One adapter layer, two consumers (CLI and UI). Progressive unification of the dev-substrate (meridian-channel) and the product (agent shell) around a shared harness layer — which matches the "amalgamation" framing in requirements.md.

### 4. Companion as reference material, not dependency

`web/CODEX_MAPPING.md` and `web/server/codex-adapter.ts` in companion are the best available reference for how to translate codex JSON-RPC into an internal event protocol. Design-orchestrator should read them when drafting the codex section of `harness-abstraction.md`. They're MIT-licensed, so the patterns are legally safe to study and reimplement in Python.

We don't import companion, we don't vendor it, we don't depend on it. We read it the way you read a well-tested reference implementation when building your own — to avoid re-learning the same lessons they already paid for.

## What to Correct in the Existing Design Docs

If any of these phrases or equivalents appear in the current design drafts, they're outdated and should be replaced:

- ❌ "codex headless is single-shot, no mid-turn injection" → ✅ "codex app-server exposes `turn/interrupt` + `turn/start` for mid-turn control over stable JSON-RPC stdio"
- ❌ "codex is deferred to V2 due to protocol instability" → ✅ "codex is V1-capable; ordering vs opencode is a product decision, not a protocol decision"
- ❌ "opencode is the only tier-1 non-Claude option" → ✅ "opencode and codex are both tier-1 with stable programmatic mid-turn surfaces"
- ❌ "`HarnessAdapter.supports_mid_turn_injection() -> bool`" → ✅ "`HarnessCapabilities.mid_turn_injection: Literal['queue', 'interrupt_restart', 'http_post', 'none']`" — capture the semantic, not just the boolean

## Sources

- https://developers.openai.com/codex/app-server — OpenAI's own docs stating the core protocol is stable
- https://github.com/The-Vibe-Company/companion — MIT reference implementation
- `web/CODEX_MAPPING.md` in companion — full message translation table
- `web/server/codex-adapter.ts` in companion — working adapter with tests

## Mid-Turn Steering is Tier-1, Not Optional

**This is the most important framing instruction in this document. Please do not treat it as a footnote.**

Mid-turn injection is not a "nice-to-have capability we might expose in the UI." It is **the differentiating feature of the platform**, and the `HarnessAdapter` abstraction must be shaped around supporting it cleanly across all three harnesses from day one. Retrofitting it later means rebuilding the interface.

### Why this matters

The typical agent orchestration loop today is:

1. User writes a prompt
2. Agent runs for minutes-to-hours
3. User reads the report
4. User spawns a new agent with corrections
5. Loop repeats

This is a slow, lossy feedback loop. By the time the user sees the output, the agent has committed to a direction and burned tokens going down it. Course-correction means starting over.

The platform we are designing collapses this loop by making **every spawn in the tree steerable mid-execution**. A user watching a sub-orchestrator head down the wrong path can say "wait, reconsider X" and the running agent absorbs that correction without being killed and respawned. The primary orchestrator can steer its own children programmatically. Approvals and redirections flow through a single control plane across the whole spawn tree.

The exact interaction pattern the user demonstrated in this conversation — pushing back on the assistant mid-response, correcting a wrong assumption, redirecting to a better answer — **needs to work for every agent in the tree, not just the top-level one**. That is the product.

### Design implications

1. **`HarnessAdapter.send_user_message()` is a core method, not an optional extension.** It must be defined in the base interface, implemented by all three V0/V1 adapters (Claude, Codex, OpenCode), and exercised by smoke tests from day one. A harness that cannot support it cannot be a tier-1 adapter.

2. **The event protocol between backend and frontend must model mid-turn input as a first-class message type.** Not a special case, not a `raw_passthrough` escape hatch. `UserMessageMidTurn` is a real event the frontend sends and the backend routes to the correct adapter method.

3. **`meridian spawn inject <spawn_id> "message"` is a V0 CLI command, not a V2 feature.** It validates the abstraction works end-to-end from the CLI side, and it immediately gives the dev-workflow orchestrators (which meridian-channel already ships) the ability to steer their children — solving the original question that started this whole design conversation.

4. **Capability semantics are surfaced honestly, not hidden.** `HarnessCapabilities.mid_turn_injection` is a semantic enum (`queue`, `interrupt_restart`, `http_post`, `none`) so the UI can render the right affordances per harness. A Claude user sees "message queued for next turn"; a Codex user sees "this will interrupt the current turn." Don't lie about wire-level behavior to fake uniformity.

5. **Routing meridian-channel's own spawn mechanism through the HarnessAdapter is the unification move.** One adapter layer, two consumers (meridian CLI and agent-shell UI). This is how the amalgamation actually amalgamates — not by the UI wrapping the CLI, but by both consuming the same adapter layer. Design-orchestrator should evaluate this explicitly as a design decision with a recommendation to the user.

### What this means for `harness-abstraction.md`

The document structure should reflect the priority. **The mid-turn control surface section should come before the lifecycle section**, because the lifecycle (launch/terminate/resume) is the boring plumbing; the mid-turn surface is the differentiating design work. If the current draft puts it in a "Capabilities" or "Advanced" subsection, promote it to a top-level concern.

Every adapter subsection (Claude / Codex / OpenCode) should explicitly answer: *how does this harness support mid-turn steering, and what are the semantic quirks the UI needs to know about?* That's the acceptance criterion for the doc being done.

### What this means for the design-orchestrator's open questions to the user

Add to the questions list: *"Do you agree that mid-turn steering is the tier-1 differentiating feature, and that all three adapters must support it from V0/V1 — or would you rather ship a simpler 'spawn, watch, respawn' loop for V0 and add steering in V1?"*

Strong recommendation from this findings doc: **tier-1, V0**. The infrastructure cost is the same (you're building the HarnessAdapter layer anyway), and the capability is what makes the product defensible vs. every other "chat UI over Claude Code" that will ship in the next six months.

## Action for Convergence Pass (p1125) or Follow-Up

1. Grep the design docs for any language treating codex as experimental, deferred, or protocol-risky. Replace with the corrected picture.
2. Update `harness-abstraction.md` to:
   - Treat all three harnesses as tier-1 design targets
   - Replace boolean capability flags with semantic enums
   - Document the `turn/interrupt` + `turn/start` pattern for codex
3. Update any implementation roadmap section to reframe V1 ordering as "product decision, not protocol decision"
4. Note the meridian-channel spawn unification opportunity (section 3 above) as an open design question or decision for the user
