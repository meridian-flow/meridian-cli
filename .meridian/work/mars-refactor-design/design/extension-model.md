# Extension Model (Phase B)

Design the extension points for capability packages, soul files, harness-specific variants, managed target sync, model catalog integration, and generalized item kinds.

See [overview](overview.md) for context. This design depends on [pipeline decomposition](pipeline-decomposition.md) Phase A being complete — specifically A1 (typed phases) for the new pipeline insertion point, and A2 (first-class LocalPackage) for local packages to discover new item kinds automatically.

## B1: Generalized Item Kinds + Soul Files

### Problem

`ItemKind` is currently a two-variant enum:

```rust
pub enum ItemKind {
    Agent,
    Skill,
}
```

Discovery hardcodes `agents/*.md` and `skills/*/SKILL.md` scan patterns. Adding a new kind (permissions, tools, MCP configs, soul files) requires modifying discovery, target building, diff, plan, apply, lock, and link — the same "8 file change" problem the prior extensibility analysis identified for new source types.

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
    Soul,        // NEW: per-model system prompt addons
    Permission,
    Tool,
    McpServer,
    Hook,
}
```

### Soul Files

Soul files are per-model system prompt addons that live in `.agents/soul/<alias>.md`. They are generic instructions injected whenever a specific model alias runs — not tied to any particular agent or skill.

**Package schema**: Soul files are markdown files in `soul/`:

```
soul/
  opus.md          # injected when model alias "opus" is used
  sonnet.md        # injected when model alias "sonnet" is used
  codex.md         # injected when "codex" harness models run
