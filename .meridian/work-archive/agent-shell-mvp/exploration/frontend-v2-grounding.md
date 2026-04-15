# frontend-v2 grounding report

Scope: `../meridian-flow/frontend-v2`

Unable to persist the report file to `/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/exploration/frontend-v2-grounding.md` because the workspace is read-only, and `meridian report create` is unavailable in this environment.

## Directory Structure

```text
.
├── .storybook/
├── public/
└── src/
    ├── components/
    │   ├── storybook/
    │   └── ui/
    ├── editor/
    │   ├── collab/
    │   ├── components/
    │   ├── content/
    │   ├── decorations/
    │   ├── export/
    │   ├── formatting/
    │   ├── interaction/
    │   ├── paste/
    │   ├── persistence/
    │   ├── session/
    │   ├── stories/
    │   ├── title-header/
    │   └── transport/
    ├── features/
    │   ├── activity-stream/
    │   │   ├── examples/
    │   │   ├── items/
    │   │   └── streaming/
    │   ├── chat-scroll/
    │   ├── docs/
    │   └── threads/
    │       ├── components/
    │       ├── composer/
    │       ├── hooks/
    │       └── streaming/
    └── lib/
        └── ws/
```

- Entry bootstrap is minimal: [src/main.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/main.tsx:1) renders [src/App.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/App.tsx:5).
- The root app is still a shell: [src/App.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/App.tsx:5) only wraps `ThemeProvider`, `ThemeToggle`, and `Toaster`.
- The editor subsystem is the old document-writing stack: `src/editor/**`.
- The thread/activity subsystem is the newer assistant-turn stack: `src/features/activity-stream/**` and `src/features/threads/**`.
- Shared transport lives under `src/lib/ws/**`.

## Tech Stack

- React 19.2.4 and React DOM 19.2.4 are declared in [package.json](/home/jimyao/gitrepos/meridian-flow/frontend-v2/package.json:63).
- TypeScript is 5.9.x, Vite is 8.x, Tailwind CSS is 4.2.x, and the build uses the Tailwind Vite plugin in [vite.config.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/vite.config.ts:14).
- Storybook 10, Vitest 4, Playwright, and jsdom are present for component and browser testing in [package.json](/home/jimyao/gitrepos/meridian-flow/frontend-v2/package.json:75).
- The atom layer is shadcn/Radix-based, not a bespoke design system: [components.json](/home/jimyao/gitrepos/meridian-flow/frontend-v2/components.json:2) uses the shadcn schema, `new-york` style, Tailwind CSS variables, and `@/components/ui` aliases.
- The UI primitives are wrappers around Radix primitives and CVA, for example [src/components/ui/button.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/components/ui/button.tsx:7) and [src/components/ui/dialog.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/components/ui/dialog.tsx:8).
- Theme tokens live in [src/index.css](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/index.css:18) with CSS variables and `@theme inline`; the app uses Geist, Geist Mono, and iA Writer Quattro.
- State management is not Redux or Zustand. I found React local state, `useSyncExternalStore`, and TanStack Query. I did not find `react-router`, Redux, or Zustand imports in the inspected tree.
- The WebSocket layer uses the native browser `WebSocket` API behind a custom wrapper in [src/lib/ws/ws-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/ws-client.ts:72).
- Collaboration/editor dependencies include `yjs`, `y-protocols`, `y-indexeddb`, `y-codemirror.next`, and the CodeMirror 6 packages in [package.json](/home/jimyao/gitrepos/meridian-flow/frontend-v2/package.json:16).
- Markdown/HTML tooling includes `marked`, `turndown`, and `dompurify` in [package.json](/home/jimyao/gitrepos/meridian-flow/frontend-v2/package.json:57).
- `dexie` is present for IndexedDB-backed persistence, and `sonner` is present for toast UI.

## AG-UI Activity Stream Reducer

