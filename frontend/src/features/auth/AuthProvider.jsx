/**
 * AuthProvider — estado global de autenticação.
 *
 * auth_status: 'loading' | 'authenticated' | 'unauthenticated' | 'pending' | 'disabled'
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { fetchMe } from './api.js'
import { setCsrfToken } from '../../lib/apiClient.js'
import { getAuthError } from './authErrors.js'

const AuthContext = createContext(null)

function initialAuthState() {
  const base = {
    auth_status: 'loading',
    user: null,
    profile: null,
    permissions: new Set(),
    csrf_token: '',
    ai_usage: null,
    auth_error: null,
  }

  if (typeof window === 'undefined') return base

  const params = new URLSearchParams(window.location.search)
  const authErrorCode = params.get('auth_error')
  if (!authErrorCode) return base

  params.delete('auth_error')
  const remaining = params.toString()
  window.history.replaceState(
    {},
    '',
    remaining ? `${window.location.pathname}?${remaining}` : window.location.pathname,
  )

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
  const callbackErrorRef = useRef(Boolean(state.auth_error))

  const refresh = useCallback(async () => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setState(s => ({ ...s, auth_status: 'loading', auth_error: null }))

    try {
      const me = await fetchMe(ctrl.signal)
      setCsrfToken(me.csrf_token || '')
      setState({
        auth_status: 'authenticated',
        user: { id: me.id, email: me.email, display_name: me.display_name,
                status: me.status, access_expires_at: me.access_expires_at },
        profile: { name: me.profile, display_name: me.profile_display },
        permissions: new Set(me.permissions || []),
        csrf_token: me.csrf_token || '',
        ai_usage: me.ai_usage || null,
        auth_error: null,
      })
    } catch (err) {
      if (err?.name === 'AbortError') return
      setCsrfToken('')
      const status = err?.status
      if (status === 403) {
        const isPending = (err?.detail || '').toLowerCase().includes('pendente')
        setState({
          auth_status: isPending ? 'pending' : 'disabled',
          user: null, profile: null, permissions: new Set(), csrf_token: '', ai_usage: null,
          auth_error: null,
        })
      } else {
        setState({
          auth_status: 'unauthenticated',
          user: null, profile: null, permissions: new Set(), csrf_token: '', ai_usage: null,
          auth_error: null,
        })
      }
    }
  }, [])

  useEffect(() => {
    // Quando o callback retornou auth_error, preservamos a mensagem na tela e
    // não fazemos /auth/me porque nenhuma sessão foi criada nesse fluxo.
    if (!callbackErrorRef.current) refresh()
    return () => abortRef.current?.abort()
  }, [refresh])

  const hasPermission = useCallback(code => state.permissions.has(code), [state.permissions])

  return (
    <AuthContext.Provider value={{ ...state, hasPermission, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}
