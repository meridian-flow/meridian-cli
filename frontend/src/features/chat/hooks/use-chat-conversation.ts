/**
 * useChatConversation — unified hook for chat conversation state.
 *
 * Combines three data sources into a single ConversationEntry[] model:
 * 1. History loaded from getChatHistory on mount → replayed through reducer
 * 2. Live streaming via SpawnChannel when activeSpawnId is set
 * 3. Chat API lifecycle (create, prompt, cancel)
 *
 * This is the main state owner for ChatThreadView. The component becomes
 * a thin rendering shell consuming entries + currentActivity.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import {
  EventType,
  SpawnChannel,
  type StreamEvent as WsStreamEvent,
  type WsState,
} from "@/lib/ws"
import { mapWsEventToStreamEvents } from "@/features/activity-stream/streaming/map-ws-event"
import type { StreamController } from "../transport-types"
import type { ConversationEntry } from "../conversation-types"
import type { ActivityBlockData } from "@/features/activity-stream/types"
import {
  conversationReducer,
  createInitialConversationState,
  type ConversationAction,
  type ConversationState,
} from "../conversation-reducer"
import { useChatHistory } from "./use-chat-history"
import {
  createChat,
  promptChat,
  cancelChat,
  getChat,
  fetchSpawnReplay,
  ApiError,
  type ChatState as ApiChatState,
  type ChatDetailResponse,
  type CreateChatOptions,
} from "@/lib/api"

import { transformHistoryToEntries } from "./transform-history"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseChatConversationOptions {
  chatId: string
  activeSpawnId: string | null
  initialPrompt?: string | null
  createChatOptions?: CreateChatOptions
  onChatCreated?: (detail: ChatDetailResponse) => void
  onSpawnStarted?: (spawnId: string) => void
  onChatStateChange?: (state: ApiChatState) => void
}

export interface UseChatConversationReturn {
  entries: ConversationEntry[]
  currentActivity: ActivityBlockData | null
  isStreaming: boolean
  isLoading: boolean
  isCreating: boolean
  isSending: boolean
  connectionState: WsState
  controller: StreamController
  chatState: ApiChatState | null
  chatDetail: ChatDetailResponse | null
  error: string | null
  sendMessage: (text: string) => Promise<void>
  cancel: () => Promise<void>
}

// ---------------------------------------------------------------------------
// Reducer wrapper — extends ConversationAction with SEED_HISTORY
// ---------------------------------------------------------------------------

type ExtendedAction =
  | ConversationAction
  | { type: "SEED_HISTORY"; entries: ConversationEntry[] }

function extendedReducer(
  state: ConversationState,
  action: ExtendedAction,
): ConversationState {
  if (action.type === "SEED_HISTORY") {
    return {
      ...state,
      entries: action.entries,
      turnSeq: action.entries.length,
    }
  }
  return conversationReducer(state, action as ConversationAction)
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChatConversation({
  chatId,
  activeSpawnId,
  initialPrompt,
  createChatOptions,
  onChatCreated,
  onSpawnStarted,
  onChatStateChange,
}: UseChatConversationOptions): UseChatConversationReturn {
  const [state, dispatch] = useReducer(extendedReducer, createInitialConversationState())
  const [connectionState, setConnectionState] = useState<WsState>("idle")
  const [chatState, setChatState] = useState<ApiChatState | null>(null)
  const [chatDetail, setChatDetail] = useState<ChatDetailResponse | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const channelRef = useRef<SpawnChannel | null>(null)
  const receivedTerminalRef = useRef(false)
  const generationRef = useRef(0)
  const startedTextRef = useRef<Set<string>>(new Set())
  const startedThinkingRef = useRef<Set<string>>(new Set())
  const startedToolRef = useRef<Set<string>>(new Set())
  const didAutoSend = useRef(false)
  // Only connect WS when the chat is actively streaming. For idle/closed
  // chats loaded from sidebar, history REST is sufficient — no WS needed
  // until the user sends a message or the chat is known to be active.
  const [wsEnabled, setWsEnabled] = useState(false)

  // Stable refs for callbacks/options to avoid stale closures in SpawnChannel
  const createChatOptionsRef = useRef(createChatOptions)
  createChatOptionsRef.current = createChatOptions
  const onChatCreatedRef = useRef(onChatCreated)
  onChatCreatedRef.current = onChatCreated
  const onSpawnStartedRef = useRef(onSpawnStarted)
  onSpawnStartedRef.current = onSpawnStarted
  const onChatStateChangeRef = useRef(onChatStateChange)
  onChatStateChangeRef.current = onChatStateChange

  const resetStartedSets = useCallback(() => {
    startedTextRef.current.clear()
    startedThinkingRef.current.clear()
    startedToolRef.current.clear()
    receivedTerminalRef.current = false
  }, [])

  // -----------------------------------------------------------------------
  // 0. Reset state when chatId changes (prevents stale entries on switch)
  //    Exception: __new__ → real ID is the same conversation (chat creation),
  //    so preserve the USER_SENT entry and streaming state.
  // -----------------------------------------------------------------------

  const prevChatIdRef = useRef(chatId)

  useEffect(() => {
    if (prevChatIdRef.current === chatId) return
    const wasNew = prevChatIdRef.current === "__new__"
    prevChatIdRef.current = chatId

    // When transitioning from zero state to a created chat, keep the
    // conversation entries (the user's first message) and streaming refs.
    // Only clear transient API state so the detail fetch picks up the real chat.
    if (wasNew && chatId !== "__new__") {
      didSeedHistory.current = chatId // Skip re-seeding — entries are live
      setError(null)
      return
    }

    dispatch({ type: "RESET" })
    didSeedHistory.current = null
    didAutoSend.current = false
    setWsEnabled(false)
    setError(null)
    setChatState(null)
    setChatDetail(null)
    resetStartedSets()
  }, [chatId, resetStartedSets])

  // -----------------------------------------------------------------------
  // 1. Load chat detail on mount (for existing chats)
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (chatId === "__new__") return

    let cancelled = false
    getChat(chatId)
      .then((detail) => {
        if (cancelled) return
        setChatState(detail.state)
        setChatDetail(detail)
        onChatStateChangeRef.current?.(detail.state)
        // Only connect WS if the chat is actively running — idle/closed
        // chats just show history from REST, no WS needed.
        const isActive = detail.state === "active" || detail.state === "draining"
        if (isActive && detail.active_p_id) {
          setWsEnabled(true)
          onSpawnStartedRef.current?.(detail.active_p_id)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : String(err))
      })

    return () => {
      cancelled = true
    }
  }, [chatId])

  // -----------------------------------------------------------------------
  // 2. Load and transform history
  // -----------------------------------------------------------------------

  const { events: historyEvents, isLoading: historyLoading } = useChatHistory(
    chatId !== "__new__" ? chatId : null,
  )

  const didSeedHistory = useRef<string | null>(null)

  useEffect(() => {
    if (historyEvents.length === 0) return
    if (didSeedHistory.current === chatId) return // Already seeded this chat
    didSeedHistory.current = chatId

    const entries = transformHistoryToEntries(historyEvents)
    dispatch({ type: "SEED_HISTORY", entries })
  }, [historyEvents, chatId])

  // -----------------------------------------------------------------------
  // 3. Auto-send initial prompt for new chats
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!initialPrompt || didAutoSend.current) return
    if (chatId !== "__new__") return
    didAutoSend.current = true

    // Add user message immediately
    dispatch({
      type: "USER_SENT",
      id: `user-${Date.now()}`,
      text: initialPrompt,
    })

    // Create the chat
    setIsCreating(true)
    setError(null)

    createChat(initialPrompt, createChatOptionsRef.current)
      .then((detail) => {
        setChatState(detail.state)
        setChatDetail(detail)
        onChatCreatedRef.current?.(detail)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        setIsCreating(false)
      })
  }, [initialPrompt, chatId])

  // -----------------------------------------------------------------------
  // 4. WebSocket streaming — connect only when wsEnabled AND activeSpawnId set.
  //    For idle/closed chats, history REST is sufficient. WS connects when:
  //    - Chat detail shows active/draining state (loaded from sidebar)
  //    - Chat just created (zero state → first message)
  //    - Follow-up message sent to idle chat
  //    Uses Connect-Then-Replay protocol for existing chats (EARS-R011)
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!activeSpawnId || !wsEnabled) {
      channelRef.current?.destroy()
      channelRef.current = null
      setConnectionState("idle")
      resetStartedSets()
      return
    }

    // Freeze any previous streaming state before connecting new spawn
    if (state.current !== null) {
      dispatch({ type: "SESSION_ENDED" })
    }

    resetStartedSets()
    setConnectionState("connecting")

    const currentGeneration = ++generationRef.current
    const currentSpawnId = activeSpawnId

    // Determine if we should use replay mode (for existing chats, not new ones)
    const useReplayMode = chatId !== "__new__"

    const channel = new SpawnChannel(
      currentSpawnId,
      {
        onEvent: (event: WsStreamEvent) => {
          if (generationRef.current !== currentGeneration) {
            return
          }

          // Skip capabilities events
          if (event.type === EventType.CUSTOM && (event as { name: string }).name === "capabilities") {
            return
          }

          for (const mapped of mapWsEventToStreamEvents(event, {
            text: startedTextRef.current,
            thinking: startedThinkingRef.current,
            tool: startedToolRef.current,
          })) {
            dispatch({ type: "STREAM_EVENT", event: mapped })

            if (mapped.type === "RUN_ERROR") {
              receivedTerminalRef.current = true
            }
          }
        },
        onClose: () => {
          if (generationRef.current !== currentGeneration) return

          if (receivedTerminalRef.current) {
            dispatch({ type: "SESSION_ENDED" })
          }
        },
        onStateChange: (nextState) => {
          if (generationRef.current !== currentGeneration) return
          setConnectionState(nextState)
        },
      },
      // Pass replay query param for existing chats (EARS-R006)
      useReplayMode ? { queryParams: { replay: "1" } } : {},
    )

    channel.connect()
    channelRef.current = channel

    // If using replay mode, fetch replay snapshot and seed conversation (EARS-R011)
    if (useReplayMode) {
      ;(async () => {
        try {
          const snapshot = await fetchSpawnReplay(currentSpawnId)
          if (generationRef.current !== currentGeneration) return

          // Transform replay events into conversation entries
          // The events are already in the same format as history events
          const entries = transformHistoryToEntries(snapshot.events)

          // Interleave inbound user messages (EARS-R012)
          // K-th inbound entry is inserted before K-th assistant turn
          if (snapshot.inbound.length > 0) {
            const entriesWithInbound: ConversationEntry[] = []
            let inboundIdx = 0
            for (const entry of entries) {
              // Insert user message before each assistant entry (turn boundary)
              if (entry.kind === "assistant" && inboundIdx < snapshot.inbound.length) {
                const inbound = snapshot.inbound[inboundIdx]
                entriesWithInbound.push({
                  kind: "user",
                  id: `replay-user-${inbound.seq}`,
                  text: inbound.text,
                  sentAt: new Date(inbound.ts * 1000),
                })
                inboundIdx++
              }
              entriesWithInbound.push(entry)
            }
            // Add any remaining inbound messages (shouldn't happen normally)
            while (inboundIdx < snapshot.inbound.length) {
              const inbound = snapshot.inbound[inboundIdx]
              entriesWithInbound.push({
                kind: "user",
                id: `replay-user-${inbound.seq}`,
                text: inbound.text,
                sentAt: new Date(inbound.ts * 1000),
              })
              inboundIdx++
            }
            dispatch({ type: "SEED_HISTORY", entries: entriesWithInbound })
          } else {
            dispatch({ type: "SEED_HISTORY", entries })
          }

          // Send replay acknowledgment to unblock WS streaming (EARS-R011 step 4)
          channel.sendReplayAck(snapshot.cursor)
        } catch (err) {
          // Replay fetch failed — fall back to current behavior (EARS-R015)
          // The WS will timeout and send all events from subscription time
          console.warn("Replay fetch failed, falling back to live-only mode:", err)
        }
      })()
    }

    return () => {
      channel.destroy()
      if (channelRef.current === channel) {
        channelRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSpawnId, wsEnabled, resetStartedSets, chatId])

  // -----------------------------------------------------------------------
  // 5. Send message
  // -----------------------------------------------------------------------

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed) return

      setError(null)

      // Append user message immediately
      dispatch({
        type: "USER_SENT",
        id: `user-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        text: trimmed,
      })

      if (chatId === "__new__") {
        setIsCreating(true)
        try {
          const detail = await createChat(trimmed, createChatOptionsRef.current)
          setChatState(detail.state)
          setWsEnabled(true) // Chat just created — connect WS for streaming
          onChatCreatedRef.current?.(detail)
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err))
        } finally {
          setIsCreating(false)
        }
      } else {
        setIsSending(true)
        try {
          const detail = await promptChat(chatId, trimmed)
          setChatState(detail.state)
          setChatDetail(detail)
          setWsEnabled(true) // Follow-up sent — connect WS for streaming
          onChatStateChangeRef.current?.(detail.state)
          if (detail.active_p_id) {
            onSpawnStartedRef.current?.(detail.active_p_id)
          }
        } catch (err) {
          if (err instanceof ApiError && err.status === 409) {
            setError("Chat is busy — waiting for the current response to complete.")
          } else {
            setError(err instanceof Error ? err.message : String(err))
          }
        } finally {
          setIsSending(false)
        }
      }
    },
    [chatId],
  )

  // -----------------------------------------------------------------------
  // 6. Cancel
  // -----------------------------------------------------------------------

  const cancel = useCallback(async () => {
    if (chatId === "__new__") return

    // Optimistically show draining state
    setChatState("draining")
    onChatStateChangeRef.current?.("draining")

    try {
      await cancelChat(chatId)
      // Refetch to get the settled state
      const detail = await getChat(chatId)
      setChatState(detail.state)
      setChatDetail(detail)
      onChatStateChangeRef.current?.(detail.state)
    } catch {
      // Cancel is best-effort — state will settle via WS
    }
  }, [chatId])

  // -----------------------------------------------------------------------
  // 7. Stream controller (WS-based interrupt/cancel)
  // -----------------------------------------------------------------------

  const controller = useMemo<StreamController>(
    () => ({
      sendMessage: (msg) => channelRef.current?.sendMessage(msg) ?? false,
      interrupt: () => channelRef.current?.interrupt() ?? false,
      cancel: () => {
        channelRef.current?.cancel()
      },
    }),
    [],
  )

  // -----------------------------------------------------------------------
  // 8. Derived state
  // -----------------------------------------------------------------------

  const isStreaming = Boolean(state.current?.activity.isStreaming)
  const currentActivity = state.current?.activity ?? null

  return {
    entries: state.entries,
    currentActivity,
    isStreaming,
    isLoading: historyLoading,
    isCreating,
    isSending,
    connectionState,
    controller,
    chatState,
    chatDetail,
    error,
    sendMessage,
    cancel,
  }
}
