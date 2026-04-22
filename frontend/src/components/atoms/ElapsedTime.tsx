import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"

interface ElapsedTimeProps {
  startedAt: Date
  endedAt?: Date
  format?: "relative" | "duration"
  className?: string
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  
  if (hours > 0) {
    const remainingMinutes = minutes % 60
    return `${hours}h ${remainingMinutes}m`
  }
  if (minutes > 0) {
    const remainingSeconds = seconds % 60
    return `${minutes}m ${remainingSeconds}s`
  }
  return `${seconds}s`
}

function formatRelative(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (seconds < 10) return "just now"
  if (seconds < 60) return `${seconds}s ago`
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

export function ElapsedTime({
  startedAt,
  endedAt,
  format = "relative",
  className,
}: ElapsedTimeProps) {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    // If ended, no need to tick
    if (endedAt) return

    const interval = setInterval(() => {
      setNow(new Date())
    }, 1000)

    return () => clearInterval(interval)
  }, [endedAt])

  const endTime = endedAt ?? now
  const elapsed = endTime.getTime() - startedAt.getTime()

  const formatted = format === "duration" 
    ? formatDuration(elapsed) 
    : formatRelative(elapsed)

  return (
    <span className={cn("font-mono text-xs text-muted-foreground", className)}>
      {formatted}
    </span>
  )
}
