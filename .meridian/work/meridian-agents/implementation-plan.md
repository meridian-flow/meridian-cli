# Implementation Plan: Managed Agent Sources Refactor

## 1. Goal

Implement the new managed-agent-source architecture with the smallest coherent codebase possible:

- `.agents/` is the only runtime discovery root
- `.meridian/agents.toml` declares sources
- `.meridian/agents.lock` records resolved installed state
- `meridian install/update/upgrade/remove` replace the old sync UX
- core runtime commands auto-ensure the default orchestrator and default subagent from installed provenance or the bootstrap `meridian-agents` source
- ambient discovery, bundled fallback, harness mirroring, and temp materialization are deleted

This plan is code-facing. It names the current modules that should be removed, rewritten, or split.

## 2. Big Cuts

### Delete multi-root discovery

These areas encode the old "discover from many places and merge" model and should be removed or collapsed to `.agents/` only:

- [settings.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/config/settings.py)
  `SearchPathConfig`, env aliases for search paths, `resolve_search_paths()`, `resolve_path_list()`
- [agent.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/agent.py)
  `_agent_search_dirs()`, `scan_agent_profiles()` duplicate-resolution behavior, bundled fallback inside `load_agent_profile()`, hard-coded `builtin_profiles()`
- [skill.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/skill.py)
  `_skill_search_dirs()`, multi-dir scanning, bundled fallback inside `SkillRegistry`
- [resolve.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/resolve.py)
  `search_paths` plumbing through launch-time resolution
- [catalog.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/catalog.py)
  bundled and builtin fallback in agent listing

### Delete bundled `.agents` fallback

These areas preserve Python-owned live content and should go away:

- [settings.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/config/settings.py)
  `bundled_agents_root()`
- [agent.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/agent.py)
  bundled profile scan and `builtin_profiles()`
- [skill.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/skill.py)
  bundled skills directory injection
- [catalog.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/catalog.py)
  bundled/builtin augmentation for listings
- [src/meridian/resources/.agents](/home/jimyao/gitrepos/meridian-channel/src/meridian/resources/.agents)

### Delete harness materialization

These areas implement the old "copy/rewrite into harness-native directories" path and should be removed:

- [materialize.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/materialize.py)
- [plan.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/plan.py)
  `materialize_for_harness()` use during primary launch planning
- [execute.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/execute.py)
  `_materialize_session_agent_name()`, `_cleanup_session_materialized()`
- [process.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/process.py)
  cleanup and orphan sweep
- [main.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/cli/main.py)
  startup cleanup of materialized files
- [diag.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/diag.py)
  repair/cleanup hooks tied to materialization
- related tests under `tests/harness/test_materialize.py` and launch/spawn tests that assert materialized names

### Delete install-time `.claude` mirroring

The current sync engine still treats `.claude` as a managed install target:

- [engine.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/sync/engine.py)
  `_prepare_claude_destination()`, `_create_claude_symlink()`, `.claude` conflict checks
- [sync_cmd.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/cli/sync_cmd.py)
  remove-path behavior that assumes `.claude` mirrors are managed state

The harness adapter may still describe native lookup paths for runtime warnings, but install must stop mutating those paths.

## 3. New Steady-State Shape

### Runtime discovery

Keep only:

- `.agents/agents/*.md`
- `.agents/skills/*/SKILL.md`

Catalog code should become simple repo-local scanners. No search-path config, no bundled fallback, no global directories.

### Managed source state

Add new state paths under `.meridian/`:

- `agents.toml`
- `agents.lock`
- `cache/agents/`

The current `sync.lock` / `cache/sync/` pair should be treated as legacy.

### Install metadata

Each external source must expose:

- `agents/`
- `skills/`
- `meridian-source.toml`

The installer resolves dependency closure from `meridian-source.toml`, not from parsing installed profile files.

### Runtime ensure seam

Add a single runtime seam:

- `plan_required_runtime_assets(repo_root) -> RuntimeAssetPlan`
- `ensure_runtime_assets(repo_root, plan) -> None`

Primary launch and spawn preparation should call that seam before trying to resolve the default orchestrator/subagent from `.agents/`.

## 4. Code Areas To Rewrite

### State/config layer

Rewrite:

- [paths.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/paths.py)
  add `agents_manifest_path`, `agents_lock_path`, `agents_cache_dir`; treat `sync_lock_path` and `sync_cache_dir` as legacy
- [settings.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/config/settings.py)
  remove search-path config, change defaults to `__meridian-orchestrator` / `__meridian-subagent`, keep `defaults.primary_agent` and `defaults.agent`

