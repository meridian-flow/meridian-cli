# Post-Implementation Review — Streaming Adapter Parity Refactor

**Scope:** 8 commits (58470a2..2d4d60a), 31 files, +1565/-679
**Reviewers:** 4 reviewers across 4 model families + 4 explorers for data gathering
**Spawn mode:** All child spawns launched via `uv run meridian spawn` (exercised the fixed streaming pipeline end-to-end)

## Verdict

**Request changes.** The refactor achieves its headline goal — Claude streaming now emits `--append-system-prompt`, `--agents`, and `--agent` (D1 bug fixed), and the strategy-map machinery is cleanly retired (D10). Parity tests confirm subprocess/streaming alignment for Claude's semantic fields. However, three independent reviewers on three different model families converged on the same structural defect: **the D15-promised projection-side completeness guard was never implemented**, and the resulting gaps include one security-relevant finding in Codex streaming and one command-line correctness regression in Claude streaming under `CLAUDECODE`.

Four HIGH findings have independent corroboration across reviewers. They should block merge until addressed.

## Build Health

- `uv run pyright` — **0 errors, 0 warnings, 0 informations**
- `uv run ruff check .` — **clean**
- Targeted unit tests (48 tests) — **all passing in 1.17s**

## What the Refactor Got Right

| Area | Status |
|---|---|
| D1 — Claude streaming emits append-system-prompt / agents / agent | Fixed (verified in `claude_ws.py:336-344`) |
| D4 — Effort normalization in factory | Consistent across Claude subprocess/streaming |
| D9 — Semantic PermissionConfig (not CLI flags) | Honored in spec construction |
| D10 — Strategy map retirement | **Clean.** Grep confirms `StrategyMap`, `FlagStrategy`, `FlagEffect`, `build_harness_command` fully deleted; no stale imports or callers |
| D11 — ConnectionConfig.model removal | Clean (only Pydantic `.model_copy()` hits remain) |
| D12 — `HarnessConnection.start(config, spec)` protocol | Consistent across all 3 connection adapters |
| D13 — Effort in PreparedSpawnPlan | Honored |
| D14 — Codex confirm-mode rejection | Works (with F6 caveat below) |
| D18 — `claude_preflight.py` naming | Correct scope |
| Deletion discipline | Clean — no dead imports, no half-migrated callers |
| Subprocess/streaming parity for Claude semantic fields | Verified by parity tests |

## HIGH Findings (Blocking)

### H1 · Codex streaming silently drops the entire permission surface
**Corroborated by:** p1417 (gpt-5.2, MED) + p1418 (opus, HIGH F1) + p1419 (sonnet refactor)

`CodexLaunchSpec.sandbox_mode` and `.approval_mode` are populated by `CodexAdapter.resolve_launch_spec()` from `PermissionConfig.sandbox` / `.approval`, but `codex_ws.py` never reads them in `start()` or `_thread_bootstrap_request()`. The subprocess path injects these via `permission_resolver.resolve_flags(HarnessId.CODEX)` (flags like `--sandbox workspace-write`, `--full-auto`, `-c approval_policy=...`). Streaming Codex reads `approval_mode` **only** to gate `confirm`-mode rejection in the `/requestApproval` handler — `default`/`auto`/`yolo` all collapse to accept-all, and `sandbox_mode` is genuinely dead.

**Impact:** A user configuring `sandbox=read-only` and launching via streaming gets Codex's default sandbox. **Silent security downgrade.** The Codex app-server supports `-c` config overrides and CLI flags that could carry these settings.

**Fix:** Either project `spec.sandbox_mode` / `spec.approval_mode` into `codex app-server` CLI args or `-c` overrides, or refuse to launch streaming Codex with non-default sandbox.

### H2 · Duplicate `--allowedTools` flags in streaming Claude under `CLAUDECODE`
**Corroborated by:** p1417 (gpt-5.2, HIGH, primary finding)

Under `CLAUDECODE=1`, `streaming_runner.py:742` builds passthrough args that merge the parent `allow` list into `--allowedTools` and passes that into `spec.extra_args`. Meanwhile `claude_ws.py:327-358` also projects `spec.permission_resolver.resolve_flags(HarnessId.CLAUDE)` — which itself injects `--allowedTools` for explicit tool allowlists — and then appends `spec.extra_args` without deduplication.

