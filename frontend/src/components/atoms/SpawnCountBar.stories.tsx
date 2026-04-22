import type { Meta, StoryObj } from "@storybook/react-vite"
import { SpawnCountBar } from "./SpawnCountBar"

const meta: Meta<typeof SpawnCountBar> = {
  title: "Components/Atoms/SpawnCountBar",
  component: SpawnCountBar,
  parameters: {
    layout: "centered",
  },
}

export default meta
type Story = StoryObj<typeof SpawnCountBar>

export const Default: Story = {
  args: {
    counts: {
      running: 2,
      queued: 1,
      succeeded: 14,
      failed: 0,
    },
  },
}

export const AllZeros: Story = {
  args: {
    counts: {
      running: 0,
      queued: 0,
      succeeded: 0,
      failed: 0,
    },
  },
}

export const SomeRunning: Story = {
  args: {
    counts: {
      running: 3,
      queued: 2,
      succeeded: 8,
      failed: 0,
    },
  },
}

export const AllDone: Story = {
  args: {
    counts: {
      running: 0,
      queued: 0,
      succeeded: 25,
      failed: 0,
    },
  },
}

export const WithFailures: Story = {
  args: {
    counts: {
      running: 1,
      queued: 0,
      succeeded: 12,
      failed: 3,
    },
  },
}

export const WithCancelled: Story = {
  args: {
    counts: {
      running: 0,
      queued: 0,
      succeeded: 10,
      failed: 2,
      cancelled: 1,
    },
  },
}

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground w-32">All zeros:</span>
        <SpawnCountBar counts={{ running: 0, queued: 0, succeeded: 0, failed: 0 }} />
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground w-32">Active work:</span>
        <SpawnCountBar counts={{ running: 2, queued: 1, succeeded: 14, failed: 0 }} />
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground w-32">All done:</span>
        <SpawnCountBar counts={{ running: 0, queued: 0, succeeded: 25, failed: 0 }} />
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground w-32">With failures:</span>
        <SpawnCountBar counts={{ running: 1, queued: 0, succeeded: 12, failed: 3 }} />
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground w-32">With cancelled:</span>
        <SpawnCountBar counts={{ running: 0, queued: 0, succeeded: 10, failed: 2, cancelled: 1 }} />
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted-foreground w-32">Large numbers:</span>
        <SpawnCountBar counts={{ running: 5, queued: 12, succeeded: 156, failed: 8 }} />
      </div>
    </div>
  ),
}

export const InStatusBar: Story = {
  render: () => (
    <div className="flex items-center gap-4 px-4 py-1 bg-background border rounded-sm h-6">
      <SpawnCountBar counts={{ running: 2, queued: 1, succeeded: 14, failed: 0 }} />
      <div className="h-3 w-px bg-border" />
      <span className="text-xs text-muted-foreground">Connected</span>
    </div>
  ),
}
