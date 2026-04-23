/**
 * Cross-mode navigation plumbing.
 *
 * The ModeViewport renders panels from the registry, so panels don't receive
 * callbacks directly from AppShell. This context is the seam: AppShell
 * provides it, any panel can consume it to request a mode switch.
 *
 * Outside AppShell (stories, isolated tests) the hook falls back to a
 * logging stub so components remain usable without a provider.
 */

import { createContext, useContext } from "react"

export interface NavigationContextValue {
  /** Switch to the chat mode, optionally focused on a specific spawn. */
  navigateToChat: (spawnId: string) => void
}

export const NavigationContext = createContext<NavigationContextValue | null>(null)

export function useNavigation(): NavigationContextValue {
  const ctx = useContext(NavigationContext)
  if (!ctx) {
    return {
      navigateToChat: (spawnId) => {
        // eslint-disable-next-line no-console
        console.log("[navigation] navigateToChat:", spawnId)
      },
    }
  }
  return ctx
}
