import { ChatCircle } from '@phosphor-icons/react'
import { sessionsManifest } from '@/features/sessions/manifest'
import type { ExtensionRegistry } from './ExtensionRegistry'

const ChatPlaceholder = () => (
  <div className="flex h-full items-center justify-center text-muted-foreground">
    Chat mode — coming in A4b
  </div>
)

export function registerFirstPartyExtensions(registry: ExtensionRegistry): void {
  // Real Sessions mode
  registry.register(sessionsManifest)

  // Chat placeholder — replaced in A4b
  registry.register({
    id: 'chat',
    name: 'Chat',
    railItems: [{ id: 'chat', icon: ChatCircle, label: 'Chat', order: 1 }],
    panels: [{ id: 'chat', component: ChatPlaceholder }],
    commands: [{ id: 'switch-to-chat', label: 'Switch to Chat', execute: () => {} }],
  })
}
