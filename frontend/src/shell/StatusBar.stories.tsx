import type { Meta, StoryObj } from "@storybook/react-vite"
import { StatusBar } from "./StatusBar"

const meta: Meta<typeof StatusBar> = {
  title: "Shell/StatusBar",
  component: StatusBar,
  parameters: { layout: "fullscreen" },
  decorators: [
    (Story) => (
      <div className="bg-background">
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof StatusBar>

const counts = { running: 2, queued: 1, succeeded: 14, failed: 1 }

export const Connected: Story = {
  args: {
    counts,
    connectionStatus: "connected",
    port: 7721,
  },
}

export const Connecting: Story = {
  args: {
    counts,
    connectionStatus: "connecting",
    port: 7721,
  },
}

export const Disconnected: Story = {
  args: {
    counts,
    connectionStatus: "disconnected",
    port: null,
  },
}

export const Idle: Story = {
  args: {
    counts: { running: 0, queued: 0, succeeded: 0, failed: 0 },
    connectionStatus: "connected",
    port: 7721,
  },
}

export const HeavyActivity: Story = {
  args: {
    counts: { running: 8, queued: 3, succeeded: 127, failed: 4, cancelled: 2 },
    connectionStatus: "connected",
    port: 7721,
  },
}

export const NoPort: Story = {
  args: {
    counts,
    connectionStatus: "connected",
  },
}
