import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Local development proxies /api to the Python quality service on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Playwright specs live under tests/ and use a real browser, not Vitest.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
