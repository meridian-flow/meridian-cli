# OpenCode Probe Findings: Extra Directory / Root Injection

Date: 2026-04-14
Target version: OpenCode 1.4.3 (changelog entry dated 2026-04-10)

## 1) Direct answer

**As of OpenCode 1.4.3, OpenCode does not provide a first-class, documented multi-root context injection mechanism equivalent to Claude `--add-dir` or Codex `--add-dir`.**

What exists instead:
- Single launch root (`[project]` / `--dir`) at process start.
- Path access outside root governed by `external_directory` permission prompts/rules.
- MCP server integration (including local MCP processes) that can be configured separately.

Why this conclusion:
- Public config docs/schema do not document workspace root arrays (`roots`, `additionalDirectories`, etc.).
- `Config.Agent` schema has no workspace/root field.
- A prior PR that explicitly introduced multi-directory workspace config (`workspace.directories`) was closed unmerged.

Evidence:
- Config docs and precedence: https://opencode.ai/docs/config/
- JSON schema URL referenced by docs: https://opencode.ai/config.json
- Source config schema (`Config.Agent`, `Mcp*`, `Permission`): https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/config/config.ts
- Closed multi-directory PR (not merged): https://github.com/anomalyco/opencode/pull/2921
- Changelog 1.4.3: https://opencode.ai/changelog

---

## 2) Q1: Does `opencode.json` support multi-root/additional-directories fields?

### Finding
**No documented or current-source-supported top-level multi-root field was found** (`roots`, `workspaces`, `additionalDirectories`, `includePaths`, etc.).

### Concrete evidence
- Official config docs list many keys (`model`, `agent`, `mcp`, `permission`, etc.) but no multi-root key:
  - https://opencode.ai/docs/config/
- Official schema endpoint is `https://opencode.ai/config.json`; no documented multi-root property appears in public docs/schema usage.
- Source-of-truth config schema in `config.ts` defines many top-level options and `Agent`/`Mcp`/`Permission`; no top-level workspace-roots array is present:
  - https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/config/config.ts
- Closed PR #2921 explicitly proposed `workspace.directories`, indicating this was not already available and was not merged:
  - https://github.com/anomalyco/opencode/pull/2921

### Important nuance
OpenCode *does* have internal project/worktree/sandbox concepts (`Project.Info.worktree`, `sandboxes`) used by control-plane internals, but that is not exposed as a stable user config for launch-time multi-root injection:
- https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/project/project.ts

---

## 3) Q2: Can OpenCode agents declare extra roots?

### Finding
**No first-class agent field for declaring extra filesystem roots.**

### Concrete evidence
`Config.Agent` supports fields like:
- `model`, `variant`, `temperature`, `prompt`, `tools` (deprecated), `permission`, `mode`, `steps`, etc.
- No `roots`, `workspace`, `directories`, `includePaths`, etc.

Source:
- https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/config/config.ts
- Agent docs (JSON + markdown frontmatter options) also show no root field:
  - https://github.com/anomalyco/opencode/blob/main/packages/web/src/content/docs/agents.mdx

### Plugin angle
Plugins can hook tool execution and add custom tools, but docs do not expose a first-class API to mutate the instance root set. Plugin hooks can influence behavior, not redefine official workspace-root semantics:
- https://github.com/anomalyco/opencode/blob/main/packages/web/src/content/docs/plugins.mdx

---

## 4) Q3: MCP as workaround path

### Finding
**Yes, MCP is the strongest workaround path for “extra dirs,” but it is not equivalent to native multi-root injection.**

### Concrete evidence
OpenCode supports MCP server config in `opencode.json`:
- Local MCP server: `type: "local"`, `command`, optional `environment`, `enabled`, `timeout`
- Remote MCP server: `type: "remote"`, `url`, headers/oauth/etc.

Sources:
- Docs: https://github.com/anomalyco/opencode/blob/main/packages/web/src/content/docs/mcp-servers.mdx
- Source schema (`McpLocal`, `McpRemote`): https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/config/config.ts

### Can this expose extra directories?
**Practically yes**, if you run a filesystem MCP server configured with multiple allowed roots/paths in that MCP server’s own CLI/env config. OpenCode itself just launches/connects to MCP.

### Community signal
There are community discussions about MCP roots and filesystem MCP usage, suggesting this pattern is relevant but still not a first-class OpenCode workspace feature:
- “Support MCP Roots” issue: https://github.com/anomalyco/opencode/issues/2308
- Related discussion on passing cwd/paths for MCP: https://github.com/anomalyco/opencode/issues/3395

### Tradeoff
This gives tool-level access through MCP, not native “all core tools now see extra roots as workspace roots” behavior.

