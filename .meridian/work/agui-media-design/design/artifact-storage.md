# Artifact Storage Design

## Problem

Media attachments need persistent storage with secure access. The existing `ArtifactStore` provides basic put/get/list, but lacks:
- HTTP endpoint for frontend fetch
- Security validation (ownership, path traversal)
- Thumbnail generation for large images
- MIME type inference
- Upload handling

## Design Goals

1. Extend existing `ArtifactStore` with media-specific operations
2. Add REST endpoints for artifact fetch and upload
3. Implement security controls (spawn ownership, path validation)
4. Support thumbnails for large images
5. Enable cross-spawn artifact references (with explicit sharing)

## Directory Structure

```
.meridian/spawns/{spawn_id}/
├── artifacts/
│   ├── media/                    # Agent-generated media
│   │   ├── {uuid}.png
│   │   ├── {uuid}.pdf
│   │   └── {uuid}.thumb.png      # Generated thumbnail
│   └── uploads/                  # User-uploaded attachments
│       ├── {uuid}.png
│       └── {uuid}.pdf
├── report.md
├── heartbeat
└── debug.jsonl
```

### Path Conventions

| Path Pattern | Purpose | Access |
|--------------|---------|--------|
| `{spawn}/artifacts/media/*` | Agent output | Read by spawn owner |
| `{spawn}/artifacts/uploads/*` | User input | Read/write by spawn owner |
| `{spawn}/artifacts/shared/*` | Cross-spawn refs | Read by any spawn in work item |

## API Endpoints

### GET /api/spawns/{spawn_id}/artifacts/{path:path}

Fetch artifact content by path.

**Request:**
```
GET /api/spawns/p42/artifacts/media/abc123.png
Authorization: Bearer <session_token>  # future
```

**Response:**
```
HTTP/1.1 200 OK
Content-Type: image/png
Content-Length: 123456
Cache-Control: private, max-age=3600
ETag: "sha256:abc123..."

<binary content>
```

**Security:**
- Validate spawn exists
- Normalize path, reject `..` traversal
- Validate path stays under `artifacts/`
- Future: check session ownership

**Error responses:**
- `400` — Invalid path (traversal attempt)
- `404` — Spawn or artifact not found
- `403` — Access denied (future)

### POST /api/spawns/{spawn_id}/artifacts/upload

Upload attachment for user message.

**Request:**
```
POST /api/spawns/p42/artifacts/upload
Content-Type: multipart/form-data

------boundary
Content-Disposition: form-data; name="file"; filename="screenshot.png"
Content-Type: image/png

<binary content>
------boundary--
```

**Response:**
```json
{
  "artifact_uri": "artifacts://p42/uploads/550e8400.png",
  "size_bytes": 123456,
  "mime_type": "image/png",
  "sha256": "abc123..."
}
```

**Security:**
- Validate spawn exists and is active (not terminal)
- Check file size < 50 MB
- Validate MIME type against allowlist
- Generate UUID filename to prevent path injection
- Scan for malicious content (future)

**Error responses:**
- `400` — Invalid file or MIME type
- `404` — Spawn not found
- `410` — Spawn already terminal
- `413` — File too large

### GET /api/spawns/{spawn_id}/artifacts

List artifacts for a spawn.

**Request:**
```
GET /api/spawns/p42/artifacts?prefix=media/
```

**Response:**
```json
{
  "items": [
    {
      "path": "media/abc123.png",
      "size_bytes": 123456,
      "mime_type": "image/png",
      "created_at": "2026-04-20T12:00:00Z",
      "has_thumbnail": true
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

### GET /api/spawns/{spawn_id}/artifacts/{path}/thumbnail

Fetch thumbnail for image artifact (generated on demand).

**Request:**
```
GET /api/spawns/p42/artifacts/media/abc123.png/thumbnail?size=256
```

**Response:**
```
HTTP/1.1 200 OK
Content-Type: image/jpeg
Content-Length: 12345

