# Final Adversarial Review — Exit-criteria mechanical enforceability

## Context

`workspace-config-design`'s R06 was rewritten (p1894, opus) with exit criteria framed as definition-anchored `rg` patterns with exact expected results. The architect verified each pattern against the live codebase and tabulated current vs. target hit counts:

| Check | Pre-R06 hits | Post-R06 target |
|---|---|---|
| `rg "^def resolve_policies\(" src/` | 1 | 1 |
| `resolve_policies\(` callers | 3 | 2 |
| `rg "^def resolve_permission_pipeline\(" src/` | 1 | 1 |
| `resolve_permission_pipeline\(` callers | 4 | 2 |
| `rg "^class RuntimeContext\b" src/` | 2 | 1 |
| `claude_preflight` imports in launch/ | 2 | 0 |
| `TieredPermissionResolver\(` outside permissions.py | 2 | 0 |
| `MERIDIAN_HARNESS_COMMAND` outside factory | 4 | 0 |
| `resolve_launch_spec\(` outside factory+adapters | 3 | 0 |
| `run_streaming_spawn` | 4 | 0 |
| `start_spawn` optional-spec fallback | 1 | 0 |
| `UnsafeNoOpPermissionResolver` in streaming/ | 2 | 0 |
| `rg "^class SpawnParams\b" src/` | 1 | 1 |

Plus Plan Object compile-time enforcement via Pyright + `match` + `assert_never` on `LaunchContext = NormalLaunchContext | BypassLaunchContext`.

## Your task — adversarial review, enforceability focus

You are the **CI mechanism** reviewer. Your job is to find ways a future contributor (or even the coder implementing R06) could ship code that violates the invariants while the CI signal stays green. In other words: are these checks actually traps, or are they theater?

Read these first:
- `.meridian/work/workspace-config-design/design/refactors.md` (R06 exit criteria specifically)
- `.meridian/work/workspace-config-design/decisions.md` (D17)
- `.meridian/spawns/p1894/report.md` (the verification table)
- `.meridian/spawns/p1891/report.md` (the prior enforceability review that found blockers — check which survived)

Probe live code where needed to verify claims.

### Pressure tests

1. **`rg` pattern gaming** — for each pattern in the exit criteria, think of ways a coder could satisfy the check while violating the invariant:
   - **Aliasing**: `from launch.permissions import resolve_permission_pipeline as rpp` — does the pattern catch this?
   - **Partial application**: `_rpp = functools.partial(resolve_permission_pipeline, ...)` — would a caller's call be missed?
   - **Re-export**: a module re-exports a builder; calls route through the re-export. Does the pattern catch the re-export site?
   - **Indirect dispatch**: storing the function in a dict or class attribute and calling via `fns["permissions"]()` — invisible to grep.
   - **Inline reimplementation**: copy-pasting the builder body instead of calling it. Invisible to grep by function name; would only be caught by a structural check.

2. **Definition-anchored patterns** — `rg "^def resolve_policies\("` assumes one definition. What about:
   - Overloaded definitions (`@overload` decorators on protocols)?
   - Class methods vs. free functions — if someone refactors into a class, the pattern breaks but the invariant may still hold (or may not).
   - Definitions inside conditional imports / platform-specific branches.

3. **"Outside permissions.py" / "outside factory" patterns** — these rely on path exclusion. Gameable by:
   - Moving the violation to a path that the pattern includes by accident (e.g., a new `src/meridian/lib/launch/...` module that looks like part of the core but isn't).
   - Import chains: if `launch/context.py` imports from `launch/helpers.py` which imports `TieredPermissionResolver`, does the check fire?

4. **`MERIDIAN_HARNESS_COMMAND` outside factory** — the current check is `rg "MERIDIAN_HARNESS_COMMAND" src/` returns only the bypass branch. But:
   - Tests use the env var too. Does the pattern exclude `tests/`? If not, it'll hit N test files and the check becomes useless.
   - Error messages, documentation strings, log messages — is the pattern tight enough?

5. **Pyright + `match` + `assert_never` enforceability** — the claim is that union exhaustiveness is compile-checked.
   - Is the project actually configured with strict exhaustiveness? `pyright.config.json` or `pyproject.toml` pyright strictness level matters. Check it.
   - If the executor dispatch uses `isinstance` ladders instead of `match`, does Pyright still flag missing arms? (Usually no.)
   - Is there a way to construct `NormalLaunchContext` or `BypassLaunchContext` incompletely (e.g., with `**kwargs` hack, `dataclass.fields`, or `field(default=None)`) that defeats "required fields"?
   - Frozen dataclasses are runtime-frozen; do they also prevent `object.__setattr__`? What about pydantic models?

6. **Driving-adapter count check** — `rg "build_launch_context\(" src/` → exactly 4 matches (primary, worker, app-streaming, dry-run preview). Verify:
   - Does the pattern hit definitions, imports, type annotations, docstrings? (False positives.)
   - If dry-run preview is called from two CLI entry points (`meridian spawn --dry-run` and `meridian --dry-run`), is it still 4 matches or 5?
   - Is there a way to add a 5th caller by importing under a different name or dispatching through a decorator?

7. **Deletions as enforcement** — `rg "^def run_streaming_spawn\(" src/` → 0 matches. OK, but:
   - Is there a git hook / CI step that actually runs these commands? Or is it just "a planner can verify manually"? If the latter, these are docs, not gates.
   - Even if CI runs them, does failure block merge? Required status check?

8. **What's NOT covered by the checks** — enumerate invariants stated in R06/D17 that have no mechanical check at all. For each, say whether it's legitimate (inherently non-mechanical) or a gap (mechanical check possible but not specified).

9. **Hidden cost** — the check `resolve_policies\( → 2 callers (def + factory)` is counted by call-site, not by definition location. A coder could add a third caller somewhere in the codebase and the check reports "3, not 2" — easy. But if someone rewrites `resolve_policies` to dispatch through a registry (`policy_registry.get("default")()`), the call-site count may not change, but the invariant is violated. How would that be caught?

### Prior findings to re-check

- **p1891 Blocker 2** (post-launch session-id contradicts "all required, frozen"): the p1894 rewrite claims session-id moved off `LaunchContext` to an executor result. Verify the design actually says this cleanly, and check if any other "optional fields" problem remains (e.g., Codex fork continuation state, `child_cwd`, preflight output).
- **p1891 Major F3** (adapter boundary — grep gameability): verify the new boundary statement distinguishes abstract contracts from concrete harnesses cleanly.
- **p1892 F5** (no structural enforcement, just docs+review): the new exit criteria ostensibly fix this by adding CI-checkable commands. But is there a CI step that actually runs them? Named in the design?

### Report format

- Findings as **Blocker / Major / Minor** with file:line references.
- Distinguish **gap** (invariant has no check at all) vs **weak check** (check exists but can be bypassed) vs **solid check** (genuinely enforceable).
- End with a **Verdict**: approve / approve-with-minor-fixes / request-changes.
- Be adversarial on mechanism. If a check "should work in principle," challenge whether it actually does.
- Target length: ~600 words of findings, plus the verdict.
