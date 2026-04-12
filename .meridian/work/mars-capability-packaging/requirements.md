# mars-capability-packaging — Requirements

**Status**: Design hand-off. To be picked up by a separate dev-orchestrator session.
**Origin**: Fell out of the `agent-shell-mvp` design conversation (c1046, 2026-04-08). Originally scoped as `mars-mcp-packaging` with MCP as the headline feature, then rescoped after the user pointed out that MCPs are the wrong headline — CLIs are better for most developer work, and MCP should be a secondary capability kind, not the primary one.

## TL;DR

Mars currently ships two `ItemKind`s: `Agent` and `Skill`. It needs **several new capability kinds**, with MCP being one of them but not the first. The primary V0 capability kind to add is **CLI dependencies** — "this pack expects these CLIs to be available in the project" — delegating install to `uv`, `npm`, `cargo`, or the appropriate package manager. MCP support is the V0 secondary addition, driven by the researcher-track interaction-layer extensions from `agent-shell-mvp` decision D26.

This consolidates three existing mars-agents issues, reframed around the new priority order:

- **haowjy/mars-agents#2** — distribute tool definitions as first-class package artifacts. **Primary**, now reframed as "ship CLI dependencies (and later, MCPs) as first-class mars items."
- **haowjy/mars-agents#3** — support MCP integration as a package-managed capability. **Secondary**, still needed for the researcher track's stateful interaction-layer extensions.
- **haowjy/mars-agents#1** — sync package-defined permissions into tool/runtime environments. **Deferred**, reserve the extension point in the schema so it doesn't require migration later.

## Strategic Framing: The Full Picture (D21–D30)

The originating session accumulated **ten strategic decisions** (D21–D30 in `agent-shell-mvp/decisions.md`) that together define the posture this work item must design against. **Read `.meridian/work/agent-shell-mvp/decisions.md` entries D21–D30 in full before starting design work** — the summary below is not a substitute.

### The decisions, in one line each

- **D21** — agent-shell-mvp replaces meridian-flow as the first MVP. "Do things that don't scale." BYO-harness-subscription, zero hosting cost, validate product direction before reviving the hosted platform.
- **D22** — agent/skill/MCP/CLI bundling via mars is the primary moat. The pack is the unit of distribution, not the MCP.
- **D23** — marketplace is the acquisition funnel for the eventual hosted platform. Same packs, different runtime.
- **D24** — concierge package authoring for the first cohort. Both tracks (developer, researcher) get hand-written reference packs.
- **D25** — shell's frontend is a generic chat UI with a renderer plugin surface. Zero domain code in the shell.
- **D26** — extensions are composite (frontend component + MCP server) pairs with bidirectional event flow. **This is where MCPs become load-bearing** — researcher-track interaction layers can't be CLIs.
- **D27** — CLI plugins / harness adapters deferred but not rejected. Mars `ItemKind` must stay extensible.
- **D28** — governing principle: architecture wide, implementation narrow. Every seam is a published versioned contract from V0.
- **D29** — implementation SRP/SOLID mirrors strategic boundaries. Mars and meridian-channel are separate products with separate release cadences.
- **D30** — **ship capabilities at the highest useful granularity.** CLI > SDK method > verbose MCP. This rescopes *this* work item from "MCP-first" to "CLI-deps first, MCP second, under a strict granularity rule."

### Why this work item exists in its current shape

Two observations from the originating session drove the rescope:

1. **The developer track is already in production.** meridian-channel plus mars plus the agents and skills in `meridian-base/` and `meridian-dev-workflow/` are already dogfooding through the user's daily work. What's missing for a second developer to adopt it is mostly packaging polish — and the packs a second developer wants are **agent + skill + CLI-deps**, not agent + skill + MCP. MCPs are largely overkill for developer workflows that already have great CLIs (pytest, ruff, git, uv, gh, jq, rg, etc.).

