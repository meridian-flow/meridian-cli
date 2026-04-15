# Migration Path

## Principle

The subprocess path is the stable reference. It must continue producing identical commands throughout the migration. Each phase is independently verifiable and committable.

## Phase 0: Fix Effort Plumbing (Upstream Bug)

### What changes
- Add `effort: str | None = None` to `PreparedSpawnPlan` in `src/meridian/lib/ops/spawn/plan.py`.
- Wire effort from `prepare.py` (where `resolved.effort` is already available) into the plan.
- Both `runner.py` and `streaming_runner.py` include `effort=plan.effort` when constructing `SpawnParams`.

### Why this is Phase 0
The correctness reviewer (p1389) discovered that effort never reaches either runner today. `PreparedSpawnPlan` lacks an `effort` field, so both runners silently drop it. This is an upstream bug affecting both paths — not a streaming-only issue. Fixing it before the spec work means the spec factory can rely on effort being present in `SpawnParams` when it arrives.

### Verification
- Unit test: construct a `PreparedSpawnPlan` with `effort="high"`, verify both runners pass `effort="high"` to `SpawnParams`.
- Smoke test: launch a Claude subprocess spawn with `--effort high`, verify `--effort high` appears in the command (via `cli_command` preview).

## Phase 1: Introduce ResolvedLaunchSpec + Factory Methods

### What changes
- New file: `src/meridian/lib/harness/launch_spec.py` with `ResolvedLaunchSpec`, `ClaudeLaunchSpec`, `CodexLaunchSpec`, `OpenCodeLaunchSpec`.
- Each adapter (`claude.py`, `codex.py`, `opencode.py`) gains `resolve_launch_spec(run, perms) -> XxxLaunchSpec`.
- Import-time completeness assertion: `_SPEC_HANDLED_FIELDS == set(SpawnParams.model_fields)`.
- Effort normalization functions refactored into spec factory methods that return normalized strings instead of mutating arg lists.
- The spec carries `PermissionConfig` and `PermissionResolver` reference (semantic, not CLI flags — per D9).

### What doesn't change
- `build_command()` — untouched, still uses strategy maps.
- Connection adapters — untouched, still hand-pick from `SpawnParams`.
- Runners — untouched.

### Verification
- Import-time assertion passes (all SpawnParams fields handled).
- Type check passes (`uv run pyright`).
- Unit test: for each adapter, `resolve_launch_spec()` with a representative `SpawnParams` produces the expected spec values.
- Existing tests pass unchanged.

## Phase 2: Reimplement build_command() on ResolvedLaunchSpec

### What changes
- Each adapter's `build_command()` calls `resolve_launch_spec()` first, then projects the spec to CLI args via explicit code (not strategy maps).
- The strategy map machinery (`StrategyMap`, `FlagStrategy`, `FlagEffect`, `build_harness_command()`) is retired (D10). The CLI projection is explicit per-harness code that builds args from the spec.
- Permission flags: CLI projection calls `spec.permission_resolver.resolve_flags(harness_id)` to get flags.
- Each CLI projection function includes a `_CLI_PROJECTED_FIELDS` frozenset that must cover all non-default fields of the spec (D15). Import-time assertion checks this.

### Design decision: explicit code over strategy framework (D10)
The strategy framework was rejected because the spec already provides completeness checking and normalization. Keeping both creates two policy layers (flagged by p1391). The explicit projection code is short, greppable, and its arg ordering is explicit — eliminating the strategy-ordering sensitivity noted by p1390 (Finding 4).

### What doesn't change
- Connection adapters — still untouched.
- Runners — still untouched.
- External behavior — `build_command()` must produce byte-identical CLI args.

### Verification
- **Critical**: For each adapter, given the same `SpawnParams` + `PermissionResolver`, the new `build_command()` produces the same `list[str]` as the old one. Parameterized unit test covering:
  - Fresh session (no continue_session_id)
  - Resume session
  - Fork session
  - Effort set to each level (low/medium/high/xhigh)
  - With and without adhoc_agent_payload
  - With and without appended_system_prompt
  - With and without permission flags (yolo, auto, confirm, default)
  - With and without extra_args
  - Interactive mode
- Import-time `_CLI_PROJECTED_FIELDS` assertion passes.
- Type check passes.
- Existing tests pass unchanged.

## Phase 3: Port Claude Streaming to Spec

### What changes
- `ClaudeConnection.start()` signature changes: receives `ClaudeLaunchSpec` in addition to `ConnectionConfig` (D12).
- `ClaudeConnection._build_command()` rewritten to project `ClaudeLaunchSpec` to CLI args (same explicit projection pattern as Phase 2).
- `streaming_runner.py` calls `adapter.resolve_launch_spec(run_params, plan.execution.permission_resolver)` and passes the spec to `connection.start()`.
  - **Note (from p1390, Finding 7):** The streaming runner must extract `plan.execution.permission_resolver` and pass it to `resolve_launch_spec()`. The subprocess runner already does this (line 695). The streaming runner currently doesn't, because connection adapters never needed permissions. This is new plumbing.
