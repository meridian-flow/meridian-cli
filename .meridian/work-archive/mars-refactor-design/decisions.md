# Decisions

## D1: Closed enum for ItemKind, not trait-based extensibility

**Choice**: Extend `ItemKind` with new variants (Permission, Tool, McpServer, Hook) as a closed enum.

**Rejected**: Trait-based `dyn ItemHandler` pattern where each kind registers a handler dynamically.

**Reasoning**: The number of item kinds is small (6-8), changes rarely, and each kind has genuinely different semantics. Exhaustive match catches every place that needs updating when a new kind is added. The dead `SourceFetcher` trait was removed in the prior v1 refactor for exactly this reason — trait abstraction for a small, stable set of types adds indirection without value. The compiler is the enforcement mechanism, not runtime dispatch.

## D2: Closed enum for AdapterKind, not trait-based (REVISED from trait approach)

**Choice**: Use a closed `AdapterKind` enum with exhaustive match for per-runtime cross-compilation (Claude, Cursor, Codex, Generic).

**Rejected**: (a) `Box<dyn RuntimeAdapter>` trait — original D2 proposed this. (b) Fully open plugin system.

**Reasoning**: The implementability reviewer flagged tension between `Box<dyn RuntimeAdapter>` and the "single binary, no dynamic loading" constraint. The adapter set is closed and small (3-4 built-in). A closed enum gives exhaustive match (compiler catches missing adapters), avoids heap allocation, and is consistent with D1's reasoning. Content sync is actually the same algorithm for all adapters — only capability cross-compilation differs. If the adapter set truly needs to be open, the enum can be replaced with a trait later. **Supersedes original D2.**

## D3: Pipeline phase structs nest rather than flatten

**Choice**: `ResolvedState` contains `LoadedConfig`, `TargetedState` contains `ResolvedState`, etc. — each phase struct nests the previous.

**Rejected**: Flattened structs where each phase returns only its new data, and `execute()` passes all previous data explicitly.

**Reasoning**: Later phases legitimately need earlier data — lock building needs the graph from resolution, finalization needs the old lock from loading. Nesting preserves access without unwieldy multi-parameter function signatures. Phase structs are moved (not cloned), so there's no memory overhead. The alternative requires execute() to maintain 6+ local variables and pass 4+ arguments to each phase function.

## D4: Capability materialization as a separate phase, not integrated into apply

**Choice**: Content items (agents, skills) are applied in `apply_plan()`. Capability items (permissions, tools, MCP, hooks) are materialized in a subsequent `materialize_capabilities()` phase.

**Rejected**: Having `apply_plan()` handle both content and capability materialization.

**Reasoning**: Content apply is destination-scoped (one item → one file/directory in canonical store). Capability materialization is target-scoped (many items → one config file per runtime). These are fundamentally different operations — content apply is per-item, capability materialization is aggregate. Keeping them separate means content sync works exactly as before (no risk), and capability materialization is additive.

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

**Choice**: `AdapterKind` has one `materialize_capabilities(&CapabilitySet, &Path)` method that receives all capabilities at once.

**Rejected**: Separate `materialize_permissions()`, `materialize_tools()`, `materialize_mcp()`, `materialize_hooks()` methods.

**Reasoning**: Flagged by SOLID reviewer as ISP violation. Per-capability methods force every adapter to implement stubs for capabilities they don't support. More importantly, multiple capability kinds often write to the same config file (e.g., Claude's `settings.json` handles permissions, MCP, and tools). A single method lets the adapter handle the merge atomically — read config once, apply all changes, write once. Separate methods would require coordination (who reads first? who writes last?) or multiple read-write cycles.

## D9: Capability materialization is non-fatal by default

**Choice**: Capability materialization failures produce diagnostics but don't fail `mars sync`. Content sync completes normally. Opt-in `--strict` makes failures fatal.

**Rejected**: Making all materialization failures fatal; making them always silent.

**Reasoning**: Flagged by implementability reviewer — failure semantics were undefined. Content sync is the primary value proposition; capability sync is additive. A package with an MCP server config that doesn't apply to a CursorAdapter shouldn't block agent/skill installation. The lock is written after content apply regardless of target sync outcome, so the next `mars sync` will re-attempt target sync.

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

