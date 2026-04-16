# Refactor Agenda

Structural rearrangement the planner must account for before / alongside
feature work. Each entry lists scope, motivation, and ordering.

## R1 — De-hardcode `CodexAdapter.resolve_session_file` (FOUNDATIONAL)

**Where:** `src/meridian/lib/harness/codex.py:392-404`.
**Today:** hard-codes `Path.home() / ".codex" / "sessions"`.
**Change:** consult `launch_env["CODEX_HOME"]` first (the adapter already
has the spawn's launch env threaded via `ArtifactStore`/context), falling
back to `Path.home() / ".codex"` only when no override is set.
**Why ordered first:** without this, per-spawn `CODEX_HOME` (SC-1) silently
breaks session resolution. The extractor already honors the env
(`extractors/codex.py:101`), so fixing the adapter brings them into
alignment rather than introducing a new concept.
**Sequencing:** must land before or in the same phase as SC-1, before any
SC-8 verification is possible.
**Files touched:** `src/meridian/lib/harness/codex.py`.

## R2 — Add `CODEX_HOME` to the child-env allowlist

**Where:** `src/meridian/lib/launch/env.py:99-130` (the
`inherit_child_env()` allowlist).
**Today:** allowlist is `PATH, HOME, USER, SHELL, LANG, TERM, TMPDIR,
PYTHONPATH, VIRTUAL_ENV` plus `LC_*`, `XDG_*`, `UV_*`. `CODEX_HOME` is
absent.
**Change:** add `CODEX_HOME` to the explicit allowlist. Note: overrides
from `env_overrides(config)` are applied *after* the allowlist (p1730),
so a per-spawn `CODEX_HOME` would propagate today via the override
channel; the allowlist addition is belt-and-suspenders for the case
where a user sets `CODEX_HOME` in their shell and expects it to reach
the child.
**Sequencing:** independent of R1. Can land in any order.
**Files touched:** `src/meridian/lib/launch/env.py`.

## R3 — Unify the adapter `env_overrides` signature

**Where:** `src/meridian/lib/harness/adapter.py` (base class) and the
three concrete adapters (`codex.py`, `claude.py`, `opencode.py`).
**Today:** `env_overrides(config: PermissionConfig) -> dict[str, str]`.
**Change:** extend to `env_overrides(config: PermissionConfig, *,
spawn_id: SpawnId, spawn_log_dir: Path) -> dict[str, str]`. Codex needs
the spawn id (and log dir) to construct its per-spawn `CODEX_HOME`
path. OpenCode ignores the new args. Claude returns `{}` either way.
**Why ordered early:** touches all three adapters; doing it once before
the feature work keeps the feature change small. Alternative: pass the
path through `PermissionConfig` as a pre-computed field. Either design is
fine — the refactor-reviewer should pick one before implementation.
**Sequencing:** before SC-1 implementation.
**Files touched:**
- `src/meridian/lib/harness/adapter.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/launch/process.py` / `launch/streaming_runner.py`
  (callers of `env_overrides`).

## R4 — Delete `_strip_tool_flags_for_codex` (SIGNAL)

**Where:** `src/meridian/lib/harness/projections/project_codex_subprocess.py:101-142`.
**Today:** strips `--allowedTools` / `--disallowedTools` with a warning.
**Change:** delete outright once SC-4 / SC-5 land. No compatibility shim.
**Why:** deletion is the structural signal that parity has arrived. A
kept warning path is a silent-strip-by-another-name.
**Sequencing:** lands in the same phase that turns on codex's
`supports_managed_allowlist = True`. Do not land earlier (would break
current silent-drop behavior before the replacement is ready).
**Files touched:**
`src/meridian/lib/harness/projections/project_codex_subprocess.py`.

## R5 — Hoist `PermissionConfig.opencode_permission_override` computation

**Where:** `src/meridian/lib/safety/permissions.py:292-320`
(`resolve_permission_pipeline`) and the `_resolve_opencode_override`
helper at `permissions.py:241-250`.
**Today:** the override is only populated when `allowed_tools` or
`disallowed_tools` is non-empty. `sandbox: read-only` alone yields no
opencode override, silently failing to enforce read-only.
**Change:** `_resolve_opencode_override` takes `sandbox` as an input
and synthesizes a baseline `{"*": "deny", "read": "allow", "grep":
"allow", "glob": "allow", "list": "allow"}` when sandbox is `read-only`
and no explicit lists are present. Composes with allowlist/denylist per
SO-2.
**Sequencing:** before SO-1/SO-2 implementation.
**Files touched:** `src/meridian/lib/safety/permissions.py`.

## R6 — Push claude read-only → plan projection into the generic mapper

**Where:** `src/meridian/lib/harness/adapter.py:55-83`
(`_permission_flags_for_harness`).
**Today:** the function has no sandbox branch for claude; only approval
modes produce `--permission-mode` values.
**Change:** add a final branch — when `config.sandbox == "read-only"`,
`config.approval == "default"`, and `harness_id == CLAUDE`, emit
`("--permission-mode", "plan")`. This is the minimal claude sandbox
projection (SL-1) and belongs with the existing approval mappings, not
as a new code path elsewhere.
**Sequencing:** independent of R1/R2/R3; lands with SL-1.
**Files touched:** `src/meridian/lib/harness/adapter.py`.

## R7 — `HarnessCapabilities` field additions

**Where:** `src/meridian/lib/harness/adapter.py:121-136`.
**Change:** add three `bool` fields (`supports_managed_sandbox`,
`supports_managed_allowlist`, `supports_managed_denylist`), default
`False`. Each concrete adapter flips the three to `True` as part of
this work (all three flip true; none regress).
**Sequencing:** before the capability-check gate in
`resolve_permission_pipeline` can run.
**Files touched:** `src/meridian/lib/harness/adapter.py` plus each
adapter (codex/claude/opencode) constructor.

## Ordering summary

```
R1 ──┐
R2 ──┼──► SC-1..SC-8 (codex home pipeline) ──► R4 (delete strip) ──► SC-13 smoke
R3 ──┘

R5 ──► SO-1..SO-9  (opencode baseline)

R6 ──► SL-1..SL-8  (claude read-only)

R7 ──► E-1..E-6 capability-check gate (depends on R6, R3, R5 flipping
                 the three flags to True in their respective adapters)
```

## Deferred / out of scope

- Generalizing `resolve_permission_pipeline` to a pluggable
  per-harness "permission builder" interface. Today only codex needs
  the config-toml synthesis; introducing a plugin seam for one consumer
  violates dev-principles (abstract at 3, not at 1). Revisit when a
  fourth harness needs a policy-on-disk mechanism.
- Consolidating `_strip_claude_tool_flags` (`adapter.py:86-96`) and the
  deleted `_strip_tool_flags_for_codex`. These serve different purposes
  (the first converts resolver flags for a different harness; the
  second dropped-with-warning) and the first still has callers.
