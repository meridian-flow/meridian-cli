# Phase 1 Verifier Brief

Verify the completed launch-core-cleanup implementation.

You are not alone in repo. Do not revert others' work. Fix only mechanical verification breakage if needed.

Goals:
- Run `uv run ruff check .`
- Run `uv run pyright`
- Run targeted tests for touched launch/spawn/process surfaces
- Run broader tests as needed if targeted coverage is insufficient or failures imply wider breakage

Focus files and artifacts:
- `.meridian/work/launch-core-cleanup/requirements.md`
- `.meridian/invariants/launch-composition-invariant.md`
- `.meridian/work/launch-core-cleanup/plan/pre-planning-notes.md`
- `.meridian/work/launch-core-cleanup/plan/phase-1-launch-core-cleanup.md`

Report:
- exact checks run
- pass/fail results
- files changed, if any
- substantive issues back to orchestrator if verification exposes real behavioral problems
