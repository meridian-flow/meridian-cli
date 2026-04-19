# Frontend UI Design (Simplified)

## Target User

**Biomedical researchers** — not developers. They want something simple that helps with their research. They shouldn't need to know what harnesses, models, or agents are.

## Design Principles

1. **Simple by default** — works out of the box with smart defaults
2. **Progressive disclosure** — power features available but hidden
3. **Start minimal** — add features only when proven necessary

## Mental Model

- **Project = Folder** — a folder on disk they want to work with
- **Session = Chat** — a conversation with one AI, bound at creation
- **Multiple sessions per project** — different conversations, different purposes

## Layout Architecture

Two-column layout: sidebar + main pane. Sidebar always visible (desktop-first).

```
┌──────────────────────────────────────────────────────────────────┐
│ App Shell (100vh, flex row)                                      │
│                                                                  │
│ ┌───────────────┬────────────────────────────────────────────────┤
│ │  Sidebar      │  Main Pane                                    │
│ │  (280px)      │  (flex-1)                                     │
│ │               │                                               │
│ │  [+ New Chat] │  Route: /                                     │
│ │               │    Logo + tagline (centered)                  │
│ │  Today        │    Composer (bottom)                          │
│ │   ● chat 1    │                                               │
│ │   ○ chat 2    │  Route: /s/:sessionId                         │
│ │               │    Chat history                               │
│ │  Yesterday    │    Composer (bottom)                          │
│ │   ✓ chat 3    │                                               │
│ │               │                                               │
│ │  ─────────    │                                               │
│ │  [theme] [⚙]  │                                               │
│ └───────────────┴────────────────────────────────────────────────┤
└──────────────────────────────────────────────────────────────────┘
```

## Component Hierarchy

```
App.tsx                           ← Shell: sidebar + router
├── Sidebar
│   ├── SidebarHeader             ← Logo + "New Chat" button
│   ├── SessionList               ← Grouped session items
│   └── SidebarFooter             ← Theme toggle
├── MainPane
│   ├── LandingPage               ← Route: /
│   │   ├── EmptyState            ← Logo + tagline
│   │   └── Composer              ← Text input + effort toggle
│   └── SessionView               ← Route: /s/:sessionId
│       ├── ThreadView            ← Chat history
│       └── Composer              ← Text input (config locked)
└── AdvancedSettings              ← Collapsible drawer/modal
```

## Routing

Uses wouter (see `frontend-routing.md`).

| Path | Component | Content |
|------|-----------|---------|
| `/` | `LandingPage` | Logo, tagline, composer ready for input |
| `/s/:sessionId` | `SessionView` | Chat history + composer |
| `*` | Redirect to `/` | Unknown paths |

## Sidebar

### SidebarHeader

```
┌───────────────┐
│ ◆ meridian    │   ← logo + wordmark
│               │
│ [+ New Chat]  │   ← full-width button
└───────────────┘
```

"New Chat" navigates to `/` (landing page).

### SessionList

Sessions fetched from `GET /api/sessions`, polled every 5 seconds. Grouped by recency (Today, Yesterday, Previous 7 Days, Older).

Each item shows:
- Status dot (● running, ✓ done, ✗ failed)
- Prompt preview (truncated)
- Relative time (2m, 1h, 3d)

Click navigates to `/s/{sessionId}`.

### SidebarFooter

Theme toggle (light/dark) and settings button.

## Composer

The composer is the primary interaction point. It needs to be simple.

