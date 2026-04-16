# Architecture: Orchestrator Profile Hardening

## Overview

Changes span two repos with different concerns:

1. **Agent profiles** (`~/gitrepos/prompts/meridian-dev-workflow/agents/`) — YAML frontmatter fixes and prompt hardening. This is the primary deliverable.
2. **Meridian CLI** (`~/gitrepos/meridian-cli/src/meridian/`) — defensive warning in the permission pipeline. This is defense-in-depth.

## Repo 1: Agent Profile Changes

### Affected profiles and their fixes

#### impl-orchestrator.md

**YAML changes:**
- `effort: medium` → `effort: high`
- `approval: auto` → remove entirely (fall back to `default`, which maps to `--permission-mode default` — user confirms each tool call). This makes `disallowed-tools: [Edit, Write, NotebookEdit]` actually enforceable.

**Rationale for removing `approval` rather than changing to `confirm`:** `default` and `confirm` both map to `--permission-mode default` for Claude. Removing the key entirely is cleaner — it means "no approval override, let the harness default handle it." Since the impl-orchestrator only needs Bash (for `meridian spawn` commands), the harness default (which prompts for confirmation) is appropriate. The orchestrator is autonomous and non-interactive, so it won't be confirming anything manually — but since Edit/Write are disallowed and Bash is the only allowed tool, the harness will auto-approve Bash calls that match the allowed pattern.

**Actually, reconsidered:** The impl-orchestrator runs autonomously without a human at the keyboard. `--permission-mode default` would block on every Bash call waiting for human confirmation that never comes. The right fix is different:

- **Option A:** `approval: yolo` — bypasses everything, but then `disallowed-tools` is also bypassed (same problem as `auto` but worse).
- **Option B:** `approval: auto` and remove Edit/Write/NotebookEdit from `disallowed-tools`, relying purely on prompt steering — accepts that YAML is not a hard fence for these tools.
- **Option C:** `approval: auto` and keep `disallowed-tools`, but add meridian-level validation that warns about the contradiction — the profile is "best effort" and the prompt is the real guardrail.
- **Option D:** Change meridian's `approval: auto` mapping from `acceptEdits` to `auto` (Claude Code's newer permission mode that auto-approves everything including Bash but still respects tool restrictions).

**Chosen: Option D as primary, with Option C as fallback awareness.**

Claude Code's `--permission-mode auto` auto-approves all tool calls but **does respect** `--allowedTools` and `--disallowedTools`. This is exactly what delegation-only orchestrators need: autonomous operation (no human confirmation) with tool restrictions enforced. The `acceptEdits` mode was the wrong mapping — it specifically auto-approves *file editing* tools, which is what contradicted the disallow list.

Verify: `--permission-mode auto` is listed in Claude CLI help output (confirmed: choices include "acceptEdits", "auto", "bypassPermissions", "default", "dontAsk", "plan").

**Updated YAML:**
```yaml
effort: high
approval: auto  # unchanged key, but meridian mapping changes from acceptEdits → auto
```

Wait — this is a **meridian code change**, not a profile change. The profile still says `approval: auto`. What changes is how meridian translates that to Claude CLI flags. See "Repo 2" below.

If we change meridian's mapping of `approval: auto` → `--permission-mode auto` (instead of `acceptEdits`), then:
- impl-orchestrator: `approval: auto` + `disallowed-tools: [Edit, Write, ...]` → `--permission-mode auto --disallowedTools Edit,Write,...` — tools are actually blocked, autonomous operation works. ✓
- docs-orchestrator: same fix, same outcome. ✓
- design-orchestrator: `approval: auto` + `tools: [Bash, Write, Edit]` → `--permission-mode auto` — autonomous, all tools available including Write/Edit which it legitimately needs. ✓
- smoke-tester: `approval: yolo` → `--dangerously-skip-permissions` — unchanged, this is intentional. ✓
- dev-orchestrator: `approval: yolo` — interactive with user, discussed separately. ✓

**Risk of changing the `auto` mapping globally:** Any profile that relied on `approval: auto` meaning `acceptEdits` (i.e., specifically wanting file-edit auto-approval but Bash confirmation) would break. Audit: no profile wants that behavior — profiles either want full autonomy or interactive confirmation. The `acceptEdits` mode was a legacy choice that doesn't match any current profile's intent.

**Conclusion for impl-orchestrator YAML:**
- `effort: medium` → `effort: high` (profile change)
- `approval: auto` stays, but meridian's projection changes to `--permission-mode auto` (code change)
- No other YAML changes needed — the disallow list becomes enforceable once the projection is correct.

