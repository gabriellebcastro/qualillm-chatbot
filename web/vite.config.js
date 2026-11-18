import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// O proxy faz o frontend chamar `/api/...` como se fosse a mesma origem, o que
// evita CORS no desenvolvimento e mantem `web/src/api.js` sem URL absoluta —
// em producao (`vite build`) os mesmos caminhos funcionam servidos pelo backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
