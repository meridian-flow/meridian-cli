import { useState, useMemo, useCallback, useEffect, useId } from "react"
import { Copy, Check } from "@phosphor-icons/react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { KeymapHint } from "@/components/atoms"
import { cn } from "@/lib/utils"
import { CaretDown, MagnifyingGlass } from "@phosphor-icons/react"

export interface NewSessionDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (request: {
    agent: string | null
    model: string | null
    harness: string
    prompt: string
    workItem: string | null
  }) => void
  availableAgents?: string[]
  availableModels?: string[]
  availableWorkItems?: Array<{ work_id: string; name: string }>
  defaultHarness?: string
  isSubmitting?: boolean
}

const DEFAULT_HARNESSES = ["claude", "codex", "opencode"]

const PROMPT_PREVIEW_LEN = 50

/**
 * Shell-escape a string for inclusion inside a double-quoted bash argument.
 * Handles backslashes, double quotes, backticks, `$`, and newlines so the
 * copied command can be pasted into a shell without losing the prompt body.
 */
export function shellEscape(str: string): string {
  return str
    .replace(/\\/g, "\\\\")
    .replace(/`/g, "\\`")
    .replace(/\$/g, "\\$")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
}

export function NewSessionDialog({
  open,
  onOpenChange,
  onSubmit,
  availableAgents = [],
  availableModels = [],
  availableWorkItems = [],
  defaultHarness = "claude",
  isSubmitting = false,
}: NewSessionDialogProps) {
  const [agent, setAgent] = useState<string | null>(null)
  const [model, setModel] = useState<string | null>(null)
  const [harness, setHarness] = useState(defaultHarness)
  const [workItem, setWorkItem] = useState<string | null>(null)
  const [prompt, setPrompt] = useState("")
  const [agentOpen, setAgentOpen] = useState(false)
  const [workItemOpen, setWorkItemOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const agentId = useId()
  const modelId = useId()
  const harnessId = useId()
  const workItemId = useId()
  const promptId = useId()

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setAgent(null)
      setModel(null)
      setHarness(defaultHarness)
      setWorkItem(null)
      setPrompt("")
    }
  }, [open, defaultHarness])

  const canSubmit = prompt.trim().length > 0 && !isSubmitting

  // Build the resolved CLI command shown in the preview. The prompt segment
  // uses a truncated, single-line rendering so the preview stays compact;
  // the copy handler expands it into a fully shell-escaped argument.
  const resolvedCommand = useMemo(() => {
    const parts = ["meridian spawn"]
    if (agent) parts.push(`-a ${agent}`)
    if (model) parts.push(`-m ${model}`)
    if (workItem) parts.push(`--work ${workItem}`)
    // Harness is implied by the spawn system - claude is default
    if (harness !== "claude") parts.push(`--harness ${harness}`)

    const trimmed = prompt.trim()
    if (trimmed.length === 0) {
      parts.push('-p "..."')
    } else {
      // Collapse newlines so the preview stays on one visual line, then truncate.
      const oneLine = trimmed.replace(/\s+/g, " ")
      const shown =
        oneLine.length > PROMPT_PREVIEW_LEN
          ? oneLine.slice(0, PROMPT_PREVIEW_LEN) + "..."
          : oneLine
      // Escape only the display-safe bits here; this string is not intended
      // to be pasted as-is (copy uses the fully-escaped full prompt).
      parts.push(`-p "${shown.replace(/"/g, '\\"')}"`)
    }
    return parts.join(" ")
  }, [agent, model, harness, workItem, prompt])

  const handleCopyCommand = useCallback(async () => {
    const parts = ["meridian spawn"]
    if (agent) parts.push(`-a ${agent}`)
    if (model) parts.push(`-m ${model}`)
    if (workItem) parts.push(`--work ${workItem}`)
    if (harness !== "claude") parts.push(`--harness ${harness}`)
    const body = prompt.trim()
    parts.push(`-p "${shellEscape(body)}"`)
    await navigator.clipboard.writeText(parts.join(" "))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [agent, model, harness, workItem, prompt])

  const handleSubmit = useCallback(() => {
    if (!canSubmit) return
    onSubmit({
      agent,
      model,
      harness,
      prompt: prompt.trim(),
      workItem,
    })
  }, [canSubmit, agent, model, harness, prompt, workItem, onSubmit])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit]
  )

  const selectedWorkItem = availableWorkItems.find(
    (w) => w.work_id === workItem
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>New Session</DialogTitle>
          <DialogDescription>
            Launch a new spawn with the specified configuration.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Agent picker with search */}
          <div className="grid grid-cols-[100px_1fr] items-center gap-2">
            <label htmlFor={agentId} className="text-sm text-muted-foreground">Agent</label>
            <Popover open={agentOpen} onOpenChange={setAgentOpen}>
              <PopoverTrigger asChild>
                <Button
                  id={agentId}
                  variant="outline"
                  size="sm"
                  className="justify-between w-full"
                >
                  <span className={cn(!agent && "text-muted-foreground")}>
                    {agent ?? "Default"}
                  </span>
                  <MagnifyingGlass size={14} className="text-muted-foreground" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[200px] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search agents..." className="h-8" />
                  <CommandList>
                    <CommandEmpty>No agents found.</CommandEmpty>
                    <CommandGroup>
                      <CommandItem
                        value=""
                        onSelect={() => {
                          setAgent(null)
                          setAgentOpen(false)
                        }}
                      >
                        <Check
                          size={14}
                          className={cn(
                            "mr-2",
                            !agent ? "opacity-100" : "opacity-0"
                          )}
                        />
                        Default
                      </CommandItem>
                      {availableAgents.map((a) => (
                        <CommandItem
                          key={a}
                          value={a}
                          onSelect={() => {
                            setAgent(a)
                            setAgentOpen(false)
                          }}
                        >
                          <Check
                            size={14}
                            className={cn(
                              "mr-2",
                              agent === a ? "opacity-100" : "opacity-0"
                            )}
                          />
                          {a}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>

          {/* Model select */}
          <div className="grid grid-cols-[100px_1fr] items-center gap-2">
            <label htmlFor={modelId} className="text-sm text-muted-foreground">Model</label>
            <Select
              value={model ?? "auto"}
              onValueChange={(v) => setModel(v === "auto" ? null : v)}
            >
              <SelectTrigger id={modelId} size="sm">
                <SelectValue placeholder="Auto-routed" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto-routed</SelectItem>
                {availableModels.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Harness select */}
          <div className="grid grid-cols-[100px_1fr] items-center gap-2">
            <label htmlFor={harnessId} className="text-sm text-muted-foreground">Harness</label>
            <Select value={harness} onValueChange={setHarness}>
              <SelectTrigger id={harnessId} size="sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DEFAULT_HARNESSES.map((h) => (
                  <SelectItem key={h} value={h}>
                    {h}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Work item select */}
          {availableWorkItems.length > 0 && (
            <div className="grid grid-cols-[100px_1fr] items-center gap-2">
              <label htmlFor={workItemId} className="text-sm text-muted-foreground">Work item</label>
              <Popover open={workItemOpen} onOpenChange={setWorkItemOpen}>
                <PopoverTrigger asChild>
                  <Button
                    id={workItemId}
                    variant="outline"
                    size="sm"
                    className="justify-between w-full"
                  >
                    <span
                      className={cn(
                        "truncate",
                        !workItem && "text-muted-foreground"
                      )}
                    >
                      {selectedWorkItem?.name ?? "None"}
                    </span>
                    <CaretDown size={14} className="text-muted-foreground" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[200px] p-0" align="start">
                  <Command>
                    <CommandInput
                      placeholder="Search work items..."
                      className="h-8"
                    />
                    <CommandList>
                      <CommandEmpty>No work items found.</CommandEmpty>
                      <CommandGroup>
                        <CommandItem
                          value=""
                          onSelect={() => {
                            setWorkItem(null)
                            setWorkItemOpen(false)
                          }}
                        >
                          <Check
                            size={14}
                            className={cn(
                              "mr-2",
                              !workItem ? "opacity-100" : "opacity-0"
                            )}
                          />
                          None
                        </CommandItem>
                        {availableWorkItems.map((item) => (
                          <CommandItem
                            key={item.work_id}
                            value={item.name}
                            onSelect={() => {
                              setWorkItem(item.work_id)
                              setWorkItemOpen(false)
                            }}
                          >
                            <Check
                              size={14}
                              className={cn(
                                "mr-2",
                                workItem === item.work_id
                                  ? "opacity-100"
                                  : "opacity-0"
                              )}
                            />
                            <span className="truncate">{item.name}</span>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          )}

          {/* Prompt textarea */}
          <div className="space-y-1.5">
            <label htmlFor={promptId} className="text-sm text-muted-foreground">Prompt</label>
            <Textarea
              id={promptId}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="What should the spawn do?"
              className="min-h-[100px] resize-y"
              autoFocus
            />
          </div>

          {/* Resolved command preview */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs text-muted-foreground">
                CLI command
              </label>
              <Button
                variant="ghost"
                size="icon-xs"
                onClick={handleCopyCommand}
                className="h-5 w-5"
              >
                {copied ? (
                  <Check size={12} className="text-success" />
                ) : (
                  <Copy size={12} />
                )}
              </Button>
            </div>
            <div className="rounded-md bg-muted p-2 font-mono text-xs text-muted-foreground overflow-x-auto">
              {resolvedCommand}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={!canSubmit}
            loading={isSubmitting}
          >
            Launch
            <KeymapHint keys="⌘↵" className="ml-2" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
