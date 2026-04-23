import { StatusDot, MonoId, ElapsedTime } from "@/components/atoms"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger,
} from "@/components/ui/context-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { SpawnSummary } from "@/types/spawn"
import { GitFork, Archive, XCircle } from "@phosphor-icons/react"

export interface SessionRowProps {
  spawn: SpawnSummary
  isSelected?: boolean
  onClick?: () => void
  onContextAction?: (action: 'cancel' | 'fork' | 'archive') => void
  className?: string
}

function formatCost(cost: number | null): string {
  if (cost === null) return "—"
  return `$${cost.toFixed(2)}`
}

export function SessionRow({
  spawn,
  isSelected = false,
  onClick,
  onContextAction,
  className,
}: SessionRowProps) {
  const canCancel = spawn.status === 'running' || spawn.status === 'queued'

  const rowContent = (
    <div
      {...(onClick ? { role: 'button', tabIndex: 0 } : {})}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick()
              }
            }
          : undefined
      }
      className={cn(
        "grid items-center gap-3 px-3 py-2 transition-colors",
        "grid-cols-[auto_auto_minmax(60px,80px)_minmax(60px,80px)_1fr_auto_auto]",
        "hover:bg-muted/50",
        isSelected && "border-l-2 border-accent-fill bg-muted/30",
        !isSelected && "border-l-2 border-transparent",
        onClick && "cursor-pointer",
        className
      )}
    >
      {/* Status */}
      <StatusDot status={spawn.status} size="md" />

      {/* Spawn ID */}
      <MonoId id={spawn.spawn_id} className="bg-transparent px-0" />

      {/* Agent */}
      <span className="text-xs text-muted-foreground truncate">
        {spawn.agent ?? "—"}
      </span>

      {/* Model */}
      <span className="text-xs text-muted-foreground truncate">
        {spawn.model ?? "—"}
      </span>

      {/* Description */}
      <span className="text-sm truncate" title={spawn.desc ?? undefined}>
        {spawn.desc ?? "—"}
      </span>

      {/* Elapsed Time */}
      <ElapsedTime
        startedAt={new Date(spawn.started_at)}
        endedAt={spawn.finished_at ? new Date(spawn.finished_at) : undefined}
        format="relative"
      />

      {/* Cost */}
      <span className="font-mono text-xs text-muted-foreground text-right min-w-[50px]">
        {formatCost(spawn.cost_usd)}
      </span>
    </div>
  )

  if (!onContextAction) {
    return rowContent
  }

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{rowContent}</ContextMenuTrigger>
      <ContextMenuContent>
        {canCancel && (
          <>
            <ContextMenuItem
              variant="destructive"
              onClick={() => onContextAction('cancel')}
            >
              <XCircle size={16} />
              Cancel
            </ContextMenuItem>
            <ContextMenuSeparator />
          </>
        )}
        {/* Fork is surfaced but disabled until the backend implements it
            (currently returns 501). Keeping it visible advertises the
            affordance without giving users a broken action. */}
        <ContextMenuItem disabled>
          <GitFork size={16} />
          Fork (coming soon)
        </ContextMenuItem>
        <ContextMenuItem onClick={() => onContextAction('archive')}>
          <Archive size={16} />
          Archive
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

// Skeleton variant for loading states
export function SessionRowSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "grid items-center gap-3 px-3 py-2",
        "grid-cols-[auto_auto_minmax(60px,80px)_minmax(60px,80px)_1fr_auto_auto]",
        className
      )}
    >
      <Skeleton className="h-[10px] w-[10px] rounded-full" />
      <Skeleton className="h-4 w-12" />
      <Skeleton className="h-3 w-14" />
      <Skeleton className="h-3 w-14" />
      <Skeleton className="h-4 w-48" />
      <Skeleton className="h-3 w-12" />
      <Skeleton className="h-3 w-10" />
    </div>
  )
}
