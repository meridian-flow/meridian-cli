/**
 * WebSocket client barrel export.
 *
 * Two-layer architecture (D57):
 *   Layer 1: WsClient — generic transport, no domain knowledge
 *   Layer 2: SpawnChannel — spawn-specific AG-UI logic
 */

export { WsClient } from "./ws-client"
export type { WsState, WsClientOptions, WsClientCallbacks } from "./ws-client"

export { SpawnChannel, isEventType } from "./spawn-channel"
export type { SpawnChannelCallbacks, SpawnChannelOptions } from "./spawn-channel"

export { EventType } from "./types"
export type {
  StreamEvent,
  ControlMessage,
  ConnectionCapabilities,
  ConnectionState,
  EventTypeName,
  MessageRole,
  // Run lifecycle
  RunStartedEvent,
  RunFinishedEvent,
  RunErrorEvent,
  RunAgentInput,
  // Text messages
  TextMessageStartEvent,
  TextMessageContentEvent,
  TextMessageEndEvent,
  TextMessageChunkEvent,
  // Reasoning (D56)
  ReasoningMessageStartEvent,
  ReasoningMessageContentEvent,
  ReasoningMessageEndEvent,
  ReasoningMessageChunkEvent,
  ReasoningStartEvent,
  ReasoningEndEvent,
  ReasoningEncryptedValueEvent,
  // Tool calls
  ToolCallStartEvent,
  ToolCallArgsEvent,
  ToolCallEndEvent,
  ToolCallChunkEvent,
  ToolCallResultEvent,
  // Steps
  StepStartedEvent,
  StepFinishedEvent,
  // State
  StateSnapshotEvent,
  StateDeltaEvent,
  MessagesSnapshotEvent,
  // Activity
  ActivitySnapshotEvent,
  ActivityDeltaEvent,
  // Raw / custom
  RawEvent,
  CustomEvent,
  // Control
  UserMessageControl,
  InterruptControl,
  CancelControl,
} from "./types"
