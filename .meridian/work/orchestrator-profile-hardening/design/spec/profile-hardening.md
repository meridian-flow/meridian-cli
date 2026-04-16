# Behavioral Specification: Orchestrator Profile Hardening

## Profile YAML Coherence

### S-YAML-01: approval/disallow contradiction detection
When a profile sets `approval: auto` (projected as `--permission-mode acceptEdits`) and also sets `disallowed-tools` including any of `Edit`, `Write`, or `NotebookEdit`, the system shall emit a warning at spawn launch time identifying the contradiction, because `acceptEdits` auto-approves file-editing tools regardless of `--disallowedTools`.

### S-YAML-02: yolo/disallow contradiction detection
When a profile sets `approval: yolo` (projected as `--dangerously-skip-permissions`) and also sets `disallowed-tools` with any entries, the system shall emit a warning at spawn launch time identifying the contradiction, because `--dangerously-skip-permissions` bypasses all permission checks including tool restrictions.

### S-YAML-03: duplicate YAML key detection
When a profile contains duplicate keys in its YAML frontmatter (e.g. two `disallowed-tools` keys), the system shall use standard YAML last-key-wins semantics but the profile author shall be informed via documentation that only the last key takes effect.

### S-YAML-04: impl-orchestrator approval coherence
The impl-orchestrator profile shall not set `approval: auto` while disallowing Edit/Write/NotebookEdit. The approval mode shall be changed so the disallow list is actually enforced by Claude Code at runtime.

### S-YAML-05: docs-orchestrator approval coherence
The docs-orchestrator profile shall not set `approval: auto` while disallowing Edit/Write/NotebookEdit. Same fix as S-YAML-04.

### S-YAML-06: dev-orchestrator approval coherence
The dev-orchestrator profile shall not set `approval: yolo` while disallowing Agent. The approval/disallow combination shall be coherent.

### S-YAML-07: design-orchestrator duplicate key fix
The design-orchestrator profile shall have a single `disallowed-tools` key that merges both current entries, not two separate keys where one silently shadows the other.

## Prompt Hardening for Delegation-Only Orchestrators

### S-PROMPT-01: explicit tool-call teaching
Delegation-only orchestrator prompts shall explicitly state that `meridian spawn` is invoked via the Bash tool — i.e., `Bash("meridian spawn -a coder ...")` — so the model connects the abstract instruction to the concrete tool call.

### S-PROMPT-02: concrete delegation examples
Delegation-only orchestrator prompts shall include at least one concrete example showing the Bash tool call shape for spawning a coder, a tester, and a reviewer, with realistic arguments including `-f`, `-p`, and `--desc`.

### S-PROMPT-03: off-limits tools named explicitly
Delegation-only orchestrator prompts shall name the specific tools that are off-limits (Edit, Write, NotebookEdit, Agent) and explain why: spawns produce traceable reports, enable review lanes, and keep the orchestrator at coordination altitude.

### S-PROMPT-04: skill references
Delegation-only orchestrator prompts shall reference `meridian-cli` and `meridian-spawn` skills as the authority on spawn mechanics and available agents.

### S-PROMPT-05: meridian-cli skill presence
Every orchestrator profile shall include `meridian-cli` in its skills list.

## Effort Level

### S-EFFORT-01: impl-orchestrator effort level
The impl-orchestrator profile shall set `effort: high` to give the model sufficient thinking budget for multi-hour autonomous orchestration runs with complex instruction compliance.

### S-EFFORT-02: docs-orchestrator effort level
The docs-orchestrator profile shall set `effort: high` for the same autonomous orchestration reasons as impl-orchestrator.

## Full Profile Audit

### S-AUDIT-01: non-orchestrator profiles unmodified
Profiles that legitimately need Edit/Write (coder, verifier, architect, browser-tester, frontend-coder, frontend-designer, code-documenter, tech-writer, unit-tester, smoke-tester, investigator, planner) shall not have their tools restricted as part of this work.

### S-AUDIT-02: read-only profiles unchanged
Profiles that are already read-only (reviewer, refactor-reviewer, explorer, internet-researcher) shall not be modified unless they have a separate coherence issue.

### S-AUDIT-03: design-orchestrator Edit/Write preserved
The design-orchestrator legitimately needs Edit and Write for design artifacts. These shall remain in its tools list. Only the duplicate key and Agent disallow need fixing.

## Code-Level Warning

### S-CODE-01: warning on contradictory permission combinations
The `_permission_flags_for_harness()` function in `adapter.py` shall detect when the resolved permission mode would override disallowed-tools entries and log a warning. Specifically: when `approval: auto` produces `acceptEdits` and `disallowed-tools` includes file-editing tools, or when `approval: yolo` produces `--dangerously-skip-permissions` and any `disallowed-tools` exist.

### S-CODE-02: warning is non-blocking
The warning shall be logged but shall not prevent the spawn from launching. The fix is in the profile YAML; the warning catches future regressions.

### S-CODE-03: adhoc agent payload propagation (lower priority)
`build_adhoc_agent_payload()` should propagate `tools` and `disallowed-tools` into the Claude `--agents` JSON payload so native Task-based sub-agents inherit restrictions. This is lower priority because no current code path exercises native Claude Tasks through meridian.
