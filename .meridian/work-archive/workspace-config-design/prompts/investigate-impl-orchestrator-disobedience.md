# Investigate — why did impl-orchestrator disobey its profile?

## The observation

Spawn `p1900` ran with agent profile `impl-orchestrator` (see `.agents/agents/impl-orchestrator.md`). That profile declares:

```yaml
tools: [Bash]
disallowed-tools: [Agent, Edit, Write, NotebookEdit, ...]
```

And its system prompt says:
- "Never write code or edit source files. Edit and Write are disabled. Don't work around this via Bash file writes. If content needs to change, spawn a `@coder`."
- "Always use `meridian spawn` for delegation — never built-in Agent tools."
- "@verifier and @smoke-tester are the baseline for every phase."
- "Smoke testing is required before anything ships."

**What actually happened in p1900**:

```
Tool use counts (from .meridian/spawns/p1900/output.jsonl):
  60 Bash
  22 Read
  12 Write     ← disallowed by profile
  11 Grep
   6 Edit      ← disallowed by profile
   0 Agent / subagent / meridian spawn invocations
```

The agent wrote and edited source files directly, and never spawned any subagents (no @coder, no @verifier, no @smoke-tester, no @reviewer). R06 shipped with 6 commits made directly by the orchestrator.

## The question

Two possible failure modes — find which one(s):

1. **Enforcement bug**: `disallowed-tools` from the profile isn't actually being propagated to the Claude CLI's `--disallowedTools` flag on this code path. If true, the flag is advisory only and nothing stops the model from using the listed tools.

2. **Instruction-following failure**: the flag is being passed correctly, but Claude (opus in this case) still used Edit/Write anyway because Claude Code's `--disallowedTools` doesn't actually block them, or because the tools were exposed via a different surface (harness hook, MCP server, etc.).

3. **Prompt-steering failure**: the system prompt said "don't do this" and the model ignored it. Separate from tool-level enforcement.

## What to do

Investigate both paths and produce a concrete diagnosis. Steps:

1. **Trace the `disallowed-tools` pipeline end-to-end** from the profile frontmatter to the actual Claude CLI invocation:
   - `src/meridian/lib/catalog/agent.py` loads `disallowed-tools` into `AgentProfile`.
   - `src/meridian/lib/launch/plan.py`, `ops/spawn/prepare.py` pass it through as `disallowed_tools`.
   - `src/meridian/lib/safety/permissions.py` `resolve_flags()` turns it into `--disallowedTools tool1,tool2,...`.
   - `src/meridian/lib/harness/projections/project_claude.py` merges it into the Claude command.
   - **Verify**: did the p1900 invocation actually receive `--disallowedTools Agent,Edit,Write,...`? The command that launched p1900 should be reconstructible from its params.
2. **Check Claude Code's behavior with `--disallowedTools`**: does that flag actually block tool use at runtime, or is it an allowlist-shaped knob that behaves differently? Consult `.agents/skills/meridian-cli/` or Claude Code's documented behavior for this flag.
3. **Check how the opus spawn was actually invoked**: logs, stderr, anything that shows the final Claude CLI args. `.meridian/spawns/p1900/stderr.log` is empty, but `output.jsonl` event `system` at the top should contain the CLI args passed.
4. **Check the prompt/steering angle**: did the profile's system prompt actually reach Claude? `.meridian/spawns/p1900/params.json:6` has the `adhoc_agent_payload` with the full prompt. Verify it was delivered as the system prompt, not dropped.
5. **Diagnose**: is this an enforcement bug (code), a framework misunderstanding (flag semantics), a prompt-steering failure (model), or a combination?

## Deliverable

Short report (<500 words):

- **Root cause**: name which failure mode(s) are real, with file:line evidence.
- **Scope**: is this impl-orchestrator specific, or does it affect every agent profile using `disallowed-tools`?
- **Proposed fix**: concrete next step per failure mode. If enforcement bug, point at the specific code path to fix. If flag semantics, propose a design change. If prompt-steering only, note that it's inherent to LLM behavior and recommend guardrails (e.g., using a model with stricter instruction following, or adding a pre-exec hook).
- **File a GitHub issue** at `meridian-flow/meridian-cli` with the findings so we don't lose the signal. Title something like "impl-orchestrator disobeyed disallowed-tools + never spawned subagents in p1900."

Probe live code, the p1900 spawn artifacts (`.meridian/spawns/p1900/`), and any relevant tests under `tests/`. Do not modify source.
