// vite.config.ts
// v1.0.2: Vite dev server 5173 + 代理 /api → FastAPI 38080
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:38080',
        changeOrigin: true,
      },
      '/docs': {
        target: 'http://127.0.0.1:38080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
