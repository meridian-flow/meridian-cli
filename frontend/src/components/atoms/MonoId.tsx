import { useState, useCallback } from "react"
import { Copy, Check } from "@phosphor-icons/react"
import { cn } from "@/lib/utils"

interface MonoIdProps {
  id: string
  prefix?: string
  copyable?: boolean
  className?: string
}

export function MonoId({ id, prefix, copyable = false, className }: MonoIdProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    if (!copyable) return
    try {
      await navigator.clipboard.writeText(id)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch (err) {
      console.error("Failed to copy:", err)
    }
  }, [copyable, id])

  const baseClasses = cn(
    "inline-flex items-center gap-1 rounded-sm bg-muted px-1.5 py-0.5",
    "font-mono text-xs",
    copyable && "cursor-pointer hover:bg-muted/80 transition-colors",
    className
  )

  const content = (
    <>
      {prefix && (
        <span className="text-muted-foreground">{prefix}</span>
      )}
      <span>{id}</span>
      {copyable && (
        <span className="ml-0.5 text-muted-foreground">
          {copied ? (
            <Check size={12} weight="bold" className="text-success" />
          ) : (
            <Copy size={12} className="opacity-0 group-hover:opacity-100 transition-opacity" />
          )}
        </span>
      )}
    </>
  )

  if (copyable) {
    return (
      <button
        type="button"
        onClick={handleCopy}
        className={cn(baseClasses, "group")}
        title={copied ? "Copied!" : "Click to copy"}
      >
        {content}
      </button>
    )
  }

  return <span className={baseClasses}>{content}</span>
}
