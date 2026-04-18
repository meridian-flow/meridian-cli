# Requirements: Managed Read-Only + Tool Allowlist Parity

## Intent

Let a user declare `sandbox: read-only` + `tools: [...]` (or `--sandbox read-only --allowed-tools ...`) on a spawn and have it actually take effect across **all three** supported harnesses: **codex**, **claude**, **opencode**. Today each harness enforces one half of the pair and silently drops the other. The user experience is: "I said read-only with Read/Grep only — why did the agent just try to write a file / call a tool I never allowlisted?"

## Current State (as investigated 2026-04-14)

See prior research spawns: p1722 (investigator), p1723 (explorer), p1724 (researcher), p1729 (codex config.toml confirmation), p1730 (CODEX_HOME plumbing exploration).

| Harness   | Managed read-only | Managed tool allowlist | How it's (partly) wired today |
|-----------|-------------------|------------------------|-------------------------------|
| codex     | ✅ `--sandbox`     | ❌ `--allowedTools` is stripped with warning | `project_codex_subprocess.py:151` |
| claude    | ❌ no sandbox projection | ✅ `--allowedTools` / `--disallowedTools` | `project_claude.py:161` |
| opencode  | ❌ no sandbox projection | ✅ `OPENCODE_PERMISSION` env JSON | `permissions.py:130`, `opencode.py:243` |

## Scope

**In:**

1. **Codex tool allowlist** via per-spawn `CODEX_HOME` pointing at a generated `config.toml`. Replaces the current "strip and warn" path. Must project profile `tools:` / `disallowed-tools:` into codex's config layering (`[features]`, `[apps._default]`, `[permissions.<name>]`, profile `sandbox_mode`/`approval_policy`).
2. **Claude managed read-only** — map `sandbox: read-only` onto Claude's `--permission-mode plan` (or equivalent). Cross-check whether `plan` is sufficient or if it needs to pair with an explicit deny list to actually block mutating tools.
3. **OpenCode managed read-only** — map `sandbox: read-only` onto the existing `OPENCODE_PERMISSION` JSON path (`*: "deny"` + per-tool allow matching the profile `tools:` list), or use OpenCode's `mode: readonly` pattern.
4. **Tests** — smoke tests that each harness actually refuses a write attempt under `sandbox: read-only` and actually refuses a non-allowlisted tool under `tools: [Read, Grep]`.
5. **Unshadowing the user's global codex config** — by default, per-spawn `CODEX_HOME` would hide user-level `~/.codex/config.toml` (credentials, history, MCP). Design must decide: layer on top (copy/include user config), document the isolation, or provide an opt-out.

**Out:**

- Changing the `tools:` / `disallowed-tools:` frontmatter schema itself.
- Rewriting the sandbox tier system (that's `sandbox-simplification`).
- Claude's `plan` mode semantics beyond confirming it meets "read-only" intent.
- Codex per-app/per-tool granularity beyond enabling/disabling the built-in set matching profile `tools:`.

## Constraints

- **Must not bolt filesystem writes onto `project_codex_subprocess.py`**. Projections stay CLI-shape-only. Generated `config.toml` materialization belongs in a launch-context / connection-start hook.
- **Must honor `Open/Closed` principle** (`AGENTS.md`): adding this capability to codex is one adapter-level change, not a cross-cutting rewrite.
- **Codex version floor** — config layering behaviors relied on here landed in codex-rs `0.78.0`+. Must declare and probe.
- **`CodexAdapter.resolve_session_file()` at `codex.py:392` hard-codes `Path.home() / ".codex" / "sessions"`** — this blocks per-spawn `CODEX_HOME` from working correctly. Must fix as part of this work.
- **Plumbing already safe:** `CODEX_HOME` passes the `preflight.extra_env` merge guard (streaming-parity-fixes S046), and the codex session extractor honors `launch_env["CODEX_HOME"]` (streaming-parity-fixes F12). The new work builds on top of this — do not re-derive it.
- **Backwards compatibility:** none needed per project policy. Schema can change.

## Success Criteria

A smoke test matrix where, for each of (codex, claude, opencode) × (read-only sandbox, narrow tool allowlist, both combined):

1. The agent refuses an edit/write attempt under `sandbox: read-only` with a visible enforcement signal (sandbox error, permission prompt, tool rejection).
2. The agent cannot invoke a tool outside `tools: [Read, Grep, Glob]` — calling such a tool errors or gets denied.
3. `meridian spawn --dry-run` shows the actual enforcement mechanism (codex `--profile` + `CODEX_HOME`, claude `--permission-mode plan --allowedTools ...`, opencode `OPENCODE_PERMISSION={...}`).
4. No silent drops. If a profile asks for something a harness can't enforce, meridian errors at spawn time instead of warning and proceeding.

## Prior Art References

- `streaming-parity-fixes` (archived) — S046, F12. `CODEX_HOME` env plumbing landed here; do not redesign it.
- `sandbox-simplification` (open, design-reviewed) — explicitly lists `allowed_tools`/`disallowed_tools` resolver as out-of-scope; this work owns that layer.
- Codex config reference: https://developers.openai.com/codex/config-reference
- Claude permissions: https://code.claude.com/docs/en/permissions
- OpenCode permissions: https://opencode.ai/docs/permissions/

## Open Questions for Design

1. Is claude `--permission-mode plan` alone sufficient for "read-only" intent, or does it also need `--disallowedTools Edit,Write,Bash(...)`?
2. Should per-spawn codex `CODEX_HOME` inherit from user-level `~/.codex` (credentials, MCP creds) or be fully isolated? Isolation = reproducibility but breaks logged-in auth; inheritance = leaks user config into spawn-visible space.
3. For codex, is "allowlist" enforced purely via `[features]` + `[apps._default].enabled = false` + `default_permissions`, or do we also need to generate per-app blocks to reach parity with claude's per-tool granularity?
4. Should meridian reject at spawn time if a profile asks for enforcement a harness can't provide, or degrade with a loud warning? (Current behavior: silent strip. Target: not that.)
