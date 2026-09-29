import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// O proxy garante que tudo fica na mesma origem (localhost:5173),
// resolvendo o problema de SameSite cookie entre frontend e backend.
//
// Dentro do Docker: target usa o hostname do serviço 'backend:8000'.
// Fora do Docker, defina BACKEND_TARGET=http://localhost:8040 ao iniciar o Vite.
// O browser continua chamando apenas localhost:5173; somente o proxy conhece o backend.
const BACKEND_TARGET = process.env.BACKEND_TARGET || 'http://backend:8000'

const proxyRoutes = ['/auth', '/assistant', '/assets', '/services', '/users', '/audit', '/chatbot', '/health', '/imports']

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: Object.fromEntries(
      proxyRoutes.map(route => [
        route,
        { target: BACKEND_TARGET, changeOrigin: true, secure: false },
      ])
    ),
  },
})
