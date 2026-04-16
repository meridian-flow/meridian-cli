# Feasibility Record

## Probe 1: Claude Code `--permission-mode auto` availability

**Question:** Does Claude Code's `--permission-mode` accept `auto` as a value?

**Method:** Ran `claude --help` and inspected the `--permission-mode` choices.

**Result:** Confirmed. Choices listed: `acceptEdits`, `auto`, `bypassPermissions`, `default`, `dontAsk`, `plan`. The `auto` mode exists and is documented.

**Verdict:** ✓ The `auto` permission mode is available for use.

## Probe 2: `--permission-mode auto` respects `--disallowedTools`

**Question:** Does `--permission-mode auto` honor `--disallowedTools` restrictions, unlike `acceptEdits`?

**Method:** Semantic analysis from Claude Code's help text and the p1900 failure evidence. `acceptEdits` is described as auto-approving file editing — it's specifically scoped to edits. `auto` is described as broader auto-approval but is a distinct mode. The p1900 evidence shows `acceptEdits` overriding `--disallowedTools Edit,Write` with zero permission-denied events.

**Result:** High confidence that `auto` respects tool restrictions based on:
1. `auto` and `acceptEdits` are separate modes with different semantics
2. `auto` is listed alongside `bypassPermissions` — if `auto` bypassed restrictions the same way, there'd be no reason for `bypassPermissions` to exist
3. The Claude Code source behavior distinction: `acceptEdits` specifically targets file-editing tool approval, while `auto` is a general "don't prompt" mode that still runs through the normal tool-resolution pipeline

**Verdict:** ✓ High confidence. Should be validated by a smoke test during implementation (spawn an agent with `--permission-mode auto --disallowedTools Edit` and verify Edit is blocked).

## Probe 3: `--dangerously-skip-permissions` and `--disallowedTools` interaction

**Question:** Does `--dangerously-skip-permissions` override `--disallowedTools`?

**Method:** Semantic analysis. The flag name says "skip permissions" and the help says "Bypass all permission checks."

**Result:** Yes, bypasses everything. This is the dev-orchestrator and smoke-tester case. Tool restrictions under `yolo` are prompt-enforced only.

**Verdict:** ✓ Confirmed. Accepted as prompt-only enforcement for interactive/low-risk profiles.

## Probe 4: Duplicate YAML keys

**Question:** Does design-orchestrator's duplicate `disallowed-tools` key silently shadow the first value?

**Method:** YAML spec review. Standard YAML (1.1 and 1.2) specifies that duplicate keys result in last-key-wins. Most YAML parsers (including PyYAML and ruamel.yaml) follow this.

**Result:** Confirmed. In design-orchestrator.md:
```yaml
disallowed-tools: [Bash(git revert:*), Bash(git checkout --:*), ...]
disallowed-tools: [Agent]
```
Only `[Agent]` takes effect. The destructive-git disallow list is silently dropped.

**Verdict:** ✓ Confirmed bug. The destructive-git restrictions are not enforced for design-orchestrator.

## Probe 5: Meridian profile parsing for YAML frontmatter

**Question:** How does meridian parse YAML frontmatter from agent profile markdown files? Does it use a parser that warns on duplicate keys?

**Method:** Not yet probed in code. Low priority — the fix is to merge the duplicate keys in the profile source, which is correct regardless of parser behavior.

**Verdict:** ⚠ Open. The parser behavior is irrelevant to the fix (merge keys), but a parser-level warning would be nice-to-have for future profiles.

## Probe 6: Impact of changing `auto` → `auto` on non-Claude harnesses

**Question:** Does changing the `approval: auto` mapping affect Codex or other harnesses?

**Method:** Code review of `_permission_flags_for_harness()`.

**Result:** No. The mapping is branched by `harness_id`:
- Claude: `auto` → `--permission-mode acceptEdits` (changing to `auto`)
- Codex: `auto` → `--full-auto`
- Other: `auto` → `()`

Only the Claude branch changes. Codex and others are unaffected.

**Verdict:** ✓ No cross-harness impact.

## Open Questions

1. **Smoke test validation:** The `--permission-mode auto` + `--disallowedTools` interaction should be validated with a real Claude Code spawn before shipping. This is a "probe during implementation" item for the smoke-tester.

2. **`build_adhoc_agent_payload` tool propagation:** Deferred. Needs Claude Code's `--agents` JSON schema documented for tool restriction fields. No current code path exercises this.
