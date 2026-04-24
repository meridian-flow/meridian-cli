/**
 * ChatPage — top-level view for Chat mode, now chat-first.
 *
 * The page has two display modes:
 * 1. **Chat thread view**: When a chat is selected (or the user starts a new
 *    chat from the empty state), the main area shows the conversation thread
 *    with a composer at the bottom. Active spawns under the chat stream
 *    their output inline.
 * 2. **Spawn column view**: When a spawn is opened directly (from the sidebar
 *    or cross-mode navigation), the multi-column layout is used as before.
 *
 * Layout choices preserved from before:
 * - Sidebar collapse toggle + capacity indicator chrome bar.
 * - Columns evenly split via CSS grid.
 * - Empty state is a quiet composition inviting the user to start a chat.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import {
  ChatCircle,
  List,
  PaperPlaneTilt,
  SidebarSimple,
} from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { useNavigation } from "@/shell/NavigationContext"

import { ChatProvider, MAX_COLUMNS, useChat } from "./ChatContext"
import { SessionList, type SessionListDataOverride } from "./SessionList"
import { ChatThreadView } from "./ChatThreadView"
import {
  ThreadColumn,
  type ThreadColumnSpawnDetails,
} from "./ThreadColumn"

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface ChatPageProps {
  /**
   * Spawn to open on mount. Honoured once per ChatProvider instance.
   */
  initialSpawnId?: string | null
  className?: string
  sessionListOverride?: SessionListDataOverride
  threadDetailsOverride?: Record<string, ThreadColumnSpawnDetails>
  initialColumns?: readonly string[]
  initialFocus?: string
  initialSidebarCollapsed?: boolean
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export function ChatPage(props: ChatPageProps) {
  return (
    <ChatProvider>
      <ChatPageContent {...props} />
    </ChatProvider>
  )
}

// ---------------------------------------------------------------------------
// Inner layout
// ---------------------------------------------------------------------------

