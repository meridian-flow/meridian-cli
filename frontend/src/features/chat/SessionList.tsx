/**
 * SessionList — narrow sidebar showing chats and spawns for chat mode.
 *
 * Primary display: Chat rows with state indicator, title/first-prompt
 * snippet, and timestamp. Each chat row is expandable to reveal nested
 * spawns. Clicking a chat selects it in ChatContext; clicking a nested
 * spawn opens it as a column.
 *
 * Below the chats section, "orphan" spawns not attached to any chat are
 * still shown for backwards compatibility with direct-spawn viewing.
 *
 * Storybook bypasses live hooks via `dataOverride`.
 */

import { useEffect, useMemo, useRef, useState } from "react"
import {
  CaretDown,
  CaretRight,
  ChatCircleDots,
  Lightning,
} from "@phosphor-icons/react"

import { ElapsedTime, MonoId, StatusDot } from "@/components/atoms"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { parseStatus } from "@/types/spawn"

import { useChat } from "./ChatContext"
import { useSessions } from "@/features/sessions/hooks"
import { useChatSessions } from "@/features/sessions/hooks/use-chat-sessions"
import type { SpawnProjection, ChatProjection } from "@/features/sessions/lib/api"

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface SessionListProps {
  className?: string
  /**
   * Storybook/test escape hatch. When provided, bypasses live hooks
   * and the ChatContext for active-column rendering.
   */
  dataOverride?: SessionListDataOverride
}

export interface SessionListDataOverride {
  chats?: ChatProjection[]
  spawns: SpawnProjection[]
  isLoading?: boolean
  error?: string | null
  activeColumns?: readonly string[]
  focusedColumn?: string | null
  selectedChatId?: string | null
  onSelectChat?: (chatId: string, state: string, activeSpawnId?: string | null) => void
  onSelectSpawn?: (spawnId: string) => void
}

function startedDate(p: SpawnProjection): Date {
  const raw = p.started_at ?? p.created_at
  return raw ? new Date(raw) : new Date(0)
}

function endedDate(p: SpawnProjection): Date | undefined {
  return p.finished_at ? new Date(p.finished_at) : undefined
}

// ---------------------------------------------------------------------------
// Chat state indicator
// ---------------------------------------------------------------------------

type ChatStateValue = 'active' | 'idle' | 'draining' | 'closed'

const CHAT_STATE_COLORS: Record<ChatStateValue, string> = {
  active: "bg-emerald-500",
  idle: "bg-amber-400",
  draining: "bg-orange-400",
  closed: "bg-zinc-400",
}

const CHAT_STATE_LABELS: Record<ChatStateValue, string> = {
  active: "Active",
  idle: "Idle",
  draining: "Draining",
  closed: "Closed",
}

