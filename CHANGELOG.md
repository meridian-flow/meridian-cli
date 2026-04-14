# Changelog

Caveman style. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/). Versions `0.0.6` through `0.0.25` in git history only — changelog fell stale, resumed at `[Unreleased]`.

## [Unreleased]

### Added
- New `finalizing` spawn state between `running` and terminal. Covers the harness-exited-but-drain-in-flight window so the reaper stops stamping live spawns mid-drain. Shows up in `spawn show`, stats, and `--status` filter.
- `spawn show` renders `orphan_finalization` distinct from `orphan_run` — tells apart drain-window hangs from runner-dead-during-run.

### Changed
- Reaper no longer false-positives over live spawns. Heartbeat window 120s, 15s startup grace, PID-reuse margin 30s, depth-gated so nested sweeps can't stamp their parents. Authority rule: runner/launcher/cancel writes always win over reconciler writes, so a late report corrects a premature stamp. Fixes recurrence of #14.
- Runner owns the heartbeat task now (30s tick, cancelled in outer `finally`), not the reaper.
- `finalize_spawn(..., origin=...)` is mandatory at every call site.
- `update_spawn` no longer accepts `status=` — lifecycle transitions go through `mark_finalizing` / `finalize_spawn` only.
- `meridian-base` package ref bumped to pick up refined prompt-writing guidance in `agent-creator` and `skill-creator`.
- Bundled `mars-agents` bumped from `0.0.14` to `0.1.1`.

### Removed
- "awaiting finalization" heuristic in detail view. Replaced by real `finalizing` status.
- Checked-in git submodules `meridian-base/` and `meridian-dev-workflow/`. Mars package deps now source of truth.

## [0.0.28] - 2026-04-13

### Added
- Primary `meridian` launch startup agent catalog. Fresh and forked sessions now show installed agents before user input. Claude gets it in appended system prompt; Codex and OpenCode inline.

### Changed
- Startup inventory now agent-only. Skills still load through normal harness launch path, but not duplicated in startup catalog.

### Fixed
- `session log` and `session search` now tell `chat not found` apart from `chat has no transcript yet`.
- Chat ref resolution now falls back to primary spawn harness session id when the chat row has none.
- `pytest-llm` launcher now uses current interpreter path more reliably.

## [0.0.27] - 2026-04-12

### Changed
- Dev workflow package updated for unified `impl-orchestrator`.

### Fixed
- Spawn model validation now resolves models from the Meridian repo root instead of drifting with CWD.
- Codex streamed report extraction now accepts current event names instead of dropping final agent output.

## [0.0.26] - 2026-04-12

### Added
- **Streaming runner**: bidirectional streaming spawn pipeline. All three harnesses (Claude, Codex, OpenCode) route through unified `execute_with_streaming` path with connection-level event consumption, budget tracking, and retry.
- **`ResolvedLaunchSpec` hierarchy**: transport-neutral launch spec per harness. `ClaudeLaunchSpec`, `CodexLaunchSpec`, `OpenCodeLaunchSpec` — each adapter owns `resolve_launch_spec()` and `build_command()`. Replaces strategy maps.
- **`--debug` mode**: structured JSONL tracing across all pipeline layers. `meridian spawn --debug` emits trace events for harness launch, event consumption, extraction, and finalization.
- **`psutil`-based process liveness**: cross-platform (Linux, macOS, Windows). PID-reuse detection via `create_time()`. Replaces `/proc/stat` parsing and `os.kill(pid, 0)`.
- **`SpawnExitedEvent`**: new event type separating process exit from finalization. Spawn stays `running` after process exits until report extraction completes — prevents false orphan detection.
- **`runner_pid` tracking**: each spawn records which PID is responsible for finalization. Foreground spawns set it in `start` event; background spawns set it in `update` after wrapper launches.
- **`MERIDIAN_WORK_DIR` and `MERIDIAN_WORK_ID` exported** into harness sessions.
- `CHANGELOG.md` resumed after staleness. Now in caveman style.

### Changed
- **Reaper rewrite**: 500-line state machine → 119 lines (~30 core). No PID files, no heartbeat, no foreground/background dispatch. Just: is `runner_pid` alive? Branch on `exited_at` presence.
- **PID/heartbeat file elimination**: `harness.pid`, `background.pid`, `heartbeat` removed. PIDs come from event stream only. Spawn directories are artifact-only.
- **`SpawnExtractor` protocol**: extraction split from adapter into composable protocol. `StreamingExtractor` wraps harness bundle for connection-aware extraction.
- **Streaming parity**: all three harnesses converge on shared launch context, env invariants, permission pipeline, and projection paths. 8-phase implementation.
- **Bundle registry**: immutable after registration. Import-time side effects populate global registry.
- Claude readline limit raised to 128 MiB for large conversation echoes.
- `.agents/` and `.claude/` removed from tracking — generated output only.

### Fixed
- Spawn orphan false-failures: `exited` event + psutil liveness prevents reaper from racing runner's post-exit finalization.
- Streaming runner completion/signal races: F2 residual race when completion and signal land on same wakeup.
- Harness binary not found now produces diagnostic error instead of silent failure.
- Codex: server-initiated JSON-RPC requests handled; send lock prevents interleaved writes.
- OpenCode: chunked response handling on message POST.
- SIGTERM masked during `streaming_serve` finalization — prevents double-cleanup.
- Continue/fork wired for Claude and Codex streaming adapters.
- Child env `WORK_DIR` fallback and `autocompact` inheritance (#12).
- Effort field wired through `PreparedSpawnPlan` to both runners.

## [0.0.5] - 2026-03-21

### Added
- `gpt52` builtin alias for `gpt-5.2`; Claude `tools` passthrough in launch plan

### Changed
- Auto-resolve builtin aliases from discovered models; manifest-first bootstrap

## [0.0.4] - 2026-03-17

### Added
- Model catalog split with routing, visibility, descriptions, and `models.toml` config

## [0.0.3] - 2026-03-17

### Added
- Bootstrap state tracking with builtin skills and source recording; designer agent

## [0.0.2] - 2026-03-17

### Fixed
- `.meridian/.gitignore` seeding and stale CLI commands in docs

## [0.0.1] - 2026-02-25

Initial release — core CLI (`spawn`, `session`, `work`), harness adapters (Claude Code, Codex, OpenCode), agent profiles, skill system, sync engine, JSONL state stores.
