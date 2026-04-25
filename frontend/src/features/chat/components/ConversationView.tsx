import { useEffect, useRef, type ComponentProps } from "react"
import { Ban, TriangleAlert } from "lucide-react"

import { cn } from "@/lib/utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { ActivityBlock } from "@/features/activity-stream"

import { UserTurnBubble } from "./UserTurnBubble"
import type { ConversationEntry } from "../conversation-types"

interface ConversationViewProps {
  entries: ConversationEntry[]
  currentActivity: ComponentProps<typeof ActivityBlock>["activity"] | null
  isConnecting: boolean
  className?: string
}

function hasLastUserEntry(entries: ConversationEntry[]) {
  return entries.at(-1)?.kind === "user"
}

export function ConversationView({
  entries,
  currentActivity,
  isConnecting,
  className,
}: ConversationViewProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const shouldAutoScrollRef = useRef(true)
  const lastUserCountRef = useRef(0)
  const userCount = entries.filter((entry) => entry.kind === "user").length

  useEffect(() => {
    if (hasLastUserEntry(entries) && userCount !== lastUserCountRef.current) {
      shouldAutoScrollRef.current = true
      lastUserCountRef.current = userCount
    }

    if (!shouldAutoScrollRef.current) {
      return
    }

    const scroller = scrollerRef.current
    if (!scroller) {
      return
    }

    scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" })
  }, [currentActivity, entries, userCount])

  return (
    <div
      ref={scrollerRef}
      onScroll={(event) => {
        const target = event.currentTarget
        const distanceFromBottom =
          target.scrollHeight - target.scrollTop - target.clientHeight
        shouldAutoScrollRef.current = distanceFromBottom < 64
      }}
      className={cn("min-h-0 flex-1 overflow-y-auto", className)}
    >
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-5 py-6">
        {entries.length === 0 && !currentActivity ? (
          <div className="flex min-h-[45vh] items-center justify-center text-sm text-muted-foreground">
            {isConnecting ? "Connecting..." : "Send a message to start the chat."}
          </div>
        ) : null}

        {entries.map((entry) => {
          if (entry.kind === "user") {
            return <UserTurnBubble key={entry.id} text={entry.text} />
          }

          if (entry.status === "error") {
            return (
              <div key={entry.id} className="space-y-2">
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
              <div key={entry.id} className="space-y-2 opacity-75">
                <Alert>
                  <Ban />
                  <AlertTitle>Response cancelled</AlertTitle>
                  <AlertDescription>This response was cancelled.</AlertDescription>
                </Alert>
                <ActivityBlock activity={entry.activity} defaultExpanded />
              </div>
            )
          }

          return <ActivityBlock key={entry.id} activity={entry.activity} defaultExpanded />
        })}

        {currentActivity ? (
          <ActivityBlock activity={currentActivity} defaultExpanded />
        ) : null}
      </div>
    </div>
  )
}
