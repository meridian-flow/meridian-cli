# Launch Spec

## Purpose

Define the launch-spec hierarchy and the factory contract that maps `SpawnParams` into harness-specific resolved specs. Construction-side accounting catches missing `SpawnParams` mappings; projection-side accounting catches spec-to-wire drift.

This doc complements [typed-harness.md](typed-harness.md), [transport-projections.md](transport-projections.md), and [permission-pipeline.md](permission-pipeline.md).

Revision round 3 changes:

- `mcp_tools` is restored as a first-class forwarded field (D4, reversing round 2 D23). Auto-packaging through mars is out of scope for v2, but manual configuration flows through today.
- Every adapter declares a `handled_fields: frozenset[str]` property (K9). The union across registered adapters must equal `SpawnParams.model_fields` at import time.

## Locations

- `src/meridian/lib/launch/launch_types.py` — shared leaf types (`PermissionResolver`, `SpecT`, `ResolvedLaunchSpec`, `PreflightResult`)
- `src/meridian/lib/launch/spawn_params.py` — `SpawnParams` itself
- `src/meridian/lib/harness/launch_spec.py` — harness-specific spec subclasses + factory helpers + cross-adapter accounting guards

## Hierarchy

### Base — `ResolvedLaunchSpec`

Base class `ResolvedLaunchSpec` lives in `launch_types.py` — see [typed-harness.md](typed-harness.md#module-launchlaunch_typespy). This includes:

- the base `continue_fork` validator
- `mcp_tools: tuple[str, ...] = ()` so every harness can forward MCP configuration
- `extra_args: tuple[str, ...] = ()` forwarded verbatim (no stripping)
- `model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)` — construction-time freeze (K7)

### Claude — `ClaudeLaunchSpec`

```python
class ClaudeLaunchSpec(ResolvedLaunchSpec):
    """Claude-specific resolved launch spec."""

    agent_name: str | None = None
    agents_payload: str | None = None
    appended_system_prompt: str | None = None
```

### Codex — `CodexLaunchSpec`

**D15 still applies:** sandbox/approval are not stored on `CodexLaunchSpec`. Projection reads `spec.permission_resolver.config.sandbox` and `.config.approval` directly.

```python
class CodexLaunchSpec(ResolvedLaunchSpec):
    """Codex-specific resolved launch spec."""

    # Subprocess-only output path (-o). Streaming ignores this field and
    # extracts reports from artifacts.
    report_output_path: str | None = None
```

### OpenCode — `OpenCodeLaunchSpec`

```python
class OpenCodeLaunchSpec(ResolvedLaunchSpec):
    """OpenCode-specific resolved launch spec."""

    agent_name: str | None = None
    skills: tuple[str, ...] = ()
```

## Factory Contract

Each concrete adapter implements `resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> SpecT`.

Rules:

1. Every `SpawnParams` field is either mapped on the spec or explicitly delegated.
2. `perms` is non-optional; callers with no permission context must opt in explicitly via `UnsafeNoOpPermissionResolver`.
3. Normalization happens once in factory helpers; projections do wire mapping only.
4. Adapter return type is concrete (`ClaudeLaunchSpec`, `CodexLaunchSpec`, `OpenCodeLaunchSpec`), not base.
5. Every adapter exposes `handled_fields: frozenset[str]` — the set of `SpawnParams` field names it consumes. Global accounting (§"Completeness Guard — Construction Side") asserts `∪ adapter.handled_fields == SpawnParams.model_fields`.
6. `extra_args` is never filtered or rewritten by the factory or the projection. It flows through verbatim.

### Example: Codex Factory (post-D15 + revision round 3)

```python
class CodexAdapter(HarnessAdapter[CodexLaunchSpec]):
    @property
    def id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def handled_fields(self) -> frozenset[str]:
        return _CODEX_HANDLED_FIELDS

    def resolve_launch_spec(
        self,
        run: SpawnParams,
        perms: PermissionResolver,
    ) -> CodexLaunchSpec:
        return CodexLaunchSpec(
            model=_normalize_model(run.model),
            effort=run.effort,
            prompt=run.prompt,
            continue_session_id=_normalize_session_id(run.continue_harness_session_id),
            continue_fork=run.continue_fork,
            permission_resolver=perms,
            extra_args=run.extra_args,
            interactive=run.interactive,
            mcp_tools=run.mcp_tools,
            report_output_path=run.report_output_path,
        )


_CODEX_HANDLED_FIELDS: frozenset[str] = frozenset({
    "model",
    "effort",
    "prompt",
    "continue_harness_session_id",
    "continue_fork",
    "extra_args",
    "interactive",
    "mcp_tools",
    "report_output_path",
    # Codex consumes these indirectly via preflight / env, not spec fields:
    "repo_root",
    # Codex ignores these explicitly (captured under handled because the
    # adapter makes the decision, rather than letting the field vanish):
    "skills",
    "agent",
    "adhoc_agent_payload",
    "appended_system_prompt",
})
```

No `_map_sandbox_mode` / `_map_approval_mode` helper is used at construction time. Mapping lives in the Codex projection module.

### Claude Factory `handled_fields`

```python
_CLAUDE_HANDLED_FIELDS: frozenset[str] = frozenset({
    "prompt",
    "model",
    "effort",
    "skills",        # consumed via agents_payload assembly in preflight
    "agent",
    "adhoc_agent_payload",
    "extra_args",
    "repo_root",
    "interactive",
    "continue_harness_session_id",
    "continue_fork",
    "appended_system_prompt",
    "mcp_tools",
    # Claude does not use report_output_path; adapter declares it handled
    # with an explicit ignore rule rather than letting it vanish:
    "report_output_path",
})
```

### OpenCode Factory `handled_fields`

```python
_OPENCODE_HANDLED_FIELDS: frozenset[str] = frozenset({
    "prompt",
    "model",
    "effort",
    "skills",
    "agent",
    "adhoc_agent_payload",
    "extra_args",
    "repo_root",
    "interactive",
    "continue_harness_session_id",
    "continue_fork",
    "mcp_tools",
    # ignored but explicitly declared:
    "appended_system_prompt",
    "report_output_path",
})
```

## Completeness Guards

### Global Guard (union across adapters)

The guard takes an **optional registry** parameter so tests can inject a private registry instead of mutating the process-global `_REGISTRY`. At import time `harness/__init__.py` invokes it with `registry=None`, which resolves to `_REGISTRY`; tests construct a fixture registry and pass it explicitly (S044).

```python
# src/meridian/lib/harness/launch_spec.py
from __future__ import annotations

from collections.abc import Mapping

from meridian.lib.harness.bundle import HarnessBundle, _REGISTRY
from meridian.lib.harness.ids import HarnessId
from meridian.lib.launch.spawn_params import SpawnParams


# Derived from SpawnParams at import time — not an authoritative list. Used
# only for clear error formatting; the actual check is the per-adapter union.
_SPEC_HANDLED_FIELDS: frozenset[str] = frozenset(SpawnParams.model_fields)


def _enforce_spawn_params_accounting(
    registry: Mapping[HarnessId, HarnessBundle] | None = None,
) -> None:
    reg = registry if registry is not None else _REGISTRY
    expected = set(SpawnParams.model_fields)
    union: set[str] = set()
    per_adapter: dict[HarnessId, frozenset[str]] = {}
    for harness_id, bundle in reg.items():
        handled = frozenset(bundle.adapter.handled_fields)
        per_adapter[harness_id] = handled
        union |= handled
    missing = expected - union
    stale = union - expected
    if missing or stale:
        raise ImportError(
            "SpawnParams cross-adapter accounting drift. "
            f"Missing (no adapter claims these): {sorted(missing)}. "
            f"Stale (claimed but not on SpawnParams): {sorted(stale)}. "
            f"Per-adapter handled_fields: "
            f"{ {h.value: sorted(f) for h, f in per_adapter.items()} }"
        )
```

This check runs at the tail of `harness/__init__.py` eager import sequence, after every bundle is registered. It is strictly about meridian-internal drift: if a developer adds a new `SpawnParams` field without claiming it on any adapter, the package fails to import (S006, S044).

`_SPEC_HANDLED_FIELDS` is **derived from `SpawnParams.model_fields`**, not hand-maintained — it is *not* an authoritative parallel list. Its only job is to produce readable error messages and to give tests a stable import-time snapshot they can compare against. The authoritative check is the per-adapter union guard above.

### Why parameterize `registry`

Without a `registry` parameter, tests that want to exercise the guard's failure modes (missing field, stale field, empty registry, duplicate harness) either mutate the process-global `_REGISTRY` (breaking isolation between tests) or can't be written at all. Threading `registry=None` through the signature preserves the zero-arg import-time call while letting fixtures pass a local `{HarnessId.CODEX: fake_bundle}` into S044.

### Per-adapter, per-projection guards

The per-adapter guard (above) enforces that every field is claimed by at least one adapter. Per-adapter completeness at the projection layer is still enforced via `_PROJECTED_FIELDS` / `_ACCOUNTED_FIELDS` in each projection module — see [transport-projections.md](transport-projections.md).

K9 (`handled_fields = consumed_fields | explicitly_ignored_fields`, see [typed-harness.md](typed-harness.md)) closes the gap in the earlier design where a global handled set could be satisfied while one adapter silently noops a field.

## Interaction with Other Docs

- [typed-harness.md](typed-harness.md): generic adapter/connection/extractor contracts, dispatch guard, bundle registration.
- [transport-projections.md](transport-projections.md): wire mapping + transport-wide completeness checks + `mcp_tools` projection.
- [permission-pipeline.md](permission-pipeline.md): non-optional resolver, immutable config, strict REST defaults.
