import test from 'node:test'
import assert from 'node:assert/strict'
import { AUTH_ERROR_MESSAGES, getAuthError } from './authErrors.js'

test('auth_error not_released explica que falta a liberação do perfil', () => {
  const err = getAuthError('not_released')
  assert.match(err.title, /não foi liberada/i)
  assert.match(err.message, /gestor de acesso/i)
})

test('auth_error provider_unavailable pede para tentar mais tarde', () => {
  const err = getAuthError('provider_unavailable')
  assert.match(err.title, /indisponível/i)
  assert.match(err.message, /tente novamente/i)
})

test('códigos do modelo antigo deixam de existir', () => {
  for (const code of ['pending', 'disabled', 'no_user']) assert.equal(AUTH_ERROR_MESSAGES[code], undefined)
})

test('auth_error técnico desconhecido recebe fallback amigável', () => {
  const err = getAuthError('qualquer_erro')
  assert.match(err.title, /acesso/i)
  assert.match(err.message, /autenticação/i)
})