- The reducer lives at [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:1).
- Its state shape is `StreamState = { activity: ActivityBlockData; toolArgsBuffers: Record<string, string> }` in [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:25).
- The rendered activity model is [ActivityBlockData](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/types.ts:57): `id`, `items`, `pendingText?`, `isStreaming?`, `error?`, `isCancelled?`.
- `ActivityItem` is a discriminated union of `thinking`, `content`, and `tool` items in [src/features/activity-stream/types.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/types.ts:14).
- The reducer handles `RUN_STARTED`, `RUN_FINISHED`, `RUN_ERROR`, `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END`, `THINKING_START`, `THINKING_TEXT_MESSAGE_START`, `THINKING_TEXT_MESSAGE_CONTENT`, `THINKING_TEXT_MESSAGE_END`, `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END`, `TOOL_CALL_RESULT`, and `RESET` in [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:101).
- Streaming chunks are appended in place: `TEXT_MESSAGE_CONTENT` appends `delta` and also updates `pendingText` in [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:153).
- Thinking is similar: `THINKING_TEXT_MESSAGE_CONTENT` appends `delta`, while the start/end events are mostly lifecycle markers in [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:192).
- Tool streaming is more involved: `TOOL_CALL_START` creates a `ToolItem`, `TOOL_CALL_ARGS` concatenates the buffer and partial-parses it with `partial-json`, `TOOL_CALL_END` does the final parse and flips status to `executing`, and `TOOL_CALL_RESULT` parses the result payload and sets `done` or `error` in [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:233).
- `ActivityBlock` couples directly to that state model. It extracts the last `content` item as the streamed response below the card, keeps earlier content inside the collapsible card, and shows a compact "earlier tools..." toggle when the block has many tools in [src/features/activity-stream/ActivityBlock.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/ActivityBlock.tsx:68).
- `ActivityBlockHeader` summarizes status and streaming phase in [src/features/activity-stream/ActivityBlockHeader.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/ActivityBlockHeader.tsx:19).
- `ToolRow` routes each tool to `ToolDetail` and shows a status badge in [src/features/activity-stream/items/ToolRow.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/items/ToolRow.tsx:42).
- `ToolDetail` dispatches to `EditDetail`, `SearchDetail`, `WebSearchDetail`, `BashDetail`, and `AgentDetail`, with a generic input/output fallback in [src/features/activity-stream/ToolDetail.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/ToolDetail.tsx:21).
- `ToolItem.nestedActivity` exists in the type model in [src/features/activity-stream/types.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/types.ts:37), and nested rendering is supported by `AgentDetail` in [src/features/activity-stream/AgentDetail.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/AgentDetail.tsx:10).
- I only found `nestedActivity` populated in stories/examples, not in the production reducer or thread mapper. See [src/features/activity-stream/examples/nested-agent.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/examples/nested-agent.ts:5) and [src/features/activity-stream/ActivityBlock.stories.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/ActivityBlock.stories.tsx:116).

## WebSocket Client

