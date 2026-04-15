# Parity Testing Strategy

## Goal

Verify that every `SpawnParams` field reaches every harness through both the subprocess and streaming paths. Adding a new field to `SpawnParams` must fail visibly if either path doesn't map it.

## Three Layers of Defense

### 1. Import-Time Completeness Assertion

In `launch_spec.py`:

```python
_SPEC_HANDLED_FIELDS: frozenset[str] = frozenset({
    "prompt", "model", "effort", "skills", "agent",
    "adhoc_agent_payload", "extra_args", "repo_root",
    "mcp_tools", "interactive", "continue_harness_session_id",
    "continue_fork", "appended_system_prompt", "report_output_path",
})

assert _SPEC_HANDLED_FIELDS == set(SpawnParams.model_fields), (
    f"SpawnParams fields changed. Update resolve_launch_spec(). "
    f"New: {set(SpawnParams.model_fields) - _SPEC_HANDLED_FIELDS}, "
    f"Removed: {_SPEC_HANDLED_FIELDS - set(SpawnParams.model_fields)}"
)
```

**Catches:** Any addition or removal of `SpawnParams` fields. Fails at import time — before any test runs.

### 2. Spec-to-Command Parity Tests

Parameterized unit tests that verify the subprocess `build_command()` output is consistent with the resolved spec:

```python
@pytest.mark.parametrize("harness,params,perms", PARITY_CASES)
def test_spec_matches_command(harness, params, perms):
    spec = harness.resolve_launch_spec(params, perms)
    command = harness.build_command(params, perms)

    # Verify spec fields appear in command
    if spec.model:
        assert "--model" in command
        assert spec.model in command
    if spec.effort:
        # harness-specific effort flag
        assert_effort_in_command(harness.id, spec.effort, command)
    if spec.permission_resolver:
        expected_flags = spec.permission_resolver.resolve_flags(harness.id)
        for flag in expected_flags:
            assert flag in command
    # ... etc for each field
```

**Catches:** Spec factory producing values that the CLI projection doesn't emit, or vice versa.

### 2.5. Transport Projection Completeness Guards (D15)

Each transport projection function includes a `_PROJECTED_FIELDS` frozenset:

```python
# In ClaudeAdapter CLI projection:
_CLI_PROJECTED_FIELDS: frozenset[str] = frozenset({
    "model", "effort", "agent_name", "appended_system_prompt",
    "agents_payload", "continue_session_id", "continue_fork",
    "permission_config", "permission_resolver", "extra_args",
    "report_output_path", "interactive", "prompt",
    "mcp_config",
})

# In ClaudeConnection streaming projection:
_STREAMING_PROJECTED_FIELDS: frozenset[str] = frozenset({
    "model", "effort", "agent_name", "appended_system_prompt",
    "agents_payload", "continue_session_id", "continue_fork",
    "permission_config", "permission_resolver", "extra_args",
    "prompt", "mcp_config",
    # "report_output_path" — not supported in streaming (reports via artifact extraction)
    # "interactive" — always false for streaming
})
```

Import-time assertion:
```python
_all_spec_fields = set(ClaudeLaunchSpec.model_fields)
_unhandled = _all_spec_fields - _CLI_PROJECTED_FIELDS - {"prompt"}
assert not _unhandled, f"ClaudeLaunchSpec fields not in CLI projection: {_unhandled}"
```

**Catches:** A field added to the spec subclass but not projected by either transport.

### 3. Cross-Transport Parity Tests

Tests that verify both subprocess and streaming paths would produce equivalent harness configuration from the same spec:

```python
@pytest.mark.parametrize("harness_id,params", PARITY_CASES)
def test_both_transports_cover_all_spec_fields(harness_id, params):
    """Verify that the streaming transport projection covers the same
    semantic fields as the subprocess projection."""
    adapter = get_adapter(harness_id)
    spec = adapter.resolve_launch_spec(params, mock_perms)

    # Subprocess produces a command
    command = adapter.build_command(params, mock_perms)
    subprocess_fields = extract_semantic_fields_from_command(command, harness_id)

    # Streaming produces a config (CLI args, JSON-RPC params, or HTTP payload)
    streaming_config = extract_streaming_config_from_spec(spec, harness_id)

    # Both should cover the same semantic fields
    assert subprocess_fields.keys() == streaming_config.keys(), (
        f"Subprocess has {subprocess_fields.keys() - streaming_config.keys()} "
        f"that streaming doesn't, and streaming has "
        f"{streaming_config.keys() - subprocess_fields.keys()} that subprocess doesn't"
    )
```

**Catches:** One transport covering a field that the other misses.

## Test Matrix

The parity cases should cover the product of:

| Dimension | Values |
|-----------|--------|
| Harness | claude, codex, opencode |
| Session | fresh, resume, fork |
| Effort | None, low, medium, high, xhigh |
| Approval | default, auto, confirm, yolo |
| Agent | None, named |
| Skills | empty, non-empty |
| Adhoc agent payload | empty, non-empty |
| Appended system prompt | None, non-empty |
| Permission flags | tiered (sandbox), explicit tools, combined |
| Extra args | empty, non-empty |
| Interactive | false, true |

Not every combination is meaningful. The test should cover at minimum:

1. **Baseline**: fresh session, no optional fields. (3 tests, one per harness)
2. **Full session lifecycle**: resume and fork for each harness. (6 tests)
3. **Effort levels**: each level for each harness. (15 tests)
4. **Permissions**: yolo, auto, confirm for each harness. (9 tests)
5. **Claude-specific**: agent + skills + adhoc payload + appended system prompt. (1 test)
6. **Codex-specific**: approval mode in streaming context. (3 tests)
7. **OpenCode-specific**: model prefix normalization. (1 test)

Total: ~38 focused parity cases.

## What's NOT Tested Here

- End-to-end spawn execution (that's smoke testing, not parity testing).
- Connection adapter protocol behavior (WebSocket handshake, HTTP retries, etc.).
- Runner-level preflight (tested separately by verifying the extracted functions match original behavior).
- MCP wiring (all adapters return `None` currently).

## Session ID Extraction

The investigators flagged that Claude streaming `session_id` always returns `None`. This is a separate extraction issue, not a launch spec issue. The `StreamingExtractor` falls back to artifact-based extraction, which works for Codex and OpenCode but not Claude (the Claude connection adapter doesn't set `session_id`).

**Fix:** After the streaming Claude subprocess starts and emits its first event, scan for a `session_id` field in the event payload and store it. This is a connection-adapter-level fix, not a spec-level fix. It should be included in Phase 3 if feasible.

## Test Location

`tests/unit/test_launch_spec_parity.py` — pure unit tests, no subprocess launches, no I/O. Mock `PermissionResolver` returns predictable flag lists.
