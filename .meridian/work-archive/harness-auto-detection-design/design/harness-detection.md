# Harness Detection

## Installed Harness Detection

Mars detects which harness CLIs are available by checking for binaries on `$PATH`.

```rust
// src/models/harness.rs (new file)

/// Known harness binaries and the binary name to check.
const HARNESS_BINARIES: &[(&str, &str)] = &[
    ("claude", "claude"),
    ("codex", "codex"),
    ("opencode", "opencode"),
    ("gemini", "gemini"),
];

/// Check which harness CLIs are installed.
/// Returns the set of harness names whose binaries are found on $PATH.
pub fn detect_installed_harnesses() -> HashSet<String> {
    HARNESS_BINARIES.iter()
        .filter(|(_, binary)| which::which(binary).is_ok())
        .map(|(name, _)| name.to_string())
        .collect()
}
```

**No caching.** Detection runs on every `resolve` call. `which` checks are ~2ms total for 4 binaries — negligible compared to the subprocess overhead of spawning an agent. Caching would introduce staleness bugs (user installs a new harness mid-session) for no measurable performance gain.

**Dependency:** Add the [`which`](https://crates.io/crates/which) crate to mars-agents. It's a small, well-maintained crate that handles cross-platform binary lookup (Windows `where`, Unix `which`).

**Error handling:** If `which` returns an unexpected error (not "not found"), log at debug level and treat as not installed. Don't crash on permission errors or broken symlinks.

## Provider-to-Harness Preference Table

Each provider has an ordered preference list of harnesses. Mars tries them in order and picks the first one that's installed.

```rust
/// Default provider → harness preference order.
/// First installed harness wins.
const PROVIDER_HARNESS_PREFERENCES: &[(&str, &[&str])] = &[
    ("anthropic", &["claude", "opencode", "gemini"]),
    ("openai",    &["codex", "opencode"]),
    ("google",    &["gemini", "opencode"]),
    ("meta",      &["opencode"]),
    ("mistral",   &["opencode"]),
    ("deepseek",  &["opencode"]),
    ("cohere",    &["opencode"]),
];
```

**Resolution algorithm:**

```rust
fn resolve_harness_for_provider(provider: &str, installed: &HashSet<String>) -> Option<String> {
    // 1. Look up preference list for this provider (case-insensitive)
    // 2. Return first harness in the list that's in `installed`
    // 3. If none installed, return None (alias is unavailable)
}
```

**No mars.toml override for v1.** The hardcoded table is sufficient. Users who need a specific harness can use the explicit `harness` field on individual aliases. A `[harness.preferences]` config section is deferred until there's demonstrated need. (See decisions.md D9.)

## Explicit Harness Validation

When an alias has `harness = "claude"` set explicitly:
- Mars **validates the harness is installed** before reporting it as resolved.
- If not installed, the alias is reported with `harness_available: false` and a message saying which binary is needed.
- This prevents the confusing case where `mars models list` shows a harness that can't actually run.

Exception: `mars models resolve --json` always includes the alias with full metadata (including the explicit harness), because consumers may need the info even if the harness isn't locally installed (e.g., for remote execution).

## When No Harness is Available

If a model alias can't resolve to any installed harness:
- `mars models list` **omits** it by default (user can't run it). `--all` includes it with `—` marker.
- `mars models resolve <alias> --json` returns the alias with `"harness": null` and an `"error"` field listing candidate harnesses.
- The JSON always includes `"harness_candidates"` — the list of harnesses that *would* work if installed.

This lets meridian distinguish "alias resolved but no harness" from "unknown alias" and give appropriate user-facing messages.
