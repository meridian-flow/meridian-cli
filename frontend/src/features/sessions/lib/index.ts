/**
 * Backwards-compat re-export — all API types and fetchers now live in
 * `@/lib/api`. Import from there directly in new code.
 */
export {
  ApiError,
  archiveSpawn,
  cancelChat,
  cancelSpawn,
  closeChat,
  createChat,
  createSpawn,
  fetchSpawnStats,
  fetchSpawns,
  fetchWorkItems,
  forkSpawn,
  getChat,
  getChatHistory,
  getChatSpawns,
  listChats,
  promptChat,
} from '@/lib/api'
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
  SpawnProjection,
  SpawnStats,
  WorkProjection,
} from '@/lib/api'
