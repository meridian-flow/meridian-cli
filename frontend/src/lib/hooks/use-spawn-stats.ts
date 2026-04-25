/**
 * Lightweight stats + connection status hook.
 *
 * For the StatusBar — doesn't fetch or hold the spawn list. Reuses the
 * shared SSE singleton so it costs no extra connection.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { sseClient, type SSEConnectionStatus } from '@/lib/sse'

import { fetchSpawnStats, type SpawnStats } from '@/lib/api'

export interface UseSpawnStatsResult {
  stats: SpawnStats | null
  connectionStatus: SSEConnectionStatus
  error: string | null
}

const REFETCH_DEBOUNCE_MS = 500

export function useSpawnStats(): UseSpawnStatsResult {
  const [stats, setStats] = useState<SpawnStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [connectionStatus, setConnectionStatus] = useState<SSEConnectionStatus>(
    sseClient.getStatus(),
  )

  const reqIdRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    const reqId = ++reqIdRef.current
    try {
      const resp = await fetchSpawnStats()
      if (reqId !== reqIdRef.current) return
      setStats(resp)
      setError(null)
    } catch (err) {
      if (reqId !== reqIdRef.current) return
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
    }
  }, [])

  const scheduleRefetch = useCallback(() => {
    if (debounceTimerRef.current !== null) return
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null
      void load()
    }, REFETCH_DEBOUNCE_MS)
  }, [load])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const unsubscribe = sseClient.subscribe((event) => {
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
        // ignore
      }
    })
    const unsubscribeStatus = sseClient.onStatusChange((next) => {
      setConnectionStatus(next)
    })
    // Sync initial status in case it changed between render and subscribe.
    setConnectionStatus(sseClient.getStatus())

    return () => {
      unsubscribe()
      unsubscribeStatus()
      if (debounceTimerRef.current !== null) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }
    }
  }, [scheduleRefetch])

  return { stats, connectionStatus, error }
}
