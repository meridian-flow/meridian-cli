import { Plus, ChatCircleDots, Folder } from "@phosphor-icons/react"
import type { ChatProjection } from "@/lib/api"

import { ElapsedTime } from "@/components/atoms"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { useChat } from "./ChatContext"
import { useSidebarData, type SidebarSection } from "./hooks/use-sidebar-data"

export interface ChatSidebarProps {
  chats: ChatProjection[]
  isLoading?: boolean
  error?: string | null
  className?: string
  onSelectChat: (chat: ChatProjection) => void
  onNewChat: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function stateLabel(state: ChatProjection["state"]): string {
  switch (state) {
    case "active":
      return "Active"
    case "draining":
      return "Draining"
    case "idle":
      return "Idle"
    case "closed":
      return "Closed"
  }
}

function stateTone(state: ChatProjection["state"]): string {
  switch (state) {
    case "active":
      return "bg-emerald-500"
    case "draining":
      return "bg-amber-400"
    case "idle":
      return "bg-amber-400"
    case "closed":
      return "bg-zinc-400"
  }
}

function ChatStateDot({ state }: { state: ChatProjection["state"] }) {
  return (
    <span
      className={cn("mt-1.5 inline-block size-2 shrink-0 rounded-full", stateTone(state))}
      aria-hidden
    />
  )
}

function chatTitle(chat: ChatProjection): string {
  if (chat.first_message_snippet) return chat.first_message_snippet
  if (chat.title) return chat.title
  return "Untitled chat"
}

// ---------------------------------------------------------------------------
// Single chat item
// ---------------------------------------------------------------------------

function ChatItem({
  chat,
  isSelected,
  onSelect,
}: {
  chat: ChatProjection
  isSelected: boolean
  onSelect: () => void
}) {
  const modelAlias = chat.model ?? "unknown"
  const timestamp = chat.updated_at ?? chat.created_at
  const shortId = chat.chat_id.slice(0, 8)

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "group flex w-full gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors",
          "border-transparent hover:border-border hover:bg-muted/40",
          isSelected && "border-border bg-muted/60 shadow-sm",
        )}
      >
        <ChatStateDot state={chat.state} />
        <div className="min-w-0 flex-1">
          <span className="line-clamp-2 text-sm font-medium leading-snug text-foreground">
            {chatTitle(chat)}
          </span>
          <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px] text-muted-foreground">
            <span className="font-mono">{shortId}</span>
            <span aria-hidden>&middot;</span>
            <span className="truncate">{modelAlias}</span>
            <span aria-hidden>&middot;</span>
            <span className="rounded bg-muted px-1 py-px uppercase tracking-wide">
              {stateLabel(chat.state)}
            </span>
            <span aria-hidden>&middot;</span>
            <ElapsedTime
              startedAt={new Date(timestamp)}
              format="relative"
              className="text-[10px]"
            />
          </div>
        </div>
      </button>
    </li>
  )
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({ section }: { section: SidebarSection }) {
  const isWorkGroup = section.type === "work-group"

  return (
    <div className="flex items-center gap-1.5 px-3 pb-1 pt-3 first:pt-2">
      {isWorkGroup && (
        <Folder weight="duotone" className="size-3 text-muted-foreground/50" />
      )}
      <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
        {section.label}
      </span>
      <span className="text-[10px] text-muted-foreground/40">
        {section.chats.length}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main sidebar
// ---------------------------------------------------------------------------

export function ChatSidebar({
  chats,
  isLoading = false,
  error = null,
  className,
  onSelectChat,
  onNewChat,
}: ChatSidebarProps) {
  const { selectedChat } = useChat()
  const { sections } = useSidebarData(chats, isLoading)
  const selectedChatId = selectedChat?.chat_id ?? null

  return (
    <aside
      className={cn(
        "flex h-72 w-full shrink-0 flex-col border-b border-border bg-background md:h-full md:w-80 md:border-b-0 md:border-r",
        className,
      )}
      aria-label="Chats"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Chats
          </h2>
          <p className="mt-1 text-[11px] text-muted-foreground/70">
            Conversations, not spawn lists.
          </p>
        </div>

        <Button type="button" size="sm" variant="outline" onClick={onNewChat}>
          <Plus className="mr-1.5 size-3.5" />
          New chat
        </Button>
      </div>

      <ScrollArea className="flex-1">
        {error ? (
          <div className="p-3 text-sm text-destructive">{error}</div>
        ) : isLoading ? (
          <ChatSidebarLoading />
        ) : sections.length === 0 ? (
          <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 px-4 text-center">
            <ChatCircleDots className="size-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">No chats yet.</p>
            <Button type="button" variant="secondary" size="sm" onClick={onNewChat}>
              Start a chat
            </Button>
          </div>
        ) : (
          <div className="pb-2">
            {sections.map((section) => (
              <div key={`${section.type}-${section.workId ?? section.label}`}>
                <SectionHeader section={section} />
                <ul className="flex flex-col gap-0.5 px-2">
                  {section.chats.map((chat) => (
                    <ChatItem
                      key={chat.chat_id}
                      chat={chat}
                      isSelected={selectedChatId === chat.chat_id}
                      onSelect={() => onSelectChat(chat)}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </aside>
  )
}

function ChatSidebarLoading() {
  return (
    <div className="flex flex-col gap-2 p-2">
      {Array.from({ length: 5 }).map((_, idx) => (
        <div
          key={idx}
          className="flex flex-col gap-2 rounded-lg border border-transparent px-3 py-2"
        >
          <div className="flex items-center gap-2">
            <Skeleton className="size-2 rounded-full" />
            <Skeleton className="h-4 w-44" />
          </div>
          <Skeleton className="h-3 w-28" />
        </div>
      ))}
    </div>
  )
}
