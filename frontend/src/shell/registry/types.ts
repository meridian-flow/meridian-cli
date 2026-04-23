import type { ComponentType } from 'react'

export interface RailItemContribution {
  id: string
  icon: ComponentType<{ size?: number; weight?: string }>
  label: string
  order: number // Lower = higher in rail
  badge?: () => number // Dynamic badge count
}

export interface PanelContribution {
  id: string // Matches rail item id
  component: ComponentType // The mode's main view
}

export interface CommandContribution {
  id: string
  label: string
  shortcut?: string // e.g. "⌘K"
  execute: () => void
  category?: string // For grouping in command palette
}

export interface ExtensionManifest {
  id: string
  name: string
  railItems: RailItemContribution[]
  panels: PanelContribution[]
  commands: CommandContribution[]
}
