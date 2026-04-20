# Media Output Design

## Problem

Agent-generated media (screenshots from browser tools, diagrams, generated images) is lost in the current AG-UI streaming. Harness mappers stringify tool results, discarding binary content. AG-UI has no native assistant-image event type — we need a CustomEvent extension.

## Design Goals

1. Detect media in harness tool results
2. Persist to spawn artifact storage
3. Emit structured CustomEvent for frontend rendering
4. Support inline base64 for small images, URI reference for large
5. Maintain text fallback for transcript readability

## CustomEvent Schema

### Event Type: `media_attachment`

```typescript
interface MediaAttachmentEvent {
  type: "CUSTOM";
  name: "media_attachment";
  value: MediaAttachment;
}

interface MediaAttachment {
  id: string;                       // Unique ID for this attachment
  message_id: string;               // Links to parent ToolCallResultEvent
  kind: "image" | "document" | "file";
  mime_type: string;                // e.g., "image/png", "application/pdf"
  filename?: string;                // Display name
  size_bytes: number;               // For progress/display decisions
  sha256?: string;                  // Content hash for dedup/caching
  
  // One of these is present
  data?: string;                    // Inline base64 (for small images, < 256KB)
  uri?: string;                     // Artifact URI (for larger content)
  
  // Context
  source: MediaSource;
  caption?: string;                 // Human-readable description
}

interface MediaSource {
  tool_call_id: string;             // Which tool produced this
  tool_name: string;                // e.g., "mcp__playwright__browser_take_screenshot"
  content_index?: number;           // Position in multi-content response
}
```

### Inline vs URI Decision

| Size | Delivery | Rationale |
|------|----------|-----------|
| < 256 KB | Inline base64 | Fast render, no extra round-trip |
| >= 256 KB | URI reference | Avoid WebSocket bloat, enable progressive load |

## Harness Mapper Changes

### Detection Strategy

Each mapper must identify image content in tool results:

**Claude** — Check `content_block` for `type: "image"`:
```python
def _translate_tool_result(self, payload: dict) -> list[BaseEvent]:
    tool_call_id = self._extract_tool_call_id(payload)
    content = payload.get("content", [])
    
    events = []
    text_parts = []
    
    for i, block in enumerate(content):
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type == "image":
                # Extract image data
                source = block.get("source", {})
                events.append(self._make_media_attachment(
                    tool_call_id=tool_call_id,
                    content_index=i,
                    image_data=source.get("data"),
                    mime_type=source.get("media_type", "image/png"),
                ))
            elif block_type == "text":
                text_parts.append(block.get("text", ""))
    
    # Always emit text result for transcript
    if text_parts:
        events.append(ToolCallResultEvent(
            message_id=str(uuid4()),
            tool_call_id=tool_call_id,
            content="\n".join(text_parts),
        ))
    
    return events
```

**Codex** — Look for `item/screenshot` events and base64 in tool results:
```python
def _translate_screenshot(self, payload: dict) -> list[BaseEvent]:
    image_data = payload.get("imageData") or payload.get("data")
    if not image_data:
        return []
    
    tool_call_id = self._extract_tool_call_id(payload) or f"screenshot-{uuid4()}"
    
    return [self._make_media_attachment(
        tool_call_id=tool_call_id,
        content_index=0,
        image_data=image_data,
        mime_type="image/png",
        tool_name="Screenshot",
    )]
```

**OpenCode** — Parse JSON tool results for base64 image fields:
```python
def _extract_media_from_result(self, payload: dict) -> list[tuple[str, str, str]]:
    """Extract (mime_type, base64_data, label) tuples from nested result."""
    media = []
    
    def walk(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            # Check for base64 image patterns
            if "image" in obj and isinstance(obj["image"], str):
                media.append(("image/png", obj["image"], path or "image"))
            if "screenshot" in obj and isinstance(obj["screenshot"], str):
                media.append(("image/png", obj["screenshot"], path or "screenshot"))
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]")
    
    walk(payload)
    return media
```

### Mapper Base Extension

Add shared helper to base mapper interface:

