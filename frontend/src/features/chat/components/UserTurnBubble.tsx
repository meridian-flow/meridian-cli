import { cn } from "@/lib/utils"

interface UserTurnBubbleProps {
  text: string
  className?: string
}

export function UserTurnBubble({ text, className }: UserTurnBubbleProps) {
  return (
    <div className={cn("flex justify-end", className)}>
      <div className="max-w-[78%] whitespace-pre-wrap rounded-lg border border-border bg-card px-3 py-2 font-editor text-sm leading-relaxed text-card-foreground shadow-sm">
        {text}
      </div>
    </div>
  )
}
