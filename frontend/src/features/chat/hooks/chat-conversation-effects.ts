/**
 * Chat conversation effect runner — executes commands emitted by the
 * state machine reducer.
 *
 * Pure bridge between the reducer's command model and actual I/O:
 * REST API calls, WebSocket lifecycle, and replay fetching. Every
 * async callback is generation-guarded to prevent stale dispatches.
 *
 * The runner owns a single SpawnChannel ref. On `connectSpawn` it
 * tears down any prior channel and creates a new one. On
 * `disconnectSpawn` it destroys the current channel.
 */

import { useCallback, useRef } from "react"

import {
  EventType,
  SpawnChannel,
  type StreamEvent as WsStreamEvent,
} from "@/lib/ws"
import { mapWsEventToStreamEvents } from "@/features/activity-stream/streaming/map-ws-event"
import type { StartedEventSets } from "@/features/activity-stream/streaming/map-ws-event"

import {
  createChat,
  getChat,
  getChatHistory,
  promptChat,
  cancelChat,
  fetchSpawnReplay,
  type ChatDetailResponse,
  type CreateChatOptions,
} from "@/lib/api"
import { transformHistoryToEntries } from "./transform-history"

import type {
  ChatCommand,
  ChatEvent,
} from "./chat-conversation-types"

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════

export interface EffectRunnerCallbacks {
  onChatCreated?: (detail: ChatDetailResponse) => void
}

export interface EffectRunnerOptions {
  createChatOptions?: CreateChatOptions
  callbacks?: EffectRunnerCallbacks
  /** When false, external callbacks (onChatCreated) are suppressed. */
  isActiveRef?: { current: boolean }
}

export interface EffectRunnerHandle {
  /** Execute a batch of commands from a single reducer transition. */
  executeCommands: (commands: ChatCommand[]) => void

  /** Get the current SpawnChannel (for StreamController delegation). */
  getChannel: () => SpawnChannel | null

  /** Tear down all resources (WS, pending fetches). Dispatches WS_CLOSED. */
  destroy: () => void

  /**
   * Tear down all resources WITHOUT dispatching any events.
   * Used during deactivation to freeze state — the channel is destroyed
   * but the machine context remains untouched.
   */
  destroySilently: () => void
}

// ═══════════════════════════════════════════════════════════════════
// Hook
// ═══════════════════════════════════════════════════════════════════

/**
 * Effect runner hook — manages side effects for the chat state machine.
 *
 * Accepts a stable `dispatch` function (from the machine wrapper) and
 * option refs. Returns a handle with `executeCommands` and resource
 * management methods.
 *
 * The dispatch function is expected to be stable (wrapped in useRef
 * or useCallback with no deps). Options are read via refs so the
 * effect runner never goes stale.
 */