## D13: Rule files are a proper ItemKind, not just a directory convention (renamed from "soul")

**Choice**: Add `ItemKind::Rule` as a first-class item kind, discovered via the convention registry with a specialized `RuleTree` discovery pattern that handles shared, per-harness, and per-model categories.

**Rejected**: (a) Treating rule files as a subdirectory convention outside the sync pipeline. (b) Keeping the "soul" naming.

**Reasoning**: Rule files need the same lifecycle as other synced content — lock tracking for change detection, `mars list` visibility, kind-based filtering, and participation in the diff/plan/apply pipeline. Making them a proper ItemKind gives all of this for free. The "soul" name was wrong — OpenClaw's Soul.md is about identity/personality. What we're building is operational rules: per-model thinking instructions, per-harness behavioral adaptations. "Rule" matches Claude Code's existing `.claude/rules/` convention and accurately describes the content. See D24 for the soul→rule rename decision.

## D14: Variant resolution happens at target sync, not discovery (REVISED)

**Choice**: Discovery finds all variants and attaches them to the base item. The canonical store (`.mars/content/`) always gets the default version. Variants are resolved and applied only when syncing managed targets.

**Rejected**: Resolving variants during discovery so the canonical store contains variant-resolved content.

**Reasoning**: `.mars/content/` is the canonical content store and should contain the default (harness-agnostic) content. If `.mars/content/` contained Claude-specific variants, any target materialized from it would get Claude-optimized content unless explicitly overridden. Keeping variant resolution at target sync means: (1) `.mars/content/` is always the universal default, (2) each managed target gets the right variant for its harness, (3) the default target (`.agents/`) always gets harness-agnostic content.

## D15: All targets are managed — copy-based materialization (REVISED)

**Choice**: ALL target directories (`.agents/`, `.claude/`, `.codex/`, `.cursor/`) are managed outputs materialized from `.mars/content/` via copy. No target is special. Default strategy is copy for all targets.

**Rejected**: (a) Keeping `.agents/` as the source of truth with symlink-based linking to other targets (original design). (b) Keeping symlink as the default materialization strategy.

**Reasoning**: The original design had `.agents/` as the managed root and other targets derived from it. This is wrong because: if a harness reads `.agents/` directly (e.g., Codex), mars can't control what it sees per-harness. You can't have content that's "shared between Claude and Cursor but not Codex" when `.agents/` is the universal source. `.mars/content/` as the canonical store, with all targets as managed outputs, solves this cleanly. Copy (not symlink) for targets because: Windows symlinks need admin mode, git symlinks are finicky, copy + tmp+rename is simpler for crash safety, and variant-resolved content can't be symlinked (each target may get different content). **Supersedes original D15.**

## D16: Model catalog is pipeline-integrated config merge, not a sync item (REVISED)

**Choice**: Model aliases are configuration that merges from the dependency tree during `resolve_graph()`, using the same precedence pattern as other config sections (consumer > deps > builtins). Models are NOT item kinds — they don't go through discover/diff/plan/apply. The cache is a separate network-fetched artifact managed by `mars models refresh`.

**Rejected**: (a) Making model aliases an item kind that packages "install." (b) Keeping model catalog independent from the pipeline (original D16).

**Reasoning**: Model aliases are configuration, not content — they don't have checksums and don't need diff/plan/apply semantics. But they're NOT independent of the pipeline either: rule discovery (B1) needs the merged model alias set to classify per-model rules, and packages distribute `[models]` sections that must merge with the same precedence as other config. The merge happens in `resolve_graph()` because that's where dependency manifests are loaded. Cache stays at `.mars/models-cache.json`. **Supersedes original D16 which treated models as fully independent.**

## D17: Variant naming convention uses `<name>.<harness>.<ext>` in source

**Choice**: Harness-specific variants are identified by filename convention: `coder.claude.md` is the Claude variant of `coder.md`. The harness identifier matches the managed target name with the leading dot stripped (`.claude` → `claude`).

**Rejected**: (a) Separate directories per harness (`agents/claude/coder.md`), (b) Frontmatter-based variant declaration, (c) mars.toml-level variant mapping.

