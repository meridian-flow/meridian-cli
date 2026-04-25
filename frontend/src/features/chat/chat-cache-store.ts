/**
 * LRU chat cache store — singleton, pure data, no I/O.
 *
 * Holds recently visited chat machine contexts so switching between
 * conversations is instant (no REST round-trip). Uses a JS Map for
 * insertion-order LRU semantics.
 *
 * Design decisions:
 *  - Max 100 entries. Active chat is pinned and never evicted.
 *  - The synthetic `__new__` draft slot is rejected on write.
 *  - Exposes `subscribe` / `getSnapshot` for `useSyncExternalStore`.
 *  - Snapshot identity is stable between mutations (reference equality
 *    check in React avoids unnecessary re-renders).
 */

import { useSyncExternalStore } from "react"

import type { ChatMachineContext } from "./hooks/chat-conversation-types"

// ═══════════════════════════════════════════════════════════════════
// Virtualizer state — saved scroll position & visible ranges
// ═══════════════════════════════════════════════════════════════════

export interface VirtuosoState {
  ranges: Array<{ startIndex: number; endIndex: number; size: number }>
  scrollTop: number
}

// ---------------------------------------------------------------------------
// Virtualizer state updater — updates only the virtualizer field in-place
// without triggering a full cache set (avoids notify churn during scroll).
// ---------------------------------------------------------------------------

export function updateVirtualizerState(
  chatId: string,
  state: VirtuosoState,
): void {
  const snap = chatCacheStore.getSnapshot()
  const entry = snap.get(chatId)
  if (!entry) return
  // Mutate the entry directly — snapshot identity is NOT refreshed.
  // This is intentional: scroll position is transient metadata that
  // doesn't warrant a React re-render of cache subscribers.
  entry.virtualizer = state
}

// ═══════════════════════════════════════════════════════════════════
// Cache entry
// ═══════════════════════════════════════════════════════════════════

export interface ChatCacheEntry {
  chatId: string
  machineContext: ChatMachineContext
  virtualizer: VirtuosoState | null
  updatedAt: number
}

// ═══════════════════════════════════════════════════════════════════
// Store interface
// ═══════════════════════════════════════════════════════════════════

export interface ChatCacheStore {
  /** Read a cached chat. Touches LRU (moves to most-recent). */
  get(chatId: string): ChatCacheEntry | null

  /** Write or update a cached chat. Evicts oldest non-active if over capacity. */
  set(chatId: string, entry: ChatCacheEntry): void

  /** Pin a chat as active — it can never be evicted while pinned. */
  setActive(chatId: string | null): void

  /** Remove a specific entry (e.g. after deletion). */
  delete(chatId: string): void

  /** Subscribe to mutations. Returns unsubscribe function. */
  subscribe(callback: () => void): () => void

  /** Immutable snapshot for useSyncExternalStore. */
  getSnapshot(): Map<string, ChatCacheEntry>
}

// ═══════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════

const MAX_ENTRIES = 100
const DRAFT_SLOT = "__new__"

// ═══════════════════════════════════════════════════════════════════
// Implementation
// ═══════════════════════════════════════════════════════════════════

class ChatCacheStoreImpl implements ChatCacheStore {
  private cache = new Map<string, ChatCacheEntry>()
  private activeChatId: string | null = null
  private listeners = new Set<() => void>()
  private snapshot: Map<string, ChatCacheEntry> = new Map()

  // ------------------------------------------------------------------
  // Read
  // ------------------------------------------------------------------

  get(chatId: string): ChatCacheEntry | null {
    const entry = this.cache.get(chatId)
    if (!entry) return null

    // Touch: delete + re-insert moves the key to the end (most recent)
    this.cache.delete(chatId)
    this.cache.set(chatId, entry)

    // Touch is a structural change to iteration order but not to
    // the data. We still emit so snapshot consumers see the fresh
    // reference if they care about ordering.
    this.notify()

    return entry
  }

  // ------------------------------------------------------------------
  // Write
  // ------------------------------------------------------------------

  set(chatId: string, entry: ChatCacheEntry): void {
    // Never cache the draft slot
    if (chatId === DRAFT_SLOT) return

    // Delete first so re-insert lands at the end
    this.cache.delete(chatId)
    this.cache.set(chatId, entry)

    this.evict()
    this.notify()
  }

  // ------------------------------------------------------------------
  // Active pin
  // ------------------------------------------------------------------

  setActive(chatId: string | null): void {
    this.activeChatId = chatId
    // No data changed — but consumers that derive from the active
    // pin (e.g. visual indicators) may need to re-render.
    this.notify()
  }

  // ------------------------------------------------------------------
  // Delete
  // ------------------------------------------------------------------

  delete(chatId: string): void {
    if (!this.cache.has(chatId)) return
    this.cache.delete(chatId)
    this.notify()
  }

  // ------------------------------------------------------------------
  // Subscribe / snapshot (useSyncExternalStore contract)
  // ------------------------------------------------------------------

  subscribe = (callback: () => void): (() => void) => {
    this.listeners.add(callback)
    return () => {
      this.listeners.delete(callback)
    }
  }

  getSnapshot = (): Map<string, ChatCacheEntry> => {
    return this.snapshot
  }

  // ------------------------------------------------------------------
  // Internals
  // ------------------------------------------------------------------

  /** Evict oldest entries (from the front of the Map) until at capacity. */
  private evict(): void {
    while (this.cache.size > MAX_ENTRIES) {
      let evicted = false
      for (const key of this.cache.keys()) {
        // Never evict the pinned active chat
        if (key === this.activeChatId) continue
        this.cache.delete(key)
        evicted = true
        break
      }
      // Safety valve: if every entry is pinned (shouldn't happen with
      // only one active pin) break to avoid an infinite loop.
      if (!evicted) break
    }
  }

  /** Rebuild the immutable snapshot and notify all subscribers. */
  private notify(): void {
    this.snapshot = new Map(this.cache)
    for (const cb of this.listeners) {
      cb()
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// Singleton export
// ═══════════════════════════════════════════════════════════════════

export const chatCacheStore: ChatCacheStore = new ChatCacheStoreImpl()

// ═══════════════════════════════════════════════════════════════════
// React hook
// ═══════════════════════════════════════════════════════════════════

/**
 * Subscribe to a single cache entry. Returns the entry or `null`.
 *
 * Uses `useSyncExternalStore` so the component re-renders only when
 * the cache snapshot identity changes. The selector runs on every
 * snapshot change, but React skips re-render when the returned
 * reference is the same (which it will be for untouched entries
 * since we read from the new Map copy).
 */
export function useChatCacheEntry(chatId: string | null): ChatCacheEntry | null {
  return useSyncExternalStore(
    chatCacheStore.subscribe,
    () => (chatId ? chatCacheStore.getSnapshot().get(chatId) ?? null : null),
  )
}
