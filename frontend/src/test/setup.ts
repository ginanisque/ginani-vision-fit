import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Auto-cleanup needs a global afterEach; provide it explicitly since vitest globals are off.
afterEach(() => {
  cleanup()
})

// jsdom does not implement object URLs; stub them for previews.
if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = () => 'blob:mock-url'
  URL.revokeObjectURL = () => undefined
}

