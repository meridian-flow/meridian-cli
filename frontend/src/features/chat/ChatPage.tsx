import { useCallback, useEffect, useRef, useState } from "react"

import { cn } from "@/lib/utils"
import { useChatSessions } from "./hooks/use-chat-sessions"

import { ChatProvider, useChat } from "./ChatContext"
import { ChatSidebar } from "./ChatSidebar"
import { ChatThreadView } from "./ChatThreadView"

export interface ChatPageProps {
  className?: string
}

export function ChatPage(props: ChatPageProps) {
  return (
    <ChatProvider>
      <ChatPageContent {...props} />
    </ChatProvider>
  )
}

function ChatPageContent({ className }: ChatPageProps) {
  const { chats, isLoading, error } = useChatSessions()
  const { selectedChat, selectChat, clearChat } = useChat()
  const [draftMode, setDraftMode] = useState(false)
  const didInitializeSelection = useRef(false)
  // Track user-initiated new-chat intent so auto-selection effects don't race
  const userInitiatedDraft = useRef(false)

  const handleSelectChat = useCallback(
    (chat: (typeof chats)[number]) => {
      userInitiatedDraft.current = false
      selectChat(chat)
      setDraftMode(false)
      didInitializeSelection.current = true
    },
    [selectChat],
  )

  const handleNewChat = useCallback(() => {
    userInitiatedDraft.current = true
    clearChat()
    setDraftMode(true)
    didInitializeSelection.current = true
  }, [clearChat])

  // Clear draftMode when a real chat is selected (either from sidebar or after
  // createChat succeeds and onChatCreated calls selectChat with the new chat).
  // The __new__ synthetic ID is excluded so the finished-chat fallback doesn't
  // prematurely exit draft mode.
  useEffect(() => {
    if (selectedChat && selectedChat.chat_id !== "__new__") {
      userInitiatedDraft.current = false
      setDraftMode(false)
    }
  }, [selectedChat])

  // Always start in zero state (new chat). Users pick a chat from the sidebar
  // if they want to continue one — we don't auto-select the first chat.
  useEffect(() => {
    if (isLoading || didInitializeSelection.current || draftMode) return
    if (selectedChat) {
      didInitializeSelection.current = true
      return
    }

    clearChat()
    setDraftMode(true)
    didInitializeSelection.current = true
  }, [isLoading, selectedChat, clearChat, draftMode])

  // If the selected chat disappears from the list (e.g. deleted server-side),
  // fall back — but never override an active user-initiated draft.
  useEffect(() => {
    if (isLoading || draftMode || !selectedChat) return
    // Synthetic __new__ chat is never in the server list — don't treat that as
    // "chat disappeared". The draftMode guard above already covers this, but
    // belt-and-suspenders for the finished-chat fallback path.
    if (selectedChat.chat_id === "__new__") return
    const stillExists = chats.some((chat) => chat.chat_id === selectedChat.chat_id)
    if (stillExists) return

    clearChat()
    setDraftMode(true)
  }, [isLoading, draftMode, selectedChat, chats, clearChat])

  return (
    <div
      className={cn(
        "flex h-full min-h-0 w-full flex-col overflow-hidden bg-background md:flex-row",
        className,
      )}
    >
      <ChatSidebar
        chats={chats}
        isLoading={isLoading}
        error={error}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
      />

      <main className="min-h-0 min-w-0 flex-1">
        <ChatThreadView chatId={draftMode ? "__new__" : (selectedChat?.chat_id ?? "__new__")} className="h-full" />
      </main>
    </div>
  )
}
