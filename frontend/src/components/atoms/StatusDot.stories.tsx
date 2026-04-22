import type { Meta, StoryObj } from "@storybook/react-vite"
import { StatusDot, type SpawnStatus } from "./StatusDot"

const meta: Meta<typeof StatusDot> = {
  title: "Components/Atoms/StatusDot",
  component: StatusDot,
  parameters: {
    layout: "centered",
  },
  argTypes: {
    status: {
      control: "select",
      options: ["running", "queued", "succeeded", "failed", "cancelled", "finalizing"],
    },
    size: {
      control: "select",
      options: ["sm", "md", "lg"],
    },
  },
}

export default meta
type Story = StoryObj<typeof StatusDot>

export const Default: Story = {
  args: {
    status: "running",
    size: "md",
  },
}

const statuses: SpawnStatus[] = [
  "running",
  "queued", 
  "succeeded",
  "failed",
  "cancelled",
  "finalizing",
]

const sizes = ["sm", "md", "lg"] as const

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-7 gap-4 items-center">
        <div className="text-xs text-muted-foreground font-medium">Size</div>
        {statuses.map((status) => (
          <div key={status} className="text-xs text-muted-foreground font-medium capitalize">
            {status}
          </div>
        ))}
      </div>
      {sizes.map((size) => (
        <div key={size} className="grid grid-cols-7 gap-4 items-center">
          <div className="text-xs text-muted-foreground font-mono">{size}</div>
          {statuses.map((status) => (
            <div key={`${size}-${status}`} className="flex justify-center">
              <StatusDot status={status} size={size} />
            </div>
          ))}
        </div>
      ))}
    </div>
  ),
}

export const Running: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <StatusDot status="running" size="sm" />
      <StatusDot status="running" size="md" />
      <StatusDot status="running" size="lg" />
      <span className="text-sm text-muted-foreground ml-2">Pulsing animation</span>
    </div>
  ),
}

export const Queued: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <StatusDot status="queued" size="sm" />
      <StatusDot status="queued" size="md" />
      <StatusDot status="queued" size="lg" />
      <span className="text-sm text-muted-foreground ml-2">Half-filled (bottom)</span>
    </div>
  ),
}

export const Succeeded: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <StatusDot status="succeeded" size="sm" />
      <StatusDot status="succeeded" size="md" />
      <StatusDot status="succeeded" size="lg" />
      <span className="text-sm text-muted-foreground ml-2">Check overlay</span>
    </div>
  ),
}

export const Failed: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <StatusDot status="failed" size="sm" />
      <StatusDot status="failed" size="md" />
      <StatusDot status="failed" size="lg" />
      <span className="text-sm text-muted-foreground ml-2">X overlay</span>
    </div>
  ),
}

export const Cancelled: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <StatusDot status="cancelled" size="sm" />
      <StatusDot status="cancelled" size="md" />
      <StatusDot status="cancelled" size="lg" />
      <span className="text-sm text-muted-foreground ml-2">Ring only (no fill)</span>
    </div>
  ),
}

export const Finalizing: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <StatusDot status="finalizing" size="sm" />
      <StatusDot status="finalizing" size="md" />
      <StatusDot status="finalizing" size="lg" />
      <span className="text-sm text-muted-foreground ml-2">Slower pulse (2s)</span>
    </div>
  ),
}
