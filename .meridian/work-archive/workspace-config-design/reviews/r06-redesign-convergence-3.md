# R06 Redesign — Convergence-3 Confirmation Review

## Per-D20 verdicts

### D20.1 — stage split (`resolve_launch_spec_stage` → `apply_workspace_projection` → `build_launch_argv`)

**closed-cleanly.**

- 3 stages named with sole-callsite invariants: `refactors.md:398-410`, `launch-core.md:218-230` (pipeline stages table), `launch-core.md:444-446` (single-owner table).
- A04 seam reachable inside A06 ordering: `harness-integration.md:224-234` ("apply_workspace_projection sitting between resolve_launch_spec_stage and build_launch_argv") matches A06 pipeline order at `launch-core.md:95-98`.
- A04 seam explicitly required by invariant prompt I-9 (`launch-composition-invariant.md:174-180`) — forbids bypass, out-of-factory calls, and post-argv mutation.
- Single-caller enforceable: each stage's callsite is unique (factory only) and the invariant prompt's I-3 table pins it (`launch-composition-invariant.md:86-88`). Drift gate + `test_workspace_projection_seam_reachable` pin the behavior.

### D20.2 — `LaunchRuntime` as 4th user-visible DTO

**closed-with-caveats.**

- Honest home for runtime-injected fields exists: `launch-core.md:155-173` lists `launch_mode`, `unsafe_no_permissions`, `debug`, `harness_command_override`, `report_output_path`, `state_paths`, `project_paths`. Same field list in `refactors.md:301-324`.
- `unsafe_no_permissions` dispatch through `resolve_permission_pipeline` is specified, not hand-waved: `refactors.md:454` + `launch-core.md:450-451` single-owner row, and pipeline stage row `launch-core.md:222` names this as the sole `TieredPermissionResolver` / `UnsafeNoOpPermissionResolver` constructor. Behavioral test `test_unsafe_no_permissions_dispatches_through_factory` (`refactors.md:600-604`) pins it.
- Caveat (minor): `LaunchRuntime` typing diverges across artifacts — `refactors.md:302` says "frozen `@dataclass`", `launch-core.md:155` says "Frozen pydantic model". Both are permitted by the global shape constraint at `launch-core.md:498-501`, but the primary description contradicts itself between the two leaves. Implementer needs to pick one deterministically (pydantic is preferable since everything else on the factory boundary is pydantic).

### D20.3 — `LaunchContext.warnings` channel

**closed-cleanly.**

- `CompositionWarning` specified: frozen pydantic model, `code: str`, `message: str`, optional `detail: dict[str, str]` — `launch-core.md:190-194` and `refactors.md:335-337`.
- Both `NormalLaunchContext.warnings` and `BypassLaunchContext.warnings` carry `tuple[CompositionWarning, ...]` — `launch-core.md:181,183` and `refactors.md:330-334`.
- Single sidechannel enforced: single-owner table row "Composition warnings sidechannel | `LaunchContext.warnings` (no other path)" (`launch-core.md:458`); shape constraint "No other path is permitted" (`launch-core.md:512-513`); invariant I-5 forbids alternative sidechannels (`launch-composition-invariant.md:127-128`).
- Driver surfacing contract named: driving adapter forwards warnings to `SpawnActionOutput.warning` (`launch-core.md:338-339`, 264-265). Behavioral test `test_composition_warnings_propagate_to_launch_context` pins end-to-end (`refactors.md:588-593`).
- Minor prose inconsistency: `refactors.md:336` uses "optional `detail: dict[str, str]`" while `launch-core.md:192` writes `detail: dict[str, str] | None`. Same semantics.

### D20.4 — invariant prompt drafted

**closed-cleanly.**

