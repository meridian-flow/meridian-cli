# Context Backend Feasibility Record

## Probed Assumptions

### Config File Locations

**Probe**: What config files exist and what precedence do they use?

**Finding**: The current config structure is:
- `<project-root>/meridian.toml` — project config, checked in
- `~/.meridian/config.toml` — user/global config

The requirements mentioned `.meridian/config.local.toml` but this doesn't exist in the codebase. The nearest pattern is `workspace.local.toml` which is gitignored.

**Verdict**: Design should introduce `<project-root>/meridian.local.toml` as a new layer matching the workspace.local.toml pattern. This provides the gitignored personal config the requirements need.

**Action**: Update design to use:
1. `<project-root>/meridian.local.toml` — personal, gitignored (NEW)
2. `<project-root>/meridian.toml` — project, checked in
3. `~/.meridian/config.toml` — global fallback

---

### Path Resolution Current State

**Probe**: How do fs_dir and work_dir currently resolve?

**Finding**: 
- `StatePaths.from_root_dir()` hardcodes `fs_dir = root_dir / "fs"` and `work_dir = root_dir / "work"`
- `resolve_repo_state_paths()` returns `.meridian/` as root_dir
- Environment variable override via `MERIDIAN_STATE_ROOT` shifts the entire state root, not individual paths

**Verdict**: Design is compatible — the resolver layer sits on top of `resolve_repo_state_paths()` and overrides specific paths when config is present.

---

### Environment Variable Integration

**Probe**: How are MERIDIAN_FS_DIR and MERIDIAN_WORK_DIR populated for spawns?

**Finding**: 
- `_normalize_meridian_fs_dir()` in `env.py` reads from env or falls back to `resolve_repo_state_paths().fs_dir`
- `_normalize_meridian_work_dir()` in `env.py` reads from env or falls back to work scratch dir resolution
- Explicit env var wins over any computed value

**Verdict**: Design integrates at the right point — modify the fallback resolution to use context config, not just state paths.

---

### Config Parser Extension Points

**Probe**: How extensible is the current config parser?

**Finding**:
- `MeridianConfig.settings_customise_sources()` chains multiple TOML sources
- `_normalize_toml_payload()` handles section-by-section parsing
- New sections can be added by extending the parser — pattern is well-established

**Verdict**: Low risk — adding `[context]` section follows existing patterns.

---

### Git Subprocess Safety

**Probe**: Are there existing patterns for subprocess execution in the codebase?

**Finding**:
- Harness adapters use subprocess for spawns
- No existing git integration in the codebase
- Python subprocess with `capture_output=True` is the standard pattern

**Verdict**: Git sync is new code but follows standard patterns. Need to handle:
- Git not installed (error gracefully)
- Network errors (warn and continue)
- Conflict markers (commit with markers, let user resolve)

---

## Open Questions

### Q1: Should local config be at `meridian.local.toml` or `.meridian/config.local.toml`?

**Analysis**: 
- `meridian.toml` is at project root, so `meridian.local.toml` is consistent
- `.meridian/config.local.toml` matches the requirements text but introduces inconsistency
- workspace.local.toml lives under `.meridian/` but config.toml is at project root

**Recommendation**: Use `<project-root>/meridian.local.toml` for consistency with `meridian.toml`.

### Q2: Should `{project}` substitution create the UUID if missing?

**Analysis**:
- `get_or_create_project_uuid()` exists and is safe
- Creating UUID on config resolution is a side effect
- Alternative: require explicit `meridian config init` first

**Recommendation**: Create UUID lazily — if user configures `{project}` path, they expect it to work. Document this behavior.

### Q3: What happens if git sync fails repeatedly?

**Analysis**:
- Network issues could cause repeated failures
- Logging every failure spams output
- Need backoff or rate limiting

**Recommendation**: Log first failure per session, then only on state change (success → failure, failure → success).

---

## Validated Constraints

1. **No breaking changes**: Zero config = current behavior — verified by path fallback design
2. **Env var precedence preserved**: Explicit `MERIDIAN_WORK_DIR` wins — verified in env.py logic
3. **Config precedence standard**: local > project > user — follows existing workspace.local.toml pattern
4. **Git sync non-blocking**: All git operations have error handling that continues session

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Config parsing regression | Low | High | Extensive fallback tests |
| Git sync blocks session | Medium | Medium | Timeout + continue on error |
| Migration data loss | Low | High | Copy-verify-delete, dry-run mode |
| Path resolution confusion | Medium | Low | Clear `meridian context` output |
