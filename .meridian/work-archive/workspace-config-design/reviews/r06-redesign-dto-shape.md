# R06 Redesign — DTO-Shape Convergence Review

> Source: opus reviewer report `p1938`. Drafted by the reviewer; materialized
> here by design-orch because the spawn lacked write permission to this path.

## Verdict

`shape-change-needed`

The redesign's core call — factory boundary at raw `SpawnRequest`, six
partial-truth DTOs collapsed to five named types,
`arbitrary_types_allowed=True` removed from the persisted artifact — is right.
FV-11's reasoning holds. But the DTO schema enumerated in `refactors.md` R06
"DTO reshape" and `launch-core.md` Type ladder is incomplete against what
today's `PreparedSpawnPlan` carries. One blocker and six major findings
require explicit schema decisions before R06 is shippable.

## DTO completeness findings

**Finding 1 — `interactive: bool` has no slot [major].** `SpawnParams.interactive`
(`adapter.py:165-185`) discriminates primary-launch from background/app-streaming
and is consumed by every driven adapter (`claude.py:285,308`, `codex.py:343,349`,
`opencode.py:226,234`). Not factory-derivable from
`SpawnRequest.{prompt,model,harness,agent,skills,...}`. Fix: add `launch_mode:
Literal["primary","background"]` to `SpawnRequest` or declare it on
`LaunchRuntime`.

**Finding 2 — `effort: str | None` has no slot [major].**
`PreparedSpawnPlan.effort` (`plan.py:46`) carries reasoning-effort projection
(Codex `-c model_reasoning_effort=...`). Undeclared on `SpawnRequest` and not
named as factory-derived. Fix: place on `SpawnRequest` (if overridable) or on
`ResolvedRunInputs` with a derivation rule.

**Finding 3 — Three `SessionContinuation` fields silently dropped [major].**
Today's `SessionContinuation` (`plan.py:24-36`) has eight fields; redesigned
`SessionRequest` lists five. Missing: `continue_harness`,
`continue_source_tracked`, `continue_source_ref`. Fix: list them on
`SessionRequest` or add a decision entry naming each deletion and the
behavior loss.

**Finding 4 — No DTO slot for composition-phase warnings [blocker].**
`PreparedSpawnPlan.warning` (`plan.py:64`) flows to `SpawnActionOutput.warning`
today. `LaunchContext` (both variants) has no warnings field; `SpawnRequest`
is user-input; `ResolvedRunInputs` is factory-internal. Fix: add `warnings:
tuple[str, ...]` (or structured `CompositionWarning`) to `LaunchContext`
populated by pipeline stages.

**Finding 5 — `context_from_resolved` channel is neither raw nor resolved
[major].** `PreparedSpawnPlan.context_from_resolved` (`plan.py:54`) is
pre-resolved by drivers today. Redesign doesn't place it. Fix: mirror the
skills pattern — raw `context_from` on `SpawnRequest`, resolved counterpart
on `ResolvedRunInputs`.

**Finding 6 — `UnsafeNoOpPermissionResolver` has no seam through
`SpawnRequest` [major].** App-streaming driver constructs
`UnsafeNoOpPermissionResolver` at `app/server.py:~300` under
`--allow-unsafe-no-permissions`. Driving-adapter prohibition list forbids
driver-side `TieredPermissionResolver(...)`; no declared seam for the unsafe
override. Fix: declare override flag on `LaunchRuntime` (or `SpawnRequest`)
and describe `resolve_permission_pipeline` dispatch.

**Finding 7 — Worker prepare→execute re-resolution semantics undeclared
[major].** Redesign eliminates persisted `cli_command` preview and
re-composes on execute. Behavior-correct simplification but undeclared. Fix:
add decision entry (or extend D19) stating that worker execute re-reads
current filesystem state; document `spawn show --plan` implications.

**Finding 8 — `RetryPolicy` field scope undeclared [minor].** Does
`RetryPolicy` include `timeout_secs`/`kill_grace_secs`? If yes, name is
misleading; if no, where do timeouts live on `SpawnRequest`? Fix: enumerate
`RetryPolicy` fields; add `ExecutionBudget` nested model if needed.

