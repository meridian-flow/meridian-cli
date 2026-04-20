# Harness Control Capability Matrix

Based on live probing of each harness's API mode (not TUI).

## Transport Summary

| Harness | API Transport | Protocol |
|---------|---------------|----------|
| Claude Code | Subprocess stdin/stdout | NDJSON (stream-json) |
| Codex | WebSocket or stdio | JSON-RPC 2.0 |
| OpenCode | HTTP | REST + SSE |

---

## Control Capabilities by Harness

### Claude Code (stream-json)

| Capability | Works? | Method | Notes |
|------------|--------|--------|-------|
| User messages | ✅ | `{"type":"user","message":{...}}` | Standard input |
| `/compact` | ✅ | Send as user message text | Returns synthetic response |
| `/skill-name` | ✅ | Send as user message text | Triggers skill activation |
| `/model <name>` | ⚠️ | Send as user message text | Recognized but returned "not available in this environment" |
| Control objects | ❌ | N/A | `{"type":"config",...}` ignored |
| Interrupt | ✅ | SIGINT to process | Existing connection supports this |

**Conclusion**: Slash commands work as user text. Model switching recognized but may be blocked in some environments. No structured control protocol.

### Codex (JSON-RPC app-server)

| Capability | Works? | Method | Notes |
|------------|--------|--------|-------|
| User messages | ✅ | `turn/start` RPC | With `input` field |
| Model switch | ✅ | `thread/start` RPC | `model` parameter |
| `/model <name>` | ✅ | User message text | Also works in `exec --json` |
| `$skill-name` | ✅ | User message text | Interpreted as skill command |
| Effort/reasoning | ✅ | `thread/start`/`thread/resume` | `model_reasoning_effort` param |
| Compact | ✅ | `thread/compact/start` RPC | Structured endpoint |
| Skills config | ✅ | `skills/config/write` RPC | Structured endpoint |
| Steer | ✅ | `turn/steer` RPC | Mid-turn steering |
| Interrupt | ✅ | `turn/interrupt` RPC | Structured endpoint |
| Fork | ✅ | `thread/fork` RPC | Structured endpoint |
| Resume | ✅ | `thread/resume` RPC | Structured endpoint |

**Conclusion**: Richest control surface. Both slash/dollar text AND structured RPCs work. Prefer structured RPCs for reliability.

### OpenCode (HTTP API)

| Capability | Works? | Method | Notes |
|------------|--------|--------|-------|
| User messages | ✅ | `POST /session/{id}/message` | With `parts` array |
| Model (session) | ✅ | `POST /session` | `model` in creation payload |
| Model (per-msg) | ✅ | `POST /session/{id}/message` | Optional `model?` param |
| Commands | ✅ | `POST /session/{id}/command` | Slash command passthrough |
| Global config | ✅ | `PATCH /global/config` | Runtime config changes |
| Compact/summarize | ✅ | `POST /session/{id}/summarize` | Explicit endpoint |
| Fork | ✅ | `POST /session/{id}/fork` | Explicit endpoint |
| Abort | ✅ | `POST /session/{id}/abort` | Explicit endpoint |
| Effort | ❌ | N/A | Not supported in streaming |
| SSE events | ✅ | `GET /event` | Real-time event stream |

**Conclusion**: HTTP REST API with explicit endpoints. Model configurable at session and message level. No effort support.

---

## App Control Abstraction

The app needs a unified control interface that maps to harness-specific implementations:

```python
class HarnessControl(Protocol):
    """Unified control interface for harness sessions."""
    
    async def send_message(self, text: str) -> None:
        """Send user message."""
        ...
    
    async def switch_model(self, model: str) -> ControlResult:
        """Switch model mid-session. Returns success/failure/needs_restart."""
        ...
    
    async def set_effort(self, level: str) -> ControlResult:
        """Set effort/reasoning level. Returns success/failure/unsupported."""
        ...
    
    async def activate_skill(self, skill: str) -> ControlResult:
        """Activate a skill. Returns success/failure."""
        ...
    
    async def compact(self) -> ControlResult:
        """Compact/summarize context."""
        ...
    
    async def interrupt(self) -> None:
        """Interrupt current turn."""
        ...

@dataclass
class ControlResult:
    success: bool
    method: Literal["live", "restart_required", "unsupported"]
    message: str | None = None
```

### Implementation per Harness

```python
class ClaudeControl(HarnessControl):
    async def switch_model(self, model: str) -> ControlResult:
        # Try slash command first
        await self.send_message(f"/model {model}")
        # Check response — if "not available", return restart_required
        return ControlResult(success=False, method="restart_required")
    
    async def activate_skill(self, skill: str) -> ControlResult:
        await self.send_message(f"/{skill}")
        return ControlResult(success=True, method="live")

class CodexControl(HarnessControl):
    async def switch_model(self, model: str) -> ControlResult:
        # Use structured RPC
        await self._rpc("thread/start", {"model": model})
        return ControlResult(success=True, method="live")
    
    async def set_effort(self, level: str) -> ControlResult:
        await self._rpc("thread/resume", {"model_reasoning_effort": level})
        return ControlResult(success=True, method="live")

class OpenCodeControl(HarnessControl):
    async def switch_model(self, model: str) -> ControlResult:
        # Per-message model override on next message
        self._next_message_model = model
        return ControlResult(success=True, method="live")
    
    async def set_effort(self, level: str) -> ControlResult:
        return ControlResult(success=False, method="unsupported")
```

---

## UI Implications

| Control | Claude | Codex | OpenCode | UI Behavior |
|---------|--------|-------|----------|-------------|
| Model switch | ⚠️ May need restart | ✅ Live | ✅ Live (next msg) | Show spinner, handle restart if needed |
| Effort | ❌ Launch only | ✅ Live | ❌ Unsupported | Disable control for Claude/OpenCode |
| Skills | ✅ Live | ✅ Live | ? | Enable for all |
| Compact | ✅ Live | ✅ Live | ✅ Live | Enable for all |

The UI should:
1. Query harness capabilities on session start
2. Enable/disable controls based on what's supported
3. Handle `restart_required` by prompting user or auto-restarting with `--resume`
4. Show appropriate feedback for each control action
