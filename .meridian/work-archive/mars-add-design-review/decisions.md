# Decision Log: mars add Design Review

## D1: Atomic Filter Replacement on Re-add

**Decided:** When `mars add` re-adds an existing source with any filter flags, the entire filter config is replaced atomically — not merged field-by-field.

**Why:** The current merge-on-presence logic (`apply_mutation` in sync/mod.rs:284-307) only overwrites filter fields that are explicitly set by the new command. This creates invalid mixed states when switching filter modes (e.g., re-adding with `--only-skills` when `agents = ["reviewer"]` was previously set would leave both `agents` and `only_skills` present). Atomic replacement is the only semantics that prevents invalid TOML and matches user intent.

**Rejected:** Field-level merge (current behavior). Would require the user to manually clear old filter fields before setting new ones. Also considered "error on conflicting re-add" — rejected because it breaks the common "re-add to change config" workflow.

## D2: No Transitive Dep Suppression in v1

**Decided:** Include mode installs named agents + all their transitive skill dependencies. There is no mechanism to exclude a transitive dep while keeping the agent.

**Why:** An agent that declares `skills: [planning]` presumably needs `planning` to function. Suppressing a transitive dep creates a broken runtime state. Mars already warns about missing skill references (`ValidationWarning::MissingSkill`), but allowing users to deliberately create this state adds complexity for a use case nobody has demonstrated.

**Future path:** If needed, per-agent exclude overrides in TOML (agent-level granularity, not source-level).

## D3: Filter Validation Deferred to Sync-Time

**Decided:** Filter name validation (do these agents/skills actually exist in the source?) happens at sync-time, not add-time.

**Why:** Add-time validation requires fetching the source tree, which is expensive, may fail (network), and makes `mars add` slow for what should be a config-authoring operation. Sync already validates discovered items against filters. Added recommendation: emit a warning for unmatched filter names at sync-time.

**Rejected:** Add-time validation with source fetch. Also considered a `--validate` flag — rejected as premature; sync already does this.

## D4: `mars remove` Stays Whole-Source Only

**Decided:** No filter-aware remove. Narrowing a source is done via re-add (`mars add source --agents subset`).

**Why:** "Remove" implies deletion; filter changes are updates. Adding filter-awareness to remove conflates two verbs and complicates the mutation model. The re-add path already works cleanly with atomic filter replacement (D1).

## D5: Category-Only Modes Are Enum Variants, Not Special Include Values

**Decided:** `OnlySkills` and `OnlyAgents` are new `FilterMode` enum variants, not special cases of Include or Exclude mode.

**Why:** Overloading Include with empty lists or sentinel values creates ambiguity (does `Include { agents: [], skills: [] }` mean "nothing" or "all skills"?). Explicit enum variants are unambiguous in code and serialize cleanly to TOML booleans.

## D6: Multi-Source Add Uses Single Sync

**Decided:** Multi-source add applies all UpsertSource mutations to the in-memory config, then runs sync once.

**Why:** Running N syncs for N sources is wasteful (each sync fetches, resolves, diffs, applies). Applying mutations in-memory is cheap; the expensive operation (sync) should run once over the complete desired state. This also avoids intermediate states where collision detection sees partial source sets.
