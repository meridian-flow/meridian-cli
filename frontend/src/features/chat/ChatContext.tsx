/**
 * Chat-only context.
 *
 * The shell now shows chats, not spawns, so this provider only tracks the
 * selected chat and the live chat state needed by the thread view.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react"
import type { ReactNode } from "react"

import type {
  ChatProjection,
  ChatState as ApiChatState,
} from "@/lib/api"

export interface ChatSelection extends ChatProjection {
  initialPrompt: string | null
}

export interface ModelSelection {
  modelId: string
  harness: string
  displayName: string
}

export interface ChatContextValue {
  selectedChat: ChatSelection | null
  selectChat: (
    chat: ChatProjection,
    options?: { initialPrompt?: string | null },
  ) => void
  clearChat: () => void
  setChatState: (chatState: ApiChatState) => void
  setActiveSpawnId: (spawnId: string | null) => void
  modelSelection: ModelSelection | null
  setModelSelection: (selection: ModelSelection | null) => void
}

export const ChatContext = createContext<ChatContextValue | null>(null)

interface ChatProviderProps {
  children: ReactNode
}

export function ChatProvider({ children }: ChatProviderProps) {
  const [selectedChat, setSelectedChat] = useState<ChatSelection | null>(null)
  const [modelSelection, setModelSelection] = useState<ModelSelection | null>(null)

  const selectChat = useCallback(
    (chat: ChatProjection, options?: { initialPrompt?: string | null }) => {
      setSelectedChat({
        ...chat,
        initialPrompt: options?.initialPrompt ?? null,
      })
    },
    [],
  )

  // modelSelection intentionally NOT cleared — persists across chat switches
  const clearChat = useCallback(() => {
    setSelectedChat(null)
  }, [])

  const setChatState = useCallback((chatState: ApiChatState) => {
    setSelectedChat((prev) => {
      if (!prev) return prev
      return { ...prev, state: chatState }
    })
  }, [])

  const setActiveSpawnId = useCallback((spawnId: string | null) => {
    setSelectedChat((prev) => {
      if (!prev) return prev
      return { ...prev, active_p_id: spawnId }
    })
  }, [])

  const value = useMemo<ChatContextValue>(
    () => ({
      selectedChat,
      selectChat,
      clearChat,
      setChatState,
      setActiveSpawnId,
      modelSelection,
      setModelSelection,
    }),
    [selectedChat, selectChat, clearChat, setChatState, setActiveSpawnId, modelSelection],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext)
  if (!ctx) {
    throw new Error("useChat must be used within a ChatProvider")
  }
  return ctx
}
