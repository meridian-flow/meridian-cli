# R06 Retry Design-Alignment Review

## 1. Intent vs current state

Verdict here: skeleton realizes hexagonal shape at executor seam, not at composition seam.

- `build_launch_context()` is real central point for preflight, runtime env merge, bypass branch, fork materialization, spec resolution, env build. See `src/meridian/lib/launch/context.py:89-213`.
- But driving adapters still do policy composition before factory call:
  - primary: `resolve_policies()` + `resolve_permission_pipeline()` in `src/meridian/lib/launch/plan.py:234-334`
  - worker: same in `src/meridian/lib/ops/spawn/prepare.py:202-328`
  - app: builds `PermissionConfig` + `TieredPermissionResolver` + `PreparedSpawnPlan` in `src/meridian/lib/app/server.py:286-351`
- Factory signature already shows boundary too late: it takes `run_prompt`, `run_model`, resolved `harness`, and `PreparedSpawnPlan` with baked `execution.permission_*`. `src/meridian/lib/launch/context.py:89-104`
- So current shape is: driving adapters still own policy resolution; factory owns launch assembly after policy resolution. Looks hexagonal. Not yet full intent from R06/D17.

`LaunchContext` sum type:

- Good local abstraction for executor dispatch. It cleanly separates native-harness path from `MERIDIAN_HARNESS_COMMAND` bypass. See `src/meridian/lib/launch/context.py:31-71`, `src/meridian/lib/launch/process.py:344-373`, `src/meridian/lib/launch/streaming_runner.py:649-657`.
- Not the abstraction that proves centralization. It helps executors. It does not solve that drivers still pre-compose policy, prompt, permission, continuation.
- So: right seam, wrong proof. Keep it as executor input. Do not use it as evidence that R06 is structurally complete.

## 2. The DTO barrier — confirm or refute

Confirmed.

Hard blocker:

- `PreparedSpawnPlan.ExecutionPolicy` carries resolved `PermissionConfig` and live `PermissionResolver`. `src/meridian/lib/ops/spawn/plan.py:9-21`
- `PreparedSpawnPlan` exposes that resolved execution bundle to every caller. `src/meridian/lib/ops/spawn/plan.py:39-66`
- Factory consumes those resolved outputs directly. `src/meridian/lib/launch/context.py:195-203`
- Therefore each driver must resolve permission policy before it can even construct factory input. That is exactly why real centralization cannot happen by moving calls only.

Nuance: barrier is bigger than `ExecutionPolicy`.

- Primary also pre-resolves prompt policy, skills injection, session seeding, and preview command before plan build. `src/meridian/lib/launch/plan.py:312-410`
- Worker does same, plus direct fork materialization before `PreparedSpawnPlan` exists. `src/meridian/lib/ops/spawn/prepare.py:278-312`, `:334-397`
- App path hand-rolls a minimal prepared plan because factory cannot accept raw safety inputs. `src/meridian/lib/app/server.py:286-351`

Minimum reshape recommendation: **(ii) split into `UnresolvedPreparedPlan` and `ResolvedPreparedPlan`**.

Why this one:

- Minimal blast radius. Worker/background flow still needs a durable pre-exec artifact on disk.
- Keeps timeout/retry/backoff/warning/reference metadata stable outside factory.
- Moves policy/safety/session-resolution boundary to the right place without forcing total deletion of plan persistence.

Recommended split:

- `UnresolvedPreparedPlan`
  - visible to drivers and persisted for background worker
  - holds `SpawnRequest`, raw continuation intent, raw safety inputs (`sandbox`, `approval`, allowed/disallowed tools), timeout/retry policy, warning/context metadata
- `ResolvedPreparedPlan`
  - factory-internal or returned alongside `LaunchContext`
  - holds resolved profile, resolved skills, prompt-policy result, `SpawnParams`, resolved permission pipeline, spec/env, materialized fork session id

Why not `(i)`:

- Too narrow for current worker handoff. You still need durable non-policy execution metadata outside factory.

Why not `(iii)`:

- Bigger migration for little gain. Background worker persistence and dry-run preview paths still want a stable pre-exec DTO.

Practical note:

- `ExecutionPolicy` should likely split too:
  - `RetryPolicy` stays pre-factory
  - `LaunchSafetyInputs` stay raw pre-factory
  - resolved permission resolver exists only post-factory

## 3. Is hexagonal even right?

Yes. Mostly.

Why hexagonal fits this domain:

- Three real driving adapters with incompatible lifecycle/mechanism constraints: primary foreground, background worker, app streaming. Design intent matches code reality. `src/meridian/lib/launch/process.py`, `src/meridian/lib/ops/spawn/execute.py`, `src/meridian/lib/app/server.py`
- Harness translation already has a strong driven-adapter boundary: `resolve_launch_spec()`, `build_command()`, `fork_session()`, `observe_session_id()`. `src/meridian/lib/harness/adapter.py:257-337`
- Domain problem is orchestration of policy resolution -> prompt shaping -> fork/session handling -> spec/env assembly. That is exactly a coordination core with adapter edges.

What is forced:

- One factory input DTO trying to be both user intent and resolved execution state.
- Claiming "hexagonal done" while policy still lives in drivers.

Better frame:

- Keep hexagonal shell.
- Inside shell, use typed pipeline/stages, not one overloaded plan blob.
- Domain core should accept unresolved intent and return resolved launch context.

Alternative shapes worth naming:

- Plain function pipeline with typed stage inputs/outputs. Viable. But that is basically the inner shape of the same hexagonal design.
- Builder pattern. Worse fit. Hides ordering/state transitions in mutating object.
- Command pattern / effect system. Overkill here. More framework than problem.

So: cycle exposed wrong boundary placement, not wrong top-level pattern.

## 4. Verdict

**proceed-with-dto-reshape**

Recommended reshape: **(ii) keep the plan object but split pre-factory and post-factory DTOs**.

Hexagonal intent still coherent. Still shippable. Current blocker is boundary timing, not pattern mismatch.

## 5. Risks

1. Fork side effects still sit on the dangerous edge of composition.
`materialize_fork()` writes external Codex session state before execution. If ownership/session ordering stays wrong, refactor can preserve orphan-fork failure windows under a cleaner DTO name. See `src/meridian/lib/launch/fork.py:7-34`.

2. Migration can leave two composition paths alive.
If old `PreparedSpawnPlan` and new unresolved/resolved shapes coexist for even one phase, drivers can keep resolving policy "temporarily" and CI `rg` guards will still pass. Need behavioral tests on factory inputs, not count guards only.

3. Session-id seam still not actually wired end-to-end.
Protocol has `observe_session_id()`, but primary/streaming executors still use `extract_latest_session_id()` and artifact/detection paths. `src/meridian/lib/launch/process.py:451-476`, `src/meridian/lib/launch/streaming_runner.py:859-883`. DTO reshape alone will not fix that drift.

Report path: `/home/jimyao/gitrepos/meridian-cli/.meridian/work/workspace-config-design/reviews/r06-retry-design-alignment.md`
Verdict: `proceed-with-dto-reshape`