- The common envelope protocol is defined in [src/lib/ws/protocol.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/protocol.ts:13).
- The envelope shape is `kind`, `op`, optional `resource`, `subId`, `seq`, `epoch`, and `payload` in [src/lib/ws/protocol.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/protocol.ts:28).
- `kind` lanes are `control`, `notify`, `stream`, and `error` in [src/lib/ws/protocol.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/protocol.ts:14).
- `WsClient` is the shared transport wrapper in [src/lib/ws/ws-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/ws-client.ts:72). It handles auth bootstrap, ping/pong, reconnect with exponential backoff + jitter, JSON envelope parsing, and `useSyncExternalStore` integration.
- The reconnect policy is native browser WS plus backoff, not a third-party socket library. The connection state machine is `disconnected`, `connecting`, `connected`, `reconnecting` in [src/lib/ws/protocol.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/protocol.ts:126).
- JSON frames are parsed by `parseEnvelope`; binary frames are handled separately in [src/lib/ws/ws-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/ws-client.ts:255).
- Binary frames are prefixed with `<subId UTF-8> 0x00 <payload>` in [src/lib/ws/ws-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/ws-client.ts:115).
- For thread streaming, [src/features/threads/streaming/ThreadWsProvider.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/ThreadWsProvider.tsx:69) creates one `WsClient` per project, routes notify events to TanStack Query invalidation, and forwards stream/control/error messages into `StreamingChannelClient`.
- The notify mapping is centralized in [src/lib/ws/notify-handler.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/notify-handler.ts:1). `spawn_started` invalidates `["threads", id, "spawns"]` in [src/features/threads/streaming/ThreadWsProvider.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/ThreadWsProvider.tsx:157).
- `StreamingChannelClient` owns turn subscriptions, per-turn gap tracking, reconnect resubscribe, and interjection sending in [src/features/threads/streaming/streaming-channel-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/streaming-channel-client.ts:100).
- It stores subscriptions by `subId`, keeps a reverse `turnId -> subId` lookup, and snapshots itself through `useSyncExternalStore` in [src/features/threads/streaming/streaming-channel-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/streaming-channel-client.ts:103).
- `handleStreamEvent` updates `seq`/`epoch` and forwards valid AG-UI payloads into the reducer callback in [src/features/threads/streaming/streaming-channel-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/streaming-channel-client.ts:347).
- `handleStreamEnded` auto-follows `stream_switch` by subscribing to `newAssistantTurnId` in [src/features/threads/streaming/streaming-channel-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/streaming-channel-client.ts:369).
- `handleGap` retries once per turn, then stops after two consecutive gaps and leaves the client to fall back to REST/notify in [src/features/threads/streaming/streaming-channel-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/streaming-channel-client.ts:400).
- `useThreadStreaming` exposes `subscribe`, `unsubscribe`, `sendInterjection`, `activeSubscriptions`, and `connectionState` in [src/features/threads/streaming/use-thread-streaming.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/use-thread-streaming.ts:57).
- The document sync side is parallel but CRDT-based: [src/lib/ws/doc-stream-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/doc-stream-client.ts:79) subscribes to `document` resources, uses binary prefix bytes `0x00` and `0x01`, and re-subscribes fresh on reconnect.
- `DocumentWsProviderImpl` is a thin adapter over `DocStreamClient` with no own auth/reconnect logic in [src/editor/transport/document-ws-provider.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/transport/document-ws-provider.ts:39).

## Thread Components

- `TurnList` is the simple list renderer that maps turns to rows in [src/features/threads/components/TurnList.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/TurnList.tsx:10).
- `TurnRow` is the main switchboard. It renders pending/error/cancelled/credit-limited assistant turns, routes normal assistant turns into `ActivityBlock`, hides system turns, and renders user turns via `UserBubble` in [src/features/threads/components/TurnRow.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/TurnRow.tsx:57).
- `PendingTurn` is the simple typing indicator with animated dots in [src/features/threads/components/PendingTurn.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/PendingTurn.tsx:3).
- `TurnStatusBanner` is the error/warning banner used by assistant failure states in [src/features/threads/components/TurnStatusBanner.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/TurnStatusBanner.tsx:1).
- `SiblingNav` provides previous/next sibling controls for branched turns in [src/features/threads/components/SiblingNav.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/SiblingNav.tsx:14).
- `UserBubble` renders user blocks and supports text, images, references, and ignores tool_result blocks in [src/features/threads/components/UserBubble.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/UserBubble.tsx:73).
- `ImageBlock` is a plain `<img>` wrapper with caption support in [src/features/threads/components/ImageBlock.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/ImageBlock.tsx:1).
- `ReferenceBlock` renders the reference chip with `ref-id`, `ref-type`, and selection metadata in [src/features/threads/components/ReferenceBlock.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/components/ReferenceBlock.tsx:1).
- `ChatComposer` is the thread composer shell; it wraps a `ComposerEditor` and `ComposerControls` in [src/features/threads/composer/ChatComposer.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/composer/ChatComposer.tsx:44).
- `ComposerEditor` is a standalone CM6 editor with history, placeholder, submit/escape key handling, and update listeners in [src/features/threads/composer/ComposerEditor.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/composer/ComposerEditor.tsx:45).
- `ComposerControls` is currently a mock control bar with local model/reasoning selectors and send/stop wiring, not a backend-backed picker in [src/features/threads/composer/ComposerControls.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/composer/ComposerControls.tsx:44).
- The thread storybook surface composes `FloatingScrollLayout`, `TimelineScrubber`, `TurnList`, and `ChatComposer` in [src/features/threads/ThreadView.stories.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/ThreadView.stories.tsx:1).