function ChatStateIndicator({ state }: { state: ChatStateValue }) {
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
        CHAT_STATE_COLORS[state] ?? "bg-zinc-400",
      )}
      title={CHAT_STATE_LABELS[state] ?? state}
    />
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionList({ className, dataOverride }: SessionListProps) {
  const live = useSessions()
  const chatHook = useChatSessions()
  const chat = useChat()

  const chats = dataOverride?.chats ?? chatHook.chats
  const spawns = dataOverride?.spawns ?? live.spawns
  const isLoading = dataOverride?.isLoading ?? (live.isLoading || chatHook.isLoading)
  const isLoadingMore = live.isLoadingMore
  const hasMore = live.hasMore
  const error = dataOverride?.error ?? live.error ?? chatHook.error
  const activeColumns = dataOverride?.activeColumns ?? chat.columnState.columns
  const focusedColumn = dataOverride?.focusedColumn ?? chat.columnState.focusedColumn
  const selectedChatId = dataOverride?.selectedChatId ?? chat.selectedChat?.chatId ?? null
  const handleSelectChat = dataOverride?.onSelectChat ?? (
    (chatId: string, state: string, activeSpawnId?: string | null) => {
      chat.selectChat(chatId, state as ChatStateValue, { activeSpawnId })
    }
  )
  const handleSelectSpawn = dataOverride?.onSelectSpawn ?? chat.openSpawn

  const activeSet = useMemo(() => new Set(activeColumns), [activeColumns])

  // Infinite scroll sentinel for the sidebar
  const sentinelRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasMore && !isLoadingMore) {
          live.loadMore()
        }
      },
      { rootMargin: '100px' },
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMore, isLoadingMore, live])

  // Sort chats: active first, then by updated_at desc
  const orderedChats = useMemo(() => {
    return [...chats].sort((a, b) => {
      const aActive = a.state === 'active' || a.state === 'draining'
      const bActive = b.state === 'active' || b.state === 'draining'
      if (aActive && !bActive) return -1
      if (!aActive && bActive) return 1
      const aTime = a.updated_at ?? a.created_at
      const bTime = b.updated_at ?? b.created_at
      return bTime.localeCompare(aTime)
    })
  }, [chats])

  // Orphan spawns: spawns not associated with any chat
  // For now, show all spawns below the chat list since we don't have
  // a chat_id field on SpawnProjection yet.
  const orphanSpawns = useMemo(() => {
    // Sort: active columns first, then newest-first
    const activeOrder = new Map<string, number>()
    activeColumns.forEach((id, idx) => activeOrder.set(id, idx))

    return [...spawns].sort((a, b) => {
      const aActive = activeOrder.has(a.spawn_id)
      const bActive = activeOrder.has(b.spawn_id)
      if (aActive && bActive) {
        return (activeOrder.get(a.spawn_id) ?? 0) - (activeOrder.get(b.spawn_id) ?? 0)
      }
      if (aActive) return -1
      if (bActive) return 1
      const at = a.started_at ?? a.created_at ?? ""
      const bt = b.started_at ?? b.created_at ?? ""
      return bt.localeCompare(at)
    })
  }, [spawns, activeColumns])

  return (
    <aside
      className={cn(
        "flex h-full w-60 shrink-0 flex-col border-r border-border bg-background",
        className,
      )}
      aria-label="Sessions"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Chats
        </h2>
        {!isLoading && !error && (chats.length > 0 || spawns.length > 0) ? (
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
            {chats.length > 0 ? chats.length : spawns.length}
          </span>
        ) : null}
      </div>

      <ScrollArea className="flex-1">
        {error ? (
          <ErrorState message={error} />
        ) : isLoading ? (
          <LoadingState />
        ) : orderedChats.length === 0 && orphanSpawns.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            {/* Chat rows */}
            {orderedChats.length > 0 && (
              <ul className="flex flex-col py-1">
                {orderedChats.map((c) => (
                  <ChatListRow
                    key={c.chat_id}
                    chat={c}
                    isSelected={selectedChatId === c.chat_id}
                    onSelect={handleSelectChat}
                    onSelectSpawn={handleSelectSpawn}
                    activeColumns={activeSet}
                    focusedColumn={focusedColumn}
                  />
                ))}
              </ul>
            )}

            {/* Divider between chats and orphan spawns */}
            {orderedChats.length > 0 && orphanSpawns.length > 0 && (
              <div className="flex items-center gap-2 px-3 py-1.5">
                <div className="h-px flex-1 bg-border/50" />
                <span className="text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/50">
                  Spawns
                </span>
                <div className="h-px flex-1 bg-border/50" />
              </div>
            )}

            {/* Orphan spawn rows (backwards compat) */}
            {orphanSpawns.length > 0 && (
              <ul className="flex flex-col py-1">
                {orphanSpawns.map((p) => (
                  <SpawnListRow
                    key={p.spawn_id}
                    spawn={p}
                    isActive={activeSet.has(p.spawn_id)}
                    isFocused={focusedColumn === p.spawn_id}
                    onSelect={handleSelectSpawn}
                  />
                ))}
              </ul>
            )}

            {hasMore && (
              <div ref={sentinelRef} className="flex items-center justify-center py-2">
                {isLoadingMore ? (
                  <div className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
                ) : (
                  <span className="text-[10px] text-muted-foreground/40">&middot;</span>
                )}
              </div>
            )}
          </>
        )}
      </ScrollArea>
    </aside>
  )
}

// ---------------------------------------------------------------------------
// Chat row
// ---------------------------------------------------------------------------

interface ChatListRowProps {
  chat: ChatProjection
  isSelected: boolean
  onSelect: (chatId: string, state: string, activeSpawnId?: string | null) => void
  onSelectSpawn: (spawnId: string) => void
  activeColumns: Set<string>
  focusedColumn: string | null
}

