# Reviewer: Cross-harness integration asymmetries (claude-opus-4-6)

You are a reviewer focused on cross-harness integration. The three harnesses (Claude, Codex, OpenCode) use fundamentally different transports: Claude uses CLI args + stdio, Codex uses JSON-RPC over app-server, OpenCode uses HTTP POST to a serve process. Asymmetries between them are sometimes necessary (the transport genuinely can't express a field) and sometimes bugs (one adapter forgot to implement what the others did). Your job is to tell them apart.

## Context

The refactor introduced `ResolvedLaunchSpec` as the common contract so that both subprocess and streaming paths consume the same spec. The per-harness subclasses (`ClaudeLaunchSpec`, `CodexLaunchSpec`, `OpenCodeLaunchSpec`) hold harness-specific fields. Design is in `.meridian/work-archive/streaming-adapter-parity/design/`, decisions in `.meridian/work-archive/streaming-adapter-parity/decisions.md`. Read `transport-projections.md` first — it describes how each transport projects the spec.

## What to review

1. **Field-by-field matrix.** Build a matrix: rows = base `ResolvedLaunchSpec` fields, columns = (Claude subprocess, Claude streaming, Codex subprocess, Codex streaming, OpenCode subprocess, OpenCode streaming). For each cell, state: honored, ignored with reason, ignored silently, or transformed. Flag every "ignored silently" as a candidate bug. Flag every "transformed" as a candidate inconsistency — and confirm the transformation is the same on both transports of the same harness.

2. **Approval and permission mapping.** The three harnesses handle permissions very differently. Walk through each one:
   - **Claude**: CLI flags (--allowedTools, --permission-mode, etc). Both subprocess and streaming should use the same resolver output.
   - **Codex**: JSON-RPC approval callbacks + `--full-auto` / `--ask-for-approval` on subprocess. Streaming uses callbacks only. D14 says confirm-mode streaming rejects; is the rejection correctly surfaced to the caller (not just logged)?
   - **OpenCode**: `OPENCODE_PERMISSION` env var + HTTP payload options. Is the env set consistently across subprocess and streaming?

   Draw the asymmetries explicitly and decide: is the asymmetry a transport necessity or a bug?

3. **Agent / skill / system-prompt forwarding.** This is the headline bug from D1 for Claude — streaming Claude silently dropped skills and agents. Check all three harnesses:
   - **Claude** has `appended_system_prompt`, `agents_payload`, skills via `--agents`. Are both paths emitting them now?
   - **Codex** passes agent body differently — via `profile` config. Does it work identically on both paths?
   - **OpenCode** passes agent body differently again. Same question.

4. **Effort.** Each harness normalizes effort differently (Claude: xhigh→max, Codex: effort→model_reasoning_effort, OpenCode: HTTP asymmetry per D16). Confirm the normalization lives in the factory (D4), not duplicated in the transport projections.

5. **Session continuity (resume / fork).** Edge case 4 in `overview.md` says both transports must handle `--resume` and `--fork-session` identically for Claude. Check that. Also check Codex's `threadId` handling on resume — is it on both paths?

6. **Transport-specific pitfalls.**
   - **Claude**: long system prompt handling, special character escaping.
   - **Codex**: JSON-RPC request ID collision (the ce1bcea commit added a send lock — is it still there?).
   - **OpenCode**: HTTP retry / connection re-use / timeout handling.

7. **HarnessConnection.start() contract.** Read `connections/base.py`. Does the protocol enforce `(config, spec)` consistently? Are there default implementations that would let a forgetful subclass implementer skip spec handling?

## Deliverable

A cross-harness matrix (markdown table) followed by findings. Each finding: severity, which harness, which transport, what's asymmetric, is it a bug or a documented asymmetry, where in the code. End with an overall assessment: are the three harnesses now behaviorally aligned where they should be, and honestly asymmetric where they must be?

## Reference files
- `.meridian/work-archive/streaming-adapter-parity/design/overview.md`
- `.meridian/work-archive/streaming-adapter-parity/design/transport-projections.md`
- `.meridian/work-archive/streaming-adapter-parity/decisions.md`
- `src/meridian/lib/harness/launch_spec.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/harness/common.py`
- `src/meridian/lib/harness/adapter.py`
- `src/meridian/lib/harness/connections/base.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `tests/harness/test_launch_spec_parity.py`
