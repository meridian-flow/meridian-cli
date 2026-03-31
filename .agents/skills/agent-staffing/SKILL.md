---
name: agent-staffing
description: Team composition for design and implementation phases — which agents to spawn, how many, what can run in parallel, and how to scale effort to complexity.
---

# Agent Staffing

Compose the right team for each phase. Two questions drive most staffing decisions: how much surface area does the change touch, and how reversible are mistakes if something goes wrong?

## Design Phase

Design staffing depends on uncertainty more than implementation volume.

- **Architects** own structural design, boundaries, interfaces, and tradeoff evaluation for candidate approaches.
- **Researchers** gather external context: ecosystem best practices, constraints from dependencies, and prior art that can reduce design risk.
- **Explorers** investigate the current codebase so design decisions reflect real code paths and integration points instead of assumptions.

One architect is usually enough when the problem is constrained and the tradeoffs are obvious. Staff multiple architects when there are materially different viable approaches, high-cost mistakes, or conflicting non-functional goals (for example, latency vs maintainability).

## Coders

One coder per phase — multiple coders on the same files create merge conflicts and duplicated work. If a phase feels too big for one coder, the plan needs splitting. Pick the coder variant that matches the work: `coder` for backend/infrastructure, `frontend-coder` for UI.

## Refactorer

The `refactor-reviewer` is a structural reviewer, not an executor. It identifies refactoring opportunities — tangled dependencies, mixed concerns, poor naming, coupling — and reports specific recommended moves. Use it to get a structural health assessment:

- After implementation phases, to spot structural debt before it compounds.
- When reviewers flag SOLID violations or abstraction drift, to get a deeper structural analysis.
- Proactively before major new work in messy areas, to understand what cleanup would help.

The refactor-reviewer reports findings with recommended moves. Spawn a coder to execute the ones worth acting on.

## Reviewers

Reviewers catch what testing can't — design drift, subtle correctness issues, architectural erosion. The value of multiple reviewers comes from different focus areas giving you different perspectives, not from redundant coverage of the same thing.

Changes that are hard to reverse (API contracts, schemas, public interfaces) or that set patterns future code will follow benefit from more review depth and model diversity. Changes that are easy to revert and well-understood need less. A reviewer on a fast model scanning for mechanical issues (naming, dead code, style) runs cheaply in parallel with deeper reviews.

Focus areas to draw from: SOLID and design quality, direction alignment with the design spec, security and trust boundaries, testing coverage and edge cases, code reduction and simplification, concurrency and state management. Not all apply to every change — pick the ones that match what could actually go wrong.

## Testers

Different testers cover different failure modes. Verification (tests, lints, type checks) is the baseline — it tells you whether the build is even healthy. Beyond that, match testing to what changed: smoke testing when user-facing behavior changed, unit testing when there's tricky logic or contracts between modules, browser testing when UI needs visual verification.

## Documenters

Decision rationale lives in conversations, not code. If nobody extracts it, it's lost when sessions end. The documenter spawned with `--from $MERIDIAN_CHAT_ID` mines conversations for decisions, pivots, and tradeoffs — then captures them in the FS mirror. Worth running when the phase involved significant decisions or discussions. Skip when the change is self-explanatory and no decisions were made.

## Backlog

Use the investigator in two modes. Primary mode is reactive bug investigation: when a failure, reviewer finding, or unexpected behavior is flagged, spawn investigator to validate root cause and either quick-fix or file/update a GH issue. Secondary mode is proactive backlog sweeps: spawn with `--from` at natural breakpoints (end of phase, after review) to mine conversations and code for deferred items. Keep proactive sweeps in the background so they do not block delivery.

## Parallelism

Think about what depends on what:

- Reviewers and testers both need finished code — they wait for the coder
- Reviewers and testers examine different dimensions — they can run simultaneously
- Documenters and investigators need the full picture — they run after review synthesis
- Within each category (all reviewers, all testers) there are no dependencies — fan them out

Cross-phase: when a phase depends on a prior phase, pass context forward with `--from` (prior spawn's report) or `-f` (output files) so the next coder has what it needs without re-discovering what already happened.
