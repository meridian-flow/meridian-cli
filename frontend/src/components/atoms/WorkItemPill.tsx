import { cn } from "@/lib/utils"

interface WorkItemPillProps {
  name: string
  isActive?: boolean
  onClick?: () => void
  className?: string
}

export function WorkItemPill({
  name,
  isActive = false,
  onClick,
  className,
}: WorkItemPillProps) {
  const isClickable = !!onClick

  const baseClasses = cn(
    "inline-flex items-center gap-1.5 max-w-[180px]",
    "rounded-sm px-2 py-0.5 text-xs",
    "bg-muted transition-colors",
    isActive && "border-l-2 border-accent-fill pl-1.5",
    isClickable && "hover:bg-muted/80 cursor-pointer",
    className
  )

  const content = (
    <>
      {isActive && (
        <span className="h-1.5 w-1.5 rounded-full bg-accent-fill shrink-0" />
      )}
      <span className="truncate">{name}</span>
    </>
  )

  if (isClickable) {
    return (
      <button type="button" onClick={onClick} className={baseClasses}>
        {content}
      </button>
    )
  }

  return <span className={baseClasses}>{content}</span>
}
