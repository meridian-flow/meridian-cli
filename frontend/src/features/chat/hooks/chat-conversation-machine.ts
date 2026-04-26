/**
 * Chat conversation state machine — pure reducer and command model.
 *
 * Single owner of the chat lifecycle. Every state transition is explicit,
 * every async callback is generation-guarded, and every side effect is
 * expressed as a command — never performed inline.
 *
 * The reducer is a pure function: (context, event) => { context, commands[] }.
 * An effect runner (subphase 2.2) reads the commands and executes them.
 *
 * See chat-lifecycle.md for the full spec, topology diagram, and
 * transition matrix.
 */

import {
  createInitialState as createStreamState,
  reduceStreamEvent,
  type StreamState,
} from "@/features/activity-stream/streaming/reducer"
import {
  freezeAssistant,
} from "../conversation-reducer"
import type { ConversationEntry } from "../conversation-types"

import type {
  ChatPhase,
  AccessMode,
  BootstrapState,
  ChatMachineContext,
  ChatCommand,
  ChatEvent,
  ChatCacheSnapshot,
  ChatDerivedState,
  TransitionResult,
} from "./chat-conversation-types"
import type { ChatDetailResponse } from "@/lib/api"

// ═══════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════

const EMPTY_BOOTSTRAP: BootstrapState = {
  detailLoaded: false,
  historyLoaded: false,
  detailPayload: null,
  historyPayload: null,
}

// ═══════════════════════════════════════════════════════════════════
// Initial state
// ═══════════════════════════════════════════════════════════════════

