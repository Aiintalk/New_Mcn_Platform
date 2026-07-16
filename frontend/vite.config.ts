import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 固定 5175（5173/5174 历史被旧项目占用；与 playwright.config.ts webServer.url 一致）
    port: 5175,
    strictPort: true, // 端口被占则直接报错（避免静默切换到 5176 导致 E2E 探活失败）
    proxy: {
      '/api': 'http://127.0.0.1:8010',
    },
  },
})
