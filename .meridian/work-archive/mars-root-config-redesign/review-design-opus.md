# Design Review: mars.toml Root Config Migration

## Overall Assessment

This is a well-motivated refactor that aligns mars with established package manager conventions (Cargo.toml, package.json at repo root). The `MarsContext` split into `project_root` + `managed_root` is structurally clean, and the migration of config/lock to project root while keeping `.agents/` as pure output is the right call.

However, there are several design quality issues worth addressing — most notably the `INIT_MARKER` approach for detecting consumer config, which introduces a fragile heuristic that will cause real problems, and some ambiguity in the merged config model.

## Findings

### 1. The `INIT_MARKER` (`# created by mars init`) is a fragile, out-of-band signal — HIGH

**File:** `src/cli/mod.rs:43`, `src/cli/init.rs:49`

The marker comment `# created by mars init` is used to distinguish consumer configs from package-only manifests. This is the weakest part of the refactor:

- **TOML comments don't roundtrip.** If any tool (or the user) re-serializes the file with a TOML library, the comment vanishes. `ensure_consumer_config` itself serializes via `toml::to_string_pretty` and prepends the marker as raw text — but any future code path that does `load → modify → save` through the typed `Config` struct will lose it, because serde doesn't preserve comments.
- **It's invisible metadata.** A user editing `mars.toml` by hand won't know the comment is load-bearing. Deleting it changes behavior silently.
- **Two detection paths diverge.** `is_consumer_config` checks for the marker OR `[sources]`. `ensure_consumer_config` checks for the marker AND `[sources]` to decide if work is needed. The combination of OR/AND across two functions with similar names is confusing and invites bugs.

**Recommendation:** Drop the marker entirely. A consumer config is one that has `[sources]` — full stop. If you need to distinguish "initialized but no sources added yet" from "not initialized," use an empty `[sources]` table, which is what `mars init` already creates. The `[sources]` key *is* the marker, and it survives serialization. If the concern is a package-only `mars.toml` that coincidentally has an empty `[sources]`, that's a non-problem: an empty sources table means "no sources" regardless of intent.

### 2. `ensure_consumer_config` silently mutates package manifests — HIGH

**File:** `src/cli/init.rs:46-91`

When `mars init` is run in a directory that already has a `mars.toml` with only `[package]`, `ensure_consumer_config` injects `[sources]` and the init marker into the file. This has two problems:

- **Surprising mutation.** Running `mars init` in a package source repo silently rewrites the author's `mars.toml`. The author may not want consumer sections in their package manifest. The function returns `Ok(false)` (not already initialized), so the user sees "initialized" — but they may not realize their existing file was modified.
- **Lossy rewrite.** The function parses as `toml::Value`, inserts a key, re-serializes with `toml::to_string_pretty`, then prepends the marker. This rewrite will reorder keys, normalize whitespace, and strip comments from the original file. If the package author had inline comments or a specific section ordering, it's gone.

**Recommendation:** When an existing `mars.toml` has `[package]` but no `[sources]`, prompt or warn the user instead of silently upgrading. Alternatively, make `mars init` refuse to touch an existing `mars.toml` that doesn't already have consumer sections — tell the user to add `[sources]` manually if they want to use the directory as both a package and a consumer.

### 3. `detect_managed_root` fallback logic is fragile with multiple `.mars/` markers — MEDIUM

**File:** `src/cli/mod.rs:216-251`

The discovery logic when `.agents/` doesn't exist:

1. Scan all immediate children of project_root for `.mars/` subdirectories
2. If exactly one, use it
3. If multiple, prefer TOOL_DIRS entries
4. If still multiple, sort and take the first alphabetically

This alphabetical fallback (step 4) is a silent heuristic that could pick the wrong directory. If a user has `.claude/.mars` and `.cursor/.mars`, the function silently picks `.claude` (alphabetically first). The user gets no warning that ambiguity was resolved by lexicographic sort.

**Recommendation:** If multiple `.mars/` markers exist and none match TOOL_DIRS priority, return an error telling the user to specify `--root` or `mars init <target>` explicitly. Silent disambiguation by alphabet violates the project's own principle: "User intent comes from explicit flags and arguments, not heuristics."

### 4. `sync::execute` now takes two separate `Path` arguments with no type safety — MEDIUM

**File:** `src/sync/mod.rs:137-141`

The signature changed from `execute(root: &Path, request)` to `execute(project_root: &Path, managed_root: &Path, request)`. Every call site now passes two bare `&Path` values. This is error-prone — swapping the argument order compiles fine and produces subtle bugs.

**Recommendation:** Pass `&MarsContext` directly instead of two paths. The context struct already exists and encapsulates both. This eliminates the ordering ambiguity and makes the API self-documenting. The same applies to `mutate_link_config` and `execute_repair_with_collision_cleanup`.

### 5. `find_agents_root` walk-up stops at `.git` but mars.toml may be at repo root — LOW

**File:** `src/cli/mod.rs:297-307`

The walk-up loop checks `is_consumer_config` first, then checks for `.git`. This means if `mars.toml` is at the repo root (the common case), it works fine. But the comment says "never cross the current git root" — the code actually does check the git root directory itself before breaking. This is correct behavior but the comment is misleading. Consider clarifying that the boundary is *exclusive* (we check the directory with `.git`, but don't go above it).

### 6. Config `save` doesn't preserve the init marker — MEDIUM

`config::save` serializes the `Config` struct. Since `Config` has no field for the marker comment, saving will drop it. Any code path that does `load → mutate → save` (e.g., `mars add`, `mars link`, `mars remove`) will silently strip the marker from `mars.toml`. After that, `is_consumer_config` falls back to checking for `[sources]`, which works — but the marker being dropped on first mutation makes the marker pointless. This reinforces Finding #1: the marker is dead weight if it doesn't survive the normal save path.

### 7. Config unification loses the separate `Manifest` module's clarity — LOW

**File:** `src/config/mod.rs`

Merging `Manifest`, `PackageInfo`, and `DepSpec` into `config/mod.rs` alongside the consumer `Config` is reasonable for a unified `mars.toml`, but the module is getting large. The `Config` struct now has `package`, `dependencies`, `sources`, and `settings` — but `package` + `dependencies` are manifest concerns while `sources` + `settings` are consumer concerns. Consider at minimum a doc comment on `Config` clarifying which fields are manifest-only, which are consumer-only, and which can coexist.

## Verdict: **Approve with changes**

The structural direction is right — `mars.toml` and `mars.lock` at project root, `.agents/` as pure output, `MarsContext` with explicit `project_root` + `managed_root`. The `.git` boundary for root discovery is a good constraint.

**Blocking:** Finding #1 (init marker) and #2 (silent mutation of package manifests). The marker introduces a maintenance trap — it will be silently dropped by normal operations and creates confusing dual-detection logic. Replace it with `[sources]` as the sole consumer signal.

**Strongly recommended:** Finding #4 (pass `&MarsContext` instead of two paths). This is a one-time cleanup that prevents a class of argument-ordering bugs across the entire codebase.

The rest are worth addressing but non-blocking.