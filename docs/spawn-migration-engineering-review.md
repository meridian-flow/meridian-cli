# Spawn Migration Engineering Review Report

## Purpose

Provide a focused review guide for the Spawn -> Spawn domain migration, including plan pointers and the key decisions that need engineering sign-off.

## Plans and Specs to Review

1. Primary rename plan (updated):
   - `~/.claude/plans/luminous-baking-oasis.md`
2. Broader implementation plan (legacy context, still referenced):
   - `plans/new-philosophy/implementation/plan.md`
3. Target CLI specs:
   - `_docs/cli-spec-agent.md`
   - `_docs/cli-spec-human.md`
4. Terminology contract:
   - `docs/developer-terminology.md`

## What Engineering Should Review

1. Domain boundary and naming policy
   - Confirm public/domain surfaces move to `spawn` terminology.
   - Confirm low-level process-execution internals may keep `run` only when purely mechanical.

2. Space scoping policy
   - Confirm target policy: no auto-create on spawn.
   - Ensure explicit context is required (`MERIDIAN_SPACE_ID` or `--space`) across CLI and MCP paths.
   - Verify error text and docs consistently reflect explicit context requirements.

3. Command/tool surface decisions
   - Confirm target CLI command family (`spawn`, `spawn list/show/wait/continue/stats`).
   - Confirm MCP rename mapping (`run_*` -> `spawn_*` target names).
   - Confirm `grep` behavior decision is final (deleted vs hidden); docs/plans should not conflict.

4. Rename coverage completeness
   - Validate all high-impact surfaces are in scope: operation registry names, CLI help text, built-in agent profile MCP tool names, stream protocol event labels, runtime error guidance, and state path/file naming.

5. Rollout and compatibility
   - Decide whether temporary aliases are required (`run.*` + `spawn.*` coexistence window).
   - Define removal point for compatibility aliases and required downstream updates.

6. Test and verification strategy
   - Ensure tests explicitly cover:
     - explicit space requirement (no auto-create)
     - agent-mode vs human-mode help surfaces
     - MCP tool naming and parity
     - stale `run_*` user-facing identifiers scan

## Recommended Reviewer Sequence

1. Review terminology/spec docs first (`docs/developer-terminology.md`, `_docs/cli-spec-*.md`).
2. Review plan consistency between `luminous-baking-oasis.md` and `plans/new-philosophy/implementation/plan.md`.
3. Approve policy deltas (explicit space, grep behavior, compatibility window).
4. Only then approve implementation slices.

## Current Known Tension to Resolve

- `plans/new-philosophy/implementation/plan.md` contains auto-create guidance for `run spawn`, while the updated rename plan and specs now target explicit space context with no auto-create fallback.
- Engineering should pick one policy as canonical before execution continues.
