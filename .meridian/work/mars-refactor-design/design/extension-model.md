# Extension Model (Phase B)

Design the extension points for capability packages: permissions, tools, MCP server registrations, hooks, and generalized item kinds.

See [overview](overview.md) for context. This design depends on [pipeline decomposition](pipeline-decomposition.md) Phase A being complete — specifically A1 (typed phases) for the new pipeline insertion point, and A2 (first-class LocalPackage) for local packages to discover new item kinds automatically.

## B1: Generalized Item Kinds

### Problem

`ItemKind` is currently a two-variant enum:

```rust
pub enum ItemKind {
    Agent,
    Skill,
}
```

Discovery hardcodes `agents/*.md` and `skills/*/SKILL.md` scan patterns. Adding a new kind (permissions, tools, MCP configs) requires modifying discovery, target building, diff, plan, apply, lock, and link — the same "8 file change" problem the prior extensibility analysis identified for new source types.

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
    Permission,
    Tool,
    McpServer,
    Hook,
}
```

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

Content items (agents, skills) are materialized by copying files to the managed root. Capability items are materialized differently — they generate config fragments that merge into runtime-specific config files.

```rust
/// How an item kind is materialized into the managed root.
pub enum MaterializationStrategy {
    /// Copy source content directly (agents, skills, hooks).
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
            Self::Agent | Self::Skill | Self::Hook => MaterializationStrategy::ContentCopy,
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
[items."permissions/sandbox-policy.toml"]
source = "base"
kind = "permission"
source_checksum = "sha256:..."
installed_checksum = "sha256:..."
dest_path = "permissions/sandbox-policy.toml"
```

Old mars versions encountering unknown kinds in the lock will fail to deserialize the `ItemKind` enum. This is acceptable — upgrading mars is expected when packages use new features. Add a clear error message:

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

This allows consumers to install only specific kinds from a source:

```toml
[dependencies.base]
url = "https://github.com/org/base"
include_kinds = ["agent", "skill"]  # skip permissions, tools, MCP
```

**Filter precedence**: Kind filters apply first, then item-level filters apply within the surviving kinds. Example: `include_kinds = ["agent", "permission"]` + `only_agents = true` → error (contradictory: `only_agents` implies "agents only" but `include_kinds` includes permissions). Conflicting filters fail at config validation time with a clear error rather than silently resolving with surprising behavior.

---

## B2: Permission Sync

### Problem

Packages can install agent and skill content, but can't declare what runtime permissions those assets expect. Users manually configure approval modes, sandbox tiers, and tool allowlists.

### Package Schema

Permission policies are declared as TOML files in `permissions/`:

```toml
# permissions/sandbox-policy.toml

[policy]
name = "sandbox-policy"
description = "Restrictive sandbox for untrusted agents"

# Approval mode: "default", "confirm", "auto", "yolo"
approval_mode = "auto"

# Sandbox tier for spawned processes
sandbox_tier = "restricted"

# Tool allowlist (if empty, all tools allowed)
allowed_tools = ["Read", "Grep", "Glob", "WebSearch"]

# Tool denylist (takes precedence over allowlist)
denied_tools = ["Bash"]

# Which agents this policy applies to (glob patterns)
applies_to = ["untrusted-*", "third-party/*"]
```

### Materialization

Permission policies are config fragments. During the new `materialize_capabilities` phase (inserted after `apply_plan` in the pipeline), permission TOML files are:

1. **Copied to managed root** as-is (`.agents/permissions/sandbox-policy.toml`) — this is the authoritative source
2. **Merged into runtime configs** per link target — each runtime adapter translates the policy into runtime-specific format

For Claude Code (`.claude/`):

```rust
fn materialize_permissions_claude(
    policies: &[PermissionPolicy],
    claude_dir: &Path,
) -> Result<(), MarsError> {
    // Read existing settings.json
    let settings_path = claude_dir.join("settings.json");
    let mut settings = load_or_default_json(&settings_path)?;
    
    // Merge permission policies into settings
    for policy in policies {
        if let Some(approval) = &policy.approval_mode {
            // Add to managed permissions section
            settings["managed_permissions"][&policy.name]["approval"] = approval.into();
        }
        // ... tools, sandbox, etc.
    }
    
    // Atomic write
    atomic_write_json(&settings_path, &settings)?;
    Ok(())
}
```

### Conflict Resolution

When multiple packages provide conflicting permission policies:
- **Most restrictive wins** for security-relevant fields (sandbox tier, denied tools)
- **Last-declared wins** for preference fields (approval mode)
- Conflicts are reported as diagnostics, not errors — the consumer can override via `mars.local.toml`

### Consumer Override

```toml
# mars.local.toml
[permission_overrides]
"sandbox-policy".approval_mode = "yolo"  # I trust this agent locally
```

---

## B3: Tool Distribution

### Problem

Skills and agents are only part of the execution contract. Tool definitions are configured separately, making packages incomplete and harder to share.

### Package Schema

Tool definitions live in `tools/`:

```toml
# tools/code-search.toml

[tool]
name = "code-search"
description = "Semantic code search across the repository"

# Tool type determines materialization
type = "mcp"  # or "builtin", "script"

# MCP-backed tool
[tool.mcp]
server = "code-search-server"  # references an MCP server from mcp/ dir
method = "search"

# Alternative: script-backed tool
# [tool.script]
# command = "scripts/search.sh"
# args = ["--format", "json"]
```

### Materialization

Tool definitions are materialized into runtime-specific config:

For Claude Code: tools map to MCP tool registrations or settings entries.
For other runtimes: the runtime adapter translates to that runtime's tool format.

The managed root stores the canonical tool definition (`tools/code-search.toml`). Link targets get runtime-specific materializations.

### Relationship to MCP

Tools can reference MCP servers declared in the same package. The tool definition is the user-facing spec; the MCP server is the implementation. Mars validates that referenced MCP servers exist in the resolved package set.

---

## B4: MCP Integration

### Problem

MCP server registrations are manually configured per runtime. Packages that provide MCP-backed capabilities can't declare the server requirements.

### Package Schema

MCP server declarations live in `mcp/`:

```toml
# mcp/code-search-server.toml

[server]
name = "code-search-server"
description = "Provides semantic code search capabilities"

# How to start the server
command = "npx"
args = ["-y", "@company/code-search-mcp"]

# Environment variables (names only — values come from consumer)
env_keys = ["OPENAI_API_KEY"]

# Optional: required resources/capabilities
capabilities = ["search", "index"]
```

### Materialization

MCP server configs are merged into runtime-specific MCP configuration:

For Claude Code (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "code-search-server": {
      "command": "npx",
      "args": ["-y", "@company/code-search-mcp"],
      "env": {}
    }
  }
}
```

The runtime adapter handles the translation. Mars stores the canonical config and each runtime gets its format.

### Environment Variables

MCP servers often need API keys or configuration values. Mars does NOT store secrets. Instead:

1. Package declares required env keys (`env_keys = ["OPENAI_API_KEY"]`)
2. Mars validates that required keys are documented
3. Consumer provides values through their environment or runtime config
4. Mars emits a diagnostic if a required key is undocumented in the consumer's setup

### Server Lifecycle

Mars doesn't manage MCP server processes — it only manages the configuration that tells runtimes how to start them. Server lifecycle is the runtime's responsibility.

---

## B5: Hook Distribution

### Problem

Lifecycle hooks and event-based automation are configured manually. Packages can't ship hooks as part of the package.

### Package Schema

Hooks live in `hooks/` as directories:

```
hooks/
  pre-commit-check/
    hook.toml       # hook metadata
    run.sh          # the script
```

```toml
# hooks/pre-commit-check/hook.toml

[hook]
name = "pre-commit-check"
description = "Validate agent configs before commit"

# Lifecycle event this hook attaches to
event = "pre-commit"

# Entry point (relative to hook directory)
command = "run.sh"

# Priority (lower = earlier, default = 100)
priority = 50
```

### Materialization

Hooks are content items (copied to managed root) + config fragments (registered in runtime hook config).

For Claude Code (`.claude/settings.json` hooks section):

```json
{
  "hooks": {
    "pre-commit": [
      {
        "command": ".agents/hooks/pre-commit-check/run.sh",
        "source": "base"
      }
    ]
  }
}
```

### Security

Hook scripts are executable code. Mars should:
1. **Not auto-enable hooks** — require explicit consumer opt-in
2. **Track hook checksums** in the lock file
3. **Warn on hook changes** during sync (like tool allowlist changes)

```toml
# mars.toml — consumer explicitly enables hooks
[settings]
enable_hooks = ["pre-commit-check"]  # only run hooks I've approved
```

---

## Runtime Adapter Architecture

### Problem

Each link target (`.claude/`, `.cursor/`, etc.) needs different materialization for capability items. Currently, link just creates symlinks for agents/ and skills/ subdirectories.

### Design

Runtime adapters handle per-runtime materialization:

```rust
/// A capability bundle ready for materialization into a runtime config.
pub struct CapabilitySet {
    pub permissions: Vec<PermissionPolicy>,
    pub tools: Vec<ToolDefinition>,
    pub mcp_servers: Vec<McpServerConfig>,
    pub hooks: Vec<HookDefinition>,
}

/// A runtime adapter knows how to materialize capabilities for a specific tool.
///
/// Single method avoids ISP violation — adapters that don't support a capability
/// kind simply skip those items. The CapabilitySet is the aggregate of all
/// capability items for this runtime, and the adapter handles them in one pass.
/// This also solves the coordination problem: when permissions and MCP servers
/// both write to settings.json, the adapter handles the merge atomically.
pub trait RuntimeAdapter {
    /// Which tool directory this adapter handles (e.g. ".claude").
    fn target_name(&self) -> &str;
    
    /// Materialize all capabilities into this runtime's config directory.
    /// Returns diagnostics for unsupported capabilities or conflicts.
    fn materialize(
        &self,
        capabilities: &CapabilitySet,
        target_dir: &Path,
    ) -> Result<Vec<Diagnostic>, MarsError>;
}
```

The single `materialize` method receives the full `CapabilitySet`, which solves two problems flagged in review:
1. **ISP**: Adapters don't need to implement separate methods for each capability type — they iterate over what they support and emit diagnostics for what they don't
2. **Config file coordination**: When permissions, MCP, and tools all write to `settings.json`, the adapter reads the file once, merges all capability types, and writes atomically

**Built-in adapters**: `ClaudeAdapter`, `CursorAdapter`, `GenericAdapter` (fallback — just symlinks content, emits "unsupported capability" diagnostics for everything else).

**Registration**: Adapters are selected by link target name in `mars.toml`:

```toml
[settings]
links = [".claude", ".cursor"]
# Mars auto-detects the adapter from the link target name
```

### Why Trait, Not Enum?

Unlike `ItemKind` and `SourceSpec` (which are closed enums), runtime adapters benefit from a trait because:
1. The set of supported runtimes grows independently of Mars's release cycle
2. Each adapter is self-contained — no shared exhaustive match needed
3. Future: adapters could be loaded from package-provided Wasm modules (far future, not designed here)

For now, the trait is implemented by 2-3 built-in structs. The trait boundary exists to keep adapter logic self-contained, not for dynamic dispatch.

### Integration with Pipeline

Capability materialization runs as a new phase after `apply_plan`:

```rust
pub fn execute(ctx: &MarsContext, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    // ... existing phases ...
    let applied = apply_plan(ctx, &planned, request)?;
    
    // New phase: materialize capabilities into runtime configs
    let materialized = materialize_capabilities(ctx, &applied)?;
    
    let report = finalize(ctx, &materialized, request)?;
    Ok(report)
}
```

Content items (agents, skills) are still handled by `apply_plan` — they're copied/symlinked to the managed root. Capability items (permissions, tools, MCP, hooks) are parsed from the managed root and materialized into runtime configs by the appropriate adapter.

### Failure Semantics and Crash Safety

Capability materialization happens **after** content apply and **before** lock write. This ordering is deliberate:

1. **Content is applied first** — agents/skills are in the managed root
2. **Capabilities are materialized** — runtime configs are updated
3. **Lock is written** — records what was installed

If capability materialization fails:
- **Content is already applied** — this is fine, the managed root is in a consistent state
- **Lock is NOT written** — the next `mars sync` will re-run the full pipeline, detecting that content is up-to-date (skip) and re-attempting capability materialization
- **Runtime configs may be partially updated** — each adapter must handle its own atomicity (read config → merge → atomic write). If an adapter crashes mid-write, the next sync repairs it.

This matches the crash-only design principle: there is no rollback. Re-running `mars sync` after a crash converges to the correct state because:
- Content that's already installed will diff as `Unchanged` (skip)
- Capabilities will be re-materialized from the managed root content
- The lock will finally be written when everything succeeds

**Error handling**: Capability materialization errors are **non-fatal by default** — they produce diagnostics and `mars sync` reports them, but does not fail the sync. Content sync is the primary value; capability sync is additive. Users can opt into strict mode with `--strict-capabilities` if they want materialization failures to be fatal.

### Link Integration

`mars link` gains a second responsibility: after creating content symlinks, invoke runtime adapters for the link target. This uses the shared reconciliation layer (A4) for atomic operations.

```
mars link .claude
  1. Symlink .agents/agents/ → .claude/agents/ (existing)
  2. Symlink .agents/skills/ → .claude/skills/ (existing)
  3. Materialize permissions → .claude/settings.json (new)
  4. Materialize MCP servers → .claude/settings.json (new)
  5. Materialize tools → .claude/settings.json (new)
  6. Register hooks → .claude/settings.json (new)
```

---

## mars.toml Schema Evolution

### Package Metadata Extension

```toml
[package]
name = "my-agents"
version = "0.2.0"
description = "Agent profiles with capability policies"

# Declare which item kinds this package provides
# (optional — mars discovers automatically, but explicit declaration
# helps consumers understand what they're installing)
provides = ["agents", "skills", "permissions", "mcp"]
```

### Consumer Configuration

```toml
[dependencies.base]
url = "https://github.com/org/base"
version = "~0.2"
# Filter by kind
include_kinds = ["agent", "skill", "permission"]
# Existing filters still work for agent/skill items
exclude = ["deprecated-agent"]

[settings]
managed_root = ".agents"
links = [".claude"]
enable_hooks = ["pre-commit-check"]

# Global permission override
[settings.permissions]
default_approval_mode = "auto"
```

### Lock Schema

The lock file version stays at `1` — new item kinds are additive and use the existing `kind` field. Old mars versions fail with a clear error on unknown kinds.

If structural changes to the lock are needed (e.g., tracking capability materialization state), bump to `version: 2` with migration:

```rust
fn migrate_lock(lock: &LockFile) -> LockFile {
    match lock.version {
        1 => {
            // v1 → v2: add materialization_hash field (default to empty)
            LockFile { version: 2, ..lock.clone() }
        }
        2 => lock.clone(),
        _ => panic!("unsupported lock version {}", lock.version),
    }
}
```

---

## What's Deliberately Out of Scope

- **Runtime process management**: Mars doesn't start, stop, or monitor MCP servers. It generates config.
- **Secret management**: Mars doesn't store API keys. It documents which env vars are needed.
- **Dynamic plugin loading**: All item kinds and adapters are compiled in. Wasm plugins are a far-future possibility, not designed here.
- **Registry/distribution model**: Package distribution (registries, publisher trust) is a separate design not covered here.
- **Workspace support**: Multi-project monorepo support is orthogonal to the extension model.
