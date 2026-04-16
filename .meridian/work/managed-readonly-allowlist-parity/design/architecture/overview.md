# Architecture Overview — Managed Read-Only + Tool Allowlist Parity

## Where enforcement is realized (by harness)

| Harness  | Sandbox mechanism                     | Allowlist mechanism                  | Injection point |
|----------|---------------------------------------|--------------------------------------|-----------------|
| codex    | generated `config.toml` `sandbox_mode = "read-only"` + `--sandbox read-only` CLI flag | generated `config.toml` `[features]` + `[apps._default].enabled = false` | per-spawn `CODEX_HOME` written at connection-start |
| claude   | `--permission-mode plan` + mutating-tool denylist union | `--allowedTools` (existing) | CLI args via `project_claude_spec_to_cli_args` |
| opencode | synthesized `OPENCODE_PERMISSION` JSON `"*": "deny"` baseline + read-tool allows | `OPENCODE_PERMISSION` JSON (existing) | `env_overrides(config)` via `PermissionConfig.opencode_permission_override` |

## Shape of the change across layers

```
┌────────────────────────────────────────────────────────────────┐
│ CLI / spawn prep                                               │
│   spawn.py, prepare.py                                         │
│   - collect `sandbox`, `tools:`, `disallowed-tools:`           │
│   - hand to resolve_permission_pipeline()                      │
└────────────────────────────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────────────┐
│ safety/permissions.py  (policy layer)                          │
│   - resolve_permission_pipeline() returns (config, resolver)   │
│   - NEW: when sandbox == "read-only", synthesize a read-only   │
│     baseline and union with explicit tool lists.               │
│   - NEW: capability check — if the harness adapter's           │
│     capability flags don't cover the requested axis,           │
│     raise HarnessCapabilityMismatch.                           │
└────────────────────────────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────────────┐
│ harness/adapter.py  (mechanism-neutral wiring)                 │
│   - HarnessCapabilities gains three new fields:                │
│     supports_managed_sandbox, supports_managed_allowlist,      │
│     supports_managed_denylist.                                 │
│   - _permission_flags_for_harness() gains claude read-only     │
│     → plan + denylist mapping.                                 │
└────────────────────────────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────────────┐
│ Per-harness adapter (mechanism)                                │
│   codex.py:   - NEW `env_overrides` returns CODEX_HOME         │
│               - NEW helper materializes codex-home dir         │
│               - FIX resolve_session_file honors launch_env     │
│   claude.py:  - projection unchanged (CLI flags)               │
│   opencode.py:- env_overrides unchanged; policy layer fills    │
│                 opencode_permission_override                   │
└────────────────────────────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────────────────────────────┐
│ launch/ (lifecycle)                                            │
│   connections/codex_ws.py       — already mkdirs spawn log dir │
│   launch/streaming_runner.py    — codex streaming start        │
│   launch/env.py                 — allowlist gains CODEX_HOME   │
│   - NEW: connection-start hook materializes CODEX_HOME for     │
│     codex spawns, writes config.toml atomically, copies auth.  │
└────────────────────────────────────────────────────────────────┘
```

## Module-level responsibilities (new and changed)

### New module: `harness/codex_home.py`

Single source of truth for the per-spawn `CODEX_HOME` materialization.
Responsibilities:
- Compute the path: `.meridian/spawns/<spawn_id>/codex-home/`.
- Render `config.toml` content from a `CodexHomePlan` dataclass.
- Atomic write via tmp+rename (matches `lib/state/` convention).
- Narrow auth copy (`auth.json`, `.credentials.json` if present).
- Public surface:
  - `build_codex_home_plan(config, resolver) -> CodexHomePlan`
  - `materialize_codex_home(spawn_id, plan) -> Path`
  - `format_codex_config_toml(plan) -> str` (also used for dry-run)

Why a separate module: projections (`project_codex_*`) stay CLI-shape-only
per requirements.md constraint; the codex adapter (`codex.py`) stays small
and focused on CLI/spec shape; materialization has its own home with its
own tests.

### Changed: `harness/codex.py`

- `env_overrides(config)` returns `{"CODEX_HOME": str(spawn_codex_home)}`
  when the per-spawn home has been materialized. The path is computed
  from `spawn_id`, which is now available in `PermissionConfig` (see
  next section) or threaded through a fresh `env_overrides(config,
  spawn_id)` signature.
- `resolve_session_file(repo_root, session_id)` consults
  `launch_env["CODEX_HOME"]` first, then falls back to
  `~/.codex / "sessions"`. See `refactors.md` R1.

### Changed: `safety/permissions.py`

- `PermissionConfig` gains an opaque `codex_config_toml` field (or a
  separate `CodexPermissionPlan` sidecar object) so the codex adapter
  can render it without re-deriving state.
- `resolve_permission_pipeline` gains: when `sandbox == "read-only"`,
  synthesize a read-only baseline for opencode even when tool lists are
  empty (currently the override is only populated when tool lists are
  non-empty, per `permissions.py:308-312`).
