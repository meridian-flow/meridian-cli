# Model Alias Schema Changes

## ModelAlias Type

`harness` becomes `Option<String>`:

```rust
pub struct ModelAlias {
    pub harness: Option<String>,       // was: String
    pub description: Option<String>,
    pub spec: ModelSpec,
}
```

## ModelSpec: Add `provider` to Pinned Variant

Pinned aliases gain an optional `provider` field so harness auto-detection works without relying solely on model ID prefix inference:

```rust
pub enum ModelSpec {
    Pinned {
        model: String,
        provider: Option<String>,      // NEW — optional, enables harness routing
    },
    AutoResolve {
        provider: String,
        match_patterns: Vec<String>,
        exclude_patterns: Vec<String>,
    },
}
```

Provider resolution for pinned aliases:
1. Use explicit `provider` if set
2. Fall back to `infer_provider_from_model_id()` (best-effort prefix matching)
3. If neither works, harness is `None` — meridian's routing handles it

## RawModelAlias Deserialization

```rust
struct RawModelAlias {
    harness: Option<String>,           // was: String (required)
    description: Option<String>,
    model: Option<String>,
    provider: Option<String>,          // now used by BOTH pinned and auto-resolve
    match_patterns: Option<Vec<String>>,
    exclude: Option<Vec<String>>,
}
```

The deserialization logic changes:
- If `model` is present: `Pinned { model, provider }` — provider is optional
- If `match` is present: `AutoResolve { provider, match_patterns, exclude }` — provider still required
- `provider` is now valid for both modes (was only for AutoResolve)

## mars.toml Backwards Compatibility

All existing configs work unchanged:

```toml
# Still works — harness forced, pinned
[models.fast]
harness = "claude"
model = "claude-haiku-4-5"

# Still works — harness forced, auto-resolve
[models.opus]
harness = "claude"
provider = "Anthropic"
match = ["*opus*"]

# NEW: no harness, auto-detected from provider
[models.opus]
provider = "Anthropic"
match = ["*opus*"]

# NEW: pinned with explicit provider for routing
[models.fast]
model = "claude-haiku-4-5"
provider = "anthropic"

# NEW: pinned, provider inferred from model ID prefix
[models.fast]
model = "claude-haiku-4-5"
```

## Builtin Aliases

All builtin aliases drop the harness field:

```rust
pub fn builtin_aliases() -> IndexMap<String, ModelAlias> {
    let mut m = IndexMap::new();
    let add = |m: &mut IndexMap<String, ModelAlias>,
               name: &str,
               provider: &str,
               match_patterns: &[&str],
               exclude: &[&str]| {
        m.insert(
            name.to_string(),
            ModelAlias {
                harness: None,  // auto-detected at resolution time
                description: None,
                spec: ModelSpec::AutoResolve {
                    provider: provider.to_string(),
                    match_patterns: match_patterns.iter().map(|s| s.to_string()).collect(),
                    exclude_patterns: exclude.iter().map(|s| s.to_string()).collect(),
                },
            },
        );
    };
    add(&mut m, "opus", "anthropic", &["*opus*"], &[]);
    add(&mut m, "sonnet", "anthropic", &["*sonnet*"], &[]);
    add(&mut m, "haiku", "anthropic", &["*haiku*"], &[]);
    add(&mut m, "codex", "openai", &["*codex*"], &["*-mini", "*-spark", "*-max"]);
    add(&mut m, "gpt", "openai", &["gpt-5*"], &["*codex*", "*-mini", "*-nano", "*-chat", "*-turbo"]);
    add(&mut m, "gemini", "google", &["gemini*", "*pro*"], &["*-customtools"]);
    m
}
```

## Provider Inference from Model ID (Best-Effort)

Used only when a pinned alias has no explicit `provider`:

```rust
/// Best-effort provider inference from model ID prefixes.
/// Returns None for unrecognized patterns — callers must handle the fallback.
fn infer_provider_from_model_id(model_id: &str) -> Option<&'static str> {
    let id = model_id.to_lowercase();
    if id.starts_with("claude-") { return Some("anthropic"); }
    if id.starts_with("gpt-") || id.starts_with("o1") || id.starts_with("o3")
       || id.starts_with("o4") || id.starts_with("codex-") { return Some("openai"); }
    if id.starts_with("gemini") { return Some("google"); }
    if id.starts_with("llama") { return Some("meta"); }
    if id.starts_with("mistral") || id.starts_with("codestral") { return Some("mistral"); }
    if id.starts_with("deepseek") { return Some("deepseek"); }
    if id.starts_with("command") { return Some("cohere"); }
    None
}
```

This is explicitly best-effort and documented as such. Users with non-standard model IDs should use `provider = "..."` in their mars.toml.

## Serialization

When serializing `ModelAlias` to JSON, `harness` is included only when explicitly set:

```rust
if let Some(h) = &self.harness {
    map.serialize_entry("harness", h)?;
}
```

For `Pinned` spec, `provider` is included only when set:
```rust
ModelSpec::Pinned { model, provider } => {
    map.serialize_entry("model", model)?;
    if let Some(p) = provider {
        map.serialize_entry("provider", p)?;
    }
}
```

## Test Updates Required

The following existing tests and helpers need updating for `harness: Option<String>`:

1. `pinned_alias()` helper (line ~785) — change `harness` param to `Option<&str>`
2. All serde roundtrip tests — add cases for missing harness
3. All `merge_model_config` tests — update `pinned_alias` calls
4. Add new tests:
   - Pinned alias without harness, with provider
   - Pinned alias without harness, without provider (inference)
   - Auto-resolve alias without harness
   - Explicit harness validation (installed/not installed)

## Impact on merge_model_config

No change to merge logic. The merge algorithm compares by alias name, not by harness. When two aliases have the same name, the higher-precedence one wins entirely.

## Impact on resolve_all

`resolve_all` gains harness detection. See [resolve-api.md](resolve-api.md) for the new return type and API.
