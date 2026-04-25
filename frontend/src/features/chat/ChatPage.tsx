import { useCallback } from "react"

import { cn } from "@/lib/utils"
import { useChatSessions } from "./hooks/use-chat-sessions"

import { ChatProvider, useChat } from "./ChatContext"
import { ChatMountPool } from "./ChatMountPool"
import { ChatSidebar } from "./ChatSidebar"

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

  const handleSelectChat = useCallback(
    (chat: (typeof chats)[number]) => {
      selectChat(chat)
    },
    [selectChat],
  )

  const handleNewChat = useCallback(() => {
    clearChat()
  }, [clearChat])

  // When no chat is selected, show zero-state (__new__).
  const chatId = selectedChat?.chat_id ?? "__new__"

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

      <main className="relative min-h-0 min-w-0 flex-1">
        <ChatMountPool activeChatId={chatId} />
      </main>
    </div>
  )
}