<thumbnail bytes>
```

**Thumbnail generation:**
- Lazy generation on first request
- Cache as `{original}.thumb.jpg`
- Max dimension (default 256px, max 512px)
- JPEG at 80% quality for size
- Only for `image/*` MIME types

## Implementation

### ArtifactStore Extension

```python
class MediaArtifactStore(BaseModel):
    """Extended artifact store with media operations."""
    
    model_config = ConfigDict()
    root_dir: Path
    
    def put_media(
        self,
        spawn_id: SpawnId,
        data: bytes,
        *,
        mime_type: str,
        category: str = "media",  # "media" | "uploads"
        filename: str | None = None,
    ) -> ArtifactRef:
        """Store media and return reference."""
        
        ext = _mime_to_extension(mime_type)
        artifact_id = uuid4().hex[:8]
        name = filename or f"{artifact_id}.{ext}"
        
        key = make_artifact_key(spawn_id, f"{category}/{name}")
        self.put(key, data)
        
        return ArtifactRef(
            uri=f"artifacts://{key}",
            size_bytes=len(data),
            mime_type=mime_type,
            sha256=hashlib.sha256(data).hexdigest(),
        )
    
    def get_or_generate_thumbnail(
        self,
        key: ArtifactKey,
        max_size: int = 256,
    ) -> bytes | None:
        """Get cached thumbnail or generate from original."""
        
        thumb_key = ArtifactKey(f"{key}.thumb.jpg")
        
        if self.exists(thumb_key):
            return self.get(thumb_key)
        
        if not self.exists(key):
            return None
        
        original = self.get(key)
        thumbnail = self._generate_thumbnail(original, max_size)
        
        if thumbnail:
            self.put(thumb_key, thumbnail)
        
        return thumbnail
    
    def _generate_thumbnail(
        self,
        image_data: bytes,
        max_size: int,
    ) -> bytes | None:
        """Generate JPEG thumbnail using Pillow."""
        try:
            from PIL import Image
            import io
            
            img = Image.open(io.BytesIO(image_data))
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            output = io.BytesIO()
            img.save(output, format="JPEG", quality=80)
            return output.getvalue()
        except Exception:
            return None
```

### Route Registration

```python
def register_artifact_routes(
    app: FastAPI,
    spawn_manager: SpawnManager,
    artifact_store: MediaArtifactStore,
    http_exception: HTTPExceptionCallable,
) -> None:
    
    @app.get("/api/spawns/{spawn_id}/artifacts/{path:path}")
    async def get_artifact(spawn_id: str, path: str) -> Response:
        spawn_id = validate_spawn_id(spawn_id, http_exception)
        
        # Security: normalize and validate path
        normalized = _normalize_artifact_path(path)
        if normalized is None:
            raise http_exception(400, "invalid artifact path")
        
        key = make_artifact_key(spawn_id, normalized)
        if not artifact_store.exists(key):
            raise http_exception(404, "artifact not found")
        
        content = artifact_store.get(key)
        mime_type = _infer_mime_type(normalized)
        
        return Response(
            content=content,
            media_type=mime_type,
            headers={
                "Cache-Control": "private, max-age=3600",
                "ETag": f'"{hashlib.sha256(content).hexdigest()[:16]}"',
            },
        )
    
    @app.post("/api/spawns/{spawn_id}/artifacts/upload")
    async def upload_artifact(
        spawn_id: str,
        file: UploadFile,
    ) -> dict:
        spawn_id = validate_spawn_id(spawn_id, http_exception)
        record = require_spawn(
            spawn_manager.state_root, spawn_id, http_exception
        )
        
        if record.status in TERMINAL_SPAWN_STATUSES:
            raise http_exception(410, "spawn already terminal")
        
        # Validate file
        content = await file.read()
        if len(content) > 50 * 1024 * 1024:
            raise http_exception(413, "file too large (max 50MB)")
        
        mime_type = file.content_type or _infer_mime_type(file.filename or "")
        if not _is_allowed_mime_type(mime_type):
            raise http_exception(400, f"unsupported file type: {mime_type}")
        
        ref = artifact_store.put_media(
            spawn_id,
            content,
            mime_type=mime_type,
            category="uploads",
            filename=file.filename,
        )
        
        return {
            "artifact_uri": ref.uri,
            "size_bytes": ref.size_bytes,
            "mime_type": ref.mime_type,
            "sha256": ref.sha256,
        }
```

### Path Normalization

```python
def _normalize_artifact_path(path: str) -> str | None:
    """Normalize and validate artifact path, return None if invalid."""
    
    # Remove leading/trailing slashes
    path = path.strip("/")
    
    # Check for traversal
    parts = Path(path).parts
    if ".." in parts:
        return None
    if any(part.startswith(".") for part in parts):
        return None
    
    # Must be under artifacts/
    if not path.startswith(("media/", "uploads/", "shared/")):
        return None
    
    return path


def _is_allowed_mime_type(mime_type: str) -> bool:
    """Check if MIME type is in allowlist."""
    
    allowed_prefixes = [
        "image/",
        "application/pdf",
        "text/plain",
        "text/markdown",
        "text/csv",
    ]
    return any(mime_type.startswith(p) for p in allowed_prefixes)


def _infer_mime_type(filename: str) -> str:
    """Infer MIME type from filename extension."""
    
    ext_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
    }
    
    ext = Path(filename).suffix.lower()
    return ext_map.get(ext, "application/octet-stream")


def _mime_to_extension(mime_type: str) -> str:
    """Convert MIME type to file extension."""
    
    mime_map = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/svg+xml": "svg",
        "application/pdf": "pdf",
        "text/plain": "txt",
        "text/markdown": "md",
    }
    
    return mime_map.get(mime_type, "bin")
```

## URI Resolution

Frontend receives `artifacts://` URIs, resolves to HTTP:

```typescript
function resolveArtifactUri(uri: string, spawnId: string): string {
  if (!uri.startsWith("artifacts://")) {
    return uri;
  }
  
  // artifacts://p42/media/abc.png -> /api/spawns/p42/artifacts/media/abc.png
  const path = uri.replace("artifacts://", "");
  const [uriSpawnId, ...rest] = path.split("/");
  
  // Validate spawn ID matches expected
  if (uriSpawnId !== spawnId) {
    console.warn(`Cross-spawn artifact reference: ${uri}`);
  }
  
  return `/api/spawns/${uriSpawnId}/artifacts/${rest.join("/")}`;
}
```

## Security Considerations

### Path Traversal
- Normalize all paths before use
- Reject `..` and hidden files (`.`)
- Validate path stays under `artifacts/` subdirectory

### Spawn Ownership
- Currently: any client with spawn_id can access artifacts
- Future: validate session token owns the spawn
- Future: check work_id for shared artifacts

### Content Validation
- Validate MIME type against allowlist
- Future: scan uploaded files for malicious content
- Reject executable file types

### Size Limits
- Upload: 50 MB max per file
- Total per spawn: 500 MB (future, soft limit with warning)
- Inline base64 in events: 256 KB

## Cleanup

Artifacts are cleaned up with spawn state:
- When spawn is deleted via `meridian spawn delete`
- When spawn dir is reaped by orphan cleanup
- Manual cleanup via `meridian spawn cleanup --artifacts`

Work-level shared artifacts survive individual spawn cleanup but are removed when work item is deleted.

## Out of Scope

- Streaming large artifact uploads
- Artifact deduplication (same sha256)
- CDN/external storage backends
- Artifact versioning
- Cross-work-item sharing
