# Agent & Skill Design Principles

Principles for writing agent profiles and skills in the meridian ecosystem. Derived from Anthropic's prompting research, the PRISM persona study (arxiv:2603.18507), and iteration on the dev-workflow orchestrators.

## Agents vs Skills

An **agent** is an actor — a model instance with a system prompt, tools, permissions, and a model choice. It runs as its own process, makes decisions, and produces output. Agents are spawned (expensive, independent).

A **skill** is knowledge — instructions loaded into an agent's context when relevant. A skill doesn't run independently; it augments whatever agent consumes it. Multiple agents can share the same skill. Skills are loaded at trigger time (cheap, composable).

The boundary: if it runs independently and produces output, it's an agent. If it's reference material that shapes how an agent works, it's a skill.

Getting this wrong in either direction is costly. A skill where an agent belongs forces the consuming agent to absorb all the complexity — decision-making, artifact production, error handling — instead of delegating to an independent process. The consumer becomes a god-object. An agent where a skill belongs spawns an entire process (context window, model call, token budget) just to deliver reference knowledge that could be injected in 200 lines — expensive, slow, and the knowledge can't be shared across agents.

A skill should have multiple consumers — if only one agent loads it, the knowledge belongs in that agent's body. Splitting a single agent's guidance across its body and a dedicated skill just creates two places to maintain with no reuse benefit. Extract into a skill when a second agent needs the same knowledge.

## No Role Identity

Don't assign personas like "you are a senior engineer" or "you are a technical PM." Research (PRISM, arxiv:2603.18507) shows that persona prompting activates instruction-following mechanisms that interfere with knowledge retrieval and reasoning accuracy. On discriminative tasks (judgment calls, factual recall, code reasoning), every persona variant reduced accuracy.

Instead, describe behaviors directly. Not "you are a careful reviewer" but "focus on correctness — does the code do what it claims?" The model doesn't need a costume to follow behavioral instructions.

## Explain WHY

Every constraint should include the reasoning behind it. Anthropic's prompting docs show that Claude generalizes from explanations — understanding *why* a rule exists lets the model apply the principle to novel situations rather than following the rule literally and missing the point.

Bad: "Never edit source files."
Good: "You don't edit source files because your value is in the continuity between user intent and autonomous orchestrators. If you drop into implementation, you lose the altitude needed to catch when an orchestrator drifts from what the user wanted."

Bad: "Always use meridian spawn."
Good: "Delegate through meridian spawn rather than built-in agent tools. Meridian spawn enables cross-session state tracking and model routing across providers — built-in agents can't persist their work or be inspected after the fact."

## Right Altitude

From Anthropic's context engineering guide: system prompts should be "specific enough to guide behavior effectively, yet flexible enough to provide strong heuristics." Two failure modes:

- **Too specific (brittle)**: Hardcoded if-then rules that break on edge cases and require constant maintenance.
- **Too vague (ineffective)**: High-level guidance that assumes shared context the model doesn't have.

The sweet spot is behavioral heuristics with reasoning. Tell the model what to do, when, and why — then trust it to apply the principle.

## Dial Back Aggressive Language

Aggressive prompt language (ALL CAPS, "CRITICAL", "you MUST", "NEVER") pushes models toward brittle, literal compliance — the opposite of the "right altitude" goal. Instructions designed to reduce undertriggering on earlier models cause overtriggering on current ones, where the model follows the instruction too rigidly and applies it in situations where it doesn't make sense. As models become more responsive to system prompts, the threshold for this overtriggering keeps dropping. Use normal language — "use this tool when..." instead of "CRITICAL: You MUST use this tool."

## Description Design

Descriptions serve the consumer — whoever is deciding whether to use this agent or skill. The body serves the entity itself. These are different audiences with different needs, and mixing them wastes tokens repeating information one audience can't act on.

### Skill Descriptions

Skill descriptions trigger loading — they're what the model sees in the skill list to decide whether to load the full SKILL.md. They should describe *when to use this skill* (situations and contexts), not *how to use it* (commands and syntax). The body handles the how.

Two audiences see skill descriptions:

1. **Agents with the skill pre-loaded** (via `skills:` array) — description is always visible alongside the body. Don't duplicate the body; the description orients, the body instructs.
2. **Agents without the skill loaded** — description is ALL they see. It must explain when to trigger clearly enough that the agent loads it when relevant. Always-loaded skills (like `__meridian-spawn` on orchestrators) still need good descriptions because other agents may not have them pre-loaded.

### Agent Descriptions

Agent descriptions serve the caller — the agent deciding whether and how to spawn this one. The caller may be in a harness that doesn't show agents natively (e.g. Codex), or may be a custom orchestrator that's never seen this agent before. Without clear descriptions, callers either don't know the agent exists, invoke it wrong, or pass insufficient context. Cover:

