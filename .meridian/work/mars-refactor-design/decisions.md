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
