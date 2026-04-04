# Decisions

## D1: Closed enum for ItemKind, not trait-based extensibility

**Choice**: Extend `ItemKind` with new variants (Permission, Tool, McpServer, Hook) as a closed enum.

**Rejected**: Trait-based `dyn ItemHandler` pattern where each kind registers a handler dynamically.

**Reasoning**: The number of item kinds is small (6-8), changes rarely, and each kind has genuinely different semantics. Exhaustive match catches every place that needs updating when a new kind is added. The dead `SourceFetcher` trait was removed in the prior v1 refactor for exactly this reason — trait abstraction for a small, stable set of types adds indirection without value. The compiler is the enforcement mechanism, not runtime dispatch.

## D2: Trait for RuntimeAdapter, not closed enum

**Choice**: Use a `RuntimeAdapter` trait for per-runtime materialization (ClaudeAdapter, CursorAdapter, etc.).

**Rejected**: Closed `RuntimeKind` enum with exhaustive match.

**Reasoning**: Unlike item kinds, runtime adapters are self-contained modules with no shared exhaustive match needed. The set of supported runtimes grows independently of mars's release cycle (new editors/tools appear). Each adapter encapsulates its own config format knowledge. The trait boundary keeps adapter logic self-contained. For now, it's 2-3 built-in structs — the trait prevents coupling between adapters.

## D3: Pipeline phase structs nest rather than flatten

**Choice**: `ResolvedState` contains `LoadedConfig`, `TargetedState` contains `ResolvedState`, etc. — each phase struct nests the previous.

**Rejected**: Flattened structs where each phase returns only its new data, and `execute()` passes all previous data explicitly.

**Reasoning**: Later phases legitimately need earlier data — lock building needs the graph from resolution, finalization needs the old lock from loading. Nesting preserves access without unwieldy multi-parameter function signatures. Phase structs are moved (not cloned), so there's no memory overhead. The alternative requires execute() to maintain 6+ local variables and pass 4+ arguments to each phase function.

## D4: Capability materialization as a separate phase, not integrated into apply

**Choice**: Content items (agents, skills) are applied in `apply_plan()`. Capability items (permissions, tools, MCP, hooks) are materialized in a subsequent `materialize_capabilities()` phase.

**Rejected**: Having `apply_plan()` handle both content and capability materialization.

**Reasoning**: Content apply is destination-scoped (one item → one file/directory in managed root). Capability materialization is target-scoped (many items → one config file per runtime). These are fundamentally different operations — content apply is per-item, capability materialization is aggregate. Keeping them separate means content sync works exactly as before (no risk), and capability materialization is additive.

## D5: DependencyEntry split is internal, not format-breaking

**Choice**: Split `DependencyEntry` into `InstallDep` and `ManifestDep` as Rust types. Both deserialize from the same TOML format as before.

**Rejected**: Changing the mars.toml format to use separate `[dependencies]` and `[manifest.dependencies]` sections.

**Reasoning**: The on-disk format works fine — a `[dependencies]` entry can serve both purposes depending on whether it's in a consumer or package config. The problem is that the Rust types don't distinguish between the two uses, causing the resolver to silently compensate. Fixing the types without changing the format preserves backwards compatibility while making the code correct.

## D6: Permission conflicts default to most-restrictive-wins

**Choice**: When multiple packages provide conflicting permission policies, security-relevant fields (sandbox tier, denied tools) resolve to the most restrictive value.

**Rejected**: First-declared-wins, error-on-conflict, or consumer-must-resolve.

**Reasoning**: Package-defined permissions are defaults, not absolutes. The most-restrictive-wins policy is the safest default — it prevents accidentally granting more permissions than intended when combining packages. Consumers override via `mars.local.toml` for their specific needs. Error-on-conflict would block adoption; first-declared-wins would create order-dependent behavior.

## D7: Phase functions consume prior state by value (move semantics)

**Choice**: Phase functions take prior state by value — `resolve_graph(ctx, loaded: LoadedConfig, ...)` moves `LoadedConfig` into the function, which returns `ResolvedState` containing it.

