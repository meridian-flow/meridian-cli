# Resolved Launch Spec

## Purpose

The `ResolvedLaunchSpec` is a transport-neutral representation of everything a harness needs to launch one spawn. It is the single place where `SpawnParams` fields are mapped to harness-specific semantics. Both the subprocess path (`build_command()`) and the streaming path (connection adapter `start()`) consume the spec — never raw `SpawnParams`.

## Location

`src/meridian/lib/harness/launch_spec.py` — new module in the harness package, alongside `adapter.py` (protocols) and `common.py` (shared helpers).

## Model Hierarchy

### Base: `ResolvedLaunchSpec`

Common fields that every harness needs, regardless of transport.

**Design principle (from review):** The spec is *semantic*, not *representational*. It carries normalized values and semantic objects, not CLI flags or wire-format strings. Each transport projection maps these semantic values to its native representation.

```python
class ResolvedLaunchSpec(BaseModel):
    """Transport-neutral resolved configuration for one harness launch."""

    model_config = ConfigDict(frozen=True)

    # Identity
    model: str | None = None

    # Execution parameters
    effort: str | None = None  # Already normalized to harness-native value
    prompt: str = ""

    # Session continuity
    continue_session_id: str | None = None
    continue_fork: bool = False

    # Permissions — semantic, not CLI-shaped (D9)
    # Each transport projection maps these to its native mechanism:
    # - CLI: perms.resolve_flags(harness_id) → --flags
    # - JSON-RPC: approval_mode → approval decision logic
    # - HTTP/env: permission_config → OPENCODE_PERMISSION env
    permission_config: PermissionConfig = Field(default_factory=PermissionConfig)
    permission_resolver: PermissionResolver | None = None

    # MCP (currently unused — all adapters return None from mcp_config())
    mcp_config: McpConfig | None = None

    # Passthrough args (transport-specific; not all are valid for all subcommands)
    extra_args: tuple[str, ...] = ()

    # Report output (harness-specific support)
    report_output_path: str | None = None

    # Interactive mode
    interactive: bool = False
```

### Claude: `ClaudeLaunchSpec`

```python
class ClaudeLaunchSpec(ResolvedLaunchSpec):
    """Claude-specific resolved launch spec."""

    # Skill injection via --append-system-prompt
    appended_system_prompt: str | None = None

    # Native agent payload via --agents
    agents_payload: str | None = None

    # Agent profile via --agent
    agent_name: str | None = None
```

### Codex: `CodexLaunchSpec`

```python
class CodexLaunchSpec(ResolvedLaunchSpec):
    """Codex-specific resolved launch spec."""

    # Effort as Codex config string: model_reasoning_effort="value"
    # (stored in base `effort` as the raw value; Codex transport
    # projects it to -c flag or JSON-RPC param)

    # Approval mode for streaming approval requests
    approval_mode: str = "default"

    # Sandbox mode for --sandbox flag
    sandbox_mode: str | None = None
```

### OpenCode: `OpenCodeLaunchSpec`

```python
class OpenCodeLaunchSpec(ResolvedLaunchSpec):
    """OpenCode-specific resolved launch spec."""

    # Agent name for session creation payload
    agent_name: str | None = None

    # Skills for session creation payload
    skills: tuple[str, ...] = ()
```

## Factory Methods

Each harness adapter gains a `resolve_launch_spec()` method:

```python
class ClaudeAdapter(BaseSubprocessHarness):
    def resolve_launch_spec(
        self,
        run: SpawnParams,
        perms: PermissionResolver,
    ) -> ClaudeLaunchSpec:
        """Resolve all SpawnParams fields into a Claude-specific launch spec."""
        ...
```

### Completeness Guard

The factory method is the completeness checkpoint. It must handle every field in `SpawnParams`:

```python
def resolve_launch_spec(self, run: SpawnParams, perms: PermissionResolver) -> ClaudeLaunchSpec:
    # Completeness check: every SpawnParams field must be handled below.
    # If a new field is added to SpawnParams and not handled here,
    # this is the place to add it — and the parity test will catch
    # the omission.

    # Model: pass through
    model = str(run.model).strip() if run.model else None

    # Effort: normalize to Claude values
    effort = self._normalize_effort(run.effort)

    # Permissions — semantic, not CLI flags (D9)
    permission_config = perms.config if hasattr(perms, 'config') else PermissionConfig()

    # Session
    continue_session_id = (run.continue_harness_session_id or "").strip() or None
    continue_fork = run.continue_fork

    # Claude-specific: skill injection
    appended_system_prompt = run.appended_system_prompt

    # Claude-specific: native agent payload
    agents_payload = run.adhoc_agent_payload.strip() or None

    # Claude-specific: agent profile
    agent_name = run.agent

    return ClaudeLaunchSpec(
        model=model,
        effort=effort,
        prompt=run.prompt,
        continue_session_id=continue_session_id,
        continue_fork=continue_fork,
        permission_config=permission_config,
        permission_resolver=perms,
        extra_args=run.extra_args,
        report_output_path=run.report_output_path,
        interactive=run.interactive,
        appended_system_prompt=appended_system_prompt,
        agents_payload=agents_payload,
        agent_name=agent_name,
    )
```

