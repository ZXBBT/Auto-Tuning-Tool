import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the Vite server proxies the API (incl. the telemetry WebSocket) to
// uvicorn, so the browser sees one origin -- the same shape Caddy gives in production.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
  build: {
    rollupOptions: {
      // the charting library changes far less often than app code: cache it separately
      output: { manualChunks: { charts: ['recharts'] } },
    },
  },
})
