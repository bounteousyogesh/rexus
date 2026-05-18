import path from 'path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const rexusEnv = (env.REXUS_ENV || env.VITE_REXUS_ENV || 'development').toLowerCase()
  const backendUrl = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [react(), tailwindcss()],
    define: {
      'import.meta.env.VITE_REXUS_ENV': JSON.stringify(rexusEnv),
    },
    server: {
      allowedHosts: true,
      proxy: {
        '/api': backendUrl,
        '/health': backendUrl,
      },
    },
  }
})
