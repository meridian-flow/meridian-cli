/**
 * API barrel — re-exports all types and domain fetchers.
 *
 * Consumers import from `@/lib/api` and get everything they need.
 */

// Infrastructure
export { ApiError } from './client'

// Types
export type {
  ChatDetailResponse,
  ChatHistoryEvent,
  ChatHistoryResponse,
  ChatProjection,
  ChatState,
  CreateChatOptions,
  CreateSpawnPermissions,
  CreateSpawnRequest,
  CreateSpawnResponse,
  CursorEnvelope,
  FetchSpawnsParams,
  SpawnInboundMessage,
  SpawnProjection,
  SpawnReplaySnapshot,
  SpawnStats,
  WorkProjection,
} from './types'

// Spawns
export {
  archiveSpawn,
  cancelSpawn,
  createSpawn,
  fetchSpawn,
  fetchSpawnReplay,
  fetchSpawns,
  fetchSpawnStats,
  forkSpawn,
} from './spawns'

// Chats
export {
  cancelChat,
  closeChat,
  createChat,
  getChat,
  getChatHistory,
  getChatSpawns,
  listChats,
  promptChat,
} from './chats'

// Work
export { fetchWorkItems } from './work'
