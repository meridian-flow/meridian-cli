import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"

export type Theme = "light" | "dark" | "system"
type ResolvedTheme = "light" | "dark"

interface ThemeContextValue {
  theme: Theme
  resolvedTheme: ResolvedTheme
  setTheme: (theme: Theme) => void
}

const STORAGE_KEY = "meridian-theme"

function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "light"
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light"
}

function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === "system" ? getSystemTheme() : theme
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "system"
    return (localStorage.getItem(STORAGE_KEY) as Theme) || "system"
  })

  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    resolveTheme(theme),
  )

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
    localStorage.setItem(STORAGE_KEY, next)
  }, [])

  // Listen for system preference changes when theme is "system"
  useEffect(() => {
    const update = () => setResolved(resolveTheme(theme))
    update()

    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)")
      mq.addEventListener("change", update)
      return () => mq.removeEventListener("change", update)
    }
  }, [theme])

  // Apply dark class to <html>
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", resolved === "dark")
  }, [resolved])

  const value = useMemo(
    () => ({ theme, resolvedTheme: resolved, setTheme }),
    [theme, resolved, setTheme],
  )

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider")
  }
  return ctx
}
