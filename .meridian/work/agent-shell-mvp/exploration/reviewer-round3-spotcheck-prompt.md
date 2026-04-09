# Round 3 spot-check: post-cleanup convergence

## Context

The agent-shell-mvp design tree has been through three rounds:

- **Round 1** (p1163, p1164, p1165): three reviewers fanned out across different model families and focus areas on the fresh rewrite. They surfaced bugs B1/B2/B3 and concerns C1–C6.
- **Fix pass** (p1166): applied fixes for B1/B2/B3 and C1–C6.
- **Round 2** (p1167, p1168): two reviewers independently converged on the same narrow set of residuals — stale wording in `events/overview.md` and `harness/overview.md`, broken `../findings-harness-protocols.md` links from `design/harness/`, and three different placements of `control_protocol_version`.
- **Cleanup pass** (p1169): applied exactly those fixes and verified with greps.

Your job is a **focused spot-check**, not a fresh full review. The design tree has already converged on the substantive questions. You're checking whether the cleanup pass landed cleanly and whether anything new broke.

## What to read

Start with the two round-2 reports to understand what was supposed to be fixed:

1. `.meridian/spawns/p1167/report.md` — round 2 reviewer (gpt-5.2)
2. `.meridian/spawns/p1168/report.md` — round 2 reviewer (gpt-5.4)
3. `.meridian/spawns/p1169/report.md` — cleanup pass architect report

Then verify the cleanup in the actual design files:

4. `$MERIDIAN_WORK_DIR/design/events/overview.md`
5. `$MERIDIAN_WORK_DIR/design/events/flow.md`
6. `$MERIDIAN_WORK_DIR/design/harness/overview.md`
7. `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
8. `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
9. `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`
10. `$MERIDIAN_WORK_DIR/design/overview.md`

## What to check

For each of the 5 cleanup-pass fixes, answer **LANDED / DID NOT LAND / LANDED BUT INTRODUCED NEW CONTRADICTION**:

1. **`events/overview.md` per-tool config ownership**: `ag_ui_events.py` should own event types and shared serialization helpers **only** — not per-tool behavior config tables. Frontend-resident `toolDisplayConfigs` is the canonical home.
2. **`harness/overview.md` FIFO wording**: "stdin control protocol" should be "FIFO control protocol" everywhere in this doc. Stdin reserved for harness subprocess I/O only.
3. **`design/harness/*.md` link depth**: `../findings-harness-protocols.md` should now be `../../findings-harness-protocols.md` in `adapters.md`, `mid-turn-steering.md`, and `abstraction.md`. Docs at `design/` depth correctly keep `../`.
4. **Single home for `control_protocol_version`**: top-level field in `params.json` (not inside `capabilities`). Removed from `SpawnRecord`. Consistent across `events/flow.md`, `harness/mid-turn-steering.md`, `harness/abstraction.md`.
5. **Navigation text**: "per-tool render config" should be "tool naming coordination" in `design/overview.md` and `harness/overview.md` navigation tables.

## Additional checks

- Did the cleanup pass introduce any **new** wording contradictions between the edited docs and the rest of the design tree?
- Is the design tree internally consistent on these axes:
  - AG-UI taxonomy fidelity (no invented events; `TOOL_CALL_START` payload is `{toolName, toolCallId}` only)
  - FIFO is the single authoritative control ingress; streaming spawn does not read its own stdin as a control channel
  - Capability bundle lives in `params.json` at top level; flat `HarnessCapabilities` shape with no `supports_` prefix for the new fields
  - `control_protocol_version` at top of `params.json`, not inside `capabilities`, not on `SpawnRecord`

## Out of scope

Do not re-litigate design decisions that survived rounds 1 and 2. Do not propose new structural changes. If you see a nit that was already noted in round 2 and explicitly left out of the cleanup pass, note it as a nit but do NOT mark it blocking.

## Report format

- For each of the 5 fixes: **LANDED** / **DID NOT LAND** / **LANDED BUT INTRODUCED NEW CONTRADICTION** with one-line evidence (file + line or quoted phrase).
- **New contradictions** (if any): list them with file + line.
- **Verdict**: `CONVERGED` / `NOT CONVERGED — [reason]`.
- **Nits**: list them if you see any, but do NOT block on nits.
