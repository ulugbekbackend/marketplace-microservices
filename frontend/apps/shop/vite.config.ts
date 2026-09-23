import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    host: true,
    allowedHosts: ['shop.localhost'],
  },
  preview: {
    port: 4173,
    host: true,
    allowedHosts: ['shop.localhost'],
  },
  build: {
    target: 'es2023',
    sourcemap: true,
  },
})
