/**
 * useChatConversation — unified hook for chat conversation state.
 *
 * Wires the pure chat state machine (chat-conversation-machine.ts) to
 * the effect runner (chat-conversation-effects.ts), producing the same
 * return contract that ChatThreadView consumes.
 *
 * Architecture:
 * 1. useReducer holds the ChatMachineContext
 * 2. A wrapper reducer captures emitted commands in a ref
 * 3. A post-dispatch effect flushes captured commands to the effect runner
 * 4. The effect runner executes I/O and dispatches response events back
 *
 * This replaces the original ad-hoc useEffect/useState approach with an
 * explicit phase machine and command model.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef } from "react"

import type { WsState } from "@/lib/ws"
import type { StreamController } from "../transport-types"
import type { ConversationEntry } from "../conversation-types"
import type { ActivityBlockData } from "@/features/activity-stream/types"
import type {
  ChatState as ApiChatState,
  ChatDetailResponse,
  CreateChatOptions,
} from "@/lib/api"

import {
  chatMachineReducer,
  createInitialMachineContext,
  deriveChatState,
} from "./chat-conversation-machine"
import type {
  ChatCommand,
  ChatEvent,
  ChatMachineContext,
  ChatCacheSnapshot,
  TransitionResult,
} from "./chat-conversation-types"
import { useEffectRunner } from "./chat-conversation-effects"
import { chatCacheStore } from "../chat-cache-store"
import type { VirtuosoState } from "../chat-cache-store"

// ---------------------------------------------------------------------------
// Types (public contract — unchanged from the original hook)
// ---------------------------------------------------------------------------

export interface UseChatConversationOptions {
  chatId: string
  isActive?: boolean // Default true — when false, all side effects are suppressed
  initialPrompt?: string | null
  createChatOptions?: CreateChatOptions
  onChatCreated?: (detail: ChatDetailResponse) => void
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
  activeSpawnId: string | null
  error: string | null
  sendMessage: (text: string) => Promise<void>
  cancel: () => Promise<void>
  /** Cached virtualizer snapshot for scroll restoration. */
  virtualizerState: VirtuosoState | null
  /** Save virtualizer state back into the cache (called from ConversationView). */
  saveVirtualizerState: (state: VirtuosoState) => void
}

// ---------------------------------------------------------------------------
// Wrapper reducer — captures commands in a ref for the effect runner
// ---------------------------------------------------------------------------

/**
 * We can't execute side effects inside a reducer, so we wrap the
 * machine reducer to stash emitted commands in a mutable ref. The
 * hook reads and flushes this ref after each dispatch via useEffect.
 */
type CommandSink = { current: ChatCommand[] }

