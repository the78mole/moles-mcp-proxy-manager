import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendPort = process.env.BACKEND_PORT ?? '8001'
const frontendPort = parseInt(process.env.PORT ?? '5174', 10)

export default defineConfig({
  plugins: [vue()],
  server: {
    port: frontendPort,
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        ws: true,
      },
      '/v1': `http://localhost:${backendPort}`,
    }
  }
})