2. **MCP tool-surface sprawl is a design smell.** Playwright's MCP exposes ~25 micro-tools (`browser_click`, `browser_hover`, etc.), and every one of them eats context budget every single turn the MCP is loaded. A single `browser_run_code` that accepts a JS snippet would be strictly better because the model already knows JS, composition happens in one call, and the tool description fits in three sentences. This generalizes: **ship capabilities at the highest useful granularity, and in the rare cases where MCP is the right answer, ship the fewest richest operations that cover the interaction model.**

The researcher track (the other half of the dual-track MVP per D25/D26) DOES need MCP support, but for genuinely stateful bidirectional interaction cases — DICOM viewer ↔ agent, 3D mesh segmentation editor ↔ agent — where a CLI fundamentally cannot work. Those cases force MCP into V0, but only for that track and only for that category of interaction.

## V0 Scope

### Primary (V0 essential, developer track unblocker): CLI-deps

**New `ItemKind::CliDependency`** (or equivalent — naming is the receiving dev-orchestrator's call).

- Packages declare CLI dependencies as first-class items: `{kind: "cli-dep", manager: "uv", spec: "pytest>=7,coverage>=7"}` or similar shape.
- Supported managers for V0: **`uv` (Python) as the flagship**, with the schema designed so `npm`, `cargo`, `brew`, and `system` (apt/dnf/whatever) can be added without migration.
- Install semantics: `mars sync` delegates to the declared manager to install into the **project's normal dependency surface** (project's `pyproject.toml` for uv, `package.json` for npm, etc.). **Mars does not own a venv or a lock file.** The project is a normal Python (or Node, or Rust, etc.) project; mars just edits the manifest and delegates install.
- No custom resolution logic. If two packs declare conflicting Python version constraints, `uv` reports the conflict and mars surfaces it cleanly. V0 does not try to be smarter than `uv`.
- Reconciliation semantics: `mars sync` run twice converges. Re-installing a pack that's already installed is a no-op. Uninstalling a pack removes the dependencies it added unless another installed pack still declares them.

**The first reference developer pack uses ONLY this capability kind** — no MCPs, no wrapper scripts, no custom tools. See D30 for the shape (TDD pack example).

### Secondary (V0 necessary for researcher track): MCP servers

**New `ItemKind::McpServer`** (or equivalent).

- Packages declare MCP servers: `{kind: "mcp-server", transport: "stdio", command: [...], env: {...}}`.
- V0 scope: Python MCP servers via stdio transport. Non-Python MCPs (Node, Rust binaries, Docker images) must not be precluded by the schema but are not implemented in V0.
- Mars installs the MCP server's Python dependencies into the project's `pyproject.toml` via uv (same delegation as CLI-deps).
- Mars emits per-harness MCP config files under `.agents/mcp/` (or equivalent) that each harness adapter can consume at spawn time. Formats per harness:
  - Claude Code: `--mcp-config` JSON pointer
  - Codex app-server: thread/start config stanza
  - OpenCode: session config stanza
- Composite extension support (per D26): a pack can declare an MCP server and a frontend renderer together as a **composite extension** — one conceptual unit, two artifacts. The exact schema for this is the receiving dev-orchestrator's design call, but the capability must be expressible.

**MCP design guidance (not schema-enforced, documented as review criteria):**

Per D30, every MCP that ships through mars must pass a review checklist during concierge authoring:

1. **Could this be a CLI instead?** If yes, it should be a CLI-dep pack, not an MCP.
2. **Does this MCP expose the fewest rich operations that cover the interaction model?** If the operation list has more than ~5 entries, there's probably a collapse opportunity.
3. **Does the MCP's state actually need to persist across calls?** If each call is self-contained, the MCP should collapse to a CLI.
4. **Does each operation earn its context budget?** Every entry in the MCP's tool list costs tokens on every turn it's loaded.

These gates are judgment calls, not schema constraints. They belong in package author documentation and in reviewer checklists, not in mars's validator.

