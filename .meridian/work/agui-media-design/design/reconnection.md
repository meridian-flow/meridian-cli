# Reconnection & Replay Design

## Problem

When WebSocket connections drop (network blips, client refresh, mobile backgrounding), clients lose stream position and miss events. AG-UI specifies `MESSAGES_SNAPSHOT` for re-synchronization, but meridian currently has no event persistence or replay capability.

## Design Goals

1. Assign stable IDs to every streamed event
2. Persist event stream for replay
3. Implement cursor-based resume
4. Support `MESSAGES_SNAPSHOT` for full history load
5. Handle reconnection across harness boundaries

## Event ID Scheme

### Format

Every AG-UI event gains an `eventId` extension field:

```typescript
interface ExtendedBaseEvent extends BaseEvent {
  eventId?: string;          // Monotonic identifier
  timestamp?: string;        // ISO 8601
}
```

**Event ID format:** `{spawn_id}:{sequence_number}`
- `sequence_number` is a monotonically increasing integer per spawn
- Example: `p42:00000001`, `p42:00000042`
- Zero-padded to 8 digits for lexicographic ordering

### Assignment

Event IDs are assigned in the WebSocket outbound path, not in mappers:

```python
class EventStream:
    """Wraps outbound events with IDs and persistence."""
    
    def __init__(
        self,
        spawn_id: SpawnId,
        event_store: EventStore,
    ):
        self._spawn_id = spawn_id
        self._event_store = event_store
        self._sequence = 0
    
    async def emit(
        self,
        websocket: WebSocketClient,
        event: BaseEvent,
    ) -> str:
        """Emit event with ID to websocket and persist."""
        
        self._sequence += 1
        event_id = f"{self._spawn_id}:{self._sequence:08d}"
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Serialize with extension fields
        payload = event.model_dump(by_alias=True, exclude_none=True)
        payload["eventId"] = event_id
        payload["timestamp"] = timestamp
        
        # Persist before send (write-ahead)
        await self._event_store.append(self._spawn_id, payload)
        
        # Send to client
        await websocket.send_text(json.dumps(payload))
        
        return event_id
```

## Event Persistence

### Storage Format

Events are stored as append-only JSONL under spawn directory:

```
.meridian/spawns/{spawn_id}/
├── events.jsonl              # Append-only event log
├── events.jsonl.flock        # File lock
└── snapshots/
    ├── 00001000.snapshot.json  # Snapshot at event 1000
    └── 00002000.snapshot.json  # Snapshot at event 2000
```

### Event Log Entry

```json
{"eventId": "p42:00000001", "timestamp": "2026-04-20T12:00:00Z", "type": "RUN_STARTED", "thread_id": "p42", "run_id": "p42-run-1"}
{"eventId": "p42:00000002", "timestamp": "2026-04-20T12:00:01Z", "type": "TEXT_MESSAGE_START", "message_id": "msg-abc", "role": "assistant"}
```

### Snapshots

Periodic snapshots for efficient replay:

```json
{
  "eventId": "p42:00001000",
  "timestamp": "2026-04-20T12:30:00Z",
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": [{"type": "text", "text": "Hello"}]
    },
    {
      "id": "msg-002", 
      "role": "assistant",
      "content": [{"type": "text", "text": "Hi there!"}]
    }
  ],
  "state": {
    "run_id": "p42-run-1",
    "status": "running"
  }
}
```

**Snapshot frequency:** Every 1000 events or 5 minutes of activity.

## Cursor-Based Resume

### WebSocket Connect with Cursor

Client can provide last-seen event ID on connect:

```typescript
// Client connects with cursor
const ws = new WebSocket(`/api/spawns/p42/ws?cursor=p42:00000500`);
```

### Server Resume Logic

```python
async def spawn_websocket_with_resume(
    websocket: WebSocketClient,
    spawn_id: str,
    cursor: str | None,
    manager: SpawnManager,
    event_store: EventStore,
) -> None:
    await websocket.accept()
    
    # Load connection state
    connection = manager.get_connection(SpawnId(spawn_id))
    is_live = connection is not None
    
    # Replay from cursor
    if cursor:
        sequence = parse_event_id(cursor)
        if sequence is not None:
            # Replay missed events
            async for event in event_store.replay_from(spawn_id, sequence + 1):
                await websocket.send_text(json.dumps(event))
    else:
        # No cursor — send MESSAGES_SNAPSHOT for full history
        snapshot = await event_store.get_latest_snapshot(spawn_id)
        if snapshot:
            await _send_event(websocket, MessagesSnapshotEvent(
                messages=snapshot["messages"],
            ))
    
    if is_live:
        # Continue with live stream
        await _stream_live_events(websocket, spawn_id, manager, event_store)
    else:
        # Spawn finished — send terminal events if not already sent
        await _send_terminal_events(websocket, spawn_id, event_store)
```