The subprocess runner at `runner.py:640` dedupes `--allowedTools` across the whole command. **The streaming path does not.** Two `--allowedTools` flags can appear in the same streaming command. Claude CLI's behavior under duplicate flags is undefined (last-wins silently drops part of the allowlist, or errors). Pre-refactor `ClaudeConnection._build_command` only used `config.model + params.extra_args` and never injected permission flags, so no collision was possible.

**Fix:** Normalize `--allowedTools` in `claude_ws._build_command` by collapsing occurrences into a single deduped union (mirroring subprocess behavior). Add a targeted test with `ExplicitToolsResolver` + runner-forwarded `--allowedTools` in extra_args, asserting exactly one merged flag.

### H3 · `run_streaming_spawn` and REST server pass `None` as `PermissionResolver`
**Corroborated by:** p1417 (gpt-5.2, MED) + p1418 (opus, HIGH F3) + p1419 (sonnet, Finding 4.3)

`streaming_runner.py:457`: `adapter.resolve_launch_spec(params, cast("PermissionResolver", None))`
`server.py:203`: same pattern

The `cast` lies to the type system. `resolve_permission_config(None)` survives via its `getattr` fallback chain, silently returning a default `PermissionConfig()`. Result: through these entrypoints, Claude streaming emits zero permission flags, Codex collapses to accept-all, OpenCode env overrides become empty.

The main production path at `streaming_runner.py:785` is fine, but these two entrypoints are a booby trap for future callers and already actively broken for the REST server path.

**Fix:** Change parameter type to honest `PermissionResolver | None`, construct a no-op resolver, or accept a `PermissionConfig`/`PermissionResolver` in the request path. Add a loud warning log at any entrypoint that bypasses permission resolution.

### H4 · D15's projection-side completeness guard is not implemented
**Corroborated by:** p1413 (explorer, primary finding) + p1418 (opus, HIGH F4) + p1419 (sonnet, Finding 3.1)

D15 committed to `_PROJECTED_FIELDS` frozensets on each transport projection so that "spec field added, projection forgot it" becomes an import-time assertion. Grep across the tree returns zero matches for `_PROJECTED_FIELDS`. The construction-side guard (`_SPEC_HANDLED_FIELDS` in `launch_spec.py:70-93`) is in place, but nothing catches the symmetric class of bug.

**Every HIGH/MEDIUM asymmetry in this review is exactly what D15 was supposed to prevent.** H1, H2, and F5 below are all the same failure mode: a spec field that exists in the data model but never reaches the wire.

**Fix:** Add one assertion per projection file validating `set(SpecSubclass.model_fields) - _IGNORED_FIELDS == _PROJECTED_FIELDS` with `_IGNORED_FIELDS` carrying documented drops. This is a small amount of code and catches the entire class of regression surfaced by this review.

## MEDIUM Findings

### M1 · Silent `isinstance(spec, XxxLaunchSpec)` branching in all 3 connection adapters
**Corroborated by:** p1418 (opus) + p1419 (sonnet, Finding 3.3)

Every streaming connection silently skips harness-specific fields when the spec is a generic `ResolvedLaunchSpec`:

```python
# claude_ws.py:336
if isinstance(spec, ClaudeLaunchSpec):
    if spec.agent_name: ...
    if spec.appended_system_prompt: ...
    if spec.agents_payload: ...
```

Combined with `spawn_manager.py:99` `resolved_spec = spec or ResolvedLaunchSpec(prompt=config.prompt)` — a fallback that constructs a bare base spec when none is provided — this creates a two-step silent failure mode. Any caller omitting the spec silently gets base-class behavior, and the isinstance branch in the connection quietly skips every harness-specific field.

**Fix:** Either raise on generic spec in each connection's `_build_command`/`_thread_bootstrap_request` (fail loud), or remove the `spawn_manager.py:99` fallback and make `spec` required. The fallback is redundant with the factory pattern and defeats its purpose.

### M2 · `BaseSubprocessHarness.resolve_launch_spec` default returns generic base spec
**Corroborated by:** p1418 (opus, F8)

`adapter.py:234-252` returns a generic `ResolvedLaunchSpec`. A new adapter forgetting to override silently drops every harness-specific field. All three current adapters override, but this is the exact class of bug D1/D2 exist to eliminate.

**Fix:** `raise NotImplementedError` instead of a default implementation.

### M3 · Claude subprocess vs streaming CLI arg ordering differs
**Corroborated by:** p1418 (opus, F5)

