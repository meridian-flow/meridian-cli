# Spec — Codex Enforcement (`SC-*`)

Per-spawn `CODEX_HOME` with a generated `config.toml` is the enforcement
substrate.

## SC-1 Per-spawn CODEX_HOME

When a codex spawn is launched, meridian shall materialize a directory at
`.meridian/spawns/<spawn_id>/codex-home/` and shall export
`CODEX_HOME=<that path>` into the harness child environment via the
adapter's `env_overrides`.

## SC-2 Generated `config.toml`

When materializing the per-spawn `CODEX_HOME`, meridian shall atomically
write a `config.toml` file at `<codex-home>/config.toml` containing the
projected profile, features, apps, and permissions derived from the spawn's
`PermissionConfig` and allowlist state.

## SC-3 Sandbox projection into profile

When the spawn's `sandbox` is `read-only`, the generated `config.toml`
shall include a `[profiles.meridian]` block with
`sandbox_mode = "read-only"` and `approval_policy = "never"` (or the
resolved approval value), and the file's top-level shall set
`profile = "meridian"`.

## SC-4 Allowlist projection into features/apps

When the spawn's `allowed_tools` is non-empty or `sandbox = "read-only"`
is declared, the generated `config.toml` shall disable the `_default` app
bucket (`[apps._default] enabled = false`) and shall set
`[features]` entries that remove non-read capabilities the profile does
not opt into (at minimum: `apps = false`, `web_search = false`,
`connectors = false`, `plugins = false`, `memory_tool = false`,
`image_generation = false`).

## SC-5 Denylist projection

When the spawn's `disallowed_tools` list explicitly names codex-known
features (e.g. `web_search`, `apps`), the generated `config.toml` shall
set the matching `[features].<name> = false` entry.

## SC-6 CLI flag layering agreement

When meridian emits `-c approval_policy=...` and `--sandbox <mode>` on the
codex CLI command, those values shall match (not contradict) the
generated profile in the per-spawn `config.toml`.

## SC-7 Auth material narrow inheritance

When materializing the per-spawn `CODEX_HOME`, meridian shall copy or
symlink **only** `auth.json` and `.credentials.json` from the user's real
`~/.codex` when those files exist, and shall not copy `config.toml`,
`history.jsonl`, `log/`, or any other file.

## SC-8 `resolve_session_file` honors `CODEX_HOME`

When resolving a codex session file path, the codex adapter shall resolve
the sessions root from the spawn's `launch_env["CODEX_HOME"]` (falling
back to `~/.codex` only when no override is present), not from a
hard-coded `Path.home() / ".codex"`.

## SC-9 Atomic materialization

When writing the per-spawn `config.toml`, meridian shall use the
tmp+rename pattern established for state files (atomic write) so that a
partially-written config never becomes visible to codex.

## SC-10 Materialization placement

The per-spawn `CODEX_HOME` materialization shall occur at
connection-start (before the harness child process is spawned) using the
same lifecycle hook that already creates the spawn log directory, and
shall not occur inside `project_codex_subprocess.py` or
`project_codex_streaming.py` (those projections stay CLI-shape-only per
Rule of Separation).

## SC-11 Codex capability declaration

The codex harness adapter shall declare
`supports_managed_sandbox = True`,
`supports_managed_allowlist = True`, and
`supports_managed_denylist = True` once the per-spawn `CODEX_HOME`
pipeline is in place, removing the current silent-strip path in
`project_codex_subprocess.py:101-142`.

## SC-12 Write attempt refusal under read-only

When a codex spawn is launched with `sandbox = "read-only"` and the agent
attempts to write a file, the codex sandbox shall refuse the write with a
non-zero shell exit or sandbox-denial signal in the emitted events.

## SC-13 Non-allowlisted tool refusal

When a codex spawn is launched with `allowed_tools = [Read, Grep, Glob]`
(or equivalent narrow set) and the agent attempts to invoke a tool outside
that set that corresponds to a codex app or disabled feature, codex shall
refuse with a visible error consistent with
`[apps._default].enabled = false` semantics.
