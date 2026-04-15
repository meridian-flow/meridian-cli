# Decision Log

## D1: Provider→harness preference table hardcoded in mars

**Decision:** The provider-to-harness preference table is hardcoded as a Rust constant in mars, with an optional mars.toml `[harness.preferences]` override.

**Alternatives rejected:**
- **Fully configurable (mars.toml only):** Would require every project to configure the table, or mars to ship a default config file. The table changes rarely (new harnesses appear maybe yearly), and hardcoding keeps it inspectable with no config files.
- **Live in meridian instead of mars:** Would make `mars models list` unable to show harness info standalone. Mars needs to resolve harnesses independently since it's the single source of truth for model aliases.

**Constraints:** Mars must work standalone (without meridian) for the `mars models list` and `mars models resolve` commands to be useful diagnostics tools.

## D2: No caching for harness detection

**Decision:** `which` binary checks run on every `resolve` / `list` invocation with no caching.

**Alternatives rejected:**
- **Cache on first call, invalidate on session boundary:** Adds complexity (where to store? how to invalidate?) for ~8ms savings. The subprocess overhead of calling mars is already 50-100ms.
- **Cache in `.mars/harness-cache.json`:** Creates staleness bugs — user installs a new harness and mars doesn't see it until cache expires.

**Constraints:** Detection must be fast enough for per-spawn use. 4 `which` checks at ~2ms each = ~8ms total, well within budget.

## D3: Pinned aliases without provider use model ID inference

**Decision:** When a pinned alias has `model = "claude-opus-4-6"` but no `harness` and no `provider`, mars infers the provider from model ID prefixes (`claude-` → anthropic, `gpt-` → openai, etc.).

**Alternatives rejected:**
- **Require provider for all aliases without harness:** Would break existing pinned aliases in mars.toml that only specify `model`. Users shouldn't need to add `provider` when the model ID makes it obvious.
- **Fall through to meridian's routing:** Would mean `mars models list` can't show harness info for these aliases, making the standalone mars experience worse.

**Constraint:** The inference is best-effort. Unknown model ID prefixes get `harness: null`, and meridian's routing handles them.

## D4: `mars models list` hides unavailable aliases by default

**Decision:** The default `mars models list` only shows aliases where both model resolution AND harness detection succeeded. `--all` shows everything.

**Alternatives rejected:**
- **Always show all aliases:** Confusing — users see aliases they can't use with no explanation. The `--all` flag exists for debugging.
- **Show unavailable aliases with a warning suffix:** Clutters the default output. The table format already shows harness, so `—` in the harness column (with `--all`) is sufficient.

## D5: `harness_source` field in resolve output

**Decision:** The resolve JSON includes `harness_source: "explicit" | "auto-detected" | "unavailable"` so consumers can distinguish how the harness was chosen.

**Rationale:** Debugging harness routing is hard without knowing whether the harness came from the alias config or auto-detection. This field costs nothing to include and makes `mars models resolve` a complete diagnostic tool.

## D6: Add `which` crate dependency

**Decision:** Use the `which` crate for cross-platform binary detection instead of raw `std::process::Command::new("which")`.

**Rationale:** `which` handles Windows (`where`), PATH parsing, and edge cases (symlinks, permissions). Rolling our own is more code for worse correctness.

## D7: No changes to meridian's model_policy.py

**Decision:** Meridian's existing harness routing (`DEFAULT_HARNESS_PATTERNS`, `route_model_with_patterns`) is unchanged.

**Rationale:** Meridian already handles the case where mars doesn't provide a harness — the `AliasEntry.harness` property falls back to pattern-based routing. Mars adding auto-detection improves the mars-side experience but doesn't change meridian's resolution path. Keeping meridian's routing as a fallback also means meridian still works if mars is unavailable or returns partial data.

## D8: Defer `mars harness list` command

**Decision:** Defer the `mars harness list` diagnostic command to a follow-up. The `mars models resolve` output already includes `harness_candidates` which covers the main debugging need.

**Rationale:** Reduces initial implementation scope. The resolve command's `harness_candidates` field + `harness_source` enum already tell users why their alias can't find a harness. A dedicated command can be added later if there's demand.

## D9: Drop HarnessConfig / [harness.preferences] from v1

**Decision:** No mars.toml section for overriding provider-to-harness preferences in v1. The hardcoded preference table is sufficient.

**Alternatives rejected:**
- **`[harness.preferences]` in mars.toml:** Premature — users who need a specific harness can already use the explicit `harness` field on individual aliases. A global preference override adds config surface for a problem nobody has yet.