**Rejected**: Borrowing prior state (`&LoadedConfig`) while nesting ownership in return types.

**Reasoning**: Flagged by implementability reviewer — the original design had phase functions borrowing prior state (`&loaded`) while the phase structs nested by ownership. This can't type-check without lifetimes or cloning. Move-by-value is the simplest model: each phase consumes the previous phase's output and produces the next. The `execute()` orchestrator is a linear chain of moves. This matches the "moved, not cloned" claim and avoids lifetime complexity.

## D8: Single RuntimeAdapter::materialize() method, not per-capability methods

**Choice**: `RuntimeAdapter` has one `materialize(&CapabilitySet, &Path)` method that receives all capabilities at once.

**Rejected**: Separate `materialize_permissions()`, `materialize_tools()`, `materialize_mcp()`, `materialize_hooks()` methods.

**Reasoning**: Flagged by SOLID reviewer as ISP violation. Per-capability methods force every adapter to implement stubs for capabilities they don't support. More importantly, multiple capability kinds often write to the same config file (e.g., Claude's `settings.json` handles permissions, MCP, and tools). A single method lets the adapter handle the merge atomically — read config once, apply all changes, write once. Separate methods would require coordination (who reads first? who writes last?) or multiple read-write cycles.

## D9: Capability materialization is non-fatal by default

**Choice**: Capability materialization failures produce diagnostics but don't fail `mars sync`. Content sync completes normally. Opt-in `--strict-capabilities` makes failures fatal.

**Rejected**: Making all materialization failures fatal; making them always silent.

**Reasoning**: Flagged by implementability reviewer — failure semantics were undefined. Content sync is the primary value proposition; capability sync is additive. A package with an MCP server config that doesn't apply to a CursorAdapter shouldn't block agent/skill installation. The lock is written only after all phases succeed (including materialization diagnostics), so the next `mars sync` will re-attempt materialization.

## D10: Local packages use the same discovery path as dependencies

**Choice**: The project root is treated as a synthetic source and run through the same `discover_source()` function as dependency sources. Only materialization strategy (Symlink vs Copy) and shadow precedence remain local-specific.

**Rejected**: Separate `discover_local_items()` function with its own scan logic.

**Reasoning**: Flagged by correctness reviewer — the original design kept local packages on a bespoke discovery path, which means Phase B's "add one entry to conventions()" wouldn't automatically apply to local packages. Using the same discovery function ensures new item kinds are discovered from local packages without maintaining parallel code.

## D11: Shared reconciliation is two layers, not one

**Choice**: Extract shared atomic filesystem operations (Layer 1) used by both sync and link, plus item-level reconciliation (Layer 2) used by sync apply. Link's merge-then-symlink algorithm remains link-specific but uses Layer 1 primitives.

**Rejected**: A single `reconcile_one()` API that fully subsumes both sync apply and link behavior.

**Reasoning**: Flagged by both correctness and implementability reviewers — the original single-layer reconcile API only modeled file-level operations, but sync handles directory installs (skills) and link has a unique merge-unique-files-then-symlink algorithm. These are genuinely different operations. Extracting shared primitives (atomic write, atomic symlink, content hash) eliminates the real duplication without forcing a false abstraction over different reconciliation strategies.

## D12: Hook scripts require explicit consumer opt-in

**Choice**: Hooks from packages are discovered and tracked but not enabled until the consumer explicitly lists them in `settings.enable_hooks`.

**Rejected**: Auto-enabling hooks, or trusting hooks from "trusted" sources.

**Reasoning**: Hook scripts are executable code — auto-enabling them from packages would be a security risk. The consumer should make an explicit decision about which hooks to run. This matches the pattern of MCP servers (configured explicitly) and avoids the npm postinstall footgun.

## D13: Soul files are a proper ItemKind, not just a directory convention

**Choice**: Add `ItemKind::Soul` as a first-class item kind, discovered via the same convention registry as agents/skills.

**Rejected**: Treating soul files as a subdirectory convention that lives outside the sync pipeline (just copy files, no lock tracking).

