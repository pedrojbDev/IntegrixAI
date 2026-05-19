import path from "node:path"

import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

function toViteBase(value: string) {
  if (value === "/") {
    return "/"
  }
  const withLeading = value.startsWith("/") ? value : `/${value}`
  return withLeading.endsWith("/") ? withLeading : `${withLeading}/`
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const appBasename = env.VITE_APP_BASENAME || (mode === "production" ? "/dashboard" : "/")

  return {
    base: toViteBase(appBasename),
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      proxy: {
        "/ops": "http://localhost:8000",
        "/health": "http://localhost:8000",
        "/tools": "http://localhost:8000",
      },
    },
  }
})
