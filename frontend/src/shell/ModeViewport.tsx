import { cn } from "@/lib/utils"
import { useRegistry } from "./registry"

export interface ModeViewportProps {
  activeMode: string
  className?: string
}

/**
 * Hosts the panel contributed by the currently-active mode. A key-based
 * remount plus a short opacity transition produces the cross-fade users
 * see when they switch modes; falls back to a friendly message when no
 * panel has been registered for the requested id.
 */
export function ModeViewport({ activeMode, className }: ModeViewportProps) {
  const registry = useRegistry()
  const Panel = registry.getPanel(activeMode)

  return (
    <section
      aria-label="Mode viewport"
      className={cn("relative h-full overflow-hidden", className)}
    >
      <div
        key={activeMode}
        className={cn(
          "h-full w-full",
          "motion-safe:animate-[fade-in_var(--duration-default)_var(--ease-default)]",
        )}
      >
        {Panel ? (
          <Panel />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-muted-foreground">
            <span className="font-mono text-sm">mode not found</span>
            <span className="text-xs opacity-70">
              no panel registered for <code className="font-mono">{activeMode}</code>
            </span>
          </div>
        )}
      </div>
    </section>
  )
}
