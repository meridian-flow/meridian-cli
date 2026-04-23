import { SpawnCountBar } from "@/components/atoms"
import { cn } from "@/lib/utils"

export interface SpawnCounts {
  running: number
  queued: number
  succeeded: number
  failed: number
  cancelled?: number
}

export interface ShellStatusBarProps {
  counts?: SpawnCounts
  connectionStatus: "connecting" | "connected" | "disconnected"
  port?: number | null
  className?: string
}

const CONNECTION_DOT: Record<ShellStatusBarProps["connectionStatus"], string> = {
  connected: "bg-success",
  connecting: "bg-amber-500",
  disconnected: "bg-destructive",
}

const CONNECTION_LABEL: Record<ShellStatusBarProps["connectionStatus"], string> = {
  connected: "connected",
  connecting: "connecting",
  disconnected: "offline",
}

/**
 * 24px status strip anchored at the bottom of the shell grid. Left side holds
 * the spawn-count summary; right side reports backend health and bound port.
 */
export function StatusBar({
  counts,
  connectionStatus,
  port,
  className,
}: ShellStatusBarProps) {
  return (
    <footer
      className={cn(
        "flex h-6 items-center gap-3 px-3 text-xs",
        "border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80",
        className,
      )}
    >
      {counts ? <SpawnCountBar counts={counts} /> : <span className="text-muted-foreground">no spawns</span>}

      <div className="flex-1" />

      <div className="flex items-center gap-1.5">
        <span
          className={cn(
            "inline-block size-1.5 rounded-full",
            CONNECTION_DOT[connectionStatus],
            connectionStatus === "connecting" && "animate-pulse",
          )}
          aria-hidden
        />
        <span className="font-mono text-muted-foreground">
          {CONNECTION_LABEL[connectionStatus]}
        </span>
      </div>

      {port != null ? (
        <>
          <div className="h-3 w-px bg-border" />
          <span className="font-mono text-muted-foreground tabular-nums">
            :{port}
          </span>
        </>
      ) : null}
    </footer>
  )
}
