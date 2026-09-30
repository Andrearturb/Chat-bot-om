/**
 * Cliente HTTP centralizado do BFF.
 *
 * Regra de arquitetura: o navegador SEMPRE usa caminhos relativos
 * (/auth, /assistant, /assets, ...). Em desenvolvimento o Vite faz proxy
 * para o FastAPI; em produção o reverse proxy deve manter frontend e BFF
 * sob a mesma origem.
 *
 * Isso evita misturar localhost:5173 e localhost:8040, garante que o cookie
 * HttpOnly de sessão seja plantado/reenviado de forma same-origin e impede
 * que uma variável VITE_* faça o browser contornar o BFF/proxy.
 */

let _csrfToken = ''
let _unauthorizedHandler = null
let _unauthorizedHandling = null

export function setCsrfToken(token) { _csrfToken = token || '' }
export function getCsrfToken() { return _csrfToken }
export function setUnauthorizedHandler(handler) { _unauthorizedHandler = handler }

export class ApiError extends Error {
  constructor(message, { status = null, kind = 'http', detail = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind
    this.detail = detail
  }
}

function normalizePath(path) {
  if (typeof path !== 'string' || !path.startsWith('/')) {
    throw new ApiError('Caminho de API inválido.', { kind: 'configuration' })
  }
  return path
}

export async function apiFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const isMutating = !['GET', 'HEAD', 'OPTIONS'].includes(method)

  const headers = {
    Accept: 'application/json',
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(isMutating && _csrfToken ? { 'X-CSRF-Token': _csrfToken } : {}),
    ...(options.headers || {}),
  }

  let response
  try {
    response = await fetch(normalizePath(path), {
      ...options,
      headers,
      credentials: 'include',
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new ApiError('Não foi possível conectar ao servidor.', { kind: 'network' })
  }

  if (response.status === 204) return null

  let payload = null
  if ((response.headers.get('content-type') || '').includes('application/json')) {
    try { payload = await response.json() } catch { /* resposta sem JSON válido */ }
  }

  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/me' && path !== '/auth/logout'
        && _unauthorizedHandler && !_unauthorizedHandling) {
      // Não prende a requisição original nem repete o redirecionamento numa rajada.
      _unauthorizedHandling = Promise.resolve()
        .then(() => _unauthorizedHandler?.())
        .catch(() => {})
        .finally(() => { _unauthorizedHandling = null })
    }
    const detail = payload?.detail || null
    const message = typeof detail === 'string' ? detail : `Erro HTTP ${response.status}`
    throw new ApiError(message, {
      status: response.status,
      kind: response.status === 429 ? 'rate_limit' : 'http',
      detail,
    })
  }
  return payload
}

export const api = {
  get:    (path, opts)       => apiFetch(path, { ...opts, method: 'GET' }),
  post:   (path, body, opts) => apiFetch(path, { ...opts, method: 'POST',  body: _body(body) }),
  put:    (path, body, opts) => apiFetch(path, { ...opts, method: 'PUT',   body: _body(body) }),
  patch:  (path, body, opts) => apiFetch(path, { ...opts, method: 'PATCH', body: _body(body) }),
  delete: (path, opts)       => apiFetch(path, { ...opts, method: 'DELETE' }),
}

function _body(b) {
  if (b === undefined || b === null) return undefined
  return typeof b === 'string' || b instanceof FormData ? b : JSON.stringify(b)
}
