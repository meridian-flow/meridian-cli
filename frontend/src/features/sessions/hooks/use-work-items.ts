/**
 * Work item list with SSE-triggered refresh.
 *
 * Work items change less frequently than spawns, so we only refetch when
 * an SSE frame explicitly mentions work.*. A new spawn inside an existing
 * work item triggers spawn.* events, not work.*, so a spawn storm doesn't
 * churn this hook.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { sseClient } from '@/lib/sse'

import { fetchWorkItems, type WorkProjection } from '../lib/api'

export interface UseWorkItemsResult {
  workItems: WorkProjection[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

const REFETCH_DEBOUNCE_MS = 500

export function useWorkItems(): UseWorkItemsResult {
  const [workItems, setWorkItems] = useState<WorkProjection[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const reqIdRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    const reqId = ++reqIdRef.current
    setError(null)
    try {
      const resp = await fetchWorkItems()
      if (reqId !== reqIdRef.current) return
      setWorkItems(resp.items)
      setIsLoading(false)
    } catch (err) {
      if (reqId !== reqIdRef.current) return
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      setIsLoading(false)
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
      if (!raw.includes('work')) return
      try {
        const parsed = JSON.parse(raw) as { type?: string }
        const type = parsed?.type
        if (typeof type === 'string' && type.startsWith('work')) {
          scheduleRefetch()
        }
      } catch {
        // non-JSON — ignore
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

  return { workItems, isLoading, error, refetch }
}