## UI Atoms

- The atom library is shadcn-style and generated around Radix primitives, not a custom design system: [components.json](/home/jimyao/gitrepos/meridian-flow/frontend-v2/components.json:1) is configured for shadcn `new-york`.
- `Button` is a CVA + Radix Slot wrapper with variants and sizes in [src/components/ui/button.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/components/ui/button.tsx:7).
- `Dialog` is a thin Radix Dialog wrapper with standard overlay/content/header/footer/title/description helpers in [src/components/ui/dialog.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/components/ui/dialog.tsx:8).
- `ThemeProvider` is custom application code, not shadcn boilerplate, and uses `useSyncExternalStore` to track the system theme in [src/components/theme-provider.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/components/theme-provider.tsx:39).
- The UI atom folder also contains the usual shadcn-style primitives such as `input`, `tabs`, `popover`, `dropdown-menu`, `scroll-area`, `tooltip`, `sonner`, and friends under `src/components/ui/`.

## Editor, CodeMirror, and Yjs

- The editor entry point is [src/editor/Editor.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/Editor.tsx:52). It can either bind to caller-provided Yjs resources or create a standalone local `Y.Doc`.
- The editor always goes through `createEditorExtensions()` in [src/editor/extensions.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/extensions.ts:89), which wires markdown parsing, focus/reveal state, live preview, yCollab, Y.UndoManager keybindings, formatting, paste handling, and interaction handlers.
- `Editor.tsx` exposes a pull-based content API and internal session refs in [src/editor/Editor.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/Editor.tsx:92).
- `Editor.tsx` seeds the CM6 document from the current Y.Text so preloaded content is visible before yCollab attaches in [src/editor/Editor.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/Editor.tsx:158).
- `DocSession` is the document-scoped lifecycle owner. It owns `Y.Doc`, `Y.Text`, `Awareness`, `Y.UndoManager`, IDB persistence, sync state, connection state, and the transport placeholder in [src/editor/session/doc-session.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/session/doc-session.ts:69).
- `SessionPool` handles warm-session creation, idle eviction, generation guards, leases, invalidation, and `useSyncExternalStore` compatibility in [src/editor/session/session-pool.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/session/session-pool.ts:66).
- `ViewController` manages open docs, one live `EditorView` per session, restore state, ownership transfer, and LRU eviction in [src/editor/session/view-controller.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/session/view-controller.ts:66).
- `useDocumentSessions()` bridges `SessionPool` + `ViewController` into React state in [src/editor/session/useDocumentSessions.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/session/useDocumentSessions.ts:1).
- `DocumentWsProviderImpl` is the doc-transport adapter that forwards Yjs updates to `DocStreamClient` and applies sync/awareness payloads in [src/editor/transport/document-ws-provider.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/transport/document-ws-provider.ts:39).
- The legacy writing-app shape is still visible in `title-header`, `tab bar`, export, word count, live preview, paste handling, and markdown collaboration helpers under `src/editor/**`.
- `exporters.ts` explicitly marks PDF/DOCX/EPUB as backend stubs in [src/editor/export/exporters.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/export/exporters.ts:98).
- `paste-handler.ts` still inserts `![pasted image](TODO: upload)` placeholders for image paste in [src/editor/paste/paste-handler.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/paste/paste-handler.ts:26).

