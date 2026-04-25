// ═══════════════════════════════════════════════════════════════════
// Transport types — stream controller interface
//
// Transport-neutral abstraction so view components (Composer, etc.)
// don't couple to a specific WebSocket or channel implementation.
// ═══════════════════════════════════════════════════════════════════

/**
 * Transport-neutral controller for spawn interaction.
 *
 * Abstracts the WebSocket channel so view components (Composer, etc.)
 * don't depend on SpawnChannel directly. Implementations:
 * - Production: wraps SpawnChannel methods
 * - Testing: mock implementation for Storybook
 */
export type StreamController = {
  /** Send a user message to the active spawn. Returns true if sent. */
  sendMessage: (text: string) => boolean
  /** Request the harness to interrupt the current turn. Returns true if sent. */
  interrupt: () => boolean
  /** Cancel the spawn entirely. */
  cancel: () => void
}
