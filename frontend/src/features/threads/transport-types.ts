// ═══════════════════════════════════════════════════════════════════
// Transport types — store interface + raw backend response shapes
//
// Defines the contract between the thread store and consumers.
// Two data paths: REST for paginated history, plus streaming state.
//
// BackendTurn / BackendTurnBlock are the raw API JSON shapes before
// mapping through turn-mapper.ts into the ThreadTurn view model.
// ═══════════════════════════════════════════════════════════════════

import type { ThreadTurn } from "./types"

// --- Raw backend response types (JSON from REST API) ---

/**
 * Raw turn block from the backend API.
 * Mirrors backend TurnBlock struct — field names match JSON tags.
 */
export type BackendTurnBlock = {
  id: string
  turn_id: string
  block_type: string
  sequence: number
  text_content?: string | null
  content?: Record<string, unknown> | null
  provider?: string | null
  provider_data?: unknown | null
  execution_side?: string | null
  status: string
  collapsed_content?: string | null
  created_at: string
  updated_at?: string | null
}

/**
 * Raw turn from the backend API.
 * Mirrors backend Turn struct — field names match JSON tags.
 */
export type BackendTurn = {
  id: string
  thread_id: string
  prev_turn_id?: string | null
  role: string
  status: string
  error?: string | null
  model?: string | null
  input_tokens?: number | null
  output_tokens?: number | null
  created_at: string
  completed_at?: string | null
  request_params?: Record<string, unknown> | null
  stop_reason?: string | null
  response_metadata?: Record<string, unknown> | null
  blocks?: BackendTurnBlock[] | null
  sibling_ids?: string[] | null
}

/**
 * Paginated turns response from GET /api/threads/{id}/turns.
 * Matches backend PaginatedTurnsResponse struct.
 */
export type PaginatedTurnsResponse = {
  turns: BackendTurn[]
  has_more_before: boolean
  has_more_after: boolean
}

// --- Thread store state ---

export type ThreadStoreState = {
  /** Active-path turns, ordered oldest → newest */
  turns: ThreadTurn[]
  /** Lookup by turn ID for O(1) access */
  turnById: Record<string, ThreadTurn>
  /** Currently streaming turn */
  activeTurnId: string | null
  /** Can paginate backwards (older turns exist) */
  hasMoreBefore: boolean
  /** Can paginate forwards (newer turns exist) */
  hasMoreAfter: boolean
  /** Streaming is active */
  isStreaming: boolean
}

// --- Thread store interface ---

/**
 * Store contract for thread data.
 *
 * Core data operations:
 * - paginated history (loadThread, paginateBefore/After, switchSibling)
 * - streaming state exposure via ThreadStoreState
 *
 * Implementations: production (real data), Storybook (in-memory mock).
 */
export type ThreadStoreInterface = {
  // REST — paginated turn history
  loadThread(threadId: string, fromTurnId?: string): Promise<void>
  paginateBefore(): Promise<void>
  paginateAfter(): Promise<void>
  /** Navigate to a different sibling turn. The thread reloads the path from this turn forward. */
  switchSibling(targetTurnId: string): Promise<void>

  // State
  readonly state: ThreadStoreState
}

// --- Stream controller interface ---

/**
 * Transport-neutral controller for spawn interaction.
 *
 * Abstracts the WebSocket channel so view components (Composer, etc.)
 * don't depend on SpawnChannel directly. Implementations:
 * - Production: wraps SpawnChannel methods
 * - Testing: mock implementation for Storybook
 */
export type StreamController = {
  /** Send a user message to the active spawn. Returns true if sent. */
  sendMessage: (text: string) => boolean
  /** Request the harness to interrupt the current turn. Returns true if sent. */
  interrupt: () => boolean
  /** Cancel the spawn entirely. */
  cancel: () => void
}
