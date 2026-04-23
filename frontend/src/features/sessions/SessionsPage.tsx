/**
 * Sessions mode — the main spawn list view.
 *
 * Thin container: wires `useSessions` + `useWorkItems` to a presentational
 * view. Stories can bypass hooks via `dataOverride` to pin any state
 * (loading, error, empty, populated) without mocking the network layer.
 *
 * Spawns are grouped by `work_id` (null → "Ungrouped"). Within a group,
 * newest-first by `started_at` (falling back to `created_at`); groups sort
 * by their freshest spawn so active work floats to the top.
 */

import { useCallback, useMemo, useState } from 'react'
import { ArrowClockwise, FolderOpen, WarningCircle } from '@phosphor-icons/react'

import { Button } from '@/components/ui/button'
import {
  FilterBar,
  SessionRow,
  SessionRowSkeleton,
  WorkItemGroupHeader,
  WorkItemGroupHeaderSkeleton,
  type StatusFilterValue,
} from '@/components/molecules'
import type { SpawnStatus, SpawnSummary } from '@/types/spawn'
import { cn } from '@/lib/utils'
import { useNavigation } from '@/shell/NavigationContext'

import { useSessions, useWorkItems } from './hooks'
import {
  archiveSpawn,
  cancelSpawn,
  forkSpawn,
  type SpawnProjection,
  type SpawnStats,
  type WorkProjection,
} from './lib'

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface SessionsPageProps {
  onNavigateToChat?: (spawnId: string) => void
  className?: string
  /**
   * Storybook/test escape hatch. When provided, bypasses `useSessions` and
   * `useWorkItems` entirely. Action handlers fall back to `console.log` so
   * stories remain interactive without network access.
   */
  dataOverride?: SessionsPageDataOverride
}

export interface SessionsPageDataOverride {
  spawns: SpawnProjection[]
  stats: SpawnStats | null
  workItems: WorkProjection[]
  isLoading?: boolean
  error?: string | null
  onRefetch?: () => void
  onAction?: (action: 'cancel' | 'fork' | 'archive', spawnId: string) => void
}

// ---------------------------------------------------------------------------
// Adapters
// ---------------------------------------------------------------------------

const KNOWN_STATUSES: ReadonlySet<SpawnStatus> = new Set<SpawnStatus>([
  'running',
  'queued',
  'succeeded',
  'failed',
  'cancelled',
  'finalizing',
])

function coerceStatus(raw: string): SpawnStatus {
  return (KNOWN_STATUSES.has(raw as SpawnStatus) ? raw : 'queued') as SpawnStatus
}

function nullifyEmpty(s: string | null | undefined): string | null {
  if (s === null || s === undefined) return null
  return s.trim() === '' ? null : s
}

/**
 * SessionRow wants a `SpawnSummary`; the API returns `SpawnProjection`.
 * The two differ in nullability conventions and the projection lacks
 * `cost_usd`. This is the single projection→summary seam.
 */
function toSummary(p: SpawnProjection): SpawnSummary {
  const started = p.started_at ?? p.created_at ?? new Date(0).toISOString()
  return {
    spawn_id: p.spawn_id,
    status: coerceStatus(p.status),
    agent: nullifyEmpty(p.agent),
    model: nullifyEmpty(p.model),
    harness: p.harness,
    work_id: p.work_id,
    desc: nullifyEmpty(p.desc),
    started_at: started,
    finished_at: p.finished_at,
    cost_usd: null,
  }
}

function statsToCounts(
  stats: SpawnStats | null,
): Partial<Record<SpawnStatus | 'all', number>> | undefined {
  if (!stats) return undefined
  return {
    all: stats.total,
    running: stats.running,
    queued: stats.queued,
    succeeded: stats.succeeded,
    failed: stats.failed,
    cancelled: stats.cancelled,
    finalizing: stats.finalizing,
  }
}

// ---------------------------------------------------------------------------
// Grouping
// ---------------------------------------------------------------------------

interface SpawnGroup {
  key: string | null
  name: string
  spawns: SpawnProjection[]
  lastActivity: Date | undefined
}

const UNGROUPED_LABEL = 'Ungrouped'