**Prompt changes (primary deliverable):**
The prompt needs fundamental hardening. Current prompt says "Edit and Write are disabled" but doesn't teach the model HOW to delegate. Rewrite to include:

1. A "How to delegate" section with concrete Bash tool call examples
2. Explicit naming of off-limits tools and why
3. Skill references for spawn mechanics
4. Clear framing: "Your only tool is Bash, and you use it to run `meridian spawn` commands"

#### docs-orchestrator.md

**YAML changes:**
- `effort: medium` → `effort: high`
- `approval: auto` stays (same projection fix in code applies here)
- No other YAML changes needed

**Prompt changes:**
Already has decent delegation language ("Never write docs directly — always delegate"). Strengthen with:
1. Explicit Bash tool call example for spawning documenters
2. Tool off-limits naming
3. Confirm `meridian-cli` is already in skills list (it is)

#### dev-orchestrator.md

**YAML changes:**
- `approval: yolo` + `disallowed-tools: [Agent, ...]` — `yolo` maps to `--dangerously-skip-permissions` which bypasses everything including the Agent disallow.
- However, dev-orchestrator is interactive (user at keyboard) and runs with human oversight. The `yolo` is intentional for frictionless interactive use.
- The `Agent` disallow is there to prevent the model from using Claude Code's built-in Agent tool instead of `meridian spawn`. With `yolo`, this is prompt-enforced only.
- **Fix:** Accept this is prompt-only enforcement. The dev-orchestrator prompt already says "Always use `meridian spawn` for delegation — never use built-in Agent tools." Add explicit naming that `Agent` tool is off-limits even though it's technically available.
- Alternative: change to `approval: auto` (now `--permission-mode auto` which respects disallowed-tools). But dev-orchestrator is interactive and the user may want truly unrestricted operation. Keep `yolo` — the Agent restriction is prompt-only, which is acceptable for an interactive, human-supervised session.

**Prompt changes:**
- Already has good delegation language. Strengthen the "never use built-in Agent tools" instruction.
- Add note that `Agent` is technically available but must not be used.

#### design-orchestrator.md

**YAML changes:**
- Fix duplicate `disallowed-tools` keys. Current:
  ```yaml
  tools: [Bash, Write, Edit]
  disallowed-tools: [Bash(git revert:*), Bash(git checkout --:*), ...]
  disallowed-tools: [Agent]
  ```
  YAML last-key-wins: only `[Agent]` takes effect. The destructive-git disallow list is silently dropped.
  
  **Fix:** Merge into single key:
  ```yaml
  disallowed-tools: [Agent, Bash(git revert:*), Bash(git checkout --:*), Bash(git restore:*), Bash(git reset --hard:*), Bash(git clean:*)]
  ```

