import { useEffect, useMemo, useState } from "react"

import { StatusBar } from "@/components/StatusBar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { TooltipProvider } from "@/components/ui/tooltip"
import { SpawnHeader } from "@/features/spawn-selector/SpawnHeader"
import { SpawnSelector } from "@/features/spawn-selector/SpawnSelector"
import { Composer } from "@/features/threads/composer/Composer"
import { StreamingIndicator } from "@/features/threads/components/StreamingIndicator"
import { ThreadView } from "@/features/threads/components/ThreadView"
import { useThreadStreaming } from "@/hooks/use-thread-streaming"
import type { ConnectionCapabilities, WsState } from "@/lib/ws"

function mapWsStateToConnectionStatus(
  spawnId: string | null,
  wsState: WsState,
): "connecting" | "connected" | "disconnected" {
  if (!spawnId) {
    return "disconnected"
  }

  if (wsState === "open") {
    return "connected"
  }

  if (wsState === "closed") {
    return "disconnected"
  }

  return "connecting"
}

function inferHarnessId(capabilities: ConnectionCapabilities | null): string | null {
  if (!capabilities) {
    return null
  }

  if (capabilities.midTurnInjection === "queue") {
    return "claude"
  }

  if (capabilities.midTurnInjection === "interrupt_restart") {
    return "codex"
  }

  return "opencode"
}

function App() {
  const [spawnId, setSpawnId] = useState<string | null>(null)
  const [harnessId, setHarnessId] = useState<string | null>(null)

  const { state, capabilities, channel, cancel, connectionState } =
    useThreadStreaming(spawnId)

  const connectionStatus = useMemo(
    () => mapWsStateToConnectionStatus(spawnId, connectionState),
    [spawnId, connectionState],
  )

  const composerDisabled = useMemo(() => {
    return !spawnId || connectionStatus !== "connected" || Boolean(state.error)
  }, [spawnId, connectionStatus, state.error])

  useEffect(() => {
    if (!spawnId) {
      setHarnessId(null)
      return
    }

    let isActive = true

    async function loadSpawnMetadata() {
      try {
        const response = await fetch(`/api/spawns/${spawnId}`)
        if (!response.ok) {
          return
        }

        const payload = (await response.json()) as { harness?: string }
        if (isActive) {
          setHarnessId(payload.harness ?? null)
        }
      } catch {
        if (isActive) {
          setHarnessId((current) => current ?? null)
        }
      }
    }

    void loadSpawnMetadata()

    return () => {
      isActive = false
    }
  }, [spawnId])

  useEffect(() => {
    if (!spawnId || harnessId) {
      return
    }

    const inferredHarness = inferHarnessId(capabilities)
    if (inferredHarness) {
      setHarnessId(inferredHarness)
    }
  }, [spawnId, harnessId, capabilities])

  function handleSpawnCreated(nextSpawnId: string) {
    setSpawnId(nextSpawnId)
    setHarnessId(null)
  }

  function handleDisconnect() {
    setSpawnId(null)
    setHarnessId(null)
  }

  return (
    <TooltipProvider>
      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <header className="border-b border-border px-6 py-3">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm font-semibold tracking-tight text-accent-text">
                meridian
              </span>
              <Badge variant="secondary" className="font-mono text-xs">
                app
              </Badge>
            </div>

            <div className="flex items-center gap-2">
              {state.isCancelled ? (
                <Badge variant="destructive" className="font-mono text-xs">
                  cancelled
                </Badge>
              ) : null}
              <Badge variant="outline" className="font-mono text-xs">
                {spawnId ? "active" : "idle"}
              </Badge>
            </div>
          </div>
        </header>

        <main className="min-h-0 flex-1 px-6 py-6">
          {!spawnId ? (
            <SpawnSelector onSpawnCreated={handleSpawnCreated} />
          ) : (
            <div className="mx-auto flex h-full max-h-[calc(100vh-12.5rem)] w-full max-w-5xl flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-0 flex-1">
                  <SpawnHeader
                    spawnId={spawnId}
                    harnessId={harnessId}
                    capabilities={capabilities}
                    connectionStatus={connectionStatus}
                  />
                </div>
                <Button type="button" size="sm" variant="outline" onClick={handleDisconnect}>
                  Disconnect
                </Button>
              </div>

              <div className="min-h-0 flex-1">
                <ThreadView items={state.items} error={state.error} />
              </div>

              {state.isStreaming ? <StreamingIndicator /> : null}

              <Composer
                channel={channel}
                capabilities={capabilities}
                isStreaming={state.isStreaming}
                disabled={composerDisabled}
                onCancel={cancel}
              />
            </div>
          )}
        </main>

        <StatusBar
          connectionStatus={connectionStatus}
          spawnId={spawnId}
          harnessId={harnessId}
        />
      </div>
    </TooltipProvider>
  )
}

export default App
