# Design Revision Brief — streaming-parity-fixes v2

Four reviewers completed the first pass on the v2 design for streaming adapter parity. All four verdicts: **Needs revision**. The architectural shape is correct, but the design docs disagree with themselves in several load-bearing places, and a handful of enforcement mechanisms are too weak to live up to their promises. None of the findings require a redesign — they are doc edits, small interface additions, and one structural move (preflight inversion).

**Your job:** apply every fix below to the design docs in `$MERIDIAN_WORK_DIR/design/`, the decision log in `$MERIDIAN_WORK_DIR/decisions.md`, and the scenario files in `$MERIDIAN_WORK_DIR/scenarios/`. Work through the list in the order given — earlier items unblock later ones. Do not re-scope; do not add new decisions not listed here. When you are done, update `design/overview.md` to reference any new module names or structural additions you introduced, and record each applied fix as a short bullet under a new `## Revision Pass 1 (post p1422/p1423/p1425/p1426)` section appended to `decisions.md`.

Read these review reports in full before starting — they contain the reasoning:

- `.meridian/spawns/p1422/report.md` (type-contract review, gpt-5.4)
- `.meridian/spawns/p1423/report.md` (permission-pipeline review, gpt-5.2)
- `.meridian/spawns/p1425/report.md` (design-alignment review, opus)
- `.meridian/spawns/p1426/report.md` (structural/refactor review, opus)

---

## CRITICAL / HIGH fixes (must land)

### F1. `CodexLaunchSpec` shape inconsistency across three docs
All four reviewers flagged this. Currently `launch-spec.md` §Codex declares `sandbox_mode`, `approval_mode`, `report_output_path` on `CodexLaunchSpec`, and the factory example populates them. But `transport-projections.md` line ~237 declares the "revised shape: NOT stored on CodexLaunchSpec", and `decisions.md` D15 confirms removal. All three docs must agree.

**Fix.**
- In `launch-spec.md` §Codex, remove `sandbox_mode` and `approval_mode` fields from `CodexLaunchSpec`. Keep only `report_output_path` (+ inherited base fields + `permission_resolver` + `extra_args`).
- In the Codex factory example (`launch-spec.md`), delete the `sandbox_mode=sandbox_mode`, `approval_mode=approval_mode` lines. Delete the `_map_sandbox_mode` / `_map_approval_mode` helper references.
- Add a prominent note at the top of `launch-spec.md` §Codex: "D15 (see decisions.md) supersedes earlier shape: sandbox/approval are not stored on the spec. Projection reads `spec.permission_resolver.config.sandbox` and `.config.approval` directly."
- Verify `transport-projections.md` §Codex and `decisions.md` D15 are already aligned — they should be.

### F2. `_PROJECTED_FIELDS` examples still list removed fields
In `transport-projections.md` the `codex_cli.py` and any other Codex projection example lists `"sandbox_mode"` and `"approval_mode"` inside `_PROJECTED_FIELDS`. Under F1's removal, these fields no longer exist on `CodexLaunchSpec.model_fields`. The import-time completeness guard would raise `ImportError` on first import because `_PROJECTED_FIELDS` contains stale entries.

**Fix.** Rewrite every `_PROJECTED_FIELDS` example in `transport-projections.md` so the field list matches the post-D15 `CodexLaunchSpec` shape. Add a single worked example of how the projection reads `spec.permission_resolver.config.sandbox` instead of `spec.sandbox_mode`.

### F3. Abstract-method enforcement: Protocol alone does not raise TypeError
`typed-harness.md` says "A new harness that forgets `resolve_launch_spec` fails at instantiation because `HarnessAdapter` is a Protocol." That is false. Protocols (even with `@runtime_checkable`) do not raise `TypeError` at instantiation — only `abc.ABC` + `@abstractmethod` does. Both p1422 and p1425 flagged this; S001 as written will not fire.

