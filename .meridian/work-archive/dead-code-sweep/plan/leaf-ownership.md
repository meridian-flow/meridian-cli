# Leaf Ownership Ledger — dead-code sweep

These `S-*` IDs are derived from `requirements.md` because this cleanup item has
no standalone `design/spec/` tree.

| EARS ID | Owning phase | Status | Tester lane | Evidence pointer | Notes |
|---|---|---|---|---|---|
| `S-AUTH-001` | `Phase 1` | `pending` |  |  | Delete `authorization.py` and all `authorize()` call sites. |
| `S-AUTH-002` | `Phase 1` | `pending` |  |  | Delete SO_PEERCRED / peer-cred plumbing. |
| `S-AUTH-003` | `Phase 1` | `pending` |  |  | Delete `/proc/<pid>/environ` caller-environment reader. |
| `S-AUTH-004` | `Phase 1` | `pending` |  |  | Delete `caller_from_env`, `_caller_from_http`, and `_caller_from_socket_peer`. |
| `S-AUTH-005` | `Phase 1` | `pending` |  |  | Remove auth-specific `MERIDIAN_SPAWN_ID` reads while preserving legitimate parent tracking. |
| `S-AUTH-006` | `Phase 1` | `pending` |  |  | Remove archived `AUTH-*` leaves plus the archived auth spec/architecture docs. |
| `S-AUTH-007` | `Phase 1` | `pending` |  |  | Add `D-25`, revert `D-06` / `D-14` / `D-19`, and restate success criterion 5. |
| `S-TOOL-001` | `Phase 1` | `pending` |  |  | Remove cancel from the MCP agent-tool surface. `derived from D-02` |
| `S-TOOL-002` | `Phase 1` | `pending` |  |  | Remove interrupt capability from the MCP agent-tool surface while keeping cooperative inject. `derived from D-02` |
| `S-DEL-001` | `Phase 1` | `pending` |  |  | Delete `CancelControl` and the `cancel` arm of `ControlMessage`. |
| `S-DEL-002` | `Phase 1` | `pending` |  |  | Delete the control-socket `message_type == "cancel"` shim. |
| `S-DEL-003` | `Phase 1` | `pending` |  |  | Delete `spawn_inject.py` `--cancel` / `action="cancel"` support. |
| `S-DEL-004` | `Phase 1` | `pending` |  |  | Delete `legacy_delete_spawn()` and `DELETE /api/spawns/{id}`. |
| `S-DEL-005` | `Phase 2` | `pending` |  |  | Delete `_read_background_pid()` and unreachable `background.pid` fallback. |
| `S-DEL-006` | `Phase 2` | `pending` |  |  | Delete `wrapper_pid` schema/write-only ballast. |
| `S-DEL-007` | `Phase 2` | `pending` |  |  | Delete `LEGACY_RECONCILER_ERRORS` and `resolve_finalize_origin()` shims. |
| `S-DEL-008` | `Phase 3` | `pending` |  |  | Delete retired `register_connection()` shim. |
| `S-DEL-009` | `Phase 3` | `pending` |  |  | Delete `launch/claude_preflight.py` wrapper after redirecting the live import. |
| `S-DEL-010` | `Phase 2` | `pending` |  |  | Remove ignored `store_name` parameter from `append_event()`. |
| `S-DEL-011` | `Phase 2` | `pending` |  |  | Delete `parent_spawn_id`, `child_context()`, and `MERIDIAN_PARENT_SPAWN_ID`. |
| `S-DEL-012` | `Phase 2` | `pending` |  |  | Delete `resolve_work_items_dir()` and `resolve_work_archive_scratch_dir()`. |
| `S-DEL-013` | `Phase 2` | `pending` |  |  | Delete `_SPEC_HANDLED_FIELDS` and `_REGISTRY` launch-spec scaffolding. |
| `S-DEL-014` | `Phase 3` | `pending` |  |  | Delete verified orphaned modules from `D-01`: `agui_types`, `stream_capture`, `terminal`, `timeout`, `reaper_config`. |
| `S-DEL-015` | `Phase 2` | `pending` |  |  | Rename `missing_worker_pid` to `missing_runner_pid` on the live reaper path. |
| `S-DEL-016` | `Phase 1` | `pending` |  |  | Remove the `ws_endpoint` `caller_from_env()` fallback as part of auth deletion. |
| `S-VER-001` | `Phase 4` | `pending` |  |  | `ruff`, `pyright`, and `pytest-llm` all pass after cleanup. |
| `S-DIST-001` | `Phase 4` | `pending` |  |  | Reinstall the global `meridian` binary and confirm version parity with source. |
| `S-SMOKE-001` | `Phase 5` | `pending` |  |  | Re-run the cancel/interrupt smoke lane and record outcomes. |
| `S-SMOKE-002` | `Phase 5` | `pending` |  |  | Re-run the AF_UNIX/liveness smoke lane and record outcomes. |
| `S-SMOKE-003` | `Phase 5` | `pending` |  |  | Capture surviving blockers as follow-up scope only, not fixes. |
