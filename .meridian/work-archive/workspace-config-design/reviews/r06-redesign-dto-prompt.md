# R06 Redesign — DTO-Shape Convergence Review

You are reviewing one specific decision in the redesigned R06 package: the
**DTO reshape**. This is the load-bearing call. Get it wrong and the
redesign is back to where the prior R06 ended up — a hexagonal shell whose
factory boundary forces composition into drivers.

## The decision under review

The redesign collapses six partial-truth DTOs into five named types, each
with a one-sentence purpose, and changes the factory boundary from
"pre-resolved `PreparedSpawnPlan`" to "raw `SpawnRequest`".

Three user-visible types after R06:

- **`SpawnRequest`** — currently dead at `harness/adapter.py:150-163`,
  becomes load-bearing. Frozen pydantic model, fully serializable, no
  `arbitrary_types_allowed`. Carries only what a caller can express:
  prompt, model ref, harness id, agent ref, skills refs, extra_args,
  mcp_tools, sandbox, approval, allowed_tools, disallowed_tools,
  autocompact, retry policy, session intent (continue_chat_id,
  requested_harness_session_id, continue_fork, source_execution_cwd,
  forked_from_chat_id), reference_files, template_vars, work_id_hint,
  agent_metadata. Constructed by every driving adapter and only by them.
- **`LaunchContext = NormalLaunchContext | BypassLaunchContext`** — sum
  type, frozen, all-required, executor input.
- **`LaunchResult`** — exit_code, child_pid, session_id (populated by
  `observe_session_id()`).

Two factory-internal types:

- **`ResolvedRunInputs`** — renamed from `SpawnParams`. Constructed only
  inside `build_launch_context()` by `build_resolved_run_inputs()`.
  Driving adapters never see it.
- **`LaunchOutcome`** — executor → driving-adapter handoff. Raw exit_code,
  child_pid, optional captured PTY stdout.

Deleted: `PreparedSpawnPlan`, `ExecutionPolicy`, top-level
`SessionContinuation`, `ResolvedPrimaryLaunchPlan`, user-facing
`SpawnParams`.

## What to read

1. `decisions.md` D17 (prior R06 decision) and D19 (this redesign).
2. `design/refactors.md` R06 section "DTO reshape (load-bearing)" — the
   primary content under review.
3. `design/architecture/launch-core.md` — A06, "Type ladder" section.
4. `design/feasibility.md` FV-11 — feasibility verdict for the raw
   `SpawnRequest` boundary.
5. `reviews/r06-retry-structural.md` §4 "Deep issues regardless of shape"
   — the type-ladder critique that drove the redesign.
6. **Source files (live code):**
   - `src/meridian/lib/harness/adapter.py:130-329` — current
     `SpawnRequest`, `SpawnParams`, `HarnessAdapter` protocol.
   - `src/meridian/lib/ops/spawn/plan.py` — current `PreparedSpawnPlan`
     and `ExecutionPolicy`.
   - `src/meridian/lib/launch/context.py:31-213` — current factory body.
   - `src/meridian/lib/ops/spawn/prepare.py:202-397` — current persisted
     plan construction.
   - `src/meridian/lib/ops/spawn/execute.py:397-865` — current persisted
     plan consumption.

## Focus areas

### 1. Field completeness

Walk every field that a driver computes today and reaches the factory
through `PreparedSpawnPlan`. For each, verify it is either:

- explicitly present on the new `SpawnRequest` schema (in `refactors.md`
  R06 "DTO reshape" or `launch-core.md` "Type ladder"), or
- explicitly derivable inside the factory from `SpawnRequest` fields, or
- explicitly out of scope and named in `decisions.md`.

Findings: any field that today's drivers carry but neither the new
`SpawnRequest` nor a factory pipeline stage owns. Especially watch:

- profile name resolution from `--agent` (drivers compute incidentally
  today — does `SpawnRequest` carry the agent ref or the resolved profile
  name?).
- skills-resolved-to-paths vs raw skills refs.
- continuation ids (continue_chat_id, requested_harness_session_id,
  forked_from_chat_id) — does the `SessionRequest` nested model have all
  of them?
