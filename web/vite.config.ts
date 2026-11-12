import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Backend runs on :8000; the app always talks to /api on the same origin.
// Build output: web/dist (Vite resolves outDir relative to this project root).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