function timeOf(p: SpawnProjection): string {
  return p.started_at ?? p.created_at ?? ''
}

function groupSpawns(
  spawns: SpawnProjection[],
  workItems: WorkProjection[],
): SpawnGroup[] {
  const nameByWorkId = new Map<string, string>()
  for (const w of workItems) nameByWorkId.set(w.work_id, w.name)

  const buckets = new Map<string | null, SpawnProjection[]>()
  for (const s of spawns) {
    const key = s.work_id ?? null
    const existing = buckets.get(key)
    if (existing) existing.push(s)
    else buckets.set(key, [s])
  }

  const groups: SpawnGroup[] = []
  for (const [key, items] of buckets) {
    items.sort((a, b) => timeOf(b).localeCompare(timeOf(a)))
    const latest = timeOf(items[0] ?? ({} as SpawnProjection))
    const lastActivity = latest ? new Date(latest) : undefined
    const name =
      key === null
        ? UNGROUPED_LABEL
        : (nameByWorkId.get(key) ?? key)
    groups.push({ key, name, spawns: items, lastActivity })
  }

  // Groups ordered by freshest spawn — pinning active work to the top.
  // Ungrouped drops to the bottom when it has no activity.
  groups.sort((a, b) => {
    const at = a.spawns[0] ? timeOf(a.spawns[0]) : ''
    const bt = b.spawns[0] ? timeOf(b.spawns[0]) : ''
    if (at === bt) {
      // Stable tiebreaker: named groups before ungrouped bucket.
      if (a.key === null && b.key !== null) return 1
      if (b.key === null && a.key !== null) return -1
      return 0
    }
    return bt.localeCompare(at)
  })

  return groups
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SessionsPage({
  onNavigateToChat,
  className,
  dataOverride,
}: SessionsPageProps)  {
  const [statusFilter, setStatusFilter] = useState<StatusFilterValue>('all')
  const [workItemFilter, setWorkItemFilter] = useState<string | null>(null)
  const [agentFilter, setAgentFilter] = useState<string | null>(null)

  // Prop wins when provided (stories, tests); otherwise consume shell context.
  const { navigateToChat } = useNavigation()
  const handleNavigate = onNavigateToChat ?? navigateToChat

  // Hooks always run — conditional hook calls would violate the rules of
  // hooks. When overrides are supplied we just ignore the hook output.
  const liveSessions = useSessions({ statusFilter, workItemFilter, agentFilter })
  const liveWorkItems = useWorkItems()

  const spawns = dataOverride?.spawns ?? liveSessions.spawns
  const stats = dataOverride?.stats ?? liveSessions.stats
  const workItems = dataOverride?.workItems ?? liveWorkItems.workItems
  const isLoading = dataOverride?.isLoading ?? liveSessions.isLoading
  const error = dataOverride?.error ?? liveSessions.error

  const refetch = useCallback(() => {
    if (dataOverride?.onRefetch) {
      dataOverride.onRefetch()
    } else {
      liveSessions.refetch()
      liveWorkItems.refetch()
    }
  }, [dataOverride, liveSessions, liveWorkItems])

  const handleContextAction = useCallback(
    async (action: 'cancel' | 'fork' | 'archive', spawnId: string) => {
      if (dataOverride?.onAction) {
        dataOverride.onAction(action, spawnId)
        return
      }
      try {
        if (action === 'cancel') await cancelSpawn(spawnId)
        else if (action === 'fork') await forkSpawn(spawnId)
        else await archiveSpawn(spawnId)
        liveSessions.refetch()
      } catch (err) {
        // Surfaced via the next render's error banner if the refetch picks
        // it up; logging keeps the failure visible for devtools users.
        // eslint-disable-next-line no-console
        console.error(`[sessions] ${action} failed for ${spawnId}:`, err)
      }
    },
    [dataOverride, liveSessions],
  )

  // Derived: de-duplicated list of agents currently visible, for the filter
  // popover. Pulled from `spawns` (not hooks) so overrides work in stories.
  const availableAgents = useMemo(() => {
    const seen = new Set<string>()
    for (const s of spawns) {
      if (s.agent && s.agent.trim() !== '') seen.add(s.agent)
    }
    return [...seen].sort((a, b) => a.localeCompare(b))
  }, [spawns])

  const availableWorkItems = useMemo(
    () => workItems.map((w) => ({ work_id: w.work_id, name: w.name })),
    [workItems],
  )

  const groups = useMemo(
    () => groupSpawns(spawns, workItems),
    [spawns, workItems],
  )

  const statusCounts = useMemo(() => statsToCounts(stats), [stats])

  return (
    <div
      className={cn(
        'flex h-full w-full flex-col overflow-hidden bg-background',
        className,
      )}
    >
      {/* Filter bar — fixed at top */}
      <div className="border-b border-border bg-background/80 px-4 py-3 backdrop-blur-sm">
        <FilterBar
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          statusCounts={statusCounts}
          workItemFilter={workItemFilter}
          onWorkItemFilterChange={setWorkItemFilter}
          availableWorkItems={availableWorkItems}
          agentFilter={agentFilter}
          onAgentFilterChange={setAgentFilter}
          availableAgents={availableAgents}
        />
      </div>

      {/* Body — scrollable region filling remaining height */}
      <div className="relative flex-1 overflow-y-auto">
        {error ? (
          <ErrorBanner message={error} onRetry={refetch} />
        ) : isLoading ? (
          <LoadingSkeleton />
        ) : groups.length === 0 ? (
          <EmptyState hasFilters={hasActiveFilters(statusFilter, workItemFilter, agentFilter)} />
        ) : (
          <div className="flex flex-col">
            {groups.map((group) => (
              <WorkItemGroupHeader
                key={group.key ?? '__ungrouped__'}
                name={group.name}
                spawnCount={group.spawns.length}
                lastActivity={group.lastActivity}
              >
                <div className="flex flex-col">
                  {group.spawns.map((p) => (
                    <SessionRow
                      key={p.spawn_id}
                      spawn={toSummary(p)}
                      onClick={() => handleNavigate(p.spawn_id)}
                      onContextAction={(action) => {
                        void handleContextAction(action, p.spawn_id)
                      }}
                    />
                  ))}
                </div>
              </WorkItemGroupHeader>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Substates
// ---------------------------------------------------------------------------

function hasActiveFilters(
  status: StatusFilterValue,
  work: string | null,
  agent: string | null,
): boolean {
  return status !== 'all' || work !== null || agent !== null
}

function LoadingSkeleton()  {
  return (
    <div aria-busy="true" aria-label="Loading sessions" className="flex flex-col">
      {Array.from({ length: 3 }).map((_, gi) => (
        <div key={gi}>
          <WorkItemGroupHeaderSkeleton />
          <div className="flex flex-col">
            {Array.from({ length: 3 }).map((_, ri) => (
              <SessionRowSkeleton key={ri} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function EmptyState({ hasFilters }: { hasFilters: boolean })  {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div
        className={cn(
          'flex h-14 w-14 items-center justify-center rounded-full',
          'bg-muted/40 text-muted-foreground',
        )}
      >
        <FolderOpen size={28} weight="duotone" />
      </div>
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-foreground">
          {hasFilters ? 'No sessions match your filters' : 'No sessions yet'}
        </p>
        <p className="max-w-xs text-xs text-muted-foreground">
          {hasFilters
            ? 'Try clearing a filter or broadening the status selection.'
            : 'Spawn your first agent to see it here in real time.'}
        </p>
      </div>
    </div>
  )
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
})  {
  return (
    <div className="px-4 py-3">
      <div
        role="alert"
        className={cn(
          'flex items-start gap-3 rounded-md border px-3 py-2.5',
          'border-destructive/40 bg-destructive/5 text-sm',
        )}
      >
        <WarningCircle
          size={18}
          weight="duotone"
          className="mt-0.5 shrink-0 text-destructive"
        />
        <div className="flex-1">
          <p className="font-medium text-destructive">Failed to load sessions</p>
          <p className="mt-0.5 text-xs text-muted-foreground break-words">{message}</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={onRetry}
          className="h-7 gap-1 text-xs"
        >
          <ArrowClockwise size={12} weight="bold" />
          Retry
        </Button>
      </div>
    </div>
  )
}
