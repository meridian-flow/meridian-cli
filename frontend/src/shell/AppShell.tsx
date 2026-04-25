import { useEffect, useMemo, useRef, useState } from "react"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { CommandPalette } from "./CommandPalette"
import { useSpawnStats } from "@/lib/hooks/use-spawn-stats"
import { ActivityBar } from "./ActivityBar"
import { ModeViewport } from "./ModeViewport"
import { StatusBar, type ShellStatusBarProps, type SpawnCounts } from "./StatusBar"
import { TopBar } from "./TopBar"
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
   * `useSpawnStats` are available to stories but not rendered in the shell.
   */
  counts?: SpawnCounts
}

/**
 * Root layout. Owns active-mode state and registry bootstrap. The CSS grid
 * places TopBar across the top, StatusBar across the bottom, ActivityBar in
 * the left column, and ModeViewport in the main cell.
 *
 * Data wiring:
 * - StatusBar connection comes from `useSpawnStats` (SSE-backed).
 */
export function AppShell({
  children,
  workItemName,
  connectionStatus,
  port,
  counts,
}: AppShellProps) {
  void counts
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
  const firstRailId = useMemo(() => reg.getRailItems()[0]?.id ?? "chat", [reg])
  const [activeMode, setActiveMode] = useState<string>(firstRailId)

  // If rail items arrive after first render (registry bootstrap), adopt the first one.
  useEffect(() => {
    if (!reg.getPanel(activeMode) && reg.getRailItems().length > 0) {
      setActiveMode(reg.getRailItems()[0].id)
    }
  }, [reg, activeMode])
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)

  // Global ⌘K / Ctrl+K toggles the command palette. Attached at the document
  // level so it works regardless of which panel has focus.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setCommandPaletteOpen((prev) => !prev)
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [])

  // Live connection status for the footer indicator.
  const { connectionStatus: liveConnectionStatus } = useSpawnStats()
  const effectiveConnectionStatus = connectionStatus ?? liveConnectionStatus

  return (
    <TooltipProvider>
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
            onCommandPalette={() => setCommandPaletteOpen(true)}
            onOpenSettings={() => console.log("settings")}
          />
        </div>

        <div style={{ gridColumn: "1", gridRow: "2" }} className="min-h-0">
          <ActivityBar
            activeMode={activeMode}
            onModeChange={setActiveMode}
            onOpenSettings={() => console.log("settings")}
          />
        </div>

        <div style={{ gridColumn: "2", gridRow: "2" }} className="min-h-0 min-w-0 overflow-hidden">
          <ErrorBoundary resetKeys={[activeMode]}>
            {children ?? <ModeViewport activeMode={activeMode} />}
          </ErrorBoundary>
        </div>

        <div style={{ gridColumn: "1 / -1", gridRow: "3" }}>
          <StatusBar
            connectionStatus={effectiveConnectionStatus}
            port={port}
          />
        </div>
      </div>

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
        onSwitchMode={setActiveMode}
      />
    </TooltipProvider>
  )
}
