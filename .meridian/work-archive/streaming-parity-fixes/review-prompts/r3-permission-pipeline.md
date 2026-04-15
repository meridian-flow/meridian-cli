# Review — streaming-parity-fixes v2 design, permission pipeline focus

You are reviewing the **v2 design** for streaming adapter parity. Your focus is the permission flow end-to-end — the same dimension where p1411 found H1 (Codex sandbox/approval silently dropped), H3 (`cast("PermissionResolver", None)` at two call sites), and L6 (ad-hoc `.config` getattr fallback). This is a security-adjacent area — the sandbox mode is a production safety boundary.

## Your focus area

**Permission pipeline correctness.** Specifically:

1. **Non-optional `PermissionResolver`.** Is the type truly non-optional everywhere? Grep the design for any place where `perms: PermissionResolver | None` lingers. Can a caller reintroduce `cast("PermissionResolver", None)` without a reviewer catching it? Is there a lint or test that proves no such cast exists in `src/`?
2. **`.config` as required Protocol member.** Does the Protocol actually enforce `config: PermissionConfig` at class definition time? What happens if a user writes a resolver that forgets to set `config` but has a `config` attribute assigned in `__init__`? Does `runtime_checkable` help here or create a false sense of safety?
3. **Codex sandbox/approval on the wire.** Does the v2 design unambiguously describe **how** the projection reads `spec.permission_resolver.config.sandbox` and `.config.approval`, and **what exact wire format** it emits for `codex app-server` — AND does D20 correctly require the coder to probe `codex app-server --help` before committing to flag names? What happens if the probe reveals the flags don't exist?
4. **`NoOpPermissionResolver` opt-out semantics.** Is the construction-time warning loud enough? Is the class's name self-documenting? Could a developer accidentally use it as a default without noticing? Does it need to be behind a feature flag or log at WARNING level always?
5. **Approval mode matrix.** Is every cell of the `sandbox ∈ {default,read-only,workspace-write,danger-full-access}` × `approval ∈ {default,auto,yolo,confirm}` matrix correctly specified — including the "default" behavior where Codex applies its own default? Is there a test that asserts every cell produces a distinct wire command?
6. **Confirm-mode rejection event.** Is D14's ordering guarantee (event enqueue BEFORE JSON-RPC error response) actually achievable given the async write contract? Could a subscriber race the handler and miss the event?
7. **Parent Claude permission forwarding (`CLAUDECODE`).** Is the merge → dedupe → projection flow really identical between subprocess and streaming? Is there a dimension where they diverge (env scrubbing, order of merge, handling of empty arrays) that the design missed?

## What to read

- `.meridian/work/streaming-parity-fixes/design/permission-pipeline.md` (primary)
- `.meridian/work/streaming-parity-fixes/design/transport-projections.md`
- `.meridian/work/streaming-parity-fixes/design/launch-spec.md`
- `.meridian/work/streaming-parity-fixes/decisions.md` (D4, D8, D11, D14, D15, D20)
- `.meridian/work/streaming-parity-fixes/scenarios/S003`, `S004`, `S007`–`S014`, `S016`, `S025`, `S032`
- `.meridian/spawns/p1411/report.md` (findings H1, H2, H3, L6, M9)
- Current source:
  - `src/meridian/lib/harness/connections/codex_ws.py`
  - `src/meridian/lib/harness/launch_spec.py`
  - `src/meridian/lib/launch/streaming_runner.py` (H3 site at line 457)
  - `src/meridian/lib/app/server.py` (H3 site at line 203)

## Deliverable

Findings with severity, file references, concrete attack / regression scenarios the gap enables, and suggested fixes.

A CRITICAL finding is: a permission control surface that v2 still lets drop silently. H1 (Codex sandbox silently ignored) was the single most important bug in p1411 — if there is any path in v2 where a similar silent drop is possible, call it out.

End with an overall verdict: **Converged / Needs revision / Reject and redesign**.
