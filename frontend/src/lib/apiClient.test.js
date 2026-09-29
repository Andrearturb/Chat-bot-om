import test from 'node:test'
import assert from 'node:assert/strict'

import { apiFetch, setCsrfToken } from './apiClient.js'

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
