# Install CLI Redesign

## Context

The install system has matured significantly. Source merging, skill dependency resolution, item-level uninstall, `agents.local.toml` overrides, and the `sources` subgroup are all in place. What remains is UX friction around item addressing and the monolithic `meridian-agents` source.

## Remaining Problems

1. **Item filters are clunky.** `--agents a,b --skills c,d` requires knowing the kind upfront. The engine already resolves `agent:` vs `skill:` prefixes internally — the CLI should too.
2. **Sources are too coarse.** `meridian-agents` bundles core runtime + dev workflow + reviewing + documenting. Users install-all and pay description tokens for items they don't use.
3. **No inline item syntax.** You can't say "install just the reviewer from this source" in a single positional arg.

## Design

### Inline Item Addressing: `@owner/repo:item`

```
@owner/repo              → entire source (all items)
@owner/repo:reviewer     → specific item from source
./local-path             → local source (all items)
./local-path:reviewer    → specific item from local source
```

The `:item` suffix is parsed from the source arg in `_build_source_config()`. Multiple items use repeated colons or comma separation (see open questions). Item names are unqualified — the engine determines agent vs skill from the source layout. If there's a collision, use explicit `agent:reviewer` or `skill:reviewing`.

This replaces `--agents` and `--skills` flags, which become deprecated (still work, merged with inline items).

### Updated Commands

Current commands stay under `sources` subgroup. Only the install syntax changes:

```bash
# ── Install ──────────────────────────────────────────────

# Sync .agents/ from lock (no args)
meridian sources install

# Install everything from a source
meridian sources install @haowjy/meridian-agents

# Install specific items (+ their skill deps)
meridian sources install @haowjy/meridian-agents:reviewer
meridian sources install @haowjy/meridian-agents:reviewer,coder,reviewing

# Install from local path
meridian sources install ./my-agents
meridian sources install ./my-agents:custom-reviewer

# With ref override
meridian sources install @myorg/team-agents --ref v2.0.0

# ── Uninstall (already works) ────────────────────────────

meridian sources uninstall reviewer coder
meridian sources uninstall --source meridian-agents

# ── Update (already works) ───────────────────────────────

meridian sources update
meridian sources update --source meridian-agents

# ── List / Status (already work) ─────────────────────────

meridian sources list
meridian sources status
```

### Implementation

**File: `src/meridian/cli/install_cmd.py`**

1. Parse `:items` suffix from the `source` positional arg in `_build_source_config()`:
   - Split on first `:` after the source locator (handle `@owner/repo:items` and `./path:items`)
   - Parse items as comma-separated list
   - Merge with any `--agents`/`--skills` flags (union)
   - Since items are unqualified, pass them as a combined list; the engine's discovery step resolves kind

2. Deprecation warning for `--agents`/`--skills` when inline items are also provided

**File: `src/meridian/lib/install/engine.py`**

3. Accept an `items: tuple[str, ...] | None` parameter alongside (or replacing) separate `agents`/`skills` on `SourceConfig`
4. During `plan_source_items()`, resolve unqualified names against discovered items to determine `agent:` or `skill:` prefix
5. Skill dependency resolution already handles the rest

**File: `src/meridian/lib/install/config.py`**

6. `SourceConfig` gets an optional `items: tuple[str, ...] | None` field
7. Manifest serialization: `items` in TOML replaces separate `agents`/`skills` arrays (or coexists during migration)

### What Already Works (No Changes Needed)

- Source merging (union semantics) — `_merge_source_config()`
- Skill dependency resolution — `resolve_skill_deps()` in `deps.py`
- `meridian sources install` with no args syncs from lock
- Item-level uninstall by name
- `agents.local.toml` for local overrides
- `--local`, `--force`, `--dry-run`, `--ref`, `--rename` flags
- Lock file format and concurrency

## Source Splitting

Separate from the CLI work. The current `meridian-agents` repo should split into:

### `@haowjy/meridian-agents` (core runtime)

Only bootstrap items: `__meridian-orchestrator`, `__meridian-subagent`, `__meridian-orchestration`, `__meridian-spawn`, `__meridian-managed-install`.

### `@haowjy/meridian-dev-workflow` (dev methodology)

Opinionated dev workflow: `coder`, `reviewer`, `reviewer-*`, `verifier`, `investigator`, `researcher`, `documenter`, `smoke-tester`, `unit-tester`, `browser-tester`, plus skills like `dev-workflow`, `design`, `planning`, `reviewing`, `work-coordination`, `documenting`, `issues`.

### Migration

1. Create `meridian-dev-workflow` repo
2. Slim `meridian-agents` to core runtime only
3. Existing users: `meridian sources install @haowjy/meridian-dev-workflow`

## Open Questions

1. **Multiple items syntax** — `@owner/repo:a,b,c` (comma-separated) vs `@owner/repo:a:b:c` (chained colons) vs repeated args? Comma-separated is cleanest — colons are already overloaded with `agent:name`.

2. **Unified `items` field vs separate `agents`/`skills`** — cleaner to have one `items` list in TOML, but needs migration path from existing manifests that use `agents = [...]` and `skills = [...]`.

3. **`--rename` future** — keep in CLI or make TOML-only for rare cases?

## Verification

1. Parse inline items: `meridian sources install @haowjy/meridian-agents:reviewer --dry-run` should filter to just the reviewer agent + its skill deps
2. Backwards compat: `meridian sources install @haowjy/meridian-agents --agents reviewer` still works
3. Mixed: inline + flags union correctly
4. Unqualified resolution: `reviewer` resolves to `agent:reviewer` from source layout
5. Collision handling: error message when name is ambiguous between agent and skill
6. Existing smoke tests still pass: `tests/smoke/install/install-cycle.md`
