# R06 Retry Structural Review

Report path: `.meridian/work/workspace-config-design/reviews/r06-retry-structural.md`

Verdict: `shape-change-needed`

## 1. Structural health signals

- `src/meridian/lib/launch/streaming_runner.py:1-1117` — module >500 lines. Mixed jobs in one file: terminal-event policy `248-301`, watchdog `361-389`, spawn-manager lifecycle `392-598`, retry/finalize/budget/guardrail orchestration `600-1109`. Signal fire.
- `src/meridian/lib/launch/process.py:1-501` — module >500 lines. Mixed jobs: PTY transport `86-248`, session/spawn-store orchestration `276-404`, finalize + session-id persistence `416-481`. Signal fire.
- `src/meridian/lib/launch/plan.py:234-410` and `src/meridian/lib/ops/spawn/prepare.py:202-397` — same composition concerns solved twice: policy resolution `234-242` vs `202-210`, permission pipeline `329-334` vs `323-328`, prompt/system-prompt shaping `336-367` vs `257-267,330-332`, preview command build `383-410` vs `334-352`. Coupling signal fire.
- `src/meridian/lib/launch/plan.py:8-29`, `src/meridian/lib/launch/process.py:23-46`, `src/meridian/lib/launch/streaming_runner.py:19-87`, `src/meridian/lib/ops/spawn/prepare.py:11-38` — import fanout high. Launch code touches config, catalog, harness, safety, state, prompt, streaming, guardrails in same modules. Coupling signal fire.
- `src/meridian/lib/launch/permissions.py:1-5`, `src/meridian/lib/launch/policies.py:1-5`, `src/meridian/lib/launch/runner.py:1-6` — stage files exist as shells/placeholders, not real owned logic. Split accidental.
- `src/meridian/lib/harness/adapter.py:41-121` — contract module also owns concrete permission-flag projection. Port not just contract; mechanism leaked upstream.
- `src/meridian/lib/ops/spawn/plan.py:39-65` — `PreparedSpawnPlan` mixes user-ish fields, resolved execution state, session state, preview command, warning, passthrough args. One DTO doing too much.
- `src/meridian/lib/launch/plan.py:178-213`, `src/meridian/lib/ops/spawn/prepare.py:356-397`, `src/meridian/lib/app/server.py:332-350`, `src/meridian/cli/streaming_serve.py:69-87`, `src/meridian/lib/ops/spawn/execute.py:397-425` — `PreparedSpawnPlan` built in 5 places. Add one field, touch at least 5 builders plus readers. Variant-cost signal fire.
- `src/meridian/lib/harness/adapter.py:150-163` — `SpawnRequest` exists, but `rg` shows zero uses outside definition. Type split not load-bearing. Dead abstraction signal.
- `src/meridian/lib/launch/fork.py:7-34` and `src/meridian/lib/ops/spawn/prepare.py:296-311` — fork materialization still has helper plus direct inline copy. “One variant -> edit N files” already happening.
- `src/meridian/lib/harness/adapter.py:332-337,466-473` with `src/meridian/lib/launch/process.py:452-477` and `src/meridian/lib/launch/streaming_runner.py:859-889` — `observe_session_id()` seam declared, no real impls, executors still own observation through `extract_latest_session_id()`. Barrier not finished.
- `src/meridian/lib/launch/__init__.py:65-77` and `src/meridian/lib/launch/context.py:153-173` — `MERIDIAN_HARNESS_COMMAND` bypass logic duplicated. Central factory not sole owner even for dry-run.
- `src/meridian/lib/launch/cwd.py:19-22` — file says helper must “stay in sync” with runner behavior. Named sync contract means split already brittle.

## 2. Responsibility map

