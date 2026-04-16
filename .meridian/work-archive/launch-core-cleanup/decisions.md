# Decisions

## 2026-04-16 - Single cleanup phase

Choice: execute launch-core-cleanup as one implementation phase.

Why:
- Core violations share same composition seam across `src/meridian/lib/launch/context.py`, `src/meridian/lib/ops/spawn/prepare.py`, `src/meridian/lib/ops/spawn/execute.py`, `src/meridian/lib/launch/streaming_runner.py`, and `src/meridian/lib/launch/command.py`.
- Splitting would create serial dependency and churn on same files with little parallel benefit.
- Requirements already define target state via invariants; no open design branch remains.

Alternatives rejected:
- Multi-phase split by priority. Rejected because P1/P2/P3/P4 overlap same launch DTO/factory boundary and would likely conflict.

## 2026-04-16 - Reviewer model policy

Choice: use only `gpt-5.4` for reviewer lanes.

Why:
- User explicitly tightened review quality requirement mid-run.
- Review asks for semantic invariant compliance, consistency, and DRY across coupled launch code; stronger model justified.

Alternatives rejected:
- `gpt-5.4-mini` review fan-out. Rejected per user instruction.
