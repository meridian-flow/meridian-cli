# R06 Retry — Structural / Refactor Review

Read `r06-retry-context-brief.md` first. That is the shared ground truth — do not re-derive it.

## Your Focus

You are the **refactor reviewer**. Look at structural health of the launch subsystem across the current R06 skeleton state. Your angle is different from the design-alignment reviewer:

- Design-alignment asks "does the code realize the intended hexagonal shape?"
- You ask "is this the right shape to have intended in the first place, and what structural debt would any refactor here inherit?"

## Question to Answer

> Is `PreparedSpawnPlan` the barrier — and only that — or are there deeper structural issues that will keep biting no matter how R06 lands? Is there a simpler shape for this subsystem than hexagonal?

## What to Read

1. All of `src/meridian/lib/launch/` — every file, at least skim
2. `src/meridian/lib/harness/adapter.py` — the ports
3. The three driving adapters:
   - `src/meridian/lib/launch/plan.py` + `src/meridian/lib/launch/process.py` + `src/meridian/lib/ops/spawn/prepare.py` (primary)
   - `src/meridian/lib/launch/streaming_runner.py` (worker)
   - `src/meridian/lib/app/server.py` + `src/meridian/cli/streaming_serve.py` (app)
4. The three driven adapters (session-id + command-building stances):
   - `src/meridian/lib/harness/claude.py`
   - `src/meridian/lib/harness/codex.py`
   - `src/meridian/lib/harness/opencode.py`
5. `src/meridian/lib/safety/permissions.py` — `TieredPermissionResolver`
6. `.meridian/work/workspace-config-design/design/refactors.md` — skim sections touching launch

## What to Produce

A markdown report at `$MERIDIAN_WORK_DIR/reviews/r06-retry-structural.md` with:

### 1. Structural health signals
Apply `dev-principles` structural signals. Which fire? File:line evidence.
- Modules > 500 lines or mixed responsibilities
- Import fanout and coupling
- Abstractions accumulating conditionals to fit new cases
- "Add one variant → edit N files" where N is high

### 2. Responsibility map
For each file in `launch/`: what is it responsible for? Where does its responsibility overlap another file's? Is the split correct or accidental?

### 3. Alternative shapes
If you were designing this from scratch today, which shape would you pick, and why?
- **Hexagonal with reshaped DTO** — current intent with the barrier removed
- **Pipeline / staged functions** — typed input → stage → typed intermediate → stage → typed output
- **Command pattern** — `LaunchCommand` objects carrying self-execution logic
- **Effect system** — pure composition returning an effect description, interpreter runs it
- **Builder pattern** — `LaunchBuilder().with_profile().with_sandbox().build()`
- **Plain function composition** — kill the abstractions, let the three drivers call ~10 small pure functions directly
- **Something else**

Rough sketch (not full design) of your top pick on this domain. Keep it ~20 lines of signature-only pseudocode.

### 4. Deep issues regardless of shape
What structural debt exists *upstream* of R06 that will re-surface no matter how R06 lands? (Example: the `PreparedSpawnPlan` vs `SpawnParams` vs `SpawnRequest` distinction itself, or the fact that session-id observation has to happen post-launch and can't be part of composition.)

### 5. Verdict
Pick one:
- **dto-reshape-is-enough** — `PreparedSpawnPlan` is the only structural barrier; reshape it and ship.
- **shape-change-needed** — the hexagonal frame itself is wrong for this domain. Recommend alternative from §3.
- **deeper-upstream-issue** — real problem is upstream of R06 (e.g. in `harness/adapter.py` shape); name it.

## Style

Caveman full. Structural signals as lists, not paragraphs. Code pointers exact.

## Termination

Report path + verdict.
