import { forwardRef, useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react"
import { Virtuoso, type VirtuosoHandle, type StateSnapshot } from "react-virtuoso"
import { Ban, TriangleAlert } from "lucide-react"

import { cn } from "@/lib/utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { ActivityBlock } from "@/features/activity-stream"

import { UserTurnBubble } from "./UserTurnBubble"
import type { ConversationEntry, UserEntry, AssistantEntry } from "../conversation-types"
import type { ActivityBlockData } from "@/features/activity-stream/types"
import type { VirtuosoState } from "../chat-cache-store"

// ---------------------------------------------------------------------------
// Virtual item model — merges frozen entries + live streaming activity
// ---------------------------------------------------------------------------

type VirtualItem =
  | { kind: "user"; id: string; entry: UserEntry }
  | { kind: "assistant"; id: string; entry: AssistantEntry }
  | { kind: "live"; id: string; activity: ActivityBlockData }

function mergeVirtualItems(
  entries: ConversationEntry[],
  currentActivity: ActivityBlockData | null,
): VirtualItem[] {
  const items: VirtualItem[] = entries.map((entry) =>
    entry.kind === "user"
      ? { kind: "user" as const, id: entry.id, entry }
      : { kind: "assistant" as const, id: entry.id, entry },
  )

  if (currentActivity) {
    items.push({ kind: "live", id: currentActivity.id, activity: currentActivity })
  }

  return items
}

// ---------------------------------------------------------------------------
// Custom Virtuoso components — preserve the original layout classes
// ---------------------------------------------------------------------------

const Scroller = forwardRef<HTMLDivElement, ComponentProps<"div">>(
  function Scroller(props, ref) {
    return <div {...props} ref={ref} />
  },
)

const List = forwardRef<HTMLDivElement, ComponentProps<"div">>(
  function List(props, ref) {
    return (
      <div
        {...props}
        ref={ref}
        className="mx-auto flex w-full max-w-3xl flex-col px-5 py-6"
      />
    )
  },
)

function Item(props: ComponentProps<"div">) {
  return <div {...props} className="pb-5" />
}

// ---------------------------------------------------------------------------
// ConversationView
// ---------------------------------------------------------------------------

interface ConversationViewProps {
  entries: ConversationEntry[]
  currentActivity: ComponentProps<typeof ActivityBlock>["activity"] | null
  isConnecting: boolean
  className?: string
  /** Saved virtualizer snapshot for instant scroll restoration. */
  initialVirtuosoState?: VirtuosoState | null
  /** Called on unmount to persist the virtualizer scroll position. */
  onSaveVirtuosoState?: (state: VirtuosoState) => void
}

export function ConversationView({
  entries,
  currentActivity,
  isConnecting,
  className,
  initialVirtuosoState,
  onSaveVirtuosoState,
}: ConversationViewProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const [isAtBottom, setIsAtBottom] = useState(true)

  const virtualItems = useMemo(
    () => mergeVirtualItems(entries, currentActivity),
    [entries, currentActivity],
  )

  // When the user sends a new message, force-scroll to the bottom so they
  // see their own message and the upcoming assistant response — even if
  // they had previously scrolled up.
  const prevEntryCountRef = useRef(entries.length)
  useEffect(() => {
    const prevCount = prevEntryCountRef.current
    prevEntryCountRef.current = entries.length

    if (entries.length > prevCount) {
      const lastEntry = entries[entries.length - 1]
      if (lastEntry?.kind === "user") {
        setIsAtBottom(true)
        // Schedule after Virtuoso has measured the new item
        requestAnimationFrame(() => {
          virtuosoRef.current?.scrollToIndex({
            index: virtualItems.length - 1,
            align: "end",
            behavior: "smooth",
          })
        })
      }
    }
  }, [entries, virtualItems.length])

  // followOutput controls auto-scroll during streaming.
  // "smooth" when at bottom → auto-scroll to new content.
  // false when user has scrolled away → don't hijack.
  const followOutput = useCallback(
    () => (isAtBottom ? "smooth" : false) as "smooth" | false,
    [isAtBottom],
  )

  const renderItem = useCallback((_index: number, item: VirtualItem) => {
    if (item.kind === "user") {
      return <UserTurnBubble text={item.entry.text} />
    }

    if (item.kind === "live") {
      return <ActivityBlock activity={item.activity} defaultExpanded />
    }

    // Assistant entry — frozen turn
    const entry = item.entry

    if (entry.status === "error") {
      return (
        <div className="space-y-2">
          <Alert variant="destructive">
            <TriangleAlert />
            <AlertTitle>Response failed</AlertTitle>
            <AlertDescription>
              {entry.activity.error ?? "An unexpected error interrupted this response."}
            </AlertDescription>
          </Alert>
          <ActivityBlock activity={entry.activity} defaultExpanded />
        </div>
      )
    }

    if (entry.status === "cancelled") {
      return (
        <div className="space-y-2 opacity-75">
          <Alert>
            <Ban />
            <AlertTitle>Response cancelled</AlertTitle>
            <AlertDescription>This response was cancelled.</AlertDescription>
          </Alert>
          <ActivityBlock activity={entry.activity} defaultExpanded />
        </div>
      )
    }

    return <ActivityBlock activity={entry.activity} defaultExpanded />
  }, [])

  const computeItemKey = useCallback((_index: number, item: VirtualItem) => item.id, [])

  // Save virtualizer scroll position on unmount for cache restoration.
  // Ref-capture the callback so the cleanup closure always has the latest.
  const onSaveRef = useRef(onSaveVirtuosoState)
  onSaveRef.current = onSaveVirtuosoState

  useEffect(() => {
    return () => {
      const ref = virtuosoRef.current
      const saveFn = onSaveRef.current
      if (!ref || !saveFn) return
      ref.getState((snapshot: StateSnapshot) => {
        saveFn({
          ranges: snapshot.ranges,
          scrollTop: snapshot.scrollTop,
        })
      })
    }
  }, [])

  // Convert the cache VirtuosoState to Virtuoso's StateSnapshot for restore.
  // Memoize on the reference so we only build it once per mount.
  const restoreState = useMemo<StateSnapshot | undefined>(() => {
    if (!initialVirtuosoState) return undefined
    return {
      ranges: initialVirtuosoState.ranges,
      scrollTop: initialVirtuosoState.scrollTop,
    }
  }, [initialVirtuosoState])

  // Empty state — no entries and no live activity
  if (virtualItems.length === 0) {
    return (
      <div className={cn("min-h-0 flex-1 overflow-y-auto", className)}>
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-5 py-6">
          <div className="flex min-h-[45vh] items-center justify-center text-sm text-muted-foreground">
            {isConnecting ? "Connecting..." : "Send a message to start the chat."}
          </div>
        </div>
      </div>
    )
  }

  return (
    <Virtuoso
      ref={virtuosoRef}
      data={virtualItems}
      itemContent={renderItem}
      computeItemKey={computeItemKey}
      followOutput={followOutput}
      atBottomStateChange={setIsAtBottom}
      atBottomThreshold={64}
      increaseViewportBy={200}
      restoreStateFrom={restoreState}
      components={{ Scroller, List, Item }}
      className={cn("min-h-0 flex-1 overflow-y-auto", className)}
    />
  )
}