- `src/meridian/lib/launch/__init__.py:47-99` — public primary-launch entrypoint + dry-run preview. Overlap accidental with `context.py:153-173` on bypass handling and with `plan.py`/`process.py` on orchestration.
- `src/meridian/lib/launch/artifact_io.py:7-11` — tiny artifact text reader. Split correct.
- `src/meridian/lib/launch/command.py:16-63` — legacy env builder + passthrough export. Overlap accidental with `env.py:123-210` and `context.py:147-203`.
- `src/meridian/lib/launch/constants.py:7-64` — shared filenames, timeouts, base commands. Split correct.
- `src/meridian/lib/launch/context.py:31-213` — real launch-attempt builder. Good seam. Bad input shape: still needs pre-resolved `PreparedSpawnPlan` plus loose `run_prompt`/`run_model`.
- `src/meridian/lib/launch/cwd.py:10-26` — child-cwd rule for Claude-in-Claude. Useful leaf. Split brittle because comment admits mirrored logic elsewhere.
- `src/meridian/lib/launch/env.py:99-210` — child env sanitize/inherit/build. Real leaf. Correct place for env mechanics.
- `src/meridian/lib/launch/errors.py:62-110` — retry classification. Leaf. Split correct.
- `src/meridian/lib/launch/extract.py:92-123` — finalization extraction orchestration. Reasonable leaf; overlap with `report.py` is intentional.
- `src/meridian/lib/launch/fork.py:7-34` — fork materialization stage. Correct concern. Current caller split is accidental because `prepare.py` still does same job inline.
- `src/meridian/lib/launch/launch_types.py:15-80` — leaf contracts for permission resolver, launch spec, preflight result. Split correct.
- `src/meridian/lib/launch/permissions.py:1-5` — re-export only. Split accidental.
- `src/meridian/lib/launch/plan.py:40-430` — primary planner: config resolution, prompt shaping, permission resolution, command preview, `PreparedSpawnPlan` build. Overlap heavy with `prepare.py`; split wrong today.
- `src/meridian/lib/launch/policies.py:1-5` — re-export only. Split accidental.
- `src/meridian/lib/launch/process.py:251-495` — primary executor + spawn/session bookkeeping + primary-only PTY/direct-Popen transport. Executor split is correct; file width is not.
- `src/meridian/lib/launch/prompt.py:63-318` — prompt composition, report instruction, skill injection, template rendering. Big but coherent enough.
- `src/meridian/lib/launch/reference.py:27-163` — reference-file and template-variable leaf helpers. Split correct.
- `src/meridian/lib/launch/report.py:140-171` — report extraction fallback chain. Split correct.
- `src/meridian/lib/launch/resolve.py:230-329` — policy/profile/harness/skill resolution. Good leaf. Overlap bad at caller layer, not inside file.
- `src/meridian/lib/launch/runner.py:1-6` — placeholder only. Split accidental.
- `src/meridian/lib/launch/runner_helpers.py:41-314` — shared executor IO/timeout/artifact helpers. Mixed helper bag, but still real shared mechanism.
- `src/meridian/lib/launch/session_ids.py:16-54` — old session-id observation utility. Now upstream debt because design wants adapter-owned observation.
- `src/meridian/lib/launch/session_scope.py:23-67` — session lifecycle context manager. Split correct.
- `src/meridian/lib/launch/signals.py:21-237` — signal forwarding + process-group helpers. Mechanism-heavy, but coherent enough.
- `src/meridian/lib/launch/streaming_runner.py:600-1109` — streaming executor + retry engine + finalizer + event parser. Too many responsibilities.
- `src/meridian/lib/launch/text_utils.py:8-63` — tiny text helper leaf. Split correct.
- `src/meridian/lib/launch/types.py:41-132` — primary-launch request/result types. Fine for primary only, but overall run typing is fragmented because other DTOs model same run elsewhere.
- `src/meridian/lib/launch/written_files.py:116-137` — written-file artifact extraction. Split correct.

## 3. Alternative shapes

- `Hexagonal with reshaped DTO` — honest fix for current blocker. Still keeps fake stage files, type ladder, and “port” module doing mechanism work. Better than now. Not best.
- `Pipeline / staged functions` — top pick. Domain here is not rich business object world. Domain here is deterministic launch composition + explicit side-effect stages. Keep 3 drivers. Keep harness adapter protocol. Keep 2 executors. Delete fake frame.
- `Command pattern` — wrong fit. Adds objects, does not remove duplicated preparation.
- `Effect system` — wrong weight. Too much machinery for a fixed launch path.
- `Builder pattern` — hides precedence and side-effect order in mutating fluent API. Worse for this domain.
- `Plain function composition` — near same as top pick. Good inside implementation. I would describe package shape as pipeline, not “plain functions only”, because executors still need names and owned modules.

Top pick sketch:

