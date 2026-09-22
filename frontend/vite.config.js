import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET = process.env.PROXY_API_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target: API_TARGET, changeOrigin: true } } },
  preview: { allowedHosts: ['.onrender.com'], proxy: { '/api': { target: API_TARGET, changeOrigin: true } } },
})
