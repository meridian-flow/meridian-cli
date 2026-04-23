import { ListDashes } from '@phosphor-icons/react'
import { SessionsPage } from './SessionsPage'
import type { ExtensionManifest } from '@/shell/registry/types'

export const sessionsManifest: ExtensionManifest = {
  id: 'sessions',
  name: 'Sessions',
  railItems: [
    {
      id: 'sessions',
      icon: ListDashes,
      label: 'Sessions',
      order: 0,
      // badge: will wire to running count later
    },
  ],
  panels: [{ id: 'sessions', component: SessionsPage }],
  commands: [
    {
      id: 'switch-to-sessions',
      label: 'Switch to Sessions',
      execute: () => {
        // Shell handles mode switching
      },
    },
  ],
}
