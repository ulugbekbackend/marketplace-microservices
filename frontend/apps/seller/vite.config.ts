import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5174,
    strictPort: true,
    host: true,
    allowedHosts: ['seller.localhost'],
  },
  preview: {
    port: 4174,
    host: true,
    allowedHosts: ['seller.localhost'],
  },
  build: {
    target: 'es2023',
    sourcemap: true,
  },
})
