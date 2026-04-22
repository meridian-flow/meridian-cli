import { cn } from "@/lib/utils"
import { StatusDot, type SpawnStatus } from "./StatusDot"

interface SpawnCounts {
  running: number
  queued: number
  succeeded: number
  failed: number
  cancelled?: number
}

interface SpawnCountBarProps {
  counts: SpawnCounts
  className?: string
}

interface CountItemProps {
  status: SpawnStatus
  count: number
}

function CountItem({ status, count }: CountItemProps) {
  return (
    <div className="flex items-center gap-1">
      <StatusDot status={status} size="sm" />
      <span className="font-mono text-xs tabular-nums">{count}</span>
    </div>
  )
}

export function SpawnCountBar({ counts, className }: SpawnCountBarProps) {
  // Always show running and succeeded, hide others if 0
  const items: Array<{ status: SpawnStatus; count: number; alwaysShow: boolean }> = [
    { status: "running", count: counts.running, alwaysShow: true },
    { status: "queued", count: counts.queued, alwaysShow: false },
    { status: "succeeded", count: counts.succeeded, alwaysShow: true },
    { status: "failed", count: counts.failed, alwaysShow: false },
  ]

  // Add cancelled if provided and > 0
  if (counts.cancelled !== undefined && counts.cancelled > 0) {
    items.push({ status: "cancelled", count: counts.cancelled, alwaysShow: false })
  }

  const visibleItems = items.filter(
    (item) => item.alwaysShow || item.count > 0
  )

  return (
    <div className={cn("flex items-center gap-3", className)}>
      {visibleItems.map((item, index) => (
        <div key={item.status} className="flex items-center gap-3">
          {index > 0 && (
            <div className="h-3 w-px bg-border" />
          )}
          <CountItem status={item.status} count={item.count} />
        </div>
      ))}
    </div>
  )
}
