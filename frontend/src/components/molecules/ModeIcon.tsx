import type { ComponentType } from "react"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export interface ModeIconProps {
  icon: ComponentType<{ size?: number; weight?: "thin" | "light" | "regular" | "bold" | "fill" | "duotone" }>
  label: string
  isActive: boolean
  badge?: number
  onClick: () => void
  className?: string
}

export function ModeIcon({
  icon: Icon,
  label,
  isActive,
  badge,
  onClick,
  className,
}: ModeIconProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={onClick}
            aria-label={label}
            className={cn(
              "relative flex items-center justify-center w-12 h-12",
              "transition-all duration-[var(--duration-fast)]",
              isActive
                ? "border-l-2 border-accent-fill"
                : "border-l-2 border-transparent",
              className
            )}
          >
            <Icon
              size={20}
              weight={isActive ? "fill" : "regular"}
              className={cn(
                "transition-opacity duration-[var(--duration-fast)]",
                isActive ? "opacity-100" : "opacity-60 hover:opacity-80"
              )}
            />
            {badge !== undefined && badge > 0 && (
              <span
                className={cn(
                  "absolute top-2 right-2",
                  "flex items-center justify-center",
                  "min-w-[14px] h-[14px] px-1",
                  "rounded-full bg-destructive text-white",
                  "text-[10px] font-medium leading-none"
                )}
              >
                {badge > 99 ? "99+" : badge}
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          {label}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
