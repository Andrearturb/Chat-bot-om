import { apiFetch } from '../../lib/apiClient.js'

export class AssetsApiError extends Error {
  constructor(message, { status = null, kind = 'service' } = {}) {
    super(message); this.name = 'AssetsApiError'; this.status = status; this.kind = kind
  }
}

async function request(path, options = {}) {
  try {
    return await apiFetch(path, options)
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new AssetsApiError(error.message || 'Erro ao comunicar com o backend.',
      { status: error?.status, kind: error?.kind || 'http' })
  }
}

export function backendFileUrl(documentId, download = false) {
  return `/assets/documents/${documentId}/file${download ? '?download=true' : ''}`
}

export const fetchAssetSummary     = ({ signal } = {}) => request('/assets/summary', { signal })
export const fetchAssetStoreFilters = ({ signal } = {}) => request('/assets/stores/filters', { signal })
export const fetchAssetStore        = (id, { signal } = {}) => request(`/assets/stores/${id}`, { signal })

export function fetchAssetStores({ q = '', praca = '', signal } = {}) {
  const p = new URLSearchParams()
  if (q.trim()) p.set('q', q.trim())
  if (praca) p.set('praca', praca)
  return request(`/assets/stores${p.size ? `?${p}` : ''}`, { signal })
}

const PATHS = { climatization: 'climatization', fire: 'fire-safety', water: 'water' }

export const createAsset  = (storeId, cat, payload) =>
  request(`/assets/stores/${storeId}/${PATHS[cat]}`, { method: 'POST', body: JSON.stringify(payload) })
export const updateAsset  = (cat, assetId, payload) =>
  request(`/assets/${PATHS[cat]}/${assetId}`, { method: 'PUT', body: JSON.stringify(payload) })
export const removeAsset  = (cat, assetId) =>
  request(`/assets/${PATHS[cat]}/${assetId}`, { method: 'DELETE' })

export const createDocument = (storeId, formData) =>
  request(`/assets/stores/${storeId}/documents`, { method: 'POST', body: formData })
export const updateDocument = (documentId, formData) =>
  request(`/assets/documents/${documentId}`, { method: 'PUT', body: formData })
export const removeDocument = (documentId) =>
  request(`/assets/documents/${documentId}`, { method: 'DELETE' })