export function createInitialMachineContext(): ChatMachineContext {
  return {
    chatId: null,
    phase: "zero",
    accessMode: "interactive",
    chatDetail: null,
    chatState: null,
    activeSpawnId: null,
    entries: [],
    current: null,
    turnSeq: 0,
    transportState: "idle",
    requestGeneration: 0,
    streamGeneration: 0,
    createGeneration: 0,
    bootstrap: { ...EMPTY_BOOTSTRAP },
    pendingOp: null,
    error: null,
    terminalSeen: false,
    cacheSnapshot: null,
  }
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════

/** Create a new assistant StreamState for a given turn sequence number. */
function newAssistant(seq: number): StreamState {
  return createStreamState(`assistant-${seq}`)
}

/** Freeze the current assistant turn and append it to entries, or return entries unchanged. */
function freezeCurrentTurn(
  entries: ConversationEntry[],
  current: StreamState | null,
  status: "complete" | "cancelled" | "error",
): ConversationEntry[] {
  if (current === null) return entries
  const frozen = freezeAssistant(current, status)
  return frozen ? [...entries, frozen] : entries
}

/** Derive access mode from a chat detail response. */
function deriveAccessMode(detail: ChatDetailResponse): AccessMode {
  return detail.launch_mode === "app" || detail.launch_mode == null
    ? "interactive"
    : "readonly"
}

/** Shorthand: produce a result with no commands. */
function noCommands(context: ChatMachineContext): TransitionResult {
  return { context, commands: [] }
}

/** Shorthand: produce a result with commands. */
function withCommands(
  context: ChatMachineContext,
  commands: ChatCommand[],
): TransitionResult {
  return { context, commands }
}

/**
 * Resolve the target phase after both detail and history are loaded.
 *
 * The resolution logic maps backend state + launch_mode to the
 * correct machine phase, following the spec's bootstrap resolution
 * rules.
 */
function resolveBootstrapPhase(detail: ChatDetailResponse): {
  phase: ChatPhase
  accessMode: AccessMode
} {
  const accessMode = deriveAccessMode(detail)

  if (detail.state === "closed") {
    return { phase: "finished", accessMode }
  }

  if (accessMode === "readonly") {
    // External-launch chats that are still live → readonly observation
    if (detail.active_p_id) {
      return { phase: "connecting", accessMode: "readonly" }
    }
    return { phase: "readonly", accessMode }
  }

  // Interactive chats
  if (
    (detail.state === "active" || detail.state === "draining" || detail.state === "idle") &&
    detail.active_p_id
  ) {
    return { phase: "connecting", accessMode }
  }

  return { phase: "idle", accessMode }
}

/**
 * Build the zero-state context, disconnecting any transport and
 * clearing all state. Used by SELECT_ZERO and UNMOUNT.
 */
function enterZero(ctx: ChatMachineContext): TransitionResult {
  const commands: ChatCommand[] = []

  // Disconnect any active spawn
  if (ctx.activeSpawnId !== null || ctx.transportState !== "idle") {
    commands.push({ type: "disconnectSpawn", generation: ctx.streamGeneration })
  }

  // Increment all generation counters so any in-flight callbacks from
  // the previous chat are generation-guarded out on arrival.
  return {
    context: {
      ...createInitialMachineContext(),
      requestGeneration: ctx.requestGeneration + 1,
      streamGeneration: ctx.streamGeneration + 1,
      createGeneration: ctx.createGeneration + 1,
    },
    commands,
  }
}

// ═══════════════════════════════════════════════════════════════════
// Main reducer
// ═══════════════════════════════════════════════════════════════════

export function chatMachineReducer(
  ctx: ChatMachineContext,
  event: ChatEvent,
): TransitionResult {
  switch (event.type) {
    // -----------------------------------------------------------------
    // Selection events
    // -----------------------------------------------------------------

    case "SELECT_ZERO":
      return enterZero(ctx)

    case "SELECT_CHAT":
      return reduceSelectChat(ctx, event.chatId, event.cached)

    case "UNMOUNT":
      return enterZero(ctx)

    // -----------------------------------------------------------------
    // User actions
    // -----------------------------------------------------------------

    case "SEND_MESSAGE":
      return reduceSendMessage(ctx, event.text, event.id, event.sentAt)

    case "CANCEL":
      return reduceCancel(ctx)

    // -----------------------------------------------------------------
    // Bootstrap responses
    // -----------------------------------------------------------------

    case "DETAIL_LOADED":
      return reduceDetailLoaded(ctx, event.detail, event.generation)

    case "DETAIL_FAILED":
      return reduceDetailFailed(ctx, event.error, event.generation)

    case "HISTORY_LOADED":
      return reduceHistoryLoaded(ctx, event.entries, event.generation)

    case "HISTORY_FAILED":
      return reduceHistoryFailed(ctx, event.error, event.generation)

    // -----------------------------------------------------------------
    // API responses
    // -----------------------------------------------------------------

    case "CREATE_SUCCEEDED":
      return reduceCreateSucceeded(ctx, event.detail, event.generation)

    case "CREATE_FAILED":
      return reduceCreateFailed(ctx, event.error, event.generation)

    case "PROMPT_SUCCEEDED":
      return reducePromptSucceeded(ctx, event.detail, event.generation)

    case "PROMPT_FAILED":
      return reducePromptFailed(ctx, event.error, event.generation)

    case "CANCEL_SUCCEEDED":
      return reduceCancelSucceeded(ctx, event.generation)

    case "CANCEL_FAILED":
      return reduceCancelFailed(ctx, event.error, event.generation)

    case "CONTINUE_SUCCEEDED":
      return reduceContinueSucceeded(ctx, event.detail, event.generation)

    case "CONTINUE_FAILED":
      return reduceContinueFailed(ctx, event.error, event.generation)

    // -----------------------------------------------------------------
    // WS lifecycle
    // -----------------------------------------------------------------

    case "WS_OPENED":
      return reduceWsOpened(ctx, event.generation)

    case "WS_CLOSED":
      return reduceWsClosed(ctx, event.generation)

    // -----------------------------------------------------------------
    // Stream events
    // -----------------------------------------------------------------

    case "STREAM_EVENT":
      return reduceStreamEventAction(ctx, event.event, event.generation)

    // -----------------------------------------------------------------
    // Replay
    // -----------------------------------------------------------------

    case "REPLAY_SUCCEEDED":
      return reduceReplaySucceeded(ctx, event.entries, event.cursor, event.generation)

    case "REPLAY_FAILED":
      return reduceReplayFailed(ctx, event.error, event.generation)

    default:
      return noCommands(ctx)
  }
}

// ═══════════════════════════════════════════════════════════════════
// Selection reducers
// ═══════════════════════════════════════════════════════════════════

function reduceSelectChat(
  ctx: ChatMachineContext,
  chatId: string,
  cached?: ChatCacheSnapshot,
): TransitionResult {
  const commands: ChatCommand[] = []

  // Disconnect any existing spawn
  if (ctx.activeSpawnId !== null || ctx.transportState !== "idle") {
    commands.push({ type: "disconnectSpawn", generation: ctx.streamGeneration })
  }

  const requestGeneration = ctx.requestGeneration + 1
  const streamGeneration = ctx.streamGeneration + 1

  // ---- Cache hit: terminal chat → instant restore ----
  if (cached?.isTerminal) {
    const accessMode = deriveAccessMode(cached.chatDetail)
    // Readonly chats restore to "readonly", not "finished" — finished
    // allows SEND_MESSAGE (continue) which is invalid for readonly.
    const phase: ChatPhase = accessMode === "readonly" ? "readonly" : "finished"

    return {
      context: {
        ...createInitialMachineContext(),
        chatId,
        phase,
        accessMode,
        chatDetail: cached.chatDetail,
        chatState: cached.chatState,
        activeSpawnId: null,
        entries: cached.entries,
        turnSeq: cached.turnSeq,
        requestGeneration,
        streamGeneration,
        createGeneration: ctx.createGeneration + 1,
        cacheSnapshot: cached,
      },
      commands,
    }
  }

  // ---- Cache hit: live/warm chat → seed + revalidate ----
  if (cached && !cached.isTerminal) {
    const { phase, accessMode } = resolveBootstrapPhase(cached.chatDetail)

    const nextCtx: ChatMachineContext = {
      ...createInitialMachineContext(),
      chatId,
      phase,
      accessMode,
      chatDetail: cached.chatDetail,
      chatState: cached.chatState,
      activeSpawnId: cached.activeSpawnId,
      entries: cached.entries,
      turnSeq: cached.turnSeq,
      requestGeneration,
      streamGeneration,
      createGeneration: ctx.createGeneration + 1,
      cacheSnapshot: cached,
    }

    // Background revalidate
    commands.push({ type: "fetchDetail", chatId, generation: requestGeneration })

    // Connect WS if the cached chat has a live spawn
    if (cached.activeSpawnId && (phase === "connecting" || phase === "streaming")) {
      commands.push({
        type: "connectSpawn",
        spawnId: cached.activeSpawnId,
        replay: true,
        generation: streamGeneration,
      })
      commands.push({
        type: "fetchReplay",
        spawnId: cached.activeSpawnId,
        generation: streamGeneration,
      })
    }

    return { context: nextCtx, commands }
  }

  // ---- Cache miss: cold load ----
  commands.push(
    { type: "fetchDetail", chatId, generation: requestGeneration },
    { type: "fetchHistory", chatId, generation: requestGeneration },
  )

  return {
    context: {
      ...createInitialMachineContext(),
      chatId,
      phase: "loading",
      requestGeneration,
      streamGeneration,
      createGeneration: ctx.createGeneration + 1,
    },
    commands,
  }
}

// ═══════════════════════════════════════════════════════════════════
// User action reducers
// ═══════════════════════════════════════════════════════════════════

function reduceSendMessage(
  ctx: ChatMachineContext,
  text: string,
  id: string,
  sentAt: Date,
): TransitionResult {
  const trimmed = text.trim()
  if (!trimmed) return noCommands(ctx)

  const userEntry: ConversationEntry = {
    kind: "user",
    id,
    text: trimmed,
    sentAt,
  }

  switch (ctx.phase) {
    // ---- zero → creating ----
    case "zero": {
      const createGeneration = ctx.createGeneration + 1
      return withCommands(
        {
          ...ctx,
          phase: "creating",
          entries: [...ctx.entries, userEntry],
          createGeneration,
          error: null,
          pendingOp: { kind: "create", prompt: trimmed },
        },
        [{ type: "createChat", prompt: trimmed, generation: createGeneration }],
      )
    }

    // ---- idle → connecting (promptChat) ----
    case "idle": {
      const streamGeneration = ctx.streamGeneration + 1
      return withCommands(
        {
          ...ctx,
          phase: "idle", // stays idle until PROMPT_SUCCEEDED
          entries: [...ctx.entries, userEntry],
          streamGeneration,
          error: null,
          pendingOp: { kind: "prompt", chatId: ctx.chatId!, text: trimmed },
        },
        [
          {
            type: "promptChat",
            chatId: ctx.chatId!,
            text: trimmed,
            generation: streamGeneration,
          },
        ],
      )
    }

    // ---- finished → creating (continueChat) ----
    case "finished": {
      const createGeneration = ctx.createGeneration + 1
      return withCommands(
        {
          ...ctx,
          phase: "creating",
          entries: [...ctx.entries, userEntry],
          createGeneration,
          error: null,
          pendingOp: { kind: "continue", chatId: ctx.chatId!, text: trimmed },
        },
        [
          {
            type: "continueChat",
            chatId: ctx.chatId!,
            text: trimmed,
            generation: createGeneration,
          },
        ],
      )
    }

    // ---- All other phases: send is blocked ----
    default:
      return noCommands(ctx)
  }
}

function reduceCancel(ctx: ChatMachineContext): TransitionResult {
  // Cancel is only meaningful in connecting/streaming/idle (interactive)
  if (ctx.accessMode === "readonly") return noCommands(ctx)

  switch (ctx.phase) {
    case "connecting":
    case "streaming":
    case "idle": {
      if (!ctx.chatId) return noCommands(ctx)
      return withCommands(
        {
          ...ctx,
          chatState: "draining",
          pendingOp: { kind: "cancel", chatId: ctx.chatId },
          error: null,
        },
        [{ type: "cancelChat", chatId: ctx.chatId, generation: ctx.streamGeneration }],
      )
    }

    default:
      return noCommands(ctx)
  }
}

// ═══════════════════════════════════════════════════════════════════
// Bootstrap response reducers
// ═══════════════════════════════════════════════════════════════════

function reduceDetailLoaded(
  ctx: ChatMachineContext,
  detail: ChatDetailResponse,
  generation: number,
): TransitionResult {
  // Generation guard
  if (generation !== ctx.requestGeneration) return noCommands(ctx)

  // ---- Background revalidation (warm-cache path) ----
  // When a cached chat is restored directly into idle/readonly/streaming,
  // the warm-cache code emits a fetchDetail for background revalidation.
  // Update metadata without changing phase — the chat is already usable.
  if (
    ctx.phase === "idle" ||
    ctx.phase === "readonly" ||
    ctx.phase === "streaming" ||
    ctx.phase === "finished"
  ) {
    const commands: ChatCommand[] = []
    const accessMode = deriveAccessMode(detail)
    let phase: ChatPhase = ctx.phase
    const activeSpawnId = detail.active_p_id ?? null

    // If backend says closed but we're in idle/readonly, transition to finished.
    // NEVER force streaming→finished here — the stream still has in-flight
    // events (text, tool results, RUN_FINISHED). Premature transition drops
    // them. The streaming phase will reach finished naturally via
    // RUN_FINISHED / RUN_ERROR / WS_CLOSED.
    if (
      detail.state === "closed" &&
      ctx.phase !== "finished" &&
      ctx.phase !== "streaming"
    ) {
      phase = "finished"
    }

    // If backend shows a new live spawn we weren't connected to, connect
    if (
      activeSpawnId &&
      activeSpawnId !== ctx.activeSpawnId &&
      detail.state !== "closed" &&
      (ctx.phase === "idle" || ctx.phase === "readonly")
    ) {
      const streamGeneration = ctx.streamGeneration + 1
      phase = "connecting"
      commands.push({
        type: "connectSpawn",
        spawnId: activeSpawnId,
        replay: true,
        generation: streamGeneration,
      })
      commands.push({
        type: "fetchReplay",
        spawnId: activeSpawnId,
        generation: streamGeneration,
      })
      return withCommands(
        {
          ...ctx,
          phase,
          chatDetail: detail,
          chatState: detail.state,
          activeSpawnId,
          accessMode,
          streamGeneration,
          // Reset: new spawn discovered via revalidation — clear the
          // previous spawn's terminal flag so stream events flow.
          terminalSeen: false,
        },
        commands,
      )
    }

    return noCommands({
      ...ctx,
      phase,
      chatDetail: detail,
      chatState: detail.state,
      activeSpawnId,
      accessMode,
    })
  }

  // ---- Bootstrap path (loading/connecting) ----
  if (ctx.phase !== "loading" && ctx.phase !== "connecting") {
    return noCommands(ctx)
  }

  const bootstrap: BootstrapState = {
    ...ctx.bootstrap,
    detailLoaded: true,
    detailPayload: detail,
  }

  const nextCtx: ChatMachineContext = {
    ...ctx,
    bootstrap,
    chatDetail: detail,
    chatState: detail.state,
    activeSpawnId: detail.active_p_id ?? ctx.activeSpawnId,
    accessMode: deriveAccessMode(detail),
  }

  // If history is also loaded, resolve to target phase
  if (bootstrap.historyLoaded) {
    return resolveBootstrap(nextCtx, detail, bootstrap.historyPayload ?? [])
  }

  return noCommands(nextCtx)
}

function reduceDetailFailed(
  ctx: ChatMachineContext,
  error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.requestGeneration) return noCommands(ctx)

  if (ctx.phase === "loading") {
    // Transition to zero so the user can retry by re-selecting the chat.
    // Staying in "loading" forever is unrecoverable.
    return noCommands({
      ...ctx,
      phase: "zero",
      error,
    })
  }

  return noCommands(ctx)
}