Subprocess: `perm_flags → extra_args → --append-system-prompt → --agents → --resume`
Streaming: `--append-system-prompt → --agents → --resume → perm_flags → extra_args`

If a user passes `--append-system-prompt` in extra_args, subprocess lets Meridian's value override the user's; streaming does the opposite. Parity tests only assert presence, not ordering. Interacts with H2 — duplicate-flag last-wins semantics depend on ordering.

**Fix:** Align ordering or extract a shared helper; extend parity tests to assert the ordering invariant.

### M4 · OpenCode streaming risks double-injecting skills
**Corroborated by:** p1418 (opus, F2 HIGH, reclassified here as MEDIUM pending OpenCode HTTP semantics)

`OpenCodeAdapter.run_prompt_policy()` returns `include_skills=True` by default, so the runner inlines skill content into the prompt for both transports. Streaming additionally sends `payload["skills"] = list(spec.skills)` in `opencode_http.py:340-344`. If OpenCode's HTTP API honors the `skills` field server-side, content appears twice.

**Fix:** Verify OpenCode HTTP API semantics first, then pick one authoritative channel — either `run_prompt_policy(include_skills=False)` for streaming and rely on HTTP, or drop the HTTP `skills` field and rely on prompt inlining.

### M5 · `report_output_path` leaks into base `ResolvedLaunchSpec`
**Corroborated by:** p1419 (sonnet, Finding 3.2)

`report_output_path` is Codex-only (subprocess `-o path`) but lives on the base class. Three subclasses now carry a field only one uses.

**Fix:** Move to `CodexLaunchSpec`. The projection only reads it inside a `if isinstance(..., CodexLaunchSpec)` branch anyway.

### M6 · Duplicate constants materially worse post-refactor
**Corroborated by:** p1419 (sonnet, Finding 5.1)

`runner.py` (958 lines) and `streaming_runner.py` (1189 lines) now both carry duplicate constants and preflight helpers. D17 deferred this as LOW; landed code made it materially worse because both monolithic runners kept their own copies instead of sharing. Should escalate from LOW to MEDIUM.

**Fix:** Extract shared constants to `launch/common.py` or similar.

### M7 · Passthrough-args debug warning promised by design is missing
**Corroborated by:** p1418 (opus, F10)

`transport-projections.md` promised a debug warning when extra_args are forwarded to `codex app-server` or `opencode serve`. No such warning exists in `codex_ws.py:216-227` or `opencode_http.py:287-301`. Invalid args fail at server startup with opaque errors.

**Fix:** Debug-level log when `spec.extra_args` is non-empty at those entrypoints.

### M8 · OpenCodeConnection does not inherit from `HarnessConnection`
**Corroborated by:** p1418 (opus, F7)

`opencode_http.py:40` is `class OpenCodeConnection:` while Claude/Codex inherit. `HarnessConnection` is `runtime_checkable` so structural checks pass, but nothing statically enforces the Protocol signature. Future Protocol changes will silently break OpenCode.

**Fix:** `class OpenCodeConnection(HarnessConnection):`.

### M9 · Codex streaming confirm-mode rejection not surfaced as event
**Corroborated by:** p1418 (opus, F6)

D14 said confirm-mode rejection should be surfaced. `codex_ws.py:611-628` logs a warning and returns a JSON-RPC error to the server, but never puts a `HarnessEvent` on the event queue. Callers see only downstream turn failures with no direct signal that Meridian rejected an approval.

**Fix:** Emit `HarnessEvent("warning/approvalRejected", {"reason":"confirm_mode","method":method})` before returning the error.

## LOW Findings

- **L1** · `_SPEC_HANDLED_FIELDS` guard uses `assert` — stripped under `python -O`. (p1417, p1419)
- **L2** · `_SPEC_HANDLED_FIELDS` lists `mcp_tools` as handled but it's handled in `env.py`, not the spec. Noted in D17 triage, still there. (p1418 F11, p1419)
- **L3** · `agent_name` duplicated on both `ClaudeLaunchSpec` and `OpenCodeLaunchSpec`. (p1419)
- **L4** · `dedupe_nonempty` and `split_csv_entries` in `claude_preflight.py` are generic utilities that don't belong in a Claude-specific module. (p1419, Finding 2.3)
- **L5** · `common.py` per-harness extractors deferred in D17 still valid — per-harness logic in a "common" module is a structural smell. (p1419, Finding 2.1)
- **L6** · `cast("PermissionResolver", None)` obscures intent at two call sites. (p1419, Finding 4.3 — also drives H3)
- **L7** · Streaming connections silently ignore `spec.interactive`. Semantically correct (streaming is never interactive) but a caller mistake passes silently. (p1418 F9)
- **L8** · Claude streaming hardcodes base command literal `["claude", "-p", ...]`. If Claude adds a required flag, only subprocess picks it up. (p1418 F12)
- **L9** · OpenCode streaming `env_overrides` round-trip (`OPENCODE_PERMISSION`) is implicit and has no direct parity test. (p1418 F13)
- **L10** · Double effort normalization in `claude.py:266-269` — once in the factory, once again in `build_command`. (p1419, Finding 5.2)
- **L11** · `runner.py` (958 lines) and `streaming_runner.py` (1189 lines) both exceed the 500-line structural-health threshold. D17 deferred; worth scheduling as follow-up. (p1419)

