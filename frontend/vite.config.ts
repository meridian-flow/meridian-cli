import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "path"

export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    allowedHosts: true,
    proxy: {
      "/api": "http://localhost:7676",
      "/ws": { target: "ws://localhost:7676", ws: true },
    },
  },
  build: {
    outDir: "dist",
  },
})
