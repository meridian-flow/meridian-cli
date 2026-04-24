import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import { TestChatPage } from "@/features/test-chat/TestChatPage"

import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <TooltipProvider>
        <TestChatPage />
      </TooltipProvider>
    </ThemeProvider>
  </StrictMode>,
)
