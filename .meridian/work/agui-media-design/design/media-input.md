# Media Input Design

## Problem

User-sent attachments (screenshots, images, documents) cannot reach harnesses today. The WebSocket `user_message` control payload accepts only `text: string`, and harness connections only send plain text via `send_user_message(text: str)`.

## Design Goals

1. Accept multimodal content from frontend via WebSocket or REST
2. Project attachments to harnesses that support them (Claude vision)
3. Degrade gracefully for text-only harnesses (Codex, OpenCode)
4. Avoid repeated base64 bloat in multi-turn sessions

## Input Contract

### WebSocket Control Message

Extend `user_message` to accept optional `attachments`:

```typescript
interface UserMessageControl {
  type: "user_message";
  text?: string;                    // Text content (optional if attachments present)
  attachments?: Attachment[];       // Zero or more attachments
}

interface Attachment {
  id: string;                       // Client-generated UUID
  kind: "image" | "document";       // Media category
  mime_type: string;                // e.g., "image/png", "application/pdf"
  filename?: string;                // Original filename for display
  source: AttachmentSource;         // Where the bytes come from
}

type AttachmentSource =
  | { type: "data"; data: string }  // Base64-encoded bytes (inline)
  | { type: "uri"; uri: string };   // Reference to uploaded artifact
```

**Validation rules:**
- At least one of `text` or `attachments` must be present
- `kind: "image"` requires `mime_type` in `image/*`
- `kind: "document"` requires `mime_type` in `application/pdf`, `text/*`
- `source.type: "data"` must be valid base64
- `source.type: "uri"` must reference a valid spawn artifact path

### Upload-First Flow (Recommended for Large Media)

For large attachments, use a two-step flow:

1. **Upload** via REST endpoint: `POST /api/spawns/{spawn_id}/artifacts/upload`
   - Request: `multipart/form-data` with file field
   - Response: `{ "artifact_uri": "artifacts://{spawn_id}/uploads/{uuid}.{ext}" }`

2. **Reference** in WebSocket message:
   ```json
   {
     "type": "user_message",
     "text": "What's in this screenshot?",
     "attachments": [{
       "id": "att-001",
       "kind": "image",
       "mime_type": "image/png",
       "source": { "type": "uri", "uri": "artifacts://p42/uploads/abc123.png" }
     }]
   }
   ```

**Threshold guidance:** Use upload-first for attachments > 100KB. Inline base64 acceptable for small images (thumbnails, clipboard screenshots).

## Harness Projection

### Claude (Vision Capable)

Claude SDK accepts images via content blocks. Project attachments to Claude's format:

```python
async def send_user_message_with_attachments(
    self,
    text: str,
    attachments: list[Attachment],
) -> None:
    content_blocks = []
    
    for att in attachments:
        if att.kind == "image":
            image_data = self._resolve_attachment_bytes(att)
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": att.mime_type,
                    "data": base64.b64encode(image_data).decode(),
                }
            })
        elif att.kind == "document" and att.mime_type == "application/pdf":
            # Claude supports PDF via document content blocks
            doc_data = self._resolve_attachment_bytes(att)
            content_blocks.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": att.mime_type,
                    "data": base64.b64encode(doc_data).decode(),
                }
            })
    
    if text:
        content_blocks.append({"type": "text", "text": text})
    
    # Send via stdin JSON stream
    await self._write_json({
        "type": "user_message",
        "content": content_blocks if len(content_blocks) > 1 else text,
    })
```

### Codex / OpenCode (Text Only)

These harnesses do not support image input. Degrade to text summary:

```python
async def send_user_message_with_attachments(
    self,
    text: str,
    attachments: list[Attachment],
) -> None:
    # Store attachments as artifacts (for potential UI display)
    artifact_refs = []
    for att in attachments:
        ref = await self._store_attachment_artifact(att)
        artifact_refs.append(ref)
    
    # Inject text summary
    summary_parts = [text] if text else []
    for att, ref in zip(attachments, artifact_refs):
        summary_parts.append(
            f"[Attachment: {att.filename or att.id} ({att.mime_type})]"
        )
    
    await self._send_text("\n".join(summary_parts))
```

## Implementation Changes

### 1. HarnessConnection Protocol Extension

Add optional attachment support to base protocol:

```python
class HarnessConnection(Generic[SpecT], ABC):
    # Existing
    async def send_user_message(self, text: str) -> None: ...
    
    # New (optional, default falls back to text-only)
    async def send_user_message_with_attachments(
        self,
        text: str,
        attachments: list[Attachment],
    ) -> None:
        # Default: ignore attachments, send text only
        await self.send_user_message(text)
    
    @property
    def supports_vision(self) -> bool:
        return False
```

### 2. SpawnManager.inject Extension

Extend injection to accept attachments:

```python
async def inject(
    self,
    spawn_id: SpawnId,
    *,
    message: str,
    attachments: list[Attachment] | None = None,
    source: str = "unknown",
) -> InjectResult:
    session = self._sessions.get(spawn_id)
    if session is None:
        return InjectResult(success=False, error="spawn not active")
    
    conn = session.connection
    if attachments and conn.supports_vision:
        await conn.send_user_message_with_attachments(message, attachments)
    else:
        # Fallback: store attachments as artifacts, send text
        await conn.send_user_message(message)
    
    return InjectResult(success=True)
```

### 3. WebSocket Control Handler

Update `_inbound_loop` to parse attachments:

```python
if message_type == "user_message":
    text = payload.get("text", "")
    raw_attachments = payload.get("attachments", [])
    
    attachments = []
    for raw in raw_attachments:
        try:
            attachments.append(Attachment.model_validate(raw))
        except ValidationError as exc:
            await _send_error(websocket, f"invalid attachment: {exc}")
            continue
    
    if not text and not attachments:
        await _send_error(websocket, "user_message requires text or attachments")
        continue
    
    result = await manager.inject(
        spawn_id,
        message=text,
        attachments=attachments if attachments else None,
        source="app_ws",
    )
```

### 4. Capabilities Reporting

Add `supportsVision` to capabilities CustomEvent:

```python
def make_capabilities_event(caps: ConnectionCapabilities) -> CustomEvent:
    return CustomEvent(
        name="capabilities",
        value={
            # ... existing fields ...
            "supportsVision": caps.supports_vision,
        },
    )
```

## Size Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Max inline base64 | 10 MB | Matches `MAX_INITIAL_PROMPT_BYTES` |
| Max upload size | 50 MB | Claude vision limit for single image |
| Max attachments per message | 20 | Claude API limit |

## Edge Cases

### Empty Text with Attachments
Valid — project attachments only. For text-only harnesses, inject `[N attachment(s)]`.

### Unsupported MIME Type
Store as artifact but exclude from harness projection. Log warning. Return artifact URI in CustomEvent so UI can display download link.

### URI Resolution Failure
Return error via WebSocket `RUN_ERROR` event. Do not send partial message to harness.

### Mid-Turn Attachment Injection
Same as text injection — behavior depends on `mid_turn_injection` capability (queue, interrupt_restart, http_post).

## Out of Scope

- Audio/video attachments (future extension)
- Multi-page PDF streaming (send as single document)
- OCR fallback for text-only harnesses (user can request explicitly)