function ChatListRow({
  chat,
  isSelected,
  onSelect,
  onSelectSpawn: _onSelectSpawn,
  activeColumns: _activeColumns,
  focusedColumn: _focusedColumn,
}: ChatListRowProps) {
  const [expanded, setExpanded] = useState(false)
  const createdAt = new Date(chat.created_at)

  const isLive = chat.state === 'active' || chat.state === 'draining'
  const chatState = chat.state as ChatStateValue

  return (
    <li>
      <button
        type="button"
        onClick={() => {
          onSelect(chat.chat_id, chat.state, chat.active_p_id)
        }}
        className={cn(
          "group relative flex w-full items-start gap-2 px-3 py-2 text-left",
          "transition-colors hover:bg-muted/40",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
          isSelected && "bg-accent/10",
          isSelected &&
            "before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:rounded-r before:bg-accent",
        )}
        aria-current={isSelected ? "true" : undefined}
        title={chat.title ?? `Chat ${chat.chat_id}`}
      >
        <div className="mt-0.5 flex shrink-0 items-center gap-1.5">
          <ChatStateIndicator state={chatState} />
          {isLive && (
            <Lightning
              weight="fill"
              className="size-2.5 text-emerald-500"
            />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-1">
            <span className="truncate text-xs font-medium text-foreground/90">
              {chat.title ?? (
                <span className="italic text-muted-foreground/70">
                  New chat
                </span>
              )}
            </span>
            <ElapsedTime
              startedAt={createdAt}
              format="relative"
              className="shrink-0 text-[10px] text-muted-foreground/60"
            />
          </div>
          <div className="mt-0.5 flex items-center gap-1.5">
            <ChatCircleDots
              weight="regular"
              className="size-3 shrink-0 text-muted-foreground/50"
            />
            {chat.model && (
              <span className="truncate font-mono text-[9px] uppercase tracking-wide text-muted-foreground/50">
                {chat.model}
              </span>
            )}
            <span className="text-[9px] text-muted-foreground/40">
              {CHAT_STATE_LABELS[chatState]}
            </span>
          </div>
        </div>

        {/* Expand/collapse caret for nested spawns */}
        {chat.active_p_id && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded((v) => !v)
            }}
            className="mt-0.5 shrink-0 rounded p-0.5 text-muted-foreground/50 hover:text-muted-foreground"
            aria-label={expanded ? "Collapse spawns" : "Expand spawns"}
          >
            {expanded ? (
              <CaretDown className="size-3" />
            ) : (
              <CaretRight className="size-3" />
            )}
          </button>
        )}
      </button>

      {/* Nested spawns (placeholder — will load from getChatSpawns when expanded) */}
      {expanded && chat.active_p_id && (
        <div className="border-l border-border/40 ml-5 py-0.5">
          <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] text-muted-foreground/60">
            <MonoId id={chat.active_p_id} className="text-[10px] px-0 py-0" />
            <span className="text-emerald-500">&bull; active</span>
          </div>
        </div>
      )}
    </li>
  )
}

// ---------------------------------------------------------------------------
// Spawn row (backwards compat — direct spawn viewing)
// ---------------------------------------------------------------------------

interface SpawnListRowProps {
  spawn: SpawnProjection
  isActive: boolean
  isFocused: boolean
  onSelect: (spawnId: string) => void
}

function SpawnListRow({ spawn, isActive, isFocused, onSelect }: SpawnListRowProps) {
  const status = parseStatus(spawn.status)
  const agent = spawn.agent?.trim() || "—"

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(spawn.spawn_id)}
        className={cn(
          "group relative flex w-full items-center gap-2 px-3 py-2 text-left",
          "transition-colors hover:bg-muted/40",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
          isActive && "bg-accent/10",
          isFocused && "before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:rounded-r before:bg-accent",
        )}
        aria-current={isFocused ? "true" : undefined}
        title={spawn.desc || agent}
      >
        <StatusDot status={status} size="sm" />
        <MonoId id={spawn.spawn_id} className="shrink-0 px-1 py-0 text-[11px]" />
        <span className="flex-1 truncate text-xs text-foreground/90">
          {agent}
        </span>
        <ElapsedTime
          startedAt={startedDate(spawn)}
          endedAt={endedDate(spawn)}
          format="relative"
          className="shrink-0 text-[10px] text-muted-foreground/70"
        />
      </button>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Substates
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <ul aria-busy="true" aria-label="Loading sessions" className="flex flex-col py-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="flex items-center gap-2 px-3 py-2">
          <Skeleton className="h-2 w-2 rounded-full" />
          <Skeleton className="h-3 w-10" />
          <Skeleton className="h-3 flex-1" />
          <Skeleton className="h-3 w-8" />
        </li>
      ))}
    </ul>
  )
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-32 flex-col items-center justify-center px-4 py-10 text-center">
      <ChatCircleDots
        weight="duotone"
        className="mb-2 size-8 text-muted-foreground/30"
      />
      <p className="text-xs text-muted-foreground">No chats or sessions</p>
      <p className="mt-1 text-[10px] text-muted-foreground/60">
        Start a new chat to begin
      </p>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="px-3 py-3 text-[11px] text-destructive"
    >
      <p className="font-medium">Failed to load</p>
      <p className="mt-0.5 break-words text-muted-foreground">{message}</p>
    </div>
  )
}
