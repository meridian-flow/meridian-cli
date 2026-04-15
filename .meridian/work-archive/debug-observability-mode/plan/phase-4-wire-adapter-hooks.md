# Phase 4: Harness Wire Hooks

## Round: 3 (parallel with Phase 5)

## Scope

Instrument Claude, Codex, and OpenCode with wire-level and state-transition trace hooks. Each adapter stores `self._tracer = config.debug_tracer` during `start()` and emits trace records only at real transport boundaries.

## Intent

This is the highest-value diagnostic layer. When a harness speaks the wrong protocol, the wire trace shows what Meridian sent, what the harness returned, and where the adapter dropped or reclassified data before the rest of the pipeline saw it.

## Files to Modify

### `src/meridian/lib/harness/connections/claude_ws.py`

Add tracer storage plus hooks for:

- `_set_state()` -> `connection/state_change`
- `_send_json()` -> `wire/stdin_write`
- `events()` raw line reads -> `wire/stdout_line`
- parsed harness events -> `wire/parsed_event`
- malformed or non-object lines -> `wire/parse_error`
- `_signal_process()` -> `wire/signal_sent`

### `src/meridian/lib/harness/connections/codex_ws.py`

Add tracer storage plus hooks for:

- `_transition()` -> `connection/state_change`
- `_request()` -> `wire/ws_send_request`
- `_notify()` -> `wire/ws_send_notify`
- `_read_messages_loop()` raw frames -> `wire/ws_recv`
- response dispatch -> `wire/ws_recv_response`
- notification dispatch -> `wire/ws_recv_notification`
- malformed JSON-RPC frames -> `wire/frame_dropped`

Important: emit the malformed-frame trace in `_read_messages_loop()` after `_parse_jsonrpc(raw_text)` returns `None`. Do not make the module-level parser helper tracer-aware.

### `src/meridian/lib/harness/connections/opencode_http.py`

Add tracer storage plus hooks for:

- `_transition()` -> `connection/state_change`
- `_post_json()` request/response pairs -> `wire/http_post` and `wire/http_response`
- `_create_session()` path attempts -> `wire/http_probe`
- `_open_event_stream()` path attempts and successful stream open -> `wire/http_probe` and `wire/sse_connect`
- parsed stream events -> `wire/sse_event`
- malformed stream payloads -> `wire/parse_error`

### Tests to Update or Add

- `tests/test_streaming_serve.py`
- `tests/harness/test_codex_ws.py`
- focused adapter tests if existing files are not enough to cover the new trace hooks

## Dependencies

- **Requires:** Phase 1, Phase 2, Phase 3.
- **Produces:** `wire` and `connection` layer events for all supported harnesses.
- **Independent of:** Phase 5.

## Patterns to Follow

- Use the shared trace helpers whenever the event shape matches.
- Use direct `tracer.emit(...)` only for adapter-specific event shapes such as Codex response/notification metadata.
- Keep trace calls out of control-flow decisions. The tracer absorbs its own failures.

## Constraints

- Do not change adapter method signatures.
- Instrument all three adapters in this phase. Partial coverage defeats the feature.
- The disabled path must remain a cheap `None` check plus normal adapter behavior.

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] Targeted adapter and streaming tests pass
- [ ] Smoke test each supported harness with debug enabled and verify `wire` and `connection` events appear
- [ ] The smoke report explicitly states which of `claude`, `codex`, and `opencode` were exercised
- [ ] With debug disabled, adapter behavior is unchanged apart from the stored `None` tracer attribute
