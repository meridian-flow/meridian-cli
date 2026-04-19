# Design: Orchestrator Profile Hardening

## Context

Read `$MERIDIAN_WORK_DIR/requirements.md` first — it has the full problem statement, root cause analysis, and success criteria.

The investigation is done. The root cause is confirmed: Claude Code's `--permission-mode acceptEdits` overrides `--disallowedTools` for file-editing tools. Three orchestrator profiles have self-contradictory YAML, and prompt-only steering proved insufficient for opus on a multi-hour run.

## Design priorities

**Prompt-steering is the primary guardrail.** Even if Edit/Write are technically available at runtime, a well-steered model should never reach for them. The p1900 failure was a prompt-steering failure first — opus had clear instructions to delegate but chose to implement directly because Edit/Write worked and the path of least resistance won. The prompt must make delegation so natural and well-taught that the model defaults to it.

**YAML is the safety net.** Fix the approval/disallow contradiction so that IF the prompt fails, the tools are actually blocked. But the prompt is the real fix — YAML enforcement is defense-in-depth.

**Code-level warning is nice-to-have.** Catches future profile authors making the same mistake.

## What you're designing

Changes across two repos:

### 1. Agent profiles (`~/gitrepos/prompts/meridian-dev-workflow/agents/`)

Audit all 20 agent profiles. For each, verify:
- The system prompt matches the YAML intent and teaches the right workflow pattern.
- The `approval` + `tools` + `disallowed-tools` combination is coherent with Claude Code's actual enforcement semantics (acceptEdits bypasses Edit/Write disallow; bypassPermissions bypasses everything).
- The effort level is appropriate for the role's autonomy and duration.

Specific profiles to fix:
- **impl-orchestrator**: the big one. Prompt needs to be fundamentally rewritten for delegation clarity. Concrete examples showing `Bash("meridian spawn -a coder ...")`. Effort → high. Approval fixed as safety net.
- **docs-orchestrator**: same approval/disallow contradiction + prompt hardening.
- **dev-orchestrator**: `approval: yolo` + `disallowed-tools: [Agent]` — does `--dangerously-skip-permissions` bypass the Agent disallow? If so, fix.
- **design-orchestrator**: has duplicate `disallowed-tools` keys in frontmatter (only last one takes effect in YAML). Fix.

#### Prompt hardening for delegation-only orchestrators (primary deliverable)

The prompt must teach the model HOW to delegate, not just tell it to. Specifically:

- **Make explicit that `meridian spawn` is a Bash command.** The model calls `Bash("meridian spawn -a coder ...")`. This is not obvious — models sometimes treat "use meridian spawn" as an abstract instruction rather than connecting it to the Bash tool.
- **Show concrete delegation examples** for each major workflow step (coding, testing, reviewing). Not abstract patterns — actual tool-call-shaped examples with realistic arguments.
- **Explain WHY delegation is mandatory** — not just "because the profile says so" but because spawns produce traceable reports, enable review lanes, and keep the orchestrator at coordination altitude. Give the model the reasoning so it can internalize the constraint.
- **Reference `meridian-cli` and `meridian-spawn` skills explicitly** as the authority on spawn mechanics and available agents.
- **Name the exact tools that are off-limits** and frame them as "you should never need these because your job is coordination, not implementation."
- **Add the `meridian-cli` skill** to any orchestrator that's missing it — it teaches the model what meridian commands exist and how they work.

### 2. Meridian CLI code (`~/gitrepos/meridian-cli/src/meridian/`)

- In `harness/adapter.py:_permission_flags_for_harness()`: detect when the resolved permission mode would override disallowed-tools entries and either warn or refuse. The specific case: `approval: auto` → `acceptEdits` while `disallowed-tools` includes Edit/Write/NotebookEdit.
- In `harness/claude.py:build_adhoc_agent_payload()`: propagate `tools` and `disallowed-tools` into the `--agents` JSON payload. (Lower priority, secondary fix.)

## Working repos

- Agent profiles source: `~/gitrepos/prompts/meridian-dev-workflow/`
  - `agents/` — 20 agent profile markdown files with YAML frontmatter
  - `skills/` — skill SKILL.md files
- CLI source: `~/gitrepos/meridian-cli/src/meridian/`

Read the source profiles directly from `~/gitrepos/prompts/meridian-dev-workflow/agents/`. Do NOT read from `.agents/agents/` (generated output, overwritten by mars sync).

## Constraints

- No backwards compatibility needed.
- Don't over-restrict profiles that legitimately need Edit/Write (coder, verifier, architect, investigator, etc.).
- design-orchestrator legitimately needs Edit/Write for design artifacts.
- The design should be practical — focus on what actually ships, not ideal-world enforcement.
- Keep changes minimal: fix the contradiction, harden the language, bump effort. Don't redesign the entire agent system.