### Static Completeness Assertion

To make the guard machine-checkable (not just convention), the factory can include a static assertion that all `SpawnParams` fields are covered:

```python
# At module level or in a test:
_SPEC_HANDLED_FIELDS: frozenset[str] = frozenset({
    "prompt", "model", "effort", "skills", "agent",
    "adhoc_agent_payload", "extra_args", "repo_root",
    "mcp_tools", "interactive", "continue_harness_session_id",
    "continue_fork", "appended_system_prompt", "report_output_path",
})
assert _SPEC_HANDLED_FIELDS == set(SpawnParams.model_fields), (
    f"SpawnParams fields changed. Update resolve_launch_spec(). "
    f"Missing: {set(SpawnParams.model_fields) - _SPEC_HANDLED_FIELDS}"
)
```

This assertion runs at import time and fails immediately if `SpawnParams` gains a new field that the spec factory doesn't handle.

## Effort Normalization

Effort normalization happens inside `resolve_launch_spec()`, not in the transport layer:

| Input | Claude | Codex | OpenCode |
|-------|--------|-------|----------|
| `"low"` | `"low"` | `"low"` | `"low"` |
| `"medium"` | `"medium"` | `"medium"` | `"medium"` |
| `"high"` | `"high"` | `"high"` | `"high"` |
| `"xhigh"` | `"max"` | `"xhigh"` | `"xhigh"` |

The spec's `effort` field stores the already-normalized value. The transport layer emits it verbatim (e.g., `--effort max` for Claude, `-c model_reasoning_effort="xhigh"` for Codex, `--variant xhigh` for OpenCode).

## Fields Consumed But Not Forwarded

Some `SpawnParams` fields are consumed by the factory but don't appear in the spec because they affect the prompt composition (handled separately by `PromptPolicy` / `RunPromptPolicy`) or the environment (handled by `env_overrides()`):

- `skills`: affects prompt composition via `RunPromptPolicy.include_skills` and `skill_injection_mode`. For Claude, skills are excluded from the prompt and injected via `--append-system-prompt` (stored in `appended_system_prompt`). For Codex/OpenCode, skills are included in the prompt directly.
- `repo_root`: used by the runner for CWD resolution, not forwarded to the harness.
- `mcp_tools`: reserved for MCP wiring (currently unused — all adapters return `None` from `mcp_config()`).

## Relationship to Existing Types

| Existing | After refactor |
|----------|---------------|
| `SpawnParams` | **Unchanged.** Remains the runner-facing input type. |
| `StrategyMap` / `FlagStrategy` / `build_harness_command()` | **Retired (D10).** The spec becomes the single policy layer. `build_command()` is explicit code that projects spec fields to CLI args. The import-time completeness assertion on the spec factory replaces the strategy completeness guard. |
| `ConnectionConfig` | **Slimmed (phased).** `model` stays until Phase 4 (D11). After Phase 4, provides only transport-level config. |
| `PermissionResolver` | **Carried in spec.** The spec holds `PermissionConfig` and `PermissionResolver` reference. CLI projection calls `resolver.resolve_flags()`. Streaming projections use `permission_config.approval` for approval decisions. |
| `RunPromptPolicy` | **Unchanged.** Still governs prompt composition, separate from spec. |
| `HarnessConnection.start()` | **Signature changes (D12).** Accepts `ResolvedLaunchSpec` instead of `SpawnParams`. |

## Upstream Fix: Effort in PreparedSpawnPlan (D13)

`PreparedSpawnPlan` currently has no `effort` field. The runners reconstruct `SpawnParams` from the plan and silently drop effort. This affects BOTH subprocess and streaming paths — effort never reaches the adapter in child spawns.

**Fix (Phase 0):** Add `effort: str | None = None` to `PreparedSpawnPlan`. Wire it through from `prepare.py` (where it's already resolved) to `SpawnParams` construction in both `runner.py` and `streaming_runner.py`.
