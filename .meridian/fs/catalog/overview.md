# catalog/ — Model and Agent/Skill Catalog

## What This Is

`src/meridian/lib/catalog/` handles two distinct catalog concerns:

1. **Model catalog** — resolving model names/aliases to concrete model IDs and harness assignments
2. **Agent/skill catalog** — loading `AgentProfile` and `SkillDocument` objects from `.agents/`

These are separate subsystems that share a directory. The model catalog feeds the launch resolution pipeline; the agent/skill catalog feeds profile loading at spawn time.

## Modules

```
catalog/
  models.py          — resolve_model() entry point; models.dev discovery + cache
  model_aliases.py   — AliasEntry type; mars CLI integration (resolve + list)
  model_policy.py    — Pattern fallback routing; visibility/superseded policy
  agent.py           — AgentProfile parser; scan_agent_profiles(); load_agent_profile()
  skill.py           — SkillDocument/SkillRegistry; parse/scan SKILL.md files
```

## Data Flow

```
spawn request (model name or alias)
  └→ resolve_model()              [models.py]
       ├→ run_mars_models_resolve() [model_aliases.py] → mars binary
       │    → AliasEntry{model_id, harness}
       └→ pattern_fallback_harness() [model_policy.py]  (if mars returns None)
            → AliasEntry{model_id, harness}

spawn request (agent name)
  └→ load_agent_profile()         [agent.py]
       └→ scan .agents/agents/*.md
            → AgentProfile{name, model, harness, skills, body, ...}

agent profile skills list
  └→ SkillRegistry.load(names)    [skill.py]
       └→ scan .agents/skills/*/SKILL.md
            → [SkillContent{name, content, path}]
```

## Key Contracts

- `resolve_model()` always returns an `AliasEntry` with a concrete `harness`. Never returns ambiguity — raises `ValueError` if no harness can be determined.
- Mars is required (bundled); absence raises `RuntimeError`. Not a soft failure.
- Agent profiles are loaded from `.agents/agents/*.md` only. No other search paths.
- Skills are loaded from `.agents/skills/*/SKILL.md` only.
- Duplicate profile/skill names: first-seen wins; conflicting duplicates log a warning and are ignored.

## Related Docs

- `catalog/models.md` — full resolution pipeline, mars integration, visibility policy
- `catalog/agents-and-skills.md` — profile/skill loading, composition, default agent policy
