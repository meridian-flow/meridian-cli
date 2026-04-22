// Barrel exports for the threads feature

// Domain types
export type {
  ActivePath,
  AssistantTurn,
  BlockStatus,
  BlockType,
  SystemTurn,
  Thread,
  ThreadTurn,
  TurnBlock,
  TurnRole,
  TurnStatus,
  UserTurn,
} from "./types"

// Transport types
export type {
  BackendTurn,
  BackendTurnBlock,
  PaginatedTurnsResponse,
  StreamController,
  ThreadStoreInterface,
  ThreadStoreState,
} from "./transport-types"

// Mapper
export { mapBlocksToActivityItems, mapTurnToViewModel, mapTurnsToViewModels } from "./turn-mapper"

// Components
export { ImageBlock } from "./components/ImageBlock"
export { ReferenceBlock } from "./components/ReferenceBlock"
export { SiblingNav } from "./components/SiblingNav"
export { PendingTurn } from "./components/PendingTurn"
export { TurnList } from "./components/TurnList"
export { TurnRow } from "./components/TurnRow"
export { TurnStatusBanner } from "./components/TurnStatusBanner"
export { UserBubble } from "./components/UserBubble"

// Storybook simulator
export type { ThreadSimulator, ThreadSimulatorConfig } from "./hooks/use-thread-simulator"
export { useThreadSimulator } from "./hooks/use-thread-simulator"
export { SpawnActivityView } from "./components/SpawnActivityView"
