import type { Meta, StoryObj } from "@storybook/react-vite"
import { KeymapHint } from "./KeymapHint"

const meta: Meta<typeof KeymapHint> = {
  title: "Components/Atoms/KeymapHint",
  component: KeymapHint,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof KeymapHint>

export const Default: Story = {
  args: {
    keys: "⌘K",
  },
}

export const CommonShortcuts: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground w-40">Command palette:</span>
        <KeymapHint keys="⌘K" />
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground w-40">Toggle sidebar:</span>
        <KeymapHint keys="⌘\\" />
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground w-40">Escape:</span>
        <KeymapHint keys="Esc" />
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground w-40">Shift combo:</span>
        <KeymapHint keys="⌘⇧P" />
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground w-40">Copy:</span>
        <KeymapHint keys="⌘C" />
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm text-muted-foreground w-40">Paste:</span>
        <KeymapHint keys="⌘V" />
      </div>
    </div>
  ),
}

export const TextFormat: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Using text format (auto-converts to symbols on Mac):
      </p>
      <div className="flex items-center gap-3">
        <KeymapHint keys="Cmd+K" />
        <KeymapHint keys="Ctrl+C" />
        <KeymapHint keys="Shift+Enter" />
        <KeymapHint keys="Alt+Tab" />
      </div>
    </div>
  ),
}

export const SymbolFormat: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        Using Mac symbols directly:
      </p>
      <div className="flex items-center gap-3">
        <KeymapHint keys="⌘K" />
        <KeymapHint keys="⌃C" />
        <KeymapHint keys="⇧↩" />
        <KeymapHint keys="⌥⇥" />
      </div>
    </div>
  ),
}

export const InContext: Story = {
  render: () => (
    <div className="flex items-center gap-2 text-sm">
      <span>Press</span>
      <KeymapHint keys="⌘K" />
      <span>to open the command palette</span>
    </div>
  ),
}

export const AllShortcuts: Story = {
  render: () => (
    <div className="grid grid-cols-2 gap-4 max-w-md">
      <div className="flex justify-between items-center">
        <span className="text-sm">New session</span>
        <KeymapHint keys="⌘N" />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-sm">Command palette</span>
        <KeymapHint keys="⌘K" />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-sm">Toggle sidebar</span>
        <KeymapHint keys="⌘\\" />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-sm">Switch mode</span>
        <KeymapHint keys="⌘1" />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-sm">Cancel</span>
        <KeymapHint keys="Esc" />
      </div>
      <div className="flex justify-between items-center">
        <span className="text-sm">Settings</span>
        <KeymapHint keys="⌘," />
      </div>
    </div>
  ),
}
