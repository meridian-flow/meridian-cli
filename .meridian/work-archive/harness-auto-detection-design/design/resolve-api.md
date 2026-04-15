# Resolve API

## New: ResolvedAlias Type

```rust
/// How the harness was determined.
#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HarnessSource {
    Explicit,       // harness field set in config
    AutoDetected,   // derived from provider + installed binaries
    Unavailable,    // no installed harness for this provider
}

/// Fully resolved model alias — everything a consumer needs to launch.
#[derive(Debug, Clone, Serialize)]
pub struct ResolvedAlias {
    pub name: String,
    pub model_id: String,
    pub provider: String,
    pub harness: Option<String>,         // None = no installed harness available
    pub harness_source: HarnessSource,
    pub harness_candidates: Vec<String>, // harnesses that would work if installed
    pub description: Option<String>,
}
```

## resolve_all Changes

The current `resolve_all` returns `IndexMap<String, String>` (alias → model_id). Replace with:

```rust
/// Resolve all aliases to concrete model IDs + harnesses.
///
/// Harness detection is encapsulated — callers don't pass installed harnesses.
pub fn resolve_all(
    aliases: &IndexMap<String, ModelAlias>,
    cache: &ModelsCache,
) -> IndexMap<String, ResolvedAlias> {
    // Detect installed harnesses once for all aliases
    let installed = detect_installed_harnesses();

    aliases.iter().filter_map(|(name, alias)| {
        // 1. Resolve model ID and provider
        let (model_id, provider) = resolve_model_and_provider(alias, cache)?;

        // 2. Resolve harness
        let candidates = harness_candidates_for_provider(&provider);
        let (harness, harness_source) = resolve_harness(alias, &provider, &installed);

        Some((name.clone(), ResolvedAlias {
            name: name.clone(),
            model_id,
            provider,
            harness,
            harness_source,
            harness_candidates: candidates,
            description: alias.description.clone(),
        }))
    }).collect()
}

fn resolve_model_and_provider(
    alias: &ModelAlias,
    cache: &ModelsCache,
) -> Option<(String, String)> {
    match &alias.spec {
        ModelSpec::Pinned { model, provider } => {
            let p = provider.clone()
                .or_else(|| infer_provider_from_model_id(model).map(str::to_string))
                .unwrap_or_else(|| "unknown".to_string());
            Some((model.clone(), p))
        }
        ModelSpec::AutoResolve { provider, match_patterns, exclude_patterns } => {
            let id = auto_resolve(provider, match_patterns, exclude_patterns, cache)?;
            Some((id, provider.clone()))
        }
    }
}

fn resolve_harness(
    alias: &ModelAlias,
    provider: &str,
    installed: &HashSet<String>,
) -> (Option<String>, HarnessSource) {
    if let Some(h) = &alias.harness {
        // Explicit harness — validate installation
        if installed.contains(h) {
            (Some(h.clone()), HarnessSource::Explicit)
        } else {
            // Explicit but not installed — still report it, but flag unavailable
            (Some(h.clone()), HarnessSource::Unavailable)
        }
    } else {
        // Auto-detect from provider
        match resolve_harness_for_provider(provider, installed) {
            Some(h) => (Some(h), HarnessSource::AutoDetected),
            None => (None, HarnessSource::Unavailable),
        }
    }
}
```

Key change from v1: harness detection is **encapsulated inside `resolve_all`** — callers don't pass `installed_harnesses` or preference config. The function detects once and uses internally.

## `mars models list` Changes

The list command gains awareness of harness availability:

- **Default (no flags):** Only show aliases with an available harness (explicit+installed, or auto-detected).
- **`--all`:** Show all aliases including unavailable ones (marked with `—` in harness column).
- **JSON output:** Always includes all aliases; unavailable ones have `harness: null` or `harness_source: "unavailable"`.

```
$ mars models list
ALIAS        HARNESS    MODE           RESOLVED                       DESCRIPTION
opus         claude     auto-resolve   claude-opus-4-6                Best reasoning
sonnet       claude     auto-resolve   claude-sonnet-4-5              Fast + capable
gpt          codex      auto-resolve   gpt-5.3-codex                 OpenAI flagship

$ mars models list --all
ALIAS        HARNESS    MODE           RESOLVED                       DESCRIPTION
opus         claude     auto-resolve   claude-opus-4-6                Best reasoning
sonnet       claude     auto-resolve   claude-sonnet-4-5              Fast + capable
haiku        claude     auto-resolve   claude-haiku-4-5               Fast and cheap
codex        —          auto-resolve   codex-mini-latest              (install: codex)
gpt          codex      auto-resolve   gpt-5.3-codex                 OpenAI flagship
gemini       —          auto-resolve   gemini-2.5-pro                 (install: gemini, opencode)
```

## `mars models resolve <alias>` Changes

### JSON Output

```json
{
  "name": "opus",
  "source": "builtin",
  "provider": "anthropic",
  "harness": "claude",
  "harness_source": "auto_detected",
  "harness_candidates": ["claude", "opencode", "gemini"],
  "model_id": "claude-opus-4-6",
  "spec": {
    "mode": "auto-resolve",
    "provider": "anthropic",
    "match": ["*opus*"],
    "exclude": []
  },
  "description": null
}
```

When no harness is available:

```json
{
  "name": "gemini",
  "source": "builtin",
  "provider": "google",
  "harness": null,
  "harness_source": "unavailable",
  "harness_candidates": ["gemini", "opencode"],
  "model_id": "gemini-2.5-pro",
  "error": "No installed harness for provider 'google'. Install one of: gemini, opencode"
}
```

When explicit harness is set but not installed:

```json
{
  "name": "custom",
  "source": "consumer (mars.toml)",
  "provider": "anthropic",
  "harness": "claude",
  "harness_source": "unavailable",
  "harness_candidates": ["claude", "opencode", "gemini"],
  "model_id": "claude-opus-4-6",
  "error": "Harness 'claude' is not installed. Run: npm install -g @anthropic-ai/claude-code"
}
```

## `mars harness list` — Deferred

A `mars harness list` diagnostic command is useful but not blocking. Deferred to follow-up. The `mars models resolve` output already includes `harness_candidates` which covers the main debugging need.

## Performance

The resolve API adds harness detection (~8ms for 4 `which` checks) to every `mars models resolve/list` call. Detection runs once per invocation, not per alias. Since meridian already pays ~50-100ms subprocess overhead to call mars, this is negligible.
