# Feasibility Assessment

## Summary

The media/attachment design is **feasible** with the current codebase. No blocking technical issues were found. Implementation can proceed in phases.

## Evidence from Research

### AG-UI Protocol (p396 Explorer)
- `UserMessage.content` accepts `ImageInputContent`, `DocumentInputContent` with base64/URL — **verified in installed package**
- `CustomEvent` is available for extension — **verified**
- No native assistant-image event — **confirmed, CustomEvent is correct approach**

### Harness Capabilities (p396 + p397)
- Claude: Vision input via content blocks, base64/URL supported — **documented in Anthropic API**
- Codex: text-only input, `response.content_part.added/done` for output — **confirmed**
- OpenCode: text-only — **confirmed**

### Production Patterns (p397 Internet Research)
- Separate upload from streaming — **adopted**
- Use file IDs/URLs not repeated base64 — **adopted**
- SSE `id` + `retry` for reconnection — **adapted to WebSocket cursors**
- Persist append-only event log with snapshots — **adopted**

## Codebase Integration Points

### Mapper Extension (Low Risk)
Current mappers are stateful translators. Adding media detection requires:
- New `_translate_media_block` method in each mapper
- Shared `AGUIMapperBase` with `_make_media_attachment` helper
- Pass `ArtifactStore` to mappers via factory

**Risk:** Low. Mappers already handle complex block types. Media is additive.

### WebSocket Control (Low Risk)
`ws_endpoint.py` already parses JSON payloads. Adding `attachments` field:
- Extend payload validation
- Pass attachments to `SpawnManager.inject`

**Risk:** Low. No changes to WebSocket framing, just payload schema.

### HarnessConnection Protocol (Low Risk)
Add optional `send_user_message_with_attachments` method:
- Default implementation falls back to `send_user_message`
- Only Claude implements vision projection

**Risk:** Low. Non-breaking addition to protocol.

### Artifact Storage (Low Risk)
`ArtifactStore` protocol already exists. Extend with:
- `put_media` helper
- Thumbnail generation (optional Pillow dependency)

**Risk:** Low. Existing protocol unchanged.

### Event Persistence (Medium Risk)
New `EventStore` for append-only event log:
- New file format (`events.jsonl`)
- Write-ahead semantics
- Snapshot generation

**Risk:** Medium. New subsystem, but follows existing JSONL patterns (spawns.jsonl, sessions.jsonl).

### REST Endpoints (Low Risk)
New routes for artifacts:
- `GET /artifacts/{path}` — file serving
- `POST /artifacts/upload` — multipart upload
- `GET /history` — message snapshot

**Risk:** Low. Standard FastAPI patterns.

## Dependencies

### Required
- None new for core functionality

### Optional
- `Pillow` for thumbnail generation
- Can be omitted; thumbnails disabled without it

## Implementation Phases

### Phase 1: Media Output (1-2 days)
- Mapper media detection
- CustomEvent emission
- Artifact storage integration
- Artifact REST endpoint

**Deliverable:** Agent screenshots appear in UI.

### Phase 2: Media Input (1-2 days)
- WebSocket control extension
- Claude vision projection
- Upload endpoint
- Text-only harness fallback

**Deliverable:** User can paste images, Claude sees them.

### Phase 3: Reconnection (2-3 days)
- Event IDs in outbound stream
- Event persistence (events.jsonl)
- Cursor-based WebSocket resume
- MESSAGES_SNAPSHOT on fresh connect

**Deliverable:** Network blips don't lose messages.

### Phase 4: Polish (1-2 days)
- Thumbnail generation
- History endpoint
- Snapshot optimization
- Error handling edge cases

**Deliverable:** Production-ready media handling.

## Open Questions

### Q1: CORS for Artifact Fetch
Current: localhost-only origin validation.
Decision needed: Add explicit CORS headers for artifact endpoints?
Recommendation: Yes, mirror WS endpoint CORS policy.

### Q2: Artifact Cleanup Policy
Current: Artifacts live with spawn.
Decision needed: Size limits? TTL for terminal spawns?
Recommendation: Defer to cleanup phase, no hard limits initially.

### Q3: Cross-Spawn Artifact References
Current: Not supported in design.
Decision needed: Allow work-item-scoped sharing?
Recommendation: Reserve `shared/` category, implement later.

## Conclusion

Design is feasible with existing architecture. No fundamental blockers. Recommend proceeding with Phase 1 implementation to validate media output before input handling.
