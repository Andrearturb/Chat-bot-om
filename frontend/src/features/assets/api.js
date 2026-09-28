const BACKEND_URL = import.meta.env.VITE_BACKEND_URL?.trim()?.replace(/\/$/, '')

export class AssetsApiError extends Error {
  constructor(message, { status = null, kind = 'service' } = {}) {
    super(message)
    this.name = 'AssetsApiError'
    this.status = status
    this.kind = kind
  }
}

function ensureBackend() {
  if (!BACKEND_URL) throw new AssetsApiError('VITE_BACKEND_URL não configurada.', { kind: 'configuration' })
}

async function request(path, options = {}) {
  ensureBackend()
  let response
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(options.headers || {}),
      },
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new AssetsApiError('Não foi possível conectar ao backend.', { kind: 'network' })
  }

  if (!response.ok) {
    let detail = `Erro HTTP ${response.status}.`
    try {
      const payload = await response.json()
      detail = payload.detail || detail
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new AssetsApiError(detail, { status: response.status, kind: 'http' })
  }

  if (response.status === 204) return null
  try {
    return await response.json()
  } catch {
    throw new AssetsApiError('O backend retornou uma resposta inválida.', { kind: 'payload' })
  }
}

export function backendFileUrl(documentId, download = false) {
  ensureBackend()
  return `${BACKEND_URL}/assets/documents/${documentId}/file${download ? '?download=true' : ''}`
}

export function fetchAssetSummary({ signal } = {}) {
  return request('/assets/summary', { signal })
}

export function fetchAssetStores({ q = '', praca = '', signal } = {}) {
  const params = new URLSearchParams()
  if (q.trim()) params.set('q', q.trim())
  if (praca) params.set('praca', praca)
  return request(`/assets/stores${params.size ? `?${params}` : ''}`, { signal })
}

export function fetchAssetStoreFilters({ signal } = {}) {
  return request('/assets/stores/filters', { signal })
}

export function fetchAssetStore(storeId, { signal } = {}) {
  return request(`/assets/stores/${storeId}`, { signal })
}

export function createAsset(storeId, category, payload) {
  const paths = { climatization: 'climatization', fire: 'fire-safety', water: 'water' }
  return request(`/assets/stores/${storeId}/${paths[category]}`, { method: 'POST', body: JSON.stringify(payload) })
}

export function updateAsset(category, assetId, payload) {
  const paths = { climatization: 'climatization', fire: 'fire-safety', water: 'water' }
  return request(`/assets/${paths[category]}/${assetId}`, { method: 'PUT', body: JSON.stringify(payload) })
}

export function removeAsset(category, assetId) {
  const paths = { climatization: 'climatization', fire: 'fire-safety', water: 'water' }
  return request(`/assets/${paths[category]}/${assetId}`, { method: 'DELETE' })
}

export function createDocument(storeId, formData) {
  return request(`/assets/stores/${storeId}/documents`, { method: 'POST', body: formData })
}

export function updateDocument(documentId, formData) {
  return request(`/assets/documents/${documentId}`, { method: 'PUT', body: formData })
}

export function removeDocument(documentId) {
  return request(`/assets/documents/${documentId}`, { method: 'DELETE' })
}
