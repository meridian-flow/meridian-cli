---
name: context-handoffs
description: Context scoping for agent spawns — use when deciding what context a spawned agent should receive, whether ephemeral reasoning should be materialized before handoff, and how much to pass. Poor context handoffs are the #1 cause of wasted agent work.
---
# Context Handoffs

Every spawn starts with a context decision. Get it wrong and the agent either guesses (too little context) or drowns (too much). The `/__meridian-spawn` skill teaches the mechanics of `-f`, `--from`, and spawn commands. This skill teaches the judgment — when to use which, how much to pass, and when to materialize before spawning.

## Choose the Right Mechanism

**`-f` — concrete artifacts.** Use when the context already exists as files: design docs, phase blueprints, source files, prior reports. The agent reads exactly what you point it at. This is the default choice because files are stable, inspectable, and survive compaction.

```bash
# Good: specific files relevant to the task
meridian spawn -a coder -p "Implement auth middleware" \
  -f $MERIDIAN_WORK_DIR/auth-design.md -f $MERIDIAN_WORK_DIR/phase-2.md -f src/middleware/base.py

# Bad: dumping a whole directory "just in case"
meridian spawn -a coder -p "Implement auth middleware" \
  -f $MERIDIAN_WORK_DIR/*.md -f src/**/*.py
```

**`--from` — conversation history.** Use when the agent needs to understand decisions, reasoning, or discussion context that hasn't been written down yet. Session history captures the *why* behind choices — tradeoff discussions, rejected alternatives, constraints discovered mid-conversation.

```bash
# Good: reviewer needs to understand design decisions from the architect session
meridian spawn -a reviewer --from p203 -p "Review against design intent"

# Bad: passing --from when the decisions are already in a design doc
```

**Materialize first — when context is too important to be ephemeral.** If critical context only lives in conversation, write it to a file *before* spawning. Materialized context survives compaction, re-spawns, and agent failures. If the spawn crashes and you re-run it, `-f` still works but `--from` may point to a compacted session.

```bash
# The architect discussed 3 approaches and chose event sourcing — materialize that
# Write the decision rationale to a file, THEN spawn the implementer
meridian spawn -a coder -p "Implement event store" -f $MERIDIAN_WORK_DIR/approach.md
```

**Rule of thumb**: if you'd be upset losing the context after a crash, materialize it. If it's supplementary background that helps but isn't essential, `--from` is fine.

## Scope Tightly

Pass the overview plus the specifics for the task. The overview orients the agent (what system, what goals), the specifics tell it what to build. Two to four files is typical. Six is a lot. Ten means you're delegating understanding instead of doing it yourself.

Tell the agent where to find more if it needs to explore — "the full design is in the work directory, focus on auth-design.md" — rather than attaching everything preemptively. Agents can read files on their own; your job is to point them at the right starting place.

When writing the prompt, prove you understood the context: include file paths, key decisions, what specifically to do. A prompt that says "based on the design, implement it" pushes synthesis onto the agent. A prompt that says "implement the token validation flow from the auth design doc §3, using the middleware pattern in src/middleware/base.py" gives the agent a running start.

## Cross-Phase Context

Use `--from <prior-spawn-id>` to carry forward what a previous phase learned. The phase-2 coder benefits from seeing what the phase-1 coder discovered — unexpected edge cases, deviations from the plan, judgment calls. The next agent can explore further on its own, but starts with the predecessor's hard-won context.

Combine mechanisms when phases produce artifacts: pass the prior spawn's report via `--from` for reasoning context, and the files it created via `-f` for concrete outputs.

```bash
# Phase 2 gets phase 1's reasoning AND its artifacts
meridian spawn -a coder \
  --from p301 \
  -f $MERIDIAN_WORK_DIR/phase-2.md \
  -f src/auth/tokens.py \
  -p "Implement token refresh, building on phase 1's token validation"
```

