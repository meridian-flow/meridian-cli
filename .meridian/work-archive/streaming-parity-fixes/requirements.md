# Streaming Parity — Design the Correct Shape

## Problem

The streaming adapter parity refactor (v1) landed but a post-implementation multi-model review (p1411, 4 reviewers across gpt-5.4/gpt-5.2/opus/sonnet) converged on four HIGH findings and nine MEDIUM findings. The findings are not individual bugs — they reveal that the refactor picked the right direction (transport-neutral spec) but stopped short of committing to it. Silent fallbacks, missing guards, and split responsibilities leave booby traps that the parity tests don't catch.

**This work is NOT "patch the findings."** We are designing the correct shape from scratch, using everything the v1 attempt taught us. If the correct shape happens to look like v1 with patches, fine. If it doesn't, we re-shape.

## What v1 Got Right (preserve)

- ResolvedLaunchSpec as a transport-neutral resolved launch spec
- Strategy map retirement (`FlagEffect`, `FlagStrategy`, `StrategyMap`, `build_harness_command` deleted cleanly)
- Subprocess `build_command()` reimplemented on top of the spec (byte-identical)
- Factory method pattern (`adapter.resolve_launch_spec(params, perms)`)
- `_SPEC_HANDLED_FIELDS` completeness guard on the factory side
- `claude_preflight.py` extracted as shared helper
- `ConnectionConfig.model` removed — adapters read model from spec

## What v1 Got Wrong (re-shape)

### H1 — Codex streaming silently drops sandbox/approval flags
`CodexLaunchSpec.sandbox_mode` and `.approval_mode` exist on the data model. `codex_ws.py` never projects them to the wire. `approval_mode` is only read to gate confirm-mode rejection; everything else collapses to accept-all. `sandbox_mode` is dead code.

**Impact:** Security downgrade. User configures `sandbox=read-only`, streaming ignores it, Codex runs with default sandbox.

### H2 — Duplicate `--allowedTools` in Claude streaming under CLAUDECODE
Under `CLAUDECODE=1`, `streaming_runner.py` merges parent allow list into `--allowedTools` via `spec.extra_args`. `claude_ws.py` also injects `--allowedTools` via `permission_resolver.resolve_flags`. No deduplication. Subprocess runner dedupes; streaming doesn't.

### H3 — `cast("PermissionResolver", None)` at 2 entrypoints
`streaming_runner.py:457` and `server.py:203` lie to the type system. `resolve_permission_config(None)` silently returns a default via `getattr` fallback. Result: Claude streaming emits zero permission flags, Codex collapses to accept-all, OpenCode env overrides become empty. Two entrypoints are a type-safety booby trap.

### H4 — D15 projection-side completeness guard not implemented
The design promised `_PROJECTED_FIELDS` frozensets on each transport projection so that "spec field added, projection forgot it" becomes an import-time assertion. Grep returns zero matches. The construction-side guard exists; the projection-side guard doesn't. **Every HIGH finding in this review is exactly what D15 was supposed to prevent.**

### M1-M2 — Silent isinstance branching + base class fallback
Every connection adapter does:
```python
if isinstance(spec, ClaudeLaunchSpec):
    if spec.agent_name: ...
```
Combined with `spawn_manager.py:99`: `resolved_spec = spec or ResolvedLaunchSpec(prompt=config.prompt)` — a fallback that constructs a bare base spec. If a caller omits the spec, the connection silently skips every harness-specific field. Plus `BaseSubprocessHarness.resolve_launch_spec` returns a generic base by default.

The base class fallbacks defeat the factory pattern.

### M3 — Claude subprocess vs streaming CLI arg ordering differs
Subprocess: `perm_flags → extra_args → --append-system-prompt → --agents → --resume`
Streaming: `--append-system-prompt → --agents → --resume → perm_flags → extra_args`

Interacts with H2 — duplicate-flag last-wins semantics depend on ordering.

### M4 — OpenCode streaming skills double-injection risk
`OpenCodeAdapter.run_prompt_policy()` returns `include_skills=True` so runner inlines skill content into prompt. Streaming ALSO sends `payload["skills"] = list(spec.skills)`. If OpenCode HTTP API honors the `skills` field server-side, content appears twice.

### M5 — `report_output_path` leaks into base `ResolvedLaunchSpec`
`report_output_path` is Codex-only but lives on the base class. Three subclasses carry a field only one uses.

### M6 — Duplicate constants between runners (escalated from LOW)
`runner.py` (958 lines) and `streaming_runner.py` (1189 lines) both carry duplicate constants and preflight helpers. D17 deferred this; landed code made it materially worse because both monolithic runners kept their own copies instead of sharing.

### M7-M9 — Missing debug log for passthrough args; OpenCodeConnection not inheriting HarnessConnection; Codex confirm-mode rejection not surfaced as event

## Design Questions to Answer

1. **Should the spec be type-enforced end-to-end?** v1's base-class fallback is the leak. Should each connection adapter require its specific spec subclass (`ClaudeConnection.start(config, spec: ClaudeLaunchSpec)`) so the isinstance check is gone and the type system enforces it? What's the cost at the dispatch site?

2. **What's the right completeness guard?** D15 was asserts on frozensets. That's one option. Another: make each transport projection a pure function that exhaustively matches every spec field (match statement) so the type checker catches drift. Another: generate projections from spec metadata.

3. **Where does the PermissionResolver live?** Two entrypoints cast None because the resolver isn't available at those call sites. Should the resolver be constructed earlier and threaded through? Should it be a lazy default with a loud warning? Should permission resolution happen inside the factory, not at call time?

4. **What do we extract from the two runners?** The post-impl review surfaced that both runners are >950 lines with duplicated constants and helpers. A shared `launch/common.py` or is there a deeper extraction opportunity (shared preflight, shared post-flight, shared finalization)?

5. **How do we handle CLI arg ordering?** Subprocess and streaming diverge on flag ordering. Is there a canonical order that both paths share, and if so, is it part of the spec projection or part of the transport?

6. **Can we make base class fallbacks impossible?** Abstract method with `raise NotImplementedError`? Protocol-only with no default implementation? Something else?

## Success Criteria

- Every SpawnParams field reaches every harness correctly through both paths
- Adding a new field to the spec fails visibly if either path doesn't map it — at type-check time or import time, not at runtime
- Zero silent fallbacks — a caller that misuses the API gets a loud error, not wrong behavior
- Permission resolution reaches every entrypoint (no None casts)
- Duplicate runner growth reversed — one shared place for shared behavior
- Post-impl multi-model review finds no structural findings

## Source Material

- Post-impl review report: .meridian/spawns/p1411/report.md (4 reviewers, full finding list)
- Individual reviewer reports: p1417 (gpt-5.2), p1418 (opus), p1419 (sonnet refactor), p1416 (gpt-5.4 design alignment)
- v1 design: .meridian/work-archive/streaming-adapter-parity/design/
- v1 decisions: .meridian/work-archive/streaming-adapter-parity/decisions.md
