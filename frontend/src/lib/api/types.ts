/**
 * Shared API response and request types.
 *
 * Mirrors the backend's `api_models.py` — keep in sync when the
 * backend schema changes.
 */

import type { SpawnStatus } from '@/types/spawn'

// ---------------------------------------------------------------------------
// Spawn types
// ---------------------------------------------------------------------------

export interface SpawnProjection {
  spawn_id: string
  status: SpawnStatus
  harness: string
  model: string
  agent: string
  work_id: string | null
  desc: string
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface SpawnStats {
  running: number
  queued: number
  succeeded: number
  failed: number
  cancelled: number
  finalizing: number
  total: number
}

export interface FetchSpawnsParams {
  work_id?: string
  status?: string
  agent?: string
  limit?: number
  cursor?: string
}

export interface CreateSpawnPermissions {
  sandbox: string
  approval: string
}

export interface CreateSpawnRequest {
  harness: string
  prompt: string
  model?: string
  agent?: string
  permissions?: CreateSpawnPermissions
}

export interface CreateSpawnResponse {
  spawn_id: string
  harness: string
}

export interface SpawnInboundMessage {
  seq: number
  text: string
  ts: number
}

export interface SpawnReplaySnapshot {
  cursor: number
  events: ChatHistoryEvent[]
  inbound: SpawnInboundMessage[]
}

// ---------------------------------------------------------------------------
// Work types
// ---------------------------------------------------------------------------

export interface WorkProjection {
  work_id: string
  name: string
  status: string
  description: string
  work_dir: string
  created_at: string
  last_activity_at: string | null
  spawn_count: number
  session_count: number
}

// ---------------------------------------------------------------------------
// Chat types
// ---------------------------------------------------------------------------

export type ChatState = 'active' | 'idle' | 'draining' | 'closed'

export interface ChatProjection {
  chat_id: string
  state: ChatState
  title: string | null
  model: string | null
  active_p_id: string | null
  created_at: string
  updated_at: string | null
  harness: string | null
  launch_mode: string | null
  work_id: string | null
  first_message_snippet: string | null
}

export interface ChatDetailResponse extends ChatProjection {
  spawns: SpawnProjection[]
}

export interface ChatHistoryEvent {
  seq: number
  type: string
  data: unknown
  timestamp: string
}

export interface ChatHistoryResponse {
  events: ChatHistoryEvent[]
  has_more: boolean
}

export interface CreateChatOptions {
  model?: string
  harness?: string
}

// ---------------------------------------------------------------------------
// Generic envelope
// ---------------------------------------------------------------------------

export interface CursorEnvelope<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}
