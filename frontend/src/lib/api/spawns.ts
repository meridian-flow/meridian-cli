/**
 * Spawn CRUD — fetch, create, cancel, fork, archive, replay.
 */

import { buildQuery, request } from './client'
import type {
  CursorEnvelope,
  CreateSpawnRequest,
  CreateSpawnResponse,
  FetchSpawnsParams,
  SpawnProjection,
  SpawnReplaySnapshot,
  SpawnStats,
} from './types'

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

export function fetchSpawn(spawnId: string): Promise<SpawnProjection> {
  return request<SpawnProjection>(`/api/spawns/${encodeURIComponent(spawnId)}/details`)
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
  await request(`/api/spawns/${encodeURIComponent(spawnId)}/cancel`, {
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
  await request(`/api/spawns/${encodeURIComponent(spawnId)}/archive`, {
    method: 'POST',
  })
}

export function fetchSpawnReplay(spawnId: string): Promise<SpawnReplaySnapshot> {
  return request<SpawnReplaySnapshot>(
    `/api/spawns/${encodeURIComponent(spawnId)}/replay`,
  )
}
