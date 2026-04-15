# Harness Auto-Detection and Unified Model Resolution

## Problem

Mars currently requires a hardcoded `harness` field on every model alias. This creates three problems:

1. **Wrong harness for the user's setup.** Builtin aliases hardcode `harness = "claude"` for Anthropic models, but a user who only has opencode installed can't use them.
2. **Redundant configuration.** The harness is derivable from the provider — Anthropic models run on claude/opencode/gemini, OpenAI models run on codex/opencode. Forcing users to specify it is busywork.
3. **Stale harness values.** When new harnesses appear (e.g., a hypothetical `aider` harness), every alias referencing that provider must be manually updated.

## Solution Overview

Make harness selection automatic by default, explicit when needed:

1. **Make `harness` optional in `ModelAlias`** — the field becomes `Option<String>` in Rust, `harness` becomes optional in mars.toml.
2. **Provider-to-harness routing** — when harness is omitted, mars derives it from the model's provider using a preference table + installed-binary detection.
3. **`mars models resolve` returns the full resolution** — alias name, resolved model ID, provider, and harness (whether explicit or auto-detected). This is the API meridian and other consumers use.
4. **Builtin aliases drop `harness`** — they specify provider + match patterns only. Harness is derived at resolution time.

## Design Docs

- [harness-detection.md](harness-detection.md) — how mars detects installed harnesses and maps providers to them
- [model-alias-changes.md](model-alias-changes.md) — schema changes to ModelAlias and mars.toml
- [resolve-api.md](resolve-api.md) — the `mars models resolve` command and its JSON output
- [meridian-integration.md](meridian-integration.md) — how meridian consumes the new mars resolve API

## Key Design Decisions

See [decisions.md](../decisions.md) for the full log (D1–D14). Summary:

- Provider→harness preference table is **hardcoded in mars**, no mars.toml override in v1. Users set `harness` per-alias if they need a specific one. (D1, D9)
- Harness detection uses **`which` per invocation** with no caching — ~8ms total, negligible. (D2)
- `ModelSpec::Pinned` gains **`provider: Option<String>`** so harness routing doesn't rely solely on model ID prefix inference. (D10)
- Explicit harness values are **validated for installation** — reported as unavailable if binary not found. (D11)
- Meridian **keeps null-harness aliases** (doesn't skip them) — its own `model_policy.py` routing is the authoritative fallback. (D12)
- `resolve_all` **encapsulates** harness detection internally — callers pass only `aliases` + `cache`. (D13)
- `HarnessSource` is an **enum** (`Explicit | AutoDetected | Unavailable`), not a string. (D14)
- `mars harness list` command **deferred** to follow-up. (D8)
