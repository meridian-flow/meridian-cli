# AG-UI Media/Attachment Design

## Problem

Meridian's AG-UI streaming currently drops all non-text content:
- User image attachments cannot be sent
- Assistant image outputs (screenshots, diagrams) are lost
- Tool results with media are stringified
- No reconnection/replay for dropped connections

## Scope

Design media handling for the meridian app, covering:

1. **Media Input** — User sending images/files to the agent
2. **Media Output** — Agent producing images/files in responses  
3. **Artifact Storage** — Where media lives, how it's fetched
4. **Reconnection/Replay** — Resuming streams, loading history

## Research Findings

From p396 (explorer) and p397 (internet-researcher):

### AG-UI Native Support
- `UserMessage.content` accepts `ImageInputContent`, `DocumentInputContent` with base64/URL
- No native assistant-image event — use `CustomEvent` for extension
- `MESSAGES_SNAPSHOT` designed for reconnection/replay
- `STATE_SNAPSHOT/DELTA` for state sync

### Harness Capabilities
- **Claude**: Vision input (base64, URL, file ref), streams content blocks, tool results can have images
- **Codex**: `response.content_part.added/done`, screenshot issues in production
- **OpenCode**: Likely text-only, needs verification

### Production Patterns
- Separate media upload from text streaming
- Use file IDs/URLs not repeated base64
- Persist append-only event log with snapshots
- SSE `id` + `retry` for reconnection

## Success Criteria

- User can paste a screenshot into composer, agent sees it
- Agent screenshot tool output renders inline in chat
- Reconnecting after network blip resumes without lost messages
- Works across Claude, Codex (OpenCode best-effort)