function createWrappedReducer(commandSink: CommandSink) {
  return function wrappedReducer(
    ctx: ChatMachineContext,
    event: ChatEvent,
  ): ChatMachineContext {
    const result: TransitionResult = chatMachineReducer(ctx, event)
    // Append commands — multiple dispatches in a single render batch
    // accumulate into the same array, flushed once in useEffect.
    if (result.commands.length > 0) {
      commandSink.current = [...commandSink.current, ...result.commands]
    }
    return result.context
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useChatConversation({
  chatId,
  isActive = true,
  initialPrompt,
  createChatOptions,
  onChatCreated,
}: UseChatConversationOptions): UseChatConversationReturn {
  // ---- Command capture ----
  // Stable ref survives re-renders; the wrapped reducer appends here.
  const commandSinkRef = useRef<ChatCommand[]>([])
  const wrappedReducer = useMemo(
    () => createWrappedReducer(commandSinkRef),
    [],
  )

  const [ctx, rawDispatch] = useReducer(wrappedReducer, undefined, createInitialMachineContext)

  // ---- Stable callback refs ----
  const onChatCreatedRef = useRef(onChatCreated)
  onChatCreatedRef.current = onChatCreated

  // ---- Inactive dispatch gate ----
  // When inactive, async callbacks (WS onClose, fetch .then) must not
  // mutate the machine context. We gate dispatch through a ref that
  // checks isActive before forwarding. This ensures state is truly
  // frozen while the conversation is dormant.
  const isActiveRef = useRef(isActive)
  isActiveRef.current = isActive

  const gatedDispatch = useCallback(
    (event: ChatEvent) => {
      if (!isActiveRef.current) return // Drop events while inactive
      rawDispatch(event)
    },
    [rawDispatch],
  )

  // ---- Effect runner ----
  // Uses gatedDispatch so async callbacks from destroyed channels
  // (WS_CLOSED, in-flight fetch responses) are silently dropped
  // when the conversation is inactive.
  const effectRunner = useEffectRunner(gatedDispatch, {
    createChatOptions,
    callbacks: {
      onChatCreated: (detail) => onChatCreatedRef.current?.(detail),
    },
  })

  // ---- Active state transitions (deactivation + reactivation) ----
  // Single effect handles both directions to avoid split-ref races.
  const wasActiveRef = useRef(isActive)
  const didReactivate = useRef(false)

  useEffect(() => {
    const wasActive = wasActiveRef.current
    wasActiveRef.current = isActive

    if (wasActive && !isActive) {
      // Active → inactive: tear down WS silently (no WS_CLOSED dispatch),
      // drop queued commands. Machine context stays frozen.
      commandSinkRef.current = []
      effectRunner.destroySilently()
    } else if (!wasActive && isActive) {
      // Inactive → active: flag reactivation so the chat-selection effect
      // re-bootstraps (fetch detail, reconnect WS, etc.).
      // Skip on initial mount — the chat-selection effect handles that.
      didReactivate.current = true
    }
  }, [isActive, effectRunner])

  // ---- Flush commands after each render that produced them ----
  // useEffect runs after React commits the state update, so ctx is
  // consistent with the commands being flushed.
  useEffect(() => {
    if (!isActive) {
      // Inactive: silently discard any commands the reducer emitted.
      commandSinkRef.current = []
      return
    }
    const commands = commandSinkRef.current
    if (commands.length === 0) return
    commandSinkRef.current = []
    effectRunner.executeCommands(commands)
  })

  // -----------------------------------------------------------------------
  // Chat selection — translate external chatId into machine events
  // -----------------------------------------------------------------------

  const prevChatIdRef = useRef<string | null>(null)
  const didMount = useRef(false)

  /** Build a ChatCacheSnapshot from a cache entry, or return undefined. */
  const buildCacheSnapshot = useCallback(
    (id: string): ChatCacheSnapshot | undefined => {
      const cached = chatCacheStore.get(id)
      if (!cached) return undefined
      const mc = cached.machineContext
      if (!mc.chatDetail || !mc.chatState) return undefined
      return {
        chatId: cached.chatId,
        chatDetail: mc.chatDetail,
        chatState: mc.chatState,
        entries: mc.entries,
        turnSeq: mc.turnSeq,
        activeSpawnId: mc.activeSpawnId,
        isTerminal:
          mc.phase === "finished" ||
          mc.phase === "readonly",
      }
    },
    [],
  )

  useEffect(() => {
    if (!isActive) return // Suppress selection while dormant

    if (!didMount.current || didReactivate.current) {
      // First mount OR reactivation — fire the initial selection event
      didMount.current = true
      didReactivate.current = false
      prevChatIdRef.current = chatId

      if (chatId === "__new__") {
        chatCacheStore.setActive(null)
        rawDispatch({ type: "SELECT_ZERO" })
      } else {
        chatCacheStore.setActive(chatId)
        const snapshot = buildCacheSnapshot(chatId)
        rawDispatch({ type: "SELECT_CHAT", chatId, cached: snapshot })
      }
      return
    }

    // Subsequent chatId changes
    if (prevChatIdRef.current === chatId) return
    const wasNew = prevChatIdRef.current === "__new__"
    prevChatIdRef.current = chatId

    // Transition from __new__ → real ID means the create succeeded and
    // the machine already has the right state. Don't re-select.
    if (wasNew && chatId !== "__new__") {
      chatCacheStore.setActive(chatId)
      return
    }

    if (chatId === "__new__") {
      chatCacheStore.setActive(null)
      rawDispatch({ type: "SELECT_ZERO" })
    } else {
      chatCacheStore.setActive(chatId)
      const snapshot = buildCacheSnapshot(chatId)
      rawDispatch({ type: "SELECT_CHAT", chatId, cached: snapshot })
    }
  }, [chatId, isActive, rawDispatch, buildCacheSnapshot])

  // -----------------------------------------------------------------------
  // Auto-send initial prompt for new chats
  // -----------------------------------------------------------------------

  const didAutoSend = useRef(false)
  const prevInitialPrompt = useRef(initialPrompt)

  useEffect(() => {
    if (!isActive) return // Suppress auto-send while dormant
    if (!initialPrompt) return
    if (chatId !== "__new__") return
    // Only auto-send once per initialPrompt value
    if (didAutoSend.current && prevInitialPrompt.current === initialPrompt) return

    didAutoSend.current = true
    prevInitialPrompt.current = initialPrompt

    rawDispatch({
      type: "SEND_MESSAGE",
      text: initialPrompt,
      id: `user-${Date.now()}`,
      sentAt: new Date(),
    })
  }, [initialPrompt, chatId, isActive, rawDispatch])

  // Reset auto-send flag when chatId changes
  useEffect(() => {
    didAutoSend.current = false
  }, [chatId])

  // -----------------------------------------------------------------------
  // Cleanup on unmount
  // -----------------------------------------------------------------------

  useEffect(() => {
    return () => {
      effectRunner.destroy()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // -----------------------------------------------------------------------
  // Write-through — keep cache current on meaningful state changes
  // -----------------------------------------------------------------------

  // Track the previous context ref to avoid writing identical snapshots.
  const prevCtxRef = useRef<ChatMachineContext | null>(null)

  useEffect(() => {
    // Don't cache the draft slot
    if (chatId === "__new__") return
    // Don't cache while inactive (frozen context)
    if (!isActive) return
    // Only cache once we have real data (past bootstrap)
    if (
      ctx.phase === "zero" ||
      ctx.phase === "creating" ||
      ctx.phase === "loading"
    ) {
      return
    }
    // Skip if context reference hasn't changed
    if (prevCtxRef.current === ctx) return
    prevCtxRef.current = ctx

    // Preserve the existing virtualizer state in the cache entry
    const existing = chatCacheStore.getSnapshot().get(chatId)
    chatCacheStore.set(chatId, {
      chatId,
      machineContext: ctx,
      virtualizer: existing?.virtualizer ?? null,
      updatedAt: Date.now(),
    })
  }, [chatId, ctx, isActive])

  // -----------------------------------------------------------------------
  // Virtualizer state — read from cache and provide save callback
  // -----------------------------------------------------------------------

  const virtualizerState = useMemo<VirtuosoState | null>(() => {
    if (chatId === "__new__") return null
    const entry = chatCacheStore.getSnapshot().get(chatId)
    return entry?.virtualizer ?? null
    // Only compute on chatId change (initial mount / switch), not on every
    // cache update — the virtualizer consumes this once via restoreStateFrom.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId])

  const saveVirtualizerState = useCallback(
    (state: VirtuosoState) => {
      if (chatId === "__new__") return
      // Direct mutation — no notify, no re-render. See updateVirtualizerState.
      const snap = chatCacheStore.getSnapshot()
      const entry = snap.get(chatId)
      if (entry) {
        entry.virtualizer = state
      }
    },
    [chatId],
  )

  // -----------------------------------------------------------------------
  // User actions
  // -----------------------------------------------------------------------

  const sendMessage = useCallback(
    async (text: string) => {
      rawDispatch({
        type: "SEND_MESSAGE",
        text,
        id: `user-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        sentAt: new Date(),
      })
    },
    [rawDispatch],
  )

  const cancel = useCallback(async () => {
    rawDispatch({ type: "CANCEL" })
  }, [rawDispatch])

  // -----------------------------------------------------------------------
  // Stream controller
  // -----------------------------------------------------------------------

  const controller = useMemo<StreamController>(
    () => ({
      sendMessage: (msg) => effectRunner.getChannel()?.sendMessage(msg) ?? false,
      interrupt: () => effectRunner.getChannel()?.interrupt() ?? false,
      cancel: () => {
        effectRunner.getChannel()?.cancel()
      },
    }),
    [effectRunner],
  )

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const derived = deriveChatState(ctx)

  // Map machine transportState to the WsState the view expects
  const connectionState: WsState = ctx.transportState

  return {
    entries: ctx.entries,
    currentActivity: derived.currentActivity,
    isStreaming: derived.isStreaming,
    isLoading: derived.isLoading,
    isCreating: derived.isCreating,
    isSending: derived.isSending,
    connectionState,
    controller,
    chatState: ctx.chatState,
    chatDetail: ctx.chatDetail,
    activeSpawnId: ctx.activeSpawnId,
    error: ctx.error,
    sendMessage,
    cancel,
    virtualizerState,
    saveVirtualizerState,
  }
}
