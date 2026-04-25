import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import {
  EventType,
  SpawnChannel,
  type ConnectionCapabilities,
  type StreamEvent as WsStreamEvent,
  type WsState,
} from "@/lib/ws"
import { mapWsEventToStreamEvents } from "@/features/activity-stream/streaming/map-ws-event"
import type { StreamController } from "@/features/chat/transport-types"
import {
  conversationReducer,
  createInitialConversationState,
} from "@/features/chat/conversation-reducer"
import type {
  UserEntry,
  AssistantEntry,
  ConversationEntry,
} from "@/features/chat/conversation-types"

import type { TestChatSessionInfo } from "./session-api"

export type { UserEntry, AssistantEntry, ConversationEntry }

export function useTestChatSession(session: TestChatSessionInfo | null) {
  const [state, dispatch] = useReducer(conversationReducer, createInitialConversationState())
  const [capabilities, setCapabilities] = useState<ConnectionCapabilities | null>(null)
  const [connectionState, setConnectionState] = useState<WsState>("idle")
  const channelRef = useRef<SpawnChannel | null>(null)
  const receivedTerminalRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const sessionGenerationRef = useRef(0)
  const startedTextRef = useRef<Set<string>>(new Set())
  const startedThinkingRef = useRef<Set<string>>(new Set())
  const startedToolRef = useRef<Set<string>>(new Set())

  const resetStartedSets = useCallback(() => {
    startedTextRef.current.clear()
    startedThinkingRef.current.clear()
    startedToolRef.current.clear()
    receivedTerminalRef.current = false
  }, [])

  useEffect(() => {
    if (!session) {
      sessionGenerationRef.current += 1
      sessionIdRef.current = null
      channelRef.current?.destroy()
      channelRef.current = null
      setConnectionState("idle")
      setCapabilities(null)
      resetStartedSets()
      dispatch({ type: "RESET" })
      return
    }

    dispatch({ type: "RESET" })
    setConnectionState("connecting")
    setCapabilities(null)
    resetStartedSets()
    receivedTerminalRef.current = false

    const currentSessionId = session.spawn_id
    const currentGeneration = sessionGenerationRef.current + 1
    sessionGenerationRef.current = currentGeneration
    sessionIdRef.current = currentSessionId

    const channel = new SpawnChannel(currentSessionId, {
      onCapabilities: (nextCapabilities) => {
        if (
          sessionGenerationRef.current !== currentGeneration ||
          sessionIdRef.current !== currentSessionId
        ) {
          return
        }
        setCapabilities(nextCapabilities)
      },
      onEvent: (event: WsStreamEvent) => {
        if (
          sessionGenerationRef.current !== currentGeneration ||
          sessionIdRef.current !== currentSessionId
        ) {
          return
        }

        if (event.type === EventType.CUSTOM && event.name === "capabilities") {
          setCapabilities(event.value as ConnectionCapabilities)
          return
        }

        for (const mapped of mapWsEventToStreamEvents(event, {
          text: startedTextRef.current,
          thinking: startedThinkingRef.current,
          tool: startedToolRef.current,
        })) {
          dispatch({ type: "STREAM_EVENT", event: mapped })

          // RUN_FINISHED means one turn is done — NOT the session.
          // Only mark terminal on RUN_ERROR (spawn crashed / was cancelled).
          // RUN_FINISHED just means the agent finished responding and is
          // waiting for the next inject.
          if (mapped.type === "RUN_ERROR") {
            receivedTerminalRef.current = true
          }
        }
      },
      onClose: () => {
        if (
          sessionGenerationRef.current !== currentGeneration ||
          sessionIdRef.current !== currentSessionId
        ) {
          return
        }

        if (receivedTerminalRef.current) {
          dispatch({ type: "SESSION_ENDED" })
        }
      },
      onStateChange: (nextState) => {
        if (
          sessionGenerationRef.current !== currentGeneration ||
          sessionIdRef.current !== currentSessionId
        ) {
          return
        }
        setConnectionState(nextState)
      },
    })

    channel.connect()
    channelRef.current = channel

    return () => {
      channel.destroy()
      if (channelRef.current === channel) {
        channelRef.current = null
      }
      if (
        sessionGenerationRef.current === currentGeneration &&
        sessionIdRef.current === currentSessionId
      ) {
        receivedTerminalRef.current = false
      }
    }
  }, [resetStartedSets, session])

  const sendMessage = useCallback((text: string) => {
    const trimmed = text.trim()
    if (!trimmed || state.sessionEnded) {
      return false
    }

    const sent = channelRef.current?.sendMessage(trimmed) ?? false
    if (!sent) {
      return false
    }

    dispatch({
      type: "USER_SENT",
      id: `user-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      text: trimmed,
    })
    return true
  }, [state.sessionEnded])

  const interrupt = useCallback(() => channelRef.current?.interrupt() ?? false, [])

  const cancel = useCallback(() => {
    channelRef.current?.cancel()
  }, [])

  const controller = useMemo<StreamController>(
    () => ({ sendMessage, interrupt, cancel }),
    [cancel, interrupt, sendMessage],
  )

  return {
    entries: state.entries,
    currentActivity: state.current?.activity ?? null,
    capabilities,
    channel: channelRef,
    connectionState,
    controller,
    isStreaming: Boolean(state.current?.activity.isStreaming),
    sessionEnded: state.sessionEnded,
    cancel,
    interrupt,
  }
}