### Catalog layer

Rewrite:

- [agent.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/agent.py)
  scan only `.agents/agents`; no builtins; no bundled fallback
- [skill.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/skill.py)
  scan only `.agents/skills`; no search-path config or bundled fallback
- [catalog.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/catalog.py)
  list exactly what is installed

### Install/source layer

The current `lib/sync` package is the closest starting point, but it should be refactored aggressively to match the new data model:

- [config.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/sync/config.py)
  replace `[[sync.sources]]` with `.meridian/agents.toml [[sources]]`, `repo/path` with `kind/url/path`, and generic `items` selectors
- [cache.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/sync/cache.py)
  turn into source adapters for `git` and `path`
- [engine.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/sync/engine.py)
  replace raw directory discovery with exported-source manifest handling, dependency closure, ownership by canonical item id, and no `.claude` writes
- [hash.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/sync/hash.py)
  keep tree hashing, but full normalized visible-content semantics
- [lock.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/sync/lock.py)
  replace `sync.lock` schema with `agents.lock` resolved-state schema

The current module names can survive briefly, but the long-term goal should be install/source naming instead of sync naming.

### Launch/spawn layer

Rewrite:

- [resolve.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/resolve.py)
  remove search-path fallback behavior
- [plan.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/plan.py)
  call runtime ensure instead of materializing
- [prepare.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/prepare.py)
  call runtime ensure before resolving agent defaults
- [execute.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/execute.py)
  drop session materialization path entirely

## 5. Commit-Sized Implementation Order

### Step 1: Publish the shipping source

Create the real shipped content in the `meridian-agents` submodule:

- promote the draft agents/skills
- rename to `__meridian-orchestrator`, `__meridian-subagent`, `dev-orchestrator`
- add `meridian-source.toml`
- encode `depends_on`, `bundle_requires`, and managed/system metadata

This unblocks everything else. The installer should target the real source repo, not drafts.

### Step 2: Introduce new state files and config defaults

Change Meridian’s state/config surface first:

- add `.meridian/agents.toml` and `.meridian/agents.lock` path handling
- add `cache/agents/`
- switch config defaults to `__meridian-orchestrator` and `__meridian-subagent`
- keep old sync state as legacy; do not migrate it

Expected touched areas:

- [paths.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/paths.py)
- [settings.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/config/settings.py)
- config docs and smoke tests

### Step 3: Add exported-source manifest parsing and source adapters

Before rewriting the CLI, make the new source model real:

- `git` and `path` adapters
- parse `meridian-source.toml`
- introduce canonical item ids: `agent:name` / `skill:name`
- define resolved source records for `agents.lock`

This is the foundation for install, update, upgrade, remove, and runtime ensure.

### Step 4: Rebuild install/update/upgrade/remove on the new model

Refactor the current sync CLI and engine into the new install model:

- `meridian install`
- `meridian update`
- `meridian upgrade`
- `meridian remove`

Core behavior:

- write `.meridian/agents.toml`
- resolve sources
- compute dependency closure from `meridian-source.toml`
- install into `.agents/`
- write `.meridian/agents.lock`
- no `.claude` writes

At the end of this step, the new install layer should work in isolation even if the runtime still has old fallback paths.

### Step 5: Collapse catalog discovery to `.agents/` only

Once install is real, simplify lookup:

- remove `SearchPathConfig`
- delete multi-root resolution
- scan only repo-local `.agents/`
- remove bundled `.agents` fallback and hard-coded builtins

Expected touched areas:

- [settings.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/config/settings.py)
- [agent.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/agent.py)
- [skill.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/skill.py)
- [catalog.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/catalog.py)
- launch/spawn call sites that currently pass `search_paths`

### Step 6: Remove bundled Python-owned content

Delete:

- bundled `.agents` resources
- `bundled_agents_root()`
- `builtin_profiles()`
- listing-time bundled/builtin augmentation

At the end of this step, Python should no longer own live default agent content.

### Step 7: Remove materialization

Delete:

- [materialize.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/materialize.py)
- launch/spawn materialization call sites
- startup and doctor cleanup tied to materialization
- tests that assert materialized naming behavior

Primary launch and spawn should pass real installed profile names directly to the harness layer.

### Step 8: Add runtime auto-ensure for required defaults

Now add the only remaining fallback behavior:

- compute required runtime asset closure for `defaults.primary_agent` and `defaults.agent`
- if missing, ensure from installed provenance or bootstrap `meridian-agents`
- persist bootstrap installs into `.meridian/agents.toml` and `.meridian/agents.lock`
- fail only the commands that actually require those assets

