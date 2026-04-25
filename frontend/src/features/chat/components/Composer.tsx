import { useCallback, useEffect, useRef, useState } from "react"
import {
  Paperclip,
  Gauge,
  ArrowUp,
  Stop,
} from "@phosphor-icons/react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { StreamController } from "../transport-types"

import type { ModelSelection } from "../ChatContext"
import type { ModelCatalog } from "../hooks/use-model-catalog"
import { ModelPicker } from "./ModelPicker"

// ---------------------------------------------------------------------------
// Composer — message input with model picker + send/interrupt controls
// ---------------------------------------------------------------------------

export interface ComposerProps {
  onSend: (text: string) => void | Promise<void>
  disabled: boolean
  isStreaming: boolean
  placeholder: string
  controller: StreamController
  // New props — Phase 2
  chatId: string
  modelSelection: ModelSelection | null
  onModelChange: (selection: ModelSelection) => void
  catalog: ModelCatalog | null
  /** Actual model id from the thread (used for read-only display). */
  threadModel?: string | null
  /** Actual harness from the thread (used for read-only display). */
  threadHarness?: string | null
}

export function Composer({
  onSend,
  disabled,
  isStreaming,
  placeholder,
  controller,
  chatId,
  modelSelection,
  onModelChange,
  catalog,
  threadModel = null,
  threadHarness = null,
}: ComposerProps) {
  const [value, setValue] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const isNewChat = chatId === "__new__"

  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }, [])

  useEffect(() => {
    resizeTextarea()
  }, [resizeTextarea, value])

  const handleSend = useCallback(async () => {
    const text = value.trim()
    if (!text) return
    setValue("")
    await onSend(text)
  }, [value, onSend])

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="rounded-lg border border-border bg-card px-3 py-3">
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                void handleSend()
              }
            }}
            disabled={disabled}
            placeholder={placeholder}
            className="max-h-[180px] min-h-12 resize-none border-none bg-transparent shadow-none font-editor focus-visible:ring-0"
          />

          <div className="mt-2 flex items-center justify-between">
            {/* Left: Model picker + disabled stubs */}
            <div className="flex items-center gap-1.5">
              {/* Model picker — interactive only in zero state */}
              {isNewChat && catalog ? (
                <ModelPicker
                  value={modelSelection}
                  onChange={onModelChange}
                  catalog={catalog}
                  disabled={disabled}
                />
              ) : (
                // Read-only: prefer actual thread model/harness over context selection
                (threadModel || threadHarness || modelSelection) && (
                  <span
                    className={cn(
                      "inline-flex h-7 items-center gap-1.5 rounded-md border border-border/40",
                      "bg-muted/40 px-2.5 text-xs font-medium text-muted-foreground",
                    )}
                  >
                    {threadHarness ?? modelSelection?.harness ?? "—"} ·{" "}
                    {threadModel ?? modelSelection?.displayName ?? "—"}
                  </span>
                )
              )}

              {/* Effort picker — disabled stub (tabIndex makes it keyboard-discoverable) */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0} role="button" aria-disabled="true" aria-label="Effort level">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      disabled
                      className="text-muted-foreground/40"
                      aria-label="Effort level"
                      tabIndex={-1}
                    >
                      <Gauge className="size-3.5" />
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  Effort — coming soon
                </TooltipContent>
              </Tooltip>

              {/* Attach button — disabled stub (tabIndex makes it keyboard-discoverable) */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0} role="button" aria-disabled="true" aria-label="Attach file">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      disabled
                      className="text-muted-foreground/40"
                      aria-label="Attach file"
                      tabIndex={-1}
                    >
                      <Paperclip className="size-3.5" />
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  Attach — coming soon
                </TooltipContent>
              </Tooltip>
            </div>

            {/* Right: Send / Interrupt controls */}
            <div className="flex items-center gap-2">
              <span className="hidden text-[10px] text-muted-foreground/50 sm:inline">
                Enter to send
              </span>

              {/* EARS-CHAT-042: Interrupt button during streaming */}
              {isStreaming && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-xs"
                      onClick={() => controller.interrupt()}
                      className="border-destructive/30 text-destructive hover:bg-destructive/10"
                    >
                      <Stop className="size-3" weight="fill" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="top" sideOffset={6}>
                    Interrupt
                  </TooltipContent>
                </Tooltip>
              )}

              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button
                      type="button"
                      size="icon-xs"
                      onClick={() => void handleSend()}
                      disabled={disabled || !value.trim()}
                      className="rounded-full"
                    >
                      <ArrowUp className="size-3.5" weight="bold" />
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={6}>
                  Send message
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
