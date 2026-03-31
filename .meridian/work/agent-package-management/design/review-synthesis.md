# mars-agents Design Review Synthesis

6 reviewers, 3 models (Opus, GPT-5.4), 5 focus areas + 1 architecture design.

## Blocking Issues

Must resolve before implementation begins.

### 1. `--force` Semantics Need Clarification

**Sources**: Conventions (p568), Positioning (p569)

`mars sync --force` is described as "like `rm -rf node_modules && npm install`" — but `.agents/` contains user-authored content alongside managed content. That analogy implies data loss.

**Resolution**: `--force` means "overwrite managed files, ignore local modifications" — never "destroy everything." Drop `node_modules` analogies from the spec. The mixed-ownership model is the whole point — the merge/conflict system exists because of it.

### 2. Three-Way Merge Must Be v1

**Sources**: Phasing (p572), Conventions (p568)

Three-way merge is the differentiating feature and the Rust language justification. Without it, v1 offers the same binary keep/overwrite behavior as current `meridian sources`. If merge is v1.5, then v1 is a lateral move — a rewrite in Rust that does what the Python code already does. The phasing reviewer called this "blocking."

**Resolution**: Move three-way merge from v1.5 to v1. Offset by cutting `doctor`, `repair`, and rename detection to v1.5. Rerere is deferred — it solves a rare case (same conflict recurring). The merge itself is the core value.

### 3. Name Collision Policy Is Missing

**Source**: Edge Cases (p570)

Two sources provide `agents/coder.md` — what happens? The spec mentions "provenance tracking" but never specifies: detection timing (at `add` or `sync`?), resolution mechanism, cross-source precedence, or transitive collisions. The existing meridian code errors hard on destination collisions with interactive rename-or-skip. Mars has none of this.

**Resolution**: Detect at resolution time (before any files are written). Error with clear message: "Source A and Source B both provide agents/coder — resolve by adding `exclude` to one source or renaming." No silent overwrite, no implicit precedence. This is a v1 requirement because it's a data-safety issue.

### 4. Cherry-Picking / Per-Source Filtering

**Source**: Edge Cases (p570)

No per-source filtering mechanism. A source with 15 agents dumps all 15. Existing meridian functionality (`agents`, `skills`, `exclude_items` fields per source) would be lost. This is a regression from current behavior.

**Resolution**: Add per-source `include` and `exclude` fields in `agents.toml`. Default is include-all. This is v1 because losing existing functionality in a replacement tool is unacceptable.

```toml
[sources.meridian-base]
url = "github.com/haowjy/meridian-base"
version = ">=0.5.0"
exclude = ["agents/deprecated-agent"]
```

### 5. Concurrent Process Safety

**Source**: Edge Cases (p570)

Two `mars sync` in parallel: both read lock, both resolve, both write files, last lock-writer wins, first writer's state is lost. No locking mechanism specified.

**Resolution**: The architecture doc (p573) addresses this with `flock` on `.agents/.mars/mars.lock` during the apply phase. Document this in the spec. Note: `flock` doesn't work on NFS or Windows — document platform limitations. Windows alternative: `LockFileEx`.

### 6. Atomic File Operations

**Source**: Edge Cases (p570)

No atomic write pattern specified. Kill mars mid-write = truncated TOML or half-installed files.

**Resolution**: The architecture doc (p573) addresses this: `write(tmp) -> fsync(tmp) -> rename(tmp, dest)`. Temp files in same directory as destination (same filesystem for atomic rename). Document this in the spec.

### 7. Dev Overrides Are Self-Contradictory

**Source**: Edge Cases (p570)

Spec says dev overrides are "not committed" but puts them in `agents.toml` which IS committed. Can't have both.

**Resolution**: The architecture doc (p573) addresses this with `agents.local.toml` (gitignored) separate from `agents.toml` (committed). Mirrors meridian's existing `agents.local.toml` pattern. Update the spec.

### 8. Git Tag Pinning / Supply Chain

**Source**: Edge Cases (p570)

Lock stores tag name, not commit SHA. Tags can be force-pushed. Silent content change = supply-chain integrity gap.

**Resolution**: The architecture doc (p573) stores both `version` (tag) and `commit` (SHA) in the lock. On sync, verify the tag still points to the locked commit. If it doesn't, warn loudly. This is v1 — compromised agent profiles are prompt injection vectors, more dangerous than compromised npm packages.

---

## High Priority Design Decisions

Not blocking, but should be resolved before implementation.

### 9. "Go Modules Approach" Is Misleading

**Source**: Conventions (p568)

The actual design is URL-based identity (Go) + constraint-based resolution with lock file (Cargo/uv). Go's MVS is deterministic without a lock file — that's not what mars does. `@v2` meaning "latest v2.x.x" diverges from Go where `v2` is a module path suffix. The combination of Go-style identity + npm-style CLI + git-style conflicts is fine — just don't claim coherence with any single tool.

**Action**: Rename to what it is. "URL-based package identity with constraint-based version resolution." Drop "Go modules approach."

### 10. Sharpen Competitive Differentiation

**Source**: Positioning (p569)

As of March 2026, `skills.sh` ships install/list/remove/check/update, `skild` markets as "unified package manager for AI Agent Skills," and Tessl is package manager + registry + evaluation. The spec should acknowledge these and lead with mars's actual differentiators: mixed-ownership management, agent-to-skill dependency validation, safe pruning via provenance, three-way merge with conflict resolution for local customizations.

