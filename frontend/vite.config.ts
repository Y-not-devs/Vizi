import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// .env общий и лежит в корне репозитория.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const apiTarget = `http://127.0.0.1:${env.API_PORT || 8000}`

  return {
    envDir: '..',
    plugins: [react()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: Number(env.WEB_PORT || 5173),
      // Фронт обращается к /api — Vite проксирует на FastAPI. Никакого CORS и хардкода URL.
      proxy: {
        '/api': apiTarget,
        '/uploads': apiTarget,
      },
    },
  }
})