**Fix.**
- In `typed-harness.md` §"Adapter Contract", declare that `HarnessAdapter[SpecT]` is both a `runtime_checkable` Protocol (for structural type checks) **and** that `BaseSubprocessHarness` is declared `class BaseSubprocessHarness(Generic[SpecT], ABC)` with `@abstractmethod def resolve_launch_spec(...)`. The two enforcement mechanisms play different roles: Protocol for pyright's structural check, ABC for runtime instantiation rejection.
- Remove any wording that says "Protocol conformance raises `TypeError` at instantiation". Replace with "ABC abstract-method enforcement raises `TypeError` at instantiation; Protocol conformance is the pyright-time check."
- Update `decisions.md` D3 body to state the ABC + @abstractmethod mechanism explicitly.
- Verify `scenarios/S001` `Verification` section names the ABC mechanism.

### F4. Dispatch cast: runtime isinstance guard + narrow cast
`typed-harness.md` currently says `await connection.start(config, cast(Any, spec))` at the dispatch site. `cast(Any, spec)` is a total type escape, and there is no runtime check that the spec actually matches `bundle.spec_cls`. Both p1422 and p1426 flagged this. S002's runtime `TypeError` assertion has nothing to fire against.

**Fix.** Replace the single declared cast with a runtime-checked narrow:

```python
async def dispatch_start(
    bundle: HarnessBundle[SpecT],
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec,
) -> HarnessConnection[SpecT]:
    if not isinstance(spec, bundle.spec_cls):
        raise TypeError(
            f"HarnessBundle invariant violated: adapter for "
            f"{bundle.harness_id} returned {type(spec).__name__}, "
            f"expected {bundle.spec_cls.__name__}"
        )
    connection = bundle.connection_cls()
    await connection.start(config, cast(SpecT, spec))
    return connection
```

- Update `typed-harness.md` dispatch section with the isinstance guard and `cast(SpecT, spec)` (not `cast(Any, spec)`).
- Update `decisions.md` (D1 or D2) to name the runtime guard as part of the dispatch contract.
- Update `scenarios/S002` so its runtime assertion cites the dispatch-site `TypeError` as the trigger, not a per-connection check.

### F5. `prepare_launch_context` has `if harness_id == CLAUDE:` branch — invert to adapter.preflight()
p1426 CRITICAL-adjacent finding H-S3. The shared launch core in `runner-shared-core.md` currently includes an `if harness_id == HarnessId.CLAUDE:` branch that executes Claude-specific preflight (parent permissions read, `--add-dir` injection). This is the exact Open/Closed violation v2 claims to eliminate in the harness layer but imports one layer up.

**Fix.** Add a `preflight` method to `HarnessAdapter[SpecT]`:

```python
@dataclass(frozen=True)
class PreflightResult:
    expanded_passthrough_args: tuple[str, ...]
    extra_env: dict[str, str] = field(default_factory=dict)
    extra_cwd_overrides: dict[str, str] = field(default_factory=dict)

class HarnessAdapter(Protocol, Generic[SpecT]):
    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult: ...
```

- `BaseSubprocessHarness.preflight` returns an empty `PreflightResult`.
- `ClaudeAdapter.preflight` does the `.claude/` read and `--add-dir` injection.
- `CodexAdapter.preflight` / `OpenCodeAdapter.preflight` use the base default (empty).
- `prepare_launch_context` calls `bundle.adapter.preflight(...)` instead of branching on `harness_id`.
- Move `claude_preflight.py` from `launch/` to `harness/claude_preflight.py` (next to `harness/claude.py`).
- Update `typed-harness.md`, `runner-shared-core.md`, and `decisions.md` accordingly. Add a new decision D21 documenting the adapter.preflight contract.

### F6. Transport-wide completeness guard (not just projection-layer)
p1422 CRITICAL. The current `_PROJECTED_FIELDS` + `_DELEGATED_FIELDS` split only checks the projection consumer. A field listed as "delegated" (e.g., `continue_session_id`, `continue_fork`) can still be silently dropped by the sibling consumer — `_bootstrap_thread`, send-user-turn wiring, method selection, env projection. The guard does not cover those.

