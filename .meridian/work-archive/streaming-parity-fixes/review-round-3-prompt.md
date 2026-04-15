# Design Review — Streaming Parity v2, Revision Round 3 (Coordinator Reframe)

## Context

The streaming-parity-fixes work is a v2 redesign of meridian's harness launch path. Round 1 produced 37 fixes, round 2 added 10 structural polish fixes, and **round 3 is a reframe**: Meridian is a **coordinator, not a policy engine**. Round 3 drops user-input policing that v2 had accumulated (reserved-flag stripping, MCP forbidden-prefix guards, PermissionConfig combination validators, harness-aware resolver) and instead codifies nine **keeper invariants (K1–K9)** that protect *internal consistency* — the things only meridian can enforce.

Your job is to review whether round 3 actually delivers the reframe cleanly, whether K1–K9 are enforceable as specified, and whether the artifacts are self-consistent across all seven design docs, `decisions.md`, and `scenarios/`.

This is a **design review**, not a code review. Nothing has been implemented yet.

## Read Order

Start here, in this order:

1. `.meridian/work/streaming-parity-fixes/design/overview.md` — guiding principle, goals, K1–K9 summary, out-of-scope policing
2. `.meridian/work/streaming-parity-fixes/decisions.md` — scroll to "Revision Pass 3 (post p1433/p1434/p1435)" section; this has H1–H17 entries covering what was dropped (H1–H3), restored (H4–H5), kept (H6–H14 = K1–K9), and clarified (H15–H17)
3. `.meridian/work/streaming-parity-fixes/design/typed-harness.md` — most of K1–K9 lands here: `HarnessBundle`, `register_harness_bundle`, `(harness_id, transport_id)` dispatch, `HarnessExtractor`, Protocol/ABC reconciliation, cancel/interrupt/SIGTERM table
4. `.meridian/work/streaming-parity-fixes/design/launch-spec.md` — per-adapter `handled_fields` sets, `_enforce_spawn_params_accounting`, restored `mcp_tools` on base
5. `.meridian/work/streaming-parity-fixes/design/transport-projections.md` — `mcp_tools` per-harness projection, eager import bootstrapping, verbatim passthrough policy, soft 400-line budget
6. `.meridian/work/streaming-parity-fixes/design/permission-pipeline.md` — frozen `PermissionConfig`, harness-agnostic `PermissionResolver.resolve_flags()`, deleted reserved-flags section, fail-closed rule (D20)
7. `.meridian/work/streaming-parity-fixes/design/runner-shared-core.md` — `RuntimeContext.child_context()` as sole `MERIDIAN_*` producer, `merge_env_overrides` invariant, narrowed parity contract (deterministic subset)
8. `.meridian/work/streaming-parity-fixes/design/edge-cases.md` — E39–E49 cover new invariants; E37 is retired
9. `.meridian/work/streaming-parity-fixes/scenarios/overview.md` — S001–S051 master index (S037 retired, S039–S051 added)

Then drill into specific scenarios as needed. The 13 new ones (S039–S051) are the ones that verify the K1–K9 claims.

## What to Evaluate

## Your Focus Area

{{FOCUS}}

## Common Ground (all reviewers)

- Is the coordinator reframe actually delivered, or did some old policing survive by accident?
- Are K1–K9 each enforceable by a concrete, *mechanical* check — not a documented convention that a future coder could forget?
- Is the design self-consistent: if two docs describe the same type or invariant, do they agree byte-for-byte?
- Does every edge case in `design/edge-cases.md` have a scenario, and does every scenario trace back to a design statement?
- Are there enforcement gaps — claims the design makes that no scenario verifies, or scenarios that verify things the design doesn't actually commit to?
- Does the design say something it shouldn't — any residual user-input policing, combination validators, string-prefix guards, or "refuse spawn for unexpected user input" logic?

## Deliverable

Produce a review report with:

- **Verdict:** `approve`, `approve-with-nits`, `changes-required`, or `block`
- **Strengths:** what the reframe got right
- **Findings:** numbered list, each with:
  - Severity (`blocker`, `major`, `minor`, `nit`)
  - Which file and section (or which K# / scenario ID) it concerns
  - What the issue is
  - Suggested fix (concrete — either a specific edit or a specific alternative to consider)
- **Coverage gaps:** design claims without scenarios, or scenarios without design anchors
- **Self-consistency:** any places where two docs or one doc and a scenario disagree

Do not edit the design docs. Report findings only.

Report back when done.
