# catalog/agents-and-skills — Agent Profiles and Skill Loading

## Agent Profiles

**Source**: `.agents/agents/*.md` (markdown with YAML frontmatter)  
**Loader**: `parse_agent_profile(path)` → `load_agent_profile(name)` → `scan_agent_profiles()`  
**Module**: `src/meridian/lib/catalog/agent.py`

### AgentProfile Fields

```python
class AgentProfile(BaseModel):
    name: str               # from frontmatter "name", else file stem
    description: str        # from frontmatter "description"
    model: str | None       # model alias or ID; resolved to model_id at load
    harness: str | None     # explicit harness override
    skills: tuple[str, ...]         # skill names to inject
    tools: tuple[str, ...]          # allowed tools (passed to harness)
    disallowed_tools: tuple[str, ...]
    mcp_tools: tuple[str, ...]      # deduplicated
    sandbox: str | None
    effort: str | None      # one of: low, medium, high, xhigh
    approval: str | None    # one of: default, confirm, auto, yolo
    autocompact: int | None # 1–100 (percentage)
    body: str               # markdown body after frontmatter
    path: Path
    raw_content: str
```

### Loading Chain

`load_agent_profile(name)`:
1. Calls `scan_agent_profiles(project_root)` to build the full profile list
2. Matches by `path.stem == name` OR `profile.name == name`
3. Raises `FileNotFoundError` with expected path if not found (includes `meridian mars sync` hint)

`scan_agent_profiles()` scans `.agents/agents/*.md` sorted alphabetically. On name collision with conflicting content: first-seen wins, duplicate logs a warning and is skipped. Identical-content duplicates (e.g., symlinks) are silently deduplicated.

### Validation

Unknown `effort` values → warning, kept as-is.  
Unknown `approval` values → warning, set to `None` (not kept).  
`autocompact` out of 1–100 range → warning, set to `None`.

## Skills

**Source**: `.agents/skills/*/SKILL.md` (markdown with YAML frontmatter)  
**Registry**: `SkillRegistry` in `src/meridian/lib/catalog/skill.py`  
**Loaded lazily**: on first `list_skills()` or `load()` call

### SkillDocument Fields

```python
class SkillDocument(BaseModel):
    name: str          # from frontmatter "name", else parent directory name
    description: str   # from frontmatter "description"
    path: Path
    content: str       # full raw file content (including frontmatter)
    body: str          # content after frontmatter
    frontmatter: dict[str, object]
```

### SkillRegistry

Filesystem-backed, no SQLite. `db_path` property exists but points to an unused JSON path; the actual index is in-memory only.

Key methods:
- `list_skills()` → `[SkillManifest{name, description, path}]` sorted by name
- `load(names)` → `[SkillContent{name, description, content, path}]` in requested order
- `show(name)` → single `SkillContent`
- `reindex()` → force rescan from disk; rejects paths not in `skills_dirs`

`load(names)` raises `KeyError` for any unknown skill name — missing skills must be caught upstream.

Skills at launch time go through `resolve_skills_from_profile()` in `launch/resolve.py`, which separates resolved from missing names and generates a user-facing warning for missing skills.

## Skill Composition at Launch

`compose_skill_injections(skills)` in `launch/prompt.py` formats skill content for Claude's `--append-system-prompt` flag. Each skill block uses the filesystem path as a header:

```
# Skill: /abs/path/to/.agents/skills/foo/SKILL.md

<content>
```

`compose_run_prompt()` formats skill blocks slightly differently (using `skill.name` not path) for direct embedding in the prompt text.

Skills are deduplicated by name before loading (`dedupe_skill_names()`, `dedupe_skill_contents()`).

## Primary Launch Inventory

Primary launch startup context now includes a compact installed agent catalog derived from the same catalog layer rather than shelling out to CLI text parsing.

`build_primary_inventory_prompt(project_root)` in `launch/prompt.py`:
- scans installed agent profiles via `scan_agent_profiles(project_root)`
- renders a stable markdown block headed `# Meridian Agents`

This intentionally exposes only the top-level agent catalog at startup. Skills remain a lower-level launch/runtime mechanism and are not listed in the primary startup inventory, even though their content may still be loaded through the harness's normal launch path for the selected agent.

## Default Agent Policy

`resolve_agent_profile_with_builtin_fallback()` in `launch/default_agent_policy.py` handles the fallback chain when no agent is explicitly requested:

1. Explicit `--agent` → load or raise
2. `config.default_agent` → try load (warns if not found, continues)
3. Built-in default (`__meridian-subagent`) → warns if `.agents/` missing entirely

The `doctor` command checks for missing `.agents/agents/` and `.agents/skills/` and warns. Missing `__meridian-subagent` profile is specifically called out since it's the default spawn agent.

## Why Agent Profiles Are YAML Frontmatter in Markdown

Agent profiles live in `.agents/` (generated by `mars sync`) as markdown files. The profile body is the agent system prompt / instructions. Frontmatter holds metadata that meridian reads (model, skills, harness, etc.). This format lets humans read profiles naturally while machines parse the frontmatter. It also makes profiles version-controllable in plain text without a custom format.

Skills follow the same pattern: `SKILL.md` has a YAML frontmatter block with `name` and `description`, and the body is the skill content injected into prompts.
