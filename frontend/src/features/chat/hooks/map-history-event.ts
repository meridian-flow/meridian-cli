/**
 * Map REST history events to StreamEvents for the activity stream reducer.
 *
 * History events arrive as `{ seq, type, data, timestamp }` envelopes from
 * `getChatHistory`. The `type` field is an AG-UI event type string, and
 * `data` contains the event payload. This mapper unwraps the envelope and
 * produces the same `StreamEvent[]` that `mapWsEventToStreamEvents` would
 * produce from a live WebSocket frame.
 *
 * Uses the same deduplication pattern (started sets) as the WS mapper so
 * replaying history produces identical reducer output to live streaming.
 */

import type { ChatHistoryEvent } from "@/lib/api"
import type { StreamEvent } from "@/features/activity-stream/streaming/events"

export type StartedSets = {
  text: Set<string>
  thinking: Set<string>
  tool: Set<string>
}

export function createStartedSets(): StartedSets {
  return {
    text: new Set(),
    thinking: new Set(),
    tool: new Set(),
  }
}

/**
 * Map a single ChatHistoryEvent to zero or more StreamEvents.
 *
 * The history event `data` payload mirrors the WS event fields — messageId,
 * delta, toolCallId, toolCallName, etc. — so we extract them the same way
 * `mapWsEventToStreamEvents` does but from the `data` object instead of a
 * typed WS event.
 */