export function useEffectRunner(
  dispatch: (event: ChatEvent) => void,
  options: EffectRunnerOptions,
): EffectRunnerHandle {
  // ---- Refs for mutable state ----
  const channelRef = useRef<SpawnChannel | null>(null)
  const startedSetsRef = useRef<StartedEventSets>(freshStartedSets())
  const dispatchRef = useRef(dispatch)
  dispatchRef.current = dispatch

  // ---- Generation tracking (gate external callbacks on staleness) ----
  const currentCreateGenerationRef = useRef(0)

  // ---- Options refs (avoid stale closures) ----
  const optionsRef = useRef(options)
  optionsRef.current = options

  // ---- Helpers ----

  function emit(event: ChatEvent) {
    dispatchRef.current(event)
  }

  function destroyChannel() {
    channelRef.current?.destroy()
    channelRef.current = null
    startedSetsRef.current = freshStartedSets()
  }

  /**
   * Tear down the channel without triggering any event dispatch.
   * Temporarily replaces the dispatch ref with a no-op so that
   * synchronous onClose callbacks from channel.destroy() are silenced.
   */
  function destroyChannelSilently() {
    const savedDispatch = dispatchRef.current
    dispatchRef.current = () => {} // swallow all events during teardown
    try {
      channelRef.current?.destroy()
    } finally {
      dispatchRef.current = savedDispatch
    }
    channelRef.current = null
    startedSetsRef.current = freshStartedSets()
  }

  // ---- Command executors ----

  function executeFetchDetail(chatId: string, generation: number) {
    getChat(chatId)
      .then((detail) => {
        emit({ type: "DETAIL_LOADED", detail, generation })
      })
      .catch((err) => {
        emit({
          type: "DETAIL_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executeFetchHistory(chatId: string, generation: number) {
    getChatHistory(chatId)
      .then((response) => {
        const entries = transformHistoryToEntries(response.events)
        emit({ type: "HISTORY_LOADED", entries, generation })
      })
      .catch((err) => {
        emit({
          type: "HISTORY_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executeCreateChat(prompt: string, generation: number) {
    currentCreateGenerationRef.current = generation
    const createOpts = optionsRef.current.createChatOptions
    createChat(prompt, createOpts)
      .then((detail) => {
        emit({ type: "CREATE_SUCCEEDED", detail, generation })
        // Gate callback on generation AND isActive — a newer create may have
        // superseded this one, or the shell may have gone dormant (#109).
        if (generation === currentCreateGenerationRef.current) {
          const isActive = optionsRef.current.isActiveRef?.current ?? true
          if (isActive) {
            optionsRef.current.callbacks?.onChatCreated?.(detail)
          }
        }
      })
      .catch((err) => {
        emit({
          type: "CREATE_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executePromptChat(chatId: string, text: string, generation: number) {
    promptChat(chatId, text)
      .then((detail) => {
        emit({ type: "PROMPT_SUCCEEDED", detail, generation })
      })
      .catch((err) => {
        emit({
          type: "PROMPT_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executeContinueChat(chatId: string, text: string, generation: number) {
    currentCreateGenerationRef.current = generation
    // Continue uses promptChat — the backend handles re-activation.
    // When a dedicated continue endpoint exists, swap this call.
    promptChat(chatId, text)
      .then((detail) => {
        emit({ type: "CONTINUE_SUCCEEDED", detail, generation })
      })
      .catch((err) => {
        emit({
          type: "CONTINUE_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executeCancelChat(chatId: string, generation: number) {
    cancelChat(chatId)
      .then(() => {
        emit({ type: "CANCEL_SUCCEEDED", generation })
      })
      .catch((err) => {
        emit({
          type: "CANCEL_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executeConnectSpawn(
    spawnId: string,
    replay: boolean,
    generation: number,
  ) {
    // Clean handoff: capture the old channel and wire up the new one
    // BEFORE destroying the old. This prevents a race where the old
    // channel's synchronous onClose callback (fired during destroy)
    // could interfere with state between teardown and creation. The
    // old channel's callbacks capture a stale generation, so any
    // events they emit are harmlessly dropped by the reducer.
    const oldChannel = channelRef.current
    channelRef.current = null

    // Fresh dedup sets for the new connection
    startedSetsRef.current = freshStartedSets()

    const channel = new SpawnChannel(
      spawnId,
      {
        onEvent: (event: WsStreamEvent) => {
          // Skip capabilities events — they're protocol-level, not conversation
          if (
            event.type === EventType.CUSTOM &&
            (event as { name: string }).name === "capabilities"
          ) {
            return
          }

          for (const mapped of mapWsEventToStreamEvents(
            event,
            startedSetsRef.current,
          )) {
            emit({ type: "STREAM_EVENT", event: mapped, generation })
          }
        },
        onClose: () => {
          emit({ type: "WS_CLOSED", generation })
        },
        onStateChange: (state) => {
          if (state === "open") {
            emit({ type: "WS_OPENED", generation })
          }
        },
      },
      replay ? { queryParams: { replay: "1" } } : {},
    )

    channel.connect()
    channelRef.current = channel

    // Tear down old channel AFTER new one is wired up
    oldChannel?.destroy()
  }

  function executeFetchReplay(spawnId: string, generation: number) {
    // Capture the channel at call time — if it's replaced before the fetch
    // resolves, we must not ack on the new channel.
    const capturedChannel = channelRef.current

    fetchSpawnReplay(spawnId)
      .then((snapshot) => {
        const entries = transformHistoryToEntries(snapshot.events)

        // Interleave inbound user messages (EARS-R012)
        if (snapshot.inbound.length > 0) {
          const entriesWithInbound = interleaveInbound(entries, snapshot.inbound)
          emit({
            type: "REPLAY_SUCCEEDED",
            entries: entriesWithInbound,
            cursor: snapshot.cursor,
            generation,
          })
        } else {
          emit({
            type: "REPLAY_SUCCEEDED",
            entries,
            cursor: snapshot.cursor,
            generation,
          })
        }

        // Send replay ack to unblock WS (EARS-R011 step 4)
        // Only ack if the channel hasn't been replaced since fetch started
        if (capturedChannel && channelRef.current === capturedChannel) {
          capturedChannel.sendReplayAck(snapshot.cursor)
        }
      })
      .catch((err) => {
        console.warn("Replay fetch failed, falling back to live-only:", err)
        emit({
          type: "REPLAY_FAILED",
          error: err instanceof Error ? err.message : String(err),
          generation,
        })
      })
  }

  function executeDisconnectSpawn(_generation: number) {
    destroyChannel()
  }

  // ---- Main executor ----

  const executeCommands = useCallback((commands: ChatCommand[]) => {
    for (const cmd of commands) {
      switch (cmd.type) {
        case "fetchDetail":
          executeFetchDetail(cmd.chatId, cmd.generation)
          break
        case "fetchHistory":
          executeFetchHistory(cmd.chatId, cmd.generation)
          break
        case "createChat":
          executeCreateChat(cmd.prompt, cmd.generation)
          break
        case "promptChat":
          executePromptChat(cmd.chatId, cmd.text, cmd.generation)
          break
        case "continueChat":
          executeContinueChat(cmd.chatId, cmd.text, cmd.generation)
          break
        case "cancelChat":
          executeCancelChat(cmd.chatId, cmd.generation)
          break
        case "connectSpawn":
          executeConnectSpawn(cmd.spawnId, cmd.replay, cmd.generation)
          break
        case "fetchReplay":
          executeFetchReplay(cmd.spawnId, cmd.generation)
          break
        case "disconnectSpawn":
          executeDisconnectSpawn(cmd.generation)
          break
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const getChannel = useCallback(() => channelRef.current, [])

  const destroy = useCallback(() => {
    destroyChannel()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const destroySilently = useCallback(() => {
    destroyChannelSilently()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { executeCommands, getChannel, destroy, destroySilently }
}

// ═══════════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════════

function freshStartedSets(): StartedEventSets {
  return {
    text: new Set<string>(),
    thinking: new Set<string>(),
    tool: new Set<string>(),
  }
}

/**
 * Interleave inbound user messages into the replay entries.
 * K-th inbound entry is inserted before K-th assistant turn.
 */
function interleaveInbound(
  entries: import("../conversation-types").ConversationEntry[],
  inbound: import("@/lib/api").SpawnInboundMessage[],
): import("../conversation-types").ConversationEntry[] {
  const result: import("../conversation-types").ConversationEntry[] = []
  let inboundIdx = 0

  for (const entry of entries) {
    if (entry.kind === "assistant" && inboundIdx < inbound.length) {
      const msg = inbound[inboundIdx]
      result.push({
        kind: "user",
        id: `replay-user-${msg.seq}`,
        text: msg.text,
        sentAt: new Date(msg.ts * 1000),
      })
      inboundIdx++
    }
    result.push(entry)
  }

  // Append any remaining inbound messages
  while (inboundIdx < inbound.length) {
    const msg = inbound[inboundIdx]
    result.push({
      kind: "user",
      id: `replay-user-${msg.seq}`,
      text: msg.text,
      sentAt: new Date(msg.ts * 1000),
    })
    inboundIdx++
  }

  return result
}
