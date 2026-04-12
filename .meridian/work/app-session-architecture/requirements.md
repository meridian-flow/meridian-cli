# App UI Redesign — Requirements

## Overview

Redesign the meridian app frontend from a single-spawn-at-a-time page to a session-based chat interface with persistent sidebar navigation and rich composer controls.

## Current State

- React + Radix UI + Tailwind frontend in `frontend/`
- Single-page: SpawnSelector (harness dropdown + prompt) → ThreadView + Composer
- No sidebar, no session list, no model browser, no routing
- Backend: FastAPI + WebSocket, AG-UI event mapping, SpawnManager
- Existing components: activity-stream (TextItem, ReasoningItem, ToolCallItem, etc.), ThreadView, Composer, SpawnSelector, SpawnHeader, StatusBar

## Target Layout

```
┌─────────────┬──────────────────────────────────────────┐
│  Sidebar     │  Empty state:                            │
│              │    Logo centered, tagline, description   │
│  Sessions    │    Composer at bottom                    │
│  ├ session 1 │                                          │
│  ├ session 2 │  Active state:                           │
│  └ session 3 │    Chat messages (existing ThreadView)   │
│              │    Composer at bottom                     │
│  + New Chat  │                                          │
└─────────────┴──────────────────────────────────────────┘
```

- **Sidebar**: Session list as primary navigation. Create new sessions, switch between existing ones. Similar to ChatGPT/Claude sidebar UX.
- **Main pane empty state**: Centered logo + "Meridian" + brief description of what it does. Composer visible at bottom — user can start typing immediately (like ChatGPT landing).
- **Main pane active state**: Thread view (existing activity stream) + Composer.

## Composer Controls

The composer has the message input area plus controls for configuring the session before/during use:

### Harness Selector
- **NOT a dropdown**. Three icons representing Claude, Codex, OpenCode arranged as a small tab-bar/toggle group.
- Selecting a harness changes which models are shown in the model selector.

### Model Selector
- **NOT a dropdown**. Interactive model browser.
- When user clicks to select a model, shows a pane/panel with the 3 harness icons as a sidebar/tab strip on the left, and the main area shows all available models for the selected harness.
- Each model shown as a card with information from `meridian models list` (name, strengths, cost tier, context window, etc.).
- User picks a model, panel closes, selection shown in composer.

### Effort / Thinking Level
- Controls how much thinking/effort the model puts in.
- Maps to harness-specific slash commands injected via the existing inject/control socket mechanism:
  - Claude: maps to thinking budget or similar
  - Codex: maps to effort level
  - OpenCode: maps to appropriate config
- UI could be a segmented control or small selector (low/medium/high/max or similar).

### Agent Profile Selector
- Choose from available agent profiles (from `.agents/agents/`).
- **Locks after session starts** — cannot change agent mid-session since skills and system prompt are set at session creation.
- Can be left empty for default/no-agent behavior.

## Backend Requirements

- **Session list endpoint**: Return active/recent sessions with metadata (spawn_id, harness, model, agent, created_at, last_message preview).
- **Model list endpoint**: Return available models grouped by harness, with metadata from `meridian models list`.
- **Effort injection**: Map effort level to harness-specific slash command, send via existing inject/control socket.
- **Session persistence**: Sessions survive page reload. Reconnect to active spawn WebSocket on revisit.

## Non-Goals (for this design)

- Multi-repo support / Jupyter-style repo switching — dropped
- File explorer in sidebar — dropped
- Server lifecycle management (lockfile, port discovery) — separate concern
- Mobile/responsive design — desktop-first is fine

## Tech Stack (existing)

- React 19, Radix UI, Tailwind CSS, Lucide icons
- pnpm, Vite
- wouter for client-side routing (already in the existing design doc)
- FastAPI backend with WebSocket
- AG-UI event protocol mapping layer
