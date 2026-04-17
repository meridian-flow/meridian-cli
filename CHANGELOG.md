# Changelog

Caveman style. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [SemVer](https://semver.org/). Versions `0.0.6` through `0.0.25` in git history only — changelog fell stale, resumed at `[Unreleased]`.

## [Unreleased]

## [0.0.33] - 2026-04-17

### Fixed
- `meridian opencode` primary launch passed the startup prompt as the root positional `project` arg instead of OpenCode's `--prompt` flag. OpenCode tried to `open()` the whole session prompt as a path and quit immediately with `ENAMETOOLONG`.

## [0.0.32] - 2026-04-17

### Fixed
- Primary launch (`meridian` with no subcommand) dropped into JSON streaming mode instead of interactive TUI. Regression from 0.0.31 launch refactoring — `interactive` flag wasn't propagated to run inputs for PRIMARY composition surface.
- Primary launch viewport sizing: PTY now created with correct terminal dimensions before child process starts. Was using `pty.fork()` which sets size after child starts; now uses `pty.openpty()` + manual fork so child sees correct size from first query.

## [0.0.31] - 2026-04-17

### Added
- `workspace.local.toml` support for multi-repo context injection. Declare `[[context-roots]]` entries pointing at sibling repos; meridian projects them to harness launches. Local-only file, gitignored by default.
- `workspace init` command creates template file with commented examples, adds local gitignore coverage via `.git/info/exclude`.
- `config show` workspace surface: status, root counts, per-harness applicability. JSON: `workspace = {status, path?, roots:{count,enabled,missing}, applicability:{claude,codex,opencode}}`.
- `doctor` workspace findings: `workspace_invalid`, `workspace_unknown_key`, `workspace_missing_root`, `workspace_unsupported_harness`.
- Launch projection: Claude (`--add-dir`), OpenCode (`permission.external_directory` env). Codex deferred to `harness-permission-abstraction` (requires CODEX_HOME config generation).
- Invalid workspace pre-launch gate blocks spawn before harness contact.
- Shared `ConfigSurface` builder unifies `config show` and `doctor` workspace state.

### Changed
- Bundled `mars-agents` 0.1.2 → 0.1.3.
- Workspace file location follows `MERIDIAN_STATE_ROOT` — lives at `state_root.parent / workspace.local.toml`.

## [0.0.30] - 2026-04-16

### Added
- New `finalizing` spawn state between `running` and terminal. Covers the harness-exited-but-drain-in-flight window so the reaper stops stamping live spawns mid-drain. Shows up in `spawn show`, stats, and `--status` filter.
- `spawn show` renders `orphan_finalization` distinct from `orphan_run` — tells apart drain-window hangs from runner-dead-during-run.

### Changed
- `meridian-dev-workflow` bumped 0.0.25 → 0.0.26 via `meridian mars sync`.
- `@impl-orchestrator` now runs a mandatory Explore phase before planning — verifies design against code reality, produces `plan/pre-planning-notes.md` as a gate artifact, terminates to a Redesign Brief when design is falsified.
- `agent-staffing` skill: new "Fan-Out vs Parallel Lanes" terminology section (same-prompt-different-models vs different-prompts-different-focus-areas); new `@reviewer as Architectural Drift Gate` section (CI-spawned reviewer enforces structural invariants semantically against a declared-invariant prompt).
- `AGENTS.md` model-routing block removed — model choice delegated to profile defaults and `meridian models list`.
- Reaper no longer false-positives over live spawns. Heartbeat window 120s, 15s startup grace, PID-reuse margin 30s, depth-gated so nested sweeps can't stamp their parents. Authority rule: runner/launcher/cancel writes always win over reconciler writes, so a late report corrects a premature stamp. Fixes recurrence of #14.
- Runner owns the heartbeat task now (30s tick, cancelled in outer `finally`), not the reaper.
- `finalize_spawn(..., origin=...)` is mandatory at every call site.
- `update_spawn` no longer accepts `status=` — lifecycle transitions go through `mark_finalizing` / `finalize_spawn` only.
- `meridian-base` package ref bumped to pick up refined prompt-writing guidance in `agent-creator` and `skill-creator`.
- Bundled `mars-agents` bumped from `0.0.14` to `0.1.1`.

### Fixed
- Codex adapter silently truncated initial prompts over 50 KiB, emitted a `warning/promptTruncated` event, and continued with the mutilated input — turning over-limit planner briefs into "no task provided" runs. Claude and OpenCode had no analogous ceiling at all. All three adapters now share one 10 MiB ceiling via `validate_prompt_size()` in `lib/harness/connections/base.py`; over-limit prompts raise `PromptTooLargeError` naming actual vs allowed bytes and the harness, before any transport contact.
- `meridian spawn --help` text now matches behavior. Was "Runs in background by default. Use --foreground to block." — both halves wrong (default is foreground, `--foreground` flag does not exist). Now describes `--background` as the opt-in flag it actually is.

### Removed
- "awaiting finalization" heuristic in detail view. Replaced by real `finalizing` status.
- Checked-in git submodules `meridian-base/` and `meridian-dev-workflow/`. Mars package deps now source of truth.

### Reverted
- R06 launch-refactor skeleton (8 commits, `3f8ad4c..45d18d7`) that landed post-v0.0.29 but never shipped in a tagged release. Skeleton was built while the codex prompt-truncation bug above was corrupting coder briefs; smoke evidence after Fix A revealed structural regressions (fork lineage split-brain in new `launch/fork.py`, row-before-fork ordering, OpenCode report extraction returning raw `session.idle` envelopes). Design package preserved under `.meridian/work/workspace-config-design/` as input for a clean retry on top of the restored tagged-stable baseline. No user impact since v0.0.29 is before the skeleton.

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
