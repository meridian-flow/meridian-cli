# Decision Log — Streaming Adapter Parity

## D1: Transport-neutral resolved launch spec, not shared flag helper

**What:** Introduce a `ResolvedLaunchSpec` dataclass that each harness adapter produces from `SpawnParams` + `PermissionResolver`. Both `build_command()` and connection adapters consume this spec, never raw `SpawnParams`.

**Why:** The investigators confirmed two codepaths independently translate `SpawnParams` into harness config — the subprocess path via `build_harness_command()` with a completeness guard, and the streaming path with no guard. A "flag helper" (option a) only works for Claude since Codex and OpenCode use different entrypoints (JSON-RPC params, HTTP payloads). A transport-neutral spec is the only abstraction that covers CLI args, JSON-RPC params, and HTTP payloads uniformly.

**Rejected:** (a) Shared CLI flag helper — doesn't generalize to non-CLI transports. (c) Deprecate subprocess path — it's the working reference and the stable path for non-bidirectional spawns.

**Constraint discovered:** Claude's `RunPromptPolicy` intentionally excludes agent body and skills from the prompt text, relying on `--append-system-prompt` and `--agents` CLI flags that the streaming path never emits. This means streaming Claude agents are silently broken — not a theoretical future regression but an active bug.

## D2: Completeness guard extends to streaming via spec construction

**What:** The `ResolvedLaunchSpec` factory method on each adapter receives all `SpawnParams` fields. The existing `_SKIP_FIELDS` / strategy completeness check in `build_harness_command()` stays, but it becomes a check against the resolved spec rather than directly against strategies. The spec factory is the single place that decides how each field maps, and the spec is the contract both transport paths consume.

**Why:** The current guard catches unmapped fields only for the subprocess path. By making spec construction the authoritative mapping point, any new `SpawnParams` field that isn't handled in the spec factory causes a visible failure for both paths, not just subprocess.

**Rejected:** Adding a parallel strategy map for streaming — this duplicates the problem.

## D3: Per-harness spec, not universal flat struct

**What:** `ResolvedLaunchSpec` is a base with common fields (model, effort, session, permissions, env). Each harness extends it with harness-specific fields (e.g., `ClaudeLaunchSpec` adds `appended_system_prompt`, `agents_payload`; `CodexLaunchSpec` adds `sandbox_mode`, `report_output_path`).

**Why:** The three harnesses have genuinely different transport semantics. Claude uses `--append-system-prompt` as a string flag. Codex uses JSON-RPC params with `model` and `threadId`. OpenCode uses HTTP POST with `model`/`modelID`. A universal flat struct forces all harness-specific fields into a shared namespace and pushes "is this field relevant?" checks into every consumer. Per-harness specs make each consumer's input explicit and typed.

**Constraint:** The base spec must carry everything the common `build_harness_command()` function needs, plus permission flags, so the subprocess path can be reimplemented on top without behavior change.

## D4: Effort normalization lives in the spec factory, not the transport layer

**What:** Each harness's effort mapping (e.g., "xhigh" → "max" for Claude, "xhigh" → `model_reasoning_effort="xhigh"` for Codex) happens during spec construction, not during CLI flag generation or JSON-RPC payload building.

**Why:** Effort normalization is harness-specific semantic knowledge, not transport encoding. If it lives in the transport layer, both transports must know the mapping. If it lives in the spec, the transport layer just emits the pre-normalized value.

## D5: Runner-level duplication resolved by extracting shared preflight

**What:** `_read_parent_claude_permissions()` and `_merge_allowed_tools_flag()` move to a shared module (e.g., `launch/preflight.py`). The Claude-specific child CWD setup (symlink session, --add-dir forwarding) also moves there. Both `runner.py` and `streaming_runner.py` call the shared functions.

**Why:** The investigators flagged this as medium-severity: even if adapter-level config is unified, the two runners can still drift on launch preflight. The fix is straightforward extraction with no behavior change.

## D6: Connection adapters become thin transport projections

**What:** `ClaudeConnection._build_command()` is replaced by a method that takes a `ClaudeLaunchSpec` and projects it to CLI args. `CodexConnection._thread_bootstrap_request()` takes a `CodexLaunchSpec` and projects to JSON-RPC params. `OpenCodeConnection._create_session()` takes an `OpenCodeLaunchSpec` and projects to HTTP payload.

**Why:** This is the key structural change. Currently each connection adapter reads raw `SpawnParams` and `ConnectionConfig`, then independently decides which fields to include. After the change, the adapter receives a fully-resolved spec where every field has already been mapped by the harness adapter's factory. The transport projection is a mechanical translation with no semantic decisions.

## D7: Approval-mode handling in Codex streaming

