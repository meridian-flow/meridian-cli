# Feasibility

Probe evidence and validated assumptions that ground the design. Re-run probes
if entries go stale.

## Installed harness versions (probed 2026-04-14)

| Harness  | Installed        | Design floor        | Verdict |
|----------|------------------|---------------------|---------|
| codex    | `codex-cli 0.120.0` | `codex-rs 0.78.0`+  | ok (well above floor) |
| claude   | `2.1.107 (Claude Code)` | `2.1.x`         | ok |
| opencode | `1.4.3`          | `1.1.1`+ (post `tools→permission` merge) | ok |

The codex floor comes from p1729 (`0.78.0` introduced project-aware config
layering; `0.80.0` fixed a `CODEX_HOME`-related bug). The installed `0.120.0`
is well past both.

## P1 — codex per-spawn `CODEX_HOME` actually overrides config

**Probe:** wrote a minimal `config.toml` under a temp `CODEX_HOME` with
`[features] multi_agent = false`. Ran `codex features list` both with and
without the override.

**Result:**
```
=== with CODEX_HOME override ===
multi_agent    stable    false
=== default ~/.codex ===
multi_agent    stable    true
```

**Verdict:** Per-spawn `CODEX_HOME` config loading works as expected. The
`[features]` override takes effect. This validates the core mechanism the
design depends on.

**Gotcha surfaced:**
- `codex` prints `WARNING: Refusing to create helper binaries under temporary
  dir "/tmp" (codex_home: ...)` when `CODEX_HOME` lives under `/tmp`.
  Putting the per-spawn home under `.meridian/spawns/<id>/codex-home/`
  (inside `$HOME`) avoids this warning. The design places the directory
  there anyway; call this out as "do not put it under `/tmp`".

## P2 — codex `exec` does not accept `--ask-for-approval`

**Probe:** `codex exec --ask-for-approval never ...` → `error: unexpected
argument '--ask-for-approval'`.

**Verdict:** This flag is interactive-only. Meridian already sets
`approval_policy` via `-c approval_policy=...` on the exec path
(`project_codex_subprocess.py:157`), which is the right mechanism. The
generated per-spawn `config.toml` also sets `approval_policy = "never"` under
the locked-down profile, so both the CLI override and the profile cover it.

**Implication for design:** the generated config.toml must set
`approval_policy` and `sandbox_mode` on the profile; CLI `-c` overrides layer
on top per codex precedence (CLI > profile > home config), so both layers
agree rather than fight.

## P3 — codex `[features]` + `[apps._default]` lockdown behaves as designed

**Probe:** config.toml with `[features] multi_agent = false` collapses the
feature from `true` → `false`. `[apps._default].enabled = false` and
`[features] apps = false` were both written and accepted without parse errors.

**Verdict:** p1729's copy-paste example is sound on the installed `0.120.0`.
Per-feature granularity works. Use this as the allowlist mechanism.

**Open verification (shift to implementation):** confirm that
`[permissions.read_only.filesystem] ":project_roots" = "read"` actually
blocks a write under `sandbox_mode = read-only`. The sandbox already blocks
writes by definition, so the permissions block is belt-and-suspenders, but
worth smoke-testing at implementation.

## P4 — claude `plan` mode is not fail-closed without an explicit denylist

**Probe:** from upstream docs (p1724): `plan` is a planning-focused
restriction that asks the model to plan before executing. `--disallowedTools`
is honored at hard-permission level with documented precedence `deny >
allow`.

**Verdict:** Relying on `plan` alone is not fail-closed. The design pairs
`--permission-mode plan` with `--disallowedTools Edit,Write,MultiEdit,
NotebookEdit,Bash,WebFetch` (and any MCP write-shaped tools) to get both the
planning nudge and the hard block.

**Open verification (shift to implementation):** smoke-test whether plan
mode plus the denylist actually rejects an `Edit` call with a visible error
(not silent no-op). Requires a real claude run; record in smoke matrix.

## P5 — opencode `OPENCODE_PERMISSION` JSON deny behavior

**Probe:** upstream docs (p1724) document `permission` rules with `allow |
ask | deny`, a global `*` rule, and per-tool rules. `OPENCODE_PERMISSION` env
var is documented as inline JSON permissions. Meridian already emits
`{"*":"deny", "read":"allow", "grep":"allow", ...}` when an allowlist exists
(`permissions.py:130-139`).

**Verdict:** The mechanism exists and meridian already wires it. Gap is only
that `sandbox: read-only` today does not synthesize a denylist for mutating
tools. The design extends the env-override synthesizer to treat
`sandbox: read-only` as producing a baseline read-only permission JSON even
when no explicit allowlist is set.

**Open verification (shift to implementation):** smoke-test opencode refuses
`write` / `edit` / `bash` when launched with the synthesized JSON; test that
denial produces a visible enforcement signal, not a silent drop.

## P6 — `CodexAdapter.resolve_session_file()` hard-code

**Probe:** `src/meridian/lib/harness/codex.py:392` hard-codes
`Path.home() / ".codex" / "sessions"`. The extractor at
`src/meridian/lib/harness/extractors/codex.py:101` already uses
`launch_env["CODEX_HOME"]`.

**Verdict:** the adapter and extractor are inconsistent. Once meridian starts
injecting per-spawn `CODEX_HOME`, session resolution via the adapter path
will go stale. This is blocked-on and must fix in the same change. See
`refactors.md` R1.

## Open questions carried into implementation

- The exact disallow-tools list for claude read-only must include every
  mutating tool claude exposes today. Edit, Write, MultiEdit, NotebookEdit,
  Bash, WebFetch are the documented ones. MCP-provided write tools depend on
  per-spawn MCP config and are outside meridian's projection; acceptable
  because meridian does not auto-inject MCP (p1722 §note).
- The opencode tool-name vocabulary (`read`, `grep`, `glob`, `write`, `edit`,
  `bash`, `list`, `webfetch`, `patch`) must match what opencode 1.4.3
  actually honors. The allowlist path already uses lowercased names
  (`permissions.py:125-127`). Verify exact spelling against opencode 1.4.3
  at smoke time.
