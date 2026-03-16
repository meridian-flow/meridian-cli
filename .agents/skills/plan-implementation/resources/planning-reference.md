# Planning Reference

Detailed conventions for phase files, dependency graphs, sizing, and context selection. Reference this when you need specifics during planning.

Work setup and artifact placement come from `__meridian-work-coordination`. This file only defines how to structure planning artifacts that already live under `$MERIDIAN_WORK_DIR`.

## Phase File Conventions

### Naming

Format: `phase-{N}-{slug}.md`

- `{N}` is a sequential integer starting at 1. Renumber if you insert phases.
- `{slug}` is short kebab-case, under 4 words. Describes what the phase does, not what it touches.

Good: `phase-1-data-model.md`, `phase-3-auth-middleware.md`
Bad: `phase-1.md`, `phase-3-update-several-files.md`

### Structure

Each phase file covers these sections. Keep them proportional to the phase's complexity — a simple phase might need one sentence per section.

```markdown
# Phase {N}: {Title}

## Scope
What this phase implements and why. The coder reads this to understand
intent, not just tasks. Include enough "why" that the coder can make
good calls on ambiguous edge cases.

## Files to Modify
- `src/auth/middleware.py` -- add token validation
- `src/auth/models.py` -- new TokenClaims dataclass
- `tests/auth/test_middleware.py` -- new file, validation tests

## Dependencies
- Requires: Phase 1 (uses the TokenStore interface defined there)
- Independent of: Phase 3 (can run in parallel)

Include interface contracts from prior phases directly here. Don't
make the coder go read other phase files.

## Verification Criteria
- [ ] `uv run pytest tests/auth/` passes
- [ ] Token validation rejects expired tokens (test case exists)
- [ ] Type checking passes: `uv run pyright`

## Agent Headcount
- **Implementer:** `coder`, model: `codex`
- **Reviewers:** `reviewer-solid`, `reviewer-security`
- **Verifier:** yes

## Context Files
Files to pass as `-f` when spawning the coder:
- `$MERIDIAN_WORK_DIR/plan/phase-2-auth-middleware.md` (this file)
- `src/auth/existing_handler.py` (pattern to follow)
- `src/auth/token_store.py` (interface from Phase 1)

## Notes
Anything the coder should know: conventions to follow, known issues
to avoid, gotchas in the existing code.
```

## Dependency Graph Formats

Choose the format that fits your plan's complexity.

### Text tree -- for linear or lightly branching plans

```
Phase 1: Data Model
  +-> Phase 2: Repository Layer
  |     +-> Phase 3: API Handlers
  |           +-> Phase 5: Integration Tests
  +-> Phase 4: Error Handling (parallel with 2-3)
```

### Table -- for plans with significant parallelism

| Phase | Depends On | Can Parallel With |
|-------|-----------|-------------------|
| 1. Data Model | -- | -- |
| 2. Repository Layer | 1 | 4 |
| 3. API Handlers | 2 | 4 |
| 4. Error Handling | 1 | 2, 3 |
| 5. Integration Tests | 2, 3, 4 | -- |

### Execution groups -- for spawning

Derived from the dependency graph. Each group is a round of parallel work.

```
Round 1: Phase 1                  (sequential -- everything depends on it)
Round 2: Phase 2, Phase 4         (parallel -- both depend only on 1)
Round 3: Phase 3                  (depends on 2)
Round 4: Phase 5                  (depends on 2, 3, 4)
```

The number of rounds is your minimum sequential wall time. Fewer rounds means faster completion but more parallel agents.

## Right-Sizing Phases

### The core heuristic

Ask: "Can a single coder agent complete this in one session and produce a testable result?" If yes, it's the right size. If no, split it.

### Signs a phase is too big

- Touches more than ~10 files
- Requires understanding multiple unrelated subsystems
- Has internal dependencies (step A within the phase must finish before step B)
- You can't write concrete verification criteria because the scope is too diffuse
- You find yourself writing "and also..." multiple times in the scope

Split along the internal dependency boundary. The sub-phases often map to the "step A / step B" you were already thinking about.

### Signs a phase is too small

- Changes a single file with a straightforward modification
- Verification is trivial ("it compiles")
- The phase exists only because you felt every file change needed its own phase

Merge with an adjacent phase that touches related code. Two small related changes are easier to review together than separately.

### The 2-8 file guideline

Not a hard rule, but a useful smell test. Phases in this range tend to be coherent (small enough to hold in context) and substantial (enough to produce a meaningful, testable change).

## Context File Selection

When spawning the coder, pick `-f` references deliberately. Too few and the coder guesses at conventions; too many and it drowns in irrelevant context.

**Always include:**
- The phase spec itself (`plan/phase-N-slug.md`)
- Source files the coder will modify (so it sees current state)

**Include when relevant:**
- Interface definitions from prior phases (types, contracts the coder consumes)
- One example file that demonstrates the codebase's conventions for similar work
- The design overview, but only if the phase needs broad architectural context

**Leave out:**
- Other phase specs (the coder doesn't need to know the full plan)
- Test files for code that isn't changing in this phase
- Design rationale docs (decision-log, implementation-log)
- Files the coder won't touch and doesn't need to reference

Fewer, more relevant files beat a large pile of "might be useful" files.

## Tips

- **Don't create cleanup-only phases.** Bake cleanup into each phase. A "Phase 5: cleanup" means Phases 1-4 left messes, which means their scope was wrong.

- **Write verification criteria the verifier can actually check.** "Should work correctly" is not verifiable. "Tests pass, type checker clean, endpoint returns 401 for expired tokens" is verifiable. If you can't write a concrete check, the scope is probably too vague.

- **Plan for the review loop.** Each phase might take 1-3 fix-and-re-review cycles. Complex phases with concurrency or security concerns tend toward 3 cycles. Simple data model phases tend toward 1. Factor this into your time estimates.

- **Capture interface contracts early.** When Phase 1 produces an interface that Phase 3 consumes, write that interface into Phase 1's verification criteria ("interface X is defined and exported") and paste it into Phase 3's blueprint. This prevents Phase 3 from discovering the interface doesn't exist or has a different shape than expected.

- **Number phases by execution order, not importance.** Phase 1 runs first. If you reorder, renumber. The numbers are execution sequence, not priority ranking.
