import { useCallback, useEffect, useState } from "react"
import { RotateCcw, TriangleAlert } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Composer } from "./Composer"

import { ConversationView } from "./ConversationView"
import { TestChatHeader } from "./TestChatHeader"
import {
  TestChatApiError,
  fetchTestChatSession,
  type TestChatSessionInfo,
} from "./session-api"
import { useTestChatSession } from "./useTestChatSession"

export function TestChatPage() {
  const [session, setSession] = useState<TestChatSessionInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadSeq, setReloadSeq] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchTestChatSession()
      .then((nextSession) => {
        if (cancelled) return
        setSession(nextSession)
      })
      .catch((exc: unknown) => {
        if (cancelled) return
        const message = exc instanceof TestChatApiError
          ? exc.message
          : exc instanceof Error
            ? exc.message
            : "Could not load test chat session."
        setError(message)
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [reloadSeq])

  const chat = useTestChatSession(session)
  const retry = useCallback(() => setReloadSeq((current) => current + 1), [])

  const composerDisabled =
    loading ||
    Boolean(error) ||
    chat.connectionState !== "open" ||
    chat.sessionEnded

  return (
    <div className="flex h-screen min-h-0 flex-col overflow-hidden bg-background text-foreground">
      {session ? (
        <TestChatHeader
          session={session}
          connectionState={chat.connectionState}
          capabilities={chat.capabilities}
          isStreaming={chat.isStreaming}
          sessionEnded={chat.sessionEnded}
          onInterrupt={chat.interrupt}
          onCancel={chat.cancel}
        />
      ) : (
        <div className="flex h-12 shrink-0 items-center border-b border-border px-4 text-sm text-muted-foreground">
          Meridian Test Chat
        </div>
      )}

      {error ? (
        <div className="mx-auto flex w-full max-w-2xl flex-1 items-center px-5">
          <Alert variant="destructive">
            <TriangleAlert />
            <AlertTitle>Could not start test chat</AlertTitle>
            <AlertDescription>
              <p>{error}</p>
              <p>Verify the server is running and try again.</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={retry}
              >
                <RotateCcw className="size-3.5" />
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      ) : (
        <>
          <ConversationView
            entries={chat.entries}
            currentActivity={chat.currentActivity}
            isConnecting={loading || chat.connectionState === "connecting"}
          />

          <div className="shrink-0 border-t border-border bg-background px-5 py-4">
            <div className="mx-auto max-w-3xl">
              <Composer
                controller={chat.controller}
                capabilities={chat.capabilities}
                isStreaming={chat.isStreaming}
                disabled={composerDisabled}
              />
              {chat.sessionEnded ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  Session ended.
                </p>
              ) : null}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
