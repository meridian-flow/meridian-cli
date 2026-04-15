# Revision Pass 2 — Structural Polish Brief

The v2 design completed revision pass 1 and was re-reviewed by two opus convergence reviewers:
- **r1b (design alignment, p1429): CONVERGED.** Only 3 LOW doc-polish findings.
- **r4b (refactor, p1430): Needs revision.** 3 HIGH + 5 MEDIUM + 2 LOW structural-polish findings.

The design shape is correct. This pass is about closing **missing-definition drift risks** the refactor-reviewer caught — the kind of gap that silently produces conflicting invented locations during implementation.

Scope: ~10 targeted doc fixes. Do NOT reopen the shape decisions from revision pass 1. If any fix would require reversing a decision in `decisions.md` (D1–D24), stop and flag it.

## Deliverables

- Every fix below applied to the relevant design doc
- `decisions.md` updated with a `## Revision Pass 2 (post p1429/p1430)` section and a bullet per fix
- New decision D25 only if H3 requires a canonical-home ruling; otherwise reuse D7 or D13
- No new scenarios (none of these findings change behavior)
- Your `report.md` must include a per-fix change summary (G1–G10 below, one line each)

## Fixes

### G1 (HIGH, r4b H1) — Complete the import topology DAG

`typed-harness.md` §Import Topology currently shows an incomplete DAG. Every module introduced by v2 must appear explicitly with upward edges. Missing modules:

- `harness/errors.py` (D24 `HarnessBinaryNotFound`)
- `harness/claude_preflight.py` (F5, referenced in `overview.md:64` and `runner-shared-core.md:26`)
- `harness/bundle.py` (see G2)
- `launch/constants.py`
- `launch/context.py`
- `launch/text_utils.py` (D13, see G5)
- `projections/_guards.py`
- `projections/_reserved_flags.py` (see G3)

Extend the ASCII DAG to include every one of these with explicit edges. Cross-reference from `overview.md` §5 so the DAG is discoverable from the overview entry point. E31/S031 ("acyclic DAG") must be verifiable against the documented DAG.

### G2 (HIGH, r4b H2) — Define HarnessBundle

`HarnessBundle[SpecT]` is referenced by the dispatch guard, `prepare_launch_context`, and `get_harness_bundle(harness_id)` — but the dataclass shape, module location, and lookup signature are nowhere in the design. D2 describes the concept in prose only.

Add a **§Bundle Registry** subsection in `typed-harness.md` with:

```python
# src/meridian/lib/harness/bundle.py
from dataclasses import dataclass
from typing import Generic
from meridian.lib.launch.launch_types import SpecT, ResolvedLaunchSpec
from meridian.lib.harness.adapter import HarnessAdapter
from meridian.lib.harness.connections.base import HarnessConnection

@dataclass(frozen=True)
class HarnessBundle(Generic[SpecT]):
    harness_id: str
    adapter: HarnessAdapter[SpecT]
    spec_cls: type[SpecT]
    connection_cls: type[HarnessConnection[SpecT]]

_REGISTRY: dict[str, HarnessBundle] = {}  # populated by harness modules at import time

def get_harness_bundle(harness_id: str) -> HarnessBundle:
    try:
        return _REGISTRY[harness_id]
    except KeyError:
        raise KeyError(f"unknown harness: {harness_id}") from None
```

Reference it from the DAG (G1) and from `runner-shared-core.md` where `get_harness_bundle` is consumed.

### G3 (HIGH, r4b H3) — Pin reserved-flag constants to one module

`_RESERVED_CODEX_ARGS` and `_RESERVED_CLAUDE_ARGS` appear in `permission-pipeline.md` as raw frozensets, and `_strip_reserved_passthrough(...)` is called from `transport-projections.md` with no import path. Three candidate homes would cause duplication across projection files.

Pin to `src/meridian/lib/harness/projections/_reserved_flags.py`:

```python
# src/meridian/lib/harness/projections/_reserved_flags.py
_RESERVED_CLAUDE_ARGS = frozenset({...})
_RESERVED_CODEX_ARGS = frozenset({...})

def strip_reserved_passthrough(
    args: list[str],
    reserved: frozenset[str],
    *,
    logger: logging.Logger,
) -> list[str]:
    ...
```

Update:
- `permission-pipeline.md` §Reserved Flags — add the module file header
- `transport-projections.md` §Reserved Flags Policy — import from the canonical path
- DAG (G1) — include `projections/_reserved_flags.py`
- `decisions.md` — either extend D7 or D8 with the ruling, or add D25 "Reserved-flag constants live in `projections/_reserved_flags.py`"

### G4 (MEDIUM, r4b M1) — Single home for `ResolvedLaunchSpec` base

`typed-harness.md:9–32` puts the base stub in `launch_types.py`. `launch-spec.md:16–49` declares the full base class body including `_validate_continue_fork_requires_session` and says `launch_spec.py` contains "harness-specific spec subclasses + factory helpers."

