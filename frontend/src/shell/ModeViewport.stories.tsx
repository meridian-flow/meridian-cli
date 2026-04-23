import { useEffect, useState } from "react"
import type { Meta, StoryObj } from "@storybook/react-vite"
import { Button } from "@/components/ui/button"
import { ModeViewport } from "./ModeViewport"
import { registry } from "./registry"

const meta: Meta<typeof ModeViewport> = {
  title: "Shell/ModeViewport",
  component: ModeViewport,
  parameters: { layout: "fullscreen" },
}

export default meta
type Story = StoryObj<typeof ModeViewport>

const AlphaPanel = () => (
  <div className="flex h-full items-center justify-center bg-card">
    <div className="text-center">
      <p className="font-mono text-2xl text-accent-text">alpha</p>
      <p className="text-sm text-muted-foreground">first demo panel</p>
    </div>
  </div>
)

const BravoPanel = () => (
  <div className="flex h-full items-center justify-center bg-muted">
    <div className="text-center">
      <p className="font-mono text-2xl text-accent-text">bravo</p>
      <p className="text-sm text-muted-foreground">second demo panel</p>
    </div>
  </div>
)

function Demo() {
  useEffect(() => {
    registry.register({
      id: "demo-alpha",
      name: "Alpha",
      railItems: [],
      panels: [{ id: "alpha", component: AlphaPanel }],
      commands: [],
    })
    registry.register({
      id: "demo-bravo",
      name: "Bravo",
      railItems: [],
      panels: [{ id: "bravo", component: BravoPanel }],
      commands: [],
    })
    return () => {
      registry.unregister("demo-alpha")
      registry.unregister("demo-bravo")
    }
  }, [])

  const [mode, setMode] = useState("alpha")
  return (
    <div className="flex h-screen flex-col">
      <div className="flex gap-2 border-b border-border bg-background p-2">
        <Button size="sm" variant={mode === "alpha" ? "default" : "outline"} onClick={() => setMode("alpha")}>
          Alpha
        </Button>
        <Button size="sm" variant={mode === "bravo" ? "default" : "outline"} onClick={() => setMode("bravo")}>
          Bravo
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setMode("nonexistent")}>
          Unknown
        </Button>
      </div>
      <div className="flex-1">
        <ModeViewport activeMode={mode} />
      </div>
    </div>
  )
}

export const CrossFade: Story = {
  render: () => <Demo />,
}
