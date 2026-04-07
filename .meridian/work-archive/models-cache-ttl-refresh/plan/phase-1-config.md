# Phase 1: Config — `models_cache_ttl_hours`

**Repo:** mars-agents (`../mars-agents/`)
**Depends on:** nothing
**Est. size:** ~20 LoC + 1-2 tests

## Goal

Add the `models_cache_ttl_hours: u32` field to `mars.toml` `[settings]`
with a custom default of 24 hours.

## Files

- `src/config/mod.rs` — add field to `Settings`, add serde default
  function.
- Existing `config` unit tests — add a round-trip test covering the new
  field (both omitted and explicitly set).

## Implementation

1. Add to `Settings`:

    ```rust
    #[serde(default = "default_models_cache_ttl_hours")]
    pub models_cache_ttl_hours: u32,
    ```

2. Add the default helper:

    ```rust
    fn default_models_cache_ttl_hours() -> u32 {
        24
    }
    ```

3. **Switch `Settings` from `#[derive(Default)]` to a manual `Default`
   impl.** This is mandatory, not optional — see decisions.md D7 and
   `design/configuration.md`. The manual impl must set
   `models_cache_ttl_hours: 24` so that any path constructing
   `Settings::default()` (test fixtures, missing `[settings]` table in
   TOML) yields the same default as a serde-deserialized config with
   only that field omitted. Example:

   ```rust
   impl Default for Settings {
       fn default() -> Self {
           Self {
               managed_root: None,
               targets: None,
               model_visibility: ModelVisibility::default(),
               models_cache_ttl_hours: 24,
           }
       }
   }
   ```

   The serde field-level `#[serde(default = "default_models_cache_ttl_hours")]`
   stays for the case where the user provides `[settings]` but omits the
   field. Both paths must yield 24.

4. Update any test fixtures that construct `Settings { ... }` literally to
   include the new field (the existing `Settings::default()` based ones
   are covered by the manual default impl).

## Verification

- `cargo fmt && cargo clippy --all-targets && cargo test --package
  mars-agents --lib config::`
- New test: parse a `mars.toml` without the field → expect 24. Parse with
  `models_cache_ttl_hours = 0` → expect 0. Parse with `= 48` → expect 48.
- New test: round-trip `Settings` through TOML and back, verifying the
  field is preserved (and is omitted from serialized output when it
  equals the default, if that matches existing serialization conventions;
  otherwise serialized explicitly — pick whichever the existing fields do).

## Out of Scope

Nothing in this phase reads or uses the field. Phase 2 is the first
consumer.