function reduceHistoryLoaded(
  ctx: ChatMachineContext,
  entries: ConversationEntry[],
  generation: number,
): TransitionResult {
  if (generation !== ctx.requestGeneration) return noCommands(ctx)

  if (ctx.phase !== "loading" && ctx.phase !== "connecting") {
    return noCommands(ctx)
  }

  const bootstrap: BootstrapState = {
    ...ctx.bootstrap,
    historyLoaded: true,
    historyPayload: entries,
  }

  const nextCtx: ChatMachineContext = {
    ...ctx,
    bootstrap,
  }

  // If detail is also loaded, resolve to target phase
  if (bootstrap.detailLoaded && bootstrap.detailPayload) {
    return resolveBootstrap(nextCtx, bootstrap.detailPayload, entries)
  }

  return noCommands(nextCtx)
}

function reduceHistoryFailed(
  ctx: ChatMachineContext,
  error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.requestGeneration) return noCommands(ctx)

  if (ctx.phase === "loading") {
    // Transition to zero so the user can retry by re-selecting the chat.
    // Staying in "loading" forever is unrecoverable.
    return noCommands({ ...ctx, phase: "zero", error })
  }

  return noCommands(ctx)
}

/**
 * Merge backend history with any existing optimistic entries.
 *
 * During the __new__ → real chatId handoff (#108), the machine holds
 * optimistic user entries from SEND_MESSAGE that may not yet appear in
 * the backend history. A naive replacement drops them. This merge:
 *
 * 1. Starts from the history entries (backend is authoritative).
 * 2. Appends any optimistic user entries from ctx.entries that are NOT
 *    already represented in history (matched by trimmed text content).
 *
 * The result preserves the user's visible message while avoiding
 * duplicates once the backend catches up.
 */