### Resume Edge Cases

**Cursor too old (events purged):**
```python
if not event_store.has_event(spawn_id, sequence):
    # Fall back to snapshot + available events
    snapshot = event_store.get_snapshot_before(spawn_id, sequence)
    if snapshot:
        await _send_snapshot(websocket, snapshot)
        await _replay_from(websocket, snapshot["eventId"])
    else:
        # No snapshot — send error, client should reload
        await _send_error(websocket, "cursor expired, reload required")
        return
```

**Cursor ahead of server:**
```python
latest = event_store.get_latest_sequence(spawn_id)
if sequence > latest:
    # Client has events server doesn't — possible corruption
    logger.warning(f"Client cursor {cursor} ahead of server {latest}")
    # Proceed with live stream, client will dedupe
```

## MESSAGES_SNAPSHOT Support

### Event Type

AG-UI defines `MESSAGES_SNAPSHOT` for full history delivery:

```typescript
interface MessagesSnapshotEvent {
  type: "MESSAGES_SNAPSHOT";
  messages: Message[];
  thread_id?: string;
}

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: MessageContent[];
  created_at?: string;
  attachments?: Attachment[];
}
```

### Generation

Build snapshot from event log:

```python
class MessageBuilder:
    """Reconstruct messages from event stream."""
    
    def build_snapshot(
        self,
        events: list[dict],
    ) -> list[dict]:
        messages = []
        current_message: dict | None = None
        current_content: list[dict] = []
        
        for event in events:
            event_type = event.get("type")
            
            if event_type == "TEXT_MESSAGE_START":
                if current_message:
                    messages.append(self._finalize_message(
                        current_message, current_content
                    ))
                current_message = {
                    "id": event["message_id"],
                    "role": event["role"],
                    "created_at": event.get("timestamp"),
                }
                current_content = []
            
            elif event_type == "TEXT_MESSAGE_CONTENT":
                if current_message:
                    # Accumulate text
                    delta = event.get("delta", "")
                    if current_content and current_content[-1].get("type") == "text":
                        current_content[-1]["text"] += delta
                    else:
                        current_content.append({"type": "text", "text": delta})
            
            elif event_type == "TEXT_MESSAGE_END":
                if current_message:
                    messages.append(self._finalize_message(
                        current_message, current_content
                    ))
                    current_message = None
                    current_content = []
            
            elif event_type == "CUSTOM" and event.get("name") == "media_attachment":
                # Include media as attachment
                if current_message:
                    attachments = current_message.setdefault("attachments", [])
                    attachments.append(event["value"])
        
        return messages
```

## Thread History Endpoint

### GET /api/spawns/{spawn_id}/history

REST endpoint for loading thread history without WebSocket:

**Request:**
```
GET /api/spawns/p42/history?format=snapshot
```

**Response:**
```json
{
  "thread_id": "p42",
  "run_id": "p42-run-1",
  "status": "succeeded",
  "messages": [
    {
      "id": "msg-001",
      "role": "user",
      "content": [{"type": "text", "text": "What's in this image?"}],
      "attachments": [{"id": "att-001", "kind": "image", "uri": "artifacts://p42/uploads/abc.png"}]
    },
    {
      "id": "msg-002",
      "role": "assistant",
      "content": [{"type": "text", "text": "I see a screenshot of..."}],
      "attachments": [{"id": "media-001", "kind": "image", "uri": "artifacts://p42/media/screenshot.png"}]
    }
  ],
  "event_count": 42,
  "latest_event_id": "p42:00000042"
}
```

### GET /api/spawns/{spawn_id}/events

Raw event log access for debugging:

**Request:**
```
GET /api/spawns/p42/events?from=p42:00000010&limit=100
```

