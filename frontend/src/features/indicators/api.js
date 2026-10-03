import { apiFetch } from '../../lib/apiClient.js'
import { adaptPreventivePayload, adaptServicesPayload } from './dataAdapter'

export class IndicatorsApiError extends Error {
  constructor(message, { status = null, kind = 'service' } = {}) {
    super(message); this.name = 'IndicatorsApiError'; this.status = status; this.kind = kind
  }
}

export async function fetchIndicatorsData({ signal } = {}) {
  let payload
  try {
    payload = await apiFetch('/services', { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new IndicatorsApiError(error.message || 'Erro ao consultar /services.',
      { status: error?.status, kind: error?.kind || 'http' })
  }
  try {
    return adaptServicesPayload(payload)
  } catch (error) {
    throw new IndicatorsApiError(error.message || 'Não foi possível interpretar os dados.', { kind: 'payload' })
  }
}

export async function fetchPreventiveIndicatorsData({ signal } = {}) {
  let payload
  try {
    payload = await apiFetch('/preventive-services', { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new IndicatorsApiError(error.message || 'Erro ao consultar /preventive-services.',
      { status: error?.status, kind: error?.kind || 'http' })
  }
  try {
    return adaptPreventivePayload(payload)
  } catch (error) {
    throw new IndicatorsApiError(error.message || 'Não foi possível interpretar os dados preventivos.', { kind: 'payload' })
  }
}
