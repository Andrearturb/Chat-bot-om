/**
 * Utilitários puros da Gestão de Usuários (testáveis com node --test).
 */

export const PROFILE_OPTIONS = [
  { value: 'ADMINISTRADOR', label: 'Administrador' },
  { value: 'ANALISTA', label: 'Analista' },
  { value: 'GERENTE', label: 'Gerente' },
  { value: 'DIRETOR', label: 'Diretor' },
  { value: 'CONVIDADO', label: 'Convidado' },
]

export const PROFILE_LABELS = Object.fromEntries(PROFILE_OPTIONS.map(({ value, label }) => [value, label]))

export const STATUS_LABELS = {
  active: 'Ativo',
  pending: 'Pendente',
  disabled: 'Bloqueado',
}

export const STATUS_OPTIONS = [
  { value: 'active', label: 'Ativo' },
  { value: 'pending', label: 'Pendente' },
  { value: 'disabled', label: 'Bloqueado' },
]

export const PASSWORD_MIN_LENGTH = 8
const USERNAME_RE = /^[a-z0-9][a-z0-9._-]{0,62}[a-z0-9]$/
const EMAIL_RE = /^[^@\s]+@[^@\s]+$/
const PROHIBITED_NAME_CHARS = /[<>&"$%!#?§;*~/\\|^=[\]{}()]/

export function profileLabel(profile) {
  return PROFILE_LABELS[profile] || 'Sem perfil'
}

export function statusLabel(status) {
  return STATUS_LABELS[status] || status || '—'
}

export function normalizeText(value = '') {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
}

/** Busca por nome, e-mail ou usuário, com filtros opcionais de perfil e status. */
export function filterUsers(users = [], { query = '', profile = '', status = '' } = {}) {
  const term = normalizeText(query)
  return users.filter((user) => {
    if (profile && user.profile !== profile) return false
    if (status && user.status !== status) return false
    if (!term) return true
    return [user.display_name, user.email, user.username].some((field) => normalizeText(field).includes(term))
  })
}

export function summarizeUsers(users = []) {
  return users.reduce(
    (acc, user) => {
      acc.total += 1
      if (user.status in acc) acc[user.status] += 1
      if (user.status === 'active' && user.profile === 'ADMINISTRADOR') acc.activeAdmins += 1
      return acc
    },
    { total: 0, active: 0, pending: 0, disabled: 0, activeAdmins: 0 },
  )
}

export function usernameFromEmail(email = '') {
  const local = String(email).trim().toLowerCase().split('@')[0] || ''
  return local
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9._-]+/g, '.')
    .replace(/[._-]{2,}/g, '.')
    .replace(/^[._-]+|[._-]+$/g, '')
    .slice(0, 64)
}

export function initials(name = '', fallback = '?') {
  const parts = String(name).trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return fallback
  const first = parts[0][0] || ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

/** Formata "Último acesso" a partir de ISO UTC ("...Z"). */
export function formatLastAccess(value, now = new Date()) {
  if (!value) return 'Nunca acessou'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Nunca acessou'
  const time = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(date)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diffDays = Math.floor((startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86_400_000)
  if (diffDays <= 0) return `Hoje, ${time}`
  if (diffDays === 1) return `Ontem, ${time}`
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date) + `, ${time}`
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short' }).format(date)
}

/**
 * Senha temporária forte gerada no navegador do administrador. Vai apenas
 * para o backend → Keycloak (temporary=true); não é armazenada no app.
 */
export function generateTemporaryPassword(length = 14, random = globalThis.crypto) {
  const sets = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnopqrstuvwxyz', '23456789', '@#$%&*-+!?']
  const all = sets.join('')
  const size = Math.max(length, 12)
  const values = new Uint32Array(size * 2)
  random.getRandomValues(values)
  // Garante ao menos um caractere de cada grupo e completa com o alfabeto todo.
  const chars = sets.map((set, index) => set[values[index] % set.length])
  for (let i = sets.length; i < size; i += 1) chars.push(all[values[i] % all.length])
  // Embaralha (Fisher–Yates) com a segunda metade dos valores aleatórios.
  for (let i = chars.length - 1; i > 0; i -= 1) {
    const j = values[size + i] % (i + 1)
    ;[chars[i], chars[j]] = [chars[j], chars[i]]
  }
  return chars.join('')
}

export function validateUserForm(form, { mode = 'create', passwordMode = 'temporary' } = {}) {
  const errors = {}
  const name = String(form.display_name || '').trim().replace(/\s+/g, ' ')
  if (name.length < 3) errors.display_name = 'Informe o nome completo.'
  else if (name.split(' ').length < 2) errors.display_name = 'Informe nome e sobrenome.'
  else if (PROHIBITED_NAME_CHARS.test(name)) errors.display_name = 'O nome contém caracteres não permitidos.'

  if (mode === 'create') {
    const email = String(form.email || '').trim()
    if (!EMAIL_RE.test(email)) errors.email = 'Informe um e-mail válido.'
    const username = String(form.username || '').trim().toLowerCase()
    if (username && !USERNAME_RE.test(username)) {
      errors.username = 'Use de 2 a 64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado.'
    }
    if (passwordMode === 'temporary') {
      const password = String(form.temporary_password || '')
      if (password.length < PASSWORD_MIN_LENGTH) {
        errors.temporary_password = `A senha temporária deve ter pelo menos ${PASSWORD_MIN_LENGTH} caracteres.`
      }
    }
  }

  // Usuário pendente pode continuar sem perfil até ser aprovado.
  if (!form.profile && form.status !== 'pending') errors.profile = 'Selecione um perfil.'
  return errors
}
