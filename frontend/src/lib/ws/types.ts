/**
 * AG-UI Stream Event types for Meridian.
 *
 * Matches the server-side Python event definitions in:
 *   meridian.lib.streaming.events + ag_ui.core.events
 *
 * D56: Uses REASONING_* (not Thinking*) for extended thinking events.
 * Discriminated union on the `type` field.
 */

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export type MessageRole = "developer" | "system" | "assistant" | "user"
export type ToolRole = "tool"

// ---------------------------------------------------------------------------
// Event type discriminator values
// ---------------------------------------------------------------------------

export const EventType = {
  // Run lifecycle
  RUN_STARTED: "RUN_STARTED",
  RUN_FINISHED: "RUN_FINISHED",
  RUN_ERROR: "RUN_ERROR",

  // Text messages
  TEXT_MESSAGE_START: "TEXT_MESSAGE_START",
  TEXT_MESSAGE_CONTENT: "TEXT_MESSAGE_CONTENT",
  TEXT_MESSAGE_END: "TEXT_MESSAGE_END",
  TEXT_MESSAGE_CHUNK: "TEXT_MESSAGE_CHUNK",

  // Reasoning messages (D56 — NOT Thinking*)
  REASONING_MESSAGE_START: "REASONING_MESSAGE_START",
  REASONING_MESSAGE_CONTENT: "REASONING_MESSAGE_CONTENT",
  REASONING_MESSAGE_END: "REASONING_MESSAGE_END",
  REASONING_MESSAGE_CHUNK: "REASONING_MESSAGE_CHUNK",
  REASONING_START: "REASONING_START",
  REASONING_END: "REASONING_END",
  REASONING_ENCRYPTED_VALUE: "REASONING_ENCRYPTED_VALUE",

  // Tool calls
  TOOL_CALL_START: "TOOL_CALL_START",
  TOOL_CALL_ARGS: "TOOL_CALL_ARGS",
  TOOL_CALL_END: "TOOL_CALL_END",
  TOOL_CALL_CHUNK: "TOOL_CALL_CHUNK",
  TOOL_CALL_RESULT: "TOOL_CALL_RESULT",

  // Steps
  STEP_STARTED: "STEP_STARTED",
  STEP_FINISHED: "STEP_FINISHED",

  // State
  STATE_SNAPSHOT: "STATE_SNAPSHOT",
  STATE_DELTA: "STATE_DELTA",
  MESSAGES_SNAPSHOT: "MESSAGES_SNAPSHOT",

  // Activity
  ACTIVITY_SNAPSHOT: "ACTIVITY_SNAPSHOT",
  ACTIVITY_DELTA: "ACTIVITY_DELTA",

  // Raw / custom
  RAW: "RAW",
  CUSTOM: "CUSTOM",
} as const

export type EventTypeName = (typeof EventType)[keyof typeof EventType]

// ---------------------------------------------------------------------------
// Base fields shared by all events
// ---------------------------------------------------------------------------

interface BaseEvent {
  timestamp?: number
  raw_event?: unknown
}

// ---------------------------------------------------------------------------
// Run lifecycle
// ---------------------------------------------------------------------------

export interface RunAgentInput {
  thread_id?: string
  run_id?: string
  state?: unknown
  messages?: unknown[]
  tools?: unknown[]
  context?: unknown[]
  forwarded_props?: Record<string, unknown>
}

export interface RunStartedEvent extends BaseEvent {
  type: typeof EventType.RUN_STARTED
  thread_id: string
  run_id: string
  parent_run_id?: string
  input?: RunAgentInput
}

export interface RunFinishedEvent extends BaseEvent {
  type: typeof EventType.RUN_FINISHED
  thread_id: string
  run_id: string
  result?: unknown
}

export interface RunErrorEvent extends BaseEvent {
  type: typeof EventType.RUN_ERROR
  message: string
  code?: string
}

// ---------------------------------------------------------------------------
// Text messages
// ---------------------------------------------------------------------------

export interface TextMessageStartEvent extends BaseEvent {
  type: typeof EventType.TEXT_MESSAGE_START
  message_id: string
  role: MessageRole
  name?: string
}

export interface TextMessageContentEvent extends BaseEvent {
  type: typeof EventType.TEXT_MESSAGE_CONTENT
  message_id: string
  delta: string
}

export interface TextMessageEndEvent extends BaseEvent {
  type: typeof EventType.TEXT_MESSAGE_END
  message_id: string
}

export interface TextMessageChunkEvent extends BaseEvent {
  type: typeof EventType.TEXT_MESSAGE_CHUNK
  message_id?: string
  role?: MessageRole
  delta?: string
  name?: string
}

// ---------------------------------------------------------------------------
// Reasoning messages (D56)
// ---------------------------------------------------------------------------

export interface ReasoningMessageStartEvent extends BaseEvent {
  type: typeof EventType.REASONING_MESSAGE_START
  message_id: string
  role: "reasoning"
}

export interface ReasoningMessageContentEvent extends BaseEvent {
  type: typeof EventType.REASONING_MESSAGE_CONTENT
  message_id: string
  delta: string
}

export interface ReasoningMessageEndEvent extends BaseEvent {
  type: typeof EventType.REASONING_MESSAGE_END
  message_id: string
}

export interface ReasoningMessageChunkEvent extends BaseEvent {
  type: typeof EventType.REASONING_MESSAGE_CHUNK
  message_id?: string
  delta?: string
}

