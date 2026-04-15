# Extension Model (Phase B)

Design the extension points for capability packages, rule files, harness-specific variants, `.mars/` canonical content store, managed target sync with cross-compilation, model catalog integration, and generalized item kinds.

See [overview](overview.md) for context. This design depends on [pipeline decomposition](pipeline-decomposition.md) Phase A being complete — specifically A1 (typed phases) for the new pipeline insertion point, and A2 (first-class LocalPackage) for local packages to discover new item kinds automatically.

## B1: Generalized Item Kinds + Rule Files

### Problem

`ItemKind` is currently a two-variant enum:

```rust
pub enum ItemKind {
    Agent,
    Skill,
}
```

Discovery hardcodes `agents/*.md` and `skills/*/SKILL.md` scan patterns. Adding a new kind (permissions, tools, MCP configs, rule files) requires modifying discovery, target building, diff, plan, apply, lock, and link — the same "8 file change" problem the prior extensibility analysis identified for new source types.

### Design

Keep `ItemKind` as a closed enum but extend it with new variants. A trait-based open system is wrong here because:
1. The number of item kinds is small (6-8 total) and changes rarely
2. Exhaustive match is a feature — the compiler catches every place that needs updating when a new kind is added
3. Each kind has genuinely different discovery, materialization, and merge semantics

```rust
#[derive(Debug, Clone, Copy, Hash, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ItemKind {
    Agent,
    Skill,
    Rule,        // NEW: per-model and per-harness behavioral instructions
    Permission,
    Tool,
    McpServer,
    Hook,
}
```

### Rule Files (renamed from "Soul Files")

