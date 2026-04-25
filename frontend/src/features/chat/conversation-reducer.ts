/**
 * Conversation reducer — manages the sequence of user/assistant turns.
 *
 * Extracted from test-chat/useTestChatSession so both test-chat and the
 * main chat feature can share the same turn-management logic.
 *
 * Pure functions only — no React hooks or side effects.
 */

import type { ActivityBlockData } from "@/features/activity-stream/types"
import {
  createInitialState,
  reduceStreamEvent,
  type StreamState,
} from "@/features/activity-stream/streaming/reducer"
import type { StreamEvent } from "@/features/activity-stream/streaming/events"
import type {
  AssistantStatus,
  AssistantEntry,
  ConversationEntry,
} from "./conversation-types"

// ═══════════════════════════════════════════════════════════════════
// State & Action types
// ═══════════════════════════════════════════════════════════════════

export type ConversationState = {
  entries: ConversationEntry[]
  current: StreamState | null
  turnSeq: number
  sessionEnded: boolean
}

export type ConversationAction =
  | { type: "USER_SENT"; text: string; id: string }
  | { type: "STREAM_EVENT"; event: StreamEvent }
  | { type: "SESSION_ENDED" }
  | { type: "RESET" }

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

export function createAssistantState(seq: number) {
  return createInitialState(`assistant-${seq}`)
}

export function activityHasContent(activity: ActivityBlockData) {
  return (
    activity.items.length > 0 ||
    Boolean(activity.pendingText) ||
    Boolean(activity.error) ||
    Boolean(activity.isCancelled)
  )
}

export function freezeAssistant(current: StreamState, status: AssistantStatus): AssistantEntry | null {
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

export function appendFrozen(
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

// ═══════════════════════════════════════════════════════════════════
// Initial state
// ═══════════════════════════════════════════════════════════════════

export function createInitialConversationState(): ConversationState {
  return { entries: [], current: null, turnSeq: 0, sessionEnded: false }
}

// ═══════════════════════════════════════════════════════════════════
// Reducer
// ═══════════════════════════════════════════════════════════════════

export function conversationReducer(
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
