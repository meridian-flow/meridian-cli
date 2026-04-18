# Post-R06 Review — Correctness + Regression Risk

## Context

R06 (hexagonal launch core) was shipped by spawn `p1900` across 6 commits on main (`3f8ad4c`, `5e8aae1`, `b19d999`, `bf4cf6c`, `c042478`, `efad4c0`). The orchestrator did all the work inline (no coder/tester/reviewer subagents were spawned). Unit tests pass but no end-to-end review happened. You're the correctness reviewer.

Your lane: **does this refactor break observable behavior?** Not "is it well-structured" (that's another reviewer). Not "does it match the design" (another reviewer). You look for **regressions**: things that worked before and might not work now.

## Read first

- `.meridian/spawns/p1900/report.md` — what the impl-orchestrator claims it shipped.
- `.meridian/work/workspace-config-design/design/refactors.md` R06 section — what was supposed to ship.
- `git diff bb72a85..efad4c0 -- src/` — the full R06 diff on main.
- `git log --oneline bb72a85..efad4c0` — the 6 R06 commits.

## Review lanes

### 1. Behavior parity check

For each driving adapter rewired in `b19d999`:
- **Primary launch** (`launch/plan.py`, `launch/process.py`): did anything that worked before stop working? PTY capture, session-ID extraction, fork continuation, Ctrl-C handling, exit code propagation, headless Popen fallback, dry-run preview.
- **Background worker** (`ops/spawn/execute.py`, `ops/spawn/prepare.py`, `launch/streaming_runner.py`): spawn launch, output capture, session-ID recording, workflow around `build_create_payload`.
- **App streaming HTTP** (`app/server.py`): `/spawns` creation flow, `/inject` and `/interrupt` routing, SpawnManager lifecycle, error responses.

For each surface, is the happy path intact? More importantly — is every **edge case** that existed pre-R06 still handled? Look at test changes: 5 tests were removed (`bf4cf6c`). Were those tests covering real behavior that's now unverified?

### 2. `MERIDIAN_HARNESS_COMMAND` bypass (c042478)

The bypass logic moved from branches in `launch/plan.py` and `launch/command.py` into a `BypassLaunchContext` returned by `build_launch_context()`. Before R06, bypass skipped policy resolution AND session resolution. After R06, the design says bypass runs policy + session, then branches.

- Does the shipped code match that? Or does it skip composition entirely?
- What about `inherit_child_env` vs `build_harness_child_env`? Pre-R06 bypass used `inherit_child_env`. Post-R06, where does bypass env come from?
- Any pre-R06 tests that specifically exercised the bypass path — do they still pass with the same assertions?

### 3. Fork continuation (b19d999)

Fork materialization absorbed into `materialize_fork()`. Pre-R06 had two sites doing identical work:
- `launch/process.py:68-105` (primary)
- `ops/spawn/prepare.py:296-311` (worker)

Post-R06, both should call `materialize_fork()`. Verify:
- `fork_session()` runs at the same moment in the launch lifecycle as before.
- Session state (`continue_harness_session_id`, fork flags) is carried through correctly.
- The forked command is built with the new session id, not the old one.
- Error handling: what happens if `fork_session()` raises? Pre-R06 behavior vs. post-R06.

### 4. `observe_session_id()` adapter seam

New adapter method. Claude has an impl (per `c042478`). What about Codex and OpenCode? If they don't have implementations yet, does the default fall-through return `None`? If so, Codex/OpenCode spawns may lose session-ID capture — a silent regression.

Check:
- `src/meridian/lib/harness/claude.py` — impl exists?
- `src/meridian/lib/harness/codex.py` — impl exists?
- `src/meridian/lib/harness/opencode.py` — impl exists?
- Default implementation in `harness/adapter.py` base class — does it raise, return None, or something else?

If Codex/OpenCode observation is broken, that's a blocker.

### 5. Type splits (3f8ad4c)

`SpawnRequest` added. `RuntimeContext` unified. Any code path that previously held a `SpawnParams` and now needs to construct a `SpawnRequest` first? If the type was widened/narrowed, any callers that depended on fields that moved?

Check for:
- Pre-R06 code that expected `SpawnParams.foo` where `foo` is now on `SpawnRequest` or vice versa.
- Runtime errors waiting to happen when a previously-working field access now `None`s or raises.

### 6. Deletions (bf4cf6c)

`run_streaming_spawn` deleted, `SpawnManager.start_spawn` fallback removed, 5 tests removed. For each deletion:
- What covered that code? If tests deleted, was it because the code was genuinely dead, or because the tests would fail with the new shape?
- Any external caller relying on `run_streaming_spawn` directly? Its old caller was `streaming_serve.py` — rewired per design. Any other caller?
- The fallback in `SpawnManager.start_spawn` — who was using it? If the unsafe fallback was load-bearing for any test or script, removing it might regress that path.

## Deliverable

Under 700 words:

- Findings as **Blocker / Major / Minor** with file:line references and concrete regression scenarios.
- For each finding, name the exact pre-R06 behavior that's now broken (or at risk).
- End with a **Verdict**: `no-regressions-found` / `regressions-likely-but-need-runtime-evidence` / `concrete-regression-evidence`.
- Do NOT modify code. Report only.

The smoke-tester is running in parallel and will provide runtime evidence. Your job is static reading to find risks they might miss, and to flag anything behavioral for them to specifically test.
