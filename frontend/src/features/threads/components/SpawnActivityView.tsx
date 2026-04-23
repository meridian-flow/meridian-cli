import { useEffect, useMemo, useRef } from "react"

import { ErrorBoundary } from "@/components/ErrorBoundary"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { ActivityBlockData } from "@/features/activity-stream/types"

import type { AssistantTurn } from "../types"

import { TurnList } from "./TurnList"

type SpawnActivityViewProps = {
  activity: ActivityBlockData
}

function toAssistantTurn(activity: ActivityBlockData): AssistantTurn {
  let status: AssistantTurn["status"] = "pending"

  if (activity.isCancelled) {
    status = "cancelled"
  } else if (activity.error) {
    status = "error"
  } else if (activity.isStreaming) {
    status = "streaming"
  } else if (activity.items.length > 0 || activity.pendingText) {
    status = "complete"
  }

  return {
    id: activity.id,
    threadId: `thread:${activity.id}`,
    parentId: null,
    role: "assistant",
    status,
    siblingIds: [activity.id],
    siblingIndex: 0,
    createdAt: new Date(),
    error: activity.error,
    activity,
  }
}

export function SpawnActivityView({ activity }: SpawnActivityViewProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const turns = useMemo(() => [toAssistantTurn(activity)], [activity])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" })
  }, [activity.items.length, activity.pendingText])

  return (
    <ScrollArea className="h-full rounded-lg border border-border bg-card">
      <div className="space-y-4 p-4">
        <ErrorBoundary resetKeys={[activity.id]}>
          <TurnList turns={turns} />
        </ErrorBoundary>
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
