import { useMemo, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"

interface SpawnSelectorProps {
  onSpawnCreated: (spawnId: string) => void
}

type HarnessId = "claude" | "codex" | "opencode"

interface SpawnCreateResponse {
  spawn_id: string
  harness: string
}

export function SpawnSelector({ onSpawnCreated }: SpawnSelectorProps) {
  const [harness, setHarness] = useState<HarnessId>("claude")
  const [prompt, setPrompt] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canSubmit = useMemo(() => prompt.trim().length > 0 && !isSubmitting, [prompt, isSubmitting])

  async function handleCreateSpawn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      const response = await fetch("/api/spawns", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          harness,
          prompt: prompt.trim(),
        }),
      })

      if (!response.ok) {
        let detail = `Request failed with ${response.status}`

        try {
          const payload = (await response.json()) as { detail?: string; error?: string }
          detail = payload.detail ?? payload.error ?? detail
        } catch {
          // fall through to status message
        }

        throw new Error(detail)
      }

      const payload = (await response.json()) as SpawnCreateResponse
      if (!payload.spawn_id) {
        throw new Error("Spawn creation succeeded but response had no spawn_id")
      }

      onSpawnCreated(payload.spawn_id)
    } catch (spawnError) {
      const message = spawnError instanceof Error ? spawnError.message : "Failed to create spawn"
      setError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl items-center justify-center py-10">
      <Card className="w-full">
        <CardHeader className="space-y-2">
          <CardTitle className="font-mono text-lg">Start New Spawn</CardTitle>
          <p className="text-sm text-muted-foreground">
            Choose a harness and provide an initial prompt to launch a new run.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreateSpawn} className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">Harness</span>
              <Select value={harness} onValueChange={(value) => setHarness(value as HarnessId)}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Select harness" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="claude">claude</SelectItem>
                  <SelectItem value="codex">codex</SelectItem>
                  <SelectItem value="opencode">opencode</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Describe what you want the spawn to do"
              className="min-h-32 resize-y"
            />

            {error ? <p className="text-sm text-destructive">{error}</p> : null}

            <Button type="submit" size="sm" disabled={!canSubmit} loading={isSubmitting}>
              Start Spawn
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