- `HarnessConnection` protocol in `base.py` updated: `start()` accepts `spec: ResolvedLaunchSpec` parameter. `SpawnParams` parameter removed.
- `SpawnManager.start_spawn()` updated to accept and forward the spec (D12). SpawnManager receives the spec from the streaming runner, which has access to the harness adapter for construction. SpawnManager does NOT construct specs — it's a transport coordinator, not a policy layer.
- `ConnectionConfig.model` stays (D11) — Codex and OpenCode still read it until Phase 4.

### Gaps fixed
- `--effort` now included in streaming command.
- `--agent` now included in streaming command.
- `--append-system-prompt` now included in streaming command.
- `--agents` (native agent payload) now included in streaming command.
- Permission flags now included in streaming command.
- `_CLI_PROJECTED_FIELDS` assertion on streaming projection ensures completeness (D15).

### What doesn't change
- Codex and OpenCode streaming — still using `ConnectionConfig.model` and `SpawnParams`-style hand-picking. They'll be ported in Phase 4. During Phase 3, they receive a default `ResolvedLaunchSpec` (base class) that provides model/prompt/extra_args — enough for them to function without changes. Their harness-specific fields come from `ConnectionConfig` until Phase 4.
- Subprocess path — working as before.

### Verification
- Smoke test: launch a Claude streaming spawn with effort, agent, and skills configured. Verify via stderr.log or process args that all flags appear.
- Unit test: `ClaudeConnection._build_command(spec)` includes all spec fields.
- Claude streaming `session_id` fix: investigate and fix if feasible.

## Phase 4: Port Codex and OpenCode Streaming to Spec

### What changes

**Codex:**
- `CodexConnection.start()` receives `CodexLaunchSpec`.
- `CodexConnection._thread_bootstrap_request()` rewritten to project `CodexLaunchSpec` to JSON-RPC params. Effort mapped to config param if app-server API supports it; otherwise logged as unsupported.
- `CodexConnection._handle_server_request()` respects `spec.permission_config.approval`:
  - `yolo` / `auto` / `default` → accept (current behavior, now explicit).
  - `confirm` → reject with error + log warning (D14). No silent auto-accept.
- `_STREAMING_PROJECTED_FIELDS` assertion on Codex streaming projection.

**OpenCode:**
- `OpenCodeConnection.start()` receives `OpenCodeLaunchSpec`.
- `OpenCodeConnection._create_session()` rewritten to project spec. Model uses already-normalized value (no `opencode-` prefix). Effort included if API supports `variant` param; logged as unsupported otherwise (D16). Fork included if API supports it.
- `_STREAMING_PROJECTED_FIELDS` assertion on OpenCode streaming projection.

**ConnectionConfig cleanup:**
- `ConnectionConfig.model` removed (D11). All adapters now read model from spec.

### Gaps fixed

**Codex:**
- Effort now forwarded via JSON-RPC (or logged as unsupported).
- Approval mode respected (D14).
- Report output path forwarded if API supports it.

**OpenCode:**
- Model prefix already normalized in spec.
- Effort forwarded (or logged as unsupported) (D16).
- Fork forwarded (or logged as unsupported) (D16).

### Verification
- Smoke test: launch Codex streaming with effort and confirm approval mode; launch OpenCode streaming with effort and model override.
- Unit test: `_thread_bootstrap_request(spec)` includes model and effort; `_create_session(spec)` uses normalized model.
- Verify `confirm` mode rejects approvals.

## Phase 5: Runner Preflight Extraction + Parity Tests

### What changes

**Runner preflight:**
- New file: `src/meridian/lib/launch/claude_preflight.py` (named per p1391 suggestion to avoid "misc bucket").
- `_read_parent_claude_permissions()`, `_merge_allowed_tools_flag()`, `_dedupe_nonempty()`, `_split_csv_entries()` extracted from both runners.
- Claude child-CWD resolution (--add-dir, parent permission forwarding) extracted.
- Both `runner.py` and `streaming_runner.py` import from `claude_preflight.py`.

**Parity tests:**
- New test file: `tests/unit/test_launch_spec_parity.py`.
- Layer 1: Import-time completeness assertion (already done in Phase 1).
- Layer 2: Spec-to-command parity tests (verify `build_command()` output matches spec).
- Layer 3: Cross-transport parity tests (verify both transports project the same semantic fields).
- Known asymmetries documented: OpenCode effort/fork unsupported in streaming (D16).

### Verification
- All parity tests pass.
- No duplicated functions remain in the two runners.
- Smoke test: full spawn lifecycle through both subprocess and streaming for each harness.

## Phase Dependencies

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5
```

Phase 5 (runner preflight extraction) can start after Phase 2, but parity tests need Phase 4 complete. The extraction portion can be parallelized with Phase 3/4 since it touches runner code, not adapter code.

## Rollback

Each phase is a separate commit (or commit series). If any phase introduces a regression:
- Phase 0: safe to revert, only adds a field and wires it through.
- Phase 1: safe to revert, only adds new code.
- Phase 2: revert restores old `build_command()` with strategy maps.
- Phase 3: revert restores old streaming Claude path.
- Phase 4: revert restores old streaming Codex/OpenCode paths.
- Phase 5: revert restores duplicated runner functions.
