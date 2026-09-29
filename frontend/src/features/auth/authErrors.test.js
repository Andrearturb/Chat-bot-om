import test from 'node:test'
import assert from 'node:assert/strict'
import { getAuthError } from './authErrors.js'

test('auth_error pending mostra mensagem de acesso aguardando liberação', () => {
  const err = getAuthError('pending')
  assert.match(err.title, /aguardando/i)
  assert.match(err.message, /autenticada/i)
})

test('auth_error técnico desconhecido recebe fallback amigável', () => {
  const err = getAuthError('qualquer_erro')
  assert.match(err.title, /acesso/i)
  assert.match(err.message, /autenticação/i)
})
