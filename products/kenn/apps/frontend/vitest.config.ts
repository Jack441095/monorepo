import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// Separate from vite.config.ts so the production build's type-check never has to know about a `test` key, and so the
// component environment is opt-in per file rather than global. The API, composable and util tests run in node, which
// is faster; a test that mounts a component carries `// @vitest-environment happy-dom` at the top.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'node',
  },
})
