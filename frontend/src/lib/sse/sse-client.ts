/**
 * Shared SSE singleton for `/api/stream`.
 *
 * Multiple React hooks subscribe through this single EventSource — we don't
 * want each hook spinning up its own connection. Lifecycle is ref-counted:
 * the first subscriber triggers connect; when the last unsubscribes, the
 * connection is torn down.
 *
 * Reconnect uses exponential backoff (1s → 2s → 4s … capped at 30s) and
 * resets on a successful open. Status is exposed so UI can show a
 * connection indicator.
 */

export type SSEConnectionStatus = 'connecting' | 'connected' | 'disconnected'

export type SSEListener = (event: MessageEvent) => void
type StatusListener = (status: SSEConnectionStatus) => void

const STREAM_URL = '/api/stream'
const BASE_RETRY_MS = 1_000
const MAX_RETRY_MS = 30_000

export class SSEClient {
  private eventSource: EventSource | null = null
  private listeners = new Set<SSEListener>()
  private statusListeners = new Set<StatusListener>()
  private retryCount = 0
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private status: SSEConnectionStatus = 'disconnected'
  private url: string

  constructor(url: string = STREAM_URL) {
    this.url = url
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  /** Subscribe to every SSE message. Returns an unsubscribe function. */
  subscribe(listener: SSEListener): () => void {
    this.listeners.add(listener)
    if (this.listeners.size === 1) {
      this.connect()
    }
    return () => {
      this.listeners.delete(listener)
      if (this.listeners.size === 0) {
        this.disconnect()
      }
    }
  }

  /** Observe connection-status transitions. Returns an unsubscribe function. */
  onStatusChange(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    return () => {
      this.statusListeners.delete(listener)
    }
  }

  getStatus(): SSEConnectionStatus {
    return this.status
  }

  /** Force-connect (normally driven by subscribe). Idempotent. */
  connect(): void {
    if (this.eventSource) return
    this.clearRetryTimer()
    this.setStatus('connecting')

    let source: EventSource
    try {
      source = new EventSource(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }

    source.onopen = () => {
      this.retryCount = 0
      this.setStatus('connected')
    }

    source.onmessage = (event: MessageEvent) => {
      this.dispatch(event)
    }

    // The backend emits named SSE events (e.g. `spawn.created`,
    // `work.archived`), which `onmessage` does NOT receive — that handler
    // only fires for unnamed `message` events. Wire each named event
    // explicitly so subscribers see the full stream.
    const namedEvents = [
      'connected',
      'keepalive',
      'spawn.created',
      'spawn.finalized',
      'spawn.archived',
      'work.created',
      'work.archived',
      'work.active_changed',
    ] as const
    for (const name of namedEvents) {
      source.addEventListener(name, (event) => {
        this.dispatch(event as MessageEvent)
      })
    }

    source.onerror = () => {
      // EventSource auto-reconnects on some browsers, but behavior is
      // inconsistent. We close and schedule our own backoff to get
      // deterministic timing and a testable status machine.
      this.teardownSource()
      this.setStatus('disconnected')
      this.scheduleReconnect()
    }

    this.eventSource = source
  }

  /** Force-disconnect (normally driven by last unsubscribe). Idempotent. */
  disconnect(): void {
    this.clearRetryTimer()
    this.teardownSource()
    this.retryCount = 0
    this.setStatus('disconnected')
  }

  // -----------------------------------------------------------------------
  // Internals
  // -----------------------------------------------------------------------

  private dispatch(event: MessageEvent): void {
    for (const listener of this.listeners) {
      try {
        listener(event)
      } catch (err) {
        // Prevent one bad listener from taking down the broadcast.
        // eslint-disable-next-line no-console
        console.error('[sse] listener threw', err)
      }
    }
  }

  private teardownSource(): void {
    if (this.eventSource) {
      this.eventSource.onopen = null
      this.eventSource.onmessage = null
      this.eventSource.onerror = null
      this.eventSource.close()
      this.eventSource = null
    }
  }

  private clearRetryTimer(): void {
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
  }

  private scheduleReconnect(): void {
    if (this.listeners.size === 0) return
    const delay = Math.min(BASE_RETRY_MS * 2 ** this.retryCount, MAX_RETRY_MS)
    this.retryCount += 1
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      this.connect()
    }, delay)
  }

  private setStatus(next: SSEConnectionStatus): void {
    if (next === this.status) return
    this.status = next
    for (const listener of this.statusListeners) {
      try {
        listener(next)
      } catch {
        // swallow — status listeners must not derail other listeners
      }
    }
  }
}

export const sseClient = new SSEClient()
