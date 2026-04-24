/**
 * Chat-first context — manages the selected chat and spawn column state.
 *
 * Two layers of selection:
 * 1. **Chat selection**: which HCP chat is active. Drives the sidebar
 *    highlight and the main thread view. At most one chat is selected.
 * 2. **Spawn column**: within a chat (or for legacy direct-spawn viewing),
 *    which spawn columns are open in the multi-column layout.
 *
 * Column lifecycle (preserved from before):
 * - `openSpawn` adds a spawn as a new column, or focuses it if already open.
 *   When the column cap is reached the least-recently-focused column is
 *   evicted.
 * - `closeColumn` removes a spawn and hands focus to the MRU survivor.
 * - `focusColumn` just updates focus and bumps the recency stack.
 *
 * Chat lifecycle (new):
 * - `selectChat` sets the active chat and optionally opens its active spawn.
 * - `clearChat` deselects the current chat without closing columns.
 * - `setChatState` / `setActiveSpawnId` for live updates from WS.
 *
 * Outside a `ChatProvider`, `useChat` throws — chat state is meaningless
 * without a provider and a silent stub would mask wiring bugs.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react"
import type { ReactNode } from "react"

import type { ChatState as ApiChatState } from "@/features/sessions/lib/api"

/** Maximum number of columns that can be open simultaneously. */
export const MAX_COLUMNS = 4

export interface ChatSelection {
  chatId: string
  chatState: ApiChatState
  activeSpawnId: string | null
  /** Initial prompt text carried from the empty-state composer. */
  initialPrompt: string | null
}

export interface ColumnState {
  /** Ordered list of spawn IDs shown as columns. At most {@link MAX_COLUMNS}. */
  columns: string[]
  /** The active/focused column (receives keyboard input). */
  focusedColumn: string | null
}

export interface ChatContextValue {
  /** Currently selected chat, or null for no chat / direct-spawn viewing. */
  selectedChat: ChatSelection | null
  /** Column layout state. */
  columnState: ColumnState
  /** Select a chat. Optionally carries an initial prompt for new chats. */
  selectChat: (chatId: string, chatState: ApiChatState, options?: { activeSpawnId?: string | null; initialPrompt?: string | null }) => void
  /** Clear the selected chat. */
  clearChat: () => void
  /** Update the live state of the selected chat (from WS or polling). */
  setChatState: (chatState: ApiChatState) => void
  /** Update the active spawn of the selected chat (when new spawn starts). */
  setActiveSpawnId: (spawnId: string | null) => void
  /** Open a spawn in a new column (or focus existing). */
  openSpawn: (spawnId: string) => void
  /** Close a column. */
  closeColumn: (spawnId: string) => void
  /** Set which column has focus. */
  focusColumn: (spawnId: string) => void
  /** Whether the column cap has been reached. */
  isMaxColumns: boolean
}

export const ChatContext = createContext<ChatContextValue | null>(null)

interface ChatProviderProps {
  children: ReactNode
}

/**
 * Move `spawnId` to the top of the recency stack, removing any prior entry.
 * Most-recently-focused is the first element; least-recently-focused is last.
 */
function bumpRecency(stack: string[], spawnId: string): string[] {
  return [spawnId, ...stack.filter((id) => id !== spawnId)]
}

export function ChatProvider({ children }: ChatProviderProps) {
  const [columns, setColumns] = useState<string[]>([])
  const [focusedColumn, setFocusedColumn] = useState<string | null>(null)
  const [, setRecency] = useState<string[]>([])
  const [selectedChat, setSelectedChat] = useState<ChatSelection | null>(null)

  const openSpawn = useCallback((spawnId: string) => {
    setRecency((prevRecency) => {
      let nextRecency = prevRecency
      setColumns((prevColumns) => {
        if (prevColumns.includes(spawnId)) {
          return prevColumns
        }
        if (prevColumns.length < MAX_COLUMNS) {
          return [...prevColumns, spawnId]
        }
        const evictTarget = prevRecency.at(-1) ?? prevColumns[0]
        nextRecency = prevRecency.filter((id) => id !== evictTarget)
        return [...prevColumns.filter((id) => id !== evictTarget), spawnId]
      })
      return bumpRecency(nextRecency, spawnId)
    })
    setFocusedColumn(spawnId)
  }, [])

  const closeColumn = useCallback((spawnId: string) => {
    setColumns((prev) => {
      if (!prev.includes(spawnId)) return prev
      const next = prev.filter((id) => id !== spawnId)

      setRecency((prevRecency) => {
        const nextRecency = prevRecency.filter((id) => id !== spawnId)
        setFocusedColumn((prevFocus) => {
          if (prevFocus !== spawnId) return prevFocus
          return nextRecency[0] ?? null
        })
        return nextRecency
      })

      return next
    })
  }, [])

  const focusColumn = useCallback((spawnId: string) => {
    setColumns((prev) => {
      if (!prev.includes(spawnId)) return prev
      setFocusedColumn(spawnId)
      setRecency((prevRecency) => bumpRecency(prevRecency, spawnId))
      return prev
    })
  }, [])

  const selectChat = useCallback(
    (chatId: string, chatState: ApiChatState, options?: { activeSpawnId?: string | null; initialPrompt?: string | null }) => {
      setSelectedChat({
        chatId,
        chatState,
        activeSpawnId: options?.activeSpawnId ?? null,
        initialPrompt: options?.initialPrompt ?? null,
      })
      // Note: we intentionally do NOT auto-open a column here.
      // The chat thread view renders inline in the main area.
      // Users can explicitly open spawn columns from the thread if needed.
    },
    [],
  )

  const clearChat = useCallback(() => {
    setSelectedChat(null)
  }, [])

  const setChatState = useCallback((chatState: ApiChatState) => {
    setSelectedChat((prev) => {
      if (!prev) return prev
      return { ...prev, chatState }
    })
  }, [])

  const setActiveSpawnId = useCallback((spawnId: string | null) => {
    setSelectedChat((prev) => {
      if (!prev) return prev
      return { ...prev, activeSpawnId: spawnId }
    })
  }, [])

  const value = useMemo<ChatContextValue>(
    () => ({
      selectedChat,
      columnState: { columns, focusedColumn },
      selectChat,
      clearChat,
      setChatState,
      setActiveSpawnId,
      openSpawn,
      closeColumn,
      focusColumn,
      isMaxColumns: columns.length >= MAX_COLUMNS,
    }),
    [
      selectedChat,
      columns,
      focusedColumn,
      selectChat,
      clearChat,
      setChatState,
      setActiveSpawnId,
      openSpawn,
      closeColumn,
      focusColumn,
    ],
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