```python
@dataclass(frozen=True)
class LaunchInputs:
    request: SpawnRequest
    runtime: RuntimeBindings
    session: SessionSpec
    permissions: PermissionSpec

@dataclass(frozen=True)
class LaunchAttempt:
    adapter: SubprocessHarness
    spec: ResolvedLaunchSpec
    env: Mapping[str, str]
    child_cwd: Path
    report_path: Path
    session_id_hint: str | None

def resolve_launch_inputs(...) -> LaunchInputs
def resolve_profile_and_prompt(inputs: LaunchInputs) -> LaunchInputs
def resolve_permissions(inputs: LaunchInputs) -> LaunchInputs
def materialize_fork(inputs: LaunchInputs) -> LaunchInputs
def build_launch_attempt(inputs: LaunchInputs) -> LaunchAttempt
def preview_command(attempt: LaunchAttempt) -> tuple[str, ...]
def execute_primary(attempt: LaunchAttempt) -> LaunchResult
async def execute_streaming(attempt: LaunchAttempt, ...) -> LaunchResult
def observe_launch_result(adapter: SubprocessHarness, attempt: LaunchAttempt, outcome: LaunchOutcome) -> LaunchResult
```

Why this shape:

- one real input type before composition
- one real attempt type after composition
- executors consume attempt, not half-plan + loose args
- side-effect stages named and isolated
- no placeholder port modules needed

## 4. Deep issues regardless of shape

- Type ladder too long. One run becomes `LaunchRequest` `src/meridian/lib/launch/types.py:41-61`, dead `SpawnRequest` `src/meridian/lib/harness/adapter.py:150-163`, `SpawnParams` `165-185`, `PreparedSpawnPlan` `src/meridian/lib/ops/spawn/plan.py:39-65`, `ResolvedPrimaryLaunchPlan` `src/meridian/lib/launch/plan.py:40-59`, `LaunchContext` `src/meridian/lib/launch/context.py:31-71`. Too many partial truths.
- `PreparedSpawnPlan` is not just barrier; it is wrong-level bundle. Holds resolved permission objects, preview command, warning text, session metadata, prompt, passthrough args, agent metadata all at once `src/meridian/lib/ops/spawn/plan.py:44-65`.
- Planning DTOs carry live objects. `ExecutionPolicy` stores `PermissionResolver` object `src/meridian/lib/ops/spawn/plan.py:14-21`, so planning model needs `arbitrary_types_allowed=True`. Inspectable file-authority shape weakened.
- Harness “port” not clean. `src/meridian/lib/harness/adapter.py:58-86,102-121` projects concrete harness permission flags inside contract module. Mechanism already leaked into supposed abstraction root.
- Session-id observation is post-launch observable, not launch input. Protocol seam exists `src/meridian/lib/harness/adapter.py:332-337`, default no-op `466-473`, but executors still scrape old way through `src/meridian/lib/launch/session_ids.py:16-54`, `src/meridian/lib/launch/process.py:452-477`, `src/meridian/lib/launch/streaming_runner.py:859-889`.
- Driver boundaries inconsistent. `src/meridian/lib/app/server.py:332-350`, `src/meridian/cli/streaming_serve.py:69-87`, and `src/meridian/lib/ops/spawn/execute.py:397-425` all rebuild plan objects directly. `src/meridian/lib/launch/__init__.py:65-77` still owns dry-run bypass logic. “One factory” not true in shape, not just in one DTO.
- Fork and child-cwd are real cross-cutting mechanisms, not cute pure pipeline stages. Evidence `src/meridian/lib/launch/fork.py:7-34`, `src/meridian/lib/ops/spawn/prepare.py:296-311`, `src/meridian/lib/launch/cwd.py:19-22`. Whichever shape lands, give each exactly one owner.
- `SpawnRequest` dead-on-arrival is strong signal R06 solved package silhouette before it solved ownership. Type exists. Flow never adopted it.

## 5. Verdict

- `shape-change-needed`
- `PreparedSpawnPlan` barrier real. Not only barrier.
- Real structural debt bigger: fake stage files, dead `SpawnRequest`, plan DTOs with live objects, duplicated plan builders, old session-id path still in executors, contract module leaking mechanism.
- Simpler shape: pipeline/staged functions with one pre-composition input type and one post-composition attempt type.
- Keep: 3 drivers, harness adapter protocol, 2 executors.
- Delete: placeholder modules, duplicate plan construction, duplicate dry-run bypass logic, session-id utility path once adapter-owned observation lands.

Bottom line:

- if team wants minimum churn, dto reshape alone can unblock one remediation pass
- if team wants subsystem that stops fighting future refactors, do pipeline reshape now
- current hexagonal frame is too much costume, not enough load-bearing structure
