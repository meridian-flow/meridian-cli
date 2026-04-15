# Explorer: Per-adapter port audit (Claude, Codex, OpenCode)

You are an explorer. Do not make code changes. Report facts only.

## Task

For each of the three harness adapters, audit the streaming connection implementation against the subprocess `build_command()` implementation, using the `ResolvedLaunchSpec` as the common contract. Goal: find any field that the subprocess path projects but the streaming path silently drops (or vice versa).

## Method per harness

For each harness, produce a table like this:

| Spec field | Subprocess projection (`build_command`) | Streaming projection (connection adapter) | Parity? |
|---|---|---|---|

Fill it in by reading:

- **Claude:** `src/meridian/lib/harness/claude.py` (for `build_command`) and `src/meridian/lib/harness/connections/claude_ws.py` (for the streaming projection — likely `_build_command` or equivalent).
- **Codex:** `src/meridian/lib/harness/codex.py` (for `build_command`) and `src/meridian/lib/harness/connections/codex_ws.py` (for `_thread_bootstrap_request` / `_create_session` / equivalent).
- **OpenCode:** `src/meridian/lib/harness/opencode.py` (for `build_command`) and `src/meridian/lib/harness/connections/opencode_http.py` (for the HTTP payload builder).

Mark "Parity?" as one of:
- **match** — both transports honor the field equivalently.
- **asymmetry (documented)** — transports differ and the difference is explicitly acknowledged per D16 or edge case 3/6 in `overview.md`.
- **asymmetry (undocumented)** — transports differ and nothing in the design allows it; this is a bug.

## Specific things to double-check

1. **Claude:**
   - `appended_system_prompt` / `agents_payload` / `skills` — is the streaming path now emitting `--append-system-prompt` and `--agents`? (D1 constraint: this was the main bug.)
   - Effort normalization — is the pre-normalized value reaching both transports?
   - `--resume` + `--fork-session` combination (edge case 4).

2. **Codex:**
   - `sandbox_mode` / `approval` / effort in the JSON-RPC params (streaming should now honor these).
   - Approval handling: when `confirm` is set and the streaming connection is non-interactive, does it reject (D14) or still auto-accept?
   - Report output path (edge case 6): subprocess injects `-o report_path`; does streaming honor it or fall back to artifact extraction?

3. **OpenCode:**
   - Model prefix normalization (`opencode-` strip) — does the spec factory produce the stripped value, and do both transports consume it?
   - Effort / fork handling on the HTTP path — per D16, these may not be supported by the HTTP API. If so, is the asymmetry logged and documented?
   - `OPENCODE_PERMISSION` env handling for permission config.

4. **HarnessConnection.start() signature.** In `src/meridian/lib/harness/connections/base.py`, does `start()` accept `(config, spec)` per D12? Walk through who calls it: `SpawnManager.start_spawn()`, `run_streaming_spawn()`, any test fixtures. Are all callers updated?

5. **Streaming entrypoints.** Verify that `run_streaming_spawn()`, `streaming_serve.py`, and `server.py` all call `adapter.resolve_launch_spec()` rather than constructing a generic spec directly. (D17 triage flagged this as the main fix.)

## Reference files
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/harness/connections/base.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `.meridian/work-archive/streaming-adapter-parity/design/transport-projections.md`
- `.meridian/work-archive/streaming-adapter-parity/decisions.md`

## Deliverable

Three parity tables (one per harness), plus a short "start() callers" audit and a "streaming entrypoint factory usage" audit. Quote exact code for any asymmetry you classify as undocumented.
