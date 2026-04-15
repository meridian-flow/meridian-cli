# Streaming Adapter Parity — Design Overview

## Problem

Two independent codepaths translate `SpawnParams` into harness configuration:

1. **Subprocess path**: `SpawnParams` → adapter `build_command()` → `build_harness_command()` with strategy completeness guard → CLI args. This path has a checked invariant: every `SpawnParams` field must have a strategy mapping or be in `_SKIP_FIELDS`, else it raises `ValueError`.

2. **Streaming path**: `SpawnParams` → connection adapter (`_build_command()` / `_thread_bootstrap_request()` / `_create_session()`) → CLI args / JSON-RPC params / HTTP payload. This path hand-picks fields with no completeness guard. New fields silently fall through.

The result: streaming Claude agents are silently broken (no skill injection, no native agent payloads), Codex streaming ignores effort/sandbox/approval config, and OpenCode streaming skips effort/fork/model normalization.

Additionally, the two runners (`runner.py`, `streaming_runner.py`) duplicate Claude-specific launch preflight: `_read_parent_claude_permissions()`, `_merge_allowed_tools_flag()`, and session symlink setup.

## Solution

Introduce a **transport-neutral resolved launch spec** as the single source of truth for how `SpawnParams` maps to harness configuration. Both the subprocess and streaming paths consume this spec, never raw `SpawnParams`.

### Architecture

```
SpawnParams + PermissionResolver
        │
        ▼
┌─────────────────────────┐
│  Harness Adapter        │
│  resolve_launch_spec()  │  ← one method per adapter, completeness-checked
└─────────┬───────────────┘
          │
          ▼
   ResolvedLaunchSpec (per-harness subclass)
          │
    ┌─────┴──────┐
    ▼            ▼
build_command()  ConnectionAdapter.start()
(CLI args)       (JSON-RPC / HTTP / stdin)
```

### Key Abstractions

See [resolved-launch-spec.md](resolved-launch-spec.md) for the spec model hierarchy.
See [migration-path.md](migration-path.md) for the phased migration.
See [runner-preflight.md](runner-preflight.md) for runner deduplication.
See [parity-testing.md](parity-testing.md) for the verification strategy.

### Design Docs

| Doc | What it covers |
|-----|---------------|
| [resolved-launch-spec.md](resolved-launch-spec.md) | The `ResolvedLaunchSpec` hierarchy, factory methods, and completeness guard |
| [transport-projections.md](transport-projections.md) | How each transport layer (CLI, JSON-RPC, HTTP, stdin) projects the spec |
| [runner-preflight.md](runner-preflight.md) | Shared runner preflight extraction |
| [migration-path.md](migration-path.md) | 5-phase migration with verification gates |
| [parity-testing.md](parity-testing.md) | Parity test strategy: same spec → equivalent config on both paths |

### Scope

**In scope:**
- Fix upstream effort plumbing bug (`PreparedSpawnPlan` missing `effort` field — D13)
- `ResolvedLaunchSpec` base + per-harness subclasses with semantic permissions (D9)
- Spec factory on each harness adapter with import-time completeness guard
- Retire strategy map machinery, spec becomes single policy layer (D10)
- Rewrite `build_command()` as explicit spec-to-CLI projection
- Rewrite connection adapter config construction as spec projection
- `HarnessConnection.start()` protocol change: accepts spec instead of `SpawnParams` (D12)
- Extract shared runner preflight from `runner.py` and `streaming_runner.py`
- Fix Codex streaming approval-mode bypass (D14)
- Fix Claude streaming missing effort/agent/skill flags
- Fix OpenCode streaming missing effort/fork/model-prefix normalization (D16)
- Machine-checkable completeness guards on both spec factory and transport projections (D15)
- Parity smoke tests

**Out of scope:**
- MCP wiring (all adapters currently return `None` from `mcp_config()`)
- New harness adapters
- Interactive/primary launch path changes (focus is on child spawns)

### Edge Cases and Failure Modes

1. **Empty or None fields**: The spec factory must handle all optional fields correctly. `effort=None` means "don't set effort", not "set effort to empty string". The current strategies already handle this via `if value is None: continue` — the spec factory must preserve this behavior.

2. **Codex approval in non-interactive streaming**: The current streaming adapter auto-accepts all approvals. After the fix, `confirm` mode in non-interactive streaming spawns has no human to approve. The spec carries `permission_config.approval` semantically, and the Codex connection adapter rejects approval requests when `confirm` is set and no interactive channel exists (D14). This surfaces the misconfiguration rather than silently granting permissions.

3. **Passthrough args routing**: Codex subprocess uses `codex exec --json` but streaming uses `codex app-server`. OpenCode subprocess uses `opencode run` but streaming uses `opencode serve`. Passthrough args valid for `exec`/`run` may not work on `app-server`/`serve`. The spec should not include passthrough args in the common fields — they remain transport-specific because their validity depends on the subcommand.

4. **Claude `--resume` + `--fork-session` combination**: Both subprocess and streaming paths must handle resume and fork identically. The spec carries `continue_session_id` and `continue_fork` as resolved values; both transports project them to their respective flags.

5. **Model prefix normalization (OpenCode)**: The `opencode-` prefix strip happens during spec construction, not during transport projection. Both paths get the already-normalized model string.

6. **Report output path (Codex)**: The subprocess path injects `-o report_path` via extra_args. The streaming path doesn't support this. The spec should carry `report_output_path` as a resolved field, but the streaming transport projection may not use it if the Codex JSON-RPC API doesn't support it — in that case the streaming path falls back to artifact-based report extraction (current behavior).
