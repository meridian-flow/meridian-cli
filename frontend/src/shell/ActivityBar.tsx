import { GearSix, Plus } from "@phosphor-icons/react"
import { ModeIcon } from "@/components/molecules"
import { cn } from "@/lib/utils"
import { useRegistry } from "./registry"

export interface ActivityBarProps {
  /** Currently active mode id. */
  activeMode: string
  /** Fires when a rail icon is clicked. */
  onModeChange: (id: string) => void
  /** Fires when the `+` action is clicked (opens NewSessionDialog). */
  onNewSession?: () => void
  /** Fires when the settings gear is clicked. */
  onOpenSettings?: () => void
  className?: string
}

/**
 * Left-edge vertical rail. Hosts mode entry points contributed through the
 * extension registry, plus pinned actions (new session, settings) at the
 * bottom. Width is fixed at 48px so the grid parent can reserve the column.
 */
export function ActivityBar({
  activeMode,
  onModeChange,
  onNewSession,
  onOpenSettings,
  className,
}: ActivityBarProps) {
  const registry = useRegistry()
  const items = registry.getRailItems()

  return (
    <nav
      aria-label="Activity bar"
      className={cn(
        "flex h-full w-12 flex-col items-stretch justify-between",
        "border-r border-border bg-sidebar text-sidebar-foreground",
        className,
      )}
    >
      <div className="flex flex-col">
        {items.map((item) => (
          <ModeIcon
            key={item.id}
            icon={item.icon}
            label={item.label}
            isActive={activeMode === item.id}
            badge={item.badge?.()}
            onClick={() => onModeChange(item.id)}
          />
        ))}
      </div>
      <div className="flex flex-col border-t border-border/60">
        <ModeIcon
          icon={Plus}
          label="New session"
          isActive={false}
          onClick={() => onNewSession?.()}
        />
        <ModeIcon
          icon={GearSix}
          label="Settings"
          isActive={false}
          onClick={() => onOpenSettings?.()}
        />
      </div>
    </nav>
  )
}
