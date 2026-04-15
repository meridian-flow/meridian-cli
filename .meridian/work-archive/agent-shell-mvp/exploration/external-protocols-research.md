# External Protocols Research
Date: 2026-04-07

## What I did
- Read the Companion repo README, reverse-engineered protocol spec, and the server/bridge source that actually launches and translates Claude Code.
- Reviewed current OpenCode docs for the live HTTP server, ACP CLI, permissions, agents, models, and storage behavior.
- Cross-checked Anthropic docs for the documented Claude Code headless `stream-json` baseline and generic tool-use framing.
- Compared all three shapes against the Codex app-server / `codex exec` style JSON-RPC bridge used by Companion.

## Key Decisions
- I treated the current OpenCode docs site as the source of truth for current behavior, and used source code mainly where the docs were underspecified.
- For OpenCode implementation details, I used the archived `opencode-ai/opencode` source as provenance because the project has moved, while the live docs now point to the current `sst/opencode` line.
- I designed the comparison around the least-common-denominator operations:
  - start session
  - send user input
  - receive streamed output
  - cancel / interrupt
  - respond to tool approval
  - resume a prior session

## Findings

### 1) Companion / Claude Code

Companion is a Bun + Hono web app that launches Claude Code as a subprocess and bridges it to the browser.

- It creates a `CliLauncher`, `WsBridge`, and `SessionStore` at startup, then restores persisted sessions.
- For Claude Code it spawns:
  - `claude --sdk-url ws://localhost:<port>/ws/cli/<sessionId>`
  - `--print`
  - `--output-format stream-json`
  - `--input-format stream-json`
  - `--verbose`
  - optional `--model`, `--permission-mode`, `--allowedTools`, `--resume`
  - `-p ""`
- It sets `CLAUDECODE=1` in the environment.
- It keeps per-session process state, pipes stdout/stderr, persists session metadata, and relaunches stale sessions after restart.
- It stores both the launcher UUID and Claude’s internal session ID so `--resume` can work after relaunch.

Protocol shape:
- Transport is NDJSON over WebSocket.
- `system/init`, `system/status`, `assistant`, `result`, `stream_event`, `control_request`, `tool_progress`, `tool_use_summary`, `auth_status`, and `keep_alive` are the core message types.
- Tool framing uses Claude content blocks:
  - `text`
  - `tool_use`
  - `tool_result`
  - `thinking`
- `stream_event` carries `message_start`, `content_block_start`, `content_block_delta`, `content_block_stop`, and `message_delta`.
- Approval flow is `control_request` subtype `can_use_tool` -> browser `permission_request` -> browser `permission_response` -> Claude `control_response`.
- Mid-turn injection works by writing `user` NDJSON messages to the active Claude channel; if Claude is not ready, Companion queues them and flushes later.
- `interrupt` becomes a Claude control request.

Browser envelope:
- Browser -> bridge:
  - `user_message`
  - `permission_response`
  - `interrupt`
  - `set_model`
  - `set_permission_mode`
- Bridge -> browser:
  - `session_init`
  - `session_update`
  - `assistant`
  - `stream_event`
  - `result`
  - `permission_request`
  - `permission_cancelled`
  - `tool_progress`
  - `tool_use_summary`
  - `status_change`
  - `auth_status`
  - `error`
  - `cli_disconnected`
  - `cli_connected`
  - `user_message`
  - `message_history`
  - `session_name_update`

Persistence / resume:
- Sessions persist as JSON in a temp-dir store by default.
- `launcher.json` stores process metadata.
- Message history and pending permissions are persisted per session.
- Session resume depends on Claude’s internal session ID, not just the launcher UUID.

Gotchas:
- `--sdk-url` is hidden.
- `-p` is ignored in SDK URL mode.
- `--input-format` and `--output-format` must both be `stream-json`.
- The CLI waits for the first `user` message after connect.
- Keepalive / reconnect behavior is part of the reverse-engineered protocol, not public docs.