## Missing Pieces and Roadmap Signals

- The root app is a placeholder shell, so there is no actual route/layout composition yet in [src/App.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/App.tsx:5).
- I did not find a real router layer or a global Redux/Zustand store in the inspected tree.
- `use-thread-simulator.ts` is explicitly Storybook-only and stubs `loadThread`, `paginateBefore`, `paginateAfter`, and `switchSibling` behavior in [src/features/threads/hooks/use-thread-simulator.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/hooks/use-thread-simulator.ts:160).
- `turn-mapper.ts` says Phase 5 will add dedicated item kinds for image/reference blocks in [src/features/threads/turn-mapper.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/turn-mapper.ts:281).
- `ComposerControls.tsx` still uses mock models and reasoning levels, so backend model selection is not wired yet in [src/features/threads/composer/ComposerControls.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/composer/ComposerControls.tsx:21).
- `src/features/activity-stream/examples/scenario-builder.ts` contains a TODO for `USER_MESSAGE` not yet being in the union, which suggests the AG-UI event surface is still evolving.
- `src/features/activity-stream/examples/nested-agent.ts` and the ActivityBlock stories show nested activity trees, but production mapping does not currently generate them.
- `src/editor/session/doc-session.ts` and `src/editor/session/session-pool.ts` still carry phase markers for the transport/session rollout, which is a sign the editor stack is intentionally staged rather than finished.

## Writing-App Legacy vs Biomedical Pivot

- Strong writing-app legacy signals: `src/editor/**`, especially [src/editor/title-header/TitleHeader.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/title-header/TitleHeader.tsx:1), [src/editor/components/TabbedEditorShell.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/components/TabbedEditorShell.tsx:1), [src/editor/export/exporters.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/export/exporters.ts:98), [src/editor/paste/paste-handler.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/paste/paste-handler.ts:7), [src/editor/session/doc-session.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/session/doc-session.ts:2), and [src/editor/session/view-controller.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/editor/session/view-controller.ts:1).
- Strong biomedical-pivot signals: [src/features/activity-stream/streaming/reducer.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/streaming/reducer.ts:1), [src/features/activity-stream/ActivityBlock.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/activity-stream/ActivityBlock.tsx:30), [src/features/threads/turn-mapper.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/turn-mapper.ts:1), [src/features/threads/streaming/ThreadWsProvider.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/streaming/ThreadWsProvider.tsx:69), and [src/features/threads/composer/ChatComposer.tsx](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/features/threads/composer/ChatComposer.tsx:44).
- Shared infrastructure that should probably be kept and reused: [src/lib/ws/ws-client.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/ws-client.ts:72), [src/lib/ws/protocol.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/protocol.ts:22), [src/lib/ws/notify-handler.ts](/home/jimyao/gitrepos/meridian-flow/frontend-v2/src/lib/ws/notify-handler.ts:1), and the `src/components/ui/**` atom set.
- Likely cut or rewrite for the new amalgamation unless document editing is explicitly needed: the `TabbedEditorShell` / title-header / export / paste / word-count / view-controller stack, and the Storybook-only simulator scaffolding.

## Ambiguities

- `nestedActivity` is a real type-level capability, but it is not wired through the main reducer or the thread mapper yet; it only appears in stories/examples.
- `ThreadWsProvider` and `DocStreamClient` both use the same `WsClient`, but they speak different lane conventions. The thread side is JSON stream/control/notify/error; the document side adds binary Yjs sync/awareness frames.
- `App.tsx` does not reveal the intended runtime product shape. The meaningful behavior is still spread across feature modules and Storybook demos.

## Verification

- I inspected the repo tree and key source files only; I did not run a build or tests.
- I could not persist the report file to `.meridian/work/agent-shell-mvp/exploration/frontend-v2-grounding.md` because the workspace is read-only.