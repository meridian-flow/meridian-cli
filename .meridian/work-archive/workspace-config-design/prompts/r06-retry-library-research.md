# R06 Retry — 3rd-Party Library & Pattern Research

Read `r06-retry-context-brief.md` first. That is the shared ground truth — do not re-derive it.

## Your Focus

You are the **internet researcher**. The user asked whether 3rd-party libraries could collapse this whole subsystem. Your job is to find out.

## The Shape Problem (Distilled)

Python subsystem with these characteristics:
- 3 driving entry points (CLI primary launch, background worker, HTTP app server) that must share composition logic
- Composition = policy resolution + permission pipeline + env building + command building + fork materialization + session-id observation
- Driven side is 3 harness adapters (Claude, Codex, OpenCode) with different session-id observation mechanisms (PTY stdout parsing, filesystem polling, inline extraction)
- Input inconsistency: different driving entry points have different pre-shapes (CLI args vs HTTP request body vs background-spawn spec), and today each resolves policies/permissions itself before handing a pre-composed `PreparedSpawnPlan` to a "factory" that can't compose what's already composed
- Requirement: composition logic must be **behaviorally testable** directly (construct factory, pass raw inputs, assert output) — not just integration-testable through the drivers
- Runtime: single-process, `asyncio`-capable but not required, no containerization for core tests
- Existing tech: pydantic BaseModel for DTOs, pyright strict mode, pytest
- Constraint: minimum total complexity (including library code owned transitively) per `dev-principles`

## Question

What exists in the Python ecosystem that could meaningfully simplify this, and where does rolling-your-own still win?

## What to Investigate

For each candidate, investigate:
- Active maintenance (commits in last 6mo, open issue responsiveness)
- API shape vs the problem shape (does it fit, or does it force a different problem?)
- Transitive deps and total LOC owned
- Python version compatibility (we're on whatever the project is — check `pyproject.toml`)
- Real-world usage patterns in comparable subsystems
- How it interacts with pyright strict / pydantic frozen models

### Candidates to check at minimum

1. **`dishka`** — DI container, scope-based, cited as modern Python DI
2. **`dependency-injector`** — classic Python DI container
3. **`punq`** — minimal DI container
4. **`inject`** — lightweight DI
5. **`returns`** — functional Result/IO/Future types; could replace sum-type-by-hand
6. **`attrs`** + builders — alternative to pydantic for factory-friendly DTOs
7. **`pydantic` discriminated unions + validators** — could we get the factory shape via pydantic's own machinery?
8. **`functools.singledispatch`** / **`multidispatch`** for the driven-adapter dispatch
9. **`immutables.Map`** or similar for the `LaunchContext` carrier
10. **Hexagonal architecture reference repos** — any canonical Python reference? Look for repos with README titles like "hexagonal Python" / "ports and adapters Python"
11. **Clean Architecture / Cosmic Python** patterns — Harry Percival's book and similar
12. **Factory patterns that are behaviorally testable** — search for "testable composition root python"

### Meta-questions

- Is there any library that specifically solves "I have 3 entry points that need to share composition, with testable factory output"?
- Is there a pattern name for this specific failure we hit (composition-root-with-pre-resolved-inputs)?
- What do mature Python projects (e.g., `litestar`, `fastapi`, `django`, `temporal-python-sdk`) do at their composition root?

## What to Produce

A markdown report at `$MERIDIAN_WORK_DIR/reviews/r06-retry-library-research.md` with:

### 1. Shortlist (top 3)
Per library/pattern:
- Name + 1-line purpose
- API shape snippet (how the factory would look if adopted)
- Total complexity delta (LOC added to deps vs LOC deleted from our code) — rough estimate
- Where it wins, where it fails on our constraints
- Maintenance signal (last commit, contributor count, known alternatives)

### 2. Rejected candidates
Short list with 1-line rejection reason each.

### 3. Pattern recommendations (no library)
If no library cleanly wins: what pattern from the literature best fits? Reference real Python projects using it.

### 4. Verdict
- **adopt-library** — which one, and the rough adoption plan
- **roll-your-own-with-pattern** — which pattern, why no library wins
- **status-quo-works** — libraries/patterns don't help; the fix is the DTO reshape and nothing more

### 5. Evidence
Links to docs, GitHub repos, benchmark numbers, issue threads you cited.

## Style

Caveman full for the body. Links in full URLs. No marketing speak.

## Termination

Report path + verdict.
