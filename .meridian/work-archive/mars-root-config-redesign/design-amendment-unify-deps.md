# Design Amendment: Unify [sources] and [dependencies] into [dependencies]

## Change

Replace `[sources]` and `[dependencies]` with a single `[dependencies]` section. Every other package manager (Cargo, npm, pip/uv) uses one section for both "what gets installed locally" and "what downstream consumers inherit." Mars should too.

## Before (two sections)

```toml
[package]
name = "my-agents"
version = "0.1.0"

[dependencies.base]           # package manifest concern — transitive
url = "https://github.com/org/base"
version = ">=1.0"

[sources.meridian-base]       # consumer concern — local install
url = "https://github.com/haowjy/meridian-base"

[sources.anthropic-skills]
url = "https://github.com/anthropics/skills"
skills = ["frontend-design"]
```

## After (unified)

```toml
[package]
name = "my-agents"
version = "0.1.0"

[dependencies.meridian-base]
url = "https://github.com/haowjy/meridian-base"

[dependencies.anthropic-skills]
url = "https://github.com/anthropics/skills"
skills = ["frontend-design"]
```

## What changes

1. **Config struct**: Remove `sources` field. `dependencies` replaces it everywhere. The `DepSpec` struct from the old manifest already has `url`, `version`, `agents`, `skills` — merge with `SourceEntry` which has `url`, `path`, `version`, `filter` (agents/skills/exclude/rename). The unified struct needs all fields from both.

2. **Consumer detection**: Was "[sources] key exists." Now: "[dependencies] key exists." Same logic, different key name.

3. **`mars init`**: Creates empty `[dependencies]` instead of empty `[sources]`.

4. **`mars add`**: Writes to `[dependencies]` instead of `[sources]`.

5. **All CLI commands** that reference "sources" in user-facing messages: update terminology to "dependencies."

6. **Lock file**: `[sources.*]` entries in mars.lock should probably also rename to `[dependencies.*]` for consistency. Or keep as implementation detail — lock format is internal.

7. **Resolver**: Already resolves from dependencies. Now also uses them as the install list. The `_self` synthetic source stays as-is (it's not a dependency).

8. **`mars list`/`mars why`**: Show dependencies, not sources.

## What doesn't change

- The `_self` synthetic source for local package items
- `[settings]` section
- `[package]` section
- Lock file structure (items, versions, hashes)
- Symlink behavior
- Git boundary walk-up

## Impact on existing design docs

- `config-model.md`: Replace all `[sources]` references with `[dependencies]`. Consumer detection key changes.
- `init-and-discovery.md`: `ensure_consumer_config` checks for `[dependencies]` not `[sources]`.
- `local-package-sync.md`: Collision check references `target_state` which comes from dependencies. No structural change.
- `api-cleanup.md`: No change.
- `phases.md`: Phase 1 references `[sources]` — update to `[dependencies]`.
- `decisions.md`: D1 and D5 need updating. D5 is now "unified into [dependencies]" instead of "kept separate."
