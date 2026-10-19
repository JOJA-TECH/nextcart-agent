import { defineConfig, devices } from "@playwright/test"

// E2E contra el stack real: levanta vite dev y uvicorn (con el modelo) si no
// están corriendo. Con reuseExistingServer en local se reutilizan los ya activos.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "pnpm dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "uv --directory ../backend run uvicorn src.backend:app --host 127.0.0.1 --port 8000",
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { NEXTCART_MODEL_PATH: "../artifacts/nextcart_model.json" },
    },
  ],
})