export interface ReasoningStartEvent extends BaseEvent {
  type: typeof EventType.REASONING_START
  message_id: string
}

export interface ReasoningEndEvent extends BaseEvent {
  type: typeof EventType.REASONING_END
  message_id: string
}

export interface ReasoningEncryptedValueEvent extends BaseEvent {
  type: typeof EventType.REASONING_ENCRYPTED_VALUE
  subtype: "tool-call" | "message"
  entity_id: string
  encrypted_value: string
}

// ---------------------------------------------------------------------------
// Tool calls
// ---------------------------------------------------------------------------

export interface ToolCallStartEvent extends BaseEvent {
  type: typeof EventType.TOOL_CALL_START
  tool_call_id: string
  tool_call_name: string
  parent_message_id?: string
}

export interface ToolCallArgsEvent extends BaseEvent {
  type: typeof EventType.TOOL_CALL_ARGS
  tool_call_id: string
  delta: string
}

export interface ToolCallEndEvent extends BaseEvent {
  type: typeof EventType.TOOL_CALL_END
  tool_call_id: string
}

export interface ToolCallChunkEvent extends BaseEvent {
  type: typeof EventType.TOOL_CALL_CHUNK
  tool_call_id?: string
  tool_call_name?: string
  parent_message_id?: string
  delta?: string
}

export interface ToolCallResultEvent extends BaseEvent {
  type: typeof EventType.TOOL_CALL_RESULT
  message_id: string
  tool_call_id: string
  content: string
  role?: ToolRole
}

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

export interface StepStartedEvent extends BaseEvent {
  type: typeof EventType.STEP_STARTED
  step_name: string
}

export interface StepFinishedEvent extends BaseEvent {
  type: typeof EventType.STEP_FINISHED
  step_name: string
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

export interface StateSnapshotEvent extends BaseEvent {
  type: typeof EventType.STATE_SNAPSHOT
  snapshot: unknown
}

export interface StateDeltaEvent extends BaseEvent {
  type: typeof EventType.STATE_DELTA
  delta: unknown[]
}

export interface MessagesSnapshotEvent extends BaseEvent {
  type: typeof EventType.MESSAGES_SNAPSHOT
  messages: unknown[]
}

// ---------------------------------------------------------------------------
// Activity
// ---------------------------------------------------------------------------

export interface ActivitySnapshotEvent extends BaseEvent {
  type: typeof EventType.ACTIVITY_SNAPSHOT
  message_id: string
  activity_type: string
  content: unknown
  replace: boolean
}

export interface ActivityDeltaEvent extends BaseEvent {
  type: typeof EventType.ACTIVITY_DELTA
  message_id: string
  activity_type: string
  patch: unknown[]
}

// ---------------------------------------------------------------------------
// Raw / custom
// ---------------------------------------------------------------------------

export interface RawEvent extends BaseEvent {
  type: typeof EventType.RAW
  event: unknown
  source?: string
}

export interface CustomEvent extends BaseEvent {
  type: typeof EventType.CUSTOM
  name: string
  value: unknown
}

// ---------------------------------------------------------------------------
// Discriminated union of all server→client events
// ---------------------------------------------------------------------------

export type StreamEvent =
  // Run lifecycle
  | RunStartedEvent
  | RunFinishedEvent
  | RunErrorEvent
  // Text messages
  | TextMessageStartEvent
  | TextMessageContentEvent
  | TextMessageEndEvent
  | TextMessageChunkEvent
  // Reasoning (D56)
  | ReasoningMessageStartEvent
  | ReasoningMessageContentEvent
  | ReasoningMessageEndEvent
  | ReasoningMessageChunkEvent
  | ReasoningStartEvent
  | ReasoningEndEvent
  | ReasoningEncryptedValueEvent
  // Tool calls
  | ToolCallStartEvent
  | ToolCallArgsEvent
  | ToolCallEndEvent
  | ToolCallChunkEvent
  | ToolCallResultEvent
  // Steps
  | StepStartedEvent
  | StepFinishedEvent
  // State
  | StateSnapshotEvent
  | StateDeltaEvent
  | MessagesSnapshotEvent
  // Activity
  | ActivitySnapshotEvent
  | ActivityDeltaEvent
  // Raw / custom
  | RawEvent
  | CustomEvent

// ---------------------------------------------------------------------------
// Client → server control messages
// ---------------------------------------------------------------------------

export interface UserMessageControl {
  type: "user_message"
  text: string
}

export interface InterruptControl {
  type: "interrupt"
}

export interface CancelControl {
  type: "cancel"
}

export type ControlMessage = UserMessageControl | InterruptControl | CancelControl

// ---------------------------------------------------------------------------
// Connection capabilities (received via CUSTOM event with name="capabilities")
// ---------------------------------------------------------------------------

export interface ConnectionCapabilities {
  midTurnInjection: "queue" | "interrupt_restart" | "http_post"
  supportsSteer: boolean
  supportsInterrupt: boolean
  supportsCancel: boolean
  runtimeModelSwitch: boolean
  structuredReasoning: boolean
}

// ---------------------------------------------------------------------------
// Connection state (mirrors the server-side ConnectionState)
// ---------------------------------------------------------------------------

export type ConnectionState =
  | "created"
  | "starting"
  | "connected"
  | "stopping"
  | "stopped"
  | "failed"
