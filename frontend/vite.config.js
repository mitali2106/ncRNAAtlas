import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the Flask API runs on :5000; Vite proxies /api to it so the
// browser talks to a single origin and no credentials live in client code.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_API_PROXY || 'http://127.0.0.1:5000', changeOrigin: true } },
  },
  build: {
    rollupOptions: {
      output: { manualChunks: { cytoscape: ['cytoscape'], charts: ['recharts'], react: ['react', 'react-dom', 'react-router-dom'] } },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
})
