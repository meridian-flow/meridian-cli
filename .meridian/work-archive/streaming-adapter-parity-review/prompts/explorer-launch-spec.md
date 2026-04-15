# Explorer: ResolvedLaunchSpec implementation vs design

You are an explorer. Do not make code changes. Your only job is to gather concrete facts and report them.

## Task

Read the `ResolvedLaunchSpec` implementation in `src/meridian/lib/harness/launch_spec.py` and verify that it matches the design described in the reference documents. Then read each per-harness factory method on the adapters (`claude.py`, `codex.py`, `opencode.py`) and verify they produce specs consistent with the design's expected fields.

## Specific questions to answer

1. **Base spec shape.** List every field on `ResolvedLaunchSpec` (the base class). For each, note the type, default, and which design decision it traces to (D1–D18 in `decisions.md`). Flag any fields that appear without a matching decision and any decisions (D4, D9, D13) whose required fields are missing.

2. **Per-harness subclasses.** Read `ClaudeLaunchSpec`, `CodexLaunchSpec`, `OpenCodeLaunchSpec`. For each:
   - List the harness-specific fields added.
   - Verify the fields match what `design/resolved-launch-spec.md` and `design/transport-projections.md` specify. Call out any fields that are in the design but missing from the implementation, or fields that are in the implementation but not in the design.
   - Confirm whether effort normalization happens in the factory (D4) — show the code snippet that proves it.
   - Confirm whether OpenCode's `opencode-` prefix strip happens in the factory (edge case 5 in `overview.md`).

3. **Factory methods.** For each of `ClaudeAdapter.resolve_launch_spec`, `CodexAdapter.resolve_launch_spec`, `OpenCodeAdapter.resolve_launch_spec`:
   - Quote the signature.
   - List which `SpawnParams` fields it reads.
   - List which `PermissionResolver` / `PermissionConfig` fields it reads.
   - Note whether the returned spec stores `PermissionConfig` semantically or pre-resolves CLI flags (D9 requires the former).

4. **Completeness guard.** Find the `_SPEC_HANDLED_FIELDS` set (or equivalent) that enforces SpawnParams→spec completeness. Quote it. Compare against the current `SpawnParams` field list in `src/meridian/lib/ops/spawn/params.py` (or wherever `SpawnParams` is defined). Identify any mismatch: SpawnParams fields not in `_SPEC_HANDLED_FIELDS`, and entries in `_SPEC_HANDLED_FIELDS` that no longer exist on `SpawnParams`. Also check the D17 triage note about `mcp_tools` — is it resolved or still in the set?

5. **Record quotes.** For each finding, quote the exact line and give the file path and line number so a reviewer can jump straight to it.

## Reference files
- `.meridian/work-archive/streaming-adapter-parity/design/overview.md`
- `.meridian/work-archive/streaming-adapter-parity/design/resolved-launch-spec.md`
- `.meridian/work-archive/streaming-adapter-parity/design/transport-projections.md`
- `.meridian/work-archive/streaming-adapter-parity/decisions.md`
- `src/meridian/lib/harness/launch_spec.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/harness/common.py`
- `src/meridian/lib/harness/adapter.py`

## Deliverable

A single structured report with sections for each of the five questions. No code changes. No recommendations — just facts with quotes and file locations.
