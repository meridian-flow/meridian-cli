---
name: agent-staffing
description: Team composition for design and implementation phases — which agents to spawn, how many, what can run in parallel, and how to scale effort to complexity. Use when composing a team for a phase, choosing review focus areas, or calibrating effort.
---

# Agent Staffing

Compose the right team for each phase. Two questions drive most staffing decisions: how much surface area does the change touch, and how reversible are mistakes if something goes wrong?

## Model Selection

Run `meridian models list` to see available models. Models with descriptions indicate their strengths — use these to match models to tasks. Override agent profile defaults with `-m` when a different model is a better fit for the specific work.

## Design Phase

Design staffing depends on uncertainty more than implementation volume.

- **Architects** own structural design, boundaries, interfaces, and tradeoff evaluation for candidate approaches.
- **Researchers** gather external context: ecosystem best practices, constraints from dependencies, and prior art that can reduce design risk.
- **Explorers** investigate the current codebase so design decisions reflect real code paths and integration points instead of assumptions.

One architect is usually enough when the problem is constrained and the tradeoffs are obvious. Staff multiple architects when there are materially different viable approaches, high-cost mistakes, or conflicting non-functional goals (for example, latency vs maintainability).

## Coders

Default to one coder per phase — multiple coders on the same files tend to create merge conflicts and duplicated work. If a phase feels too big for one coder, splitting the plan is usually better than parallelizing coders. The exception is when phases touch cleanly disjoint file sets. Pick the coder variant that matches the work: `coder` for backend/infrastructure, `frontend-coder` for UI.

## Reviewers

Reviewers catch what testing can't — design drift, subtle correctness issues, architectural erosion. The value of multiple reviewers comes from different focus areas and different models, not redundant coverage.

**Choosing focus areas.** The change itself tells you what perspectives matter — think about what could go wrong that testing won't catch. Common dimensions: concurrent state and races, security and trust boundaries, module structure and abstraction quality, correctness and contract compliance, design alignment (does implementation match intent?). Not all apply to every change — pick the ones that match what could actually go wrong.

**Model diversity.** Fan out reviewers across different models, not just different focus areas. Different models have different blind spots — using the same model for every reviewer gives you N copies of the same perspective.

**Review agents.** Different agents serve different review purposes:
- **reviewer** — adversarial code analysis with a specified focus area. Read-only.
- **refactor-reviewer** — structural review for tangled dependencies, mixed concerns, coupling. Read-only — reports findings with recommended moves.
- **verifier** — build health gate. Runs tests, type checks, lints. Fixes mechanical breakage, reports substantive failures.
- **investigator** — root-cause triage. Spawn when a test fails unexpectedly or a reviewer flags something needing deeper analysis.

**Calibrating effort.** Scale review to the risk:
- **Low risk** (internal refactor, well-tested area) — one reviewer, fast model, quick pass.
- **Medium risk** (new feature, moderate complexity) — two reviewers with different focus areas.
- **High risk** (security-sensitive, concurrent, public API) — two or three reviewers on strong models with different focus areas.

**Synthesizing findings.** Fix valid findings — agents are cheap. The only findings to skip are ones the reviewer got wrong. When reviewers disagree, you have context they don't — make the call and record it in the decision log. Keep iterating while reviewers surface real issues; stop when they come back clean. If reviews aren't converging, that's a signal the design has a structural problem — investigate or escalate.

## Testers

Different testers cover different failure modes. Verification (tests, lints, type checks) is the baseline. Beyond that, match testing to what changed: smoke testing when user-facing behavior changed, unit testing when there's tricky logic or contracts between modules, browser testing when UI needs visual verification.

## Documenters

Decision rationale lives in conversations, not code. If nobody extracts it, it's lost when sessions end. The documenter mines conversations for decisions, pivots, and tradeoffs — then captures them in the FS mirror. Worth running when the phase involved significant decisions. Skip when the change is self-explanatory.

## Backlog

Use the investigator in two modes. Reactive: when a failure or unexpected behavior is flagged, spawn to validate root cause and either quick-fix or file a GH issue. Proactive: spawn at natural breakpoints to mine conversations and code for deferred items. Keep proactive sweeps in the background so they don't block delivery.

## Parallelism

Think about what depends on what:

- Reviewers and testers both need finished code — they wait for the coder
- Reviewers and testers examine different dimensions — they can run simultaneously
- Documenters and investigators need the full picture — they run after review synthesis
- Within each category (all reviewers, all testers) there are no dependencies — fan them out

See `/context-handoffs` for how to pass context between phases.
