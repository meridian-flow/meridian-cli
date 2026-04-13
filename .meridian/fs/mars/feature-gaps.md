# Mars Agents Feature Gaps

Context: review of `mars-agents` as of April 4, 2026.

This note captures feature areas that appear missing if Mars is meant to evolve from "agent/skill content sync" into a broader agent ecosystem package manager.

## Summary

Mars is already strong at:

- resolving package sources
- syncing agent and skill content into a managed root
- preserving local edits and handling merge/conflict flows
- linking managed content into tool directories

The main missing surface is environment and capability sync, not basic content sync.

## Missing Feature Areas

### 1. Permission Sync

Problem:
Packages can install agent and skill content, but they cannot declaratively define the runtime permission model those assets expect.

Examples:

- approval mode defaults
- sandbox tier expectations
- tool allowlists or denylists
- runtime-specific permission settings

Why it matters:
Without permission sync, a package can ship content that assumes capabilities the runtime never grants. That leaves behavior fragmented across package content and local manual setup.

Suggested direction:
Add a declarative package section for permission policy that Mars can materialize into supported tool/runtime configs.

Draft issue title:
`Feature: sync package-defined permissions into tool/runtime environments`

### 2. Tool Definition Distribution

Problem:
Mars distributes prompts and skills, but not first-class tool definitions.

Examples:

- packaged tool specs
- shared tool aliases
- tool metadata and descriptions
- runtime-specific tool registrations derived from one package schema

Why it matters:
Skills and agents are only part of the execution contract. If tools are configured elsewhere, packages are incomplete and harder to share reproducibly.

Suggested direction:
Support package-managed tool definitions with a declarative intermediate schema and per-runtime materialization.

Draft issue title:
`Feature: distribute tool definitions as first-class Mars package artifacts`

### 3. Hook Definition Distribution

Problem:
Mars does not appear to have a first-class model for distributing hooks or automation bindings.

Examples:

- lifecycle hooks
- trigger-based actions
- post-sync hooks
- runtime event hooks

Why it matters:
If teams rely on hooks to make agents useful in practice, then Mars currently syncs content without syncing the automation behavior around that content.

Suggested direction:
Add declarative hook definitions that can be installed, validated, and materialized per runtime without embedding runtime-specific imperative logic throughout Mars.

Draft issue title:
`Feature: distribute hook definitions and lifecycle integrations`

### 4. MCP Integration

Problem:
Mars packages do not currently appear to manage MCP capability wiring as a first-class package concern.

Examples:

- MCP server registrations
- resource or template exposure
- capability bundles that depend on external MCP services
- package-managed MCP configuration fragments

Why it matters:
If the long-term ecosystem is about agent capabilities rather than just markdown assets, MCP integration is a major missing layer.

Suggested direction:
Add a package schema for MCP integration that can describe required servers, configuration fragments, and possibly validation of expected capability presence.

Draft issue title:
`Feature: support MCP integration as a package-managed capability`

### 5. Distribution Model

Problem:
Mars can fetch from git and local paths, but that is not the same as having a real package distribution model.

Examples:

- package discovery
- publisher identity and trust
- registry or index support
- cached metadata and search
- install policy by source trust level

Why it matters:
Git URLs are enough for a developer tool, but not enough for a broader package ecosystem. Sharing and trust remain ad hoc.

Suggested direction:
Introduce a registry or index model, even if minimal at first, with explicit publisher and provenance handling.

Draft issue title:
`Feature: add a real package distribution model beyond git/path sources`

## Product Framing

A useful way to think about Mars:

1. Content packages
2. Capability packages
3. Runtime policy packages
4. Distribution and trust

Mars is already good at `1`.

The missing work is mostly `2`, `3`, and `4`.

## Prioritization

If only a few of these should be built next, the likely order is:

1. permission sync
2. tool definition distribution
3. MCP integration
4. hook definition distribution
5. broader distribution model

Rationale:

- permissions and tools are the most direct gap between packaged content and usable runtime behavior
- MCP is likely central if Mars is evolving toward capability management
- hooks matter, but they risk dragging runtime-specific imperative logic into Mars too early
- a full distribution model is important later, but not necessary before Mars proves the broader package schema

## GitHub Follow-Up

Attempted GitHub issue creation was blocked in this environment because `gh auth status` reported an invalid token for the configured account.

When GitHub auth is available again, create one issue per feature area using the draft titles above.