```

**Discovery convention**: `soul/*.md` — flat files, same as agents.

**Materialization**: Content copy (same as agents/skills). Soul files are copied to `.agents/soul/` and symlinked/synced to managed targets. The consuming harness (meridian) reads them at spawn time by matching the resolved model alias.

**Naming convention**: The filename (without `.md`) matches the model alias from `[models]` in mars.toml. This is a convention, not enforced by mars — mars just syncs the files. The consuming system matches `soul/<alias>.md` to the active model alias at runtime.

**Why a new ItemKind, not just a directory convention?** Soul files need to participate in the standard pipeline: they should be lockable, filterable (`include_kinds = ["soul"]`), and visible in `mars list`. Making them a proper ItemKind gives them all of this for free via the discovery convention registry.

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

pub enum DiscoveryPattern {
    /// Each *.<ext> file is one item (e.g. agents/*.md, permissions/*.toml).
    FlatFiles { extension: &'static str },
    /// Each subdirectory containing a marker file is one item (e.g. skills/*/SKILL.md).
    MarkerDirs { marker: &'static str },
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
            kind: ItemKind::Soul,
            dir_name: "soul",
            pattern: DiscoveryPattern::FlatFiles { extension: "md" },
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

Content items (agents, skills, soul files) are materialized by copying files to the managed root. Capability items are materialized differently — they generate config fragments that merge into runtime-specific config files.

```rust
/// How an item kind is materialized into the managed root.
pub enum MaterializationStrategy {
    /// Copy source content directly (agents, skills, soul files, hooks).
    ContentCopy,
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
            Self::Agent | Self::Skill | Self::Soul | Self::Hook => MaterializationStrategy::ContentCopy,
            Self::Permission | Self::Tool | Self::McpServer => MaterializationStrategy::ConfigFragment {
                format: FragmentFormat::Toml,
            },
        }
    }
}
```

### Destination Path Convention

Each kind has a deterministic destination path:

```rust
impl ItemKind {
    pub fn dest_dir(&self) -> &'static str {
        match self {
            Self::Agent => "agents",
            Self::Skill => "skills",
            Self::Soul => "soul",
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
[items."soul/opus.md"]
source = "base"
kind = "soul"
source_checksum = "sha256:..."
installed_checksum = "sha256:..."
dest_path = "soul/opus.md"
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

Packages can ship harness-specific variants alongside the default version. Variant resolution happens at sync time based on the active link targets.

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
soul/
  opus.md                     # default (soul files can have variants too)
  opus.claude.md              # Claude-specific soul addon
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

This requires passing the set of known harness IDs into `discover_source()`:

```rust
pub fn discover_source(
    tree_path: &Path,
    fallback_name: Option<&str>,
    harness_ids: &HashSet<String>,  // NEW: from settings.targets
) -> Result<(Vec<DiscoveredItem>, Vec<Diagnostic>), MarsError>
```

**Resolution in target building**: During `build_target()`, the active managed targets determine which variants are relevant. For each item:

1. If a variant exists for a managed target's harness → use the variant for that target
2. If no variant exists → use the default version
3. Variants for inactive harnesses are ignored (not installed)

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

**Managed root gets the default version**. `.agents/` always contains the default (non-variant) content. Variants are resolved and applied only to managed targets during target sync (B3).

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

## B3: Managed Target Sync (Link Reframing)

### Problem

`mars link` currently means "create symlinks from `.claude/agents/` → `.agents/agents/`". This is limiting because:

1. Symlinks break tools that don't follow them
2. No mechanism to push harness-specific variant content to targets
3. No mechanism to merge capability configs (permissions, MCP, tools) into target-specific config files
4. Can't handle soul files or other new item kinds that targets need

### Reframing

**'Link' no longer means symlink.** It means "mars owns and manages this target directory." `.agents/` is the centralized source of truth. Most harnesses read from `.agents/` directly. Managed targets (like `.claude/`) exist for tools that insist on their own directory. Mars keeps managed targets in sync with `.agents/` plus any harness-specific content.

### Design

**ManagedTarget** replaces the current link concept:

```rust
/// A directory that mars manages — keeps in sync with .agents/ plus harness-specific content.
pub struct ManagedTarget {
    /// Target directory name (e.g. ".claude").
    pub name: String,
    /// Harness identifier for variant resolution (derived from name, e.g. "claude").
    pub harness_id: String,
    /// How content items are synced to this target.
    pub content_strategy: ContentStrategy,
    /// Which runtime adapter handles capability materialization.
    pub adapter_kind: AdapterKind,
}

/// Closed enum for adapter selection — matches the "single binary, no dynamic loading" constraint.
/// Adapter logic is method dispatch on this enum, not trait objects.
pub enum AdapterKind {
    Claude,
    Cursor,
    Generic,  // fallback for unknown targets
}

impl AdapterKind {
    /// Select adapter from target name.
    pub fn from_target(name: &str) -> Self {
        match name.trim_start_matches('.') {
            "claude" => Self::Claude,
            "cursor" => Self::Cursor,
            _ => Self::Generic,
        }
    }
}

/// How content (agents, skills, soul files) reaches a managed target.
pub enum ContentStrategy {
    /// Symlink subdirectories (current behavior — fast, but some tools don't follow).
    Symlink,
    /// Copy content, resolving harness-specific variants.
    /// Used when the target needs variant content or the tool doesn't follow symlinks.
    Copy,
    /// Mirror: copy + keep in sync on every `mars sync`.
    /// For targets that need variant-resolved content AND ongoing sync.
    Mirror,
}
```

**Default behavior**: `ContentStrategy::Mirror` for all managed targets. This is the simplest correct behavior — every `mars sync` ensures managed targets match `.agents/` with variants resolved. Symlink mode is available as an optimization for targets that don't need variants and where the tool follows symlinks.

**Sync flow for managed targets**:

```
mars sync
  → Phase A pipeline (load → resolve → discover → target → diff → plan → apply → lock)
  → For each managed target:
      1. Content sync: copy items from .agents/ to target, substituting variants where available
      2. Capability materialization: merge config fragments into target-specific configs
      3. Reconcile: detect conflicts, handle force/skip semantics
```

**Configuration**:

```toml
[settings]
managed_root = ".agents"

# Managed targets — mars keeps these in sync with .agents/
[[settings.targets]]
name = ".claude"
# content_strategy = "mirror"  # default, can be omitted
# harness_id = "claude"        # derived from name by stripping leading dot

[[settings.targets]]
name = ".cursor"
```

Backwards compatibility: the existing `links = [".claude"]` syntax is supported and equivalent to `[[settings.targets]] name = ".claude"` with default settings.

**Content sync algorithm** for a managed target:

```rust
fn sync_target_content(
    managed_root: &Path,
    target: &ManagedTarget,
    items: &[TargetItem],
    strategy: &ContentStrategy,
) -> Result<Vec<ReconcileOutcome>, MarsError> {
    let mut outcomes = Vec::new();
    
    for item in items {
        let source = match item.variants.get(&target.harness_id) {
            // Harness-specific variant exists — use it instead of default
            Some(variant) => &variant.source_path,
            // No variant — use the default from managed root
            None => &item.dest_path.resolve(managed_root),
        };
        
        let dest = item.dest_path.resolve(&target.path);
        let outcome = reconcile_one(&dest, desired_state_from(source, &item.materialization), false)?;
        outcomes.push(outcome);
    }
    
    outcomes
}
```

**Orphan cleanup**: When items are removed from `.agents/`, the corresponding files in managed targets are also removed. The reconcile layer handles this by comparing the target directory against the expected item set.

**First-run adoption**: The current `merge_and_link` behavior for adopting existing target directories is preserved. On first `mars sync` when a managed target has existing content (not yet managed by mars), mars scans for conflicts, offers to merge unique files into `.agents/`, and then takes ownership of the target directory.

### Relationship to A4 (Shared Reconciliation)

Managed target sync uses the same reconciliation primitives from A4:

- **Layer 1 (atomic fs ops)**: `atomic_write_file`, `atomic_install_dir`, `safe_remove` — used for content copy
- **Layer 2 (item-level reconciliation)**: `reconcile_one`, `scan_destination` — used for per-item sync to targets

The current link-specific `merge_and_link` algorithm becomes the "first-run adoption" path, not the steady-state sync path. Steady-state managed target sync is item-level reconciliation, same as sync apply.

---

## B4: Model Catalog Integration

### Problem

Model alias → harness + model resolution is needed for agent spawning. This is being implemented independently (issue #7) but must integrate cleanly with the mars pipeline and config schema.

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
- `read_cache()` / `write_cache()` for `.agents/models-cache.json`
- `resolve_alias()` for alias lookup

### Design: Integration Points

**No changes to Phase A pipeline.** The model catalog is orthogonal to the sync pipeline — it's not an item kind, not discovered from sources, and not diffed/planned/applied. It's a separate artifact that mars manages.

**Cache location**: `.agents/models-cache.json` — already implemented. This is a mars-managed artifact in the managed root, not a synced item.

**Refresh lifecycle**: `mars models refresh` fetches live data from models.dev and writes the cache. Meridian triggers this when the cache TTL is stale. Mars doesn't auto-refresh during `mars sync` — the cache is a separate concern.

**Config-level integration**: The `[models]` section in mars.toml defines project-specific model aliases. These are read during `load_config()` and available in `LoadedConfig`. Soul files (B1) reference model aliases by filename convention — `soul/opus.md` matches the `opus` alias.

**Package-provided model aliases**: Packages can ship `[models]` entries in their manifest. During resolution, package-provided aliases are merged into the consumer's model config with consumer aliases taking precedence (same shadow semantics as local packages shadowing dependencies).

```toml
# In a package's mars.toml
[models]
opus = { harness = "claude", model = "claude-opus-4-6", description = "Best for complex reasoning" }
sonnet = { harness = "claude", model = "claude-sonnet-4-6", description = "Fast and capable" }
```

**What mars does NOT do**: Mars doesn't route models at runtime. It provides the alias table and cache. Meridian reads these at spawn time.

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

### Materialization

Permission policies are config fragments. During the `materialize_capabilities` phase (B3's managed target sync), permission TOML files are:

1. **Copied to managed root** as-is (`.agents/permissions/sandbox-policy.toml`)
2. **Merged into runtime configs** per managed target — each runtime adapter translates the policy into runtime-specific format

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
```

### Materialization

Tool definitions are materialized into runtime-specific config per managed target. The managed root stores the canonical definition. Runtime adapters translate to each target's format.

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
```

### Materialization

Merged into runtime-specific MCP configuration per managed target. Mars does NOT store secrets — it documents required env keys and validates they're declared.

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

---

## Runtime Adapter Architecture

### Design

Runtime adapters handle per-target materialization. With the link reframing, adapters now have two responsibilities:

1. **Content sync**: Copy/sync items from `.agents/` to the managed target, resolving variants
2. **Capability materialization**: Merge config fragments into target-specific config files

```rust
impl AdapterKind {
    /// Sync content items to the target directory.
    /// Resolves harness-specific variants where available.
    pub fn sync_content(
        &self,
        managed_root: &Path,
        target: &ManagedTarget,
        items: &[TargetItem],
    ) -> Result<Vec<ReconcileOutcome>, MarsError> {
        // Content sync is generic — same algorithm for all adapters.
        // Variant resolution uses target.harness_id to pick the right variant.
        sync_target_content(managed_root, target, items, &target.content_strategy)
    }
    
    /// Materialize all capabilities into this target's config.
    /// Returns diagnostics for unsupported capabilities or conflicts.
    pub fn materialize_capabilities(
        &self,
        capabilities: &CapabilitySet,
        target_dir: &Path,
    ) -> Result<Vec<Diagnostic>, MarsError> {
        match self {
            Self::Claude => materialize_claude(capabilities, target_dir),
            Self::Cursor => materialize_cursor(capabilities, target_dir),
            Self::Generic => materialize_generic(capabilities, target_dir),
        }
    }
}
```

**Why enum, not trait?** The implementability reviewer flagged tension between `Box<dyn RuntimeAdapter>` and the "single binary, no dynamic loading" constraint. The adapter set is closed and small (2-3 built-in). A closed enum gives exhaustive match (compiler catches missing adapters) and avoids heap allocation. If the adapter set truly needs to be open in the future, the enum can be replaced with a trait at that point — but the current constraints don't justify the indirection.

### Content sync is generic; capability materialization is adapter-specific

Content sync (copy items, resolve variants) follows the same algorithm for all adapters — the only input that varies is the harness ID for variant resolution. This is a shared function, not per-adapter logic.

Capability materialization is genuinely different per adapter — Claude's `settings.json`, Cursor's config format, etc. This is where `AdapterKind` dispatches to adapter-specific logic.

### Capability Set

```rust
/// A capability bundle ready for materialization into a target config.
pub struct CapabilitySet {
    pub permissions: Vec<PermissionPolicy>,
    pub tools: Vec<ToolDefinition>,
    pub mcp_servers: Vec<McpServerConfig>,
    pub hooks: Vec<HookDefinition>,
    pub model_aliases: IndexMap<String, ModelAlias>,  // from [models] config
}
```

Model aliases are included in the CapabilitySet so runtime adapters can reference them when materializing configs that need model information.

### Integration with Pipeline

Managed target sync runs as a phase after `apply_plan`:

```rust
pub fn execute(ctx: &MarsContext, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    // ... existing phases ...
    let applied = apply_plan(ctx, planned, request)?;
    
    // New phase: sync managed targets (content + capabilities)
    let synced = sync_managed_targets(ctx, applied, request)?;
    
    let report = finalize(ctx, synced, request)?;
    Ok(report)
}
```

### Failure Semantics and Crash Safety

Managed target sync happens **after** content apply and **before** lock write:

1. **Content is applied first** — `.agents/` is in a consistent state
2. **Managed targets are synced** — content + capabilities written to targets
3. **Lock is written** — records what was installed

If target sync fails:
- `.agents/` is already correct
- **Lock IS still written** — the lock records what's in `.agents/`, which is the source of truth. Target sync state is tracked separately.
- Managed targets may be partially updated — each adapter handles its own atomicity
- Re-running `mars sync` converges: content diffs as unchanged (lock matches), targets get re-synced

**Error handling**: Target sync errors are **non-fatal by default**. Content sync to `.agents/` is the primary value; target sync is additive. The lock always reflects the `.agents/` state regardless of target sync outcome. Target sync status is reported in `SyncReport.target_outcomes` so the CLI can display which targets succeeded/failed. Opt-in `--strict` makes target sync failures fatal (lock not written, full re-run on next sync).

---

## mars.toml Schema Evolution

### Package Metadata Extension

```toml
[package]
name = "my-agents"
version = "0.2.0"
description = "Agent profiles with capability policies"
provides = ["agents", "skills", "soul", "permissions", "mcp"]
```

### Consumer Configuration

```toml
[dependencies.base]
url = "https://github.com/org/base"
version = "~0.2"
include_kinds = ["agent", "skill", "soul", "permission"]
exclude = ["deprecated-agent"]

[models]
opus = { harness = "claude", model = "claude-opus-4-6", description = "Best reasoning" }
sonnet = { harness = "claude", model = "claude-sonnet-4-6", description = "Fast" }

[settings]
managed_root = ".agents"
enable_hooks = ["pre-commit-check"]

[[settings.targets]]
name = ".claude"

[[settings.targets]]
name = ".cursor"
# content_strategy = "symlink"  # override for cursor
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

fn deserialize_v1(raw: toml::Value) -> Result<LockFile, MarsError> {
    // Current deserialization — no variants field
    toml::from_str(...)
}

fn deserialize_v2(raw: toml::Value) -> Result<LockFile, MarsError> {
    // Extended deserialization — includes optional variants per item
    toml::from_str(...)
}
```

**Migration**: When mars writes a lock file, it uses v2 format if any items have variants, v1 otherwise. This means projects that don't use variants keep v1 locks and stay compatible with older mars. The first `mars sync` after adding variant content upgrades the lock to v2.

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

[items."soul/opus.md"]
source = "base"
kind = "soul"
source_checksum = "sha256:..."
installed_checksum = "sha256:..."
dest_path = "soul/opus.md"
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
