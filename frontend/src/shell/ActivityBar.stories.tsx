import { useEffect, useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"
import { ChatCircle, ListDashes, Lightning } from "@phosphor-icons/react"
import { ActivityBar } from "./ActivityBar"
import { registry } from "./registry"

const meta: Meta<typeof ActivityBar> = {
  title: "Shell/ActivityBar",
  component: ActivityBar,
  parameters: {
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <div className="h-screen bg-background">
        <Story />
      </div>
    ),
  ],
}

export default meta
type Story = StoryObj<typeof ActivityBar>

function useRegisterDemoExtensions(withBadge = false) {
  useEffect(() => {
    registry.register({
      id: "demo-sessions",
      name: "Sessions",
      railItems: [
        {
          id: "sessions",
          icon: ListDashes,
          label: "Sessions",
          order: 0,
          badge: withBadge ? () => 3 : undefined,
        },
      ],
      panels: [],
      commands: [],
    })
    registry.register({
      id: "demo-chat",
      name: "Chat",
      railItems: [{ id: "chat", icon: ChatCircle, label: "Chat", order: 1 }],
      panels: [],
      commands: [],
    })
    registry.register({
      id: "demo-actions",
      name: "Actions",
      railItems: [{ id: "actions", icon: Lightning, label: "Actions", order: 2 }],
      panels: [],
      commands: [],
    })
    return () => {
      registry.unregister("demo-sessions")
      registry.unregister("demo-chat")
      registry.unregister("demo-actions")
    }
  }, [withBadge])
}

function Demo({ withBadge = false }: { withBadge?: boolean }) {
  useRegisterDemoExtensions(withBadge)
  const [active, setActive] = useState("sessions")
  return (
    <ActivityBar
      activeMode={active}
      onModeChange={setActive}
      onNewSession={() => console.log("new session")}
      onOpenSettings={() => console.log("settings")}
    />
  )
}

export const Default: Story = {
  render: () => <Demo />,
}

export const WithBadge: Story = {
  render: () => <Demo withBadge />,
}
