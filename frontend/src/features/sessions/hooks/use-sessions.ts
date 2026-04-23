/**
 * Spawn list + stats with live SSE updates.
 *
 * - Initial load: parallel fetch of list and stats.
 * - Refetch on filter change.
 * - SSE: on any `spawn.event`, schedule a debounced refetch (500ms) so a
 *   burst of events coalesces into a single round-trip.
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
}

export interface UseSessionsResult {
  spawns: SpawnProjection[]
  stats: SpawnStats | null
  isLoading: boolean
  error: string | null
  refetch: () => void
}

const REFETCH_DEBOUNCE_MS = 500

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
  const { statusFilter, workItemFilter, agentFilter } = options

  const [spawns, setSpawns] = useState<SpawnProjection[]>([])
  const [stats, setStats] = useState<SpawnStats | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const reqIdRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { param: statusParam, localStatuses } = useMemo(
    () => resolveStatusParam(statusFilter),
    [statusFilter],
  )

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
      setIsLoading(false)
    } catch (err) {
      if (reqId !== reqIdRef.current) return
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      setIsLoading(false)
    }
  }, [statusParam, localStatuses, workItemFilter, agentFilter])

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

  return { spawns, stats, isLoading, error, refetch }
}
