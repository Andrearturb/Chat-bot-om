import { api } from '../../lib/apiClient.js'

export const LOGIN_PATH = '/login'

// Marcadores não sensíveis em sessionStorage (nada de tokens ou dados pessoais).
const REDIRECT_KEY = 'om-auth-login-started-at'
const LOGOUT_KEY = 'om-auth-logged-out'
const REDIRECT_GUARD_MS = 20_000

function readStorage(key) {
  try { return sessionStorage.getItem(key) } catch { return null }
}

function writeStorage(key, value) {
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch { /* armazenamento indisponível: segue sem o marcador */ }
}

export function fetchMe(signal) { return api.get('/auth/me', { signal }) }

export function isLoginPath(pathname = window.location.pathname) {
  return pathname.replace(/\/+$/, '') === LOGIN_PATH
}

/** Inicia o fluxo OIDC existente: /auth/login → Keycloak (tema gentil-om). */
export function startLogin() {
  writeStorage(REDIRECT_KEY, String(Date.now()))
  // Caminho relativo: o proxy do Vite (DEV) ou o reverse proxy (PROD) mantém
  // tudo na mesma origem do cookie de sessão.
  window.location.assign('/auth/login')
}

/** Evita laço de redirecionamento caso a sessão não se confirme após o login. */
export function loginRecentlyStarted(now = Date.now()) {
  const startedAt = Number(readStorage(REDIRECT_KEY) || 0)
  return startedAt > 0 && now - startedAt < REDIRECT_GUARD_MS
}

export function clearLoginMarker() { writeStorage(REDIRECT_KEY, null) }

export function consumeLoggedOutNotice() {
  const flag = readStorage(LOGOUT_KEY)
  if (flag) writeStorage(LOGOUT_KEY, null)
  return Boolean(flag)
}

/** Volta para /login sem sessão (usado nas telas de acesso pendente/indisponível). */
export function leaveToLogin() {
  window.location.assign(LOGIN_PATH)
}

/**
 * Encerra a sessão da aplicação e, em seguida, a sessão SSO do Keycloak.
 * O backend devolve a URL de logout OIDC, que retorna o usuário para /login.
 */
export async function logoutAndRedirect() {
  let target = LOGIN_PATH
  try {
    const result = await api.post('/auth/logout', {})
    if (result?.logout_url) target = result.logout_url
  } catch { /* sessão já inválida: basta voltar ao /login */ }
  writeStorage(LOGOUT_KEY, '1')
  clearLoginMarker()
  window.location.assign(target)
}

export function logout() { return api.post('/auth/logout', {}) }
export function fetchAiUsage(signal) { return api.get('/auth/usage', { signal }) }
