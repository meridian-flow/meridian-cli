# Auto-extracted Report

## Run Report

I scanned `/home/jimyao/gitrepos/prompts/meridian-base` for every `meridian context`, `meridian work current`, `MERIDIAN_WORK_DIR`, `MERIDIAN_FS_DIR`, `MERIDIAN_WORK_ID`, and `work_id` reference, then read the matching files with line numbers to identify what still assumes `work_id`-based path derivation or missing env projection.

### Files that need text updates

- [skills/meridian-cli/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md#L20), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md#L45), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md#L131): update the command-table row and the “Context Query” section so `meridian context` is documented as returning expanded paths (`work_dir`, `fs_dir`) instead of the old `{work_id, repo_root, state_root, depth}` shape; replace the example JSON, the `work_id` null note, the path-convention bullets, and the “Not injected” block so they no longer teach agents to derive paths from `work_id`.

- [skills/meridian-work-coordination/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-work-coordination/SKILL.md#L20), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-work-coordination/SKILL.md#L52): keep `meridian work current` as a work-id lookup only if that command’s contract is staying the same, but rewrite the artifact-placement section so it uses projected env vars or `meridian context`’s expanded paths instead of `WORK_ID=$(meridian work current)` plus `.meridian/work/<work_id>/`.

- [skills/meridian-spawn/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-spawn/SKILL.md#L58), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-spawn/SKILL.md#L184): update the prompt examples and the shared-files section to stop treating `.meridian/work/<work_id>/` as the only path source; they should use `MERIDIAN_WORK_DIR` / `MERIDIAN_FS_DIR` or the expanded context paths instead.

- [skills/agent-creator/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/SKILL.md#L296), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/SKILL.md#L307), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/SKILL.md#L312), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/SKILL.md#L319), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/SKILL.md#L325): rewrite the “Where it puts output” guidance and the “Paths: query context, derive from convention” section so agents describe output locations in terms of `work_dir` / `fs_dir`, not `work_id`; remove the claim that `MERIDIAN_WORK_DIR`, `MERIDIAN_WORK_ID`, and `MERIDIAN_FS_DIR` are not projected.

- [skills/agent-creator/resources/example-profiles.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/resources/example-profiles.md#L117), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/resources/example-profiles.md#L159): update the orchestrator example so it points at expanded paths and projected env vars instead of telling the reader to get `work_id` from `meridian work current` and derive `.meridian/work/<work_id>/`.

- [skills/agent-creator/resources/anti-patterns.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/resources/anti-patterns.md#L94), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/resources/anti-patterns.md#L130), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/resources/anti-patterns.md#L137), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/resources/anti-patterns.md#L149): replace the old anti-pattern example that saves to `.meridian/work/$(meridian work current)/plan.md`, the “harness exports these automatically” wording, and the explanation that `MERIDIAN_WORK_DIR` / `MERIDIAN_FS_DIR` are unprojected; this section should be rewritten for the restored env projection model.

- [skills/meridian-cli/resources/debugging.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/debugging.md#L40), [file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/resources/debugging.md#L67): update the shared-files example and state-layout bullets so they no longer tell agents to query `work current` and guess `.meridian/work/<work_id>/`; those examples should point at projected env vars or `context`-derived expanded paths.

- [agents/meridian-default-orchestrator.md](file:///home/jimyao/gitrepos/prompts/meridian-base/agents/meridian-default-orchestrator.md#L117), [file:///home/jimyao/gitrepos/prompts/meridian-base/agents/meridian-default-orchestrator.md#L159): update the profile description and body so the orchestrator uses `work_dir` / `fs_dir` directly instead of describing path resolution as “get `work_id` from `meridian work current` then derive `.meridian/work/<work_id>/`”.

### Related references that likely stay, unless `meridian work current` itself changes

- [skills/meridian-cli/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-cli/SKILL.md#L49), [skills/meridian-work-coordination/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/meridian-work-coordination/SKILL.md#L20), [skills/agent-creator/SKILL.md](file:///home/jimyao/gitrepos/prompts/meridian-base/skills/agent-creator/SKILL.md#L312): these still describe `meridian work current` as returning `work_id`. If that command is staying an identity lookup, those lines can remain; if you also change `work current`, they need a second pass.

### Files with no relevant update needed from this sweep

- `agents/meridian-subagent.md` had no `context` / work-path / env-var references.
- `README.md` had no matching path/env-var guidance.
- `skills/meridian-cli/resources/configuration.md` only has the generic `MERIDIAN_*` precedence note; it does not teach the old work-path projection model.

### Verification

- Ran repository-wide `rg` sweeps and line-numbered reads only.
- No edits were made.
- No tests were run; this was a documentation inventory pass in a read-only workspace.

### Blockers

- Filesystem is read-only, so I could not apply the documentation updates directly.