function mergeWithOptimisticEntries(
  historyEntries: ConversationEntry[],
  existingEntries: ConversationEntry[],
): ConversationEntry[] {
  // Fast path: no existing entries to preserve
  if (existingEntries.length === 0) return historyEntries

  // Collect text of all user entries from history for dedup
  const historyUserTexts = new Set<string>()
  for (const entry of historyEntries) {
    if (entry.kind === "user") {
      historyUserTexts.add(entry.text.trim())
    }
  }

  // Find optimistic user entries not yet in history
  const optimistic: ConversationEntry[] = []
  for (const entry of existingEntries) {
    if (entry.kind === "user" && !historyUserTexts.has(entry.text.trim())) {
      optimistic.push(entry)
    }
  }

  if (optimistic.length === 0) return historyEntries

  // Prepend optimistic user entries before history (they were sent first)
  return [...optimistic, ...historyEntries]
}

/**
 * Both detail and history are loaded — resolve the target phase and
 * emit any follow-up commands (WS connect, replay fetch).
 */
function resolveBootstrap(
  ctx: ChatMachineContext,
  detail: ChatDetailResponse,
  historyEntries: ConversationEntry[],
): TransitionResult {
  const commands: ChatCommand[] = []
  const { phase, accessMode } = resolveBootstrapPhase(detail)

  // Merge history with any existing optimistic entries (#108)
  const mergedEntries = mergeWithOptimisticEntries(historyEntries, ctx.entries)

  let nextCtx: ChatMachineContext = {
    ...ctx,
    phase,
    accessMode,
    chatDetail: detail,
    chatState: detail.state,
    activeSpawnId: detail.active_p_id ?? null,
    entries: mergedEntries,
    turnSeq: mergedEntries.length,
    bootstrap: { ...EMPTY_BOOTSTRAP }, // Clear bootstrap tracking
    error: null,
  }

  // If resolving to connecting, set up the spawn transport
  if (phase === "connecting" && detail.active_p_id) {
    const streamGeneration = ctx.streamGeneration + 1
    nextCtx = { ...nextCtx, streamGeneration }
    commands.push({
      type: "connectSpawn",
      spawnId: detail.active_p_id,
      replay: true,
      generation: streamGeneration,
    })
    commands.push({
      type: "fetchReplay",
      spawnId: detail.active_p_id,
      generation: streamGeneration,
    })
  }

  return { context: nextCtx, commands }
}

