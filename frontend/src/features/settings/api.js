const BACKEND_URL = import.meta.env.VITE_BACKEND_URL?.trim()?.replace(/\/$/, '')

export class SettingsApiError extends Error {
  constructor(message, { kind = 'service', status = null } = {}) {
    super(message)
    this.name = 'SettingsApiError'
    this.kind = kind
    this.status = status
  }
}

export async function fetchSystemStatus({ signal } = {}) {
  if (!BACKEND_URL) {
    throw new SettingsApiError('O endereço do serviço não está configurado.', { kind: 'configuration' })
  }

  let response
  try {
    response = await fetch(`${BACKEND_URL}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new SettingsApiError('Não foi possível conectar ao Gentileza agora.', { kind: 'network' })
  }

  let payload
  try {
    payload = await response.json()
  } catch {
    throw new SettingsApiError('O serviço retornou uma resposta inválida.', {
      kind: 'payload',
      status: response.status,
    })
  }

  if (response.status >= 500 && !payload?.components) {
    throw new SettingsApiError('Não foi possível verificar o status do sistema.', {
      kind: 'http',
      status: response.status,
    })
  }

  return payload
}