- `approval: auto` stays (design-orch legitimately needs Edit/Write for design artifacts, and with the new `auto` → `--permission-mode auto` mapping, those tools remain available since they're in `tools: [Bash, Write, Edit]` and not in `disallowed-tools`).

**Prompt changes:**
- Already has good delegation language. No major changes needed.
- Verify `meridian-cli` is in skills list (it is).

### Profiles requiring no changes (audit confirmation)

| Profile | Tools | Approval | Disallow | Verdict |
|---|---|---|---|---|
| architect | Bash(meridian *), Bash(git *), Write, Edit, WebSearch, WebFetch | (default) | (none) | ✓ coherent |
| browser-tester | Bash, Write, Edit, playwright | (default) | destructive git | ✓ coherent |
| code-documenter | Bash(meridian *), Bash(git *), Write, Edit | (default) | (none) | ✓ coherent |
| coder | Bash, Write, Edit | (default) | destructive git | ✓ coherent |
| explorer | Bash(meridian *), Bash(rg *), etc. | (default) | (none) | ✓ coherent (read-only sandbox) |
| frontend-coder | Bash, Write, Edit | (default) | destructive git | ✓ coherent |
| frontend-designer | Bash(meridian *), Write, Edit, WebSearch, WebFetch | (default) | (none) | ✓ coherent |
| internet-researcher | Bash(meridian *), WebSearch, WebFetch | (default) | (none) | ✓ coherent (read-only sandbox) |
| investigator | Bash, Write, Edit, WebSearch, WebFetch | (default) | destructive git | ✓ coherent |
| planner | Bash(meridian *), Write, Edit, WebSearch, WebFetch | (default) | (none) | ✓ coherent |
| refactor-reviewer | Bash(meridian/git read commands) | (default) | (none) | ✓ coherent (read-only sandbox) |
| reviewer | Bash(meridian/git read commands) | (default) | (none) | ✓ coherent (read-only sandbox) |
| smoke-tester | Bash, Write, Edit | yolo | destructive git | ⚠ yolo bypasses destructive-git disallow, but smoke-tester needs full access to test; destructive-git is prompt-enforced. Acceptable. |
| tech-writer | Bash(meridian *), Bash(git *), Write, Edit, WebSearch, WebFetch | (default) | (none) | ✓ coherent |
| unit-tester | Bash, Write, Edit | (default) | destructive git | ✓ coherent |
| verifier | Bash, Write, Edit | (default) | destructive git | ✓ coherent |

**smoke-tester note:** `approval: yolo` with `disallowed-tools` for destructive git is the same contradiction pattern as dev-orchestrator. But smoke-tester needs unrestricted Bash to run tests and the destructive-git restriction is prompt-enforced. This is acceptable — the risk of a smoke-tester doing `git reset --hard` is low and the consequence is recoverable. No change needed.

## Repo 2: Meridian CLI Code Changes

### Change 1: Fix `approval: auto` projection (primary)

**File:** `src/meridian/lib/harness/adapter.py`  
**Function:** `_permission_flags_for_harness()`

Change the `auto` mapping for Claude from `acceptEdits` to `auto`:

```python
# Before:
if config.approval == "auto":
    if harness_id == HarnessId.CLAUDE:
        return ("--permission-mode", "acceptEdits")

# After:
if config.approval == "auto":
    if harness_id == HarnessId.CLAUDE:
        return ("--permission-mode", "auto")
```

This is a one-line change with high impact: every profile using `approval: auto` now gets `--permission-mode auto` which respects `--disallowedTools`.

### Change 2: Add contradiction warning (defense-in-depth)

**File:** `src/meridian/lib/harness/adapter.py`  
**Function:** New validation in `resolve_permission_flags()` or a new function called from it.

After resolving permission flags, check for contradictions:

1. If permission flags include `--permission-mode acceptEdits` and resolver flags include `--disallowedTools` containing Edit/Write/NotebookEdit → warn.
2. If permission flags include `--dangerously-skip-permissions` and resolver flags include `--disallowedTools` with any entries → warn.

This catches:
- Future profiles that explicitly use `acceptEdits` via extra_args
- The `yolo` + `disallowed-tools` pattern (dev-orchestrator, smoke-tester)

The warning is informational — it does not block launch. The message should clearly explain the semantics: "approval mode X overrides disallowed-tools Y; tool restrictions will not be enforced at runtime."

**Location:** In `resolve_permission_flags()` after both base_flags and resolver_flags are computed, before returning.

### Change 3: Adhoc agent payload propagation (lower priority)

**File:** `src/meridian/lib/harness/claude.py`  
**Function:** `build_claude_adhoc_agent_json()`

Currently builds a minimal `{name: {description, prompt}}` payload. To propagate tool restrictions, the payload would need `allowedTools` and `disallowedTools` fields in the agent JSON structure.

**Deferred:** This requires understanding Claude Code's `--agents` JSON schema for tool restrictions on sub-agents. No current code path uses this — native Tasks through meridian are not exercised. Defer until the feature is needed.

## Key Design Decision: `auto` vs `acceptEdits`

Claude Code exposes two autonomous modes:
- `acceptEdits`: auto-approves file editing tools (Edit, Write, NotebookEdit) but may prompt for others. Critically, it **overrides** `--disallowedTools` for those tools.
- `auto`: auto-approves **all** tool calls but **respects** `--allowedTools` and `--disallowedTools`.

Meridian's `approval: auto` was mapped to `acceptEdits` — likely from when `auto` didn't exist or wasn't well-understood. The `auto` mode is what meridian profiles actually want: autonomous operation with tool restrictions honored.

Changing this mapping is safe because:
1. No profile relies on the `acceptEdits`-specific behavior (auto-approve edits, prompt for Bash). Every `approval: auto` profile wants full autonomy.
2. The `auto` mode is strictly more capable than `acceptEdits` in the tools it auto-approves, while being stricter in respecting the disallow list — net positive.
3. If someone truly wants `acceptEdits` behavior, they can pass `--permission-mode acceptEdits` via `extra_args`.
