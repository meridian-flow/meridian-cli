# Maintainers

Agents that keep the project healthy — extracting decisions before they're lost, updating documentation to match reality, surfacing deferred issues before they compound. These don't build new features or review code; they maintain the connective tissue that lets future agents (and humans) work effectively.

## Documentation

**code-documenter** — maintains the internal knowledge layer: compressed architecture mirror in `$MERIDIAN_FS_DIR`, code comment accuracy, and decision rationale captured from conversations. The FS mirror is what agents read to understand the codebase without reading every source file — when it drifts, every downstream agent makes decisions on stale information. Run after phases that change architecture, module boundaries, or data flows. Also mines conversation transcripts for decisions that don't make it into code.

**tech-writer** — maintains user-facing documentation: getting started guides, CLI reference, API contracts, tutorials, and integration docs. Adapts to audience level from non-technical overview to developer reference. Run when features ship, APIs change, or users report confusion. Verifies docs against current code — stale user docs destroy trust.

## Issue Mining

**investigator** — surfaces problems before they compound. Two modes:

- **Proactive backlog sweeps** — mines conversations, code, and spawn reports for deferred items, latent bugs, TODO debt, and unresolved questions at phase boundaries. These items are invisible in the code and lost from conversations after compaction — if nobody extracts them at phase boundaries, they accumulate silently.
- **Reactive investigation** — digs into root cause when a test fails unexpectedly, a reviewer flags something ambiguous, or a spawn produces surprising results. Either quick-fixes the issue, files it for tracking, or closes it as a non-issue with reasoning.