**Fix.** In `transport-projections.md` §Completeness Guard, state explicitly that the guard covers the **union** of every consumer in a given transport path, not only the projection function. For Codex streaming, the guard in `projections/codex_streaming.py` (after F9 merge) must union every consumer of `CodexLaunchSpec` on the streaming path: app-server args, JSON-RPC params, method selection, prompt sender, env projection. Document the pattern: each consumer-module exports an `_ACCOUNTED_FIELDS: frozenset[str]` set, and the projection module's guard compares `CodexLaunchSpec.model_fields - _SPEC_DELEGATED_FIELDS` against the union of those sets. A field in `_DELEGATED_FIELDS` still has to appear in at least one `_ACCOUNTED_FIELDS` of a delegated consumer.

Add a `scenarios/S036` (append to `scenarios/overview.md` and create the file) for this broader completeness check: "Delegated field has no consumer". Tester: @unit-tester.

### F7. Passthrough args cannot override sandbox/approval (reserved-flags policy)
p1423 HIGH. Currently projections append `spec.extra_args` after permission flags. If the harness CLI is last-wins, a user can `-c sandbox_mode="danger-full-access"` in extra_args and bypass the enforced config.

**Fix.** In `permission-pipeline.md`, add a new section "Reserved Flags":

- Define `_RESERVED_CODEX_ARGS: frozenset[str] = frozenset({"sandbox", "sandbox_mode", "approval_policy", "full-auto", "ask-for-approval"})` (verified against real codex after D20 probe).
- Define `_RESERVED_CLAUDE_ARGS: frozenset[str] = frozenset({"--allowedTools", "--disallowedTools"})` — these are merged, not overridden (dedupe via D8).
- The projection filters `spec.extra_args` and strips any arg matching a reserved prefix. Emits WARNING log per stripped arg.
- Unit test: attempted override does not change effective permission config.

Add `scenarios/S037` for reserved-flag stripping. Tester: @unit-tester + @smoke-tester.

### F8. Fail-closed policy at Codex integration boundary
p1423 CRITICAL. D20 requires probing `codex app-server --help` but doesn't define fail-closed behavior if the probe shows the sandbox/approval knobs don't exist.

**Fix.** In `decisions.md` D20, add: "If the probe reveals that `codex app-server` cannot express the requested sandbox/approval, the projection raises `HarnessCapabilityMismatch` and the runner fails the spawn before launch. No silent downgrade is permitted. If `permission_resolver.config.sandbox != 'default'` and the implementation cannot emit an equivalent app-server directive, the spawn fails with a structured error naming the missing capability."

Add `scenarios/S038` for fail-closed behavior. Tester: @smoke-tester.

### F9. Codex `codex_appserver.py` + `codex_jsonrpc.py` → merge into `codex_streaming.py`
p1426 HIGH-ish structural finding M-S3. The Codex streaming path currently splits into 3 modules, creating a 5-file blast radius. Merge `codex_appserver.py` + `codex_jsonrpc.py` into one `projections/codex_streaming.py` exporting two functions. One `_PROJECTED_FIELDS` / `_DELEGATED_FIELDS` guard per module (not per function).

**Fix.** Update `transport-projections.md` file layout, update the sample code, and adjust `scenarios/S030`, `S031`, and `edge-cases.md` to reference the new module name.

### F10. `NoOpPermissionResolver` is NOT the REST server default
p1423 HIGH. Currently `permission-pipeline.md` says the REST server defaults to `NoOpPermissionResolver` "for backward compatibility". But AGENTS.md explicitly says "No real users... No backwards compatibility needed." And the project instruction is to make silent opt-outs impossible.

**Fix.** In `permission-pipeline.md` §REST server:
- Default behavior: missing permission block is HTTP 400 Bad Request.
- Opt-out: server config knob `--allow-unsafe-no-permissions` (loud name on purpose) enables `NoOpPermissionResolver` as the fallback for requests missing permission metadata. Without the knob, the server rejects.
- Rename the class to `UnsafeNoOpPermissionResolver` in `decisions.md` D11, `launch-spec.md`, and all references — the name must match the risk.

Update `scenarios/S013` to reflect the strict default.

---

## MEDIUM fixes (must land in the same pass)

### F11. D5 guard sample catches both directions of drift
`decisions.md` D5 code sample only checks `_missing = _expected - _PROJECTED_FIELDS`. It doesn't check stale entries (`_stale = _PROJECTED_FIELDS - _expected`). Update the D5 code block to show both-direction check and a combined error message.