### Tertiary (V0 minimum, stubbed but not implemented): extensibility hooks

Per D27 and D28, the mars `ItemKind` enum must stay extensible. V0 reserves schema hooks for future kinds without committing to implementation:

- `ItemKind::FrontendExtension` (researcher track, V0 for the shell but may not block this work item) — composite with MCP per D26
- `ItemKind::WorkflowTemplate` (V1) — declarative recipe the agent follows
- `ItemKind::CliCommand` (V2, per D27) — in-process meridian-channel extension, gated on trust infrastructure

The schema must not hardcode the current list of kinds in a place that would require rewriting when new kinds are added. Use enum extensibility and dispatch tables; never use closed `match` statements on the item kind outside a single dispatch function.

### Explicitly Out of Scope (V0)

- **Non-Python CLI-deps** (npm, cargo, brew, system) — schema hooks required, implementation deferred
- **Non-stdio MCP transports** (HTTP, SSE, WebSocket) — schema hooks required, implementation deferred
- **Signing, provenance, package authentication** — reserve hooks, no-op in V0. Moves up to V0.5 per D23 when the funnel surface becomes real.
- **Marketplace UI / discovery service** — V0 discovery is direct URLs in the user's config. A central index is a V0.5 concern.
- **Dependency conflict resolution beyond what uv/npm/cargo do natively** — delegate to the ecosystem tool. Mars is a coordinator, not a solver.
- **Mars owning a venv or any sandbox** — per the "project is a normal Python project" constraint in D28. The project's own `.venv/` or equivalent is the install target. Mars never owns runtime isolation.
- **In-process items** (CliCommand, HarnessAdapter) — per D27, reserved for after trust infrastructure exists.

## Constraint: "Project Is a Normal Python Project"

The consuming project is a normal Python project (or Node, or Rust, etc.) with its own dependency manifest at the repo root. Meridian-channel is installed via `uv tool install meridian-channel` and runs from the user's system tools. Mars runs inside that project.

**Implications the design must not violate:**

- Mars edits the project's `pyproject.toml` (for Python deps) and lets `uv sync` handle install. Mars does not run its own package manager.
- Mars does not own any venv. No `~/.meridian/venvs/...`, no mars-owned sandboxes, no hidden dependency directories. The project's `.venv/` at the repo root is the install target.
- `mars sync` is idempotent and reconciles with the current state of the project's manifest. Running it twice produces the same result.
- Mars's job is "edit manifests + materialize config files into `.agents/`", not "run a package manager." Delegation over implementation.

## Cross-Reference: agent-shell-mvp

The consumer side of this contract lives in `.meridian/work/agent-shell-mvp/`. Relevant files:

- `decisions.md` — the full decision log D1–D30 (this work item inherits D21–D30)
- `requirements.md` — the shell's overall goals, now understood as the researcher-track V0 product
- `findings-harness-protocols.md` — corrected harness picture and mid-turn injection findings
- `synthesis.md` — design convergence output from p1101
- `design/` — current flat design corpus, in the middle of a hierarchical restructure + D21–D28 correction pass (spawn `bhvk2iljf`)

The correction pass running against `agent-shell-mvp/design/` is restructuring the shell design around D21–D28. It is NOT waiting on this work item — it treats the mars capability contract as "reference the mars-capability-packaging work item for specifics, leave pointers." These two work items run in parallel.

## Prior Art

CLAUDE.md line 129 cites `.meridian/work/agent-package-management/design/` as the mars baseline. The work tree also contains: `mars-refactor-design`, `mars-structural-refactor-design`, `mars-root-config-redesign`, `mars-distribution`, `mars-source-fetch-rewrite`, `mars-agents-v1-refactor`, `mars-add-design-review`, `mars-link-design` (done).

The incoming design-orchestrator should:

