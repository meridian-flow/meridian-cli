# Launch Composition — Architectural Drift Gate Invariant

> Design-package draft. Implementation copies this content verbatim to
> `.meridian/invariants/launch-composition-invariant.md` and updates both
> in sync as legitimate architecture changes land. Owned by the launch
> subsystem; reviewers run on PRs that touch
> `src/meridian/lib/(launch|harness|ops/spawn|app)/` and
> `src/meridian/cli/streaming_serve.py`.

You are reviewing a code diff against the meridian launch subsystem. Your
job is to detect architectural drift from the declared invariants below.
You return one verdict (`pass` or `fail`) plus a list of file:line
violations with a one-sentence explanation each.

The invariants are semantic, not syntactic. Renamed wrappers, indirect
calls, dynamic imports, and shim functions that satisfy the invariants in
appearance but violate them in behavior are violations. When in doubt,
err on the side of `fail` and let the human PR author justify the change.

## Protected files

Composition rules apply to:

- **Domain core (sole composition surface):**
  `src/meridian/lib/launch/context.py`, `launch/policies.py`,
  `launch/permissions.py`, `launch/prompt.py`, `launch/run_inputs.py`,
  `launch/fork.py`, `launch/command.py`, `launch/env.py`.
- **Driving adapters (must not compose):**
  `src/meridian/lib/launch/plan.py`, `launch/process.py`,
  `lib/ops/spawn/prepare.py`, `lib/ops/spawn/execute.py`,
  `lib/app/server.py`, `src/meridian/cli/streaming_serve.py`.
- **Driven port (contracts only):** `src/meridian/lib/harness/adapter.py`.
- **Driven adapters (mechanism, not composition):**
  `src/meridian/lib/harness/claude.py`, `harness/codex.py`,
  `harness/opencode.py`.
- **Executors:** `src/meridian/lib/launch/process.py` (primary
  capture-mode branch), `lib/launch/streaming_runner.py` (async
  subprocess).

## Invariants

### I-1 Composition centralization

Composition lives only inside `build_launch_context()` (in
`launch/context.py`) and the named pipeline stages it calls. The named
stages are: `_build_bypass_context`, `resolve_policies`,
`resolve_permission_pipeline`, `compose_prompt`,
`build_resolved_run_inputs`, `materialize_fork`,
`resolve_launch_spec_stage`, `apply_workspace_projection`,
`build_launch_argv`, `build_env_plan`.

A driving adapter that performs any composition itself — including
constructing a `ResolvedLaunchSpec`, an argv tuple from harness flags, a
permission resolver, or a child env mapping — violates I-1.

### I-2 Driving-adapter prohibition list

A file in the driving-adapter list MUST NOT contain any of the following
calls (direct or via local rename / dynamic import):

- `resolve_policies(...)`
- `resolve_permission_pipeline(...)`
- `TieredPermissionResolver(...)`
- `UnsafeNoOpPermissionResolver(...)`
- `adapter.resolve_launch_spec(...)`
- `adapter.project_workspace(...)`
- `adapter.build_command(...)`
- `adapter.fork_session(...)`
- `adapter.seed_session(...)`
- `adapter.filter_launch_content(...)`
- `build_harness_child_env(...)`
- `extract_latest_session_id(...)` (function deleted)
- direct construction of a `PermissionConfig`, `ResolvedLaunchSpec`, or
  `ResolvedRunInputs`

If a driving adapter needs any of the above, it constructs a
`SpawnRequest` and calls `build_launch_context()`. Period.

### I-3 Single owners

| Concern | Sole owner |
|---|---|
| Bypass dispatch | `launch/context.py:_build_bypass_context()` |
| `MERIDIAN_HARNESS_COMMAND` parsing | `launch/context.py:_build_bypass_context()` |
| Fork materialization | `launch/fork.py:materialize_fork()` |
| Adapter `resolve_launch_spec` callsite | `launch/command.py:resolve_launch_spec_stage()` |
| Adapter `project_workspace` callsite | `launch/command.py:apply_workspace_projection()` |
| Adapter `build_command` callsite | `launch/command.py:build_launch_argv()` |
| Adapter `fork_session` callsite | `launch/fork.py:materialize_fork()` |
| `TieredPermissionResolver`/`UnsafeNoOpPermissionResolver` construction | `launch/permissions.py:resolve_permission_pipeline()` |
| Session-ID observation | per-adapter `observe_session_id()`; called once by driving adapter post-execution |
| `RuntimeContext` type definition | `core/context.py` (no duplicate in `launch/context.py`) |
| Child cwd creation (`mkdir`) | inside the factory, after spawn row exists |

