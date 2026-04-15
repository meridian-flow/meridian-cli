# Transport Projections

## Purpose

Each transport layer (CLI, JSON-RPC, HTTP, stdin-pipe) mechanically projects a `ResolvedLaunchSpec` into its native format. No semantic decisions happen here — all normalization, permission resolution, and field mapping already happened during spec construction.

## Claude Transport Projections

### Subprocess (CLI args)

Source: `ClaudeAdapter.build_command()` — rewritten to take `ClaudeLaunchSpec`.

```
ClaudeLaunchSpec → CLI args
──────────────────────────────────────────
model           → --model <value>
effort          → --effort <value>      (already normalized to "max" etc.)
agent_name      → --agent <value>
appended_system_prompt → --append-system-prompt <value>
agents_payload  → --agents <value>
continue_session_id → --resume <value>
continue_fork   → --fork-session        (only if continue_session_id set)
permission_config + permission_resolver → resolver.resolve_flags(HarnessId.CLAUDE) appended
mcp_config      → mcp_config.command_args appended (currently None)
extra_args      → appended directly
prompt          → "-" (stdin mode) or first positional (interactive)
interactive     → switches base command from [claude -p --output-format stream-json --verbose] to [claude]
```

### Streaming (stdin stream-json)

Source: `ClaudeConnection._build_command()` — rewritten to take `ClaudeLaunchSpec`.

The streaming path uses the same Claude subprocess but with `--input-format stream-json --output-format stream-json`. The spec fields project to CLI args identically to the subprocess path, except:

- `prompt` is sent via stdin JSON (`{"type":"user","message":{"role":"user","content":"..."}}`) instead of CLI arg.
- `interactive` is always false for streaming connections.
- `report_output_path` is not used (reports extracted from output.jsonl).

```
ClaudeLaunchSpec → streaming CLI args
──────────────────────────────────────────
model           → --model <value>
effort          → --effort <value>
agent_name      → --agent <value>
appended_system_prompt → --append-system-prompt <value>
agents_payload  → --agents <value>
continue_session_id → --resume <value>
continue_fork   → --fork-session
permission_config + permission_resolver → resolver.resolve_flags(HarnessId.CLAUDE) appended
extra_args      → appended directly
```

**Current gap filled:** The streaming path currently skips `effort`, `agent_name`, `appended_system_prompt`, `agents_payload`, and `permission_flags`. After this change, the spec projection is a mechanical mapping that includes all of them.

## Codex Transport Projections

### Subprocess (CLI args)

Source: `CodexAdapter.build_command()` — rewritten to take `CodexLaunchSpec`.

```
CodexLaunchSpec → CLI args (codex exec --json)
──────────────────────────────────────────
model           → --model <value>
effort          → -c model_reasoning_effort="<value>"
permission_config + permission_resolver → resolver.resolve_flags(HarnessId.CODEX) appended
continue_session_id → subcommand: resume <value>
report_output_path → -o <value>         (injected via extra_args)
prompt          → "-" (stdin mode) or last positional
extra_args      → appended before prompt
```

### Streaming (JSON-RPC via WebSocket)

Source: `CodexConnection._thread_bootstrap_request()` — rewritten to take `CodexLaunchSpec`.

The Codex streaming path launches `codex app-server --listen ws://...` as the subprocess, then communicates via JSON-RPC. The spec projects differently for the server launch command vs. the JSON-RPC session bootstrap:

**Server launch command:**
```
CodexLaunchSpec → codex app-server CLI args
──────────────────────────────────────────
(server takes no model/effort/permission flags — those go to JSON-RPC)
extra_args      → WARNING: exec-only args may not work on app-server.
                  The spec should separate server_args from exec_args if needed.
                  For now, passthrough args are forwarded as-is (current behavior).
```

**JSON-RPC thread bootstrap:**
```
CodexLaunchSpec → JSON-RPC params
──────────────────────────────────────────
model           → {"model": "<value>"}
effort          → {"config": {"model_reasoning_effort": "<value>"}}
                  (OR server-level config — depends on Codex app-server API)
continue_session_id → threadId in thread/resume or thread/fork
continue_fork   → method: thread/fork (vs thread/resume vs thread/start)
```

**Permission handling in streaming (D9, D14):**

