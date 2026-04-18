# Launch Seam Exploration

You are an @explorer. Map the two launch pipelines in meridian-cli and decide whether they should share a seam — and if so, at what depth — and whether a prep refactor is needed before the workspace-config design can land cleanly.

## Context

The workspace-config design (`.meridian/work/workspace-config-design/`) proposes a `HarnessWorkspaceProjection` interface (`R05` in `design/refactors.md`) wired into `src/meridian/lib/launch/context.py` as "the shared launch seam."

A reviewer just flagged that `launch/context.py` is only used by the **spawn** path (`meridian spawn ...`). The **primary** launch path (`meridian` invoked directly, not as a spawn) uses a different composition pipeline entirely: `launch/plan.py` + `launch/process.py` + `launch/command.py`.

If the two pipelines don't share a seam, either:
- Workspace projection gets implemented twice (duplication)
- Workspace projection applies only to spawns (spec regression)
- Or we prep-refactor the pipelines to share a seam first

You are doing the probing to decide which.

## Scope of exploration

### Pipeline A: Spawn path
- Entry: `meridian spawn ...`
- Composition seam: `src/meridian/lib/launch/context.py::prepare_launch_context()` around line 148–223
- Executor: `src/meridian/lib/ops/spawn/execute.py::execute_with_streaming()`
- Subprocess spawn: various harness connection files in `src/meridian/lib/harness/connections/`

### Pipeline B: Primary launch path
- Entry: `meridian` invoked directly (no `spawn` subcommand)
- Composition seams suspected: `src/meridian/lib/launch/plan.py`, `src/meridian/lib/launch/process.py`, `src/meridian/lib/launch/command.py`
- Subprocess spawn: currently unknown

Find the entry point for primary launch. Trace its command-building, env-building, cwd-resolution, and subprocess-spawn code paths end to end.

## Questions to answer

### Q1: What does each pipeline actually do?
For each pipeline, produce a numbered list of the composition steps it performs, in order. Be concrete — name the functions called and the types built.

### Q2: What do the two pipelines share?
- Shared utility modules (e.g., `launch/env.py`, `launch/text_utils.py`, `launch/resolve.py`)
- Shared type vocabulary (e.g., `ResolvedLaunchSpec`, `SpawnParams`)
- Shared harness-adapter calls (e.g., `harness.resolve_launch_spec()`, preflight)

### Q3: Where do they legitimately diverge?
Identify real functional differences, not historical parallel evolution. Examples of what to look for:
- Does one path inherit the parent env and the other not?
- Does one path support preflight and the other not?
- Does one path expose a plan-file artifact that the other doesn't?
- Does one path handle logging, work-item attachment, or report-extraction differently?
- Does one path resolve cwd differently (e.g., primary might use `$PWD`, spawn might use `execution_cwd` from `SpawnParams`)?

Classify each divergence as:
- **Fundamental**: removing it would change observable behavior users depend on
- **Incidental**: duplication that has drifted, no user-visible consequence
- **Unclear**: would need more investigation to decide

### Q4: What are the depth options?

For each, give evidence-backed cost + risk.

**Depth 1 — Full pipeline unification.** Primary and spawn both call `prepare_launch_context()` (or a replacement). How much would unification actually eliminate? How many of the divergences from Q3 are fundamental?

**Depth 2 — Shared projection merge point only.** Both pipelines keep their composition, but both call `harness.project_workspace(...)` and merge the returned `HarnessWorkspaceProjection` at their own seam. How many files change in each pipeline? Is the merge symmetric?

**Depth 3 — Narrow v1 spec.** `CTX-1.u1` applies only to spawned subagents. Primary launches don't project workspace roots in v1. What's the impact on the typical user flow of launching meridian from a multi-repo setup?

### Q5: Other features already duplicated across the two pipelines

Workspace projection is the immediate concern, but if the two pipelines don't share a seam, this is probably not the only duplication. Find at least 3 concrete examples of features that had to be implemented twice (or would if they were added today). This indicates the scale of the structural debt.

### Q6: Your recommendation

One of:
- **Depth 1 (prep refactor needed)**: unification is cheap enough and the divergences are incidental. Write a new `R0X` into `refactors.md` for the prep refactor.
- **Depth 2 (no prep refactor)**: pipelines stay separate, but R05 grows to hit both seams. Describe what R05 needs to add.
- **Depth 3 (narrow spec)**: divergence is real and unification is expensive. Spec narrows to spawn-only for v1.
- **Something else**: explain.

## Files to load

- `.meridian/work/workspace-config-design/design/refactors.md`
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md`
- `.meridian/work/workspace-config-design/design/spec/context-root-injection.md`

Explore the source tree as needed:
- `src/meridian/lib/launch/context.py`
- `src/meridian/lib/launch/plan.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/command.py`
- `src/meridian/lib/launch/env.py`
- `src/meridian/lib/launch/resolve.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/cli/main.py` (to find the primary launch entry point — grep for the non-spawn command that launches a harness)

Use grep liberally. You may read any file in `src/`.

## Output

A report structured by the numbered questions. Keep it concrete — grep output and file:line citations rather than narrative. Don't estimate file counts as ranges; give an exact count.

End with a clear recommendation (one line) and a one-paragraph rationale.
