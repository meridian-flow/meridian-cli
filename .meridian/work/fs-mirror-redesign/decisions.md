# Decisions — fs/ Mirror Redesign

## fs/ is a domain-structured codebase mirror
fs/ serves agents, not humans. Compressed, navigable, domain-scoped. Each doc covers what exists, how it works, why it's that way. The "why" is the highest-value content — code shows what, but design rationale is invisible without it.

## Domain-based, not source-path-based
`fs/harness/` not `fs/lib/harness/`. Mirrors the conceptual architecture so agents navigate by concept. Decoupled from source tree refactors.

## Hierarchical SRP documentation
Each doc covers ONE coherent concept (single responsibility). Domains contain an overview doc that orients plus topic docs that go deep. Cross-references between domains rather than re-explaining.

## No research in fs/
Research is work-scoped ($MERIDIAN_WORK_DIR). Lasting findings get synthesized into domain docs. Raw research gets archived with the work item. The distinction: research is investigation, the mirror is synthesized knowledge.

## Three documentation layers
- fs/ ($MERIDIAN_FS_DIR) — agent-facing codebase mirror
- docs/ — user-facing documentation (CLI reference, guides)
- $MERIDIAN_WORK_DIR — work-scoped artifacts including research

## Generic methodology, project-specific domains
meridian-dev-workflow/ encodes HOW to structure a mirror (hierarchical SRP, domain-based). The specific domain tree (harness/, state/, catalog/ etc.) is project-specific. Code-documenter discovers domains from existing fs/ structure and project docs, not from its own profile.

## Documentation is separate from implementation
impl-orchestrator ships verified code. Documentation is a different concern with a different orchestrator. Mixing them makes impl longer, blocks impl completion on doc failures, and conflates two different review dimensions (code correctness vs doc accuracy).

## Documentation is multi-step (needs an orchestrator)
The documentation phase is a write/review/fix loop: fan out documenters → fan out reviewers checking docs against source code → fix accuracy issues → commit. We proved this empirically in this session — 3 documenters produced docs with real accuracy issues (wrong execution paths, invented status values, stale capability flags, wrong CLI commands) that 3 reviewers caught and fixers resolved. Single-shot documentation isn't reliable.

## Accuracy against source code is the critical review dimension
Doc reviewers must verify claims against actual code, not just check for readability. The review findings in this session were all factual errors invisible without reading source.

## Decision mining is part of documentation
Conversations contain decisions that don't make it into code — why an approach was chosen, what was rejected, constraints discovered mid-implementation. The docs-orchestrator should mine conversation history so this context survives compaction.
