# Orchestrator Profile Hardening

## Problem

Spawn p1900 (impl-orchestrator, opus) had `disallowed-tools: [Agent, Edit, Write, NotebookEdit, ...]` and `tools: [Bash]` in its profile. Meridian correctly projected `--allowedTools Bash --disallowedTools Agent,Edit,Write,...` onto the Claude CLI. Despite this, opus used Edit 6 times and Write 12 times, never spawned a single subagent, and shipped 6 commits directly.

### Root cause (confirmed)

The profile also sets `approval: auto`, which meridian maps to `--permission-mode acceptEdits`. Claude Code's `acceptEdits` mode auto-approves file-editing tools, overriding `--disallowedTools` for those tools. Zero permission-denied events in p1900's output confirms this — the disallow list was never enforced.

### Scope of the problem

Three orchestrator profiles are affected:

| Profile | approval | disallowed | Impact |
|---|---|---|---|
| impl-orchestrator | auto | Agent, Edit, Write, NotebookEdit | **confirmed bypassed** (p1900) — did all implementation directly |
| docs-orchestrator | auto | Agent, Edit, Write, NotebookEdit | same bug, untested |
| dev-orchestrator | yolo | Agent | yolo → `--dangerously-skip-permissions`, Agent disallow likely also bypassed |

**Critical reference point: design-orchestrator proves prompt-steering works.** design-orchestrator has `tools: [Bash, Write, Edit]`, `approval: auto` (same `acceptEdits` permission mode), runs on the same opus model — and it ALWAYS delegates to @architect/@reviewer. It has never failed to spawn subagents. This means the impl-orchestrator failure is a **prompt quality gap**, not a fundamental model limitation. Study what design-orchestrator's prompt does right and replicate that pattern for impl-orchestrator and docs-orchestrator.

design-orchestrator has a minor YAML bug (duplicate `disallowed-tools` key, only last takes effect) but is otherwise the gold standard for delegation behavior.

Additionally, `build_adhoc_agent_payload()` in `harness/claude.py:262` strips `tools`, `disallowed-tools`, `model`, `approval`, `sandbox` from the agent profile when building Claude's `--agents` JSON. Native Task-based sub-agents would inherit none of the profile restrictions.

## What needs to change

### Primary repo: `~/gitrepos/prompts/meridian-dev-workflow/`

All 20 agent profiles need audit. Changes for affected orchestrators:

1. **YAML profile fixes.** The `approval` + `disallowed-tools` combination must be coherent with Claude Code's actual enforcement semantics. If `approval: auto` means `acceptEdits` which bypasses Edit/Write disallow, either:
   - Drop `approval: auto` on orchestrators that disallow Edit/Write (use `confirm` or no approval override)
   - Or accept that enforcement is prompt-only and don't pretend the YAML is a hard fence

2. **Prompt hardening.** The system prompt for delegation-only orchestrators needs stronger, more specific language:
   - Make explicit that `meridian spawn` is a **Bash command** — `Bash("meridian spawn -a coder ...")` — not a native tool. Models sometimes don't connect "use meridian spawn" with "call the Bash tool with a meridian command."
   - Reference the `meridian-cli` and `meridian-spawn` skills explicitly as the source of truth for spawn mechanics.
   - Add concrete examples of the expected delegation pattern (Bash tool → meridian spawn → wait).
   - Make the "never edit files directly" instruction unmistakably clear — name the exact tools that are off-limits and why.

3. **Effort level.** impl-orchestrator currently runs `effort: medium`. For a multi-hour autonomous orchestration run, this should be `effort: high` to give the model more thinking budget for instruction compliance.

### Secondary repo: `~/gitrepos/meridian-cli/`

4. **Code-level defense.** In `harness/adapter.py:_permission_flags_for_harness()`, when `approval: auto` maps to `acceptEdits`, warn or refuse if the profile also disallows Edit/Write — the combination is self-contradictory. At minimum, log a warning; ideally, refuse the combination.

5. **Adhoc agent payload.** `build_adhoc_agent_payload()` should propagate `tools` and `disallowed-tools` into the Claude `--agents` JSON so native Task sub-agents inherit restrictions. (Lower priority — no current code path exercises this.)

## Constraints

- Changes in `~/gitrepos/prompts/meridian-dev-workflow/` are committed there, then synced to meridian-cli via `meridian mars sync`.
- No backwards compatibility needed (per CLAUDE.md).
- Every profile change must be coherent: the YAML frontmatter, the system prompt text, and the actual Claude CLI projection must tell the same story.
- Don't over-restrict profiles that legitimately need Edit/Write (coder, verifier, architect, etc.).
- `design-orchestrator` legitimately needs Edit/Write for design artifacts — don't break it.

## Success criteria

1. No orchestrator profile has a self-contradictory approval/disallowed-tools combination.
2. Delegation-only orchestrators (impl-orch, docs-orch) have prompts that unambiguously teach the model to delegate via `Bash("meridian spawn ...")`.
3. All 20 profiles audited with a coherent tools/approval/disallow/prompt story.
4. meridian-cli code warns on contradictory approval+disallow combos.
5. impl-orchestrator effort bumped to high.
