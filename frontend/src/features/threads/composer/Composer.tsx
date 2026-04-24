import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { AlertTriangle, Pause, Send, Square, Zap } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { ConnectionCapabilities } from "@/lib/ws"
import type { StreamController } from "../transport-types"

interface ComposerProps {
  controller: StreamController | null
  capabilities: ConnectionCapabilities | null
  isStreaming: boolean
  disabled: boolean
}

function getSendTooltip(
  capabilities: ConnectionCapabilities | null,
  isStreaming: boolean,
): string {
  if (!capabilities) {
    return "Send message"
  }

  if (capabilities.midTurnInjection === "queue") {
    return "Message queued for next turn"
  }

  if (capabilities.midTurnInjection === "interrupt_restart" && isStreaming) {
    return "Sending will steer the current turn"
  }

  return "Send message"
}

export function Composer({
  controller,
  capabilities,
  isStreaming,
  disabled,
}: ComposerProps) {
  const [value, setValue] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const sendTooltip = useMemo(
    () => getSendTooltip(capabilities, isStreaming),
    [capabilities, isStreaming],
  )

  const sendLabel = useMemo(() => {
    if (capabilities?.midTurnInjection === "queue") {
      return "Queue"
    }

    if (capabilities?.midTurnInjection === "interrupt_restart" && isStreaming) {
      return "Steer"
    }

    return "Send"
  }, [capabilities, isStreaming])

  const canSend = useMemo(() => {
    return !disabled && value.trim().length > 0
  }, [disabled, value])

  const resizeTextarea = useCallback(() => {
    const element = textareaRef.current
    if (!element) {
      return
    }

    element.style.height = "auto"
    element.style.height = `${Math.min(element.scrollHeight, 220)}px`
  }, [])

  useEffect(() => {
    resizeTextarea()
  }, [resizeTextarea, value])

  const handleSend = useCallback(() => {
    if (!canSend) {
      return
    }

    const nextText = value.trim()
    const sent = controller?.sendMessage(nextText) ?? false

    if (!sent) {
      return
    }

    setValue("")
  }, [canSend, controller, value])

  return (
    <div className="rounded-lg border border-border bg-card px-3 py-3">
      <div className="space-y-3">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              handleSend()
            }
          }}
          disabled={disabled}
          placeholder={disabled ? "Waiting for connection..." : "Type a message..."}
          className="max-h-[220px] min-h-18 resize-none font-editor"
        />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            Enter to send. Shift+Enter for newline.
          </p>
          <div className="flex items-center gap-2">
            {isStreaming ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => controller?.interrupt()}
                >
                  <Pause className="size-3.5" />
                  Interrupt
                </Button>
                <Button type="button" variant="destructive" size="sm" onClick={() => controller?.cancel()}>
                  <Square className="size-3.5" />
                  Cancel
                </Button>
              </>
            ) : null}

            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button
                    type="button"
                    size="sm"
                    variant={
                      capabilities?.midTurnInjection === "queue" && isStreaming
                        ? "secondary"
                        : "default"
                    }
                    className={
                      capabilities?.midTurnInjection === "interrupt_restart" && isStreaming
                        ? "ring-1 ring-amber-400/60"
                        : undefined
                    }
                    onClick={handleSend}
                    disabled={!canSend}
                  >
                    {capabilities?.midTurnInjection === "interrupt_restart" && isStreaming ? (
                      <AlertTriangle className="size-3.5 text-amber-600" />
                    ) : capabilities?.midTurnInjection === "interrupt_restart" ? (
                      <Zap className="size-3.5" />
                    ) : (
                      <Send className="size-3.5" />
                    )}
                    {sendLabel}
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent side="top" sideOffset={6}>
                {sendTooltip}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>
    </div>
  )
}
