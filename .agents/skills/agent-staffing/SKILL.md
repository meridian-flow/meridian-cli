---
name: agent-staffing
description: Team composition for implementation phases — which agents to spawn, how many, what can run in parallel, and how to scale effort to complexity. Use when planning the agent team for a phase before spawning anyone.
---

# Agent Staffing

Compose the right team for each phase. Two questions drive most staffing decisions: how much surface area does the change touch, and how reversible are mistakes if something goes wrong?

## Coders

One coder per phase — multiple coders on the same files create merge conflicts and duplicated work. If a phase feels too big for one coder, the plan needs splitting. Pick the coder variant that matches the work: `coder` for backend/infrastructure, `frontend-coder` for UI.

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