Pick **`launch_types.py`** as the single home:
- Move the full base class body and the `_validate_continue_fork_requires_session` validator into `typed-harness.md` §Module: `launch/launch_types.py`
- Replace `launch-spec.md` §Base code block with a one-line reference: "Base class `ResolvedLaunchSpec` lives in `launch_types.py` — see `typed-harness.md` §Base Class."
- Update `launch-spec.md` prose about what `launch_spec.py` contains accordingly

### G5 (MEDIUM, r4b M2) — Resolve `launch/text_utils.py`

D13 claims L5 closure via `launch/text_utils.py`, but the module is absent from every module layout (`runner-shared-core.md` §Module Layout, `overview.md` §5, DAG).

Either:
- **Option A**: Add `launch/text_utils.py` to the Module Layout sections and the DAG (G1), and briefly describe its responsibilities (one paragraph in `runner-shared-core.md`).
- **Option B**: Strike the second half of D13 and re-open L5 as deferred.

Pick Option A unless text_utils would be a <50 line module with no consumers beyond one call site — in which case inline and take Option B.

### G6 (MEDIUM, r4b M3) — Delete `PreflightResult.extra_cwd_overrides`

`typed-harness.md:27–32` defines `extra_cwd_overrides: dict[str, str]`, which flows into `merged_overrides` (the env dict) in `runner-shared-core.md:98`. A field named "cwd" that lands in env is mislabeled; Claude preflight's real needs are covered by `extra_env` + `expanded_passthrough_args`.

Delete `extra_cwd_overrides` from `PreflightResult`. Update `runner-shared-core.md` prose to match. If a second consumer later needs cwd overrides, add then.

### G7 (MEDIUM, r4b M4) — Collapse `LaunchContext.permission_config` into `perms.config`

`runner-shared-core.md:31–41` declares both `LaunchContext.perms: PermissionResolver` and `LaunchContext.permission_config: PermissionConfig`. The context constructor populates `permission_config` from `perms.config`, creating two sources of truth for the same value.

Delete `LaunchContext.permission_config`. Callers read `ctx.perms.config`. Update every design code sample in `runner-shared-core.md`, `transport-projections.md`, and `permission-pipeline.md` that references `ctx.permission_config`.

### G8 (MEDIUM, r4b M5) — Tie consumer-union accounting to real consumer modules

`transport-projections.md:121–164` declares five `_*_ACCOUNTED_FIELDS` frozensets inline without citing origin modules. F6's intent was "each consumer-module exports an `_ACCOUNTED_FIELDS` set" — the guard only verifies "listed in one of these sets", not that a real consumer reads the field.

Two-step fix:
1. Rewrite the block to `from ... import _ACCOUNTED_FIELDS as _APP_SERVER_ACCOUNTED_FIELDS` (and similarly for every consumer). Name the source module for each in a comment table.
2. If F9's "merge codex streaming into one module" means there's only one consumer module, restructure to per-function accounted sets (`_APP_SERVER_ARG_FIELDS`, `_JSONRPC_PARAM_FIELDS`, etc.) defined next to the functions that consume them, and reference them by name from the top-of-file aggregation.

Additionally: explain why `interactive` is in `_ENV_ACCOUNTED_FIELDS` on a long-lived WebSocket path. If it doesn't belong there, move it to the actual consumer's set.

### G9 (LOW, r4b L1) — Inline `_AgentNameMixin`

`launch-spec.md:56–64` extracts `_AgentNameMixin` across Claude and OpenCode (2 call sites). Per dev-principles §Abstraction Judgment, extract at 3+ instances.

Inline `agent_name: str | None = None` on both `ClaudeLaunchSpec` and `OpenCodeLaunchSpec` directly. Delete `_AgentNameMixin`. If Codex ever needs `agent_name`, revisit the extraction at that point.

Update D10 in `decisions.md` to reflect this — the mixin was introduced on the assumption of a 3rd consumer; revisit if/when that consumer arrives.

### G10 (LOW, r4b L2) — Simplify `_SPEC_DELEGATED_FIELDS` in codex streaming

`transport-projections.md:148–170` declares `_SPEC_DELEGATED_FIELDS = {"report_output_path"}`, unions it back into the accounted set, subtracts, re-unions. Net effect: a plain `_check_projection_drift(CodexLaunchSpec, _ACCOUNTED_FIELDS, frozenset())`.

Either:
- Simplify the block to the one-line form and remove `_SPEC_DELEGATED_FIELDS` from codex streaming, or
- Make delegated fields enforceably distinct: require that delegated fields appear in **exactly one** consumer set (not zero, not two), and have `_check_projection_drift` verify this.

Pick simplification unless the distinct-enforcement option is genuinely needed across more than one projection.

## Non-goals

- Do NOT reopen CodexLaunchSpec shape, REST default, dispatch cast site, preflight inversion, or any other revision pass 1 decision.
- Do NOT add new scenarios — these are structural-doc fixes.
- Do NOT touch `review-prompts/` or `scenarios/overview.md` unless G1–G10 explicitly require it.

## Report format

Return a per-fix change summary like p1427's:

```
1. G1: [what changed]
2. G2: [what changed]
...
```

End with any unresolved questions or blockers (empty list is fine).