### 11. Add "Why Standalone?" Section

**Source**: Positioning (p569)

The design should explicitly state why mars is a separate binary rather than part of meridian. The reasoning exists (discussed in conversation: faster execution, no Python dependency, reusable by non-meridian tools, cleaner separation) but isn't written down in the spec.

**Action**: Add a "Why Standalone?" section to the design doc capturing the rationale.

### 12. Item Model Should Be Extensible

**Source**: Extensibility (p571)

Hard-coding `agents/` and `skills/` as the only two installable kinds blocks future content types (MCP server configs, Cursor rules, tool definitions, prompts). The manifest, lock, and filesystem layout all assume exactly two kinds.

**Action**: Use an `ItemKind` enum (as the architecture doc proposes). V1 ships with `Agent` and `Skill` only. Adding a new kind = add an enum variant + discovery logic + destination pattern. Match exhaustiveness catches missing cases.

### 13. URL-as-Identity Limits Registry

**Source**: Extensibility (p571)

**Decision**: Punt. URL-as-identity works for v1. No registry planned. If registry ever happens, introduce stable package ID then. Architecture's `ItemId = (kind, name)` already decouples item identity from URL at the item level.

### 14. Migration Path from Current Meridian Sources

**Source**: Phasing (p572)

**Decision**: Skip. No external users to migrate. When mars is ready, manually update meridian's own config.

### 15. Source Without `mars.toml` Manifest

**Source**: Edge Cases (p570)

**Decision**: Manifest is optional. Filesystem convention (`agents/*.md`, `skills/*/SKILL.md`) is the primary discovery mode — design for the case where nobody has a `mars.toml`. Manifest adds value when present (declared deps, metadata) but is never required. Spec updated.

---

## Medium Priority

### 16. Workspace / Monorepo Support

**Source**: Extensibility (p571)

Current architecture assumes one project root = one config = one lock = one cache. The architecture doc's `SyncContext` with separate `root` and `install_target` is a good hedge — minimal cost now, enables workspace later.

### 17. Circular Dependencies

**Source**: Edge Cases (p570)

Topological sort fails on cycles. The spec says "topological sort" but never mentions cycle detection or error reporting. Trivial to implement — just needs to be specified.

### 18. Case-Insensitive Filesystems

**Source**: Edge Cases (p570)

Source A provides `Coder.md`, Source B provides `coder.md` — same file on macOS/Windows, different entries in lock. Lock must normalize or detect. Also: Windows `MAX_PATH`, symlink privilege requirements, path separators.

### 19. Git Interaction Edge Cases

**Source**: Edge Cases (p570)

- Mars conflict markers inside git conflict markers — mars can't distinguish its `<<<<<<<` from git's
- Lock file merges on multi-dev teams — bad lock merge = orphaned files
- Solution: document that lock files should use git's merge=ours or similar strategy

### 20. Rerere Solves the Wrong Problem

**Source**: Conventions (p568)

**Decision**: Defer both rerere and patches/overlays. Solve when it's actually a problem.

---

## Scope Reshuffling Recommendation

Based on all 5 reviewers' input, the recommended v1 scope:

**Add to v1** (currently missing or deferred):
- Three-way merge (from v1.5)
- Name collision detection + error, with rename as escape hatch
- Cherry-picking / per-source `include`/`exclude`
- `mars list` (table stakes, trivial)
- `mars why` (trivial, high value)
- Security: commit SHA pinning + hash-change warnings
- Manifest-optional — filesystem convention is primary, `mars.toml` is enhancement

**Cut from v1** (defer or drop):
- `mars doctor`
- `mars repair`
- `mars migrate` (no users to migrate)
- Rename/breaking change detection
- Rerere and patches/overlays
- `mars outdated` / `mars update` / `mars upgrade`
- Semantic frontmatter-aware merge (use whole-file three-way merge in v1)
- Registry / stable package ID

**Effort estimate**: ~8-10 weeks for reshuffled MVP vs ~14-18 weeks as originally scoped.

---

## Architecture Highlights (p573)

The Rust architecture doc (`.meridian/work/agent-package-management/design/rust-architecture.md`) addresses many of the reviewer findings. Key decisions:

- **Single crate, lib + bin** — no workspace overhead
- **`ItemId = (kind, name)`** — stable identity decoupled from URL
- **`ItemKind` enum** — typed, match-exhaustive, extensible
- **`agents.local.toml`** — separate gitignored file for dev overrides
- **Atomic writes** — tmp + fsync + rename
- **`flock` advisory lock** — during apply phase only
- **`thiserror`** — structured errors with distinct exit codes
- **Lock stores commit SHA** alongside tag name
- **Sync pipeline as pure data flow** — pure transforms in the middle, I/O at edges
- **Separate `root` vs `install_target`** — future workspace support

---

## Open Questions (Not Yet Addressed by Any Reviewer)

1. **CI usage pattern** — `mars sync --frozen` (error if lock is out of date, don't fetch)?
2. **Partial sync failure** — source A syncs fine, source B fails. Roll back A or keep partial?
3. **Large file handling** — binary assets in agent packages?
4. **Offline mode** — sync from cache only when network is unavailable?
5. **`mars add --dev`** — dev-only sources not installed in CI/production?
