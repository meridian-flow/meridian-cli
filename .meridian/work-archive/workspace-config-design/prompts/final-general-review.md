# Final General Review — Workspace-Config Design

You are the **general reviewer** on a final pass before the design hands off to `@impl-orchestrator`. Your focus is whether this design is still a good design given the current state of the codebase and overall project posture.

This design package was drafted against probes captured on 2026-04-14. The codebase has evolved since then. Your most important job is to verify that the files, modules, and behaviors the design *touches* still look like what the design claims — or to flag where they've drifted in a way that would invalidate the design.

The design has no real users today (single-dev project per `CLAUDE.md`: "No real users, no real user data. No backwards compatibility needed"). Don't recommend migration scaffolding or backward-compat. Recommend things that make the design *work* or *not work* against the current repo state.

## Files to load

Design package:

- `.meridian/work/workspace-config-design/requirements.md`
- `.meridian/work/workspace-config-design/decisions.md`
- `.meridian/work/workspace-config-design/design/feasibility.md`
- `.meridian/work/workspace-config-design/design/refactors.md`
- `.meridian/work/workspace-config-design/design/spec/*.md`
- `.meridian/work/workspace-config-design/design/architecture/*.md`
- `.meridian/work/workspace-config-design/probe-evidence/probes.md`
- `.meridian/work/workspace-config-design/opencode-probe-findings.md`

Explore the source tree as needed:
- `src/meridian/lib/state/paths.py`
- `src/meridian/lib/config/settings.py`
- `src/meridian/lib/ops/config.py`
- `src/meridian/lib/ops/runtime.py`
- `src/meridian/lib/ops/diag.py`
- `src/meridian/lib/launch/context.py`
- `src/meridian/lib/harness/adapter.py`
- `src/meridian/lib/harness/claude_preflight.py`
- `src/meridian/lib/harness/projections/*`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `src/meridian/lib/ops/spawn/execute.py`

You have grep and read tools. Use them to sample the specific seams the design claims.

## Codepath freshness checks

Design claims → verify in current source. Flag drift that would break the implementation plan.

### CP1: `execute.py:462` dispatch to streaming
Design D16 claims all three harnesses set `supports_bidirectional=True`, so `execute_with_streaming` is always hit and `execute_with_finalization` is dead code. `env_additions` reach the child identically either way via `asyncio.create_subprocess_exec(..., env=env)`.

Verify:
- `supports_bidirectional` is set on all three harness adapters.
- Dispatch logic in `execute.py` (around line 462 or current location) still routes based on `supports_bidirectional`.
- Streaming paths still spawn via `create_subprocess_exec` with an `env` param.

### CP2: Claude preflight `--add-dir` emission
Design A04 claims Claude's preflight at `claude_preflight.py:120-166` currently owns workspace-root emission, and the refactor moves it out so preflight keeps only `execution_cwd` + parent-forwarded `additionalDirectories`.

Verify:
- Current Claude preflight still owns the workspace-root emission layer described.
- No third party has already moved this or changed the order of emission.

### CP3: Codex subprocess projection tail append
Design A04 claims `project_codex_subprocess.py:189-227` currently appends `spec.extra_args` directly at line 219, and the refactor appends workspace projection after that tail.

Verify:
- Current codex subprocess projection structure matches this shape.
- Tail-append semantics haven't changed.

### CP4: Codex streaming projection exists and uses same utilities
Design R05 includes `project_codex_streaming.py` as part of the projection-interface extraction.

Verify:
- File exists, has an analogous shape to the subprocess projection, would need an analogous `project_workspace` implementation.

### CP5: OpenCode projections exist and can accept config overlay
Design A04 and D11 claim OpenCode day-1 support is `permission.external_directory` delivered via `OPENCODE_CONFIG_CONTENT`. The projection lives at `project_opencode_subprocess.py:83-160` and its streaming counterpart.

Verify:
- Both projection files exist.
- `project_opencode_subprocess.py` currently does not touch workspace roots (clean extension point).
- `harness/opencode.py` or equivalent has a place to wire the config overlay without bloating.

