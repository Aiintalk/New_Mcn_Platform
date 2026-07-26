import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 固定 5175（5173/5174 历史被旧项目占用；与 playwright.config.ts webServer.url 一致）
    port: 5175,
    strictPort: true, // 端口被占则直接报错（避免静默切换到 5176 导致 E2E 探活失败）
    host: true, // 暴露到 LAN/Tailscale（等价 --host；npm run dev 不带参也能被其它主机访问）
    allowedHosts: true, // 放开 Host 头校验：允许经 LAN IP / Tailscale 域名等非 localhost 形式访问（dev-only）
    proxy: {
      '/api': 'http://127.0.0.1:8010',
    },
  },
})
