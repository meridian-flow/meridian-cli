# Smoke Test: agent-shell-mvp

You are testing the agent-shell-mvp implementation — bidirectional streaming, FastAPI server, and React UI. This code has passed static checks (pyright, ruff, existing pytest) but has NEVER been run against a real harness.

## What to test

### Phase 1: Bidirectional Streaming

1. **`meridian streaming serve`** — Does it start? Does it launch a harness subprocess? Does output flow to output.jsonl?
   ```bash
   uv run meridian streaming serve --harness claude -p "List files in the current directory"
   ```
   - Verify spawn_id is printed
   - Verify `.meridian/spawns/<id>/output.jsonl` gets events
   - Verify `.meridian/spawns/<id>/control.sock` exists

2. **`meridian spawn inject`** — Does it deliver a message through the control socket?
   ```bash
   uv run meridian spawn inject <spawn_id> "What files did you find?"
   ```
   - Verify message is delivered (check output.jsonl for response)
   - Verify `.meridian/spawns/<id>/inbound.jsonl` records the inject
   - Test `--interrupt` flag

3. **Connection state machine** — Does `streaming serve` handle harness exit cleanly? Does it handle Ctrl-C?

### Phase 2: FastAPI + AG-UI

4. **`meridian app --no-browser`** — Does the server start?
   ```bash
   uv run meridian app --no-browser --port 8420
   ```
   - Does it start without errors?
   - Does `GET http://localhost:8420/api/spawns` return `[]`?

5. **Spawn via REST** — Can you start a spawn through the API?
   ```bash
   curl -X POST http://localhost:8420/api/spawns -H 'Content-Type: application/json' -d '{"harness": "claude", "prompt": "List files"}'
   ```
   - Does it return a spawn_id?

6. **WebSocket streaming** — Connect to `ws://localhost:8420/ws/spawn/{spawn_id}`:
   - Do you receive RUN_STARTED?
   - Do you receive CUSTOM capabilities event?
   - Do AG-UI events flow (text, tool calls, reasoning)?
   - Send a user_message frame — does the harness receive it?

### Phase 3: React UI

7. **Frontend build** — Does it build?
   ```bash
   cd frontend && pnpm install && pnpm build
   ```

8. **TypeScript** — Does it type-check?
   ```bash
   cd frontend && pnpm tsc --noEmit
   ```

## What to report

For each test:
- **PASS**: describe what you observed
- **FAIL**: describe the error, include stack traces, relevant logs
- **BLOCKED**: describe what prevented testing (missing dep, harness not available, etc.)

Focus on Phase 1 and Phase 2 first — those are the foundation. Phase 3 build verification is secondary.

Important: Use `uv run meridian` (not `meridian`) to test against local source. Run `uv sync --extra app` first to install app dependencies.
