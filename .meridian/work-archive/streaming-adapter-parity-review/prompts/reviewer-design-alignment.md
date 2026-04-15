# Reviewer: Design alignment and protocol completeness (gpt-5.4)

You are a design-alignment reviewer. Your job is to compare the landed implementation against the design docs and decision log, and surface places where the code diverges from the agreed-upon design.

## Context

The streaming-adapter-parity refactor just landed across 8 commits (58470a2..2d4d60a, +1565/-679, 31 files). It introduces a transport-neutral `ResolvedLaunchSpec` so both the subprocess path (`build_command()`) and the streaming path (`HarnessConnection.start()`) consume one spec produced by `adapter.resolve_launch_spec()`, rather than independently re-mapping `SpawnParams`.

The design is in `.meridian/work-archive/streaming-adapter-parity/design/`. The full decision log is in `.meridian/work-archive/streaming-adapter-parity/decisions.md`. Before writing anything, read these and also check the "D17: Final Review Triage" section which enumerates items that were fixed-now vs deferred.

## What to review

1. **Architecture fidelity.** Does the code actually implement the architecture drawn in `design/overview.md` (SpawnParams → adapter.resolve_launch_spec() → ResolvedLaunchSpec → { build_command() | ConnectionAdapter.start() })? Or does some path still read `SpawnParams` directly and bypass the spec? Look specifically at:
   - `run_streaming_spawn()` in `src/meridian/lib/launch/streaming_runner.py`
   - `src/meridian/cli/streaming_serve.py`
   - `src/meridian/lib/app/server.py`
   - `SpawnManager.start_spawn()` in `src/meridian/lib/streaming/spawn_manager.py`

   D17 triage flagged these three as fixed — verify the fix held.

2. **Decision alignment.** Walk through D1–D18. For each decision, mark as "implemented", "implemented but different", or "not implemented". Give a one-line justification. Pay special attention to:
   - D4 (effort normalization in the factory, not the transport)
   - D9 (semantic `PermissionConfig`, not pre-resolved CLI flags)
   - D10 (strategy map retired — is `StrategyMap`/`FlagStrategy`/`FlagEffect`/`build_harness_command` actually gone?)
   - D12 (`HarnessConnection.start()` signature is `(config, spec)` — check all callers)
   - D13 (effort field present on `PreparedSpawnPlan` and wired to both runners)
   - D14 (Codex confirm-mode rejects, doesn't auto-accept)
   - D15 (spec → transport projection guard exists in all three connection adapters)
   - D17 (fix-now items are fixed; deferred items have tracking)
   - D18 (the module is `claude_preflight.py`, not `preflight.py`)

3. **Protocol completeness.** For each transport (Claude CLI args, Codex JSON-RPC, OpenCode HTTP), read the projection code and confirm every semantically relevant spec field reaches the other side. Cross-check against the subprocess `build_command()` output for the same spec. If a field is intentionally dropped because the transport API doesn't support it, confirm D16 documentation is followed (log + parity test marks it as known asymmetry).

4. **Scope discipline.** The refactor's stated scope is child-spawn launch. Did it creep into interactive/primary launch changes (explicitly out of scope)? Did it touch MCP wiring or new harness adapters (also out of scope)?

5. **Edge cases enumerated in `overview.md` §Edge Cases.** For each of the six edge cases, confirm the implementation actually handles it and point at the code. If an edge case is not covered, flag it.

## Deliverable

Structured findings, each with severity (blocker / high / medium / low / observation), location (file:line), what the design expected, what the code does, and a concrete fix recommendation. Group by category (Architecture / Decisions / Protocol / Scope / Edge cases). End with a summary verdict: does the landed code realize the design, with caveats?

## Reference files
- `.meridian/work-archive/streaming-adapter-parity/design/overview.md`
- `.meridian/work-archive/streaming-adapter-parity/design/resolved-launch-spec.md`
- `.meridian/work-archive/streaming-adapter-parity/design/transport-projections.md`
- `.meridian/work-archive/streaming-adapter-parity/design/migration-path.md`
- `.meridian/work-archive/streaming-adapter-parity/design/runner-preflight.md`
- `.meridian/work-archive/streaming-adapter-parity/design/parity-testing.md`
- `.meridian/work-archive/streaming-adapter-parity/decisions.md`
- `src/meridian/lib/harness/launch_spec.py`
- `src/meridian/lib/harness/adapter.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/harness/common.py`
- `src/meridian/lib/harness/connections/base.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `src/meridian/lib/launch/claude_preflight.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/ops/spawn/plan.py`
- `src/meridian/lib/ops/spawn/prepare.py`
