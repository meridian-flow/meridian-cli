import { useCallback, useEffect, useMemo } from "react"
import {
  Spinner,
  WarningCircle,
} from "@phosphor-icons/react"
import { toast } from "sonner"

import { cn } from "@/lib/utils"
import { ConversationView } from "./components/ConversationView"
import type { ChatState as ApiChatState, ChatDetailResponse } from "@/features/sessions/lib/api"

import { useChat } from "./ChatContext"
import { ChatBanner, type ChatUIState } from "./components/ChatBanner"
import { Composer } from "./components/Composer"
import { ZeroStateGreeting } from "./components/ZeroStateGreeting"
import { useChatConversation } from "./hooks/use-chat-conversation"
import { useModelCatalog } from "./hooks/use-model-catalog"

// ---------------------------------------------------------------------------
// UI state derivation
// ---------------------------------------------------------------------------

function deriveChatUIState(
  chatId: string,
  chatDetail: ChatDetailResponse | null,
  chatState: ApiChatState | null,
): ChatUIState {
  if (chatId === "__new__") return "zero"
  if (!chatDetail) return "loading" // detail still fetching — disable composer
  if (chatDetail.launch_mode && chatDetail.launch_mode !== "app") return "readonly"
  if (chatState === "closed") return "finished"
  if (chatState === "active" || chatState === "draining") return "active"
  return "idle"
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface ChatThreadViewProps {
  chatId: string
  className?: string
}

export function ChatThreadView({ chatId, className }: ChatThreadViewProps) {
  const {
    selectedChat,
    setChatState,
    setActiveSpawnId,
    selectChat,
    clearChat,
    modelSelection,
    setModelSelection,
  } = useChat()

  const activeSpawnId = selectedChat?.active_p_id ?? null
  const initialPrompt = selectedChat?.initialPrompt ?? null

  // Fetch model catalog for the picker
  const { catalog } = useModelCatalog()

  // Seed default model selection from catalog when zero-state loads
  useEffect(() => {
    if (modelSelection === null && catalog?.defaultModel) {
      setModelSelection({
        modelId: catalog.defaultModel.modelId,
        harness: catalog.defaultModel.harness,
        displayName: catalog.defaultModel.displayName,
      })
    }
  }, [catalog, modelSelection, setModelSelection])

  const {
    entries,
    currentActivity,
    isStreaming,
    isLoading,
    isCreating,
    isSending,
    connectionState,
    controller,
    chatState: hookChatState,
    chatDetail,
    error,
    sendMessage: rawSendMessage,
    cancel,
  } = useChatConversation({
    chatId,
    activeSpawnId,
    initialPrompt,
    // Pass model selection as createChatOptions for new chats
    createChatOptions: modelSelection
      ? { model: modelSelection.modelId, harness: modelSelection.harness }
      : undefined,
    onChatCreated: (detail) => {
      selectChat(detail, { initialPrompt: null })
      setActiveSpawnId(detail.active_p_id)
    },
    onSpawnStarted: (spawnId) => {
      setActiveSpawnId(spawnId)
    },
    onChatStateChange: (state) => {
      setChatState(state)
    },
  })

  const chatState = selectedChat?.state ?? hookChatState ?? "idle"
  const uiState = deriveChatUIState(chatId, chatDetail, chatState)

  const composerDisabled = isCreating || isSending || uiState === "readonly" || uiState === "loading"
  const threadTitle = selectedChat?.title ?? "New chat"
  const threadModel = chatDetail?.model ?? selectedChat?.model ?? null
  const threadHarness = useMemo(() => {
    const spawnId = selectedChat?.active_p_id ?? null
    if (!spawnId) return null
    return chatDetail?.spawns.find((spawn) => spawn.spawn_id === spawnId)?.harness ?? null
  }, [chatDetail, selectedChat?.active_p_id])

  const handleCancel = useCallback(async () => {
    await cancel()
  }, [cancel])

  // Finished-chat fallback: redirect message to a new chat
  const sendMessage = useCallback(
    async (text: string) => {
      if (uiState === "finished") {
        toast.info("Starting a new conversation (continuation coming soon)")
        clearChat()
        // Defer so clearChat propagates and chatId becomes __new__
        setTimeout(() => {
          selectChat(
            {
              chat_id: "__new__",
              state: "idle",
              title: null,
              model: null,
              active_p_id: null,
              created_at: new Date().toISOString(),
              updated_at: null,
              harness: null,
              launch_mode: null,
              work_id: null,
              first_message_snippet: null,
            },
            { initialPrompt: text },
          )
        }, 0)
        return
      }
      await rawSendMessage(text)
    },
    [uiState, rawSendMessage, clearChat, selectChat],
  )

  // Composer placeholder per state
  const composerPlaceholder = useMemo(() => {
    switch (uiState) {
      case "zero":
        return "Type your first message..."
      case "loading":
        return "Loading..."
      case "active":
        return "Type a follow-up..."
      case "readonly":
        return "Read-only — cannot send messages"
      case "finished":
        return "Send a message to start a new chat..."
      default:
        return "Resume the conversation..."
    }
  }, [uiState])

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div
      className={cn(
        "flex min-h-0 flex-1 flex-col",
        className,
      )}
    >
      {/* Header — hide for zero state and loading (no detail yet) */}
      {uiState !== "zero" && uiState !== "loading" && (
        <div className="border-b border-border bg-background/95 px-4 py-3 backdrop-blur">
          <div className="mx-auto flex max-w-3xl items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold text-foreground">
                {threadTitle}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono uppercase tracking-wide">
                  model: {threadModel ?? "unknown"}
                </span>
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono uppercase tracking-wide">
                  harness: {threadHarness ?? "unknown"}
                </span>
              </div>
            </div>
            <div className="shrink-0 rounded-full border border-border/70 bg-muted/40 px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Chat
            </div>
          </div>
        </div>
      )}

      {/* Chat header banner */}
      <ChatBanner
        uiState={uiState}
        isStreaming={isStreaming}
        onCancel={handleCancel}
      />

      {/* Loading state — existing chat, detail not yet available */}
      {uiState === "loading" && entries.length === 0 && !currentActivity ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-2.5 text-sm text-muted-foreground">
            <Spinner className="size-4 animate-spin" />
            <span>Loading conversation...</span>
          </div>
        </div>
      ) : /* Zero state greeting OR conversation */
      uiState === "zero" && entries.length === 0 && !currentActivity ? (
        <ZeroStateGreeting />
      ) : (
        <ConversationView
          entries={entries}
          currentActivity={currentActivity}
          isConnecting={connectionState === "connecting" || isLoading}
        />
      )}

      {/* Loading indicator when creating/sending */}
      {(isCreating || isSending) && (
        <div className="flex items-center gap-2 border-t border-border/30 px-5 py-2 text-xs text-muted-foreground">
          <Spinner className="size-3.5 animate-spin" />
          <span>{isCreating ? "Starting chat..." : "Sending..."}</span>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="flex items-start gap-2 border-t border-destructive/10 bg-destructive/5 px-5 py-2 text-xs text-destructive">
          <WarningCircle className="mt-0.5 size-3.5 shrink-0" />
          <div>
            <p className="font-medium">Error</p>
            <p className="mt-0.5 text-muted-foreground">{error}</p>
          </div>
        </div>
      )}

      {/* Composer — always visible (EARS-CHAT-040) */}
      <Composer
        onSend={sendMessage}
        disabled={composerDisabled}
        isStreaming={isStreaming}
        placeholder={composerPlaceholder}
        controller={controller}
        chatId={chatId}
        modelSelection={modelSelection}
        onModelChange={setModelSelection}
        catalog={catalog}
        threadModel={threadModel}
        threadHarness={threadHarness}
      />
    </div>
  )
}
