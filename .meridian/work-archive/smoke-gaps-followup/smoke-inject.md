# spawn inject smoke test

No claimed EARS statement IDs were provided with this test request, so coverage is reported by scenario label.

## Setup

- CLI runner for scenarios 1-8: installed `meridian` binary.
- HTTP runner for scenario 9: `uv run meridian app` after `uv sync --extra app --extra dev`, because the installed binary lacked app dependencies.
- Disposable repo: `/tmp/meridian-inject-smoke.GWHr7Z`
- Env:
  - `MERIDIAN_REPO_ROOT=/tmp/meridian-inject-smoke.GWHr7Z`
  - `MERIDIAN_STATE_ROOT=/tmp/meridian-inject-smoke.GWHr7Z/.meridian`
- Minimal config copied into the disposable repo: `mars.toml`, `mars.lock`
- Harness/model used for live runs: `codex` + `gpt-5.4-mini`

## Scenario 1: message inject to live streaming spawn

- Outcome: `verified`
- Classification: expected behavior
- Setup:
  - `meridian streaming serve --harness codex -m gpt-5.4-mini -p 'Start generating 400 numbered lines ... include the literal prefix INJECT-RECEIVED in your response.'`
  - Spawn id: `p3`
- Invocation:
  - `meridian spawn show p3 --format text`
  - `meridian spawn inject p3 'Answer exactly: INJECT-RECEIVED MESSAGE-ONE.' --format text`
- Observed:
  - `spawn show` before inject:
    - `Status: running`
  - inject output:
    - `Message delivered to spawn p3`
  - `spawn show` after completion:
    - `Status: succeeded (exit 0)`
  - `inbound.jsonl`:
    - `{"action":"user_message","data":{"text":"Answer exactly: INJECT-RECEIVED MESSAGE-ONE."},"source":"control_socket",...}`
  - `output.jsonl`:
    - initial assistant message completed with `LINE-001 ... LINE-400`
    - injected user message recorded as a user item
    - second assistant message completed with `INJECT-RECEIVED MESSAGE-ONE.`

## Scenario 2: interrupt inject

- Outcome: `falsified`
- Classification: real bug
- Setup:
  - `meridian streaming serve --harness codex -m gpt-5.4-mini -p 'Start generating 10000 numbered lines ... unless interrupted.'`
  - Spawn id: `p4`
- Invocation:
  - `meridian spawn show p4 --format text`
  - `meridian spawn inject p4 --interrupt --format text`
  - `meridian spawn show p4 --format text`
  - attempted continuation:
    - `meridian spawn inject p4 'Answer exactly: INTERRUPTED-AND-CONTINUED.' --format text`
- Observed:
  - inject output:
    - `Interrupt delivered to spawn p4`
  - immediate post-inject `spawn show`:
    - `Status: failed (exit 1)`
    - `Failure: turn_interrupted`
  - follow-up inject failed:
    - `Error: spawn not running: p4 has no control socket`
  - `inbound.jsonl` recorded the interrupt action.
  - `output.jsonl` ended with:
    - `turn.status":"interrupted"`
- Expected:
  - current turn should stop
  - spawn should remain active and accept follow-up input

## Scenario 3: cancel inject

- Outcome: `falsified`
- Classification: real bug
- Setup:
  - `meridian streaming serve --harness codex -m gpt-5.4-mini -p 'Start generating 10000 numbered lines ... unless cancelled.'`
  - Spawn id: `p5`
- Invocation:
  - `meridian spawn show p5 --format text`
  - `meridian spawn inject p5 --cancel --format text`
  - `meridian spawn show p5 --format text`
- Observed:
  - inject output:
    - `Cancel delivered to spawn p5`
  - post-inject `spawn show`:
    - `Status: succeeded (exit 0)`
  - `spawn log p5` showed `0 assistant messages`
  - `inbound.jsonl` recorded:
    - `{"action":"cancel","data":{},"source":"control_socket",...}`
  - `spawns.jsonl` finalized `p5` as:
    - `status":"succeeded","exit_code":0`
- Expected:
  - terminal status should be `cancelled`, not `succeeded`

## Scenario 4: inject before control.sock exists

- Outcome: `verified`
- Classification: expected behavior in this run
- Setup:
  - immediate post-launch inject against a background spawn
  - spawn creation:
    - `meridian --format json spawn -m gpt-5.4-mini --background -p 'Do not finish quickly. Count from 1 to 500 in order, one per line.'`
  - Spawn id: `p6`
- Invocation:
  - inject was issued immediately after parsing the spawn id:
    - `meridian spawn inject "$race_id" 'RACE-PING' --format text`
- Observed:
  - inject output:
    - `Message delivered to spawn p6`
  - immediate `spawn show` after inject:
    - `Status: running`
  - `inbound.jsonl` recorded:
    - `{"action":"user_message","data":{"text":"RACE-PING"},"source":"control_socket",...}`
- Notes:
  - this verifies the 3x1s socket retry covered the startup race in this attempt
  - I did not find a failing window in this environment

## Scenario 5: inject to non-existent spawn id

- Outcome: `verified`
- Classification: expected behavior
- Invocation:
  - `meridian spawn inject p999999 'hello' --format text`
- Observed:
  - stderr:
    - `Error: spawn not found: p999999`
  - exit code:
    - `1`

## Scenario 6: inject to completed spawn

