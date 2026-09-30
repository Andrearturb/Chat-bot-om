/**
 * Utilitários puros da Gestão de Usuários — consulta somente leitura
 * (testáveis com node --test). Perfis vêm do Keycloak, via /users.
 */

export const NO_PROFILE = 'SEM_PERFIL'

export const PROFILE_OPTIONS = [
  { value: 'ADMINISTRADOR', label: 'Administrador' },
  { value: 'GERENTE', label: 'Gerente' },
  { value: 'ANALISTA', label: 'Analista' },
  { value: 'DIRETOR', label: 'Diretor' },
  { value: 'CONVIDADO', label: 'Convidado' },
]

export const PROFILE_LABELS = Object.fromEntries(PROFILE_OPTIONS.map(({ value, label }) => [value, label]))

export function profileLabel(profile) {
  return PROFILE_LABELS[profile] || 'Sem perfil'
}

export function normalizeText(value = '') {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
}

/** Busca por nome, e-mail ou usuário; filtro por qualquer perfil da pessoa ou "Sem perfil". */
export function filterUsers(users = [], { query = '', profile = '' } = {}) {
  const term = normalizeText(query)
  return users.filter((user) => {
    const profiles = user.profiles || []
    if (profile === NO_PROFILE && profiles.length) return false
    if (profile && profile !== NO_PROFILE && !profiles.includes(profile)) return false
    if (!term) return true
    return [user.display_name, user.email, user.username].some((field) => normalizeText(field).includes(term))
  })
}

/** Quem ainda não tem perfil (aguardando liberação) vem primeiro; depois, ordem alfabética. */
export function sortUsers(users = []) {
  return [...users].sort((a, b) =>
    Number((a.profiles || []).length > 0) - Number((b.profiles || []).length > 0)
    || String(a.display_name).localeCompare(String(b.display_name), 'pt-BR', { sensitivity: 'base' }))
}

export function summarizeUsers(users = []) {
  return users.reduce(
    (acc, user) => {
      acc.total += 1
      if (user.active_session) acc.activeSessions += 1
      if (!(user.profiles || []).length) acc.withoutProfile += 1
      return acc
    },
    { total: 0, activeSessions: 0, withoutProfile: 0 },
  )
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