**Rationale (from review):** The explicit `harness` field on aliases already covers the "I want a specific harness" use case. Global preference overrides would only matter when a user wants a non-default harness for ALL models from a provider — a rare enough scenario to not justify the config complexity.

## D10: Add `provider: Option<String>` to Pinned aliases

**Decision:** The `ModelSpec::Pinned` variant gains an optional `provider` field, used for harness routing when `harness` is omitted.

**Alternatives rejected:**
- **Rely solely on `infer_provider_from_model_id()` prefix matching:** Not reliable enough for all model IDs. Custom or future model IDs may not follow known prefix patterns.
- **Require provider for all harnessless aliases:** Would break existing pinned aliases that only specify `model`.

**Resolution order for pinned alias provider:** explicit `provider` field → `infer_provider_from_model_id()` → `None` (meridian routing fallback).

## D11: Validate explicit harness installation

**Decision:** When an alias has an explicit `harness` field, mars validates the binary is installed and reports `harness_source: "unavailable"` if not.

**Alternatives rejected:**
- **Trust explicit harness unconditionally (v1 design):** Confusing — `mars models list` shows a harness that can't actually run, giving users false confidence.
- **Error and refuse to show the alias:** Too strict — the alias is valid configuration, the harness is just not installed on this machine.

**Approach:** Report the alias with its explicit harness but flag it as unavailable. `mars models list` (default) hides it; `--all` shows it. `resolve --json` includes it with the error.

## D12: Keep null-harness aliases in meridian (don't skip)

**Decision:** Meridian does NOT skip aliases where mars reports `harness: null`. They flow through to meridian's own `model_policy.py` routing as a fallback.

**Alternatives rejected:**
- **Skip null-harness aliases (v1 design):** Would break `meridian spawn -m opus` when mars can't detect a harness. The alias is valid — it resolved to a model ID — the harness just couldn't be auto-detected from the mars side.

**Rationale (from review):** Mars harness detection and meridian's harness routing are independent systems. Mars auto-detection is an improvement to the mars standalone experience, not a gate for meridian. Meridian's routing handles edge cases (direct API harness, environment differences) that mars can't detect.

## D13: Encapsulate harness detection inside resolve_all

**Decision:** `resolve_all` signature stays at 2 params (`aliases`, `cache`). Harness detection is called internally, not passed as a parameter.

**Alternatives rejected:**
- **Pass `installed_harnesses` and `harness_preferences` as params (v1 design):** Leaks implementation details into the public API. Callers shouldn't need to know about harness detection internals.

**Approach:** `resolve_all` calls `detect_installed_harnesses()` once internally and uses the result for all aliases. This keeps the API surface simple while allowing the implementation to change (e.g., adding caching later) without breaking callers.

## D14: HarnessSource as enum, not string

**Decision:** Use a Rust enum `HarnessSource { Explicit, AutoDetected, Unavailable }` instead of string literals.

**Rationale:** Type safety. Prevents typos in string comparisons and gives exhaustive match checking. Serializes to snake_case strings in JSON for consumer compatibility.

## D15: cfg(not(test)) workaround for Phase 3→4 boundary

**Decision:** Phase 3 coder added `#[cfg(not(test))]` on `pub mod cli;` in lib.rs so `cargo test --lib` could pass while cli/models.rs was broken. Removed after Phase 4 fixed cli/models.rs.

**Rationale:** This was a reasonable workaround for the intentional Phase 3→4 boundary break. The gate was temporary and removed in the same session.

## D16: Provider casing inconsistency deferred

**Decision:** `infer_provider_from_model_id` returns lowercase ("anthropic"), while `normalize_provider` in the cache returns title-case ("Anthropic"). This inconsistency is accepted because `resolve_harness_for_provider` lowercases internally, so routing works correctly regardless.

**Alternatives considered:**
- Normalize all provider strings to lowercase at schema level. Would require changing normalize_provider and potentially breaking consumers expecting title-case.
- Add a normalize step in resolve_model_and_provider. Unnecessary since the routing layer already handles it.

**Constraint:** The casing difference is cosmetic in the `ResolvedAlias.provider` field — the functional routing works correctly due to `to_lowercase()` in harness.rs.

## D17: Empty string harness/provider edge case deferred

**Decision:** `harness = ""` in TOML deserializes as `Some("")` rather than `None`. Accepted as a non-blocking edge case — users don't write empty harness strings in practice.

**Raised by:** gpt-5.2 Phase 1 review. Could be addressed in a follow-up with a custom deserializer that normalizes empty strings to None.
