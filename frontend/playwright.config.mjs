import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/browser',
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:18173',
    headless: true,
    launchOptions: process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}
  },
  webServer: {
    command: 'pnpm dev --host 127.0.0.1 --port 18173 --strictPort',
    url: 'http://127.0.0.1:18173/tests/browser/fixture.html',
    timeout: 60000
  }
})
