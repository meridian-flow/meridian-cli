/**
 * Chat history hook — fetches AG-UI event history with pagination.
 *
 * Loads the first page on mount, exposes `loadMore()` to append the next
 * page. Re-fetches from scratch when `chatId` changes.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getChatHistory,
  type ChatHistoryEvent,
} from '@/lib/api'

export interface UseChatHistoryResult {
  events: ChatHistoryEvent[]
  isLoading: boolean
  isLoadingMore: boolean
  hasMore: boolean
  error: string | null
  loadMore: () => void
  refetch: () => void
}

const DEFAULT_PAGE_SIZE = 100

export function useChatHistory(
  chatId: string | null,
  pageSize: number = DEFAULT_PAGE_SIZE,
): UseChatHistoryResult {
  const [events, setEvents] = useState<ChatHistoryEvent[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false)
  const [hasMore, setHasMore] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const reqIdRef = useRef(0)

  const load = useCallback(async () => {
    if (!chatId) return

    const reqId = ++reqIdRef.current
    setError(null)
    setIsLoading(true)

    try {
      const resp = await getChatHistory(chatId, 0, pageSize)
      if (reqId !== reqIdRef.current) return
      setEvents(resp.events)
      setHasMore(resp.has_more)
      setIsLoading(false)
    } catch (err) {
      if (reqId !== reqIdRef.current) return
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      setIsLoading(false)
    }
  }, [chatId, pageSize])

  // Reset + fetch on chatId change.
  useEffect(() => {
    if (!chatId) {
      setEvents([])
      setIsLoading(false)
      setHasMore(false)
      setError(null)
      return
    }

    // Clear old events immediately before fetching new ones.
    // This prevents a race where stale events from the previous chat
    // could be seeded into the new chat by useChatConversation.
    setEvents([])
    setHasMore(false)
    setError(null)

    void load()
  }, [chatId, load])

  const loadMore = useCallback(async () => {
    if (!chatId || isLoadingMore || !hasMore) return

    setIsLoadingMore(true)
    const lastSeq = events.length > 0 ? events[events.length - 1].seq + 1 : 0

    try {
      const resp = await getChatHistory(chatId, lastSeq, pageSize)
      setEvents((prev) => {
        // Deduplicate by seq
        const existingSeqs = new Set(prev.map((e) => e.seq))
        const newEvents = resp.events.filter((e) => !existingSeqs.has(e.seq))
        return [...prev, ...newEvents]
      })
      setHasMore(resp.has_more)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
    } finally {
      setIsLoadingMore(false)
    }
  }, [chatId, isLoadingMore, hasMore, events, pageSize])

  const refetch = useCallback(() => {
    void load()
  }, [load])

  return { events, isLoading, isLoadingMore, hasMore, error, loadMore, refetch }
}
