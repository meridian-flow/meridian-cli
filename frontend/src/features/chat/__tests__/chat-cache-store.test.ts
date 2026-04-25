import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ChatCacheEntry } from "../chat-cache-store"
import type { ChatMachineContext } from "../hooks/chat-conversation-types"

type ChatCacheStoreModule = typeof import("../chat-cache-store")

beforeEach(() => {
  vi.resetModules()
})

async function loadStore(): Promise<ChatCacheStoreModule> {
  return import("../chat-cache-store")
}

function makeContext(chatId: string): ChatMachineContext {
  return {
    chatId,
    phase: "idle",
    accessMode: "interactive",
    chatDetail: null,
    chatState: null,
    activeSpawnId: null,
    entries: [],
    current: null,
    turnSeq: 0,
    transportState: "closed",
    requestGeneration: 0,
    streamGeneration: 0,
    createGeneration: 0,
    bootstrap: {
      detailLoaded: false,
      historyLoaded: false,
      detailPayload: null,
      historyPayload: null,
    },
    pendingOp: null,
    error: null,
    terminalSeen: false,
    cacheSnapshot: null,
  }
}

function makeEntry(chatId: string, updatedAt: number): ChatCacheEntry {
  return {
    chatId,
    machineContext: makeContext(chatId),
    virtualizer: null,
    updatedAt,
  }
}

function seedEntries(
  set: ChatCacheStoreModule["chatCacheStore"]["set"],
  count: number,
  startIndex = 0,
): void {
  for (let index = startIndex; index < startIndex + count; index += 1) {
    const chatId = `chat-${index}`
    set(chatId, makeEntry(chatId, index))
  }
}

describe("chatCacheStore", () => {
  it("evicts the oldest non-active entry first when capacity is exceeded", async () => {
    const { chatCacheStore } = await loadStore()

    seedEntries(chatCacheStore.set.bind(chatCacheStore), 100)
    chatCacheStore.set("chat-100", makeEntry("chat-100", 100))

    const snapshot = chatCacheStore.getSnapshot()

    expect(snapshot.size).toBe(100)
    expect(snapshot.has("chat-0")).toBe(false)
    expect(snapshot.has("chat-1")).toBe(true)
    expect(snapshot.has("chat-100")).toBe(true)
    expect(Array.from(snapshot.keys())[0]).toBe("chat-1")
  })

  it("keeps the active chat pinned even when it is the oldest entry", async () => {
    const { chatCacheStore } = await loadStore()

    chatCacheStore.setActive("chat-0")
    seedEntries(chatCacheStore.set.bind(chatCacheStore), 100)
    chatCacheStore.set("chat-100", makeEntry("chat-100", 100))

    const snapshot = chatCacheStore.getSnapshot()

    expect(snapshot.size).toBe(100)
    expect(snapshot.has("chat-0")).toBe(true)
    expect(snapshot.has("chat-1")).toBe(false)
    expect(snapshot.has("chat-100")).toBe(true)
    expect(Array.from(snapshot.keys())[0]).toBe("chat-0")
  })

  it("rejects the draft slot on write", async () => {
    const { chatCacheStore } = await loadStore()

    chatCacheStore.set("__new__", makeEntry("__new__", 0))

    const snapshot = chatCacheStore.getSnapshot()

    expect(snapshot.size).toBe(0)
    expect(snapshot.has("__new__")).toBe(false)
  })

  it("notifies subscribers on set, delete, and setActive mutations", async () => {
    const { chatCacheStore } = await loadStore()
    const callback = vi.fn()

    const unsubscribe = chatCacheStore.subscribe(callback)

    chatCacheStore.set("chat-0", makeEntry("chat-0", 0))
    expect(callback).toHaveBeenCalledTimes(1)

    chatCacheStore.setActive("chat-0")
    expect(callback).toHaveBeenCalledTimes(2)

    chatCacheStore.delete("chat-0")
    expect(callback).toHaveBeenCalledTimes(3)

    unsubscribe()
    chatCacheStore.set("chat-1", makeEntry("chat-1", 1))
    expect(callback).toHaveBeenCalledTimes(3)
  })

  it("moves a read entry to the most recent position", async () => {
    const { chatCacheStore } = await loadStore()

    seedEntries(chatCacheStore.set.bind(chatCacheStore), 3)

    expect(Array.from(chatCacheStore.getSnapshot().keys())).toEqual([
      "chat-0",
      "chat-1",
      "chat-2",
    ])

    const entry = chatCacheStore.get("chat-0")

    expect(entry?.chatId).toBe("chat-0")
    expect(Array.from(chatCacheStore.getSnapshot().keys())).toEqual([
      "chat-1",
      "chat-2",
      "chat-0",
    ])
  })
})