**Reasoning**: Filename convention is the simplest mechanism that works with the existing discovery pipeline. It requires no config, no parsing, and no new directory structure. Discovery already scans `agents/*.md` — extending the pattern to recognize `<name>.<harness>.md` is a minimal change. Separate directories would break the flat `agents/` convention and complicate lock paths. Frontmatter-based declaration would require parsing every file during discovery. Config-level mapping would be verbose for the common case.

## D18: Managed targets configured via `settings.targets` list (REVISED)

**Choice**: Simple `targets = [".claude", ".cursor"]` list in `[settings]`. Backwards-compatible with existing `links` syntax.

**Rejected**: (a) `[[settings.targets]]` array-of-tables with per-target configuration (original design). (b) Breaking the `links` syntax.

**Reasoning**: Per-target configuration (content strategy, per-target kind filtering) is deferred — the initial implementation copies all content to all targets. A simple list is sufficient and simpler to configure. When per-target configuration is needed, `[[settings.targets]]` with `name`/`include_kinds`/`exclude_kinds` fields can be introduced as an alternative syntax. The existing `links = [".claude"]` syntax is supported as equivalent to `targets = [".agents", ".claude"]` (the old behavior always had `.agents/` as managed root plus linked targets). **Supersedes original D18.**

## D19: Content sync is generic; capability cross-compilation dispatches via AdapterKind enum

**Choice**: Content sync uses a shared function (variant resolution by harness ID). Capability cross-compilation dispatches through a closed `AdapterKind` enum.

**Rejected**: (a) Trait-based `Box<dyn RuntimeAdapter>` with both sync_content and materialize methods, (b) Keeping sync_content adapter-specific.

**Reasoning**: Implementability reviewer flagged tension between `Box<dyn RuntimeAdapter>` and the "single binary, no dynamic loading" constraint from D1. Content sync is actually the same algorithm for all adapters — the only varying input is the harness ID for variant selection. Making it adapter-specific would duplicate the same code across adapters. Capability cross-compilation genuinely differs per adapter (different config formats, different native features), so that's where dispatch happens.

## D20: Variant parsing uses last-segment matching against known harness IDs

**Choice**: Extract the harness ID by matching the last dot-separated stem segment against the set of known managed target harness IDs from config. Item names may contain dots; harness IDs may not.

**Rejected**: (a) Always splitting on the second-to-last dot (ambiguous for dotted names), (b) Using a different delimiter like `__` or `@`.

**Reasoning**: Both reviewers flagged the `<name>.<harness>.<ext>` convention as ambiguous for names containing dots. The fix is to make variant detection depend on config: a file is only a variant if its last stem segment matches a configured harness ID. This means `review.v2.claude.md` is a variant of `review.v2` for `claude` *only if* `claude` is a configured target. Without configured targets, no files are variants. Requiring harness IDs to be dot-free (enforced at config validation) makes the split unambiguous. Alternative delimiters (`__`, `@`) would break the natural `.claude.md` naming that users expect.

## D21: Lock written regardless of target sync outcome (non-strict mode)

**Choice**: In non-strict mode, the lock is always written after successful content apply to `.mars/content/`, even if managed target sync fails. Target sync status is reported separately in `SyncReport.target_outcomes`.

**Rejected**: (a) Not writing lock on target sync failure (original design), (b) Always making target sync failure fatal.

**Reasoning**: Correctness reviewer flagged that "lock not written + non-fatal target sync" is contradictory — if the command succeeds but the lock isn't advanced, the next run doesn't have a committed baseline. The lock should reflect what's in `.mars/content/` (the source of truth), not what's in managed targets. Targets are derived state that can always be re-synced. Writing the lock ensures the next `mars sync` operates from the correct baseline and only re-runs target sync (which is idempotent).

## D22: Variant content goes through the same rewrite pipeline as base items

**Choice**: `VariantSource` includes a `rewritten_content` field, and variant content goes through the same frontmatter/rename rewrite pipeline as the base item during target building.

**Rejected**: Skipping rewrites for variant content (only using raw source files).

**Reasoning**: Correctness reviewer flagged that `sync_target_content()` would read raw variant files, bypassing the rewrite pipeline that transforms base items (frontmatter transforms, skill renames per `rewrite.rs`). This would cause managed targets to get unrewritten variant content while `.mars/content/` gets the rewritten default — breaking renamed skill references. Variants must go through the same transforms to maintain consistency.