export function mapHistoryEventToStreamEvents(
  event: ChatHistoryEvent,
  started: StartedSets,
): StreamEvent[] {
  const data = event.data as Record<string, unknown> | undefined
  const mapped: StreamEvent[] = []

  switch (event.type) {
    // -----------------------------------------------------------------
    // Run lifecycle
    // -----------------------------------------------------------------
    case "RUN_STARTED":
      mapped.push({ type: "RUN_STARTED" })
      break

    case "RUN_FINISHED":
      mapped.push({ type: "RUN_FINISHED" })
      break

    case "RUN_ERROR": {
      const message = String(data?.message ?? "Unknown error")
      const code = data?.code as string | undefined
      const isCancelled =
        code === "cancelled" ||
        code === "canceled" ||
        /cancelled|canceled/i.test(message)
      mapped.push({ type: "RUN_ERROR", message, isCancelled })
      break
    }

    // -----------------------------------------------------------------
    // Text messages
    // -----------------------------------------------------------------
    case "TEXT_MESSAGE_START": {
      const messageId = String(data?.messageId ?? `hist-text-${event.seq}`)
      if (!started.text.has(messageId)) {
        started.text.add(messageId)
        mapped.push({ type: "TEXT_MESSAGE_START", messageId })
      }
      break
    }

    case "TEXT_MESSAGE_CONTENT": {
      const messageId = String(data?.messageId ?? `hist-text-${event.seq}`)
      const delta = String(data?.delta ?? data?.text ?? "")
      if (!started.text.has(messageId)) {
        started.text.add(messageId)
        mapped.push({ type: "TEXT_MESSAGE_START", messageId })
      }
      if (delta) {
        mapped.push({ type: "TEXT_MESSAGE_CONTENT", messageId, delta })
      }
      break
    }

    case "TEXT_MESSAGE_END": {
      const messageId = String(data?.messageId ?? `hist-text-${event.seq}`)
      if (started.text.has(messageId)) {
        mapped.push({ type: "TEXT_MESSAGE_END", messageId })
      }
      break
    }

    case "TEXT_MESSAGE_CHUNK": {
      const messageId = data?.messageId as string | undefined
      if (!messageId) break
      const delta = data?.delta as string | undefined
      if (!started.text.has(messageId)) {
        started.text.add(messageId)
        mapped.push({ type: "TEXT_MESSAGE_START", messageId })
      }
      if (delta) {
        mapped.push({ type: "TEXT_MESSAGE_CONTENT", messageId, delta })
      }
      break
    }

    // -----------------------------------------------------------------
    // Reasoning / thinking
    // -----------------------------------------------------------------
    case "REASONING_START":
    case "REASONING_MESSAGE_START": {
      const messageId = String(data?.messageId ?? `hist-think-${event.seq}`)
      if (!started.thinking.has(messageId)) {
        started.thinking.add(messageId)
        mapped.push({ type: "THINKING_START", thinkingId: messageId })
        mapped.push({ type: "THINKING_TEXT_MESSAGE_START", thinkingId: messageId })
      }
      break
    }

    case "REASONING_MESSAGE_CONTENT": {
      const messageId = String(data?.messageId ?? `hist-think-${event.seq}`)
      const delta = String(data?.delta ?? "")
      if (!started.thinking.has(messageId)) {
        started.thinking.add(messageId)
        mapped.push({ type: "THINKING_START", thinkingId: messageId })
        mapped.push({ type: "THINKING_TEXT_MESSAGE_START", thinkingId: messageId })
      }
      if (delta) {
        mapped.push({ type: "THINKING_TEXT_MESSAGE_CONTENT", thinkingId: messageId, delta })
      }
      break
    }

    case "REASONING_MESSAGE_CHUNK": {
      const messageId = data?.messageId as string | undefined
      if (!messageId) break
      const delta = data?.delta as string | undefined
      if (!started.thinking.has(messageId)) {
        started.thinking.add(messageId)
        mapped.push({ type: "THINKING_START", thinkingId: messageId })
        mapped.push({ type: "THINKING_TEXT_MESSAGE_START", thinkingId: messageId })
      }
      if (delta) {
        mapped.push({ type: "THINKING_TEXT_MESSAGE_CONTENT", thinkingId: messageId, delta })
      }
      break
    }

    case "REASONING_END":
    case "REASONING_MESSAGE_END": {
      const messageId = String(data?.messageId ?? `hist-think-${event.seq}`)
      if (started.thinking.has(messageId)) {
        mapped.push({ type: "THINKING_TEXT_MESSAGE_END", thinkingId: messageId })
      }
      break
    }

    // -----------------------------------------------------------------
    // Tool calls
    // -----------------------------------------------------------------
    case "TOOL_CALL_START": {
      const toolCallId = String(data?.toolCallId ?? `hist-tool-${event.seq}`)
      const toolCallName = String(data?.toolCallName ?? "Tool")
      if (!started.tool.has(toolCallId)) {
        started.tool.add(toolCallId)
        mapped.push({ type: "TOOL_CALL_START", toolCallId, toolCallName })
      }
      break
    }

    case "TOOL_CALL_ARGS": {
      const toolCallId = String(data?.toolCallId ?? `hist-tool-${event.seq}`)
      const delta = String(data?.delta ?? "")
      if (!started.tool.has(toolCallId)) {
        started.tool.add(toolCallId)
        mapped.push({ type: "TOOL_CALL_START", toolCallId, toolCallName: "Tool" })
      }
      if (delta) {
        mapped.push({ type: "TOOL_CALL_ARGS", toolCallId, delta })
      }
      break
    }

    case "TOOL_CALL_CHUNK": {
      const toolCallId = data?.toolCallId as string | undefined
      if (!toolCallId) break
      const toolCallName = (data?.toolCallName as string) ?? "Tool"
      const delta = data?.delta as string | undefined
      if (!started.tool.has(toolCallId)) {
        started.tool.add(toolCallId)
        mapped.push({ type: "TOOL_CALL_START", toolCallId, toolCallName })
      }
      if (delta) {
        mapped.push({ type: "TOOL_CALL_ARGS", toolCallId, delta })
      }
      break
    }

    case "TOOL_CALL_END": {
      const toolCallId = String(data?.toolCallId ?? `hist-tool-${event.seq}`)
      if (started.tool.has(toolCallId)) {
        mapped.push({ type: "TOOL_CALL_END", toolCallId })
      }
      break
    }

    case "TOOL_CALL_RESULT": {
      const toolCallId = String(data?.toolCallId ?? `hist-tool-${event.seq}`)
      const content = String(data?.content ?? "")
      if (!started.tool.has(toolCallId)) {
        started.tool.add(toolCallId)
        mapped.push({ type: "TOOL_CALL_START", toolCallId, toolCallName: "Tool" })
      }
      mapped.push({ type: "TOOL_CALL_RESULT", toolCallId, content })
      break
    }

    // -----------------------------------------------------------------
    // Steps
    // -----------------------------------------------------------------
    case "STEP_FINISHED":
      mapped.push({ type: "RUN_FINISHED" })
      break

    // -----------------------------------------------------------------
    // Legacy / backward-compat event types
    //
    // Older chats may have `user_message` / `assistant_message` events
    // that don't map to AG-UI. We handle user_message here (creates a
    // synthetic user entry signal). assistant_message is skipped — its
    // content should already be covered by TEXT_MESSAGE_* events.
    // -----------------------------------------------------------------
    case "user_message":
      // Handled in transformHistoryToEntries as a turn boundary — skip here
      break

    case "assistant_message":
      // Legacy format — content already covered by TEXT_MESSAGE_* events
      // in newer history. Ignored to avoid double-rendering.
      break

    default:
      // Unknown event type — skip silently
      break
  }

  return mapped
}
