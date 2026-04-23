import { useSyncExternalStore } from 'react'
import type {
  CommandContribution,
  ExtensionManifest,
  PanelContribution,
  RailItemContribution,
} from './types'

type Listener = () => void

/**
 * Central registry for shell extensions.
 *
 * Extensions contribute rail items (mode entry points), panels (mode views),
 * and commands (palette actions). Components subscribe via {@link useRegistry}
 * to re-render when contributions change.
 */
export class ExtensionRegistry {
  private manifests = new Map<string, ExtensionManifest>()
  private listeners = new Set<Listener>()
  private version = 0

  register(manifest: ExtensionManifest): void {
    this.manifests.set(manifest.id, manifest)
    this.bump()
  }

  unregister(extensionId: string): void {
    if (this.manifests.delete(extensionId)) {
      this.bump()
    }
  }

  getRailItems(): RailItemContribution[] {
    const items: RailItemContribution[] = []
    for (const manifest of this.manifests.values()) {
      items.push(...manifest.railItems)
    }
    return items.sort((a, b) => a.order - b.order)
  }

  getPanel(id: string): PanelContribution['component'] | undefined {
    for (const manifest of this.manifests.values()) {
      const panel = manifest.panels.find((p) => p.id === id)
      if (panel) return panel.component
    }
    return undefined
  }

  getCommands(): CommandContribution[] {
    const commands: CommandContribution[] = []
    for (const manifest of this.manifests.values()) {
      commands.push(...manifest.commands)
    }
    return commands
  }

  getAllManifests(): ExtensionManifest[] {
    return Array.from(this.manifests.values())
  }

  /** Subscribe to registry mutations. Returns unsubscribe. */
  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  /** Snapshot for `useSyncExternalStore` — bumps on every mutation. */
  getSnapshot = (): number => this.version

  private bump(): void {
    this.version += 1
    for (const listener of this.listeners) {
      listener()
    }
  }
}

/** Process-wide singleton registry. */
export const registry = new ExtensionRegistry()

/**
 * React hook returning the singleton registry. Components re-render
 * whenever any extension registers or unregisters.
 */
export function useRegistry(): ExtensionRegistry {
  useSyncExternalStore(registry.subscribe, registry.getSnapshot, registry.getSnapshot)
  return registry
}
