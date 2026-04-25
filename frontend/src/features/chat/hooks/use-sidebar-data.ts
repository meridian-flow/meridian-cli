/**
 * useSidebarData — combines chat projections with work items for grouped sidebar display.
 *
 * Produces two sections:
 * 1. Active — chats with state active | idle | draining
 * 2. Latest — closed chats, grouped by work item (with an "ungrouped" bucket)
 */

import { useCallback, useEffect, useRef, useState, useMemo } from "react"

import {
  fetchWorkItems,
  type ChatProjection,
  type WorkProjection,
} from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SidebarSection {
  type: "active" | "work-group" | "ungrouped"
  label: string
  workId?: string
  chats: ChatProjection[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isLiveState(state: ChatProjection["state"]): boolean {
  return state === "active" || state === "idle" || state === "draining"
}

function byMostRecent(a: ChatProjection, b: ChatProjection): number {
  const aTime = a.updated_at ?? a.created_at
  const bTime = b.updated_at ?? b.created_at
  return bTime.localeCompare(aTime)
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseSidebarDataResult {
  sections: SidebarSection[]
  isLoading: boolean
}

export function useSidebarData(
  chats: ChatProjection[],
  chatsLoading: boolean,
): UseSidebarDataResult {
  const [workItems, setWorkItems] = useState<WorkProjection[]>([])
  const [workLoading, setWorkLoading] = useState(true)
  const reqIdRef = useRef(0)

  const loadWork = useCallback(async () => {
    const reqId = ++reqIdRef.current
    try {
      const resp = await fetchWorkItems()
      if (reqId !== reqIdRef.current) return
      setWorkItems(resp.items)
    } catch {
      // Work items are optional enrichment — degrade gracefully
      if (reqId !== reqIdRef.current) return
      setWorkItems([])
    } finally {
      if (reqId === reqIdRef.current) setWorkLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadWork()
  }, [loadWork])

  const sections = useMemo<SidebarSection[]>(() => {
    const active: ChatProjection[] = []
    const closed: ChatProjection[] = []

    for (const chat of chats) {
      if (isLiveState(chat.state)) {
        active.push(chat)
      } else {
        closed.push(chat)
      }
    }

    // Sort each bucket by most-recent first
    active.sort(byMostRecent)
    closed.sort(byMostRecent)

    const result: SidebarSection[] = []

    // Active section (only if non-empty)
    if (active.length > 0) {
      result.push({
        type: "active",
        label: "Active",
        chats: active,
      })
    }

    // Closed chats — group by work_id
    if (closed.length > 0) {
      const workMap = new Map(workItems.map((w) => [w.work_id, w]))
      const grouped = new Map<string, ChatProjection[]>()
      const ungrouped: ChatProjection[] = []

      for (const chat of closed) {
        if (chat.work_id) {
          const list = grouped.get(chat.work_id)
          if (list) {
            list.push(chat)
          } else {
            grouped.set(chat.work_id, [chat])
          }
        } else {
          ungrouped.push(chat)
        }
      }

      // Work groups first, ordered by the most recent chat in each group
      const groupEntries = [...grouped.entries()].sort(([, aChats], [, bChats]) => {
        const aTime = aChats[0].updated_at ?? aChats[0].created_at
        const bTime = bChats[0].updated_at ?? bChats[0].created_at
        return bTime.localeCompare(aTime)
      })

      for (const [workId, groupChats] of groupEntries) {
        const work = workMap.get(workId)
        result.push({
          type: "work-group",
          label: work?.name ?? workId.slice(0, 8),
          workId,
          chats: groupChats,
        })
      }

      // Ungrouped closed chats at the end
      if (ungrouped.length > 0) {
        result.push({
          type: "ungrouped",
          label: "Latest",
          chats: ungrouped,
        })
      }
    }

    return result
  }, [chats, workItems])

  return {
    sections,
    isLoading: chatsLoading || workLoading,
  }
}