Sources:
- [README.md](https://github.com/KjellKod/the-vibe-company-companion/blob/main/README.md)
- [WEBSOCKET_PROTOCOL_REVERSED.md](https://github.com/KjellKod/the-vibe-company-companion/blob/main/WEBSOCKET_PROTOCOL_REVERSED.md)
- [web/server/index.ts](https://github.com/KjellKod/the-vibe-company-companion/blob/main/web/server/index.ts)
- [web/server/cli-launcher.ts](https://github.com/KjellKod/the-vibe-company-companion/blob/main/web/server/cli-launcher.ts)
- [web/server/ws-bridge.ts](https://github.com/KjellKod/the-vibe-company-companion/blob/main/web/server/ws-bridge.ts)
- [web/server/session-types.ts](https://github.com/KjellKod/the-vibe-company-companion/blob/main/web/server/session-types.ts)
- [web/server/session-store.ts](https://github.com/KjellKod/the-vibe-company-companion/blob/main/web/server/session-store.ts)

Anthropic baseline docs:
- [Claude Code SDK](https://docs.anthropic.com/pt/docs/claude-code/sdk)
- [Claude Code headless mode](https://docs.anthropic.com/zh-CN/docs/claude-code/sdk/sdk-headless)
- [Tool use examples](https://docs.anthropic.com/claude/docs/tool-use-examples)

### 2) OpenCode

OpenCode is broader than one transport. Current docs show:
- A terminal TUI / CLI
- A standalone HTTP server via `opencode serve`
- An ACP server via `opencode acp`
- Browser / desktop / IDE-oriented clients around the server APIs

Current server shape:
- `opencode serve` exposes a standalone HTTP server and OpenAPI spec.
- `GET /global/event` is an SSE stream.
- `GET /session`, `POST /session`, `GET /session/:id`, `DELETE /session/:id`, `POST /session/:id/abort`, `POST /session/:id/fork`, `POST /session/:id/share`, and `POST /session/:id/init` are part of the session lifecycle.
- `GET /session/:id/message`, `POST /session/:id/message`, `GET /session/:id/message/:messageID`, `POST /session/:id/prompt_async`, `POST /session/:id/command`, and `POST /session/:id/shell` are the main interaction endpoints.
- The message body accepts `messageID?`, `model?`, `agent?`, `noReply?`, `system?`, `tools?`, and `parts`.

ACP:
- `opencode acp` starts a server that uses stdin/stdout with nd-JSON.
- That makes ACP a subprocess protocol, not an HTTP protocol.

Tool framing / message model:
- The public docs describe messages as `{ info: Message, parts: Part[] }`.
- The code models parts like:
  - `reasoning`
  - `text`
  - `image_url`
  - `binary`
  - `tool_call`
  - `tool_result`
  - `finish`
- So OpenCode is a persisted part-based message system, not a raw token stream protocol.

Permission gating:
- Permissions are config-driven.
- Allowed values are `allow`, `ask`, and `deny`.
- Per-agent overrides exist.
- The session API also exposes a permission response endpoint.

Persistence:
- Troubleshooting docs say app data lives under `~/.local/share/opencode/`.
- Project data is stored under `project/`, with Git-repo projects under `./<project-slug>/storage/`.
- The code persists sessions and messages in SQLite-backed services.

Profiles / agents / models:
- Config supports `model` and `small_model`.
- `agent` config supports custom prompts, models, and permissions.
- `default_agent` controls the default primary agent.
- Agents can be defined in markdown files under `.opencode/agents/` or `~/.config/opencode/agents/`.

Gotchas:
- In real-world use, model selection has drifted to the last-used model instead of config defaults in reported issues.
- Agent toggling has also been reported to ignore an agent-specific model and reuse another agent’s model.
- `tools` is deprecated in favor of agent `permission`.

Sources:
- [OpenCode intro](https://opencode.ai/docs/)
- [OpenCode server docs](https://opencode.ai/docs/server)
- [OpenCode CLI docs](https://dev.opencode.ai/docs/ru/cli/)
- [OpenCode permissions docs](https://opencode.ai/docs/permissions)
- [OpenCode agents docs](https://opencode.ai/docs/agents)
- [OpenCode tools docs](https://opencode.ai/docs/tools)
- [OpenCode troubleshooting docs](https://opencode.ai/docs/troubleshooting)
- [cmd/root.go](https://github.com/opencode-ai/opencode/blob/main/cmd/root.go)
- [internal/app/app.go](https://github.com/opencode-ai/opencode/blob/main/internal/app/app.go)
- [internal/session/session.go](https://github.com/opencode-ai/opencode/blob/main/internal/session/session.go)
- [internal/message/message.go](https://github.com/opencode-ai/opencode/blob/main/internal/message/message.go)
- [internal/permission/permission.go](https://github.com/opencode-ai/opencode/blob/main/internal/permission/permission.go)

Real-world issue threads:
- [Issue #1296](https://github.com/sst/opencode/issues/1296)
- [Issue #3550](https://github.com/sst/opencode/issues/3550)

### 3) Comparison Table

| Dimension | Claude Code stream-json | OpenCode HTTP / ACP | Codex exec / app-server |
|---|---|---|---|
| Session lifecycle | Long-lived CLI process; resumption via Claude session ID | Server-backed sessions; TUI / client can attach to persisted state | One subprocess per session in Companion; resume via thread ID |
| Input channel | stdin stream-json or `--sdk-url` WebSocket NDJSON | HTTP body to `POST /session/:id/message` or `prompt_async`; ACP uses stdin/stdout nd-JSON | stdio JSON-RPC to `codex app-server` |
| Output channel | stdout stream-json or WebSocket NDJSON | HTTP JSON responses plus SSE bus events on `/global/event` | stdout JSON-RPC notifications |
| Mid-turn injection | Yes, by sending more user JSON while active | Yes, via `prompt_async` or interactive append-prompt semantics | Yes, via `turn/start`, `turn/interrupt`, and queued browser messages |
| Permission gating | Yes, `control_request` / `control_response` | Yes, config-driven `allow` / `ask` / `deny` plus permission endpoints | Yes, JSON-RPC approval requests and accept/decline responses |
| Tool framing | `tool_use` / `tool_result` content blocks | `Part[]` with `tool_call`, `tool_result`, `reasoning`, `finish` | Item lifecycle events translated into `tool_use` / `tool_result` |
| Documented vs reverse-engineered | Headless stream-json and generic tool-use are documented; `--sdk-url` is reverse-engineered | Public docs cover the server and ACP surface; implementation details are in source | Companion’s mapping is reverse-engineered from the app-server protocol |

## Files Created / Modified
- None. The sandbox rejected filesystem writes, so I could not create `.meridian/work/agent-shell-mvp/exploration/external-protocols-research.md` locally.

## Verification
- Verified Companion behavior against live repository source and its reverse-engineered protocol doc.
- Verified OpenCode behavior against live docs on `opencode.ai` / `dev.opencode.ai`.
- Verified Claude Code baseline behavior against Anthropic docs.
- Cross-checked OpenCode implementation details against source files in the archived provenance repo where docs were underspecified.

## Issues / Blockers
- `meridian report create --stdin` is unavailable in this environment. The command returned `Unknown command: report`.
- I could not write the requested workdir file because the sandbox is read-only.
- I did not find a separate public issue trail for Companion’s stream-json quirks; the reverse-engineered protocol doc is the main source of those edge cases.