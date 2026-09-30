/**
 * AuthProvider — estado global de autenticação.
 *
 * auth_status: 'loading' | 'redirecting' | 'authenticated' | 'unauthenticated' | 'pending' | 'disabled'
 *
 * Navegação sem sessão:
 * - "/" (ou qualquer tela do app) → vai direto para o login do Keycloak, que já
 *   tem a identidade visual do Chat-bot O&M (uma única tela de login);
 * - "/login" → página de apresentação (retorno do logout, erros e acesso negado),
 *   sem redirecionamento automático para não criar laços.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  clearLoginMarker,
  consumeLoggedOutNotice,
  fetchMe,
  isLoginPath,
  LOGIN_PATH,
  loginRecentlyStarted,
  startLogin,
} from './api.js'
import { setCsrfToken } from '../../lib/apiClient.js'
import { getAuthError } from './authErrors.js'

const AuthContext = createContext(null)

const EMPTY_SESSION = {
  user: null,
  profile: null,
  permissions: new Set(),
  csrf_token: '',
  ai_usage: null,
}

function replaceUrl(path) {
  if (typeof window === 'undefined') return
  if (window.location.pathname + window.location.search !== path) {
    window.history.replaceState({}, '', path)
  }
}

function initialAuthState() {
  const base = { auth_status: 'loading', ...EMPTY_SESSION, auth_error: null, notice: null }
  if (typeof window === 'undefined') return base

  const params = new URLSearchParams(window.location.search)
  const authErrorCode = params.get('auth_error')
  if (!authErrorCode) {
    const notice = isLoginPath() && consumeLoggedOutNotice() ? 'Você saiu com segurança.' : null
    return { ...base, notice }
  }

  // O callback informou um problema: nenhuma sessão foi criada nesse fluxo.
  clearLoginMarker()
  replaceUrl(LOGIN_PATH)
  const authError = getAuthError(authErrorCode)
  if (authErrorCode === 'pending') return { ...base, auth_status: 'pending', auth_error: authError }
  if (authErrorCode === 'disabled') return { ...base, auth_status: 'disabled', auth_error: authError }
  return { ...base, auth_status: 'unauthenticated', auth_error: authError }
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth deve ser usado dentro de <AuthProvider>')
  return ctx
}

export function AuthProvider({ children }) {
  const [state, setState] = useState(initialAuthState)
  const abortRef = useRef(null)
  const callbackErrorRef = useRef(state.auth_status !== 'loading')

  // silent: revalida permissões sem trocar a tela por "Verificando acesso…"
  // (ex.: administrador alterou o próprio perfil na Gestão de Usuários).
  const refresh = useCallback(async ({ silent = false } = {}) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    if (!silent) setState(s => ({ ...s, auth_status: 'loading', auth_error: null }))

    try {
      const me = await fetchMe(ctrl.signal)
      setCsrfToken(me.csrf_token || '')
      clearLoginMarker()
      if (isLoginPath()) replaceUrl('/')
      setState({
        auth_status: 'authenticated',
        user: { id: me.id, email: me.email, username: me.username, display_name: me.display_name,
                status: me.status, access_expires_at: me.access_expires_at },
        profile: { name: me.profile, display_name: me.profile_display },
        permissions: new Set(me.permissions || []),
        csrf_token: me.csrf_token || '',
        ai_usage: me.ai_usage || null,
        auth_error: null,
        notice: null,
      })
    } catch (err) {
      if (err?.name === 'AbortError') return
      setCsrfToken('')
      const status = err?.status

      if (status === 403) {
        const isPending = (err?.detail || '').toLowerCase().includes('pendente')
        replaceUrl(LOGIN_PATH)
        setState({ auth_status: isPending ? 'pending' : 'disabled', ...EMPTY_SESSION, auth_error: null, notice: null })
        return
      }

      if (status === 401 && !isLoginPath()) {
        if (loginRecentlyStarted()) {
          // Voltou do Keycloak sem sessão válida: mostra o motivo em vez de repetir o login.
          clearLoginMarker()
          replaceUrl(LOGIN_PATH)
          setState({ auth_status: 'unauthenticated', ...EMPTY_SESSION,
                     auth_error: getAuthError('session_not_started'), notice: null })
          return
        }
        setState(s => ({ ...s, auth_status: 'redirecting' }))
        startLogin()
        return
      }

      replaceUrl(LOGIN_PATH)
      setState(s => ({
        auth_status: 'unauthenticated',
        ...EMPTY_SESSION,
        auth_error: status === 401 ? null : getAuthError('unavailable'),
        notice: status === 401 ? s.notice : null,
      }))
    }
  }, [])

  useEffect(() => {
    // Quando o callback retornou auth_error, preservamos a mensagem na tela e
    // não fazemos /auth/me porque nenhuma sessão foi criada nesse fluxo.
    if (!callbackErrorRef.current) refresh()
    return () => abortRef.current?.abort()
  }, [refresh])

  const hasPermission = useCallback(code => state.permissions.has(code), [state.permissions])
  const isAdmin = state.profile?.name === 'ADMINISTRADOR' && state.permissions.has('users.manage')

  return (
    <AuthContext.Provider value={{ ...state, hasPermission, isAdmin, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}