**What:** The current Codex streaming adapter auto-accepts all approval requests (`requestApproval` → `accept`). The resolved spec will carry the configured approval mode, and the Codex connection adapter will respect it: `confirm` → queue for user approval (or reject in non-interactive), `default` → harness decides, `auto` → accept, `yolo` → accept.

**Why:** Investigator p1386 flagged this as a behavioral divergence, not just a missing flag. The subprocess path uses `--full-auto`, `--ask-for-approval`, etc. The streaming path ignores the configured mode entirely.

## D8: Migration is incremental, subprocess path stays working throughout

**What:** The migration proceeds in 6 phases: (0) fix effort plumbing upstream, (1) introduce spec + factory, (2) reimplement subprocess `build_command()` on top, (3) port Claude streaming, (4) port Codex and OpenCode streaming, (5) add parity tests + runner preflight extraction. Each phase is independently verifiable.

**Why:** The subprocess path is the stable reference. Breaking it during migration would make both paths unreliable simultaneously. Each phase has a clear verification: phase 2 must produce identical CLI commands to the current implementation.

## D9: permission_flags is CLI-shaped — replace with semantic permission object

**What:** The `ResolvedLaunchSpec` carries `PermissionConfig` (the semantic permission object) and `PermissionResolver` reference, not pre-resolved CLI flags. Each transport projection calls `perms.resolve_flags(harness_id)` for CLI, or maps `PermissionConfig.approval` to JSON-RPC approval-mode decisions, or maps to env overrides for OpenCode.

**Why:** The refactor reviewer (p1391) correctly identified that `permission_flags: tuple[str, ...]` is a CLI artifact, not transport-neutral. Codex streaming handles permissions via JSON-RPC approval decisions, not CLI flags. OpenCode handles permissions via `OPENCODE_PERMISSION` env, not CLI flags. Carrying pre-resolved CLI flags forces streaming transports to either ignore them (current bug) or parse them (wrong abstraction level).

**Rejected:** Keeping `permission_flags` in spec — forces CLI-shaped thinking into non-CLI transports.

## D10: Retire strategy map machinery, spec becomes the single policy layer

**What:** After Phase 2, the strategy map (`StrategyMap`, `FlagStrategy`, `FlagEffect`, `build_harness_command()`) is retired. `build_command()` becomes explicit code that projects spec fields to CLI args. The import-time completeness assertion on the spec factory replaces the strategy completeness guard.

**Why:** The refactor reviewer (p1391) flagged that keeping both spec normalization and strategy mapping creates two policy layers. The spec already handles completeness and normalization. The strategy layer's only remaining value is CLI arg ordering, which is trivially handled by explicit code. Two policy layers increase cognitive load and create "where does this mapping live?" ambiguity.

**Constraint:** The Phase 2 verification (byte-identical CLI output) must hold. The explicit projection code must reproduce the same arg ordering.

## D11: ConnectionConfig.model removal deferred to Phase 4

**What:** In Phase 3 (Claude streaming port), `ConnectionConfig.model` stays. Claude's connection adapter reads model from the spec but the field remains in `ConnectionConfig` for Codex and OpenCode. Removal happens in Phase 4 when all adapters are ported.

**Why:** The design alignment reviewer (p1390, Finding 2) correctly identified that removing `model` from `ConnectionConfig` in Phase 3 would break the un-ported Codex and OpenCode adapters, violating phase independence.

## D12: HarnessConnection.start() protocol change is in-scope

**What:** The design explicitly acknowledges that `HarnessConnection.start()` signature changes from `(config, params)` to `(config, spec)`. This is a protocol change. All callers are mapped: `SpawnManager.start_spawn()`, `run_streaming_spawn()`, and any test fixtures.

**Why:** The design alignment reviewer (p1390, Finding 1) caught a contradiction: the overview said protocol changes were out of scope, but Phase 3 requires one.

## D13: Effort is missing from PreparedSpawnPlan — upstream fix required

**What:** `PreparedSpawnPlan` lacks an `effort` field. The runners reconstruct `SpawnParams` from the plan and silently drop effort. This is an upstream bug that affects BOTH paths, not just streaming. Phase 0 adds `effort` to `PreparedSpawnPlan` and wires it through to `SpawnParams` construction in both runners.

**Why:** The correctness reviewer (p1389, Finding 1) discovered that effort isn't actually reaching either runner path today. The gap was attributed to streaming adapters, but it's an upstream plumbing issue. Fixing it at the adapter layer alone would leave the bug intact.

## D14: Codex streaming confirm-mode rejects approvals, not auto-accepts

**What:** When `confirm` approval mode is configured and the streaming connection has no interactive channel, approval requests are rejected (not silently auto-accepted). The Codex connection logs a warning explaining that confirm mode requires an interactive session.