- All 10 invariants present in `launch-composition-invariant.md` — I-1 centralization (42-50), I-2 prohibition list (56-77), I-3 single-owner table (80-98), I-4 observation path (100-111), I-5 DTO discipline (113-131), I-6 stage modules own real logic (133-147), I-7 driven port shape only (149-160), I-8 executors mechanism-only (162-172), I-9 workspace seam reachable (174-180), I-10 fork-after-row (182-191).
- Protected file list enumerated (20-38) — domain core, driving adapters, driven port, driven adapters, executors each listed by path.
- "What does NOT count as a violation" carve-out present (193-202) — names renaming, adding new stages, adding fields under discipline, replacing harness mechanism inside its own adapter.
- Structured JSON output format present (206-221) — `verdict` enum, `violations[]` with `invariant`/`file`/`line`/`explanation`, optional `notes`, explicit merge-blocking contract.
- Prompt is concrete enough: explicit listed callsites (I-2), explicit callsite→owner mapping (I-3), explicit adapter-side forbidden state (I-4), explicit violations ("re-export shells", `arbitrary_types_allowed`, `Path` fields, `None`-default load-bearing fields). A reviewer spawn against this prompt will produce actionable file:line verdicts.

## New issues introduced

### Major — A04 still carries the pre-D20 "getter not parser" language

- Pointer: `design/architecture/harness-integration.md:152-153` vs `design/architecture/launch-core.md:336-352`.
- What's wrong: A04 says `observe_session_id()` "is a getter over adapter-held state, not a parser of `launch_outcome`." A06 (and decisions.md D20 "Observe-session-ID contract clarification") explicitly permits parsing `launch_outcome.captured_stdout` for Claude PTY mode as a legitimate source, forbidding only adapter-instance singleton state. `refactors.md:523` even calls the prior "not a parser" framing "superseded."
- Why it matters: this is the exact contradiction the convergence-2 alignment reviewer flagged (`r06-redesign-alignment.md:22-26`). D20 claims it was resolved, and A06 does carry the unified contract — but A04 was not updated to match. `decisions.md:957-974` names `harness-integration.md` (A04) in the "touchpoints updated by convergence-2" list specifically for new stage names, yet the observe-session-id wording was not also corrected. An implementer anchoring on A04's contract will read and enforce the forbidden "not a parser" constraint, then hit the Claude PTY parse in A06 and be stuck re-deciding.
- Fix direction: update `harness-integration.md:151-154` to match the unified A06/D20 language — `observe_session_id()` reads per-launch inputs only (`launch_outcome.captured_stdout` OR per-launch state reachable via `launch_context`), and forbids only adapter-instance singleton state.
- Severity: major. Same severity as the convergence-2 alignment-reviewer major that was supposed to close here; one sentence lag behind the unification.

### Minor — `LaunchRuntime` type-family inconsistency between leaves

- Pointer: `design/refactors.md:302` (frozen `@dataclass`) vs `design/architecture/launch-core.md:155` (Frozen pydantic model).
- What's wrong: same DTO described with two different library choices. Permissive umbrella at `launch-core.md:498-501` allows either, but the specific descriptions disagree.
- Why it matters: pydantic vs dataclass changes constructor semantics, validator availability, and serialization reach. Not load-bearing for persistence (LaunchRuntime is not persisted per `refactors.md:323-324`), but implementers reading the two leaves will re-decide.
- Fix direction: choose one and update both leaves. Pydantic is the more defensible default given the other factory inputs are pydantic.

### Minor — Type-count framing differs across leaves

- Pointer: `refactors.md:367-371` ("4 user-visible + 2 internal = 6 named types") vs `launch-core.md:211-214` ("6 partial-truth DTOs to 7 named types with one-sentence purposes (4 user-visible DTOs + `CompositionWarning` auxiliary + 2 factory-internal)").
- What's wrong: same type ladder, different boundary on whether `CompositionWarning` is counted as user-visible or as auxiliary. Not behavioral.
- Fix direction: pick one framing in both places so the "user-visible" count is stable for reference from overview/realizes sections.

## Sanity pass

