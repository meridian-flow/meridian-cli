/**
 * SessionList — narrow sidebar of active and recent spawns for chat mode.
 *
 * The full filter surface lives in Sessions mode; here we keep the rail
 * lean. Compact rows show just enough to scan: status, id, agent, age.
 * Clicking a row opens (or focuses) the spawn as a column via ChatContext.
 *
 * Storybook bypasses the live `useSessions` hook via `dataOverride`. The
 * hook still mounts (rules of hooks) but the view reads from the override
 * so stories don't touch the network. Active-column highlighting also
 * accepts an override for the same reason — stories can pin which rows
 * appear "open" without mounting a stateful ChatProvider.
 */

import { useEffect, useMemo, useRef } from "react"

import { ElapsedTime, MonoId, StatusDot } from "@/components/atoms"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { parseStatus } from "@/types/spawn"

import { useChat } from "./ChatContext"
import { useSessions } from "@/features/sessions/hooks"
import type { SpawnProjection } from "@/features/sessions/lib/api"

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface SessionListProps {
  className?: string
  /**
   * Storybook/test escape hatch. When provided, bypasses the live
   * `useSessions` hook and the ChatContext for active-column rendering.
   * The `onSelect` callback receives clicks instead of `chat.openSpawn`.
   */
  dataOverride?: SessionListDataOverride
}

export interface SessionListDataOverride {
  spawns: SpawnProjection[]
  isLoading?: boolean
  error?: string | null
  activeColumns?: readonly string[]
  focusedColumn?: string | null
  onSelect?: (spawnId: string) => void
}

function startedDate(p: SpawnProjection): Date {
  const raw = p.started_at ?? p.created_at
  return raw ? new Date(raw) : new Date(0)
}

function endedDate(p: SpawnProjection): Date | undefined {
  return p.finished_at ? new Date(p.finished_at) : undefined
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionList({ className, dataOverride }: SessionListProps) {
  // Hooks always run regardless of override (rules of hooks). When the
  // override is supplied, we ignore the live values.
  const live = useSessions()
  const chat = useChat()

  const spawns = dataOverride?.spawns ?? live.spawns
  const isLoading = dataOverride?.isLoading ?? live.isLoading
  const isLoadingMore = live.isLoadingMore
  const hasMore = live.hasMore
  const error = dataOverride?.error ?? live.error
  const activeColumns = dataOverride?.activeColumns ?? chat.state.columns
  const focusedColumn = dataOverride?.focusedColumn ?? chat.state.focusedColumn
  const handleSelect = dataOverride?.onSelect ?? chat.openSpawn

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

  // Sort: active columns first (in their column order), then newest-first
  // by start time. Keeps focused work pinned at the top while still
  // reflecting recent activity below.
  const orderedSpawns = useMemo(() => {
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
          Sessions
        </h2>
        {!isLoading && !error && spawns.length > 0 ? (
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
            {spawns.length}
          </span>
        ) : null}
      </div>

      <ScrollArea className="flex-1">
        {error ? (
          <ErrorState message={error} />
        ) : isLoading ? (
          <LoadingState />
        ) : orderedSpawns.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <ul className="flex flex-col py-1">
              {orderedSpawns.map((p) => (
                <SessionListRow
                  key={p.spawn_id}
                  spawn={p}
                  isActive={activeSet.has(p.spawn_id)}
                  isFocused={focusedColumn === p.spawn_id}
                  onSelect={handleSelect}
                />
              ))}
            </ul>
            {hasMore && (
              <div ref={sentinelRef} className="flex items-center justify-center py-2">
                {isLoadingMore ? (
                  <div className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground" />
                ) : (
                  <span className="text-[10px] text-muted-foreground/40">·</span>
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
// Row
// ---------------------------------------------------------------------------

interface SessionListRowProps {
  spawn: SpawnProjection
  isActive: boolean
  isFocused: boolean
  onSelect: (spawnId: string) => void
}

function SessionListRow({ spawn, isActive, isFocused, onSelect }: SessionListRowProps) {
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
          // Subtle focus indicator: thin accent rail for the focused column
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
      <p className="text-xs text-muted-foreground">No sessions</p>
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
