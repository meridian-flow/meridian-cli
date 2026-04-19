# Feasibility Notes

## Summary

Local code inspection, upstream OpenCode docs, and the post-refactor reassessment suggest the main parity path is feasible, but not by treating OpenCode like Claude/Codex.

## What looks feasible

- Permission parity through OpenCode-native permission/config overlays rather than streaming launch flags.
- Effort parity by mapping Meridian effort to OpenCode model/variant/config semantics rather than inventing unsupported session payload fields.
- Streaming fork parity through dedicated OpenCode fork/session APIs instead of forcing fork into create-session payloads.
- MCP parity through config-defined MCP servers and per-session/per-agent tool selection.
- Skill parity through OpenCode-native discovery/config rather than only prompt injection.
- The best unifying mechanism appears to be `harness-native-profile-projection`: project Meridian intent into harness-native OpenCode profile/config state rather than continuing to chase CLI-flag parity.

Important constraint:
- Emitting `OPENCODE_PERMISSION` / `OPENCODE_CONFIG_CONTENT` is only partial progress. The current streaming projection still logs that permission resolver overrides are ignored, so parity remains unproven and likely incomplete on the live `opencode serve` path.

## What looks fragile today

- Session transcript lookup when the launch environment differs from the current shell environment.
- Report extraction for the live OpenCode terminal/event shape observed in smoke.
- Storage probing if OpenCode changes on-disk layout.
- Live model/provider fidelity between the requested OpenCode model and the exported session metadata.
- Live streaming continuation/fork behavior, which is currently worse than the older parity notes captured.

## Recommended implementation order

1. Design `harness-native-profile-projection` for OpenCode as the primary fix path.
2. Treat current config/permission overlay work as partial plumbing that can support that design, not as a closed item.
3. Validate live semantics before calling parity solved.
4. Fix or explicitly classify the real runtime mismatches:
   - model fidelity
   - live continue/fork behavior
   - effort mapping
   - permission semantics on streaming
   - report extraction
   - session lookup env persistence
5. Tighten docs and smoke cases so claims match actual verified OpenCode support.
6. Revisit lower-priority storage/report hardening once the MVP parity path is solid.

## Reassessment update

- `p1908` completed and showed:
  - live `opencode serve` sidecar behavior is real
  - effort is still ignored on streaming
  - live continuation lost session context
  - live fork hung / remained queued
  - report extraction surfaced terminal `session.idle` instead of assistant text
  - exported session metadata did not preserve the requested provider/model in the observed runs
- `p2137` confirmed the launch-core refactor fixed the config/permission projection story and narrowed the remaining gaps to runtime fidelity and readback behavior.
  Correction: the refactor added config/permission projection machinery, but did not prove equivalent live permission behavior on streaming.
