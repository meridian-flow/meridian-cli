# CLI Surface Blast Radius: `meridian spawn report create`

## Assessment

Deletion blast radius: **medium**.

The core report read path survives because `spawn show` reads `report.md` on demand and the finalization pipeline already auto-wraps assistant-message reports as `# Auto-extracted Report`. But deleting `report.create` removes a public CLI/MCP write API that is explicitly taught to agents and documented in the user-facing surface.

## 1. Agent Prompts / Profiles

- Direct `meridian spawn report create` instruction appears in **1 `.agents` file** with **2 exact hits**:
  - `.agents/skills/meridian-spawn/resources/advanced-commands.md:57`
  - `.agents/skills/meridian-spawn/resources/advanced-commands.md:60`
- The same resource also teaches the surrounding report flow:
  - `.agents/skills/meridian-spawn/resources/advanced-commands.md:44` says `spawn show` includes the report by default.
  - `.agents/skills/meridian-spawn/resources/advanced-commands.md:51` teaches `spawn report show`.
  - `.agents/skills/meridian-spawn/resources/advanced-commands.md:54` teaches `spawn report search`.
- The launch prompt injected into spawned runs also tells every agent to use the command:
  - `src/meridian/lib/launch/prompt.py:103-115`
- `meridian-cli` skill documents the report concept at a high level, but does not itself teach the `create` command:
  - `.agents/skills/meridian-cli/SKILL.md:18`
  - `.agents/skills/meridian-cli/SKILL.md:69`

## 2. Source Code

- CLI wiring:
  - `src/meridian/cli/report_cmd.py:91-116` registers `report.create`, `report.show`, and `report.search`; `default_handler` points to create.
  - `src/meridian/lib/ops/manifest.py:321-352` exposes the same set and maps them to MCP names.
- Report file storage:
  - `src/meridian/lib/ops/report.py:147-165` writes `.meridian/spawns/<id>/report.md`.
  - `src/meridian/lib/ops/report.py:168-223` reads and searches that same file.
- Read path used by `spawn show`:
  - `src/meridian/lib/ops/spawn/query.py:76-88` reads `report.md` on demand.
  - `src/meridian/lib/ops/spawn/models.py:383-440` appends the report body to the detail view.
  - `src/meridian/lib/launch/process.py:810-813` notes the report is read on-demand via `spawn show`, not inlined.
- Finalization path:
  - `src/meridian/lib/launch/extract.py:52-77` writes `# Auto-extracted Report` when the report content came from the assistant message.
  - `src/meridian/lib/launch/report.py:140-171` prefers `report.md`, then extractor output, then the last assistant message.
- I did not find any internal runtime callers to `report_create_sync` beyond the CLI/MCP wrappers above.

### No `report.list`

- Search across `src/meridian/`, `docs/`, `.agents/`, and work artifacts found no live `report.list` / `spawn report list` implementation.
- The report command family in `src/meridian/lib/ops/manifest.py:321-352` is create/show/search only.

## 3. Documentation

- Direct CLI docs:
  - `docs/commands.md:35-40` documents `meridian spawn report create` and `meridian report search`.
  - `docs/troubleshooting.md:44-51` tells users to use `meridian report search`.
- MCP docs:
  - `docs/mcp-tools.md:24-34` lists `report_create`, `report_show`, and `report_search`.
  - `docs/mcp-tools.md:88-126` gives examples for `report_create`, `report_show`, and `report_search`.
- No direct `spawn report create` mention was found in `README.md`, `CLAUDE.md`, `AGENTS.md`, or `CHANGELOG.md`.

## 4. Work Artifacts / History

- Live work area:
  - **2 files**, **5 hits**.
  - Main live reference: `.meridian/work/spawn-finalize-bugs/requirements.md:48-67,77-78` argues for deleting `meridian spawn report create` and making the auto-extracted final message canonical.
- Archive:
  - **23 files**, **30 hits**.
  - Representative refs:
    - `.meridian/work-archive/meridian-base-consolidation/design/04-cli-help-gaps.md:86-91`
    - `.meridian/work-archive/orchestrator-restructure/design/architecture/root-topology.md:52`
    - `.meridian/work-archive/orchestrator-restructure/design/architecture/orchestrator-topology/planning-and-review-loop.md:72`
    - `.meridian/work-archive/orchestrator-restructure/design/architecture/orchestrator-topology/design-phase.md:85`
    - `.meridian/work-archive/agent-shell-mvp/design.archived/events/flow.md:259`
    - `.meridian/work-archive/orchestrator-restructure/reviews/extracted/r3-parallelism.md:360`
- These records show the command has been treated as a standard terminal-report emission path in prior design and review work.

## 5. Actual Usage Evidence

- Direct grep over the current `.meridian/spawns/*/output.jsonl` corpus found **0 matches** for `meridian spawn report create` or `spawn report create`.
- Sample recent `output.jsonl` files inspected (`p455`, `p1765`, `p1692`) did not contain the command.
- Interpretation: there is no evidence in the current log corpus that agents are self-invoking the command frequently.

## 6. Alternate Derived-Report Path

- `src/meridian/lib/launch/extract.py:63-77` writes `# Auto-extracted Report` when the report content came from the assistant message.
- `src/meridian/lib/launch/report.py:140-171` prefers `report.md` and falls back to the assistant message.
- `src/meridian/lib/ops/spawn/query.py:76-88` reads `report.md` directly for `spawn show`.
- `src/meridian/lib/ops/spawn/models.py:383-440` appends the report body to `spawn show` output.

## What Would Break

- Users and agents calling `meridian spawn report create` from the CLI.
- MCP clients using `report_create`.
- The universal report-instruction path in spawned prompts unless updated first.
- User-facing docs and work-artifact references would become stale.
- `spawn show` and report reading do **not** break; they already consume `report.md` and the auto-extracted report path.

## Recommendation

- Delete `report.create` only if the goal is to make the final assistant message canonical and treat `report.md` as derived cache.
- Before deletion, update:
  - `src/meridian/lib/launch/prompt.py` to remove the explicit create-command instruction.
  - `src/meridian/cli/report_cmd.py` and `src/meridian/lib/ops/manifest.py` to drop the CLI/MCP write verb.
  - `docs/commands.md`, `docs/mcp-tools.md`, and `.agents/skills/meridian-spawn/resources/advanced-commands.md`.
- Keep `report.show` and `report.search` if report browsing remains useful.
- I would not expect a runtime regression in `spawn show`, but I would expect prompt/docs/tooling breakage until the instruction surface is cleaned up.
