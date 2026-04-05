# Decision Log

## D1: Extend RuntimeOverrides rather than build new resolution framework

**Choice**: Add `agent` field to `RuntimeOverrides` and use the existing `resolve()` first-non-None mechanism for all fields including model/harness/agent.

**Why**: `RuntimeOverrides.resolve()` already works correctly for 5 of 7 resolvable fields. The pattern is proven, tested, and understood. Building a new framework would be more work, more risk, and more code to maintain — for no additional capability. The ad-hoc if/elif chains in `resolve_policies()` are the problem, not the `RuntimeOverrides` abstraction.

**Rejected**: New `ResolutionLayer` framework with source tracking. Adds complexity (source tracking, layer introspection) that isn't needed to fix the precedence violations. Source tracking for `_source_for_key` display is a separate concern that can be added later without changing the resolution mechanism.

## D2: Two-phase resolution — resolve primaries, then derive dependents

**Choice**: Phase 1 resolves all independently-specifiable fields via layer merge. Phase 2 derives harness from model (and applies harness-specific model defaults) as pure functions on the resolved output.

**Why**: The current bug exists because harness derivation is interleaved with model resolution. By separating "what did the user/config specify?" from "what do we derive from that?", derivation can't interfere with precedence. A derived harness from a CLI model naturally inherits CLI precedence because it's computed from the CLI-provided model.

**Rejected**: Single-pass resolution with precedence-tagged values (each value carries its source level). More theoretically elegant but significantly more complex — every comparison needs to check levels, and the existing `resolve()` first-non-None is simpler and sufficient. The tag approach solves a problem we don't have (needing to know *where* a value came from during resolution).

## D3: Agent field added to RuntimeOverrides

**Choice**: Add `agent: str | None = None` to `RuntimeOverrides` so agent resolution uses the same first-non-None mechanism as all other fields.

**Why**: Agent resolution currently uses a separate code path (`load_agent_profile_with_fallback` with its own `requested_agent` / `configured_default` / `builtin_default` chain). This is structurally identical to first-non-None across layers but uses different code. Unifying it means one mechanism for all precedence decisions, eliminating the dead `config.primary.agent` field (violation #4).

**Trade-off**: Agent is slightly different from other fields because it triggers profile loading (which produces more overrides). This means agent must be resolved first (from CLI > ENV > config layers, without profile layer), then the profile is loaded, then all other fields are resolved with the profile layer included. This is a sequencing constraint, not a structural one.

## D4: Keep approval="default" → None mapping for now

**Choice**: Document violation #7 (`--approval default` can't override profile approval) as a known limitation. Don't fix in this refactor.

**Why**: Fixing it properly requires changing the CLI's default value for `--approval` from `"default"` to `None` (to distinguish "not specified" from "explicitly default"). This touches the CLI argument parser, which is outside the resolve pipeline's scope. The use case (user explicitly wants to reset approval to "default" when a profile sets something else) is rare enough to defer.

**Rejected**: Add a sentinel like `"__unset__"` as the CLI default. Leaks implementation details into the CLI layer and adds special-case handling throughout.
