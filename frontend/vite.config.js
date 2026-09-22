import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api/* is proxied to the FastAPI backend so the browser never hits CORS in dev.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } } },
})
