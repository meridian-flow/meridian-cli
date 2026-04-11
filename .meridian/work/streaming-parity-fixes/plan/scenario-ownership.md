# Streaming Parity Fixes v3: Scenario Ownership

Each scenario is claimed exactly once. Phase closure is gated on every non-retired scenario in that phase reaching `verified` in `scenarios/`. The retired reserved-flag scenario remains owned for traceability but stays `retired`.

## Phase 1

- `S001` — Adapter omits `resolve_launch_spec` override
- `S040` — `HarnessAdapter` Protocol and `BaseHarnessAdapter` ABC stay reconciled
- `S053` — Adapter-level `continue_fork` normalization when session id absent (added during Phase 1 execution)

## Phase 2

- `S003` — Caller passes `None` as `PermissionResolver`
- `S004` — Resolver lacks `.config`
- `S006` — New `SpawnParams` field forgotten in factory accounting
- `S013` — REST server POST with no permission block
- `S020` — `continue_fork=True` with no `continue_session_id`
- `S051` — `PermissionConfig` is frozen after construction
- `S052` — `PermissionResolver.resolve_flags` stays harness-agnostic

## Phase 3

- `S005` — New Claude spec field forgotten in projection
- `S011` — Streaming Claude resolver-internal `--allowedTools` dedupe
- `S012` — Subprocess Claude dedupe parity
- `S015` — Claude spec round-trip with every field populated
- `S021` — Claude subprocess vs streaming byte-equal arg tails
- `S022` — User passes `--append-system-prompt` in `extra_args`
- `S023` — Resolver `--allowedTools` and user passthrough both forwarded verbatim

## Phase 4

- `S007` — Streaming Codex with `sandbox=read-only`
- `S008` — Streaming Codex with `approval=auto`
- `S009` — Streaming Codex with `approval=default`
- `S010` — Streaming Codex confirm rejection emits event
- `S016` — Codex permission matrix semantics
- `S019` — Codex `report_output_path` on streaming path
- `S029` — `codex app-server` rejects passthrough args surfaces cleanly
- `S032` — Codex approval rejection event visible on queue
- `S036` — Delegated field has no consumer
- `S038` — Codex fail-closed capability mismatch

## Phase 5

- `S017` — OpenCode model prefix normalization
- `S018` — OpenCode skills single-injection
- `S034` — `OpenCodeConnection` inherits `HarnessConnection`

## Phase 6

- `S024` — `LaunchContext` parity across runners
- `S025` — Parent Claude permissions forwarded identically
- `S026` — No duplicate constants across runners
- `S046` — `preflight.extra_env` containing `MERIDIAN_*` raises
- `S046b` — `plan_overrides` containing `MERIDIAN_*` raises

## Phase 7

- `S002` — Base `ResolvedLaunchSpec` passed to Claude dispatch
- `S030` — Projection completeness check runs at import
- `S031` — No circular imports
- `S033` — Debug log for passthrough args on streaming
- `S037` — Reserved-flag stripping (retired; remain retired)
- `S039` — Duplicate harness bundle registration raises `ValueError`
- `S043` — `HarnessBundle` missing an extractor fails registration
- `S044` — New `SpawnParams` field unclaimed by any adapter fails at import
- `S045` — `extra_args` is forwarded verbatim to every transport
- `S047` — `mcp_tools` is projected into every harness wire format
- `S049` — Streaming session-id fallback via `HarnessExtractor`
- `S050` — Unsupported `(harness, transport)` dispatch raises

## Phase 8

- `S014` — `run_streaming_spawn` with caller-supplied resolver
- `S027` — `python -O` strips nothing meaningful
- `S028` — Harness binary missing from PATH
- `S035` — All connections satisfy the same `HarnessConnection` surface
- `S041` — `send_cancel` is idempotent across transports
- `S042` — Runner SIGTERM parity across subprocess and streaming
- `S048` — Cancel vs completion race yields exactly one terminal status
