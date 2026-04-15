# Phase 6: WebSocket and Mapper Hooks

## Round: 4 (after Phases 4 and 5)

## Scope

Instrument `ws_endpoint.py` with mapper-level and WebSocket-level trace hooks. The tracer is fetched from `SpawnManager` and passed into both `_outbound_loop()` and `_inbound_loop()`. The `AGUIMapper` protocol stays unchanged.

## Intent

This closes the observability gap at the app boundary. When a harness event reaches the mapper but produces no AG-UI output, the trace should show the input payload, the empty translation result, and the WebSocket traffic that did or did not reach the client.

## Files to Modify

### `src/meridian/lib/app/ws_endpoint.py`

Update `spawn_websocket()` to fetch the tracer with `manager.get_tracer(SpawnId(spawn_id))` and pass it to both loop tasks.

Update `_outbound_loop()` to:

- record `mapper/translate_input`
- assign `translated = mapper.translate(event)` before iterating
- record `mapper/translate_output`
- record `websocket/ws_send` after each `_send_event(...)`

Update `_inbound_loop()` to:

- record `websocket/ws_recv` for inbound frames
- record `websocket/control_dispatch` for recognized control messages

Do not change `_send_event()` or the `AGUIMapper` protocol.

### Tests to Update or Add

- `tests/test_app_server.py`
- `tests/test_app_agui_phase3.py`

## Dependencies

- **Requires:** Phase 4 and Phase 5.
- **Produces:** `mapper` and `websocket` layer events, completing the end-to-end trace.

## Patterns to Follow

- Keep trace emission local to `ws_endpoint.py`; do not push tracer awareness into mapper implementations.
- Record output counts and event types before the WebSocket send loop so empty translations are visible in the trace.

## Constraints

- Do not widen the control-message surface or change AG-UI semantics.
- The disabled path must remain a simple `None` guard.

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest-llm tests/test_app_server.py tests/test_app_agui_phase3.py` passes
- [ ] Full pipeline smoke test through the app/WebSocket path produces `wire`, `connection`, `drain`, `mapper`, and `websocket` events in one `debug.jsonl`
- [ ] Empty mapper translations produce `output_count: 0` in `translate_output`
- [ ] With debug disabled, WebSocket behavior is unchanged apart from the added `None` guards
