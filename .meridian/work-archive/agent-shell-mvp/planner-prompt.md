# Planning: agent-shell-mvp

Decompose the approved design into executable implementation phases with per-phase blueprints.

## Design Input

The 6 design documents in `design/` are the approved specification:

- `design/overview.md` — System topology, data flow, repository layout
- `design/harness-abstraction.md` — ISP-segregated interfaces, ConnectionState machine, ConnectionCapabilities
- `design/phase-1-streaming.md` — SpawnManager, durable drain, ControlSocketServer, `meridian spawn inject`, headless runner
- `design/phase-2-fastapi-agui.md` — WebSocket endpoint, AG-UI mapper protocol per harness
- `design/phase-3-react-ui.md` — Keep/Cut/Extend analysis, SpawnWsClient, capability-aware UI
- `design/edge-cases.md` — 12 enumerated failure modes

`requirements.md` captures user intent and constraints. `decisions.md` (D1-D56) captures all design decisions.

## Critical Override: D56

**Use standard AG-UI `REASONING_*` events from `ag_ui.core`, NOT custom `THINKING_*` events.** The design docs (particularly `phase-2-fastapi-agui.md` and `phase-3-react-ui.md`) reference `THINKING_*` with `thinkingId` — this was overridden by D56. The planner must ensure implementation phases use the standard `REASONING_*` event types. Rename frontend-v2 references if needed.

## Phase Structure

The design specifies 3 sequential major phases:

1. **Bidirectional streaming foundation** — All 3 harnesses (Claude, Codex, OpenCode), `meridian spawn inject`, smoke tests as gate
2. **FastAPI WebSocket server** — AG-UI event translation via `ag-ui-protocol` Python SDK, unit + smoke tests as gate
3. **React UI** — Built from frontend-v2 building blocks, browser tests as gate

Each phase must be decomposable into sub-steps small enough for a single @coder spawn. Include verification criteria for each sub-step.

## Staffing Section (Required)

The plan overview MUST include a staffing section. The design-orchestrator recommended:

- **Phase 1**: 1 @coder (strongest model — gpt-5.3-codex), @verifier + @smoke-tester
- **Phase 2**: 1 @coder, @verifier + @unit-tester (mapper tests) + @smoke-tester
- **Phase 3**: 1 @coder (frontend), @verifier + @browser-tester
- **Final review loop**: @reviewer fan-out (gpt-5.4, opus, gpt-5.2) with design alignment focus + @refactor-reviewer

Evaluate this recommendation and adjust if warranted — the @impl-orchestrator will only run review loops if the plan tells it to.

## Output

Produce `plan/overview.md` + per-phase files (`plan/phase-1.md`, `plan/phase-2.md`, `plan/phase-3.md`) in `$MERIDIAN_WORK_DIR/plan/`.

Each phase file should include:
- Ordered sub-steps with clear scope boundaries
- File paths that will be created/modified
- Verification criteria (what tests must pass)
- Dependencies on prior phases
- Edge cases from `design/edge-cases.md` relevant to that phase

The overview should include:
- Phase dependency graph
- Staffing section with model assignments and review policy
- Parallelism opportunities (if any sub-steps across phases are independent)
- Risk areas and mitigation