```python
class AGUIMapperBase:
    """Shared implementation for media attachment handling."""
    
    def __init__(self, artifact_store: ArtifactStore | None = None):
        self._artifact_store = artifact_store
        self._spawn_id: str = ""
    
    def set_spawn_context(self, spawn_id: str) -> None:
        self._spawn_id = spawn_id
    
    def _make_media_attachment(
        self,
        *,
        tool_call_id: str,
        content_index: int,
        image_data: str,  # base64
        mime_type: str,
        tool_name: str = "ToolCall",
        caption: str | None = None,
    ) -> CustomEvent:
        attachment_id = f"media-{uuid4().hex[:8]}"
        message_id = f"msg-{uuid4().hex[:8]}"
        
        # Decode to measure size
        try:
            raw_bytes = base64.b64decode(image_data)
        except Exception:
            # Invalid base64 — emit error event instead
            return self._make_error_custom_event(
                f"Invalid base64 in tool result from {tool_name}"
            )
        
        size_bytes = len(raw_bytes)
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        
        # Decide inline vs artifact storage
        if size_bytes < 256 * 1024:
            # Inline
            return CustomEvent(
                name="media_attachment",
                value={
                    "id": attachment_id,
                    "message_id": message_id,
                    "kind": "image",
                    "mime_type": mime_type,
                    "size_bytes": size_bytes,
                    "sha256": sha256_hash,
                    "data": image_data,
                    "source": {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "content_index": content_index,
                    },
                    "caption": caption,
                },
            )
        else:
            # Store as artifact
            ext = _mime_to_extension(mime_type)
            artifact_key = make_artifact_key(
                self._spawn_id,
                f"media/{attachment_id}.{ext}",
            )
            
            if self._artifact_store:
                self._artifact_store.put(artifact_key, raw_bytes)
            
            return CustomEvent(
                name="media_attachment",
                value={
                    "id": attachment_id,
                    "message_id": message_id,
                    "kind": "image",
                    "mime_type": mime_type,
                    "size_bytes": size_bytes,
                    "sha256": sha256_hash,
                    "uri": f"artifacts://{artifact_key}",
                    "source": {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "content_index": content_index,
                    },
                    "caption": caption,
                },
            )
```

## Mapper Factory Changes

Pass artifact store to mappers:

```python
def get_agui_mapper(
    harness_id: HarnessId,
    spawn_id: str,
    artifact_store: ArtifactStore | None = None,
) -> AGUIMapper:
    mappers = {
        HarnessId.CLAUDE: ClaudeAGUIMapper,
        HarnessId.CODEX: CodexAGUIMapper,
        HarnessId.OPENCODE: OpenCodeAGUIMapper,
    }
    cls = mappers.get(harness_id)
    if cls is None:
        raise ValueError(f"No AG-UI mapper for {harness_id}")
    
    mapper = cls(artifact_store=artifact_store)
    mapper.set_spawn_context(spawn_id)
    return mapper
```

## Tool-Specific Detection

### Known Media-Producing Tools

| Tool Pattern | Expected Content |
|--------------|------------------|
| `mcp__playwright__browser_take_screenshot` | PNG base64 in result |
| `mcp__playwright__browser_snapshot` | HTML + optional screenshot |
| `Read` (image files) | Base64 image in content |
| `WebFetch` (image URLs) | Base64 image in content |

### Heuristic Detection

When tool name is unknown, apply heuristics:
1. Check for known base64 prefixes (`/9j/` for JPEG, `iVBOR` for PNG)
2. Check field names: `image`, `screenshot`, `data`, `base64`
3. Check MIME type hints in surrounding JSON

## Text Companion

Always emit a text `ToolCallResultEvent` alongside media attachments for transcript readability:

```python
def _emit_media_with_text(
    self,
    tool_call_id: str,
    media_events: list[CustomEvent],
    text_content: str | None = None,
) -> list[BaseEvent]:
    events: list[BaseEvent] = list(media_events)
    
    # Generate text summary if none provided
    if not text_content:
        attachment_count = len(media_events)
        text_content = f"[{attachment_count} media attachment(s)]"
    
    events.append(ToolCallResultEvent(
        message_id=str(uuid4()),
        tool_call_id=tool_call_id,
        content=text_content,
    ))
    
    return events
```

## Edge Cases

### Multiple Images in One Tool Result
Emit multiple `media_attachment` CustomEvents, each with unique `id` but same `tool_call_id`. The `content_index` field distinguishes them.

### Corrupted/Invalid Image Data
Log warning, skip `media_attachment` event, emit text result with `[Invalid image data]`.

### Unknown MIME Type
Default to `application/octet-stream`, emit with `kind: "file"`, let frontend decide rendering.

### Very Large Images (> 10MB)
Store as artifact, emit event with `uri`. Frontend can show thumbnail placeholder and lazy-load.

## Sequence Diagram

```
Harness                 Mapper                  WebSocket              Frontend
  |                       |                        |                       |
  |-- tool_result ------->|                        |                       |
  |   (with image)        |                        |                       |
  |                       |-- detect image         |                       |
  |                       |-- store artifact       |                       |
  |                       |                        |                       |
  |                       |-- ToolCallResultEvent->|-- TEXT_MESSAGE ------>|
  |                       |   "[1 attachment]"     |                       |
  |                       |                        |                       |
  |                       |-- CustomEvent -------->|-- CUSTOM ------------->|
  |                       |   "media_attachment"   |   name=media_attachment|
  |                       |                        |                       |
  |                       |                        |   (if uri reference)  |
  |                       |                        |<-- GET /artifacts ----|
  |                       |                        |--- image bytes ------>|
```

## Out of Scope

- Streaming large images progressively (future: chunked transfer)
- Image processing (resize, thumbnail generation) — see artifact-storage.md
- Audio/video media (future extension)
- Image diff/comparison tools
