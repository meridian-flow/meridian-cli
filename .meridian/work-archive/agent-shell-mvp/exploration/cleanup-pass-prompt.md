# Cleanup pass: round-2 residuals on agent-shell-mvp design tree

## Context

Round 2 reviewers p1167 (gpt-5.2) and p1168 (gpt-5.4) independently converged on the same narrow set of residual issues after the fix-pass (p1166). All are wording drift and small consistency gaps — no structural problems. Your job is a **tight, targeted cleanup**: read the round 2 reports and apply exactly the fixes they list, then re-verify with `grep`.

This is not a review. Apply the changes, don't re-litigate them.

## What to read first

1. `.meridian/spawns/p1167/report.md` — round 2 reviewer (gpt-5.2)
2. `.meridian/spawns/p1168/report.md` — round 2 reviewer (gpt-5.4)
3. `$MERIDIAN_WORK_DIR/design/events/overview.md`
4. `$MERIDIAN_WORK_DIR/design/harness/overview.md`
5. `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
6. `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
7. `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`
8. `$MERIDIAN_WORK_DIR/design/events/flow.md`
9. `$MERIDIAN_WORK_DIR/design/overview.md`

## Fixes to apply

### 1. `events/overview.md` — remove stale `ag_ui_events.py` per-tool config claim (B2 residual, NC1 in p1167 & p1168)

**Problem**: `events/overview.md` still says `ag_ui_events.py` contains "per-tool behavior config tables" and "the per-tool config dict". This contradicts the fix-pass rule: per-tool render config is frontend-resident in meridian-flow's `toolDisplayConfigs`, the wire format carries only `{toolName, toolCallId}`, and the adapter layer owns no tool config tables.

**Fix**: Rewrite the affected sentences in `events/overview.md` so `ag_ui_events.py` is described as owning **event types and shared serialization helpers only** — not tool config tables. The adapter layer does NOT own per-tool config; it's a meridian-flow coordination concern (registered in `toolDisplayConfigs`, keyed by `toolName`). Cross-link to `frontend/component-architecture.md` §"Per-Tool Display Config" for the canonical definition.

Also check the navigation text in `events/overview.md` — if the table row for `harness-translation.md` still says "plus per-tool render config", change it to "plus tool naming coordination (no wire config)".

Also check line ~31 of `events/overview.md` — if it still uses the old vocabulary `stdout: visible | collapsed | inline`, replace with the canonical `ToolDisplayConfig` field names (`inputCollapsed`, `stdoutCollapsed`, `stderrMode`) or simply delete the example since wire config is gone.

### 2. `harness/overview.md` — remove stale "stdin control protocol" wording (B3 residual, NC1 in p1167)

**Problem**: `harness/overview.md` still says "stdin control protocol" in at least three places (Role section, Read Next bullet, and a third reference). The fix-pass established that FIFO is the single authoritative control ingress and the streaming spawn does NOT use stdin as a control channel.

**Fix**: Replace every "stdin control protocol" mention in `harness/overview.md` with "FIFO control protocol". Add a short clarifier where the original said "consumes a normalized stdin control protocol" — reword to "consumes a normalized FIFO-based control protocol" and note that stdin is reserved for harness subprocess I/O only (not used as a control channel by the adapter).

Also check the navigation or "Read Next" bullet — if it says "Stdin control frame model + reader" or similar, rename to "FIFO control frame model + reader".

### 3. `design/harness/*.md` — fix broken `../findings-harness-protocols.md` relative paths (C4 residual)

**Problem**: `design/harness/adapters.md`, `design/harness/mid-turn-steering.md`, and `design/harness/abstraction.md` each reference `../findings-harness-protocols.md`. From `design/harness/`, `..` resolves to `design/`, not to the work-item root where `findings-harness-protocols.md` actually lives. The correct relative path is `../../findings-harness-protocols.md`.

**Fix**: In `design/harness/adapters.md`, `design/harness/mid-turn-steering.md`, and `design/harness/abstraction.md`, replace every occurrence of `../findings-harness-protocols.md` with `../../findings-harness-protocols.md`. Double-check each link by running `ls` from the doc's directory after the change. Do not touch links in files at `design/` depth (they use `../findings-harness-protocols.md` correctly from there).

Spot-check: after editing, run `grep -rn 'findings-harness-protocols.md' design/harness/ design/events/ design/` and verify each link resolves with the correct number of `..` segments.

### 4. Pick one authoritative home for `control_protocol_version` (NC2 in p1168)

**Problem**: `events/flow.md` and `harness/mid-turn-steering.md` put `control_protocol_version` inside `params.json.capabilities`. `harness/abstraction.md` omits it from the `params.json` example. `harness/mid-turn-steering.md` also models it on `SpawnRecord`. Three different placements, two different surfaces.

**Fix**: Pick **one** canonical home and propagate it. Recommendation: put it at the **top level** of `params.json` (alongside `capabilities`), not inside `capabilities`, because the version describes the control-frame wire format — a property of the spawn's control surface — not a capability of the harness. So the shape becomes:

```json
{
  "harness": "claude|codex|opencode",
  "control_protocol_version": "0.1",
  "capabilities": {
    "mid_turn_injection": "queue|interrupt_restart|http_post|none",
    "runtime_model_switch": false,
    "runtime_permission_switch": false,
    "structured_reasoning_stream": false,
    "cost_tracking": false
  }
}
```

Remove `control_protocol_version` from `SpawnRecord` entirely — `params.json` is the durable source of truth for spawn metadata, `SpawnRecord` is the in-memory read model. Update `harness/abstraction.md`'s `params.json` example to include `control_protocol_version` at the top level, and remove any `SpawnRecord` field referencing it.

Apply to: `events/flow.md`, `harness/mid-turn-steering.md`, `harness/abstraction.md`. Cross-check `events/harness-translation.md` to make sure it doesn't have a contradicting placement.

### 5. Navigation text in other overviews (nit in p1168)

`overview.md` line ~149 and `harness/overview.md` line ~93 still describe "per-tool render config" in navigation tables. Update those to "tool naming coordination" to match the no-wire-config contract. This is a one-phrase edit per doc.

## Principles

1. **Apply, don't re-design.** The round 2 reviewers already made the call. Do the exact fix they listed.
2. **Verify after editing.** After each fix, grep for the stale pattern to confirm it's gone. Report grep results in your final summary.
3. **Don't touch anything else.** No other docs, no other scope expansion. If you find something else that looks wrong, mention it in the report but do NOT fix it — the orchestrator will decide whether it's in scope.

## Deliverables

Targeted edits to:
- `$MERIDIAN_WORK_DIR/design/events/overview.md`
- `$MERIDIAN_WORK_DIR/design/harness/overview.md`
- `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
- `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
- `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`
- `$MERIDIAN_WORK_DIR/design/events/flow.md`
- `$MERIDIAN_WORK_DIR/design/overview.md` (navigation nit only)

## Report format

For each of the 5 fixes:
- Files changed
- Verification grep results ("zero stale matches" or list what's left)
- Any judgment call you made

Then a summary line: `READY FOR FINAL CONVERGENCE CHECK` or `BLOCKED: [reason]`.
