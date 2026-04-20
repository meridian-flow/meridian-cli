# Simplified Harness UI Design

## TL;DR

Meridian UI is a **thin passthrough** to harnesses. Harnesses already have rich slash command interfaces for model switching, effort, skills, etc. Meridian doesn't abstract over this — it just sends commands through.

---

## Core Insight

Slash commands are just user messages. When you type `/model sonnet` in Claude Code, it's processed as input. Meridian can send `/model sonnet` as a user message and the harness handles it natively.

---

## What Harnesses Already Support

### Claude Code

| Command | Purpose |
|---------|---------|
| `/model sonnet` | Switch to Sonnet |
| `/model opus` | Switch to Opus |
| `/compact` | Summarize context |
| `/clear` | Fresh start |
| `/skill-name` | Activate skill |
| `--effort high` | Set effort (at launch) |

### Codex CLI

| Command | Purpose |
|---------|---------|
| `/model` | Switch model + reasoning effort |
| `/fast` | Toggle fast mode |
| `/compact` | Summarize context |
| `/plan` | Switch to plan mode |
| `/permissions` | Set permissions |

### OpenCode

TBD — probe for slash command interface.

---

## Simplified Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Meridian UI                               │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  Session Viewer  │  │  Message Input   │  │  Command Bar  │  │
│  │  (read-only for  │  │  (sends to       │  │  (UI for      │  │
│  │   past sessions) │  │   harness)       │  │   slash cmds) │  │
│  └──────────────────┘  └──────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Command Router                                │
│                                                                  │
│  User message    →  send_user_message(text)                     │
│  /model sonnet   →  send_user_message("/model sonnet")          │
│  /compact        →  send_user_message("/compact")               │
│  Switch harness  →  start new session (fresh)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 HarnessConnection (existing)                     │
│                                                                  │
│  send_user_message(text)  →  harness stdin/HTTP                 │
│  events()                 →  stream responses                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## What Changes vs Current Design

### Kill

| Concept | Why |
|---------|-----|
| RunPolicy / SessionPolicy / TurnIntent | Over-abstraction; harness handles this |
| InstructionStack (5 layers) | Skills are harness-native, not Meridian-injected |
| HarnessProjector abstraction | Just send commands through |
| Projection modes | No instruction injection needed |
| CapabilityManifest with scope mapping | Replace with simple command support list |
| Cross-harness fork with context | Session formats incompatible; just start fresh |

### Keep

| Concept | Why |
|---------|-----|
| HarnessConnection | Still need to talk to harnesses |
| AG-UI mapper | Still need to translate events for UI |
| Session viewer | Display past sessions |
| Spawn launch (RunPolicy equivalent) | Still need launch-time config |

### Simplify

| Before | After |
|--------|-------|
| CapabilityManifest with scope/degradation | Simple list: `supported_commands: ["/model", "/compact", ...]` |
| SessionPolicy with instruction stack | Just track active skills by ID |
| TurnIntent with steer/effort/constraints | Just the user message |

---

## Cross-Harness Switching

**Old approach (killed):**
- Fork session with context carrying
- Translate conversation between formats
- N×N conversion paths

**New approach:**
- Past session = read-only viewer (just render it)
- "Switch harness" = start fresh session on new harness
- User has context in their head / on screen
- No programmatic context transfer

---

## Intra-Harness Changes

These work because the harness handles them natively:

| Change | How |
|--------|-----|
| Switch model | Send `/model <name>` |
| Change effort | Send `/fast` or launch with `--effort` |
| Activate skill | Send `/skill-name` or `$skill-name` |
| Compact context | Send `/compact` |

---

## Simple Capability Model

```python
@dataclass
class HarnessCommands:
    """What slash commands does this harness support?"""
    
    harness_id: HarnessId
    
    # Slash commands the harness recognizes
    supported_commands: frozenset[str]
    
    # Launch-time flags (for initial session config)
    supported_launch_flags: frozenset[str]
    
    @classmethod
    def claude(cls) -> "HarnessCommands":
        return cls(
            harness_id=HarnessId.CLAUDE,
            supported_commands=frozenset([
                "/model", "/compact", "/clear", "/config",
                # Skills: /skill-name (dynamic, not enumerable)
            ]),
            supported_launch_flags=frozenset([
                "--model", "--effort", "--append-system-prompt",
                "--agent", "--approval",
            ]),
        )
    
    @classmethod
    def codex(cls) -> "HarnessCommands":
        return cls(
            harness_id=HarnessId.CODEX,
            supported_commands=frozenset([
                "/model", "/fast", "/compact", "/plan",
                "/permissions", "/clear", "/new", "/fork",
            ]),
            supported_launch_flags=frozenset([
                "--model", "--approval-mode",
            ]),
        )
```

---

## UI Behavior

### Command Bar

The UI exposes harness commands as buttons/dropdowns:

```
[Model: Sonnet ▼]  [Effort: High ▼]  [Compact]  [Clear]
```

Clicking "Model: Opus" sends `/model opus` to the harness.

### Session List

Shows past sessions. Click to view (read-only). "Open in Claude" / "Open in Codex" starts a fresh session.

### Skills

Skills are passed at launch time (`--agent`, skill flags) or activated via slash commands during session.

---

## Launch-Time vs Runtime

| Config | When | How |
|--------|------|-----|
| Harness | Launch | Can't change mid-session |
| Initial model | Launch | `--model` flag |
| Model switch | Runtime | `/model` command |
| Effort | Launch or Runtime | `--effort` flag or harness command |
| Skills | Launch | `--agent`, skill flags |
| Skill activation | Runtime | `/skill-name` command |

---

## Implementation Plan

1. **Keep existing connection layer** — `HarnessConnection.send_user_message()` already works
2. **Add command routing** — UI sends slash commands as user messages
3. **Add simple capability list** — so UI knows what commands to show
4. **Add session viewer** — render past sessions read-only
5. **Kill policy layer design** — don't build RunPolicy/SessionPolicy/TurnIntent

---

## What About Agent Instructions?

For spawn (`meridian spawn -a reviewer`):
- Agent profile is passed at launch via `--agent` or `--append-system-prompt`
- This happens at spawn creation, not via slash commands
- No change needed

For UI sessions:
- User starts session with optional agent selection
- Agent passed at launch time
- Mid-session agent change = start new session (same as harness switch)

---

## Sources

- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)
- [Codex CLI slash commands](https://developers.openai.com/codex/cli/slash-commands)

---

## Appendix: OpenCode Commands

From [OpenCode Commands](https://opencode.ai/docs/commands/):

| Command | Purpose |
|---------|---------|
| `/model [name]` | Switch model |
| `/agent [name]` | Switch agent |
| `/session [id]` | Switch session |
| `/sessions` | List sessions |
| `/new` | New session |
| `/compact` | Toggle compact mode |
| `/clear` | Clear screen |
| `/help` | Show help |

OpenCode also supports the slash command pattern. All three major harnesses (Claude Code, Codex, OpenCode) have native slash command interfaces for model switching, session management, and context control.

This confirms the design: **Meridian UI just passes commands through**.
