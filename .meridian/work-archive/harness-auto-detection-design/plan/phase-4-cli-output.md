# Phase 4: CLI Output — models list + resolve Commands

## Scope

Update `mars models list` and `mars models resolve` to consume `ResolvedAlias` instead of `IndexMap<String, String>`. Add `--all` flag to `list`. Update JSON output format to include provider, harness_source, and harness_candidates. Update table output to show auto-detected harnesses and hide unavailable aliases by default.

## Files to Modify

All changes are in **`/home/jimyao/gitrepos/mars-agents/src/cli/models.rs`**:

### `ModelsCommand` enum (line 18)

1. Add `--all` flag to `List` variant:
   ```rust
   #[derive(Debug, Subcommand)]
   pub enum ModelsCommand {
       Refresh,
       List(ListArgs),
       Resolve(ResolveAliasArgs),
       Alias(AddAliasArgs),
   }

   #[derive(Debug, Parser)]
   pub struct ListArgs {
       /// Show all aliases including those without an available harness.
       #[arg(long)]
       all: bool,
   }
   ```

2. Update the `run` dispatch to pass `ListArgs`:
   ```rust
   ModelsCommand::List(args) => run_list(args, ctx, json),
   ```

### `run_list()` function (line 90)

3. Change signature to accept `ListArgs`. Update to use `ResolvedAlias`:

   **JSON output**: Emit the richer structure. Each alias entry includes `name`, `harness`, `harness_source`, `harness_candidates`, `provider`, `mode`, `model_id` (new field name), `resolved_model` (kept for compat), `description`.

   ```rust
   fn run_list(args: &ListArgs, ctx: &MarsContext, json: bool) -> Result<i32, MarsError> {
       let mars = mars_dir(ctx);
       let cache = models::read_cache(&mars)?;
       let merged = load_merged_aliases(ctx)?;
       let resolved = models::resolve_all(&merged, &cache);

       if json {
           let entries: Vec<serde_json::Value> = resolved.values()
               .map(|r| {
                   let mode = match merged.get(&r.name).map(|a| &a.spec) {
                       Some(ModelSpec::Pinned { .. }) => "pinned",
                       Some(ModelSpec::AutoResolve { .. }) => "auto-resolve",
                       None => "unknown",
                   };
                   let mut obj = serde_json::json!({
                       "name": r.name,
                       "harness": r.harness,
                       "harness_source": r.harness_source,
                       "harness_candidates": r.harness_candidates,
                       "provider": r.provider,
                       "mode": mode,
                       "model_id": r.model_id,
                       "resolved_model": r.model_id, // compat
                       "description": r.description,
                   });
                   if r.harness_source == HarnessSource::Unavailable {
                       if let Some(h) = &r.harness {
                           obj["error"] = serde_json::json!(
                               format!("Harness '{}' is not installed", h)
                           );
                       } else {
                           obj["error"] = serde_json::json!(
                               format!("No installed harness for provider '{}'. Install one of: {}",
                                   r.provider, r.harness_candidates.join(", "))
                           );
                       }
                   }
                   obj
               })
               .collect();
           // ... print JSON
       }
   }
   ```

   **Table output**: Default hides unavailable aliases. `--all` shows them with `—` in harness column and install hint in description:

   ```rust
   // Table output
   for r in resolved.values() {
       // Skip unavailable unless --all
       if !args.all && r.harness_source == HarnessSource::Unavailable {
           continue;
       }
       let harness_display = r.harness.as_deref().unwrap_or("—");
       let mode = match merged.get(&r.name).map(|a| &a.spec) {
           Some(ModelSpec::Pinned { .. }) => "pinned",
           Some(ModelSpec::AutoResolve { .. }) => "auto-resolve",
           None => "unknown",
       };
       let desc = if r.harness_source == HarnessSource::Unavailable {
           format!("(install: {})", r.harness_candidates.join(", "))
       } else {
           r.description.clone().unwrap_or_default()
       };
       println!("{:<12} {:<10} {:<14} {:<30} {}", r.name, harness_display, mode, r.model_id, desc);
   }
   ```

### `run_resolve()` function (line 156)

4. Update to use `ResolvedAlias`:

   **JSON output**: Emit `model_id` alongside `resolved_model`, include `provider`, `harness_source`, `harness_candidates`. Add `error` field when unavailable:

   ```rust
   let resolved_map = models::resolve_all(&merged, &cache);
   let resolved_entry = resolved_map.get(&args.name);

   if json {
       if let Some(r) = resolved_entry {
           let mut out = serde_json::json!({
               "name": r.name,
               "source": source,
               "provider": r.provider,
               "harness": r.harness,
               "harness_source": r.harness_source,
               "harness_candidates": r.harness_candidates,
               "model_id": r.model_id,
               "resolved_model": r.model_id,
               "spec": format_spec(&alias.spec),
               "description": r.description,
           });
           // Add error for unavailable
           if r.harness_source == HarnessSource::Unavailable { ... }
           println!("{}", serde_json::to_string_pretty(&out).unwrap());
       } else {
           // Model didn't resolve (auto-resolve with no cache match)
           // ... existing error path
       }
   }
   ```

   **Text output**: Show harness source info:
   ```
   Harness:  claude (auto-detected)
   Provider: anthropic
   ```

### Imports

5. Add necessary imports at top of `models.rs`:
   ```rust
   use crate::models::{self, ModelSpec, HarnessSource};
   ```

## Dependencies

- **Requires:** Phase 3 (ResolvedAlias type and updated resolve_all return type).
- **Independent of:** Phase 5 (meridian changes).

## Interface Contract

The JSON output for `mars models list --json` must include these fields per alias:
- `name: string`
- `model_id: string` (new)
- `resolved_model: string` (compat, same value as model_id)
- `harness: string | null`
- `harness_source: "explicit" | "auto_detected" | "unavailable"`
- `harness_candidates: string[]`
- `provider: string`
- `mode: "pinned" | "auto-resolve"`
- `description: string | null`
- `error: string` (only when harness_source is "unavailable")

The JSON output for `mars models resolve <alias> --json` must include these same fields plus `source` and `spec`.

## Verification Criteria

- [ ] `cargo build` succeeds — all compile errors from Phase 3's return type change resolved
- [ ] `cargo test` passes
- [ ] `mars models list` shows only available aliases (no unavailable)
- [ ] `mars models list --all` shows all aliases with `—` for unavailable harnesses
- [ ] `mars models list --json` includes `model_id`, `harness_source`, `harness_candidates`, `provider`
- [ ] `mars models resolve opus --json` includes all new fields
- [ ] `mars models resolve opus` text output shows harness source
- [ ] `cargo clippy` clean
