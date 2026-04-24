/**
 * Spawn-specific AG-UI channel — domain layer atop the generic WsClient.
 *
 * Responsibilities:
 *   - Construct the spawn-specific WS URL from page origin + spawn ID
 *   - Parse incoming JSON frames as StreamEvent (discriminated on `type`)
 *   - Send typed outbound control frames (user_message, interrupt, cancel)
 *   - Track spawn capabilities received via CUSTOM events
 *
 * D57: Layer 2 of the two-layer WS architecture.
 */

import { WsClient, type WsState } from "./ws-client"
import {
  EventType,
  type StreamEvent,
  type ControlMessage,
  type ConnectionCapabilities,
  type EventTypeName,
} from "./types"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SpawnChannelCallbacks {
  /** Called when the WS connection to the spawn opens. */
  onOpen?: () => void

  /** Called on every parsed AG-UI stream event. */
  onEvent?: (event: StreamEvent) => void

  /** Called when connection capabilities arrive (CUSTOM name="capabilities"). */
  onCapabilities?: (caps: ConnectionCapabilities) => void

  /** Called when the connection closes. */
  onClose?: (code: number, reason: string) => void

  /** Called on connection error. */
  onError?: (event: Event) => void

  /** Called when the transport state transitions. */
  onStateChange?: (state: WsState) => void
}

export interface SpawnChannelOptions {
  /** Override the WS base URL. Defaults to deriving from `window.location`. */
  baseUrl?: string

  /** Auto-reconnect on unexpected close? Default: false for spawn channels
   *  (spawns are ephemeral — reconnecting to a finished spawn makes no sense). */
  autoReconnect?: boolean
}

// ---------------------------------------------------------------------------
// URL builder
// ---------------------------------------------------------------------------

function buildSpawnWsUrl(spawnId: string, baseUrl?: string): string {
  if (baseUrl) {
    const base = baseUrl.replace(/\/$/, "")
    return `${base}/api/spawns/${spawnId}/ws`
  }

  // Derive from current page origin
  const loc = window.location
  const protocol = loc.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${loc.host}/api/spawns/${spawnId}/ws`
}

// ---------------------------------------------------------------------------
// Event validation
// ---------------------------------------------------------------------------

const KNOWN_EVENT_TYPES = new Set<string>(Object.values(EventType))

function isStreamEvent(data: unknown): data is StreamEvent {
  if (typeof data !== "object" || data === null) return false
  const obj = data as Record<string, unknown>
  return typeof obj.type === "string" && KNOWN_EVENT_TYPES.has(obj.type)
}

// ---------------------------------------------------------------------------
// SpawnChannel
// ---------------------------------------------------------------------------

export class SpawnChannel {
  readonly spawnId: string
  private client: WsClient
  private callbacks: SpawnChannelCallbacks
  private _capabilities: ConnectionCapabilities | null = null
  private _runId: string | null = null

  constructor(
    spawnId: string,
    callbacks: SpawnChannelCallbacks = {},
    options: SpawnChannelOptions = {},
  ) {
    this.spawnId = spawnId
    this.callbacks = callbacks

    const url = buildSpawnWsUrl(spawnId, options.baseUrl)

    this.client = new WsClient(
      {
        url,
        autoReconnect: options.autoReconnect ?? false,
      },
      {
        onOpen: () => this.callbacks.onOpen?.(),
        onMessage: (data) => this.handleMessage(data),
        onClose: (code, reason) => this.callbacks.onClose?.(code, reason),
        onError: (event) => this.callbacks.onError?.(event),
        onStateChange: (state) => this.callbacks.onStateChange?.(state),
      },
    )
  }

  // -----------------------------------------------------------------------
  // Public API
  // -----------------------------------------------------------------------

  /** Current transport state. */
  get state(): WsState {
    return this.client.state
  }

  /** Harness capabilities, available after the CUSTOM event arrives. */
  get capabilities(): ConnectionCapabilities | null {
    return this._capabilities
  }

  /** Current run ID, set when RUN_STARTED arrives. */
  get runId(): string | null {
    return this._runId
  }

  /** Open the WebSocket connection to this spawn. */
  connect(): void {
    this.client.connect()
  }

  /** Send a user message to the spawn. */
  sendMessage(text: string): boolean {
    return this.sendControl({ type: "user_message", text })
  }

  /** Request an interrupt of the current turn. */
  interrupt(): boolean {
    return this.sendControl({ type: "interrupt" })
  }

  /** Request cancellation of the spawn. */
  cancel(): boolean {
    return this.sendControl({ type: "cancel" })
  }

  /** Close the channel gracefully. */
  close(): void {
    this.client.close()
  }

  /** Tear down and release resources. */
  destroy(): void {
    this.client.destroy()
  }

  /** Replace callbacks (for re-binding on React re-render). */
  setCallbacks(callbacks: SpawnChannelCallbacks): void {
    this.callbacks = callbacks
  }

  // -----------------------------------------------------------------------
  // Internals
  // -----------------------------------------------------------------------

  private sendControl(msg: ControlMessage): boolean {
    return this.client.send(msg)
  }

  private handleMessage(data: unknown): void {
    // Handle transport-level keepalive before AG-UI event dispatch.
    // Server sends {type:"keepalive"} every 30s; we must respond with {type:"pong"}
    // within 90s or the connection is closed as stale.
    if (
      typeof data === "object" &&
      data !== null &&
      (data as { type?: string }).type === "keepalive"
    ) {
      this.client.send({ type: "pong" })
      return
    }

    if (!isStreamEvent(data)) {
      // Unknown frame shape — silently drop (or log in dev)
      if (import.meta.env.DEV) {
        console.warn("[SpawnChannel] Unknown frame:", data)
      }
      return
    }

    const event = data as StreamEvent

    // Extract capabilities from CUSTOM events
    if (
      event.type === EventType.CUSTOM &&
      (event as { name: string }).name === "capabilities"
    ) {
      this._capabilities = (event as { value: ConnectionCapabilities }).value
      this.callbacks.onCapabilities?.(this._capabilities)
    }

    // Track run ID
    if (event.type === EventType.RUN_STARTED) {
      this._runId = (event as { runId: string }).runId
    }

    this.callbacks.onEvent?.(event)
  }
}

// ---------------------------------------------------------------------------
// Convenience: typed event narrowing helpers
// ---------------------------------------------------------------------------

export function isEventType<T extends EventTypeName>(
  event: StreamEvent,
  type: T,
): event is Extract<StreamEvent, { type: T }> {
  return event.type === type
}
