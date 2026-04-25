/**
 * Chat list with SSE-triggered refresh.
 *
 * Fetches all chats on mount and refetches when SSE broadcasts a
 * chat-related event. Bursts of events are debounced so a flurry of
 * chat updates coalesces into a single round-trip.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { sseClient } from '@/lib/sse'

import { listChats, type ChatProjection } from '@/lib/api'

export interface UseChatSessionsResult {
  chats: ChatProjection[]
  isLoading: boolean
  error: string | null
  refetch: () => void
}

const REFETCH_DEBOUNCE_MS = 500

export function useChatSessions(): UseChatSessionsResult {
  const [chats, setChats] = useState<ChatProjection[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  const reqIdRef = useRef(0)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    const reqId = ++reqIdRef.current
    setError(null)
    try {
      const resp = await listChats()
      if (reqId !== reqIdRef.current) return
      setChats(resp)
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

  // Initial load.
  useEffect(() => {
    void load()
  }, [load])

  // SSE live updates — refetch on chat.* or spawn.* events (a new spawn
  // under a chat may change the chat's state/active_p_id).
  useEffect(() => {
    const unsubscribe = sseClient.subscribe((event) => {
      const raw = event.data
      if (typeof raw !== 'string') return
      if (!raw.includes('chat') && !raw.includes('spawn')) return
      try {
        const parsed = JSON.parse(raw) as { type?: string }
        const type = parsed?.type
        if (
          typeof type === 'string' &&
          (type.startsWith('chat') || type.startsWith('spawn'))
        ) {
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

  return { chats, isLoading, error, refetch }
}