**Reasoning**: Soul files need the same lifecycle as other synced content — lock tracking for change detection, `mars list` visibility, kind-based filtering (`include_kinds = ["soul"]`), and participation in the diff/plan/apply pipeline. Making them a proper ItemKind gives all of this for free via the discovery convention registry. The alternative would require bespoke handling outside the pipeline, which is exactly the pattern the refactor is eliminating.

## D14: Harness variant resolution happens at target sync, not discovery

**Choice**: Discovery finds all variants and attaches them to the base item. The managed root (`.agents/`) always gets the default version. Variants are resolved and applied only when syncing managed targets.

**Rejected**: Resolving variants during discovery so `.agents/` contains variant-resolved content.

**Reasoning**: `.agents/` is the canonical source of truth and should contain the default (harness-agnostic) content. If `.agents/` contained Claude-specific variants, any tool reading `.agents/` directly would get Claude-optimized content even when running under a different harness. Keeping variant resolution at target sync time means: (1) `.agents/` is always the universal default, (2) each managed target gets the right variant for its harness, (3) tools reading `.agents/` directly still work correctly with the default content.

## D15: Link reframed as "managed target sync" — not symlinks

**Choice**: Redefine `mars link` to mean "mars owns and manages this target directory," with content copied (not symlinked) and variants resolved per target. Default strategy is mirror (copy + ongoing sync).

**Rejected**: Keeping symlink-based linking as the primary mechanism, with variant support bolted on.

**Reasoning**: The original symlink approach worked for agents/skills where the content is the same regardless of harness. With harness-specific variants, soul files, and capability materialization, each managed target needs different content than `.agents/`. Symlinks point to one location — they can't resolve variants. Copying is the only mechanism that supports per-target content customization. The mirror strategy ensures targets stay in sync without requiring users to re-run `mars link` separately from `mars sync`. Symlink mode is preserved as an optimization for simple cases where no variants or capabilities are needed.

## D16: Model catalog is pipeline-adjacent, not a sync item

**Choice**: The `[models]` config section and models cache are managed as standalone artifacts, not as items in the sync pipeline. `mars models refresh` is a separate command. The pipeline carries model config through `LoadedConfig` but doesn't discover/diff/apply models.

**Rejected**: Making model aliases an item kind that packages "install."

**Reasoning**: Model aliases are configuration, not content. They don't come from a source tree directory, don't have checksums, and don't need diff/plan/apply semantics. They're key-value mappings in mars.toml. The cache is a network-fetched artifact, not a package artifact. Forcing models into the item pipeline would require inventing fake discovery/diff/apply semantics for what's fundamentally a config merge. Instead, model aliases merge at config load time (package defaults + consumer overrides), and the cache is a standalone file that `mars models refresh` manages.

## D17: Variant naming convention uses `<name>.<harness>.<ext>` in source

**Choice**: Harness-specific variants are identified by filename convention: `coder.claude.md` is the Claude variant of `coder.md`. The harness identifier matches the managed target name with the leading dot stripped (`.claude` → `claude`).

**Rejected**: (a) Separate directories per harness (`agents/claude/coder.md`), (b) Frontmatter-based variant declaration, (c) mars.toml-level variant mapping.

**Reasoning**: Filename convention is the simplest mechanism that works with the existing discovery pipeline. It requires no config, no parsing, and no new directory structure. Discovery already scans `agents/*.md` — extending the pattern to recognize `<name>.<harness>.md` is a minimal change. Separate directories would break the flat `agents/` convention and complicate lock paths. Frontmatter-based declaration would require parsing every file during discovery. Config-level mapping would be verbose for the common case.

## D18: Managed targets configured via `[[settings.targets]]` with backwards-compatible `links`

**Choice**: New `[[settings.targets]]` TOML array for managed target configuration, with the existing `links = [".claude"]` syntax supported as shorthand.

**Rejected**: Breaking the `links` syntax, or overloading it with new fields.

**Reasoning**: The `links` syntax is simple and works for the common case. The new `[[settings.targets]]` syntax is needed for per-target configuration (content strategy, etc.). Supporting both means existing mars.toml files keep working. The migration path is: `links = [".claude"]` is equivalent to `[[settings.targets]] name = ".claude"` with defaults. Users who need per-target config use the new syntax.

