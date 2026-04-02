# Source Fetch Rewrite: Decisions

## D1: merge/mod.rs must be in scope

**Context**: Reviewing git2's dependency surface for the source fetch rewrite. The design identified 6 files but missed `merge/mod.rs`.

**Decided**: `merge/mod.rs` is a critical file to modify — it uses `git2::merge_file()` for three-way conflict resolution during sync. Must add a pure-Rust merge library (e.g., `diffy`, `similar`) to the dependency list and include merge rewrite in the implementation plan.

**Evidence**: The [rust-architecture spec](../agent-package-management/design/rust-architecture.md) explicitly documents that merge wraps `git2::merge_file()`. The sync pipeline calls this from `apply.rs` during `PlannedAction::Merge`.

## D2: Non-GitHub HTTPS sources fall back to system git, not archive

**Context**: The design handles only GitHub archive URLs. Non-GitHub HTTPS hosts (GitLab, Gitea, self-hosted) would get incorrect archive URLs that 404.

**Decided**: Archive download is a GitHub-specific optimization. All other HTTPS hosts fall back to `git clone --depth 1`, which works with any git-compatible host. This means the `SourceFormat` classification needs a host check in addition to the URL scheme check.

**Alternatives rejected**:
- **Error on non-GitHub HTTPS**: Too restrictive — users with GitLab sources would be blocked entirely.
- **GitLab/Gitea archive patterns in v1**: Over-scoped. Each host has different archive URL patterns and edge cases. System git handles them all.

## D3: Two URL types — FetchUrl (stored) + SourceUrl (derived)

**Context**: The v1 refactor defines `SourceUrl` as protocol-stripped for identity comparison. This design needs protocol-included URLs for fetch dispatch. The two goals conflict on whether `agents.toml` stores the scheme.

**Decided**: `FetchUrl` (with scheme) is stored in `agents.toml`. `SourceUrl` (scheme-stripped) is derived at load time for identity comparison. This satisfies both designs: fetch dispatch uses the scheme, deduplication ignores it.

**Why not store `format` field**: The `format = "github"` proposed in overview.md is redundant — format can be inferred from the URL. Storing it creates a field users can set incorrectly. Removed from the design.

## D4: Legacy URL migration via auto-upgrade on read

**Context**: Existing `agents.toml` files store bare URLs like `github.com/owner/repo` (protocol stripped by current `normalize()`). New design stores `https://github.com/owner/repo`.

**Decided**: Auto-detect and normalize at config load time. Bare domains get `https://` prepended. Next config write persists the new format. This is non-breaking — old configs parse correctly, new writes upgrade the format silently.

## D5: Lock parse failure handling differs between repair and sync

**Context**: The design proposes treating corrupt lock as empty for the repair command.

**Decided**: Only `mars repair` treats a corrupt lock as empty (with a warning). Normal `mars sync` errors with "lock is corrupt — run `mars repair`". This prevents silently discarding lock provenance during routine operations. Version mismatch (lock from newer mars) always errors with a clear message.

**Why not always treat as empty**: Lock files record pinned versions, commit SHAs, and checksums. Silently discarding this data during normal sync means the next resolve may pick different versions — a reproducibility violation that's hard to detect.

## D6: Cache atomicity via temp+rename

**Context**: mars's crash-only design principle requires atomic writes. Archive extraction without atomicity leaves partial content on kill.

**Decided**: Extract archives to `{cache_path}.tmp.{pid}`, then atomic `rename()` to final path. If rename fails because another process won the race, delete our temp dir — the winner's content is valid. Same pattern as mars's existing `fs/` module for file writes.

## D7: Tarball extraction must sanitize paths and reject symlinks

**Context**: Security review p652 found symlink traversal vulnerabilities in the discovery module. Tarball extraction is another attack surface.

**Decided**: During archive extraction, reject symlinks and hard links, reject `..` path components, reject absolute paths, and strip the first path component (the `{repo}-{sha}/` prefix). This addresses the source-level symlink concern from the security review within fetched archives.