## Deferred Items from D17 — Status

| Deferred item | Current status |
|---|---|
| `resolve_permission_config` Protocol gap | Still valid; `getattr` fallback chain works but is type-unsafe |
| Per-harness extractors in `common.py` | Still valid (L5) |
| Runner module size | **Materially worse** — dual duplication across two files (M6) |
| Duplicate constants | **Materially worse** — escalate to MEDIUM (M6) |
| Naming conventions | Mostly fine; `report_output_path` leak is the main naming issue |
| Assert under `-O` | Still valid (L1) |
| OpenCode debug vs warning | Addressed via D16 documentation |

## Convergence Across Reviewers

Three independent model families converged on the same root cause:

| Finding | p1417 (gpt-5.2) | p1418 (opus) | p1419 (sonnet refactor) |
|---|---|---|---|
| Codex sandbox/approval dropped in streaming | MED #2 | HIGH F1 | Flagged |
| D15 guard missing | Implicit | HIGH F4 | MED 3.1 |
| `cast(PermissionResolver, None)` | MED #3 | HIGH F3 | 4.3 |
| Duplicate `--allowedTools` in Claude streaming | **HIGH #1** | — | — |
| `assert` under `-O` | LOW #4 | — | Deferred |
| Silent isinstance branching | — | Implicit | MED 3.3 |
| OpenCode skills double-injection | — | HIGH F2 | — |

Cross-reviewer agreement on H1, H3, and H4 gives high confidence these are real. H2 (duplicate `--allowedTools`) is single-reviewer but inspectably correct from the code, and its interaction with M3 (ordering) makes it particularly dangerous.

## Recommended Actions

**Before merge / in this cycle:**
1. **H1** — Wire Codex streaming permission projection (sandbox_mode + approval_mode). Security-relevant.
2. **H2** — Dedupe `--allowedTools` in `claude_ws._build_command`; add regression test.
3. **H3** — Fix `cast("PermissionResolver", None)` in `streaming_runner.py:457` and `server.py:203`.
4. **H4** — Implement `_PROJECTED_FIELDS` completeness guards per D15. This is cheap and prevents the entire class of regression.
5. **M1** — Decide: raise on generic spec in connection `_build_command`, or remove the `spawn_manager.py:99` fallback. The current state is silent failure.
6. **M2** — `raise NotImplementedError` in `BaseSubprocessHarness.resolve_launch_spec`.

**Non-blocking but worth this cycle:**
- M3 (arg ordering), M4 (OpenCode skills — needs API investigation first), M7 (passthrough debug log), M8 (`HarnessConnection` inheritance).

**Follow-up work:**
- M5, M6 (escalate duplicate-constants cleanup), M9, all LOW items.
- L11: runner.py / streaming_runner.py decomposition as a scheduled refactor.

## Structural Health Assessment

The refactor **does** leave the codebase easier to navigate in its intended dimension — the ResolvedLaunchSpec contract is explicit, the strategy-map indirection is gone, and per-harness factories are discoverable. However, the structural gain is partially offset by:

1. Duplicate runner growth (M6) — the two runners are now more similar in implementation but no code is shared between them.
2. Silent failure surfaces (M1, M2) — the generic-base-class fallbacks defeat the factory pattern they were built to support.
3. The D15 guard gap (H4) — the construction-side guard is half the story; without the projection-side guard, the refactor's core invariant ("one spec, consistent projection") is unenforced.

The refactor lands mostly where it intended to, but leaves three to four concrete booby traps that reviewers caught but the parity tests did not. Addressing H1-H4 and M1-M2 would bring the structural health up to what D1-D18 described on paper.
