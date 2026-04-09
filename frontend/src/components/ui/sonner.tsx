import { Toaster as SonnerToaster, type ToasterProps } from "sonner"
import { useTheme } from "@/components/theme-provider"

/**
 * Meridian toast container.
 * Uses sonner under the hood with theme-aware styling.
 */
function Toaster(props: ToasterProps) {
  let theme: ToasterProps["theme"] = "light"

  // Try to use theme context — fall back to light if outside provider
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const { resolvedTheme } = useTheme()
    theme = resolvedTheme
  } catch {
    // Outside ThemeProvider (e.g. Storybook) — default to light
  }

  return (
    <SonnerToaster
      theme={theme}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
          error: "group-[.toaster]:text-destructive",
          success: "group-[.toaster]:text-success",
          warning: "group-[.toaster]:text-muted-foreground",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
