import { apiFetch } from '../../lib/apiClient.js'

export class SettingsApiError extends Error {
  constructor(message, { kind = 'service', status = null } = {}) {
    super(message)
    this.name = 'SettingsApiError'
    this.kind = kind
    this.status = status
  }
}

export async function fetchSystemStatus({ signal } = {}) {
  try {
    return await apiFetch('/health', {
      method: 'GET',
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new SettingsApiError(error.message || 'Não foi possível verificar o status do sistema.', {
      kind: error?.kind || 'http',
      status: error?.status || null,
    })
  }
}
