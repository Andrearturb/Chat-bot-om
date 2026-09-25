import { adaptServicesPayload } from './dataAdapter'

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL?.trim()?.replace(/\/$/, '')

export class IndicatorsApiError extends Error {
  constructor(message, { status = null, kind = 'service' } = {}) {
    super(message)
    this.name = 'IndicatorsApiError'
    this.status = status
    this.kind = kind
  }
}

export async function fetchIndicatorsData({ signal } = {}) {
  if (!BACKEND_URL) {
    throw new IndicatorsApiError('VITE_BACKEND_URL não configurada.', { kind: 'configuration' })
  }

  let response
  try {
    response = await fetch(`${BACKEND_URL}/services`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new IndicatorsApiError('Não foi possível conectar ao backend.', { kind: 'network' })
  }

  if (!response.ok) {
    throw new IndicatorsApiError(`Erro HTTP ${response.status} ao consultar /services.`, {
      status: response.status,
      kind: 'http',
    })
  }

  let payload
  try {
    payload = await response.json()
  } catch {
    throw new IndicatorsApiError('O backend retornou uma resposta inválida.', { kind: 'payload' })
  }

  try {
    return adaptServicesPayload(payload)
  } catch (error) {
    throw new IndicatorsApiError(error.message || 'Não foi possível interpretar os dados do backend.', {
      kind: 'payload',
    })
  }
}