function ChatPageContent({
  initialSpawnId,
  className,
  sessionListOverride,
  threadDetailsOverride,
  initialColumns,
  initialFocus,
  initialSidebarCollapsed,
}: ChatPageProps) {
  const { selectedChat, columnState, openSpawn, closeColumn, focusColumn } = useChat()
  const { pendingChatSpawnId, clearPendingChatSpawnId } = useNavigation()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    Boolean(initialSidebarCollapsed),
  )

  const didSeed = useRef(false)

  useEffect(() => {
    if (didSeed.current) return
    didSeed.current = true

    const seeds: string[] = []
    if (initialColumns) seeds.push(...initialColumns)
    if (initialSpawnId && !seeds.includes(initialSpawnId)) seeds.push(initialSpawnId)
    for (const id of seeds) openSpawn(id)
    if (initialFocus) focusColumn(initialFocus)
  }, [initialColumns, initialSpawnId, initialFocus, openSpawn, focusColumn])

  useEffect(() => {
    if (!pendingChatSpawnId) return
    openSpawn(pendingChatSpawnId)
    clearPendingChatSpawnId()
  }, [pendingChatSpawnId, openSpawn, clearPendingChatSpawnId])

  const columnCount = columnState.columns.length
  const hasChatSelected = selectedChat !== null
  // Show chat thread view whenever a chat is selected. Columns render
  // independently below in a split layout when present.
  const showThreadView = hasChatSelected

  return (
    <div
      className={cn(
        "relative flex h-full min-h-0 w-full overflow-hidden bg-background",
        className,
      )}
    >
      <aside
        className={cn(
          "relative h-full shrink-0 overflow-hidden",
          "transition-[width] duration-200 ease-out",
          sidebarCollapsed ? "w-0" : "w-60",
        )}
        aria-hidden={sidebarCollapsed}
      >
        <div className="absolute inset-y-0 right-0 w-60">
          <SessionList dataOverride={sessionListOverride} />
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <ColumnAreaChrome
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
          columnCount={columnCount}
          hasChatSelected={hasChatSelected}
        />

        {showThreadView ? (
          <div
            className={cn(
              "flex min-h-0 flex-1",
              columnCount > 0 && "gap-0",
            )}
          >
            <ChatThreadView
              chatId={selectedChat.chatId}
              className={columnCount > 0 ? "w-1/2 border-r border-border/40" : undefined}
            />
            {columnCount > 0 && (
              <div
                className="grid min-h-0 flex-1 gap-2 p-2"
                style={{
                  gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
                }}
              >
                {columnState.columns.map((spawnId) => (
                  <ErrorBoundary key={spawnId}>
                    <ThreadColumn
                      spawnId={spawnId}
                      isFocused={columnState.focusedColumn === spawnId}
                      onClose={() => closeColumn(spawnId)}
                      onFocus={() => focusColumn(spawnId)}
                      detailsOverride={threadDetailsOverride?.[spawnId]}
                    />
                  </ErrorBoundary>
                ))}
              </div>
            )}
          </div>
        ) : columnCount === 0 ? (
          <EmptyColumnState sidebarCollapsed={sidebarCollapsed} />
        ) : (
          <div
            className="grid min-h-0 flex-1 gap-2 p-2"
            style={{
              gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
            }}
          >
            {columnState.columns.map((spawnId) => (
              <ErrorBoundary key={spawnId}>
                <ThreadColumn
                  spawnId={spawnId}
                  isFocused={columnState.focusedColumn === spawnId}
                  onClose={() => closeColumn(spawnId)}
                  onFocus={() => focusColumn(spawnId)}
                  detailsOverride={threadDetailsOverride?.[spawnId]}
                />
              </ErrorBoundary>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chrome bar
// ---------------------------------------------------------------------------

interface ColumnAreaChromeProps {
  sidebarCollapsed: boolean
  onToggleSidebar: () => void
  columnCount: number
  hasChatSelected: boolean
}

function ColumnAreaChrome({
  sidebarCollapsed,
  onToggleSidebar,
  columnCount,
  hasChatSelected,
}: ColumnAreaChromeProps) {
  const ToggleIcon = sidebarCollapsed ? List : SidebarSimple
  const tooltip = sidebarCollapsed ? "Show sessions" : "Hide sessions"

  return (
    <div className="flex h-9 items-center justify-between border-b border-border/60 pl-1 pr-3">
      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={onToggleSidebar}
              aria-label={tooltip}
              aria-pressed={!sidebarCollapsed}
              className="text-muted-foreground hover:text-foreground"
            >
              <ToggleIcon weight="regular" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">{tooltip}</TooltipContent>
        </Tooltip>

        {hasChatSelected && (
          <span className="flex items-center gap-1 text-[10px] font-medium text-accent-foreground/70">
            <ChatCircle weight="fill" className="size-3 text-accent-fill" />
            Chat
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {columnCount > 0 && (
          <>
            <span className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
              Columns
            </span>
            <CapacityDots count={columnCount} />
            <span className="font-mono text-[10px] tabular-nums text-muted-foreground/60">
              {columnCount}/{MAX_COLUMNS}
            </span>
          </>
        )}
      </div>
    </div>
  )
}

function CapacityDots({ count }: { count: number }) {
  return (
    <div className="flex items-center gap-1" aria-hidden>
      {Array.from({ length: MAX_COLUMNS }).map((_, i) => (
        <span
          key={i}
          className={cn(
            "h-1.5 w-1.5 rounded-full transition-colors",
            i < count ? "bg-accent-fill" : "bg-border",
          )}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Empty state — now invites starting a new chat
// ---------------------------------------------------------------------------

function EmptyColumnState({ sidebarCollapsed }: { sidebarCollapsed: boolean }) {
  const { selectChat } = useChat()
  const [composerValue, setComposerValue] = useState("")

  const handleNewChat = useCallback(() => {
    const text = composerValue.trim()
    if (!text) return
    // Pass the initial prompt so ChatThreadView can auto-send it
    selectChat("__new__", "active", { initialPrompt: text })
  }, [composerValue, selectChat])

  return (
    <div className="relative flex min-h-0 flex-1 items-center justify-center p-8">
      {/* Hairline grid backdrop */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, var(--border) 1px, transparent 1px), linear-gradient(to bottom, var(--border) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 80%)",
          WebkitMaskImage:
            "radial-gradient(ellipse at center, black 30%, transparent 80%)",
        }}
      />

      <div className="relative flex max-w-md flex-col items-center text-center">
        <div
          className={cn(
            "mb-5 flex size-14 items-center justify-center rounded-full",
            "border border-border/70 bg-background/80 text-muted-foreground/70",
            "shadow-[0_1px_0_var(--border)] backdrop-blur",
          )}
        >
          <ChatCircle weight="duotone" className="size-7" />
        </div>

        <p className="mb-2 text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground/70">
          Start a conversation
        </p>
        <h2 className="mb-2 text-lg font-semibold tracking-tight text-foreground">
          What would you like to work on?
        </h2>
        <p className="mb-6 text-sm leading-relaxed text-muted-foreground">
          {sidebarCollapsed ? (
            <>
              Start a new chat or re-open the sidebar to resume an existing
              conversation.
            </>
          ) : (
            <>
              Type your first message below, or pick an existing chat from the
              sidebar. Spawns run side-by-side in columns.
            </>
          )}
        </p>

        {/* Inline quick-start composer */}
        <div className="flex w-full items-center gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={composerValue}
              onChange={(e) => setComposerValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleNewChat()
                }
              }}
              placeholder="Ask anything..."
              className={cn(
                "h-10 w-full rounded-lg border border-border bg-card px-4 pr-10",
                "text-sm text-foreground placeholder:text-muted-foreground/50",
                "focus:outline-none focus:ring-2 focus:ring-ring/50",
                "transition-shadow",
              )}
            />
            <button
              type="button"
              onClick={handleNewChat}
              disabled={!composerValue.trim()}
              className={cn(
                "absolute right-2 top-1/2 -translate-y-1/2",
                "flex size-6 items-center justify-center rounded-md",
                "text-muted-foreground hover:text-foreground",
                "disabled:opacity-30 disabled:pointer-events-none",
                "transition-colors",
              )}
              aria-label="Start chat"
            >
              <PaperPlaneTilt weight="fill" className="size-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