- retry policy fields (`RetryPolicy`).
- agent_metadata, work_id_hint, template_vars, reference_files.
- harness-specific spec fields surfaced today through `ResolvedLaunchSpec`
  (does the factory recompute them from `SpawnRequest`, or are they
  unrecoverable?).

### 2. Round-trip fidelity

Per FV-11, `SpawnRequest` must round-trip through `model_dump_json` /
`model_validate_json` without `arbitrary_types_allowed`. Check:

- All fields are primitive or pydantic-friendly types.
- No `PermissionResolver`, no `HarnessAdapter`, no `Path` that pydantic
  can't serialize.
- Nested models (`RetryPolicy`, `SessionRequest`) are themselves frozen
  and primitive.

If any field today's persisted plan carries cannot be serialized as
plain JSON, flag it. The persisted artifact is a JSON blob the operator
can `cat`.

### 3. Construction-site enumeration

The structural review enumerated 5 places `PreparedSpawnPlan` is built
today (`launch/plan.py:178-213`, `ops/spawn/prepare.py:356-397`,
`app/server.py:332-350`, `cli/streaming_serve.py:69-87`,
`ops/spawn/execute.py:397-425`). Each becomes a single
`SpawnRequest(...)` call followed by `build_launch_context()`.

For each construction site, walk what the current code computes locally
that the new factory must reconstruct. Findings: any site where the
current driver computes a value the factory cannot reconstruct from raw
fields.

### 4. Factory-internal type discipline

`ResolvedRunInputs` and `LaunchOutcome` are factory-internal. Verify:

- No driving adapter constructs `ResolvedRunInputs` directly.
- No driving adapter consumes `ResolvedRunInputs` fields directly (it
  only consumes `LaunchContext`).
- `LaunchOutcome` flows from executor → driving adapter only; the driving
  adapter then assembles `LaunchResult` via `observe_session_id()`. No
  driver should inspect `LaunchOutcome.captured_stdout` directly to
  scrape session ids — that's the adapter's job.

### 5. Comparative honesty: the rejected DTO splits

The structural review's top-pick alternative was `LaunchInputs`/`LaunchAttempt`
(pre-composition vs post-composition input types). The redesign instead
makes `SpawnRequest` the pre-composition input and reuses `LaunchContext`
as the post-composition type. Evaluate whether this is a better fit than
the structural review's proposal:

- `SpawnRequest` already exists on the protocol — making it load-bearing
  closes a dead-abstraction signal.
- The structural review proposed `LaunchInputs` carrying `RuntimeBindings`
  + `SessionSpec` + `PermissionSpec` — does the redesign lose anything by
  not having these as separate types?
- Is `LaunchContext` honestly the post-composition type, or does it carry
  pre-composition fields that should have been resolved away?

### 6. Out-of-scope hygiene

The redesign explicitly defers:
- Background-worker `disallowed_tools` correctness fix (separate commit
  with own test — but `SpawnRequest.disallowed_tools` makes it fixable).
- Issue #34 (Popen-fallback session-ID via filesystem polling).
- Issue #32 (dead legacy subprocess-runner code).

Verify each is logged in `decisions.md` D19 or `refactors.md` R06
out-of-scope section.

## Output format

Write `reviews/r06-redesign-dto-shape.md` with sections:

```
# R06 Redesign — DTO-Shape Convergence Review

## Verdict
{pass | shape-change-needed | block}

## DTO completeness findings
(missing fields, lost data on persistence, unrecoverable values)

## Round-trip-fidelity findings
(serializability concerns)

## Construction-site findings
(per the 5 enumerated sites)

## Factory-internal-type-discipline findings

## Comparative honesty
(brief — does the SpawnRequest boundary work better than the structural
review's `LaunchInputs`/`LaunchAttempt` alternative? If not, name what's
missing.)

## Severity count
- blocker: N
- major: N
- minor: N
```

## Constraints

- This is a **DTO-focused** review — leave general structural concerns
  (wider than DTOs) to the design-alignment reviewer running in parallel.
- Stay at design altitude. Do not propose specific Python types; propose
  what the DTO must carry and why.
- Do not re-derive the prior R06 review findings; assume them as
  background and verify the redesign closes the DTO-relevant ones.
- Read-only: write only to `reviews/r06-redesign-dto-shape.md`.
