import type { Meta, StoryObj } from "@storybook/react-vite"
import { AppShell } from "./AppShell"

const meta: Meta<typeof AppShell> = {
  title: "Shell/AppShell",
  component: AppShell,
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof AppShell>

export const Connected: Story = {
  args: {
    connectionStatus: "connected",
    port: 7721,
    counts: { running: 2, queued: 0, succeeded: 11, failed: 0 },
    workItemName: "auth-refactor",
  },
}

export const Connecting: Story = {
  args: {
    connectionStatus: "connecting",
    port: 7721,
    counts: { running: 0, queued: 0, succeeded: 0, failed: 0 },
  },
}

export const Disconnected: Story = {
  args: {
    connectionStatus: "disconnected",
    counts: { running: 0, queued: 0, succeeded: 0, failed: 0 },
  },
}

export const DarkTheme: Story = {
  args: {
    connectionStatus: "connected",
    port: 7721,
    counts: { running: 3, queued: 1, succeeded: 42, failed: 1 },
    workItemName: "ui-polish",
  },
  decorators: [
    (Story) => (
      <div className="dark">
        <Story />
      </div>
    ),
  ],
}