- **What it does** and what it produces — so the caller knows whether this is the right agent for the task
- **How to invoke it** — include `meridian spawn -a <name>` so callers in any harness know the command, not just those with native agent discovery
- **What context it needs** — so the caller passes the right artifacts and history rather than leaving the agent to guess. E.g. "pass conversation context with --from and relevant files with -f, or mention specific files in the prompt so the agent can explore on its own"
- **Where it puts its output** — so orchestrators can find artifacts without reading agent code or waiting for completion. E.g. `$MERIDIAN_WORK_DIR/design/`

## Progressive Disclosure

Context windows are finite. Loading everything all the time wastes tokens on information the agent doesn't need for this specific task. Skills use a three-level loading system that matches how likely information is to be needed:

1. **Description** (short — a sentence or two) — always in context, triggers loading. Cheap because it's short.
2. **SKILL.md body** (keep it digestible — a few hundred lines at most) — loaded when skill triggers. Covers the core loop and common patterns. If it grows long enough that agents spend significant context budget on a single skill, it needs to push detail into resources.
3. **Bundled resources** — loaded on demand from the body's references. Advanced commands, debugging, configuration, edge cases — information needed only in specific situations.

Reference resources clearly from the body with guidance on *when* to read them, so the agent knows what's available without loading it preemptively.

## Don't Repeat Across Levels

Each level should add new information, not restate what a previous level already covered. If the description explains something, the body should go deeper or start from where the description left off. If the body explains something, resources shouldn't repeat it. Repetition wastes tokens on every invocation and creates maintenance drift — update one place, forget the other, now they contradict each other and the agent gets conflicting instructions.

## Agent Body: Don't Assume Your Caller

The agent body shouldn't reference who spawned it ("dev-orchestrator spawns you with...") or how it was invoked (`--from`, `-f`). The agent sees whatever context lands in its window — it has no way to distinguish `--from` context from `-f` context from inline prompt context. Describing behaviors in terms of invocation mechanics ("read all context passed via `--from`") is meaningless to the agent and creates a false dependency on a specific caller.

Keeping agents caller-agnostic makes them reusable across workflows. A design-orchestrator spawned by a dev-orchestrator and one spawned by a custom CI pipeline should behave identically.

## Don't Prescribe Sequences

Anthropic's guidance: "prefer general instructions over prescriptive steps — a prompt like 'think thoroughly' often produces better reasoning than a hand-written step-by-step plan." Numbered step flows (Step 1: Understand, Step 2: Explore, Step 3: Design) constrain the model to a rigid sequence that may not fit the problem. A simple design doesn't need a full exploration phase. A complex one might need review mid-design, not after. Prescriptive flows prevent the model from adapting to the actual situation. Instead describe:

- What inputs it receives
- What outputs it produces
- What quality bar to hit (reviewed, convergent, decisions logged)
- What tools it has (which agents to spawn, which skills to use)
- When to escalate

The model figures out the sequence based on the specific problem.

## Don't Hardcode Models

Model rankings change month to month. Hardcoding "fan out across opus, gpt-5.4, and codex" means the prompt is stale the moment a new model drops or pricing changes. Instead write "fan out across diverse strong models" and point to `meridian models list` and `/agent-staffing` for current guidance. Match model cost to task value — research and bulk exploration are high-throughput information gathering that should use fast/cheap models; review and architecture are judgment-heavy and benefit from the strongest available.

## Agent Prompt Layout

A well-structured prompt puts the most important context first so the model orients quickly. These are priorities ordered by importance, not a rigid template — adapt the structure to the agent's complexity. A short utility agent doesn't need five sections.

- **Open with what this agent does and why it matters** — functional description, not identity claim. This is what the model sees first after compaction, so it should orient the model on its purpose immediately.
- **Behavioral constraints with reasoning** — what not to do and why. Early placement means these are less likely to be lost in long contexts, where primacy and recency effects dominate.
- **Core workflow and quality bar** — what to produce, what tools are available, what "done" looks like. This is the bulk of most prompts.
- **Specific guidance per mode** — escalation, completion criteria, edge cases. Later placement because these apply situationally, not on every invocation.

## Tool Restrictions

Agent profiles support two mechanisms for controlling tool access:

- **`tools`** (allowlist): Lists tools the agent is permitted to use. On Claude, `--allowedTools` does not actually restrict built-in tools (Agent, Read, Glob, etc. remain available regardless). Primarily useful for scoping Bash permissions (e.g. `Bash(git *)`) and for OpenCode/Codex where the allowlist is enforced.
- **`disallowed-tools`** (denylist): Lists tools the agent must not use. On Claude, `--disallowedTools` genuinely removes tools from the agent's tool list. Use this to enforce boundaries — e.g. `disallowed-tools: [Agent]` on orchestrators that must use `meridian spawn` instead.

When both are set, both are emitted — the allowlist doesn't suppress the denylist. Use the denylist for hard restrictions and the allowlist for scoping what's available.
