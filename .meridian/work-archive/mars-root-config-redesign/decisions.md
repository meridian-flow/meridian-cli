# Decision Log

## D1: `[dependencies]` as sole consumer marker (no init comment)

**Choice:** Delete `INIT_MARKER`. A `mars.toml` is consumer config iff it has `[dependencies]`.

**Why:** The marker doesn't survive `config::save()` (serde drops TOML comments). Every `mars add`/`mars link`/`mars rename` does load→mutate→save, silently stripping the marker. Two detection codepaths (marker OR sources vs marker AND sources) were already inconsistent. All four reviewers flagged this.

**Rejected:** Keeping marker + adding serde comment preservation. TOML crates for Rust (`toml`, `toml_edit`) have different tradeoffs — `toml_edit` preserves formatting but the project uses `toml` (serde-based). Switching crates for a feature we don't need is wrong.

## D2: Persist managed root in `[settings]` (not drop custom support)

**Choice:** Add `settings.managed_root: Option<String>` to `mars.toml`.

**Why:** Custom targets matter for `.claude/`, `.cursor/` directories where the harness reads from a non-`.agents` path. Without persistence, `mars init .claude` works once but a clean checkout loses the target name and falls back to `.agents`.

**Rejected:** Drop custom target support entirely. Would force symlink workflows (`mars link`) for something that should just work — and `mars link` is already more complex than setting a config field.

**Rejected:** Persist in `.mars/config.json` inside managed dir. Circular — if the managed dir is deleted, we need the name to recreate it, but the name is inside the dir we're trying to find.

## D3: Local package items as synthetic `_self` source

**Choice:** Inject local items during sync as a synthetic source, not a user-visible `[sources]` entry.

**Why:** Local items have a fundamentally different lifecycle than external sources — they're not fetched, cached, or version-locked. Making them a real source creates circular references (project references itself), confuses `mars list` output, and adds resolver complexity for something that should be a simple discovery+symlink.

**Rejected:** `[sources._self] path = "."` — circular reference, resolver confusion, user-visible noise.

**Rejected:** Separate `[self]` or `[local]` config section — adds config complexity for a feature that can be entirely implicit (if you have `[package]` + `[sources]`, your local items get symlinked).

## D4: `mars init` defaults to git root

**Choice:** Walk up from cwd to find `.git`, use that as default project root.

**Why:** `mars.toml` at repo root is the canonical placement. Running `mars init` from a subdirectory should initialize the project, not create a stranded config. Walk-up discovery already stops at `.git` — if init creates config in a subdirectory, it's invisible from sibling directories.

**Rejected:** Keep cwd default with a warning. Users ignore warnings, and the resulting broken state (config in wrong place) is hard to diagnose.

## D5: Unified `[dependencies]` (replaces `[sources]` and old `[dependencies]`)

**Choice:** Single `[dependencies]` section for both "what gets installed locally" and "what downstream consumers inherit." Replaces both the old `[sources]` (consumer) and `[dependencies]` (manifest) sections.

**Why:** Every other package manager does this — Cargo, npm, pip/uv all use one section. `cargo add foo` both installs locally AND declares the transitive dependency. The resolver handles the distinction internally. Having two sections (`[sources]` vs `[dependencies]`) with overlapping fields confused the model without adding real value.

**Rejected (original design):** Keep `[sources]` and `[dependencies]` separate with different semantics. This was the initial design choice, but it doesn't match any established package manager convention and forces users to understand an artificial distinction.

## D6: Skills get directory-level symlinks, agents get file-level

**Choice:** `.agents/skills/my-skill/ → ../../skills/my-skill/` (directory symlink) vs `.agents/agents/my-agent.md → ../../agents/my-agent.md` (file symlink).

**Why:** Skills are directories containing `SKILL.md` plus optional `resources/` subdirectories. File-level symlinks would only capture `SKILL.md`, missing resources. Directory-level symlinks capture everything. Agents are single `.md` files — file-level is correct.

**Discovered by:** Correctness reviewer caught that the original design would produce broken skills.

## D7: `_self` items bypass the diff engine

**Choice:** Inject `PlannedAction::Symlink` directly into the plan after the normal diff→plan pipeline. Don't route through `diff::compute` or `plan::create`.

**Why:** The diff engine compares source hashes against lock hashes to detect changes. For symlinks, the question is "does the symlink point to the right place?" not "has the content changed?" Routing through diff would require special-casing `_self` in three places (diff, plan, target), or using empty content hashes that break the diff engine (produces `LocalModified` on every re-sync because disk hash ≠ empty lock hash).

**Rejected:** Empty content hash in lock. Causes every re-sync to report "kept" for local items because `hash::compute_hash` follows symlinks and returns non-empty hash ≠ "".

**Rejected:** Add `is_symlink: bool` to `TargetItem` and route through normal pipeline. Three touch points instead of one clean injection point.

## D8: `detect_managed_root` returns Result, distinguishes NotFound from parse errors

**Choice:** `detect_managed_root(project_root) -> Result<PathBuf>`. `NotFound` falls through to defaults, parse errors propagate.

**Why:** The original design used `if let Ok(config) = ...` which swallows ALL errors including parse errors. A typo in `[settings]` would silently fall back to `.agents` instead of telling the user their config is broken.

**Discovered by:** Correctness reviewer.

## D9: Relative symlinks for local items

**Choice:** Use relative symlinks (`../../agents/my-agent.md`) instead of absolute paths.

**Why:** Relative symlinks survive repo moves/renames. Absolute symlinks break when the repo is moved to a different directory. This is standard practice (npm's `link`, Cargo's path dependencies all deal with this).

## D10: Unify `[sources]` and `[dependencies]` into single `[dependencies]`

**Choice:** Remove `[sources]` entirely. `[dependencies]` is the sole section for declaring what packages to install/depend on. Consumer detection becomes: mars.toml has `[dependencies]` key.

**Why:** Cargo, npm, pip/uv all use one section. The two-section model (`[sources]` for local install, `[dependencies]` for transitive resolution) doesn't match any established convention and forces users to learn an artificial distinction. The resolver can handle both roles from one declaration internally.

**Impact:** Config struct drops `sources` field, gains unified `dependencies` with all fields from both `SourceEntry` and `DepSpec`. `mars init` creates empty `[dependencies]`. `mars add` writes to `[dependencies]`. All user-facing "source" terminology becomes "dependency." Lock file `[sources.*]` entries rename to `[dependencies.*]` for consistency.