Call sites:

- [plan.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/plan.py)
- [prepare.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/prepare.py)

### Step 9: Delete legacy sync naming and cleanup

After the new path is working:

- remove old `sync` command registration and help text
- rename types/functions/modules that still encode the old model
- delete legacy code paths left around only for the transition

This is where the refactor becomes intellectually clean instead of just functionally correct.

## 5a. Recommended Commit Sequence

The doc order above is architecturally correct, but the code should land in smaller slices that keep the tree runnable.

### Commit 1: Foundation state and config surface

Land the new names and paths before changing behavior:

- add `.meridian/agents.toml`, `.meridian/agents.lock`, and `cache/agents/` path fields
- rename runtime config surface from `default_primary_agent` to `primary_agent`
- switch built-in defaults to `__meridian-orchestrator` and `__meridian-subagent`
- update config docs, config ops, and targeted tests

This commit should not delete sync/discovery yet. It makes the new vocabulary real in code first.

### Commit 2: New source-manifest and lock primitives

Make the new install model representable without rewriting the whole CLI yet:

- add parser/models for `.meridian/agents.toml`
- add parser/models for `.meridian/agents.lock`
- define canonical item ids `agent:name` / `skill:name`
- add exported-source manifest parsing for `meridian-source.toml`
- add source-adapter seams for `git` and `path`

This commit should focus on data models and pure logic, not catalog/runtime call sites.

### Commit 3: Install engine on new state

Replace the old sync engine behavior while keeping discovery/runtime mostly intact:

- reconcile declared sources into `.agents/`
- compute closure from exported-source manifests
- write `.meridian/agents.lock`
- stop writing `.claude/`
- support `install`, `update`, `upgrade`, and `remove`

At the end of this commit, install management should work even if runtime still has old fallback paths.

### Commit 4: Collapse discovery to `.agents/` only

Now that install is real, simplify lookup aggressively:

- remove `SearchPathConfig`
- remove search-path config/env plumbing
- scan only `.agents/agents` and `.agents/skills`
- delete bundled fallback and builtin profile augmentation from catalog/listing

This commit should leave catalog and launch resolution with one discovery root and no ambient merge logic.

### Commit 5: Remove materialization

Delete the runtime copy/rewrite layer after direct discovery is stable:

- remove `materialize_for_harness()` and cleanup helpers
- remove materialized-name session plumbing
- pass installed profile names directly through launch/spawn
- delete materialization-specific cleanup and tests

### Commit 6: Runtime auto-ensure for required defaults

Add the final runtime bootstrap seam on top of the new install/discovery model:

- compute required runtime assets for `defaults.primary_agent` and `defaults.agent`
- ensure missing core assets from installed provenance or bootstrap `meridian-agents`
- persist bootstrap installs into `.meridian/agents.toml` and `.meridian/agents.lock`

### Commit 7: Cleanup and rename pass

After the new path is proven:

- remove old `sync` nouns from CLI/help/types where possible
- delete legacy sync state/code kept only for transition
- optionally start the separate `.lock`-for-mutex cleanup

### Parallel prerequisite: shipped source content

The `meridian-agents` repo still needs to publish the real source tree and `meridian-source.toml`. That work can happen in parallel, but Commit 3 and beyond should target the real exported source shape rather than draft files.

## 6. Areas That Should Basically Vanish

If the refactor is complete, these concepts should be gone from core code:

- configurable global agent/skill discovery roots
- `.claude` as an install destination
- bundled `.agents` package resources as runtime content
- hard-coded builtin agent profiles
- temp materialized agent/skill copies
- discovery-time conflict resolution across multiple roots
- split semantics between profile body and frontmatter for modification checks

## 7. Verification Strategy

Prefer smoke coverage over detailed unit expansion.

Add or update smoke flows for:

- install from `meridian-agents`
- update from lock without re-resolving
- upgrade a floating ref
- remove a source and prune owned content
- runtime bootstrap when `.agents/` is missing core defaults
- failure path when bootstrap/install fails
- local modification detection using full visible-content comparison
- no `.claude` writes during install/update/remove
- no bundled fallback when `.agents/` is missing

Keep targeted unit tests only for:

- source manifest parsing
- dependency closure
- hash/local-mod behavior
- lock read/write
- runtime ensure planner behavior

## 8. Optional Follow-On Cleanup

Not required for the main refactor, but architecturally desirable:

- stop using bare `.lock` names for mutex-style runtime files
- move advisory locking to hidden `.flock` sidecars or another internal-only path
- reserve `.lock` for developer-facing resolved state such as `.meridian/agents.lock`
