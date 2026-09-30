import test from 'node:test'
import assert from 'node:assert/strict'
import {
  filterUsers,
  formatLastAccess,
  initials,
  NO_PROFILE,
  profileLabel,
  sortUsers,
  summarizeUsers,
} from './userUtils.js'

const USERS = [
  { id: 1, display_name: 'Administrador OM', email: 'admin.om@chatbot-om.local', username: 'admin.om',
    profile: 'ADMINISTRADOR', profiles: ['ADMINISTRADOR'], active_session: true },
  { id: 2, display_name: 'João Araújo', email: 'joao@empresa.com', username: 'joao.araujo',
    profile: 'GERENTE', profiles: ['GERENTE', 'ANALISTA'], active_session: false },
  { id: 3, display_name: 'Maria Souza', email: 'maria@empresa.com', username: 'maria',
    profile: null, profiles: [], active_session: false },
]

test('perfis são exibidos de forma amigável', () => {
  assert.equal(profileLabel('ADMINISTRADOR'), 'Administrador')
  assert.equal(profileLabel('CONVIDADO'), 'Convidado')
  assert.equal(profileLabel(null), 'Sem perfil')
})

test('busca por nome, e-mail e usuário ignora acentos e caixa', () => {
  assert.deepEqual(filterUsers(USERS, { query: 'joao araujo' }).map(u => u.id), [2])
  assert.deepEqual(filterUsers(USERS, { query: 'MARIA@' }).map(u => u.id), [3])
  assert.deepEqual(filterUsers(USERS, { query: 'admin.om' }).map(u => u.id), [1])
  assert.equal(filterUsers(USERS, { query: 'inexistente' }).length, 0)
})

test('filtro de perfil considera todos os perfis da pessoa', () => {
  assert.deepEqual(filterUsers(USERS, { profile: 'ANALISTA' }).map(u => u.id), [2])
  assert.deepEqual(filterUsers(USERS, { profile: 'GERENTE', query: 'joão' }).map(u => u.id), [2])
})

test('filtro "Sem perfil" mostra as contas ainda não liberadas', () => {
  assert.deepEqual(filterUsers(USERS, { profile: NO_PROFILE }).map(u => u.id), [3])
})

test('resumo conta total, sessões ativas e contas sem perfil', () => {
  assert.deepEqual(summarizeUsers(USERS), { total: 3, activeSessions: 1, withoutProfile: 1 })
  assert.deepEqual(summarizeUsers([]), { total: 0, activeSessions: 0, withoutProfile: 0 })
})

test('ordenação mostra primeiro quem aguarda liberação e depois por nome', () => {
  assert.deepEqual(sortUsers(USERS).map(u => u.id), [3, 1, 2])
})

test('iniciais do nome', () => {
  assert.equal(initials('João Araújo'), 'JA')
  assert.equal(initials('Maria'), 'M')
  assert.equal(initials(''), '?')
})

test('último acesso em linguagem amigável', () => {
  const now = new Date(2026, 8, 30, 15, 0)
  assert.equal(formatLastAccess(null, now), 'Nunca acessou')
  assert.equal(formatLastAccess(new Date(2026, 8, 30, 9, 5).toISOString(), now), 'Hoje, 09:05')
  assert.match(formatLastAccess(new Date(2026, 8, 29, 9, 5).toISOString(), now), /^Ontem, 09:05$/)
})
