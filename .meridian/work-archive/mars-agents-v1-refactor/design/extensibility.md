# Extensibility Analysis

How the v1 refactor design accommodates future extension points. For each: where the design is closed (enum match, if-else) vs open (traits, callbacks), what's cheap to add now, and where to deliberately resist abstraction.

See [overview](overview.md) for the refactor scope, [features.md](../../agent-package-management/design/features.md) for v2 plans, and [sync-pipeline](sync-pipeline.md) for the unified pipeline.

## Summary Table

| Extension Point | Can Add Without Modifying Existing Code? | Touch Points | Recommended Pattern |
|---|---|---|---|
| New source type (registry) | No | 6–8 files | Closed enum + new adapter file — compiler enforces completeness |
| New CLI command | No | 3 files (enum, handler, dispatch) | Standard clap derive — this is fine |
| New ConfigMutation variant | No | 3 match arms | Closed enum — keep it; exhaustive match is the feature |
| New filter mode | Mostly yes | 1 if-else branch in `build()` | Optional fields on `SourceEntry` — no enum needed |
| Plugin hooks (pre/post sync) | Yes (after one-time hook infra) | 0 after setup | Config-driven hooks between pipeline steps |
| Patches | Mostly yes | 1 new pipeline step + storage | New step after apply, new lock field |
| Private registry auth | Yes | New adapter internal | Credential callbacks, no pipeline change |

## Extension Point 1: New Source Types

### Current Design

`SourceEntry` is a tagged serde enum:

```rust
#[serde(tag = "type")]
pub enum SourceEntry {
    Git { url, version, agents, skills, exclude, rename },
    Path { path, agents, skills, exclude, rename },
}
```

`SourceId` is also an enum (`Git { url }` / `Path { canonical }`). `SourceFormat` in the parser is a 5-variant enum. The resolver routes to `source/git.rs` or `source/path.rs` based on spec type.

### Adding `SourceEntry::Registry`

Touch points — every exhaustive match on `SourceEntry`, `SourceId`, `SourceSpec`, `SourceFormat`:

| File | What Changes |
|---|---|
| `config/mod.rs` | Add `Registry { name, version, ... }` variant to `SourceEntry` |
| `source/parse.rs` | Add `SourceFormat::Registry`, classify `mars.dev/package-name` inputs |
| `source/registry.rs` | **New file** — fetch from registry API, version listing, download |
| `resolve/mod.rs` | Handle registry resolution (version listing differs from git tag listing) |
| `types.rs` | Add `SourceId::Registry { name: PackageName }` |
| `lock/mod.rs` | New fields on `LockedSource` for registry metadata (or reuse URL) |
| `config/merge.rs` | Handle registry entries in effective config merge |
| `cli/add.rs` | Parse `mars add package-name` (no URL, no path — just a name) |

**That's 8 files.** There is no way around this — a new source type threads through config, parsing, resolution, fetching, and locking.

### Should We Make This Zero-Change?

**No. And here's why.**

The trait-based approach (a `Source` trait with `resolve()`, `fetch()`, `list_versions()`) only helps with the fetching layer. It doesn't eliminate changes to config parsing, CLI input classification, `SourceId` identity, or lock structure. Those are inherently per-source-type decisions.

