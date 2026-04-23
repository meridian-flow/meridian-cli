import { useEffect, useMemo, useRef, useState } from "react"
import { TooltipProvider } from "@/components/ui/tooltip"
import { NewSessionDialog } from "@/components/molecules"
import { ActivityBar } from "./ActivityBar"
import { ModeViewport } from "./ModeViewport"
import { StatusBar, type ShellStatusBarProps, type SpawnCounts } from "./StatusBar"
import { TopBar } from "./TopBar"
import { registerFirstPartyExtensions, registry, useRegistry } from "./registry"

export interface AppShellProps {
  /** Optional override for the viewport body. When omitted, the active mode's panel is rendered. */
  children?: React.ReactNode
  workItemName?: string | null
  connectionStatus?: ShellStatusBarProps["connectionStatus"]
  port?: number | null
  counts?: SpawnCounts
}

/**
 * Root layout. Owns active-mode state, registry bootstrap, and the new-session
 * dialog. The CSS grid places TopBar across the top, StatusBar across the
 * bottom, ActivityBar in the left column, and ModeViewport in the main cell.
 */
export function AppShell({
  children,
  workItemName,
  connectionStatus = "connecting",
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
            counts={counts}
            connectionStatus={connectionStatus}
            port={port}
          />
        </div>
      </div>

      <NewSessionDialog
        open={newSessionOpen}
        onOpenChange={setNewSessionOpen}
        onSubmit={(req) => {
          console.log("new session", req)
          setNewSessionOpen(false)
        }}
      />
    </TooltipProvider>
  )
}