## D19: Content sync is generic; capability materialization dispatches via AdapterKind enum

**Choice**: Content sync uses a shared function (variant resolution by harness ID). Capability materialization dispatches through a closed `AdapterKind` enum. Replaces the original `Box<dyn RuntimeAdapter>` trait approach.

**Rejected**: (a) Trait-based `Box<dyn RuntimeAdapter>` with both sync_content and materialize methods, (b) Keeping sync_content adapter-specific.

**Reasoning**: Implementability reviewer flagged tension between `Box<dyn RuntimeAdapter>` and the "single binary, no dynamic loading" constraint from D1. Content sync is actually the same algorithm for all adapters — the only varying input is the harness ID for variant selection. Making it adapter-specific would duplicate the same code across adapters. Capability materialization genuinely differs per adapter (different config formats), so that's where dispatch happens. A closed enum gives exhaustive match and avoids heap allocation, consistent with D1's reasoning.

## D20: Variant parsing uses last-segment matching against known harness IDs

**Choice**: Extract the harness ID by matching the last dot-separated stem segment against the set of known managed target harness IDs from config. Item names may contain dots; harness IDs may not.

**Rejected**: (a) Always splitting on the second-to-last dot (ambiguous for dotted names), (b) Using a different delimiter like `__` or `@`.

**Reasoning**: Both reviewers flagged the `<name>.<harness>.<ext>` convention as ambiguous for names containing dots. The fix is to make variant detection depend on config: a file is only a variant if its last stem segment matches a configured harness ID. This means `review.v2.claude.md` is a variant of `review.v2` for `claude` *only if* `claude` is a configured target. Without configured targets, no files are variants. Requiring harness IDs to be dot-free (enforced at config validation) makes the split unambiguous. Alternative delimiters (`__`, `@`) would break the natural `.claude.md` naming that users expect.

## D21: Lock written regardless of target sync outcome (non-strict mode)

**Choice**: In non-strict mode, the lock is always written after successful content apply to `.agents/`, even if managed target sync fails. Target sync status is reported separately in `SyncReport.target_outcomes`.

**Rejected**: (a) Not writing lock on target sync failure (original design), (b) Always making target sync failure fatal.

**Reasoning**: Correctness reviewer flagged that "lock not written + non-fatal target sync" is contradictory — if the command succeeds but the lock isn't advanced, the next run doesn't have a committed baseline. The lock should reflect what's in `.agents/` (the source of truth), not what's in managed targets. Targets are derived state that can always be re-synced. Writing the lock ensures the next `mars sync` operates from the correct baseline and only re-runs target sync (which is idempotent).

## D22: Variant content goes through the same rewrite pipeline as base items

**Choice**: `VariantSource` includes a `rewritten_content` field, and variant content goes through the same frontmatter/rename rewrite pipeline as the base item during target building.

**Rejected**: Skipping rewrites for variant content (only using raw source files).

**Reasoning**: Correctness reviewer flagged that `sync_target_content()` would read raw variant files, bypassing the rewrite pipeline that transforms base items (frontmatter transforms, skill renames per `rewrite.rs`). This would cause managed targets to get unrewritten variant content while `.agents/` gets the rewritten default — breaking renamed skill references. Variants must go through the same transforms to maintain consistency.

## D23: Lock version conditional on content — v1 when no variants, v2 when variants present

**Choice**: Mars writes v1 lock format when no items have variants, v2 when any item has variants. The loader checks the version field before deserializing and rejects unknown versions with a clear error.

**Rejected**: (a) Always writing v2 once the mars version supports it, (b) Silently ignoring unknown fields.

**Reasoning**: Correctness reviewer flagged that the v2 lock schema (nested `variants` table) would be silently accepted and variant data dropped by older mars versions that only know v1. Conditional version writing means projects that don't use variants stay on v1 (compatible with older mars). Projects that adopt variants get v2, and older mars fails fast with a clear upgrade message instead of silently dropping data.
