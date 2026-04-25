/**
 * Transform REST history events into ConversationEntry[].
 *
 * Strategy: replay AG-UI events through the same reducer pipeline used for
 * live streaming. This guarantees that history and live content produce
 * identical ActivityBlockData structures — tool calls, thinking blocks,
 * and text content are all faithfully reconstructed.
 *
 * Turn boundaries:
 *   1. `user_message` events → UserEntry
 *   2. `RUN_STARTED` / `RUN_FINISHED` → assistant turn boundaries
 *   3. If neither lifecycle event exists, user messages act as implicit
 *      turn boundaries (backward compat with older chat formats).
 */

import type { ChatHistoryEvent } from "@/features/sessions/lib/api"
import type { ConversationEntry } from "../conversation-types"
import {
  conversationReducer,
  createInitialConversationState,
  type ConversationState,
} from "../conversation-reducer"
import {
  mapHistoryEventToStreamEvents,
  createStartedSets,
} from "./map-history-event"

/**
 * Convert a `getChatHistory` event array into frozen ConversationEntry[].
 *
 * The transform works by:
 * 1. Walking events in sequence order
 * 2. Detecting user messages (via `user_message` type or `TEXT_MESSAGE_START`
 *    with role="user") and emitting UserEntry actions
 * 3. Mapping all AG-UI events through `mapHistoryEventToStreamEvents` and
 *    feeding the resulting StreamEvents into the `conversationReducer`
 * 4. After all events are processed, dispatching SESSION_ENDED to freeze
 *    any remaining streaming state
 */
export function transformHistoryToEntries(
  events: ChatHistoryEvent[],
): ConversationEntry[] {
  if (events.length === 0) return []

  const started = createStartedSets()
  let state: ConversationState = createInitialConversationState()

  for (const evt of events) {
    const data = evt.data as Record<string, unknown> | undefined

    // Handle user messages — these become UserEntry turns.
    // Freeze any accumulated assistant state first so user messages act as
    // implicit turn boundaries for legacy histories missing RUN_STARTED/RUN_FINISHED.
    if (evt.type === "user_message") {
      if (state.current !== null) {
        state = conversationReducer(state, { type: "SESSION_ENDED" })
      }
      const text = String(data?.content ?? data?.text ?? "")
      if (text) {
        state = conversationReducer(state, {
          type: "USER_SENT",
          id: `hist-user-${evt.seq}`,
          text,
        })
      }
      continue
    }

    // Handle TEXT_MESSAGE_START with role="user" — also a user message
    if (evt.type === "TEXT_MESSAGE_START") {
      const role = data?.role as string | undefined
      if (role === "user") {
        if (state.current !== null) {
          state = conversationReducer(state, { type: "SESSION_ENDED" })
        }
        const text = String(data?.content ?? data?.text ?? "")
        if (text) {
          state = conversationReducer(state, {
            type: "USER_SENT",
            id: `hist-user-${evt.seq}`,
            text,
          })
        }
        continue
      }
    }

    // Map to StreamEvents and feed through the reducer
    const streamEvents = mapHistoryEventToStreamEvents(evt, started)
    for (const streamEvent of streamEvents) {
      state = conversationReducer(state, {
        type: "STREAM_EVENT",
        event: streamEvent,
      })
    }
  }

  // Freeze any remaining in-flight assistant turn
  if (state.current !== null) {
    state = conversationReducer(state, { type: "SESSION_ENDED" })
  }

  return state.entries
}
