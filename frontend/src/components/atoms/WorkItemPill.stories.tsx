import type { Meta, StoryObj } from "@storybook/react-vite"
import { WorkItemPill } from "./WorkItemPill"

const meta: Meta<typeof WorkItemPill> = {
  title: "Components/Atoms/WorkItemPill",
  component: WorkItemPill,
  parameters: {
    layout: "centered",
  },
  argTypes: {
    isActive: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof WorkItemPill>

export const Default: Story = {
  args: {
    name: "auth-refactor",
  },
}

export const Active: Story = {
  args: {
    name: "auth-refactor",
    isActive: true,
  },
}

export const Clickable: Story = {
  args: {
    name: "auth-refactor",
    onClick: () => console.log("clicked"),
  },
}

export const ActiveClickable: Story = {
  args: {
    name: "auth-refactor",
    isActive: true,
    onClick: () => console.log("clicked"),
  },
}

export const LongName: Story = {
  args: {
    name: "this-is-a-very-long-work-item-name-that-should-truncate",
  },
}

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Short name:</span>
        <WorkItemPill name="auth" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Normal name:</span>
        <WorkItemPill name="auth-refactor" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Long (truncated):</span>
        <WorkItemPill name="this-is-a-very-long-work-item-name" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Inactive:</span>
        <WorkItemPill name="auth-refactor" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Active:</span>
        <WorkItemPill name="auth-refactor" isActive />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Clickable:</span>
        <WorkItemPill name="auth-refactor" onClick={() => alert("Clicked!")} />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Active + Click:</span>
        <WorkItemPill name="auth-refactor" isActive onClick={() => alert("Clicked!")} />
      </div>
    </div>
  ),
}

export const Interactive: Story = {
  render: () => (
    <div className="flex gap-2">
      <WorkItemPill name="task-1" onClick={() => console.log("task-1")} />
      <WorkItemPill name="task-2" isActive onClick={() => console.log("task-2")} />
      <WorkItemPill name="task-3" onClick={() => console.log("task-3")} />
    </div>
  ),
}
