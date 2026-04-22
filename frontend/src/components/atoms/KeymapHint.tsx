import { useMemo } from "react"
import { cn } from "@/lib/utils"

interface KeymapHintProps {
  keys: string
  className?: string
}

function detectOS(): "mac" | "windows" | "other" {
  if (typeof navigator === "undefined") return "other"
  const platform = navigator.platform?.toLowerCase() ?? ""
  if (platform.includes("mac")) return "mac"
  if (platform.includes("win")) return "windows"
  return "other"
}

function formatKeys(keys: string): string {
  const os = detectOS()
  
  // If already using symbols, keep them
  if (keys.includes("⌘") || keys.includes("⌃") || keys.includes("⇧")) {
    // On Windows, convert Mac symbols to text
    if (os === "windows") {
      return keys
        .replace(/⌘/g, "Ctrl")
        .replace(/⌃/g, "Ctrl")
        .replace(/⇧/g, "Shift")
        .replace(/⌥/g, "Alt")
    }
    return keys
  }
  
  // If using text like "Cmd" or "Ctrl", format appropriately
  if (os === "mac") {
    return keys
      .replace(/Cmd/gi, "⌘")
      .replace(/Ctrl/gi, "⌃")
      .replace(/Shift/gi, "⇧")
      .replace(/Alt/gi, "⌥")
      .replace(/Option/gi, "⌥")
  }
  
  return keys
}

export function KeymapHint({ keys, className }: KeymapHintProps) {
  const formattedKeys = useMemo(() => formatKeys(keys), [keys])

  return (
    <span
      className={cn(
        "inline-flex items-center",
        "rounded border border-border/50 px-1.5 py-0.5",
        "font-mono text-xs text-muted-foreground",
        className
      )}
    >
      {formattedKeys}
    </span>
  )
}