- Outcome: `verified`
- Classification: expected behavior
- Invocation:
  - `meridian spawn inject p3 'late message' --format text`
- Observed:
  - stderr:
    - `Error: spawn not running: p3 has no control socket`
  - exit code:
    - `1`

## Scenario 7: inject to non-streaming spawn

- Outcome: `blocked`
- Classification: known limitation / coverage gap
- Reason:
  - in this environment the configured user-facing harnesses (`claude`, `codex`, `opencode`) all advertise `supports_bidirectional=True`
  - I did not find a public CLI path in this disposable repo that forced the legacy non-bidirectional subprocess execution path without changing code or config internals

## Scenario 8: double-inject race

- Outcome: `falsified`
- Classification: real bug
- Setup:
  - `meridian streaming serve --harness codex -m gpt-5.4-mini -p 'Generate 400 numbered lines ... acknowledge later user messages exactly as ACK: <message>.'`
  - Spawn id: `p7`
- Invocation:
  - parallel CLI calls:
    - `meridian spawn inject p7 'ALPHA' --format text`
    - `meridian spawn inject p7 'BETA' --format text`
- Observed:
  - both CLI calls returned:
    - `Message delivered to spawn p7`
  - `inbound.jsonl` recorded both messages in order:
    - `ALPHA`
    - `BETA`
  - `output.jsonl` recorded both injected user-message items, but in reversed order:
    - `BETA`
    - `ALPHA`
  - assistant output only acknowledged one message:
    - `ACK: ALPHA`
- Expected:
  - both messages should be handled without loss or reordering corruption

## Scenario 9: HTTP inject parity

### 9a: message inject via `POST /api/spawns/{id}/inject`

- Outcome: `falsified`
- Classification: real bug in lifecycle/reaper, message delivery itself works
- Setup:
  - app server:
    - `uv run meridian app --no-browser --host 127.0.0.1 --port 8429 --allow-unsafe-no-permissions`
  - create spawn:
    - `POST /api/spawns` with `{"harness":"codex","model":"gpt-5.4-mini","prompt":"Generate 400 numbered lines ... include HTTP-INJECT-RECEIVED in your response."}`
  - Spawn id: `p8`
- Invocation:
  - inject:
    - `POST /api/spawns/p8/inject` with `{"text":"Answer exactly: HTTP-INJECT-RECEIVED MESSAGE-ONE."}`
  - status checks:
    - `GET /api/spawns/p8`
    - `meridian spawn show p8 --format text`
- Observed:
  - inject response:
    - `{"ok":true}`
  - app status response after inject:
    - `{"spawn_id":"p8","harness":"codex","state":"connected"}`
  - durable inbound log:
    - `{"action":"user_message","data":{"text":"Answer exactly: HTTP-INJECT-RECEIVED MESSAGE-ONE."},"source":"rest",...}`
  - `output.jsonl` later contained:
    - initial assistant message `HTTP-001 ... HTTP-400`
    - injected user message item
    - assistant message `HTTP-INJECT-RECEIVED MESSAGE-ONE.`
  - but CLI `spawn show` reconciled the same spawn to:
    - `Status: failed (exit 1)`
    - `Failure: missing_worker_pid`
  - `spawns.jsonl` shows conflicting finalizations:
    - first finalize at line 42:
      - `status":"failed","error":"missing_worker_pid"`
    - later finalize at line 43:
      - `status":"succeeded","origin":"launcher"`
  - despite the later success finalize, `meridian spawn show p8` still reports the earlier failure
- Expected:
  - no orphan/reaper false positive while the app-owned `SpawnManager` still reports the spawn as connected

### 9b: interrupt parity via `POST /api/spawns/{id}/inject`

- Outcome: `falsified`
- Classification: documented-but-unimplemented
- Invocation:
  - `POST /api/spawns/p8/inject` with `{"interrupt":true}`
- Observed:
  - HTTP 422
  - body:
    - `{"detail":[{"type":"missing","loc":["body","text"],"msg":"Field required","input":{"interrupt":true}}]}`
- Expected:
  - parity with CLI interrupt injection, or an explicit documented non-support story

### 9c: cancel parity via `POST /api/spawns/{id}/inject`

- Outcome: `falsified`
- Classification: documented-but-unimplemented
- Invocation:
  - `POST /api/spawns/p8/inject` with `{"cancel":true}`
- Observed:
  - HTTP 422
  - body:
    - `{"detail":[{"type":"missing","loc":["body","text"],"msg":"Field required","input":{"cancel":true}}]}`
- Expected:
  - parity with CLI cancel injection, or an explicit documented non-support story

## Summary of gaps

- Real bug:
  - CLI interrupt inject finalizes the spawn as failed (`turn_interrupted`) instead of leaving it resumable.
  - CLI cancel inject finalizes the spawn as `succeeded` instead of `cancelled`.
  - Double inject accepts both requests but reorders/partially loses handling at the user-visible layer.
  - App-managed spawns can be falsely reaped as `missing_worker_pid` while still connected, producing conflicting finalization events and incorrect `spawn show` output.
- Documented-but-unimplemented:
  - `POST /api/spawns/{id}/inject` only supports free-form text today; interrupt/cancel parity with CLI is not implemented.
- Known limitation / coverage gap:
  - no clean public path in this environment to force a non-bidirectional subprocess spawn for scenario 7.
