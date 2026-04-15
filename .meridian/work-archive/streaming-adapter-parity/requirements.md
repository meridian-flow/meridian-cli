# Streaming Adapter Parity — Requirements

## Problem

The streaming connection adapters (claude_ws.py, codex_ws.py, opencode_http.py) rebuilt harness command construction from scratch, dropping numerous parameters the old subprocess adapters handle. This is a structural duplication problem — two codepaths produce harness config independently with no shared enforcement.

The subprocess path has a checked completeness guard (build_harness_command() fails on unmapped fields). The streaming path hand-picks fields with no equivalent guard, so new fields silently fall through.

## Gaps Found (from investigation)

### Claude streaming missing:
- --effort flag
- --agent flag
- --append-system-prompt
- --agents (native agent profiles)
- Permission/sandbox flags from resolver
- CRITICAL: Claude prompt policy skips agent body + skills from prompt text, relying on these CLI flags. Agents are silently broken on streaming.

### Codex streaming missing:
- -c model_reasoning_effort=... (effort)
- All sandbox/approval flags (--sandbox, --full-auto, --ask-for-approval)
- -o report_path (report output)
- Auto-accepting approvals instead of respecting configured approval mode

### OpenCode streaming missing:
- --variant effort (effort)
- --fork flag
- Model prefix normalization (opencode- strip)

### Both Codex and OpenCode:
- Passthrough args go to wrong subcommands (app-server/serve vs exec/run)

### Session ID extraction:
- Claude session_id always returns None in connection adapter
- StreamingExtractor lacks harness-specific fallback session detection
- Codex threadId alias not scanned in generic artifact fallback

### Runner-level duplication:
- _read_parent_claude_permissions() duplicated in both runners
- Claude child-CWD/session setup duplicated in both runners

## Recommended Approach (from refactor reviewer)

Transport-neutral resolved launch spec — a shared harness-owned resolver that produces the full configuration once. Then:
- build_command() becomes a thin CLI projection of that spec
- Connection adapters consume the same resolved fields for WebSocket/HTTP transport
- One resolver, two output formats, zero duplication

### Migration path:
1. Shared resolver for all harness config (model, effort, permissions, session resume/fork, skill/system-prompt injection, agent payload, env overrides, MCP)
2. Reimplement subprocess build_command() on top of it (no behavior change)
3. Port Claude streaming first (closest to subprocess shape)
4. Port Codex and OpenCode
5. Parity tests across fresh/resume/fork/effort/sandbox/approval/skills/agent

## Constraints

- The subprocess path MUST continue working — it is the stable reference
- Connection adapters use different transports (CLI args vs JSON-RPC params vs HTTP payload) so the shared spec must be transport-neutral
- The checked completeness guard from build_harness_command() must extend to cover the streaming path

## Success criteria

- Every SpawnParams field reaches every harness through both paths
- Adding a new field to SpawnParams fails visibly if either path does not map it
- Parity tests verify both paths produce equivalent harness configuration