The current `SourceProvider` trait (issue #17, being replaced in Phase 8) is exactly this — a fat trait that tried to abstract over source types. The reviews flagged it as a violation of ISP because git and path sources have fundamentally different capabilities (path sources don't have versions, git sources don't need path resolution). A registry source would add yet another capability mismatch (no git clone, has API auth, has package names instead of URLs).

**What Rust gives us that's better than traits here: exhaustive match.** When `SourceEntry::Registry` is added, the compiler flags every match arm that needs updating. No runtime "forgot to handle this case" bugs. This is exactly the "type system enforcement over runtime checks" philosophy from the refactor (overview.md §Type System Strategy).

### Minimum Change to Make Registry Cheaper

Two things we can do now at near-zero cost:

1. **Factor the shared fields out of `SourceEntry` variants.** Currently `agents`, `skills`, `exclude`, `rename` are duplicated across `Git` and `Path`. A third variant would triplicate them. Extract to a shared `FilterConfig`:

```rust
pub struct SourceEntry {
    pub spec: SourceSpec,           // Git { url, version } | Path { path } | Registry { name, version }
    pub filter: FilterConfig,       // agents, skills, exclude, rename — shared
}

pub struct FilterConfig {
    pub agents: Option<Vec<ItemName>>,
    pub skills: Option<Vec<ItemName>>,
    pub exclude: Option<Vec<ItemName>>,
    pub rename: Option<RenameMap>,
}
```

This reduces the per-variant surface to just the spec-specific fields. A new source type adds one `SourceSpec` variant and nothing else in config. The newtypes design (Phase 7, issue #15) already flags `EffectiveConfig` as bundling too many concerns — this separation aligns with that fix.

2. **Keep the source adapter files self-contained.** The current design already does this: `source/git.rs` and `source/path.rs` are independent modules. Adding `source/registry.rs` is pure addition. No existing adapter needs to change.

### Authenticated Private Registries

Auth for a registry is internal to the registry adapter. `source/registry.rs` handles credential lookup (env var, config file, keychain). It doesn't affect the pipeline, resolver, or config structure. The `git2` credential callbacks that already exist for git SSH auth demonstrate the pattern — auth is per-adapter, not per-pipeline.

One config addition: a `[registry]` or `[auth]` section in `agents.toml` or `agents.local.toml` for token storage. This is a new config section, not a change to existing sections.

### Decision: Factor `FilterConfig` out of `SourceEntry` in Phase 7

The newtypes phase already touches `SourceEntry` to replace `String` fields with newtypes. This is the natural time to also extract the shared filter fields. The extraction is a pure refactor — serde compatibility is maintained via `#[serde(flatten)]`. Adding a source type later goes from 8 file changes to 6 (config parsing and filter logic are decoupled).

**Do not** introduce a `Source` trait or plugin system. The number of source types will be 3 (git, path, registry) for the foreseeable future. Three concrete implementations with exhaustive match is simpler and more correct than a trait object registry.

---

## Extension Point 2: New CLI Commands

### Current Design

Clap derive with a `Command` enum in `cli/mod.rs`:

```rust
#[derive(Debug, clap::Subcommand)]
pub enum Command {
    Sync(SyncArgs),
    Add(AddArgs),
    Remove(RemoveArgs),
    Upgrade(UpgradeArgs),
    // ... 13 variants total
}

pub fn dispatch(cli: Cli) -> Result<i32, MarsError> {
    match cli.command {
        Command::Sync(args) => sync::run(&args, &root, cli.json),
        Command::Add(args) => add::run(&args, &root, cli.json),
        // ...
    }
}
```

### Adding `mars audit`, `mars diff`

3 touch points per command:
1. Add variant to `Command` enum
2. Create `cli/audit.rs` (or `cli/diff_cmd.rs`)
3. Add match arm in `dispatch()`

### Is This a Problem?

**No.** This is the standard clap pattern. The 3-touch-point cost is minimal, and the compiler enforces that dispatch handles every command. Reducing it further (e.g., auto-registration, command plugins) would add complexity for no benefit — we're talking about 15-20 commands total, not hundreds.

The important distinction: **read-only commands don't need to go through `SyncRequest`/`execute()`.** The unified pipeline is for state-mutating operations. `mars audit`, `mars diff`, `mars list`, `mars why`, `mars outdated` all read config + lock + disk and produce output without the flock/resolve/apply cycle. They call library functions directly:

```rust
// cli/audit.rs — reads, doesn't mutate
pub fn run(args: &AuditArgs, root: &Path, json: bool) -> Result<i32, MarsError> {
    let config = config::load(root)?;
    let lock = lock::load(root)?;
    let findings = audit::scan(root, &config, &lock)?;
    output::print_audit(&findings, json);
    Ok(if findings.has_critical() { 1 } else { 0 })
}
```

### Decision: No change needed

The current clap derive + dispatch pattern is the right approach for mars's command count. Don't abstract further.

---

## Extension Point 3: New ConfigMutation Variants

### Current Design (Post-Phase 4)

```rust
pub enum ConfigMutation {
    UpsertSource { name, entry },
    RemoveSource { name },
    SetOverride { source_name, local_path },
    ClearOverride { source_name },
}
```

Matched in 3 places:
- `apply_mutation()` — modifies `Config`
- `apply_local_mutation()` — modifies `LocalConfig`
- Step 15 of `execute()` — decides which file to persist

### Adding `AddRename` (for `mars rename`)

Would need:
```rust
ConfigMutation::AddRename {
    source_name: SourceName,
    rule: RenameRule,
}
```

Touch points: the enum definition + all 3 match arms.

### Should Mutations Be Trait Objects?

**No.** Here's the analysis:

| Approach | Pros | Cons |
|---|---|---|
| Closed enum | Exhaustive match, no heap alloc, inline data, compiler catches new variants | Must edit 3 match arms per variant |
| Trait objects (`dyn ConfigMutation`) | Open for extension, no enum edit | Heap alloc, lost exhaustiveness, must implement `apply_to_config` + `apply_to_local` + `persistence_target` per variant, harder to validate combinations |

The closed enum wins for a set this small. There are ~6 possible config mutations total (upsert, remove, rename, set override, clear override, maybe set-setting). The set is bounded by what `agents.toml` and `agents.local.toml` can express. Adding a variant is a 5-minute change with compiler guidance.

The exhaustive match is a **feature, not a limitation.** When `AddRename` is added, the compiler forces you to decide: does it modify `Config` or `LocalConfig`? What does step 15 persist? These are questions you must answer — the enum forces you to answer them at compile time instead of discovering at runtime that your trait impl forgot to handle persistence.

### The Real Risk: Step 15 Branching

The bigger concern isn't the enum — it's step 15 in `execute()`, which decides what to persist based on the mutation type:

```rust
match &request.mutation {
    Some(ConfigMutation::UpsertSource { .. } | ConfigMutation::RemoveSource { .. }) => {
        config::save(root, &config)?;
    }
    Some(ConfigMutation::SetOverride { .. } | ConfigMutation::ClearOverride { .. }) => {
        config::save_local(root, &local)?;
    }
    None => {}
}
```

This match grows with every variant. Worse, some future mutations might modify both files. A cleaner approach: give `ConfigMutation` a method that declares its persistence targets:

```rust
impl ConfigMutation {
    /// Which config files this mutation affects.
    fn persistence_targets(&self) -> PersistenceTargets {
        match self {
            Self::UpsertSource { .. } | Self::RemoveSource { .. } | Self::AddRename { .. } =>
                PersistenceTargets::CONFIG,
            Self::SetOverride { .. } | Self::ClearOverride { .. } =>
                PersistenceTargets::LOCAL,
        }
    }
}

bitflags! {
    struct PersistenceTargets: u8 {
        const CONFIG = 0b01;
        const LOCAL  = 0b10;
    }
}
```

Then step 15 becomes:

```rust
if let Some(mutation) = &request.mutation {
    let targets = mutation.persistence_targets();
    if !request.options.dry_run {
        if targets.contains(PersistenceTargets::CONFIG) { config::save(root, &config)?; }
        if targets.contains(PersistenceTargets::LOCAL) { config::save_local(root, &local)?; }
    }
}
```

This eliminates the step 15 match entirely. New variants declare their persistence targets alongside their definition, not in a distant match arm.

### Decision: Keep closed enum, add `persistence_targets()` method in Phase 4

The method is ~10 lines and eliminates one of the three match sites. The other two (`apply_mutation`, `apply_local_mutation`) remain exhaustive matches — those encode per-variant logic that can't be generalized.

---

## Extension Point 4: New Filter Modes

### Current Design

Filtering is implicit in `SourceEntry` fields, not an explicit `FilterMode` enum. The logic in `target::build()` is an if-else chain:

```rust
if let Some(ref agents) = source_entry.agents {
    // agents mode: include these + skill deps
} else if let Some(ref skills) = source_entry.skills {
    // skills mode: include these explicitly
} else if let Some(ref exclude) = source_entry.exclude {
    // exclude mode: everything except these
} else {
    // default: everything
}
```

### Adding Pattern-Based Globs

A glob filter (`include_pattern: Option<String>`) would add one branch to the if-else chain and one field to `SourceEntry`/`FilterConfig`. No existing branches change.

### Should We Introduce a `FilterMode` Enum?

**Maybe, but not now.** The current 4 modes (agents, skills, exclude, all) are naturally expressed as Option fields because they're mutually exclusive config choices. A `FilterMode` enum would look like:

```rust
pub enum FilterMode {
    All,
    Agents(Vec<ItemName>),
    Skills(Vec<ItemName>),
    Exclude(Vec<ItemName>),
    Pattern(GlobPattern),  // future
}
```

This is cleaner than the Option fields for validation (can't accidentally set both agents and exclude), but it complicates serde deserialization from TOML. The current Optional fields map naturally to TOML syntax — the user writes `agents = ["coder"]` or `exclude = ["deprecated"]`, and the absence of both means "all."

A `FilterMode` enum would require either a tagged `[filter]` section or custom deserialization that infers the variant from which fields are present — essentially reimplementing the current if-else logic in a serde visitor.

### Decision: No change now, extract `FilterConfig` in Phase 7

The if-else chain in `build()` is fine for 4-5 modes. The Phase 7 `FilterConfig` extraction (recommended in Extension Point 1 above) is the right place to consider whether a `FilterMode` enum earns its keep. If glob patterns are planned for v2, add the enum then.

---

## Extension Point 5: Plugin Hooks (Pre-Sync, Post-Sync)

### Where They Attach

The unified pipeline in [sync-pipeline.md](sync-pipeline.md) has 17 discrete steps with typed intermediate values. Hooks insert between steps:

```
Step 0:  Validate request
  ── pre-sync hook ──
Step 1:  Acquire flock
Step 2-4: Load config, apply mutation, merge
Step 5:  Validate targets
Step 6:  Load lock
Step 7:  Resolve graph
  ── post-resolve hook ──
Step 8-11: Build target, collisions, validate
Step 12-13: Diff + plan
  ── pre-apply hook ──  (last chance to inspect/abort)
Step 14: Frozen gate
Step 15: Persist config
Step 16: Apply plan
Step 17: Write lock
  ── post-sync hook ──
```

### Does `SyncRequest` Need an Extension Mechanism?

**No.** Hooks come from config, not from the command:

```toml
# agents.toml
[hooks]
pre-sync = "scripts/validate-agents.sh"
post-sync = "scripts/notify-team.sh"
```

They're loaded at step 2 (config load) and executed at the hook points. The pipeline function is where hooks integrate, not the request.

### What the Current Design Needs for Hooks

1. **A `[hooks]` section in config.** Pure config addition — new field on `Settings`.
2. **Hook execution logic.** A function like `run_hook(name, hook_cmd, context) -> Result<()>` that shells out, passes context via env vars or JSON stdin, and fails the pipeline on non-zero exit.
3. **Hook points in `execute()`.** 4-5 `if let Some(hook) = config.hooks.pre_sync { run_hook(...)?; }` calls placed between steps.

None of this requires changing existing types. The pipeline's sequential structure (each step depends on the previous step's output) makes insertion trivial — it's just another step in the sequence.

### Decision: No changes now, pipeline is hook-ready

The unified `execute()` function with discrete steps is the ideal hook integration point. No structural preparation needed. When hooks ship in v2, it's a localized addition to `execute()` plus config parsing.

---

## Extension Point 6: v2 Feature Compatibility

For each v2 feature from [features.md](../../agent-package-management/design/features.md), whether the v1 refactor makes it easier or harder.

### Patches (Persistent Local Customizations)

**What it needs**: Store patch data per item, apply after sync, track in lock.

**Refactor impact**: **Positive.** The `TargetItem.rewritten_content: Option<String>` pattern from the [frontmatter](frontmatter.md) design establishes the precedent for "content override before apply." Patches follow the same pattern: after step 16 applies the plan, a new step 16b applies patches. The `installed_checksum` field (dual checksum design) already handles "what we wrote differs from what the source provided."

**Required changes**: New lock field (`patch_checksum` or `patched: bool`). New config section (`[patches]` or inline). New pipeline step. No changes to existing steps.

### Rerere (Reuse Recorded Resolution)

**What it needs**: Record conflict resolutions, replay on future merges.

**Refactor impact**: **Neutral.** Rerere lives in the merge layer (`merge/mod.rs`), which the refactor doesn't modify. The unified pipeline makes it clearer where merges happen (step 16, inside `apply::execute()`), but the merge implementation itself is untouched.

**Required changes**: `.mars/rerere/` storage, check in `merge::merge_content()` before presenting conflicts.

### Semantic Frontmatter Merge

**What it needs**: Field-level merge for YAML frontmatter instead of line-level.

**Refactor impact**: **Strongly positive.** The Phase 1 [frontmatter module](frontmatter.md) creates a typed `Frontmatter` struct with field-level access. Currently used for skill rewriting, but the same typed access enables field-level merge: parse base, local, and theirs into `Frontmatter` structs, merge each field independently, serialize the result. Without the frontmatter module, semantic merge would require building this from scratch.

**Required changes**: New function in `frontmatter/mod.rs` (`merge_frontmatter(base, local, theirs) -> MergeResult`). Integration point in `merge/mod.rs`.

### Script Management (Security Model)

**What it needs**: Trust model for bundled scripts, approval workflow, checksum verification.

**Refactor impact**: **Neutral.** Scripts are a new item kind alongside agents and skills. The refactor's `ItemKind` enum (currently `Agent | Skill`) would need a `Script` variant. The `discover/` module would need to find scripts. The unified pipeline processes all items the same way after discovery, so the pipeline itself doesn't change — it's the discovery and validation steps that expand.

**Required changes**: `ItemKind::Script`, discovery pattern, trust validation step (between steps 10-11), config `[trust]` section.

### Source Trust Policies

**What it needs**: `[trust]` config section, validation during resolution.

**Refactor impact**: **Positive.** The unified pipeline loads config at step 2 under flock. Trust validation can run at step 5 (validate targets) — check each source's type against the trust policy before resolution. The `SourceSpec` enum makes this a clean match.

**Required changes**: `[trust]` in `Settings`, validation function at step 5.

### `mars diff` (Show Pending Changes)

**What it needs**: Read lock + fetch upstream + diff without applying.

**Refactor impact**: **Positive.** This is a read-only command that reuses pipeline steps 2-12 (config → resolve → target → diff) without steps 13-17 (plan → apply → lock). The refactored pipeline has clean intermediate values that `mars diff` can consume directly.

**Required changes**: New CLI command (3 touch points), calls library functions directly. No pipeline changes.

### `mars audit` (Security Audit)

**What it needs**: Scan installed content for suspicious patterns, check dependencies.

**Refactor impact**: **Neutral.** Purely additive — reads from disk, produces a report. No pipeline interaction.

**Required changes**: New `audit/` module, new CLI command.

### `mars init --from` (Clone Existing Config)

**What it needs**: Read a remote project's `agents.toml`, copy it locally.

**Refactor impact**: **Neutral.** Simple addition to `cli/init.rs`. No pipeline interaction — it creates the config file, then the user runs `mars sync`.

**Required changes**: New flag on `InitArgs`, URL fetch logic.

### Private Registry Auth

**What it needs**: Credential storage, auth headers on registry API calls.

**Refactor impact**: **Positive** (if `FilterConfig` extraction happens). Registry auth is internal to `source/registry.rs`. The credential lookup pattern (`env var → config file → credential helper`) mirrors what `git2` already does for git auth. No pipeline changes.

**Required changes**: Auth module, `[registry.auth]` config section, credential helpers.

---

## Where the Design Is Closed vs Open

### Deliberately Closed (Enum Match — Keep It)

| Type | Variants | Why Closed Is Correct |
|---|---|---|
| `SourceSpec` / `SourceEntry` | Git, Path (+Registry) | Source types have fundamentally different data shapes. Exhaustive match prevents forgotten handling. New types are rare (years between additions). |
| `ConfigMutation` | 4-6 variants | Bounded by config file structure. Exhaustive match ensures persistence correctness. |
| `MarsError` | ~10 variants | `exit_code()` must be exhaustive per [resolver-and-errors](resolver-and-errors.md). Wildcard default hides new error categories. |
| `ItemKind` | Agent, Skill (+Script) | Discovery and destination path logic differs per kind. Exhaustive match in `discover/`, `target::build()`, lock. |
| `DiffEntry` / `PlannedAction` | 6 variants each | Pipeline stages — each variant maps to a specific action. The set is determined by the merge matrix (2×2 = 4 cases + orphan + new). |

### Naturally Open (Add Without Modifying)

| Extension | Mechanism | Why Open Works |
|---|---|---|
| New CLI commands | Add file + enum variant + dispatch arm | Read-only commands bypass pipeline entirely. Compiler catches missing dispatch. |
| Plugin hooks | Config section + insertion points in `execute()` | Pipeline steps are sequential; hooks are additional steps. |
| New frontmatter fields | `Frontmatter.yaml` is a `Mapping` (schema-agnostic) | Typed accessors for known fields, generic `get()` for unknown fields. |
| Lock schema extensions | `version: 1` field + optional fields | New fields in lock don't break old readers (serde skips unknown fields by default). |
| Source adapter internals | Each adapter is a self-contained module | `source/registry.rs` can have its own auth, caching, API logic without touching `source/git.rs`. |

---

## Concrete Changes to the Refactor Design

### Change 1: Extract `FilterConfig` from `SourceEntry` (Phase 7)

**In [newtypes-and-parsing.md](newtypes-and-parsing.md)**: When converting `SourceEntry` fields to newtypes, also factor the shared filter fields into a `FilterConfig` struct:

```rust
pub struct SourceEntry {
    pub spec: SourceSpec,
    pub filter: FilterConfig,
}

pub enum SourceSpec {
    Git { url: SourceUrl, version: Option<String> },
    Path { path: PathBuf },
}

pub struct FilterConfig {
    pub agents: Option<Vec<ItemName>>,
    pub skills: Option<Vec<ItemName>>,
    pub exclude: Option<Vec<ItemName>>,
    pub rename: Option<RenameMap>,
}
```

**Why now**: Phase 7 already modifies every field of `SourceEntry` for newtype conversion. The extraction is a pure refactor on top of that work. Doing it separately later would require re-touching all the same call sites.

**Cost**: ~30 minutes of additional work in Phase 7. All match arms on `SourceEntry` change shape (from per-variant fields to `entry.filter.agents`), but they're already being modified for newtypes.

**Benefit**: Adding `SourceSpec::Registry` later touches 6 files instead of 8. Filter logic in `target::build()` works identically regardless of source type.

### Change 2: Add `persistence_targets()` to `ConfigMutation` (Phase 4)

**In [sync-pipeline.md](sync-pipeline.md)**: Replace the step 15 match with a `persistence_targets()` method on `ConfigMutation`.

**Why now**: Step 15 is being written fresh as part of the unified pipeline. Starting with the method avoids ever writing the match that would need to grow.

**Cost**: ~10 lines.

**Benefit**: New `ConfigMutation` variants declare persistence alongside their definition. Step 15 never needs editing again.

### Change 3: No other changes

Everything else is YAGNI. Specifically, do **not**:

- **Introduce a `Source` trait hierarchy.** Three concrete adapter files with exhaustive match is simpler and more correct than trait objects for 3 types.
- **Make `FilterMode` an enum.** The if-else chain is fine for 4 modes. The enum adds serde complexity for no benefit until globs are actually planned.
- **Add hook infrastructure.** The pipeline is structurally ready for hooks. Adding the infra before v2 is premature abstraction — the hook API should be designed when the requirements are concrete.
- **Add a plugin system for commands.** 15 commands in a match statement is not a scaling problem.
- **Make `MarsError` open (trait-based).** The exhaustive `exit_code()` match is the primary value of the closed enum. Opening it would require a default exit code, which defeats the purpose.

---

## YAGNI Boundaries

These are things that sound reasonable but would be premature:

| Abstraction | Why Not Now |
|---|---|
| `Source` trait for extensible source types | 3 concrete types don't justify a trait hierarchy. Exhaustive match is safer. The dead `SourceFetcher` trait (issue #10) is being removed for exactly this reason. |
| Command plugin registry | mars will have ~20 commands. A match statement with 20 arms is fine. Plugin overhead (registration, discovery, lifecycle) exceeds the benefit. |
| `FilterMode` enum | The if-else chain in `target::build()` is 4 branches. The enum complicates serde for no code quality gain. Revisit when globs arrive. |
| Hook framework (pre/post every step) | Only 2-4 hook points are useful (pre-sync, post-resolve, pre-apply, post-sync). A generic framework for arbitrary hook points would be unused complexity. Add hooks as config fields when v2 ships. |
| Middleware/interceptor pipeline | The 17-step pipeline is sequential with typed intermediates. Wrapping it in a middleware chain adds indirection without flexibility — the steps have concrete dependencies on previous steps' outputs. |
| `DiffEntry`/`PlannedAction` extensibility | These encode the 2×2 merge matrix. The matrix doesn't grow — it's determined by the fundamental question "did source change × did local change." New actions (like patch application) are separate pipeline steps, not new diff/plan variants. |

---

## Summary: What Makes v2 Easy vs Hard

**Easy (no structural changes)**:
- Plugin hooks — pipeline steps are discrete, config can declare hooks
- `mars diff`, `mars audit` — read-only commands, pure addition
- `mars init --from` — simple config copy
- Private registry auth — internal to adapter
- Lock schema extensions — optional fields + version number
- Patches — new pipeline step + lock field

**Moderate (localized structural changes)**:
- Semantic frontmatter merge — builds on Phase 1 frontmatter module
- Rerere — contained in merge layer
- Source trust policies — new config section + validation step
- Script management — new `ItemKind` variant + discovery pattern

**Hard (cross-cutting structural changes)**:
- New source type (registry) — 6-8 files, inherent to source threading through the system
- Workspace support — `SyncRequest` currently assumes one root; workspaces need per-target resolution

The refactor doesn't make the hard ones easy — that would require premature abstraction. It makes the hard ones **predictable**: exhaustive match tells you exactly what to update, and the unified pipeline means there's one place to thread through, not two (the forked upgrade engine is the cautionary tale).
