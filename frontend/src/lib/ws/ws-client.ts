/**
 * Generic WebSocket transport — no domain knowledge of spawns or AG-UI.
 *
 * Handles connection lifecycle, JSON frame send/receive, automatic reconnection,
 * and state tracking. Designed for reuse by any channel that needs reliable
 * bidirectional JSON messaging over WebSocket.
 *
 * D57: Layer 1 of the two-layer WS architecture.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type WsState = "idle" | "connecting" | "open" | "closing" | "closed"

export interface WsClientOptions {
  /** WebSocket URL to connect to. */
  url: string

  /** Protocols to pass to the WebSocket constructor. */
  protocols?: string | string[]

  /** Automatic reconnect after unexpected close? Default: true. */
  autoReconnect?: boolean

  /** Base delay (ms) before first reconnect attempt. Default: 1000. */
  reconnectBaseDelay?: number

  /** Maximum reconnect delay (ms) with exponential backoff. Default: 30000. */
  reconnectMaxDelay?: number

  /** Maximum number of consecutive reconnect attempts. 0 = unlimited. Default: 0. */
  maxReconnectAttempts?: number
}

export interface WsClientCallbacks {
  /** Called when the connection opens. */
  onOpen?: () => void

  /** Called when a parsed JSON frame arrives. */
  onMessage?: (data: unknown) => void

  /** Called on raw message that fails JSON parse (binary or malformed text). */
  onRawMessage?: (data: string | ArrayBuffer) => void

  /** Called when the connection closes (intentional or not). */
  onClose?: (code: number, reason: string, wasClean: boolean) => void

  /** Called on WebSocket error. */
  onError?: (event: Event) => void

  /** Called when state transitions. */
  onStateChange?: (state: WsState) => void
}

// ---------------------------------------------------------------------------
// WsClient
// ---------------------------------------------------------------------------

export class WsClient {
  private ws: WebSocket | null = null
  private _state: WsState = "idle"
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private intentionalClose = false

  private readonly options: Required<
    Pick<
      WsClientOptions,
      "url" | "autoReconnect" | "reconnectBaseDelay" | "reconnectMaxDelay" | "maxReconnectAttempts"
    >
  > &
    Pick<WsClientOptions, "protocols">

  private callbacks: WsClientCallbacks

  constructor(options: WsClientOptions, callbacks: WsClientCallbacks = {}) {
    this.options = {
      url: options.url,
      protocols: options.protocols,
      autoReconnect: options.autoReconnect ?? true,
      reconnectBaseDelay: options.reconnectBaseDelay ?? 1000,
      reconnectMaxDelay: options.reconnectMaxDelay ?? 30_000,
      maxReconnectAttempts: options.maxReconnectAttempts ?? 0,
    }
    this.callbacks = callbacks
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  get state(): WsState {
    return this._state
  }

  /** Connect (or reconnect) to the server. */
  connect(): void {
    if (this._state === "connecting" || this._state === "open") return

    this.intentionalClose = false
    this.clearReconnectTimer()
    this.setState("connecting")

    const ws = this.options.protocols
      ? new WebSocket(this.options.url, this.options.protocols)
      : new WebSocket(this.options.url)

    ws.onopen = () => {
      this.reconnectAttempts = 0
      this.setState("open")
      this.callbacks.onOpen?.()
    }

    ws.onmessage = (event: MessageEvent) => {
      if (typeof event.data === "string") {
        try {
          const parsed: unknown = JSON.parse(event.data)
          this.callbacks.onMessage?.(parsed)
        } catch {
          this.callbacks.onRawMessage?.(event.data)
        }
      } else {
        this.callbacks.onRawMessage?.(event.data as ArrayBuffer)
      }
    }

    ws.onclose = (event: CloseEvent) => {
      this.ws = null
      this.setState("closed")
      this.callbacks.onClose?.(event.code, event.reason, event.wasClean)

      if (!this.intentionalClose && this.options.autoReconnect) {
        this.scheduleReconnect()
      }
    }

    ws.onerror = (event: Event) => {
      this.callbacks.onError?.(event)
    }

    this.ws = ws
  }

  /** Send a JSON-serializable payload. Returns false if not connected. */
  send(data: unknown): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify(data))
    return true
  }

  /** Gracefully close the connection. Disables auto-reconnect for this close. */
  close(code?: number, reason?: string): void {
    this.intentionalClose = true
    this.clearReconnectTimer()

    if (this.ws) {
      this.setState("closing")
      this.ws.close(code ?? 1000, reason ?? "client close")
    } else {
      this.setState("closed")
    }
  }

  /** Replace callbacks (for re-binding after component remount). */
  setCallbacks(callbacks: WsClientCallbacks): void {
    this.callbacks = callbacks
  }

  /** Tear down everything — close + clear timers + null out. */
  destroy(): void {
    this.close()
    this.ws = null
  }

  // -----------------------------------------------------------------------
  // Internals
  // -----------------------------------------------------------------------

  private setState(next: WsState): void {
    if (next === this._state) return
    this._state = next
    this.callbacks.onStateChange?.(next)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private scheduleReconnect(): void {
    const max = this.options.maxReconnectAttempts
    if (max > 0 && this.reconnectAttempts >= max) return

    const delay = Math.min(
      this.options.reconnectBaseDelay * 2 ** this.reconnectAttempts,
      this.options.reconnectMaxDelay,
    )

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++
      this.connect()
    }, delay)
  }
}
