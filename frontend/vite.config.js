import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const backend = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:5000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@shared': fileURLToPath(new URL('../shared', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Same-origin proxy: the session cookie never needs cross-site settings.
    proxy: { '/api': { target: backend, changeOrigin: false } },
    fs: { allow: ['..'] },
  },
  preview: {
    port: 4173,
    proxy: { '/api': { target: backend, changeOrigin: false } },
  },
});