The spec carries `permission_config.approval` as a semantic value. The Codex streaming projection maps it to approval-request behavior:

```
permission_config.approval → approval request handling
──────────────────────────────────────────
"yolo"    → accept all (current behavior, now explicit)
"auto"    → accept all
"default" → accept all (Codex default is auto-accept in exec mode)
"confirm" → reject with error + log warning (no interactive channel; D14)
```

The CLI projection calls `spec.permission_resolver.resolve_flags(HarnessId.CODEX)` to get sandbox/approval flags.

**Current gaps filled:** effort, approval-mode-aware request handling, sandbox flags (via CLI projection for subprocess, via semantic mapping for streaming).

## OpenCode Transport Projections

### Subprocess (CLI args)

Source: `OpenCodeAdapter.build_command()` — rewritten to take `OpenCodeLaunchSpec`.

```
OpenCodeLaunchSpec → CLI args (opencode run)
──────────────────────────────────────────
model           → --model <value>       (already normalized: opencode- prefix stripped)
effort          → --variant <value>
continue_session_id → --session <value>
continue_fork   → --fork
permission_config → env_overrides via adapter.env_overrides(config) (OPENCODE_PERMISSION)
prompt          → "-" (stdin mode) or last positional
extra_args      → appended before prompt
```

### Streaming (HTTP API)

Source: `OpenCodeConnection._create_session()` — rewritten to take `OpenCodeLaunchSpec`.

The OpenCode streaming path launches `opencode serve --port <N>` as the subprocess, then communicates via HTTP.

**Server launch command:**
```
OpenCodeLaunchSpec → opencode serve CLI args
──────────────────────────────────────────
(server takes --port only; model/effort go to HTTP session)
extra_args      → WARNING: run-only args may not work on serve.
```

**HTTP session creation:**
```
OpenCodeLaunchSpec → HTTP POST /session payload
──────────────────────────────────────────
model           → {"model": "<value>", "modelID": "<value>"}
agent_name      → {"agent": "<value>"}
skills          → {"skills": [<values>]}
continue_session_id → {"session_id": "<value>", "continue_session_id": "<value>"}
effort          → (no current HTTP param — investigate opencode API)
continue_fork   → (no current HTTP param — investigate opencode API)
```

**Current gaps filled:** model prefix normalization (done in spec, not transport), effort (pending opencode API support), fork (pending opencode API support).

## Passthrough Args Warning

Both Codex and OpenCode use different subcommands for subprocess (`exec`/`run`) vs. streaming (`app-server`/`serve`). Passthrough args designed for one subcommand may not work on the other.

**Current behavior:** passthrough args are forwarded to whichever subcommand is in use. This is correct — the user/caller is responsible for knowing which subcommand they're targeting.

**Design decision:** The spec carries `extra_args` as-is. The transport projection forwards them to the appropriate subcommand. No attempt to filter or validate — that's the caller's responsibility. However, the streaming runner should log a debug-level warning when passthrough args are present, since they may not be valid for the server subcommand.

## ConnectionConfig Changes

After Phase 4, `ConnectionConfig` carries transport-level config only. During Phase 3, `model` stays for Codex/OpenCode backward compatibility (D11):

```python
@dataclass(frozen=True)
class ConnectionConfig:
    spawn_id: SpawnId
    harness_id: HarnessId
    model: str | None        # stays until Phase 4 (D11)
    prompt: str              # still needed for initial message send
    repo_root: Path
    env_overrides: dict[str, str]
    timeout_seconds: float | None = None
    ws_bind_host: str = "127.0.0.1"
    ws_port: int = 0
    debug_tracer: DebugTracer | None = None
```

Updated `HarnessConnection.start()` signature (D12):

```python
async def start(
    self,
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec,
) -> None:
```

`SpawnParams` is removed from `start()`. The spec replaces it entirely. The streaming runner:
1. Extracts `plan.execution.permission_resolver` (new plumbing — previously unused by streaming path).
2. Calls `adapter.resolve_launch_spec(run_params, permission_resolver)`.
3. Passes the spec to `connection.start(config, spec)`.

`SpawnManager.start_spawn()` is updated to accept and forward the spec. SpawnManager does NOT construct specs — it's a transport coordinator. The streaming runner provides the spec.
