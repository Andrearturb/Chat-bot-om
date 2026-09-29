import { api } from '../../lib/apiClient.js'

export function fetchMe(signal) { return api.get('/auth/me', { signal }) }

export function startLogin() {
  // Usa caminho relativo — o proxy do Vite (DEV) ou o servidor (PROD)
  // encaminha para o backend. O redirect chain permanece na mesma origem.
  window.location.href = '/auth/login'
}

export function logout() { return api.post('/auth/logout', {}) }
export function fetchAiUsage(signal) { return api.get('/auth/usage', { signal }) }
