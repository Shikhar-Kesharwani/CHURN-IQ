// CHURN-55: browser smoke tests against a real uvicorn backend.
//
//   cd frontend && npx playwright install chromium   # once
//   npm run test:e2e
//
// Playwright starts both servers itself:
//   * the FastAPI backend (backend/main.py) on 127.0.0.1:8000, using the
//     committed model and data, with no Gemini key and no email config;
//   * a production build of the frontend (vite build + vite preview) on
//     127.0.0.1:4173, pointed at that backend.
// E2E_PYTHON selects the Python that has backend/requirements.txt installed.
import { defineConfig, devices } from '@playwright/test'

const API = 'http://127.0.0.1:8000'
const WEB = 'http://127.0.0.1:4173'
const python = process.env.E2E_PYTHON || 'python'

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.js',          // not *.test.js, so vitest never picks these up
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: WEB,
    trace: 'off',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${python} -m uvicorn main:app --host 127.0.0.1 --port 8000`,
      cwd: '../backend',
      url: `${API}/`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: { GEMINI_API_KEY: '', EMAIL_API_TOKEN: '', GMAIL_SENDER: '', GMAIL_APP_PASS: '' },
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      command: 'npx vite build && npx vite preview --host 127.0.0.1 --port 4173 --strictPort',
      url: WEB,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: { VITE_API_URL: API },
    },
  ],
})

export { API }
