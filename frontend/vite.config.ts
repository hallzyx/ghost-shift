import { fileURLToPath } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// El cliente siempre llama a `/api/*`; Vite lo reenvía al backend FastAPI quitando
// el prefijo. Cambia el destino con VITE_BACKEND_URL si el backend no está en :8000.
export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), 'VITE_'), ...process.env };
  const backend = env.VITE_BACKEND_URL ?? 'http://localhost:8000';
  const mock = env.VITE_MOCK === '1';
  const proxy = {
    '/api': {
      target: backend,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ''),
    },
  };
  return {
    plugins: [react()],
    // Sin VITE_MOCK=1 el módulo mock se sustituye por un stub vacío.
    resolve: mock
      ? {}
      : { alias: [{ find: /^\.\/mock$/, replacement: fileURLToPath(new URL('./src/mock/disabled.ts', import.meta.url)) }] },
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
    build: { target: 'es2020' },
  };
});
