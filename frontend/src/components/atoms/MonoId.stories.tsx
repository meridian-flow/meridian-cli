import type { Meta, StoryObj } from "@storybook/react-vite"
import { MonoId } from "./MonoId"

const meta: Meta<typeof MonoId> = {
  title: "Components/Atoms/MonoId",
  component: MonoId,
  parameters: {
    layout: "centered",
  },
  argTypes: {
    copyable: {
      control: "boolean",
    },
  },
}

export default meta
type Story = StoryObj<typeof MonoId>

export const Default: Story = {
  args: {
    id: "p281",
  },
}

export const WithPrefix: Story = {
  args: {
    id: "p281",
    prefix: "spawn",
  },
}

export const Copyable: Story = {
  args: {
    id: "p281",
    copyable: true,
  },
}

export const CopyableWithPrefix: Story = {
  args: {
    id: "c42",
    prefix: "chat",
    copyable: true,
  },
}

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Short ID:</span>
        <MonoId id="p1" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Long ID:</span>
        <MonoId id="p1234567" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">With prefix:</span>
        <MonoId id="p281" prefix="spawn" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Chat ID:</span>
        <MonoId id="c42" prefix="chat" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">Copyable:</span>
        <MonoId id="p281" copyable />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-32">All features:</span>
        <MonoId id="p281" prefix="spawn" copyable />
      </div>
    </div>
  ),
}

export const Interactive: Story = {
  render: () => (
    <div className="flex flex-col gap-4 items-start">
      <p className="text-sm text-muted-foreground">Click to copy (hover for icon):</p>
      <MonoId id="p281" copyable />
      <MonoId id="c42" prefix="chat" copyable />
      <MonoId id="session-abc123" copyable />
    </div>
  ),
}