## D23: Lock version conditional on content — v1 when no variants, v2 when variants present

**Choice**: Mars writes v1 lock format when no items have variants, v2 when any item has variants. The loader checks the version field before deserializing and rejects unknown versions with a clear error.

**Rejected**: (a) Always writing v2 once the mars version supports it, (b) Silently ignoring unknown fields.

**Reasoning**: Correctness reviewer flagged that the v2 lock schema (nested `variants` table) would be silently accepted and variant data dropped by older mars versions that only know v1. Conditional version writing means projects that don't use variants stay on v1 (compatible with older mars). Projects that adopt variants get v2, and older mars fails fast with a clear upgrade message instead of silently dropping data.

## D24: "Soul" renamed to "Rule" — operational instructions, not identity

**Choice**: Rename `ItemKind::Soul` to `ItemKind::Rule`. Directory `soul/` becomes `rules/`. Three categories: shared rules (all targets), per-harness rules (rules/claude/), per-model rules (rules/opus.md).

**Rejected**: (a) Keeping "soul" naming. (b) "Prompt" as the name. (c) Flat rules/ without subcategories.

**Reasoning**: "Soul" implies identity and personality — OpenClaw's Soul.md is about *who* the AI is. What we're building is operational instructions: "you're on opus, think deeply", "you're on codex, go straight to code", "always use ruff for linting." These are behavioral *rules*, not identity. "Rule" matches Claude Code's existing `.claude/rules/` convention, making materialization natural — mars just copies rules into the directory Claude Code already reads. "Prompt" was rejected because it's too generic and conflicts with the concept of user prompts. The three-category structure (shared/per-harness/per-model) emerged from the realization that per-model rules aren't harness-specific — opus behaves the same way regardless of whether it's running under Claude Code or Codex.

## D25: .mars/ as canonical content store, all targets derived

**Choice**: `.mars/content/` is the canonical resolved content store. ALL target directories (`.agents/`, `.claude/`, `.codex/`, `.cursor/`) are managed outputs materialized via copy from `.mars/content/`. No target is special.

**Rejected**: (a) `.agents/` as the managed root with other targets derived from it (original architecture). (b) Each target resolving independently from sources.

**Reasoning**: The original design had `.agents/` as both source of truth and a target that harnesses read directly. This creates an unsolvable problem: if a harness (e.g., Codex) reads `.agents/` directly, mars can't control what content that harness sees. You can't have content that's "shared between Claude and Cursor but not Codex" when `.agents/` is the universal source. `.mars/content/` as a neutral canonical store, with ALL targets (including `.agents/`) as managed outputs, solves this cleanly. Per-target content control becomes natural: each target gets exactly the content its adapter resolves. `.mars/` is entirely gitignored (derived state). `mars.toml` and `mars.lock` stay at project root and are committed.

## D26: Copy from .mars/content/ to targets, not symlinks

**Choice**: All content is COPIED from `.mars/content/` to managed targets. No symlinks between canonical store and targets.

**Rejected**: (a) Symlinks from targets to `.mars/content/`. (b) Hardlinks. (c) Reflinks.

**Reasoning**: Four concrete problems with symlinks for target materialization: (1) **Windows**: symlinks require admin or developer mode — copy works everywhere. (2) **Git**: symlinks are platform-dependent and require `core.symlinks` config — tools interacting with target directories may not handle symlinks correctly. (3) **Atomicity**: copy + tmp+rename is the simplest crash-safe write pattern — symlink atomicity requires remove+create (race window). (4) **Variant content**: when a target gets a harness-specific variant instead of the default, the content is *different* from `.mars/content/` — symlinks can only point to one source. Copy is the only mechanism that supports per-target content customization. Performance cost is negligible — we're copying markdown files and TOML configs, not gigabytes.

## D27: Harness-specific schema extensions via [item.harness] sections

**Choice**: Package schema supports harness-specific override sections using `[<item_type>.<harness_id>]` convention. Adapters read universal section + their own harness section. Unknown harness sections are ignored.

**Rejected**: (a) Separate harness-specific files alongside universal definitions. (b) Frontmatter-based harness overrides. (c) No harness-specific extensions (adapters figure it out).