- **Schema completeness** — pass. Every live driver field has a named home: `interactive`→`LaunchRuntime.launch_mode`; `effort`→`SpawnRequest.effort`; `unsafe_no_permissions`/`debug`/`harness_command_override`/`report_output_path`/`state_paths`/`project_paths`→`LaunchRuntime`; 8 continuation fields→`SessionRequest` nested (`launch-core.md:138-144`); `context_from` raw→`SpawnRequest`, `context_from_resolved`→`ResolvedRunInputs`; `warning`→`LaunchContext.warnings`; `RetryPolicy` vs `ExecutionBudget` split at `launch-core.md:134-137`; `agent_metadata: dict[str, str]` typed at `launch-core.md:149`; `Path` stored as `str` at `launch-core.md:151-153` and invariant I-5.
- **observe_session_id contract unification** — fail. A06 + decisions.md D20 unified the contract, but A04 `harness-integration.md:152-153` still contradicts. See major finding above.
- **Five new behavioral tests** — pass. All five are specified well enough for a tester: `test_child_cwd_not_created_before_spawn_row` (`refactors.md:583-587`, asserts start_spawn-before-mkdir across drivers including streaming-runner fallback), `test_composition_warnings_propagate_to_launch_context` (`refactors.md:588-593`, stage-append→context→`SpawnActionOutput` end-to-end), `test_workspace_projection_seam_reachable` (`refactors.md:594-599`, sentinel `project_workspace.extra_args` observable in final argv), `test_unsafe_no_permissions_dispatches_through_factory` (`refactors.md:600-604`, runtime flag→`UnsafeNoOpPermissionResolver` with no driver-side construction), `test_session_request_carries_all_eight_continuation_fields` (`refactors.md:605-608`, JSON round-trip schema lock).

## Overall verdict

**ready-with-minor-followups.**

The four D20 changes substantively land: stage split makes A04 reachable, `LaunchRuntime` gives runtime-injected fields an honest home, `LaunchContext.warnings` replaces the deleted sidechannel, and the invariant prompt is drafted in full. One convergence-2 major is not fully closed (A04 observe-session-id wording still contradicts A06/D20) but the fix is a two-line prose patch, not a structural change. Two minor consistency issues (`LaunchRuntime` type family, type-count framing) are prose-level.

Recommend: apply the A04 prose fix plus the two minors, then advance. These do not need another full convergence round.

## Top 3 impl-orch Explore-phase checks

1. **Verify the driving-adapter prohibition list against real call sites.** Run the invariant-prompt I-2 grep list against HEAD — `resolve_policies`, `resolve_permission_pipeline`, `TieredPermissionResolver`, `UnsafeNoOpPermissionResolver`, `adapter.resolve_launch_spec`, `adapter.project_workspace`, `adapter.build_command`, `adapter.fork_session`, `adapter.seed_session`, `adapter.filter_launch_content`, `build_harness_child_env`, `extract_latest_session_id` — in `launch/plan.py`, `launch/process.py`, `ops/spawn/prepare.py`, `ops/spawn/execute.py`, `app/server.py`, `cli/streaming_serve.py`. Pin the initial surface the refactor must scrub; confirm no missed callsites invalidate the prohibition list before implementation begins.

2. **Verify fork-after-row preconditions at existing call sites.** Read current `launch/process.py:~306` (spawn-row creation) and `:~328` (factory call) to confirm the ordering already holds on the primary path. Inspect `launch/streaming_runner.py` fallback (`execute_with_streaming`) for the current create-row-mid-flight path D7 flagged — that's the one that becomes a precondition-error path, not a pass-through. Catch shape surprises (e.g. primary actually creates the row later than claimed, or streaming-runner fallback already has a guard) before phase 1 starts.

3. **Verify `LaunchRuntime` field set is complete against live driver state.** Walk each driving adapter — primary (`launch/plan.py`, `launch/process.py`), worker prepare (`ops/spawn/prepare.py`), worker execute (`ops/spawn/execute.py`), app streaming (`app/server.py`), `cli/streaming_serve.py` — and cross-check every runtime-injected non-user-input field reaching today's `SpawnParams`/`PreparedSpawnPlan` against the 7 fields declared on `LaunchRuntime`. Any leftover field (e.g. debug telemetry hooks, depth markers, control-socket handles) not on `LaunchRuntime` and not factory-derivable is a missed schema entry that needs adding before phase 1 commits to the DTO shape.