// ═══════════════════════════════════════════════════════════════════
// API response reducers
// ═══════════════════════════════════════════════════════════════════

function reduceCreateSucceeded(
  ctx: ChatMachineContext,
  detail: ChatDetailResponse,
  generation: number,
): TransitionResult {
  // Generation guard
  if (generation !== ctx.createGeneration) return noCommands(ctx)

  if (ctx.phase !== "creating") return noCommands(ctx)

  const commands: ChatCommand[] = []
  const streamGeneration = ctx.streamGeneration + 1

  // Critical: preserve the optimistic user message (entries survive)
  let nextCtx: ChatMachineContext = {
    ...ctx,
    chatId: detail.chat_id,
    phase: "connecting",
    chatDetail: detail,
    chatState: detail.state,
    activeSpawnId: detail.active_p_id ?? null,
    accessMode: deriveAccessMode(detail),
    streamGeneration,
    pendingOp: null,
    error: null,
    // Defensive reset: createSucceeded originates from zero→creating where
    // terminalSeen should already be false, but reset explicitly to prevent
    // edge cases if the context was seeded from a cached terminal chat.
    terminalSeen: false,
  }

  // Connect to the spawn
  if (detail.active_p_id) {
    commands.push({
      type: "connectSpawn",
      spawnId: detail.active_p_id,
      replay: false, // New chat — no replay needed
      generation: streamGeneration,
    })
  }

  return { context: nextCtx, commands }
}

