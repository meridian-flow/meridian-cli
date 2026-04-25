import type { ActivityBlockData } from "@/features/activity-stream/types"

export type AssistantStatus = "streaming" | "complete" | "cancelled" | "error"

export type UserEntry = {
  kind: "user"
  id: string
  text: string
  sentAt: Date
}

export type AssistantEntry = {
  kind: "assistant"
  id: string
  activity: ActivityBlockData
  status: AssistantStatus
}

export type ConversationEntry = UserEntry | AssistantEntry