### F12. D10 addresses L3, not L5
`decisions.md` D10 says it addresses "L5". It actually closes L3 (`agent_name` duplication). Correct the label. Add a sentence to D12 or D13 noting that L5 (per-harness logic in `common.py`) is addressed by the `launch/text_utils.py` extraction.

### F13. S002 / typed-harness.md contradiction on runtime isinstance
`typed-harness.md` says "no runtime spec-subclass checks downstream of dispatch". `scenarios/S002` requires a runtime `TypeError` from `ClaudeConnection.start`. F4 resolves this at dispatch site, so `S002` should cite the dispatch-site `TypeError`, not a per-connection `start()` check. Update S002 accordingly. Carve out in `typed-harness.md`: "Defensive boundary guards at dispatch are allowed; behavior-switching isinstance branches inside connections are not."

### F14. S030 / S031 enumerate every projection module
Currently S030 and S031 list only `projections/claude.py, projections/codex.py, projections/opencode.py`. After F9 consolidation, the full list is `claude.py, codex_cli.py, codex_streaming.py, opencode_cli.py, opencode_http.py` (or equivalent post-F9 names). Rewrite both scenarios to enumerate every module per the updated `transport-projections.md` layout.

Also add the meta-assertion: `rg "_PROJECTED_FIELDS" src/meridian/lib/harness/projections/` returns exactly N matches, one per module listed in the design.

### F15. S033 points at the right function
`scenarios/S033` currently says "projection function (`project_opencode_spec_to_http_payload`)". The HTTP payload function does NOT forward passthrough args; it sends JSON. The debug log lives in `project_opencode_spec_to_serve_command` (the CLI projection for `opencode serve`). Rewrite S033 to target the correct function.

### F16. S019 debug log must exist in `transport-projections.md`
`scenarios/S019` asserts a debug log for Codex streaming ignoring `report_output_path`, but `transport-projections.md` `project_codex_spec_to_appserver_command` never reads `report_output_path`. Add the guarded debug log to the projection example in `transport-projections.md`:

```python
if spec.report_output_path is not None:
    logger.debug(
        "Codex streaming ignores report_output_path; reports extracted from artifacts",
        path=spec.report_output_path,
    )
```

Mark `report_output_path` in Codex streaming's `_DELEGATED_FIELDS` set with a comment: `"report_output_path",  # delegated to artifact extraction, not wire`.

### F17. S020 covers all three harnesses
`scenarios/S020` currently tests `ClaudeLaunchSpec(continue_fork=True, continue_session_id=None)`. `continue_fork` / `continue_session_id` live on the base `ResolvedLaunchSpec`, so the validator applies to all harnesses. Either place the validator on `ResolvedLaunchSpec` (cleanest) or parametrize S020 over all three subclasses. State the choice in `launch-spec.md` §Base Spec.

### F18. S005 / S030 verification plans: executable strategy
The current "monkey-patch `ClaudeLaunchSpec.model_fields`" strategy does not work — Pydantic v2's `model_fields` is not a simple dict and `importlib.reload` captures the snapshot at first import. Rewrite the verification plans to use a concrete strategy:

- Extract the drift check into a helper `_check_projection_drift(spec_cls: type[BaseModel], projected: frozenset[str], delegated: frozenset[str]) -> None` in `harness/projections/_guards.py`.
- Each projection module calls the helper at import time: `_check_projection_drift(ClaudeLaunchSpec, _PROJECTED_FIELDS, _DELEGATED_FIELDS)`.
- Unit tests exercise the helper directly with a synthetic spec class, asserting both the happy path and both error paths (missing, stale).

Update `scenarios/S005`, `S030`, and `transport-projections.md` §Completeness Guard to reference the helper pattern.

### F19. Import cycle topology: add `launch_types.py`
`typed-harness.md` asserts "verified acyclic" without specifying how. Current layout has `adapter.py` ↔ `launch_spec.py` cycle via `SpawnParams` / `PermissionResolver`. Extract a leaf module `src/meridian/lib/harness/launch_types.py` containing:

- `SpawnParams`
- `PermissionResolver` (Protocol)
- `SpecT` TypeVar
- `ResolvedLaunchSpec` (base)
- `PreflightResult` (from F5)

Both `adapter.py` and `launch_spec.py` import from `launch_types.py`. State the dependency DAG explicitly in `typed-harness.md`.

### F20. `HarnessConnection` ABC and facet Protocols: collapse or inherit
`typed-harness.md` has `HarnessConnection[SpecT]` ABC with abstract methods that duplicate `HarnessLifecycle`/`HarnessSender`/`HarnessReceiver` runtime_checkable Protocols. Pick one of:

- **(a) Collapse.** Delete the three facet Protocols. Only `HarnessConnection[SpecT]` ABC exists.
- **(b) Inherit.** `class HarnessConnection(HarnessLifecycle, HarnessSender, HarnessReceiver, Generic[SpecT], ABC): ...` — methods live on the facets only.

Default choice: **(a) Collapse** — grep shows the facets have almost no consumers in the design. Add a decision D22 recording the choice and the rg-backed audit.

### F21. `cast(Any, spec)` → `cast(SpecT, spec)` (see F4)
Already covered by F4. Audit all uses of `cast(Any, ...)` in the v2 design docs and narrow every one.

### F22. Dispatch cast site: one authoritative doc
`typed-harness.md` puts the cast in `SpawnManager.start_spawn`. `runner-shared-core.md` line ~311 says it lives inside the shared launch context. Pick `SpawnManager.start_spawn` (it is the actual dispatch seam; `prepare_launch_context` doesn't call `connection.start`). Remove the conflicting wording from `runner-shared-core.md`.

### F23. Approval-mode matrix: distinct semantic behavior, not distinct wire strings
`scenarios/S016` requires every sandbox×approval cell to produce a distinct wire command. But Codex may collapse `auto`/`yolo`/`confirm` to a single `on-request` mode at the wire level. Rewrite S016 so the requirement is "distinct **semantic** behavior + audit trail", not distinct CLI strings. Meridian-side handler behavior (auto-accept vs reject) and audit logging is what differs between `auto` and `yolo` when Codex exposes the same wire flag.

### F24. Approval value validation: `PermissionConfig.approval` is a `Literal`
`PermissionConfig.approval` should be typed as `Literal["default", "auto", "yolo", "confirm"]` so pyright catches drift at the source. Alternatively, the projection's mapper raises `ValueError` on unknown values. Pick the Literal option and state it in `permission-pipeline.md`.

### F25. Confirm-mode event ordering: precise sequence semantics
`decisions.md` D14 and `scenarios/S032` should clarify that the ordering guarantee is "event is enqueued before `send_error` is awaited". In tests, assert sequence numbers / call ordering, not wall-clock. Update both.

### F26. `--append-system-prompt` policy: reconcile overview.md and S022
`overview.md` says Meridian's `--append-system-prompt` drops the user's value; `transport-projections.md` + `S022` say both flags appear and Claude's last-wins semantics let the user win. Pick one policy and align all three docs. Recommended: keep S022's "both flags appear, user wins by last-wins" but add a projection-time WARNING log when a known Meridian-managed flag is detected in `extra_args`. Update `overview.md` accordingly.

### F27. D19 commits to a post-v2 line budget or extracts drain/finalize
p1426 M-S7. D19 defers full runner decomposition but current runners are ~958 / ~1189 lines. Post-v2 forecast is ~750 / ~950 lines — still above the 500-line health signal. Either (a) commit in D19 to a post-v2 line budget with a trigger ("if post-v2 sizes exceed X, raise L11 back into v2 scope"), or (b) extract `drain + finalize + report extraction` into `launch/finalize.py` as part of v2. Default to (a): name the target as 500 lines each, trigger L11 if exceeded.

### F28. Projection file naming: consistent axis
p1426 M-S4. Rename projection modules to `projections/project_<harness>_<transport>.py` (or pick a new directory name like `wire/` or `projection/`):

- `projections/project_claude.py` (one file, both transports)
- `projections/project_codex_subprocess.py`
- `projections/project_codex_streaming.py` (after F9 merge)
- `projections/project_opencode_subprocess.py`
- `projections/project_opencode_streaming.py`

The invariant: `rg <basename>` produces one hit per conceptual thing. Update `transport-projections.md`, `overview.md`, and scenarios referencing old names.

---

## LOW fixes (clean up in the same pass)

### F29. `launch/core.py` → `launch/context.py`
Rename the shared launch module. `core.py` is a generic "pit" name; `context.py` matches the primary export (`LaunchContext`).

### F30. Delete `mcp_tools` from `SpawnParams` for v2
`mcp_tools` is delegated to `build_harness_child_env`, but `overview.md` says MCP wiring is out of scope and all adapters return `None` from `mcp_config()`. Delete the field for v2. Add a decision D23 documenting the stub-out and noting that MCP lands in a future work item.

### F31. `_SPEC_HANDLED_FIELDS` per-adapter limitation stated
Add a sentence to `launch-spec.md` §Completeness Guard: "This guard enforces that every `SpawnParams` field has a home somewhere in the system. It does not enforce per-adapter completeness — an adapter that ignores a field will not trip this guard. Per-adapter completeness is enforced at the projection layer via `_PROJECTED_FIELDS`."

### F32. `BaseSubprocessHarness` default-method audit note
Add a bullet to `typed-harness.md` Migration Shape: "Audit `BaseSubprocessHarness` eleven default methods (`fork_session`, `owns_untracked_session`, `blocked_child_env_vars`, `seed_session`, `filter_launch_content`, `detect_primary_session_id`, `mcp_config`, `extract_report`, `resolve_session_file`, `run_prompt_policy`, `build_adhoc_agent_payload`). Delete any that have no caller or are overridden by every concrete adapter."

### F33. `HarnessBinaryNotFound` shared error class
p1425 L-C. Either introduce `HarnessBinaryNotFound` as an explicit decision in `decisions.md` (new D24), or rewrite `scenarios/S028` to reference "whatever structured error class the runners emit" without naming it. Pick the former: introduce the class in `lib/harness/errors.py` (or equivalent) and cite it in D24.

### F34. S015 field-coverage assertion tightening
`scenarios/S015` says "iterate over `ClaudeLaunchSpec.model_fields` and confirm every field is reflected somewhere in the output". Tighten: for each field, the test table specifies the exact wire representation (flag+arg pair, deduped-tail contents, or "delegated to ..." with pointer). Parametrize the test over the field table.

### F35. `project_opencode_spec_to_http_payload` → `project_opencode_spec_to_session_payload`
Rename to match the HTTP semantics (the payload creates a session). Update `decisions.md` D7, `transport-projections.md`, and scenarios.

### F36. `NoOpPermissionResolver` → `UnsafeNoOpPermissionResolver` everywhere (see F10)
Already covered by F10, but make sure the rename lands in `decisions.md` D11, all design docs, and all scenario files.

### F37. `NoOpPermissionResolver` construction warning: test fixture suppression
Add a note to `decisions.md` D11: "Unit tests that intentionally construct `UnsafeNoOpPermissionResolver` may pass a `_suppress_warning=True` kwarg for noise control, or route the warning through `warnings.warn` so pytest can capture-suppress it."

---

## Deliverables

After applying every fix:

1. Every design doc in `$MERIDIAN_WORK_DIR/design/` is self-consistent and consistent with decisions.md.
2. Every scenario file referenced in a fix is updated; new scenarios (S036, S037, S038) exist and are added to `scenarios/overview.md`.
3. `decisions.md` has a new `## Revision Pass 1 (post p1422/p1423/p1425/p1426)` section at the bottom with one bullet per applied fix, naming the fix ID (F1–F37) and a one-line description of what changed. New decisions (D21–D24) are added as full entries in the body of decisions.md.
4. `design/overview.md` reflects any new module names (`launch_types.py`, `harness/claude_preflight.py`, `launch/context.py`, renamed projection modules, `projections/_guards.py`).
5. Report what you changed per fix ID. Call out any fix you could not apply without an unresolved question, and what the question is.

Do not introduce new decisions outside the F1–F37 scope. If you find another problem, flag it in your report but do not fix it — I will decide whether to include it in the next revision pass.
