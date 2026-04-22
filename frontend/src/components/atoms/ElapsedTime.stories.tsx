import type { Meta, StoryObj } from "@storybook/react-vite"
import { ElapsedTime } from "./ElapsedTime"

const meta: Meta<typeof ElapsedTime> = {
  title: "Components/Atoms/ElapsedTime",
  component: ElapsedTime,
  parameters: {
    layout: "centered",
  },
  argTypes: {
    format: {
      control: "select",
      options: ["relative", "duration"],
    },
  },
}

export default meta
type Story = StoryObj<typeof ElapsedTime>

// Helper to create dates relative to now
const secondsAgo = (s: number) => new Date(Date.now() - s * 1000)
const minutesAgo = (m: number) => new Date(Date.now() - m * 60 * 1000)
const hoursAgo = (h: number) => new Date(Date.now() - h * 60 * 60 * 1000)
const daysAgo = (d: number) => new Date(Date.now() - d * 24 * 60 * 60 * 1000)

export const Default: Story = {
  args: {
    startedAt: minutesAgo(2),
    format: "relative",
  },
}

export const LiveTicking: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">These timers update every second:</p>
      <div className="flex items-center gap-2">
        <span className="text-sm w-24">Running:</span>
        <ElapsedTime startedAt={new Date()} format="duration" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm w-24">Started 5s ago:</span>
        <ElapsedTime startedAt={secondsAgo(5)} format="relative" />
      </div>
    </div>
  ),
}

export const Completed: Story = {
  render: () => {
    const start = minutesAgo(5)
    const end = minutesAgo(1)
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">These show static duration (ended):</p>
        <div className="flex items-center gap-2">
          <span className="text-sm w-32">Duration format:</span>
          <ElapsedTime startedAt={start} endedAt={end} format="duration" />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm w-32">Relative format:</span>
          <ElapsedTime startedAt={start} endedAt={end} format="relative" />
        </div>
      </div>
    )
  },
}

export const RelativeFormat: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-24">Just now:</span>
        <ElapsedTime startedAt={secondsAgo(3)} format="relative" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-24">30 seconds:</span>
        <ElapsedTime startedAt={secondsAgo(30)} format="relative" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-24">2 minutes:</span>
        <ElapsedTime startedAt={minutesAgo(2)} format="relative" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-24">1 hour:</span>
        <ElapsedTime startedAt={hoursAgo(1)} format="relative" />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground w-24">3 days:</span>
        <ElapsedTime startedAt={daysAgo(3)} format="relative" />
      </div>
    </div>
  ),
}

export const DurationFormat: Story = {
  render: () => {
    const now = new Date()
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground w-24">0 seconds:</span>
          <ElapsedTime 
            startedAt={now} 
            endedAt={now} 
            format="duration" 
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground w-24">45 seconds:</span>
          <ElapsedTime 
            startedAt={secondsAgo(45)} 
            endedAt={new Date()} 
            format="duration" 
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground w-24">4m 12s:</span>
          <ElapsedTime 
            startedAt={new Date(Date.now() - (4 * 60 + 12) * 1000)} 
            endedAt={new Date()} 
            format="duration" 
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground w-24">1h 2m:</span>
          <ElapsedTime 
            startedAt={new Date(Date.now() - (62 * 60) * 1000)} 
            endedAt={new Date()} 
            format="duration" 
          />
        </div>
      </div>
    )
  },
}