**Why:** The design alignment reviewer (p1390, Finding 6) caught a contradiction in the design. Auto-accepting in confirm mode defeats the user's intent. Rejecting is the safe default — it surfaces the misconfiguration rather than silently granting permissions.

## D15: Spec → transport projection gets a machine-checkable completeness guard

**What:** Each transport projection function includes a `_PROJECTED_FIELDS` frozenset that must match all non-default fields of the corresponding spec subclass. An import-time or test-time assertion catches fields added to the spec but not to the projection.

**Why:** The design alignment reviewer (p1390, Finding 3) identified that the completeness guard only covers SpawnParams → spec, not spec → transport. Without a projection guard, a new spec field can be added and projected by the subprocess path but forgotten in the streaming projection.

## D16: OpenCode parity contract narrowed for unsupported API features

**What:** The parity contract acknowledges that some features may not be supported by the OpenCode HTTP API (effort, fork). For these, the spec carries the resolved value, the streaming projection logs a debug-level warning noting the feature is unsupported, and the subprocess path still applies it. The parity test marks these as known asymmetries rather than failures.

**Why:** The correctness reviewer (p1389, Finding 3) correctly identified that claiming full parity when the transport API doesn't support certain features is overclaiming. Honest documentation of asymmetries is more useful than false parity claims.

## D17: Implementation plan splits per-harness streaming ports and reserves final cleanup for shared runner work

**What:** The execution plan uses seven phases (0-6), not the draft six-phase sequence. Claude, Codex, and OpenCode streaming ports each get their own implementation phase. The final phase owns the shared Claude runner-preflight extraction, `ConnectionConfig.model` removal, and the full parity/smoke matrix.

**Why:** The planning rules for integration work are stricter than the migration sketch: one external protocol target per phase is easier to verify, review, and roll back. Splitting Codex and OpenCode prevents a single large integration phase from hiding which transport regressed. Holding the shared runner cleanup until the end also reduces merge pressure while `HarnessConnection.start()` and the streaming runner are still changing.

**Rejected:** Keeping Codex and OpenCode in one combined integration phase, or extracting runner preflight earlier into a parallel branch while the streaming protocol contract is still moving.

## D18: Use `claude_preflight.py` rather than a generic `preflight.py`

**What:** The extracted runner helper module should land as `src/meridian/lib/launch/claude_preflight.py`.

**Why:** The duplicated logic is Claude-specific: parent permission forwarding, `--add-dir` propagation, and child session accessibility. Naming the module after the harness keeps the scope obvious and avoids creating a vague launch "misc bucket."

**Rejected:** `src/meridian/lib/launch/preflight.py`, which obscures that the helpers are Claude-only.

## D17: Final Review Triage

**Context:** 4 reviewers across gpt-5.4, gpt-5.2, opus, and sonnet reviewed the full change set.

### Fix now:
- **run_streaming_spawn() + streaming_serve.py + server.py bypass adapter factories**: These entrypoints construct generic `ResolvedLaunchSpec` instead of calling `adapter.resolve_launch_spec()`. This drops harness-specific normalization (OpenCode model prefix stripping, agent/skills forwarding, Claude effort normalization). The gpt-5.4 and gpt-5.2 reviewers independently identified this as the same behavioral regression. This is the main fix.

- **MCP tools in completeness guard**: `_SPEC_HANDLED_FIELDS` claims `mcp_tools` is "handled" but `ResolvedLaunchSpec` has no MCP field. The field is handled in the env builder, not the spec. The guard should be truthful about what "handled" means. Minor fix — either add a comment or drop from the set and add a separate assertion.

### Defer to follow-up:
- **resolve_permission_config Protocol gap** (sonnet finding #1): Valid observation that PermissionResolver should expose a permission_config property. But adding a Protocol property affects all resolver implementations and is scope creep for this refactor. The current defensive approach works correctly.

- **Per-harness extractors in common.py** (sonnet finding #2): Valid that report extraction functions belong in adapter modules. Separate refactor — not part of the launch spec migration.

- **Runner module size** (sonnet finding #3): Pre-existing issue, partially improved by claude_preflight extraction. Further decomposition is follow-up work.

- **Duplicate constants, naming conventions, assert under -O** (sonnet findings #4-7): All valid low-severity findings. Not blocking and can be addressed incrementally.

- **OpenCode debug vs warning level** (gpt-5.2 minor): Design decision D16 explicitly chose debug level. This is documented behavior, not a bug.

**Reasoning:** The refactor's scope is launch spec parity. Structural improvements to unrelated modules (common.py, runner decomposition, Protocol hierarchy) are better served by separate targeted refactors than by scope expansion here.
