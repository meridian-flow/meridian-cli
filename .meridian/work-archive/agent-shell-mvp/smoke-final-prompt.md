# Final Smoke Test: agent-shell-mvp

All known bugs are fixed. Verify the complete stack works end-to-end.

Use `uv run meridian` (local source). Run `uv sync --extra app` first.

## Test 1: streaming serve + inject round-trip

1. `timeout 90 uv run meridian streaming serve --harness claude -p "You are a helpful assistant. Wait for instructions." > /tmp/serve.log 2>&1 &`
2. Sleep 15s (give Claude time to start and respond)
3. Get spawn ID from /tmp/serve.log
4. Verify output.jsonl has events (wc -l, head -1)
5. `uv run meridian spawn inject <id> "Count to 5"` — should succeed (may retry once for socket)
6. Sleep 15s
7. Verify output.jsonl grew (new events after inject)
8. Verify inbound.jsonl recorded the inject
9. Kill background process

## Test 2: meridian app WebSocket e2e

1. `timeout 90 uv run meridian app --no-browser --port 8420 > /tmp/app.log 2>&1 &`
2. Sleep 5s
3. `curl -s http://localhost:8420/api/spawns` — should return []
4. Start a spawn via POST:
   ```
   curl -s -X POST http://localhost:8420/api/spawns -H 'Content-Type: application/json' -d '{"harness":"claude","prompt":"Say exactly: SMOKE TEST PASSED"}'
   ```
5. Sleep 5s
6. Get spawn_id from `curl -s http://localhost:8420/api/spawns`
7. Write a Python WebSocket test to /tmp/ws_test.py, then run it:
   - Connect to ws://localhost:8420/ws/spawn/{spawn_id}
   - Collect events for 30s or until RUN_FINISHED
   - Print each event type
   - Report: did you see RUN_STARTED? Text events? RUN_FINISHED?
8. Kill background process

## Test 3: Frontend serves from meridian app

1. Verify frontend/dist/ exists and has files
2. Start `uv run meridian app --no-browser --port 8421 > /tmp/app2.log 2>&1 &`
3. Sleep 3s
4. `curl -s http://localhost:8421/ | head -5` — should return HTML
5. Kill background process

## Report

For each test: PASS or FAIL with specific output. If FAIL, include the error.
