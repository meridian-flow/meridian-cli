/**
 * Chat lifecycle — create, list, prompt, cancel, close, history, spawns.
 */

import { buildQuery, request } from './client'
import type {
  ChatDetailResponse,
  ChatHistoryResponse,
  ChatProjection,
  CreateChatOptions,
  SpawnProjection,
} from './types'

export function createChat(
  prompt: string,
  options?: CreateChatOptions,
): Promise<ChatDetailResponse> {
  return request<ChatDetailResponse>('/api/chats', {
    method: 'POST',
    body: JSON.stringify({
      prompt,
      model: options?.model,
      harness: options?.harness,
    }),
  })
}

export function listChats(): Promise<ChatProjection[]> {
  return request<ChatProjection[]>('/api/chats')
}

export function getChat(chatId: string): Promise<ChatDetailResponse> {
  return request<ChatDetailResponse>(`/api/chats/${encodeURIComponent(chatId)}`)
}

export function promptChat(chatId: string, text: string): Promise<ChatDetailResponse> {
  return request<ChatDetailResponse>(
    `/api/chats/${encodeURIComponent(chatId)}/prompt`,
    {
      method: 'POST',
      body: JSON.stringify({ text }),
    },
  )
}

export async function cancelChat(chatId: string): Promise<void> {
  await request(`/api/chats/${encodeURIComponent(chatId)}/cancel`, {
    method: 'POST',
  })
}

export async function closeChat(chatId: string): Promise<void> {
  await request(`/api/chats/${encodeURIComponent(chatId)}/close`, {
    method: 'POST',
  })
}

export function getChatHistory(
  chatId: string,
  startSeq?: number,
  limit?: number,
): Promise<ChatHistoryResponse> {
  const query = buildQuery({
    start_seq: startSeq ?? 0,
    limit: limit ?? 100,
  })
  return request<ChatHistoryResponse>(
    `/api/chats/${encodeURIComponent(chatId)}/history${query}`,
  )
}

export function getChatSpawns(chatId: string): Promise<SpawnProjection[]> {
  return request<SpawnProjection[]>(
    `/api/chats/${encodeURIComponent(chatId)}/spawns`,
  )
}
