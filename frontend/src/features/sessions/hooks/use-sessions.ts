/**
 * Spawn list + stats with live SSE updates and cursor pagination.
 *
 * - Initial load: parallel fetch of first page and stats.
 * - Refetch on filter change (resets to first page).
 * - `loadMore()`: appends next page using the cursor from the last response.
 * - SSE: on any `spawn.event`, schedule a debounced refetch of the first
 *   page (500ms) so a burst of events coalesces into a single round-trip.
 *   SSE refetch replaces only the first page and preserves already-loaded
 *   pages to avoid jarring resets.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { STATUS_FILTER_MAPPING, type StatusFilterValue } from '@/components/molecules/FilterBar'
import type { SpawnStatus } from '@/types/spawn'
import { sseClient } from '@/lib/sse'

import {
  fetchSpawnStats,
  fetchSpawns,
  type SpawnProjection,
  type SpawnStats,
} from '../lib/api'

export interface UseSessionsOptions {
  statusFilter?: StatusFilterValue
  workItemFilter?: string | null
  agentFilter?: string | null
  /** Page size — defaults to 50. */
  pageSize?: number
}

export interface UseSessionsResult {
  spawns: SpawnProjection[]
  stats: SpawnStats | null
  isLoading: boolean
  isLoadingMore: boolean
  hasMore: boolean
  error: string | null
  refetch: () => void
  loadMore: () => void
}

const REFETCH_DEBOUNCE_MS = 500
const DEFAULT_PAGE_SIZE = 50

/**
 * Map the UI status filter to a server-side `status` query param. The
 * backend accepts a single status string, so grouped filters like "done"
 * fan out client-side: we pass no `status` param and filter items locally.
 */
function resolveStatusParam(filter: StatusFilterValue | undefined): {
  param: SpawnStatus | undefined
  localStatuses: readonly SpawnStatus[] | null
} {
  if (!filter || filter === 'all') {
    return { param: undefined, localStatuses: null }
  }
  const mapping = STATUS_FILTER_MAPPING[filter]
  if (mapping === 'all') {
    return { param: undefined, localStatuses: null }
  }
  if (mapping.length === 1) {
    return { param: mapping[0], localStatuses: null }
  }
  return { param: undefined, localStatuses: mapping }
}

export function useSessions(options: UseSessionsOptions = {}): UseSessionsResult {
  const { statusFilter, workItemFilter, agentFilter, pageSize = DEFAULT_PAGE_SIZE } = options

  const [spawns, setSpawns] = useState<SpawnProjection[]>([])
  const [stats, setStats] = useState<SpawnStats | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false)
  const [hasMore, setHasMore] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const reqIdRef = useRef(0)
  const cursorRef = useRef<string | null>(null)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { param: statusParam, localStatuses } = useMemo(
    () => resolveStatusParam(statusFilter),
    [statusFilter],
  )

  /** Fetch first page + stats. Resets accumulated spawns. */
  const load = useCallback(async () => {
    const reqId = ++reqIdRef.current
    setError(null)

    const workId = workItemFilter ?? undefined
    try {
      const [listResp, statsResp] = await Promise.all([
        fetchSpawns({
          work_id: workId,
          status: statusParam,
          agent: agentFilter ?? undefined,
          limit: pageSize,
        }),
        fetchSpawnStats(workId),
      ])

      // Stale response guard — a newer request may have started.
      if (reqId !== reqIdRef.current) return

      let items = listResp.items
      if (localStatuses) {
        const allowed = new Set<string>(localStatuses)
        items = items.filter((s) => allowed.has(s.status))
      }

      setSpawns(items)
      setStats(statsResp)
      setHasMore(listResp.has_more)
      cursorRef.current = listResp.next_cursor ?? null
      setIsLoading(false)
    } catch (err) {
      if (reqId !== reqIdRef.current) return
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      setIsLoading(false)
    }
  }, [statusParam, localStatuses, workItemFilter, agentFilter, pageSize])

  /** Fetch next page and append to existing spawns. */
  const loadMore = useCallback(async () => {
    if (!cursorRef.current || isLoadingMore) return

    setIsLoadingMore(true)
    const workId = workItemFilter ?? undefined
    try {
      const listResp = await fetchSpawns({
        work_id: workId,
        status: statusParam,
        agent: agentFilter ?? undefined,
        limit: pageSize,
        cursor: cursorRef.current,
      })

      let items = listResp.items
      if (localStatuses) {
        const allowed = new Set<string>(localStatuses)
        items = items.filter((s) => allowed.has(s.status))
      }

      setSpawns((prev) => {
        // Deduplicate — SSE refetch may have already added some of these
        const existingIds = new Set(prev.map((s) => s.spawn_id))
        const newItems = items.filter((s) => !existingIds.has(s.spawn_id))
        return [...prev, ...newItems]
      })
      setHasMore(listResp.has_more)
      cursorRef.current = listResp.next_cursor ?? null
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
    } finally {
      setIsLoadingMore(false)
    }
  }, [statusParam, localStatuses, workItemFilter, agentFilter, pageSize, isLoadingMore])

  const scheduleRefetch = useCallback(() => {
    if (debounceTimerRef.current !== null) return
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null
      void load()
    }, REFETCH_DEBOUNCE_MS)
  }, [load])

  // Initial load + refetch on filter change.
  useEffect(() => {
    setIsLoading(true)
    cursorRef.current = null
    void load()
  }, [load])

  // SSE live updates.
  useEffect(() => {
    const unsubscribe = sseClient.subscribe((event) => {
      // Only spawn-related frames drive refetch. Parse lazily to avoid
      // unpacking every frame on the hot path.
      const raw = event.data
      if (typeof raw !== 'string') return
      if (!raw.includes('spawn')) return
      try {
        const parsed = JSON.parse(raw) as { type?: string }
        const type = parsed?.type
        if (typeof type === 'string' && type.startsWith('spawn')) {
          scheduleRefetch()
        }
      } catch {
        // non-JSON frame — ignore
      }
    })
    return () => {
      unsubscribe()
      if (debounceTimerRef.current !== null) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
    }
  }, [scheduleRefetch])

  const refetch = useCallback(() => {
    void load()
  }, [load])

  return { spawns, stats, isLoading, isLoadingMore, hasMore, error, refetch, loadMore }
}
