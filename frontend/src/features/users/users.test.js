import test from 'node:test'
import assert from 'node:assert/strict'
import {
  filterUsers,
  formatLastAccess,
  generateTemporaryPassword,
  initials,
  profileLabel,
  statusLabel,
  summarizeUsers,
  usernameFromEmail,
  validateUserForm,
} from './userUtils.js'

const USERS = [
  { id: 1, display_name: 'Administrador OM', email: 'admin.om@local', username: 'admin.om', profile: 'ADMINISTRADOR', status: 'active' },
  { id: 2, display_name: 'João Araújo', email: 'joao@empresa.com', username: 'joao.araujo', profile: 'ANALISTA', status: 'active' },
  { id: 3, display_name: 'Maria Souza', email: 'maria@empresa.com', username: 'maria', profile: null, status: 'pending' },
  { id: 4, display_name: 'Carlos Lima', email: 'carlos@empresa.com', username: 'carlos', profile: 'GERENTE', status: 'disabled' },
]

test('perfis e status são exibidos de forma amigável', () => {
  assert.equal(profileLabel('ADMINISTRADOR'), 'Administrador')
  assert.equal(profileLabel('CONVIDADO'), 'Convidado')
  assert.equal(profileLabel(null), 'Sem perfil')
  assert.equal(statusLabel('active'), 'Ativo')
  assert.equal(statusLabel('pending'), 'Pendente')
  assert.equal(statusLabel('disabled'), 'Bloqueado')
})

test('busca por nome, e-mail e usuário ignora acentos e caixa', () => {
  assert.deepEqual(filterUsers(USERS, { query: 'joao araujo' }).map(u => u.id), [2])
  assert.deepEqual(filterUsers(USERS, { query: 'MARIA@' }).map(u => u.id), [3])
  assert.deepEqual(filterUsers(USERS, { query: 'admin.om' }).map(u => u.id), [1])
  assert.equal(filterUsers(USERS, { query: 'inexistente' }).length, 0)
})

test('filtros de perfil e status combinam com a busca', () => {
  assert.deepEqual(filterUsers(USERS, { status: 'active' }).map(u => u.id), [1, 2])
  assert.deepEqual(filterUsers(USERS, { profile: 'GERENTE' }).map(u => u.id), [4])
  assert.deepEqual(filterUsers(USERS, { query: 'a', status: 'pending' }).map(u => u.id), [3])
})

test('resumo conta status e administradores ativos', () => {
  assert.deepEqual(summarizeUsers(USERS), { total: 4, active: 2, pending: 1, disabled: 1, activeAdmins: 1 })
})

test('usuário é sugerido a partir do e-mail', () => {
  assert.equal(usernameFromEmail('João.Silva@Empresa.com'), 'joao.silva')
  assert.equal(usernameFromEmail('maria+teste@empresa.com'), 'maria.teste')
  assert.equal(usernameFromEmail(''), '')
})

test('iniciais usam primeiro e último nome', () => {
  assert.equal(initials('Ana Paula Souza'), 'AS')
  assert.equal(initials('Ana'), 'A')
  assert.equal(initials(''), '?')
})

test('senha temporária é forte e aleatória', () => {
  const a = generateTemporaryPassword()
  const b = generateTemporaryPassword()
  assert.equal(a.length, 14)
  assert.notEqual(a, b)
  assert.match(a, /[A-Z]/)
  assert.match(a, /[a-z]/)
  assert.match(a, /[0-9]/)
  assert.match(a, /[@#$%&*\-+!?]/)
})

test('validação do formulário de cadastro', () => {
  const valid = { display_name: 'Maria Oliveira', email: 'maria@empresa.com', username: 'maria.oliveira',
                  profile: 'GERENTE', temporary_password: 'Senha#Forte1' }
  assert.deepEqual(validateUserForm(valid), {})
  assert.ok(validateUserForm({ ...valid, display_name: 'Maria' }).display_name)
  assert.ok(validateUserForm({ ...valid, email: 'invalido' }).email)
  assert.ok(validateUserForm({ ...valid, username: 'Maria Oliveira' }).username)
  assert.ok(validateUserForm({ ...valid, profile: '' }).profile)
  assert.ok(validateUserForm({ ...valid, temporary_password: '123' }).temporary_password)
  assert.deepEqual(validateUserForm({ ...valid, temporary_password: '' }, { passwordMode: 'email' }), {})
  assert.deepEqual(validateUserForm({ display_name: 'Maria Oliveira', profile: 'GERENTE' }, { mode: 'edit' }), {})
  // Aprovar um pendente exige perfil; mantê-lo pendente não.
  assert.ok(validateUserForm({ display_name: 'Maria Oliveira', profile: '', status: 'active' }, { mode: 'edit' }).profile)
  assert.deepEqual(validateUserForm({ display_name: 'Maria Oliveira', profile: '', status: 'pending' }, { mode: 'edit' }), {})
})

test('último acesso amigável', () => {
  const now = new Date(2026, 8, 29, 15, 0)
  assert.equal(formatLastAccess(null, now), 'Nunca acessou')
  assert.match(formatLastAccess(new Date(2026, 8, 29, 9, 5).toISOString(), now), /^Hoje, /)
  assert.match(formatLastAccess(new Date(2026, 8, 28, 9, 5).toISOString(), now), /^Ontem, /)
  assert.match(formatLastAccess(new Date(2026, 7, 1, 9, 5).toISOString(), now), /^01\/08\/2026, /)
})
