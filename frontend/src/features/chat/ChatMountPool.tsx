/**
 * ChatMountPool — keeps one ChatThreadView shell per cached chat.
 *
 * Active shell is visible and positioned in flow. Inactive shells use
 * `visibility: hidden` + `position: absolute` to preserve their React
 * trees and virtualizer measurements without affecting layout.
 *
 * Key behaviors:
 *  - The `__new__` draft slot is always mounted (never evicted).
 *  - Cached chats get a shell as long as they exist in the cache store.
 *  - When a cache entry is evicted, its shell unmounts (React tree torn down).
 *  - When the active chat is not in the cache (cold sidebar click), the pool
 *    renders an extra shell so the main pane is never blank.
 *  - Only the active shell runs side effects (WS, fetch, polling) via
 *    the `isActive` prop passed to ChatThreadView → useChatConversation.
 */

import { useSyncExternalStore } from "react"

import { chatCacheStore } from "./chat-cache-store"
import { ChatThreadView } from "./ChatThreadView"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatMountPoolProps {
  activeChatId: string // "__new__" for draft, or real chat ID
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChatMountPool({ activeChatId }: ChatMountPoolProps) {
  const snapshot = useSyncExternalStore(
    chatCacheStore.subscribe,
    chatCacheStore.getSnapshot,
  )

  // Draft slot is always present; cached chats follow.
  // Use Array.from to get a stable iteration (Map keys).
  const cachedIds = Array.from(snapshot.keys())

  // Always render the active chat even if it hasn't been cached yet (cold load).
  const activeNotCached =
    activeChatId !== "__new__" && !cachedIds.includes(activeChatId)

  return (
    <>
      {/* Draft slot — always mounted */}
      <div
        key="__new__"
        style={{
          visibility: activeChatId === "__new__" ? "visible" : "hidden",
          position: activeChatId === "__new__" ? "relative" : "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
        }}
      >
        <ChatThreadView
          chatId="__new__"
          isActive={activeChatId === "__new__"}
          className="h-full"
        />
      </div>

      {/* Active chat if not yet in cache (cold load from sidebar) */}
      {activeNotCached && (
        <div
          key={activeChatId}
          style={{
            visibility: "visible",
            position: "relative",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
          }}
        >
          <ChatThreadView
            chatId={activeChatId}
            isActive={true}
            className="h-full"
          />
        </div>
      )}

      {/* One shell per cached chat */}
      {cachedIds.map((chatId) => (
        <div
          key={chatId}
          style={{
            visibility: chatId === activeChatId ? "visible" : "hidden",
            position: chatId === activeChatId ? "relative" : "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
          }}
        >
          <ChatThreadView
            chatId={chatId}
            isActive={chatId === activeChatId}
            className="h-full"
          />
        </div>
      ))}
    </>
  )
}
