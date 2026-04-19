# Decisions Log

## 2026-04-18: Schema Design

**Decision:** Use `work_dir` (expanded path) instead of `work_id` in both `ContextOutput` and `WorkCurrentOutput`.

**Reasoning:** One model is cleaner — query returns paths, agents use literals. No derive-from-work_id step.

**Alternatives rejected:**
- Returning both `work_id` and `work_dir` — adds complexity, agents would have to choose
- Env var projection only — can't handle work switching (subprocess can't set parent env)

## 2026-04-18: context_roots source

**Decision:** Use `get_projectable_roots()` for context_roots — returns only enabled + existing roots.

**Reasoning:** Matches what launch projection uses. No point returning disabled or missing roots.

## 2026-04-18: Env var projection correction

**Decision:** Skills should teach query-only pattern, NOT env var projection for WORK_DIR/FS_DIR.

**Reasoning:** Per requirements: "Do NOT project MERIDIAN_WORK_DIR, MERIDIAN_FS_DIR, or MERIDIAN_WORK_ID. These stay dead."

**Fix applied:** p15 removed all env var claims from meridian-base skills.

## 2026-04-18: Deferred items

**Decision:** meridian-dev-workflow repo, CHANGELOG.md, and docs/ updates deferred.

**Reasoning:** Out of scope for this work item. The reviewer identified these as needing updates, but they're in a different repo or separate documentation concerns. CLI and meridian-base skills are the authoritative contract.
