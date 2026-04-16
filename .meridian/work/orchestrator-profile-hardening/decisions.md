# Decisions

## D1: Map `approval: auto` to `--permission-mode auto` instead of `acceptEdits`

**What:** Change meridian's Claude projection of `approval: auto` from `--permission-mode acceptEdits` to `--permission-mode auto`.

**Why:** `acceptEdits` auto-approves file-editing tools (Edit, Write, NotebookEdit) regardless of `--disallowedTools`, which is the root cause of the p1900 failure. `auto` auto-approves all tool calls but respects `--allowedTools` and `--disallowedTools`. This is what every `approval: auto` profile actually wants: autonomous operation with tool restrictions honored.

**Alternatives rejected:**
- *Remove `approval: auto` from affected profiles:* Would require `approval: yolo` (bypasses everything) or `approval: confirm`/`default` (blocks on human confirmation, incompatible with autonomous spawns). Neither is correct.
- *Keep `acceptEdits` and remove Edit/Write from disallow lists:* Accepts prompt-only enforcement, gives up the YAML safety net entirely. Profile YAML would be misleading — it wouldn't express the tool restriction intent.
- *Add a new approval mode like `auto-restricted`:* Over-engineering. Claude Code already has the right mode; meridian just mapped to the wrong one.

**Risk:** Profiles that relied on `acceptEdits`-specific behavior (auto-approve edits, prompt for Bash) would break. Audit confirms no profile wants this — every `approval: auto` profile wants full autonomy.

## D2: Prompt hardening as primary guardrail, YAML as safety net

**What:** Treat prompt improvements as the primary fix and YAML coherence as defense-in-depth.

**Why:** Even with correct YAML enforcement, a determined or confused model can work around tool restrictions (e.g., `Bash("cat > file.py << 'EOF' ...")` bypasses Edit/Write restrictions). The prompt must make delegation so natural that the model defaults to it. The p1900 failure was a prompt-steering failure — opus had instructions to delegate but they weren't specific enough to override the path-of-least-resistance when Edit/Write were available.

**Alternatives rejected:**
- *Rely solely on YAML enforcement:* Bash file writes are an easy workaround. YAML alone cannot prevent direct implementation.
- *Rely solely on prompt steering:* The p1900 incident proves prompt-only enforcement fails. Defense in depth is warranted.

## D3: Accept prompt-only enforcement for dev-orchestrator `Agent` disallow

**What:** Keep `approval: yolo` on dev-orchestrator and accept that `disallowed-tools: [Agent]` is prompt-enforced only.

**Why:** dev-orchestrator is interactive with a human at the keyboard. The `yolo` mode is intentional for frictionless interactive use. The `Agent` restriction prevents the model from using Claude Code's built-in Agent tool instead of `meridian spawn`, but this is a workflow preference not a security boundary. Prompt enforcement is adequate for human-supervised sessions.

**Alternatives rejected:**
- *Change to `approval: auto`:* Would add confirmation prompts to the interactive session, degrading UX for the primary human-supervised use case.

## D4: Merge design-orchestrator duplicate YAML keys

**What:** Merge two `disallowed-tools` keys into one containing both the Agent disallow and the destructive-git disallows.

**Why:** YAML last-key-wins means only `[Agent]` takes effect, silently dropping the destructive-git restrictions. Both restrictions are intended.

## D5: Defer `build_adhoc_agent_payload` tool propagation

**What:** Do not add `tools`/`disallowed-tools` propagation to the adhoc agent JSON payload in this work item.

**Why:** No current code path exercises native Claude Tasks through meridian. The Claude `--agents` JSON schema for tool restrictions is not well-documented. The risk is zero today and the fix requires schema validation we can't do without testing against real Claude Task execution.
