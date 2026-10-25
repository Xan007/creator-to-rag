import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load ALL env vars (including non-VITE_ ones) so the dev proxy target can be
  // configured without exposing it to the client bundle.
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'
  const usePolling = env.CHOKIDAR_USEPOLLING === 'true'

  // Keep `/api/...` requests same-origin in dev, so the browser never has to do
  // a CORS preflight. The prefix is stripped before hitting FastAPI.
  const proxy = {
    '/api': {
      target: proxyTarget,
      changeOrigin: true,
      rewrite: (requestPath: string) => requestPath.replace(/^\/api/, ''),
    },
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      proxy,
      watch: usePolling
        ? { usePolling: true, interval: 1000 }
        : {
            // Watching the Python venv / data folders burns CPU on Windows.
            ignored: ['**/.venv/**', '**/__pycache__/**', '**/dist/**', '**/.pytest_cache/**'],
          },
      warmup: {
        clientFiles: ['./src/main.tsx', './src/App.tsx'],
      },
    },
    preview: {
      proxy,
    },
    optimizeDeps: {
      include: [
        'react',
        'react-dom',
        'i18next',
        'react-i18next',
        'lucide-react',
        '@tanstack/react-table',
      ],
    },
    build: {
      target: 'baseline-widely-available',
      // Private source code: do not publish source maps.
      sourcemap: false,
      chunkSizeWarningLimit: 600,
      cssCodeSplit: true,
      reportCompressedSize: true,
      rolldownOptions: {
        output: {
          // Vite 8 uses Rolldown: `manualChunks` is deprecated in favour of
          // `codeSplitting` groups. See https://rolldown.rs/in-depth/manual-code-splitting
          codeSplitting: {
            groups: [
              {
                name: 'react-vendor',
                test: /node_modules[\\/](?:react|react-dom|scheduler)[\\/]/,
                priority: 40,
              },
              {
                name: 'i18n',
                test: /node_modules[\\/](?:i18next|i18next-browser-languagedetector|react-i18next)[\\/]/,
                priority: 25,
              },
              {
                // Dialog primitives are only needed by the lazy-loaded modals
                // and the details sheet, so keep them out of the initial vendor.
                name: 'radix',
                test: /node_modules[\\/](?:@radix-ui|aria-hidden|react-remove-scroll|react-remove-scroll-bar|react-style-singleton|get-nonce|use-callback-ref|use-sidecar|detect-node-es)[\\/]/,
                priority: 22,
              },
              {
                name: 'table',
                test: /node_modules[\\/]@tanstack[\\/]/,
                priority: 20,
              },
            ],
          },
        },
      },
    },
  }
})
