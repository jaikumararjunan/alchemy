import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') }
  },
  server: {
    port: 3000,
    host: '0.0.0.0',   // needed inside Docker
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: p => p.replace(/^\/api/, ''),
      },
      '/ws': {
        target: process.env.VITE_API_URL?.replace('http', 'ws') || 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',      // Docker copies dist/ → /app/static/
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor:       ['react', 'react-dom', 'react-router-dom'],
          charts:       ['recharts'],
          query:        ['@tanstack/react-query'],
        },
      },
    },
  },
}))
