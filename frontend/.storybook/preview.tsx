import type { Preview } from "@storybook/react-vite"
import type { Theme } from "@/components/theme-provider"
import { ThemeProvider } from "@/components/theme-provider"
import "@/index.css"

type ToolbarTheme = Extract<Theme, "light" | "dark">

const preview: Preview = {
  decorators: [
    (Story, context) => {
      const selectedTheme = (context.globals.theme ?? "light") as ToolbarTheme

      if (typeof document !== "undefined") {
        const root = document.documentElement
        root.classList.toggle("dark", selectedTheme === "dark")
        root.classList.toggle("light", selectedTheme === "light")
      }

      if (typeof window !== "undefined") {
        localStorage.setItem("meridian-theme", selectedTheme)
      }

      return (
        <ThemeProvider>
          <div className="min-h-screen bg-background p-4 text-foreground">
            <Story />
          </div>
        </ThemeProvider>
      )
    },
  ],
  globalTypes: {
    theme: {
      name: "Theme",
      description: "Toggle Meridian light/dark theme",
      defaultValue: "light",
      toolbar: {
        icon: "contrast",
        dynamicTitle: true,
        items: [
          { value: "light", title: "Light" },
          { value: "dark", title: "Dark" },
        ],
      },
    },
  },
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: "transparent",
      values: [{ name: "transparent", value: "transparent" }],
    },
    viewport: {
      options: {
        desktopExpanded: {
          name: "Desktop Expanded (1440)",
          styles: { width: "1440px", height: "900px" },
        },
        medium: {
          name: "Medium (1024)",
          styles: { width: "1024px", height: "768px" },
        },
        compact: {
          name: "Compact (768)",
          styles: { width: "768px", height: "1024px" },
        },
        mobile: {
          name: "Mobile (390)",
          styles: { width: "390px", height: "844px" },
        },
      },
    },
  },
}

export default preview