- `resolve_permission_pipeline` gains a capability-check parameter
  (`harness_capabilities: HarnessCapabilities`) and raises
  `HarnessCapabilityMismatch` when the requested axes exceed capabilities.

### Changed: `harness/adapter.py`

- `HarnessCapabilities` gains three booleans (see diagram above).
- `_permission_flags_for_harness` gains claude read-only handling: when
  `config.sandbox == "read-only"` and `config.approval == "default"` and
  `harness_id == CLAUDE`, emit `("--permission-mode", "plan")`. Denylist
  union happens in the permission resolver (not here) so the
  `project_claude_*` path naturally folds it into `--disallowedTools`.

### Changed: `harness/projections/project_codex_subprocess.py`

- Delete `_strip_tool_flags_for_codex` and its warnings. Deletion is the
  signal that parity is achieved.
- Keep the rest (the `-c approval_policy=...` and `--sandbox` emission).

### Changed: `launch/env.py`

- Add `CODEX_HOME` to the child-env allowlist (next to `HOME`, `PATH`,
  etc.), per the p1730 finding that currently `CODEX_HOME` does not pass
  the sanitization allowlist.

### Changed: `launch/` connection-start

- Codex connection-start hook (`codex_ws.py` and the streaming runner
  where `process.py` forks codex) calls
  `materialize_codex_home(spawn_id, plan)` before the child launches.
  Materialization happens after the spawn log dir already exists
  (minimizes new lifecycle surface area).

## Lifecycle of a codex read-only spawn

1. CLI parses `--sandbox read-only` (or profile provides it) and profile
   `tools: [Read, Grep, Glob]`.
2. `prepare.py` composes `SpawnParams` and calls
   `resolve_permission_pipeline`.
3. Policy layer synthesizes a `CodexPermissionPlan`:
   - `sandbox_mode = "read-only"`
   - `approval_policy = "never"`
   - `[features] apps = false, web_search = false, ...`
   - `[apps._default] enabled = false`
   - `default_permissions = "read_only"` +
     `[permissions.read_only.filesystem] :project_roots = "read"` +
     `[permissions.read_only.network] enabled = false`
4. Capability check: codex adapter advertises full managed support →
   pass. No `HarnessCapabilityMismatch`.
5. Connection-start hook calls
   `materialize_codex_home(spawn_id, plan)` which:
   - `mkdir -p .meridian/spawns/<spawn_id>/codex-home/`
   - atomic write `config.toml` from `format_codex_config_toml(plan)`
   - symlink or copy `~/.codex/auth.json` if present
   - symlink or copy `~/.codex/.credentials.json` if present
6. `codex.env_overrides(config, spawn_id)` returns
   `{"CODEX_HOME": "<spawn>/codex-home"}` which merges into the launch env.
7. `project_codex_spec_to_cli_args` emits `codex exec --profile
   meridian --sandbox read-only -c approval_policy="never" ...` (no
   allowlist flag; allowlist lives entirely in the per-spawn config).
8. Codex launches, loads `$CODEX_HOME/config.toml`, honors the locked-down
   profile.
9. On session resolution, `CodexAdapter.resolve_session_file` now reads
   from `$CODEX_HOME/sessions/` instead of `~/.codex/sessions/`.

## Lifecycle of a claude read-only spawn

1. CLI parses `--sandbox read-only` and profile `tools: [Read, Grep, Glob]`,
   `disallowed-tools: []`.
2. `prepare.py` composes `SpawnParams` and calls
   `resolve_permission_pipeline`.
3. Policy layer: the existing resolver path already handles
   `allowed_tools`. For read-only, it unions
   `(Edit, Write, MultiEdit, NotebookEdit, Bash, WebFetch)` into the
   `disallowed_tools` tuple before building the resolver.
4. Capability check: claude adapter advertises managed sandbox (via plan
   mode), managed allowlist, managed denylist → pass.
5. `adapter._permission_flags_for_harness` emits
   `("--permission-mode", "plan")` because sandbox is read-only and
   approval is default.
6. `project_claude_spec_to_cli_args` emits
   `claude ... --permission-mode plan --allowedTools Read,Grep,Glob
   --disallowedTools Edit,Write,MultiEdit,NotebookEdit,Bash,WebFetch`.

## Lifecycle of an opencode read-only spawn

1. CLI parses `--sandbox read-only` and profile
   `tools: [Read, Grep, Glob]`.
2. `prepare.py` composes `SpawnParams` and calls
   `resolve_permission_pipeline`.
3. Policy layer: synthesizes `OPENCODE_PERMISSION` JSON
   `{"*":"deny","read":"allow","grep":"allow","glob":"allow"}` (the
   intersection of read-only baseline and allowlist, per SO-2).
4. Capability check: opencode adapter advertises full managed support → pass.
5. `OpenCodeAdapter.env_overrides(config)` returns
   `{"OPENCODE_PERMISSION": "..."}` (existing path).
6. OpenCode launches, honors the env permission JSON.
