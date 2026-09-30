import test from 'node:test'
import assert from 'node:assert/strict'

import { ApiError, apiFetch, setCsrfToken, setUnauthorizedHandler } from './apiClient.js'

test('apiFetch usa caminho relativo e envia cookies para o BFF same-origin', async () => {
  const originalFetch = globalThis.fetch
  let call
  globalThis.fetch = async (url, options) => {
    call = { url, options }
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }

  try {
    const result = await apiFetch('/auth/me')
    assert.deepEqual(result, { ok: true })
    assert.equal(call.url, '/auth/me')
    assert.equal(call.options.credentials, 'include')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('apiFetch envia CSRF em chamadas mutáveis sem trocar a origem', async () => {
  const originalFetch = globalThis.fetch
  let call
  globalThis.fetch = async (url, options) => {
    call = { url, options }
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    })
  }

  try {
    setCsrfToken('csrf-test')
    await apiFetch('/auth/logout', { method: 'POST', body: '{}' })
    assert.equal(call.url, '/auth/logout')
    assert.equal(call.options.credentials, 'include')
    assert.equal(call.options.headers['X-CSRF-Token'], 'csrf-test')
  } finally {
    setCsrfToken('')
    globalThis.fetch = originalFetch
  }
})

// ── 401 no meio do uso: o AuthProvider registra um handler que leva ao login ──

function mockUnauthorizedFetch() {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Sessão inválida' }), {
    status: 401,
    headers: { 'content-type': 'application/json' },
  })
  return () => { globalThis.fetch = originalFetch }
}

function assertApiError401(err) {
  assert.ok(err instanceof ApiError)
  assert.equal(err.status, 401)
  return true
}

test('401 fora de /auth/me aciona o handler uma vez e continua rejeitando com ApiError', async () => {
  const restoreFetch = mockUnauthorizedFetch()
  let calls = 0
  setUnauthorizedHandler(async () => { calls += 1 })

  try {
    await assert.rejects(apiFetch('/assets/stores'), assertApiError401)
    assert.equal(calls, 1)
  } finally {
    setUnauthorizedHandler(null)
    restoreFetch()
  }
})

test('401 de /auth/me e /auth/logout não aciona o handler', async () => {
  const restoreFetch = mockUnauthorizedFetch()
  let calls = 0
  setUnauthorizedHandler(async () => { calls += 1 })

  try {
    await assert.rejects(apiFetch('/auth/me'), assertApiError401)
    await assert.rejects(apiFetch('/auth/logout', { method: 'POST', body: '{}' }), assertApiError401)
    assert.equal(calls, 0)
  } finally {
    setUnauthorizedHandler(null)
    restoreFetch()
  }
})

test('rajada de 401 em paralelo aciona o handler uma única vez até ele terminar', async () => {
  const restoreFetch = mockUnauthorizedFetch()
  let calls = 0
  let release
  setUnauthorizedHandler(() => {
    calls += 1
    return new Promise(resolve => { release = resolve })
  })

  try {
    const results = await Promise.allSettled([
      apiFetch('/assets/stores'),
      apiFetch('/assistant/conversations'),
      apiFetch('/auth/usage'),
    ])
    assert.deepEqual(results.map(r => r.status), ['rejected', 'rejected', 'rejected'])
    assert.equal(calls, 1)

    // Terminada a renovação, um novo 401 volta a acionar o handler.
    release()
    await new Promise(resolve => setTimeout(resolve, 0))
    await assert.rejects(apiFetch('/assets/stores'), assertApiError401)
    assert.equal(calls, 2)
    release()
  } finally {
    setUnauthorizedHandler(null)
    restoreFetch()
  }
})

test('handler que falha não mascara o ApiError do 401', async () => {
  const restoreFetch = mockUnauthorizedFetch()
  let calls = 0

  try {
    setUnauthorizedHandler(() => { calls += 1; throw new Error('falha síncrona') })
    await assert.rejects(apiFetch('/assets/stores'), assertApiError401)

    setUnauthorizedHandler(async () => { calls += 1; throw new Error('falha assíncrona') })
    await assert.rejects(apiFetch('/assets/stores'), assertApiError401)
    await new Promise(resolve => setTimeout(resolve, 0))

    assert.equal(calls, 2)
  } finally {
    setUnauthorizedHandler(null)
    restoreFetch()
  }
})
