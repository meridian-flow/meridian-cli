import { GearSix } from "@phosphor-icons/react"
import { KeymapHint, WorkItemPill } from "@/components/atoms"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface TopBarProps {
  /** Name of the currently active work item, if any. */
  workItemName?: string | null
  onWorkItemClick?: () => void
  onCommandPalette?: () => void
  onOpenSettings?: () => void
  className?: string
}

/**
 * 44px-tall application chrome. Carries brand label, active work-item pill,
 * a discoverable command-palette hint, and settings access. Sticky at the
 * top of the grid via its parent layout.
 */
export function TopBar({
  workItemName,
  onWorkItemClick,
  onCommandPalette,
  onOpenSettings,
  className,
}: TopBarProps) {
  return (
    <header
      className={cn(
        "flex h-11 items-center gap-3 px-4",
        "border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm font-semibold tracking-tight text-accent-text">
          meridian
        </span>
        <Badge variant="secondary" className="h-5 px-1.5 font-mono text-[10px] uppercase tracking-wider">
          app
        </Badge>
      </div>

      {workItemName ? (
        <>
          <span className="text-muted-foreground/50" aria-hidden>
            /
          </span>
          <WorkItemPill
            name={workItemName}
            isActive
            onClick={onWorkItemClick}
          />
        </>
      ) : null}

      <div className="flex-1" />

      <button
        type="button"
        onClick={onCommandPalette}
        className={cn(
          "inline-flex items-center gap-2 rounded-md px-2 py-1",
          "text-xs text-muted-foreground",
          "transition-colors duration-[var(--duration-fast)]",
          "hover:bg-muted hover:text-foreground",
        )}
        aria-label="Open command palette"
      >
        <span>Search</span>
        <KeymapHint keys="⌘K" />
      </button>

      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onOpenSettings}
        aria-label="Settings"
      >
        <GearSix size={16} />
      </Button>
    </header>
  )
}
