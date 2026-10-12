import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => cleanup())

// Recharts' ResponsiveContainer needs ResizeObserver, which jsdom lacks.
globalThis.ResizeObserver =
  globalThis.ResizeObserver ||
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
