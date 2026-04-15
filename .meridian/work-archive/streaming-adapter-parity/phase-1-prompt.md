# Phase 1: Launch Spec Foundation

## Task

Add the transport-neutral `ResolvedLaunchSpec` model hierarchy plus `resolve_launch_spec()` factory methods on every harness adapter. This phase creates the single mapping layer every later phase consumes but does NOT change how commands or connections are built yet.

## What to Create

### 1. New file: `src/meridian/lib/harness/launch_spec.py`

Create the spec model hierarchy using frozen Pydantic BaseModel (match style in `adapter.py`):

```python
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from meridian.lib.harness.adapter import PermissionResolver, SpawnParams
from meridian.lib.safety.permissions import PermissionConfig

class ResolvedLaunchSpec(BaseModel):
    """Transport-neutral resolved configuration for one harness launch."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: str | None = None
    effort: str | None = None
    prompt: str = ""
    continue_session_id: str | None = None
    continue_fork: bool = False
    permission_config: PermissionConfig = Field(default_factory=PermissionConfig)
    permission_resolver: PermissionResolver | None = None
    extra_args: tuple[str, ...] = ()
    report_output_path: str | None = None
    interactive: bool = False

class ClaudeLaunchSpec(ResolvedLaunchSpec):
    """Claude-specific resolved launch spec."""
    appended_system_prompt: str | None = None
    agents_payload: str | None = None
    agent_name: str | None = None

class CodexLaunchSpec(ResolvedLaunchSpec):
    """Codex-specific resolved launch spec."""
    approval_mode: str = "default"
    sandbox_mode: str | None = None

class OpenCodeLaunchSpec(ResolvedLaunchSpec):
    """OpenCode-specific resolved launch spec."""
    agent_name: str | None = None
    skills: tuple[str, ...] = ()
```

Also add a module-level completeness guard:

```python
_SPEC_HANDLED_FIELDS: frozenset[str] = frozenset({
    "prompt", "model", "effort", "skills", "agent",
    "adhoc_agent_payload", "extra_args", "repo_root",
    "mcp_tools", "interactive", "continue_harness_session_id",
    "continue_fork", "appended_system_prompt", "report_output_path",
})

assert _SPEC_HANDLED_FIELDS == set(SpawnParams.model_fields), (
    f"SpawnParams fields changed. Update resolve_launch_spec() and _SPEC_HANDLED_FIELDS. "
    f"Missing: {set(SpawnParams.model_fields) - _SPEC_HANDLED_FIELDS}, "
    f"Extra: {_SPEC_HANDLED_FIELDS - set(SpawnParams.model_fields)}"
)
```

### 2. Add `resolve_launch_spec()` to each adapter

**ClaudeAdapter** (`src/meridian/lib/harness/claude.py`):
```python
def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> ClaudeLaunchSpec:
```
Normalize effort using `_claude_effort_transform` logic (map "xhigh" -> "max").

**CodexAdapter** (`src/meridian/lib/harness/codex.py`):
```python
def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> CodexLaunchSpec:
```
Normalize effort (pass through as-is for Codex). Extract `approval_mode` from `perms` config. Extract `sandbox_mode` from `perms` config.

**OpenCodeAdapter** (`src/meridian/lib/harness/opencode.py`):
```python
def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> OpenCodeLaunchSpec:
```
Normalize model by stripping `opencode-` prefix. Carry `agent` and `skills`.

### 3. Add to adapter protocol (`src/meridian/lib/harness/adapter.py`)

Add `resolve_launch_spec` to `SubprocessHarness` protocol and `BaseSubprocessHarness`:
```python
# In SubprocessHarness Protocol:
def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> ResolvedLaunchSpec: ...

# In BaseSubprocessHarness:
def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> ResolvedLaunchSpec:
    return ResolvedLaunchSpec(
        model=str(run.model).strip() if run.model else None,
        effort=run.effort,
        prompt=run.prompt,
        continue_session_id=(run.continue_harness_session_id or "").strip() or None,
        continue_fork=run.continue_fork,
        extra_args=run.extra_args,
        report_output_path=run.report_output_path,
        interactive=run.interactive,
    )
```

### 4. Re-export from `src/meridian/lib/harness/__init__.py`

Check if the harness package re-exports primitives. If so, add the spec types.

### 5. New test file: `tests/harness/test_launch_spec.py`

Test each adapter's `resolve_launch_spec()`:
- Claude: effort normalization (xhigh -> max), appended_system_prompt passthrough, agents_payload passthrough
- Codex: effort passthrough, approval/sandbox from permissions
- OpenCode: model prefix strip, skills and agent passthrough
- All: None effort stays None, completeness guard holds

## Constraints
- Do NOT change `build_command()` — that's Phase 2
- Do NOT change any connection adapter — that's Phase 3+
- The only new source of truth should be `resolve_launch_spec()`, not a second strategy layer
- Match existing frozen Pydantic style

## Permission Config Access

The `PermissionResolver` protocol has `resolve_flags(harness_id)`. To get the semantic config:
- Look at how `resolve_permission_pipeline()` in `src/meridian/lib/safety/permissions.py` constructs the resolver
- The resolver carries a `config` attribute (PermissionConfig) — check what's available
- The Codex spec needs `approval_mode` from the config, the OpenCode spec doesn't need it directly

## Verification
```bash
uv run pyright
uv run ruff check .
uv run pytest-llm tests/harness/test_launch_spec.py -x -q
uv run pytest-llm tests/ -x -q  # all tests must still pass
```