### Landing Page Composer

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  What would you like to work on?                               │
│                                                                │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  [Quick ○ ● Thorough]                   [Advanced ▾]   [Send] │
└────────────────────────────────────────────────────────────────┘
```

**Effort Toggle** — the only visible control. Two modes:
- **Quick** — fast responses, lower cost (maps to lower thinking budget)
- **Thorough** — deeper thinking, better for complex problems

**Advanced** — collapsed by default. Clicking expands a section with:
- Harness selection (Claude/Codex/OpenCode)
- Model selection (dropdown, not a browser dialog)
- Agent profile selection (dropdown)

Most users never touch Advanced. The defaults work.

### Session Composer

Same textarea, but:
- Effort toggle is hidden (locked at creation)
- Advanced section hidden (config is fixed for session)
- Just the textarea + send button

```
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│  Continue your conversation...                                 │
│                                                                │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                         [Send] │
└────────────────────────────────────────────────────────────────┘
```

## Effort Toggle

Two-option toggle replaces the 4-level segmented control:

| Mode | What it means | Backend mapping |
|------|--------------|-----------------|
| **Quick** | Fast, good for simple questions | Claude: `budget_tokens=1024`, Codex: `effort=low` |
| **Thorough** | Slower, better for complex analysis | Claude: no budget limit, Codex: `effort=high` |

The toggle uses Radix ToggleGroup with `type="single"`. Default: **Thorough** (researchers want good answers by default).

## Advanced Settings

Collapsed by default. When expanded:

```
┌────────────────────────────────────────────────────────────────┐
│  Advanced Settings                                      [Hide] │
├────────────────────────────────────────────────────────────────┤
│  AI Provider     [Claude ▾]                                    │
│  Model           [claude-sonnet-4-6 ▾]                         │
│  Profile         [None ▾]                                      │
└────────────────────────────────────────────────────────────────┘
```

- **AI Provider** — Dropdown: Claude, Codex, OpenCode. Changing resets Model.
- **Model** — Dropdown of models for selected provider. Shows display name.
- **Profile** — Agent profile. "None" is valid.

No model cards, no capability badges, no cost tiers. Just dropdowns.

## Session Creation Flow

1. User types prompt in composer
2. Clicks Send (or presses Enter)
3. `POST /api/sessions` with:
   ```json
   {
     "prompt": "Analyze my RNA-seq data...",
     "effort": "thorough",
     "harness": "claude",           // from Advanced, or default
     "model": "claude-sonnet-4-6",  // from Advanced, or default
     "agent": null                  // from Advanced, or null
   }
   ```
4. Navigate to `/s/{session_id}`
5. WebSocket connects, streaming begins

## Session View

Shows chat history (existing ThreadView) + composer.

Header shows minimal context:
```
┌────────────────────────────────────────────────────────────────┐
│  ← Back    Analyzing RNA-seq data...              ● Connected  │
└────────────────────────────────────────────────────────────────┘
```

- Back button returns to landing page
- Prompt preview (truncated)
- Connection status dot

Config is locked. User cannot change harness/model/effort mid-session.

## Empty State (Landing Page)

```
                    ◆
                    
               meridian
               
      AI-assisted research tools
      
      
  ┌────────────────────────────────┐
  │ What would you like to...      │
  └────────────────────────────────┘
```

Logo centered above composer. Minimal tagline. The composer is ready for input.

## What Changes vs. Original Design

| Aspect | Original Design | Simplified |
|--------|-----------------|------------|
| Effort control | 4-level segmented (Lo/Med/Hi/Max) | 2-option toggle (Quick/Thorough) |
| Harness selection | 3-icon toggle, always visible | Dropdown in collapsed Advanced |
| Model selection | Full browser dialog with cards | Simple dropdown |
| Agent selection | Always-visible dropdown | Dropdown in collapsed Advanced |
| SessionConfigBar | Dedicated component above composer | Inline effort toggle + collapsible |
| Model metadata | Cost tiers, capabilities, context limits | Just the name |
| Edge cases | 40+ specified scenarios | Handle errors gracefully |
| Loading states | Skeleton placeholders per component | Simple spinners where needed |

## What Does NOT Change

- **Sidebar + main pane layout** — good structure
- **Session persistence** — sessions survive reload
- **Routing** — wouter, `/` and `/s/:id`
- **ThreadView** — existing activity stream
- **WebSocket protocol** — AG-UI events
- **Theme system** — light/dark/system

## Scope Boundaries

### In Scope

- Sidebar with session list
- Landing page with composer
- Session view with chat history
- Effort toggle (Quick/Thorough)
- Collapsible Advanced settings
- Session persistence

### Out of Scope

- Multi-repo support
- File explorer
- Model cards/browser
- Mobile responsive
- Event replay for completed sessions
- Session deletion/archival
- Session renaming

## Implementation Notes

### Hooks

```tsx
// useSessionConfig — simplified
interface SessionConfig {
  effort: "quick" | "thorough"
  harness: "claude" | "codex" | "opencode"
  model: string | null
  agent: string | null
}

function useSessionConfig() {
  const [effort, setEffort] = useState<"quick" | "thorough">("thorough")
  const [harness, setHarness] = useState("claude")
  const [model, setModel] = useState<string | null>(null)
  const [agent, setAgent] = useState<string | null>(null)
  
  // When harness changes, clear model (models are harness-specific)
  function selectHarness(next: string) {
    setHarness(next)
    setModel(null)
  }
  
  return { effort, harness, model, agent, setEffort, selectHarness, setModel, setAgent }
}
```

### Backend Changes

The session creation endpoint accepts `effort` as `"quick"` or `"thorough"` instead of 4 levels. The harness adapter maps these to appropriate settings.

Effort mapping:
```python
EFFORT_MAPPING = {
    "claude": {"quick": {"budget_tokens": 1024}, "thorough": {}},
    "codex": {"quick": {"effort": "low"}, "thorough": {"effort": "high"}},
}
```

### Dependencies

Same as original design: `wouter` for routing. No additional dependencies.
