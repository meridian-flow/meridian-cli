# Probe Evidence (re-run 2026-04-14)

All probes run against current checkout (`meridian-cli` HEAD) and installed `codex-cli 0.120.0`. Every claim cites a live file + line number. Use this as ground truth for the design package; do not re-derive.

## Probe 1 — `codex exec --add-dir` exists

**Verdict**: confirmed. Codex is a viable target for workspace-root injection in v1.

**Evidence** (`codex exec --help`, codex-cli 0.120.0):

```
      --add-dir <DIR>
          Additional directories that should be writable alongside the primary workspace
```

Also present: `--skip-git-repo-check`, `-C/--cd <DIR>`, `--sandbox <read-only|workspace-write|danger-full-access>`.

**Known gotcha** (from prior-round feedback, still valid): when the effective sandbox is `read-only`, codex treats `--add-dir` as inert. This does not surface in `codex exec --help`; it's a runtime behavior. The design MUST report this per-harness, per-sandbox applicability in `config show` / `doctor` (prior F6).

## Probe 2 — `dedupe_nonempty` preserves first-seen order

**Verdict**: confirmed first-seen. Any design that depends on "last-wins" at this dedupe layer is wrong.

**Evidence**: `src/meridian/lib/launch/text_utils.py:8-19`

```python
def dedupe_nonempty(values: Iterable[str]) -> list[str]:
    """Strip and dedupe values while preserving first-seen order."""
    seen: set[str] = set()
    deduped: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
```

**Call sites relying on this ordering**:

- `lib/harness/claude_preflight.py:117` — `return dedupe_nonempty(additional_directories), dedupe_nonempty(allowed_tools)` (from parent-forwarding path).
- `lib/harness/claude_preflight.py:131-145` — directly emits `--add-dir` tokens to the passthrough tail. The *order* of emission is: user passthrough args → `execution_cwd` → parent `additionalDirectories`. Raw tokens are not deduped here; dedupe only applies to the parsed parent lists.
- `lib/harness/projections/project_claude.py:62,105,163` — parent-allowed-tools merge uses first-seen semantics.
- `lib/launch/text_utils.py:34,58` — `--allowedTools` flag merge (`existing + additional`, then dedupe).