**Response:**
```json
{
  "events": [
    {"eventId": "p42:00000011", "type": "TEXT_MESSAGE_CONTENT", ...},
    {"eventId": "p42:00000012", "type": "TEXT_MESSAGE_END", ...}
  ],
  "next_cursor": "p42:00000111",
  "has_more": true
}
```

## Event Store Implementation

```python
class EventStore:
    """Append-only event persistence with snapshot support."""
    
    def __init__(self, state_root: Path):
        self._state_root = state_root
    
    def _events_path(self, spawn_id: SpawnId) -> Path:
        return self._state_root / "spawns" / str(spawn_id) / "events.jsonl"
    
    async def append(
        self,
        spawn_id: SpawnId,
        event: dict,
    ) -> None:
        """Append event to log with write-ahead semantics."""
        path = self._events_path(spawn_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        line = json.dumps(event, ensure_ascii=False) + "\n"
        async with aiofiles.open(path, "a") as f:
            await f.write(line)
        
        # Check if snapshot needed
        sequence = self._parse_sequence(event.get("eventId", ""))
        if sequence and sequence % 1000 == 0:
            await self._create_snapshot(spawn_id, sequence)
    
    async def replay_from(
        self,
        spawn_id: SpawnId,
        from_sequence: int,
    ) -> AsyncIterator[dict]:
        """Replay events starting from sequence number."""
        path = self._events_path(spawn_id)
        if not path.exists():
            return
        
        async with aiofiles.open(path, "r") as f:
            async for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    event_seq = self._parse_sequence(event.get("eventId", ""))
                    if event_seq and event_seq >= from_sequence:
                        yield event
                except json.JSONDecodeError:
                    continue
    
    def get_latest_sequence(self, spawn_id: SpawnId) -> int:
        """Get the latest event sequence number."""
        path = self._events_path(spawn_id)
        if not path.exists():
            return 0
        
        # Read last line
        with open(path, "rb") as f:
            f.seek(0, 2)  # End
            size = f.tell()
            if size == 0:
                return 0
            
            # Find last newline
            pos = size - 1
            while pos > 0:
                f.seek(pos)
                if f.read(1) == b"\n":
                    break
                pos -= 1
            
            line = f.read().decode().strip()
            if not line:
                return 0
            
            try:
                event = json.loads(line)
                return self._parse_sequence(event.get("eventId", "")) or 0
            except json.JSONDecodeError:
                return 0
```

## Reconnection Flow

```
Client                          Server                         EventStore
  |                               |                                |
  |-- WS connect (cursor=p42:50) ->|                                |
  |                               |-- get events from 51 ---------->|
  |                               |<-- events 51-100 ---------------|
  |<-- replay events 51-100 ------|                                |
  |                               |                                |
  |                               |-- subscribe to live stream     |
  |<-- live events 101+ ----------|                                |
  |                               |                                |
  |   (disconnect)                |                                |
  |                               |                                |
  |-- WS connect (cursor=p42:120)->|                                |
  |                               |-- get events from 121 --------->|
  |                               |<-- events 121-150 --------------|
  |<-- replay events 121-150 -----|                                |
  |<-- live events 151+ ----------|                                |
```

## Implementation Phases

### Phase 1: Event IDs & Persistence
- Add `eventId` and `timestamp` to outbound events
- Implement `EventStore` with append-only log
- No replay yet — clients restart from scratch

### Phase 2: Cursor Resume
- Accept `cursor` query param on WebSocket connect
- Implement `replay_from()` for missed events
- Handle cursor-too-old fallback

### Phase 3: Snapshots
- Periodic snapshot generation
- `MESSAGES_SNAPSHOT` event on fresh connect
- REST `/history` endpoint

### Phase 4: Optimization
- Snapshot-based replay for long sessions
- Event log rotation/cleanup
- Client-side deduplication

## Edge Cases

### Multiple WebSocket Clients
Each client tracks its own cursor. Event IDs are per-spawn, so all clients see same IDs.

### Harness Restart Mid-Session
New `RUN_STARTED` event gets next sequence number. Clients see continuous stream with gap in run_id.

### Event Log Corruption
If log is corrupted (partial write), skip malformed lines and continue. Log warning.

### Long-Running Sessions
After 100K events, rotate log and keep last N events + latest snapshot. Older events become unavailable for replay.

## Out of Scope

- Cross-spawn event correlation
- Real-time event sync between server instances
- Event compression
- Client-side event caching