**Finding 9 — `agent_metadata` typing undeclared [minor].** Fix: declare
`dict[str, str]` (matches `template_vars`) or nested model.

**Finding 10 — `debug: bool` routing undeclared [minor].**
`BackgroundWorkerParams.debug` not placed. Fix: declare on `LaunchRuntime`.

## Round-trip-fidelity findings

**R1 — Nested types (`RetryPolicy`, `SessionRequest`) must be explicitly
frozen pydantic models.** One-liner addition to Type ladder required.

**R2 — `template_vars` and `agent_metadata` dict types must be declared
JSON-safe.** Specify `dict[str, str]`.

**R3 — Path fields must remain `str`, not `Path`.** Preserves existing
round-trip without custom encoders; state in refactors.md.

## Construction-site findings

- **CS-1 `launch/plan.py:178-213` [ok with caveat]** — `adapter.seed_session()`
  and `adapter.filter_launch_content()` are not in launch-core.md single-owner
  table; must be named.
- **CS-2 `ops/spawn/prepare.py:356-397` [ok]** — covered; only Finding 4
  remains unplaced.
- **CS-3 `app/server.py:332-350` [blocked on Finding 6]** — cannot collapse
  to `SpawnRequest(...)` + factory call until unsafe-resolver seam is
  declared.
- **CS-4 `cli/streaming_serve.py:69-87` [ok with note]** — state explicitly
  that this driver disappears entirely under R06 rather than constructing a
  DTO.
- **CS-5 `ops/spawn/execute.py:397-425` [hinges on Findings 7+10]** —
  re-resolution semantics + `debug` routing must be declared.

## Factory-internal-type-discipline findings

- **FI-1 — `ResolvedRunInputs` scoping [ok].** Add to prohibition list:
  drivers MUST NOT construct or consume.
- **FI-2 — Prohibit driver reads of `LaunchOutcome.captured_stdout`
  [minor].** Session-ID observation routed exclusively through
  `adapter.observe_session_id`.
- **FI-3 — Explicit "no pre-composition fields in NormalLaunchContext"
  statement [minor].** Lock post-composition invariant in launch-core.md.
- **FI-4 — `NormalLaunchContext.run_inputs: ResolvedRunInputs` exposure
  [minor].** Declare the readable-but-not-reconstructable contract.
- **FI-5 — Bypass extension guidance [minor].** Document that future
  shared-diagnostic fields go on a shared base, not `NormalLaunchContext`.

## Comparative honesty

The structural review's `LaunchInputs`/`LaunchAttempt` alternative is cleaner
in the abstract (flatter post-composition type, per-stage monomorphic
testability, no legacy baggage), but the redesign's `SpawnRequest` boundary
wins on two decisive grounds: (1) it closes the dead-abstraction signal on
the existing protocol at zero type-ladder cost, and (2) it lets
`model_dump_json`/`model_validate_json` be the single persistence mechanism
for the worker prepare→execute artifact. The structural review's
`RuntimeBindings`/`SessionSpec`/`PermissionSpec` decomposition reappears as
nested models inside `SpawnRequest` and factory-internal pipeline stage
outputs — the naming differs; the decomposition is the same. The legitimate
concern from the structural review — "post-composition type should be flat,
not a bundle" — is partially addressed by FI-3/FI-4: make the `run_inputs`
indirection an intentional, documented choice.

## Out-of-scope hygiene

- Background-worker `disallowed_tools` correctness fix — logged in
  refactors.md R06 "Red flag". ✓
- Issue #34 (Popen-fallback session-ID) — logged in refactors.md R06
  "Out of scope" and launch-core.md "Resolved Behaviors". ✓
- Issue #32 (dead legacy subprocess-runner) — logged in launch-core.md
  "What This Leaf Does Not Cover" and feasibility.md open question 7. ✓

## Severity count

- blocker: 1 (Finding 4)
- major: 6 (Findings 1, 2, 3, 5, 6, 7)
- minor: 8 (Findings 8, 9, 10, R1, R2, R3, FI-2, FI-3, FI-4, FI-5)
