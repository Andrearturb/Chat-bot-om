import { apiFetch } from '../../lib/apiClient.js'
import { exportParams, filtersParams } from './filters.js'

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

export function fetchAssetStores({ q = '', pracas = [], storeIds = [], signal } = {}) {
  const p = filtersParams({ pracas, storeIds })
  if (q.trim()) p.set('q', q.trim())
  return request(`/assets/stores${p.size ? `?${p}` : ''}`, { signal })
}

export const fetchStoreOptions = ({ signal } = {}) => request('/assets/stores/options', { signal })

export const fetchExportPreview = ({ filters, types, scope, signal } = {}) =>
  request(`/assets/export/preview?${exportParams(filters, types, scope)}`, { signal })

/** Baixa a planilha. Usa fetch direto (a resposta é um arquivo) e traduz os erros para mensagens. */
export async function downloadAssetsExport({ filters, types, scope, signal } = {}) {
  let response
  try {
    response = await fetch(`/assets/export?${exportParams(filters, types, scope)}`, { credentials: 'include', signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new AssetsApiError('Não foi possível conectar ao servidor.', { kind: 'network' })
  }
  if (!response.ok) {
    if (response.status === 401) throw new AssetsApiError('Sua sessão expirou. Entre novamente.', { status: 401 })
    let detail = ''
    try { detail = (await response.json())?.detail } catch { /* corpo sem JSON */ }
    throw new AssetsApiError(typeof detail === 'string' && detail ? detail : `Erro ${response.status}`, { status: response.status })
  }
  const filename = /filename="([^"]+)"/.exec(response.headers.get('content-disposition') || '')?.[1] || 'ativos.xlsx'
  return { blob: await response.blob(), filename }
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