### CP6: `StatePaths` is `.meridian`-scoped today
Design FV-5 claims `lib/state/paths.py:93-128` shows `StatePaths` is `.meridian`-scoped. R01 introduces `ProjectPaths` for project-root files.

Verify:
- `StatePaths` today has no project-root file responsibilities beyond `config.toml`.
- Removing `config_path` from `StatePaths` is not coupled to state responsibilities that must stay.

### CP7: `resolve_repo_root` caller surface
Design R01 lists 9 source files calling `resolve_repo_root`. The refactor renames to `resolve_project_root`.

Verify with `rg`:
- Every caller listed still exists.
- No new callers have appeared that aren't in the list (would widen the rename surface).

### CP8: Config command family bypasses loader resolver
Design F3 / R02 claims `config init/show/set/get/reset` all bypass `_resolve_project_toml` and use a `_config_path()` helper. The refactor unifies this.

Verify:
- `_config_path()` or equivalent still exists in `ops/config.py`.
- The bypass pattern described is still how the command family works.

### CP9: Bootstrap auto-writes config scaffold
Design FV-6 / F9 claims `ensure_state_bootstrap_sync` in `ops/config.py:737-763` auto-writes the scaffold template, called from `ops/runtime.py:66`.

Verify:
- This auto-write still exists.
- The split described (runtime dirs + gitignore vs project config) is still an intuitive cleavage.

### CP10: `supports_bidirectional` + streaming subprocess spawn
Design D16 claims streaming still uses `create_subprocess_exec` under the hood.

Verify in `src/meridian/lib/harness/connections/opencode_http.py` (or current OpenCode connection file):
- Child process spawn still happens via `asyncio.create_subprocess_exec(..., env=env)`.
- `env` is composed from `inherit_child_env(os.environ, config.env_overrides)` or equivalent — so env additions propagate.

## General correctness & structural health

### GR1: Refactor scope completeness
- Does R05 actually cover everything that needs to change to extract `HarnessWorkspaceProjection`? Any launch-side touchpoint missed?
- Is R01 big enough? Any hidden coupling between `StatePaths` and project-root concerns not captured in the 9-file scope?

### GR2: Abstraction judgment
Per `dev-principles` — "Leave two similar cases duplicated. Extract at three."
- Is `HarnessWorkspaceProjection` extracted at the right time (3+ consumers: Claude, Codex, OpenCode — yes)?
- Is `ProjectConfigState` extracted at the right time (4+ consumers: loader, config commands, bootstrap, diagnostics — yes)?
- Is `ordered-root planner` (`launch/context_roots.py`) justified as a separate module, or premature?

### GR3: Integration boundary discipline
The design touches external CLI tools (Claude, Codex, OpenCode).
- Are probe claims specific enough that the implementer knows what to re-probe before writing adapters? (D11 for OpenCode, F1 for Codex.)
- Any adapter written against assumptions rather than observed behavior?

### GR4: Observable-by-default posture
`CLAUDE.md` principle: "Observable by default." Workspace state must be inspectable.
- Does the design make workspace state actually visible everywhere it matters (`config show`, `doctor`, launch diagnostics)?
- Any state that gets lost between the snapshot and the launch?

### GR5: Simplest-orchestration posture
The design introduces ~8 new modules. Justify the count.
- Any module that's premature? Any that should merge into a sibling?
- Any that feel like they exist to satisfy an abstraction rather than a need?

### GR6: Cross-cutting concerns
- Logging / telemetry for workspace projection — is there anything we need for observability of workspace-affected launches?
- Security: `MERIDIAN_WORKSPACE` could point anywhere; is any validation described (e.g., must be a regular file)?
- Concurrency: workspace state is read at spawn time; any races with `workspace init` or editor saves?

## Output

Structured report. For each finding:

- **Severity**: HIGH (blocks impl), MEDIUM (fix during impl), LOW (post-impl).
- **Location**: file + section.
- **Finding**: what's wrong or drifted.
- **Evidence**: concrete grep/read output.
- **Suggested fix**: one sentence, or "defer to impl-orch".

End with:
- Summary of codepath drift (CP1–CP10).
- Verdict: `ready-for-impl` / `minor-fixes-needed` / `blocking-issues`.

Keep it tight. Flag what matters.