function reduceCreateFailed(
  ctx: ChatMachineContext,
  error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.createGeneration) return noCommands(ctx)
  if (ctx.phase !== "creating") return noCommands(ctx)

  // Revert to zero, but keep the optimistic user entry visible so the
  // user can see what they typed and retry.
  return noCommands({
    ...ctx,
    phase: "zero",
    chatId: null,
    pendingOp: null,
    error,
  })
}

function reducePromptSucceeded(
  ctx: ChatMachineContext,
  detail: ChatDetailResponse,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  // Prompt response can arrive in idle (normal) or connecting (rare race)
  if (ctx.phase !== "idle" && ctx.phase !== "connecting") return noCommands(ctx)

  const commands: ChatCommand[] = []

  let nextCtx: ChatMachineContext = {
    ...ctx,
    phase: "connecting",
    chatDetail: detail,
    chatState: detail.state,
    activeSpawnId: detail.active_p_id ?? ctx.activeSpawnId,
    pendingOp: null,
    error: null,
    // Reset: terminalSeen is spawn-scoped — a new spawn is starting,
    // so the previous spawn's terminal flag must not block its events.
    terminalSeen: false,
  }

  if (detail.active_p_id) {
    commands.push({
      type: "connectSpawn",
      spawnId: detail.active_p_id,
      replay: false,
      generation,
    })
  }

  return { context: nextCtx, commands }
}

function reducePromptFailed(
  ctx: ChatMachineContext,
  error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  if (
    ctx.phase !== "idle" &&
    ctx.phase !== "connecting" &&
    ctx.phase !== "streaming"
  ) {
    return noCommands(ctx)
  }

  return noCommands({
    ...ctx,
    phase: "idle",
    pendingOp: null,
    error,
  })
}

function reduceCancelSucceeded(
  ctx: ChatMachineContext,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  // Bump streamGeneration to invalidate any buffered stream events
  // from the cancelled turn that haven't arrived yet.
  const nextStreamGen = ctx.streamGeneration + 1

  switch (ctx.phase) {
    case "streaming": {
      // Freeze the current turn, move to idle, let WS close naturally
      const entries = freezeCurrentTurn(ctx.entries, ctx.current, "cancelled")
      return noCommands({
        ...ctx,
        phase: "idle",
        entries,
        current: null,
        chatState: "draining",
        streamGeneration: nextStreamGen,
        pendingOp: null,
        error: null,
      })
    }

    case "connecting":
    case "idle": {
      return noCommands({
        ...ctx,
        phase: "idle",
        streamGeneration: nextStreamGen,
        pendingOp: null,
        error: null,
      })
    }

    default:
      return noCommands(ctx)
  }
}

function reduceCancelFailed(
  ctx: ChatMachineContext,
  error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  // Cancel is best-effort — stay in current phase, show error
  return noCommands({
    ...ctx,
    pendingOp: null,
    error,
  })
}

