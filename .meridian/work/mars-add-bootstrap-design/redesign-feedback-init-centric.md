## Redesign Feedback: Init-Centric Bootstrap

The current `mars add` bootstrap design is still too special-case.

### New Direction

Bootstrap should be modeled around `mars init`, not around an `add`-specific bootstrap mode.

### Desired Model

- `mars init` is the canonical bootstrap primitive.
- There is an explicit allowlist of subcommands that may auto-initialize when config is missing.
- Those subcommands reuse the same initialization semantics as `mars init`.
- Root discovery should not grow hidden one-off bootstrap behavior for `add`.

### Questions To Resolve

- What are the default semantics of `mars init`?
- Which subcommands belong in the auto-init allowlist?
- Should `add` effectively run init logic before continuing?
- Which commands must still fail on missing config?

### Expected Sequencing

Treat this as three distinct design tracks:

1. **Bootstrap semantics**
   - Make `mars init` the canonical bootstrap path.
   - Define the auto-init allowlist.
   - Make `add` follow that model.

2. **Remove accidental git assumptions**
   - After bootstrap semantics are settled, do a focused pass on git-coupled core semantics.
   - Keep git only where it is a real product requirement.

3. **Repo-wide Windows compatibility**
   - Do a separate repo-wide Windows compatibility pass for `mars-agents`.
   - Windows remains a constraint throughout, but the full compatibility audit is its own effort.

### Constraint

Do not fold the full repo-wide de-git pass or Windows compatibility program into the `mars add` feature design.
Those should be named and scoped separately.

---

## Resolution

**Status**: Addressed in design package revision.

The design package has been revised to implement the init-centric model:

| Feedback Item | How Addressed |
|---------------|---------------|
| `mars init` as canonical bootstrap | spec INIT-1 through INIT-5 define init semantics |
| Explicit auto-init allowlist | spec table classifies all commands; decisions D2 |
| `add` reuses init semantics | architecture shows `invoke_init_at()` calling `bootstrap_at()` |
| No hidden one-off bootstrap | architecture shows shared code path via `AutoInit` enum |
| Default semantics of init | cwd-based, no git (spec INIT-2, decisions D3, D8) |
| Which commands fail on missing config | all except `init` and `add` (spec AUTO-1, FAIL-1) |
| Follow-on tracks scoped out | spec "Follow-On Design Tracks", decisions D16, D17 |
