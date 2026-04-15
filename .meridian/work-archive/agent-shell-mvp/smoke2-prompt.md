# Smoke Test Round 2: agent-shell-mvp

The Claude streaming serve basic flow works (events flow to output.jsonl after the stdin/stdout fix). Test the remaining items.

Use `uv run meridian` (local source). Run `uv sync --extra app` first.

## Test 1: spawn inject round-trip

Start streaming serve, inject a message, confirm Claude responds to it.

1. Start: `timeout 120 uv run meridian streaming serve --harness claude -p "You are a helpful assistant. Wait for my questions." > /tmp/serve_out.txt 2>&1 &`
2. Wait ~10s for Claude to connect
3. Get spawn ID from `/tmp/serve_out.txt`
4. Check `output.jsonl` has initial events
5. Run: `uv run meridian spawn inject <ID> "How many files are in the current directory?"`
6. Wait ~15s
7. Check `inbound.jsonl` recorded the inject
8. Check `output.jsonl` has NEW events after the inject timestamp
9. Kill the background process

Key question: does output.jsonl grow after inject? If yes, round-trip works.

## Test 2: meridian app end-to-end

1. Start: `timeout 120 uv run meridian app --no-browser --port 8420 > /tmp/app_out.txt 2>&1 &`
2. Wait ~5s
3. `curl -s http://localhost:8420/api/spawns` — should return empty list
4. `curl -s -X POST http://localhost:8420/api/spawns -H 'Content-Type: application/json' -d '{"harness":"claude","prompt":"Say exactly: SMOKE TEST PASSED"}'` — should return spawn_id
5. Wait ~5s
6. `curl -s http://localhost:8420/api/spawns` — should show the spawn
7. Write a small Python script to a file, then run it, to test WebSocket:
   - Connect to `ws://localhost:8420/ws/spawn/{spawn_id}`
   - Receive events, print their types
   - Look for RUN_STARTED, text events, RUN_FINISHED
8. Kill the background process

Important: for the Python WebSocket test, write the script to a .py file first, then run it. Don't try to inline Python with f-strings in bash — it causes quoting issues.

## Test 3: Frontend build

```bash
cd frontend
pnpm install
pnpm tsc --noEmit
pnpm build
ls -la dist/
```

## Report format

For each test: PASS/FAIL/BLOCKED with specific observations. Include event types seen, error messages, line counts.