function reduceContinueSucceeded(
  ctx: ChatMachineContext,
  detail: ChatDetailResponse,
  generation: number,
): TransitionResult {
  if (generation !== ctx.createGeneration) return noCommands(ctx)

  if (ctx.phase !== "creating") return noCommands(ctx)

  const commands: ChatCommand[] = []
  const streamGeneration = ctx.streamGeneration + 1

  const nextCtx: ChatMachineContext = {
    ...ctx,
    phase: "connecting",
    chatDetail: detail,
    chatState: detail.state,
    activeSpawnId: detail.active_p_id ?? null,
    accessMode: deriveAccessMode(detail),
    streamGeneration,
    pendingOp: null,
    error: null,
    // Reset: terminalSeen is spawn-scoped — a new spawn is starting,
    // so the previous spawn's terminal flag must not block its events.
    terminalSeen: false,
  }

  if (detail.active_p_id) {
    commands.push({
      type: "connectSpawn",
      spawnId: detail.active_p_id,
      replay: false,
      generation: streamGeneration,
    })
  }

  return { context: nextCtx, commands }
}

function reduceContinueFailed(
  ctx: ChatMachineContext,
  error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.createGeneration) return noCommands(ctx)

  if (ctx.phase !== "creating") return noCommands(ctx)

  // Fall back to finished — the chat identity is preserved
  return noCommands({
    ...ctx,
    phase: "finished",
    pendingOp: null,
    error,
  })
}

// ═══════════════════════════════════════════════════════════════════
// WebSocket lifecycle reducers
// ═══════════════════════════════════════════════════════════════════

function reduceWsOpened(
  ctx: ChatMachineContext,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  return noCommands({
    ...ctx,
    transportState: "open",
  })
}

function reduceWsClosed(
  ctx: ChatMachineContext,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  const nextCtx: ChatMachineContext = {
    ...ctx,
    transportState: "closed",
    activeSpawnId: null,
  }

  switch (ctx.phase) {
    case "connecting":
    case "streaming": {
      // If we received a terminal event (RUN_FINISHED/RUN_ERROR), the
      // close is just transport cleanup. Otherwise it's unexpected.
      if (ctx.terminalSeen) {
        const entries = freezeCurrentTurn(ctx.entries, ctx.current, "complete")
        return noCommands({
          ...nextCtx,
          phase: "idle",
          entries,
          current: null,
        })
      }

      // Unexpected close — check if backend says closed
      if (ctx.chatState === "closed") {
        const entries = freezeCurrentTurn(ctx.entries, ctx.current, "complete")
        return noCommands({
          ...nextCtx,
          phase: "finished",
          entries,
          current: null,
        })
      }

      // Unexpected close, no terminal event, not closed — go to idle
      // and let the next action (send/cancel) reattach
      const entries = freezeCurrentTurn(ctx.entries, ctx.current, "complete")
      return noCommands({
        ...nextCtx,
        phase: "idle",
        entries,
        current: null,
      })
    }

    case "idle":
    case "readonly":
      // Graceful close after finished turn
      return noCommands(nextCtx)

    default:
      return noCommands(nextCtx)
  }
}

// ═══════════════════════════════════════════════════════════════════
// Stream event reducer
// ═══════════════════════════════════════════════════════════════════