1. Start from `agent-package-management/design/` as the authoritative mars baseline.
2. Skim the other mars-* work items only as needed to understand what's superseded.
3. Ask the user which are still canonical if the corpus is ambiguous — don't guess.
4. Read D21–D30 in `agent-shell-mvp/decisions.md` in full before designing anything.

## Open Questions for the Design Phase

1. **Capability kind naming**: `CliDependency` vs `CliDep` vs `ToolDep` vs something else. The receiving dev-orchestrator picks.
2. **Composite extension schema**: how does a package declare "this MCP and this frontend component belong together under kind X"? Per D26, composite extensions are a real requirement; the schema shape is open.
3. **CLI-deps conflict surfacing**: when two packs declare conflicting specs (e.g., `pytest>=7` and `pytest<7`), what does mars do? Probably: delegate the conflict detection to uv and surface the error cleanly with pointers to both packs. Confirm.
4. **MCP config file layout**: single merged file, one file per MCP, one file per harness? Affects how mars sync reconciles partial installs.
5. **Discovery at spawn time**: does `meridian spawn` read the materialized config directly, or does each harness adapter own discovery? This impacts the mars ↔ meridian-channel seam.
6. **Extensibility hooks for V1/V2 kinds**: what's the minimum schema scaffolding that lets `FrontendExtension`, `WorkflowTemplate`, and `CliCommand` be added later without migration?
7. **Delegation contract for package managers**: when mars calls `uv add`, what's the invocation shape, error handling, and idempotence story? Same question for `npm install`, `cargo add`, etc. when those kinds are added.

## Deliverables

- Design docs under `.meridian/work/mars-capability-packaging/design/` (hierarchical folder structure, progressive disclosure per the same discipline as agent-shell-mvp) covering:
  - Capability kinds as a concept — why multiple kinds, how they compose in a pack
  - CLI-deps detailed design (V0 primary)
  - MCP server detailed design (V0 secondary, including composite extension support)
  - Mars ↔ project contract — manifest editing, delegation, reconciliation
  - Per-harness config emission — Claude / Codex / OpenCode
  - V0 validation plan — the TDD pack (or whichever developer pack is picked first) as the CLI-deps validation, and the researcher-track PyVista interaction pack as the MCP validation
- Decision log capturing tradeoffs around the open questions
- Implementation plan phases (handed off to impl-orchestrator later, not part of this work item)

## Handoff Note to the Receiving dev-orchestrator

The originating session (c1046) hit context limits and the user is passing this work to a fresh dev-orchestrator session. The full reasoning behind this work item lives in:

- This requirements.md (the distilled, post-rescope version)
- `.meridian/work/agent-shell-mvp/decisions.md` entries D21–D30 — **read all ten, not just the summary above**
- `.meridian/work/agent-shell-mvp/findings-harness-protocols.md` — harness protocol picture, including which harnesses natively support MCP
- `.meridian/work/agent-shell-mvp/requirements.md` — the shell's goals, which this work item supports
- GitHub issues haowjy/mars-agents#1, #2, #3 — the pre-existing feature requests this consolidates
- CLAUDE.md line 129 — confirms mars design lives in meridian-channel, not the mars-agents repo
- `../mars-agents/src/types.rs` — current `ItemKind` enum, starting point for schema extension

**Recommended first moves for the receiving dev-orchestrator:**

1. Read `agent-shell-mvp/decisions.md` D21–D30 in full.
2. Read `agent-package-management/design/` for prior art.
3. Skim `../mars-agents/src/` to understand the current schema and sync engine shape.
4. Confirm scope with the user — specifically: "is CLI-deps really V0 primary and MCP V0 secondary, or do you want to see both sized and then pick?" Don't assume the prioritization is final until the user confirms.
5. Spawn a design-orchestrator with the full context.

**Do not** start with the MCP schema. Start with CLI-deps, validate it against the TDD pack shape from D30, and only then move to MCPs. If MCPs start pulling scope, push back — per D30, they're the secondary kind, not the primary one.
