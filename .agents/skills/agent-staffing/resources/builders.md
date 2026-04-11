# Builders

Agents that produce artifacts — code, design docs, research findings, and captured decisions.

## Coders

@coder — production code writer for backend and infrastructure. Implements scoped tasks from phase blueprints. One @coder per phase — multiple @coders on the same files create merge conflicts and duplicated work. If a phase feels too big for one @coder, splitting the plan is better than parallelizing coders. The exception is when phases touch cleanly disjoint file sets, determined at plan time — then @coders can run in parallel across phases.

@frontend-coder — production frontend code writer. Same staffing rules as @coder — one per phase, split the plan if it's too big. Pick this variant when the work is primarily UI implementation.

## Design Exploration

Scale design staffing to uncertainty, not implementation volume.

@architect — structural design, boundaries, interfaces, and tradeoff evaluation. One @architect is usually enough when the problem is constrained and the tradeoffs are obvious. Staff multiple @architects when there are materially different viable approaches, high-cost mistakes, or conflicting non-functional goals.

@internet-researcher — reads the internet so design decisions reflect what the ecosystem already knows: library behavior in production, known failure modes, upstream issue trackers, real-world usage patterns. The single most-forgotten delegation in the design loop — agents default to guessing from training data instead of verifying what's actually out there, and designs built on unverified assumptions are expensive to unwind. Staff liberally whenever the design depends on how something behaves upstream. Research is high-throughput information gathering, not deep reasoning — use fast, cheap models and spawn multiple in parallel if needed.

@explorer — the internal counterpart to @internet-researcher. Reads the current codebase so design decisions reflect real code paths and integration points instead of assumptions. Pair the two when the design crosses the boundary between "what we have" and "what the world has." Cheap and high-throughput.
