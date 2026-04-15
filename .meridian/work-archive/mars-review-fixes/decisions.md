# Decision Log

## D1: Canonicalize comparison — match on (Ok, Ok) only

**Context:** F4 found that `canonicalize().ok() == canonicalize().ok()` treats two failures as equal.

**Decision:** Use `match (resolved.canonicalize(), expected.canonicalize())` and only return true on `(Ok(a), Ok(b)) if a == b`. All other cases (any Err) return false.

**Alternatives rejected:**
- *Compare raw paths when canonicalize fails* — raw paths may have `.`, `..`, or symlinks, making textual comparison unreliable.
- *Return error when canonicalize fails* — too strict. The managed subdir may legitimately not exist yet (empty `agents/` not created). Treating failure as "not matching" is correct — if we can't confirm they're the same, they're not confirmed the same.

**Note:** `scan_link_target()` in link.rs already uses the correct pattern. `unlink()` was fixed in a prior commit. Only `check_link_health()` in doctor.rs still has the bug.

## D2: Sync crash safety — tolerance over reordering

**Context:** F12 found that crash during apply leaves config updated but lock/disk inconsistent.

**Original proposal:** Move config save to after apply+lock.

**Rejected by review (p715/gpt-5.4):** `mars sync` runs with `mutation: None` — it reads config as-is and doesn't replay the original mutation. If lock was written but config wasn't, lock has items config doesn't request → sync would remove them, undoing the apply. This creates a worse recovery model.

**Decision:** Keep the current order (config first, then apply, then lock). Make `check_unmanaged_collisions` tolerant of partially-installed files — when a planned install matches existing disk content (same hash), skip the collision error.

**Why this works:** The current order's crash recovery relies on `mars sync` re-resolving from the new (already-saved) config. The only thing that blocks re-sync is unmanaged-collision detection flagging the partially-installed files. Making that check hash-aware lets sync converge.

**Alternatives rejected:**
- *Reorder config save to after apply* — breaks recovery as described above
- *Journal file* — unnecessary complexity; hash-aware collision check achieves the same result in ~10 lines

## D3: Rename-old pattern for atomic_install_dir vs. copy-on-write

**Context:** F13 found a gap between `remove_dir_all(dest)` and `rename(tmp, dest)`.

**Decision:** Rename dest to `.old`, rename new into place, then delete `.old`. Rollback on failure.

**Alternatives rejected:**
- *Copy-on-write / reflink* — requires filesystem support (btrfs/APFS), not portable.
- *Keep both old and new, swap via rename* — same as chosen approach, just different naming. We use `.{name}.old` prefix to keep it hidden.
- *Accept the gap since sync.lock is held* — true that another mars process can't race, but a crash still leaves the dir missing. Sync lock doesn't protect against crashes.

## D4: Skip symlinks in scanning rather than follow with depth limit

**Context:** F3 found that check/doctor follow symlinks to arbitrary locations.

**Decision:** Skip symlinked entries with a warning. Do not follow them.

**Alternatives rejected:**
- *Follow with depth/size limit* — complicated to implement correctly. What's the right limit? What if the symlink points to a valid skill that happens to be large? The limit becomes a heuristic, violating AGENTS.md principle 4.
- *Resolve and validate the target* — still follows the symlink, which is the core risk. A symlink to `/dev/random` would hang regardless of validation.
- *Error on symlinks* — too strict. Users may have legitimate reasons for symlinks (dev overrides). Warning + skip is informative without blocking.

## D5: Containment check only for auto-discovered roots

**Context:** F1 found that symlinked `.agents/` can redirect project_root.

**Decision:** Validate containment in `find_agents_root()` for auto-discovered roots only. `--root` bypasses the check.

**Alternatives rejected:**
- *Always validate, including --root* — `--root` is explicitly "I know what I'm doing." Blocking it breaks legitimate cross-project operations.
- *Never canonicalize managed_root* — breaks symlink comparison in link.rs (relative vs absolute paths don't match).
- *Store both canonical and original paths* — adds complexity throughout the codebase for a rare edge case. The containment check at the boundary is simpler.

## D6: Per-entry flock for git cache vs content-addressed entries

**Context:** F14 found that git clone cache entries can race across processes.

**Decision:** Use `FileLock` per cache entry (`{url_dirname}.lock`) around fetch+checkout.

**Alternatives rejected:**
- *Content-addressed git entries (`{url}_{sha}/`)* — requires full repo copy per version, breaks shallow clone optimization, wastes disk.
- *Global cache lock* — too coarse. Different URLs should be fetchable concurrently.
- *Accept the race* — corruption risk is real when two repos share a git source. The lock is cheap insurance.

## D7: Canonicalize cwd before walk-up (review S1)

**Context:** Review (p716/opus) identified that ancestor-directory symlinks bypass the containment check.

**Decision:** Canonicalize `cwd` at the start of `find_agents_root` before the walk-up loop. This means the walk-up operates on real paths, catching both `.agents/` symlinks and ancestor symlinks.

**Tradeoff:** Canonicalizing cwd changes what paths are displayed in error messages (canonical instead of user-typed). Acceptable — error clarity is more important than path familiarity in this context.

## D8: Different symlink policies for check vs doctor (review S3)

**Context:** Review (p716/opus) noted that doctor validates installed state where mars-created symlinks are normal, while check validates source packages where symlinks are suspicious.

**Decision:** check.rs skips all symlinks with "source packages should not contain symlinks." doctor.rs skips individual symlinks within agents/skills with a different message. doctor's existing `check_link_health()` continues to validate top-level link symlinks.

**Why not identical policies:** doctor needs to validate linked installations. A blanket skip-all-symlinks in doctor would skip every linked agent and skill, defeating its purpose.

## D9: Symlinks in link target dir are informational (review S5)

**Context:** Review (p716/opus) noted that treating symlinks in the target dir as conflicts is hostile UX — users may organize agents with symlinks.

**Decision:** `.follow_links(false)` for safety, but skip symlinks silently rather than treating them as conflicts. Symlinks survive the merge-and-link process since only regular files are compared and moved.

## D10: Tier 3 deferred — extract shared scanning after symlink work

**Context:** F19/F20 are refactoring findings with no correctness impact.

**Decision:** Defer to backlog. A shared `is_symlink` helper is added in Phase 4b to prevent immediate divergence (per review S6), but the full scanning extraction is deferred.

**Reasoning:** The scanning code will change during F3 implementation. Full extraction before all scanning changes stabilize means doing the work twice. The shared helper is the minimal investment to prevent the worst duplication.

## D11: atomic_install_dir — honest about the remaining gap

**Context:** Review (p715/gpt-5.4) noted the overview claimed the pattern "eliminates the gap" but the crash analysis shows dest can still be absent.

**Decision:** Updated docs to accurately describe the improvement: the gap shrinks from a potentially long `remove_dir_all` to a single `rename` syscall. The `.old` sentinel makes the state diagnosable and `mars sync` recovers by reinstalling. No false claims of elimination.
