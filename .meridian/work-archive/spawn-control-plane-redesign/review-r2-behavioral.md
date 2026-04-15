# v2r2 Design Review — Behavioral Correctness & Spec-Architecture Alignment

You are reviewing the v2r2 revision of the spawn control plane design package. This is the second review round; v2r2 addresses all findings from the first round (p1794 gpt-5.4, p1795 opus).

## Your Focus Areas

1. **Behavioral correctness**: Do the EARS statements in spec/ fully cover the requirements? Are there gaps, ambiguities, or contradictions between spec leaves?

2. **Spec-architecture alignment**: Does every spec EARS statement have a clear realization in the architecture/ tree? Does the architecture introduce behavior not specified? Are the test plans sufficient to verify each leaf?

3. **v2r2 revision correctness**: The following changes were made in response to first-round findings. Verify each is correctly propagated:
   - D-03 revised: two-lane cancel (SIGTERM for CLI, in-process for app). Was unified SIGTERM; reviewers blocked due to external-SIGTERM targeting problem.
   - D-13 revised: SIGKILL removed entirely. Was SIGKILL with finalizing re-check; reviewer identified TOCTOU race.
   - D-17 new: 400 vs 422 split. Schema validation → 422 (FastAPI), semantic validation → 400 (custom handler).
   - D-18 new: INJ-002 narrowed. Control socket ack ordering guaranteed; HTTP ack ordering NOT guaranteed; clients use inbound_seq.
   - D-19 new: Peercred failure → DENY. Was operator fallback; reviewers flagged as fail-open.

4. **Decision log completeness**: Does decisions.md capture all non-obvious choices with reasoning, alternatives, and constraints?

## Review Protocol

- Rate each finding: blocker / major / minor / nit.
- A **blocker** means the design cannot proceed to planning without resolution.
- A **major** means significant risk but addressable during implementation.
- For each finding, cite the specific file and EARS ID or section.
- End with a verdict: APPROVE or REQUEST CHANGES.

## Files to Review

Read the following files in the design package at `$MERIDIAN_WORK_DIR/design/`:
- `spec/overview.md` — entry point
- `spec/cancel.md` — CAN-001..CAN-008
- `spec/interrupt.md` — INT-001..INT-007
- `spec/inject.md` — INJ-001..INJ-006
- `spec/liveness.md` — LIV-001..LIV-005
- `spec/http_surface.md` — HTTP-001..HTTP-006
- `spec/authorization.md` — AUTH-001..AUTH-007
- `architecture/overview.md` — architecture entry point
- `architecture/cancel_pipeline.md` — SignalCanceller two-lane
- `architecture/interrupt_pipeline.md`
- `architecture/inject_serialization.md`
- `architecture/liveness_contract.md`
- `architecture/http_endpoints.md`
- `architecture/authorization_guard.md`
- `refactors.md` — refactor agenda and phase hints

Also read the decisions log:
- `$MERIDIAN_WORK_DIR/decisions.md` — D-01..D-19

And the requirements for context:
- `$MERIDIAN_WORK_DIR/requirements.md`
