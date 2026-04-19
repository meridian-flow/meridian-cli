# Decisions

## 2026-04-16

Decision: treat the OpenCode compaction plugin as non-blocking and likely obsolete for this work item.

Why:
- Meridian's current runtime path for OpenCode is the local `opencode serve` sidecar plus HTTP session/message flow.
- The plugin is not required for normal spawn execution, report extraction, or session creation.
- Existing docs that still describe `.opencode/plugins/meridian.ts` appear to be stale rather than evidence of a missing launch prerequisite.

Alternatives considered:
- Treat plugin absence as a blocking parity gap.
  Rejected because the current implementation does not depend on it for the core OpenCode path.

## 2026-04-16

Decision: bias parity design toward OpenCode-native config and API surfaces rather than additional flag projection.

Why:
- OpenCode appears to expose rich config via environment/config overlays and a session/message server API.
- Several current gaps are caused by trying to map Meridian launch semantics onto a thinner flag surface than OpenCode actually uses.
- This direction aligns with the prior `managed-readonly-allowlist-parity` design intuition: use managed/config-style representations when the harness is config-first.

Alternatives considered:
- Continue extending CLI-flag parity only.
  Rejected because it does not fit MCP, permission policy, or fork semantics well on OpenCode.

## 2026-04-17

Decision: retire the older “OpenCode has no config/permission-style projection at all” framing from this work item, but do not treat parity as solved.

Why:
- The launch-core refactor now projects OpenCode workspace/config state via `OPENCODE_CONFIG_CONTENT`.
- The adapter also emits `OPENCODE_PERMISSION` when permission overrides are present.
- But the streaming projection layer still explicitly says permission resolver overrides are ignored, so env projection should be treated as partial plumbing, not completed parity.

Alternatives considered:
- Call config/permission parity fixed.
  Rejected because the current code only proves that env/config overlays are emitted, not that the live OpenCode streaming path enforces equivalent permission semantics.

## 2026-04-17

Decision: use `harness-native-profile-projection` as the intended path to full OpenCode parity.

Why:
- OpenCode is config-/agent-/session-driven enough that trying to finish parity via flag projection is the wrong seam.
- The recent refactor already moved Meridian partway toward env/config projection, but the remaining gap is semantic fidelity, not missing raw plumbing.
- A harness-native profile projection can express permission policy, agent shape, tool/MCP configuration, and model/profile defaults in the form OpenCode actually expects.

Alternatives considered:
- Continue patching individual OpenCode gaps one flag or payload field at a time.
  Rejected because it risks preserving the wrong abstraction boundary and repeating the same mismatch across permissions, skills, MCP, and model behavior.