A new callsite that violates the table is a violation. A "thin wrapper"
that delegates back to the sole owner is a wrapper, not a callsite — fine.
A wrapper that re-implements the underlying logic (rather than delegating)
is a violation.

### I-4 Observation path

`observe_session_id()` is called by exactly one path: the driving adapter
after the executor returns `LaunchOutcome`. The driving adapter then
assembles `LaunchResult` with the returned session_id.

Adapter implementations may inspect `launch_outcome.captured_stdout`
(legitimate parser source) or per-launch state reachable via
`launch_context` (e.g., `connection.session_id` for HTTP/WS adapters).
They MUST NOT read or write adapter-instance singleton state shared across
launches. Any field on the adapter class that holds a session id, a chat
id, or last-launch state is a violation.

### I-5 DTO discipline

The following are violations:

- Reintroducing `PreparedSpawnPlan`, `ExecutionPolicy`, top-level
  `SessionContinuation`, `ResolvedPrimaryLaunchPlan`, or any new
  pre-composed DTO whose factory consumes already-resolved permission /
  spec / argv state.
- Adding `arbitrary_types_allowed = True` to any model in
  `launch/`, `harness/`, `ops/spawn/`, or `app/` (the
  persisted-artifact contract requires JSON round-trip without escape
  hatches).
- Storing `Path` (rather than `str`) on `SpawnRequest` or any nested
  model that participates in `model_dump_json` round-trip.
- Introducing a sidechannel for composition warnings other than
  `LaunchContext.warnings`.
- A `NormalLaunchContext` field with a `None` default that is load-bearing
  for executor behavior (post-composition context must be complete at
  construction).

### I-6 Stage modules own real logic

Each pipeline-stage module owns at least one real definition consumed by
the factory. The following modules MUST NOT be re-export shells:

- `launch/policies.py`
- `launch/permissions.py`
- `launch/fork.py`
- `launch/env.py`
- `launch/command.py`
- `launch/run_inputs.py`
- `launch/prompt.py`

A module whose only top-level statements are `from ... import` re-exports
is a violation — the stage is a phantom.

### I-7 Driven port keeps shape only

`src/meridian/lib/harness/adapter.py` declares contracts (Protocols,
abstract base classes, frozen DTOs) only. It MUST NOT contain:

- Concrete permission-flag projection logic.
- Concrete env construction.
- Concrete session-ID observation.
- Concrete command-argv assembly.

Mechanism for any harness lives in the adapter that implements that
harness (`harness/claude.py`, `harness/codex.py`, `harness/opencode.py`).

### I-8 Executors stay mechanism-only

The two executors (`launch/process.py` primary, `launch/streaming_runner.py`
async subprocess) accept `LaunchContext`, run a process, and return
`LaunchOutcome`. They MUST NOT:

- Construct argv, env, perms, or any composition output.
- Call adapter methods other than transport primitives.
- Inspect harness identity to choose composition behavior (sum-type
  dispatch on `LaunchContext` variants is fine).

### I-9 Workspace projection seam is reachable

`apply_workspace_projection` runs between `resolve_launch_spec_stage` and
`build_launch_argv` inside the factory. The diff MUST NOT:

- Bypass `apply_workspace_projection` for any harness.
- Move `adapter.project_workspace` calls outside the factory.
- Mutate argv after `build_launch_argv` returns to inject workspace roots.

### I-10 Fork-after-row ordering

The diff MUST preserve the invariant that `fork_session` is invoked only
after a spawn row exists for the current launch. Any new code path that
reaches `materialize_fork()` without first calling `start_spawn` (or
equivalent) is a violation.

