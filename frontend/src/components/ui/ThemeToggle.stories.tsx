import type { Meta, StoryObj } from "@storybook/react-vite"
import { ThemeToggle } from "./theme-toggle"
import { ThemeProvider } from "@/components/theme-provider"

const meta = {
  title: "UI/ThemeToggle",
  component: ThemeToggle,
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <ThemeProvider>
        <Story />
      </ThemeProvider>
    ),
  ],
} satisfies Meta<typeof ThemeToggle>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {}
