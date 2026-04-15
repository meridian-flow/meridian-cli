Execute the implementation plan for agent-shell-mvp. Design and plan are approved.

Start with Round 1 (Phase 1A: interfaces and types), then Round 2 (parallel: 1B Claude, 1C Codex, 1D OpenCode, 1E SpawnManager). Follow the staffing section in the plan overview for model assignments and review policy.

Key overrides to enforce throughout:
- **D56**: Use standard AG-UI `REASONING_*` events from `ag_ui.core`, NOT custom `THINKING_*`. Applies to Phase 2B mappers and Phase 3 frontend.
- **D57**: Phase 3 uses two-layer WS client — generic `WsClient` (no domain knowledge) + `SpawnChannel` on top (spawn-specific AG-UI logic). NOT a monolithic `SpawnWsClient`.

All design docs, plan files, requirements, and decisions are attached as context files. The plan overview has the full execution round sequence, staffing table, and review convergence policy.
