# Frontend Requirements

## Target User

Biomedical researchers. Non-technical. Want something simple that helps with their work.

## Core Concept

**Agent = the configuration.**

User picks an assistant type. That's it. The agent profile handles everything else behind the scenes (model, harness, effort, system prompt, skills).

## UI

```
┌──────────────┬───────────────────────────────────────────────┐
│ Sidebar      │                                               │
│              │                                               │
│ + New Chat   │  ┌─────────────────────────────────────────┐  │
│              │  │ Ask anything...                         │  │
│ Chats        │  └─────────────────────────────────────────┘  │
│ ● Current    │                                               │
│ ○ Yesterday  │  [Research Helper ▾]                  [Send]  │
│ ○ Earlier    │                                               │
└──────────────┴───────────────────────────────────────────────┘
```

### Controls

- **Agent selector** — dropdown of available assistants
- **Send button** — send message
- **That's it**

No Quick/Thorough. No model picker. No harness toggle. No effort slider.

### Agent Selector

Shows user-facing agents provided by the system:
- Research Helper
- Data Analyst
- Literature Reviewer
- Script Writer
- (whatever agents are configured)

Agent is **locked after first message** — can't change mid-session.

### What Agent Profiles Define

Behind the scenes, each agent profile specifies:
- Model (e.g., claude-opus-4)
- Harness (claude/codex/opencode)
- Effort/thinking level
- System prompt
- Skills

User doesn't see or configure any of this.

## Session Lifecycle

- Pick agent → start chatting
- Agent locked after first message
- Session persists (survives browser close, server restart)
- Can have multiple sessions with different agents

## Sidebar

- List of chats
- Click to switch
- New Chat button
- Grouped by recency (Today, Yesterday, etc.)

## Project/Folder

- User opens a project folder
- All chats in sidebar are for that project
- Switch projects = different chat history

## Remote Access

- Server can bind to 0.0.0.0
- Token auth for remote connections
- Same UI works on phone

## Non-Goals

- Model selection UI
- Harness selection UI
- Effort/thinking controls
- Advanced configuration
- Multiple folders per project
