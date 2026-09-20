import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const API_URL = env.API_URL || ''
  // API_URL 为空时，代理到 velvet_thunder Dashboard（8080）
  const proxyTarget =
    API_URL && /^https?:\/\//i.test(API_URL) ? API_URL : 'http://127.0.0.1:8080'

  return {
    plugins: [vue()],
    define: {
      API_URL: JSON.stringify(API_URL),
    },
    server: {
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
        // KENN 经 Dashboard：/kenn/api/* → 后端再转到 :8090
        '/kenn': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
