import type { Meta, StoryObj } from "@storybook/react-vite"
import { TopBar } from "./TopBar"

const meta: Meta<typeof TopBar> = {
  title: "Shell/TopBar",
  component: TopBar,
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
type Story = StoryObj<typeof TopBar>

export const NoWorkItem: Story = {
  args: {
    onCommandPalette: () => console.log("palette"),
    onOpenSettings: () => console.log("settings"),
  },
}

export const WithWorkItem: Story = {
  args: {
    workItemName: "auth-refactor",
    onWorkItemClick: () => console.log("work item"),
    onCommandPalette: () => console.log("palette"),
    onOpenSettings: () => console.log("settings"),
  },
}

export const LongWorkItemName: Story = {
  args: {
    workItemName: "a-really-long-work-item-name-that-truncates",
    onCommandPalette: () => console.log("palette"),
  },
}