Rule files are per-model and per-harness behavioral instructions — operational rules like "you're on opus, think deeply" or "you're on codex, go straight to code." They are NOT identity or personality (that's what "soul" implies). Claude Code already uses `.claude/rules/` as its native convention; mars materializes rules into that existing structure.

**Three categories of rules:**

1. **Shared rules** — apply to all harnesses and models. Generic behavioral instructions.
2. **Per-harness rules** — apply when running under a specific harness (e.g., Claude Code, Cursor, Codex). Live in harness-named subdirectories.
3. **Per-model rules** — apply when a specific model alias is active. Matched by filename to model alias at spawn time by the consuming system (meridian), not by mars.

**Package layout:**

```
rules/
  general.md              # shared rule — materialized to all targets
  code-style.md           # shared rule
  claude/                 # per-harness: Claude Code specific
    review.md             # → .claude/rules/review.md
    hooks-usage.md        # → .claude/rules/hooks-usage.md
  cursor/                 # per-harness: Cursor specific
    mdc-format.md         # → .cursor/rules/mdc-format.md
  codex/                  # per-harness: Codex specific
    sandbox.md            # → .codex/rules/sandbox.md
  opus.md                 # per-model: injected when model alias "opus" is used
  sonnet.md               # per-model: injected when model alias "sonnet" is used
```

**Discovery convention:**

Rules have a more complex discovery pattern than other item kinds because of the three categories:

```rust
DiscoveryConvention {
    kind: ItemKind::Rule,
    dir_name: "rules",
    pattern: DiscoveryPattern::RuleTree,  // NEW pattern type
}
```

`DiscoveryPattern::RuleTree` scans:
1. `rules/*.md` — shared rules and per-model rules (distinguished at materialization time by matching filename against model aliases)
2. `rules/<harness_id>/*.md` — per-harness rules, where `<harness_id>` matches a configured target's harness ID

```rust
pub enum DiscoveryPattern {
    /// Each *.<ext> file is one item (e.g. agents/*.md, permissions/*.toml).
    FlatFiles { extension: &'static str },
    /// Each subdirectory containing a marker file is one item (e.g. skills/*/SKILL.md).
    MarkerDirs { marker: &'static str },
    /// Rule tree: flat *.md files at root + harness-specific subdirectories.
    RuleTree,
}
```

**Discovered rule items carry category metadata:**

```rust
pub enum RuleCategory {
    /// rules/*.md that don't match a model alias — shared across all targets.
    Shared,
    /// rules/*.md that match a model alias — applied at spawn time.
    Model { alias: String },
    /// rules/<harness_id>/*.md — applied to a specific target.
    Harness { harness_id: String },
}
```

The category is determined during discovery by checking (requires both harness IDs from config and merged model aliases from B4):
- If the file is under `rules/<subdir>/` and `<subdir>` matches a configured harness ID → `Harness`
- If the file is `rules/<name>.md` and `<name>` matches a model alias from the merged `[models]` config (see B4 — merged from dependency tree + builtins during `resolve_graph()`) → `Model`
- Otherwise → `Shared`

**Materialization:**

Rules materialize differently per category:
- **Shared rules** → copied to all targets' `rules/` directory (e.g., `.claude/rules/general.md`, `.agents/rules/general.md`)
- **Per-harness rules** → copied only to the matching target's `rules/` directory (e.g., `rules/claude/review.md` → `.claude/rules/review.md`)
- **Per-model rules** → copied to `.mars/rules/` for meridian to read at spawn time. NOT materialized to targets (the consuming system applies them dynamically based on active model).

**Why renamed from "soul"?** "Soul" implies identity and personality — OpenClaw's Soul.md is about who the AI is. What we're building is operational instructions: coding style rules, harness-specific behavior, model-specific thinking patterns. "Rule" matches Claude Code's existing `.claude/rules/` convention and accurately describes the content's purpose.

### Per-Kind Discovery

Discovery moves from hardcoded path patterns to a registry of discoverers:

```rust
/// Convention for discovering items of a specific kind in a source tree.
pub struct DiscoveryConvention {
    pub kind: ItemKind,
    /// Directory under source root (e.g. "agents", "permissions").
    pub dir_name: &'static str,
    /// How items are identified within the directory.
    pub pattern: DiscoveryPattern,
}

/// Built-in discovery conventions.
pub fn conventions() -> Vec<DiscoveryConvention> {
    vec![
        DiscoveryConvention {
            kind: ItemKind::Agent,
            dir_name: "agents",
            pattern: DiscoveryPattern::FlatFiles { extension: "md" },
        },
        DiscoveryConvention {
            kind: ItemKind::Skill,
            dir_name: "skills",
            pattern: DiscoveryPattern::MarkerDirs { marker: "SKILL.md" },
        },
        DiscoveryConvention {
            kind: ItemKind::Rule,
            dir_name: "rules",
            pattern: DiscoveryPattern::RuleTree,
        },
        DiscoveryConvention {
            kind: ItemKind::Permission,
            dir_name: "permissions",
            pattern: DiscoveryPattern::FlatFiles { extension: "toml" },
        },
        DiscoveryConvention {
            kind: ItemKind::Tool,
            dir_name: "tools",
            pattern: DiscoveryPattern::FlatFiles { extension: "toml" },
        },
        DiscoveryConvention {
            kind: ItemKind::McpServer,
            dir_name: "mcp",
            pattern: DiscoveryPattern::FlatFiles { extension: "toml" },
        },
        DiscoveryConvention {
            kind: ItemKind::Hook,
            dir_name: "hooks",
            pattern: DiscoveryPattern::MarkerDirs { marker: "hook.toml" },
        },
    ]
}
```

`discover_source()` iterates over conventions instead of hardcoding two scan patterns. Adding a new kind means adding one entry to `conventions()`.

### Per-Kind Materialization

Content items (agents, skills, rule files) are materialized by copying files to the canonical store. Capability items are materialized differently — they generate config fragments that merge into runtime-specific config files.

```rust
/// How an item kind is materialized into the canonical store (.mars/).
pub enum MaterializationStrategy {
    /// Copy source content directly (agents, skills, hooks).
    ContentCopy,
    /// Rule files — content copy with category-aware target routing.
    RuleCopy,
    /// Parse source and generate config fragments (permissions, tools, MCP).
    ConfigFragment { format: FragmentFormat },
}

pub enum FragmentFormat {
    /// TOML fragments that merge into a target config.
    Toml,
    /// JSON fragments that merge into a target config.
    Json,
}

impl ItemKind {
    pub fn materialization(&self) -> MaterializationStrategy {
        match self {
            Self::Agent | Self::Skill | Self::Hook => MaterializationStrategy::ContentCopy,
            Self::Rule => MaterializationStrategy::RuleCopy,
            Self::Permission | Self::Tool | Self::McpServer => MaterializationStrategy::ConfigFragment {
                format: FragmentFormat::Toml,
            },
        }
    }
}
```

### Destination Path Convention

Each kind has a deterministic destination path in `.mars/`:

```rust
impl ItemKind {
    pub fn dest_dir(&self) -> &'static str {
        match self {
            Self::Agent => "agents",
            Self::Skill => "skills",
            Self::Rule => "rules",
            Self::Permission => "permissions",
            Self::Tool => "tools",
            Self::McpServer => "mcp",
            Self::Hook => "hooks",
        }
    }
}
```

### Lock Compatibility

The lock file already stores `kind` as a lowercase string. New kinds serialize naturally:

```toml
[items."rules/general.md"]
source = "base"
kind = "rule"
source_checksum = "sha256:..."
installed_checksum = "sha256:..."
dest_path = "rules/general.md"

[items."rules/claude/review.md"]
source = "base"
kind = "rule"
source_checksum = "sha256:..."
installed_checksum = "sha256:..."
dest_path = "rules/claude/review.md"
```

Old mars versions encountering unknown kinds in the lock will fail to deserialize the `ItemKind` enum. This is acceptable — upgrading mars is expected when packages use new features:

```rust
// In ItemKind deserialization
_ => Err(format!("unknown item kind '{}' — upgrade mars to handle this package", s))
```

### FilterConfig Extension

The current `FilterConfig` has `agents` and `skills` fields. Extend with a generic filter:

```rust
pub struct FilterConfig {
    // Existing kind-specific filters (backwards compatible)
    pub agents: Option<Vec<ItemName>>,
    pub skills: Option<Vec<ItemName>>,
    pub exclude: Option<Vec<ItemName>>,
    pub rename: Option<RenameMap>,
    pub only_skills: bool,
    pub only_agents: bool,
    // New: generic kind filter
    pub include_kinds: Option<Vec<ItemKind>>,  // if set, only install these kinds
    pub exclude_kinds: Option<Vec<ItemKind>>,  // if set, skip these kinds
}
```

**Filter precedence**: Kind filters apply first, then item-level filters apply within the surviving kinds. Conflicting filters (`only_agents = true` + `include_kinds = ["permission"]`) fail at config validation time with a clear error.

---

## B2: Harness-Specific Variants

### Problem

Different harnesses have different capabilities. An agent profile optimized for Claude Code may not work well with Cursor or Codex. Currently, packages ship one version and consumers manually maintain harness-specific copies.

### Design

Packages can ship harness-specific variants alongside the default version. Variant resolution happens at sync time based on the configured managed targets.

**Package layout convention**:

```
agents/
  coder.md                    # default version
  coder.claude.md             # Claude Code variant
  coder.cursor.md             # Cursor variant
skills/
  planning/
    SKILL.md                  # default
    SKILL.claude.md           # Claude Code variant
rules/
  general.md                  # default (rules can have variants too)
  general.claude.md           # Claude-specific variant
```

**Naming convention**: `<name>.<harness>.<ext>` for flat files, `<MARKER>.<harness>.<ext>` for marker dirs. The harness identifier matches managed target names (e.g., `.claude` → `claude`, `.cursor` → `cursor`).

**Variant parsing rule**: The harness identifier is extracted by matching the second-to-last dot-separated segment against the set of known managed target harness IDs from config. The algorithm:

1. Split filename (without final extension) on `.` — e.g., `coder.claude` → `["coder", "claude"]`
2. If the last segment matches a known harness ID (from `[[settings.targets]]`) → it's a variant. Base name is everything before that segment.
3. If no match → it's a base item with a dotted name (e.g., `my.company.agent.md` is base name `my.company.agent`).

This is unambiguous because variant resolution requires the harness ID set from config. A file like `review.v2.claude.md` is a variant of `review.v2` for `claude` only if `claude` is a configured target. Without configured targets, no files are variants.

**Constraint**: Item names MAY contain dots. Harness IDs in `[[settings.targets]]` MUST NOT contain dots (enforced at config validation). This ensures the last-segment match is always unambiguous.

**Discovery changes**: Discovery finds all variants and attaches them to the base item. The algorithm is:

```rust
/// A discovered item with optional harness-specific variants.
pub struct DiscoveredItem {
    pub id: ItemId,
    pub source_path: PathBuf,
    /// Harness-specific variants: harness_name → source_path.
    pub variants: IndexMap<String, PathBuf>,
}
```

**Variant attachment algorithm** (inside `discover_source()`):

1. Scan all files matching the convention pattern (e.g., `agents/*.md`)
2. For each file, check if the last dot-separated stem segment matches a known harness ID
3. If yes → set aside as variant (harness_id, base_name, path)
4. If no → create base `DiscoveredItem`
5. After scanning all files, attach collected variants to their base items by matching `base_name`
6. Variants without a matching base item emit a `Diagnostic::Warning` and are skipped

This requires passing the set of known harness IDs and model aliases into `discover_source()`:

```rust
pub fn discover_source(
    tree_path: &Path,
    fallback_name: Option<&str>,
    harness_ids: &HashSet<String>,  // from settings.targets
    model_aliases: &HashSet<String>,  // from merged [models] config (B4)
) -> Result<(Vec<DiscoveredItem>, Vec<Diagnostic>), MarsError>
```

The `model_aliases` parameter comes from `ResolvedState.model_aliases` (merged during `resolve_graph()` per B4). It's used by `DiscoveryPattern::RuleTree` to classify per-model vs. shared rules.

**Resolution in target building**: During `build_target()`, the configured managed targets determine which variants are relevant. For each item:

1. If a variant exists for a managed target's harness → use the variant for that target
2. If no variant exists → use the default version
3. Variants for unconfigured harnesses are ignored (not installed)

**TargetItem extension**:

```rust
pub struct TargetItem {
    pub id: ItemId,
    pub origin: SourceOrigin,
    pub source_id: SourceId,
    pub source_path: PathBuf,          // default version
    pub dest_path: DestPath,
    pub source_hash: ContentHash,
    pub is_flat_skill: bool,
    pub rewritten_content: Option<String>,
    pub materialization: Materialization,
    /// Harness-specific variant paths (harness_name → source_path).
    /// Empty if no variants exist. Used during managed target sync.
    pub variants: IndexMap<String, VariantSource>,
}

pub struct VariantSource {
    pub source_path: PathBuf,
    pub source_hash: ContentHash,
    /// Rewritten content for this variant (same transform as base item).
    /// Ensures variant content goes through the same rewrite pipeline
    /// (frontmatter transforms, skill renames) as the base item.
    pub rewritten_content: Option<String>,
}
```

**Canonical store gets the default version**. `.mars/` always contains the default (non-variant) content. Variants are resolved and applied only when syncing managed targets.

**Lock tracking**: Variants are tracked in the lock alongside the base item:

```toml
[items."agents/coder.md"]
source = "base"
kind = "agent"
source_checksum = "sha256:abc..."
installed_checksum = "sha256:abc..."
dest_path = "agents/coder.md"

[items."agents/coder.md".variants]
claude = "sha256:def..."
cursor = "sha256:ghi..."
```

This keeps variant checksums in the lock for change detection without creating separate lock entries for each variant. The variant content lives in the source; only the hash is tracked.

**What's NOT designed here**: Variant-specific filtering (e.g., "only install the claude variant of this agent"). The initial implementation installs all available variants and resolves at target sync time. If filtering is needed, it can be added to `FilterConfig` later.

---

## B3: `.mars/` Canonical Store + Managed Target Sync

### Problem

The prior design had `.agents/` as the managed root — the centralized source of truth that managed targets derived from. This is wrong because:

1. If a harness reads `.agents/` directly (e.g., Codex), mars can't control what it sees per-harness
2. You can't have "shared between Claude and Cursor but not Codex" content when `.agents/` is the universal source
3. `.agents/` is conceptually a target for harnesses that don't have their own directory, not a neutral store

### Reframing

**`.mars/` is the canonical content store.** ALL target directories — `.agents/`, `.claude/`, `.codex/`, `.cursor/` — are managed outputs that mars materializes content INTO. No target is special. `.agents/` is simply the default target for harnesses that don't have their own directory convention.

### Design

**Directory structure:**

```
project/
  mars.toml                   # committed
  mars.lock                   # committed
  .mars/                      # gitignored — derived state
    content/                  # canonical resolved content
      agents/
      skills/
      rules/
      rules/claude/           # per-harness rules
      permissions/
      tools/
      mcp/
      hooks/
    models-cache.json         # model metadata cache
  .agents/                    # managed target (default)
  .claude/                    # managed target
    agents/                   # copied from .mars/ (with variants resolved)
    skills/
    rules/                    # shared rules + claude-specific rules merged
  .cursor/                    # managed target
```

**`.mars/` is entirely gitignored.** It's derived state — `mars sync` regenerates it from `mars.toml` + `mars.lock` + sources. Only `mars.toml` and `mars.lock` at project root are committed.

**ManagedTarget:**

```rust
/// A directory that mars manages — materialized from .mars/ with target-specific content.
pub struct ManagedTarget {
    /// Target directory path relative to project root (e.g. ".claude", ".agents").
    pub path: String,
    /// Harness identifier for variant resolution (derived from path, e.g. "claude").
    pub harness_id: String,
    /// Which runtime adapter handles capability cross-compilation.
    pub adapter: AdapterKind,
    /// Which item kinds to include in this target (None = all).
    pub include_kinds: Option<Vec<ItemKind>>,
    /// Which item kinds to exclude from this target.
    pub exclude_kinds: Option<Vec<ItemKind>>,
}
```

**AdapterKind — closed enum for adapter selection:**

```rust
/// Closed enum for adapter selection — matches the "single binary, no dynamic loading" constraint.
/// Adapter logic is method dispatch on this enum, not trait objects.
pub enum AdapterKind {
    Claude,
    Cursor,
    Codex,
    Generic,  // fallback for unknown targets
}

impl AdapterKind {
    /// Select adapter from target path.
    pub fn from_target(path: &str) -> Self {
        match path.trim_start_matches('.') {
            "claude" => Self::Claude,
            "cursor" => Self::Cursor,
            "codex" => Self::Codex,
            "agents" => Self::Generic,
            _ => Self::Generic,
        }
    }
}
```

**Copy-based materialization — always copy, never symlink to targets:**

All content is COPIED from `.mars/` to targets. Reasons:
- **Windows**: symlinks need admin/developer mode
- **Git**: symlinks are finicky across platforms
- **Atomicity**: copy + tmp+rename is simpler for crash safety
- **No broken links**: if `.mars/` is rebuilt, targets still work until next sync
- **Variant resolution**: copies can contain variant-specific content; symlinks can only point to one source

**Configuration:**

```toml
[settings]
# Managed targets — mars copies content from .mars/ into these
targets = ['.claude', '.codex']

# Optional: also generate .agents/ (default target)
# If targets is empty or omitted, .agents/ is the sole target (backwards compat)
```

When `targets` is not specified, `.agents/` is the sole target (backwards compatibility with existing projects). When `targets` is specified, only the listed targets are materialized. To also get `.agents/`, include it in the list:

```toml
targets = ['.agents', '.claude', '.codex']
```

Backwards compatibility: the existing `links = [".claude"]` syntax is supported and equivalent to `targets = ['.agents', '.claude']` — the old behavior always had `.agents/` as the managed root plus linked targets.

**Sync flow:**

```
mars sync
  → Phase A pipeline (load → resolve → discover → target → diff → plan)
  → apply_plan: write resolved content to .mars/
  → sync_managed_targets: for each configured target:
      1. Content sync: copy items from .mars/, substituting variants
      2. Rule routing: shared rules to all targets, per-harness rules to matching target only
      3. Capability cross-compilation: merge config fragments into target-native configs
      4. Orphan cleanup: remove files in target that are no longer in .mars/
  → finalize: write lock, build report
```

**Content sync algorithm:**

```rust
fn sync_target_content(
    content_root: &Path,        // .mars/
    target: &ManagedTarget,
    items: &[TargetItem],
) -> Result<Vec<ReconcileOutcome>, MarsError> {
    let mut outcomes = Vec::new();
    
    for item in items {
        // Skip items excluded from this target
        if !target.should_include(&item.id.kind) {
            continue;
        }
        
        // For rules: apply category-based routing
        if item.id.kind == ItemKind::Rule {
            if let Some(category) = &item.rule_category {
                match category {
                    RuleCategory::Harness { harness_id } if harness_id != &target.harness_id => continue,
                    RuleCategory::Model { .. } => continue,  // model rules stay in .mars/
                    _ => {}  // shared rules go to all targets
                }
            }
        }
        
        // Determine source: variant if available, else default from canonical store
        let source = match item.variants.get(&target.harness_id) {
            Some(variant) => variant.effective_content_path(),
            None => content_root.join(&item.dest_path),
        };
        
        // Determine destination in target
        let dest = target.resolve_dest(&item);  // may remap paths (e.g., rules/claude/x.md → rules/x.md)
        
        let desired = DesiredState::CopyFile {
            source,
            hash: item.source_hash.clone(),
        };
        let outcome = reconcile_one(&dest, desired, false)?;
        outcomes.push(outcome);
    }
    
    // Orphan cleanup: remove files in target that aren't in the item set
    cleanup_orphans(&target.path, &expected_paths, &mut outcomes)?;
    
    outcomes
}
```

**Per-harness rule path remapping:** When per-harness rules are materialized to their matching target, the harness subdirectory is flattened. Example: `rules/claude/review.md` in `.mars/` → `.claude/rules/review.md` in the target (not `.claude/rules/claude/review.md`). This matches Claude Code's native `.claude/rules/` convention.

**First-run adoption:** When a target directory has existing content not yet managed by mars, mars scans for conflicts, offers to merge unique user files into `.mars/`, and then takes ownership. This is the legacy link adoption behavior, preserved for migration.

**Orphan cleanup:** When items are removed from `.mars/`, the corresponding files in all managed targets are also removed. The reconcile layer handles this by comparing each target directory against the expected item set for that target.

### Relationship to A4 (Shared Reconciliation)

Managed target sync uses the same reconciliation primitives from A4:

- **Layer 1 (atomic fs ops)**: `atomic_copy_file`, `atomic_copy_dir`, `safe_remove` — used for all target materialization
- **Layer 2 (item-level reconciliation)**: `reconcile_one`, `scan_destination` — used for per-item sync to targets

### Failure Semantics and Crash Safety

Target sync happens **after** content apply to `.mars/` and **before** lock write:

1. **Content is applied first** — `.mars/` is in a consistent state
2. **Managed targets are synced** — content + capabilities written to targets
3. **Lock is written** — records what was installed

If target sync fails:
- `.mars/` is already correct
- **Lock IS still written** — the lock records what's in `.mars/`, which is the source of truth. Target sync state is tracked separately.
- Managed targets may be partially updated — each item is atomic (tmp+rename) but the full target sync is not transactional
- Re-running `mars sync` converges: content diffs as unchanged, targets get re-synced

**Error handling**: Target sync errors are **non-fatal by default**. Content sync to `.mars/` is the primary value; target sync is additive. The lock always reflects the `.mars/` state regardless of target sync outcome. Target sync status is reported in `SyncReport.target_outcomes` so the CLI can display which targets succeeded/failed. Opt-in `--strict` makes target sync failures fatal.

---

## B4: Model Catalog Integration

### Problem

Model alias → harness + model resolution is needed for agent spawning. The existing `ModelAlias` struct only supports pinned model IDs, but real usage requires auto-resolution against a live model catalog — models are released frequently, and hardcoding IDs means manual updates on every release. The model catalog must integrate into the pipeline's config merge system so packages can distribute model aliases with operational descriptions, and the dependency tree's merge precedence applies uniformly.

### Current State (Already Implemented)

The `[models]` section already exists in `Config`:

```rust
pub struct Config {
    // ...
    pub models: IndexMap<String, ModelAlias>,
}
```

`models.rs` already implements:
- `ModelAlias` struct with `harness`, `model`, `description`
- `ModelsCache` with `CachedModel` entries (cost, limits, capabilities)
- `fetch_models()` to pull from models.dev API
- `read_cache()` / `write_cache()` for cache persistence
- `resolve_alias()` for alias lookup

### Design: ModelAlias with Two Modes

The current `ModelAlias` only supports pinned model IDs. Extend to support two modes:

**Pinned** — explicit model ID, no resolution needed:

```toml
[models.fast]
harness = 'claude'
model = 'claude-haiku-4-5'
description = 'Fast and cheap'
```

**Auto-resolve** — pattern matching against the models cache:

```toml
[models.opus]
harness = 'claude'
provider = 'anthropic'
match = ['opus']
exclude = ['*-preview']
description = 'Best reasoning model'
```

```rust
/// A model alias — either pinned to a specific model ID or auto-resolved
/// against the models cache at resolution time.
pub struct ModelAlias {
    pub harness: String,
    pub description: Option<String>,
    pub spec: ModelSpec,
}

pub enum ModelSpec {
    /// Explicit model ID — no resolution needed.
    Pinned { model: String },
    /// Pattern-based resolution against models cache.
    AutoResolve {
        provider: String,
        match_patterns: Vec<String>,
        exclude_patterns: Vec<String>,
    },
}
```

**Serde**: The two modes are distinguished by field presence — `model` field means pinned, `match` field means auto-resolve. Both present is a config validation error.

```rust
// Deserialization logic (simplified):
if raw.model.is_some() && raw.match_patterns.is_some() {
    return Err("model alias cannot have both 'model' and 'match'");
}
if let Some(model) = raw.model {
    ModelSpec::Pinned { model }
} else if let Some(patterns) = raw.match_patterns {
    ModelSpec::AutoResolve {
        provider: raw.provider.unwrap_or_else(|| infer_provider(&raw.harness)),
        match_patterns: patterns,
        exclude_patterns: raw.exclude.unwrap_or_default(),
    }
} else {
    return Err("model alias must have either 'model' or 'match'");
}
```

### Auto-Resolve Algorithm

Auto-resolution runs against the models cache (`.mars/models-cache.json`):

```rust
pub fn auto_resolve(
    spec: &ModelSpec::AutoResolve,
    cache: &ModelsCache,
) -> Option<String> {
    let candidates: Vec<&CachedModel> = cache.models.iter()
        // 1. Filter by provider
        .filter(|m| m.provider == spec.provider)
        // 2. All match patterns must hit (AND)
        .filter(|m| spec.match_patterns.iter().all(|p| glob_match(p, &m.id)))
        // 3. No exclude patterns may hit (OR)
        .filter(|m| !spec.exclude_patterns.iter().any(|p| glob_match(p, &m.id)))
        // 4. Skip *-latest suffix (synthetic aliases, not real models)
        .filter(|m| !m.id.ends_with("-latest"))
        .collect();

    // 5. Sort by newest release_date, then shortest ID (prefer canonical names)
    candidates.sort_by(|a, b| {
        b.release_date.cmp(&a.release_date)
            .then(a.id.len().cmp(&b.id.len()))
    });

    // 6. Pick first
    candidates.first().map(|m| m.id.clone())
}
```

**Glob matching**: `*` matches any sequence of characters; everything else is literal. This is intentionally simpler than full glob — no `?`, no character classes. Sufficient for model ID patterns.

```rust
fn glob_match(pattern: &str, text: &str) -> bool {
    // Simple glob: split on '*', check that all literal segments appear in order.
    let parts: Vec<&str> = pattern.split('*').collect();
    // ... standard glob matching
}
```

### Builtin Aliases

Mars ships default auto-resolve specs for common model families. These provide working defaults without any `[models]` config — a fresh project can immediately use `opus`, `sonnet`, etc.

```rust
pub fn builtin_aliases() -> IndexMap<String, ModelAlias> {
    indexmap! {
        "opus" => ModelAlias {
            harness: "claude", description: Some("Strong orchestrator..."),
            spec: ModelSpec::AutoResolve {
                provider: "anthropic", match_patterns: vec!["opus"],
                exclude_patterns: vec![],
            },
        },
        "sonnet" => ModelAlias {
            harness: "claude", description: Some("Balanced speed and quality"),
            spec: ModelSpec::AutoResolve {
                provider: "anthropic", match_patterns: vec!["sonnet"],
                exclude_patterns: vec![],
            },
        },
        "haiku" => ModelAlias {
            harness: "claude", description: Some("Fast and cheap"),
            spec: ModelSpec::AutoResolve {
                provider: "anthropic", match_patterns: vec!["haiku"],
                exclude_patterns: vec![],
            },
        },
        "codex" => ModelAlias {
            harness: "codex", description: Some("OpenAI Codex"),
            spec: ModelSpec::AutoResolve {
                provider: "openai", match_patterns: vec!["codex"],
                exclude_patterns: vec![],
            },
        },
        "gpt" => ModelAlias {
            harness: "codex", description: Some("OpenAI GPT flagship"),
            spec: ModelSpec::AutoResolve {
                provider: "openai", match_patterns: vec!["gpt-5.*"],
                exclude_patterns: vec!["*-mini", "*-nano", "*-chat-*", "*-turbo"],
            },
        },
        "gemini" => ModelAlias {
            harness: "gemini", description: Some("Google Gemini Pro"),
            spec: ModelSpec::AutoResolve {
                provider: "google", match_patterns: vec!["gemini", "pro"],
                exclude_patterns: vec!["*-flash", "*-lite"],
            },
        },
    }
}
```

**Fallback model IDs**: When the cache is empty (first run, no network), builtins fall back to hardcoded model IDs so aliases still resolve:

```rust
pub fn fallback_model_ids() -> IndexMap<&'static str, &'static str> {
    indexmap! {
        "opus" => "claude-opus-4",
        "sonnet" => "claude-sonnet-4",
        "haiku" => "claude-haiku-4",
        "codex" => "codex-1",
        "gpt" => "gpt-5.3",
        "gemini" => "gemini-2.5-pro",
    }
}
```

### Model Config Merge from Dependency Tree

Model aliases merge from the dependency tree using the **same precedence pattern** as permissions, tools, MCP, and rules:

```
consumer mars.toml > dependencies (in declaration order) > builtins > fallback IDs
```

This merge happens during `resolve_graph()` (A1 Phase 2), alongside dependency resolution. The resolver walks the dependency tree and collects `[models]` sections from each package manifest:

```rust
fn merge_model_config(
    consumer: &IndexMap<String, ModelAlias>,
    deps: &[ResolvedDep],  // in declaration order
) -> (IndexMap<String, ModelAlias>, Vec<Diagnostic>) {
    let mut merged = builtin_aliases();
    let mut diagnostics = Vec::new();

    // Layer 1: dependencies in reverse declaration order (last declared = lowest priority)
    for dep in deps.iter().rev() {
        if let Some(manifest) = &dep.manifest {
            for (name, alias) in &manifest.models {
                if merged.contains_key(name) && !is_builtin(name) {
                    // Two deps at same level define same alias: first declared wins
                    diagnostics.push(Diagnostic::warning(
                        "model-alias-conflict",
                        format!(
                            "model alias `{name}` defined by both `{}` and prior dep — using first declared",
                            dep.name
                        ),
                    ));
                    continue;
                }
                merged.insert(name.clone(), alias.clone());
            }
        }
    }

    // Layer 2: consumer overrides everything
    for (name, alias) in consumer {
        merged.insert(name.clone(), alias.clone());
    }

    (merged, diagnostics)
}
```

The merged model aliases are stored in `ResolvedState` and available to all subsequent pipeline phases:

```rust
pub struct ResolvedState {
    pub loaded: LoadedConfig,
    pub graph: ResolvedGraph,
    pub model_aliases: IndexMap<String, ModelAlias>,  // merged from tree + builtins
}
```

**Why merge in resolve_graph, not load_config?** Because dependency manifests are loaded during resolution — `load_config()` only reads the consumer's own config. The dependency tree isn't available until resolution runs.

### Manifest Extension for Model Exports

Packages export `[models]` alongside `[dependencies]` in their manifest:

```rust
pub struct Manifest {
    pub package: PackageMetadata,
    pub dependencies: IndexMap<String, ManifestDep>,
    pub models: IndexMap<String, ModelAlias>,  // NEW
}
```

`load_manifest()` extracts `[models]` from the package's mars.toml. Packages distribute model aliases with operational descriptions — the descriptions are the real value:

```toml
# In a package's mars.toml (e.g., meridian-base)
[models.opus]
harness = 'claude'
provider = 'anthropic'
match = ['opus']
description = 'Strong orchestrator. Creative but can hallucinate. Best for architecture and design.'

[models.sonnet]
harness = 'claude'
provider = 'anthropic'
match = ['sonnet']
description = 'Balanced speed and quality. Good default for most tasks.'

[models.haiku]
harness = 'claude'
provider = 'anthropic'
match = ['haiku']
description = 'Fast and cheap. Use for research, exploration, bulk work.'
```

Consumer overrides any field — harness, spec, description. A consumer can pin an alias that a package defined as auto-resolve, or change the description to match their operational context.

### Integration with Rule Discovery (B1)

Model aliases inform rule discovery: `rules/opus.md` is a per-model rule only if `opus` is a known model alias. The merged model alias set (from `ResolvedState.model_aliases`) is passed to `discover_source()` alongside the harness ID set:

```rust
pub fn discover_source(
    tree_path: &Path,
    fallback_name: Option<&str>,
    harness_ids: &HashSet<String>,
    model_aliases: &HashSet<String>,  // from merged [models] config
) -> Result<(Vec<DiscoveredItem>, Vec<Diagnostic>), MarsError>
```

Rule category determination (from B1) uses both sets:
- `rules/<subdir>/` where `<subdir>` matches a harness ID → `RuleCategory::Harness`
- `rules/<name>.md` where `<name>` matches a model alias → `RuleCategory::Model`
- Otherwise → `RuleCategory::Shared`

This creates an explicit dependency: **B4 model config merge must complete before B1 rule discovery runs.** In the pipeline, this is naturally satisfied because `resolve_graph()` (which merges model config) runs before `build_target()` (which runs discovery).

### Integration with CapabilitySet

Model aliases are included in the `CapabilitySet` so runtime adapters can reference them when materializing configs:

```rust
pub struct CapabilitySet {
    pub permissions: Vec<PermissionPolicy>,
    pub tools: Vec<ToolDefinition>,
    pub mcp_servers: Vec<McpServerConfig>,
    pub hooks: Vec<HookDefinition>,
    pub model_aliases: IndexMap<String, ModelAlias>,  // from merged config
}
```

This allows adapters to emit model configuration into target-native formats. For example, the Claude adapter could write model alias information to `.claude/settings.json` if Claude Code supports reading it.

### Cache Location and Lifecycle

**Cache location**: `.mars/models-cache.json` — gitignored as part of `.mars/`. The cache is a network-fetched artifact, not a package artifact.

**Refresh lifecycle**: `mars models refresh` fetches live data from models.dev and writes the cache. Meridian triggers this when the cache TTL is stale. Mars does NOT auto-refresh during `mars sync` — the cache is a separate concern with its own staleness policy.

**Cache schema**:

```rust
pub struct ModelsCache {
    pub fetched_at: DateTime<Utc>,
    pub models: Vec<CachedModel>,
}

pub struct CachedModel {
    pub id: String,
    pub provider: String,
    pub release_date: Option<NaiveDate>,
    pub description: Option<String>,
    // ... cost, limits, capabilities (already implemented)
}
```

### CLI Commands

All model commands operate on the merged alias set (consumer + deps + builtins) and the local cache:

- **`mars models refresh`** — fetch from models.dev API, write cache to `.mars/models-cache.json`
- **`mars models list`** — display cached models with optional filters (`--provider`, `--harness`)
- **`mars models resolve NAME`** — resolve alias against merged config + builtins + cache. Shows resolution chain: which layer provided the alias, what pattern matched, what model ID was resolved.
- **`mars models alias`** — list all aliases: source (consumer/dep/builtin), spec (pinned/auto-resolve), resolved model ID, description
- **`mars models alias NAME --harness H --match P [--exclude P] [--provider P] [--model M] [--description D]`** — add/update alias in consumer mars.toml
- **`mars models alias --remove NAME`** — remove alias from consumer mars.toml

All commands support `--json` for structured output.

**`mars models resolve` output example:**

```json
{
  "alias": "opus",
  "source": "builtin",
  "spec": {
    "type": "auto_resolve",
    "provider": "anthropic",
    "match": ["opus"],
    "exclude": []
  },
  "resolved_model": "claude-opus-4-6-20260401",
  "harness": "claude",
  "description": "Strong orchestrator..."
}
```

### What Mars Does NOT Do

Mars doesn't route models at runtime. It provides the alias table (merged from dependency tree + builtins) and the cache (fetched from models.dev). Meridian reads these at spawn time to resolve `--model opus` to an actual model ID and harness.

---

## B5: Permission Sync

### Problem

Packages can install agent and skill content, but can't declare what runtime permissions those assets expect.

### Package Schema

Permission policies are declared as TOML files in `permissions/`:

```toml
# permissions/sandbox-policy.toml

[policy]
name = "sandbox-policy"
description = "Restrictive sandbox for untrusted agents"

approval_mode = "auto"
sandbox_tier = "restricted"
allowed_tools = ["Read", "Grep", "Glob", "WebSearch"]
denied_tools = ["Bash"]
applies_to = ["untrusted-*", "third-party/*"]
```

### Harness-Specific Schema Extension

Permission policies can include harness-specific overrides:

```toml
[policy]
name = "sandbox-policy"
approval_mode = "auto"

[policy.claude]
# Claude Code specific: map to settings.json permissions
allow_mcp_tools = true

[policy.codex]
# Codex specific: map to sandbox configuration
sandbox_mode = "network-disabled"
```

### Materialization

Permission policies are config fragments. During managed target sync, each adapter cross-compiles permissions into the target's native config format:

1. **Canonical store**: copied to `.mars/permissions/` as-is
2. **Claude target**: adapter merges into `.claude/settings.json` permissions section
3. **Cursor target**: adapter generates `.cursor/rules/` entries for permission guidance
4. **Generic target**: copied as-is to target's `permissions/` directory

### Conflict Resolution

When multiple packages provide conflicting permission policies:
- **Most restrictive wins** for security-relevant fields (sandbox tier, denied tools)
- **Last-declared wins** for preference fields (approval mode)
- Conflicts are reported as diagnostics

### Consumer Override

```toml
# mars.local.toml
[permission_overrides]
"sandbox-policy".approval_mode = "yolo"
```

---

## B6: Tool Distribution

### Package Schema

Tool definitions live in `tools/`:

```toml
# tools/code-search.toml
[tool]
name = "code-search"
description = "Semantic code search"
type = "mcp"

[tool.mcp]
server = "code-search-server"
method = "search"

# Harness-specific extension: Claude Code native tool binding
[tool.claude]
native_tool = "code_search"
```

### Materialization

Tool definitions are cross-compiled into target-native config per managed target. The canonical store holds the universal definition. Each adapter translates to its target's format, using harness-specific extensions when present.

---

## B7: MCP Integration

### Package Schema

MCP server declarations in `mcp/`:

```toml
# mcp/code-search-server.toml
[server]
name = "code-search-server"
command = "npx"
args = ["-y", "@company/code-search-mcp"]
env_keys = ["OPENAI_API_KEY"]

# Harness-specific: Claude Code MCP configuration
[server.claude]
transport = "stdio"

# Harness-specific: Cursor MCP configuration  
[server.cursor]
transport = "sse"
port = 3100
```

### Materialization

Cross-compiled into target-native MCP configuration per managed target. The Claude adapter writes to `.claude/settings.json` MCP section; the Cursor adapter writes to Cursor's MCP config format. Mars does NOT store secrets — it documents required env keys and validates they're declared.

---

## B8: Hook Distribution

### Package Schema

Hooks in `hooks/` as directories:

```
hooks/pre-commit-check/
  hook.toml
  run.sh
```

### Security

Hook scripts require explicit consumer opt-in:

```toml
[settings]
enable_hooks = ["pre-commit-check"]
```

### Harness-Specific Hooks

Claude Code has native hook support. The Claude adapter can cross-compile hook definitions into `.claude/settings.json` hooks configuration:

```toml
# hooks/lint-on-save/hook.toml
[hook]
name = "lint-on-save"
event = "pre-save"
command = "ruff check --fix"

[hook.claude]
# Claude Code native hook mapping
event = "PreToolUse"
matcher = "Write"
```

---

## Runtime Adapter Architecture (Cross-Compiler Model)

### Design

Runtime adapters are **cross-compilers**: they take universal package definitions and emit harness-native equivalents. Each harness has unique capabilities that go beyond format translation:

- **Claude Code**: hooks in settings.json, native MCP transport, permissions via settings.json, `.claude/rules/` for rules
- **Cursor**: `.mdc` rule files with frontmatter file patterns, own MCP config format
- **Codex**: AGENTS.md conventions, sandbox model, own directory structure
- **Generic**: basic content copy, no capability materialization

The adapter's job is to:
1. **Map universal features** to harness-native equivalents
2. **Honor harness-specific extensions** (`[tool.claude]`, `[server.cursor]`, etc.) when present
3. **Emit diagnostics** when features have no equivalent in the target harness (e.g., hooks have no Cursor equivalent)

```rust
impl AdapterKind {
    /// Cross-compile all capabilities into this target's native config format.
    /// Returns diagnostics for unsupported capabilities or conflicts.
    pub fn materialize_capabilities(
        &self,
        capabilities: &CapabilitySet,
        target_dir: &Path,
    ) -> Result<Vec<Diagnostic>, MarsError> {
        match self {
            Self::Claude => claude::materialize(capabilities, target_dir),
            Self::Cursor => cursor::materialize(capabilities, target_dir),
            Self::Codex => codex::materialize(capabilities, target_dir),
            Self::Generic => generic::materialize(capabilities, target_dir),
        }
    }
    
    /// Emit diagnostic when a capability can't be cross-compiled.
    fn unsupported_diagnostic(&self, capability: &str) -> Diagnostic {
        Diagnostic::warning(
            "unsupported-capability",
            format!("{capability} has no equivalent in {} — skipping", self.name()),
        )
    }
}
```

**Why enum, not trait?** The adapter set is closed and small (3-4 built-in). A closed enum gives exhaustive match (compiler catches missing adapters), avoids heap allocation, and is consistent with D1's reasoning for ItemKind. If the adapter set truly needs to be open in the future, the enum can be replaced with a trait at that point.

### Content sync is generic; capability cross-compilation is adapter-specific

Content sync (copy items, resolve variants) follows the same algorithm for all adapters — the only input that varies is the harness ID for variant selection and the rule category routing. This is a shared function.

Capability cross-compilation is genuinely different per adapter — Claude's `settings.json`, Cursor's config format, Codex's conventions. This is where `AdapterKind` dispatches to adapter-specific logic.

### Harness-Specific Package Schema Extensions

The package schema supports harness-specific override sections for items that have harness-specific features. The convention is `[<item_type>.<harness_id>]`:

```toml
# Universal definition
[tool]
name = "code-search"
type = "mcp"

# Claude-specific override
[tool.claude]
native_tool = "code_search"

# Cursor-specific override  
[tool.cursor]
display_name = "Code Search (MCP)"
```

Adapters read the universal section plus their own harness-specific section. Unknown harness sections are ignored (forward compatible — adding a new harness section doesn't break existing adapters).

### Capability Set

```rust
/// A capability bundle ready for cross-compilation into target configs.
pub struct CapabilitySet {
    pub permissions: Vec<PermissionPolicy>,
    pub tools: Vec<ToolDefinition>,
    pub mcp_servers: Vec<McpServerConfig>,
    pub hooks: Vec<HookDefinition>,
    pub model_aliases: IndexMap<String, ModelAlias>,  // from [models] config
}
```

Each item in the capability set carries its universal definition plus any harness-specific extensions parsed from the source TOML. Adapters extract their own extensions during materialization.

Model aliases are included in the CapabilitySet so runtime adapters can reference them when materializing configs that need model information.

### Integration with Pipeline

Managed target sync runs as a phase after `apply_plan`:

```rust
pub fn execute(ctx: &MarsContext, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    // ... existing phases ...
    let applied = apply_plan(ctx, planned, request)?;     // writes to .mars/
    
    // New phase: sync all managed targets (content copy + capability cross-compilation)
    let synced = sync_managed_targets(ctx, applied, request)?;
    
    let report = finalize(ctx, synced, request)?;
    Ok(report)
}
```

---

## mars.toml Schema Evolution

### Package Metadata Extension

```toml
[package]
name = "my-agents"
version = "0.2.0"
description = "Agent profiles with capability policies"
provides = ["agents", "skills", "rules", "permissions", "mcp"]
```

### Consumer Configuration

```toml
[dependencies.base]
url = "https://github.com/org/base"
version = "~0.2"
include_kinds = ["agent", "skill", "rule", "permission"]
exclude = ["deprecated-agent"]

[models]
opus = { harness = "claude", model = "claude-opus-4-6", description = "Best reasoning" }
sonnet = { harness = "claude", model = "claude-sonnet-4-6", description = "Fast" }

[settings]
targets = [".claude", ".cursor"]
enable_hooks = ["pre-commit-check"]
```

### Lock Schema

Lock version stays at `1` for new item kinds (additive — the `kind` field is already a string). Bump to `version: 2` when variants are introduced, since the nested `variants` table is a structural schema change.

**Lock version gating**: The lock loader must check the version field before deserializing:

```rust
fn load_lock(path: &Path) -> Result<LockFile, MarsError> {
    let raw: toml::Value = ...;
    let version = raw.get("version").and_then(|v| v.as_integer()).unwrap_or(1);
    
    match version {
        1 => deserialize_v1(raw),
        2 => deserialize_v2(raw),  // includes variant support
        v => Err(MarsError::InvalidRequest {
            message: format!("lock version {v} is not supported — upgrade mars"),
        }),
    }
}
```

**Migration**: When mars writes a lock file, it uses v2 format if any items have variants, v1 otherwise. This means projects that don't use variants keep v1 locks and stay compatible with older mars.

```toml
version = 2

[items."agents/coder.md"]
source = "base"
kind = "agent"
source_checksum = "sha256:abc..."
installed_checksum = "sha256:abc..."
dest_path = "agents/coder.md"

[items."agents/coder.md".variants]
claude = "sha256:def..."

[items."rules/general.md"]
source = "base"
kind = "rule"
source_checksum = "sha256:..."
installed_checksum = "sha256:..."
dest_path = "rules/general.md"
```

---

## What's Deliberately Out of Scope

- **Runtime process management**: Mars doesn't start, stop, or monitor MCP servers. It generates config.
- **Secret management**: Mars doesn't store API keys. It documents which env vars are needed.
- **Dynamic plugin loading**: All item kinds and adapters are compiled in.
- **Registry/distribution model**: Package distribution is a separate design.
- **Workspace support**: Multi-project monorepo support is orthogonal.
- **Model runtime routing**: Mars provides the alias table and cache; meridian does the routing at spawn time.
- **Variant-level filtering**: Initial implementation installs all variants; filtering can be added later.
- **Per-target kind filtering**: Initial implementation syncs all content kinds to all targets; per-target `include_kinds`/`exclude_kinds` can be added later.