---

## 5) Q4: Environment variables or config overlays for extra roots

### Finding
**No env var found for multi-root injection (no `OPENCODE_EXTRA_DIRS`, `OPENCODE_ROOTS`, etc.).**

### Concrete evidence
`Flag` env set includes config layering and overrides such as:
- `OPENCODE_CONFIG`, `OPENCODE_CONFIG_DIR`, `OPENCODE_CONFIG_CONTENT`
- `OPENCODE_DISABLE_PROJECT_CONFIG`
- many runtime toggles

But no `OPENCODE_EXTRA_DIRS`-style root list.

Source:
- https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/flag/flag.ts

### Config layering behavior (useful but not multi-root)
OpenCode merges config from remote/global/custom/project/.opencode/inline/managed sources.
This can alter permissions and MCP setup, but does not create a native root array mechanism.

Sources:
- Docs precedence: https://opencode.ai/docs/config/
- Source merge/load flow: https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/config/config.ts
- Path discovery for config directories: https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/config/paths.ts

---

## 6) Q5: Recent/upcoming support signals

### What exists
- **Closed, unmerged attempt** for workspace multi-directory support (`workspace.directories`):
  - https://github.com/anomalyco/opencode/pull/2921
- **Ongoing user demand** around multi-root/roots in adjacent areas:
  - Patch tool issue explicitly links multi-directory request: https://github.com/anomalyco/opencode/issues/11113
  - MCP roots feature request: https://github.com/anomalyco/opencode/issues/2308

### Recent releases (1.4.x)
No 1.4.0–1.4.3 changelog entry indicates shipped native multi-root directory injection.
- https://opencode.ai/changelog

### Interpretation
There is clear demand and at least one concrete attempted implementation, but no shipped first-class feature as of 1.4.3.

---

## 7) Ranked alternatives for equivalent behavior

### A) MCP-based extra dirs (best practical near-term)
Viability: **High**
Complexity: **Medium**

How:
- Configure local filesystem MCP server(s) in `opencode.json` under `mcp` with commands that expose desired external roots.

Pros:
- Officially supported integration surface.
- Fine-grained path exposure managed by MCP server.
- Can be standardized per project/team config.

Cons:
- Not identical to native harness add-dir semantics.
- Depends on MCP server capability/latency and prompt behavior (“use X tool”).
- Different ergonomics from built-in file tools.

### B) `external_directory` permission allowlist + normal tools
Viability: **Medium-High**
Complexity: **Low-Medium**

How:
- Preconfigure `permission.external_directory` patterns for known extra paths.

Pros:
- Uses native tools directly.
- Already supported and documented.

Cons:
- This is permission gating, not root injection.
- Can be broad/risky if over-allowlisted.
- Still lacks explicit multi-root launch contract.

Evidence:
- https://github.com/anomalyco/opencode/blob/main/packages/web/src/content/docs/permissions.mdx
- https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/tool/external-directory.ts
- https://github.com/anomalyco/opencode/blob/main/packages/opencode/src/project/instance.ts

### C) Symlink extra dirs into project root
Viability: **Medium**
Complexity: **Low**

Pros:
- Simple, no upstream changes.
- Makes paths appear under one root.

Cons:
- Fragile across OS/tooling/security policies.
- Can confuse indexing/watchers and relative path assumptions.
- Operationally hacky.

### D) Prompt-only directory summaries / manual file references
Viability: **Low-Medium**
Complexity: **Low**

Pros:
- Fastest to bootstrap.

Cons:
- Weak guarantees; context drift and stale summaries.
- Bad ergonomics for substantial code edits.
- Not acceptable as durable day-1 parity with add-dir semantics.

### E) Wait for upstream native feature
Viability: **Unknown timeline**
Complexity: **Low now, High uncertainty**

Pros:
- Would provide cleaner first-class behavior if shipped.

Cons:
- No committed timeline signal found.
- Prior implementation attempt was closed unmerged.

---

## 8) Recommendation for Meridian (day-1 support requirement)

For day-1 support, do **not** block on upstream OpenCode native multi-root.

Recommended Meridian strategy:
1. Treat OpenCode as **no-native-add-dir** in capability matrix (as of 1.4.3).
2. Offer **MCP-based augmentation** as primary OpenCode path for additional directory access.
3. Optionally add a fallback mode using `external_directory` pre-allowlists for known paths.
4. Mark behavior parity as **partial** vs Claude/Codex native add-dir and expose this clearly in UX/docs.
5. Keep a watch on upstream issues/PRs (#2308, #11113, descendants of #2921) and switch when native support lands.

This gets reliable day-1 functionality with explicit tradeoffs, without pretending parity where it does not exist.
