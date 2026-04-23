import { ChatCircle, ListDashes } from '@phosphor-icons/react'
import type { ExtensionRegistry } from './ExtensionRegistry'

const SessionsPlaceholder = () => (
  <div className="flex h-full items-center justify-center text-muted-foreground">
    Sessions mode — coming in A4a
  </div>
)

const ChatPlaceholder = () => (
  <div className="flex h-full items-center justify-center text-muted-foreground">
    Chat mode — coming in A4b
  </div>
)

export function registerFirstPartyExtensions(registry: ExtensionRegistry): void {
  registry.register({
    id: 'sessions',
    name: 'Sessions',
    railItems: [{ id: 'sessions', icon: ListDashes, label: 'Sessions', order: 0 }],
    panels: [{ id: 'sessions', component: SessionsPlaceholder }],
    commands: [{ id: 'switch-to-sessions', label: 'Switch to Sessions', execute: () => {} }],
  })

  registry.register({
    id: 'chat',
    name: 'Chat',
    railItems: [{ id: 'chat', icon: ChatCircle, label: 'Chat', order: 1 }],
    panels: [{ id: 'chat', component: ChatPlaceholder }],
    commands: [{ id: 'switch-to-chat', label: 'Switch to Chat', execute: () => {} }],
  })
}
