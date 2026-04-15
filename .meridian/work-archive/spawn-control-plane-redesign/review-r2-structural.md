# v2r2 Design Review — Structural Soundness & Refactor Sequencing

You are reviewing the v2r2 revision of the spawn control plane design package. This is the second review round; v2r2 addresses all findings from the first round (p1794 gpt-5.4, p1795 opus).

## Your Focus Areas

1. **Structural soundness**: Is the module layout clean? Are responsibilities well-separated? Is coupling between components appropriate? Are there hidden dependencies or circular references?

2. **Refactor sequencing**: Does `refactors.md` correctly capture all structural prep needed? Are the phase dependencies accurate? Can the phases actually parallelize as claimed? Are there missing refactors that the architecture implies but the agenda doesn't list?

3. **Two-lane cancel architecture (D-03)**: The biggest structural decision. Evaluate:
   - Is the `SignalCanceller` dispatcher design clean? (Two private methods branching on `launch_mode`)
   - Is the cross-process HTTP cancel path (R-09) correctly sequenced?
   - Does the `manager: SpawnManager | None` constructor parameter create coupling problems?
   - Are there edge cases in the two-lane dispatch not covered by the test plan?

4. **Authorization guard integration (D-19)**: The `PeercredFailure` exception pattern — is it the right abstraction? Does it integrate cleanly with FastAPI's dependency injection? Are there surfaces that could accidentally bypass the deny-on-failure path?

5. **Existing codebase fit**: Does the architecture account for the actual source layout? Cross-reference with:
   - `src/meridian/lib/streaming/spawn_manager.py` — SpawnManager
   - `src/meridian/lib/launch/streaming_runner.py` — runner
   - `src/meridian/lib/app/server.py` — app server
   - `src/meridian/lib/state/spawn_store.py` — state schema
   - `src/meridian/lib/state/liveness.py` — PID-reuse guard

## Review Protocol

- Rate each finding: blocker / major / minor / nit.
- A **blocker** means the design cannot proceed to planning without resolution.
- A **major** means significant risk but addressable during implementation.
- For each finding, cite the specific file and section.
- End with a verdict: APPROVE or REQUEST CHANGES.

## Files to Review

Read the following files in the design package at `$MERIDIAN_WORK_DIR/design/`:
- `architecture/overview.md` — entry point
- `architecture/cancel_pipeline.md` — SignalCanceller two-lane
- `architecture/interrupt_pipeline.md`
- `architecture/inject_serialization.md`
- `architecture/liveness_contract.md`
- `architecture/http_endpoints.md`
- `architecture/authorization_guard.md`
- `refactors.md` — refactor agenda and phase hints

Also read the spec and decisions for cross-reference:
- `spec/overview.md`
- `spec/cancel.md`
- `spec/authorization.md`
- `$MERIDIAN_WORK_DIR/decisions.md`

And the source files listed above for codebase fit verification.