In particular, the streaming-runner fallback path (`execute_with_streaming`)
MUST raise a precondition error rather than create a row mid-flight when
no row exists.

The `start` event for the forked child's spawn row MUST NOT pre-populate
`harness_session_id`. That field is written later by `update`, identical
to non-fork starts. Fork paths have no special access to the session-id
field on `start`; smuggling the child's future session id into the start
row is a violation. (Added after R06-v1 smoke revealed fork start rows
were being populated out-of-order versus non-fork start rows.)

### I-11 Fork lineage coherence

Every fork MUST produce exactly one new chat row in `sessions.jsonl`
AND one `start` event in `spawns.jsonl`, written such that no persisted
read ever observes one without the other. The new `spawns.jsonl` row's
`chat_id` MUST reference the new `sessions.jsonl` chat row (not the
parent's chat). `spawn children <parent>` MUST return the forked child.
`forked_from_chat_id` on the new sessions row MUST name the parent's
chat id.

Failure mode this invariant closes: fork paths that keep the parent's
`chat_id` on the child's spawns.jsonl row while `sessions.jsonl` creates
a new chat — producing orphaned `spawn children` results, poisoned
`--fork <session_id>` follow-ons, and reports that disagree with the
persisted spawn row. Observed empirically in R06-v1 smoke lane 4; a
violation the original 10 invariants did not name.

### I-12 Report content type

The `report.md` file written for any spawn MUST contain the agent's
final user-facing assistant message as plain text, across every harness
family. It MUST NOT contain raw transport event envelopes (for example
`{"event_type":"session.idle","harness_id":"opencode","payload":{...}}`),
protocol framing, transport-state objects, or any JSON blob that was
never intended as user-visible content.

Driven-port methods that produce report content (`extract_report_content()`
or equivalent per-adapter) are typed and documented to return user-facing
message text only. "The returned string happens to contain a stringified
envelope" is not compliant. Driven-port typing SHOULD expose content
contracts beyond Python shape — a `-> str` return type that documents
"user-facing assistant message text, no transport envelopes" is the bar,
not just `-> str`.

Failure mode this invariant closes: OpenCode report extraction returning
raw `session.idle` event envelopes instead of the agent's message,
observed in R06-v1 smoke lane 2. Likely fallout from the streaming
runner consolidation where a content-extraction seam was collapsed
without preserving its semantic contract.

### I-13 Adapter transforms are observable

Driven adapters MUST NOT silently lossy-transform caller inputs. Any
transformation either preserves semantics (idempotent) or surfaces via a
`CompositionWarning` on the `LaunchContext.warnings` channel. "Accepted
with modification" is not a valid adapter behavior.

Scope note: this invariant is cross-cutting and slightly wider than the
original R06 composition scope. It is included here because the class of
bug it prevents — silent input mutation at adapter boundaries — is what
corrupted the R06-v1 implementation cycle itself (codex silently
truncating coder briefs at 50 KiB). The factory-side output channel for
warnings (`LaunchContext.warnings`) is the enforcement mechanism R06
already provides, so adding I-13 costs no new machinery.

## What does NOT count as a violation

- Renaming a stage function while preserving its single-callsite
  invariant.
- Adding a new stage to the pipeline, provided it is named in the factory
  and has a sole owner module.
- Adding fields to `SpawnRequest`, `LaunchContext`, `LaunchRuntime`, or
  `ResolvedRunInputs` provided their type discipline (frozen, JSON-safe,
  scope) is preserved.
- Replacing one harness's mechanism inside its own adapter file.

## Output format

Return a JSON object:

```json
{
  "verdict": "pass" | "fail",
  "violations": [
    {
      "invariant": "I-2",
      "file": "src/meridian/lib/app/server.py",
      "line": 332,
      "explanation": "App-streaming driver still constructs TieredPermissionResolver directly; should call build_launch_context() with runtime.unsafe_no_permissions instead."
    }
  ],
  "notes": "(optional, for ambiguous cases worth flagging without failing)"
}
```

If `verdict` is `pass`, `violations` is an empty list. The CI step blocks
merge on `fail`.
