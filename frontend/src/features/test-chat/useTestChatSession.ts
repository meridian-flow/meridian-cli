import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import {
  EventType,
  SpawnChannel,
  type ConnectionCapabilities,
  type StreamEvent as WsStreamEvent,
  type WsState,
} from "@/lib/ws"
import {
  createInitialState,
  reduceStreamEvent,
  type StreamState,
} from "@/features/activity-stream/streaming/reducer"
import { mapWsEventToStreamEvents } from "@/features/activity-stream/streaming/map-ws-event"
import type { StreamEvent } from "@/features/activity-stream/streaming/events"
import type { ActivityBlockData } from "@/features/activity-stream/types"
import type { StreamController } from "@/features/threads/transport-types"

import type { TestChatSessionInfo } from "./session-api"

type AssistantStatus = "streaming" | "complete" | "cancelled" | "error"

export type UserEntry = {
  kind: "user"
  id: string
  text: string
  sentAt: Date
}

export type AssistantEntry = {
  kind: "assistant"
  id: string
  activity: ActivityBlockData
  status: AssistantStatus
}

export type ConversationEntry = UserEntry | AssistantEntry

type ConversationState = {
  entries: ConversationEntry[]
  current: StreamState | null
  turnSeq: number
  sessionEnded: boolean
}

type ConversationAction =
  | { type: "USER_SENT"; text: string; id: string }
  | { type: "STREAM_EVENT"; event: StreamEvent }
  | { type: "SESSION_ENDED" }
  | { type: "RESET" }

function createAssistantState(seq: number) {
  return createInitialState(`assistant-${seq}`)
}

function activityHasContent(activity: ActivityBlockData) {
  return (
    activity.items.length > 0 ||
    Boolean(activity.pendingText) ||
    Boolean(activity.error) ||
    Boolean(activity.isCancelled)
  )
}

function freezeAssistant(current: StreamState, status: AssistantStatus): AssistantEntry | null {
  const activity = {
    ...current.activity,
    isStreaming: false,
    pendingText: undefined,
  }

  if (!activityHasContent(activity)) {
    return null
  }

  return {
    kind: "assistant",
    id: activity.id,
    activity,
    status,
  }
}

function appendFrozen(
  entries: ConversationEntry[],
  current: StreamState | null,
  status: AssistantStatus,
) {
  if (current === null) {
    return entries
  }

  const frozen = freezeAssistant(current, status)
  return frozen ? [...entries, frozen] : entries
}

function conversationReducer(
  state: ConversationState,
  action: ConversationAction,
): ConversationState {
  switch (action.type) {
    case "RESET":
      return { entries: [], current: null, turnSeq: 0, sessionEnded: false }

    case "USER_SENT":
      return {
        ...state,
        entries: [
          ...state.entries,
          {
            kind: "user",
            id: action.id,
            text: action.text,
            sentAt: new Date(),
          },
        ],
      }

    case "STREAM_EVENT": {
      if (action.event.type === "RUN_STARTED") {
        const entries = appendFrozen(state.entries, state.current, "complete")
        const turnSeq = state.turnSeq + 1
        const current = reduceStreamEvent(createAssistantState(turnSeq), action.event)
        return { ...state, entries, current, turnSeq }
      }

      if (action.event.type === "RUN_FINISHED") {
        const current = state.current
          ? reduceStreamEvent(state.current, action.event)
          : reduceStreamEvent(createAssistantState(state.turnSeq + 1), action.event)

        return {
          ...state,
          entries: appendFrozen(state.entries, current, "complete"),
          current: null,
          turnSeq: state.current ? state.turnSeq : state.turnSeq + 1,
        }
      }

      if (action.event.type === "RUN_ERROR") {
        const current = state.current
          ? reduceStreamEvent(state.current, action.event)
          : reduceStreamEvent(createAssistantState(state.turnSeq + 1), action.event)

        return {
          ...state,
          entries: appendFrozen(
            state.entries,
            current,
            action.event.isCancelled ? "cancelled" : "error",
          ),
          current: null,
          turnSeq: state.current ? state.turnSeq : state.turnSeq + 1,
        }
      }

      const current = state.current ?? reduceStreamEvent(
        createAssistantState(state.turnSeq + 1),
        { type: "RUN_STARTED" },
      )
      return {
        ...state,
        current: reduceStreamEvent(current, action.event),
        turnSeq: state.current ? state.turnSeq : state.turnSeq + 1,
      }
    }

    case "SESSION_ENDED":
      return {
        ...state,
        entries: appendFrozen(state.entries, state.current, "complete"),
        current: null,
        sessionEnded: true,
      }

    default:
      return state
  }
}

export function useTestChatSession(session: TestChatSessionInfo | null) {
  const [state, dispatch] = useReducer(conversationReducer, {
    entries: [],
    current: null,
    turnSeq: 0,
    sessionEnded: false,
  })
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
