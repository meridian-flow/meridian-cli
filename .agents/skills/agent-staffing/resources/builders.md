# Builders

Agents that produce artifacts — code, design docs, research findings, and captured decisions.

## Coders

**coder** — production code writer for backend and infrastructure. Implements scoped tasks from phase blueprints. One coder per phase — multiple coders on the same files create merge conflicts and duplicated work. If a phase feels too big for one coder, splitting the plan is better than parallelizing coders. The exception is when phases touch cleanly disjoint file sets, determined at plan time — then coders can run in parallel across phases.

**frontend-coder** — production frontend code writer. Same staffing rules as coder — one per phase, split the plan if it's too big. Pick this variant when the work is primarily UI implementation.

## Design Exploration

Scale design staffing to uncertainty, not implementation volume.

**architect** — structural design, boundaries, interfaces, and tradeoff evaluation. One architect is usually enough when the problem is constrained and the tradeoffs are obvious. Staff multiple architects when there are materially different viable approaches, high-cost mistakes, or conflicting non-functional goals.

**researcher** — gathers external context: ecosystem best practices, constraints from dependencies, library comparisons, and prior art. Research is high-throughput information gathering, not deep reasoning — use fast, cheap models and spawn multiple in parallel if needed.

**explorer** — investigates the current codebase so design decisions reflect real code paths and integration points instead of assumptions. Cheap and high-throughput.

## Documentation

**documenter** — mines conversations for decisions, pivots, and tradeoffs, then captures them in persistent artifacts. Decision rationale lives in conversations and gets lost after compaction — if nobody extracts it, future agents re-derive decisions that were already made, wasting cycles and risking different conclusions. Run after phases that involved significant decisions, which is most phases.