function reduceStreamEventAction(
  ctx: ChatMachineContext,
  event: import("@/features/activity-stream/streaming/events").StreamEvent,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  // Reject events after a terminal transition (RUN_FINISHED/RUN_ERROR
  // already processed). Prevents late-arriving buffered events from
  // resurrecting a frozen turn.
  if (ctx.terminalSeen) return noCommands(ctx)

  // Stream events are only meaningful in connecting/streaming/idle/readonly
  if (
    ctx.phase !== "connecting" &&
    ctx.phase !== "streaming" &&
    ctx.phase !== "idle" &&
    ctx.phase !== "readonly"
  ) {
    return noCommands(ctx)
  }

  // ---- RUN_STARTED ----
  if (event.type === "RUN_STARTED") {
    // Freeze any prior turn
    const entries = freezeCurrentTurn(ctx.entries, ctx.current, "complete")
    const turnSeq = ctx.turnSeq + 1
    const current = reduceStreamEvent(newAssistant(turnSeq), event)

    return noCommands({
      ...ctx,
      phase: "streaming",
      entries,
      current,
      turnSeq,
      terminalSeen: false,
    })
  }

  // ---- RUN_FINISHED ----
  if (event.type === "RUN_FINISHED") {
    const current = ctx.current
      ? reduceStreamEvent(ctx.current, event)
      : reduceStreamEvent(newAssistant(ctx.turnSeq + 1), event)

    const entries = freezeCurrentTurn(ctx.entries, current, "complete")

    // Determine target phase: readonly stays readonly, others go idle
    const targetPhase: ChatPhase = ctx.accessMode === "readonly" ? "readonly" : "idle"

    return noCommands({
      ...ctx,
      phase: targetPhase,
      entries,
      current: null,
      turnSeq: ctx.current ? ctx.turnSeq : ctx.turnSeq + 1,
      terminalSeen: true,
    })
  }

  // ---- RUN_ERROR ----
  if (event.type === "RUN_ERROR") {
    const current = ctx.current
      ? reduceStreamEvent(ctx.current, event)
      : reduceStreamEvent(newAssistant(ctx.turnSeq + 1), event)

    const status = event.isCancelled ? "cancelled" : "error"
    const entries = freezeCurrentTurn(ctx.entries, current, status)

    // Fatal errors go to finished, cancellations go to idle/readonly
    const isFatal = !event.isCancelled
    let targetPhase: ChatPhase
    if (isFatal) {
      targetPhase = "finished"
    } else if (ctx.accessMode === "readonly") {
      targetPhase = "readonly"
    } else {
      targetPhase = "idle"
    }

    return noCommands({
      ...ctx,
      phase: targetPhase,
      entries,
      current: null,
      turnSeq: ctx.current ? ctx.turnSeq : ctx.turnSeq + 1,
      terminalSeen: true,
      error: event.isCancelled ? null : event.message,
    })
  }

  // ---- All other stream events (text, thinking, tool, etc.) ----
  // Ensure we have a current assistant turn. If we somehow receive
  // content events without a prior RUN_STARTED, synthesize one.
  let current = ctx.current
  let turnSeq = ctx.turnSeq
  let phase = ctx.phase

  if (current === null) {
    turnSeq = ctx.turnSeq + 1
    current = reduceStreamEvent(newAssistant(turnSeq), { type: "RUN_STARTED" })
    phase = "streaming"
  }

  current = reduceStreamEvent(current, event)

  return noCommands({
    ...ctx,
    phase: phase === "connecting" ? "streaming" : phase,
    current,
    turnSeq,
  })
}

// ═══════════════════════════════════════════════════════════════════
// Replay reducers
// ═══════════════════════════════════════════════════════════════════

function reduceReplaySucceeded(
  ctx: ChatMachineContext,
  entries: ConversationEntry[],
  _cursor: number,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  // Replay seeds the conversation from the snapshot. It can arrive in
  // connecting, streaming, idle, or readonly. In all cases, it replaces
  // the entries array (the live stream will append on top).
  if (
    ctx.phase !== "connecting" &&
    ctx.phase !== "streaming" &&
    ctx.phase !== "idle" &&
    ctx.phase !== "readonly"
  ) {
    return noCommands(ctx)
  }

  return noCommands({
    ...ctx,
    entries,
    turnSeq: entries.length,
  })
}

function reduceReplayFailed(
  ctx: ChatMachineContext,
  _error: string,
  generation: number,
): TransitionResult {
  if (generation !== ctx.streamGeneration) return noCommands(ctx)

  // Replay is best-effort — fall back to live-only mode. No phase change.
  return noCommands(ctx)
}

// ═══════════════════════════════════════════════════════════════════
// Derived state
// ═══════════════════════════════════════════════════════════════════

/**
 * Compute derived booleans from the machine context. Called on every
 * render — pure, no allocation beyond the returned object.
 */
export function deriveChatState(ctx: ChatMachineContext): ChatDerivedState {
  const isStreaming = ctx.phase === "streaming" && ctx.current !== null
  const currentActivity = ctx.current?.activity ?? null

  return {
    isStreaming,
    isLoading: ctx.phase === "loading",
    isCreating: ctx.phase === "creating",
    isSending: ctx.pendingOp?.kind === "prompt",
    currentActivity,
    composerEnabled:
      ctx.phase === "zero" ||
      ctx.phase === "idle" ||
      ctx.phase === "finished",
    cancelVisible:
      ctx.accessMode === "interactive" &&
      (ctx.phase === "connecting" ||
        ctx.phase === "streaming"),
  }
}