**Reasoning**: Each harness has unique capabilities that go beyond format translation — Claude Code has hooks and native MCP, Cursor has .mdc frontmatter patterns, Codex has its own sandbox model. A package author needs to express "this MCP server uses stdio transport on Claude but SSE on Cursor" without maintaining separate files. Inline `[server.claude]` / `[server.cursor]` sections are the most natural TOML pattern, keep everything about one item in one file, and are forward-compatible (adding a new harness section doesn't break existing adapters that ignore it). Separate files would complicate the package structure and break the 1-file-per-item convention for capability items.

## D28: Adapters are cross-compilers, not format translators

**Choice**: Runtime adapters map universal package features to harness-native equivalents, emit diagnostics for unsupported features, and honor harness-specific schema extensions. The mental model is a "cross-compiler" targeting different harness runtimes.

**Rejected**: (a) Simple format translators (just convert TOML → settings.json). (b) No adapters (dump universal format and let harnesses figure it out).

**Reasoning**: Each harness has genuinely different capabilities: Claude Code has hooks in settings.json and native MCP transport; Cursor has .mdc rule files with frontmatter file patterns; Codex has its own sandbox model and AGENTS.md conventions. A format translator can't handle this — it's not just "same data, different syntax." The adapter needs to understand what the harness can and can't do, use the harness-specific schema extensions when available, and emit clear diagnostics when a feature has no equivalent ("hooks have no Cursor equivalent — skipping"). This is cross-compilation: same source semantics, different target capabilities. The adapter is the authoritative source of "what does this harness support."

## D29: .mars/ is derived state — user gitignores it, mars doesn't auto-edit

**Choice**: `.mars/` contains only derived state. Users should add `.mars/` to `.gitignore` themselves. Mars does NOT auto-edit `.gitignore`. `mars doctor` warns if `.mars/` is not gitignored.

**Rejected**: (a) Mars auto-adding `.mars/` to `.gitignore` on init. (b) Committing `.mars/` content. (c) Putting mars.lock inside `.mars/`.

**Reasoning**: npm doesn't auto-gitignore `node_modules/`, cargo doesn't auto-gitignore `target/`. Auto-editing `.gitignore` is presumptuous — users manage their own ignore files. `mars doctor` provides a diagnostic warning as a safety net. `.mars/` is fully derived from `mars.toml` + `mars.lock` + source repos. `mars.toml` and `mars.lock` stay at project root and are committed.

## D30: settings.targets controls which targets exist; .agents/ is default when targets is omitted (unchanged)

**Choice**: When `settings.targets` is not specified in mars.toml, `.agents/` is the sole managed target (backwards compatibility). When `targets` is specified, only the listed directories are managed. To include `.agents/`, list it explicitly.

**Rejected**: (a) Always creating `.agents/` regardless of config. (b) Requiring `targets` to be specified.

**Reasoning**: Existing projects without `targets` config must keep working — they get `.agents/` as the sole target, which matches current behavior exactly. New projects adopting multi-target can list exactly which targets they want. Making `.agents/` always present would force projects that only use `.claude/` to also have a redundant `.agents/` directory. The opt-in model is cleaner and matches the progressive disclosure principle: simple projects don't need to know about targets at all.

## D31: ModelAlias supports two modes — pinned and auto-resolve

**Choice**: `ModelAlias` has a `ModelSpec` enum with two variants: `Pinned { model: String }` for explicit model IDs, and `AutoResolve { provider, match_patterns, exclude_patterns }` for pattern-based resolution against the models cache. Distinguished by field presence in TOML — `model` field means pinned, `match` field means auto-resolve.

**Rejected**: (a) Single mode with optional fields (ambiguous semantics). (b) Separate `[models.pinned]` and `[models.auto]` config sections (verbose, unintuitive). (c) Always auto-resolve with `model` as a filter pattern (overcomplicates the simple case).

**Reasoning**: Pinned aliases are the simple, predictable case — "opus always means claude-opus-4-6." Auto-resolve aliases are the maintainable case — "opus means the newest opus model." Users need both: pinned for stability in production, auto-resolve for development where staying current matters. Making them a single struct with an enum spec keeps the config surface small while the Rust types make the distinction explicit. Both modes deserialize from the same `[models.NAME]` table, so the config is uniform.

## D32: Builtin aliases are hardcoded auto-resolve specs, overridable

**Choice**: Mars ships default auto-resolve specs for common model families (opus, sonnet, haiku, codex, gpt, gemini). These are the lowest-priority layer — any package or consumer definition overrides them. When the cache is empty, builtins fall back to hardcoded model IDs.

**Rejected**: (a) No builtins — require every project to define all aliases. (b) Builtins from a shipped config file (adds a file to manage, versioning complexity). (c) Builtins as highest priority (consumer can't override).

**Reasoning**: A fresh project should be able to use `--model opus` without any config. Builtins provide this zero-config experience. Making them lowest priority ensures packages and consumers always win — builtins are sensible defaults, not opinions. The fallback IDs for empty cache prevent first-run failures when there's no network — the alias resolves to a reasonable model ID even without a cache, and the next `mars models refresh` improves the resolution.

## D33: Model config merges from dependency tree with same precedence as other config

**Choice**: Model aliases merge during `resolve_graph()` with precedence: consumer mars.toml > dependencies (in declaration order) > builtins > fallback IDs. When two deps at the same level define the same alias, first declared wins with a diagnostic warning.

**Rejected**: (a) Consumer-only model config (packages can't distribute defaults). (b) Separate merge logic from other config (inconsistent mental model). (c) Last-declared wins for same-level conflicts (less predictable — the dependency you listed first should have higher priority).

**Reasoning**: Model aliases follow the exact same merge pattern as permissions, tools, MCP, and rules — this is the design's central config merge model. Making models a special case would be a false distinction. First-declared-wins for same-level deps matches TOML declaration order, which is the only visible ordering signal the consumer has. The merge happens in `resolve_graph()` (not `load_config()`) because dependency manifests aren't available until resolution.

## D34: Auto-resolve uses simple glob matching — * only

**Choice**: Glob patterns use `*` as the only wildcard (matches any character sequence). Everything else is literal. Match patterns are AND (all must hit); exclude patterns are OR (any hit excludes).

**Rejected**: (a) Full glob with `?`, character classes, etc. (b) Regex. (c) Substring matching without wildcards.

**Reasoning**: Model IDs are structured strings like `claude-opus-4-6-20260401`. The only pattern users need is "contains this substring" (`*opus*`) or "starts with this" (`gpt-5.*`). Full glob or regex adds complexity without value — nobody needs `claude-opus-4-[56]` patterns for model selection. AND semantics for match patterns lets users intersect filters naturally (`['gemini', 'pro']` = models matching both). OR semantics for excludes lets users list multiple exclusion patterns (`['*-mini', '*-nano']`). This matches how users think about model filtering.

## D35: B4 must complete before B1 — model aliases inform rule discovery

**Choice**: Phase ordering changed: B4 (model catalog) runs before B1 (generalized item kinds + rules). Rule discovery depends on the merged model alias set to classify per-model vs. shared rules.

**Rejected**: (a) Keeping B4 independent/parallel with B1 (original ordering). (b) Hardcoding known model names for rule classification instead of using config.

**Reasoning**: `rules/opus.md` is a per-model rule only if `opus` is a known model alias. Without the merged alias set from B4, rule discovery can't distinguish `rules/opus.md` (per-model) from `rules/general.md` (shared). The dependency is natural in the pipeline: `resolve_graph()` merges model config, `build_target()` runs discovery with the merged aliases — the pipeline ordering already satisfies this. Hardcoding model names would break the extensibility model — packages can define arbitrary aliases.

## D36: Manifest exports [models] alongside [dependencies]

**Choice**: `Manifest` struct extended with `models: IndexMap<String, ModelAlias>`. `load_manifest()` extracts `[models]` from package mars.toml. Packages distribute model aliases with operational descriptions.

**Rejected**: (a) Models only in consumer config (packages can't share operational knowledge). (b) Separate model manifest file.

**Reasoning**: The real value of package-distributed model aliases is the descriptions — "opus: strong orchestrator, creative but can hallucinate, best for architecture." This operational knowledge belongs with the package that uses those models in its agent profiles. Consumer overrides any field, so packages provide defaults that the consumer can customize. Extending the existing `Manifest` struct keeps the package format unified.
