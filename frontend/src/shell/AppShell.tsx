import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { TooltipProvider } from "@/components/ui/tooltip"
import { NewSessionDialog } from "@/components/molecules"
import { useSpawnStats } from "@/features/sessions/hooks"
import { createSpawn } from "@/features/sessions/lib"
import { ActivityBar } from "./ActivityBar"
import { ModeViewport } from "./ModeViewport"
import { StatusBar, type ShellStatusBarProps, type SpawnCounts } from "./StatusBar"
import { TopBar } from "./TopBar"
import { NavigationContext, type NavigationContextValue } from "./NavigationContext"
import { registerFirstPartyExtensions, registry, useRegistry } from "./registry"

export interface AppShellProps {
  /** Optional override for the viewport body. When omitted, the active mode's panel is rendered. */
  children?: React.ReactNode
  workItemName?: string | null
  /**
   * Optional override for StatusBar connection indicator. When omitted, the
   * live SSE connection status from `useSpawnStats` is used.
   */
  connectionStatus?: ShellStatusBarProps["connectionStatus"]
  port?: number | null
  /**
   * Optional override for StatusBar counts. When omitted, live stats from
   * `useSpawnStats` are rendered.
   */
  counts?: SpawnCounts
}

/**
 * Root layout. Owns active-mode state, registry bootstrap, and the new-session
 * dialog. The CSS grid places TopBar across the top, StatusBar across the
 * bottom, ActivityBar in the left column, and ModeViewport in the main cell.
 *
 * Data wiring:
 * - StatusBar counts + connection come from `useSpawnStats` (SSE-backed).
 * - NewSessionDialog submits to `POST /api/spawns` via `createSpawn`.
 * - Click-to-chat navigation is provided through `NavigationContext` so the
 *   registry-rendered panels can request mode switches without prop drilling.
 *
 * Explicit `counts`/`connectionStatus` props still win — Storybook and tests
 * rely on that override path.
 */
export function AppShell({
  children,
  workItemName,
  connectionStatus,
  port,
  counts,
}: AppShellProps) {
  const didBootstrap = useRef(false)
  useEffect(() => {
    if (didBootstrap.current) return
    didBootstrap.current = true
    // Skip if any extensions already registered (e.g. in stories).
    if (registry.getRailItems().length === 0) {
      registerFirstPartyExtensions(registry)
    }
  }, [])

  const reg = useRegistry()
  const firstRailId = useMemo(() => reg.getRailItems()[0]?.id ?? "sessions", [reg])
  const [activeMode, setActiveMode] = useState<string>(firstRailId)

  // If rail items arrive after first render (registry bootstrap), adopt the first one.
  useEffect(() => {
    if (!reg.getPanel(activeMode) && reg.getRailItems().length > 0) {
      setActiveMode(reg.getRailItems()[0].id)
    }
  }, [reg, activeMode])

  const [newSessionOpen, setNewSessionOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Live stats — StatusBar binding. Explicit props still take precedence so
  // stories can pin specific states.
  const { stats, connectionStatus: liveConnectionStatus } = useSpawnStats()
  const liveCounts = useMemo<SpawnCounts | undefined>(
    () =>
      stats
        ? {
            running: stats.running,
            queued: stats.queued,
            succeeded: stats.succeeded,
            failed: stats.failed,
          }
        : undefined,
    [stats],
  )

  const effectiveCounts = counts ?? liveCounts
  const effectiveConnectionStatus = connectionStatus ?? liveConnectionStatus

  const handleNewSession = useCallback(
    async (req: {
      agent: string | null
      model: string | null
      harness: string
      prompt: string
      workItem: string | null
    }) => {
      setIsSubmitting(true)
      setSubmitError(null)
      try {
        await createSpawn({
          harness: req.harness,
          prompt: req.prompt,
          model: req.model ?? undefined,
          agent: req.agent ?? undefined,
          // Backend requires a permissions block. `auto` + `workspace-write`
          // is the safest default that still lets most agent profiles run;
          // richer controls belong in the dialog UI when we add them.
          permissions: { sandbox: "workspace-write", approval: "auto" },
        })
        setNewSessionOpen(false)
        // New spawn surfaces automatically through the SSE → stats refetch path.
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        setSubmitError(message)
        // eslint-disable-next-line no-console
        console.error("[shell] createSpawn failed:", err)
      } finally {
        setIsSubmitting(false)
      }
    },
    [],
  )

  const handleNavigateToChat = useCallback((spawnId: string) => {
    // Chat mode wiring (pick up spawnId) lands in A4b; for now the mode
    // switch alone is the observable behaviour.
    // eslint-disable-next-line no-console
    console.log("[shell] navigate to chat for spawn:", spawnId)
    setActiveMode("chat")
  }, [])

  const navigationValue = useMemo<NavigationContextValue>(
    () => ({ navigateToChat: handleNavigateToChat }),
    [handleNavigateToChat],
  )

  return (
    <TooltipProvider>
      <NavigationContext.Provider value={navigationValue}>
        <div
          className="grid h-screen w-screen bg-background text-foreground"
          style={{
            gridTemplateColumns: "48px 1fr",
            gridTemplateRows: "44px 1fr 24px",
          }}
        >
          <div style={{ gridColumn: "1 / -1", gridRow: "1" }}>
            <TopBar
              workItemName={workItemName}
              onCommandPalette={() => console.log("command palette")}
              onOpenSettings={() => console.log("settings")}
            />
          </div>

          <div style={{ gridColumn: "1", gridRow: "2" }} className="min-h-0">
            <ActivityBar
              activeMode={activeMode}
              onModeChange={setActiveMode}
              onNewSession={() => setNewSessionOpen(true)}
              onOpenSettings={() => console.log("settings")}
            />
          </div>

          <div style={{ gridColumn: "2", gridRow: "2" }} className="min-h-0 min-w-0 overflow-hidden">
            {children ?? <ModeViewport activeMode={activeMode} />}
          </div>

          <div style={{ gridColumn: "1 / -1", gridRow: "3" }}>
            <StatusBar
              counts={effectiveCounts}
              connectionStatus={effectiveConnectionStatus}
              port={port}
            />
          </div>
        </div>

        <NewSessionDialog
          open={newSessionOpen}
          onOpenChange={(next) => {
            setNewSessionOpen(next)
            if (!next) setSubmitError(null)
          }}
          onSubmit={(req) => {
            void handleNewSession(req)
          }}
          isSubmitting={isSubmitting}
        />
        {submitError && newSessionOpen ? (
          // A lightweight inline error surface until the dialog grows its own
          // error row. Keeps the failure visible without blocking re-submit.
          <div
            role="alert"
            className="pointer-events-none fixed bottom-8 left-1/2 z-50 -translate-x-1/2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive shadow-md"
          >
            {submitError}
          </div>
        ) : null}
      </NavigationContext.Provider>
    </TooltipProvider>
  )
}
