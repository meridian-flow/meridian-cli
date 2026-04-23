/**
 * Sessions mode — pure fetch wrappers for the spawn/work REST API.
 *
 * No React, no state — just typed fetchers that throw on non-2xx.
 * Request/response shapes mirror the backend's `api_models.py`.
 */

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface SpawnProjection {
  spawn_id: string
  /** 'running' | 'queued' | 'succeeded' | 'failed' | 'cancelled' | 'finalizing' */
  status: string
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

export interface CursorEnvelope<T> {
  items: T[]
  next_cursor: string | null
  has_more: boolean
}

// ---------------------------------------------------------------------------
// Request parameter types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  }
  return parts.length === 0 ? '' : `?${parts.join('&')}`
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: string; message?: string }
      detail = body.detail ?? body.message ?? detail
    } catch {
      // non-JSON body — keep statusText
    }
    throw new ApiError(response.status, `${response.status} ${detail}`)
  }

  // 204 / empty body
  if (response.status === 204) return undefined as T
  const text = await response.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

// ---------------------------------------------------------------------------
// Spawns
// ---------------------------------------------------------------------------

export function fetchSpawns(
  params: FetchSpawnsParams = {},
): Promise<CursorEnvelope<SpawnProjection>> {
  const query = buildQuery({
    work_id: params.work_id,
    status: params.status,
    agent: params.agent,
    limit: params.limit,
    cursor: params.cursor,
  })
  return request<CursorEnvelope<SpawnProjection>>(`/api/spawns/list${query}`)
}

export function fetchSpawnStats(work_id?: string): Promise<SpawnStats> {
  const query = buildQuery({ work_id })
  return request<SpawnStats>(`/api/spawns/stats${query}`)
}

export function createSpawn(req: CreateSpawnRequest): Promise<CreateSpawnResponse> {
  return request<CreateSpawnResponse>('/api/spawns', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export async function cancelSpawn(spawnId: string): Promise<void> {
  await request<void>(`/api/spawns/${encodeURIComponent(spawnId)}/cancel`, {
    method: 'POST',
  })
}

export function forkSpawn(spawnId: string): Promise<{ spawn_id: string }> {
  return request<{ spawn_id: string }>(
    `/api/spawns/${encodeURIComponent(spawnId)}/fork`,
    { method: 'POST' },
  )
}

export async function archiveSpawn(spawnId: string): Promise<void> {
  await request<void>(`/api/spawns/${encodeURIComponent(spawnId)}/archive`, {
    method: 'POST',
  })
}

// ---------------------------------------------------------------------------
// Work items
// ---------------------------------------------------------------------------

export function fetchWorkItems(): Promise<CursorEnvelope<WorkProjection>> {
  return request<CursorEnvelope<WorkProjection>>('/api/work')
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export { ApiError }