**Design implication**: if the workspace root injection dedupes against parent passthrough with `dedupe_nonempty`, **whatever appears first wins**. If workspace roots should not override user passthrough `--add-dir` values, the workspace roots must be emitted *after* the passthrough tail, not before. Conversely, if user passthrough should override workspace config (sensible, since it's explicit CLI override), passthrough goes first.

## Probe 3 — Meridian reads no `.meridian/models.toml`

**Verdict**: confirmed Mars-owned. Drop `models.toml` migration from design scope.

**Evidence**: `rg "models\.toml|models_merged" src/ tests/` returns zero Python hits. The only model-alias read path is:

- `lib/catalog/model_aliases.py:229` reads `.mars/models-merged.json` (mars-produced).
- `lib/catalog/model_aliases.py:5-6` docstring: "mars dependency packages (via .mars/models-merged.json) and consumer config (via mars.toml [models])."

Meridian has no `models.toml` loader. Migrating a file Meridian never reads is a no-op masquerading as a refactor.

## Probe 4 — Full blast radius of migrating committed config location

**Verdict**: the rename touches ≥9 files across 5 modules + tests + smoke. RF-1-equivalent in the new design must enumerate these; "one-function change" is wrong.

**Evidence** (every site referencing `.meridian/config.toml` or `_config_path`):

### Read/write sites

| File | Line(s) | Role |
|------|---------|------|
| `lib/state/paths.py` | 127 | `config_path = root_dir / "config.toml"` — canonical path computation on `StatePaths`. |
| `lib/state/paths.py` | 21, 33 | `_GITIGNORE_CONTENT` + `_REQUIRED_GITIGNORE_LINES` pin `!config.toml` in `.meridian/.gitignore`. |
| `lib/config/settings.py` | 25 | `_DEFAULT_USER_CONFIG = ~/.meridian/config.toml` (user-scope, not committed — still references the filename shape). |
| `lib/config/settings.py` | 206-210 | `_resolve_project_toml` — **the loader's resolver**. Returns `resolve_state_paths(repo_root).config_path` if present. |
| `lib/config/settings.py` | 213-227 | `_resolve_user_config_path` — independent of project path. |
| `lib/ops/config.py` | 342-343 | `_config_path()` — helper used by every `config` subcommand. |
| `lib/ops/config.py` | 758, 777, 827, 846, 872 | `config_init_sync`, `config_show_sync`, `config_set_sync`, `config_get_sync`, `config_reset_sync` — **every command bypasses `_resolve_project_toml` and uses the single `_config_path`**. Changing the loader without changing these leaves the commands writing to the legacy path while reads resolve from root. |
| `lib/ops/config.py` | 737-763 | `ensure_state_bootstrap_sync` — creates `_config_path(repo_root)` if missing on first run. |
| `lib/ops/config.py` | 602-606 | `_user_config_path_from_env()` — env-based user config discovery. |

### CLI help / advisory text

| File | Line | Content |
|------|------|---------|
| `lib/ops/manifest.py` | 242 | `"Scaffold .meridian/config.toml with commented defaults."` |
| `lib/ops/manifest.py` | 266 | `"Set one config key in .meridian/config.toml."` |
| `cli/main.py` | 806-815 | `config_app` help: `"Repository-level config (.meridian/config.toml) for default..."` |

### Tests / smoke

| File | Line | Purpose |
|------|------|---------|
| `tests/smoke/quick-sanity.md` | 45-47 | First-run bootstrap asserts `test -f "$MERIDIAN_STATE_ROOT/config.toml"`. |
| `tests/ops/test_config_warnings.py` | — | Config warnings suite. |
| `tests/ops/test_runtime_bootstrap.py` | — | First-run bootstrap. |
| `tests/config/test_settings.py` | — | Loader precedence and project-file parsing. |
| `tests/test_state/test_paths.py` | — | `StatePaths` fields. |
| `tests/cli/test_sync_cmd.py` | — | References `.meridian/config.toml` flow. |
| `tests/test_cli_bootstrap.py` | — | CLI first-run bootstrap. |

**Design implication**: any "move committed config to repo root" refactor must coordinate (a) a new path resolver that knows both legacy and root locations, (b) rewiring `_config_path()` → a dual-location lookup for reads and a root-preferred location for writes, (c) bootstrap-template emission at the new location, (d) gitignore adjustment (the `!config.toml` exception in `.meridian/.gitignore` becomes dead), (e) CLI help + manifest description updates, (f) smoke + unit test updates, (g) a divergent-file policy (byte-equal → auto-consolidate; divergent → abort with explicit remediation).

## Probe 5 — Codex command projection has no `--add-dir` wiring today

**Verdict**: workspace-root injection on the codex path requires a new integration point. Today's projection has no hook for it.

**Evidence**: `lib/harness/projections/project_codex_subprocess.py:189-227`. The projection builds:

```
base_command
  --model MODEL                        (if set)
  -c model_reasoning_effort="..."     (if effort set)
  <permission flags>                   (sandbox + approval)
  <mcp flags>
  resume <harness_session_id>          (if continue)
  <spec.extra_args>                    (passthrough tail)
  -o REPORT                            (if report_output_path and non-interactive)
  <guarded_prompt>
```

`spec.extra_args` is the only path through which `--add-dir` reaches codex today. The architect must decide **where** in this sequence workspace-emitted `--add-dir` tokens go: before or after `spec.extra_args`. (Workspace dirs should NOT silently override explicit CLI `--add-dir` from the user → workspace emits *after* extra_args so explicit user tokens come first; `codex exec` accepts repeated `--add-dir`, and first-occurrence semantics of any downstream dedupe preserve user intent.)

Also observe: the codex subprocess uses `-C/--cd <DIR>` absence — Meridian relies on cwd to set the primary workspace. `--add-dir` augments that primary workspace.

## Probe 6 — Claude preflight already injects `--add-dir` for parent-forwarding

**Verdict**: adding workspace-root injection on the claude path extends an existing mechanism; no new integration point needed, but the ordering interaction with parent-forwarding must be explicit.

**Evidence**: `lib/harness/claude_preflight.py:131-147`:

```python
expanded_args: list[str] = [*passthrough_args, "--add-dir", str(execution_cwd)]
...
for additional_directory in parent_additional_directories:
    expanded_args.extend(("--add-dir", additional_directory))
```

Current order: **passthrough_args → execution_cwd → parent.additionalDirectories**. Claude CLI accepts multiple `--add-dir`. Workspace roots should land alongside parent-forwarded dirs with explicit, documented order.

## Probe 7 — `StatePaths` is `.meridian`-scoped; no repo-root file abstraction exists

**Verdict**: prior F8 correct. Adding root-file discovery to `StatePaths` mixes concerns.

**Evidence**: `lib/state/paths.py:93-128` defines `StatePaths` with fields like `root_dir`, `artifacts_dir`, `spawns_dir`, `cache_dir`, `config_path` — all rooted under `.meridian/`. There is no existing module for "files at the repo root" (only `resolve_repo_root` at `lib/config/settings.py:804-838`, which anchors on `.agents/skills/` or `.git` but does not enumerate root files).

**Design implication**: introduce a separate repo-root file abstraction (e.g., `lib/config/project_paths.py` or similar). Committed `meridian.toml`, gitignored `workspace.local.toml`, `MERIDIAN_WORKSPACE` env override, and root `.gitignore` adjustments live there — not in `state/paths.py`.

## Probe 8 — First-run bootstrap creates committed config unconditionally today

**Verdict**: prior F9 correct. Silent auto-creation of a new root file is a regression for users who don't opt in.

**Evidence**: `lib/ops/config.py:737-763`. `ensure_state_bootstrap_sync` is called on every `resolve_runtime_root_and_config` path (`lib/ops/runtime.py:66`). It unconditionally:

1. Creates the `.meridian/` tree (spawns_dir, artifacts_dir, etc.).
2. Calls `ensure_gitignore(repo_root)`.
3. Calls `_ensure_mars_init(...)`.
4. If `_config_path(repo_root)` doesn't exist, writes `_scaffold_template()` to it.

**Design implication**: moving config to the root MUST NOT bring this auto-create behavior with it. Bootstrap should idempotently ensure `.meridian/` state directories exist (runtime state is always needed) but root `meridian.toml` creation must be opt-in via `config init` / `config migrate`.

## Probe 9 — `mars.toml` already lives at repo root; `.mars/` is Mars's local state

**Verdict**: the target convention exists for Mars. Meridian's root config placement matches.

**Evidence**:

- `lib/ops/config.py:712` — `mars_toml = repo_root / "mars.toml"`.
- `lib/catalog/model_aliases.py:229` — reads `.mars/models-merged.json`.

Both are repo-root-sibling (for `mars.toml`) and repo-root-local-state (for `.mars/`). Meridian's root-level `meridian.toml` (committed project policy) mirrors `mars.toml`; Meridian's local state stays in `.meridian/`. Mars/Meridian separability is already partially enforced by Mars; Meridian just needs to stop committing `.meridian/config.toml`.

## Summary for the design round

1. `codex --add-dir` is real. v1 can inject workspace roots into codex and claude. Opencode mechanism is out of scope for this probe; the design must either (a) probe and document it, or (b) declare opencode unsupported in v1 and surface it in `config show`/`doctor` — not silently no-op.
2. `dedupe_nonempty` is first-seen. Any ordering claim ("passthrough wins last-wins") in prior design was wrong. Put user passthrough first so its `--add-dir` values win under any downstream dedupe.
3. Models migration is not in scope.
4. Committed-config migration touches ≥9 files + tests + smoke. The refactor agenda must enumerate all of them.
5. `StatePaths` is not the home for root-file policy. A new `ProjectPaths` / `RepoFiles` abstraction is needed.
6. First-run silent file creation at the repo root is a footgun. File creation is opt-in only.
