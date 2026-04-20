# Design Decisions

## D1: CustomEvent for Media Output (Not RAW)

**Decision:** Use `CustomEvent` with `name="media_attachment"` for agent-generated media, not `RAW` events.

**Why:** 
- AG-UI has no native assistant-image event type
- `CustomEvent` is the intended extension mechanism
- `RAW` is for debugging/protocol passthrough, not structured content
- Frontend can type-discriminate on `event.name`

**Alternatives rejected:**
- `RAW` event: loses semantic typing, harder to render
- New event type: requires AG-UI protocol changes

---

## D2: Inline Base64 vs URI Threshold at 256KB

**Decision:** Inline small images (< 256KB) as base64 in event, reference larger as artifact URIs.

**Why:**
- Small images render immediately without extra round-trip
- Large images would bloat WebSocket frames and memory
- 256KB is ~2 decoded PNG screenshots at typical resolution

**Alternatives considered:**
- Always URI: adds latency for small images
- Always inline: WebSocket bloat, client memory pressure
- 100KB threshold: too aggressive, most screenshots exceed

---

## D3: Upload-First Flow for Large Attachments

**Decision:** Require separate upload for attachments > 100KB before WebSocket message.

**Why:**
- WebSocket is not designed for large binary payloads
- Multipart upload gives progress feedback
- Server can validate/scan before spawn sees it
- Artifact URI can be reused in multi-turn

**Trade-off:** Two round-trips for large attachments. Acceptable because large uploads are already latency-bound.

---

## D4: Text-Only Harness Degradation

**Decision:** For Codex/OpenCode, store attachments as artifacts and inject text placeholder `[N attachment(s)]`.

**Why:**
- These harnesses don't support vision input
- Preserving attachments in artifacts allows:
  - UI to still display them
  - Future harness versions to access
  - Transcript to reference them

**Alternatives rejected:**
- OCR and inject: expensive, lossy, not user-requested
- Reject attachment messages: breaks user workflow

---

## D5: Event ID Format `{spawn_id}:{sequence}`

**Decision:** Use colon-separated spawn ID and zero-padded sequence number.

**Why:**
- Spawn ID prefix enables multi-spawn filtering without parsing
- Zero-padding enables lexicographic sorting
- Colons are URI-safe but unlikely in spawn IDs
- Simple to parse: `spawn_id, seq = event_id.rsplit(":", 1)`

**Alternatives considered:**
- UUID per event: harder to order, no spawn context
- Timestamp-based: clock skew issues, not monotonic
- Integer only: loses spawn context in cross-spawn scenarios

---

## D6: Write-Ahead Event Persistence

**Decision:** Persist events to disk before sending to WebSocket.

**Why:**
- Guarantees replay availability even if server crashes after send
- Consistent ordering: disk sequence = wire sequence
- Enables crash recovery without client-side log

**Trade-off:** Slightly higher latency (disk write before send). Mitigated with buffered writes and SSD-targeted workload.

---

## D7: MESSAGES_SNAPSHOT on Fresh Connect

**Decision:** Send full message snapshot when client connects without cursor, replay delta with cursor.

**Why:**
- AG-UI specifies `MESSAGES_SNAPSHOT` for initialization
- Client doesn't need to replay entire event stream
- Reduces data transfer for long sessions
- Consistent with AG-UI reconnection semantics

---

## D8: Artifact Path Structure

**Decision:** `{spawn}/artifacts/{category}/{filename}` with categories `media/`, `uploads/`, `shared/`.

**Why:**
- Separates agent output from user input
- `shared/` enables future cross-spawn references
- Category prefix enables access control rules
- Filename is UUID-based to prevent collisions

---

## D9: Thumbnail Generation On-Demand

**Decision:** Generate thumbnails lazily on first request, cache as `.thumb.jpg`.

**Why:**
- Most images may never need thumbnails
- Avoids upfront compute cost during streaming
- Cache prevents regeneration
- JPEG thumbnail is universally renderable

**Trade-off:** First thumbnail request is slower. Acceptable for non-blocking UI patterns (placeholder until loaded).

---

## D10: Pillow for Thumbnail Generation

**Decision:** Use Pillow (PIL) for image processing, make it optional dependency.

**Why:**
- Pillow is widely used, well-maintained
- Handles common formats (PNG, JPEG, GIF, WebP)
- Pure Python fallback exists (slower but functional)
- Already common in Python web stacks

**Alternative rejected:**
- ImageMagick subprocess: external dependency, security surface
- Sharp/Node: wrong language runtime
- No thumbnails: poor UX for large images
